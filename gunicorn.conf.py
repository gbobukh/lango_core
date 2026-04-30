# Gunicorn config for lango_core
# Use: gunicorn -c gunicorn.conf.py lango_core.wsgi:application

bind = "127.0.0.1:8002"
workers = 3
timeout = 300  # 5 min - match nginx proxy_read_timeout for long workflows
accesslog = "/root/lango_core/logs/gunicorn_access.log"
errorlog = "/root/lango_core/logs/gunicorn_error.log"
