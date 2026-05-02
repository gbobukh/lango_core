# Runtime Environment

This document describes the actual runtime environment and the minimal safe runbook for `lango_core`.

## Project Root

- Path: `/root/lango_core`
- Django entrypoint: `manage.py`

All management commands below assume you are in this directory.

## Python Runtime

- Runtime Python binary: `/usr/bin/python3.14`
- Django version in runtime: `5.2.7`

Use the same Python for migrations and maintenance commands to match the running app environment.

## Gunicorn Runtime

`lango_core` is running with:

- Python: `/usr/bin/python3.14`
- Gunicorn binary: `/usr/local/bin/gunicorn`
- Command: `gunicorn -c gunicorn.conf.py lango_core.wsgi:application`
- Master process has PPID `1` and worker processes are its children.

Gunicorn config file:

- `gunicorn.conf.py`
- Bind: `127.0.0.1:8002`
- Logs:
  - `/root/lango_core/logs/gunicorn_access.log`
  - `/root/lango_core/logs/gunicorn_error.log`

## Migration Runbook

Apply service builder migrations:

```bash
cd /root/lango_core
/usr/bin/python3.14 manage.py migrate service_builder
```

Check migration status:

```bash
cd /root/lango_core
/usr/bin/python3.14 manage.py showmigrations service_builder
```

## Safe Gunicorn Reload (Only `lango_core`)

Find the `lango_core` gunicorn master PID:

```bash
ps -eo pid,ppid,cmd | awk '$2==1 && $0 ~ /\/usr\/bin\/python3\.14/ && $0 ~ /gunicorn -c gunicorn\.conf\.py lango_core\.wsgi:application/ {print $1}'
```

Reload only that master:

```bash
kill -HUP <MASTER_PID>
```

Verify new workers started:

```bash
ps -eo pid,ppid,lstart,cmd | awk '$0 ~ /\/usr\/bin\/python3\.14/ && $0 ~ /gunicorn -c gunicorn\.conf\.py lango_core\.wsgi:application/ {print}'
```

## Applying changes to a running app

This section complements the migration and Gunicorn reload runbooks above. It reflects how admin UI and static assets actually behave in this deployment.

### 1) Static files in production (not only “reload Gunicorn”)

- `STATIC_URL` is `/static/`; `STATIC_ROOT` is `/var/www/lango_core_static/` (see `lango_core/settings.py`). Collected assets are served from that directory (see `lango_core/urls.py` with `static(..., document_root=settings.STATIC_ROOT)` when `DEBUG` is on).
- After changing files under app `static/` trees (for example `service_builder/static/...`), you must run **`collectstatic`** so the updated files are copied into `STATIC_ROOT`.
- **Reloading Gunicorn does not replace `collectstatic`.** If JS/CSS changed but was not collected, the browser will keep loading old or missing files from `STATIC_ROOT`.
- Quick sanity check after collect:

```bash
ls -la /var/www/lango_core_static/service_builder/js/
```

### 2) Cache busting: what not to do and what to do instead

- **Do not** append query strings such as `?v=2` to paths in Django `Form.Media` or `Media` tuples (for example `'myapp/js/foo.js?v=2'`). Those URLs are treated as literal filenames; the `?` is encoded (`%3F`), the server looks for a non-existent file, and you get **404** in the browser.
- **Do** bump versions by **renaming the file** (for example `foo_v10.js`) and updating the reference in `admin.py`, `widgets.py`, or templates. Then run `collectstatic` and reload Gunicorn as usual.

### 3) Order of operations (checklists)

**After changing admin JavaScript/CSS or templates that ship as static files:**

1. `cd /root/lango_core && /usr/bin/python3.14 manage.py collectstatic --noinput`
2. Graceful reload of the `lango_core` Gunicorn master (`kill -HUP <MASTER_PID>`) — see [Safe Gunicorn Reload](#safe-gunicorn-reload-only-lango_core).
3. In the browser: **hard refresh** (`Ctrl+F5`) or a private window — CDN or browser cache may still serve old assets.
4. In DevTools → Network: confirm the script URL returns **200** (not 404); if you expect a new file name, confirm the request hits the new path.

**After changing Python models or DB-backed `choices`:**

1. Run the relevant `migrate` (see [Migration Runbook](#migration-runbook)).
2. `HUP` Gunicorn so workers load the new code.

### 4) Admin: click-to-edit and polymorphic step-type scripts

- Inline scenario steps use **click-to-edit** for existing rows. Polymorphic scripts (for example `scenario_step_polymorphic_v*.js`) often look for a real `select[id$="-step_type"]` inside the row.
- While the row is still in **read/display** mode, that `select` may not be in the DOM yet; visibility toggles (hide/show `Action type`, `Action config`, etc.) may not run until the user opens the row for edit or changes `Step type` once.
- **Known behaviour:** switching `Step type` away and back (or opening the field for edit) can “fix” the layout. This is a limitation of client-side init order vs click-to-edit, not a separate renderer per legacy step type.

## Important Notes

- There is another project process on this host (`api_mapping_project`). Do not restart it unless explicitly requested.
- This repository does not define a single deployment orchestrator file (no confirmed project-local systemd unit in repo). Use process-based verification when operating manually.
- For cron workflow execution, Python is resolved via `PYTHON_PATH` with fallback to `python3` in:
  - `scripts/run_workflow_cron.sh`
  - `scheduler/crontab.py`

## Redis Prerequisites (Rate Limits)

The project uses Redis for shared API rate-limiting across gunicorn workers.

- Python dependency: `redis` (installed from `requirements.txt`)
- Service binaries expected:
  - `/usr/bin/redis-server`
  - `/usr/bin/redis-cli`
- Connectivity:
  - default URL: `redis://127.0.0.1:6379/0`
  - override via `REDIS_URL`

Quick checks:

```bash
redis-cli ping
```

```bash
cd /root/lango_core
/usr/bin/python3.14 manage.py shell -c "from service_builder.rate_limit import ApiRateLimiter; print(bool(ApiRateLimiter._get_redis()))"
```
