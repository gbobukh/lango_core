"""
Django settings — shared defaults for all environments.

Optional dev overlays live in ``local.py`` (see ``__init__.py``).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Repo root (package is lango_core/settings/base.py → three parents up)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / '.env')


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == '':
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_csv(name: str) -> list[str]:
    raw = os.environ.get(name, '')
    return [item.strip() for item in raw.split(',') if item.strip()]


# When multiple Django deployments share one Unix user crontab and the same Redis on one host
# (e.g. prod under /root/lango_core and staging under /root/staging-core), set a distinct
# SCHEDULER_NAMESPACE per .env so cron sync and workflow distributed locks do not cross-talk.
# Not a secret. Default ``prod`` keeps legacy single-environment deploys predictable if unset.
_scheduler_namespace_raw = os.environ.get("SCHEDULER_NAMESPACE", "prod")
SCHEDULER_NAMESPACE = (_scheduler_namespace_raw.strip() or "prod")

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# Override with SECRET_KEY in .env for any deployed or shared environment.
# Empty SECRET_KEY in .env (from copied .env.example) uses the dev fallback below.
_secret_key = os.environ.get('SECRET_KEY', '').strip()
SECRET_KEY = _secret_key or (
    'django-insecure-ay^4ut=ue_6+u)isq@qb(8w#x9ruol9=k7pmz#f9pqog&#*5dj'
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = _env_bool('DEBUG', True)

_allowed = _env_csv('ALLOWED_HOSTS')
if _allowed:
    ALLOWED_HOSTS = _allowed
else:
    ALLOWED_HOSTS = ['*', 'core.lango.media', 'www.core.lango.media']

# Настройки для работы с Cloudflare
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# Local DEBUG: no HTTPS redirect by default. Production (DEBUG off): redirect unless SECURE_SSL_REDIRECT=0
if DEBUG:
    SECURE_SSL_REDIRECT = _env_bool('SECURE_SSL_REDIRECT', False)
else:
    SECURE_SSL_REDIRECT = _env_bool('SECURE_SSL_REDIRECT', True)

if DEBUG:
    CSRF_COOKIE_SECURE = False
    SESSION_COOKIE_SECURE = False
else:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = False  # HTTP через Cloudflare (как раньше)

CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_USE_SESSIONS = False
CSRF_COOKIE_NAME = 'csrftoken'

_CSRF_TRUSTED_ORIGINS = [
    'https://core.lango.media',
    'http://core.lango.media',
    'https://www.core.lango.media',
    'http://www.core.lango.media',
    'https://*.core.lango.media',
    'http://*.core.lango.media',
    'https://*.lango.media',
    'http://*.lango.media',
    'https://91.99.239.93:8002',
    'http://91.99.239.93:8002',
    'https://91.99.239.93',
    'http://91.99.239.93',
]
if DEBUG:
    _CSRF_TRUSTED_ORIGINS.extend(
        [
            'http://127.0.0.1:8000',
            'http://localhost:8000',
            'http://127.0.0.1:8001',
            'http://localhost:8001',
        ]
    )
_CSRF_TRUSTED_ORIGINS.extend(_env_csv('CSRF_TRUSTED_ORIGINS_EXTRA'))
CSRF_TRUSTED_ORIGINS = _CSRF_TRUSTED_ORIGINS

# Включить логирование для отладки CSRF
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'lango_core.csrf_middleware': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
        'lango_core.middleware': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}

# Дополнительные настройки для Cloudflare
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# Настройки сессий для Cloudflare (SESSION_COOKIE_SECURE выше: False как раньше)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'integrations',
    'metadata',
    'service_builder.apps.ServiceBuilderConfig',
    'scheduler.apps.SchedulerConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'lango_core.middleware.CloudflareMiddleware',  # Cloudflare middleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',  # Standard CSRF middleware
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'lango_core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'lango_core.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
_static_root = os.environ.get('STATIC_ROOT', '').strip()
STATIC_ROOT = str(Path(_static_root)) if _static_root else str(BASE_DIR / 'staticfiles')

MEDIA_URL = '/media/'
_media_root = os.environ.get('MEDIA_ROOT', '').strip()
MEDIA_ROOT = str(Path(_media_root)) if _media_root else str(BASE_DIR / 'media')

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
