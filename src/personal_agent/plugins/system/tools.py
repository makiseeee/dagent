from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from personal_agent.core.tools.base import Tool, ToolSpec


class GetCurrentTimeInput(BaseModel):
    timezone: str = "Asia/Shanghai"


def get_current_time(args: GetCurrentTimeInput) -> dict:
    now = datetime.now(ZoneInfo(args.timezone))

    return {
        "timezone": args.timezone,
        "iso": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
    }


def get_tools() -> list[Tool]:
    return [
        Tool(
            spec=ToolSpec(
                name="system.get_current_time",
                description="Get the current date and time for a given timezone.",
                input_schema=GetCurrentTimeInput,
                side_effect="none",
                require_confirmation=False,
            ),
            func=get_current_time,
        )
    ]