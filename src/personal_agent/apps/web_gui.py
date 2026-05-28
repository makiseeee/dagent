from __future__ import annotations

import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


HOST = "127.0.0.1"
PORT = 8765
TODAY_MESSAGE = "今天有什么事项？"
REMINDER_INTERVAL_SECONDS = 60


HTML_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>个人 Agent</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1f2937;
      --muted: #667085;
      --border: #d0d5dd;
      --primary: #2563eb;
      --primary-hover: #1d4ed8;
      --danger: #b42318;
      --shadow: 0 8px 28px rgba(16, 24, 40, 0.08);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei",
        "Noto Sans CJK SC", "PingFang SC", Arial, sans-serif;
      line-height: 1.5;
    }

    main {
      width: min(960px, calc(100vw - 32px));
      margin: 32px auto;
    }

    h1 {
      margin: 0 0 20px;
      font-size: 30px;
      font-weight: 700;
    }

    section {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 18px;
      margin-bottom: 16px;
    }

    label,
    h2 {
      display: block;
      margin: 0 0 10px;
      font-size: 16px;
      font-weight: 650;
    }

    .command-row,
    .reminder-row {
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }

    input {
      flex: 1 1 320px;
      min-width: 0;
      height: 42px;
      padding: 0 12px;
      border: 1px solid var(--border);
      border-radius: 6px;
      font: inherit;
      background: #ffffff;
      color: var(--text);
    }

    button {
      height: 42px;
      padding: 0 16px;
      border: 1px solid transparent;
      border-radius: 6px;
      background: var(--primary);
      color: #ffffff;
      font: inherit;
      font-weight: 650;
      cursor: pointer;
    }

    button:hover {
      background: var(--primary-hover);
    }

    button.secondary {
      background: #ffffff;
      color: var(--text);
      border-color: var(--border);
    }

    button.secondary:hover {
      background: #f2f4f7;
    }

    button.danger {
      background: #ffffff;
      color: var(--danger);
      border-color: #fda29b;
    }

    button.danger:hover {
      background: #fff1f0;
    }

    button:disabled {
      cursor: not-allowed;
      opacity: 0.65;
    }

    .status {
      color: var(--muted);
      font-weight: 650;
    }

    pre {
      height: min(58vh, 520px);
      min-height: 260px;
      overflow: auto;
      margin: 0;
      padding: 14px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #101828;
      color: #f9fafb;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 13px;
    }
  </style>
</head>
<body>
  <main>
    <h1>个人 Agent</h1>

    <section>
      <label for="message">指令</label>
      <div class="command-row">
        <input id="message" type="text" placeholder="请输入指令，例如：今天有什么事项？" autocomplete="off">
        <button id="sendButton" type="button">发送</button>
        <button id="todayButton" class="secondary" type="button">今天事项</button>
      </div>
    </section>

    <section>
      <h2>提醒</h2>
      <div class="reminder-row">
        <button id="startReminderButton" type="button">开始提醒</button>
        <button id="stopReminderButton" class="danger" type="button">停止提醒</button>
        <span>状态：<span id="reminderStatus" class="status">就绪</span></span>
      </div>
    </section>

    <section>
      <h2>输出</h2>
      <pre id="output" aria-live="polite"></pre>
    </section>
  </main>

  <script>
    const messageInput = document.getElementById("message");
    const sendButton = document.getElementById("sendButton");
    const todayButton = document.getElementById("todayButton");
    const startReminderButton = document.getElementById("startReminderButton");
    const stopReminderButton = document.getElementById("stopReminderButton");
    const reminderStatus = document.getElementById("reminderStatus");
    const output = document.getElementById("output");

    function appendOutput(title, data) {
      const time = new Date().toLocaleString("zh-CN", { hour12: false });
      const stdout = data.stdout || "";
      const stderr = data.stderr || "";
      const status = typeof data.returncode === "number" ? `退出码：${data.returncode}` : "";
      const body = [stdout, stderr ? `stderr:\\n${stderr}` : "", status].filter(Boolean).join("\\n");
      output.textContent += `[${time}] ${title}\\n${body || "完成"}\\n\\n`;
      output.scrollTop = output.scrollHeight;
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

    async function runAsk(message) {
      if (!message.trim()) return;
      sendButton.disabled = true;
      todayButton.disabled = true;
      appendOutput("正在执行", { stdout: message });
      try {
        const data = await requestJson("/api/ask", {
          method: "POST",
          body: JSON.stringify({ message }),
        });
        appendOutput("执行结果", data);
      } catch (error) {
        appendOutput("错误", { stderr: error.message, returncode: 1 });
      } finally {
        sendButton.disabled = false;
        todayButton.disabled = false;
      }
    }

    sendButton.addEventListener("click", () => runAsk(messageInput.value));
    todayButton.addEventListener("click", async () => {
      todayButton.disabled = true;
      appendOutput("正在执行", { stdout: "今天有什么事项？" });
      try {
        const data = await requestJson("/api/today", { method: "POST", body: "{}" });
        appendOutput("执行结果", data);
      } catch (error) {
        appendOutput("错误", { stderr: error.message, returncode: 1 });
      } finally {
        todayButton.disabled = false;
      }
    });

    messageInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        runAsk(messageInput.value);
      }
    });

    startReminderButton.addEventListener("click", async () => {
      try {
        const data = await requestJson("/api/reminders/start", { method: "POST", body: "{}" });
        reminderStatus.textContent = data.status || "提醒监听中";
        appendOutput("提醒", data);
      } catch (error) {
        appendOutput("错误", { stderr: error.message, returncode: 1 });
      }
    });

    stopReminderButton.addEventListener("click", async () => {
      try {
        const data = await requestJson("/api/reminders/stop", { method: "POST", body: "{}" });
        reminderStatus.textContent = data.status || "已停止";
        appendOutput("提醒", data);
      } catch (error) {
        appendOutput("错误", { stderr: error.message, returncode: 1 });
      }
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

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return {"status": "提醒监听中", "stdout": "提醒监听已经在运行。"}

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
            run_agent_command(["schedule", "reminders", "due"])
            self._stop_event.wait(REMINDER_INTERVAL_SECONDS)


reminder_watcher = ReminderWatcher()


def run_agent_command(args: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["uv", "run", "agent", *args],
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


class WebGuiHandler(BaseHTTPRequestHandler):
    server_version = "PersonalAgentWebGui/0.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(HTML_PAGE)
            return
        if path == "/api/reminders/due":
            self._send_json(run_agent_command(["schedule", "reminders", "due"]))
            return
        self._send_json({"error": "未找到接口"}, status=404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/ask":
            body = self._read_json()
            message = str(body.get("message", "")).strip()
            if not message:
                self._send_json({"error": "请输入指令"}, status=400)
                return
            self._send_json(run_agent_command(["ask", message]))
            return
        if path == "/api/today":
            self._send_json(run_agent_command(["ask", TODAY_MESSAGE]))
            return
        if path == "/api/reminders/start":
            self._send_json(reminder_watcher.start())
            return
        if path == "/api/reminders/stop":
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
