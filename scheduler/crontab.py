"""
Sync ScheduledWorkflow entries to system crontab using python-crontab.
"""
import os
import re
import sys

from django.conf import settings

MARKER = "# lango_core scheduler"
SCHEDULED_WORKFLOW_LOCK_PREFIX = "workflow_lock:sw"


def _get_redis_client():
    try:
        import redis
    except ImportError:
        return None
    try:
        redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        client.ping()
        return client
    except Exception:
        return None


def is_scheduled_workflow_running(sw_id, redis_client=None):
    """Return True if Redis lock key exists for this scheduled workflow."""
    if not sw_id:
        return False
    client = redis_client or _get_redis_client()
    if not client:
        return False
    try:
        lock_key = f"{SCHEDULED_WORKFLOW_LOCK_PREFIX}:{sw_id}"
        return bool(client.exists(lock_key))
    except Exception:
        return False


def get_crontab_info():
    """
    Read current crontab and return structured info for display.
    Returns dict: {
        'error': str or None,
        'entries': [{'cron_expr': str, 'command': str, 'sw_id': int or None, 'sw': ScheduledWorkflow or None, 'status': str}, ...],
        'active_in_db': int,
        'in_crontab': int,
    }
    """
    result = {
        'error': None,
        'entries': [],
        'active_in_db': 0,
        'in_crontab': 0,
    }
    try:
        from crontab import CronTab
    except ImportError:
        result['error'] = "python-crontab is not installed."
        return result

    from scheduler.models import ScheduledWorkflow

    active = ScheduledWorkflow.objects.filter(is_active=True).select_related('workflow', 'frequency')
    result['active_in_db'] = active.count()
    sw_by_id = {sw.pk: sw for sw in active}
    redis_client = _get_redis_client()

    try:
        cron = CronTab(user=True)
    except Exception as e:
        result['error'] = str(e)
        return result

    sw_id_re = re.compile(r'sw_id=(\d+)')
    for job in cron:
        if not job.comment or MARKER not in job.comment:
            continue
        result['in_crontab'] += 1
        m = sw_id_re.search(job.comment)
        sw_id = int(m.group(1)) if m else None
        sw = sw_by_id.get(sw_id) if sw_id else None
        if sw_id and not sw:
            status = 'orphan'  # in crontab but SW deleted or inactive
        elif sw:
            status = 'synced'
        else:
            status = 'unknown'
        result['entries'].append({
            'cron_expr': str(job.slices) if job.slices else '—',
            'command': job.command or '',
            'sw_id': sw_id,
            'sw': sw,
            'status': status,
            'arguments_summary': sw.get_arguments_summary() if sw else '—',
            'is_running': is_scheduled_workflow_running(sw_id, redis_client=redis_client) if sw_id else False,
        })

    # Check for missing: active in DB but not in crontab
    in_cron_ids = {e['sw_id'] for e in result['entries'] if e['sw_id']}
    for sw in active:
        if sw.pk not in in_cron_ids:
            result['entries'].append({
                'cron_expr': '—',
                'command': '(not in crontab)',
                'sw_id': sw.pk,
                'sw': sw,
                'status': 'missing',
                'arguments_summary': sw.get_arguments_summary(),
                'is_running': is_scheduled_workflow_running(sw.pk, redis_client=redis_client),
            })
            result['in_crontab'] += 0  # don't count missing as in crontab

    return result


def sync_crontab():
    """
    Sync all active ScheduledWorkflow entries to the system crontab.
    Removes existing scheduler entries and adds current ones.
    Returns (success: bool, message: str).
    """
    try:
        from crontab import CronTab
    except ImportError:
        return False, "python-crontab is not installed. Run: pip install python-crontab"

    from scheduler.models import ScheduledWorkflow

    # Use current user's crontab by default
    cron = CronTab(user=True)

    # Remove existing scheduler entries (comment marker)
    to_remove = [job for job in cron if job.comment and MARKER in job.comment]
    for job in to_remove:
        cron.remove(job)

    # Add new entries for active scheduled workflows
    # Use wrapper script to avoid % escaping issues in crontab
    base_dir = str(settings.BASE_DIR)
    python_path = os.environ.get('PYTHON_PATH', sys.executable)
    script_path = os.path.join(base_dir, 'scripts', 'run_workflow_cron.sh')

    for sw in ScheduledWorkflow.objects.filter(is_active=True).select_related('workflow', 'frequency'):
        cron_expr = sw.frequency.to_cron_expression()
        cmd = f"PYTHON_PATH={python_path} {script_path} {sw.pk}"
        job = cron.new(command=cmd, comment=f"{MARKER} sw_id={sw.pk}")
        job.setall(cron_expr)

    cron.write()
    count = ScheduledWorkflow.objects.filter(is_active=True).count()
    return True, f"Synced {count} scheduled workflow(s) to crontab."
