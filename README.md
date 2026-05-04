# lango_core

Django service for integrations, metadata, service builder (scenarios/workflows), and scheduling.

## Requirements

- Python 3.12+ (production notes use 3.14; match your deployment)
- See `requirements.txt`

## Local setup (minimal)

```bash
cd lango_core
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env if needed; for a quick local admin, defaults are usually enough.
python manage.py migrate
python manage.py createsuperuser   # optional
python manage.py runserver 0.0.0.0:8000
```

Open `http://127.0.0.1:8000/admin/`.

Static files for development are served by Django when `DEBUG=1`. For production-style static collection:

```bash
export STATIC_ROOT=   # optional; defaults to ./staticfiles
python manage.py collectstatic --noinput
```

## Environment

Copy `.env.example` to `.env`. Variables are loaded from `.env` via `python-dotenv` in `lango_core/settings/` (`base.py`). Set `LANGO_USE_LOCAL_SETTINGS=1` locally to enable `local.py` overlays (paths, optional dev flags).

- **`SECRET_KEY`**: set in any non-local / shared environment.
- **`DEBUG`**: `0` for production; `1` (default) enables local-friendly SSL/cookie and CSRF behavior.
- **`REDIS_URL`**: optional; see `docs/api_rate_limits.md`.
- **`STATIC_ROOT`**: optional; defaults to `<repo>/staticfiles`. **Existing production** deployments that used `/var/www/lango_core_static/` should set `STATIC_ROOT=/var/www/lango_core_static` in `.env` so `collectstatic` behavior stays unchanged.

## Documentation

- Runtime / Gunicorn / migrations: `docs/runtime_environment.md`
- Architecture walkthrough: `docs/walkthrough.md`
- **Staging** on this host (`staging-core.lango.media`): `docs/staging_setup.md`

## Tests

```bash
python manage.py test
```
