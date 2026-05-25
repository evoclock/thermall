# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Per-Reading display widget with severity colour-coding.

`ThresholdLabel` is the keystone widget consumed by every per-category
panel (CPU, VRM, GPU, Storage, Fans). It renders one line of the form

    <label>: <value:.1f><unit>  <phrase>

with colour derived from the reading's `severity`. It does not re-grade;
the panel that owns it grades readings via `mapping.grade_reading` or
`mapping.grade_many` before assignment.
"""

from __future__ import annotations

from typing import Any

from textual.widgets import Static

from thermall.mapping import ThresholdSet
from thermall.model import Reading, Severity

# Fallback severity colours used when the widget is rendered outside
# a Textual app context (e.g. unit tests that construct without
# mounting). When mounted, the active theme's success / warning /
# error colours are read at format time so the label adapts to the
# user's chosen retro palette instead of clashing.
_FALLBACK_SEVERITY_MARKUP: dict[Severity, str] = {
    Severity.OK: "green",
    Severity.WARN: "yellow",
    Severity.CRIT: "bold red",
    Severity.UNKNOWN: "dim",
}


def severity_markup_for(app: Any, severity: Severity) -> str:
    """Resolve a Rich-markup colour spec for `severity` against `app`'s theme.

    Reads `app.current_theme.success / warning / error` when those are
    available (app constructed, theme registered). Falls back to plain
    Rich named colours when there is no app context. Always returns
    a non-empty markup string suitable for `[{spec}]...[/{spec}]`.
    """

    if app is None:
        return _FALLBACK_SEVERITY_MARKUP[severity]
    try:
        theme = app.current_theme
    except Exception:
        return _FALLBACK_SEVERITY_MARKUP[severity]
    if severity is Severity.OK:
        return str(theme.success) if theme.success else "green"
    if severity is Severity.WARN:
        return str(theme.warning) if theme.warning else "yellow"
    if severity is Severity.CRIT:
        colour = str(theme.error) if theme.error else "red"
        return f"bold {colour}"
    return "dim"


class ThresholdLabel(Static):
    """One-line, colour-coded display of a single `Reading`.

    `reading` is a writable attribute: assigning a new `Reading`
    re-renders the widget immediately. `thresholds` supplies the
    per-category phrase map (e.g. "CPU running hot" for WARN); the
    widget never invokes `thresholds.grade()` because grading is the
    panel layer's responsibility.

    Severity colour resolves against the active app theme at format
    time, so the label tracks the user's current palette. The
    pre-mount construction renders with fallback colours; the panel's
    snapshot-setter remount on every refresh tick picks up the real
    theme colours once mounted.
    """

    def __init__(
        self,
        reading: Reading,
        thresholds: ThresholdSet,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._thresholds = thresholds
        self._reading = reading
        self.update(self._format(reading))

    @property
    def reading(self) -> Reading:
        """The currently-rendered `Reading`."""

        return self._reading

    @reading.setter
    def reading(self, new_reading: Reading) -> None:
        self._reading = new_reading
        self.update(self._format(new_reading))

    @property
    def thresholds(self) -> ThresholdSet:
        """The `ThresholdSet` providing severity phrases."""

        return self._thresholds

    def _format(self, reading: Reading) -> str:
        """Build the Rich-markup string to display for `reading`."""

        label = reading.label
        value_str = f"{reading.value:.1f}"
        unit = _format_unit(reading.unit)
        phrase = self._thresholds.phrase_for(reading.severity)
        body = f"{label}: {value_str}{unit}  {phrase}"
        markup = severity_markup_for(self._safe_app(), reading.severity)
        return f"[{markup}]{body}[/{markup}]"

    def _safe_app(self) -> Any:
        """Return `self.app` or `None` if no app context (pre-mount)."""

        try:
            return self.app
        except Exception:
            return None


def _format_unit(unit: str) -> str:
    """Render a sensor unit as its conventional glyph.

    `C` becomes `°C`; other units pass through unchanged. The degree
    sign is a unit glyph, not an ornamental icon; per writing-style.md
    it is acceptable in user-facing rendered output but not in source
    comments or docstrings (this docstring uses the word "degree").
    """

    if unit == "C":
        return "°C"
    return unit
