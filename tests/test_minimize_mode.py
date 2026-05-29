# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the dashboard's minimize mode (m keybinding).

Toggling minimize adds the `minimized` CSS class to
`#dashboard-body`, which via the dashboard's CSS rules hides
`.reading-detail` widgets and all `ThresholdLabel` widgets. Headers,
braille charts, and spinning fans remain visible.
"""

from __future__ import annotations

import pytest

from thermall.config import Config
from thermall.dashboard import Dashboard


def _stub_collectors(monkeypatch: pytest.MonkeyPatch) -> None:
    from thermall.collectors import (
        NvidiaCollector,
        SensorsCollector,
        SmartdJournalCollector,
    )

    monkeypatch.setattr(SensorsCollector, "live", classmethod(lambda _cls: "{}"))
    monkeypatch.setattr(NvidiaCollector, "live", classmethod(lambda _cls: ""))
    monkeypatch.setattr(SmartdJournalCollector, "live", classmethod(lambda _cls: ""))


class TestMinimizeKeybinding:
    def test_m_binding_present(self) -> None:
        from textual.binding import Binding

        m_bindings = [b for b in Dashboard.BINDINGS if isinstance(b, Binding) and b.key == "m"]
        assert len(m_bindings) == 1
        assert m_bindings[0].action == "toggle_minimize"


class TestMinimizeStateToggle:
    @pytest.mark.asyncio
    async def test_starts_expanded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_collectors(monkeypatch)
        app = Dashboard(Config(detected_board=None))
        async with app.run_test(size=(160, 60)) as pilot:
            await pilot.pause()
            body = app.query_one("#dashboard-body")
            assert "minimized" not in body.classes
            assert app._minimized is False

    @pytest.mark.asyncio
    async def test_press_m_minimizes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_collectors(monkeypatch)
        app = Dashboard(Config(detected_board=None))
        async with app.run_test(size=(160, 60)) as pilot:
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            body = app.query_one("#dashboard-body")
            assert "minimized" in body.classes
            assert app._minimized is True

    @pytest.mark.asyncio
    async def test_press_m_twice_restores(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_collectors(monkeypatch)
        app = Dashboard(Config(detected_board=None))
        async with app.run_test(size=(160, 60)) as pilot:
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            body = app.query_one("#dashboard-body")
            assert "minimized" not in body.classes
            assert app._minimized is False


class TestMinimizeCssRules:
    def test_reading_detail_hidden_under_minimized(self) -> None:
        # Pin the CSS rule shape so a future refactor that drops the
        # `#dashboard-body.minimized` scoping (and accidentally bleeds
        # into the settings modal) is caught.
        css = Dashboard.CSS
        assert "#dashboard-body.minimized .reading-detail" in css
        assert "#dashboard-body.minimized ThresholdLabel" in css
        assert "display: none" in css
