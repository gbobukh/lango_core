#!/bin/bash
# Wrapper for cron: avoids % escaping issues in crontab.
# Usage: run_workflow_cron.sh <sw_id>
# Called by scheduler/crontab.py sync.
# Uses PYTHON_PATH env if set (from sync), else python3.

set -e
cd "$(dirname "$0")/.."
DATE=$(date +%Y-%m-%d)
mkdir -p logs/cron_workflow/$DATE
PYTHON="${PYTHON_PATH:-python3}"
exec $PYTHON manage.py run_workflow --scheduled-workflow=$1 >> logs/cron_workflow/$DATE/sw_$1.log 2>&1
