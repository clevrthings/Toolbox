from __future__ import annotations

from pathlib import Path
import json
import re
import urllib.request

from textual.app import App
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, ListItem, ListView, Static

from toolbox.registry import ToolRegistry


class ToolScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", priority=True)]

    def __init__(self, tool_name: str, tool_description: str) -> None:
        super().__init__()
        self._tool_name = tool_name
        self._tool_description = tool_description

    def compose(self):
        yield Header()
        yield Static(f"[b]{self._tool_name}[/b]\n\n{self._tool_description}\n\n(placeholder view)", id="tool-view")
        yield Footer()


class ToolboxApp(App):
    TITLE = "Toolbox"
    SUB_TITLE = "Tools hub"
    CSS_PATH = "styles.tcss"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        super().__init__()
        self._tool_registry = registry or ToolRegistry.discover()
        self._filtered_tools = list(self._tool_registry.tools)
        self._categories: list[str] = []
        self._selected_category = "All"

    def compose(self):
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Static("Tools", id="sidebar-title")
                self.search_input = Input(placeholder="Search tools...", id="tool-search")
                yield self.search_input
                yield Static("Categories", id="category-title")
                self.category_list = ListView(id="category-list")
                yield self.category_list
                self.tool_list = ListView(id="tool-list")
                yield self.tool_list
            with Vertical(id="content"):
                yield Static("Select a tool to view details.", id="content-title")
                self.update_status = Static("", id="update-status")
                yield self.update_status
                self.tool_details = Static("", id="tool-details")
                yield self.tool_details
        yield Footer()

    def on_mount(self) -> None:
        self._populate_categories()
        self._refresh_tool_list("")
        self.tool_list.focus()
        self.run_worker(self._startup_update_check, thread=True)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tool-search":
            self._refresh_tool_list(event.value)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.index is None:
            return
        if event.list_view.id == "category-list":
            self._selected_category = self._categories[event.list_view.index]
            self._refresh_tool_list(self.search_input.value)
            self.tool_list.focus()
            return
        tool = self._filtered_tools[event.list_view.index]
        self.open_tool(tool)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.index is None:
            return
        if event.list_view.id == "category-list":
            self._selected_category = self._categories[event.list_view.index]
            self._refresh_tool_list(self.search_input.value)
            return
        self._show_tool(event.list_view.index)

    def _show_tool(self, index: int) -> None:
        tool = self._filtered_tools[index]
        hint = "Press Enter to open."
        if tool.screen_factory is None:
            hint = "No UI yet."
        self.tool_details.update(
            f"[b]{tool.name}[/b]\n\nCategory: {tool.category}\n\n{tool.description}\n\n{hint}"
        )

    def open_tool(self, tool) -> None:
        if tool.screen_factory is None:
            self.push_screen(ToolScreen(tool.name, tool.description))
            return
        self.push_screen(tool.screen_factory())

    def on_key(self, event) -> None:
        if event.key == "escape" and len(self.screen_stack) > 1:
            event.stop()
            self.pop_screen()

    def _refresh_tool_list(self, query: str) -> None:
        needle = query.strip().lower()
        category = self._selected_category
        self._filtered_tools = [
            tool
            for tool in self._tool_registry.tools
            if (needle in tool.name.lower() if needle else True)
            and (category == "All" or tool.category == category)
        ]
        self.tool_list.clear()
        for tool in self._filtered_tools:
            self.tool_list.append(ListItem(Static(tool.name)))
        if self._filtered_tools:
            self.tool_list.index = 0
            self._show_tool(0)
        else:
            self.tool_details.update("No tools match your search.")

    def _startup_update_check(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        local_version = self._read_local_version(repo_root)
        branch = self._read_update_branch(repo_root)
        remote_version = self._fetch_remote_version(branch)
        if local_version is None or remote_version is None:
            return
        if self._compare_versions(local_version, remote_version) < 0:
            self.call_from_thread(
                self.update_status.update,
                f"[yellow]Update available: {local_version} → {remote_version}.[/yellow]",
            )

    def _read_local_version(self, repo_root: Path) -> str | None:
        pyproject = repo_root / "pyproject.toml"
        if not pyproject.exists():
            return None
        text = pyproject.read_text(encoding="utf-8")
        match = re.search(r'^version\\s*=\\s*"(.*?)"\\s*$', text, re.MULTILINE)
        return match.group(1) if match else None

    def _fetch_remote_version(self, branch: str) -> str | None:
        url = f"https://raw.githubusercontent.com/clevrthings/Toolbox/{branch}/pyproject.toml"
        try:
            with urllib.request.urlopen(url, timeout=6) as response:
                text = response.read().decode("utf-8")
        except Exception:
            return None
        match = re.search(r'^version\\s*=\\s*"(.*?)"\\s*$', text, re.MULTILINE)
        return match.group(1) if match else None

    def _read_update_branch(self, repo_root: Path) -> str:
        config_path = repo_root / ".toolbox_config.json"
        if not config_path.exists():
            return "main"
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return "main"
        branch = data.get("update_branch")
        return branch if branch in {"main", "dev"} else "main"

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

    def _populate_categories(self) -> None:
        categories = sorted({tool.category for tool in self._tool_registry.tools})
        self._categories = ["All", *categories]
        self.category_list.clear()
        for category in self._categories:
            self.category_list.append(ListItem(Static(category)))
        if self._categories:
            self.category_list.index = 0
            self._selected_category = self._categories[0]


def run() -> None:
    ToolboxApp().run()


if __name__ == "__main__":
    run()
