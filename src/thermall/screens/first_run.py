# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""First-run setup screen for thermall."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Static

from thermall.config import _DEFAULT_THRESHOLDS, Config, default_config_path

if TYPE_CHECKING:
    pass


class FirstRunScreen(Screen[None]):
    """First-run wizard screen shown when no config exists."""

    def __init__(self, config: Config, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        detected = self._config.detected_board
        board_text = (
            f"We detected your motherboard as {detected}"
            if detected
            else "No board profile matched"
        )

        with Container(id="wizard"):
            yield Static("Welcome to thermall", id="header")
            yield Static(board_text, id="board-line")

            # Labels section
            with Vertical(id="labels-section"):
                yield Static("[b]Proposed labels:[/b]")
                labels = self._config.labels
                if labels:
                    for raw, display in sorted(labels.items()):
                        yield Static(f"  {raw} → {display}")
                else:
                    yield Static("  (none - defaults applied)")

            # Thresholds section
            with Vertical(id="thresholds-section"):
                yield Static("[b]Proposed thresholds:[/b]")
                for category, ts in sorted(_DEFAULT_THRESHOLDS.items()):
                    yield Static(f"  {category}: warn {ts.warn:.0f}, crit {ts.crit:.0f}")

            # Buttons
            yield Horizontal(
                Button("Accept", variant="primary", id="btn-accept"),
                Button("Skip", variant="default", id="btn-skip"),
                Button("Edit", variant="default", id="btn-edit"),
                id="buttons",
            )

    @on(Button.Pressed, "#btn-accept")
    def on_accept(self) -> None:
        self._save_config(use_defaults=True)
        self.app.pop_screen()

    @on(Button.Pressed, "#btn-skip")
    def on_skip(self) -> None:
        self._save_config(use_defaults=False)
        self.app.pop_screen()

    @on(Button.Pressed, "#btn-edit")
    def on_edit(self) -> None:
        editor = os.environ.get("EDITOR", "nano")
        toml_path = self._temp_toml_path()

        # Open editor
        result = subprocess.run([editor, str(toml_path)], check=False)

        if result.returncode == 0:
            # User saved and closed editor - accept the result
            self._save_from_file(toml_path)

        self.app.pop_screen()

    def action_quit_wizard(self) -> None:
        """Quit without saving - no config file created."""
        self.app.pop_screen()
        self.app.exit(0)

    def _save_config(self, use_defaults: bool) -> None:
        """Save config to default path."""
        config_path = default_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        config = Config() if use_defaults else Config(labels={}, thresholds={})
        config_path.write_text(config.to_toml())

    def _temp_toml_path(self) -> Path:
        """Create a temp file with current proposed config."""
        config = Config(
            labels=self._config.labels,
            thresholds=self._config.thresholds,
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as tmp:
            tmp.write(config.to_toml())
        return Path(tmp.name)

    def _save_from_file(self, toml_path: Path) -> None:
        """Save config from an external edit."""
        config_path = default_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(toml_path, config_path)


def show_if_no_config(config: Config) -> bool:
    """Check if config file exists; return True if wizard should show."""
    return not default_config_path().exists()
