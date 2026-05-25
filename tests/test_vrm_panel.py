# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for `VrmPanel`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from thermall.config import Config
from thermall.model import DeviceSnapshot, Reading
from thermall.widgets.threshold_label import ThresholdLabel
from thermall.widgets.vrm_panel import VrmPanel


def _snap(vrm_temps: tuple[Reading, ...] = ()) -> DeviceSnapshot:
    return DeviceSnapshot(
        taken_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        vrm_temps=vrm_temps,
    )


def _reading(
    raw_label: str = "nct6798 AUXTIN0",
    value: float = 50.0,
    display_label: str | None = None,
) -> Reading:
    return Reading(
        raw_label=raw_label,
        value=value,
        unit="C",
        display_label=display_label,
    )


class _PanelApp(App[None]):
    def __init__(self, panel: VrmPanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel


def _child_renderables(panel: VrmPanel) -> list[str]:
    contents: list[str] = []
    for child in panel.children:
        if isinstance(child, ThresholdLabel):
            contents.append(child._format(child.reading))
        elif isinstance(child, Static):
            contents.append(str(child.render()))
    return contents


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_renders_all_auxtin_readings_with_resolved_labels() -> None:
    snapshot = _snap(
        vrm_temps=(
            _reading("nct6798 AUXTIN0", 45.0, display_label="VRM (CPU)"),
            _reading("nct6798 AUXTIN1", 38.0, display_label="PCH"),
            _reading("nct6798 AUXTIN2", 50.0, display_label="VRM (SoC)"),
            _reading("nct6798 AUXTIN3", 41.0),  # unmapped; falls back to raw
            _reading("nct6798 AUXTIN4", 39.0),
        ),
    )
    panel = VrmPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        # Header is shown
        assert any("Motherboard / VRM" in c for c in contents)
        # Resolved labels appear
        assert any("VRM (CPU)" in c for c in contents)
        assert any("PCH" in c for c in contents)
        assert any("VRM (SoC)" in c for c in contents)
        # Unmapped readings fall back to raw label
        assert any("nct6798 AUXTIN3" in c for c in contents)
        assert any("nct6798 AUXTIN4" in c for c in contents)
        # One ThresholdLabel per reading
        labels = [c for c in panel.children if isinstance(c, ThresholdLabel)]
        assert len(labels) == 5


@pytest.mark.asyncio
async def test_uses_vrm_thresholds_for_severity_phrase() -> None:
    # vrm warn=90, crit=100. 95 C is WARN; phrase should be the
    # category override "VRM running hot".
    snapshot = _snap(
        vrm_temps=(_reading("nct6798 AUXTIN0", 95.0, display_label="VRM (CPU)"),),
    )
    panel = VrmPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("VRM running hot" in c for c in contents)


@pytest.mark.asyncio
async def test_crit_temperature_gets_crit_phrase_and_styling() -> None:
    snapshot = _snap(vrm_temps=(_reading(value=110.0),))
    panel = VrmPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("VRM critical" in c for c in contents)
        # Crit gets `bold <theme.error>` styling via ThresholdLabel;
        # ThresholdLabel resolves the colour against the active app
        # theme so we read it from the pilot's app to stay
        # theme-agnostic.
        expected_crit = f"bold {pilot.app.current_theme.error}"
        assert any(f"[{expected_crit}]" in c for c in contents)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_vrm_temps_shows_nct6775_install_hint() -> None:
    snapshot = _snap(vrm_temps=())
    panel = VrmPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        # The friendly hint appears
        assert any("nct6775" in c for c in contents)
        # The "Nuvoton" callout is in the hint
        assert any("Nuvoton" in c for c in contents)
        # No ThresholdLabel children
        assert not any(isinstance(c, ThresholdLabel) for c in panel.children)


@pytest.mark.asyncio
async def test_panel_updates_on_snapshot_change() -> None:
    initial = _snap(vrm_temps=(_reading(value=50.0),))
    panel = VrmPanel(Config(), initial)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        before = _child_renderables(panel)
        assert any("50.0" in c for c in before)

        # Replace with a hotter snapshot
        panel.snapshot = _snap(vrm_temps=(_reading(value=98.0),))
        await pilot.pause()
        after = _child_renderables(panel)
        assert any("98.0" in c for c in after)
        assert not any("50.0" in c for c in after)


@pytest.mark.asyncio
async def test_panel_handles_unmapped_label_falls_back_to_raw_label() -> None:
    snapshot = _snap(vrm_temps=(_reading("nct6798 AUXTIN0", 60.0, display_label=None),))
    panel = VrmPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("nct6798 AUXTIN0" in c for c in contents)


@pytest.mark.asyncio
async def test_snapshot_change_from_populated_to_empty_shows_hint() -> None:
    populated = _snap(vrm_temps=(_reading(),))
    panel = VrmPanel(Config(), populated)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        panel.snapshot = _snap(vrm_temps=())
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("nct6775" in c for c in contents)
        assert not any(isinstance(c, ThresholdLabel) for c in panel.children)


@pytest.mark.asyncio
async def test_panel_handles_extreme_temp_without_crash() -> None:
    snapshot = _snap(vrm_temps=(_reading(value=999.0),))
    panel = VrmPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        # Did not raise; very high value still grades CRIT cleanly.
        contents = _child_renderables(panel)
        assert any("VRM critical" in c for c in contents)


@pytest.mark.asyncio
async def test_panel_handles_negative_temp() -> None:
    snapshot = _snap(vrm_temps=(_reading(value=-5.0),))
    panel = VrmPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        # Negative is well below warn (90), so OK ("cool")
        assert any("cool" in c for c in contents)
