from pathlib import Path

from personal_agent.core.config.loader import ObsidianConfig
from personal_agent.plugins.schedule.services.reminder_state import ReminderStateStore


def test_reminder_state_mark_and_has_seen(tmp_path: Path):
    config = ObsidianConfig(
        vault_path=str(tmp_path),
        daily_note_dir="2. Areas/日记",
        date_format="%Y-%m-%d",
    )

    store = ReminderStateStore(config)

    key = "rule1::2026-05-27T20:00:00+08:00"

    assert store.has_seen(key) is False

    store.mark_seen(
        key,
        {
            "title": "跑步",
            "rule_id": "rule1",
            "instance_time": "2026-05-27T20:00:00+08:00",
            "reminder_time": "2026-05-27T19:30:00+08:00",
        },
    )

    assert store.has_seen(key) is True

    text = store.path.read_text(encoding="utf-8")
    assert "跑步" in text
    assert "rule1" in text


def test_reminder_state_prune_before(tmp_path: Path):
    config = ObsidianConfig(
        vault_path=str(tmp_path),
        daily_note_dir="2. Areas/日记",
        date_format="%Y-%m-%d",
    )

    store = ReminderStateStore(config)

    old_key = "rule1::2026-05-01T20:00:00+08:00"
    new_key = "rule2::2026-05-27T20:00:00+08:00"

    store.mark_seen(
        old_key,
        {
            "title": "旧提醒",
            "rule_id": "rule1",
            "instance_time": "2026-05-01T20:00:00+08:00",
            "reminder_time": "2026-05-01T19:30:00+08:00",
        },
    )
    store.mark_seen(
        new_key,
        {
            "title": "新提醒",
            "rule_id": "rule2",
            "instance_time": "2026-05-27T20:00:00+08:00",
            "reminder_time": "2026-05-27T19:30:00+08:00",
        },
    )

    removed = store.prune_before("2026-05-10")

    assert removed == 1
    assert store.has_seen(old_key) is False
    assert store.has_seen(new_key) is True