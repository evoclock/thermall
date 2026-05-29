# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for `FansPanel`.

Built via RED-GREEN-REFACTOR cycles. Each commit aims to keep a
narrow failing scope and the minimal implementation to clear it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from thermall.config import Config
from thermall.model import DeviceSnapshot, Fan
from thermall.widgets.fans_panel import FansPanel, _is_cpu_fan


def _snap(fans: tuple[Fan, ...] = ()) -> DeviceSnapshot:
    return DeviceSnapshot(
        taken_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        fans=fans,
    )


class _PanelApp(App[None]):
    def __init__(self, panel: FansPanel) -> None:
        super().__init__()
        self._panel = panel

    def compose(self) -> ComposeResult:
        yield self._panel


def _rendered_strings(panel: FansPanel) -> list[str]:
    """Return the rendered text of each Static descendant in the panel."""

    return [str(child.render()) for child in panel.query(Static)]


# ---------------------------------------------------------------------------
# Round 1 — structure: panel constructs and renders a header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_panel_constructs_and_mounts_header() -> None:
    panel = FansPanel(Config(), _snap())
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        rendered = _rendered_strings(panel)
        assert any("Fans" in s for s in rendered)


# ---------------------------------------------------------------------------
# Round 2 — empty state shows friendly nct6775 install hint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_fans_shows_nct6775_hint() -> None:
    panel = FansPanel(Config(), _snap(fans=()))
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        rendered = _rendered_strings(panel)
        assert any("nct6775" in s for s in rendered)
        assert any("Nuvoton" in s for s in rendered)


# ---------------------------------------------------------------------------
# Round 3 — a single spinning fan renders label + RPM + "Spinning"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_fan_renders_label_rpm_and_spinning_status() -> None:
    panel = FansPanel(
        Config(),
        _snap(fans=(Fan(raw_label="nct6798 fan3", rpm=900, display_label="Chassis front"),)),
    )
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        rendered = _rendered_strings(panel)
        joined = "\n".join(rendered)
        assert "Chassis front" in joined
        assert "900" in joined
        assert "Spinning" in joined


# ---------------------------------------------------------------------------
# Round 4 — zero-RPM fans mark "Stopped"; multiple fans sort by raw_label
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_rpm_fan_marks_stopped() -> None:
    panel = FansPanel(
        Config(),
        _snap(fans=(Fan(raw_label="nct6798 fan6", rpm=0, display_label="NVMe heatsink"),)),
    )
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        rendered = "\n".join(_rendered_strings(panel))
        assert "Stopped" in rendered
        assert "Spinning" not in rendered


@pytest.mark.asyncio
async def test_multiple_fans_sort_by_raw_label_for_stable_ordering() -> None:
    # Pass fans in random-ish order; rendered output should be sorted
    # by raw_label so the dashboard does not flicker between refreshes
    # if the collector returns the same set in a different order.
    fans = (
        Fan(raw_label="nct6798 fan5", rpm=1100, display_label="Chassis top"),
        Fan(raw_label="nct6798 fan2", rpm=800, display_label="AIO pump"),
        Fan(raw_label="nct6798 fan4", rpm=900, display_label="Chassis rear"),
    )
    panel = FansPanel(Config(), _snap(fans=fans))
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        rendered = _rendered_strings(panel)
        # Skip the header (Fans); the next three lines are fan rows in sorted order.
        fan_rows = [s for s in rendered if "Fans" not in s or "RPM" in s]
        # Find each label's index in the rendered list and assert ordering.
        ordering = [
            next(i for i, s in enumerate(fan_rows) if label in s)
            for label in ("AIO pump", "Chassis rear", "Chassis top")
        ]
        assert ordering == sorted(ordering)


# ---------------------------------------------------------------------------
# Round 5 — CPU-named fans are filtered out (CpuPanel renders them)
# ---------------------------------------------------------------------------


class TestIsCpuFan:
    """Cover the discrete-word matching helper directly."""

    def test_matches_cpu_word_in_raw_label(self) -> None:
        assert _is_cpu_fan(Fan(raw_label="cpu_fan", rpm=1000)) is True

    def test_matches_via_display_label(self) -> None:
        assert _is_cpu_fan(Fan(raw_label="fan1", rpm=1000, display_label="CPU fan")) is True

    def test_does_not_match_chassis_fan(self) -> None:
        assert _is_cpu_fan(Fan(raw_label="fan3", rpm=900, display_label="Chassis front")) is False

    def test_does_not_match_cputin_substring(self) -> None:
        # "cputin" contains "cpu" as a substring but not as a discrete
        # token; the helper must reject it.
        assert _is_cpu_fan(Fan(raw_label="cputin_fan", rpm=900)) is False

    def test_does_not_match_unrelated_fan_no_display_label(self) -> None:
        assert _is_cpu_fan(Fan(raw_label="fan1", rpm=1500)) is False

    def test_case_insensitive(self) -> None:
        assert _is_cpu_fan(Fan(raw_label="CPU", rpm=1000)) is True


