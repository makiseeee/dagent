from __future__ import annotations

import platform
import shutil
import subprocess


def is_wsl() -> bool:
    release = platform.uname().release.lower()
    return "microsoft" in release or "wsl" in release


def can_send_windows_notification() -> bool:
    return is_wsl() and shutil.which("powershell.exe") is not None


def _escape_powershell_single_quoted(text: str) -> str:
    return text.replace("'", "''")


def send_windows_message_box(
    *,
    title: str,
    message: str,
    timeout_seconds: int = 10,
) -> dict:
    """
    Send a simple Windows MessageBox from WSL via powershell.exe.

    This is intentionally simple and stable. It is not a toast notification yet.
    """
    if not can_send_windows_notification():
        return {
            "status": "unavailable",
            "message": "Windows notification is only available from WSL with powershell.exe.",
        }

    safe_title = _escape_powershell_single_quoted(title)
    safe_message = _escape_powershell_single_quoted(message)

    command = (
        "Add-Type -AssemblyName PresentationFramework; "
        f"[System.Windows.MessageBox]::Show('{safe_message}', '{safe_title}')"
    )

    try:
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-Command", command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return {
            "status": "sent",
            "title": title,
            "message": message,
            "timeout_seconds": timeout_seconds,
        }

    except Exception as exc:
        return {
            "status": "error",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }