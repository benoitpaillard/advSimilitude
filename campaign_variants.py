"""Corrections to the reference database using only audited, periodic campaign runs.

Interpolate ratios for thrust, power and peak Mh. Signed quantities that can cross
zero use additive corrections normalized by V². Never extrapolate the corrections
or silently replace an explicitly rejected run with an interpolated result.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd
from scipy.interpolate import LinearNDInterpolator

VARIANTS = {
    'reference': ('Référence — σ=1,425 ; DIR=−2,5°', 1.425, -2.5),
    'dir_plus2': ('DIR=+2° — σ=1,425', 1.425, 2.0),
    'sigma_1p7': ('Solidité σ=1,7 — DIR=−2,5°', 1.7, -2.5),
    'combined_1p7': ('Combinaison — σ=1,7 ; DIR=+2°', 1.7, 2.0),
}
INPUTS = ['Ve [m/s]', 'Lambda [-]', 'Bmax[°]']
RATIOS = ['thrust[N]', 'DHP[W]', 'Mh max']
DELTAS = ['sideforce[N]', 'Cd_mean[N.m]']


def load_campaign(directory=None):
    root = Path(directory) if directory is not None else Path(__file__).resolve().parent
    metadata = json.loads((root / 'campaign_metadata.json').read_text())
    for file, checksum in [('campaign_results.csv', metadata['results_sha256']),
                           (metadata['reference_database'], metadata['reference_sha256'])]:
        if hashlib.sha256((root / file).read_bytes()).hexdigest() != checksum:
            raise ValueError(f'Les données de campagne ne correspondent pas au fichier {file}.')
    return pd.read_csv(root / 'campaign_results.csv'), metadata


class CampaignSurrogate:
    def __init__(self, reference, reference_df, variant, campaign_df):
        if variant not in VARIANTS or variant == 'reference':
            raise ValueError(f'Variante inconnue : {variant}')
        self.reference = reference
        self.variant = variant
        self.output_cols = reference.output_cols
        self.database_orbital_diameter_m = reference.database_orbital_diameter_m
        self.cleaning_report = reference.cleaning_report
        self.all_runs = campaign_df[campaign_df.variant == variant].copy()
        finite = np.isfinite(self.all_runs[RATIOS + DELTAS].to_numpy()).all(axis=1)
        accepted = (self.all_runs.converged & ~self.all_runs.diverged & finite
                    & (self.all_runs['thrust[N]'] < 0) & (self.all_runs['DHP[W]'] > 0)
                    & self.all_runs['eta_Cp[%]'].between(0, 100, inclusive='neither')
                    & (self.all_runs['Mh max'] > 0))
        self.runs = self.all_runs[accepted].copy()
        self.runs['thrust_propulsive[N]'] = -self.runs['thrust[N]']
        self.runs['sideforce_abs[N]'] = self.runs['sideforce[N]'].abs()
        self.rejected = {self._key(*r[INPUTS]): r['run'] for _, r in self.all_runs[~accepted].iterrows()}
        self.measured = {self._key(*r[INPUTS]): r['run'] for _, r in self.runs.iterrows()}
        base = reference_df.set_index('run').loc[self.runs.run]
        coefficients = []
        for col in RATIOS:
            coefficients.append(self.runs[col].to_numpy() / base[col].to_numpy())
        for col in DELTAS:
            coefficients.append((self.runs[col].to_numpy() - base[col].to_numpy()) / self.runs[INPUTS[0]].to_numpy()**2)
        self._linear = LinearNDInterpolator(self.runs[INPUTS].to_numpy(), np.array(coefficients).T, fill_value=np.nan)
        for name, col in [('v',INPUTS[0]), ('lambda',INPUTS[1]), ('bmax',INPUTS[2])]:
            setattr(self, name+'_min', float(self.runs[col].min()))
            setattr(self, name+'_max', float(self.runs[col].max()))
        self.lambda_candidates = reference.lambda_candidates
        self.bmax_candidates = reference.bmax_candidates

    @staticmethod
    def _key(v, lam, bmax):
        return tuple(round(float(x), 10) for x in (v,lam,bmax))

    @lru_cache(maxsize=4096)
    def _evaluate(self, v, lam, bmax):
        key = self._key(v,lam,bmax)
        result = {col: np.nan for col in self.output_cols}
        result.update(campaign_variant=self.variant, campaign_supported=False,
                      campaign_run='', campaign_quality='hors domaine', campaign_warning='',
                      **{'sigma[°]': VARIANTS[self.variant][1], 'DIR[°]': VARIANTS[self.variant][2]})
        if key in self.rejected:
            result.update(campaign_quality='cas rejeté', campaign_run=self.rejected[key],
                          campaign_warning='Cas calculé sans convergence périodique ou avec une anomalie ; résultat exclu.')
            return result
        coeff = np.asarray(self._linear([[v,lam,bmax]]))[0]
        if not np.isfinite(coeff).all():
            result['campaign_warning'] = 'Hors du domaine couvert par les cas convergés de cette variante ; aucune extrapolation.'
            return result
        base = self.reference(v,lam,bmax)
        if base.get('_used_nearest_fallback'):
            result['campaign_warning'] = 'Hors du domaine interpolable de la base de référence.'
            return result
        result.update(base)
        for col, factor in zip(RATIOS,coeff[:3]):
            result[col] = base[col]*factor
        for col, delta in zip(DELTAS,coeff[3:]):
            result[col] = base[col]+delta*v**2
        result['thrust_propulsive[N]'] = -result['thrust[N]']
        result['sideforce_abs[N]'] = abs(result['sideforce[N]'])
        result['Cp_mean[N.m]'] = result['DHP[W]']/(2*v/(lam*self.database_orbital_diameter_m))
        result['eta_Cp[%]'] = -result['thrust[N]']*v/result['DHP[W]']*100
        for col in ['kth[-]', 'ktvoith[-]', 'ks[-]']:
            if col in base:
                result[col] = base[col]*coeff[0]
        for col in ['kqh[-]', 'kqvoith[-]', 'kd[-]']:
            if col in base:
                result[col] = base[col]*coeff[1]
        if not (result['thrust_propulsive[N]'] > 0 and result['DHP[W]'] > 0 and 0 < result['eta_Cp[%]'] < 100):
            result.update({col: np.nan for col in self.output_cols})
            result['campaign_warning'] = 'La correction interpolée produit un bilan non propulsif ou un rendement non physique ; point exclu.'
            return result
        warning = 'Pics mécaniques à valider séparément : écart de 20 % sur Mh max du pilote de référence.'
        if v > 12 and self.variant != 'dir_plus2':
            warning += ' Couverture clairsemée entre 12 et 30 m/s ; contrôle V30 limité à certains régimes.'
        result.update(campaign_supported=True, campaign_run=self.measured.get(key,''),
                      campaign_quality='calcul CFD convergé' if key in self.measured else 'correction interpolée entre cas convergés',
                      campaign_warning=warning, _used_nearest_fallback=False)
        return result

    def __call__(self,v,lam,bmax):
        return dict(self._evaluate(float(v),float(lam),float(bmax)))

    def domain_diagnostics(self,v,lam,bmax):
        diagnostics = self.reference.domain_diagnostics(v,lam,bmax)
        result = self(v,lam,bmax)
        supported = bool(result['campaign_supported'])
        diagnostics.update(domain_ok=bool(diagnostics['domain_ok'] and supported))
        if not supported:
            diagnostics['domain_warning'] = result['campaign_warning']
        diagnostics.update({k:val for k,val in result.items() if k.startswith('campaign_')})
        return diagnostics
