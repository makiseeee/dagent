from __future__ import annotations

from pathlib import Path
from typing import Any

from personal_agent.core.backup.git_backup import GitBackupManager
from personal_agent.core.config.loader import AppConfig
from personal_agent.core.llm.client import LLMClient
from personal_agent.plugins.schedule.obsidian.matcher import is_same_or_rewrite
from personal_agent.plugins.schedule.obsidian.reader import ObsidianScheduleReader
from personal_agent.plugins.schedule.obsidian.writer import build_append_schedule_plan


def _normalize_content(content: str) -> str:
    return content.strip(" \t\r\n：:，,。.!！?？")


def _today_has_similar_item(
    reader: ObsidianScheduleReader,
    *,
    target_date: str,
    content: str,
) -> bool:
    result = reader.read_daily_items(target_date, include_recurring=False)

    for item in result.get("items", []):
        if item.get("section") != "日程":
            continue

        if is_same_or_rewrite(content, item.get("content") or ""):
            return True

    return False


def prepare_add_today_item(
    config: AppConfig,
    *,
    content: str,
    llm: LLMClient | None = None,
    llm_rewrite: bool = True,
) -> dict[str, Any]:
    """
    Prepare a proposal to append one unchecked task into today's ## 日程.

    This function does not write files.
    """
    del llm
    reader = ObsidianScheduleReader(config.obsidian)
    target_date = reader.resolve_date("today")
    note_path = reader.get_daily_note_path(target_date)
    schedule_content = _normalize_content(content)

    if not note_path.exists():
        return {
            "operation": "schedule.add_today_item",
            "status": "target_note_missing",
            "changed": False,
            "target_date": target_date,
            "note_path": str(note_path),
            "content": content,
            "schedule_content": schedule_content,
            "message": "Target daily note does not exist. Please create it first.",
            "diff": "",
            "files": {},
        }

    if not schedule_content:
        return {
            "operation": "schedule.add_today_item",
            "status": "no_changes",
            "changed": False,
            "target_date": target_date,
            "note_path": str(note_path),
            "content": content,
            "schedule_content": schedule_content,
            "message": "No task content provided.",
            "diff": "",
            "files": {},
        }

    if _today_has_similar_item(
        reader,
        target_date=target_date,
        content=schedule_content,
    ):
        return {
            "operation": "schedule.add_today_item",
            "status": "duplicate",
            "changed": False,
            "target_date": target_date,
            "note_path": str(note_path),
            "content": content,
            "schedule_content": schedule_content,
            "message": "A same or similar task already exists in today's schedule.",
            "new_lines": [],
            "skipped_duplicates": [schedule_content],
            "diff": "",
            "files": {},
        }

    plan = build_append_schedule_plan(
        note_path=note_path,
        items=[
            {
                "content": schedule_content,
                "schedule_content": schedule_content,
                "suggested_type": "task",
            }
        ],
        heading="日程",
    )

    status = "prepared" if plan.changed else "no_changes"

    return {
        "operation": "schedule.add_today_item",
        "status": status,
        "changed": plan.changed,
        "target_date": target_date,
        "note_path": plan.note_path,
        "heading": plan.heading,
        "content": content,
        "schedule_content": schedule_content,
        "new_lines": plan.new_lines,
        "skipped_duplicates": plan.skipped_duplicates,
        "diff": plan.diff,
        "old_text": plan.old_text,
        "new_text": plan.new_text,
        "files": {plan.note_path: plan.new_text} if plan.changed else {},
        "llm_rewrite": llm_rewrite,
    }


def apply_add_today_item(
    config: AppConfig,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    if proposal.get("operation") != "schedule.add_today_item":
        raise ValueError(f"Unsupported operation: {proposal.get('operation')}")

    if proposal.get("status") != "prepared":
        return {
            "status": "blocked",
            "message": f"Proposal status is not prepared: {proposal.get('status')}",
        }

    if not proposal.get("changed"):
        return {
            "status": "no_changes",
            "message": proposal.get("message") or "Nothing to change.",
        }

    reader = ObsidianScheduleReader(config.obsidian)
    target_date = reader.resolve_date("today")
    expected_note_path = str(reader.get_daily_note_path(target_date))
    note_path = str(proposal.get("note_path") or "")
    files = proposal.get("files") or {}

    if note_path != expected_note_path:
        return {
            "status": "blocked",
            "message": "Add-today proposal may only modify today's daily note.",
            "note_path": note_path,
            "expected_note_path": expected_note_path,
        }

    if set(files) != {expected_note_path}:
        return {
            "status": "blocked",
            "message": "Add-today proposal contains unexpected file changes.",
        }

    path = Path(expected_note_path)

    if not path.exists():
        return {
            "status": "blocked",
            "message": "Target daily note no longer exists.",
            "note_path": expected_note_path,
        }

    current_text = path.read_text(encoding="utf-8")
    old_text = proposal.get("old_text")
    new_text = proposal.get("new_text")

    if current_text != old_text:
        return {
            "status": "blocked",
            "message": "File changed since proposal was prepared.",
            "note_path": expected_note_path,
        }

    if files[expected_note_path] != new_text:
        return {
            "status": "blocked",
            "message": "Proposal file content does not match new_text.",
        }

    expected_proposal = prepare_add_today_item(
        config,
        content=str(proposal.get("content") or ""),
        llm=None,
        llm_rewrite=bool(proposal.get("llm_rewrite", True)),
    )

    if expected_proposal.get("new_text") != new_text:
        return {
            "status": "blocked",
            "message": "Add-today proposal contains changes outside the prepared append.",
        }

    pre_backup = None
    post_commit = None

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        pre_backup = manager.commit_all("Backup before agent add today item")

    path.write_text(new_text, encoding="utf-8")

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        post_commit = manager.commit_all("Agent add item into today's schedule")

    return {
        "status": "applied",
        "target_date": proposal.get("target_date"),
        "note_path": expected_note_path,
        "new_lines": proposal.get("new_lines", []),
        "pre_backup": pre_backup,
        "post_commit": post_commit,
    }
