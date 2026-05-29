# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the `SettingsScreen` modal."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Button, Static

from thermall.config import Config, load, write_dismissal
from thermall.dashboard import Dashboard
from thermall.screens.settings import REFRESH_INTERVAL_OPTIONS, SettingsScreen


def _stub_collectors(monkeypatch: pytest.MonkeyPatch) -> None:
    from thermall import refresh as r

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(lambda cls: "{}"))
    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))


def _stub_prereqs_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub `check_all` to report every prereq passing, so no help cards mount."""
    from thermall.prereqs import PrereqStatus

    monkeypatch.setattr(
        "thermall.dashboard.check_all",
        lambda: tuple(
            PrereqStatus(id=i, name=i, ok=True, install_command="", friendly_message="")
            for i in ("sensors", "nct6775", "smartd")
        ),
    )


class TestKeybindingAndOpenClose:
    @pytest.mark.asyncio
    async def test_s_opens_settings_screen(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        app = Dashboard(Config(detected_board=None))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            # The active (topmost) screen should now be SettingsScreen.
            assert isinstance(app.screen, SettingsScreen)

    @pytest.mark.asyncio
    async def test_escape_closes_settings_screen(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        app = Dashboard(Config(detected_board=None))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            # Settings is popped; the main dashboard is the active screen.
            assert not isinstance(app.screen, SettingsScreen)

    @pytest.mark.asyncio
    async def test_close_button_closes_settings_screen(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        app = Dashboard(Config(detected_board=None))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            close_btn = app.screen.query_one("#close-settings", Button)
            close_btn.press()
            await pilot.pause()
            await pilot.pause()
            assert not isinstance(app.screen, SettingsScreen)

    @pytest.mark.asyncio
    async def test_modal_renders_visible_close_hint(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        app = Dashboard(Config(detected_board=None))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            hint_lines = [str(s.content) for s in app.screen.query(Static).filter(".modal-hint")]
            assert any("Esc" in h for h in hint_lines)
            assert any("Close" in h for h in hint_lines)


class TestRenderedSections:
    @pytest.mark.asyncio
    async def test_renders_three_section_headers(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        app = Dashboard(Config(detected_board=None))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            headers = [str(s.content) for s in app.screen.query(Static).filter(".section-header")]
            assert any("Refresh interval" in h for h in headers)
            assert any("Help cards" in h for h in headers)
            assert any("Advanced" in h for h in headers)

    @pytest.mark.asyncio
    async def test_renders_one_button_per_refresh_option(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        app = Dashboard(Config(detected_board=None))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            buttons = list(app.screen.query("Button.refresh-option"))
            assert len(buttons) == len(REFRESH_INTERVAL_OPTIONS)

    @pytest.mark.asyncio
    async def test_current_refresh_button_is_highlighted(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        # Default config has refresh_seconds=2.0; the "2 s" button
        # should have the `selected` class.
        app = Dashboard(Config(detected_board=None, refresh_seconds=2.0))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            btn = app.screen.query_one("#refresh-2", Button)
            assert "selected" in btn.classes

    @pytest.mark.asyncio
    async def test_advanced_section_is_static_text_not_interactive(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        app = Dashboard(Config(detected_board=None))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            advanced_lines = list(app.screen.query(".advanced-line"))
            assert len(advanced_lines) >= 2
            # No advanced-line should be a Button.
            for line in advanced_lines:
                assert not isinstance(line, Button)


class TestChangingRefreshInterval:
    @pytest.mark.asyncio
    async def test_pressing_refresh_button_writes_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        app = Dashboard(Config(detected_board=None, refresh_seconds=2.0))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            btn = app.screen.query_one("#refresh-5", Button)
            btn.press()
            await pilot.pause()
            await pilot.pause()
            # Live config updated.
            assert app.config.refresh_seconds == 5.0
            # And written to disk: re-loading config returns the new value.
            config_path = tmp_path / "thermall" / "config.toml"
            assert config_path.exists()
            reloaded = load(config_path)
            assert reloaded.refresh_seconds == 5.0

    @pytest.mark.asyncio
    async def test_changing_refresh_restarts_timer(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        app = Dashboard(Config(detected_board=None, refresh_seconds=2.0))
        async with app.run_test() as pilot:
            await pilot.pause()
            old_timer = app._refresh_timer
            await pilot.press("s")
            await pilot.pause()
            btn = app.screen.query_one("#refresh-1", Button)
            btn.press()
            await pilot.pause()
            await pilot.pause()
            # Timer was restarted (new Timer instance, distinct from old).
            assert app._refresh_timer is not None
            assert app._refresh_timer is not old_timer

    @pytest.mark.asyncio
    async def test_new_button_becomes_highlighted_after_change(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        app = Dashboard(Config(detected_board=None, refresh_seconds=2.0))
        # SettingsScreen modal hosts a 128-char-wide pixel-art header
        # (SettingsAnimation) plus the settings body; this exceeds
        # pilot's default 80x24 viewport and pushes click targets
        # off-screen. Oversized headless terminal restores them.
        async with app.run_test(size=(160, 60)) as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            new_btn = app.screen.query_one("#refresh-10", Button)
            old_btn = app.screen.query_one("#refresh-2", Button)
            await pilot.click(new_btn)
            await pilot.pause()
            assert "selected" in new_btn.classes
            assert "selected" not in old_btn.classes


class TestHelpCardReset:
    @pytest.mark.asyncio
    async def test_pressing_reset_clears_dismissed_state(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        # Pre-seed: user dismissed two cards previously.
        state_file = tmp_path / "thermall" / "state.toml"
        write_dismissal("sensors", state_file)
        write_dismissal("smartd", state_file)

        app = Dashboard(Config(detected_board=None))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            btn = app.screen.query_one("#reset-help-cards", Button)
            btn.press()
            await pilot.pause()
            await pilot.pause()
            # State file is now empty.
            from thermall.config import load_dismissed

            assert load_dismissed(state_file) == set()

    @pytest.mark.asyncio
    async def test_reset_when_state_file_does_not_exist(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        # No pre-existing state file.
        app = Dashboard(Config(detected_board=None))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            btn = app.screen.query_one("#reset-help-cards", Button)
            # Must not raise.
            btn.press()
            await pilot.pause()
            await pilot.pause()


class TestConditionalAnimation:
    @pytest.mark.asyncio
    async def test_animation_mounts_on_large_terminal(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        from thermall.widgets.settings_animation import SettingsAnimation

        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        app = Dashboard(Config(detected_board=None))
        # Above the animation threshold (138x40).
        async with app.run_test(size=(160, 60)) as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            animations = list(app.screen.query(SettingsAnimation))
            assert len(animations) == 1

    @pytest.mark.asyncio
    async def test_animation_skipped_on_small_terminal(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        from thermall.widgets.settings_animation import SettingsAnimation

        _stub_collectors(monkeypatch)
        _stub_prereqs_ok(monkeypatch)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

        app = Dashboard(Config(detected_board=None))
        # Below the animation threshold; settings controls must still render.
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            animations = list(app.screen.query(SettingsAnimation))
            assert animations == []
            # Settings controls still mount: Close button must exist.
            close_btn = app.screen.query_one("#close-settings", Button)
            assert close_btn is not None
