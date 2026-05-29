# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for `ThresholdLabel` (the per-Reading display widget).

Pilot-style tests mount the widget in a minimal Textual `App`, let it
render, then inspect the widget's `renderable` (the Rich Text the
Static will display). Colour styling is verified by checking the
Rich-markup string emitted, since pixel-level colour assertions are
brittle across terminals.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from thermall.mapping import ThresholdSet
from thermall.model import Reading, Severity
from thermall.widgets.threshold_label import ThresholdLabel


def _cpu_thresholds() -> ThresholdSet:
    return ThresholdSet(
        category="cpu",
        warn=80.0,
        crit=90.0,
        severity_phrases={
            Severity.OK: "cool",
            Severity.WARN: "CPU running hot",
            Severity.CRIT: "CPU critical",
        },
    )


def _reading(
    raw_label: str = "k10temp Tctl",
    value: float = 50.0,
    unit: str = "C",
    severity: Severity = Severity.OK,
    display_label: str | None = "CPU package",
) -> Reading:
    return Reading(
        raw_label=raw_label,
        value=value,
        unit=unit,
        display_label=display_label,
        severity=severity,
    )


class _OneWidgetApp(App[None]):
    def __init__(self, widget: ThresholdLabel) -> None:
        super().__init__()
        self._widget = widget

    def compose(self) -> ComposeResult:
        yield self._widget


def _rendered_markup(widget: ThresholdLabel) -> str:
    """Return the Rich markup string the widget is configured to display.

    Calls `ThresholdLabel._format` directly (the same path
    `__init__` and the `reading` setter take). Tests assert against
    this string for both text-content checks (`"CPU package" in s`)
    and styling checks (`"[green]" in s`); the markup string
    contains both because Rich markup is inline.
    """

    return widget._format(widget.reading)


# Convenience alias for tests that read clearer when the variable name
# implies "the text the user will see". The underlying value is the
# same markup string; substring checks work for both text and tags.
_rendered_text = _rendered_markup


# ---------------------------------------------------------------------------
# Severity-driven rendering: happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_renders_ok_severity_with_phrase_and_theme_success_colour() -> None:
    widget = ThresholdLabel(
        _reading(severity=Severity.OK, value=50.0),
        _cpu_thresholds(),
        id="lbl",
    )
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        text = _rendered_text(widget)
        markup = _rendered_markup(widget)
        assert "CPU package" in text
        assert "50.0" in text
        assert "°C" in text
        assert "cool" in text
        # Severity colour comes from the active theme's success token.
        # Pin against that rather than a hard-coded "green" so the
        # widget remains theme-aware.
        expected = str(pilot.app.current_theme.success)
        assert f"[{expected}]" in markup
        assert f"[/{expected}]" in markup


@pytest.mark.asyncio
async def test_renders_warn_severity_with_category_phrase_and_theme_warning_colour() -> None:
    widget = ThresholdLabel(
        _reading(severity=Severity.WARN, value=85.0),
        _cpu_thresholds(),
    )
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        text = _rendered_text(widget)
        markup = _rendered_markup(widget)
        assert "CPU running hot" in text
        expected = str(pilot.app.current_theme.warning)
        assert f"[{expected}]" in markup


@pytest.mark.asyncio
async def test_renders_crit_severity_with_bold_theme_error_colour() -> None:
    widget = ThresholdLabel(
        _reading(severity=Severity.CRIT, value=95.0),
        _cpu_thresholds(),
    )
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        text = _rendered_text(widget)
        markup = _rendered_markup(widget)
        assert "CPU critical" in text
        # CRIT gets a `bold ` prefix on top of the theme's error colour.
        expected = f"bold {pilot.app.current_theme.error}"
        assert f"[{expected}]" in markup
        assert f"[/{expected}]" in markup


@pytest.mark.asyncio
async def test_renders_unknown_severity_with_dim_and_no_reading_phrase() -> None:
    # No category override for UNKNOWN; falls back to DEFAULT_PHRASES.
    widget = ThresholdLabel(
        _reading(severity=Severity.UNKNOWN, value=0.0),
        _cpu_thresholds(),
    )
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        text = _rendered_text(widget)
        markup = _rendered_markup(widget)
        assert "no reading" in text
        assert "[dim]" in markup


# ---------------------------------------------------------------------------
# Formatting: numbers, units, labels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_formats_value_with_one_decimal() -> None:
    widget = ThresholdLabel(
        _reading(value=42.123, severity=Severity.OK),
        _cpu_thresholds(),
    )
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        assert "42.1" in _rendered_text(widget)
        # And no longer-precision artefact:
        assert "42.123" not in _rendered_text(widget)


@pytest.mark.asyncio
async def test_celsius_unit_renders_as_degree_glyph() -> None:
    widget = ThresholdLabel(
        _reading(unit="C", value=40.0, severity=Severity.OK),
        _cpu_thresholds(),
    )
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        assert "°C" in _rendered_text(widget)


@pytest.mark.asyncio
async def test_non_celsius_unit_passes_through_unchanged() -> None:
    widget = ThresholdLabel(
        _reading(unit="RPM", value=1200.0, severity=Severity.OK),
        _cpu_thresholds(),
    )
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        text = _rendered_text(widget)
        assert "RPM" in text
        # No °C glyph snuck in for a non-Celsius unit
        assert "°C" not in text


