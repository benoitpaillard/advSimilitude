from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator

KNOT_TO_MS = 0.514444
DEFAULT_REF_DIAMETER_M = 0.300


@dataclass
class ScalingExponents:
    force_diam_exp: float
    moment_diam_exp: float
    power_diam_exp: float


SCALING_MODES = {
    # Homothétie 3D complète
    "3d": ScalingExponents(force_diam_exp=2.0, moment_diam_exp=3.0, power_diam_exp=2.0),
    # Interprétation 2D extrudée: la hauteur hors-plan reste inchangée
    "2d": ScalingExponents(force_diam_exp=1.0, moment_diam_exp=2.0, power_diam_exp=1.0),
}


class Surrogate3D:
    """Interpolateur robuste (linéaire + nearest en secours) sur (V, lambda, Bmax)."""

    def __init__(self, df: pd.DataFrame, input_cols: Iterable[str], output_cols: Iterable[str]) -> None:
        self.input_cols = list(input_cols)
        self.output_cols = list(output_cols)
        pts = df[self.input_cols].to_numpy(dtype=float)
        self._linear: Dict[str, LinearNDInterpolator] = {}
        self._nearest: Dict[str, NearestNDInterpolator] = {}
        for col in self.output_cols:
            vals = df[col].to_numpy(dtype=float)
            self._linear[col] = LinearNDInterpolator(pts, vals, fill_value=np.nan)
            self._nearest[col] = NearestNDInterpolator(pts, vals)

    def __call__(self, V_ms: float, lam: float, bmax_deg: float) -> Dict[str, float]:
        p = np.array([[float(V_ms), float(lam), float(bmax_deg)]], dtype=float)
        out: Dict[str, float] = {}
        for col in self.output_cols:
            v = float(self._linear[col](p)[0])
            if np.isnan(v):
                v = float(self._nearest[col](p)[0])
            out[col] = v
        return out


def knots_to_ms(knots: float) -> float:
    return knots * KNOT_TO_MS


def ms_to_knots(ms: float) -> float:
    return ms / KNOT_TO_MS


def load_summary(path: str | Path, summary_sheet: str = "Summary") -> pd.DataFrame:
    """Charge uniquement la feuille Summary, ce qui reste rapide même pour un xlsx énorme."""
    wb = load_workbook(filename=path, read_only=True, data_only=True)
    if summary_sheet not in wb.sheetnames:
        raise ValueError(f"Feuille '{summary_sheet}' introuvable. Feuilles disponibles: {wb.sheetnames[:10]} ...")
    ws = wb[summary_sheet]

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("La feuille Summary est vide.")

    headers = list(rows[0])
    if headers[0] is None:
        headers[0] = "run"
    headers = [str(h).strip() if h is not None else f"col_{i}" for i, h in enumerate(headers)]

    data = pd.DataFrame(rows[1:], columns=headers)
    data = data.dropna(how="all").copy()

    for col in data.columns:
        if col == "run":
            continue
        data[col] = pd.to_numeric(data[col], errors="coerce")

    data = data.dropna(subset=["Ve [m/s]", "Lambda [-]", "Bmax[°]"])

    # Grandeurs utiles avec signe plus intuitif côté propulsion.
    if "thrust[N]" in data.columns:
        data["thrust_propulsive[N]"] = -data["thrust[N]"]
    if "sideforce[N]" in data.columns:
        data["sideforce_abs[N]"] = data["sideforce[N]"].abs()

    return data.reset_index(drop=True)


def build_surrogate(df: pd.DataFrame) -> Surrogate3D:
    needed = [
        "eta_Cp[%]",
        "thrust[N]",
        "thrust_propulsive[N]",
        "sideforce[N]",
        "sideforce_abs[N]",
        "Mh max",
        "DHP[W]",
        "Cp_mean[N.m]",
        "Cd_mean[N.m]",
        "kth[-]",
        "kqh[-]",
        "ktvoith[-]",
        "kqvoith[-]",
        "ks[-]",
        "kd[-]",
    ]
    output_cols = [c for c in needed if c in df.columns]
    return Surrogate3D(df, ["Ve [m/s]", "Lambda [-]", "Bmax[°]"], output_cols)


def equivalent_reference_speed(
    V_target_ms: float,
    D_target_m: float,
    D_ref_m: float = DEFAULT_REF_DIAMETER_M,
    iso_reynolds: bool = True,
) -> float:
    """
    Cas équivalent dans la base P300.
    iso_reynolds=True -> V_ref = V_target * D_target / D_ref
    iso_reynolds=False -> V_ref = V_target
    """
    if iso_reynolds:
        return V_target_ms * D_target_m / D_ref_m
    return V_target_ms


