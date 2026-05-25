# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Textual application for thermall.

Mounts the StatusHeader plus the five per-category panels (CPU, VRM,
GPU, Storage, Fans) and drives them with a periodic refresh loop. The
initial snapshot is collected before the first paint so panels never
render a "no data" transient on launch.

Per the design rationale: collection and grading live in
`thermall.refresh`; the panel widgets are presentational and consume
whatever `DeviceSnapshot` they are handed. The Dashboard's job is to
wire them up, drive the refresh timer, and forward each new snapshot
into every child widget.
"""

from __future__ import annotations

from typing import ClassVar

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Vertical
from textual.timer import Timer
from textual.widgets import Footer, Header

from thermall.config import Config, load_dismissed, write_dismissal
from thermall.history import HistoryStore
from thermall.model import DeviceSnapshot
from thermall.prereqs import check_all
from thermall.refresh import collect_snapshot
from thermall.screens import FirstRunScreen, HelpScreen
from thermall.screens.settings import SettingsScreen
from thermall.themes import ALL_THEMES, DEFAULT_THEME, next_theme_name
from thermall.widgets.cpu_panel import CpuPanel
from thermall.widgets.fans_panel import FansPanel
from thermall.widgets.gpu_panel import GpuPanel
from thermall.widgets.help_card import HelpCard
from thermall.widgets.min_size_hint import MinSizeHint
from thermall.widgets.status_header import StatusHeader
from thermall.widgets.storage_panel import StoragePanel
from thermall.widgets.vrm_panel import VrmPanel


class Dashboard(App[None]):
    """The main dashboard application."""

    # Two stacked horizontal rows. Each row gets half the vertical space
    # left after Header / StatusHeader / Footer; panels inside each row
    # split that row evenly. The previous single-row layout gave each
    # of five panels ~20 cols on a 100-col terminal, which clipped the
    # Storage and Fans rows. The `dashboard-row` class scopes the row
    # height to layout rows only — per-drive Horizontals inside
    # StoragePanel must not match this selector.
    # Below these terminal dimensions, the dashboard hides itself and
    # shows a `MinSizeHint` instead of clipping panels off-screen.
    # Sized for: 3 panels wide x ~25 chars each + borders/margins (90+),
    # Header + StatusHeader + 2 panel rows + Footer (~28+).
    MIN_TERMINAL_WIDTH: ClassVar[int] = 90
    MIN_TERMINAL_HEIGHT: ClassVar[int] = 28

    CSS = """
    Screen {
        background: $surface;
    }
    /* Minimize mode (toggled with `m`): adds `minimized` class to
       `#dashboard-body`, which hides per-sensor detail rows + stopped
       fans + ThresholdLabel readings across all panels. Headers +
       braille charts + spinning fans stay visible. Scoped to the
       dashboard body so it doesn't bleed into the settings modal. */
    #dashboard-body.minimized .reading-detail {
        display: none;
    }
    #dashboard-body.minimized ThresholdLabel {
        display: none;
    }
    /* The dashboard body is wrapped in `Container#dashboard-body` so a
       single `display: none` toggles all the panels at once when the
       terminal is too small. MinSizeHint takes its place during that
       state. */
    Container#dashboard-body {
        height: 1fr;
    }
    MinSizeHint {
        display: none;
        height: 1fr;
    }
    Vertical.help-cards {
        height: auto;
    }
    CpuPanel, VrmPanel, GpuPanel, StoragePanel, FansPanel {
        padding: 1 2;
        border: round $primary 50%;
        margin: 0 1;
    }
    /* Main panel area: 3-column x 2-row grid. CPU and VRM occupy the
       top row of the left two columns; Fans and Storage occupy the
       bottom row of the same columns; GPU spans BOTH rows in the
       right column so 3 GPU readings + their per-GPU braille charts
       have enough vertical room. Per user request 2026-05-23. */
    Container.panel-grid {
        layout: grid;
        grid-size: 3 2;
        grid-columns: 1fr 1fr 1fr;
        grid-rows: 1fr 1fr;
        height: 1fr;
    }
    GpuPanel {
        row-span: 2;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit"),
        Binding("h", "help", "Help"),
        Binding("t", "cycle_theme", "Theme"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "open_settings", "Settings"),
        Binding("m", "toggle_minimize", "Minimize"),
    ]

    def __init__(self, config: Config, *, show_wizard: bool = False) -> None:
        super().__init__()
        # Register every curated retro theme and set the default
        # before compose() runs so the first paint uses the chosen
        # palette. All themes in the cycle are custom; none are
        # Textual built-ins (the prior tokyo-night / nord / gruvbox
        # lineup was retired in favour of the user's palette set).
        for theme in ALL_THEMES:
            self.register_theme(theme)
        self.theme = DEFAULT_THEME
        self.config = config
        # Collect the first snapshot up-front so compose() has data
        # to pass into every panel on first paint. The cost is one
        # synchronous collector pass during App init; happens once.
        self.snapshot: DeviceSnapshot = collect_snapshot(config)
        # One ring buffer per sensor label. Seed with the initial
        # snapshot so the first paint already shows a single-cell
        # sparkline instead of a blank one.
        self.history = HistoryStore()
        self._record_snapshot(self.snapshot)
        # Prereq help-card state: check each prereq once at startup;
        # only show cards for prereqs that are failing AND the user
        # has not previously dismissed. Re-check happens per-launch
        # (no in-session re-check); the user dismisses with `d`.
        self._dismissed_prereqs = load_dismissed()
        self._prereq_statuses = check_all()
        self._refresh_timer: Timer | None = None
        self.title = "thermall"
        board_suffix = f"; board: {config.detected_board}" if config.detected_board else ""
        self.sub_title = f"refresh {config.refresh_seconds:g}s; theme {config.theme}{board_suffix}"
        self._show_wizard = show_wizard
        # Minimize mode: collapses per-sensor details (ThresholdLabels
        # and per-fan detail rows + stopped fans) while keeping braille
        # charts + panel headers + spinning fans visible. Per-session
        # state, not persisted.
        self._minimized = False

    def _visible_help_cards(self) -> list[HelpCard]:
        """Return one `HelpCard` for each failing, non-dismissed prereq."""

        return [
            HelpCard(status, on_dismiss=self._dismiss_card)
            for status in self._prereq_statuses
            if not status.ok and status.id not in self._dismissed_prereqs
        ]

    def _dismiss_card(self, prereq_id: str) -> None:
        """Persist the dismissal so the card stays gone across launches."""

        self._dismissed_prereqs.add(prereq_id)
        write_dismissal(prereq_id)

    def _record_snapshot(self, snap: DeviceSnapshot) -> None:
        """Push every numeric reading in `snap` into the history store.

        Temperatures (CPU / VRM / other) are keyed by `raw_label`; GPU
        temperatures are keyed by the GPU name (which the GpuPanel uses
        as the reading's `raw_label`). Fans / drive events / power /
        memory are not tracked — sparklines are for temperatures only,
        per the v1 scope.
        """

        for reading in (*snap.cpu_temps, *snap.vrm_temps, *snap.other_temps):
            self.history.record(reading.raw_label, reading.value)
        for gpu in snap.gpus:
            self.history.record(gpu.name, gpu.temperature_c)

    def on_mount(self) -> None:
        # Initial size sync — on_resize doesn't always fire reliably
        # at startup on every terminal, so call once with the current
        # size to set the correct MinSizeHint / dashboard-body state.
        self._sync_min_size_visibility(self.size.width, self.size.height)
        if self._show_wizard:
            self.push_screen(FirstRunScreen(self.config))
        else:
            self._start_refresh()

    def _start_refresh(self) -> None:
        """Start the periodic refresh once the app is mounted."""
        self._refresh_timer = self.set_interval(self.config.refresh_seconds, self._refresh_now)

    def restart_refresh_timer(self) -> None:
        """Stop the current refresh timer and start a new one at the live cadence.

        Called by the settings screen when the user changes the
        refresh interval; takes effect immediately so the next tick
        respects the new value rather than waiting for the running
        timer to finish.
        """

        if self._refresh_timer is not None:
            self._refresh_timer.stop()
        self._start_refresh()

    def action_toggle_minimize(self) -> None:
        """Toggle minimize mode: hide/show per-sensor detail rows.

        In minimize mode, panels hide their `.reading-detail` widgets
        and `ThresholdLabel`s (via CSS), and re-render their braille
        charts at 3x normal height so the freed vertical space is
        actually used. The minimize button's label updates to reflect
        the current state.
        """

        self._minimized = not self._minimized
        try:
            body = self.query_one("#dashboard-body")
        except Exception:
            # Body not yet mounted (very early in startup); the next
            # toggle will land.
            return
        if self._minimized:
            body.add_class("minimized")
        else:
            body.remove_class("minimized")

        # Propagate state to every panel that supports it so charts
        # re-render at the larger / smaller height.
        for panel in self.query(".panel-grid > *"):
            if hasattr(panel, "minimized"):
                panel.minimized = self._minimized

    def action_open_settings(self) -> None:
        """Push the settings screen onto the screen stack."""

        self.push_screen(SettingsScreen())

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        # MinSizeHint and the dashboard body are siblings; on_resize
        # toggles their `display` so only one shows at a time. Both
        # take height 1fr of the body area.
        yield MinSizeHint(
            min_width=self.MIN_TERMINAL_WIDTH,
            min_height=self.MIN_TERMINAL_HEIGHT,
            id="min-size-hint",
        )
        with Container(id="dashboard-body"):
            yield StatusHeader(self.snapshot)
            # Help cards stack above the panels; only mounts when there
            # is at least one failing, non-dismissed prereq. The Vertical
            # has `height: auto` so it collapses to zero when empty.
            help_cards = self._visible_help_cards()
            if help_cards:
                yield Vertical(*help_cards, classes="help-cards")
            # Main panel grid: 3 columns x 2 rows. CPU + VRM share the
            # top of the first two columns; Fans + Storage the bottom.
            # GPU spans both rows in the third column for vertical room.
            with Container(classes="panel-grid"):
                yield CpuPanel(self.config, self.snapshot, history=self.history)
                yield VrmPanel(self.config, self.snapshot, history=self.history)
                yield GpuPanel(self.config, self.snapshot, history=self.history)
                yield FansPanel(self.config, self.snapshot)
                yield StoragePanel(self.config, self.snapshot, history=self.history)
        yield Footer()

    def on_resize(self, event: events.Resize) -> None:
        """Swap MinSizeHint vs the dashboard body based on terminal size."""

        self._sync_min_size_visibility(event.size.width, event.size.height)

    def _sync_min_size_visibility(self, width: int, height: int) -> None:
        too_small = width < self.MIN_TERMINAL_WIDTH or height < self.MIN_TERMINAL_HEIGHT
        try:
            hint = self.query_one(MinSizeHint)
            body = self.query_one("#dashboard-body")
        except Exception:
            # Called before compose() finished; the on_resize fired
            # during early mount can race the widget tree. Safe to
            # skip — the post-mount call will re-sync.
            return
        hint.update_current_size(width, height)
        hint.display = too_small
        body.display = not too_small

    def _refresh_now(self) -> None:
        """Fetch a fresh snapshot and push it into every child widget."""
        snap = collect_snapshot(self.config)
        self.snapshot = snap
        # Record into history BEFORE assigning to panels: panels query
        # the store at re-mount time, so the latest sample must already
        # be there when the snapshot setter fires.
        self._record_snapshot(snap)
        # Each widget type has its own `snapshot` attribute
        for header in self.query(StatusHeader):
            header.snapshot = snap
        for cpu in self.query(CpuPanel):
            cpu.snapshot = snap
        for vrm in self.query(VrmPanel):
            vrm.snapshot = snap
        for gpu in self.query(GpuPanel):
            gpu.snapshot = snap
        for storage in self.query(StoragePanel):
            storage.snapshot = snap
        for fans in self.query(FansPanel):
            fans.snapshot = snap

    def action_help(self) -> None:
        """Open the help overlay modal (bindings + panel guide)."""

        self.push_screen(HelpScreen())

    def action_cycle_theme(self) -> None:
        """Advance to the next theme in the curated cycle.

        Also fires `_refresh_now()` so the BrailleChart and
        ThresholdLabel widgets re-render with the new theme's
        success / warning / error colours immediately, instead of
        waiting for the next periodic refresh tick (~2 s).
        """
        new_theme = next_theme_name(self.theme)
        self.theme = new_theme
        self.notify(f"Theme: {new_theme}")
        self._refresh_now()

    def action_refresh(self) -> None:
        """Immediate refresh on `r` keypress."""
        self._refresh_now()


def run(config: Config, *, show_wizard: bool = False) -> int:
    """Entry point. Returns the exit code."""
    Dashboard(config, show_wizard=show_wizard).run()
    return 0
