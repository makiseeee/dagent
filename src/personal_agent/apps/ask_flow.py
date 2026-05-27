import sys

from rich.console import Console
from rich.panel import Panel

from personal_agent.core.config.loader import AppConfig
from personal_agent.apps.runtime_factory import build_runtime
from personal_agent.apps.confirmation_handlers import (
    handle_mark_done_if_present,
    handle_pending_confirmation,
)


console = Console()


def run_ask_flow(
    config: AppConfig,
    message: str,
    *,
    stream: bool = True,
) -> None:
    runtime, llm = build_runtime(config)

    state = runtime.prepare(message)

    if handle_mark_done_if_present(config, state):
        return

    if state.pending_confirmation:
        handle_pending_confirmation(config, state)
        return

    if stream:
        console.print("[bold blue]Personal Agent[/bold blue]")

        if state.final_answer:
            sys.stdout.write(state.final_answer)
        elif state.messages:
            for chunk in llm.chat_stream(state.messages, temperature=0.2):
                sys.stdout.write(chunk)
                sys.stdout.flush()
        else:
            sys.stdout.write("没有可用回复。")

        sys.stdout.write("\n")
        sys.stdout.flush()
        return

    if state.final_answer:
        final_answer = state.final_answer
    elif state.messages:
        final_answer = llm.chat(state.messages, temperature=0.2)
    else:
        final_answer = "没有可用回复。"

    console.print(
        Panel(
            final_answer,
            title="Personal Agent",
            border_style="blue",
        )
    )