def rescale_outputs(
    base: Dict[str, float],
    V_target_ms: float,
    V_ref_ms: float,
    D_target_m: float,
    D_ref_m: float,
    scaling_mode: str = "3d",
) -> Dict[str, float]:
    if scaling_mode not in SCALING_MODES:
        raise ValueError(f"scaling_mode doit être parmi {list(SCALING_MODES)}")
    exps = SCALING_MODES[scaling_mode]

    out = dict(base)
    v_ratio = V_target_ms / V_ref_ms
    d_ratio = D_target_m / D_ref_m

    def scale(name: str, v_exp: float, d_exp: float) -> None:
        if name in out and out[name] is not None:
            out[name] = float(out[name]) * (v_ratio ** v_exp) * (d_ratio ** d_exp)

    # efforts
    scale("thrust[N]", 2.0, exps.force_diam_exp)
    scale("thrust_propulsive[N]", 2.0, exps.force_diam_exp)
    scale("sideforce[N]", 2.0, exps.force_diam_exp)
    scale("sideforce_abs[N]", 2.0, exps.force_diam_exp)

    # moments
    scale("Mh max", 2.0, exps.moment_diam_exp)
    scale("Cp_mean[N.m]", 2.0, exps.moment_diam_exp)
    scale("Cd_mean[N.m]", 2.0, exps.moment_diam_exp)

    # puissance
    scale("DHP[W]", 3.0, exps.power_diam_exp)

    # Recalcule les grandeurs dérivées à partir des variables signées mises à l'échelle.
    if "thrust[N]" in out:
        out["thrust_propulsive[N]"] = -float(out["thrust[N]"])
    if "sideforce[N]" in out:
        out["sideforce_abs[N]"] = abs(float(out["sideforce[N]"]))

    # eta et coefficients restent inchangés (à premier ordre)
    return out


def evaluate_target_case(
    surrogate: Surrogate3D,
    V_target_ms: float,
    lam: float,
    bmax_deg: float,
    D_target_m: float,
    D_ref_m: float = DEFAULT_REF_DIAMETER_M,
    iso_reynolds: bool = True,
    scaling_mode: str = "3d",
) -> Dict[str, float]:
    V_ref_ms = equivalent_reference_speed(V_target_ms, D_target_m, D_ref_m, iso_reynolds)
    base = surrogate(V_ref_ms, lam, bmax_deg)
    scaled = rescale_outputs(base, V_target_ms, V_ref_ms, D_target_m, D_ref_m, scaling_mode)
    scaled.update(
        {
            "V_target_ms": float(V_target_ms),
            "V_target_kn": float(ms_to_knots(V_target_ms)),
            "lambda": float(lam),
            "Bmax_deg": float(bmax_deg),
            "D_target_m": float(D_target_m),
            "D_ref_m": float(D_ref_m),
            "V_reference_in_database_ms": float(V_ref_ms),
            "omega_target_rad_s": float(2.0 * V_target_ms / (lam * D_target_m)),
            "omega_target_rpm": float(2.0 * V_target_ms / (lam * D_target_m) * 60.0 / (2.0 * np.pi)),
            "iso_reynolds": bool(iso_reynolds),
            "scaling_mode": scaling_mode,
        }
    )
    return scaled


def optimize_operating_point(
    surrogate: Surrogate3D,
    V_target_ms: float,
    D_target_m: float,
    lambda_candidates: Iterable[float],
    bmax_candidates: Iterable[float],
    D_ref_m: float = DEFAULT_REF_DIAMETER_M,
    iso_reynolds: bool = True,
    scaling_mode: str = "3d",
    objective: str = "max_eta",
    min_thrust_propulsive_N: Optional[float] = None,
    max_Mh_Nm: Optional[float] = None,
    max_DHP_W: Optional[float] = None,
) -> Tuple[Dict[str, float], pd.DataFrame]:
    rows = []
    for lam in lambda_candidates:
        for bmax in bmax_candidates:
            r = evaluate_target_case(
                surrogate=surrogate,
                V_target_ms=V_target_ms,
                lam=float(lam),
                bmax_deg=float(bmax),
                D_target_m=D_target_m,
                D_ref_m=D_ref_m,
                iso_reynolds=iso_reynolds,
                scaling_mode=scaling_mode,
            )
            feasible = True
            if min_thrust_propulsive_N is not None and r.get("thrust_propulsive[N]", -np.inf) < min_thrust_propulsive_N:
                feasible = False
            if max_Mh_Nm is not None and r.get("Mh max", np.inf) > max_Mh_Nm:
                feasible = False
            if max_DHP_W is not None and r.get("DHP[W]", np.inf) > max_DHP_W:
                feasible = False
            r["feasible"] = feasible
            rows.append(r)

    table = pd.DataFrame(rows)
    table["thrust_per_power"] = table["thrust_propulsive[N]"] / table["DHP[W]"].clip(lower=1e-9)
    feasible = table[table["feasible"]].copy()
    if feasible.empty:
        raise RuntimeError("Aucun point faisable avec les contraintes données.")

    if objective == "max_eta":
        idx = feasible["eta_Cp[%]"].idxmax()
    elif objective == "min_dhp":
        idx = feasible["DHP[W]"].idxmin()
    elif objective == "max_thrust":
        idx = feasible["thrust_propulsive[N]"].idxmax()
    elif objective == "max_thrust_per_power":
        idx = feasible["thrust_per_power"].idxmax()
    else:
        raise ValueError("objective doit être parmi: max_eta, min_dhp, max_thrust, max_thrust_per_power")

    best = feasible.loc[idx].to_dict()
    return best, table.sort_values(["lambda", "Bmax_deg"]).reset_index(drop=True)


