# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Storage panel widget for the thermall dashboard."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Static

from thermall.config import Config
from thermall.history import HistoryStore
from thermall.model import DeviceSnapshot, DriveHealthEvent, Reading, Severity
from thermall.sysfs import nvme_devices
from thermall.widgets.braillechart import BrailleChart
from thermall.widgets.threshold_label import ThresholdLabel

_CHART_WIDTH = 20
_CHART_HEIGHT = 4
_MINIMIZED_CHART_HEIGHT_MULTIPLIER = 3


def _is_nvme(reading: Reading) -> bool:
    """Check if a reading is from an NVMe device."""
    label = reading.raw_label.lower()
    return "composite" in label or label.startswith("nvme")


def _chip_from_raw_label(raw_label: str) -> str | None:
    """Pull the lm-sensors chip name out of a `<chip> <sensor>` raw label.

    Returns the leading whitespace-separated token when it looks like an
    nvme chip (`nvme-pci-<hex>`); else `None`. The sensor portion
    (`Composite`, `Sensor 1`, ...) is everything after the chip.
    """

    if not raw_label:
        return None
    chip, _, _ = raw_label.partition(" ")
    if chip.startswith("nvme-pci-"):
        return chip
    return None


def _drive_name(
    reading: Reading,
    label_map: dict[str, str] | Mapping[str, str],
    nvme_models: Mapping[str, str] | None = None,
) -> str:
    """Build the display name for an NVMe reading.

    Resolution order:
    1. Exact entry in `label_map` (user-configured wins over auto).
    2. Drive model from `nvme_models` (sysfs lookup keyed by lm-sensors
       chip name); when the reading is a sub-sensor (`Sensor 1`,
       `Sensor 2`, ...), append the sub-sensor label so multi-sensor
       drives stay distinguishable.
    3. Fallback: strip a trailing `Composite` from `raw_label` and
       return whatever remains. Keeps panels rendering on systems with
       no `/sys/class/nvme` (containers, restricted environments) and
       preserves the legacy label shape for callers that pre-date this
       enrichment.
    """

    if reading.raw_label in label_map:
        return label_map[reading.raw_label]

    chip = _chip_from_raw_label(reading.raw_label)
    if chip and nvme_models and chip in nvme_models:
        model = nvme_models[chip]
        sensor_part = reading.raw_label[len(chip) :].strip()
        if sensor_part and sensor_part.lower() != "composite":
            return f"{model} ({sensor_part})"
        return model

    name = reading.raw_label
    if name.lower().endswith(" composite"):
        name = name[:-10]
    elif name.lower().endswith("composite"):
        name = name[:-9]
    return name.strip()


def _most_recent_event(
    events: tuple[DriveHealthEvent, ...], device: str | None
) -> DriveHealthEvent | None:
    """Find the most recent event for a device."""
    matching = [e for e in events if e.device == device]
    if not matching:
        return None
    return max(matching, key=lambda e: e.timestamp)


class StoragePanel(Vertical):
    """Container panel for the Storage block of the dashboard."""

    def __init__(
        self,
        config: Config,
        snapshot: DeviceSnapshot | None = None,
        nvme_models: Mapping[str, str] | None = None,
        history: HistoryStore | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._snapshot = snapshot if snapshot is not None else _empty_snapshot()
        # Resolve `nvme-pci-<bus><devfn>` chip names to friendly drive
        # model strings exactly once per panel instance. Hardware does
        # not hot-swap during a session; re-reading sysfs on every
        # refresh tick would waste syscalls. Tests inject a fake map.
        self._nvme_models: Mapping[str, str] = (
            nvme_models if nvme_models is not None else nvme_devices()
        )
        self._history = history
        self._minimized = False

    @property
    def snapshot(self) -> DeviceSnapshot:
        """The currently-rendered snapshot."""
        return self._snapshot

    @snapshot.setter
    def snapshot(self, new_snapshot: DeviceSnapshot) -> None:
        """Re-render with a new snapshot when the dashboard refreshes."""
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
            for child in self._build_widgets():
                self.mount(child)

    def _chart_height(self) -> int:
        return (
            _CHART_HEIGHT * _MINIMIZED_CHART_HEIGHT_MULTIPLIER if self._minimized else _CHART_HEIGHT
        )

    def compose(self) -> ComposeResult:
        yield from self._build_widgets()

    def _build_widgets(self) -> Iterator[Widget]:
        """Yield this panel's widget tree.

        Used both by Textual's compose() lifecycle (initial mount) and
        by the snapshot setter (re-mount on refresh). Constructs the
        per-drive Horizontal containers explicitly via the
        constructor, so it works without an active compose stack.
        """
        yield Static("Storage", classes="panel-header")

        if not self._nvme_readings:
            yield Static(
                "No NVMe drives detected.",
                classes="panel-empty",
            )
            return

        # One chart at the top tracks the hottest drive; per-drive
        # text rows below carry absolute values + health status.
        hottest = max(self._nvme_readings, key=lambda r: r.value)
        nvme_thresholds = self._config.thresholds.get("nvme")
        if self._history is not None:
            yield BrailleChart(
                self._history.get(hottest.raw_label),
                width=_CHART_WIDTH,
                height=self._chart_height(),
                thresholds=nvme_thresholds,
                unit="°C",
            )

        for reading in self._nvme_readings:
            drive_name = _drive_name(reading, self._config.labels, self._nvme_models)
            threshold = self._config.thresholds.get("nvme")
            event = _most_recent_event(self._snapshot.drive_health_events, reading.raw_label)

            row_children: list[Widget] = [Static(drive_name, classes="drive-name")]
            if threshold:
                row_children.append(ThresholdLabel(reading=reading, thresholds=threshold))
            else:
                row_children.append(Static(f"{reading.value:.0f}{reading.unit}"))
            row_children.append(self._health_label(event, reading.raw_label))
            yield Horizontal(*row_children, classes="reading-detail")

    def _health_label(self, event: DriveHealthEvent | None, device: str) -> Static:
        """Render health status for a drive."""
        snapshot = self._snapshot

        # Case 1: smartd unavailable - show install hint
        if not snapshot.smartd_available:
            return Static(
                "[dim]Health monitoring off — Install smartmontools to enable.[/dim]",
                classes="health-unavailable",
            )

        # Case 2: no event for this device - healthy
        if event is None:
            return Static("[green]Healthy[/green]", classes="health-ok")

        # Case 3: event present - show message with severity color
        severity = event.severity
        if severity == Severity.CRIT:
            colour = "red"
        elif severity == Severity.WARN:
            colour = "yellow"
        else:
            colour = "dim"

        # Truncate long messages
        msg = event.message
        if len(msg) > 50:
            msg = msg[:47] + "..."

        return Static(f"[{colour}]{msg}[/{colour}]", classes=f"health-{severity.value}")

    @property
    def _nvme_readings(self) -> tuple[Reading, ...]:
        """Get NVMe composite temps from other_temps."""
        return tuple(r for r in self._snapshot.other_temps if _is_nvme(r))


def _empty_snapshot() -> DeviceSnapshot:
    """Create an empty snapshot for initial render."""
    return DeviceSnapshot(taken_at=datetime(2026, 1, 1, 0, 0, 0))
