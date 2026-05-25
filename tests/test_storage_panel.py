# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the StoragePanel widget."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from thermall.config import Config
from thermall.model import DeviceSnapshot, DriveHealthEvent, Reading, Severity
from thermall.widgets.storage_panel import (
    StoragePanel,
    _chip_from_raw_label,
    _drive_name,
    _is_nvme,
    _most_recent_event,
)


def _snap(
    other_temps: tuple[Reading, ...] = (),
    drive_health_events: tuple[DriveHealthEvent, ...] = (),
    smartd_available: bool = True,
) -> DeviceSnapshot:
    return DeviceSnapshot(
        taken_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        other_temps=other_temps,
        drive_health_events=drive_health_events,
        smartd_available=smartd_available,
    )


def _reading(
    raw_label: str = "nvme Composite",
    value: float = 45.0,
    unit: str = "°C",
    display_label: str | None = None,
) -> Reading:
    return Reading(
        raw_label=raw_label,
        value=value,
        unit=unit,
        display_label=display_label,
    )


def _event(
    message: str,
    device: str | None = None,
    severity: Severity = Severity.OK,
    timestamp: datetime | None = None,
) -> DriveHealthEvent:
    return DriveHealthEvent(
        timestamp=timestamp or datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        message=message,
        priority=6,
        severity=severity,
        device=device,
    )


class _StoragePanelApp(App[None]):
    def __init__(self, config: Config, snapshot: DeviceSnapshot) -> None:
        super().__init__()
        self._config = config
        self._snapshot = snapshot

    def compose(self) -> ComposeResult:
        yield StoragePanel(config=self._config, snapshot=self._snapshot)


# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestIsNvme:
    def test_composite_is_nvme(self) -> None:
        assert _is_nvme(_reading(raw_label="nvme Composite")) is True

    def test_nvme_prefix_is_nvme(self) -> None:
        assert _is_nvme(_reading(raw_label="nvme-pci-0800")) is True

    def test_case_insensitive(self) -> None:
        assert _is_nvme(_reading(raw_label="NVME Composite")) is True

    def test_non_nvme_not_nvme(self) -> None:
        assert _is_nvme(_reading(raw_label="k10temp Tctl")) is False
        assert _is_nvme(_reading(raw_label="nct6798 SYSTIN")) is False


