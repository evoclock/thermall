# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""btop-style braille-dot area chart with severity-coloured gradient.

`render_braille_chart` is a pure function: take a sequence of floats
plus optional `ThresholdSet`, return a `BrailleChart` whose `rows`
are Rich-marked-up strings ready for a Textual Static.

Why Braille over block characters: a single Braille character
(U+2800 to U+28FF) encodes a 2x4 grid of dots. A `width` x `height`
braille chart thus resolves `width * 2` samples horizontally and
`height * 4` levels vertically. For a 20x4 chart that's 40 samples
by 16 levels — enough density to communicate trend the way btop
does, instead of the chunky stair-stepped blocks of a one-dot-per-
char renderer.

Coloring: each character column carries the colour of the highest-
severity sample it represents (a column with one WARN and one OK
sample colours WARN). When `thresholds` is `None` the chart renders
without colour (plain accent). Severity-based colour communicates
"is this safe?" alongside the height-based "how high is this?".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from thermall.mapping import ThresholdSet
from thermall.model import Severity

# Braille code points start at U+2800. Each braille char encodes up
# to 8 dots; the bit value for each dot position in a 2x4 grid is:
#
#   col 0  col 1
#   ┌──────────┐
#   │ 0x01  0x08│  row 0 (top)
#   │ 0x02  0x10│  row 1
#   │ 0x04  0x20│  row 2
#   │ 0x40  0x80│  row 3 (bottom)
#   └──────────┘
#
# To set a dot at (row, col), OR the cell value into the braille
# base (0x2800).
_DOT_BITS: Final[tuple[tuple[int, int], ...]] = (
    (0x01, 0x08),  # row 0 (topmost)
    (0x02, 0x10),  # row 1
    (0x04, 0x20),  # row 2
    (0x40, 0x80),  # row 3 (bottom)
)
_BRAILLE_BASE: Final[int] = 0x2800

DEFAULT_SEVERITY_COLORS: Final[dict[Severity, str]] = {
    Severity.OK: "green",
    Severity.WARN: "yellow",
    Severity.CRIT: "bold red",
    Severity.UNKNOWN: "dim",
}
"""Fallback severity colours used when the caller supplies no override.

The widget layer reads the active app theme's success / warning /
error colours and passes them via the `severity_colors` parameter;
when that's `None` (or the renderer is called from a test outside any
app), these named Rich colours apply.
"""

# Empty character — U+2800 looks blank in most terminals.
_EMPTY_BRAILLE: Final[str] = "⠀"

DEFAULT_HEIGHT: Final[int] = 4
"""Default chart height in character rows (= 16 vertical pixels)."""

DEFAULT_WIDTH: Final[int] = 20
"""Default chart width in character columns (= 40 sample slots)."""


@dataclass(frozen=True, slots=True)
class BrailleChart:
    """A rendered braille area chart plus its axis labels.

    `rows` has `height` entries top-to-bottom; each is a Rich-
    marked-up string (e.g. `"[green]⡄[/green][yellow]⣿[/yellow]"`).
    `min_label` and `max_label` carry the actual numeric range so
    the caller can render axis text next to the chart.
    """

    rows: tuple[str, ...]
    min_label: str
    max_label: str

    @property
    def height(self) -> int:
        return len(self.rows)


