from rich.console import Console
from rich.table import Table
import typer

from personal_agent.core.config.loader import load_config
from personal_agent.plugins.schedule.obsidian import ObsidianScheduleReader
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pathlib import Path
from rich.panel import Panel
from rich.syntax import Syntax

from personal_agent.core.backup.git_backup import GitBackupManager
from personal_agent.plugins.schedule.writer import build_append_schedule_plan
from personal_agent.core.llm.client import LLMClient
from personal_agent.plugins.schedule.organizer import organize_schedule_items

from personal_agent.plugins.schedule.adopt_overdue_service import (
    prepare_adopt_overdue_today,
    apply_adopt_overdue_today,
)

from personal_agent.plugins.schedule.adopt_inbox_service import (
    prepare_adopt_inbox_today,
    apply_adopt_inbox_today,
)

from personal_agent.plugins.schedule.organized_migration_service import (
    prepare_mark_organized_existing,
    apply_mark_organized_existing,
)

app = typer.Typer(
    help="Schedule commands.",
    no_args_is_help=True,
)

console = Console()
def render_inbox_result(result: dict, *, raw: bool = False) -> None:
    console.print(
        f"[bold]Inbox Range:[/bold] {result.get('start_date')} → {result.get('end_date')}"
    )
    console.print(f"[bold]Days:[/bold] {result.get('days')}")
    console.print(f"[dim]Raw parsed items: {result.get('raw_count')}[/dim]")

    groups = result.get("groups", {})

    titles = {
        "overdue": "过期 / 遗留任务",
        "today": "今日零散任务",
        "future": "未来任务",
        "unplanned": "未安排任务",
    }

    for bucket in ["overdue", "today", "future", "unplanned"]:
        items = groups.get(bucket, [])

        if not items:
            continue

        table = Table(title=titles.get(bucket, bucket))
        table.add_column("Date")
        table.add_column("Time")
        table.add_column("Content")
        table.add_column("Raw Type")
        table.add_column("Suggest")
        table.add_column("Review")
        table.add_column("Source")
        table.add_column("Organized")

        if raw:
            table.add_column("Created")
            table.add_column("Date Source")
            table.add_column("Line")

        for item in items:
            table.add_row(
                item.get("effective_date") or "",
                item.get("time") or "",
                item.get("content") or "",
                item.get("item_type") or "",
                item.get("suggested_type") or "",
                item.get("review_status") or "",
                item.get("section") or "",
                "yes" if item.get("organized") else "",
                *(([
                    item.get("created_time") or "",
                    item.get("date_source") or "",
                    str(item.get("line_number") or ""),
                ]) if raw else []),
            )

        console.print(table)

    if result.get("count") == 0:
        console.print("[green]No inbox items found.[/green]")
    else:
        console.print(f"[bold]Total inbox items:[/bold] {result.get('count')}")

def get_current_week_range() -> tuple[str, str]:
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()

def render_schedule_result(result: dict, *, raw: bool = False) -> None:
    date = result.get("date")
    start_date = result.get("start_date")
    end_date = result.get("end_date")
    note_path = result.get("note_path")
    exists = result.get("exists", True)
    items = result.get("items", [])

    if start_date and end_date:
        console.print(f"[bold]Range:[/bold] {start_date} → {end_date}")
        console.print(
            f"[dim]Scanned notes: {result.get('scan_start')} → {result.get('scan_end')}[/dim]"
        )
    else:
        console.print(f"[bold]Date:[/bold] {date}")
        console.print(f"[bold]Note:[/bold] {note_path}")

    if not exists:
        console.print("[yellow]Daily note does not exist.[/yellow]")
        return

    table = Table(title="Schedule Items")

    table.add_column("Status")
    table.add_column("Raw Type")
    table.add_column("Suggest")
    table.add_column("Time")
    table.add_column("Content")
    table.add_column("Section")

    if raw:
        table.add_column("Created")
        table.add_column("Effective Date")
        table.add_column("Date Source")
        table.add_column("Line")

    for item in items:
        done = item.get("done")

        if done is True:
            status = "✅"
        elif done is False:
            status = "⬜"
        else:
            status = ""

        table.add_row(
            status,
            item.get("item_type") or "",
            item.get("suggested_type") or "",
            item.get("time") or "",
            item.get("content") or "",
            item.get("section") or "",
            *(([
                item.get("created_time") or "",
                item.get("effective_date") or "",
                item.get("date_source") or "",
                str(item.get("line_number") or ""),
            ]) if raw else []),
        )

    console.print(table)

    raw_count = result.get("raw_count")
    filtered_out_count = result.get("filtered_out_count")

    if raw_count is not None:
        console.print(
            f"[dim]Returned {len(items)} items. "
            f"Raw parsed: {raw_count}. "
            f"Filtered out: {filtered_out_count}.[/dim]"
        )


