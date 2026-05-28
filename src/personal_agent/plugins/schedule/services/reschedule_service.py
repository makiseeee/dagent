from __future__ import annotations

import difflib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from personal_agent.core.backup.git_backup import GitBackupManager
from personal_agent.core.config.loader import AppConfig
from personal_agent.plugins.schedule.obsidian.matcher import (
    is_same_or_rewrite,
    text_similarity,
)
from personal_agent.plugins.schedule.obsidian.reader import ObsidianScheduleReader
from personal_agent.plugins.schedule.obsidian.writer import find_section_bounds


AUTO_APPLY_THRESHOLD = 0.48
AMBIGUOUS_MARGIN = 0.08
RESCHEDULE_TAG = "#agent/rescheduled"

ZH_WEEKDAY_TO_INDEX = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}


def _today() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def _parse_target_date(target_date_text: str) -> str | None:
    text = target_date_text.strip()

    if not text:
        return None

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return datetime.strptime(text, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None

    today = _today().date()

    if "后天" in text:
        return (today + timedelta(days=2)).isoformat()

    if "明天" in text:
        return (today + timedelta(days=1)).isoformat()

    match = re.search(r"下周\s*([一二三四五六日天])", text)
    if match:
        target_weekday = ZH_WEEKDAY_TO_INDEX[match.group(1)]
        start_of_next_week = today + timedelta(days=(7 - today.weekday()))
        return (start_of_next_week + timedelta(days=target_weekday)).isoformat()

    return None


def _append_rescheduled_tag(line: str) -> str:
    if RESCHEDULE_TAG in line:
        return line
    return f"{line.rstrip()} {RESCHEDULE_TAG}"


def _item_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": item.get("content"),
        "effective_date": item.get("effective_date"),
        "source_file": item.get("source_file"),
        "line_number": item.get("line_number"),
        "match_score": item.get("match_score"),
    }


def _build_diff(old_files: dict[str, str], files: dict[str, str]) -> str:
    chunks: list[str] = []

    for path in sorted(files):
        old_text = old_files[path]
        new_text = files[path]

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

    return "\n".join(chunk for chunk in chunks if chunk)


def _find_candidates(
    config: AppConfig,
    *,
    target_text: str,
    days: int,
) -> list[dict[str, Any]]:
    reader = ObsidianScheduleReader(config.obsidian)
    recent = reader.read_recent_items(days=days, include_today=True)
    candidates: list[dict[str, Any]] = []

    for item in recent.get("items", []):
        if item.get("section") != "日程":
            continue

        if item.get("done") is True:
            continue

        if item.get("item_type") != "task":
            continue

        content = item.get("content") or ""
        score = text_similarity(target_text, content)

        enriched = dict(item)
        enriched["match_score"] = score
        candidates.append(enriched)

    candidates.sort(key=lambda item: item.get("match_score", 0), reverse=True)
    return candidates


def _target_has_similar_item(
    config: AppConfig,
    *,
    target_date: str,
    content: str,
) -> bool:
    reader = ObsidianScheduleReader(config.obsidian)
    result = reader.read_daily_items(target_date, include_recurring=False)

    for item in result.get("items", []):
        if item.get("section") != "日程":
            continue

        if is_same_or_rewrite(content, item.get("content") or ""):
            return True

    return False


