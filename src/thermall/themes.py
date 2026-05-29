# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Theme catalogue for thermall.

Four curated themes the dashboard cycles through with the `t` key
binding. Each defines its own `success` / `warning` / `error` colours
so the per-reading ThresholdLabel and the BrailleChart's
severity-coloured dots adapt to the active palette instead of clashing
with hard-coded green / yellow / red.

Themes:
- thermall-default            (palette: pulp-magazine cover navy / teal / peach / orange / red)
- thermall-pacific-northwest  (palette: electric cyan + magenta + midnight)
- thermall-clay-court         (palette: cream + amber + deep red on dark brown)
- thermall-power-station      (palette: mint + peach + cream on warm grey)

Each theme leans on two or three dominant colours plus accents because
that's what reads as a coherent identity on the dashboard at a glance.
Palettes that needed all five plus white to evoke their inspiration
(notably a true VHS / SMPTE colour-bar look) belong in a different
project where the rendering surface can carry that many channels
without going to mush.

All themes register via `App.register_theme()` in Dashboard.__init__;
none are Textual built-ins.
"""

from __future__ import annotations

from typing import Final

from textual.theme import Theme

THERMALL_DEFAULT = Theme(
    name="thermall-default",
    primary="#50a3ab",
    secondary="#f6723a",
    accent="#fadac1",
    success="#50a3ab",
    warning="#f6723a",
    error="#c43b39",
    foreground="#fadac1",
    background="#0a1620",
    surface="#1d313c",
    panel="#2b4756",
    boost="#3a5e70",
    dark=True,
)

THERMALL_PACIFIC_NORTHWEST = Theme(
    name="thermall-pacific-northwest",
    primary="#00d9ff",
    secondary="#ff2bd6",
    accent="#7df9ff",
    success="#39ff8a",
    warning="#ffcc00",
    error="#ff3860",
    foreground="#d6f6ff",
    background="#000814",
    surface="#001428",
    panel="#001a33",
    boost="#002b50",
    dark=True,
)

THERMALL_CLAY_COURT = Theme(
    name="thermall-clay-court",
    primary="#e18e04",
    secondary="#813c01",
    accent="#fce2bf",
    success="#7ca838",
    warning="#e18e04",
    error="#b92a18",
    foreground="#fce2bf",
    background="#1a0a03",
    surface="#4c1d09",
    panel="#5e2510",
    boost="#723018",
    dark=True,
)

THERMALL_POWER_STATION = Theme(
    name="thermall-power-station",
    primary="#79c39e",
    secondary="#e77843",
    accent="#ee9b69",
    success="#79c39e",
    warning="#ee9b69",
    error="#e77843",
    foreground="#ead1b5",
    background="#1a1816",
    surface="#383431",
    panel="#4a4540",
    boost="#5c564f",
    dark=True,
)


# Every theme that must be registered with App.register_theme().
# Order in this tuple is the cycle order; first entry is the default.
ALL_THEMES: Final[tuple[Theme, ...]] = (
    THERMALL_DEFAULT,
    THERMALL_PACIFIC_NORTHWEST,
    THERMALL_CLAY_COURT,
    THERMALL_POWER_STATION,
)


THEME_CYCLE: Final[tuple[str, ...]] = tuple(t.name for t in ALL_THEMES)


DEFAULT_THEME: Final[str] = THEME_CYCLE[0]


def next_theme_name(current: str) -> str:
    """Return the next theme to load given the current one.

    Wraps from the last entry back to the first. If `current` is not
    in the cycle (user-set theme via `app.theme = ...`), restart at
    the default so they can resume cycling.
    """

    if current not in THEME_CYCLE:
        return DEFAULT_THEME
    idx = THEME_CYCLE.index(current)
    return THEME_CYCLE[(idx + 1) % len(THEME_CYCLE)]
