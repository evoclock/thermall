# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Help overlay modal for thermall.

Pushed by both the `h` and `?` dashboard keybindings. Replaces the
prior notify-toast list of bindings with a proper modal that
documents:

- Every key binding with a one-line description
- What each panel shows
- How minimize mode (`m`) behaves
- A pointer to the README for deeper docs

Dismissed with Esc or by clicking the Close button. Scoped to its
own screen so it doesn't fight other modals (e.g. SettingsScreen).
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

# (key, description) pairs. Mirrors Dashboard.BINDINGS but with
# longer descriptions than fit in the Textual Footer.
_KEY_BINDINGS: tuple[tuple[str, str], ...] = (
    ("q", "Quit thermall"),
    ("h", "Show this help overlay"),
    ("s", "Open settings (refresh interval, dismissed help cards, themes)"),
    ("t", "Cycle to the next theme in the curated set"),
    ("r", "Force an immediate sensor refresh (between scheduled ticks)"),
    ("m", "Toggle minimize mode (braille charts grow, detail rows hide)"),
    ("Esc", "Close any open modal (settings, help, first-run wizard)"),
)

# (panel name, description) pairs.
_PANELS: tuple[tuple[str, str], ...] = (
    (
        "CPU",
        "Package + per-core temperatures, hottest-core trend braille chart, "
        "CPU-mapped fans inline.",
    ),
    (
        "Motherboard / VRM",
        "Board sensors (VRM, AUXTIN, chipset) — advisory only; doesn't drive "
        "the overall warm/critical verdict.",
    ),
    (
        "GPUs",
        "Per-GPU temperature, fan %, power draw, memory used. Braille chart "
        "tracks the hottest GPU.",
    ),
    (
        "Fans",
        "Chassis + GPU + NVMe fans (everything that isn't a CPU fan). RPM + "
        "spinning/stopped status. In minimize mode, only spinning fans show.",
    ),
    (
        "Storage",
        "NVMe + SATA drive temperatures with model + sensor labels. "
        "Health column surfaces smartd events when available.",
    ),
)


class HelpScreen(ModalScreen[None]):
    """Help overlay listing bindings, panels, and minimize behaviour."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen > Vertical {
        width: 80;
        max-width: 95%;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }
    HelpScreen .help-title {
        color: $primary;
        text-style: bold;
        text-align: center;
        padding-bottom: 1;
    }
    HelpScreen .help-section {
        color: $accent;
        text-style: bold;
        padding-top: 1;
    }
    HelpScreen .help-row {
        color: $foreground 80%;
    }
    HelpScreen .help-key {
        color: $secondary;
        text-style: bold;
    }
    HelpScreen .help-hint {
        color: $foreground 60%;
        text-align: center;
        padding-top: 1;
    }
    HelpScreen .help-close {
        width: 1fr;
        margin-top: 1;
    }
    HelpScreen VerticalScroll {
        height: 1fr;
        min-height: 10;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "Close", show=True),
        Binding("h", "close", "Close help", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("thermall — Help", classes="help-title")
            with VerticalScroll():
                yield Static("Key bindings", classes="help-section")
                for key, description in _KEY_BINDINGS:
                    yield Static(
                        f"  [bold]{key:<7}[/bold]  {description}",
                        classes="help-row",
                    )
                yield Static("Panels", classes="help-section")
                for name, description in _PANELS:
                    yield Static(
                        f"  [bold]{name}[/bold]\n      {description}",
                        classes="help-row",
                    )
                yield Static("More", classes="help-section")
                yield Static(
                    "  Full docs live in the README "
                    "([link]github.com/jgamboa/thermall[/link]). "
                    "Config + state files: ~/.config/thermall/.",
                    classes="help-row",
                )
            yield Static(
                "Press Esc or click Close to return.",
                classes="help-hint",
            )
            yield Button("Close", id="close-help", classes="help-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-help":
            self.action_close()

    def action_close(self) -> None:
        self.dismiss(None)
