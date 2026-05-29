# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""BrailleChart Textual widget.

Thin Static-derived wrapper over `thermall.braillechart.render_braille_chart`.
Formats the chart rows alongside min/max axis labels into a single
multi-line markup string ready for mounting.

Layout:

      87°C  ⠀⠀⠀⠀⠀⣷⣦⠀⠀⠀⠀⠀
            ⠀⠀⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀
            ⠀⠀⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀
      40°C  ⣠⣤⣶⣶⣿⣿⣿⣀⣀⣤⣴⣶

Per-character colour is encoded by the renderer via Rich markup
(green / yellow / bold red for OK / WARN / CRIT). When no
ThresholdSet is supplied the chart renders without colour and
the caller's default theme accent applies.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from textual.widgets import Static

from thermall.braillechart import DEFAULT_HEIGHT, DEFAULT_WIDTH, render_braille_chart
from thermall.mapping import ThresholdSet
from thermall.model import Severity

_LABEL_WIDTH = 6
"""Character columns reserved on the left for min / max labels."""


_FALLBACK_COLORS: dict[Severity, str] = {
    Severity.OK: "green",
    Severity.WARN: "yellow",
    Severity.CRIT: "bold red",
    Severity.UNKNOWN: "dim",
}


def _theme_severity_colors(app: Any) -> dict[Severity, str] | None:
    """Resolve per-severity Rich-markup colours against `app.current_theme`.

    Returns a dict keyed by `Severity` when the app is available and
    has a theme registered; returns `None` when there's no app context
    (e.g. widget constructed outside Pilot, tests that instantiate
    without mounting). The renderer falls back to its own defaults
    when given `None`.
    """

    if app is None:
        return None
    try:
        theme = app.current_theme
    except Exception:
        return None
    return {
        Severity.OK: str(theme.success) if theme.success else "green",
        Severity.WARN: str(theme.warning) if theme.warning else "yellow",
        Severity.CRIT: f"bold {theme.error}" if theme.error else "bold red",
        Severity.UNKNOWN: "dim",
    }


class BrailleChart(Static):
    """btop-style multi-row area chart with severity-coloured dots.

    Rebuilt in place on `samples` reassignment (no remount). Owns its
    chart dimensions, thresholds, and unit string; the panel that
    mounts it owns the data and refresh wiring.
    """

    DEFAULT_CSS = """
    BrailleChart {
        height: auto;
    }
    """

    def __init__(
        self,
        samples: Sequence[float] = (),
        *,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        thresholds: ThresholdSet | None = None,
        unit: str = "",
        **kwargs: Any,
    ) -> None:
        if "classes" in kwargs:
            kwargs["classes"] = f"braillechart {kwargs['classes']}"
        else:
            kwargs["classes"] = "braillechart"
        self._chart_width = width
        self._chart_height = height
        self._thresholds = thresholds
        self._unit = unit
        self._samples = tuple(samples)
        super().__init__(self._format(self._samples), markup=True, **kwargs)

    @property
    def samples(self) -> tuple[float, ...]:
        return self._samples

    @samples.setter
    def samples(self, new_samples: Sequence[float]) -> None:
        self._samples = tuple(new_samples)
        self.update(self._format(self._samples))

    @property
    def chart_width(self) -> int:
        return self._chart_width

    @property
    def chart_height(self) -> int:
        return self._chart_height

    def _safe_app(self) -> Any:
        """Return `self.app` or `None` if no app context (pre-mount)."""

        try:
            return self.app
        except Exception:
            return None

    def _format(self, samples: Sequence[float]) -> str:
        """Build the multi-line Rich-marked string the Static renders.

        First row leads with `max_label` right-aligned in a fixed
        slot; last row leads with `min_label`; middle rows have an
        empty label slot. A single space sits between label and
        chart row.
        """

        chart = render_braille_chart(
            samples,
            width=self._chart_width,
            height=self._chart_height,
            thresholds=self._thresholds,
            severity_colors=_theme_severity_colors(self._safe_app()),
            unit=self._unit,
        )
        lines: list[str] = []
        last_idx = len(chart.rows) - 1
        for i, row in enumerate(chart.rows):
            if i == 0:
                label = chart.max_label
            elif i == last_idx:
                label = chart.min_label
            else:
                label = ""
            lines.append(f"{label:>{_LABEL_WIDTH}} {row}")
        return "\n".join(lines)
