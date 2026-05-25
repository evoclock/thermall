# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Animated pixel-art for the SettingsScreen modal.

Direct port of the ChatGPT-generated prototype script Julen pasted on
2026-05-23. Composites three symbolic sprite stacks (fan, wind,
thermometer) onto a 64x18 canvas, then renders each cell as a
2-space Rich-markup background. Cycles three composited frames at
~7 Hz (0.14s tick).

Frames, palette, canvas dimensions, sprite offsets, and tick cadence
are all verbatim from the source script. The only adaptation is from
raw ANSI escape codes to Textual / Rich markup (`[on #hex]  [/]`),
since Textual renders through Rich's style system rather than
writing escapes directly to stdout.
"""

from __future__ import annotations

from typing import Any, Final

from textual.timer import Timer
from textual.widgets import Static

# Two-space cell keeps roughly square pixel proportions in most
# terminal fonts. Matches the prototype's `CELL = "  "`.
_CELL: Final[str] = "  "

# Palette: dot is transparent (no background), others are RGB bg
# colours rendered as Rich `[on #hex]` markup. Hex values converted
# from the prototype's `\033[48;2;R;G;Bm` sequences.
_PALETTE: Final[dict[str, str | None]] = {
    ".": None,
    "K": "191919",
    "C": "f6efdd",
    "R": "ff5b18",
    "W": "464646",
    "B": "46b4e6",
}

# Fan: 22 wide x 13 tall, 3 frames showing blades rotating.
_FAN_FRAMES: Final[tuple[tuple[str, ...], ...]] = (
    (
        "......................",
        ".......KKKKKKKK.......",
        ".....KKCCCCCCCCKK.....",
        "....KCCCKKCCKKCCCK....",
        "...KCCCKKKCCKKKCCCK...",
        "...KCCCCKKCCKKCCCCK...",
        "...KCCKKKCCCCKKKCCK...",
        "...KCCKKKCCCCKKKCCK...",
        "...KCCCCKKCCKKCCCCK...",
        "...KCCCKKKCCKKKCCCK...",
        "....KCCCKKCCKKCCCK....",
        ".....KKCCCCCCCCKK.....",
        ".......KKKKKKKK.......",
    ),
    (
        "......................",
        ".......KKKKKKKK.......",
        ".....KKCCCCCCCCKK.....",
        "....KCCCCKKKKCCCCK....",
        "...KCCCCKKKKKKCCCCK...",
        "...KCCCCCCKKKKCCCCK...",
        "...KCCKKKKCCCCKCCCK...",
        "...KCCCKCCCCKKKKCCK...",
        "...KCCCCKKKKCCCCCCK...",
        "...KCCCCKKKKKKCCCCK...",
        "....KCCCCKKKKCCCCK....",
        ".....KKCCCCCCCCKK.....",
        ".......KKKKKKKK.......",
    ),
    (
        "......................",
        ".......KKKKKKKK.......",
        ".....KKCCCCCCCCKK.....",
        "....KCCCCCCCCCCCCK....",
        "...KCCCCKKKKKKCCCCK...",
        "...KCCKKKKKKKKKKCCK...",
        "...KCCCCCCKKCCCCCCK...",
        "...KCCCCCCKKCCCCCCK...",
        "...KCCKKKKKKKKKKCCK...",
        "...KCCCCKKKKKKCCCCK...",
        "....KCCCCCCCCCCCCK....",
        ".....KKCCCCCCCCKK.....",
        ".......KKKKKKKK.......",
    ),
)

# Wind: 11 wide x 3 tall, 3 frames drifting rightward.
_WIND_FRAMES: Final[tuple[tuple[str, ...], ...]] = (
    (
        "WW..WW.....",
        "WWWWWWW....",
        ".WWWWW.....",
    ),
    (
        ".WW..WW....",
        ".WWWWWWW...",
        "..WWWWW....",
    ),
    (
        "..WW..WW...",
        "..WWWWWWW..",
        "...WWWWW...",
    ),
)

# Thermometer: 7 wide x 10 tall, 3 frames showing mercury rising.
_THERMOMETER_FRAMES: Final[tuple[tuple[str, ...], ...]] = (
    (
        "..KKK..",
        ".KCCCK.",
        ".KCKCK.",
        ".KCKCK.",
        ".KCRCK.",
        ".KCRCK.",
        "KKCRCKK",
        "KCRRRCK",
        "KRRRRRK",
        ".KKKKK.",
    ),
    (
        "..KKK..",
        ".KCCCK.",
        ".KCKCK.",
        ".KCKCK.",
        ".KCCCK.",
        ".KCRCK.",
        "KKCRCKK",
        "KCRRRCK",
        "KRRRRRK",
        ".KKKKK.",
    ),
    (
        "..KKK..",
        ".KCCCK.",
        ".KCKCK.",
        ".KCCCK.",
        ".KCCCK.",
        ".KCRCK.",
        "KKCRCKK",
        "KCRRRCK",
        "KRRRRRK",
        ".KKKKK.",
    ),
)

_CANVAS_HEIGHT: Final[int] = 18
_CANVAS_WIDTH: Final[int] = 64

# (row, col) offsets where each sprite stack is composited onto the
# canvas. Verbatim from the prototype's `build_frame`.
_FAN_OFFSET: Final[tuple[int, int]] = (2, 0)
_WIND_OFFSET: Final[tuple[int, int]] = (8, 28)
_THERMOMETER_OFFSET: Final[tuple[int, int]] = (4, 49)

_FRAME_COUNT: Final[int] = 3
_TICK_SECONDS: Final[float] = 0.14


def _overlay(
    canvas: list[str],
    sprite: tuple[str, ...],
    row_offset: int,
    col_offset: int,
) -> list[str]:
    """Overlay a symbolic sprite onto a symbolic canvas (dots transparent)."""

    rows = [list(row) for row in canvas]
    for s_row_idx, s_row in enumerate(sprite):
        t_row = row_offset + s_row_idx
        if t_row < 0 or t_row >= len(rows):
            continue
        for s_col_idx, symbol in enumerate(s_row):
            t_col = col_offset + s_col_idx
            if t_col < 0 or t_col >= len(rows[t_row]):
                continue
            if symbol != ".":
                rows[t_row][t_col] = symbol
    return ["".join(r) for r in rows]


def build_composited_frame(
    frame_idx: int,
    *,
    canvas_width: int,
    canvas_height: int,
    fan_offset: tuple[int, int],
    wind_offset: tuple[int, int],
    thermometer_offset: tuple[int, int],
) -> list[str]:
    """Composite the fan + wind + thermometer sprites onto a parametric canvas.

    Public to let other widgets (e.g. dashboard `TitleBar`) reuse the
    same sprite stacks at different canvas sizes and offsets without
    duplicating the frame definitions.
    """

    canvas = ["." * canvas_width for _ in range(canvas_height)]
    canvas = _overlay(canvas, _FAN_FRAMES[frame_idx], *fan_offset)
    canvas = _overlay(canvas, _WIND_FRAMES[frame_idx], *wind_offset)
    canvas = _overlay(canvas, _THERMOMETER_FRAMES[frame_idx], *thermometer_offset)
    return canvas


def _build_frame(frame_idx: int) -> list[str]:
    """Composite the SettingsAnimation frame at its native dimensions."""

    return build_composited_frame(
        frame_idx,
        canvas_width=_CANVAS_WIDTH,
        canvas_height=_CANVAS_HEIGHT,
        fan_offset=_FAN_OFFSET,
        wind_offset=_WIND_OFFSET,
        thermometer_offset=_THERMOMETER_OFFSET,
    )


def render_symbolic_frame(frame: list[str]) -> str:
    """Render a symbolic frame as Rich-markup background-coloured cells.

    Public so other animation widgets reusing the sprite stacks can
    share the rendering path. Dot symbols emit literal spaces with no
    background-colour markup, preserving terminal-background
    transparency.
    """

    lines: list[str] = []
    for row in frame:
        cells: list[str] = []
        for symbol in row:
            color = _PALETTE.get(symbol)
            if color is None:
                cells.append(_CELL)
            else:
                cells.append(f"[on #{color}]{_CELL}[/]")
        lines.append("".join(cells).rstrip())
    return "\n".join(lines)


# Internal alias used by SettingsAnimation to keep the name stable
# for the existing test suite that pins `_render_frame`.
_render_frame = render_symbolic_frame


class SettingsAnimation(Static):
    """Composited animated fan + airflow + thermometer for SettingsScreen.

    Cycles 3 frames at ~7 Hz via a Textual Timer; renders into a
    Static via Rich markup so it co-exists with Textual's render loop
    instead of writing raw escapes to stdout the way the prototype
    script did.

    Final rendered dimensions: 64 cells wide x 18 rows tall, where
    each cell is `"  "` (2 spaces) -> 128 chars wide x 18 text rows.
    The parent modal needs to be at least ~132 chars wide to avoid
    clipping the right edge.
    """

    DEFAULT_CSS = f"""
    SettingsAnimation {{
        height: {_CANVAS_HEIGHT};
        width: auto;
        padding: 0;
    }}
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("markup", True)
        super().__init__(**kwargs)
        self._frame: int = 0
        self._timer: Timer | None = None
        self.update(_render_frame(_build_frame(self._frame)))

    def on_mount(self) -> None:
        self._timer = self.set_interval(_TICK_SECONDS, self._advance)

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    @property
    def frame(self) -> int:
        return self._frame

    def _advance(self) -> None:
        self._frame = (self._frame + 1) % _FRAME_COUNT
        self.update(_render_frame(_build_frame(self._frame)))
