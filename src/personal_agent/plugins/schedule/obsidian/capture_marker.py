from pathlib import Path
from typing import Any


ORGANIZED_TAG = "#agent/organized"


def line_has_organized_tag(line: str) -> bool:
    return ORGANIZED_TAG in line


def mark_capture_lines_organized(
    *,
    new_text_by_path: dict[str, str],
    items: list[dict[str, Any]],
) -> dict[str, str]:
    """
    Add #agent/organized to source Thino lines.

    new_text_by_path:
      path -> current planned new text

    items:
      parsed source items with source_file and line_number

    Returns updated new_text_by_path.
    """
    result = dict(new_text_by_path)

    for item in items:
        source_file = item.get("source_file")
        line_number = item.get("line_number")

        if not source_file or not line_number:
            continue

        path = str(Path(source_file))

        if path in result:
            text = result[path]
        else:
            text = Path(path).read_text(encoding="utf-8")

        lines = text.splitlines()

        index = int(line_number) - 1
        if index < 0 or index >= len(lines):
            continue

        old_line = lines[index]

        if line_has_organized_tag(old_line):
            continue

        lines[index] = old_line.rstrip() + f" {ORGANIZED_TAG}"
        result[path] = "\n".join(lines) + "\n"

    return result