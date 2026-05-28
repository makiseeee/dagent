from typing import Any, Callable

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from personal_agent.core.config.loader import AppConfig
from personal_agent.core.runtime.state import AgentState
from personal_agent.plugins.schedule.services.organize_service import apply_organize_today
from personal_agent.plugins.schedule.services.mark_done_service import apply_mark_done
from personal_agent.plugins.schedule.services.adopt_overdue_service import apply_adopt_overdue_today
from personal_agent.plugins.schedule.services.adopt_inbox_service import apply_adopt_inbox_today
from personal_agent.plugins.schedule.services.recurring_service import (
    apply_recurring_proposal,
)


console = Console()


def handle_mark_done_if_present(config: AppConfig, state: AgentState) -> bool:
    """
    schedule.mark_done is low-risk:
    if the prepared proposal passed safety checks, apply it immediately.
    """
    if not state.observations:
        return False

    observation = state.observations[-1]
    if not isinstance(observation, dict):
        return False

    result = observation.get("result")
    if not isinstance(result, dict):
        return False

    if result.get("operation") != "schedule.mark_done":
        return False

    should_apply = (
        result.get("status") == "prepared"
        and result.get("changed") is True
        and result.get("safe_change") is True
    )

    if should_apply:
        apply_result = apply_mark_done(config, result)

        console.print(
            Panel(
                (
                    f"Status: {apply_result.get('status')}\n\n"
                    f"{apply_result.get('old_line', '')}\n"
                    f"{apply_result.get('new_line', '')}"
                ),
                title="Mark Done",
                border_style="green",
            )
        )
        return True

    message_lines = [
        f"Status: {result.get('status')}",
        f"Changed: {result.get('changed')}",
        f"Safe change: {result.get('safe_change')}",
        f"Message: {result.get('message', '')}",
        f"Target: {result.get('target_text', '')}",
    ]

    candidates = result.get("candidates") or []
    if candidates:
        message_lines.append("")
        message_lines.append("Candidates:")
        for item in candidates:
            message_lines.append(
                f"- {item.get('content')} "
                f"(score={item.get('match_score', 0):.2f}, "
                f"date={item.get('effective_date')}, "
                f"line={item.get('line_number')})"
            )

    console.print(
        Panel(
            "\n".join(message_lines),
            title="Mark Done Not Applied",
            border_style="yellow",
        )
    )
    return True


def _print_rewritten_items_table(title: str, items: list[dict[str, Any]]) -> None:
    if not items:
        return

    table = Table(title=title)
    table.add_column("Original")
    table.add_column("Schedule Text")
    table.add_column("Reason")

    for item in items:
        table.add_row(
            item.get("original") or "",
            item.get("schedule_content") or "",
            item.get("rewrite_reason") or "",
        )

    console.print(table)


def _print_proposal_common(proposal: dict[str, Any], *, title: str) -> None:
    console.print(f"[bold]Target:[/bold] {proposal.get('note_path')}")
    console.print(f"[bold]New lines:[/bold] {len(proposal.get('new_lines', []))}")

    skipped = proposal.get("skipped_duplicates") or []
    if skipped:
        console.print("[yellow]Skipped duplicates:[/yellow]")
        for item in skipped:
            console.print(f"- {item}")

    if not proposal.get("changed"):
        console.print("[green]Nothing to change.[/green]")
        return

    console.print(
        Panel(
            Syntax(
                proposal.get("diff") or "",
                "diff",
                theme="monokai",
                line_numbers=False,
            ),
            title=title,
            border_style="yellow",
        )
    )


def _confirm_and_apply(
    config: AppConfig,
    proposal: dict[str, Any],
    *,
    diff_title: str,
    apply_func: Callable[[AppConfig, dict[str, Any]], dict[str, Any]],
) -> bool:
    _print_proposal_common(proposal, title=diff_title)

    if not proposal.get("changed"):
        return True

    confirmed = typer.confirm("Apply this change?")
    if not confirmed:
        console.print("[yellow]Cancelled.[/yellow]")
        return True

    result = apply_func(config, proposal)

    console.print(
        Panel(
            str(result),
            title="Apply Result",
            border_style="green",
        )
    )

    return True


def handle_pending_confirmation(config: AppConfig, state: AgentState) -> bool:
    pending = state.pending_confirmation
    if not pending:
        return False

    proposal = pending.get("result") or {}
    operation = proposal.get("operation")
    if operation in {"schedule.recurring_add", "schedule.recurring_cancel"}:
        rule = proposal.get("rule") or {}

        if rule:
            table = Table(title="Recurring Rule Change")
            table.add_column("Field")
            table.add_column("Value")

            for key in [
                "id",
                "title",
                "weekdays",
                "time",
                "reminder_minutes",
                "duration_minutes",
                "start_date",
                "end_date",
                "status",
            ]:
                value = rule.get(key)
                table.add_row(key, "" if value is None else str(value))

            console.print(table)

        return _confirm_and_apply(
            config,
            proposal,
            diff_title="Proposed Recurring Rule Diff",
            apply_func=apply_recurring_proposal,
        )
    if operation == "schedule.organize_today":
        _print_rewritten_items_table(
            "LLM Rewritten Schedule Items",
            proposal.get("rewritten_items") or [],
        )
        return _confirm_and_apply(
            config,
            proposal,
            diff_title="Proposed Organize Diff",
            apply_func=apply_organize_today,
        )
    if operation == "schedule.adopt_inbox_today":
        _print_rewritten_items_table(
            "Adopt Inbox Items",
            proposal.get("rewritten_items") or [],
        )
        return _confirm_and_apply(
            config,
            proposal,
            diff_title="Proposed Adopt-inbox Diff",
            apply_func=apply_adopt_inbox_today,
        )
    if operation == "schedule.adopt_overdue_today":
        _print_rewritten_items_table(
            "Adopt Overdue Items",
            proposal.get("rewritten_items") or [],
        )
        return _confirm_and_apply(
            config,
            proposal,
            diff_title="Proposed Adopt-overdue Diff",
            apply_func=apply_adopt_overdue_today,
        )

    console.print(
        Panel(
            str(pending),
            title="Pending Confirmation",
            border_style="yellow",
        )
    )
    return True