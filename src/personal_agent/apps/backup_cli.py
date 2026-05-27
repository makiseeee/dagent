from datetime import datetime
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.panel import Panel

from personal_agent.core.config.loader import load_config
from personal_agent.core.backup.git_backup import GitBackupManager


app = typer.Typer(
    help="Git backup commands for Obsidian vault.",
    no_args_is_help=True,
)

console = Console()


@app.command()
def status():
    """
    Show git status for the Obsidian vault.
    """
    config = load_config()
    manager = GitBackupManager(config.obsidian.vault_path)

    result = manager.get_status()

    if not result.has_changes:
        console.print(
            Panel(
                f"Repo: {result.repo_path}\nBranch: {result.branch}\n\nNo changes.",
                title="Obsidian Git Status",
                border_style="green",
            )
        )
        return

    console.print(
        Panel(
            (
                f"Repo: {result.repo_path}\n"
                f"Branch: {result.branch}\n\n"
                f"{result.status_short}"
            ),
            title="Obsidian Git Status",
            border_style="yellow",
        )
    )


@app.command("commit")
def commit_cmd(
    message: str | None = typer.Option(
        None,
        "--message",
        "-m",
        help="Commit message.",
    ),
    push: bool = typer.Option(
        False,
        "--push",
        help="Push to remote after commit.",
    ),
):
    """
    Commit all current Obsidian vault changes.
    """
    config = load_config()
    manager = GitBackupManager(config.obsidian.vault_path)

    if message is None:
        now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
        message = f"{config.backup.default_commit_message} - {now}"

    result = manager.commit_and_maybe_push(message=message, push=push)

    if result["status"] == "no_changes":
        console.print(
            Panel(
                result["message"],
                title="Obsidian Git Backup",
                border_style="green",
            )
        )
        return

    if result["status"] == "committed":
        body = result.get("stdout", "")

        push_result = result.get("push")
        if push_result:
            body += "\n\nPush: " + push_result.get("status", "")

            if push_result.get("error"):
                body += "\n" + push_result["error"]

        console.print(
            Panel(
                body,
                title="Obsidian Git Backup",
                border_style="green",
            )
        )
        return

    console.print(
        Panel(
            str(result),
            title="Obsidian Git Backup Error",
            border_style="red",
        )
    )