# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the `MinSizeHint` widget and dashboard size-handling."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from thermall.widgets.min_size_hint import MinSizeHint


class _Host(App[None]):
    def __init__(self, hint: MinSizeHint) -> None:
        super().__init__()
        self._hint = hint

    def compose(self) -> ComposeResult:
        yield self._hint


class TestMinSizeHintWidget:
    def test_constructor_stores_minimums(self) -> None:
        hint = MinSizeHint(min_width=100, min_height=30)
        assert hint.min_width == 100
        assert hint.min_height == 30

    def test_initial_message_mentions_required_size(self) -> None:
        hint = MinSizeHint(min_width=100, min_height=30)
        content = str(hint.content)
        assert "100" in content
        assert "30" in content

    def test_update_current_size_changes_message(self) -> None:
        hint = MinSizeHint(min_width=100, min_height=30)
        hint.update_current_size(75, 22)
        content = str(hint.content)
        assert "75" in content
        assert "22" in content

    @pytest.mark.asyncio
    async def test_mounts_in_app_without_error(self) -> None:
        hint = MinSizeHint(min_width=100, min_height=30)
        app = _Host(hint)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert hint.is_mounted


class TestDashboardMinSizeBehavior:
    @pytest.mark.asyncio
    async def test_min_size_hint_hidden_when_terminal_is_large(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from thermall.collectors import (
            NvidiaCollector,
            SensorsCollector,
            SmartdJournalCollector,
        )
        from thermall.config import Config
        from thermall.dashboard import Dashboard

        monkeypatch.setattr(SensorsCollector, "live", classmethod(lambda _cls: "{}"))
        monkeypatch.setattr(NvidiaCollector, "live", classmethod(lambda _cls: ""))
        monkeypatch.setattr(SmartdJournalCollector, "live", classmethod(lambda _cls: ""))

        app = Dashboard(Config(detected_board=None))
        async with app.run_test(size=(160, 60)) as pilot:
            await pilot.pause()
            hint = app.query_one(MinSizeHint)
            body = app.query_one("#dashboard-body")
            # Big terminal: hint hidden, body shown.
            assert hint.display is False
            assert body.display is True

    @pytest.mark.asyncio
    async def test_min_size_hint_shown_when_terminal_is_small(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from thermall.collectors import (
            NvidiaCollector,
            SensorsCollector,
            SmartdJournalCollector,
        )
        from thermall.config import Config
        from thermall.dashboard import Dashboard

        monkeypatch.setattr(SensorsCollector, "live", classmethod(lambda _cls: "{}"))
        monkeypatch.setattr(NvidiaCollector, "live", classmethod(lambda _cls: ""))
        monkeypatch.setattr(SmartdJournalCollector, "live", classmethod(lambda _cls: ""))

        app = Dashboard(Config(detected_board=None))
        # Tiny terminal, below MIN_TERMINAL_WIDTH and MIN_TERMINAL_HEIGHT.
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            hint = app.query_one(MinSizeHint)
            body = app.query_one("#dashboard-body")
            assert hint.display is True
            assert body.display is False

    @pytest.mark.asyncio
    async def test_dashboard_exposes_minimum_constants(self) -> None:
        from thermall.dashboard import Dashboard

        assert isinstance(Dashboard.MIN_TERMINAL_WIDTH, int)
        assert isinstance(Dashboard.MIN_TERMINAL_HEIGHT, int)
        assert Dashboard.MIN_TERMINAL_WIDTH > 0
        assert Dashboard.MIN_TERMINAL_HEIGHT > 0
