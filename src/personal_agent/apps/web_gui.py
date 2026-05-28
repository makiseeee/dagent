from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


HOST = "127.0.0.1"
PORT = 8765
TODAY_MESSAGE = "今天有什么事项？"
WEEK_MESSAGE = "这周有什么安排？"
DEFAULT_REMINDER_INTERVAL_SECONDS = 60
DEFAULT_REMINDER_WINDOW_MINUTES = 5


ALLOWED_COMMANDS: set[tuple[str, ...]] = {
    ("uv", "run", "agent", "schedule", "inbox", "--days", "7", "--raw"),
    ("uv", "run", "agent", "schedule", "adopt-inbox-today"),
    ("uv", "run", "agent", "schedule", "adopt-inbox-today", "--apply", "--yes"),
    ("uv", "run", "agent", "schedule", "recurring", "list"),
    ("uv", "run", "agent", "schedule", "reminders", "due"),
}


HTML_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>个人 Agent</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #eef2f7;
      --panel: #ffffff;
      --panel-soft: #f8fafc;
      --text: #182230;
      --muted: #667085;
      --border: #d0d5dd;
      --primary: #2563eb;
      --primary-hover: #1d4ed8;
      --success: #067647;
      --warning: #b54708;
      --danger: #b42318;
      --danger-bg: #fff1f0;
      --shadow: 0 14px 36px rgba(16, 24, 40, 0.10);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      background:
        linear-gradient(180deg, #f7f9fc 0%, #eef2f7 44%, #e9eef5 100%);
      color: var(--text);
      font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
      line-height: 1.5;
    }

    main {
      width: min(1120px, calc(100vw - 32px));
      margin: 28px auto 40px;
    }

    .header {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      gap: 16px;
      margin-bottom: 18px;
    }

    h1,
    h2,
    p {
      margin: 0;
    }

    h1 {
      font-size: 32px;
      font-weight: 750;
      letter-spacing: 0;
    }

    .subtitle {
      margin-top: 6px;
      color: var(--muted);
      font-size: 15px;
    }

    .server {
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }

    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.95fr);
      gap: 16px;
      align-items: start;
    }

    .stack {
      display: grid;
      gap: 16px;
    }

    .card {
      background: var(--panel);
      border: 1px solid rgba(208, 213, 221, 0.86);
      border-radius: 14px;
      box-shadow: var(--shadow);
      padding: 18px;
    }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }

    .card h2,
    label {
      display: block;
      font-size: 16px;
      font-weight: 700;
      letter-spacing: 0;
    }

    .hint {
      color: var(--muted);
      font-size: 13px;
    }

    .command-row,
    .reminder-row,
    .field-row {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }

    input {
      min-width: 0;
      height: 42px;
      padding: 0 12px;
      border: 1px solid var(--border);
      border-radius: 10px;
      font: inherit;
      background: #ffffff;
      color: var(--text);
      outline: none;
    }

    input:focus {
      border-color: #84adff;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.14);
    }

    #message {
      flex: 1 1 360px;
    }

    .number-field {
      width: 120px;
    }

    button {
      min-height: 42px;
      padding: 0 15px;
      border: 1px solid transparent;
      border-radius: 10px;
      background: var(--primary);
      color: #ffffff;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      transition: background 0.15s ease, border-color 0.15s ease, transform 0.08s ease;
    }

    button:hover {
      background: var(--primary-hover);
    }

    button:active {
      transform: translateY(1px);
    }

    button.secondary {
      background: #ffffff;
      color: var(--text);
      border-color: var(--border);
    }

    button.secondary:hover {
      background: #f2f4f7;
    }

    button.warning {
      background: #ffffff;
      color: var(--warning);
      border-color: #fedf89;
    }

    button.warning:hover {
      background: #fffaeb;
    }

    button.danger {
      background: #ffffff;
      color: var(--danger);
      border-color: #fda29b;
    }

    button.danger:hover {
      background: var(--danger-bg);
    }

    button:disabled {
      cursor: not-allowed;
      opacity: 0.62;
      transform: none;
    }

    .quick-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .quick-grid button {
      width: 100%;
      min-height: 46px;
      text-align: center;
    }

    .status {
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: 0 10px;
      border-radius: 999px;
      background: var(--panel-soft);
      color: var(--muted);
      font-weight: 700;
      font-size: 13px;
    }

    .status.running {
      background: #ecfdf3;
      color: var(--success);
    }

    .status.stopped {
      background: #f2f4f7;
      color: #475467;
    }

    .status.error {
      background: var(--danger-bg);
      color: var(--danger);
    }

    .output-toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }

    .output-log {
      height: min(62vh, 640px);
      min-height: 360px;
      overflow: auto;
      border: 1px solid #202939;
      border-radius: 12px;
      background: #101828;
      color: #f9fafb;
      padding: 12px;
    }

    .entry {
      border-bottom: 1px solid rgba(255, 255, 255, 0.10);
      padding: 0 0 12px;
      margin-bottom: 12px;
    }

    .entry:last-child {
      border-bottom: 0;
      margin-bottom: 0;
    }

    .entry-header {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: #c7d7fe;
      font-size: 12px;
      margin-bottom: 8px;
    }

    .entry.error .entry-header {
      color: #fecdca;
    }

    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 13px;
      line-height: 1.55;
    }

    .stderr {
      color: #fecaca;
      margin-top: 8px;
    }

    .return-code {
      color: #a4b3c8;
      margin-top: 8px;
    }

    .empty {
      color: #a4b3c8;
      font-size: 13px;
    }

    @media (max-width: 880px) {
      main {
        width: min(100% - 20px, 1120px);
        margin-top: 18px;
      }

      .header {
        display: block;
      }

      .server {
        margin-top: 8px;
      }

      .grid {
        grid-template-columns: 1fr;
      }

      .quick-grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <main>
    <header class="header">
      <div>
        <h1>个人 Agent</h1>
        <p class="subtitle">本地日程与提醒助手</p>
      </div>
      <p class="server">127.0.0.1:8765</p>
    </header>

    <div class="grid">
      <div class="stack">
        <section class="card">
          <div class="card-header">
            <h2>自然语言指令</h2>
            <span class="hint">Enter 发送</span>
          </div>
          <div class="command-row">
            <input id="message" type="text" placeholder="请输入指令，例如：今天有什么事项？" autocomplete="off">
            <button id="sendButton" type="button">发送</button>
          </div>
        </section>

        <section class="card">
          <div class="card-header">
            <h2>快捷操作</h2>
            <span class="hint">固定白名单命令</span>
          </div>
          <div class="quick-grid">
            <button type="button" data-ask="今天有什么事项？">今天事项</button>
            <button type="button" data-command='["uv","run","agent","schedule","inbox","--days","7","--raw"]'>查看 inbox</button>
            <button type="button" data-command='["uv","run","agent","schedule","adopt-inbox-today"]'>预览安排 inbox</button>
            <button class="warning" type="button" data-command='["uv","run","agent","schedule","adopt-inbox-today","--apply","--yes"]'>应用安排 inbox（直接写入）</button>
            <button type="button" data-ask="这周有什么安排？">本周安排</button>
            <button type="button" data-command='["uv","run","agent","schedule","recurring","list"]'>循环日程</button>
            <button type="button" data-reminders-due="true">检查提醒</button>
          </div>
        </section>

        <section class="card">
          <div class="card-header">
            <h2>提醒</h2>
            <span id="reminderStatus" class="status">就绪</span>
          </div>
          <div class="field-row">
            <label for="intervalSeconds">检查间隔（秒）</label>
            <input id="intervalSeconds" class="number-field" type="number" min="5" step="1" value="60">
            <label for="windowMinutes">提醒窗口（分钟）</label>
            <input id="windowMinutes" class="number-field" type="number" min="1" step="1" value="5">
          </div>
          <div class="reminder-row" style="margin-top: 12px;">
            <button id="startReminderButton" type="button">开始提醒</button>
            <button id="stopReminderButton" class="danger" type="button">停止提醒</button>
            <span class="hint">开始后按设定间隔检查提醒，并把结果写入输出。</span>
          </div>
        </section>
      </div>

      <section class="card">
        <div class="output-toolbar">
          <h2>输出</h2>
          <button id="clearOutputButton" class="secondary" type="button">清空输出</button>
        </div>
        <div id="output" class="output-log" aria-live="polite">
          <div class="empty">暂无输出。</div>
        </div>
      </section>
    </div>
  </main>

  <script>
    const messageInput = document.getElementById("message");
    const sendButton = document.getElementById("sendButton");
    const clearOutputButton = document.getElementById("clearOutputButton");
    const startReminderButton = document.getElementById("startReminderButton");
    const stopReminderButton = document.getElementById("stopReminderButton");
    const reminderStatus = document.getElementById("reminderStatus");
    const intervalSecondsInput = document.getElementById("intervalSeconds");
    const windowMinutesInput = document.getElementById("windowMinutes");
    const output = document.getElementById("output");
    let activeRuns = 0;
    let reminderTimer = null;

    function setBusy(isBusy) {
      if (isBusy) activeRuns += 1;
      else activeRuns = Math.max(0, activeRuns - 1);
      sendButton.disabled = activeRuns > 0;
      sendButton.textContent = activeRuns > 0 ? "执行中..." : "发送";
    }

    function setReminderStatus(text, state) {
      reminderStatus.textContent = text;
      reminderStatus.className = `status ${state || ""}`.trim();
    }

    function clearEmptyState() {
      const empty = output.querySelector(".empty");
      if (empty) empty.remove();
    }

    function appendOutput(title, commandText, data) {
      clearEmptyState();
      const entry = document.createElement("article");
      const failed = Boolean(data.stderr) || (typeof data.returncode === "number" && data.returncode !== 0);
      entry.className = failed ? "entry error" : "entry";

      const header = document.createElement("div");
      header.className = "entry-header";
      const time = new Date().toLocaleString("zh-CN", { hour12: false });
      header.innerHTML = `<span>${escapeHtml(title)}</span><span>${escapeHtml(time)}</span>`;

      const command = document.createElement("pre");
      command.textContent = `> ${commandText}`;

      const stdout = document.createElement("pre");
      stdout.textContent = data.stdout || "完成";

      entry.appendChild(header);
      entry.appendChild(command);
      entry.appendChild(stdout);

      if (data.stderr) {
        const stderr = document.createElement("pre");
        stderr.className = "stderr";
        stderr.textContent = `stderr:\\n${data.stderr}`;
        entry.appendChild(stderr);
      }

      if (typeof data.returncode === "number") {
        const code = document.createElement("pre");
        code.className = "return-code";
        code.textContent = `退出码：${data.returncode}`;
        entry.appendChild(code);
      }

      output.appendChild(entry);
      output.scrollTop = output.scrollHeight;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    async function requestJson(url, options = {}) {
      const response = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || `请求失败：${response.status}`);
      }
      return data;
    }

    async function runAsk(message, title = "自然语言指令") {
      const trimmed = message.trim();
      if (!trimmed) return;
      setBusy(true);
      try {
        const data = await requestJson("/api/ask", {
          method: "POST",
          body: JSON.stringify({ message: trimmed }),
        });
        appendOutput(title, trimmed, data);
      } catch (error) {
        appendOutput("发生错误", trimmed, { stderr: error.message, returncode: 1 });
      } finally {
        setBusy(false);
      }
    }

    async function runCommand(args, title = "快捷操作") {
      setBusy(true);
      const commandText = args.join(" ");
      try {
        const data = await requestJson("/api/command", {
          method: "POST",
          body: JSON.stringify({ args }),
        });
        appendOutput(title, commandText, data);
      } catch (error) {
        appendOutput("发生错误", commandText, { stderr: error.message, returncode: 1 });
      } finally {
        setBusy(false);
      }
    }

    async function checkReminders(title = "检查提醒") {
      const windowMinutes = Math.max(1, Number.parseInt(windowMinutesInput.value || "5", 10));
      const commandText = `uv run agent schedule reminders due --window-minutes ${windowMinutes}`;
      try {
        const data = await requestJson(`/api/reminders/due?window_minutes=${encodeURIComponent(windowMinutes)}`);
        appendOutput(title, commandText, data);
        if (data.returncode !== 0) setReminderStatus("发生错误", "error");
      } catch (error) {
        setReminderStatus("发生错误", "error");
        appendOutput("发生错误", commandText, { stderr: error.message, returncode: 1 });
      }
    }

    sendButton.addEventListener("click", () => runAsk(messageInput.value));
    messageInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !sendButton.disabled) {
        runAsk(messageInput.value);
      }
    });

    document.querySelectorAll("[data-ask]").forEach((button) => {
      button.addEventListener("click", () => runAsk(button.dataset.ask || "", button.textContent.trim()));
    });

    document.querySelectorAll("[data-command]").forEach((button) => {
      button.addEventListener("click", () => {
        const args = JSON.parse(button.dataset.command || "[]");
        runCommand(args, button.textContent.trim());
      });
    });

    document.querySelector("[data-reminders-due]").addEventListener("click", () => {
      checkReminders("检查提醒");
    });

    clearOutputButton.addEventListener("click", () => {
      output.innerHTML = '<div class="empty">暂无输出。</div>';
    });

    startReminderButton.addEventListener("click", () => {
      if (reminderTimer) return;
      const intervalSeconds = Math.max(5, Number.parseInt(intervalSecondsInput.value || "60", 10));
      setReminderStatus("提醒监听中", "running");
      checkReminders("提醒监听");
      reminderTimer = window.setInterval(() => checkReminders("提醒监听"), intervalSeconds * 1000);
    });

    stopReminderButton.addEventListener("click", () => {
      if (reminderTimer) {
        window.clearInterval(reminderTimer);
        reminderTimer = null;
      }
      setReminderStatus("已停止", "stopped");
      appendOutput("提醒", "停止提醒", { stdout: "提醒监听已停止。" });
    });
  </script>
