from personal_agent.plugins.schedule.organizer import normalize_relative_date_words


def test_remove_stale_tomorrow_when_target_date_matches_effective_date():
    result = normalize_relative_date_words(
        "准备组会（明晚）",
        item_effective_date="2026-05-27",
        target_date="2026-05-27",
    )

    assert result == "准备组会"


def test_remove_stale_tomorrow_prefix():
    result = normalize_relative_date_words(
        "明天晚上准备组会",
        item_effective_date="2026-05-27",
        target_date="2026-05-27",
    )

    assert result == "准备组会"


def test_keep_relative_date_when_target_date_does_not_match():
    result = normalize_relative_date_words(
        "明天晚上准备组会",
        item_effective_date="2026-05-28",
        target_date="2026-05-27",
    )

    assert result == "明天晚上准备组会"