from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Select,
    Static,
)

from toolbox.tools.base import Tool


class YouTubeDownloaderScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", priority=True)]

    _VIDEO_QUALITY = [
        ("Best", "best"),
        ("1080p", "1080"),
        ("720p", "720"),
        ("480p", "480"),
        ("360p", "360"),
        ("Worst", "worst"),
    ]
    _AUDIO_QUALITY = [
        ("Best Audio", "bestaudio"),
        ("Worst Audio", "worstaudio"),
    ]
    def compose(self):
        yield Header()
        with ScrollableContainer(id="yt-form"):
            yield Static("YouTube Downloader", id="yt-title")
            yield Label("Video URL")
            self.url_input = Input(placeholder="https://www.youtube.com/watch?v=...", id="yt-url")
            yield self.url_input
            yield Label("Mode")
            self.mode_select = Select(
                [("Video", "video"), ("Audio Only", "audio")],
                value="video",
                id="yt-mode",
            )
            yield self.mode_select
            yield Label("Quality")
            self.quality_select = Select(
                self._VIDEO_QUALITY,
                value="best",
                id="yt-quality",
            )
            yield self.quality_select
            yield Label("Output folder (optional)")
            with Horizontal(id="yt-output-row"):
                self.output_input = Input(
                    placeholder=str(self._default_output_dir()),
                    id="yt-output",
                )
                yield self.output_input
                yield Button("Browse", id="yt-output-browse")
            with Horizontal(id="yt-actions"):
                yield Button("Download", id="yt-download", variant="success")
                yield Button("Copy Log", id="yt-copy")
                yield Button("Clear Log", id="yt-clear")
            self.status = Static("", id="yt-status")
            yield self.status
            self.log_view = RichLog(id="yt-log", highlight=True)
            yield self.log_view
        yield Footer()

    def __init__(self) -> None:
        super().__init__()
        self._log_lines: list[str] = []

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "yt-mode":
            if event.value == "audio":
                self.quality_select.set_options(self._AUDIO_QUALITY)
                self.quality_select.value = "bestaudio"
            else:
                self.quality_select.set_options(self._VIDEO_QUALITY)
                self.quality_select.value = "best"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yt-clear":
            self._clear_log()
            return
        if event.button.id == "yt-copy":
            self._copy_log()
            return
        if event.button.id == "yt-output-browse":
            self._open_picker()
            return
        if event.button.id == "yt-download":
            self._start_download()

    def _start_download(self) -> None:
        if importlib.util.find_spec("yt_dlp") is None:
            self.status.update("[red]Missing dependency: yt-dlp. Run 'pip install -e .'[/red]")
            return
        if self.mode_select.value == "audio" and shutil.which("ffmpeg") is None:
            self.status.update("[red]Missing dependency: ffmpeg (required for audio).[/red]")
            return
        url = self.url_input.value.strip()
        if not url:
            self.status.update("[red]URL is required.[/red]")
            return
        output_dir = self.output_input.value.strip() or str(self._default_output_dir())
        payload = self._build_options(url, output_dir)
        self._clear_log()
        self.status.update("Downloading...")
        self.run_worker(lambda: self._worker(payload), thread=True)

    def _build_options(self, url: str, output_dir: str) -> dict:
        mode = self.mode_select.value or "video"
        quality = self.quality_select.value or "best"
        out_path = Path(output_dir).expanduser()
        options: dict = {
            "noplaylist": True,
            "outtmpl": {"default": str(out_path / "%(title)s.%(ext)s")},
            "merge_output_format": "mp4",
            "progress_hooks": [self._progress_hook],
            "quiet": True,
            "no_warnings": True,
        }

        if mode == "audio":
            fmt = "bestaudio" if quality == "bestaudio" else "worstaudio"
            options["format"] = fmt
            options["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                }
            ]
            return {"url": url, "options": options}

        if quality in {"best", "worst"}:
            options["format"] = (
                "bestvideo+bestaudio/best"
                if quality == "best"
                else "worstvideo+worstaudio/worst"
            )
            return {"url": url, "options": options}

        height = quality
        options["format"] = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        return {"url": url, "options": options}

    def _worker(self, payload: dict) -> None:
        try:
            import yt_dlp
        except Exception as exc:
            self.app.call_from_thread(self.status.update, f"[red]yt-dlp error: {exc}[/red]")
            return

        url = payload["url"]
        options = payload["options"]
        options["logger"] = _YtLogger(self)

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
        except Exception as exc:
            self.app.call_from_thread(self.status.update, f"[red]Download failed: {exc}[/red]")
            return

        self.app.call_from_thread(self.status.update, "[green]Download completed.[/green]")

    def _default_output_dir(self) -> Path:
        return Path.home() / "Desktop"

    def _open_picker(self) -> None:
        current = self.output_input.value.strip()
        start_path = Path(current).expanduser() if current else self._default_output_dir()
        if start_path.exists() and start_path.is_file():
            start_path = start_path.parent

        def _apply(path: Path) -> None:
            self.output_input.value = str(path)

        self.app.push_screen(
            PathPickerScreen(
                on_selected=_apply,
                start_path=start_path,
                title="Select output folder",
            )
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

    def _progress_hook(self, data: dict) -> None:
        status = data.get("status")
        if status == "downloading":
            percent = data.get("_percent_str", "").strip()
            speed = data.get("_speed_str", "").strip()
            eta = data.get("_eta_str", "").strip()
            self.app.call_from_thread(
                self._log, f"Downloading {percent} {speed} ETA {eta}".strip()
            )
        elif status == "finished":
            filename = data.get("filename", "download")
            self.app.call_from_thread(self._log, f"Finished: {filename}")


class _YtLogger:
    def __init__(self, screen: YouTubeDownloaderScreen) -> None:
        self._screen = screen

    def debug(self, msg: str) -> None:
        self._screen.app.call_from_thread(self._screen._log, msg)

    def info(self, msg: str) -> None:
        self._screen.app.call_from_thread(self._screen._log, msg)

    def warning(self, msg: str) -> None:
        self._screen.app.call_from_thread(self._screen._log, f"WARNING: {msg}")

    def error(self, msg: str) -> None:
        self._screen.app.call_from_thread(self._screen._log, f"ERROR: {msg}")


class PathPickerScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Cancel", priority=True)]

    def __init__(
        self,
        *,
        on_selected,
        start_path: Path | None = None,
        title: str = "Select folder",
    ) -> None:
        super().__init__()
        self._on_selected = on_selected
        self._start_path = start_path or Path.home()
        self._title = title

    def compose(self):
        yield Header()
        yield Static(self._title, id="yt-picker-title")
        yield FilteredDirectoryTree(self._start_path, id="yt-picker-tree")
        yield Footer()

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self._on_selected(event.path)
        self.app.pop_screen()


class FilteredDirectoryTree(DirectoryTree):
    def filter_paths(self, paths):
        return [path for path in paths if not path.name.startswith(".")]


TOOL = Tool(
    name="YouTube Downloader",
    description="Download YouTube videos or audio with selectable quality.",
    category="Video",
    screen_factory=YouTubeDownloaderScreen,
)
