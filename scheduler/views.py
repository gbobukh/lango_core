import os
import subprocess
import sys
import uuid
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.decorators import method_decorator

from .crontab import (
    get_crontab_info,
    is_scheduled_workflow_running,
    scheduled_workflow_redis_lock_key,
)

SCHEDULED_WORKFLOW_LOCK_TTL_SECONDS = 60 * 60  # 1 hour


def _get_redis_client():
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


def _release_lock_if_owned(client, lock_key, token):
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
        pass


@method_decorator(staff_member_required, name='dispatch')
class CrontabView(View):
    """Read-only view of current crontab with scheduler entries and status."""

    def get(self, request):
        info = get_crontab_info()
        return render(request, 'admin/scheduler/crontab_view.html', {
            'crontab_info': info,
            'title': 'Crontab',
        })


@method_decorator(staff_member_required, name='dispatch')
class RunScheduledWorkflowView(View):
    """Trigger scheduled workflow run asynchronously from admin."""

    def get(self, request, sw_id):
        messages.warning(request, 'Run action requires POST.')
        return redirect('admin:scheduler_scheduledworkflow_crontab')

    def post(self, request, sw_id):
        from .models import ScheduledWorkflow
        try:
            ScheduledWorkflow.objects.get(pk=sw_id)
        except ScheduledWorkflow.DoesNotExist:
            messages.error(request, f'ScheduledWorkflow {sw_id} not found.')
            return redirect('admin:scheduler_scheduledworkflow_crontab')

        if is_scheduled_workflow_running(sw_id):
            messages.warning(request, f'ScheduledWorkflow {sw_id} is already running.')
            return redirect('admin:scheduler_scheduledworkflow_crontab')

        lock_client = None
        lock_key = scheduled_workflow_redis_lock_key(sw_id)
        lock_token = None
        lock_acquired = False
        lock_client = _get_redis_client()
        if lock_client:
            lock_token = uuid.uuid4().hex
            lock_acquired = bool(
                lock_client.set(
                    lock_key,
                    lock_token,
                    nx=True,
                    ex=SCHEDULED_WORKFLOW_LOCK_TTL_SECONDS,
                )
            )
            if not lock_acquired:
                messages.warning(request, f'ScheduledWorkflow {sw_id} is already running.')
                return redirect('admin:scheduler_scheduledworkflow_crontab')

        base_dir = str(settings.BASE_DIR)
        python_path = os.environ.get('PYTHON_PATH', sys.executable)
        cmd = [
            python_path,
            'manage.py',
            'run_workflow',
            f'--scheduled-workflow={sw_id}',
        ]
        if lock_acquired and lock_token:
            cmd.append(f'--lock-token={lock_token}')

        log_fh = None
        try:
            date_str = datetime.now().strftime('%Y-%m-%d')
            log_dir = os.path.join(base_dir, 'logs', 'cron_workflow', date_str)
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, f'sw_{sw_id}.log')
            log_fh = open(log_path, 'a', encoding='utf-8')
            log_fh.write(f"\n[manual-trigger] started from admin at {datetime.now().isoformat()}\n")
            log_fh.flush()
            subprocess.Popen(
                cmd,
                cwd=base_dir,
                stdout=log_fh,
                stderr=log_fh,
                start_new_session=True,
                close_fds=True,
            )
        except Exception as e:
            if lock_acquired:
                _release_lock_if_owned(lock_client, lock_key, lock_token)
            messages.error(request, f'Failed to start run: {e}')
            return redirect('admin:scheduler_scheduledworkflow_crontab')
        finally:
            if log_fh:
                log_fh.close()

        messages.success(request, f'ScheduledWorkflow {sw_id} started in background.')
        return redirect('admin:scheduler_scheduledworkflow_crontab')


@method_decorator(staff_member_required, name='dispatch')
class GetWorkflowArgumentsView(View):
    """Returns workflow.arguments for the given workflow_id. Used by ScheduledWorkflow argument mapping widget."""

    def get(self, request, workflow_id):
        from service_builder.models import Workflow
        try:
            workflow = Workflow.objects.get(pk=workflow_id)
            args = workflow.arguments or []
            # Normalize: ensure each arg has name, type
            normalized = []
            for a in args:
                if isinstance(a, str):
                    normalized.append({'name': a, 'type': 'string'})
                elif isinstance(a, dict):
                    n = dict(a)
                    n.setdefault('name', '')
                    n.setdefault('type', 'string')
                    normalized.append(n)
            return JsonResponse({'arguments': normalized})
        except Workflow.DoesNotExist:
            return JsonResponse({'arguments': []})
