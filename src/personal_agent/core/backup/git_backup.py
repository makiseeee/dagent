from pathlib import Path
import subprocess
from pydantic import BaseModel


class GitCommandResult(BaseModel):
    ok: bool
    command: list[str]
    cwd: str
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


class GitBackupStatus(BaseModel):
    repo_path: str
    is_git_repo: bool
    has_changes: bool
    branch: str | None = None
    status_short: str = ""


class GitBackupManager:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).expanduser()

    def _run_git(self, args: list[str]) -> GitCommandResult:
        command = ["git", *args]

        completed = subprocess.run(
            command,
            cwd=self.repo_path,
            text=True,
            capture_output=True,
            check=False,
        )

        return GitCommandResult(
            ok=completed.returncode == 0,
            command=command,
            cwd=str(self.repo_path),
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
            returncode=completed.returncode,
        )

    def ensure_repo_exists(self) -> None:
        if not self.repo_path.exists():
            raise FileNotFoundError(f"Repo path does not exist: {self.repo_path}")

        result = self._run_git(["rev-parse", "--is-inside-work-tree"])
        if not result.ok or result.stdout.strip() != "true":
            raise RuntimeError(f"Not a git repository: {self.repo_path}")

    def get_status(self) -> GitBackupStatus:
        self.ensure_repo_exists()

        branch_result = self._run_git(["branch", "--show-current"])
        status_result = self._run_git(["status", "--short"])

        if not status_result.ok:
            raise RuntimeError(status_result.stderr or "Failed to get git status")

        status_short = status_result.stdout

        return GitBackupStatus(
            repo_path=str(self.repo_path),
            is_git_repo=True,
            has_changes=bool(status_short.strip()),
            branch=branch_result.stdout or None,
            status_short=status_short,
        )

    def commit_all(self, message: str) -> dict:
        self.ensure_repo_exists()

        status = self.get_status()
        if not status.has_changes:
            return {
                "status": "no_changes",
                "message": "No changes to commit.",
                "repo_path": str(self.repo_path),
                "branch": status.branch,
            }

        add_result = self._run_git(["add", "."])
        if not add_result.ok:
            return {
                "status": "error",
                "step": "git add",
                "error": add_result.stderr,
            }

        commit_result = self._run_git(["commit", "-m", message])
        if not commit_result.ok:
            return {
                "status": "error",
                "step": "git commit",
                "error": commit_result.stderr,
                "stdout": commit_result.stdout,
            }

        return {
            "status": "committed",
            "message": message,
            "repo_path": str(self.repo_path),
            "branch": status.branch,
            "stdout": commit_result.stdout,
        }

    def push(self) -> dict:
        self.ensure_repo_exists()

        push_result = self._run_git(["push"])
        if not push_result.ok:
            return {
                "status": "error",
                "step": "git push",
                "error": push_result.stderr,
                "stdout": push_result.stdout,
            }

        return {
            "status": "pushed",
            "stdout": push_result.stdout,
        }

    def commit_and_maybe_push(self, message: str, push: bool = False) -> dict:
        commit_result = self.commit_all(message)

        if commit_result["status"] != "committed":
            return commit_result

        if push:
            push_result = self.push()
            commit_result["push"] = push_result

        return commit_result