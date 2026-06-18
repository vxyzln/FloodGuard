# FloodGuard

Desktop flood risk and evacuation planning prototype for Indian cities.

## Setup

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python train_model.py
python setup_db.py
python seed_data.py
python app.py
```

`setup_db.py`, `seed_data.py`, and `app.py` prompt for the MySQL root password if `FLOODGUARD_DB_PASSWORD` is not set.

The app is still demoable without MySQL: it uses the generated offline cache in `assets/seed_cache.json` and placeholder maps in `assets/maps/`. MySQL logging is attempted for every simulation run and skipped gracefully if the database is unavailable.

## MySQL

Expected connection:

- host: `localhost`
- port: `3306`
- user: `root`
- database: `floodguard`

Optional environment variables:

- `FLOODGUARD_DB_HOST`
- `FLOODGUARD_DB_PORT`
- `FLOODGUARD_DB_USER`
- `FLOODGUARD_DB_PASSWORD`
- `FLOODGUARD_DB_NAME`

