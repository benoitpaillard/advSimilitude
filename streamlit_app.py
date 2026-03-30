from __future__ import annotations

import importlib.util
import io
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd
import streamlit as st

APP_TITLE = "ADV Propulse - Application navigateur"
CORE_SCRIPT_NAME = "adv_propulse_scaling_optimizer.py"


def resource_path(filename: str) -> Path:
    return Path(__file__).resolve().parent / filename


@st.cache_resource
def load_core_module():
    core_path = resource_path(CORE_SCRIPT_NAME)
    if not core_path.exists():
        raise FileNotFoundError(f"Le fichier coeur '{CORE_SCRIPT_NAME}' est introuvable: {core_path}")
    spec = importlib.util.spec_from_file_location("adv_propulse_core_streamlit", core_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Impossible de charger {core_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["adv_propulse_core_streamlit"] = module
    spec.loader.exec_module(module)
    return module


@st.cache_data(show_spinner=False)
def load_summary_from_bytes(file_bytes: bytes) -> Tuple[str, pd.DataFrame]:
    core = load_core_module()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    df = core.load_summary(tmp_path)
    return tmp_path, df


@st.cache_resource(show_spinner=False)
def build_surrogate_from_bytes(file_bytes: bytes):
    core = load_core_module()
    tmp_path, df = load_summary_from_bytes(file_bytes)
    surrogate = core.build_surrogate(df)
    return tmp_path, df, surrogate


def dataframe_to_download_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def report_text(best: Dict[str, Any], law: pd.DataFrame | None, raw_env: pd.DataFrame | None, top10: pd.DataFrame | None) -> str:
    lines = ["=== Meilleur point ==="]
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
            lines.append(f"{k}: {best[k]}")
    if law is not None:
        lines.append("")
        lines.append("=== Loi discrete Bmax_opt(lambda) coherente avec le cas cible ===")
        lines.append(law.to_string(index=False))
    if raw_env is not None:
        lines.append("")
        lines.append("=== Enveloppe brute de la base CFD ===")
        lines.append(raw_env.to_string(index=False))
    if top10 is not None:
        lines.append("")
        lines.append("=== Top 10 faisables ===")
        lines.append(top10.to_string(index=False))
    return "\n".join(lines)


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    core = load_core_module()

    st.title(APP_TITLE)
    st.caption("Interface web cross-platform pour la mise a l'echelle et l'optimisation ADV-propulse.")

    with st.sidebar:
        st.header("Entrees")
        uploaded = st.file_uploader("Fichier Excel (.xlsx)", type=["xlsx"])
        mode = st.radio("Mode", ["Optimisation", "Evaluation d'un point"], index=0)
        diameter_mm = st.number_input("Diametre cible [mm]", min_value=1.0, value=200.0, step=10.0)
        speed_kn = st.number_input("Vitesse cible [kn]", min_value=0.1, value=10.0, step=0.5)
        reference_diameter_mm = st.number_input("Diametre de reference [mm]", min_value=1.0, value=300.0, step=10.0)
        iso_re = st.checkbox("Correction iso-Reynolds", value=True)
        scaling_mode = st.selectbox("Mode d'echelle", ["3d", "2d"], index=0)

        if mode == "Optimisation":
            objective = st.selectbox(
                "Objectif",
                ["max_eta", "min_dhp", "max_thrust", "max_thrust_per_power"],
                index=0,
            )
            min_thrust = st.text_input("Poussee mini [N]", value="")
            max_mh = st.text_input("Mh max [N.m]", value="")
            max_dhp = st.text_input("DHP max [W]", value="")
            lambda_value = None
            bmax_value = None
        else:
            objective = "max_eta"
            lambda_value = st.number_input("Lambda impose", min_value=0.01, value=1.3, step=0.1)
            bmax_value = st.number_input("Bmax impose [deg]", min_value=0.0, value=17.5, step=2.5)
            min_thrust = max_mh = max_dhp = ""

        run = st.button("Lancer", type="primary", use_container_width=True)

    if uploaded is None:
        st.info("Chargez un fichier .xlsx pour commencer.")
        return

    if not run:
        st.stop()

    def as_optional_float(value: str):
        value = value.strip()
        if value == "":
            return None
        return float(value.replace(",", "."))

    with st.spinner("Chargement de la base et calcul..."):
        file_bytes = uploaded.getvalue()
        _, df, surrogate = build_surrogate_from_bytes(file_bytes)

        V_target_ms = core.knots_to_ms(float(speed_kn))
        D_target_m = float(diameter_mm) / 1000.0
        D_ref_m = float(reference_diameter_mm) / 1000.0
        min_thrust_v = as_optional_float(min_thrust)
        max_mh_v = as_optional_float(max_mh)
        max_dhp_v = as_optional_float(max_dhp)

        if mode == "Optimisation":
            lambda_candidates = sorted(df["Lambda [-]"].dropna().unique())
            bmax_candidates = sorted(df["Bmax[°]"].dropna().unique())

            best, table = core.optimize_operating_point(
                surrogate=surrogate,
                V_target_ms=V_target_ms,
                D_target_m=D_target_m,
                lambda_candidates=lambda_candidates,
                bmax_candidates=bmax_candidates,
                D_ref_m=D_ref_m,
                iso_reynolds=iso_re,
                scaling_mode=scaling_mode,
                objective=objective,
                min_thrust_propulsive_N=min_thrust_v,
                max_Mh_Nm=max_mh_v,
                max_DHP_W=max_dhp_v,
            )
            law = core.suggest_bmax_law_for_target(
                surrogate=surrogate,
                V_target_ms=V_target_ms,
                D_target_m=D_target_m,
                lambda_candidates=lambda_candidates,
                bmax_candidates=bmax_candidates,
                D_ref_m=D_ref_m,
                iso_reynolds=iso_re,
                scaling_mode=scaling_mode,
                objective=objective,
                min_thrust_propulsive_N=min_thrust_v,
                max_Mh_Nm=max_mh_v,
                max_DHP_W=max_dhp_v,
            )
            raw_env = core.suggest_raw_bmax_envelope(df)

            sort_col = {
                "max_eta": "eta_Cp[%]",
                "min_dhp": "DHP[W]",
                "max_thrust": "thrust_propulsive[N]",
                "max_thrust_per_power": "thrust_per_power",
            }[objective]
            ascending = objective == "min_dhp"
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
            top10 = table[table["feasible"]][cols].sort_values(sort_col, ascending=ascending).head(10)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Lambda opt", f"{best['lambda']:.3f}")
            c2.metric("Bmax opt [deg]", f"{best['Bmax_deg']:.2f}")
            c3.metric("eta_Cp [%]", f"{best['eta_Cp[%]']:.2f}")
            c4.metric("DHP [W]", f"{best['DHP[W]']:.1f}")

            c5, c6, c7, c8 = st.columns(4)
            c5.metric("Poussee propulsive [N]", f"{best['thrust_propulsive[N]']:.1f}")
            c6.metric("Sideforce abs [N]", f"{best['sideforce_abs[N]']:.1f}")
            c7.metric("Mh max [N.m]", f"{best['Mh max']:.1f}")
            c8.metric("Omega [rpm]", f"{best['omega_target_rpm']:.1f}")

            st.subheader("Loi discrete Bmax_opt(lambda) coherente avec le cas cible")
            st.dataframe(law, use_container_width=True, hide_index=True)
            st.download_button(
                "Telecharger la loi discrete en CSV",
                data=dataframe_to_download_bytes(law),
                file_name="bmax_law_target.csv",
                mime="text/csv",
            )

            st.subheader("Enveloppe brute de la base CFD")
            st.dataframe(raw_env, use_container_width=True, hide_index=True)
            st.download_button(
                "Telecharger l'enveloppe brute en CSV",
                data=dataframe_to_download_bytes(raw_env),
                file_name="raw_envelope.csv",
                mime="text/csv",
            )

            st.subheader("Top 10 faisables")
            st.dataframe(top10, use_container_width=True, hide_index=True)
            st.download_button(
                "Telecharger le top 10 en CSV",
                data=dataframe_to_download_bytes(top10),
                file_name="top10_feasible.csv",
                mime="text/csv",
            )

            txt = report_text(best, law, raw_env, top10)
            st.download_button(
                "Telecharger le rapport TXT",
                data=txt.encode("utf-8"),
                file_name="adv_propulse_report.txt",
                mime="text/plain",
            )
        else:
            result = core.evaluate_target_case(
                surrogate=surrogate,
                V_target_ms=V_target_ms,
                lam=float(lambda_value),
                bmax_deg=float(bmax_value),
                D_target_m=D_target_m,
                D_ref_m=D_ref_m,
                iso_reynolds=iso_re,
                scaling_mode=scaling_mode,
            )
            result_df = pd.DataFrame({"parametre": list(result.keys()), "valeur": list(result.values())})
            st.subheader("Evaluation d'un point")
            st.dataframe(result_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Telecharger le resultat en CSV",
                data=dataframe_to_download_bytes(result_df),
                file_name="evaluation_point.csv",
                mime="text/csv",
            )


if __name__ == "__main__":
    main()
