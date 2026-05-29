# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the Dashboard application."""

from __future__ import annotations

import pytest

from thermall.config import Config
from thermall.dashboard import Dashboard
from thermall.widgets.cpu_panel import CpuPanel
from thermall.widgets.fans_panel import FansPanel
from thermall.widgets.gpu_panel import GpuPanel
from thermall.widgets.status_header import StatusHeader
from thermall.widgets.storage_panel import StoragePanel
from thermall.widgets.vrm_panel import VrmPanel


def _stub_collectors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock out all collectors so the Dashboard never shells out."""
    from thermall import refresh as r

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(lambda cls: "{}"))
    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))


@pytest.mark.asyncio
async def test_dashboard_boots_with_panels_mounted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_collectors(monkeypatch)
    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        # All six dashboard widgets present
        assert app.query_one(StatusHeader)
        assert app.query_one(CpuPanel)
        assert app.query_one(VrmPanel)
        assert app.query_one(GpuPanel)
        assert app.query_one(StoragePanel)
        assert app.query_one(FansPanel)
        assert "refresh" in app.sub_title


@pytest.mark.asyncio
async def test_quit_binding_exits_app(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_collectors(monkeypatch)
    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()


def test_dashboard_has_expected_bindings() -> None:
    # Dashboard.BINDINGS is typed as list[BindingType], which is a
    # union of Binding | tuple[str, str] | tuple[str, str, str].
    # Every entry in this dashboard is actually a Binding object, so
    # narrow before reading .key.
    from textual.binding import Binding

    keys = [b.key for b in Dashboard.BINDINGS if isinstance(b, Binding)]
    for required in ("q", "h", "t", "r", "m"):
        assert required in keys, f"missing binding for {required!r}"


@pytest.mark.asyncio
async def test_dashboard_has_initial_snapshot_before_first_paint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # collect_snapshot must run BEFORE compose, so panels and header
    # have a populated snapshot on their very first render. No
    # "no data yet" transient.
    _stub_collectors(monkeypatch)
    app = Dashboard(Config(detected_board=None))
    # The snapshot exists on the App instance after __init__, before
    # any pilot/await pause.
    assert app.snapshot is not None


@pytest.mark.asyncio
async def test_refresh_action_triggers_recollect(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mutate the mocked SensorsCollector.live() between calls so we can
    # observe that the dashboard re-fetched, not just stored the initial.
    from thermall import refresh as r

    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))

    calls: list[int] = []

    def live(cls: object) -> str:
        calls.append(len(calls) + 1)
        return "{}"

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(live))

    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        baseline = len(calls)
        await pilot.press("r")
        await pilot.pause()
        # Pressing r must have re-invoked the sensors collector.
        assert len(calls) > baseline


@pytest.mark.asyncio
async def test_refresh_propagates_snapshot_to_all_widgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # After a refresh, the panel and StatusHeader snapshots must point
    # to the new DeviceSnapshot, not the initial one.
    _stub_collectors(monkeypatch)
    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        initial = app.snapshot
        await pilot.press("r")
        await pilot.pause()
        # New DeviceSnapshot instance after refresh
        assert app.snapshot is not initial
        # All widgets see the same updated snapshot identity
        assert app.query_one(CpuPanel).snapshot is app.snapshot
        assert app.query_one(VrmPanel).snapshot is app.snapshot
        assert app.query_one(GpuPanel).snapshot is app.snapshot
        assert app.query_one(StoragePanel).snapshot is app.snapshot
        assert app.query_one(FansPanel).snapshot is app.snapshot
        assert app.query_one(StatusHeader).snapshot is app.snapshot


@pytest.mark.asyncio
async def test_on_mount_starts_refresh_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    # A `set_interval` call in on_mount registers a periodic callback.
    # Verify the timer is registered. Textual's Timer does not expose
    # the interval as a public attribute, so we only assert that
    # set_interval was called and returned a Timer instance.
    _stub_collectors(monkeypatch)
    from textual.timer import Timer

    config = Config(detected_board=None, refresh_seconds=2.0)
    app = Dashboard(config)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app._refresh_timer is not None
        assert isinstance(app._refresh_timer, Timer)


# ---------------------------------------------------------------------------
# Two-row layout (3 thermal panels on top, storage + fans on the bottom)
# ---------------------------------------------------------------------------
#
# Five panels at `width: 1fr` in a single Horizontal row produced ~20 cols
# per panel on a default 100-col terminal, which clipped Storage's
# Drive | Temp | Health rows so badly that the panel looked empty.
# The 3+2 split gives Storage ~50 cols (half the screen) and keeps the
# thermals legibly side-by-side.


@pytest.mark.asyncio
async def test_dashboard_main_grid_holds_all_five_panels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 3x2 panel grid mounts CPU, VRM, GPU, Fans, Storage."""

    _stub_collectors(monkeypatch)
    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        grids = list(app.query("Container.panel-grid"))
        assert len(grids) == 1
        children = {type(c) for c in grids[0].children}
        assert CpuPanel in children
        assert VrmPanel in children
        assert GpuPanel in children
        assert FansPanel in children
        assert StoragePanel in children


