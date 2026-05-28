# AGENTS.md

## Project

This is a local personal agent framework written in Python.

Repository:
https://github.com/makiseeee/dagent

The project runs with uv.

Important commands:

```bash
uv sync
uv run pytest
uv run agent --help
uv run agent ask "今天有什么事项？"
uv run agent schedule reminders due
Language

The user interface must be in Simplified Chinese.

Use Chinese labels, buttons, status text, error messages, and README usage examples for the GUI.

Examples:

输入框 placeholder: 请输入指令，例如：今天有什么事项？
Send button: 发送
Today button: 今天事项
Reminder button: 开始提醒 / 停止提醒
Output area title: 输出
Status text: 就绪 / 正在执行 / 提醒监听中
Constraints

Do not rewrite the agent architecture.

Do not change schedule parser behavior.

Do not change Obsidian data formats.

Do not hardcode API keys.

Do not require .env to be committed.

Do not modify existing CLI behavior.

The GUI must be optional. The CLI must keep working.

Keep tests passing.

Preferred GUI

Build a minimal desktop GUI.

Prefer Tkinter unless there is a strong reason to use another GUI framework.

Put GUI code under:

src/personal_agent/apps/gui.py

Add an entrypoint if appropriate:

agent-gui = "personal_agent.apps.gui:main"
GUI requirements

The GUI should have:

A Chinese title, such as 个人 Agent.
A text input box.
A 发送 button.
A scrollable output area.
A 今天事项 button that sends 今天有什么事项？.
A reminder section:
开始提醒
停止提醒
reminder status label
Long-running calls must not freeze the UI.
Use a background thread for command execution.
Display stdout and stderr in the output area.
Reuse existing CLI or Python functions instead of duplicating schedule logic.
Suggested implementation

For the first version, it is acceptable for the GUI to call subprocess commands:

uv run agent ask "<用户输入>"
uv run agent schedule reminders due

But the code should be structured so it can later call internal Python functions directly.

Reminder watcher should reuse existing reminder logic if possible:

personal_agent.plugins.schedule.services.reminder_service.find_due_recurring_reminders
personal_agent.plugins.schedule.services.reminder_state.ReminderStateStore
personal_agent.core.notify.send_windows_message_box
Acceptance criteria

Before finishing, run:

uv run pytest
uv run agent --help

Manual checks:

uv run agent-gui

The GUI should open and support:

输入 今天有什么事项？
点击 发送
点击 今天事项
点击 开始提醒
点击 停止提醒

Do not make unrelated refactors.


