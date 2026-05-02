"""
Dev-machine overlays (loaded only if LANGO_USE_LOCAL_SETTINGS=1 in env).

Use ``from django.conf import settings`` in application code; add symbols here
gradually instead of branching entire functions per environment.
"""

from pathlib import Path

from .base import BASE_DIR

ENVIRONMENT_LABEL = 'local'

# Writable debug trace (e.g. Click-to-edit); ensure parent dir exists before use.
CLICK_TO_EDIT_DEBUG_LOG_PATH: Path = BASE_DIR / 'logs' / 'click_to_edit_debug.log'
