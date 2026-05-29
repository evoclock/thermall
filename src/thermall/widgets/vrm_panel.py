# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""VRM / chipset / motherboard panel.

Renders `DeviceSnapshot.vrm_temps` (populated by the aggregator's
category routing) as one `ThresholdLabel` per reading, graded against
`config.thresholds["vrm"]`. Empty `vrm_temps` surfaces a friendly hint
that the user likely needs to load the `nct6775` kernel module, since
that is the most common reason VRM and motherboard sensors are
invisible on AMD boards with a Nuvoton SuperIO chip.
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
from thermall.model import DeviceSnapshot, Reading
from thermall.widgets.braillechart import BrailleChart
from thermall.widgets.threshold_label import ThresholdLabel

_CHART_WIDTH = 20
_CHART_HEIGHT = 4
_MINIMIZED_CHART_HEIGHT_MULTIPLIER = 3

_EMPTY_HINT = (
    "No motherboard sensors detected. Load the [b]nct6775[/b] kernel module to "
    "see fan and VRM temperatures on Nuvoton-based boards (ASUS B550, X570, and "
    "similar). See the README Prerequisites section for the persistent setup."
)


def _empty_snapshot() -> DeviceSnapshot:
    """Synthesise a placeholder snapshot for construction-time defaults."""

    return DeviceSnapshot(taken_at=datetime.now(tz=UTC))


class VrmPanel(Vertical):
    """Container panel for the motherboard / VRM block of the dashboard."""

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
        yield Static("[bold]Motherboard / VRM[/bold]")

        if not self._snapshot.vrm_temps:
            yield Static(_EMPTY_HINT)
            return

        thresholds = self._config.thresholds["vrm"]
        primary = _hottest(self._snapshot.vrm_temps)
        if primary is not None and self._history is not None:
            yield BrailleChart(
                self._history.get(primary.raw_label),
                width=_CHART_WIDTH,
                height=self._chart_height(),
                thresholds=thresholds,
                unit="°C",
            )
        for reading in self._snapshot.vrm_temps:
            graded = grade_reading(reading, thresholds)
            yield ThresholdLabel(graded, thresholds)


def _hottest(readings: tuple[Reading, ...]) -> Reading | None:
    """Pick the highest-valued reading; `None` for an empty tuple."""

    if not readings:
        return None
    return max(readings, key=lambda r: r.value)
