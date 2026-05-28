from pydantic import BaseModel

from personal_agent.core.config.loader import AppConfig
from personal_agent.core.llm.client import LLMClient
from personal_agent.core.tools.base import Tool, ToolSpec
from personal_agent.plugins.schedule.obsidian.reader import ObsidianScheduleReader
from personal_agent.plugins.schedule.services.organize_service import prepare_organize_today
from personal_agent.plugins.schedule.services.mark_done_service import prepare_mark_done
from personal_agent.plugins.schedule.services.adopt_overdue_service import prepare_adopt_overdue_today
from personal_agent.plugins.schedule.services.adopt_inbox_service import prepare_adopt_inbox_today
from personal_agent.plugins.schedule.services.recurring_service import (
    prepare_add_recurring_rule,
    prepare_cancel_recurring_rule,
)

class AddRecurringRuleInput(BaseModel):
    title: str
    weekdays: list[str]
    time: str | None = None
    reminder_minutes: int | None = 30
    duration_minutes: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    note: str | None = None


class CancelRecurringRuleInput(BaseModel):
    rule_id: str | None = None
    query: str | None = None

class GetDailyItemsInput(BaseModel):
    date: str | None = None


class MarkDoneInput(BaseModel):
    target_text: str
    days: int = 7


class OrganizeTodayInput(BaseModel):
    llm_rewrite: bool = True


class AdoptOverdueTodayInput(BaseModel):
    lookback_days: int = 7
    llm_rewrite: bool = False


class AdoptInboxTodayInput(BaseModel):
    lookback_days: int = 7
    llm_rewrite: bool = True


class GetRangeItemsInput(BaseModel):
    start_date: str
    end_date: str
    lookback_days: int = 30


class GetInboxItemsInput(BaseModel):
    days: int = 7
    include_organized: bool = False


class GetTodayOverviewInput(BaseModel):
    lookback_days: int = 7


