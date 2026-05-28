from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from personal_agent.core.config.loader import ObsidianConfig
from personal_agent.plugins.schedule.models import ScheduleItem
from personal_agent.plugins.schedule.parsing.thino_parser import parse_markdown_lines
from personal_agent.plugins.schedule.obsidian.matcher import is_same_or_rewrite
from personal_agent.plugins.schedule.recurring.store import RecurringStore


TODAY_ALIASES = {"", "today", "今天", "今日", "now", "当前"}


class ObsidianScheduleReader:
    def __init__(self, config: ObsidianConfig):
        self.config = config

    def resolve_date(self, date_text: str | None) -> str:
        if date_text is None or date_text.strip().lower() in TODAY_ALIASES:
            return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")

        date_text = date_text.strip()

        try:
            parsed = datetime.strptime(date_text, "%Y-%m-%d")
            return parsed.strftime("%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(
                f"Unsupported date format: {date_text}. Expected YYYY-MM-DD or today."
            ) from exc

    def get_daily_note_path(self, date_text: str) -> Path:
        if not self.config.vault_path:
            raise RuntimeError("obsidian.vault_path is empty in configs/agent.yaml")

        vault_path = Path(self.config.vault_path).expanduser()
        daily_dir = self.config.daily_note_dir.strip("/")

        parsed_date = datetime.strptime(date_text, "%Y-%m-%d")
        filename = parsed_date.strftime(self.config.date_format) + ".md"

        if daily_dir:
            return vault_path / daily_dir / filename

        return vault_path / filename

    def _read_note_items(self, note_date: str) -> dict:
        note_path = self.get_daily_note_path(note_date)

        if not note_path.exists():
            return {
                "date": note_date,
                "note_path": str(note_path),
                "exists": False,
                "items": [],
                "message": "Daily note file does not exist.",
            }

        lines = note_path.read_text(encoding="utf-8").splitlines()

        items: list[ScheduleItem] = parse_markdown_lines(
            lines,
            note_date=note_date,
            source_file=str(note_path),
        )

        return {
            "date": note_date,
            "note_path": str(note_path),
            "exists": True,
            "items": [item.model_dump() for item in items],
            "count": len(items),
        }

    def read_daily_items(
        self,
        date_text: str | None = None,
        include_recurring: bool = False,
    ) -> dict:
        resolved_date = self.resolve_date(date_text)

        if include_recurring:
            result = self.read_range_items_with_recurring(
                start_date=resolved_date,
                end_date=resolved_date,
                lookback_days=30,
            )
        else:
            result = self.read_range_items(
                start_date=resolved_date,
                end_date=resolved_date,
                lookback_days=30,
            )

        result["date"] = resolved_date
        return result

    def read_range_items(
        self,
        start_date: str,
        end_date: str,
        lookback_days: int = 30,
    ) -> dict:
        start = datetime.strptime(self.resolve_date(start_date), "%Y-%m-%d").date()
        end = datetime.strptime(self.resolve_date(end_date), "%Y-%m-%d").date()

        if end < start:
            raise ValueError("end_date must be greater than or equal to start_date")

        scan_start = start - timedelta(days=lookback_days)
        scan_end = end

        all_items: list[dict] = []
        scanned_notes: list[dict] = []

        current = scan_start
        while current <= scan_end:
            note_date = current.isoformat()
            note_result = self._read_note_items(note_date)

            scanned_notes.append(
                {
                    "date": note_date,
                    "note_path": note_result["note_path"],
                    "exists": note_result["exists"],
                    "count": note_result.get("count", 0),
                }
            )

            if note_result["exists"]:
                all_items.extend(note_result["items"])

            current += timedelta(days=1)

        range_items = []
        filtered_out = []

        for item in all_items:
            effective_date = item.get("effective_date") or item.get("date")

            if start.isoformat() <= effective_date <= end.isoformat():
                range_items.append(item)
            else:
                filtered_out.append(item)

        range_items.sort(
            key=lambda item: (
                item.get("effective_date") or item.get("date") or "",
                item.get("time") or "99:99",
                item.get("created_time") or "99:99",
                item.get("line_number") or 0,
            )
        )

        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "scan_start": scan_start.isoformat(),
            "scan_end": scan_end.isoformat(),
            "lookback_days": lookback_days,
            "items": range_items,
            "count": len(range_items),
            "raw_count": len(all_items),
            "filtered_out_count": len(filtered_out),
            "scanned_notes": scanned_notes,
        }

    def read_recurring_items(
        self,
        start_date: str,
        end_date: str,
    ) -> dict:
        """
        Read recurring schedule instances as schedule-like items.
        """
        store = RecurringStore(self.config)
        instances = store.instances_between(start_date, end_date)

        items: list[dict] = []

        for instance in instances:
            data = instance.model_dump()

            items.append(
                {
                    "date": data["date"],
                    "content": data["title"],
                    "raw_line": "",
                    "source_file": str(store.path),
                    "line_number": 0,
                    "time": data.get("time"),
                    "created_time": None,
                    "effective_date": data["date"],
                    "date_source": "recurring",
                    "explicit_date_text": None,
                    "done": None,
                    "item_type": "recurring",
                    "suggested_type": "event",
                    "actionable": True,
                    "tags": [],
                    "organized": True,
                    "section": "循环日程",
                    "source": "recurring",
                    "rule_id": data.get("rule_id"),
                    "duration_minutes": data.get("duration_minutes"),
                    "reminder_minutes": data.get("reminder_minutes"),
                }
            )

        items.sort(
            key=lambda item: (
                item.get("effective_date") or "",
                item.get("time") or "99:99",
                item.get("content") or "",
            )
        )

        return {
            "mode": "recurring_instances",
            "start_date": start_date,
            "end_date": end_date,
            "items": items,
            "count": len(items),
            "store_path": str(store.path),
        }

    def read_range_items_with_recurring(
        self,
        start_date: str,
        end_date: str,
        lookback_days: int = 30,
    ) -> dict:
        """
        Read normal Obsidian schedule items plus recurring instances.
        """
        result = self.read_range_items(
            start_date=start_date,
            end_date=end_date,
            lookback_days=lookback_days,
        )

        recurring_result = self.read_recurring_items(
            start_date=result["start_date"],
            end_date=result["end_date"],
        )

        merged_items = result["items"] + recurring_result["items"]

        merged_items.sort(
            key=lambda item: (
                item.get("effective_date") or item.get("date") or "",
                item.get("time") or "99:99",
                item.get("created_time") or "99:99",
                item.get("line_number") or 0,
            )
        )

        result["items"] = merged_items
        result["count"] = len(merged_items)
        result["recurring_items"] = recurring_result["items"]
        result["recurring_count"] = recurring_result["count"]
        result["recurring_store_path"] = recurring_result["store_path"]

        return result

    def read_recent_items(
        self,
        days: int = 7,
        include_today: bool = True,
    ) -> dict:
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()

        end = today if include_today else today - timedelta(days=1)
        start = end - timedelta(days=days - 1)

        all_items: list[dict] = []
        scanned_notes: list[dict] = []

        current = start
        while current <= end:
            note_date = current.isoformat()
            note_result = self._read_note_items(note_date)

            scanned_notes.append(
                {
                    "date": note_date,
                    "note_path": note_result["note_path"],
                    "exists": note_result["exists"],
                    "count": note_result.get("count", 0),
                }
            )

            if note_result["exists"]:
                all_items.extend(note_result["items"])

            current += timedelta(days=1)

        return {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "days": days,
            "items": all_items,
            "count": len(all_items),
            "scanned_notes": scanned_notes,
        }

    def read_inbox_items(
        self,
        days: int = 7,
        include_organized: bool = False,
    ) -> dict:
        """
        Inbox means:
        - source is ## Thino
        - not done
        - not marked with #agent/organized unless include_organized=True

        Inbox does NOT include overdue formal schedule tasks.
        Overdue formal schedule tasks are handled by read_today_overview().
        """
        recent = self.read_recent_items(days=days, include_today=True)
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

        inbox_items: list[dict] = []

        bucket_labels = {
            "overdue": "过期待安排",
            "today": "今天可安排",
            "future": "未来待安排",
            "unplanned": "未安排事项",
        }

        for item in recent["items"]:
            if item.get("section") != "Thino":
                continue

            if item.get("done") is True:
                continue

            is_organized = item.get("organized") is True

            if is_organized and not include_organized:
                continue

            effective_date = item.get("effective_date") or item.get("date")
            date_source = item.get("date_source")
            note_date = item.get("date")

            if date_source == "note_default":
                # 没有显式日期，属于未安排 capture。
                # 如果它就是今天写的，也可以作为今天可安排项。
                if note_date == today:
                    bucket = "today"
                else:
                    bucket = "unplanned"
            else:
                if effective_date < today:
                    bucket = "overdue"
                elif effective_date == today:
                    bucket = "today"
                else:
                    bucket = "future"

            enriched = dict(item)
            enriched["bucket"] = bucket
            enriched["bucket_label"] = bucket_labels.get(bucket, bucket)
            enriched["bucket_reason"] = (
                f"effective_date={effective_date}, "
                f"note_date={note_date}, "
                f"date_source={date_source}, "
                f"organized={is_organized}"
            )
            enriched["organized"] = is_organized
            enriched["organized_match"] = None

            if is_organized:
                enriched["review_status"] = "already_organized"
            elif item.get("actionable"):
                enriched["review_status"] = "actionable"
            else:
                enriched["review_status"] = "memo_candidate"

            inbox_items.append(enriched)

        inbox_items.sort(
            key=lambda item: (
                {
                    "overdue": 0,
                    "today": 1,
                    "unplanned": 2,
                    "future": 3,
                }.get(item.get("bucket"), 9),
                item.get("effective_date") or "",
                item.get("date") or "",
                item.get("created_time") or "99:99",
                item.get("line_number") or 0,
            )
        )

        groups = {
            "overdue": [],
            "today": [],
            "future": [],
            "unplanned": [],
        }

        for item in inbox_items:
            groups.setdefault(item["bucket"], []).append(item)

        return {
            "mode": "inbox",
            "days": days,
            "start_date": recent["start_date"],
            "end_date": recent["end_date"],
            "today": today,
            "include_organized": include_organized,
            "items": inbox_items,
            "groups": groups,
            "count": len(inbox_items),
            "raw_count": recent["count"],
            "scanned_notes": recent["scanned_notes"],
        }

    def read_today_overview(
        self,
        lookback_days: int = 7,
    ) -> dict:
        """
        Today's overview.

        Formal schedule:
        - today_schedule_items: today's ## 日程 items
        - overdue_schedule_items: previous ## 日程 unfinished tasks not already in today's ## 日程
        - recurring_items: recurring instances for today

        Inbox:
        - inbox_due_items: Thino inbox items whose effective_date <= today or today's no-explicit-date captures
        - inbox_future_items: Thino inbox items whose effective_date > today
        - inbox_unplanned_items: Thino inbox items without explicit date from previous days
        """
        today = self.resolve_date("today")

        today_result = self.read_daily_items(today, include_recurring=False)
        recent = self.read_recent_items(days=lookback_days, include_today=True)

        today_schedule_items: list[dict] = []

        for item in today_result.get("items", []):
            if item.get("section") != "日程":
                continue

            if item.get("effective_date") != today:
                continue

            enriched = dict(item)
            enriched["overview_bucket"] = "today_schedule"
            today_schedule_items.append(enriched)

        overdue_schedule_items: list[dict] = []

        for item in recent.get("items", []):
            effective_date = item.get("effective_date") or item.get("date")

            if item.get("section") != "日程":
                continue

            if item.get("item_type") != "task":
                continue

            if item.get("done") is True:
                continue

            if effective_date >= today:
                continue

            # 如果这个旧日程已经被接收到今天日程，就不再作为遗留项显示。
            already_in_today = any(
                is_same_or_rewrite(
                    item.get("content") or "",
                    today_item.get("content") or "",
                )
                for today_item in today_schedule_items
            )

            if already_in_today:
                continue

            enriched = dict(item)
            enriched["overview_bucket"] = "overdue_schedule"
            overdue_schedule_items.append(enriched)

        overdue_schedule_items.sort(
            key=lambda item: (
                item.get("effective_date") or "",
                item.get("line_number") or 0,
            )
        )

        # Inbox 只来自 Thino，且 organized capture 默认已被 read_inbox_items 过滤。
        inbox = self.read_inbox_items(
            days=lookback_days,
            include_organized=False,
        )
        inbox_groups = inbox.get("groups", {})

        inbox_due_items = (
            inbox_groups.get("overdue", [])
            + inbox_groups.get("today", [])
        )
        inbox_future_items = inbox_groups.get("future", [])
        inbox_unplanned_items = inbox_groups.get("unplanned", [])

        recurring_result = self.read_recurring_items(today, today)
        recurring_items = recurring_result.get("items", [])

        return {
            "mode": "today_overview",
            "date": today,
            "lookback_days": lookback_days,

            "today_schedule_items": today_schedule_items,
            "overdue_schedule_items": overdue_schedule_items,
            "recurring_items": recurring_items,

            "inbox_due_items": inbox_due_items,
            "inbox_future_items": inbox_future_items,
            "inbox_unplanned_items": inbox_unplanned_items,

            # items 给 LLM 一个“今天需要关注”的合并视图
            "items": (
                overdue_schedule_items
                + today_schedule_items
                + recurring_items
                + inbox_due_items
            ),

            "today_schedule_count": len(today_schedule_items),
            "overdue_schedule_count": len(overdue_schedule_items),
            "recurring_count": len(recurring_items),
            "inbox_due_count": len(inbox_due_items),
            "inbox_future_count": len(inbox_future_items),
            "inbox_unplanned_count": len(inbox_unplanned_items),
            "count": (
                len(today_schedule_items)
                + len(overdue_schedule_items)
                + len(recurring_items)
                + len(inbox_due_items)
            ),
        }