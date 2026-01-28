from __future__ import annotations

import threading
from dataclasses import dataclass

from pythonosc import dispatcher, osc_server, udp_client
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Static

from toolbox.tools.base import Tool


@dataclass
class _OscServerState:
    server: osc_server.ThreadingOSCUDPServer | None = None
    thread: threading.Thread | None = None


class OscToolScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", priority=True)]

    def __init__(self) -> None:
        super().__init__()
        self._server_state = _OscServerState()
        self._log_lines: list[str] = []

    def compose(self):
        yield Header()
        with ScrollableContainer(id="osc-form"):
            yield Static("OSC Sender/Receiver", id="osc-title")
            with Horizontal(id="osc-top"):
                with Vertical(id="osc-sender"):
                    yield Static("Sender", classes="section-title")
                    yield Label("Target host")
                    self.send_host = Input(value="127.0.0.1", id="osc-send-host")
                    yield self.send_host
                    yield Label("Target port")
                    self.send_port = Input(value="8000", id="osc-send-port")
                    yield self.send_port
                    yield Label("Address")
                    self.send_address = Input(value="/toolbox", id="osc-send-address")
                    yield self.send_address
                    yield Label("Arguments (comma separated)")
                    self.send_args = Input(placeholder="1, 2.5, hello", id="osc-send-args")
                    yield self.send_args
                    yield Button("Send", id="osc-send", variant="success")
                with Vertical(id="osc-receiver"):
                    yield Static("Receiver", classes="section-title")
                    yield Label("Listen host")
                    self.recv_host = Input(value="0.0.0.0", id="osc-recv-host")
                    yield self.recv_host
                    yield Label("Listen port")
                    self.recv_port = Input(value="8000", id="osc-recv-port")
                    yield self.recv_port
                    with Horizontal(id="osc-recv-actions"):
                        yield Button("Start", id="osc-recv-start", variant="success")
                        yield Button("Stop", id="osc-recv-stop")
            self.status = Static("", id="osc-status")
            yield self.status
            with Horizontal(id="osc-log-actions"):
                yield Button("Copy Log", id="osc-copy")
                yield Button("Clear Log", id="osc-clear")
            self.log_view = RichLog(id="osc-log", highlight=True)
            yield self.log_view
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "osc-send":
            self._send_message()
            return
        if event.button.id == "osc-copy":
            self._copy_log()
            return
        if event.button.id == "osc-clear":
            self._clear_log()
            return
        if event.button.id == "osc-recv-start":
            self._start_server()
            return
        if event.button.id == "osc-recv-stop":
            self._stop_server()
            return

    def _send_message(self) -> None:
        host = self.send_host.value.strip()
        port_raw = self.send_port.value.strip()
        address = self.send_address.value.strip() or "/toolbox"
        if not host or not port_raw:
            self.status.update("[red]Host and port are required.[/red]")
            return
        try:
            port = int(port_raw)
        except ValueError:
            self.status.update("[red]Port must be a number.[/red]")
            return

        args = self._parse_args(self.send_args.value)
        try:
            client = udp_client.SimpleUDPClient(host, port)
            client.send_message(address, args)
            self.status.update("[green]OSC message sent.[/green]")
        except Exception as exc:
            self.status.update(f"[red]Send failed: {exc}[/red]")

    def _start_server(self) -> None:
        if self._server_state.server is not None:
            self.status.update("[yellow]Receiver already running.[/yellow]")
            return
        host = self.recv_host.value.strip() or "0.0.0.0"
        port_raw = self.recv_port.value.strip()
        try:
            port = int(port_raw)
        except ValueError:
            self.status.update("[red]Port must be a number.[/red]")
            return

        osc_dispatcher = dispatcher.Dispatcher()
        osc_dispatcher.set_default_handler(self._handle_message)
        try:
            server = osc_server.ThreadingOSCUDPServer((host, port), osc_dispatcher)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._server_state = _OscServerState(server=server, thread=thread)
            self.status.update(f"[green]Listening on {host}:{port}[/green]")
        except Exception as exc:
            self.status.update(f"[red]Failed to start server: {exc}[/red]")

    def _stop_server(self) -> None:
        server = self._server_state.server
        if server is None:
            self.status.update("[yellow]Receiver is not running.[/yellow]")
            return
        server.shutdown()
        server.server_close()
        self._server_state = _OscServerState()
        self.status.update("[green]Receiver stopped.[/green]")

    def _handle_message(self, address, *args) -> None:
        self.app.call_from_thread(
            self._log, f"{address} {list(args)}"
        )

    def _log(self, text: str) -> None:
        self._log_lines.append(text)
        self.log_view.write(text)

    def _clear_log(self) -> None:
        self._log_lines.clear()
        self.log_view.clear()
        self.status.update("")

    def _copy_log(self) -> None:
        if not self._log_lines:
            self.status.update("[yellow]Log is empty.[/yellow]")
            return
        self.app.copy_to_clipboard("\n".join(self._log_lines))
        self.status.update("[green]Log copied to clipboard.[/green]")

    @staticmethod
    def _parse_args(raw: str):
        if not raw.strip():
            return []
        parts = [p.strip() for p in raw.split(",")]
        parsed = []
        for part in parts:
            if part == "":
                continue
            for caster in (int, float):
                try:
                    parsed.append(caster(part))
                    break
                except ValueError:
                    continue
            else:
                parsed.append(part)
        return parsed


TOOL = Tool(
    name="OSC Sender/Receiver",
    description="Send and receive OSC messages over UDP.",
    category="Network",
    screen_factory=OscToolScreen,
)