@pytest.mark.asyncio
async def test_cpu_fans_filtered_out_of_fans_panel() -> None:
    # CpuPanel renders the CPU fan; FansPanel must NOT duplicate it.
    fans = (
        Fan(raw_label="fan1", rpm=1450, display_label="CPU"),
        Fan(raw_label="nct6798 fan3", rpm=900, display_label="Chassis front"),
    )
    panel = FansPanel(Config(), _snap(fans=fans))
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        rendered = "\n".join(_rendered_strings(panel))
        assert "Chassis front" in rendered
        assert "CPU" not in rendered or "Chassis" in rendered  # CPU fan filtered
        # Stronger check: the literal label "CPU:" (which would appear
        # in the fan row "CPU: 1450 RPM (Spinning)") must be absent.
        assert "CPU: " not in rendered


# ---------------------------------------------------------------------------
# Round 6 — reactivity: snapshot setter rebuilds children
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_panel_updates_on_snapshot_change() -> None:
    initial = _snap(
        fans=(Fan(raw_label="nct6798 fan3", rpm=900, display_label="Chassis"),),
    )
    panel = FansPanel(Config(), initial)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        before = "\n".join(_rendered_strings(panel))
        assert "900" in before

        panel.snapshot = _snap(
            fans=(Fan(raw_label="nct6798 fan3", rpm=1400, display_label="Chassis"),),
        )
        await pilot.pause()
        after = "\n".join(_rendered_strings(panel))
        assert "1400" in after
        assert "900" not in after


@pytest.mark.asyncio
async def test_transition_from_populated_to_empty_shows_hint() -> None:
    populated = _snap(fans=(Fan(raw_label="nct6798 fan3", rpm=900),))
    panel = FansPanel(Config(), populated)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        panel.snapshot = _snap(fans=())
        await pilot.pause()
        rendered = "\n".join(_rendered_strings(panel))
        assert "nct6775" in rendered


@pytest.mark.asyncio
async def test_cpu_only_fans_treated_as_empty() -> None:
    # If the only visible fan is the CPU fan (rendered by CpuPanel),
    # this panel has nothing to show and surfaces the install hint.
    cpu_only = _snap(fans=(Fan(raw_label="cpu_fan", rpm=1500, display_label="CPU"),))
    panel = FansPanel(Config(), cpu_only)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        rendered = "\n".join(_rendered_strings(panel))
        assert "nct6775" in rendered
        # The CPU fan label does not leak through
        assert "CPU: 1500" not in rendered


# ---------------------------------------------------------------------------
# Round 7 — edge cases: extreme RPM, no display label, sort stability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extreme_rpm_renders_without_overflow() -> None:
    panel = FansPanel(
        Config(),
        _snap(fans=(Fan(raw_label="nct6798 fan1", rpm=10000),)),
    )
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        rendered = "\n".join(_rendered_strings(panel))
        assert "10000" in rendered
        assert "Spinning" in rendered


@pytest.mark.asyncio
async def test_fan_without_display_label_uses_raw_label() -> None:
    panel = FansPanel(
        Config(),
        _snap(fans=(Fan(raw_label="nct6798 fan1", rpm=1200),)),
    )
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        rendered = "\n".join(_rendered_strings(panel))
        assert "nct6798 fan1" in rendered


@pytest.mark.asyncio
async def test_sort_is_stable_across_identical_input_in_different_order() -> None:
    # Two fan tuples with the same elements in different orders should
    # produce identical rendered output (stable across collector returns).
    fans_a = (
        Fan(raw_label="nct6798 fan1", rpm=1450, display_label="A"),
        Fan(raw_label="nct6798 fan2", rpm=900, display_label="B"),
        Fan(raw_label="nct6798 fan3", rpm=700, display_label="C"),
    )
    fans_b = (fans_a[2], fans_a[0], fans_a[1])

    panel_a = FansPanel(Config(), _snap(fans=fans_a))
    panel_b = FansPanel(Config(), _snap(fans=fans_b))

    async with _PanelApp(panel_a).run_test() as pilot:
        await pilot.pause()
        rendered_a = _rendered_strings(panel_a)
    async with _PanelApp(panel_b).run_test() as pilot:
        await pilot.pause()
        rendered_b = _rendered_strings(panel_b)

    assert rendered_a == rendered_b


@pytest.mark.asyncio
async def test_only_cpu_fan_present_does_not_render_fan_row_for_it() -> None:
    # Boundary: a single CPU fan should not appear in this panel even
    # though the snapshot has exactly one fan.
    snapshot = _snap(
        fans=(Fan(raw_label="cpu_fan", rpm=1450, display_label="CPU"),),
    )
    panel = FansPanel(Config(), snapshot)
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        rendered = _rendered_strings(panel)
        # No row containing "RPM"; the install hint is present instead.
        assert not any("RPM" in s for s in rendered)


@pytest.mark.asyncio
async def test_negative_rpm_handled_without_crash() -> None:
    # Some sensors momentarily report negative values during init.
    # Render without error; treat as Spinning since rpm != 0.
    panel = FansPanel(
        Config(),
        _snap(fans=(Fan(raw_label="nct6798 fan1", rpm=-1),)),
    )
    async with _PanelApp(panel).run_test() as pilot:
        await pilot.pause()
        rendered = "\n".join(_rendered_strings(panel))
        assert "-1" in rendered
        # Spinning because rpm != 0, even if the value is nonsensical.
        # The user sees the strange value and can investigate.
        assert "Spinning" in rendered
