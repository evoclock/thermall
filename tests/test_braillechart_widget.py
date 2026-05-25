# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the BrailleChart Textual widget."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from thermall.mapping import ThresholdSet
from thermall.widgets.braillechart import BrailleChart


class _Host(App[None]):
    def __init__(self, chart: BrailleChart) -> None:
        super().__init__()
        self._chart = chart

    def compose(self) -> ComposeResult:
        yield self._chart


class TestConstruction:
    def test_defaults(self) -> None:
        c = BrailleChart()
        assert c.samples == ()
        assert c.chart_width > 0
        assert c.chart_height > 0

    def test_with_samples(self) -> None:
        c = BrailleChart([1.0, 2.0, 3.0])
        assert c.samples == (1.0, 2.0, 3.0)

    def test_custom_dimensions(self) -> None:
        c = BrailleChart([1.0], width=12, height=2)
        assert c.chart_width == 12
        assert c.chart_height == 2

    def test_has_class(self) -> None:
        c = BrailleChart()
        assert "braillechart" in c.classes

    def test_preserves_custom_classes(self) -> None:
        c = BrailleChart(classes="my-extra")
        assert "braillechart" in c.classes
        assert "my-extra" in c.classes


class TestRendering:
    def test_empty_renders_n_a_labels(self) -> None:
        c = BrailleChart(width=4, height=2)
        content = str(c.content)
        assert "n/a" in content

    def test_with_data_renders_unit_in_labels(self) -> None:
        c = BrailleChart([20.0, 50.0], width=4, height=2, unit="°C")
        content = str(c.content)
        assert "50°C" in content
        assert "20°C" in content

    def test_height_matches_rows(self) -> None:
        c = BrailleChart([1.0, 2.0, 3.0], width=4, height=4)
        content = str(c.content)
        assert content.count("\n") == 3  # 4 rows = 3 newlines

    def test_setter_updates_content(self) -> None:
        c = BrailleChart([10.0, 10.0], width=4, height=2, unit="°C")
        before = str(c.content)
        c.samples = [10.0, 99.0]
        after = str(c.content)
        assert before != after
        assert "99°C" in after

    def test_thresholds_produce_rich_markup(self) -> None:
        # 5 samples in 4 char columns of 2 slots each + 3 padding:
        # char col 0 = padded, col 1 = OK only, col 2 = OK + WARN -> yellow,
        # col 3 = WARN + CRIT -> red. Covers all three severity colours.
        c = BrailleChart(
            [40.0, 50.0, 75.0, 80.0, 90.0],
            width=4,
            height=2,
            thresholds=ThresholdSet(category="cpu", warn=70.0, crit=85.0),
        )
        content = str(c.content)
        assert "green" in content
        assert "yellow" in content
        assert "red" in content


class TestMountLifecycle:
    @pytest.mark.asyncio
    async def test_mounts_in_app(self) -> None:
        c = BrailleChart([1.0, 2.0, 3.0, 4.0], width=10, height=3, unit="°C")
        app = _Host(c)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert c.is_mounted

    @pytest.mark.asyncio
    async def test_setter_post_mount(self) -> None:
        c = BrailleChart([1.0, 2.0], width=5, height=2, unit="°C")
        app = _Host(c)
        async with app.run_test() as pilot:
            await pilot.pause()
            before = str(c.content)
            c.samples = [50.0, 99.0]
            await pilot.pause()
            after = str(c.content)
            assert before != after
            assert "99°C" in after
