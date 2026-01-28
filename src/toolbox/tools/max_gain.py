from __future__ import annotations

from pathlib import Path
import importlib.util
import shutil

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
    RichLog,
    Static,
    Switch,
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
        on_selected,
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
        yield Static(self._title, id="maxgain-picker-title")
        yield FilteredDirectoryTree(self._start_path, id="maxgain-picker-tree")
        yield Footer()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        if self._mode not in {"file", "any"}:
            return
        self._on_selected(event.path)
        self.app.pop_screen()

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        if self._mode not in {"directory", "any"}:
            return
        self._on_selected(event.path)
        self.app.pop_screen()


class MaxGainScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", priority=True)]
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

    def __init__(self) -> None:
        super().__init__()
        self._log_lines: list[str] = []

    def compose(self):
        yield Header()
        with ScrollableContainer(id="maxgain-form"):
            yield Static("MaxGain", id="maxgain-title")
            yield Label("Source audio file or folder")
            with Horizontal(id="maxgain-source-row"):
                self.source_input = Input(
                    placeholder="path/to/audio",
                    id="maxgain-source",
                )
                yield self.source_input
                yield Button("Browse", id="maxgain-source-browse")
            yield Label("Output folder (optional)")
            with Horizontal(id="maxgain-output-row"):
                self.output_folder_input = Input(
                    placeholder="Default: <source>/normalized",
                    id="maxgain-output-folder",
                )
                yield self.output_folder_input
                yield Button("Browse", id="maxgain-output-browse")
            yield Label("Output name (optional, single file)")
            self.output_name_input = Input(
                placeholder="Default: <name>_normalised.<ext>",
                id="maxgain-output-name",
            )
            yield self.output_name_input
            yield Label("Target peak (dBFS)")
            self.target_dbfs_input = Input(
                value="-1.0",
                id="maxgain-target-dbfs",
            )
            yield self.target_dbfs_input
            with Horizontal(id="maxgain-options"):
                yield Label("Convert to MP3")
                self.to_mp3 = Switch(value=False, id="maxgain-mp3")
                yield self.to_mp3
            with Horizontal(id="maxgain-actions"):
                yield Button("Start", id="maxgain-run", variant="success")
                yield Button("Copy Log", id="maxgain-copy")
                yield Button("Clear Log", id="maxgain-clear")
            self.status = Static("", id="maxgain-status")
            yield self.status
            self.progress = ProgressBar(id="maxgain-progress")
            yield self.progress
            self.log_view = RichLog(id="maxgain-log", highlight=True)
            yield self.log_view
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "maxgain-clear":
            self._clear_log()
            self.source_input.value = ""
            self.output_folder_input.value = ""
            self.output_name_input.value = ""
            self.target_dbfs_input.value = "-1.0"
            self.to_mp3.value = False
            return
        if event.button.id == "maxgain-copy":
            self._copy_log()
            return
        if event.button.id == "maxgain-source-browse":
            self._open_picker(target="source")
            return
        if event.button.id == "maxgain-output-browse":
            self._open_picker(target="output")
            return
        if event.button.id == "maxgain-run":
            self._run_script()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "maxgain-mp3":
            self._refresh_default_output()

    def _open_picker(self, *, target: str) -> None:
        current = (
            self.source_input.value.strip()
            if target == "source"
            else self.output_folder_input.value.strip()
        )
        start_path = Path(current).expanduser() if current else Path.home()
        if start_path.exists() and start_path.is_file():
            start_path = start_path.parent

        def _apply(path: Path) -> None:
            if target == "source":
                self.source_input.value = str(path)
                self._refresh_default_output()
                return
            self.output_folder_input.value = str(path)

        mode = "any" if target == "source" else "directory"
        title = "Select audio file or folder" if target == "source" else "Select output folder"
        self.app.push_screen(
            PathPickerScreen(
                mode=mode,
                on_selected=_apply,
                start_path=start_path,
                title=title,
            )
        )

    def _run_script(self) -> None:
        if not self._deps_ready():
            return
        source = self._resolve_source()
        if source is None:
            return
        target_dbfs = self._parse_target_dbfs()
        if target_dbfs is None:
            return
        output_path = self._resolve_output(source)
        if output_path is None:
            return
        self.status.update("Normalizing...")
        self._clear_log()
        self.progress.update(progress=0, total=0)
        self.run_worker(
            lambda: self._worker(source, output_path, target_dbfs),
            thread=True,
        )

    def _deps_ready(self) -> bool:
        if importlib.util.find_spec("pydub") is None:
            self.status.update("[red]Missing dependency: pydub.[/red]")
            return False
        if (
            importlib.util.find_spec("audioop") is None
            and importlib.util.find_spec("pyaudioop") is None
        ):
            self.status.update(
                "[red]Missing dependency: audioop-lts (install it first).[/red]"
            )
            return False
        if shutil.which("ffmpeg") is None:
            self.status.update("[red]Missing dependency: ffmpeg.[/red]")
            return False
        return True

    def _resolve_source(self) -> Path | None:
        raw = self.source_input.value.strip()
        if not raw:
            self.status.update("[red]Source path is required.[/red]")
            return None
        source = Path(raw).expanduser()
        if not source.exists():
            self.status.update("[red]Source path not found.[/red]")
            return None
        return source

    def _resolve_output(self, source: Path) -> Path | None:
        output_folder_raw = self.output_folder_input.value.strip()
        if source.is_dir():
            if output_folder_raw:
                output_dir = Path(output_folder_raw).expanduser()
                if output_dir.suffix:
                    self.status.update("[red]Output folder is required for batches.[/red]")
                    return None
            else:
                output_dir = source / "normalized"
            return output_dir

        output_ext = ".mp3" if self.to_mp3.value else source.suffix.lower()
        if not output_ext:
            self.status.update("[red]Unknown output extension.[/red]")
            return None

        output_name = self.output_name_input.value.strip()
        output_dir = source.parent
        if output_folder_raw:
            output_dir = Path(output_folder_raw).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)

        if output_name:
            output_path = output_dir / output_name
            if output_path.suffix != output_ext:
                output_path = output_path.with_suffix(output_ext)
        else:
            output_path = output_dir / f"{source.stem}_normalised{output_ext}"
        return output_path

    def _refresh_default_output(self) -> None:
        if self.output_name_input.value.strip():
            return
        raw = self.source_input.value.strip()
        if not raw:
            return
        source = Path(raw).expanduser()
        if not source.exists():
            return
        if source.is_dir():
            self.output_folder_input.placeholder = f"Default: {source / 'normalized'}"
            return
        output_ext = ".mp3" if self.to_mp3.value else source.suffix.lower()
        self.output_name_input.placeholder = f"Default: {source.stem}_normalised{output_ext}"

    def _worker(self, source: Path, output_path: Path, target_dbfs: float) -> None:
        try:
            from pydub import AudioSegment
        except Exception as exc:
            self.app.call_from_thread(
                self.status.update, f"[red]pydub error: {exc}[/red]"
            )
            return

        files = self._collect_files(source)
        if not files:
            self.app.call_from_thread(
                self.status.update,
                "[red]No audio files found.[/red]",
            )
            return

        output_dir = output_path if source.is_dir() else output_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        total = len(files)
        self.app.call_from_thread(self.progress.update, progress=0, total=total)

        errors: list[str] = []
        for index, audio_file in enumerate(files, start=1):
            try:
                audio = AudioSegment.from_file(audio_file)
                peak = audio.max_dBFS
                if peak == float("-inf"):
                    gain_needed = 0.0
                    self.app.call_from_thread(
                        self._log, f"{audio_file.name}: silent input; no gain applied."
                    )
                else:
                    gain_needed = target_dbfs - peak

                self.app.call_from_thread(
                    self._log,
                    f"{audio_file.name}: peak {peak:.2f} dBFS -> gain {gain_needed:.2f} dB",
                )

                normalized = audio.apply_gain(gain_needed)
                output_ext = ".mp3" if self.to_mp3.value else audio_file.suffix.lower()
                out_name = f"{audio_file.stem}_normalised{output_ext}"
                out_path = output_dir / out_name if source.is_dir() else output_path
                file_format = out_path.suffix.lower().lstrip(".")
                export_args = {}
                if file_format == "mp3":
                    export_args = {"parameters": ["-q:a", "0"]}
                normalized.export(out_path, format=file_format, **export_args)
                self.app.call_from_thread(self._log, f"Saved: {out_path}")
            except Exception as exc:
                errors.append(f"{audio_file.name}: {exc}")
            self.app.call_from_thread(self.progress.update, progress=index, total=total)

        if errors:
            self.app.call_from_thread(
                self.status.update,
                f"[yellow]Done with {len(errors)} errors. Check output folder.[/yellow]",
            )
        else:
            self.app.call_from_thread(
                self.status.update, "[green]MaxGain completed.[/green]"
            )

    def _log(self, text: str) -> None:
        self._log_lines.append(text)
        self.log_view.write(text)

    def _clear_log(self) -> None:
        self._log_lines.clear()
        self.log_view.clear()
        self.status.update("")
        self.progress.update(progress=0, total=0)

    def _copy_log(self) -> None:
        if not self._log_lines:
            self.status.update("[yellow]Log is empty.[/yellow]")
            return
        self.app.copy_to_clipboard("\n".join(self._log_lines))
        self.status.update("[green]Log copied to clipboard.[/green]")

    def _parse_target_dbfs(self) -> float | None:
        raw = self.target_dbfs_input.value.strip()
        if not raw:
            self.status.update("[red]Target dBFS is required.[/red]")
            return None
        try:
            return float(raw)
        except ValueError:
            self.status.update("[red]Target dBFS must be a number.[/red]")
            return None

    def _collect_files(self, source: Path) -> list[Path]:
        if source.is_file() and source.suffix.lower() in self._INPUT_EXTS:
            return [source]
        if source.is_dir():
            files: list[Path] = []
            for ext in sorted(self._INPUT_EXTS):
                files.extend(source.glob(f"*{ext}"))
            return sorted(set(files))
        return []


TOOL = Tool(
    name="MaxGain",
    description="Normalize audio to a target peak dBFS (single file or folder).",
    category="Audio",
    screen_factory=MaxGainScreen,
)
