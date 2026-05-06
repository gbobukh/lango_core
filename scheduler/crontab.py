"""
Sync ScheduledWorkflow entries to system crontab using python-crontab.
"""
import os
import re
import sys

from django.conf import settings

# Base substring every scheduler cron comment must contain (before namespace split).
MARKER_BASE = "# lango_core scheduler"
_NS_RE = re.compile(r"\bns=([^\s]+)")
_SW_ID_RE = re.compile(r"sw_id=(\d+)")


def get_scheduler_namespace():
    """Deployment id for cron comments and Redis locks (from settings.SCHEDULER_NAMESPACE)."""
    return getattr(settings, "SCHEDULER_NAMESPACE", "prod") or "prod"


def format_scheduler_cron_comment(sw_id, namespace=None):
    """Cron job comment marking a row as managed by this deployment's scheduler sync."""
    ns = namespace or get_scheduler_namespace()
    return f"{MARKER_BASE} ns={ns} sw_id={sw_id}"


def cron_comment_matches_namespace(comment, namespace=None):
    """
    True if comment is a namespaced scheduler row owned by ``namespace``.
    Legacy lines with MARKER_BASE but without ns= do not match any namespace (manual cleanup).
    """
    if not comment or MARKER_BASE not in comment:
        return False
    ns = namespace or get_scheduler_namespace()
    m = _NS_RE.search(comment)
    if not m:
        return False
    return m.group(1) == ns


def scheduled_workflow_redis_lock_key(sw_id, namespace=None):
    """
    Redis key for ScheduledWorkflow overlap protection.
    Include namespace so the same primary key in different DBs does not lock the other env.
    """
    ns = namespace or get_scheduler_namespace()
    return f"workflow_lock:{ns}:sw:{sw_id}"


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
        lock_key = scheduled_workflow_redis_lock_key(sw_id)
        return bool(client.exists(lock_key))
    except Exception:
        return False


def get_crontab_info():
    """
    Read current crontab and return structured info for display.

    Only jobs whose comment matches MARKER_BASE and ns=<current namespace> are listed and
    counted in ``in_crontab``. Other lango_core scheduler markers (different ns or legacy
    without ns=) are counted in ``foreign_scheduler_jobs``.
    """
    result = {
        'error': None,
        'entries': [],
        'active_in_db': 0,
        'in_crontab': 0,
        'scheduler_namespace': get_scheduler_namespace(),
        'foreign_scheduler_jobs': 0,
    }
    try:
        from crontab import CronTab
    except ImportError:
        result['error'] = "python-crontab is not installed."
        return result

    from scheduler.models import ScheduledWorkflow

    namespace = get_scheduler_namespace()
    active = ScheduledWorkflow.objects.filter(is_active=True).select_related('workflow', 'frequency')
    result['active_in_db'] = active.count()
    sw_by_id = {sw.pk: sw for sw in active}
    redis_client = _get_redis_client()

    try:
        cron = CronTab(user=True)
    except Exception as e:
        result['error'] = str(e)
        return result

    for job in cron:
        if not job.comment or MARKER_BASE not in job.comment:
            continue
        if not cron_comment_matches_namespace(job.comment, namespace):
            result['foreign_scheduler_jobs'] += 1
            continue
        result['in_crontab'] += 1
        m = _SW_ID_RE.search(job.comment)
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

    return result


def sync_crontab():
    """
    Sync all active ScheduledWorkflow entries to the system crontab for this deployment.
    Removes only cron rows marked with MARKER_BASE and ns=<current SCHEDULER_NAMESPACE>.

    Returns (success: bool, message: str).
    """
    try:
        from crontab import CronTab
    except ImportError:
        return False, "python-crontab is not installed. Run: pip install python-crontab"

    from scheduler.models import ScheduledWorkflow

    namespace = get_scheduler_namespace()
    cron = CronTab(user=True)

    to_remove = [
        job for job in cron
        if job.comment and cron_comment_matches_namespace(job.comment, namespace)
    ]
    for job in to_remove:
        cron.remove(job)

    base_dir = str(settings.BASE_DIR)
    python_path = os.environ.get('PYTHON_PATH', sys.executable)
    script_path = os.path.join(base_dir, 'scripts', 'run_workflow_cron.sh')

    for sw in ScheduledWorkflow.objects.filter(is_active=True).select_related('workflow', 'frequency'):
        cron_expr = sw.frequency.to_cron_expression()
        cmd = f"PYTHON_PATH={python_path} {script_path} {sw.pk}"
        comment = format_scheduler_cron_comment(sw.pk, namespace)
        job = cron.new(command=cmd, comment=comment)
        job.setall(cron_expr)

    cron.write()
    count = ScheduledWorkflow.objects.filter(is_active=True).count()
    return True, f"Synced {count} scheduled workflow(s) to crontab (namespace={namespace})."
