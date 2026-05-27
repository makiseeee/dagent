import re

from personal_agent.plugins.schedule.models import ScheduleItem
from personal_agent.plugins.schedule.date_resolver import resolve_explicit_date
from personal_agent.plugins.schedule.classifier import suggest_target_type


HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s+(?P<title>.+?)\s*$")

TIME_ONLY_RE = re.compile(
    r"""
    ^(?P<indent>\s*)
    (?P<marker>[-*])\s+
    (?P<time>\d{1,2}:\d{2})
    \s*$
    """,
    re.VERBOSE,
)

LIST_LINE_RE = re.compile(
    r"""
    ^(?P<indent>\s*)
    (?P<marker>[-*])\s+
    (?:
        (?P<checkbox>\[[ xX]\])\s*
    )?
    (?:
        (?P<time>\d{1,2}:\d{2})
        (?:
            \s*[-~]\s*
            (?P<end_time>\d{1,2}:\d{2})
        )?
        \s+
    )?
    (?P<content>.+?)
    \s*$
    """,
    re.VERBOSE,
)

INLINE_CHECKBOX_RE = re.compile(
    r"""
    ^\s*
    (?:
        [-*]\s+
    )?
    (?P<checkbox>\[[ xX]\])
    \s*
    (?P<content>.+?)
    \s*$
    """,
    re.VERBOSE,
)

TAG_RE = re.compile(r"#([\w\-/\u4e00-\u9fff]+)")

PARSE_SECTIONS = {"日程", "Thino", "Schedule", "Tasks", "Todo"}


def normalize_heading(title: str) -> str:
    return title.strip().lstrip("#").strip()


def parse_markdown_lines(
    lines: list[str],
    *,
    note_date: str,
    source_file: str,
) -> list[ScheduleItem]:
    items: list[ScheduleItem] = []

    current_section: str | None = None
    current_thino_created_time: str | None = None

    for idx, line in enumerate(lines, start=1):
        heading_match = HEADING_RE.match(line)
        if heading_match:
            current_section = normalize_heading(heading_match.group("title"))
            current_thino_created_time = None
            continue

        if current_section not in PARSE_SECTIONS:
            continue

        # Thino 分组时间：
        # - 18:49
        #   - 修改 fig 2
        # 这里 18:49 是 created_time，不是日程时间。
        time_only_match = TIME_ONLY_RE.match(line)
        if time_only_match and current_section == "Thino":
            current_thino_created_time = time_only_match.group("time")
            continue

        match = LIST_LINE_RE.match(line)
        if not match:
            continue

        indent = match.group("indent") or ""
        checkbox = match.group("checkbox")
        explicit_time = match.group("time")
        content = match.group("content").strip()

        # 兼容 Thino 这种格式：
        # - 21:15 - [ ] 下周一开始复习...
        inline_checkbox_match = INLINE_CHECKBOX_RE.match(content)
        if checkbox is None and inline_checkbox_match:
            checkbox = inline_checkbox_match.group("checkbox")
            content = inline_checkbox_match.group("content").strip()

        if not content:
            continue

        # 先统一初始化，避免 UnboundLocalError
        done: bool | None = None
        item_type = "memo"
        schedule_time: str | None = None
        created_time: str | None = None

        if current_section == "Thino":
            # Thino 顶层：
            # - 18:57 27 号问一下陈老师大创报销
            # 这里 18:57 是创建时间，不是日程时间。
            is_top_level = len(indent) == 0

            if is_top_level and checkbox is None and explicit_time is not None:
                created_time = explicit_time
                current_thino_created_time = explicit_time
                schedule_time = None
                item_type = "memo"

            elif is_top_level and checkbox is not None and explicit_time is not None:
                done = checkbox.lower() == "[x]"
                created_time = explicit_time
                current_thino_created_time = explicit_time
                schedule_time = None
                item_type = "task"

            else:
                # Thino 子项继承最近的创建时间
                created_time = current_thino_created_time

                if checkbox is not None:
                    done = checkbox.lower() == "[x]"
                    item_type = "task"
                else:
                    item_type = "memo"

                if explicit_time is not None and current_section == "Thino":
                    created_time = explicit_time

                schedule_time = None

        else:
            # ## 日程 下面的时间才是真正日程时间
            schedule_time = explicit_time

            if checkbox is not None:
                done = checkbox.lower() == "[x]"
                item_type = "task"
            elif schedule_time is not None:
                item_type = "event"
            else:
                item_type = "memo"

        explicit_date, explicit_date_text = resolve_explicit_date(content, note_date)

        if explicit_date is not None:
            effective_date = explicit_date
            date_source = "explicit"
        else:
            effective_date = note_date
            date_source = "note_default"

        suggested_type, actionable = suggest_target_type(
            content=content,
            item_type=item_type,
            time=schedule_time,
            explicit_date_text=explicit_date_text,
        )

        tags = TAG_RE.findall(content)
        organized = "agent/organized" in tags

        item = ScheduleItem(
            date=note_date,
            time=schedule_time,
            created_time=created_time,
            effective_date=effective_date,
            date_source=date_source,
            explicit_date_text=explicit_date_text,
            done=done,
            content=content,
            raw_line=line.rstrip("\n"),
            source_file=source_file,
            line_number=idx,
            item_type=item_type,
            suggested_type=suggested_type,
            actionable=actionable,
            tags=tags,
            organized=organized,
            section=current_section,
        )

        items.append(item)

    return items