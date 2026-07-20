from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import streamlit as st

APP_TITLE = "ADV Propulse - Application navigateur"
CORE_SCRIPT_NAME = "adv_propulse_scaling_optimizer.py"
BUNDLED_DATA_CANDIDATES = [
    "adv_propulse_database.xlsx",
    "tab.xlsx",
    "outputAll.xlsx",
]


def resource_path(filename: str) -> Path:
    return Path(__file__).resolve().parent / filename


def discover_bundled_workbook() -> Optional[Path]:
    root = Path(__file__).resolve().parent
    for name in BUNDLED_DATA_CANDIDATES:
        path = root / name
        if path.exists():
            return path
    matches = sorted(root.glob("*.xlsx"))
    return matches[0] if matches else None


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


@st.cache_data(show_spinner=False)
def load_summary_from_path(path_str: str) -> Tuple[str, pd.DataFrame]:
    core = load_core_module()
    df = core.load_summary(path_str)
    return path_str, df


@st.cache_resource(show_spinner=False)
def build_surrogate_from_path(path_str: str):
    core = load_core_module()
    _, df = load_summary_from_path(path_str)
    surrogate = core.build_surrogate(df)
    return path_str, df, surrogate


def dataframe_to_download_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def as_optional_float(value: str):
    value = value.strip()
    if value == "":
        return None
    return float(value.replace(",", "."))


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
        "blade_length_ratio_used",
        "force_scale_factor",
        "moment_scale_factor",
        "power_scale_factor",
        "reynolds_mode",
        "chord_ratio_target_to_ref_used",
        "domain_warning",
        "_used_nearest_fallback",
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
    bundled_workbook = discover_bundled_workbook()

    st.title(APP_TITLE)
    st.caption(
        "Mise a l'echelle et optimisation ADV-propulse. Le diametre orbital de la base est deduit "
        "automatiquement de V, lambda et omega; les pertes de separateur decimal x1000 sont reparees au chargement."
    )

    with st.sidebar:
        st.header("Base de donnees")
        if bundled_workbook is not None:
            st.success(f"Base bundlee detectee : {bundled_workbook.name}")
        else:
            st.warning("Aucune base bundlee detectee dans le dossier de l'application.")

        uploaded = st.file_uploader(
            "Remplacer la base bundlee par un autre fichier Excel (.xlsx)",
            type=["xlsx"],
            help="Optionnel. Si vous ne chargez rien ici, l'application utilisera automatiquement la base bundlee.",
        )

        st.header("Entrees")
        mode = st.radio("Mode", ["Optimisation", "Evaluation d'un point"], index=0)
        diameter_mm = st.number_input("Diametre cible [mm]", min_value=1.0, value=200.0, step=10.0)
        speed_kn = st.number_input("Vitesse cible [kn]", min_value=0.1, value=10.0, step=0.5)
        st.text_input(
            "Diametre orbital de la base",
            value="Detecte automatiquement (300 mm pour la base bundlee)",
            disabled=True,
            help="Cette valeur appartient a l'abaque CFD et ne doit pas etre remplacee par une dimension de la machine reelle.",
        )

        st.markdown("---")
        iso_re = st.checkbox(
            "Correction iso-Reynolds",
            value=False,
            help="A activer seulement si la comparaison de corde est definie et si la vitesse equivalente reste dans le domaine de l'abaque.",
        )
        reynolds_mode = "diameter"
        chord_ratio_text = ""
        sigma_target_text = ""
        sigma_ref_text = ""
        blades_target = 3.0
        blades_ref = 3.0
        if iso_re:
            reynolds_mode = st.selectbox(
                "Base de comparaison iso-Re",
                ["diameter", "chord_ratio", "sigma"],
                format_func=lambda x: {
                    "diameter": "V*D (approximation simple)",
                    "chord_ratio": "V*c via rapport c_cible/c_ref impose",
                    "sigma": "V*c via sigma*D/Z",
                }[x],
                index=0,
            )
            if reynolds_mode == "chord_ratio":
                chord_ratio_text = st.text_input("Rapport de corde c_cible / c_ref", value="")
            elif reynolds_mode == "sigma":
                sigma_target_text = st.text_input("Sigma cible [-]", value="")
                sigma_ref_text = st.text_input("Sigma ref [-]", value="")
                blades_target = st.number_input("Nombre de pales cible", min_value=1.0, value=3.0, step=1.0)
                blades_ref = st.number_input("Nombre de pales ref", min_value=1.0, value=3.0, step=1.0)

        st.markdown("---")
        scaling_mode = st.selectbox(
            "Mode d'echelle",
            ["3d", "2d"],
            index=1,
            help=(
                "3d = homothetie complete, la longueur de pale suit le diametre. "
                "2d = correction explicite par longueur de pale H_target/H_ref."
            ),
        )
        target_blade_length_text = st.text_input("Longueur de pale cible [m] (utilisee en 2d)", value="")
        reference_blade_length_text = st.text_input(
            "Longueur de pale effective utilisee au post-traitement de la base [m]", value="5.00",
            help="Valeur calibree provisoirement autour de 5 m sur les cas P200, P75.6 et le point de bollard-pull. A remplacer si la valeur originale est retrouvee."
        )

        st.markdown("---")
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
            measured_dhp_kw_text = ""
        else:
            objective = "max_eta"
            lambda_value = st.number_input("Lambda impose", min_value=0.01, value=1.3, step=0.1)
            bmax_value = st.number_input("Bmax impose [deg]", min_value=0.0, value=15.0, step=2.5)
            measured_dhp_kw_text = st.text_input(
                "DHP mesuree connue [kW] (optionnel, pour calibrer la longueur effective)", value=""
            )
            min_thrust = max_mh = max_dhp = ""

        run = st.button("Lancer", type="primary", use_container_width=True)

    if uploaded is not None:
        source_label = uploaded.name
        source_kind = "uploaded"
    elif bundled_workbook is not None:
        source_label = bundled_workbook.name
        source_kind = "bundled"
    else:
        st.error("Aucun fichier de base disponible. Ajoutez un classeur .xlsx a cote de l'application ou chargez-en un.")
        return

    st.info(f"Base utilisee : {source_label}")

    if not run:
        st.stop()

    with st.spinner("Chargement de la base et calcul..."):
        if source_kind == "uploaded":
            _, df, surrogate = build_surrogate_from_bytes(uploaded.getvalue())
        else:
            _, df, surrogate = build_surrogate_from_path(str(bundled_workbook))

        inferred_diameter_m = float(df.attrs.get("database_orbital_diameter_m", core.DEFAULT_REF_DIAMETER_M))
        cleaning_report = dict(df.attrs.get("cleaning_report", {}))
        st.success(f"Diametre orbital deduit de l'abaque : {inferred_diameter_m*1000:.1f} mm")
        with st.expander("Controle qualite automatique de la base"):
            st.write(
                "Le classeur contient des pertes ponctuelles de separateur decimal (facteurs x1000). "
                "Les colonnes redondantes sont reparees avant interpolation; DHP reste la grandeur d'ancrage."
            )
            st.json(cleaning_report)

        V_target_ms = core.knots_to_ms(float(speed_kn))
        D_target_m = float(diameter_mm) / 1000.0
        D_ref_m = float(df.attrs.get("database_orbital_diameter_m", core.DEFAULT_REF_DIAMETER_M))
        min_thrust_v = as_optional_float(min_thrust)
        max_mh_v = as_optional_float(max_mh)
        max_dhp_v = as_optional_float(max_dhp)
        chord_ratio_v = as_optional_float(chord_ratio_text)
        sigma_target_v = as_optional_float(sigma_target_text)
        sigma_ref_v = as_optional_float(sigma_ref_text)
        target_blade_length_v = as_optional_float(target_blade_length_text)
        ref_blade_length_v = as_optional_float(reference_blade_length_text)
        measured_dhp_kw_v = as_optional_float(measured_dhp_kw_text)

        if scaling_mode == "2d" and (target_blade_length_v is None or ref_blade_length_v is None):
            st.warning(
                "En mode 2d, si une longueur de pale manque, aucun facteur H_target/H_ref n'est applique. "
                "Renseignez les deux valeurs pour corriger la puissance et les efforts."
            )

        common_kwargs = dict(
            surrogate=surrogate,
            V_target_ms=V_target_ms,
            D_target_m=D_target_m,
            D_ref_m=D_ref_m,
            iso_reynolds=iso_re,
            scaling_mode=scaling_mode,
            reynolds_mode=reynolds_mode,
            chord_ratio_target_to_ref=chord_ratio_v,
            sigma_target=sigma_target_v,
            sigma_ref=sigma_ref_v,
            blades_target=float(blades_target),
            blades_ref=float(blades_ref),
            target_blade_length_m=target_blade_length_v,
            ref_blade_length_m=ref_blade_length_v,
        )

        if mode == "Optimisation":
            lambda_candidates = sorted(df["Lambda [-]"].dropna().unique())
            bmax_candidates = sorted(df["Bmax[°]"].dropna().unique())

            best, table = core.optimize_operating_point(
                lambda_candidates=lambda_candidates,
                bmax_candidates=bmax_candidates,
                objective=objective,
                min_thrust_propulsive_N=min_thrust_v,
                max_Mh_Nm=max_mh_v,
                max_DHP_W=max_dhp_v,
                **common_kwargs,
            )
            law = core.suggest_bmax_law_for_target(
                lambda_candidates=lambda_candidates,
                bmax_candidates=bmax_candidates,
                objective=objective,
                min_thrust_propulsive_N=min_thrust_v,
                max_Mh_Nm=max_mh_v,
                max_DHP_W=max_dhp_v,
                **common_kwargs,
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
                    "status",
                    "domain_warning",
                    "_used_nearest_fallback",
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

            st.subheader("Facteurs utilises")
            meta_cols = [
                "V_reference_in_database_ms",
                "blade_length_ratio_used",
                "force_scale_factor",
                "moment_scale_factor",
                "power_scale_factor",
                "reynolds_mode",
                "chord_ratio_target_to_ref_used",
                "domain_warning",
                "_used_nearest_fallback",
            ]
            meta_df = pd.DataFrame({"parametre": meta_cols, "valeur": [best.get(c) for c in meta_cols]})
            st.dataframe(meta_df, use_container_width=True, hide_index=True)

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
                lam=float(lambda_value),
                bmax_deg=float(bmax_value),
                **common_kwargs,
            )
            metrics = [
                ("eta_Cp [%]", "eta_Cp[%]"),
                ("Poussee propulsive [N]", "thrust_propulsive[N]"),
                ("Sideforce abs [N]", "sideforce_abs[N]"),
                ("Mh max [N.m]", "Mh max"),
                ("DHP [W]", "DHP[W]"),
                ("Omega [rpm]", "omega_target_rpm"),
            ]
            cols = st.columns(3)
            for i, (label, key) in enumerate(metrics):
                value = result.get(key)
                cols[i % 3].metric(label, f"{value:.3f}" if value is not None else "NA")

            if result.get("domain_warning"):
                st.error(
                    "Attention : " + str(result.get("domain_warning")) + ". "
                    "Le resultat utilise un voisin de bord et doit etre considere comme une extrapolation."
                )

            if measured_dhp_kw_v is not None and measured_dhp_kw_v > 0 and ref_blade_length_v:
                predicted_kw = float(result.get("DHP[W]", float("nan"))) / 1000.0
                inferred_h = float(ref_blade_length_v) * predicted_kw / measured_dhp_kw_v
                st.subheader("Calibrage sur le point mesure")
                ccal1, ccal2, ccal3 = st.columns(3)
                ccal1.metric("DHP calculee [kW]", f"{predicted_kw:.3f}")
                ccal2.metric("DHP mesuree [kW]", f"{measured_dhp_kw_v:.3f}")
                ccal3.metric("Longueur effective deduite [m]", f"{inferred_h:.3f}")
                st.info(
                    "Cette longueur est un coefficient de post-traitement effectif. "
                    "Calibrez-la sur plusieurs points avant de la figer."
                )

            st.subheader("Resultat detaille")
            result_df = pd.DataFrame({"parametre": list(result.keys()), "valeur": list(result.values())})
            st.dataframe(result_df, use_container_width=True, hide_index=True)

            txt = report_text(result, None, None, None)
            st.download_button(
                "Telecharger le resultat TXT",
                data=txt.encode("utf-8"),
                file_name="adv_propulse_point.txt",
                mime="text/plain",
            )


if __name__ == "__main__":
    main()