def suggest_raw_bmax_envelope(df: pd.DataFrame) -> pd.DataFrame:
    """Enveloppe brute: meilleur eta par lambda sur toute la base, sans condition cible."""
    work = df.copy()
    idx = work.groupby("Lambda [-]")["eta_Cp[%]"].idxmax()
    law = work.loc[idx, ["Ve [m/s]", "Lambda [-]", "Bmax[°]", "eta_Cp[%]"]].sort_values("Lambda [-]")
    law = law.rename(
        columns={
            "Ve [m/s]": "V_base_ms",
            "Lambda [-]": "lambda",
            "Bmax[°]": "Bmax_opt_deg",
            "eta_Cp[%]": "eta_opt_pct",
        }
    )
    return law.reset_index(drop=True)


def suggest_bmax_law_for_target(
    surrogate: Surrogate3D,
    V_target_ms: float,
    D_target_m: float,
    lambda_candidates: Iterable[float],
    bmax_candidates: Iterable[float],
    D_ref_m: float = DEFAULT_REF_DIAMETER_M,
    iso_reynolds: bool = True,
    scaling_mode: str = "3d",
    objective: str = "max_eta",
    min_thrust_propulsive_N: Optional[float] = None,
    max_Mh_Nm: Optional[float] = None,
    max_DHP_W: Optional[float] = None,
) -> pd.DataFrame:
    """Loi discrète cohérente avec le cas cible: pour chaque lambda, meilleur Bmax au point demandé."""
    rows = []
    for lam in lambda_candidates:
        try:
            best, _ = optimize_operating_point(
                surrogate=surrogate,
                V_target_ms=V_target_ms,
                D_target_m=D_target_m,
                lambda_candidates=[lam],
                bmax_candidates=bmax_candidates,
                D_ref_m=D_ref_m,
                iso_reynolds=iso_reynolds,
                scaling_mode=scaling_mode,
                objective=objective,
                min_thrust_propulsive_N=min_thrust_propulsive_N,
                max_Mh_Nm=max_Mh_Nm,
                max_DHP_W=max_DHP_W,
            )
            rows.append(
                {
                    "lambda": best["lambda"],
                    "feasible": True,
                    "status": "ok",
                    "Bmax_opt_deg": best["Bmax_deg"],
                    "eta_opt_pct": best.get("eta_Cp[%]"),
                    "thrust_propulsive_N": best.get("thrust_propulsive[N]"),
                    "sideforce_abs_N": best.get("sideforce_abs[N]"),
                    "Mh_max_Nm": best.get("Mh max"),
                    "DHP_W": best.get("DHP[W]"),
                    "omega_rpm": best.get("omega_target_rpm"),
                    "V_reference_in_database_ms": best.get("V_reference_in_database_ms"),
                }
            )
        except RuntimeError:
            rows.append(
                {
                    "lambda": float(lam),
                    "feasible": False,
                    "status": "no_feasible_point",
                    "Bmax_opt_deg": np.nan,
                    "eta_opt_pct": np.nan,
                    "thrust_propulsive_N": np.nan,
                    "sideforce_abs_N": np.nan,
                    "Mh_max_Nm": np.nan,
                    "DHP_W": np.nan,
                    "omega_rpm": np.nan,
                    "V_reference_in_database_ms": np.nan,
                }
            )
    return pd.DataFrame(rows).sort_values("lambda").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mise à l'échelle et optimisation d'un ADV-propulse à partir d'une base P300.")
    parser.add_argument("xlsx", help="Chemin du fichier xlsx")
    parser.add_argument("--diameter-mm", type=float, required=True, help="Diamètre orbital cible en mm")
    parser.add_argument("--speed-kn", type=float, required=True, help="Vitesse cible en noeuds")
    parser.add_argument("--lambda", dest="lam", type=float, default=None, help="Lambda imposé")
    parser.add_argument("--bmax", type=float, default=None, help="Bmax imposé en degrés")
    parser.add_argument("--optimize", action="store_true", help="Optimise lambda/Bmax au lieu d'évaluer un point imposé")
    parser.add_argument("--objective", choices=["max_eta", "min_dhp", "max_thrust", "max_thrust_per_power"], default="max_eta")
    parser.add_argument("--min-thrust-N", type=float, default=None)
    parser.add_argument("--max-Mh-Nm", type=float, default=None)
    parser.add_argument("--max-DHP-W", type=float, default=None)
    parser.add_argument("--scaling-mode", choices=["3d", "2d"], default="3d")
    parser.add_argument("--no-iso-re", action="store_true", help="Utilise le même V dans la base au lieu du cas iso-Re")
    parser.add_argument("--reference-diameter-mm", type=float, default=300.0)
    args = parser.parse_args()

    df = load_summary(args.xlsx)
    surrogate = build_surrogate(df)

    V_target_ms = knots_to_ms(args.speed_kn)
    D_target_m = args.diameter_mm / 1000.0
    D_ref_m = args.reference_diameter_mm / 1000.0
    iso_reynolds = not args.no_iso_re

    if args.optimize:
        lambda_candidates = sorted(df["Lambda [-]"].dropna().unique())
        bmax_candidates = sorted(df["Bmax[°]"].dropna().unique())
        best, table = optimize_operating_point(
            surrogate=surrogate,
            V_target_ms=V_target_ms,
            D_target_m=D_target_m,
            lambda_candidates=lambda_candidates,
            bmax_candidates=bmax_candidates,
            D_ref_m=D_ref_m,
            iso_reynolds=iso_reynolds,
            scaling_mode=args.scaling_mode,
            objective=args.objective,
            min_thrust_propulsive_N=args.min_thrust_N,
            max_Mh_Nm=args.max_Mh_Nm,
            max_DHP_W=args.max_DHP_W,
        )
        print("=== Meilleur point ===")
        for k in [
            "lambda",
            "Bmax_deg",
            "eta_Cp[%]",
            "thrust_propulsive[N]",
            "sideforce_abs[N]",
            "Mh max",
            "DHP[W]",
            "omega_target_rad_s",
            "omega_target_rpm",
            "V_reference_in_database_ms",
        ]:
            if k in best:
                print(f"{k}: {best[k]}")
        print("\n=== Loi discrète Bmax_opt(lambda) cohérente avec le cas cible ===")
        law = suggest_bmax_law_for_target(
            surrogate=surrogate,
            V_target_ms=V_target_ms,
            D_target_m=D_target_m,
            lambda_candidates=lambda_candidates,
            bmax_candidates=bmax_candidates,
            D_ref_m=D_ref_m,
            iso_reynolds=iso_reynolds,
            scaling_mode=args.scaling_mode,
            objective=args.objective,
            min_thrust_propulsive_N=args.min_thrust_N,
            max_Mh_Nm=args.max_Mh_Nm,
            max_DHP_W=args.max_DHP_W,
        )
        print(law.to_string(index=False))
        print("\n=== Enveloppe brute de la base CFD (indépendante du cas cible) ===")
        print(suggest_raw_bmax_envelope(df).to_string(index=False))
        print("\n=== Top 10 faisables ===")
        sort_col = {
            "max_eta": "eta_Cp[%]",
            "min_dhp": "DHP[W]",
            "max_thrust": "thrust_propulsive[N]",
            "max_thrust_per_power": "thrust_per_power",
        }[args.objective]
        ascending = args.objective == "min_dhp"
        cols = [
            c
            for c in [
                "lambda",
                "Bmax_deg",
                "eta_Cp[%]",
                "thrust_propulsive[N]",
                "sideforce_abs[N]",
                "Mh max",
                "DHP[W]",
                "thrust_per_power",
            ]
            if c in table.columns
        ]
        print(table[table["feasible"]][cols].sort_values(sort_col, ascending=ascending).head(10).to_string(index=False))
    else:
        if args.lam is None or args.bmax is None:
            raise ValueError("Sans --optimize, il faut fournir --lambda et --bmax")
        result = evaluate_target_case(
            surrogate=surrogate,
            V_target_ms=V_target_ms,
            lam=args.lam,
            bmax_deg=args.bmax,
            D_target_m=D_target_m,
            D_ref_m=D_ref_m,
            iso_reynolds=iso_reynolds,
            scaling_mode=args.scaling_mode,
        )
        print("=== Evaluation d'un point ===")
        for k, v in result.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
