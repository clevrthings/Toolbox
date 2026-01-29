from __future__ import annotations

import platform
import re
import shutil
import subprocess
from dataclasses import dataclass

from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, RichLog, Static

from toolbox.tools.base import Tool


@dataclass(frozen=True)
class InterfaceAddress:
    name: str
    address: str


class NetworkInfoScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", priority=True)]

    def compose(self):
        yield Header()
        with ScrollableContainer(id="netinfo-form"):
            yield Static("Network Interfaces", id="netinfo-title")
            yield Button("Refresh", id="netinfo-refresh", variant="success")
            self.log_view = RichLog(id="netinfo-log", highlight=True)
            yield self.log_view
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "netinfo-refresh":
            self._refresh()

    def _refresh(self) -> None:
        self.log_view.clear()
        addresses = self._collect_addresses()
        if not addresses:
            self.log_view.write("No IP addresses found.")
            return
        for item in addresses:
            self.log_view.write(f"{item.name}: {item.address}")

    def _collect_addresses(self) -> list[InterfaceAddress]:
        system = platform.system().lower()
        if system == "windows":
            return self._parse_ipconfig()
        if shutil.which("ip"):
            addresses = self._parse_ip_addr()
            if addresses:
                return addresses
        return self._parse_ifconfig()

    def _parse_ip_addr(self) -> list[InterfaceAddress]:
        result = subprocess.run(
            ["ip", "-o", "-4", "addr", "show"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        addresses: list[InterfaceAddress] = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            iface = parts[1]
            ip = parts[3].split("/")[0]
            addresses.append(InterfaceAddress(iface, ip))
        return addresses

    def _parse_ifconfig(self) -> list[InterfaceAddress]:
        result = subprocess.run(
            ["ifconfig"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        addresses: list[InterfaceAddress] = []
        current_iface: str | None = None
        for line in result.stdout.splitlines():
            if line and not line.startswith("\t") and not line.startswith(" "):
                current_iface = line.split(":")[0]
                continue
            if current_iface is None:
                continue
            line = line.strip()
            if line.startswith("inet "):
                match = re.search(r"inet\s+([0-9.]+)", line)
                if match:
                    addresses.append(InterfaceAddress(current_iface, match.group(1)))
        return addresses

    def _parse_ipconfig(self) -> list[InterfaceAddress]:
        result = subprocess.run(
            ["ipconfig"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        addresses: list[InterfaceAddress] = []
        current_iface: str | None = None
        for line in result.stdout.splitlines():
            if line and not line.startswith(" "):
                current_iface = line.strip().rstrip(":")
                continue
            if "IPv4 Address" in line:
                match = re.search(r"IPv4 Address[^\d]*([\d.]+)", line)
                if match and current_iface:
                    addresses.append(InterfaceAddress(current_iface, match.group(1)))
        return addresses


TOOL = Tool(
    name="Network Info",
    description="Show IP addresses for connected network interfaces.",
    category="Network",
    screen_factory=NetworkInfoScreen,
)
