# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the StatusHeader widget."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from textual.app import App, ComposeResult

from thermall.model import (
    DeviceSnapshot,
    DriveHealthEvent,
    Fan,
    Gpu,
    NvmeDrive,
    Reading,
    Severity,
)
from thermall.widgets.status_header import StatusHeader


class StatusHeaderApp(App[None]):
    """Test app that mounts a StatusHeader widget."""

    def __init__(self, snapshot: DeviceSnapshot | None = None) -> None:
        super().__init__()
        self.snapshot = snapshot

    def compose(self) -> ComposeResult:
        yield StatusHeader(snapshot=self.snapshot)


def _snap(
    cpu_temps: tuple[Reading, ...] = (),
    vrm_temps: tuple[Reading, ...] = (),
    other_temps: tuple[Reading, ...] = (),
    fans: tuple[Fan, ...] = (),
    gpus: tuple[Gpu, ...] = (),
    nvmes: tuple[NvmeDrive, ...] = (),
    drive_health_events: tuple[DriveHealthEvent, ...] = (),
    warnings: tuple[str, ...] = (),
) -> DeviceSnapshot:
    return DeviceSnapshot(
        taken_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        cpu_temps=cpu_temps,
        vrm_temps=vrm_temps,
        other_temps=other_temps,
        fans=fans,
        gpus=gpus,
        nvmes=nvmes,
        drive_health_events=drive_health_events,
        warnings=warnings,
    )


def _reading(
    raw_label: str = "k10temp Tctl",
    value: float = 50.0,
    unit: str = "°C",
    display_label: str | None = None,
    severity: Severity = Severity.OK,
) -> Reading:
    return Reading(
        raw_label=raw_label,
        value=value,
        unit=unit,
        display_label=display_label,
        severity=severity,
    )


# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_header_renders_ok_state() -> None:
    snapshot = _snap(
        cpu_temps=(_reading(value=45.0),),
        vrm_temps=(_reading(raw_label="vrm", value=40.0),),
    )
    widget = StatusHeader(snapshot=snapshot)
    async with StatusHeaderApp(snapshot=snapshot).run_test() as pilot:
        await pilot.pause()
        # Widget renders OK state
        content = widget.render()
        assert "Everything cool" in str(content)


@pytest.mark.asyncio
async def test_status_header_renders_warn_state() -> None:
    snapshot = _snap(
        cpu_temps=(_reading(value=85.0, display_label="CPU package", severity=Severity.WARN),),
    )
    widget = StatusHeader(snapshot=snapshot)
    async with StatusHeaderApp(snapshot=snapshot).run_test() as pilot:
        await pilot.pause()
        content = widget.render()
        assert "Running warm" in str(content)


@pytest.mark.asyncio
async def test_status_header_renders_crit_state() -> None:
    snapshot = _snap(
        other_temps=(
            _reading(
                raw_label="nvme", value=82.0, display_label="NVMe drive", severity=Severity.CRIT
            ),
        ),
    )
    widget = StatusHeader(snapshot=snapshot)
    async with StatusHeaderApp(snapshot=snapshot).run_test() as pilot:
        await pilot.pause()
        content = widget.render()
        assert "Needs attention" in str(content)


@pytest.mark.asyncio
async def test_status_header_renders_unknown_state() -> None:
    snapshot = _snap()
    widget = StatusHeader(snapshot=snapshot)
    async with StatusHeaderApp(snapshot=snapshot).run_test() as pilot:
        await pilot.pause()
        content = widget.render()
        # Should have either "No data" or "Waiting"
        text = str(content)
        assert "No data" in text or "Waiting" in text


# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_header_updates_on_snapshot_change() -> None:
    ok_snapshot = _snap(cpu_temps=(_reading(value=45.0),))
    crit_snapshot = _snap(
        other_temps=(_reading(raw_label="nvme", value=82.0, severity=Severity.CRIT),)
    )

    app = StatusHeaderApp(snapshot=ok_snapshot)
    async with app.run_test() as pilot:
        widget = app.query_one(StatusHeader)

        # Initially OK
        assert "Everything cool" in str(widget.render())

        # Update to CRIT
        widget.snapshot = crit_snapshot
        await pilot.pause()

        # Now shows CRIT
        assert "Needs attention" in str(widget.render())


@pytest.mark.asyncio
async def test_status_header_picks_highest_severity_when_mixed() -> None:
    snapshot = _snap(
        cpu_temps=(_reading(value=80.0, severity=Severity.WARN),),
        gpus=(
            Gpu(
                index=0,
                name="GPU0",
                temperature_c=95.0,
                fan_percent=50.0,
                power_watts=250.0,
                memory_used_mb=4096,
                memory_total_mb=8192,
                severity=Severity.CRIT,
            ),
        ),
    )
    widget = StatusHeader(snapshot=snapshot)
    async with StatusHeaderApp(snapshot=snapshot).run_test() as pilot:
        await pilot.pause()
        content = widget.render()
        # Should show CRIT, not WARN
        assert "Needs attention" in str(content)


@pytest.mark.asyncio
async def test_status_header_handles_warnings_only() -> None:
    snapshot = _snap(warnings=("fan6 stopped",))
    widget = StatusHeader(snapshot=snapshot)
    async with StatusHeaderApp(snapshot=snapshot).run_test() as pilot:
        await pilot.pause()
        content = widget.render()
        text = str(content)
        assert "fan6" in text


@pytest.mark.asyncio
async def test_status_header_sub_line_uses_display_label() -> None:
    snapshot = _snap(
        cpu_temps=(
            _reading(
                raw_label="k10temp Tctl",
                value=85.0,
                display_label="CPU package",
                severity=Severity.WARN,
            ),
        ),
    )
    widget = StatusHeader(snapshot=snapshot)
    async with StatusHeaderApp(snapshot=snapshot).run_test() as pilot:
        await pilot.pause()
        content = widget.render()
        text = str(content)
        # Should have "CPU package", not raw "k10temp"
        assert "CPU package" in text
        assert "k10temp" not in text
