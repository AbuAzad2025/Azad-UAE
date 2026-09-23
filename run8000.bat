@echo off
set DATABASE_URL=postgresql+psycopg2://azad_app:azad_app_pass@localhost:5432/erp_azad_full
set PORT=8000
set HOST=0.0.0.0
set OWNER_PASSWORD=DevOwner@2026Local!
set AZAD_MASTER_DAILY_SEED=Azad@1983
python app.py