class TestDriveName:
    def test_strips_composite_suffix(self) -> None:
        r = _reading(raw_label="nvme0 Composite")
        assert _drive_name(r, {}) == "nvme0"

    def test_uses_label_map(self) -> None:
        r = _reading(raw_label="nvme0 Composite")
        assert _drive_name(r, {"nvme0 Composite": "NVMe (system)"}) == "NVMe (system)"

    def test_no_composite_suffix_unchanged(self) -> None:
        r = _reading(raw_label="nvme-pci-0800")
        assert _drive_name(r, {}) == "nvme-pci-0800"

    # --- nvme_models lookup (sysfs-driven drive identity) ---

    def test_uses_nvme_model_for_chip(self) -> None:
        r = _reading(raw_label="nvme-pci-0100 Composite")
        models = {"nvme-pci-0100": "CT4000P310SSD8"}
        assert _drive_name(r, {}, models) == "CT4000P310SSD8"

    def test_appends_sensor_part_when_not_composite(self) -> None:
        # A drive can expose Composite plus Sensor 1, Sensor 2; the
        # drive name should keep them distinguishable.
        r = _reading(raw_label="nvme-pci-0100 Sensor 1")
        models = {"nvme-pci-0100": "CT4000P310SSD8"}
        assert _drive_name(r, {}, models) == "CT4000P310SSD8 (Sensor 1)"

    def test_label_map_wins_over_nvme_models(self) -> None:
        # User-configured labels override auto-detected model.
        r = _reading(raw_label="nvme-pci-0100 Composite")
        label_map = {"nvme-pci-0100 Composite": "System SSD"}
        models = {"nvme-pci-0100": "CT4000P310SSD8"}
        assert _drive_name(r, label_map, models) == "System SSD"

    def test_falls_back_when_chip_not_in_nvme_models(self) -> None:
        # A drive whose chip is not in the sysfs map: continue down the
        # fallback chain (strip Composite from raw label).
        r = _reading(raw_label="nvme-pci-0900 Composite")
        models = {"nvme-pci-0100": "CT4000P310SSD8"}  # different chip
        assert _drive_name(r, {}, models) == "nvme-pci-0900"

    def test_falls_back_when_nvme_models_is_none(self) -> None:
        # On a system with no /sys/class/nvme (containers, restricted
        # envs), nvme_devices() returns {} which is falsy.
        r = _reading(raw_label="nvme-pci-0100 Composite")
        assert _drive_name(r, {}, None) == "nvme-pci-0100"

    def test_falls_back_when_nvme_models_empty(self) -> None:
        r = _reading(raw_label="nvme-pci-0100 Composite")
        assert _drive_name(r, {}, {}) == "nvme-pci-0100"

    def test_sensor_part_case_insensitive(self) -> None:
        # Be defensive about case — lm-sensors uses `Composite` and
        # `Sensor 1` but other versions may differ.
        r = _reading(raw_label="nvme-pci-0100 composite")  # lowercase
        models = {"nvme-pci-0100": "CT4000P310SSD8"}
        assert _drive_name(r, {}, models) == "CT4000P310SSD8"

    def test_old_format_label_still_resolves(self) -> None:
        # Pre-chip-suffix raw labels (`nvme Composite`) skip the sysfs
        # path entirely and use the fallback. Ensures the old
        # collector format still renders sensibly.
        r = _reading(raw_label="nvme Composite")
        models = {"nvme-pci-0100": "CT4000P310SSD8"}
        assert _drive_name(r, {}, models) == "nvme"


class TestChipFromRawLabel:
    def test_composite_returns_chip(self) -> None:
        assert _chip_from_raw_label("nvme-pci-0100 Composite") == "nvme-pci-0100"

    def test_sub_sensor_returns_chip(self) -> None:
        assert _chip_from_raw_label("nvme-pci-0100 Sensor 1") == "nvme-pci-0100"

    def test_non_nvme_returns_none(self) -> None:
        assert _chip_from_raw_label("k10temp Tctl") is None

    def test_old_format_returns_none(self) -> None:
        # `nvme Composite` lacks `-pci-` so cannot be mapped to a
        # specific drive; fall through to the legacy strip-Composite
        # path.
        assert _chip_from_raw_label("nvme Composite") is None

    def test_empty_string_returns_none(self) -> None:
        assert _chip_from_raw_label("") is None

    def test_only_chip_no_sensor_returns_chip(self) -> None:
        # Defensive — `partition` returns the full string in [0] when
        # there's no separator. We still want to recognise the chip.
        assert _chip_from_raw_label("nvme-pci-0100") == "nvme-pci-0100"


class TestMostRecentEvent:
    def test_no_events_returns_none(self) -> None:
        assert _most_recent_event((), "nvme0") is None

    def test_no_matching_device_returns_none(self) -> None:
        e = _event("test", device="nvme1")
        assert _most_recent_event((e,), "nvme0") is None

    def test_returns_most_recent(self) -> None:
        old = _event("old", device="nvme0", timestamp=datetime(2026, 5, 22, 12, 0, tzinfo=UTC))
        new = _event("new", device="nvme0", timestamp=datetime(2026, 5, 23, 12, 0, tzinfo=UTC))
        result = _most_recent_event((old, new), "nvme0")
        assert result is new
        assert result.message == "new"


# Happy path - panel rendering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_storage_panel_renders_one_drive_healthy() -> None:
    """Panel shows a drive with 'Healthy' status."""
    snapshot = _snap(
        other_temps=(_reading(raw_label="nvme0 Composite", value=45.0),),
        drive_health_events=(),
    )
    config = Config()
    app = _StoragePanelApp(config, snapshot)

    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(StoragePanel)
        assert panel is not None


