from pathlib import Path
from typing import Any
import difflib

from personal_agent.core.config.loader import AppConfig
from personal_agent.core.backup.git_backup import GitBackupManager
from personal_agent.plugins.schedule.obsidian import ObsidianScheduleReader
from personal_agent.plugins.schedule.matcher import is_same_or_rewrite
from personal_agent.plugins.schedule.capture_marker import ORGANIZED_TAG


def _read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _write_text(path: str | Path, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


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


def _mark_item_line_organized(
    text: str,
    item: dict[str, Any],
) -> str:
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


def prepare_mark_organized_existing(
    config: AppConfig,
    *,
    days: int = 7,
    threshold: float = 0.72,
) -> dict[str, Any]:
    """
    Migrate old Thino captures that have already been organized into ## 日程.

    This function uses fuzzy matching only for historical migration.
    Normal workflow should use explicit #agent/organized when writing.
    """
    reader = ObsidianScheduleReader(config.obsidian)
    recent = reader.read_recent_items(days=days, include_today=True)

    items = recent.get("items", [])

    thino_items = [
        item
        for item in items
        if item.get("section") == "Thino"
        and item.get("done") is not True
        and item.get("organized") is not True
    ]

    schedule_items = [
        item
        for item in items
        if item.get("section") == "日程"
    ]

    matches: list[dict[str, Any]] = []

    for thino_item in thino_items:
        best_match: dict[str, Any] | None = None
        best_score = 0.0

        for schedule_item in schedule_items:
            score = 1.0 if is_same_or_rewrite(
                thino_item.get("content") or "",
                schedule_item.get("content") or "",
                threshold=threshold,
            ) else 0.0

            if score > best_score:
                best_score = score
                best_match = schedule_item

        if best_match is None:
            continue

        matches.append(
            {
                "source_item": thino_item,
                "matched_schedule_item": best_match,
                "score": best_score,
            }
        )

    old_text_by_path: dict[str, str] = {}
    new_text_by_path: dict[str, str] = {}

    for match in matches:
        item = match["source_item"]
        source_file = item.get("source_file")

        if not source_file:
            continue

        path = str(Path(source_file))

        if path not in old_text_by_path:
            old_text_by_path[path] = _read_text(path)

        current_text = new_text_by_path.get(path, old_text_by_path[path])
        new_text_by_path[path] = _mark_item_line_organized(current_text, item)

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
        "operation": "schedule.mark_organized_existing",
        "status": "prepared" if changed_files else "no_changes",
        "days": days,
        "threshold": threshold,
        "changed": bool(changed_files),
        "changed_files": list(changed_files.keys()),
        "files": changed_files,
        "diff": diff,
        "organized_tag": ORGANIZED_TAG,
        "matches": [
            {
                "source_content": match["source_item"].get("content"),
                "source_file": match["source_item"].get("source_file"),
                "source_line": match["source_item"].get("line_number"),
                "matched_content": match["matched_schedule_item"].get("content"),
                "matched_file": match["matched_schedule_item"].get("source_file"),
                "matched_line": match["matched_schedule_item"].get("line_number"),
                "score": match["score"],
            }
            for match in matches
        ],
        "message": (
            "Prepared organized marker migration."
            if changed_files
            else "No historical organized captures found."
        ),
    }


def apply_mark_organized_existing(
    config: AppConfig,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    if proposal.get("operation") != "schedule.mark_organized_existing":
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
        pre_backup = manager.commit_all("Backup before marking organized captures")

    for path, text in files.items():
        _write_text(path, text)

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        post_commit = manager.commit_all("Agent mark historical captures organized")

    return {
        "status": "applied",
        "changed_files": list(files.keys()),
        "pre_backup": pre_backup,
        "post_commit": post_commit,
    }