def render_braille_chart(
    values: Sequence[float],
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    thresholds: ThresholdSet | None = None,
    severity_colors: dict[Severity, str] | None = None,
    unit: str = "",
) -> BrailleChart:
    """Render `values` as a braille-dot area chart with optional colour.

    Behaviour:
    - Empty values: all-blank rows; labels are `"n/a"`.
    - Each character column holds two samples (left dot, right dot).
    - More samples than `width * 2`: keep only the latest.
    - Fewer: left-pad with blank braille chars so the newest sample
      sits at the rightmost dot position.
    - All-equal values (or one value): single mid-height baseline
      across the populated columns; min == max in the labels.
    - `thresholds`: when supplied, each character column is coloured
      by the highest-severity sample it covers. Without thresholds,
      the rendered rows are plain (caller styles them).
    - `severity_colors`: per-severity Rich-markup colour overrides
      (typically read from the active app theme so the chart matches
      the user's chosen palette). When `None`, `DEFAULT_SEVERITY_COLORS`
      applies. Keys missing from a user-supplied dict also fall back.
    - NaN / inf: coerced to the min of the finite values; never
      destabilises the auto-scale.
    """

    palette = dict(DEFAULT_SEVERITY_COLORS)
    if severity_colors is not None:
        palette.update(severity_colors)

    if width < 1:
        raise ValueError(f"width must be >= 1, got {width}")
    if height < 1:
        raise ValueError(f"height must be >= 1, got {height}")

    pixel_rows = height * 4
    sample_slots = width * 2

    if not values:
        blank = (_EMPTY_BRAILLE * width,) * height
        return BrailleChart(rows=blank, min_label="n/a", max_label="n/a")

    sanitised = [_finite_or_min(v, values) for v in values]
    samples = sanitised[-sample_slots:]
    pad_left = sample_slots - len(samples)

    lo = min(samples)
    hi = max(samples)
    span = hi - lo

    min_label = _format_value(lo, unit)
    max_label = _format_value(hi, unit)

    # Compute each sample's pixel height (0..pixel_rows). Flat / one
    # sample renders at mid height so the user sees a visible
    # baseline rather than an invisible row of empties.
    if span < 1e-9:
        baseline = pixel_rows // 2
        pixel_heights = [baseline] * len(samples)
    else:
        pixel_heights = [int((v - lo) / span * pixel_rows) for v in samples]
    # Bound; without this a max sample equals `pixel_rows` which is
    # out of range for the bit grid.
    pixel_heights = [max(1, min(pixel_rows, h)) for h in pixel_heights]

    # Precompute severities (when thresholds provided).
    severities: list[Severity | None] = []
    if thresholds is not None:
        severities = [thresholds.grade(v) for v in samples]
    else:
        severities = [None] * len(samples)

    rows: list[list[str]] = [[] for _ in range(height)]

    # Walk character columns: each holds two samples.
    cols_in_chart = width
    for char_col in range(cols_in_chart):
        slot_left = char_col * 2 - pad_left
        slot_right = slot_left + 1

        left_h = _height_for_slot(slot_left, pixel_heights)
        right_h = _height_for_slot(slot_right, pixel_heights)

        # Severity for colouring this character: max of the two slots.
        cell_severity = _max_severity(
            _severity_for_slot(slot_left, severities),
            _severity_for_slot(slot_right, severities),
        )

        for char_row in range(height):
            char = _char_for(left_h, right_h, char_row, height)
            rows[char_row].append(_paint(char, cell_severity, palette))

    return BrailleChart(
        rows=tuple("".join(row) for row in rows),
        min_label=min_label,
        max_label=max_label,
    )


def _char_for(left_h: int, right_h: int, char_row: int, total_rows: int) -> str:
    """Build one braille character covering pixel rows in `char_row`.

    `char_row` is 0 (top) to `total_rows - 1` (bottom). Each char
    covers 4 pixel rows; pixel rows are also indexed top to bottom.
    A dot at (pixel_row, col) is set iff the sample value's height
    reaches that pixel row.
    """

    mask = 0
    top_pixel = char_row * 4
    bottom_pixel = top_pixel + 3

    for col_idx, h in ((0, left_h), (1, right_h)):
        # h is bar height from bottom; fills pixels [total_rows*4 - h .. total_rows*4 - 1].
        bar_top = (total_rows * 4) - h
        for row_in_char in range(4):
            pixel_row = top_pixel + row_in_char
            if pixel_row > bottom_pixel:
                break
            if pixel_row >= bar_top:
                mask |= _DOT_BITS[row_in_char][col_idx]
    return chr(_BRAILLE_BASE + mask)


def _height_for_slot(slot: int, pixel_heights: list[int]) -> int:
    """Look up the pixel-height for `slot`; 0 when out of range."""

    if 0 <= slot < len(pixel_heights):
        return pixel_heights[slot]
    return 0


def _severity_for_slot(slot: int, severities: list[Severity | None]) -> Severity | None:
    """Look up the severity for `slot`; `None` when out of range."""

    if 0 <= slot < len(severities):
        return severities[slot]
    return None


_SEVERITY_RANK: Final[dict[Severity, int]] = {
    Severity.UNKNOWN: 0,
    Severity.OK: 1,
    Severity.WARN: 2,
    Severity.CRIT: 3,
}


def _max_severity(a: Severity | None, b: Severity | None) -> Severity | None:
    """Return the highest-ranked severity of the two; None if both are None."""

    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return a if _SEVERITY_RANK[a] >= _SEVERITY_RANK[b] else b


def _paint(char: str, severity: Severity | None, palette: dict[Severity, str]) -> str:
    """Wrap `char` in Rich markup for `severity`; passthrough if None."""

    if severity is None:
        return char
    colour = palette[severity]
    return f"[{colour}]{char}[/{colour}]"


def _finite_or_min(value: float, all_values: Sequence[float]) -> float:
    """Coerce NaN / inf to the min of `all_values`'s finite entries."""

    if _is_finite(value):
        return value
    finite = [v for v in all_values if _is_finite(v)]
    return min(finite) if finite else 0.0


def _is_finite(value: float) -> bool:
    if value != value:  # NaN
        return False
    return value not in (float("inf"), float("-inf"))


def _format_value(value: float, unit: str) -> str:
    return f"{value:.0f}{unit}"
