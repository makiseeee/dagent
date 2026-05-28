from __future__ import annotations

import difflib
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import yaml

from personal_agent.core.backup.git_backup import GitBackupManager
from personal_agent.core.config.loader import AppConfig
from personal_agent.plugins.schedule.recurring import (
    RecurringRule,
    RecurringStore,
    normalize_weekdays,
)


def _now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"recurring": []}

    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        return {"recurring": []}

    if "recurring" not in data or data["recurring"] is None:
        data["recurring"] = []

    return data


def _dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
    )


def _build_diff(path: Path, old_text: str, new_text: str) -> str:
    if old_text == new_text:
        return ""

    return "\n".join(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=f"{path} (before)",
            tofile=f"{path} (after)",
            lineterm="",
        )
    )


def _make_rule_id(title: str) -> str:
    suffix = uuid4().hex[:8]
    date_part = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")
    safe_hint = "".join(ch for ch in title.lower() if ch.isalnum())[:12]
    if safe_hint:
        return f"recur_{date_part}_{safe_hint}_{suffix}"
    return f"recur_{date_part}_{suffix}"


def prepare_add_recurring_rule(
    config: AppConfig,
    *,
    title: str,
    weekdays: list[str],
    time: str | None = None,
    reminder_minutes: int | None = 30,
    duration_minutes: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """
    Prepare adding a weekly recurring rule.

    This function does not write files.
    """
    store = RecurringStore(config.obsidian)
    path = store.path

    old_text = path.read_text(encoding="utf-8") if path.exists() else ""
    data = _read_yaml(path)

    normalized_weekdays = normalize_weekdays(weekdays)

    rule = RecurringRule(
        id=_make_rule_id(title),
        title=title.strip(),
        frequency="weekly",
        weekdays=normalized_weekdays,
        time=time,
        duration_minutes=duration_minutes,
        reminder_minutes=reminder_minutes,
        start_date=start_date or _today(),
        end_date=end_date,
        status="active",
        created_at=_now(),
        updated_at=None,
        note=note,
    )

    new_data = dict(data)
    new_data["recurring"] = list(data.get("recurring", [])) + [rule.model_dump()]
    new_text = _dump_yaml(new_data)
    diff = _build_diff(path, old_text, new_text)

    return {
        "operation": "schedule.recurring_add",
        "status": "prepared",
        "changed": old_text != new_text,
        "note_path": str(path),
        "diff": diff,
        "files": {str(path): new_text},
        "rule": rule.model_dump(),
        "message": "Prepared recurring rule creation.",
    }


def prepare_cancel_recurring_rule(
    config: AppConfig,
    *,
    rule_id: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """
    Prepare cancelling a recurring rule by id or fuzzy title query.

    This function does not write files.
    """
    store = RecurringStore(config.obsidian)
    path = store.path

    old_text = path.read_text(encoding="utf-8") if path.exists() else ""
    data = _read_yaml(path)
    items = list(data.get("recurring", []))

    matched_index: int | None = None
    matched_rule: RecurringRule | None = None

    for index, item in enumerate(items):
        rule = RecurringRule.model_validate(item)

        if rule.status != "active":
            continue

        if rule_id and rule.id == rule_id:
            matched_index = index
            matched_rule = rule
            break

        if query and query.strip() and query.strip() in rule.title:
            matched_index = index
            matched_rule = rule
            break

    if matched_index is None or matched_rule is None:
        return {
            "operation": "schedule.recurring_cancel",
            "status": "not_found",
            "changed": False,
            "note_path": str(path),
            "diff": "",
            "files": {},
            "rule_id": rule_id,
            "query": query,
            "message": "No active recurring rule matched.",
        }

    matched_rule.status = "cancelled"
    matched_rule.updated_at = _now()
    items[matched_index] = matched_rule.model_dump()

    new_data = dict(data)
    new_data["recurring"] = items
    new_text = _dump_yaml(new_data)
    diff = _build_diff(path, old_text, new_text)

    return {
        "operation": "schedule.recurring_cancel",
        "status": "prepared",
        "changed": old_text != new_text,
        "note_path": str(path),
        "diff": diff,
        "files": {str(path): new_text},
        "rule": matched_rule.model_dump(),
        "rule_id": matched_rule.id,
        "query": query,
        "message": "Prepared recurring rule cancellation.",
    }


def apply_recurring_proposal(
    config: AppConfig,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    operation = proposal.get("operation")

    if operation not in {
        "schedule.recurring_add",
        "schedule.recurring_cancel",
    }:
        raise ValueError(f"Unsupported operation: {operation}")

    if not proposal.get("changed"):
        return {
            "status": "no_changes",
            "message": proposal.get("message") or "Nothing to change.",
        }

    files = proposal.get("files") or {}

    if not isinstance(files, dict) or not files:
        return {
            "status": "blocked",
            "message": "No file changes found in proposal.",
        }

    pre_backup = None
    post_commit = None

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        pre_backup = manager.commit_all("Backup before recurring rule change")

    for path_text, new_text in files.items():
        path = Path(path_text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_text, encoding="utf-8")

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        post_commit = manager.commit_all("Agent update recurring rules")

    return {
        "status": "applied",
        "operation": operation,
        "changed_files": list(files.keys()),
        "rule": proposal.get("rule"),
        "pre_backup": pre_backup,
        "post_commit": post_commit,
    }