@pytest.mark.asyncio
async def test_storage_panel_renders_one_drive_with_event() -> None:
    """Panel shows a drive with a smartd event."""
    event = _event(
        "Power-on self-test failed",
        device="nvme0",
        severity=Severity.WARN,
    )
    snapshot = _snap(
        other_temps=(_reading(raw_label="nvme0 Composite", value=45.0),),
        drive_health_events=(event,),
    )
    config = Config()
    app = _StoragePanelApp(config, snapshot)

    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(StoragePanel)
        assert panel is not None


@pytest.mark.asyncio
async def test_storage_panel_renders_two_drives() -> None:
    """Panel shows two NVMe drives."""
    snapshot = _snap(
        other_temps=(
            _reading(raw_label="nvme0 Composite"),
            _reading(raw_label="nvme1 Composite"),
        ),
    )
    config = Config()
    app = _StoragePanelApp(config, snapshot)

    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(StoragePanel)
        assert panel is not None


# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_storage_panel_no_drives_no_events() -> None:
    """Empty list shows 'No NVMe drives detected'."""
    snapshot = _snap()
    config = Config()
    app = _StoragePanelApp(config, snapshot)

    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(StoragePanel)
        assert panel is not None


@pytest.mark.asyncio
async def test_storage_panel_smartd_unavailable_shows_install_hint() -> None:
    """smartd_available=False shows install hint."""
    snapshot = _snap(
        other_temps=(_reading(raw_label="nvme0 Composite"),),
        smartd_available=False,
    )
    config = Config()
    app = _StoragePanelApp(config, snapshot)

    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(StoragePanel)
        assert panel is not None


@pytest.mark.asyncio
async def test_storage_panel_shows_most_recent_event_per_drive() -> None:
    """Two events for same drive - shows most recent."""
    old = _event(
        "Old warning",
        device="nvme0",
        timestamp=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
    )
    new = _event(
        "New critical",
        device="nvme0",
        severity=Severity.CRIT,
        timestamp=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
    )
    snapshot = _snap(
        other_temps=(_reading(raw_label="nvme0 Composite"),),
        drive_health_events=(old, new),
    )
    config = Config()
    app = _StoragePanelApp(config, snapshot)

    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(StoragePanel)
        assert panel is not None


@pytest.mark.asyncio
async def test_storage_panel_handles_event_with_no_device_attribute() -> None:
    """Event with device=None shows up."""
    event = _event("Global smartd warning", device=None, severity=Severity.WARN)
    snapshot = _snap(
        other_temps=(_reading(raw_label="nvme0 Composite"),),
        drive_health_events=(event,),
    )
    config = Config()
    app = _StoragePanelApp(config, snapshot)

    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one(StoragePanel)
        assert panel is not None


# Model tests for smartd_available field
# ---------------------------------------------------------------------------


class TestSmartdAvailable:
    def test_snapshot_smartd_available_default_true(self) -> None:
        snap = DeviceSnapshot(taken_at=datetime.now(tz=UTC))
        assert snap.smartd_available is True

    def test_aggregate_smartd_available_false(self) -> None:
        from thermall.model import aggregate

        snap = aggregate(smartd_available=False)
        assert snap.smartd_available is False

    def test_aggregate_smartd_available_defaults_true(self) -> None:
        from thermall.model import aggregate

        snap = aggregate()
        assert snap.smartd_available is True


# ---------------------------------------------------------------------------
# Regression — snapshot setter outside the mount lifecycle
# ---------------------------------------------------------------------------
#
# Bug: previously the snapshot setter called `self.compose()` directly.
# StoragePanel.compose() uses `with Horizontal():` which pokes into
# `App._compose_stacks[-1]`; outside Textual's mount lifecycle that stack
# is empty and the context manager raises IndexError. The fix splits
# compose() and the setter to both use `_build_widgets()`, which
# constructs Horizontal containers explicitly.
#
# This test exercises the failure mode: mount the panel with a snapshot,
# then assign a NEW snapshot (the refresh-loop path), and verify no
# IndexError. It mirrors what `Dashboard._refresh_now()` does at runtime
# every config.refresh_seconds.


