from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from personal_agent.core.config.loader import ObsidianConfig


class ReminderStateStore:
    def __init__(self, config: ObsidianConfig):
        self.config = config
        self.path = self._get_state_path()

    def _get_state_path(self) -> Path:
        if not self.config.vault_path:
            raise RuntimeError("obsidian.vault_path is empty in configs/agent.yaml")

        vault_path = Path(self.config.vault_path).expanduser()
        return vault_path / ".wenbo-agent" / "reminder_state.yaml"

    def _now(self) -> str:
        return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")

    def _load_raw(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"seen": {}}

        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))

        if not isinstance(data, dict):
            return {"seen": {}}

        if "seen" not in data or data["seen"] is None:
            data["seen"] = {}

        if not isinstance(data["seen"], dict):
            data["seen"] = {}

        return data

    def _save_raw(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            yaml.safe_dump(
                data,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def has_seen(self, key: str) -> bool:
        data = self._load_raw()
        return key in data.get("seen", {})

    def mark_seen(self, key: str, item: dict[str, Any]) -> None:
        data = self._load_raw()
        seen = data.setdefault("seen", {})

        seen[key] = {
            "title": item.get("title"),
            "rule_id": item.get("rule_id"),
            "instance_time": item.get("instance_time"),
            "reminder_time": item.get("reminder_time"),
            "reminded_at": self._now(),
        }

        self._save_raw(data)

    def prune_before(self, before_date: str) -> int:
        """
        Remove seen records whose instance_time date is before before_date.
        """
        cutoff = datetime.fromisoformat(f"{before_date}T00:00:00+08:00")

        data = self._load_raw()
        seen = data.get("seen", {})

        kept = {}
        removed = 0

        for key, value in seen.items():
            instance_time = value.get("instance_time")

            if not instance_time:
                kept[key] = value
                continue

            try:
                parsed = datetime.fromisoformat(instance_time)
            except ValueError:
                kept[key] = value
                continue

            if parsed < cutoff:
                removed += 1
            else:
                kept[key] = value

        data["seen"] = kept
        self._save_raw(data)

        return removed

    def prune_older_than_days(self, days: int = 14) -> int:
        cutoff_date = (
            datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=days)
        ).isoformat()
        return self.prune_before(cutoff_date)