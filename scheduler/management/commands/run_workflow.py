"""
Management command to run a workflow by ID or by ScheduledWorkflow.
Used by cron: python manage.py run_workflow --scheduled-workflow=1
"""
import os
import sys
import uuid
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand

from service_builder.utils import WorkflowRunner
from scheduler.crontab import scheduled_workflow_redis_lock_key


SCHEDULED_WORKFLOW_LOCK_TTL_SECONDS = 60 * 60  # 1 hour


def _get_cron_workflow_log_path(sw_id):
    """Path: logs/cron_workflow/{date}/sw_{id}.log (rotation by day)."""
    date_str = datetime.now().strftime('%Y-%m-%d')
    return os.path.join(settings.BASE_DIR, 'logs', 'cron_workflow', date_str, f'sw_{sw_id}.log')


def _append_cron_workflow_log(log_path, sw_id, workflow_name, success, error, logs):
    """Append a structured block to the log file."""
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, 'a', encoding='utf-8') as f:
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            status = 'SUCCESS' if success else 'FAILED'
            f.write(f"\n{'='*60}\n")
            f.write(f"[{ts}] sw_id={sw_id} workflow=\"{workflow_name}\" {status}\n")
            if error:
                f.write(f"  Error: {error}\n")
            if logs:
                for line in logs:
                    f.write(f"  {str(line)}\n")
            f.write(f"{'='*60}\n")
    except Exception as e:
        pass  # Don't fail the workflow if logging fails


def _get_redis_client():
    """Return Redis client, or None if unavailable."""
    try:
        import redis
    except Exception:
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


def _acquire_scheduled_workflow_lock(sw_id):
    """
    Acquire distributed lock for a ScheduledWorkflow.
    Returns tuple: (acquired: bool, token: str|None, client|None, key: str).
    """
    lock_key = scheduled_workflow_redis_lock_key(sw_id)
    client = _get_redis_client()
    if not client:
        # Redis unavailable -> fail-open to avoid breaking scheduled execution.
        return True, None, None, lock_key

    token = uuid.uuid4().hex
    acquired = bool(
        client.set(
            lock_key,
            token,
            nx=True,
            ex=SCHEDULED_WORKFLOW_LOCK_TTL_SECONDS,
        )
    )
    if not acquired:
        return False, None, client, lock_key
    return True, token, client, lock_key


def _release_scheduled_workflow_lock(client, lock_key, token):
    """
    Release lock only if token matches current lock owner.
    Prevents deleting a lock acquired by another process after TTL expiry.
    """
    if not client or not token:
        return
    try:
        release_script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        end
        return 0
        """
        client.eval(release_script, 1, lock_key, token)
    except Exception:
        # Never fail workflow result due to lock release errors.
        pass


class Command(BaseCommand):
    help = "Run a workflow by ID or by ScheduledWorkflow ID."

    def add_arguments(self, parser):
        parser.add_argument(
            '--workflow',
            type=int,
            help='Workflow ID to run (uses empty context)',
        )
        parser.add_argument(
            '--scheduled-workflow',
            type=int,
            help='ScheduledWorkflow ID (uses workflow + default_arguments)',
        )
        parser.add_argument(
            '--lock-token',
            type=str,
            help='Pre-acquired Redis lock token for scheduled workflow execution.',
        )

    def handle(self, *args, **options):
        workflow_id = options.get('workflow')
        scheduled_id = options.get('scheduled_workflow')
        prelock_token = options.get('lock_token')

        if workflow_id and scheduled_id:
            self.stderr.write(self.style.ERROR('Use only one of --workflow or --scheduled-workflow.'))
            sys.exit(1)

        if not workflow_id and not scheduled_id:
            self.stderr.write(self.style.ERROR('Provide --workflow or --scheduled-workflow.'))
            sys.exit(1)

        sw = None
        if scheduled_id:
            from scheduler.models import ScheduledWorkflow
            from scheduler.utils import resolve_default_arguments
            try:
                sw = ScheduledWorkflow.objects.select_related('workflow').get(
                    pk=scheduled_id, is_active=True
                )
            except ScheduledWorkflow.DoesNotExist:
                self.stderr.write(self.style.ERROR(f'ScheduledWorkflow {scheduled_id} not found or inactive.'))
                sys.exit(1)
            workflow_id = sw.workflow_id
            initial_context = resolve_default_arguments(
                sw.default_arguments or {},
                sw.workflow.arguments if sw.workflow_id else [],
            )
        else:
            from service_builder.models import Workflow
            try:
                Workflow.objects.get(pk=workflow_id)
            except Workflow.DoesNotExist:
                self.stderr.write(self.style.ERROR(f'Workflow {workflow_id} not found.'))
                sys.exit(1)
            initial_context = {}

        lock_client = None
        lock_key = None
        lock_token = None
        if scheduled_id:
            if prelock_token:
                lock_key = scheduled_workflow_redis_lock_key(scheduled_id)
                lock_client = _get_redis_client()
                if not lock_client:
                    self.stderr.write(
                        self.style.ERROR(
                            f"Cannot validate pre-acquired lock for ScheduledWorkflow {scheduled_id}: Redis unavailable."
                        )
                    )
                    sys.exit(1)
                current_token = lock_client.get(lock_key)
                if current_token != prelock_token:
                    self.stdout.write(
                        self.style.WARNING(
                            f"ScheduledWorkflow {scheduled_id} lock token mismatch/expired. Skipping launch."
                        )
                    )
                    sys.exit(0)
                lock_token = prelock_token
            else:
                acquired, lock_token, lock_client, lock_key = _acquire_scheduled_workflow_lock(scheduled_id)
                if not acquired:
                    self.stdout.write(
                        self.style.WARNING(
                            f'ScheduledWorkflow {scheduled_id} is already running. Skipping duplicate launch.'
                        )
                    )
                    sys.exit(0)

        try:
            runner = WorkflowRunner(workflow_id, initial_context)
            result = runner.run()
            success = result.get('success')
            error = result.get('error', '')
            logs = result.get('logs', [])

            if sw:
                log_path = _get_cron_workflow_log_path(scheduled_id)
                workflow_name = sw.workflow.name if sw.workflow else f'Workflow {workflow_id}'
                _append_cron_workflow_log(log_path, scheduled_id, workflow_name, success, error, logs)

            if success:
                self.stdout.write(self.style.SUCCESS(f'Workflow {workflow_id} completed successfully.'))
            else:
                self.stderr.write(self.style.ERROR(f'Workflow {workflow_id} failed: {error or "unknown"}'))
                sys.exit(1)
        finally:
            if scheduled_id:
                _release_scheduled_workflow_lock(lock_client, lock_key, lock_token)
