from pathlib import Path
from typing import Any

from personal_agent.core.config.loader import AppConfig
from personal_agent.core.llm.client import LLMClient
from personal_agent.core.backup.git_backup import GitBackupManager
from personal_agent.plugins.schedule.obsidian.reader import ObsidianScheduleReader
from personal_agent.plugins.schedule.organizer import organize_schedule_items
from personal_agent.plugins.schedule.obsidian.writer import build_append_schedule_plan
import difflib
from personal_agent.plugins.schedule.obsidian.capture_marker import ORGANIZED_TAG

def prepare_organize_today(
    config: AppConfig,
    llm: LLMClient,
    *,
    llm_rewrite: bool = True,
) -> dict[str, Any]:
    """
    Prepare a proposal for organizing today's Thino inbox items into today's ## 日程.

    This function must not write files.
    """
    reader = ObsidianScheduleReader(config.obsidian)

    today = reader.resolve_date("today")
    inbox = reader.read_inbox_items(days=1, include_organized=False)

    today_items = inbox.get("groups", {}).get("today", [])

    candidates = [
        item
        for item in today_items
        if item.get("suggested_type") in {"task", "event"} or item.get("actionable")
    ]

    rewritten_items = candidates

    if llm_rewrite and candidates:
        rewritten_items = organize_schedule_items(
            llm,
            candidates,
            target_date=today,
        )

    note_path = reader.get_daily_note_path(today)

    plan = build_append_schedule_plan(
        note_path=note_path,
        items=rewritten_items,
        heading="日程",
    )
    final_new_text = plan.new_text
    final_diff = plan.diff

    if plan.changed:
        note_path = plan.note_path
        lines = final_new_text.splitlines()

        for item in candidates:
            source_file = item.get("source_file")
            line_number = item.get("line_number")

            # 第一版只处理同一个 daily note 文件
            if not source_file or str(source_file) != str(note_path):
                continue

            if not line_number:
                continue

            index = int(line_number) - 1

            if index < 0 or index >= len(lines):
                continue

            if ORGANIZED_TAG in lines[index]:
                continue

            lines[index] = lines[index].rstrip() + f" {ORGANIZED_TAG}"

        final_new_text = "\n".join(lines) + "\n"

        old_text = Path(note_path).read_text(encoding="utf-8")

        final_diff = "\n".join(
            difflib.unified_diff(
                old_text.splitlines(),
                final_new_text.splitlines(),
                fromfile=f"{note_path} (before)",
                tofile=f"{note_path} (after)",
                lineterm="",
            )
        )

    return {
        "operation": "schedule.organize_today",
        "target_date": today,
        "note_path": plan.note_path,
        "heading": plan.heading,
        "changed": plan.changed,
        "new_lines": plan.new_lines,
        "skipped_duplicates": plan.skipped_duplicates,
        "diff": final_diff,
        "new_text": final_new_text,
        "organized_tag": ORGANIZED_TAG,
        "llm_rewrite": llm_rewrite,
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


def apply_organize_today(
    config: AppConfig,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    """
    Apply a previously prepared organize_today proposal.
    """
    if proposal.get("operation") != "schedule.organize_today":
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
        pre_backup = manager.commit_all("Backup before agent organize today's schedule")

    note_path.write_text(new_text, encoding="utf-8")

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        post_commit = manager.commit_all("Agent organize today's schedule")

    return {
        "status": "applied",
        "note_path": str(note_path),
        "new_lines": proposal.get("new_lines", []),
        "pre_backup": pre_backup,
        "post_commit": post_commit,
    }