import difflib
import re
from pathlib import Path
from pydantic import BaseModel


HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s+(?P<title>.+?)\s*$")


class ScheduleAppendPlan(BaseModel):
    note_path: str
    heading: str
    new_lines: list[str]
    skipped_duplicates: list[str]
    diff: str
    old_text: str
    new_text: str
    changed: bool


def normalize_heading(title: str) -> str:
    return title.strip().lstrip("#").strip()


def get_heading_info(line: str) -> tuple[int, str] | None:
    match = HEADING_RE.match(line)
    if not match:
        return None

    return len(match.group("level")), normalize_heading(match.group("title"))


def find_section_bounds(
    lines: list[str],
    heading: str,
) -> tuple[int, int, int] | None:
    """
    Return (heading_index, content_start, content_end).
    content_end is exclusive.
    """
    target = normalize_heading(heading)

    for i, line in enumerate(lines):
        info = get_heading_info(line)
        if not info:
            continue

        level, title = info
        if title != target:
            continue

        content_start = i + 1
        content_end = len(lines)

        for j in range(i + 1, len(lines)):
            next_info = get_heading_info(lines[j])
            if next_info and next_info[0] <= level:
                content_end = j
                break

        return i, content_start, content_end

    return None


def ensure_section(
    lines: list[str],
    heading: str,
    *,
    before_heading: str = "Thino",
) -> list[str]:
    if find_section_bounds(lines, heading) is not None:
        return lines

    insert_at = len(lines)
    before_target = normalize_heading(before_heading)

    for i, line in enumerate(lines):
        info = get_heading_info(line)
        if info and info[1] == before_target:
            insert_at = i
            break

    block: list[str] = []

    if insert_at > 0 and lines[insert_at - 1].strip():
        block.append("")

    block.extend([f"## {heading}", ""])

    if insert_at < len(lines) and lines[insert_at].strip():
        block.append("")

    return lines[:insert_at] + block + lines[insert_at:]


def build_schedule_line(item: dict) -> str:
    content = (
        item.get("schedule_content")
        or item.get("content")
        or ""
    ).strip()
    suggested_type = item.get("suggested_type")
    time = item.get("time")

    if suggested_type == "event" and time:
        return f"- {time} {content}"

    return f"- [ ] {content}"


def build_append_schedule_plan(
    note_path: str | Path,
    items: list[dict],
    *,
    heading: str = "日程",
) -> ScheduleAppendPlan:
    path = Path(note_path)

    if path.exists():
        old_text = path.read_text(encoding="utf-8")
    else:
        old_text = f"# {path.stem}\n\n## {heading}\n"

    lines = old_text.splitlines()
    lines = ensure_section(lines, heading)

    section = find_section_bounds(lines, heading)
    if section is None:
        raise RuntimeError(f"Failed to create or find heading: {heading}")

    _, content_start, content_end = section
    existing_section_text = "\n".join(lines[content_start:content_end])

    new_lines: list[str] = []
    skipped_duplicates: list[str] = []

    for item in items:
        source_content = (item.get("content") or "").strip()
        schedule_content = (
            item.get("schedule_content")
            or item.get("content")
            or ""
        ).strip()

        if not schedule_content:
            continue

        duplicate_candidates = {
            source_content,
            schedule_content,
        }

        if any(text and text in existing_section_text for text in duplicate_candidates):
            skipped_duplicates.append(schedule_content)
            continue

        new_lines.append(build_schedule_line(item))

    if not new_lines:
        new_text = "\n".join(lines) + "\n"
        diff = ""
        return ScheduleAppendPlan(
            note_path=str(path),
            heading=heading,
            new_lines=[],
            skipped_duplicates=skipped_duplicates,
            diff=diff,
            old_text=old_text,
            new_text=new_text,
            changed=False,
        )

    insert_block = new_lines[:]

    if content_end > content_start and lines[content_end - 1].strip():
        insert_block = [""] + insert_block

    if content_end < len(lines) and lines[content_end].strip():
        insert_block = insert_block + [""]

    new_all_lines = lines[:content_end] + insert_block + lines[content_end:]
    new_text = "\n".join(new_all_lines) + "\n"

    diff = "\n".join(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=f"{path} (before)",
            tofile=f"{path} (after)",
            lineterm="",
        )
    )

    return ScheduleAppendPlan(
        note_path=str(path),
        heading=heading,
        new_lines=new_lines,
        skipped_duplicates=skipped_duplicates,
        diff=diff,
        old_text=old_text,
        new_text=new_text,
        changed=True,
    )