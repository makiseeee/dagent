from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from personal_agent.core.config.loader import (
    AgentConfig,
    AppConfig,
    BackupConfig,
    LLMConfig,
    ObsidianConfig,
)
from personal_agent.plugins.schedule.services.recurring_service import (
    apply_recurring_proposal,
    prepare_add_recurring_rule,
)
from personal_agent.plugins.schedule.services.reminder_service import (
    find_due_recurring_reminders,
)


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        llm=LLMConfig(
            provider="deepseek",
            base_url="https://api.deepseek.com",
            default_model="deepseek-chat",
            cheap_model=None,
        ),
        agent=AgentConfig(
            name="test-agent",
            require_confirmation_for_write=True,
        ),
        obsidian=ObsidianConfig(
            vault_path=str(tmp_path),
            daily_note_dir="2. Areas/日记",
            date_format="%Y-%m-%d",
        ),
        backup=BackupConfig(
            git_enabled=False,
            git_auto_push=False,
            default_commit_message="test",
        ),
    )


def test_due_recurring_reminder(tmp_path: Path):
    config = make_config(tmp_path)

    proposal = prepare_add_recurring_rule(
        config,
        title="跑步",
        weekdays=["WE"],
        time="20:00",
        reminder_minutes=30,
        duration_minutes=60,
        start_date="2026-05-27",
    )
    apply_recurring_proposal(config, proposal)

    now = datetime(2026, 5, 27, 19, 20, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = find_due_recurring_reminders(
        config,
        window_minutes=15,
        now=now,
    )

    assert result["count"] == 1

    item = result["items"][0]
    assert item["title"] == "跑步"
    assert item["time"] == "20:00"
    assert item["reminder_minutes"] == 30
    assert item["minutes_until_reminder"] == 10
    assert item["minutes_until_event"] == 40


def test_no_due_recurring_reminder_outside_window(tmp_path: Path):
    config = make_config(tmp_path)

    proposal = prepare_add_recurring_rule(
        config,
        title="跑步",
        weekdays=["WE"],
        time="20:00",
        reminder_minutes=30,
        duration_minutes=60,
        start_date="2026-05-27",
    )
    apply_recurring_proposal(config, proposal)

    now = datetime(2026, 5, 27, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = find_due_recurring_reminders(
        config,
        window_minutes=15,
        now=now,
    )

    assert result["count"] == 0


def test_reminder_across_midnight_window(tmp_path: Path):
    config = make_config(tmp_path)

    # Event is at 00:10 on 2026-05-28.
    # Reminder is 20 minutes before, so reminder time is 2026-05-27 23:50.
    # Use the weekday that Python says 2026-05-28 actually is.
    event_date = datetime(2026, 5, 28, tzinfo=ZoneInfo("Asia/Shanghai"))
    weekday_codes = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
    event_weekday = weekday_codes[event_date.weekday()]

    proposal = prepare_add_recurring_rule(
        config,
        title="晚间检查",
        weekdays=[event_weekday],
        time="00:10",
        reminder_minutes=20,
        duration_minutes=10,
        start_date="2026-05-28",
    )
    apply_recurring_proposal(config, proposal)

    now = datetime(2026, 5, 27, 23, 45, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = find_due_recurring_reminders(
        config,
        window_minutes=10,
        now=now,
    )

    assert result["count"] == 1
    assert result["items"][0]["title"] == "晚间检查"