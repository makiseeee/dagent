import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from personal_agent.core.config.loader import load_config
from personal_agent.core.llm.client import LLMClient
from personal_agent.core.runtime.runtime import AgentRuntime
from personal_agent.core.tools.registry import ToolRegistry
from personal_agent.plugins.system.tools import get_tools as get_system_tools
from personal_agent.plugins.schedule.tools import get_tools as get_schedule_tools


app = typer.Typer(
    help="Debug and trace agent execution.",
    no_args_is_help=True,
)

console = Console()


def build_runtime() -> AgentRuntime:
    config = load_config()
    llm = LLMClient(config.llm)

    tools = ToolRegistry()

    for tool in get_system_tools():
        tools.register(tool)

    for tool in get_schedule_tools(config):
        tools.register(tool)

    return AgentRuntime(llm=llm, tools=tools)


def summarize_observation(observation: dict) -> dict:
    result = observation.get("result")

    if isinstance(result, dict):
        summary = {
            "status": observation.get("status"),
            "tool_name": observation.get("tool_name"),
            "tool_args": observation.get("tool_args"),
        }

        for key in [
            "date",
            "start_date",
            "end_date",
            "count",
            "raw_count",
            "filtered_out_count",
            "scan_start",
            "scan_end",
            "lookback_days",
        ]:
            if key in result:
                summary[key] = result[key]
        if result.get("mode") == "today_overview":
            for field in [
                "today_schedule_items",
                "overdue_items",
                "today_inbox",
                "future_inbox",
                "unplanned_inbox",
                "overdue_inbox",
            ]:
                values = result.get(field)
                if isinstance(values, list):
                    summary[f"{field}_count"] = len(values)
                    summary[f"{field}_preview"] = [
                        {
                            "content": item.get("content"),
                            "effective_date": item.get("effective_date"),
                            "done": item.get("done"),
                            "item_type": item.get("item_type"),
                            "section": item.get("section"),
                        }
                        for item in values[:5]
                    ]

            return summary
        items = result.get("items")
        if isinstance(items, list):
            summary["items_preview"] = [
                {
                    "content": item.get("content"),
                    "effective_date": item.get("effective_date"),
                    "time": item.get("time"),
                    "done": item.get("done"),
                    "item_type": item.get("item_type"),
                    "section": item.get("section"),
                }
                for item in items[:10]
            ]

        return summary

    return observation


@app.command()
def ask(
    message: str,
    show_observation: bool = typer.Option(
        False,
        "--show-observation",
        help="Show full tool observation JSON.",
    ),
    show_answer: bool = typer.Option(
        True,
        "--answer/--no-answer",
        help="Show final answer.",
    ),
):
    """
    Run agent ask with debug trace.
    """
    runtime = build_runtime()
    state = runtime.run(message)

    console.print(
        Panel(
            message,
            title="User Input",
            border_style="blue",
        )
    )

    if state.planner_output:
        planner_json = json.dumps(
            state.planner_output,
            ensure_ascii=False,
            indent=2,
        )

        console.print(
            Panel(
                Syntax(planner_json, "json", theme="monokai", line_numbers=False),
                title="Planner Output",
                border_style="magenta",
            )
        )

    if state.tool_calls:
        table = Table(title="Tool Calls")
        table.add_column("Tool")
        table.add_column("Arguments")
        table.add_column("Status")
        table.add_column("Summary")

        for call in state.tool_calls:
            result = call.result if isinstance(call.result, dict) else {}
            tool_result = result.get("result")

            summary_parts: list[str] = []

            if isinstance(tool_result, dict):
                for key in [
                    "date",
                    "start_date",
                    "end_date",
                    "count",
                    "raw_count",
                    "filtered_out_count",
                ]:
                    if key in tool_result:
                        summary_parts.append(f"{key}={tool_result[key]}")

            table.add_row(
                call.tool_name,
                json.dumps(call.arguments, ensure_ascii=False),
                str(result.get("status", "")),
                ", ".join(summary_parts),
            )

        console.print(table)

    if state.observations:
        for idx, observation in enumerate(state.observations, start=1):
            data = observation if show_observation else summarize_observation(observation)
            observation_json = json.dumps(data, ensure_ascii=False, indent=2)

            console.print(
                Panel(
                    Syntax(
                        observation_json,
                        "json",
                        theme="monokai",
                        line_numbers=False,
                    ),
                    title=f"Observation {idx}",
                    border_style="yellow",
                )
            )

    if show_answer:
        console.print(
            Panel(
                state.final_answer or "",
                title="Final Answer",
                border_style="green",
            )
        )