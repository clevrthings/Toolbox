from __future__ import annotations

import json
import re
import tomllib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, RichLog, Select, Static

from toolbox.tools.base import Tool


class SettingsScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", priority=True)]

    def __init__(self) -> None:
        super().__init__()
        self._repo_root = Path(__file__).resolve().parents[3]
        self._config_path = self._repo_root / ".toolbox_config.json"

    def compose(self):
        yield Header()
        with ScrollableContainer(id="settings-form"):
            yield Static("Settings", id="settings-title")
            self.version_label = Static("", id="settings-version")
            yield self.version_label
            yield Label("Update channel")
            self.branch_select = Select(
                [("Main", "main"), ("Dev", "dev")],
                value="main",
                id="settings-branch",
            )
            yield self.branch_select
            with Horizontal(id="settings-actions"):
                yield Button("Check for updates", id="settings-check")
                yield Button("Update", id="settings-update", variant="success")
                yield Button("Copy Log", id="settings-copy")
                yield Button("Clear Log", id="settings-clear")
            self.log_view = RichLog(id="settings-log", highlight=True)
            yield self.log_view
        yield Footer()

    def on_mount(self) -> None:
        version = self._read_version()
        self.version_label.update(f"Version: {version}")
        self._load_branch_setting()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "settings-branch":
            self._save_branch_setting()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-clear":
            self.log_view.clear()
            return
        if event.button.id == "settings-copy":
            text = "\n".join(
                self._line_to_text(line) for line in self.log_view.lines
            )
            if not text.strip():
                self._log("Log is empty.")
                return
            self.app.copy_to_clipboard(text)
            self._log("Log copied to clipboard.")
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
        branch = self.branch_select.value or "main"
        local_version = self._read_version()
        remote_version = self._fetch_remote_version(branch)
        if remote_version is None:
            self._log(f"Failed to fetch remote version for branch '{branch}'.")
            return
        if self._compare_versions(local_version, remote_version) >= 0:
            self._log(f"Up to date. ({local_version})")
            return
        self._log(f"Update available: {local_version} -> {remote_version}")

    def _update_worker(self) -> None:
        if shutil.which("python") is None and shutil.which("python3") is None:
            self._log("Python is not available.")
            return
        branch = self.branch_select.value or "main"
        if self._has_uncommitted_changes():
            self._log("Local changes detected. Back up or commit before updating.")
            return
        if not self._download_and_replace(branch):
            return
        self._log("Updating dependencies...")
        pip = self._run_command([sys.executable, "-m", "pip", "install", "-e", "."])
        if pip.returncode != 0:
            self._log(pip.stderr or pip.stdout or "Dependency update failed.")
            return
        version = self._read_version()
        self.version_label.update(f"Version: {version}")
        self._log("Update complete. Restart the app to apply changes.")

    def _has_uncommitted_changes(self) -> bool:
        git_dir = self._repo_root / ".git"
        if not git_dir.exists():
            return False
        if shutil.which("git") is None:
            return False
        status = self._run_command(["git", "status", "--porcelain"])
        return bool(status.stdout.strip())

    def _fetch_remote_version(self, branch: str) -> str | None:
        url = f"https://raw.githubusercontent.com/clevrthings/Toolbox/{branch}/pyproject.toml"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Toolbox-Updater"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                text = response.read().decode("utf-8")
                status = getattr(response, "status", 200)
        except Exception as exc:
            self._log(f"Fetch failed: {exc}")
            return None
        if status != 200:
            self._log(f"Fetch failed: HTTP {status}")
            return None
        return self._parse_version_toml(text, url)

    def _download_and_replace(self, branch: str) -> bool:
        url = f"https://github.com/clevrthings/Toolbox/archive/refs/heads/{branch}.zip"
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = Path(tmpdir) / "update.zip"
                with urllib.request.urlopen(url, timeout=20) as response:
                    zip_path.write_bytes(response.read())
                extract_dir = Path(tmpdir) / "extract"
                extract_dir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(zip_path) as archive:
                    archive.extractall(extract_dir)
                root_dirs = [p for p in extract_dir.iterdir() if p.is_dir()]
                if not root_dirs:
                    self._log("Update failed: no files in archive.")
                    return False
                source_root = root_dirs[0]
                self._replace_tree(source_root, self._repo_root)
                return True
        except Exception as exc:
            self._log(f"Update failed: {exc}")
            return False

    def _replace_tree(self, source: Path, dest: Path) -> None:
        keep = {".git", ".venv"}
        for item in dest.iterdir():
            if item.name in keep:
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        for item in source.iterdir():
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)

    def _run_command(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            cwd=str(self._repo_root),
            capture_output=True,
            text=True,
        )

    def _log(self, message: str) -> None:
        try:
            self.log_view.write(message)
        except Exception:
            self.app.call_from_thread(self.log_view.write, message)

    def _compare_versions(self, local: str, remote: str) -> int:
        def _parse(value: str) -> tuple[int, ...]:
            parts = re.split(r"[.+-]", value)
            nums: list[int] = []
            for part in parts:
                if part.isdigit():
                    nums.append(int(part))
                else:
                    break
            return tuple(nums)

        local_tuple = _parse(local)
        remote_tuple = _parse(remote)
        if local_tuple == remote_tuple:
            return 0
        if local_tuple > remote_tuple:
            return 1
        return -1

    def _parse_version_toml(self, text: str, url: str) -> str | None:
        try:
            data = tomllib.loads(text)
        except Exception as exc:
            self._log(f"Failed to parse pyproject.toml: {exc}")
            return None
        project = data.get("project") if isinstance(data, dict) else None
        version = project.get("version") if isinstance(project, dict) else None
        if not version:
            self._log(f"Version not found in remote pyproject.toml ({url}).")
            return None
        return str(version)

    def _line_to_text(self, line) -> str:
        if hasattr(line, "segments"):
            return "".join(getattr(segment, "text", "") for segment in line.segments)
        if hasattr(line, "plain"):
            return line.plain
        if hasattr(line, "text"):
            text = line.text
            return getattr(text, "plain", str(text))
        return str(line)

    def _load_branch_setting(self) -> None:
        if not self._config_path.exists():
            return
        try:
            data = json.loads(self._config_path.read_text(encoding="utf-8"))
        except Exception:
            return
        branch = data.get("update_branch")
        if branch in {"main", "dev"}:
            self.branch_select.value = branch

    def _save_branch_setting(self) -> None:
        branch = self.branch_select.value or "main"
        data = {"update_branch": branch}
        try:
            self._config_path.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            self._log("Failed to save update channel.")


TOOL = Tool(
    name="Settings",
    description="Manage updates and view version information.",
    category="System",
    screen_factory=SettingsScreen,
)
