from personal_agent.plugins.schedule.parsing.thino_parser import parse_markdown_lines


def test_thino_created_time_is_not_schedule_time():
    lines = [
        "## Thino",
        "- 18:57 27 号问一下陈老师 大创报销",
    ]

    items = parse_markdown_lines(
        lines,
        note_date="2026-05-26",
        source_file="2026-05-26.md",
    )

    assert len(items) == 1

    item = items[0]
    assert item.content == "27 号问一下陈老师 大创报销"
    assert item.created_time == "18:57"
    assert item.time is None
    assert item.effective_date == "2026-05-27"
    assert item.date_source == "explicit"


def test_thino_inline_checkbox_after_created_time():
    lines = [
        "## Thino",
        "- 21:29 - [ ] 下周一开始复习人工智能基础的时候记得做并且提交一下第五章作业",
    ]

    items = parse_markdown_lines(
        lines,
        note_date="2026-05-26",
        source_file="2026-05-26.md",
    )

    assert len(items) == 1

    item = items[0]
    assert item.content == "下周一开始复习人工智能基础的时候记得做并且提交一下第五章作业"
    assert item.created_time == "21:29"
    assert item.time is None
    assert item.item_type == "task"
    assert item.done is False
    assert item.effective_date == "2026-06-01"


def test_thino_time_group_plain_indented_capture():
    lines = [
        "## Thino",
        "- 20:22 ",
        "\t明天问一下陈老师后面的安排",
    ]

    items = parse_markdown_lines(
        lines,
        note_date="2026-05-28",
        source_file="2026-05-28.md",
    )

    assert len(items) == 1

    item = items[0]
    assert item.content == "明天问一下陈老师后面的安排"
    assert item.created_time == "20:22"
    assert item.time is None
    assert item.item_type == "memo"
    assert item.done is None
    assert item.effective_date == "2026-05-29"
    assert item.date_source == "explicit"


def test_thino_time_group_plain_indented_note_default_capture():
    lines = [
        "## Thino",
        "- 20:22 ",
        "\t旧备忘",
    ]

    items = parse_markdown_lines(
        lines,
        note_date="2026-05-28",
        source_file="2026-05-28.md",
    )

    assert len(items) == 1

    item = items[0]
    assert item.content == "旧备忘"
    assert item.created_time == "20:22"
    assert item.effective_date == "2026-05-28"
    assert item.date_source == "note_default"


def test_agent_organized_tag_is_parsed():
    lines = [
        "## Thino",
        "- 18:57 27 号问一下陈老师 大创报销 #agent/organized",
    ]

    items = parse_markdown_lines(
        lines,
        note_date="2026-05-26",
        source_file="2026-05-26.md",
    )

    assert len(items) == 1

    item = items[0]
    assert item.organized is True
    assert "agent/organized" in item.tags


def test_schedule_task_is_formal_task():
    lines = [
        "## 日程",
        "- [ ] 调研轻量级 VLA 使用的 Benchmark",
    ]

    items = parse_markdown_lines(
        lines,
        note_date="2026-05-27",
        source_file="2026-05-27.md",
    )

    assert len(items) == 1

    item = items[0]
    assert item.section == "日程"
    assert item.item_type == "task"
    assert item.done is False
    assert item.effective_date == "2026-05-27"
