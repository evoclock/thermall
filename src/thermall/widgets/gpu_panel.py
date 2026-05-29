# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""GPU dashboard panel.

Renders `DeviceSnapshot.gpus` as one sub-block per visible NVIDIA GPU
(model name, threshold-graded temperature, fan percent, power draw,
memory usage). On a system with no NVIDIA GPU the panel shows a plain
"No NVIDIA GPU detected." line; AMD / Intel GPU support is out of
scope for v1 per the scope doc § non-goals.

Each GPU's temperature is wrapped in a `Reading` so the
`ThresholdLabel` widget (12h) can render it consistently with the
CPU / VRM panels. The `Reading` uses the GPU model name as both
raw and display label.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from thermall.config import Config
from thermall.history import HistoryStore
from thermall.mapping import grade_reading
from thermall.model import DeviceSnapshot, Gpu, Reading
from thermall.widgets.braillechart import BrailleChart
from thermall.widgets.threshold_label import ThresholdLabel

_CHART_WIDTH = 20
_CHART_HEIGHT = 4
_MINIMIZED_CHART_HEIGHT_MULTIPLIER = 3


def _empty_snapshot() -> DeviceSnapshot:
    """Synthesise a placeholder snapshot for construction-time defaults."""

    return DeviceSnapshot(taken_at=datetime.now(tz=UTC))


def _gpu_temperature_reading(gpu: Gpu) -> Reading:
    """Wrap a `Gpu`'s temperature in a `Reading` for `ThresholdLabel`."""

    return Reading(
        raw_label=gpu.name,
        value=gpu.temperature_c,
        unit="C",
        display_label=gpu.name,
    )


def _format_fan(percent: float | None) -> str:
    """Format a GPU fan percentage; passively-cooled cards report None."""

    if percent is None:
        return "Fan: passive"
    return f"Fan: {percent:.0f}%"


def _format_power(watts: float | None) -> str:
    """Format a GPU power draw; integrated GPUs may report None."""

    if watts is None:
        return "Power: n/a"
    return f"Power: {watts:.1f} W"


def _format_memory(used_mb: int | None, total_mb: int | None) -> str:
    """Format GPU memory usage; either field absent renders n/a.

    NVIDIA reports values in megabytes; we display as-is rather than
    converting to GB because the values are already small integers
    that read clearly and conversion would introduce rounding error.
    """

    if used_mb is None or total_mb is None:
        return "Memory: n/a"
    return f"Memory: {used_mb} / {total_mb} MB"


class GpuPanel(Vertical):
    """Container panel for the GPU block of the dashboard."""

    def __init__(
        self,
        config: Config,
        snapshot: DeviceSnapshot | None = None,
        history: HistoryStore | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._snapshot = snapshot if snapshot is not None else _empty_snapshot()
        self._history = history
        self._minimized = False

    def compose(self) -> ComposeResult:
        yield from self._panel_widgets()

    @property
    def snapshot(self) -> DeviceSnapshot:
        return self._snapshot

    @snapshot.setter
    def snapshot(self, new_snapshot: DeviceSnapshot) -> None:
        self._snapshot = new_snapshot
        self._rebuild()

    @property
    def minimized(self) -> bool:
        return self._minimized

    @minimized.setter
    def minimized(self, value: bool) -> None:
        if value == self._minimized:
            return
        self._minimized = value
        self._rebuild()

    def _rebuild(self) -> None:
        if self.is_mounted:
            self.remove_children()
            for child in self._panel_widgets():
                self.mount(child)

    def _chart_height(self) -> int:
        return (
            _CHART_HEIGHT * _MINIMIZED_CHART_HEIGHT_MULTIPLIER if self._minimized else _CHART_HEIGHT
        )

    def _panel_widgets(self) -> Iterator[Widget]:
        gpus = self._snapshot.gpus
        header = "GPUs" if len(gpus) > 1 else "GPU"
        yield Static(f"[bold]{header}[/bold]")

        if not gpus:
            yield Static("No NVIDIA GPU detected.")
            return

        thresholds = self._config.thresholds["gpu"]
        # One chart at the top showing the hottest GPU; users with a
        # single GPU see its trend, multi-GPU users see the one most
        # likely to need attention.
        hottest_gpu = max(gpus, key=lambda g: g.temperature_c)
        if self._history is not None:
            yield BrailleChart(
                self._history.get(hottest_gpu.name),
                width=_CHART_WIDTH,
                height=self._chart_height(),
                thresholds=thresholds,
                unit="°C",
            )
        for gpu in gpus:
            yield Static(gpu.name, classes="reading-detail")
            graded = grade_reading(_gpu_temperature_reading(gpu), thresholds)
            yield ThresholdLabel(graded, thresholds)
            yield Static(_format_fan(gpu.fan_percent), classes="reading-detail")
            yield Static(_format_power(gpu.power_watts), classes="reading-detail")
            yield Static(
                _format_memory(gpu.memory_used_mb, gpu.memory_total_mb),
                classes="reading-detail",
            )