</body>
</html>
"""


class ReminderWatcher:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._interval_seconds = DEFAULT_REMINDER_INTERVAL_SECONDS
        self._window_minutes = DEFAULT_REMINDER_WINDOW_MINUTES

    def start(self, *, interval_seconds: int, window_minutes: int) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return {"status": "提醒监听中", "stdout": "提醒监听已经在运行。"}

            self._interval_seconds = max(5, interval_seconds)
            self._window_minutes = max(1, window_minutes)
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
            return {"status": "提醒监听中", "stdout": "提醒监听已启动。"}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._stop_event.set()
            thread = self._thread

        if thread and thread.is_alive():
            thread.join(timeout=2)

        return {"status": "已停止", "stdout": "提醒监听已停止。"}

    def _run(self) -> None:
        while not self._stop_event.is_set():
            run_agent_command(
                [
                    "schedule",
                    "reminders",
                    "due",
                    "--window-minutes",
                    str(self._window_minutes),
                ]
            )
            self._stop_event.wait(self._interval_seconds)


reminder_watcher = ReminderWatcher()


def run_command(command: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return {
            "stdout": "",
            "stderr": str(exc),
            "returncode": 127,
        }

    return {
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returncode": completed.returncode,
    }


def run_agent_command(args: list[str]) -> dict[str, Any]:
    return run_command(["uv", "run", "agent", *args])


def parse_positive_int(value: str | None, default: int, minimum: int) -> int:
    try:
        parsed = int(value or "")
    except ValueError:
        return default
    return max(minimum, parsed)


class WebGuiHandler(BaseHTTPRequestHandler):
    server_version = "PersonalAgentWebGui/0.2"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(HTML_PAGE)
            return
        if parsed.path == "/api/reminders/due":
            query = parse_qs(parsed.query)
            window_minutes = parse_positive_int(
                query.get("window_minutes", [""])[0],
                DEFAULT_REMINDER_WINDOW_MINUTES,
                1,
            )
            self._send_json(
                run_agent_command(
                    [
                        "schedule",
                        "reminders",
                        "due",
                        "--window-minutes",
                        str(window_minutes),
                    ]
                )
            )
            return
        self._send_json({"error": "未找到接口"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/ask":
            body = self._read_json()
            message = str(body.get("message", "")).strip()
            if not message:
                self._send_json({"error": "请输入指令"}, status=400)
                return
            self._send_json(run_agent_command(["ask", message]))
            return
        if parsed.path == "/api/command":
            body = self._read_json()
            args = body.get("args")
            if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
                self._send_json({"error": "命令参数无效"}, status=400)
                return
            if tuple(args) not in ALLOWED_COMMANDS:
                self._send_json({"error": "该命令不在白名单中"}, status=403)
                return
            self._send_json(run_command(args))
            return
        if parsed.path == "/api/today":
            self._send_json(run_agent_command(["ask", TODAY_MESSAGE]))
            return
        if parsed.path == "/api/reminders/start":
            body = self._read_json()
            interval_seconds = parse_positive_int(
                str(body.get("interval_seconds", "")),
                DEFAULT_REMINDER_INTERVAL_SECONDS,
                5,
            )
            window_minutes = parse_positive_int(
                str(body.get("window_minutes", "")),
                DEFAULT_REMINDER_WINDOW_MINUTES,
                1,
            )
            self._send_json(
                reminder_watcher.start(
                    interval_seconds=interval_seconds,
                    window_minutes=window_minutes,
                )
            )
            return
        if parsed.path == "/api/reminders/stop":
            self._send_json(reminder_watcher.stop())
            return
        self._send_json({"error": "未找到接口"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw_body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError:
            return {}
        if isinstance(data, dict):
            return data
        return {}

    def _send_html(self, content: str, status: int = 200) -> None:
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), WebGuiHandler)
    print(f"个人 Agent Web GUI 已启动：http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        reminder_watcher.stop()
        server.server_close()
        print("个人 Agent Web GUI 已停止。", flush=True)


if __name__ == "__main__":
    main()
