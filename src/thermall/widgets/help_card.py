# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Help-when-broken card widget.

`HelpCard` surfaces one failing prerequisite as a friendly banner
above the dashboard panels: a short message plus the install
command the user can copy. Dismissed cards persist via
`thermall.config.write_dismissal` so they do not reappear on
subsequent launches.

UX (per `user-ui-quality-apple-level`):
- One card per failing prereq, stacked vertically.
- `d` keypress while a card is focused removes it AND persists the
  dismissal.
- No error styling (no red, no exclamation marks); the card is a
  hint, not an alarm.
"""

from __future__ import annotations

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import Static

from thermall.prereqs import PrereqStatus


class HelpCard(Vertical):
    """One installable-prerequisite friendly card.

    The card is a `Vertical` of two `Static`s: the friendly message
    and the install command. Focusing it (Tab) enables the `d`
    binding which removes the card from the dashboard and writes the
    dismissal to the state file via `on_dismiss`.
    """

    DEFAULT_CSS = """
    HelpCard {
        height: auto;
        padding: 0 1;
        margin: 0 1;
        border: round $accent 50%;
        background: $panel;
    }
    HelpCard:focus {
        border: round $accent;
    }
    HelpCard > Static.help-message {
        color: $foreground;
        padding-bottom: 0;
    }
    HelpCard > Static.help-command {
        color: $accent;
        text-style: italic;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("d", "dismiss", "Dismiss", show=True),
    ]

    # Override the base-class default to make the card focusable so
    # the `d` binding fires. Match the base class's declaration form
    # (plain assignment, no ClassVar) to satisfy mypy.
    can_focus = True

    def __init__(
        self,
        prereq: PrereqStatus,
        on_dismiss: Any | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("id", f"help-card-{prereq.id}")
        super().__init__(**kwargs)
        self._prereq = prereq
        self._on_dismiss = on_dismiss

    @property
    def prereq(self) -> PrereqStatus:
        return self._prereq

    def compose(self) -> ComposeResult:
        yield Static(self._prereq.friendly_message, classes="help-message")
        yield Static(f"  $ {self._prereq.install_command}", classes="help-command")

    def action_dismiss(self) -> None:
        """Remove this card from the screen and persist the dismissal."""

        if self._on_dismiss is not None:
            self._on_dismiss(self._prereq.id)
        self.remove()
