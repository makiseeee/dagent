from __future__ import annotations

from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field

from personal_agent.core.config.loader import ObsidianConfig


Weekday = Literal["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
RecurringStatus = Literal["active", "cancelled", "paused"]


WEEKDAY_TO_INDEX: dict[str, int] = {
    "MO": 0,
    "TU": 1,
    "WE": 2,
    "TH": 3,
    "FR": 4,
    "SA": 5,
    "SU": 6,
}

INDEX_TO_WEEKDAY = {value: key for key, value in WEEKDAY_TO_INDEX.items()}


class RecurringRule(BaseModel):
    id: str
    title: str
    frequency: Literal["weekly"] = "weekly"
    weekdays: list[Weekday]
    time: str | None = None
    duration_minutes: int | None = None
    reminder_minutes: int | None = None
    start_date: str
    end_date: str | None = None
    status: RecurringStatus = "active"
    created_at: str
    updated_at: str | None = None
    note: str | None = None


class RecurringInstance(BaseModel):
    rule_id: str
    title: str
    date: str
    time: str | None = None
    duration_minutes: int | None = None
    reminder_minutes: int | None = None
    source: Literal["recurring"] = "recurring"


class RecurringStore:
    def __init__(self, config: ObsidianConfig):
        self.config = config
        self.path = self._get_store_path()

    def _get_store_path(self) -> Path:
        if not self.config.vault_path:
            raise RuntimeError("obsidian.vault_path is empty in configs/agent.yaml")

        vault_path = Path(self.config.vault_path).expanduser()
        return vault_path / ".wenbo-agent" / "recurring.yaml"

    def _now(self) -> str:
        return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")

    def _today(self) -> str:
        return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

    def _load_raw(self) -> dict:
        if not self.path.exists():
            return {"recurring": []}

        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))

        if not isinstance(data, dict):
            return {"recurring": []}

        if "recurring" not in data or data["recurring"] is None:
            data["recurring"] = []

        return data

    def _save_raw(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            yaml.safe_dump(
                data,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def list_rules(
        self,
        *,
        include_cancelled: bool = False,
    ) -> list[RecurringRule]:
        raw = self._load_raw()

        rules = [
            RecurringRule.model_validate(item)
            for item in raw.get("recurring", [])
        ]

        if not include_cancelled:
            rules = [rule for rule in rules if rule.status == "active"]

        return rules

    def add_weekly_rule(
        self,
        *,
        title: str,
        weekdays: list[Weekday],
        time: str | None = None,
        duration_minutes: int | None = None,
        reminder_minutes: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        note: str | None = None,
    ) -> RecurringRule:
        raw = self._load_raw()
        now = self._now()

        rule = RecurringRule(
            id=f"recur_{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')}_{uuid4().hex[:8]}",
            title=title.strip(),
            frequency="weekly",
            weekdays=weekdays,
            time=time,
            duration_minutes=duration_minutes,
            reminder_minutes=reminder_minutes,
            start_date=start_date or self._today(),
            end_date=end_date,
            status="active",
            created_at=now,
            updated_at=None,
            note=note,
        )

        raw.setdefault("recurring", []).append(rule.model_dump())
        self._save_raw(raw)

        return rule

    def cancel_rule(self, rule_id: str) -> RecurringRule:
        raw = self._load_raw()
        items = raw.get("recurring", [])

        for index, item in enumerate(items):
            rule = RecurringRule.model_validate(item)

            if rule.id != rule_id:
                continue

            rule.status = "cancelled"
            rule.updated_at = self._now()
            items[index] = rule.model_dump()
            raw["recurring"] = items
            self._save_raw(raw)
            return rule

        raise KeyError(f"Recurring rule not found: {rule_id}")

    def get_rule(self, rule_id: str) -> RecurringRule:
        for rule in self.list_rules(include_cancelled=True):
            if rule.id == rule_id:
                return rule

        raise KeyError(f"Recurring rule not found: {rule_id}")

    def instances_between(
        self,
        start_date: str,
        end_date: str,
        *,
        include_cancelled: bool = False,
    ) -> list[RecurringInstance]:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        if end < start:
            raise ValueError("end_date must be greater than or equal to start_date")

        rules = self.list_rules(include_cancelled=include_cancelled)
        instances: list[RecurringInstance] = []

        current = start
        while current <= end:
            weekday = INDEX_TO_WEEKDAY[current.weekday()]

            for rule in rules:
                if rule.frequency != "weekly":
                    continue

                if weekday not in rule.weekdays:
                    continue

                if current < date.fromisoformat(rule.start_date):
                    continue

                if rule.end_date and current > date.fromisoformat(rule.end_date):
                    continue

                instances.append(
                    RecurringInstance(
                        rule_id=rule.id,
                        title=rule.title,
                        date=current.isoformat(),
                        time=rule.time,
                        duration_minutes=rule.duration_minutes,
                        reminder_minutes=rule.reminder_minutes,
                    )
                )

            current += timedelta(days=1)

        instances.sort(
            key=lambda item: (
                item.date,
                item.time or "99:99",
                item.title,
            )
        )

        return instances


def normalize_weekdays(values: list[str]) -> list[Weekday]:
    result: list[Weekday] = []

    aliases = {
        "MON": "MO",
        "MONDAY": "MO",
        "周一": "MO",
        "星期一": "MO",
        "TUE": "TU",
        "TUESDAY": "TU",
        "周二": "TU",
        "星期二": "TU",
        "WED": "WE",
        "WEDNESDAY": "WE",
        "周三": "WE",
        "星期三": "WE",
        "THU": "TH",
        "THURSDAY": "TH",
        "周四": "TH",
        "星期四": "TH",
        "FRI": "FR",
        "FRIDAY": "FR",
        "周五": "FR",
        "星期五": "FR",
        "SAT": "SA",
        "SATURDAY": "SA",
        "周六": "SA",
        "星期六": "SA",
        "SUN": "SU",
        "SUNDAY": "SU",
        "周日": "SU",
        "周天": "SU",
        "星期日": "SU",
        "星期天": "SU",
    }

    for value in values:
        key = value.strip().upper()
        normalized = aliases.get(key, aliases.get(value.strip(), key))

        if normalized not in WEEKDAY_TO_INDEX:
            raise ValueError(f"Unsupported weekday: {value}")

        result.append(normalized)  # type: ignore[arg-type]

    return result