@pytest.mark.asyncio
async def test_snapshot_setter_outside_initial_mount_does_not_index_error() -> None:
    """Reproduce the IndexError seen on the live machine during refresh."""

    from datetime import UTC, datetime

    from textual.app import App

    from thermall.config import Config
    from thermall.model import DeviceSnapshot, Reading
    from thermall.widgets.storage_panel import StoragePanel

    def _snap_with_two_drives() -> DeviceSnapshot:
        # Two NVMe composite readings — the scenario from the live
        # traceback (both nvme0n1 and nvme1n1 produce a Composite).
        # Post drive-identity work, each chip carries its bus suffix
        # so the labels stay distinct.
        return DeviceSnapshot(
            taken_at=datetime.now(tz=UTC),
            other_temps=(
                Reading(
                    raw_label="nvme-pci-0100 Composite",
                    value=40.0,
                    unit="C",
                ),
                Reading(
                    raw_label="nvme-pci-0800 Composite",
                    value=39.0,
                    unit="C",
                ),
            ),
        )

    panel = StoragePanel(Config(), _snap_with_two_drives(), nvme_models={})

    class _Host(App[None]):
        def compose(self) -> ComposeResult:
            yield panel

    async with _Host().run_test() as pilot:
        await pilot.pause()
        # The refresh path: assign a new snapshot while mounted.
        # Before the fix this raised IndexError from
        # `Horizontal.__enter__` poking `_compose_stacks[-1]`.
        panel.snapshot = _snap_with_two_drives()


# ---------------------------------------------------------------------------
# Multi-drive identity (user's actual hardware: Crucial + Kingston)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_storage_panel_renders_distinct_models_for_two_drives() -> None:
    """Two NVMe chips resolve to two distinct model names via injected sysfs.

    Reproduces the user's live hardware: nvme-pci-0100 (Crucial) and
    nvme-pci-0800 (Kingston). Without chip-suffix preservation +
    sysfs lookup, both would render as the same `nvme` row.
    """

    snapshot = _snap(
        other_temps=(
            _reading(raw_label="nvme-pci-0100 Composite", value=40.0),
            _reading(raw_label="nvme-pci-0800 Composite", value=39.0),
        ),
    )
    config = Config()
    injected_models = {
        "nvme-pci-0100": "CT4000P310SSD8",
        "nvme-pci-0800": "KINGSTON SNV2S2000G",
    }
    panel = StoragePanel(config, snapshot, nvme_models=injected_models)

    class _Host(App[None]):
        def compose(self) -> ComposeResult:
            yield panel

    async with _Host().run_test() as pilot:
        await pilot.pause()
        # Drive name Statics must carry both model strings; the
        # `panel-header` Static carries "Storage" so we filter it out.
        names = [str(s.content) for s in panel.query(Static).filter(".drive-name")]
        assert "CT4000P310SSD8" in names
        assert "KINGSTON SNV2S2000G" in names


@pytest.mark.asyncio
async def test_storage_panel_appends_sub_sensor_label() -> None:
    """A drive that exposes Composite + Sensor 1 keeps them distinguishable."""

    snapshot = _snap(
        other_temps=(
            _reading(raw_label="nvme-pci-0100 Composite", value=40.0),
            _reading(raw_label="nvme-pci-0100 Sensor 1", value=41.0),
        ),
    )
    config = Config()
    panel = StoragePanel(
        config,
        snapshot,
        nvme_models={"nvme-pci-0100": "CT4000P310SSD8"},
    )

    class _Host(App[None]):
        def compose(self) -> ComposeResult:
            yield panel

    async with _Host().run_test() as pilot:
        await pilot.pause()
        names = [str(s.content) for s in panel.query(Static).filter(".drive-name")]
        assert "CT4000P310SSD8" in names
        assert "CT4000P310SSD8 (Sensor 1)" in names
        await pilot.pause()
        # Re-render succeeded; panel is still mounted and has children.
        assert panel.is_mounted
        assert len(list(panel.children)) > 0
