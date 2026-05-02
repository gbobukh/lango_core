"""
Django settings entrypoint (``DJANGO_SETTINGS_MODULE=lango_core.settings``).

Loads ``base`` for every deployment. Loads ``local`` only when
``LANGO_USE_LOCAL_SETTINGS`` is truthy in the environment (after ``.env``).
Production should leave that unset.
"""

import os

from .base import *  # noqa: F401,F403


def _env_truthy(name: str) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == '':
        return False
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


if _env_truthy('LANGO_USE_LOCAL_SETTINGS'):
    from .local import *  # noqa: F401,F403
