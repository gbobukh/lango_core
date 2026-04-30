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
