# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Fans dashboard panel.

Stub. Implementation grows via RED-GREEN-REFACTOR cycles in
sequence with `tests/test_fans_panel.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from thermall.config import Config
from thermall.model import DeviceSnapshot, Fan


def _empty_snapshot() -> DeviceSnapshot:
    return DeviceSnapshot(taken_at=datetime.now(tz=UTC))


def _is_cpu_fan(fan: Fan) -> bool:
    """True when the fan label tokenises CPU.

    Checks `display_label` and `raw_label` with discrete-word matching
    so "cputin" or "cpu_aux_chassis" do not false-match. Used to
    exclude CPU-cooler fans from this panel (CpuPanel renders them).
    """

    candidates = [fan.raw_label.lower()]
    if fan.display_label is not None:
        candidates.append(fan.display_label.lower())
    return any(_has_word(label, "cpu") for label in candidates)


def _has_word(label: str, word: str) -> bool:
    """Discrete-token substring match (mirrors mapping._has_word).

    Duplicated rather than reaching across the `mapping._has_word`
    private boundary; if a third caller appears, promote to public
    in `thermall.mapping`.
    """

    if word not in label:
        return False
    idx = 0
    while True:
        idx = label.find(word, idx)
        if idx < 0:
            return False
        before_ok = idx == 0 or not label[idx - 1].isalnum()
        end = idx + len(word)
        after_ok = end == len(label) or not label[end].isalnum()
        if before_ok and after_ok:
            return True
        idx = end


class FansPanel(Vertical):
    """Container panel for the fans block of the dashboard."""

    def __init__(
        self,
        config: Config,
        snapshot: DeviceSnapshot | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._snapshot = snapshot if snapshot is not None else _empty_snapshot()

    def compose(self) -> ComposeResult:
        yield from self._panel_widgets()

    @property
    def snapshot(self) -> DeviceSnapshot:
        return self._snapshot

    @snapshot.setter
    def snapshot(self, new_snapshot: DeviceSnapshot) -> None:
        self._snapshot = new_snapshot
        if self.is_mounted:
            self.remove_children()
            for child in self._panel_widgets():
                self.mount(child)

    def _panel_widgets(self) -> Iterator[Widget]:
        # Plain readings: header + per-fan lines, top-down. The
        # composited fan + airflow + thermometer pixel-art used to
        # live here but moved to its own `CreditPane` at the bottom
        # of the dashboard, since it needs the full screen width to
        # fit alongside readable text on most monitors.
        yield Static("[bold]Fans[/bold]")
        visible = [f for f in self._snapshot.fans if not _is_cpu_fan(f)]
        if not visible:
            yield Static(
                "No fan sensors detected. Load the [b]nct6775[/b] kernel module to "
                "see fan headers on Nuvoton-based boards. See the README "
                "Prerequisites section for the persistent setup."
            )
            return
        for fan in sorted(visible, key=lambda f: f.raw_label):
            status = "Stopped" if fan.is_stopped else "Spinning"
            # Tag stopped fans so minimize mode (Screen.minimized)
            # can hide them via CSS while keeping spinning fans
            # visible.
            css_class = "reading-detail fan-stopped" if fan.is_stopped else "fan-spinning"
            yield Static(
                f"{fan.label}: {fan.rpm} RPM ({status})",
                classes=css_class,
            )
