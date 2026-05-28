from personal_agent.plugins.schedule.parsing.date_resolver import resolve_explicit_date


def test_resolve_tomorrow():
    date, text = resolve_explicit_date("明天晚上准备组会", "2026-05-26")

    assert date == "2026-05-27"
    assert text == "明天"


def test_resolve_day_with_space():
    date, text = resolve_explicit_date("27 号问一下陈老师 大创报销", "2026-05-26")

    assert date == "2026-05-27"
    assert text == "27 号"


def test_resolve_day_without_space():
    date, text = resolve_explicit_date("27号问一下陈老师 大创报销", "2026-05-26")

    assert date == "2026-05-27"
    assert text == "27号"


def test_resolve_next_monday():
    date, text = resolve_explicit_date(
        "下周一开始复习人工智能基础",
        "2026-05-26",
    )

    assert date == "2026-06-01"
    assert text == "下周一"