# Deployment bundle for Streamlit Community Cloud

Files:
- `streamlit_app.py` : browser app entrypoint
- `adv_propulse_scaling_optimizer.py` : computation core
- `requirements.txt` : Python dependencies for deployment

## Local run
```bash
python3 -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Community Cloud
Push these files to the root of a GitHub repository, then create a new app on Streamlit Community Cloud and choose `streamlit_app.py` as the entrypoint.
