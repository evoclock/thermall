# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the `HelpCard` widget and dashboard integration."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from thermall.prereqs import PrereqStatus
from thermall.widgets.help_card import HelpCard


def _fail_status(id: str = "sensors") -> PrereqStatus:
    return PrereqStatus(
        id=id,
        name="lm-sensors",
        ok=False,
        install_command="sudo apt install lm-sensors",
        friendly_message="Install lm-sensors to see CPU, motherboard, and storage temperatures.",
    )


class _Host(App[None]):
    def __init__(self, card: HelpCard) -> None:
        super().__init__()
        self._card = card

    def compose(self) -> ComposeResult:
        yield self._card


class TestHelpCardConstruction:
    def test_carries_prereq(self) -> None:
        status = _fail_status()
        card = HelpCard(status)
        assert card.prereq is status

    def test_id_derived_from_prereq(self) -> None:
        card = HelpCard(_fail_status("sensors"))
        assert card.id == "help-card-sensors"

    def test_can_focus_for_dismissal(self) -> None:
        # The `d` binding requires focus; the class attribute drives that.
        assert HelpCard.can_focus is True


class TestHelpCardRendering:
    @pytest.mark.asyncio
    async def test_mounts_with_message_and_command(self) -> None:
        status = _fail_status()
        card = HelpCard(status)
        async with _Host(card).run_test() as pilot:
            await pilot.pause()
            assert card.is_mounted
            # Both Static children are present (message + command).
            statics = list(card.query(Static))
            assert len(statics) == 2
            contents = [str(s.content) for s in statics]
            assert any(status.friendly_message in c for c in contents)
            assert any(status.install_command in c for c in contents)

    @pytest.mark.asyncio
    async def test_dismiss_removes_card_from_app(self) -> None:
        status = _fail_status()
        card = HelpCard(status)
        async with _Host(card).run_test() as pilot:
            await pilot.pause()
            # Confirm baseline: the screen has the card before dismiss.
            assert len(pilot.app.query(HelpCard)) == 1
            await card.remove()
            await pilot.pause()
            # After removal the screen has no HelpCard children.
            assert len(pilot.app.query(HelpCard)) == 0

    @pytest.mark.asyncio
    async def test_dismiss_invokes_callback_with_prereq_id(self) -> None:
        seen: list[str] = []
        card = HelpCard(_fail_status("smartd"), on_dismiss=lambda pid: seen.append(pid))
        async with _Host(card).run_test() as pilot:
            await pilot.pause()
            card.action_dismiss()
            await pilot.pause()
            # Callback fires synchronously in action_dismiss; the
            # remove() that follows is async and not waited on here.
            assert seen == ["smartd"]

    @pytest.mark.asyncio
    async def test_dismiss_without_callback_does_not_raise(self) -> None:
        # on_dismiss=None is the test-default path; must not crash.
        card = HelpCard(_fail_status())
        async with _Host(card).run_test() as pilot:
            await pilot.pause()
            # No exception raised even with on_dismiss=None.
            card.action_dismiss()
            await pilot.pause()


# ---------------------------------------------------------------------------
# Config state-file helpers (load_dismissed / write_dismissal / clear_dismissed)
# ---------------------------------------------------------------------------


