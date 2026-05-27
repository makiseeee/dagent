import typer

from personal_agent.core.config.loader import load_config
from personal_agent.apps import schedule_cli, backup_cli, debug_cli
from personal_agent.apps.ask_flow import run_ask_flow


app = typer.Typer(
    help="Personal extensible agent framework.",
    no_args_is_help=True,
)

app.add_typer(schedule_cli.app, name="schedule")
app.add_typer(backup_cli.app, name="backup")
app.add_typer(debug_cli.app, name="debug")


@app.callback()
def main():
    """
    Personal Agent CLI.
    """
    pass


@app.command()
def ask(
    message: str,
    stream: bool = typer.Option(
        True,
        "--stream/--no-stream",
        help="Stream the final answer token by token.",
    ),
):
    """
    Ask the personal agent a question.
    """
    config = load_config()

    run_ask_flow(
        config,
        message,
        stream=stream,
    )


if __name__ == "__main__":
    app()