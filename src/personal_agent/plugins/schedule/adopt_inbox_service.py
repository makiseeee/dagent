from pathlib import Path
from typing import Any
import difflib

from personal_agent.core.config.loader import AppConfig
from personal_agent.core.llm.client import LLMClient
from personal_agent.core.backup.git_backup import GitBackupManager
from personal_agent.plugins.schedule.obsidian import ObsidianScheduleReader
from personal_agent.plugins.schedule.organizer import organize_schedule_items
from personal_agent.plugins.schedule.writer import build_append_schedule_plan
from personal_agent.plugins.schedule.capture_marker import ORGANIZED_TAG


def _read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _write_text(path: str | Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mark_source_line_organized(
    text: str,
    item: dict[str, Any],
) -> str:
    """
    Add #agent/organized to the source Thino line.

    Prefer matching raw_line because writing to today's ## 日程 may shift line numbers
    when source_file == target note.
    """
    raw_line = item.get("raw_line")
    line_number = item.get("line_number")

    lines = text.splitlines()

    target_index: int | None = None

    if raw_line:
        for idx, line in enumerate(lines):
            if line.rstrip() == str(raw_line).rstrip():
                target_index = idx
                break

    if target_index is None and line_number:
        idx = int(line_number) - 1
        if 0 <= idx < len(lines):
            target_index = idx

    if target_index is None:
        return text

    if ORGANIZED_TAG in lines[target_index]:
        return text

    lines[target_index] = lines[target_index].rstrip() + f" {ORGANIZED_TAG}"
    return "\n".join(lines) + "\n"


def _build_multi_file_diff(
    old_text_by_path: dict[str, str],
    new_text_by_path: dict[str, str],
) -> str:
    chunks: list[str] = []

    for path in sorted(new_text_by_path.keys()):
        old_text = old_text_by_path.get(path, "")
        new_text = new_text_by_path[path]

        if old_text == new_text:
            continue

        chunks.append(
            "\n".join(
                difflib.unified_diff(
                    old_text.splitlines(),
                    new_text.splitlines(),
                    fromfile=f"{path} (before)",
                    tofile=f"{path} (after)",
                    lineterm="",
                )
            )
        )

    return "\n\n".join(chunk for chunk in chunks if chunk)


def prepare_adopt_inbox_today(
    config: AppConfig,
    llm: LLMClient | None = None,
    *,
    lookback_days: int = 7,
    llm_rewrite: bool = True,
) -> dict[str, Any]:
    """
    Prepare a proposal to adopt due inbox items into today's ## 日程.

    Inbox items are Thino capture items that are not marked #agent/organized.
    This function does not write files.
    """
    reader = ObsidianScheduleReader(config.obsidian)

    today = reader.resolve_date("today")
    inbox = reader.read_inbox_items(
        days=lookback_days,
        include_organized=False,
    )

    groups = inbox.get("groups", {})
    candidates = groups.get("overdue", []) + groups.get("today", [])

    candidates = [
        item
        for item in candidates
        if item.get("suggested_type") in {"task", "event"} or item.get("actionable")
    ]

    if not candidates:
        return {
            "operation": "schedule.adopt_inbox_today",
            "status": "no_candidates",
            "target_date": today,
            "lookback_days": lookback_days,
            "changed": False,
            "message": "No due inbox items to adopt into today's schedule.",
            "new_lines": [],
            "skipped_duplicates": [],
            "diff": "",
            "files": {},
            "source_items": [],
            "rewritten_items": [],
        }

    rewritten_items = candidates

    if llm_rewrite and llm is not None:
        rewritten_items = organize_schedule_items(
            llm,
            candidates,
            target_date=today,
        )

    today_note_path = reader.get_daily_note_path(today)

    append_plan = build_append_schedule_plan(
        note_path=today_note_path,
        items=rewritten_items,
        heading="日程",
    )

    old_text_by_path: dict[str, str] = {}
    new_text_by_path: dict[str, str] = {}

    target_path = str(Path(today_note_path))

    if Path(today_note_path).exists():
        old_text_by_path[target_path] = _read_text(today_note_path)
    else:
        old_text_by_path[target_path] = ""

    new_text_by_path[target_path] = append_plan.new_text

    # Mark all adopted candidates as organized, including duplicates.
    # If a candidate is skipped because today's schedule already contains it,
    # it should still leave the inbox.
    for item in candidates:
        source_file = item.get("source_file")
        if not source_file:
            continue

        source_path = str(Path(source_file))

        if source_path not in old_text_by_path:
            old_text_by_path[source_path] = _read_text(source_path)

        current_text = new_text_by_path.get(source_path, old_text_by_path[source_path])
        new_text_by_path[source_path] = _mark_source_line_organized(
            current_text,
            item,
        )

    changed_files = {
        path: text
        for path, text in new_text_by_path.items()
        if old_text_by_path.get(path, "") != text
    }

    diff = _build_multi_file_diff(
        old_text_by_path=old_text_by_path,
        new_text_by_path=new_text_by_path,
    )

    return {
        "operation": "schedule.adopt_inbox_today",
        "status": "prepared" if changed_files else "no_changes",
        "target_date": today,
        "lookback_days": lookback_days,
        "note_path": append_plan.note_path,
        "heading": append_plan.heading,
        "changed": bool(changed_files),
        "changed_files": list(changed_files.keys()),
        "files": changed_files,
        "new_lines": append_plan.new_lines,
        "skipped_duplicates": append_plan.skipped_duplicates,
        "diff": diff,
        "organized_tag": ORGANIZED_TAG,
        "llm_rewrite": llm_rewrite,
        "source_items": [
            {
                "content": item.get("content"),
                "effective_date": item.get("effective_date"),
                "bucket": item.get("bucket"),
                "source_file": item.get("source_file"),
                "line_number": item.get("line_number"),
            }
            for item in candidates
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


def apply_adopt_inbox_today(
    config: AppConfig,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    if proposal.get("operation") != "schedule.adopt_inbox_today":
        raise ValueError(f"Unsupported operation: {proposal.get('operation')}")

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
        pre_backup = manager.commit_all("Backup before agent adopt inbox items")

    for path, text in files.items():
        _write_text(path, text)

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        post_commit = manager.commit_all("Agent adopt inbox items into today")

    return {
        "status": "applied",
        "target_date": proposal.get("target_date"),
        "changed_files": list(files.keys()),
        "new_lines": proposal.get("new_lines", []),
        "pre_backup": pre_backup,
        "post_commit": post_commit,
    }