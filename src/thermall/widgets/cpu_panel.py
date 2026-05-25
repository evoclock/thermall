# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""CPU dashboard panel.

Renders `DeviceSnapshot.cpu_temps` (populated by the aggregator's
category routing) as one `ThresholdLabel` per reading, plus a fan
row for any `Fan` in `snapshot.fans` whose label tokenises CPU.

Empty `cpu_temps` is treated as a help-when-broken state per
`user-ui-quality-apple-level`: the panel surfaces a one-line
remediation hint rather than rendering blank.

The panel is a `Vertical` so children can mount independently; the
single-snapshot setter pattern triggers a re-mount whenever the
dashboard's refresh loop assigns a fresh snapshot.
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
from thermall.model import DeviceSnapshot, Fan, Reading
from thermall.widgets.braillechart import BrailleChart
from thermall.widgets.threshold_label import ThresholdLabel

_CHART_WIDTH = 20
# When the dashboard is in minimize mode, the chart fills the vertical
# space previously occupied by the per-sensor detail rows. 3x normal
# height gives the chart enough room to actually use the freed space.
_MINIMIZED_CHART_HEIGHT_MULTIPLIER = 3
_CHART_HEIGHT = 4

_EMPTY_HINT = (
    "No CPU sensors detected. Install [b]lm-sensors[/b] and run [b]sudo sensors-detect[/b]."
)


def _empty_snapshot() -> DeviceSnapshot:
    """Synthesise a placeholder snapshot for construction-time defaults."""

    return DeviceSnapshot(taken_at=datetime.now(tz=UTC))


def _is_cpu_fan(fan: Fan) -> bool:
    """True when the fan label tokenises CPU.

    Checks `display_label` first (user-configured names like "CPU fan",
    "AIO pump") and falls back to `raw_label`. Uses discrete-word
    matching so that "cputin" (a chassis sensor name that can leak
    into fan-channel labelling on some chips) does not false-match.
    """

    candidates = [fan.raw_label.lower()]
    if fan.display_label is not None:
        candidates.append(fan.display_label.lower())
    return any(_has_word(label, "cpu") for label in candidates)


def _has_word(label: str, word: str) -> bool:
    """Discrete-token substring match identical to mapping._has_word.

    Duplicated here to avoid importing a private name across module
    boundaries. If a third caller needs the same logic, promote to
    public in `thermall.mapping`.
    """

    if word not in label:
        return False
    idx = 0
    while True:
        idx = label.find(word, idx)
        if idx < 0:
            return False
        before_ok = idx == 0 or not label[idx - 1].isalnum()
        end = idx + len(word)
        after_ok = end == len(label) or not label[end].isalnum()
        if before_ok and after_ok:
            return True
        idx = end


class CpuPanel(Vertical):
    """Container panel for the CPU block of the dashboard."""

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
        yield Static("[bold]CPU[/bold]")

        if not self._snapshot.cpu_temps:
            yield Static(_EMPTY_HINT)
        else:
            thresholds = self._config.thresholds["cpu"]
            # btop-style braille chart for the hottest reading, with
            # min/max axis labels and severity-coloured dots
            # (green/yellow/red mapped to OK/WARN/CRIT). Sits above
            # the per-reading text rows so trend and absolute values
            # are both visible at a glance.
            primary = _hottest(self._snapshot.cpu_temps)
            if primary is not None and self._history is not None:
                yield BrailleChart(
                    self._history.get(primary.raw_label),
                    width=_CHART_WIDTH,
                    height=self._chart_height(),
                    thresholds=thresholds,
                    unit="°C",
                )
            for reading in self._snapshot.cpu_temps:
                graded = grade_reading(reading, thresholds)
                yield ThresholdLabel(graded, thresholds)

        for fan in self._snapshot.fans:
            if _is_cpu_fan(fan):
                status = "Stopped" if fan.is_stopped else "Spinning"
                yield Static(
                    f"{fan.label}: {fan.rpm} RPM ({status})",
                    classes="reading-detail",
                )


def _hottest(readings: tuple[Reading, ...]) -> Reading | None:
    """Pick the highest-valued reading; `None` for an empty tuple.

    The dashboard's chart heuristic shows trend for the currently-
    hottest sensor — the one most likely to need watching.
    """

    if not readings:
        return None
    return max(readings, key=lambda r: r.value)