@pytest.mark.asyncio
async def test_uses_display_label_when_present() -> None:
    widget = ThresholdLabel(
        _reading(display_label="CPU package", raw_label="k10temp Tctl"),
        _cpu_thresholds(),
    )
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        text = _rendered_text(widget)
        assert "CPU package" in text
        assert "k10temp Tctl" not in text


@pytest.mark.asyncio
async def test_falls_back_to_raw_label_when_display_label_none() -> None:
    widget = ThresholdLabel(
        _reading(display_label=None, raw_label="k10temp Tctl"),
        _cpu_thresholds(),
    )
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        text = _rendered_text(widget)
        assert "k10temp Tctl" in text


# ---------------------------------------------------------------------------
# Reactivity: assigning a new reading updates the render
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_updates_on_reading_change() -> None:
    initial = _reading(value=50.0, severity=Severity.OK)
    widget = ThresholdLabel(initial, _cpu_thresholds())
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        assert "50.0" in _rendered_text(widget)
        assert "cool" in _rendered_text(widget)

        # Assign a hotter reading; widget should re-render.
        widget.reading = _reading(value=92.0, severity=Severity.CRIT)
        await pilot.pause()
        text = _rendered_text(widget)
        assert "92.0" in text
        assert "CPU critical" in text
        assert "50.0" not in text


@pytest.mark.asyncio
async def test_reading_property_returns_current_reading() -> None:
    r = _reading(value=70.0, severity=Severity.OK)
    widget = ThresholdLabel(r, _cpu_thresholds())
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        assert widget.reading is r
        new_r = _reading(value=82.0, severity=Severity.WARN)
        widget.reading = new_r
        await pilot.pause()
        assert widget.reading is new_r


# ---------------------------------------------------------------------------
# Edge cases: extreme / unusual readings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handles_zero_value() -> None:
    widget = ThresholdLabel(
        _reading(value=0.0, severity=Severity.OK),
        _cpu_thresholds(),
    )
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        assert "0.0°C" in _rendered_text(widget)


@pytest.mark.asyncio
async def test_handles_negative_value() -> None:
    widget = ThresholdLabel(
        _reading(value=-10.0, severity=Severity.OK),
        _cpu_thresholds(),
    )
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        assert "-10.0°C" in _rendered_text(widget)


@pytest.mark.asyncio
async def test_handles_very_large_value() -> None:
    # An NVMe sensor occasionally returns garbage like 65261 (a known
    # uninitialised marker). Widget must not crash or overflow.
    widget = ThresholdLabel(
        _reading(value=65261.85, severity=Severity.CRIT),
        _cpu_thresholds(),
    )
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        text = _rendered_text(widget)
        assert "65261.8" in text or "65261.9" in text  # rounding to 1dp


@pytest.mark.asyncio
async def test_handles_empty_raw_label() -> None:
    widget = ThresholdLabel(
        _reading(raw_label="", display_label=None, severity=Severity.OK),
        _cpu_thresholds(),
    )
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        text = _rendered_text(widget)
        # Format is "<label>: <value>..."; an empty label yields ": 50.0..."
        # Widget must not crash; we don't assert on the label content
        # because the empty case is degenerate.
        assert "50.0" in text


@pytest.mark.asyncio
async def test_handles_empty_unit() -> None:
    widget = ThresholdLabel(
        _reading(unit="", value=42.0, severity=Severity.OK),
        _cpu_thresholds(),
    )
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        text = _rendered_text(widget)
        assert "42.0" in text


@pytest.mark.asyncio
async def test_widget_does_not_re_grade_reading() -> None:
    # ThresholdLabel must trust the reading's severity field; it MUST
    # NOT call thresholds.grade(value) and override. Verify by passing
    # a CRIT-severity reading with a value that would grade OK; the
    # widget should render CRIT styling regardless.
    cool_value_but_crit_severity = _reading(value=30.0, severity=Severity.CRIT)
    widget = ThresholdLabel(cool_value_but_crit_severity, _cpu_thresholds())
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        markup = _rendered_markup(widget)
        # The widget rendered the CRIT styling (bold + theme error),
        # not OK (theme success), despite the value being below the
        # warn threshold.
        theme = pilot.app.current_theme
        expected_crit = f"bold {theme.error}"
        expected_ok = str(theme.success)
        assert f"[{expected_crit}]" in markup
        assert f"[{expected_ok}]" not in markup


@pytest.mark.asyncio
async def test_uses_phrases_from_supplied_thresholds_not_global() -> None:
    # If the panel supplies category-specific phrases, the widget must
    # use those, not the global DEFAULT_PHRASES.
    custom_thresholds = ThresholdSet(
        category="custom",
        warn=80.0,
        crit=90.0,
        severity_phrases={
            Severity.OK: "all clear",
            Severity.WARN: "watch this",
            Severity.CRIT: "investigate",
        },
    )
    widget = ThresholdLabel(_reading(severity=Severity.WARN), custom_thresholds)
    async with _OneWidgetApp(widget).run_test() as pilot:
        await pilot.pause()
        text = _rendered_text(widget)
        assert "watch this" in text
        assert "CPU running hot" not in text  # the default cpu phrase
