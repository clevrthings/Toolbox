from __future__ import annotations

import socket
import socketserver
import threading
from dataclasses import dataclass

from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Static

from toolbox.tools.base import Tool


@dataclass
class _TcpServerState:
    server: socketserver.ThreadingTCPServer | None = None
    thread: threading.Thread | None = None


class _TcpHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server  # type: ignore[assignment]
        app = getattr(server, "app", None)
        if app is None:
            return
        data = self.request.recv(4096)
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = repr(data)
        app.call_from_thread(
            getattr(app.screen, "_log", lambda *_: None),
            f"{self.client_address[0]}:{self.client_address[1]} -> {text}",
        )


class TcpToolScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", priority=True)]

    def __init__(self) -> None:
        super().__init__()
        self._server_state = _TcpServerState()
        self._log_lines: list[str] = []

    def compose(self):
        yield Header()
        with ScrollableContainer(id="tcp-form"):
            yield Static("TCP Sender/Receiver", id="tcp-title")
            with Horizontal(id="tcp-top"):
                with Vertical(id="tcp-sender"):
                    yield Static("Sender", classes="section-title")
                    yield Label("Target host")
                    self.send_host = Input(value="127.0.0.1", id="tcp-send-host")
                    yield self.send_host
                    yield Label("Target port")
                    self.send_port = Input(value="9000", id="tcp-send-port")
                    yield self.send_port
                    yield Label("Message")
                    self.send_message = Input(placeholder="Hello TCP", id="tcp-send-message")
                    yield self.send_message
                    yield Button("Send", id="tcp-send", variant="success")
                with Vertical(id="tcp-receiver"):
                    yield Static("Receiver", classes="section-title")
                    yield Label("Listen host")
                    self.recv_host = Input(value="0.0.0.0", id="tcp-recv-host")
                    yield self.recv_host
                    yield Label("Listen port")
                    self.recv_port = Input(value="9000", id="tcp-recv-port")
                    yield self.recv_port
                    with Horizontal(id="tcp-recv-actions"):
                        yield Button("Start", id="tcp-recv-start", variant="success")
                        yield Button("Stop", id="tcp-recv-stop")
            self.status = Static("", id="tcp-status")
            yield self.status
            with Horizontal(id="tcp-log-actions"):
                yield Button("Copy Log", id="tcp-copy")
                yield Button("Clear Log", id="tcp-clear")
            self.log_view = RichLog(id="tcp-log", highlight=True)
            yield self.log_view
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "tcp-send":
            self._send_message()
            return
        if event.button.id == "tcp-copy":
            self._copy_log()
            return
        if event.button.id == "tcp-clear":
            self._clear_log()
            return
        if event.button.id == "tcp-recv-start":
            self._start_server()
            return
        if event.button.id == "tcp-recv-stop":
            self._stop_server()
            return

    def _send_message(self) -> None:
        host = self.send_host.value.strip()
        port_raw = self.send_port.value.strip()
        message = self.send_message.value
        if not host or not port_raw:
            self.status.update("[red]Host and port are required.[/red]")
            return
        try:
            port = int(port_raw)
        except ValueError:
            self.status.update("[red]Port must be a number.[/red]")
            return
        try:
            with socket.create_connection((host, port), timeout=3) as sock:
                sock.sendall(message.encode("utf-8"))
            self.status.update("[green]Message sent.[/green]")
        except Exception as exc:
            self.status.update(f"[red]Send failed: {exc}[/red]")

    def _start_server(self) -> None:
        if self._server_state.server is not None:
            self.status.update("[yellow]Server already running.[/yellow]")
            return
        host = self.recv_host.value.strip() or "0.0.0.0"
        port_raw = self.recv_port.value.strip()
        try:
            port = int(port_raw)
        except ValueError:
            self.status.update("[red]Port must be a number.[/red]")
            return
        try:
            server = socketserver.ThreadingTCPServer((host, port), _TcpHandler)
            server.daemon_threads = True
            server.app = self.app  # type: ignore[attr-defined]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._server_state = _TcpServerState(server=server, thread=thread)
            self.status.update(f"[green]Listening on {host}:{port}[/green]")
        except Exception as exc:
            self.status.update(f"[red]Failed to start server: {exc}[/red]")

    def _stop_server(self) -> None:
        server = self._server_state.server
        if server is None:
            self.status.update("[yellow]Server is not running.[/yellow]")
            return
        server.shutdown()
        server.server_close()
        self._server_state = _TcpServerState()
        self.status.update("[green]Server stopped.[/green]")

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


TOOL = Tool(
    name="TCP Sender/Receiver",
    description="Send TCP messages and receive incoming TCP payloads.",
    category="Network",
    screen_factory=TcpToolScreen,
)