def prepare_reschedule_item(
    config: AppConfig,
    *,
    target_text: str,
    target_date_text: str,
    days: int = 7,
) -> dict[str, Any]:
    """
    Prepare a conservative reschedule proposal.

    This function does not write files.
    """
    target_date = _parse_target_date(target_date_text)

    if target_date is None:
        return {
            "operation": "schedule.reschedule_item",
            "status": "not_found",
            "changed": False,
            "target_text": target_text,
            "target_date_text": target_date_text,
            "message": "Unsupported target date. Use 明天, 后天, 下周一, or YYYY-MM-DD.",
            "candidates": [],
        }

    reader = ObsidianScheduleReader(config.obsidian)
    target_note_path = reader.get_daily_note_path(target_date)

    if not target_note_path.exists():
        return {
            "operation": "schedule.reschedule_item",
            "status": "target_note_missing",
            "changed": False,
            "target_text": target_text,
            "target_date_text": target_date_text,
            "target_date": target_date,
            "note_path": str(target_note_path),
            "message": "Target daily note does not exist. Please create it first.",
            "candidates": [],
        }

    candidates = _find_candidates(config, target_text=target_text, days=days)

    if not candidates:
        return {
            "operation": "schedule.reschedule_item",
            "status": "not_found",
            "changed": False,
            "target_text": target_text,
            "target_date_text": target_date_text,
            "target_date": target_date,
            "message": "No matching unfinished schedule task found.",
            "candidates": [],
        }

    best = candidates[0]
    best_score = best.get("match_score", 0)
    best_content = best.get("content") or ""

    if (
        best_score < AUTO_APPLY_THRESHOLD
        and target_text not in best_content
        and best_content not in target_text
    ):
        return {
            "operation": "schedule.reschedule_item",
            "status": "low_confidence",
            "changed": False,
            "target_text": target_text,
            "target_date_text": target_date_text,
            "target_date": target_date,
            "message": "Best match confidence is too low.",
            "best_score": best_score,
            "candidates": [_item_summary(item) for item in candidates[:5]],
        }

    if len(candidates) >= 2:
        second = candidates[1]
        second_score = second.get("match_score", 0)

        if best_score - second_score < AMBIGUOUS_MARGIN:
            return {
                "operation": "schedule.reschedule_item",
                "status": "ambiguous_match",
                "changed": False,
                "target_text": target_text,
                "target_date_text": target_date_text,
                "target_date": target_date,
                "message": "Multiple candidates are too close. Refusing automatic reschedule.",
                "best_score": best_score,
                "second_score": second_score,
                "candidates": [_item_summary(item) for item in candidates[:5]],
            }

    source_path = Path(best["source_file"])
    source_old_text = source_path.read_text(encoding="utf-8")
    source_lines = source_old_text.splitlines()
    source_line_number = best["line_number"]
    old_line = source_lines[source_line_number - 1]
    new_line = _append_rescheduled_tag(old_line)

    if "- [ ]" not in old_line:
        return {
            "operation": "schedule.reschedule_item",
            "status": "not_found",
            "changed": False,
            "target_text": target_text,
            "target_date_text": target_date_text,
            "target_date": target_date,
            "matched_item": _item_summary(best),
            "message": "Matched line is not an unfinished task.",
        }

    old_files = {str(source_path): source_old_text}
    files = {str(source_path): source_old_text}

    if old_line != new_line:
        new_source_lines = source_lines[:]
        new_source_lines[source_line_number - 1] = new_line
        files[str(source_path)] = "\n".join(new_source_lines) + "\n"

    target_old_text = target_note_path.read_text(encoding="utf-8")
    target_lines = target_old_text.splitlines()
    section = find_section_bounds(target_lines, "日程")

    if section is None:
        return {
            "operation": "schedule.reschedule_item",
            "status": "not_found",
            "changed": False,
            "target_text": target_text,
            "target_date_text": target_date_text,
            "target_date": target_date,
            "matched_item": _item_summary(best),
            "note_path": str(target_note_path),
            "message": "Target daily note has no ## 日程 section.",
        }

    skipped_duplicates: list[str] = []
    new_lines: list[str] = []

    if _target_has_similar_item(config, target_date=target_date, content=best_content):
        skipped_duplicates.append(best_content)
    else:
        _, content_start, content_end = section
        insert_line = f"- [ ] {best_content}"
        insert_block = [insert_line]

        if content_end > content_start and target_lines[content_end - 1].strip():
            insert_block = [""] + insert_block

        if content_end < len(target_lines) and target_lines[content_end].strip():
            insert_block = insert_block + [""]

        new_target_lines = (
            target_lines[:content_end]
            + insert_block
            + target_lines[content_end:]
        )

        old_files.setdefault(str(target_note_path), target_old_text)
        files[str(target_note_path)] = "\n".join(new_target_lines) + "\n"
        new_lines.append(insert_line)

    old_files.setdefault(str(target_note_path), target_old_text)
    files.setdefault(str(target_note_path), target_old_text)

    changed = any(files[path] != old_files[path] for path in files)

    return {
        "operation": "schedule.reschedule_item",
        "status": "prepared",
        "changed": changed,
        "target_text": target_text,
        "target_date_text": target_date_text,
        "target_date": target_date,
        "days": days,
        "source_note_path": str(source_path),
        "target_note_path": str(target_note_path),
        "note_path": str(target_note_path),
        "line_number": source_line_number,
        "matched_item": _item_summary(best),
        "old_line": old_line,
        "new_line": new_line,
        "new_lines": new_lines,
        "skipped_duplicates": skipped_duplicates,
        "diff": _build_diff(old_files, files),
        "old_files": old_files,
        "files": files,
        "candidates": [_item_summary(item) for item in candidates[:5]],
    }


def apply_reschedule_item(
    config: AppConfig,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    if proposal.get("operation") != "schedule.reschedule_item":
        raise ValueError(f"Unsupported operation: {proposal.get('operation')}")

    if proposal.get("status") != "prepared":
        return {
            "status": "blocked",
            "message": f"Proposal status is not prepared: {proposal.get('status')}",
        }

    if not proposal.get("changed"):
        return {
            "status": "no_changes",
            "message": "Nothing to change.",
        }

    old_files = proposal.get("old_files") or {}
    files = proposal.get("files") or {}

    if not old_files or not files:
        return {
            "status": "blocked",
            "message": "Proposal does not include file contents.",
        }

    for path_text, expected_old_text in old_files.items():
        path = Path(path_text)

        if not path.exists():
            return {
                "status": "blocked",
                "message": "File no longer exists.",
                "note_path": str(path),
            }

        current_text = path.read_text(encoding="utf-8")

        if current_text != expected_old_text:
            return {
                "status": "blocked",
                "message": "File changed since proposal was prepared.",
                "note_path": str(path),
            }

    pre_backup = None
    post_commit = None

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        pre_backup = manager.commit_all("Backup before agent reschedule item")

    for path_text, new_text in files.items():
        path = Path(path_text)
        old_text = old_files.get(path_text)

        if old_text == new_text:
            continue

        path.write_text(new_text, encoding="utf-8")

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        post_commit = manager.commit_all("Agent reschedule schedule item")

    return {
        "status": "applied",
        "target_text": proposal.get("target_text"),
        "target_date": proposal.get("target_date"),
        "source_note_path": proposal.get("source_note_path"),
        "target_note_path": proposal.get("target_note_path"),
        "line_number": proposal.get("line_number"),
        "new_lines": proposal.get("new_lines", []),
        "skipped_duplicates": proposal.get("skipped_duplicates", []),
        "pre_backup": pre_backup,
        "post_commit": post_commit,
    }
