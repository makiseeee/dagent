from pydantic import BaseModel

from personal_agent.core.config.loader import AppConfig
from personal_agent.core.tools.base import Tool, ToolSpec
from personal_agent.plugins.schedule.obsidian import ObsidianScheduleReader

from personal_agent.core.llm.client import LLMClient
from personal_agent.plugins.schedule.organize_service import prepare_organize_today
from personal_agent.plugins.schedule.mark_done_service import prepare_mark_done
from personal_agent.plugins.schedule.adopt_overdue_service import prepare_adopt_overdue_today

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
    def adopt_overdue_today(args: AdoptOverdueTodayInput) -> dict:
        llm = LLMClient(config.llm) if args.llm_rewrite else None
        return prepare_adopt_overdue_today(
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
        return reader.read_daily_items(args.date)
    
    def get_range_items(args: GetRangeItemsInput) -> dict:
        return reader.read_range_items(
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
                    "unfinished formal schedule tasks from previous days, and today's "
                    "loose Thino inbox items. Use this when the user asks what they "
                    "should do today, today's matters, today's tasks, or today's schedule."
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
                        "This tool prepares a diff proposal only. It must be confirmed before writing."
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
                    "Obsidian daily notes. If date is omitted, use today. "
                    "Items without explicit date default to their note date. "
                    "Items with explicit natural-language dates are assigned to effective_date."
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
                    "within a date range. This scans recent daily notes with a lookback window, "
                    "so future tasks recorded in earlier notes can still be found."
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