@pytest.mark.asyncio
async def test_dashboard_gpu_panel_spans_two_grid_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GpuPanel CSS sets `row-span: 2` so 3 GPUs fit vertically."""

    _stub_collectors(monkeypatch)
    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        # The row-span is set in Dashboard.CSS; pin the rule's presence
        # so a future regression that removes it is caught.
        assert "row-span: 2" in Dashboard.CSS


@pytest.mark.asyncio
async def test_dashboard_has_no_bottom_animation_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bottom animation + credits row was removed in favour of
    keeping the tool resource-light. Pinning the absence guards
    against accidental re-introduction."""

    _stub_collectors(monkeypatch)
    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        rows = list(app.query("Horizontal.bottom-row"))
        assert rows == []


# ---------------------------------------------------------------------------
# Theme cycle (12j)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_loads_default_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    """First paint uses the curated default theme."""
    from thermall.themes import DEFAULT_THEME

    _stub_collectors(monkeypatch)
    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.theme == DEFAULT_THEME


@pytest.mark.asyncio
async def test_dashboard_registers_all_curated_themes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every theme in `ALL_THEMES` is registered and selectable by name."""
    from thermall.themes import ALL_THEMES

    _stub_collectors(monkeypatch)
    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        for theme in ALL_THEMES:
            app.theme = theme.name
            await pilot.pause()
            assert app.theme == theme.name


@pytest.mark.asyncio
async def test_t_key_cycles_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pressing `t` advances through the curated cycle."""
    from thermall.themes import THEME_CYCLE

    _stub_collectors(monkeypatch)
    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        # Start at default (THEME_CYCLE[0]); pressing `t` lands us at [1].
        assert app.theme == THEME_CYCLE[0]
        await pilot.press("t")
        await pilot.pause()
        assert app.theme == THEME_CYCLE[1]
        await pilot.press("t")
        await pilot.pause()
        assert app.theme == THEME_CYCLE[2]


@pytest.mark.asyncio
async def test_t_key_wraps_around(monkeypatch: pytest.MonkeyPatch) -> None:
    """A full cycle of `t` presses returns to the starting theme."""
    from thermall.themes import THEME_CYCLE

    _stub_collectors(monkeypatch)
    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        start = app.theme
        for _ in range(len(THEME_CYCLE)):
            await pilot.press("t")
            await pilot.pause()
        assert app.theme == start


# ---------------------------------------------------------------------------
# Sparkline history (12m)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_has_history_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dashboard owns a HistoryStore for sparkline rendering."""
    from thermall.history import HistoryStore

    _stub_collectors(monkeypatch)
    app = Dashboard(Config(detected_board=None))
    assert isinstance(app.history, HistoryStore)


@pytest.mark.asyncio
async def test_dashboard_seeds_history_at_init(monkeypatch: pytest.MonkeyPatch) -> None:
    """Initial snapshot lands in history before the first paint.

    Means the very first frame already shows a single-cell sparkline
    rather than blank space.
    """
    from thermall import refresh as r

    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))
    # Single CPU reading that will surface as a snapshot temperature.
    monkeypatch.setattr(
        r.SensorsCollector,
        "live",
        classmethod(
            lambda cls: '{"k10temp-pci-00c3": {"Adapter": "x", "Tctl": {"temp1_input": 45.0}}}'
        ),
    )

    app = Dashboard(Config(detected_board=None))
    # History should carry the initial CPU sample, keyed by raw_label.
    samples = app.history.get("k10temp Tctl")
    assert samples == (45.0,)


@pytest.mark.asyncio
async def test_refresh_appends_to_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each refresh tick records a new sample per reading."""
    from thermall import refresh as r

    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))

    # First call returns 45.0, second returns 46.0; verifies that the
    # refresh action recollects AND records, not just reuses the seed.
    values = iter([45.0, 46.0, 47.0])

    def live(cls: object) -> str:
        v = next(values)
        return f'{{"k10temp-pci-00c3": {{"Adapter": "x", "Tctl": {{"temp1_input": {v}}}}}}}'

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(live))

    app = Dashboard(Config(detected_board=None))
    # First sample seeded at init.
    assert app.history.get("k10temp Tctl") == (45.0,)

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        samples = app.history.get("k10temp Tctl")
        assert len(samples) >= 2
        assert samples[-1] == 46.0


@pytest.mark.asyncio
async def test_braille_chart_visible_in_thermal_panels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At least one BrailleChart widget mounts inside the panels.

    Doesn't pin a count (collector mock-driven snapshot would be a
    fragile pin); just asserts the integration is wired through:
    Dashboard passes history to panels, panels render a braille chart
    for the hottest reading when history has data.
    """
    from thermall import refresh as r
    from thermall.widgets.braillechart import BrailleChart

    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(
        r.SensorsCollector,
        "live",
        classmethod(
            lambda cls: '{"k10temp-pci-00c3": {"Adapter": "x", "Tctl": {"temp1_input": 45.0}}}'
        ),
    )

    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        charts = list(app.query(BrailleChart))
        assert len(charts) >= 1


@pytest.mark.asyncio
async def test_collector_failures_dont_crash_dashboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # All three collectors unavailable; dashboard must still boot and
    # mount panels (each panel shows its own friendly empty state).
    from thermall import refresh as r
    from thermall.collectors import CollectorUnavailableError

    def fail(cls: object) -> str:
        raise CollectorUnavailableError("nope")

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(fail))
    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(fail))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(fail))

    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        # Dashboard still booted with all panels
        assert app.query_one(CpuPanel)
        assert app.query_one(FansPanel)
        # Snapshot is populated (empty, but not None)
        assert app.snapshot is not None
        assert app.snapshot.smartd_available is False
