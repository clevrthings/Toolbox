from __future__ import annotations

from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from toolbox.tools.base import Tool


class AudioDistanceScreen(Screen):
    BINDINGS = [Binding("escape", "back", "Back", priority=True)]

    def __init__(self) -> None:
        super().__init__()
        self._updating = False
        self._speed = self._speed_from_temp(20.0)

    def compose(self):
        yield Header()
        with ScrollableContainer(id="distance-form"):
            yield Static("Audio Distance", id="distance-title")
            yield Label("Temperature (°C)")
            self.temp_input = Input(value="20", id="distance-temp")
            yield self.temp_input
            self.speed_label = Static("", id="distance-speed")
            yield self.speed_label

            yield Label("Time (ms)")
            self.time_input = Input(placeholder="e.g. 10", id="distance-time")
            yield self.time_input
            yield Label("Distance (m)")
            self.distance_input = Input(placeholder="e.g. 3.43", id="distance-meters")
            yield self.distance_input

            yield Label("Frequency (Hz)")
            self.freq_input = Input(placeholder="e.g. 440", id="distance-hz")
            yield self.freq_input
            yield Label("Wavelength (m)")
            self.wavelength_input = Input(placeholder="e.g. 0.78", id="distance-wavelength")
            yield self.wavelength_input

            yield Button("Clear", id="distance-clear")
        yield Footer()

    def on_mount(self) -> None:
        self._update_speed_label()

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._updating:
            return
        if event.input.id == "distance-temp":
            temp = self._parse_float(event.value)
            if temp is None:
                return
            self._speed = self._speed_from_temp(temp)
            self._update_speed_label()
            self._recompute_pairs()
            return

        if event.input.id == "distance-time":
            self._update_time_distance(from_time=True)
            return
        if event.input.id == "distance-meters":
            self._update_time_distance(from_time=False)
            return
        if event.input.id == "distance-hz":
            self._update_freq_wavelength(from_freq=True)
            return
        if event.input.id == "distance-wavelength":
            self._update_freq_wavelength(from_freq=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "distance-clear":
            return
        self._updating = True
        try:
            self.time_input.value = ""
            self.distance_input.value = ""
            self.freq_input.value = ""
            self.wavelength_input.value = ""
        finally:
            self._updating = False

    def _update_time_distance(self, *, from_time: bool) -> None:
        if from_time:
            value = self._parse_float(self.time_input.value)
            if value is None:
                self._set_value(self.distance_input, "")
                return
            distance = self._speed * (value / 1000.0)
            self._set_value(self.distance_input, f"{distance:.4f}")
        else:
            value = self._parse_float(self.distance_input.value)
            if value is None:
                self._set_value(self.time_input, "")
                return
            if self._speed <= 0:
                return
            time_ms = (value / self._speed) * 1000.0
            self._set_value(self.time_input, f"{time_ms:.4f}")

    def _update_freq_wavelength(self, *, from_freq: bool) -> None:
        if from_freq:
            value = self._parse_float(self.freq_input.value)
            if value is None:
                self._set_value(self.wavelength_input, "")
                return
            if value <= 0:
                return
            wavelength = self._speed / value
            self._set_value(self.wavelength_input, f"{wavelength:.4f}")
        else:
            value = self._parse_float(self.wavelength_input.value)
            if value is None:
                self._set_value(self.freq_input, "")
                return
            if value <= 0:
                return
            freq = self._speed / value
            self._set_value(self.freq_input, f"{freq:.4f}")

    def _recompute_pairs(self) -> None:
        time_raw = self.time_input.value.strip()
        distance_raw = self.distance_input.value.strip()
        if time_raw and not distance_raw:
            self._update_time_distance(from_time=True)
        elif distance_raw and not time_raw:
            self._update_time_distance(from_time=False)

        freq_raw = self.freq_input.value.strip()
        wavelength_raw = self.wavelength_input.value.strip()
        if freq_raw and not wavelength_raw:
            self._update_freq_wavelength(from_freq=True)
        elif wavelength_raw and not freq_raw:
            self._update_freq_wavelength(from_freq=False)

    def _update_speed_label(self) -> None:
        self.speed_label.update(f"Speed of sound: {self._speed:.2f} m/s")

    def _speed_from_temp(self, temp_c: float) -> float:
        return 331.3 + 0.606 * temp_c

    def _parse_float(self, raw: str) -> float | None:
        raw = raw.strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    def _set_value(self, widget: Input, value: str) -> None:
        self._updating = True
        try:
            widget.value = value
        finally:
            self._updating = False


TOOL = Tool(
    name="Audio Distance",
    description="Convert time to distance and frequency to wavelength using the speed of sound.",
    category="Audio",
    screen_factory=AudioDistanceScreen,
)