@app.command()
def today(raw: bool = typer.Option(False, "--raw", help="Show parser metadata.")):
    """
    Show today's schedule without using LLM.
    """
    config = load_config()
    reader = ObsidianScheduleReader(config.obsidian)
    result = reader.read_daily_items("today")
    render_schedule_result(result, raw=raw)


@app.command("date")
def date_cmd(
    date: str,
    raw: bool = typer.Option(False, "--raw", help="Show parser metadata."),
):
    """
    Show schedule items for a specific date.
    """
    config = load_config()
    reader = ObsidianScheduleReader(config.obsidian)
    result = reader.read_daily_items(date)
    render_schedule_result(result, raw=raw)


@app.command()
def raw(date: str = "today"):
    """
    Show raw parsed schedule items with metadata.
    """
    config = load_config()
    reader = ObsidianScheduleReader(config.obsidian)
    result = reader.read_daily_items(date)
    render_schedule_result(result, raw=True)


@app.command()
def week(raw: bool = typer.Option(False, "--raw", help="Show parser metadata.")):
    """
    Show this week's schedule without using LLM.
    """
    config = load_config()
    reader = ObsidianScheduleReader(config.obsidian)

    start_date, end_date = get_current_week_range()
    result = reader.read_range_items(start_date, end_date, lookback_days=30)

    render_schedule_result(result, raw=raw)


@app.command()
def inbox(
    days: int = typer.Option(7, "--days", "-d", help="Look back N days."),
    raw: bool = typer.Option(False, "--raw", help="Show parser metadata."),
    show_organized: bool = typer.Option(
        False,
        "--show-organized",
        help="Also show items already organized into ## 日程.",
    ),
):
    """
    Show loose unfinished items from recent Thino sections.
    """
    config = load_config()
    reader = ObsidianScheduleReader(config.obsidian)

    result = reader.read_inbox_items(
        days=days,
        include_organized=show_organized,
    )
    render_inbox_result(result, raw=raw)

@app.command()
def review(
    days: int = typer.Option(7, "--days", "-d", help="Look back N days."),
    raw: bool = typer.Option(False, "--raw", help="Show parser metadata."),
    show_organized: bool = typer.Option(
        False,
        "--show-organized",
        help="Also show items already organized into ## 日程.",
    ),
):
    """
    Review recent loose schedule/task items.
    """
    config = load_config()
    reader = ObsidianScheduleReader(config.obsidian)

    result = reader.read_inbox_items(
        days=days,
        include_organized=show_organized,
    )
    render_inbox_result(result, raw=raw)

@app.command("range")
def range_cmd(
    start_date: str,
    end_date: str,
    raw: bool = typer.Option(False, "--raw", help="Show parser metadata."),
):
    """
    Show schedule items for a date range.
    """
    config = load_config()
    reader = ObsidianScheduleReader(config.obsidian)

    result = reader.read_range_items(start_date, end_date, lookback_days=30)

    render_schedule_result(result, raw=raw)


@app.command("organize-today")
def organize_today(
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply changes to the daily note.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation when applying.",
    ),
    llm_rewrite: bool = typer.Option(
        True,
        "--llm-rewrite/--plain",
        help="Use LLM to rewrite schedule item text before writing.",
    ),
):
    """
    Organize today's Thino inbox items into today's ## 日程 section.

    Default is dry-run: show diff only.
    """
    config = load_config()
    reader = ObsidianScheduleReader(config.obsidian)

    today = reader.resolve_date("today")
    inbox = reader.read_inbox_items(days=1, include_organized=False)

    today_items = inbox.get("groups", {}).get("today", [])

    candidates = [
        item
        for item in today_items
        if item.get("suggested_type") in {"task", "event"} or item.get("actionable")
    ]

    if not candidates:
        console.print("[green]No today inbox items to organize.[/green]")
        return

    note_path = reader.get_daily_note_path(today)
    if llm_rewrite:
        llm = LLMClient(config.llm)
        candidates = organize_schedule_items(
            llm,
            candidates,
            target_date=today,
        )

        rewrite_table = Table(title="LLM Rewritten Schedule Items")
        rewrite_table.add_column("Original")
        rewrite_table.add_column("Schedule Text")
        rewrite_table.add_column("Reason")

        for item in candidates:
            rewrite_table.add_row(
                item.get("content") or "",
                item.get("schedule_content") or "",
                item.get("rewrite_reason") or "",
            )

        console.print(rewrite_table)
    plan = build_append_schedule_plan(
        note_path=note_path,
        items=candidates,
        heading="日程",
    )

    console.print(f"[bold]Target:[/bold] {plan.note_path}")
    console.print(f"[bold]New lines:[/bold] {len(plan.new_lines)}")

    if plan.skipped_duplicates:
        console.print("[yellow]Skipped duplicates:[/yellow]")
        for item in plan.skipped_duplicates:
            console.print(f"- {item}")

    if not plan.changed:
        console.print("[green]Nothing to change.[/green]")
        return

    console.print(
        Panel(
            Syntax(plan.diff, "diff", theme="monokai", line_numbers=False),
            title="Proposed Diff",
            border_style="yellow",
        )
    )

    if not apply:
        console.print(
            "[dim]Dry-run only. Use --apply to write these changes.[/dim]"
        )
        return

    if not yes:
        confirmed = typer.confirm("Apply this change?")
        if not confirmed:
            console.print("[yellow]Cancelled.[/yellow]")
            return

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        backup_result = manager.commit_all("Backup before organizing today's schedule")
        console.print(
            Panel(
                str(backup_result),
                title="Pre-write Git Backup",
                border_style="blue",
            )
        )

    Path(plan.note_path).write_text(plan.new_text, encoding="utf-8")

    console.print("[green]Wrote schedule items to daily note.[/green]")

    if config.backup.git_enabled:
        manager = GitBackupManager(config.obsidian.vault_path)
        commit_result = manager.commit_all("Agent organize today's schedule")
        console.print(
            Panel(
                str(commit_result),
                title="Post-write Git Commit",
                border_style="green",
            )
        )
