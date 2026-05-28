#  DAgent

A local extensible personal agent framework running in WSL.

Current features:

- CLI agent runtime
- DeepSeek-compatible LLM adapter
- Tool registry / planner / executor
- Obsidian + Thino schedule parser
- Schedule inbox and daily overview
- Git backup support
- Safe write operations with diff / confirmation

## Setup

```bash
uv sync
cp .env.example .env
cp configs/agent.example.yaml configs/agent.yaml
```

## Web GUI

启动本地 Web GUI：

```bash
uv run agent-web
```

然后在浏览器打开：

```text
http://127.0.0.1:8765
```

页面是简体中文界面，默认只监听 `127.0.0.1`。常用操作：

- 在输入框输入自然语言指令，例如 `今天有什么事项？`，点击“发送”或按 Enter。
- “今天事项”：等价执行 `今天有什么事项？`。
- “查看 inbox”：执行 `uv run agent schedule inbox --days 7 --raw`。
- “预览安排 inbox”：执行 dry-run，不写入文件。
- “应用安排 inbox（直接写入）”：执行 `uv run agent schedule adopt-inbox-today --apply --yes`，会直接写入 Obsidian 相关文件，使用前请先预览。
- “本周安排”：等价执行 `这周有什么安排？`。
- “循环日程”：执行 `uv run agent schedule recurring list`。
- “检查提醒”：执行 `uv run agent schedule reminders due`。

提醒区域可以设置“检查间隔（秒）”和“提醒窗口（分钟）”。点击“开始提醒”后，页面会按设定间隔检查提醒并把结果追加到输出区域；点击“停止提醒”会停止页面端监听。

finally,
koishi is absolutely right!!
