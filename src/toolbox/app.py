from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

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
        if shutil.which("git") is None:
            return
        repo_root = Path(__file__).resolve().parents[2]
        check = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if check.returncode != 0 or "true" not in check.stdout:
            return
        upstream = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if upstream.returncode != 0:
            return
        subprocess.run(
            ["git", "fetch", "--prune"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        counts = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", f"HEAD...{upstream.stdout.strip()}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if counts.returncode != 0:
            return
        try:
            _ahead, behind = counts.stdout.strip().split()
        except ValueError:
            return
        try:
            behind_count = int(behind)
        except ValueError:
            return
        if behind_count > 0:
            self.call_from_thread(
                self.update_status.update,
                f"[yellow]Update available: {behind_count} commit(s) behind.[/yellow]",
            )

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
