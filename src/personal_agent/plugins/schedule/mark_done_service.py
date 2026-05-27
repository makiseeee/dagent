from pathlib import Path
from typing import Any
import difflib

from personal_agent.core.config.loader import AppConfig
from personal_agent.core.backup.git_backup import GitBackupManager
from personal_agent.plugins.schedule.obsidian import ObsidianScheduleReader
from personal_agent.plugins.schedule.matcher import text_similarity
CANDIDATE_THRESHOLD = 0.35
AUTO_APPLY_THRESHOLD = 0.48
AMBIGUOUS_MARGIN = 0.08

def _is_unchecked_task_line(line: str) -> bool:
    return "- [ ]" in line


def _mark_line_done(line: str) -> str:
    return line.replace("- [ ]", "- [x]", 1)


def _is_safe_mark_done_change(old_line: str, new_line: str) -> bool:
    """
    Only allow changing the checkbox marker:
    - [ ] -> - [x]

    Everything else must remain exactly the same.
    """
    if old_line == new_line:
        return False

    if "- [ ]" not in old_line:
        return False

    expected = old_line.replace("- [ ]", "- [x]", 1)
    return new_line == expected


def prepare_mark_done(
    config: AppConfig,
    *,
    target_text: str,
    days: int = 7,
) -> dict[str, Any]:
    """
    Prepare a safe mark-done proposal.

    This function does not write files.
    """
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

        if (
            score >= CANDIDATE_THRESHOLD
            or target_text in content
            or content in target_text
        ):
            enriched = dict(item)
            enriched["match_score"] = score
            candidates.append(enriched)

    candidates.sort(key=lambda item: item.get("match_score", 0), reverse=True)

    if not candidates:
        return {
            "operation": "schedule.mark_done",
            "changed": False,
            "status": "not_found",
            "target_text": target_text,
            "message": "No matching unfinished schedule task found.",
            "candidates": [],
        }

    best = candidates[0]

    best_score = best.get("match_score", 0)
    best_content = best.get("content") or ""

    # 如果第一名不够明显，拒绝自动写入。
    if best_score < AUTO_APPLY_THRESHOLD and target_text not in best_content:
        return {
            "operation": "schedule.mark_done",
            "changed": False,
            "status": "low_confidence",
            "target_text": target_text,
            "message": "Best match confidence is too low.",
            "best_score": best_score,
            "candidates": candidates[:5],
        }

    # 如果前两名太接近，拒绝自动写入，避免误标记。
    if len(candidates) >= 2:
        second = candidates[1]
        second_score = second.get("match_score", 0)

        if best_score - second_score < AMBIGUOUS_MARGIN:
            return {
                "operation": "schedule.mark_done",
                "changed": False,
                "status": "ambiguous_match",
                "target_text": target_text,
                "message": "Multiple candidates are too close. Refusing automatic mark-done.",
                "best_score": best_score,
                "second_score": second_score,
                "candidates": candidates[:5],
            }

    path = Path(best["source_file"])
    old_text = path.read_text(encoding="utf-8")
    lines = old_text.splitlines()

    line_number = best["line_number"]
    old_line = lines[line_number - 1]

    if not _is_unchecked_task_line(old_line):
        return {
            "operation": "schedule.mark_done",
            "changed": False,
            "status": "not_unchecked_line",
            "target_text": target_text,
            "matched_item": best,
            "old_line": old_line,
        }

    new_line = _mark_line_done(old_line)

    if not _is_safe_mark_done_change(old_line, new_line):
        return {
            "operation": "schedule.mark_done",
            "changed": False,
            "status": "unsafe_change",
            "target_text": target_text,
            "matched_item": best,
            "old_line": old_line,
            "new_line": new_line,
        }

    new_lines = lines[:]
    new_lines[line_number - 1] = new_line
    new_text = "\n".join(new_lines) + "\n"

    diff = "\n".join(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=f"{path} (before)",
            tofile=f"{path} (after)",
            lineterm="",
        )
    )

    return {
        "operation": "schedule.mark_done",
        "changed": True,
        "status": "prepared",
        "target_text": target_text,
        "note_path": str(path),
        "line_number": line_number,
        "matched_item": best,
        "old_line": old_line,
        "new_line": new_line,
        "diff": diff,
        "new_text": new_text,
        "safe_change": True,
        "candidates": candidates[:5],
    }


def apply_mark_done(
    config: AppConfig,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    if proposal.get("operation") != "schedule.mark_done":
        raise ValueError(f"Unsupported operation: {proposal.get('operation')}")

    if not proposal.get("changed"):
        return {
            "status": "no_changes",
            "message": proposal.get("message") or "Nothing to change.",
        }

    if not proposal.get("safe_change"):
        return {
            "status": "blocked",
            "message": "Unsafe mark_done proposal blocked.",
        }

    note_path = Path(proposal["note_path"])
    old_text = note_path.read_text(encoding="utf-8")
    old_lines = old_text.splitlines()

    line_number = proposal["line_number"]
    current_line = old_lines[line_number - 1]

    # 再次确认磁盘上的当前行仍然是 prepare 时那一行。
    if current_line != proposal["old_line"]:
        return {
            "status": "blocked",
            "message": "File changed since proposal was prepared.",
            "current_line": current_line,
            "expected_old_line": proposal["old_line"],
        }

    new_line = proposal["new_line"]

    if not _is_safe_mark_done_change(current_line, new_line):
        return {
            "status": "blocked",
            "message": "Unsafe checkbox change blocked.",
        }

    new_lines = old_lines[:]
    new_lines[line_number - 1] = new_line
    new_text = "\n".join(new_lines) + "\n"

    pre_backup = None
    post_commit = None

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        pre_backup = manager.commit_all("Backup before agent mark done")

    note_path.write_text(new_text, encoding="utf-8")

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        post_commit = manager.commit_all("Agent mark schedule item done")

    return {
        "status": "applied",
        "note_path": str(note_path),
        "line_number": line_number,
        "old_line": current_line,
        "new_line": new_line,
        "pre_backup": pre_backup,
        "post_commit": post_commit,
    }