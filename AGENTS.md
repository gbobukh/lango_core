# Agents

## Cursor Cloud specific instructions

### Overview

Lango Core is a Django 5.2.7 API integration orchestration platform. The primary interface is the Django Admin panel. It uses SQLite for local development (no external database needed) and has four Django apps: `integrations`, `service_builder`, `scheduler`, `metadata`.

### Quick reference

- **Activate venv:** `source /workspace/.venv/bin/activate`
- **Run tests:** `python manage.py test` (see `README.md`)
- **Run dev server:** `python manage.py runserver 0.0.0.0:8000`
- **Apply migrations:** `python manage.py migrate`
- **Admin URL:** `http://127.0.0.1:8000/admin/`

### Gotchas

- The `.env` file is loaded via `python-dotenv` in `lango_core/settings/base.py`. Copy `.env.example` to `.env` if it does not exist; defaults are fine for local dev.
- Redis is optional; the rate limiter fails open if Redis is unavailable, so the app runs fine without it.
- `python3.12-venv` system package is required to create the virtualenv on Ubuntu 24.04 (not pre-installed).
- The `LANGO_USE_LOCAL_SETTINGS=1` env var enables `lango_core/settings/local.py` overlays — not needed for basic dev.
- Static files are served by Django in `DEBUG=1` mode. No `collectstatic` needed for development.
- `ServiceEndpoint` model does not have a `base_url` field; use `resource_path` for path and `tracker` FK for the API target.
