from pathlib import Path
from typing import Any

from personal_agent.core.config.loader import AppConfig
from personal_agent.core.llm.client import LLMClient
from personal_agent.core.backup.git_backup import GitBackupManager
from personal_agent.plugins.schedule.obsidian.reader import ObsidianScheduleReader
from personal_agent.plugins.schedule.organizer import organize_schedule_items
from personal_agent.plugins.schedule.obsidian.writer import build_append_schedule_plan


def prepare_adopt_overdue_today(
    config: AppConfig,
    llm: LLMClient | None = None,
    *,
    lookback_days: int = 7,
    llm_rewrite: bool = False,
) -> dict[str, Any]:
    """
    Prepare a proposal to append overdue unfinished schedule tasks into today's ## 日程.

    This function does not write files.
    """
    reader = ObsidianScheduleReader(config.obsidian)

    today = reader.resolve_date("today")
    overview = reader.read_today_overview(lookback_days=lookback_days)

    overdue_items = overview.get("overdue_items", [])

    rewritten_items = overdue_items

    if llm_rewrite and llm is not None and overdue_items:
        rewritten_items = organize_schedule_items(
            llm,
            overdue_items,
            target_date=today,
        )

    today_note_path = reader.get_daily_note_path(today)

    plan = build_append_schedule_plan(
        note_path=today_note_path,
        items=rewritten_items,
        heading="日程",
    )

    return {
        "operation": "schedule.adopt_overdue_today",
        "target_date": today,
        "lookback_days": lookback_days,
        "note_path": plan.note_path,
        "heading": plan.heading,
        "changed": plan.changed,
        "new_lines": plan.new_lines,
        "skipped_duplicates": plan.skipped_duplicates,
        "diff": plan.diff,
        "new_text": plan.new_text,
        "llm_rewrite": llm_rewrite,
        "source_items": [
            {
                "content": item.get("content"),
                "effective_date": item.get("effective_date"),
                "source_file": item.get("source_file"),
                "line_number": item.get("line_number"),
            }
            for item in overdue_items
        ],
        "rewritten_items": [
            {
                "original": item.get("content"),
                "schedule_content": item.get("schedule_content") or item.get("content"),
                "suggested_type": item.get("suggested_type"),
                "rewrite_reason": item.get("rewrite_reason"),
            }
            for item in rewritten_items
        ],
    }


def apply_adopt_overdue_today(
    config: AppConfig,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    if proposal.get("operation") != "schedule.adopt_overdue_today":
        raise ValueError(f"Unsupported operation: {proposal.get('operation')}")

    if not proposal.get("changed"):
        return {
            "status": "no_changes",
            "message": "Nothing to change.",
        }

    note_path = Path(proposal["note_path"])
    new_text = proposal["new_text"]

    pre_backup = None
    post_commit = None

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        pre_backup = manager.commit_all("Backup before agent adopt overdue items")

    note_path.write_text(new_text, encoding="utf-8")

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        post_commit = manager.commit_all("Agent adopt overdue items into today")

    return {
        "status": "applied",
        "target_date": proposal.get("target_date"),
        "note_path": str(note_path),
        "new_lines": proposal.get("new_lines", []),
        "pre_backup": pre_backup,
        "post_commit": post_commit,
    }