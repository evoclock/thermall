# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the help overlay modal and dashboard action wiring."""

from __future__ import annotations

import pytest

from thermall.config import Config
from thermall.dashboard import Dashboard
from thermall.screens.help import HelpScreen


def _stub_collectors(monkeypatch: pytest.MonkeyPatch) -> None:
    from thermall.collectors import (
        NvidiaCollector,
        SensorsCollector,
        SmartdJournalCollector,
    )

    monkeypatch.setattr(SensorsCollector, "live", classmethod(lambda _cls: "{}"))
    monkeypatch.setattr(NvidiaCollector, "live", classmethod(lambda _cls: ""))
    monkeypatch.setattr(SmartdJournalCollector, "live", classmethod(lambda _cls: ""))


class TestHelpScreenStructure:
    def test_screens_package_exports_help_screen(self) -> None:
        from thermall import screens

        assert hasattr(screens, "HelpScreen")
        assert screens.HelpScreen is HelpScreen

    def test_help_screen_has_close_action(self) -> None:
        # The Escape binding must call action_close on this screen.
        from textual.binding import Binding

        escape_bindings = [
            b
            for b in HelpScreen.BINDINGS
            if isinstance(b, Binding) and b.key == "escape" and b.action == "close"
        ]
        assert len(escape_bindings) == 1


class TestDashboardActionsPushHelpScreen:
    @pytest.mark.asyncio
    async def test_press_h_pushes_help_screen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_collectors(monkeypatch)
        app = Dashboard(Config(detected_board=None))
        async with app.run_test(size=(160, 60)) as pilot:
            await pilot.pause()
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)

    @pytest.mark.asyncio
    async def test_escape_dismisses_help_screen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_collectors(monkeypatch)
        app = Dashboard(Config(detected_board=None))
        async with app.run_test(size=(160, 60)) as pilot:
            await pilot.pause()
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, HelpScreen)


class TestHelpContent:
    @pytest.mark.asyncio
    async def test_help_lists_every_dashboard_binding_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The help overlay must mention every keybinding the dashboard
        # actually offers; otherwise the docs drift from reality.
        from textual.binding import Binding

        from thermall.screens.help import _KEY_BINDINGS

        documented_tokens = " ".join(key for key, _ in _KEY_BINDINGS)

        for binding in Dashboard.BINDINGS:
            if not isinstance(binding, Binding):
                continue
            assert binding.key in documented_tokens, (
                f"binding `{binding.key}` not documented in HelpScreen _KEY_BINDINGS"
            )
