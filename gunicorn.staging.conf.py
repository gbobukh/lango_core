# Gunicorn config for staging (lango_core) — binds 127.0.0.1:8003
# systemd: ExecStart=/usr/local/bin/gunicorn -c gunicorn.staging.conf.py lango_core.wsgi:application

bind = "127.0.0.1:8003"
workers = 2
timeout = 300
accesslog = "/root/staging-core/logs/staging/gunicorn_access.log"
errorlog = "/root/staging-core/logs/staging/gunicorn_error.log"
