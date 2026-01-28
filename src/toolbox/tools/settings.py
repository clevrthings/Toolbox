from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, RichLog, Static

from toolbox.tools.base import Tool


class SettingsScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", priority=True)]

    def __init__(self) -> None:
        super().__init__()
        self._repo_root = Path(__file__).resolve().parents[3]

    def compose(self):
        yield Header()
        with ScrollableContainer(id="settings-form"):
            yield Static("Settings", id="settings-title")
            self.version_label = Static("", id="settings-version")
            yield self.version_label
            with Horizontal(id="settings-actions"):
                yield Button("Check for updates", id="settings-check")
                yield Button("Update", id="settings-update", variant="success")
                yield Button("Clear Log", id="settings-clear")
            self.log_view = RichLog(id="settings-log", highlight=True)
            yield self.log_view
        yield Footer()

    def on_mount(self) -> None:
        version = self._read_version()
        self.version_label.update(f"Version: {version}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-clear":
            self.log_view.clear()
            return
        if event.button.id == "settings-check":
            self.run_worker(self._check_updates_worker, thread=True)
            return
        if event.button.id == "settings-update":
            self.run_worker(self._update_worker, thread=True)

    def _read_version(self) -> str:
        try:
            from importlib.metadata import PackageNotFoundError, version
        except Exception:
            PackageNotFoundError = Exception

            def version(_: str) -> str:
                raise PackageNotFoundError()

        try:
            return version("toolbox")
        except Exception:
            pyproject = self._repo_root / "pyproject.toml"
            if not pyproject.exists():
                return "dev"
            text = pyproject.read_text(encoding="utf-8")
            match = re.search(r'^version\\s*=\\s*"(.*?)"\\s*$', text, re.MULTILINE)
            return match.group(1) if match else "dev"

    def _check_updates_worker(self) -> None:
        if not self._git_ready():
            return
        self._log("Fetching remote...")
        fetch = self._run_command(["git", "fetch", "--prune"])
        if fetch.returncode != 0:
            self._log(fetch.stderr or fetch.stdout or "git fetch failed.")
            return
        upstream = self._get_upstream()
        if upstream is None:
            self._log("No upstream is configured for this branch.")
            return
        ahead, behind = self._ahead_behind(upstream)
        if ahead is None:
            return
        if behind == 0 and ahead == 0:
            self._log("Up to date.")
            return
        if behind > 0:
            self._log(f"Updates available: {behind} commit(s) behind {upstream}.")
        if ahead > 0:
            self._log(f"Local branch is {ahead} commit(s) ahead of {upstream}.")

    def _update_worker(self) -> None:
        if not self._git_ready():
            return
        if self._working_tree_dirty():
            self._log("Working tree has uncommitted changes. Commit or stash first.")
            return
        upstream = self._get_upstream()
        if upstream is None:
            self._log("No upstream is configured for this branch.")
            return
        self._log("Pulling latest changes...")
        pull = self._run_command(["git", "pull", "--ff-only"])
        if pull.returncode != 0:
            self._log(pull.stderr or pull.stdout or "git pull failed.")
            return
        self._log("Updating dependencies...")
        pip = self._run_command([sys.executable, "-m", "pip", "install", "-e", "."])
        if pip.returncode != 0:
            self._log(pip.stderr or pip.stdout or "Dependency update failed.")
            return
        version = self._read_version()
        self.version_label.update(f"Version: {version}")
        self._log("Update complete. Restart the app to apply changes.")

    def _git_ready(self) -> bool:
        if shutil.which("git") is None:
            self._log("git is not installed.")
            return False
        check = self._run_command(["git", "rev-parse", "--is-inside-work-tree"])
        if check.returncode != 0 or "true" not in check.stdout:
            self._log("This folder is not a git repository.")
            return False
        return True

    def _working_tree_dirty(self) -> bool:
        status = self._run_command(["git", "status", "--porcelain"])
        return bool(status.stdout.strip())

    def _get_upstream(self) -> str | None:
        upstream = self._run_command(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]
        )
        if upstream.returncode != 0:
            return None
        return upstream.stdout.strip()

    def _ahead_behind(self, upstream: str) -> tuple[int | None, int | None]:
        counts = self._run_command(
            ["git", "rev-list", "--left-right", "--count", f"HEAD...{upstream}"]
        )
        if counts.returncode != 0:
            self._log(counts.stderr or counts.stdout or "Failed to compare branches.")
            return None, None
        try:
            ahead_str, behind_str = counts.stdout.strip().split()
            return int(ahead_str), int(behind_str)
        except ValueError:
            self._log("Failed to parse update status.")
            return None, None

    def _run_command(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            cwd=str(self._repo_root),
            capture_output=True,
            text=True,
        )

    def _log(self, message: str) -> None:
        self.app.call_from_thread(self.log_view.write, message)


TOOL = Tool(
    name="Settings",
    description="Manage updates and view version information.",
    category="System",
    screen_factory=SettingsScreen,
)
