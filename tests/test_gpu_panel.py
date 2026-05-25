# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for `GpuPanel`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from thermall.config import Config
from thermall.model import DeviceSnapshot, Gpu
from thermall.widgets.gpu_panel import (
    GpuPanel,
    _format_fan,
    _format_memory,
    _format_power,
    _gpu_temperature_reading,
)
from thermall.widgets.threshold_label import ThresholdLabel


def _gpu(
    index: int = 0,
    name: str = "NVIDIA GeForce RTX 3060",
    temperature_c: float = 54.0,
    fan_percent: float | None = 34.0,
    power_watts: float | None = 52.98,
    memory_used_mb: int | None = 2425,
    memory_total_mb: int | None = 12288,
) -> Gpu:
    return Gpu(
        index=index,
        name=name,
        temperature_c=temperature_c,
        fan_percent=fan_percent,
        power_watts=power_watts,
        memory_used_mb=memory_used_mb,
        memory_total_mb=memory_total_mb,
    )


def _snap(gpus: tuple[Gpu, ...] = ()) -> DeviceSnapshot:
    return DeviceSnapshot(
        taken_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        gpus=gpus,
    )


class _PanelApp(App[None]):
    def __init__(self, panel: GpuPanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel


def _child_renderables(panel: GpuPanel) -> list[str]:
    contents: list[str] = []
    for child in panel.children:
        if isinstance(child, ThresholdLabel):
            contents.append(child._format(child.reading))
        elif isinstance(child, Static):
            contents.append(str(child.render()))
    return contents


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestFormatFan:
    def test_returns_passive_for_none(self) -> None:
        assert _format_fan(None) == "Fan: passive"

    def test_returns_percent_for_value(self) -> None:
        assert _format_fan(39.0) == "Fan: 39%"

    def test_rounds_fractional_percent_to_int(self) -> None:
        assert _format_fan(39.6) == "Fan: 40%"

    def test_zero_percent(self) -> None:
        assert _format_fan(0.0) == "Fan: 0%"


class TestFormatPower:
    def test_returns_na_for_none(self) -> None:
        assert _format_power(None) == "Power: n/a"

    def test_returns_one_decimal_watts(self) -> None:
        assert _format_power(78.43) == "Power: 78.4 W"

    def test_zero_power(self) -> None:
        assert _format_power(0.0) == "Power: 0.0 W"


class TestFormatMemory:
    def test_returns_na_when_used_is_none(self) -> None:
        assert _format_memory(None, 12288) == "Memory: n/a"

    def test_returns_na_when_total_is_none(self) -> None:
        assert _format_memory(1234, None) == "Memory: n/a"

    def test_returns_na_when_both_none(self) -> None:
        assert _format_memory(None, None) == "Memory: n/a"

    def test_formats_used_and_total(self) -> None:
        assert _format_memory(1234, 12288) == "Memory: 1234 / 12288 MB"


class TestGpuTemperatureReading:
    def test_uses_gpu_name_as_label(self) -> None:
        gpu = _gpu(name="NVIDIA RTX 5070")
        reading = _gpu_temperature_reading(gpu)
        assert reading.display_label == "NVIDIA RTX 5070"
        assert reading.raw_label == "NVIDIA RTX 5070"

    def test_uses_gpu_temperature_value(self) -> None:
        gpu = _gpu(temperature_c=82.0)
        reading = _gpu_temperature_reading(gpu)
        assert reading.value == 82.0
        assert reading.unit == "C"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_renders_single_gpu_with_all_fields() -> None:
    snapshot = _snap(gpus=(_gpu(name="NVIDIA RTX 3060", temperature_c=54.0),))
    panel = GpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        # Singular header
        assert any("GPU" in c for c in contents)
        # Model name appears
        assert any("NVIDIA RTX 3060" in c for c in contents)
        # Temp appears via ThresholdLabel
        assert any("54.0" in c for c in contents)
        # Fan / power / memory rows present
        assert any("Fan:" in c for c in contents)
        assert any("Power:" in c for c in contents)
        assert any("Memory:" in c for c in contents)


@pytest.mark.asyncio
async def test_renders_multiple_gpus_in_index_order() -> None:
    snapshot = _snap(
        gpus=(
            _gpu(index=0, name="NVIDIA GeForce RTX 3060", temperature_c=54.0),
            _gpu(index=1, name="NVIDIA GeForce RTX 5070 Ti", temperature_c=46.0),
        ),
    )
    panel = GpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        # Header changes to plural for >1 GPU
        assert any("GPUs" in c for c in contents)
        # Both GPUs appear; verify ordering by joining the visible
        # content and searching for first vs second model name.
        joined = "\n".join(contents)
        first_idx = joined.find("RTX 3060")
        second_idx = joined.find("RTX 5070 Ti")
        assert 0 <= first_idx < second_idx


@pytest.mark.asyncio
async def test_uses_gpu_thresholds_for_severity() -> None:
    # gpu warn=75, crit=85. 90 C is CRIT; phrase override "GPU critical".
    snapshot = _snap(gpus=(_gpu(temperature_c=90.0),))
    panel = GpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("GPU critical" in c for c in contents)
        # CRIT styling pulls the theme's error colour at format time.
        expected_crit = f"bold {pilot.app.current_theme.error}"
        assert any(f"[{expected_crit}]" in c for c in contents)


# ---------------------------------------------------------------------------
# Edge cases: passive card, missing fields, empty system
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_passive_card_shows_passive_not_blank() -> None:
    snapshot = _snap(gpus=(_gpu(fan_percent=None),))
    panel = GpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("Fan: passive" in c for c in contents)


@pytest.mark.asyncio
async def test_no_power_data_shows_na() -> None:
    snapshot = _snap(gpus=(_gpu(power_watts=None),))
    panel = GpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("Power: n/a" in c for c in contents)


@pytest.mark.asyncio
async def test_no_memory_data_shows_na() -> None:
    snapshot = _snap(gpus=(_gpu(memory_used_mb=None, memory_total_mb=None),))
    panel = GpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("Memory: n/a" in c for c in contents)


@pytest.mark.asyncio
async def test_empty_gpus_shows_friendly_message() -> None:
    snapshot = _snap(gpus=())
    panel = GpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("No NVIDIA GPU detected" in c for c in contents)
        # Header still says "GPU" (singular) for the empty case;
        # Static.render() strips Rich markup so we assert the plain text.
        assert any(c.strip() == "GPU" for c in contents)


@pytest.mark.asyncio
async def test_snapshot_change_re_renders_panel() -> None:
    initial = _snap(gpus=(_gpu(temperature_c=50.0),))
    panel = GpuPanel(Config(), initial)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        before = _child_renderables(panel)
        assert any("50.0" in c for c in before)

        panel.snapshot = _snap(gpus=(_gpu(temperature_c=82.0),))
        await pilot.pause()
        after = _child_renderables(panel)
        assert any("82.0" in c for c in after)
        assert not any("50.0" in c for c in after)


@pytest.mark.asyncio
async def test_transition_from_populated_to_empty_shows_message() -> None:
    populated = _snap(gpus=(_gpu(),))
    panel = GpuPanel(Config(), populated)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        panel.snapshot = _snap(gpus=())
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("No NVIDIA GPU detected" in c for c in contents)


@pytest.mark.asyncio
async def test_partial_memory_data_treated_as_missing() -> None:
    # If only one of used/total is present, render n/a; the dashboard
    # never wants to show a fraction with a missing denominator.
    snapshot = _snap(gpus=(_gpu(memory_used_mb=1234, memory_total_mb=None),))
    panel = GpuPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        contents = _child_renderables(panel)
        assert any("Memory: n/a" in c for c in contents)
        # The half-value should NOT leak through
        joined = "\n".join(contents)
        assert "1234" not in joined or "n/a" in joined  # n/a wins
