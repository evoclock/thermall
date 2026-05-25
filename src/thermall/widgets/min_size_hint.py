# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""btop-style minimum-size hint for thermall.

Shown in the dashboard body when the terminal is smaller than the
dimensions thermall needs to render usefully. Mirrors the pattern
btop / htop use: instead of silently clipping the dashboard so that
GPUs or fans disappear off-screen, surface the required vs current
size and ask the user to resize.

The widget updates its message live as the user resizes, so the
"current size" tracks reality without a re-mount.
"""

from __future__ import annotations

from typing import Any

from textual.widgets import Static


class MinSizeHint(Static):
    """Centered "terminal too small" message with live size readout."""

    DEFAULT_CSS = """
    MinSizeHint {
        width: 100%;
        height: 100%;
        content-align: center middle;
        color: $warning;
        text-style: bold;
        padding: 2 4;
    }
    """

    def __init__(
        self,
        *,
        min_width: int,
        min_height: int,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._min_width = min_width
        self._min_height = min_height
        self._current_width = min_width
        self._current_height = min_height
        self._render_message()

    @property
    def min_width(self) -> int:
        return self._min_width

    @property
    def min_height(self) -> int:
        return self._min_height

    def update_current_size(self, width: int, height: int) -> None:
        """Refresh the displayed "current" dimensions after a resize."""

        self._current_width = width
        self._current_height = height
        self._render_message()

    def _render_message(self) -> None:
        msg = (
            "[bold]Terminal too small to render thermall[/bold]\n\n"
            f"Required size: [b]{self._min_width} x {self._min_height}[/b]\n"
            f"Current size:  [b]{self._current_width} x {self._current_height}[/b]\n\n"
            "Resize the window or zoom out (Ctrl/Cmd + minus)."
        )
        self.update(msg)
