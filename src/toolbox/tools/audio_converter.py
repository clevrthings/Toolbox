from __future__ import annotations

from pathlib import Path
import shutil
import importlib.util
import subprocess
import sys
from typing import Callable

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
    ProgressBar,
    Select,
    Static,
)

from toolbox.tools.base import Tool


class FilteredDirectoryTree(DirectoryTree):
    def filter_paths(self, paths):
        return [path for path in paths if not path.name.startswith(".")]


class PathPickerScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Cancel", priority=True)]

    def __init__(
        self,
        *,
        mode: str,
        on_selected: Callable[[Path], None],
        start_path: Path | None = None,
        title: str = "Select path",
    ) -> None:
        super().__init__()
        self._mode = mode
        self._on_selected = on_selected
        self._start_path = start_path or Path.home()
        self._title = title

    def compose(self):
        yield Header()
        yield Static(self._title, id="path-picker-title")
        yield FilteredDirectoryTree(self._start_path, id="path-picker-tree")
        yield Footer()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        if self._mode not in {"file", "any"}:
            return
        self._finish(event.path)

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        if self._mode not in {"directory", "any"}:
            return
        self._finish(event.path)

    def _finish(self, path: Path) -> None:
        self._on_selected(path)
        self.app.pop_screen()


class AudioConverterScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", priority=True)]

    _FORMATS = [
        ("MP3", "mp3"),
        ("WAV", "wav"),
        ("FLAC", "flac"),
        ("AIFF", "aiff"),
        ("OGG", "ogg"),
        ("OPUS", "opus"),
        ("M4A (AAC)", "m4a"),
    ]
    _LOSSY_FORMATS = {"mp3", "ogg", "opus", "m4a"}
    _INPUT_EXTS = {
        ".wav",
        ".mp3",
        ".flac",
        ".aiff",
        ".aif",
        ".ogg",
        ".opus",
        ".m4a",
        ".aac",
    }

    def compose(self):
        yield Header()
        with ScrollableContainer(id="audio-form"):
            yield Static("Audio Converter", id="audio-title")
            yield Label("Source file or folder")
            with Horizontal(id="audio-source-row"):
                self.source_input = Input(
                    placeholder="path/to/file or /path/to/folder",
                    id="audio-source",
                )
                yield self.source_input
                yield Button("Browse", id="audio-source-browse")
            yield Label("Target folder (optional)")
            with Horizontal(id="audio-target-row"):
                self.target_input = Input(
                    placeholder="path/to/output (default: format subfolder)",
                    id="audio-target",
                )
                yield self.target_input
                yield Button("Browse", id="audio-target-browse")
            yield Label("Format")
            self.format_select = Select(
                self._FORMATS,
                value="mp3",
                id="audio-format",
            )
            yield self.format_select
            self.bitrate_label = Label("Bitrate (lossy)")
            yield self.bitrate_label
            self.bitrate_select = Select(
                [("320k", "320k"), ("256k", "256k"), ("192k", "192k"), ("128k", "128k"), ("96k", "96k")],
                value="192k",
                id="audio-bitrate",
            )
            yield self.bitrate_select
            yield Label("Sample rate (optional)")
            self.sample_rate_input = Input(
                placeholder="e.g. 44100",
                id="audio-sample-rate",
            )
            yield self.sample_rate_input
            with Horizontal(id="audio-actions"):
                yield Button("Start", id="audio-start", variant="success")
                yield Button("Clear", id="audio-clear")
            self.status = Static("", id="audio-status")
            yield self.status
            self.progress = ProgressBar(id="audio-progress")
            yield self.progress
        yield Footer()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop()
            self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "audio-clear":
            self.source_input.value = ""
            self.target_input.value = ""
            self.sample_rate_input.value = ""
            self.format_select.value = "mp3"
            self.bitrate_select.value = "192k"
            self._refresh_format_options()
            self.status.update("")
            self.progress.update(progress=0, total=0)
            return
        if event.button.id == "audio-source-browse":
            self._open_picker(mode="any", target="source")
            return
        if event.button.id == "audio-target-browse":
            self._open_picker(mode="directory", target="target")
            return
        if event.button.id == "audio-start":
            self._start_conversion()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "audio-format":
            self._refresh_format_options()

    def on_mount(self) -> None:
        self._refresh_format_options()

    def _start_conversion(self) -> None:
        if not self._pydub_installed():
            self._prompt_pydub_install()
            return
        if not self._audioop_available():
            self._prompt_audioop_install()
            return
        if shutil.which("ffmpeg") is None:
            self._prompt_ffmpeg_install()
            return
        try:
            source, target = self._resolve_paths()
        except ValueError as exc:
            self.status.update(f"[red]{exc}[/red]")
            return

        fmt = self.format_select.value or "mp3"
        bitrate = self.bitrate_select.value or "192k"
        sample_rate, ok = self._parse_sample_rate()
        if not ok:
            return
        self.status.update("Starting conversion...")
        self.progress.update(progress=0, total=0)
        self.run_worker(
            lambda: self._convert_worker(source, target, fmt, bitrate, sample_rate),
            thread=True,
        )

    def _pydub_installed(self) -> bool:
        return importlib.util.find_spec("pydub") is not None

    def _audioop_available(self) -> bool:
        return (
            importlib.util.find_spec("audioop") is not None
            or importlib.util.find_spec("pyaudioop") is not None
        )

    def _prompt_pydub_install(self) -> None:
        self.status.update(
            "[yellow]pydub is required. Select Install to add it.[/yellow]"
        )

        def _start_install() -> None:
            self.status.update("Installing pydub...")
            self.run_worker(self._install_pydub_worker, thread=True)

        self.app.push_screen(PydubPromptScreen(on_install=_start_install))

    def _install_pydub_worker(self) -> None:
        root = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(root)],
            capture_output=True,
            text=True,
            cwd=str(root),
        )
        if result.returncode == 0:
            self.app.call_from_thread(
                self.status.update,
                "[green]pydub installed. Press Start to run conversion.[/green]",
            )
            return

        message = result.stderr.strip() or result.stdout.strip() or "Installation failed."
        self.app.call_from_thread(self.status.update, f"[red]{message}[/red]")

    def _prompt_audioop_install(self) -> None:
        self.status.update(
            "[yellow]audioop is required for pydub on Python 3.14. Select Install to add it.[/yellow]"
        )

        def _start_install() -> None:
            self.status.update("Installing audioop-lts...")
            self.run_worker(self._install_audioop_worker, thread=True)

        self.app.push_screen(AudioopPromptScreen(on_install=_start_install))

    def _install_audioop_worker(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "audioop-lts"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            self.app.call_from_thread(
                self.status.update,
                "[green]audioop-lts installed. Press Start to run conversion.[/green]",
            )
            return

        message = result.stderr.strip() or result.stdout.strip() or "Installation failed."
        self.app.call_from_thread(self.status.update, f"[red]{message}[/red]")

    def _prompt_ffmpeg_install(self) -> None:
        self.status.update(
            "[yellow]ffmpeg is required. Select Install to download it.[/yellow]"
        )

        def _start_install() -> None:
            self.status.update("Installing ffmpeg...")
            self.run_worker(self._install_ffmpeg_worker, thread=True)

        self.app.push_screen(FFmpegPromptScreen(on_install=_start_install))

    def _install_ffmpeg_worker(self) -> None:
        script = Path(__file__).resolve().parents[3] / "scripts" / "install_ffmpeg_macos.sh"
        if not script.exists():
            self.app.call_from_thread(
                self.status.update,
                "[red]Installer script not found: scripts/install_ffmpeg_macos.sh[/red]",
            )
            return

        result = subprocess.run(
            ["bash", str(script)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            self.app.call_from_thread(
                self.status.update,
                "[green]ffmpeg installed. Press Start to run conversion.[/green]",
            )
            return

        message = result.stderr.strip() or result.stdout.strip() or "Installation failed."
        self.app.call_from_thread(self.status.update, f"[red]{message}[/red]")

    def _open_picker(self, *, mode: str, target: str) -> None:
        current = self.source_input.value if target == "source" else self.target_input.value
        if current:
            candidate = Path(current).expanduser()
            if candidate.exists():
                start_path = candidate if candidate.is_dir() else candidate.parent
            else:
                start_path = candidate.parent
        else:
            start_path = Path.home()

        def _apply(path: Path) -> None:
            if target == "source":
                self.source_input.value = str(path)
            else:
                self.target_input.value = str(path)

        title = "Select file or folder" if mode == "any" else "Select folder"
        self.app.push_screen(
            PathPickerScreen(
                mode=mode,
                on_selected=_apply,
                start_path=start_path,
                title=title,
            )
        )

    def _resolve_paths(self) -> tuple[Path, Path]:
        source_raw = self.source_input.value.strip()
        target_raw = self.target_input.value.strip()

        if not source_raw:
            raise ValueError("Source path is required.")

        source = Path(source_raw).expanduser()
        if not source.exists():
            raise ValueError("Source path does not exist.")

        if target_raw:
            target = Path(target_raw).expanduser()
            if target.exists() and target.is_file():
                raise ValueError("Target path must be a folder.")
        else:
            base = source if source.is_dir() else source.parent
            output_fmt = self.format_select.value or "mp3"
            target = base / output_fmt
        return source, target

    def _convert_worker(
        self,
        source: Path,
        target: Path,
        output_fmt: str,
        bitrate: str,
        sample_rate: int | None,
    ) -> None:
        if shutil.which("ffmpeg") is None:
            self.app.call_from_thread(
                self.status.update,
                "[red]ffmpeg is still missing. Install it and try again.[/red]",
            )
            return
        try:
            from pydub import AudioSegment
        except ImportError:
            self.app.call_from_thread(
                self.status.update,
                "[red]pydub failed to import. Install audioop-lts and try again.[/red]",
            )
            return

        files = self._collect_files(source)
        if not files:
            self.app.call_from_thread(
                self.status.update,
                "[red]No audio files found in the source.[/red]",
            )
            return

        target.mkdir(parents=True, exist_ok=True)
        total = len(files)
        self.app.call_from_thread(self.progress.update, progress=0, total=total)

        export_format = self._export_format(output_fmt)
        export_args = self._export_args(output_fmt, bitrate)

        errors: list[str] = []
        for index, wav_file in enumerate(files, start=1):
            try:
                out_file = target / f"{wav_file.stem}.{output_fmt}"
                audio = AudioSegment.from_file(wav_file)
                if sample_rate is not None:
                    audio = audio.set_frame_rate(sample_rate)
                audio.export(out_file, format=export_format, **export_args)
                self.app.call_from_thread(
                    self.status.update,
                    f"Converted {wav_file.name}",
                )
            except Exception as exc:
                errors.append(f"{wav_file.name}: {exc}")
            self.app.call_from_thread(self.progress.update, progress=index, total=total)

        if errors:
            self.app.call_from_thread(
                self.status.update,
                f"[yellow]Done with {len(errors)} errors. Check output folder.[/yellow]",
            )
        else:
            self.app.call_from_thread(
                self.status.update,
                "[green]Conversion completed.[/green]",
            )

    def _collect_files(self, source: Path) -> list[Path]:
        if source.is_file() and source.suffix.lower() in self._INPUT_EXTS:
            return [source]
        if source.is_dir():
            files: list[Path] = []
            for ext in sorted(self._INPUT_EXTS):
                files.extend(source.glob(f"*{ext}"))
            return sorted(set(files))
        return []

    def _export_format(self, output_fmt: str) -> str:
        if output_fmt == "m4a":
            return "ipod"
        return output_fmt

    def _export_args(self, output_fmt: str, bitrate: str) -> dict:
        if output_fmt in self._LOSSY_FORMATS:
            return {"parameters": ["-b:a", bitrate]}
        return {}

    def _parse_sample_rate(self) -> tuple[int | None, bool]:
        raw = self.sample_rate_input.value.strip()
        if not raw:
            return None, True
        try:
            rate = int(raw)
        except ValueError:
            self.status.update("[red]Sample rate must be a number.[/red]")
            return None, False
        if rate <= 0:
            self.status.update("[red]Sample rate must be positive.[/red]")
            return None, False
        return rate, True

    def _refresh_format_options(self) -> None:
        output_fmt = self.format_select.value or "mp3"
        is_lossy = output_fmt in self._LOSSY_FORMATS
        self.bitrate_label.display = is_lossy
        self.bitrate_select.display = is_lossy


class FFmpegPromptScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Cancel", priority=True)]

    def __init__(self, on_install: Callable[[], None]) -> None:
        super().__init__()
        self._on_install = on_install

    def compose(self):
        yield Header()
        yield Static(
            "ffmpeg is required to convert audio.\n\nInstall it now?",
            id="ffmpeg-prompt",
        )
        with Horizontal(id="ffmpeg-actions"):
            yield Button("Install", id="ffmpeg-install", variant="success")
            yield Button("Cancel", id="ffmpeg-cancel")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ffmpeg-install":
            self.app.pop_screen()
            self._on_install()
            return
        if event.button.id == "ffmpeg-cancel":
            self.app.pop_screen()


class PydubPromptScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Cancel", priority=True)]

    def __init__(self, on_install: Callable[[], None]) -> None:
        super().__init__()
        self._on_install = on_install

    def compose(self):
        yield Header()
        yield Static(
            "pydub is required to convert audio.\n\nInstall it now?",
            id="pydub-prompt",
        )
        with Horizontal(id="pydub-actions"):
            yield Button("Install", id="pydub-install", variant="success")
            yield Button("Cancel", id="pydub-cancel")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "pydub-install":
            self.app.pop_screen()
            self._on_install()
            return
        if event.button.id == "pydub-cancel":
            self.app.pop_screen()


class AudioopPromptScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Cancel", priority=True)]

    def __init__(self, on_install: Callable[[], None]) -> None:
        super().__init__()
        self._on_install = on_install

    def compose(self):
        yield Header()
        yield Static(
            "audioop is required for pydub on Python 3.14.\n\nInstall it now?",
            id="audioop-prompt",
        )
        with Horizontal(id="audioop-actions"):
            yield Button("Install", id="audioop-install", variant="success")
            yield Button("Cancel", id="audioop-cancel")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "audioop-install":
            self.app.pop_screen()
            self._on_install()
            return
        if event.button.id == "audioop-cancel":
            self.app.pop_screen()


TOOL = Tool(
    name="Audio Converter",
    description="Batch convert audio files between common formats.",
    category="Audio",
    screen_factory=AudioConverterScreen,
)
