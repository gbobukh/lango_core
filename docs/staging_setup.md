# Staging (staging-core.lango.media)

Separate Gunicorn on **127.0.0.1:8003**, code in `/root/staging-core`.

## Files in repo

- `gunicorn.staging.conf.py` — staging Gunicorn
- `deploy/lango-core-staging.service` — systemd unit template
- `deploy/nginx-staging-core.lango.media.conf` — nginx (HTTP-first for Certbot)
- `deploy/staging.env.template` — copy to `.env`

## One-time setup

```bash
# env
sudo cp /root/staging-core/deploy/staging.env.template /root/staging-core/.env
sudo nano /root/staging-core/.env   # set SECRET_KEY if must match copied prod DB crypto

sudo mkdir -p /var/www/lango_core_static_staging
sudo chown root:root /var/www/lango_core_static_staging

cd /root/staging-core
/usr/bin/python3.14 -m pip install -r requirements.txt
/usr/bin/python3.14 manage.py migrate --noinput
/usr/bin/python3.14 manage.py collectstatic --noinput

sudo cp deploy/lango-core-staging.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lango-core-staging

sudo cp deploy/nginx-staging-core.lango.media.conf /etc/nginx/sites-available/staging-core.lango.media
sudo ln -sf /etc/nginx/sites-available/staging-core.lango.media /etc/nginx/sites-enabled/staging-core.lango.media
sudo nginx -t && sudo systemctl reload nginx
```

TLS (after `A`/proxy DNS for `staging-core.lango.media` points here):

```bash
sudo certbot --nginx -d staging-core.lango.media
```

## Operations

Reload staging app after code changes:

```bash
sudo systemctl reload lango-core-staging
# or kill -HUP <master PID>
```

Prod is unchanged: `lango-core-django.service` → `127.0.0.1:8002`.
