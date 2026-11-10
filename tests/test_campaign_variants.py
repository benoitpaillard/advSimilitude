from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import adv_propulse_scaling_optimizer as core
from campaign_variants import CampaignSurrogate, load_campaign


@pytest.fixture(scope='module')
def data():
    df = core.load_summary(ROOT/'adv_propulse_database_Lpale0.375m.npz')
    return df, core.build_surrogate(df), load_campaign()[0]


@pytest.fixture(scope='module')
def models(data):
    df, reference, campaign = data
    return {v: CampaignSurrogate(reference,df,v,campaign) for v in ['dir_plus2','sigma_1p7','combined_1p7']}


def test_campaign_counts_and_frozen_reference(data,models):
    df, reference, campaign = data
    assert len(campaign) == 1705
    assert campaign.converged.sum() == 1301
    assert {v:len(m.runs) for v,m in models.items()} == {'dir_plus2':679,'sigma_1p7':368,'combined_1p7':253}
    # The reference remains the existing database; corrections are opt-in.
    row = df[df.run == 'run.50'].iloc[0]
    result = reference(2,1.3,15)
    assert result['DHP[W]'] == pytest.approx(row['DHP[W]'])
    assert result['Mh max'] == pytest.approx(row['Mh max'])


def test_all_1300_converged_knots_reproduce_direct_summaries(models):
    for model in models.values():
        for _,row in model.runs.iterrows():
            out = model(row['Ve [m/s]'],row['Lambda [-]'],row['Bmax[°]'])
            assert out['campaign_supported']
            assert out['campaign_run'] == row.run
            assert out['campaign_quality'] == 'calcul CFD convergé'
            for col in ['thrust[N]','DHP[W]','Mh max','sideforce[N]','Cd_mean[N.m]']:
                assert out[col] == pytest.approx(row[col],rel=1e-8,abs=1e-8)


@pytest.mark.parametrize('variant,v,lam,bmax',[
    ('dir_plus2',8,1.7,17.5),('combined_1p7',4,1.7,12.5),
    ('combined_1p7',30,.5,25),('sigma_1p7',30,.8,25),
])
def test_known_anomalies_are_never_used_or_repaired(models,variant,v,lam,bmax):
    out = models[variant](v,lam,bmax)
    assert not out['campaign_supported']
    assert out['campaign_quality'] == 'cas rejeté'
    assert np.isnan(out['DHP[W]'])


def test_no_nearest_extrapolation_or_rejected_case_filling(models):
    model = models['sigma_1p7']
    for args in [(31,1.1,17.5),(30,.5,15),(10,2,20)]:
        out = model(*args)
        assert not out['campaign_supported']
        assert np.isnan(out['DHP[W]'])
        assert not model.domain_diagnostics(*args)['domain_ok']


def test_interpolated_balance_and_scaling(models):
    model = models['sigma_1p7']
    out = model(9,1.15,18)
    assert out['campaign_supported']
    assert out['campaign_quality'].startswith('correction interpolée')
    assert out['eta_Cp[%]'] == pytest.approx(-out['thrust[N]']*9/out['DHP[W]']*100)
    assert out['DHP[W]'] == pytest.approx(out['Cp_mean[N.m]']*2*9/(1.15*.3))
    point = core.evaluate_target_case(model,9,1.15,18,.3,iso_reynolds=False,scaling_mode='2d',target_blade_length_m=.75,ref_blade_length_m=.375)
    for col in ['DHP[W]','Mh max','thrust[N]']:
        assert point[col] == pytest.approx(out[col]*2)
    assert point['campaign_supported']
    assert point['sigma[°]'] == 1.7
    assert point['eta_Cp[%]'] == pytest.approx(out['eta_Cp[%]'])


def test_optimizer_excludes_unconverged_and_unsupported_candidates(models):
    best, table = core.optimize_operating_point(models['sigma_1p7'],30,.3,[.5,.8,1.1,1.7],[12.5,17.5,25],iso_reynolds=False)
    assert best['campaign_supported']
    assert np.isfinite(best['DHP[W]'])
    rejected = table[~table.campaign_supported]
    assert len(rejected) >= 5
    assert not rejected.feasible.any()
    assert set(rejected.status) == {'campaign_unsupported'}
    with pytest.raises(RuntimeError):
        core.optimize_operating_point(models['sigma_1p7'],31,.3,[1.1],[17.5],iso_reynolds=False)