class TestConfigStateHelpers:
    def test_load_dismissed_returns_empty_when_file_missing(self, tmp_path: Path) -> None:
        from thermall.config import load_dismissed

        target = tmp_path / "state.toml"
        assert load_dismissed(target) == set()

    def test_load_dismissed_reads_existing(self, tmp_path: Path) -> None:
        from thermall.config import load_dismissed

        target = tmp_path / "state.toml"
        target.write_text('[help_cards]\ndismissed = ["sensors", "smartd"]\n')
        assert load_dismissed(target) == {"sensors", "smartd"}

    def test_load_dismissed_handles_corrupt_toml(self, tmp_path: Path) -> None:
        from thermall.config import load_dismissed

        target = tmp_path / "state.toml"
        target.write_text("this is not valid toml [[[ \n")
        # Corrupt file is a soft reset, not a crash.
        assert load_dismissed(target) == set()

    def test_load_dismissed_handles_unexpected_shape(self, tmp_path: Path) -> None:
        from thermall.config import load_dismissed

        target = tmp_path / "state.toml"
        # `dismissed` written as a string, not a list.
        target.write_text('[help_cards]\ndismissed = "sensors"\n')
        assert load_dismissed(target) == set()

    def test_write_dismissal_creates_state_file(self, tmp_path: Path) -> None:
        from thermall.config import load_dismissed, write_dismissal

        target = tmp_path / "thermall" / "state.toml"
        write_dismissal("sensors", target)
        assert target.exists()
        assert load_dismissed(target) == {"sensors"}

    def test_write_dismissal_appends_without_duplicates(self, tmp_path: Path) -> None:
        from thermall.config import load_dismissed, write_dismissal

        target = tmp_path / "state.toml"
        write_dismissal("sensors", target)
        write_dismissal("smartd", target)
        write_dismissal("sensors", target)  # duplicate
        assert load_dismissed(target) == {"sensors", "smartd"}

    def test_clear_dismissed_empties_the_list(self, tmp_path: Path) -> None:
        from thermall.config import clear_dismissed, load_dismissed, write_dismissal

        target = tmp_path / "state.toml"
        write_dismissal("sensors", target)
        write_dismissal("smartd", target)
        clear_dismissed(target)
        assert load_dismissed(target) == set()

    def test_clear_dismissed_safe_when_file_missing(self, tmp_path: Path) -> None:
        from thermall.config import clear_dismissed, load_dismissed

        target = tmp_path / "state.toml"
        clear_dismissed(target)
        assert load_dismissed(target) == set()


# ---------------------------------------------------------------------------
# Dashboard integration
# ---------------------------------------------------------------------------


def _stub_collectors(monkeypatch: pytest.MonkeyPatch) -> None:
    from thermall import refresh as r

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(lambda cls: "{}"))
    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))


@pytest.mark.asyncio
async def test_dashboard_shows_no_cards_when_all_prereqs_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from thermall.config import Config
    from thermall.dashboard import Dashboard

    _stub_collectors(monkeypatch)
    monkeypatch.setattr(
        "thermall.dashboard.check_all",
        lambda: tuple(
            PrereqStatus(id=i, name=i, ok=True, install_command="", friendly_message="")
            for i in ("sensors", "nct6775", "smartd")
        ),
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert list(app.query(HelpCard)) == []


@pytest.mark.asyncio
async def test_dashboard_shows_three_cards_when_all_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from thermall.config import Config
    from thermall.dashboard import Dashboard

    _stub_collectors(monkeypatch)
    monkeypatch.setattr(
        "thermall.dashboard.check_all",
        lambda: tuple(
            PrereqStatus(
                id=i,
                name=i,
                ok=False,
                install_command=f"install {i}",
                friendly_message=f"please install {i}",
            )
            for i in ("sensors", "nct6775", "smartd")
        ),
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        cards = list(app.query(HelpCard))
        assert len(cards) == 3


@pytest.mark.asyncio
async def test_dashboard_hides_dismissed_cards(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from thermall.config import Config, write_dismissal
    from thermall.dashboard import Dashboard

    _stub_collectors(monkeypatch)
    monkeypatch.setattr(
        "thermall.dashboard.check_all",
        lambda: tuple(
            PrereqStatus(
                id=i,
                name=i,
                ok=False,
                install_command=f"install {i}",
                friendly_message=f"please install {i}",
            )
            for i in ("sensors", "nct6775", "smartd")
        ),
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    # Pre-seed: user already dismissed the smartd card on a prior launch.
    state_file = tmp_path / "thermall" / "state.toml"
    write_dismissal("smartd", state_file)

    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        ids = {card.prereq.id for card in app.query(HelpCard)}
        assert ids == {"sensors", "nct6775"}


@pytest.mark.asyncio
async def test_dismissing_card_persists_to_state_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from thermall.config import Config, load_dismissed
    from thermall.dashboard import Dashboard

    _stub_collectors(monkeypatch)
    monkeypatch.setattr(
        "thermall.dashboard.check_all",
        lambda: (
            PrereqStatus(
                id="sensors",
                name="sensors",
                ok=False,
                install_command="install sensors",
                friendly_message="install sensors",
            ),
        ),
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    app = Dashboard(Config(detected_board=None))
    async with app.run_test() as pilot:
        await pilot.pause()
        card = app.query_one(HelpCard)
        card.action_dismiss()
        await pilot.pause()
        # State file written; dismissal persisted.
        assert load_dismissed(tmp_path / "thermall" / "state.toml") == {"sensors"}
