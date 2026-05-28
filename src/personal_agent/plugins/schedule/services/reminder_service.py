from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from personal_agent.core.config.loader import AppConfig
from personal_agent.plugins.schedule.recurring import RecurringStore


def find_due_recurring_reminders(
    config: AppConfig,
    *,
    window_minutes: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Find recurring schedule instances whose reminder time falls within:

        now <= reminder_time <= now + window_minutes

    This does not send notifications. It only returns due reminders.
    """
    current = now or datetime.now(ZoneInfo("Asia/Shanghai"))

    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo("Asia/Shanghai"))

    window_end = current + timedelta(minutes=window_minutes)

    store = RecurringStore(config.obsidian)

    # 跨天窗口时也要查到明天的 instance
    start_date = current.date().isoformat()
    end_date = (window_end.date() + timedelta(days=1)).isoformat()

    instances = store.instances_between(start_date, end_date)

    due_items: list[dict[str, Any]] = []

    for item in instances:
        if not item.time:
            continue

        reminder_minutes = item.reminder_minutes

        if reminder_minutes is None:
            continue

        instance_time = datetime.fromisoformat(
            f"{item.date}T{item.time}:00"
        ).replace(tzinfo=ZoneInfo("Asia/Shanghai"))

        reminder_time = instance_time - timedelta(minutes=reminder_minutes)

        if current <= reminder_time <= window_end:
            due_items.append(
                {
                    "rule_id": item.rule_id,
                    "title": item.title,
                    "date": item.date,
                    "time": item.time,
                    "instance_time": instance_time.isoformat(timespec="seconds"),
                    "reminder_time": reminder_time.isoformat(timespec="seconds"),
                    "reminder_minutes": reminder_minutes,
                    "duration_minutes": item.duration_minutes,
                    "minutes_until_reminder": int(
                        (reminder_time - current).total_seconds() // 60
                    ),
                    "minutes_until_event": int(
                        (instance_time - current).total_seconds() // 60
                    ),
                }
            )

    due_items.sort(
        key=lambda x: (
            x["reminder_time"],
            x["instance_time"],
            x["title"],
        )
    )

    return {
        "mode": "recurring_reminders_due",
        "now": current.isoformat(timespec="seconds"),
        "window_minutes": window_minutes,
        "window_end": window_end.isoformat(timespec="seconds"),
        "items": due_items,
        "count": len(due_items),
    }