def get_tools(config: AppConfig) -> list[Tool]:
    reader = ObsidianScheduleReader(config.obsidian)

    def add_recurring_rule(args: AddRecurringRuleInput) -> dict:
        return prepare_add_recurring_rule(
            config,
            title=args.title,
            weekdays=args.weekdays,
            time=args.time,
            reminder_minutes=args.reminder_minutes,
            duration_minutes=args.duration_minutes,
            start_date=args.start_date,
            end_date=args.end_date,
            note=args.note,
        )

    def cancel_recurring_rule(args: CancelRecurringRuleInput) -> dict:
        return prepare_cancel_recurring_rule(
            config,
            rule_id=args.rule_id,
            query=args.query,
        )
    def adopt_overdue_today(args: AdoptOverdueTodayInput) -> dict:
        llm = LLMClient(config.llm) if args.llm_rewrite else None
        return prepare_adopt_overdue_today(
            config,
            llm,
            lookback_days=args.lookback_days,
            llm_rewrite=args.llm_rewrite,
        )

    def adopt_inbox_today(args: AdoptInboxTodayInput) -> dict:
        llm = LLMClient(config.llm) if args.llm_rewrite else None
        return prepare_adopt_inbox_today(
            config,
            llm,
            lookback_days=args.lookback_days,
            llm_rewrite=args.llm_rewrite,
        )

    def get_today_overview(args: GetTodayOverviewInput) -> dict:
        return reader.read_today_overview(
            lookback_days=args.lookback_days,
        )

    def mark_done(args: MarkDoneInput) -> dict:
        return prepare_mark_done(
            config,
            target_text=args.target_text,
            days=args.days,
        )

    def organize_today(args: OrganizeTodayInput) -> dict:
        llm = LLMClient(config.llm)
        return prepare_organize_today(
            config,
            llm,
            llm_rewrite=args.llm_rewrite,
        )
    
    def get_daily_items(args: GetDailyItemsInput) -> dict:
        return reader.read_daily_items(args.date, include_recurring=True)


    def get_range_items(args: GetRangeItemsInput) -> dict:
        return reader.read_range_items_with_recurring(
            start_date=args.start_date,
            end_date=args.end_date,
            lookback_days=args.lookback_days,
        )

    def get_inbox_items(args: GetInboxItemsInput) -> dict:
        return reader.read_inbox_items(
            days=args.days,
            include_organized=args.include_organized,
        )

    return [
        Tool(
            spec=ToolSpec(
                name="schedule.recurring_add",
                description=(
                    "Prepare adding a weekly recurring schedule rule. "
                    "Use when the user says 每周..., 以后每周..., or asks to create a fixed recurring schedule."
                ),
                input_schema=AddRecurringRuleInput,
                side_effect="write",
                require_confirmation=True,
            ),
            func=add_recurring_rule,
        ),
        Tool(
            spec=ToolSpec(
                name="schedule.recurring_cancel",
                description=(
                    "Prepare cancelling an active recurring schedule rule by rule_id or title query. "
                    "Use when the user asks to cancel a recurring schedule."
                ),
                input_schema=CancelRecurringRuleInput,
                side_effect="write",
                require_confirmation=True,
            ),
            func=cancel_recurring_rule,
        ),
        Tool(
            spec=ToolSpec(
                name="schedule.adopt_inbox_today",
                description=(
                    "Adopt due inbox items into today's ## 日程 section. "
                    "Inbox items come from Thino captures that are not marked "
                    "#agent/organized. This prepares a diff proposal and requires confirmation."
                ),
                input_schema=AdoptInboxTodayInput,
                side_effect="write",
                require_confirmation=True,
            ),
            func=adopt_inbox_today,
        ),
        Tool(
            spec=ToolSpec(
                name="schedule.adopt_overdue_today",
                description=(
                    "Adopt overdue unfinished formal schedule tasks from previous days "
                    "into today's ## 日程 section. This prepares a diff proposal and requires confirmation."
                ),
                input_schema=AdoptOverdueTodayInput,
                side_effect="write",
                require_confirmation=True,
            ),
            func=adopt_overdue_today,
        ),
        Tool(
            spec=ToolSpec(
                name="schedule.get_today_overview",
                description=(
                    "Read today's overview. Includes today's schedule items, "
                    "unfinished formal schedule tasks from previous days, and due inbox items."
                ),
                input_schema=GetTodayOverviewInput,
                side_effect="read",
                require_confirmation=False,
            ),
            func=get_today_overview,
        ),
        Tool(
            spec=ToolSpec(
                name="schedule.mark_done",
                description=(
                    "Mark a schedule task as done by changing only its checkbox "
                    "from [ ] to [x]. Use this when the user says 完成xxx, "
                    "做完xxx, or mark xxx as done."
                ),
                input_schema=MarkDoneInput,
                side_effect="write",
                require_confirmation=False,
            ),
            func=mark_done,
        ),
        Tool(
            spec=ToolSpec(
                name="schedule.organize_today",
                description=(
                    "Organize today's loose Thino inbox items into today's ## 日程 section. "
                    "This only handles captures from today's daily note. "
                    "This tool prepares a diff proposal only."
                ),
                input_schema=OrganizeTodayInput,
                side_effect="write",
                require_confirmation=True,
            ),
            func=organize_today,
        ),
        Tool(
            spec=ToolSpec(
                name="schedule.get_daily_items",
                description=(
                    "Read schedule, task, event, and memo items for one date from the user's "
                    "Obsidian daily notes. If date is omitted, use today."
                ),
                input_schema=GetDailyItemsInput,
                side_effect="read",
                require_confirmation=False,
            ),
            func=get_daily_items,
        ),
        Tool(
            spec=ToolSpec(
                name="schedule.get_range_items",
                description=(
                    "Read schedule, task, event, and memo items whose effective_date falls "
                    "within a date range."
                ),
                input_schema=GetRangeItemsInput,
                side_effect="read",
                require_confirmation=False,
            ),
            func=get_range_items,
        ),
        Tool(
            spec=ToolSpec(
                name="schedule.get_inbox_items",
                description=(
                    "Read loose unfinished items from recent Thino sections. "
                    "Use this when the user asks to整理 Thino, 查看零散任务, inbox, review, "
                    "or find unorganized tasks from recent days."
                ),
                input_schema=GetInboxItemsInput,
                side_effect="read",
                require_confirmation=False,
            ),
            func=get_inbox_items,
        ),
    ]