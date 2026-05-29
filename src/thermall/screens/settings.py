# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Settings screen for the thermall dashboard.

Reached from the main dashboard via the `s` keybinding; dismissed
with `escape`. Per `user-ui-quality-apple-level`, settings live
behind a screen rather than as a wall of CLI flags. v1 deliberately
exposes a small set:

- Refresh interval (1 / 2 / 5 / 10 seconds).
- Help-card dismissal reset ("show all dismissed help cards again"
  on next launch).
- Advanced section pointing at README sections for tmux composition
  mode and the NvmeCollector opt-in setup (documentation only).

Changes save immediately to `~/.config/thermall/config.toml` and
`state.toml`; no Save button. The dashboard's refresh timer
restarts whenever the refresh interval changes so the new cadence
applies without a reload.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from thermall.config import Config, clear_dismissed, write_config
from thermall.widgets.settings_animation import SettingsAnimation

if TYPE_CHECKING:
    from textual.widgets import Button as ButtonType

# v1 refresh interval options, in seconds. Pinned to round values
# the user can predict; finer-grained tuning is a TOML edit, not a UI
# control.
REFRESH_INTERVAL_OPTIONS: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0)

# Terminal must be at least this large for the SettingsAnimation to
# render. Below either threshold, the animation is skipped and a
# one-line hint in the modal explains why. Tuned permissively: 130
# cols / 38 rows lets the animation appear on most landscape
# terminals at the cost of a couple of cells potentially clipping
# off the right edge on the narrowest still-eligible widths.
_ANIMATION_MIN_TERMINAL_WIDTH: int = 130
_ANIMATION_MIN_TERMINAL_HEIGHT: int = 38


class SettingsScreen(ModalScreen[None]):
    """Modal settings screen overlaying the dashboard.

    Three sections, top-to-bottom: refresh interval radio set,
    help-card reset button, advanced documentation block. All three
    sit inside a single `Vertical` so the layout is predictable; the
    modal backdrop dims the dashboard behind.
    """

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }
    SettingsScreen > Vertical {
        /* 132 cells wide accommodates the 128-char SettingsAnimation
           plus padding/border. Clamps to 95% on narrower terminals so
           the modal still fits (the animation will clip on the right,
           the settings controls stay usable). */
        width: 132;
        max-width: 95%;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    SettingsScreen .refresh-row {
        /* 4 refresh-option buttons laid out horizontally so the whole
           modal fits without scrolling. Each button takes 1fr inside
           this row, so they evenly divide the modal width. */
        height: 3;
        margin-bottom: 1;
    }
    SettingsScreen .modal-title {
        color: $primary;
        text-style: bold;
        text-align: center;
        padding-bottom: 0;
    }
    SettingsScreen .modal-hint {
        color: $foreground 60%;
        text-align: center;
        padding-bottom: 1;
    }
    SettingsScreen .close-button {
        width: 1fr;
        margin-top: 1;
    }
    SettingsScreen .section-header {
        color: $accent;
        text-style: bold;
        padding-top: 1;
    }
    SettingsScreen .refresh-option {
        width: 1fr;
        margin: 0 1;
    }
    SettingsScreen .refresh-option.selected {
        background: $primary 30%;
    }
    SettingsScreen .advanced-line {
        color: $foreground 70%;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()

    def compose(self) -> ComposeResult:
        config = self._current_config()
        with Vertical():
            # Animated fan + airflow + thermometer pixel art at the
            # top of the modal — only mounts when the terminal is big
            # enough to render it without clipping the controls below.
            # On smaller terminals the modal shows controls only, and
            # the Close button is guaranteed reachable without scroll.
            if self._has_animation_room():
                yield SettingsAnimation()
            yield Static("Settings", classes="modal-title")
            yield Static(
                "Press Esc or click Close to return to the dashboard.",
                classes="modal-hint",
            )
            yield Static("Refresh interval", classes="section-header")
            with Horizontal(classes="refresh-row"):
                for option in REFRESH_INTERVAL_OPTIONS:
                    yield self._refresh_button(option, current=config.refresh_seconds)
            yield Static("Help cards", classes="section-header")
            yield Button(
                "Show all dismissed help cards again",
                id="reset-help-cards",
            )
            yield Static("Advanced", classes="section-header")
            yield Static(
                "  tmux composition mode: see README § 'tmux mode'.",
                classes="advanced-line",
            )
            yield Static(
                "  NvmeCollector opt-in (privileged): see README § 'NVMe helper'.",
                classes="advanced-line",
            )
            yield Button("Close", id="close-settings", classes="close-button")

    @staticmethod
    def _refresh_button(option: float, *, current: float) -> Button:
        selected = abs(option - current) < 1e-9
        classes = "refresh-option selected" if selected else "refresh-option"
        return Button(
            f"{option:g} s",
            id=f"refresh-{int(option)}",
            classes=classes,
        )

    def _current_config(self) -> Config:
        """Read the live `config` off the parent dashboard."""

        # The Dashboard mounts itself as `self.app`; its `config`
        # attribute is the live, possibly-mutated config object.
        config: Config = self.app.config  # type: ignore[attr-defined]
        return config

    def _has_animation_room(self) -> bool:
        """True iff the terminal is large enough to host SettingsAnimation."""

        size = self.app.size
        return (
            size.width >= _ANIMATION_MIN_TERMINAL_WIDTH
            and size.height >= _ANIMATION_MIN_TERMINAL_HEIGHT
        )

    def on_button_pressed(self, event: ButtonType.Pressed) -> None:
        """Dispatch button presses by id."""

        button_id = event.button.id or ""
        if button_id.startswith("refresh-"):
            seconds = float(button_id.removeprefix("refresh-"))
            self._set_refresh_interval(seconds)
        elif button_id == "reset-help-cards":
            self._reset_help_cards()
        elif button_id == "close-settings":
            self.action_close()

    def _set_refresh_interval(self, seconds: float) -> None:
        """Save the new interval and restart the dashboard timer."""

        old = self._current_config()
        new = replace(old, refresh_seconds=seconds)
        write_config(new)
        # Hot-update the live config + restart the timer in place.
        self.app.config = new  # type: ignore[attr-defined]
        restart = getattr(self.app, "restart_refresh_timer", None)
        if callable(restart):
            restart()
        self.app.sub_title = f"refresh {new.refresh_seconds:g}s; theme {new.theme}" + (
            f"; board: {new.detected_board}" if new.detected_board else ""
        )
        # Re-render the selection highlight by remounting the
        # refresh-option buttons.
        self._refresh_button_highlights()
        self.notify(f"Refresh interval: {seconds:g} s")

    def _reset_help_cards(self) -> None:
        """Clear the dismissed-prereqs list.

        Takes effect on the next dashboard launch; we deliberately do
        NOT re-render the current session's cards, both to keep the
        change predictable and to avoid mid-session UI thrash.
        """

        clear_dismissed()
        self.notify("Dismissed help cards will reappear on next launch")

    def _refresh_button_highlights(self) -> None:
        """Toggle the `selected` class on each refresh-interval button."""

        current = self._current_config().refresh_seconds
        for option in REFRESH_INTERVAL_OPTIONS:
            try:
                btn = self.query_one(f"#refresh-{int(option)}", Button)
            except Exception:
                continue
            if abs(option - current) < 1e-9:
                btn.add_class("selected")
            else:
                btn.remove_class("selected")

    def action_close(self) -> None:
        """Close the modal and return to the dashboard."""

        self.dismiss(None)
