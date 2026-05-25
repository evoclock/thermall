# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for `thermall.braillechart.render_braille_chart`."""

from __future__ import annotations

import pytest

from thermall.braillechart import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    BrailleChart,
    render_braille_chart,
)
from thermall.mapping import ThresholdSet


class TestEmptyAndDefaults:
    def test_empty_values_blank_rows(self) -> None:
        chart = render_braille_chart([], width=5, height=2)
        assert chart.rows == ("⠀" * 5, "⠀" * 5)
        assert chart.min_label == "n/a"
        assert chart.max_label == "n/a"

    def test_default_dimensions(self) -> None:
        chart = render_braille_chart([45.0])
        assert chart.height == DEFAULT_HEIGHT
        # Each row should be DEFAULT_WIDTH characters long.
        for row in chart.rows:
            # Strip any rich markup before counting visible width.
            assert len([c for c in row if not c.startswith("[")]) >= DEFAULT_WIDTH

    def test_zero_width_rejected(self) -> None:
        with pytest.raises(ValueError, match="width"):
            render_braille_chart([1.0], width=0, height=3)

    def test_zero_height_rejected(self) -> None:
        with pytest.raises(ValueError, match="height"):
            render_braille_chart([1.0], width=3, height=0)

    def test_returns_braillechart(self) -> None:
        assert isinstance(render_braille_chart([1.0]), BrailleChart)


class TestFlatValues:
    def test_single_value_renders_baseline(self) -> None:
        chart = render_braille_chart([45.0], width=4, height=2, unit="°C")
        assert chart.min_label == chart.max_label == "45°C"
        # Some dots are set (not all empty braille).
        non_empty = [r for r in chart.rows if r.replace("⠀", "")]
        assert non_empty, "expected at least one row with set dots"

    def test_all_equal_renders_baseline(self) -> None:
        chart = render_braille_chart([42.0, 42.0, 42.0, 42.0], width=4, height=3)
        assert chart.min_label == chart.max_label


class TestAscendingDescending:
    def test_ascending_uses_increasing_dots(self) -> None:
        # 16 ascending values in 8-char wide (16 slots), 4 rows tall
        # (16 pixel rows). Each value should map to monotonically
        # increasing pixel heights.
        values = [10.0 * i for i in range(1, 17)]
        chart = render_braille_chart(values, width=8, height=4)
        # min and max labels reflect the range.
        assert chart.min_label == "10"
        assert chart.max_label == "160"
        # Bottom-row characters should have at least some dots set
        # (every column reaches the lower portion of the chart).
        bottom_row = chart.rows[-1]
        assert "⠀" not in bottom_row.replace("⠀", "X", 0)

    def test_descending_pattern(self) -> None:
        # Descending values should still produce a valid chart.
        values = [160.0 - 10.0 * i for i in range(16)]
        chart = render_braille_chart(values, width=8, height=4)
        assert chart.min_label == "10"
        assert chart.max_label == "160"


class TestSanitisation:
    def test_nan_handled(self) -> None:
        chart = render_braille_chart([10.0, float("nan"), 20.0], width=4, height=2)
        assert chart.min_label == "10"
        assert chart.max_label == "20"

    def test_inf_handled(self) -> None:
        chart = render_braille_chart([10.0, float("inf"), 20.0], width=4, height=2)
        assert chart.max_label == "20"

    def test_negative_handled(self) -> None:
        chart = render_braille_chart([-10.0, 0.0, 10.0], width=4, height=2, unit="°C")
        assert chart.min_label == "-10°C"
        assert chart.max_label == "10°C"


class TestUnits:
    def test_unit_in_labels(self) -> None:
        chart = render_braille_chart([20.0, 50.0], width=4, height=2, unit="°C")
        assert chart.min_label == "20°C"
        assert chart.max_label == "50°C"

    def test_no_unit(self) -> None:
        chart = render_braille_chart([20.0, 50.0], width=4, height=2)
        assert chart.min_label == "20"


class TestSeverityColouring:
    def _thresholds(self) -> ThresholdSet:
        return ThresholdSet(category="cpu", warn=70.0, crit=85.0)

    def test_no_thresholds_no_markup(self) -> None:
        # Without thresholds, characters render without Rich tags.
        chart = render_braille_chart([20.0, 50.0], width=4, height=2)
        for row in chart.rows:
            assert "[" not in row, "expected no markup when thresholds is None"

    def test_thresholds_apply_severity_colours(self) -> None:
        # All samples below warn -> green markup throughout.
        chart = render_braille_chart(
            [40.0, 50.0, 60.0],
            width=4,
            height=2,
            thresholds=self._thresholds(),
        )
        joined = "".join(chart.rows)
        assert "[green]" in joined
        assert "[yellow]" not in joined
        assert "[bold red]" not in joined

    def test_warn_samples_show_yellow(self) -> None:
        chart = render_braille_chart(
            [40.0, 75.0, 78.0],
            width=4,
            height=2,
            thresholds=self._thresholds(),
        )
        joined = "".join(chart.rows)
        assert "[yellow]" in joined

    def test_crit_samples_show_red(self) -> None:
        chart = render_braille_chart(
            [40.0, 75.0, 90.0],
            width=4,
            height=2,
            thresholds=self._thresholds(),
        )
        joined = "".join(chart.rows)
        assert "[bold red]" in joined

    def test_mixed_severity_column_takes_max(self) -> None:
        # A character covers 2 samples; if one is CRIT the column
        # must paint as CRIT regardless of the other.
        # [crit, ok] -> single char column -> crit colour.
        chart = render_braille_chart(
            [90.0, 40.0],
            width=1,
            height=2,
            thresholds=self._thresholds(),
        )
        joined = "".join(chart.rows)
        assert "[bold red]" in joined


class TestSize:
    def test_height_matches_request(self) -> None:
        chart = render_braille_chart([10.0, 50.0, 30.0], width=8, height=5)
        assert chart.height == 5

    def test_more_values_than_capacity_keeps_last(self) -> None:
        # width=2 means 4 sample slots; supplying 20 keeps last 4.
        values = [float(i) for i in range(20)]
        chart = render_braille_chart(values, width=2, height=2)
        # min label = 16 (the start of the kept slice)
        assert chart.min_label == "16"
        assert chart.max_label == "19"
