from __future__ import annotations

from pathlib import Path
import wave

from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer
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
        yield Static(self._title, id="stereo-picker-title")
        yield FilteredDirectoryTree(self._start_path, id="stereo-picker-tree")
        yield Footer()

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self._on_selected(event.path)
        self.app.pop_screen()


class StereoMergerScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", priority=True)]

    def __init__(self) -> None:
        super().__init__()
        self._log_lines: list[str] = []

    def compose(self):
        yield Header()
        with ScrollableContainer(id="stereo-form"):
            yield Static("Stereo Merger", id="stereo-title")
            yield Label("Source folder with .L/.R WAV pairs")
            with Horizontal(id="stereo-source-row"):
                self.source_input = Input(
                    placeholder="path/to/folder",
                    id="stereo-source",
                )
                yield self.source_input
                yield Button("Browse", id="stereo-source-browse")
            with Horizontal(id="stereo-options"):
                yield Label("Delete source files after merge")
                self.delete_sources = Switch(value=True, id="stereo-delete")
                yield self.delete_sources
            with Horizontal(id="stereo-actions"):
                yield Button("Start", id="stereo-run", variant="success")
                yield Button("Copy Log", id="stereo-copy")
                yield Button("Clear Log", id="stereo-clear")
            self.status = Static("", id="stereo-status")
            yield self.status
            self.progress = ProgressBar(id="stereo-progress")
            yield self.progress
            self.log_view = RichLog(id="stereo-log", highlight=True)
            yield self.log_view
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "stereo-clear":
            self._clear_log()
            return
        if event.button.id == "stereo-copy":
            self._copy_log()
            return
        if event.button.id == "stereo-source-browse":
            self._open_picker()
            return
        if event.button.id == "stereo-run":
            self._run_script()

    def _open_picker(self) -> None:
        current = self.source_input.value.strip()
        start_path = Path(current).expanduser() if current else Path.home()
        if start_path.exists() and start_path.is_file():
            start_path = start_path.parent

        def _apply(path: Path) -> None:
            self.source_input.value = str(path)

        self.app.push_screen(
            PathPickerScreen(
                on_selected=_apply,
                start_path=start_path,
                title="Select source folder",
            )
        )

    def _run_script(self) -> None:
        source = self._resolve_source()
        if source is None:
            return
        self.status.update("Merging...")
        self._clear_log()
        self.progress.update(progress=0, total=0)
        self.run_worker(lambda: self._worker(source), thread=True)

    def _resolve_source(self) -> Path | None:
        raw = self.source_input.value.strip()
        if not raw:
            self.status.update("[red]Source folder is required.[/red]")
            return None
        source = Path(raw).expanduser()
        if not source.exists() or not source.is_dir():
            self.status.update("[red]Source folder not found.[/red]")
            return None
        return source

    def _worker(self, source: Path) -> None:
        pairs = self._collect_pairs(source)
        if not pairs:
            self.app.call_from_thread(
                self.status.update,
                "[red]No .L/.R WAV pairs found.[/red]",
            )
            return

        total = len(pairs)
        self.app.call_from_thread(self.progress.update, progress=0, total=total)

        for index, (key, left, right) in enumerate(pairs, start=1):
            output_path = left.parent / f"{key}.wav"
            try:
                self._merge_to_stereo(left, right, output_path)
                if self.delete_sources.value:
                    left.unlink(missing_ok=True)
                    right.unlink(missing_ok=True)
                self.app.call_from_thread(
                    self._log, f"Merged: {output_path}"
                )
            except Exception as exc:
                self.app.call_from_thread(
                    self._log, f"Failed {key}: {exc}"
                )
            self.app.call_from_thread(
                self.progress.update, progress=index, total=total
            )

        self.app.call_from_thread(
            self.status.update, "[green]Stereo merge completed.[/green]"
        )

    def _collect_pairs(self, source: Path):
        grouped: dict[str, dict[str, Path]] = {}
        for path in source.glob("*.wav"):
            name = path.name
            if name.endswith(".L.wav"):
                key = name.replace(".L.wav", "")
                grouped.setdefault(key, {})["L"] = path
            elif name.endswith(".R.wav"):
                key = name.replace(".R.wav", "")
                grouped.setdefault(key, {})["R"] = path

        pairs = []
        for key, files in grouped.items():
            left = files.get("L")
            right = files.get("R")
            if left and right:
                pairs.append((key, left, right))
            else:
                self.app.call_from_thread(
                    self._log, f"Skipping {key}: missing L or R"
                )
        return pairs

    def _merge_to_stereo(self, left_path: Path, right_path: Path, output_path: Path) -> None:
        with wave.open(str(left_path), "rb") as left_wav, wave.open(
            str(right_path), "rb"
        ) as right_wav:
            if (
                left_wav.getframerate() != right_wav.getframerate()
                or left_wav.getnframes() != right_wav.getnframes()
                or left_wav.getsampwidth() != right_wav.getsampwidth()
            ):
                raise ValueError("Input files differ in parameters.")

            sampwidth = left_wav.getsampwidth()
            nframes = left_wav.getnframes()
            framerate = left_wav.getframerate()

            frames_left = left_wav.readframes(nframes)
            frames_right = right_wav.readframes(nframes)

            if sampwidth == 3:
                stereo_bytes = bytearray()
                for i in range(0, len(frames_left), 3):
                    stereo_bytes += frames_left[i : i + 3]
                    stereo_bytes += frames_right[i : i + 3]
            else:
                frame_size = sampwidth
                stereo_bytes = bytearray()
                for i in range(0, len(frames_left), frame_size):
                    stereo_bytes += frames_left[i : i + frame_size]
                    stereo_bytes += frames_right[i : i + frame_size]

            with wave.open(str(output_path), "wb") as stereo_wav:
                stereo_wav.setnchannels(2)
                stereo_wav.setsampwidth(sampwidth)
                stereo_wav.setframerate(framerate)
                stereo_wav.writeframes(stereo_bytes)

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


TOOL = Tool(
    name="Stereo Merger",
    description="Merge .L/.R mono WAV pairs into stereo WAV.",
    category="Audio",
    screen_factory=StereoMergerScreen,
)
