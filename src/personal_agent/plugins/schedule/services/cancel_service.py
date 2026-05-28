from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from personal_agent.core.backup.git_backup import GitBackupManager
from personal_agent.core.config.loader import AppConfig
from personal_agent.plugins.schedule.obsidian.matcher import text_similarity
from personal_agent.plugins.schedule.obsidian.reader import ObsidianScheduleReader


AUTO_APPLY_THRESHOLD = 0.48
AMBIGUOUS_MARGIN = 0.08
CANCELLED_TAG = "#agent/cancelled"


def _append_cancelled_tag(line: str) -> str:
    if CANCELLED_TAG in line:
        return line
    return f"{line.rstrip()} {CANCELLED_TAG}"


def _item_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": item.get("content"),
        "effective_date": item.get("effective_date"),
        "source_file": item.get("source_file"),
        "line_number": item.get("line_number"),
        "match_score": item.get("match_score"),
    }


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

        raw_line = item.get("raw_line") or ""
        if CANCELLED_TAG in raw_line:
            continue

        content = item.get("content") or ""
        score = text_similarity(target_text, content)

        enriched = dict(item)
        enriched["match_score"] = score
        candidates.append(enriched)

    candidates.sort(key=lambda item: item.get("match_score", 0), reverse=True)
    return candidates


def prepare_cancel_item(
    config: AppConfig,
    *,
    target_text: str,
    days: int = 7,
) -> dict[str, Any]:
    """
    Prepare a conservative cancel proposal.

    This function does not write files.
    """
    candidates = _find_candidates(config, target_text=target_text, days=days)

    if not candidates:
        return {
            "operation": "schedule.cancel_item",
            "status": "not_found",
            "changed": False,
            "target_text": target_text,
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
            "operation": "schedule.cancel_item",
            "status": "low_confidence",
            "changed": False,
            "target_text": target_text,
            "message": "Best match confidence is too low.",
            "best_score": best_score,
            "candidates": [_item_summary(item) for item in candidates[:5]],
        }

    if len(candidates) >= 2:
        second = candidates[1]
        second_score = second.get("match_score", 0)

        if best_score - second_score < AMBIGUOUS_MARGIN:
            return {
                "operation": "schedule.cancel_item",
                "status": "ambiguous_match",
                "changed": False,
                "target_text": target_text,
                "message": "Multiple candidates are too close. Refusing automatic cancel.",
                "best_score": best_score,
                "second_score": second_score,
                "candidates": [_item_summary(item) for item in candidates[:5]],
            }

    source_path = Path(best["source_file"])
    old_text = source_path.read_text(encoding="utf-8")
    lines = old_text.splitlines()
    line_number = best["line_number"]
    old_line = lines[line_number - 1]

    if "- [ ]" not in old_line:
        return {
            "operation": "schedule.cancel_item",
            "status": "not_found",
            "changed": False,
            "target_text": target_text,
            "matched_item": _item_summary(best),
            "message": "Matched line is not an unfinished task.",
        }

    new_line = _append_cancelled_tag(old_line)

    if old_line == new_line:
        return {
            "operation": "schedule.cancel_item",
            "status": "not_found",
            "changed": False,
            "target_text": target_text,
            "matched_item": _item_summary(best),
            "message": "Matched task is already cancelled.",
        }

    new_lines = lines[:]
    new_lines[line_number - 1] = new_line
    new_text = "\n".join(new_lines) + "\n"

    return {
        "operation": "schedule.cancel_item",
        "status": "prepared",
        "changed": True,
        "target_text": target_text,
        "note_path": str(source_path),
        "line_number": line_number,
        "matched_item": _item_summary(best),
        "old_line": old_line,
        "new_line": new_line,
        "diff": _build_diff(source_path, old_text, new_text),
        "old_files": {str(source_path): old_text},
        "files": {str(source_path): new_text},
        "candidates": [_item_summary(item) for item in candidates[:5]],
    }


def apply_cancel_item(
    config: AppConfig,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    if proposal.get("operation") != "schedule.cancel_item":
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
    note_path_text = proposal.get("note_path")

    if not old_files or not files:
        return {
            "status": "blocked",
            "message": "Proposal does not include file contents.",
        }

    if not isinstance(note_path_text, str):
        return {
            "status": "blocked",
            "message": "Proposal does not include note_path.",
        }

    if set(old_files) != {note_path_text} or set(files) != {note_path_text}:
        return {
            "status": "blocked",
            "message": "Cancel proposal may only modify the matched source note.",
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

    note_path = Path(note_path_text)
    current_text = note_path.read_text(encoding="utf-8")
    current_lines = current_text.splitlines()
    line_number = proposal.get("line_number")
    old_line = proposal.get("old_line")
    new_line = proposal.get("new_line")

    if not isinstance(line_number, int) or line_number < 1:
        return {
            "status": "blocked",
            "message": "Invalid line_number.",
        }

    if line_number > len(current_lines):
        return {
            "status": "blocked",
            "message": "Matched line no longer exists.",
        }

    if current_lines[line_number - 1] != old_line:
        return {
            "status": "blocked",
            "message": "Matched line changed since proposal was prepared.",
        }

    if (
        not isinstance(old_line, str)
        or not isinstance(new_line, str)
        or "- [ ]" not in old_line
        or new_line != _append_cancelled_tag(old_line)
    ):
        return {
            "status": "blocked",
            "message": "Unsafe cancel line change blocked.",
        }

    expected_lines = current_lines[:]
    expected_lines[line_number - 1] = new_line
    expected_new_text = "\n".join(expected_lines) + "\n"

    if files[note_path_text] != expected_new_text:
        return {
            "status": "blocked",
            "message": "Cancel proposal contains changes outside the matched line.",
        }

    pre_backup = None
    post_commit = None

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        pre_backup = manager.commit_all("Backup before agent cancel item")

    note_path.write_text(expected_new_text, encoding="utf-8")

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        post_commit = manager.commit_all("Agent cancel schedule item")

    return {
        "status": "applied",
        "target_text": proposal.get("target_text"),
        "note_path": proposal.get("note_path"),
        "line_number": proposal.get("line_number"),
        "old_line": proposal.get("old_line"),
        "new_line": proposal.get("new_line"),
        "pre_backup": pre_backup,
        "post_commit": post_commit,
    }
