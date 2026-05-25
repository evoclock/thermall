# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for `CpuPanel`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from thermall.config import Config
from thermall.model import DeviceSnapshot, Fan, Reading
from thermall.widgets.cpu_panel import CpuPanel, _is_cpu_fan
from thermall.widgets.threshold_label import ThresholdLabel


def _snap(
    cpu_temps: tuple[Reading, ...] = (),
    fans: tuple[Fan, ...] = (),
) -> DeviceSnapshot:
    return DeviceSnapshot(
        taken_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        cpu_temps=cpu_temps,
        fans=fans,
    )


def _reading(
    raw_label: str = "k10temp Tctl",
    value: float = 50.0,
    unit: str = "C",
    display_label: str | None = None,
) -> Reading:
    return Reading(
        raw_label=raw_label,
        value=value,
        unit=unit,
        display_label=display_label,
    )


class _PanelApp(App[None]):
    def __init__(self, panel: CpuPanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel


def _child_renderables(panel: CpuPanel) -> list[str]:
    """Return the rendered (markup) content of each Static / ThresholdLabel child."""

    contents: list[str] = []
    for child in panel.children:
        if isinstance(child, ThresholdLabel):
            # Pull the markup via the same path the widget itself uses.
            contents.append(child._format(child.reading))
        elif isinstance(child, Static):
            renderable = child.render()
            contents.append(str(renderable))
    return contents


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_panel_renders_header_and_per_ccd_readings() -> None:
    snapshot = _snap(
        cpu_temps=(
            _reading("k10temp Tctl", 50.0, display_label="CPU package"),
            _reading("k10temp Tccd1", 48.0, display_label="CPU CCD1"),
            _reading("k10temp Tccd2", 47.0, display_label="CPU CCD2"),
        ),
    )
    panel = CpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("CPU" in c for c in contents)
        assert any("CPU package" in c for c in contents)
        assert any("CPU CCD1" in c for c in contents)
        assert any("CPU CCD2" in c for c in contents)
        # One ThresholdLabel per cpu reading
        labels = [c for c in panel.children if isinstance(c, ThresholdLabel)]
        assert len(labels) == 3


@pytest.mark.asyncio
async def test_panel_shows_cpu_fan_row_when_fan_label_contains_cpu_word() -> None:
    snapshot = _snap(
        cpu_temps=(_reading(),),
        fans=(
            Fan(raw_label="fan1", rpm=1450, display_label="CPU fan"),
            Fan(raw_label="fan3", rpm=900, display_label="Chassis front"),
        ),
    )
    panel = CpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        # The CPU fan appears
        assert any("CPU fan" in c and "1450 RPM" in c for c in contents)
        # The chassis fan does NOT appear in this panel
        assert not any("Chassis front" in c for c in contents)


@pytest.mark.asyncio
async def test_panel_marks_stopped_cpu_fan() -> None:
    snapshot = _snap(
        cpu_temps=(_reading(),),
        fans=(Fan(raw_label="cpu_fan", rpm=0),),
    )
    panel = CpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("Stopped" in c for c in contents)


@pytest.mark.asyncio
async def test_panel_uses_severity_phrase_from_threshold_set() -> None:
    # 85 C is between cpu warn=80 and crit=90, so severity is WARN and
    # the phrase should be the per-category "CPU running hot".
    snapshot = _snap(
        cpu_temps=(_reading("k10temp Tctl", 85.0, display_label="CPU package"),),
    )
    panel = CpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("CPU running hot" in c for c in contents)


# ---------------------------------------------------------------------------
# Edge cases: empty / missing / unusual data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_panel_shows_friendly_install_hint_when_no_cpu_temps() -> None:
    snapshot = _snap(cpu_temps=())
    panel = CpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        # No ThresholdLabel children (no readings)
        assert not any(isinstance(c, ThresholdLabel) for c in panel.children)
        # The install hint is present
        assert any("lm-sensors" in c for c in contents)
        assert any("sensors-detect" in c for c in contents)


@pytest.mark.asyncio
async def test_panel_with_no_fans_does_not_show_fan_row() -> None:
    snapshot = _snap(
        cpu_temps=(_reading(),),
        fans=(),
    )
    panel = CpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        assert not any("RPM" in c for c in contents)


@pytest.mark.asyncio
async def test_panel_handles_extreme_temp_without_crash() -> None:
    snapshot = _snap(cpu_temps=(_reading(value=999.0),))
    panel = CpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        # Did not raise; 999 C grades CRIT and shows the CPU critical phrase.
        contents = _child_renderables(panel)
        assert any("CPU critical" in c for c in contents)


@pytest.mark.asyncio
async def test_panel_handles_negative_temp_without_misclassifying_severity() -> None:
    # Some sensors report negative temps when offline. Negative values
    # are below the warn threshold, so severity should be OK.
    snapshot = _snap(cpu_temps=(_reading(value=-10.0),))
    panel = CpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        # "cool" is the OK phrase for cpu (instance override -> "cool")
        assert any("cool" in c for c in contents)


# ---------------------------------------------------------------------------
# Reactivity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_panel_updates_on_snapshot_change() -> None:
    initial = _snap(cpu_temps=(_reading(value=50.0),))
    panel = CpuPanel(Config(), initial)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        before = _child_renderables(panel)
        assert any("50.0" in c for c in before)

        # Replace the snapshot with one whose reading is much hotter
        panel.snapshot = _snap(cpu_temps=(_reading(value=92.0),))
        await pilot.pause()

        after = _child_renderables(panel)
        assert any("92.0" in c for c in after)
        # Old reading is no longer rendered
        assert not any("50.0" in c for c in after)


@pytest.mark.asyncio
async def test_snapshot_change_from_populated_to_empty_shows_hint() -> None:
    populated = _snap(cpu_temps=(_reading(),))
    panel = CpuPanel(Config(), populated)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        # Now drop to empty cpu_temps
        panel.snapshot = _snap(cpu_temps=())
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("lm-sensors" in c for c in contents)


# ---------------------------------------------------------------------------
# `_is_cpu_fan` helper coverage (pure logic, no widget)
# ---------------------------------------------------------------------------


class TestIsCpuFan:
    def test_matches_when_raw_label_is_cpu_word(self) -> None:
        assert _is_cpu_fan(Fan(raw_label="cpu", rpm=1000)) is True

    def test_matches_when_raw_label_contains_cpu_token(self) -> None:
        assert _is_cpu_fan(Fan(raw_label="cpu_fan", rpm=1000)) is True

    def test_matches_via_display_label(self) -> None:
        assert _is_cpu_fan(Fan(raw_label="fan1", rpm=1000, display_label="CPU fan")) is True

    def test_does_not_match_chassis_fan(self) -> None:
        assert _is_cpu_fan(Fan(raw_label="fan3", rpm=900, display_label="Chassis front")) is False

    def test_does_not_match_cputin_substring(self) -> None:
        # CPUTIN is a chassis-area temperature sensor name that can leak
        # into fan-channel naming on some boards; the discrete-word
        # check must reject it.
        assert _is_cpu_fan(Fan(raw_label="cputin_fan", rpm=900)) is False

    def test_does_not_match_unrelated_fan_with_no_display_label(self) -> None:
        assert _is_cpu_fan(Fan(raw_label="fan1", rpm=1500)) is False

    def test_case_insensitive(self) -> None:
        assert _is_cpu_fan(Fan(raw_label="CPU", rpm=1000)) is True
