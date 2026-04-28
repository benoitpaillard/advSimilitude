#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements_streamlit.txt
streamlit run adv_propulse_streamlit_app.py
