# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Status header widget for the thermall dashboard."""

from __future__ import annotations

from textual.widgets import Static

from thermall.model import DeviceSnapshot, Reading, Severity


class StatusHeader(Static):
    """A one-line status summary widget.

    Renders one of four colour-coded states based on the highest severity
    in the snapshot. The main line gives a quick verdict, the sub-line
    provides context.
    """

    DEFAULT_CSS = """
    StatusHeader {
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(self, snapshot: DeviceSnapshot | None = None) -> None:
        super().__init__()
        self.snapshot = snapshot

    def watch_snapshot(self, snapshot: DeviceSnapshot | None) -> None:
        """Re-render when the snapshot changes."""
        self.refresh()

    def render(self) -> str:
        """Render the status line based on current snapshot."""
        if self.snapshot is None:
            return self._render_unknown()

        severity = self.snapshot.max_severity

        if severity == Severity.OK:
            return self._render_ok()
        if severity == Severity.WARN:
            return self._render_warn()
        if severity == Severity.CRIT:
            return self._render_crit()
        # Severity.UNKNOWN - but check for warnings
        if self.snapshot.warnings:
            return self._render_warnings()
        return self._render_unknown()

    def _render_warnings(self) -> str:
        """Render warnings-only state."""
        snapshot = self.snapshot
        assert snapshot is not None
        if snapshot.warnings:
            return f"[yellow]Running warm[/yellow]\n{snapshot.warnings[0]}"
        return self._render_unknown()

    def _render_ok(self) -> str:
        return "[green]Everything cool[/green]\nAll sensors within normal range."

    def _render_warn(self) -> str:
        """Render warning state - find the warmest reading."""
        snapshot = self.snapshot
        assert snapshot is not None

        # Find the warmest reading
        warm_reading = self._find_warmest_reading()
        if warm_reading:
            label = warm_reading.display_label or warm_reading.raw_label
            return f"[yellow]Running warm[/yellow]\n{label} at {warm_reading.value:.0f}{warm_reading.unit}"

        # Fallback to warnings
        if snapshot.warnings:
            return f"[yellow]Running warm[/yellow]\n{snapshot.warnings[0]}"

        return "[yellow]Running warm[/yellow]\nOne or more sensors elevated."

    def _render_crit(self) -> str:
        """Render critical state - find critical readings."""
        snapshot = self.snapshot
        assert snapshot is not None

        crit_reading = self._find_critical_reading()
        if crit_reading:
            label = crit_reading.display_label or crit_reading.raw_label
            return f"[red]Needs attention[/red]\n{label} at {crit_reading.value:.0f}{crit_reading.unit}"

        # Check GPUs
        for gpu in snapshot.gpus:
            if gpu.severity == Severity.CRIT:
                return (
                    f"[red]Needs attention[/red]\n{gpu.name} critical at {gpu.temperature_c:.0f}°C"
                )

        # Check drive health events
        for event in snapshot.drive_health_events:
            if event.severity == Severity.CRIT:
                return f"[red]Needs attention[/red]\n{event.message[:50]}..."

        return "[red]Needs attention[/red]\nOne or more sensors at critical levels."

    def _render_unknown(self) -> str:
        return "[dim]No data yet[/dim]\nWaiting for first sensor read."

    def _find_warmest_reading(self) -> Reading | None:
        """Find the highest-severity reading that is WARN.

        Restricted to `primary_temps` so a WARN-graded VRM /
        motherboard reading doesn't drive the subline. The verdict
        and the subline must stay consistent: if `max_severity`
        ignores advisory categories, so must the named reading.
        """
        snapshot = self.snapshot
        assert snapshot is not None

        for r in snapshot.primary_temps:
            if r.severity == Severity.WARN:
                return r

        return None

    def _find_critical_reading(self) -> Reading | None:
        """Find the first critical reading among primary indicators."""
        snapshot = self.snapshot
        assert snapshot is not None

        for r in snapshot.primary_temps:
            if r.severity == Severity.CRIT:
                return r

        return None