@app.command("adopt-overdue-today")
def adopt_overdue_today(
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply changes to today's daily note.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation when applying.",
    ),
    lookback_days: int = typer.Option(
        7,
        "--lookback-days",
        help="Look back N days for unfinished schedule tasks.",
    ),
    llm_rewrite: bool = typer.Option(
        False,
        "--llm-rewrite/--plain",
        help="Use LLM to rewrite adopted task text.",
    ),
):
    """
    Adopt overdue unfinished ## 日程 tasks into today's ## 日程.

    Default is dry-run: show diff only.
    """
    config = load_config()
    llm = LLMClient(config.llm) if llm_rewrite else None

    proposal = prepare_adopt_overdue_today(
        config,
        llm,
        lookback_days=lookback_days,
        llm_rewrite=llm_rewrite,
    )

    console.print(f"[bold]Target date:[/bold] {proposal.get('target_date')}")
    console.print(f"[bold]Target note:[/bold] {proposal.get('note_path')}")
    console.print(f"[bold]New lines:[/bold] {len(proposal.get('new_lines', []))}")

    source_items = proposal.get("source_items") or []
    if source_items:
        table = Table(title="Overdue Items")
        table.add_column("Date")
        table.add_column("Content")
        table.add_column("Line")

        for item in source_items:
            table.add_row(
                item.get("effective_date") or "",
                item.get("content") or "",
                str(item.get("line_number") or ""),
            )

        console.print(table)

    if proposal.get("skipped_duplicates"):
        console.print("[yellow]Skipped duplicates:[/yellow]")
        for item in proposal["skipped_duplicates"]:
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
            title="Proposed Adopt-overdue Diff",
            border_style="yellow",
        )
    )

    if not apply:
        console.print("[dim]Dry-run only. Use --apply to write changes.[/dim]")
        return

    if not yes:
        confirmed = typer.confirm("Apply this adopt-overdue change?")
        if not confirmed:
            console.print("[yellow]Cancelled.[/yellow]")
            return

    result = apply_adopt_overdue_today(config, proposal)

    console.print(
        Panel(
            str(result),
            title="Adopt-overdue Result",
            border_style="green",
        )
    )
