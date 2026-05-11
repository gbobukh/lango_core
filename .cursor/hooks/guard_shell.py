#!/usr/bin/env python3
"""Gate agent shell commands against agent-access-zones principle 2."""

from __future__ import annotations

import json
import re
import sys
from typing import Literal

Permission = Literal["allow", "deny", "ask"]

DENY_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"set_password|changepassword|createsuperuser", re.I),
        "Смена пароля или создание superuser через shell запрещены без явного запроса.",
    ),
    (
        re.compile(r"manage\.py\s+shell\b.*\bset_password\b", re.I | re.S),
        "manage.py shell с set_password запрещён без явного запроса.",
    ),
    (
        re.compile(r"git\s+push\b.*--force|git\s+push\s+-f\b|git\s+reset\s+--hard", re.I),
        "Опасная git-операция (force push / hard reset) запрещена без явного запроса.",
    ),
)

ASK_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bgit\s+(commit|push|merge|rebase|cherry-pick|reset|checkout|clean|stash)\b", re.I),
        "Git-команда с побочными эффектами требует подтверждения.",
    ),
    (
        re.compile(r"manage\.py\s+(migrate|flush|loaddata|sqlflush|dbshell)\b", re.I),
        "Команда Django меняет БД и требует подтверждения.",
    ),
    (
        re.compile(r"manage\.py\s+shell\b", re.I),
        "manage.py shell может менять данные; нужно подтверждение.",
    ),
    (
        re.compile(r"\brm\s+(-[^\s]*r[^\s]*f|-[^\s]*f[^\s]*r)", re.I),
        "Рекурсивное удаление требует подтверждения.",
    ),
    (
        re.compile(r"\b(DROP\s+TABLE|TRUNCATE\s+TABLE|DELETE\s+FROM)\b", re.I),
        "SQL с удалением данных требует подтверждения.",
    ),
    (
        re.compile(r"\b(pip|pip3|uv)\s+install\b|\bnpm\s+install\b|\byarn\s+add\b", re.I),
        "Установка зависимостей требует подтверждения.",
    ),
)


def emit(permission: Permission, user_message: str, agent_message: str) -> None:
    print(
        json.dumps(
            {
                "permission": permission,
                "user_message": user_message,
                "agent_message": agent_message,
            }
        )
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        emit(
            "allow",
            "",
            "Hook guard_shell: invalid JSON input; command allowed (fail-open).",
        )
        return 0

    command = payload.get("command") or ""
    if not command.strip():
        emit("allow", "", "")
        return 0

    for pattern, user_message in DENY_RULES:
        if pattern.search(command):
            emit(
                "deny",
                user_message,
                "Команда отклонена project hook guard_shell (принцип 2). "
                "Остановись и запроси подтверждение у пользователя.",
            )
            return 2

    for pattern, user_message in ASK_RULES:
        if pattern.search(command):
            emit(
                "ask",
                user_message,
                "Команда требует подтверждения пользователя (project hook guard_shell).",
            )
            return 0

    emit("allow", "", "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