@app.command("adopt-inbox-today")
def adopt_inbox_today(
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply changes to today's daily note and source Thino captures.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation when applying.",
    ),
    lookback_days: int = typer.Option(
        7,
        "--lookback-days",
        help="Look back N days for due inbox items.",
    ),
    llm_rewrite: bool = typer.Option(
        True,
        "--llm-rewrite/--plain",
        help="Use LLM to rewrite adopted inbox item text.",
    ),
):
    """
    Adopt due inbox items into today's ## 日程.

    This reads recent Thino inbox items whose effective_date is today or overdue,
    writes them into today's ## 日程, and marks source Thino lines with
    #agent/organized.

    Default is dry-run: show diff only.
    """
    config = load_config()
    llm = LLMClient(config.llm) if llm_rewrite else None

    proposal = prepare_adopt_inbox_today(
        config,
        llm,
        lookback_days=lookback_days,
        llm_rewrite=llm_rewrite,
    )

    console.print(f"[bold]Target date:[/bold] {proposal.get('target_date')}")
    console.print(f"[bold]Target note:[/bold] {proposal.get('note_path')}")
    console.print(f"[bold]Changed files:[/bold] {len(proposal.get('changed_files', []))}")
    console.print(f"[bold]New lines:[/bold] {len(proposal.get('new_lines', []))}")

    source_items = proposal.get("source_items") or []
    if source_items:
        table = Table(title="Due Inbox Items")
        table.add_column("Date")
        table.add_column("Bucket")
        table.add_column("Content")
        table.add_column("Line")

        for item in source_items:
            table.add_row(
                item.get("effective_date") or "",
                item.get("bucket") or "",
                item.get("content") or "",
                str(item.get("line_number") or ""),
            )

        console.print(table)

    rewritten_items = proposal.get("rewritten_items") or []
    if rewritten_items:
        table = Table(title="LLM Rewritten Schedule Items")
        table.add_column("Original")
        table.add_column("Schedule Text")
        table.add_column("Reason")

        for item in rewritten_items:
            table.add_row(
                item.get("original") or "",
                item.get("schedule_content") or "",
                item.get("rewrite_reason") or "",
            )

        console.print(table)

    skipped = proposal.get("skipped_duplicates") or []
    if skipped:
        console.print("[yellow]Skipped duplicates:[/yellow]")
        for item in skipped:
            console.print(f"- {item}")

    if not proposal.get("changed"):
        console.print(
            Panel(
                proposal.get("message") or "Nothing to change.",
                title="Adopt Inbox",
                border_style="green",
            )
        )
        return

    console.print(
        Panel(
            Syntax(
                proposal.get("diff") or "",
                "diff",
                theme="monokai",
                line_numbers=False,
            ),
            title="Proposed Adopt-inbox Diff",
            border_style="yellow",
        )
    )

    if not apply:
        console.print("[dim]Dry-run only. Use --apply to write changes.[/dim]")
        return

    if not yes:
        confirmed = typer.confirm("Apply this adopt-inbox change?")
        if not confirmed:
            console.print("[yellow]Cancelled.[/yellow]")
            return

    result = apply_adopt_inbox_today(config, proposal)

    console.print(
        Panel(
            str(result),
            title="Adopt-inbox Result",
            border_style="green",
        )
    )
    
@app.command("mark-organized-existing")
def mark_organized_existing(
    days: int = typer.Option(
        7,
        "--days",
        "-d",
        help="Look back N days for historical Thino captures.",
    ),
    threshold: float = typer.Option(
        0.72,
        "--threshold",
        help="Similarity threshold for historical migration.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply organized markers to source Thino lines.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation when applying.",
    ),
):
    """
    Mark historical Thino captures as organized if they already appear in ## 日程.

    This is a migration command for old data created before #agent/organized existed.
    Default is dry-run.
    """
    config = load_config()

    proposal = prepare_mark_organized_existing(
        config,
        days=days,
        threshold=threshold,
    )

    console.print(f"[bold]Days:[/bold] {proposal.get('days')}")
    console.print(f"[bold]Threshold:[/bold] {proposal.get('threshold')}")
    console.print(f"[bold]Matches:[/bold] {len(proposal.get('matches', []))}")
    console.print(f"[bold]Changed files:[/bold] {len(proposal.get('changed_files', []))}")

    matches = proposal.get("matches") or []
    if matches:
        table = Table(title="Historical Organized Matches")
        table.add_column("Thino Capture")
        table.add_column("Matched Schedule")
        table.add_column("Source Line")
        table.add_column("Matched Line")

        for match in matches:
            table.add_row(
                match.get("source_content") or "",
                match.get("matched_content") or "",
                str(match.get("source_line") or ""),
                str(match.get("matched_line") or ""),
            )

        console.print(table)

    if not proposal.get("changed"):
        console.print(
            Panel(
                proposal.get("message") or "Nothing to change.",
                title="Mark Organized Existing",
                border_style="green",
            )
        )
        return

    console.print(
        Panel(
            Syntax(
                proposal.get("diff") or "",
                "diff",
                theme="monokai",
                line_numbers=False,
            ),
            title="Proposed Organized Marker Migration",
            border_style="yellow",
        )
    )

    if not apply:
        console.print("[dim]Dry-run only. Use --apply to write changes.[/dim]")
        return

    if not yes:
        confirmed = typer.confirm("Apply organized markers?")
        if not confirmed:
            console.print("[yellow]Cancelled.[/yellow]")
            return

    result = apply_mark_organized_existing(config, proposal)

    console.print(
        Panel(
            str(result),
            title="Mark Organized Existing Result",
            border_style="green",
        )
    )