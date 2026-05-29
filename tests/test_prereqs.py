# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for `thermall.prereqs`."""

from __future__ import annotations

import subprocess

import pytest

from thermall.prereqs import (
    PrereqStatus,
    check_all,
    check_nct6775,
    check_sensors,
    check_smartd,
)


def _completed(returncode: int, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout)


class TestCheckSensors:
    def test_ok_when_on_path(self) -> None:
        result = check_sensors(which=lambda cmd: "/usr/bin/sensors")
        assert isinstance(result, PrereqStatus)
        assert result.id == "sensors"
        assert result.ok is True

    def test_fails_when_absent(self) -> None:
        result = check_sensors(which=lambda cmd: None)
        assert result.ok is False
        # Friendly text always mentions the install command's package.
        assert "lm-sensors" in result.friendly_message
        assert result.install_command

    def test_only_looks_up_sensors_command(self) -> None:
        # The injected `which` should be called exactly with "sensors".
        seen: list[str] = []

        def fake(cmd: str) -> str | None:
            seen.append(cmd)
            return "/usr/bin/sensors"

        check_sensors(which=fake)
        assert seen == ["sensors"]


class TestCheckSmartd:
    def test_ok_when_systemctl_reports_active(self) -> None:
        result = check_smartd(
            which=lambda cmd: f"/usr/bin/{cmd}",
            run=lambda argv: _completed(0),
        )
        assert result.id == "smartd"
        assert result.ok is True

    def test_fails_when_systemctl_reports_inactive(self) -> None:
        result = check_smartd(
            which=lambda cmd: f"/usr/bin/{cmd}",
            run=lambda argv: _completed(3),
        )
        assert result.ok is False
        assert "smartmontools" in result.friendly_message

    def test_handles_systemctl_missing(self) -> None:
        # No systemctl on PATH (containers, restricted envs); the
        # check must still return a sensible failure status without
        # raising.
        result = check_smartd(which=lambda cmd: None, run=lambda argv: _completed(0))
        assert result.ok is False
        assert result.install_command  # still suggests installation

    def test_handles_run_raising_oserror(self) -> None:
        def boom(argv: list[str]) -> subprocess.CompletedProcess[str]:
            raise OSError("no such directory")

        result = check_smartd(which=lambda cmd: "/usr/bin/systemctl", run=boom)
        assert result.ok is False

    def test_handles_run_timing_out(self) -> None:
        def slow(argv: list[str]) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=1.0)

        result = check_smartd(which=lambda cmd: "/usr/bin/systemctl", run=slow)
        assert result.ok is False


class TestCheckNct6775:
    def test_ok_when_module_loaded(self) -> None:
        contents = (
            "ext4 1056768 1 - Live 0x0000000000000000\nnct6775 65536 0 - Live 0x0000000000000000\n"
        )
        result = check_nct6775(read_modules=lambda: contents)
        assert result.id == "nct6775"
        assert result.ok is True

    def test_ok_when_nct6798_variant_loaded(self) -> None:
        # nct6798 is in the same family; should also satisfy the check.
        result = check_nct6775(read_modules=lambda: "nct6798 65536 0 - Live 0x0000000000000000\n")
        assert result.ok is True

    def test_fails_when_module_absent(self) -> None:
        contents = "ext4 1056768 1 - Live 0x0000000000000000\n"
        result = check_nct6775(read_modules=lambda: contents)
        assert result.ok is False
        assert "nct6775" in result.friendly_message

    def test_handles_empty_proc_modules(self) -> None:
        result = check_nct6775(read_modules=lambda: "")
        assert result.ok is False

    def test_handles_proc_modules_unreadable(self) -> None:
        def boom() -> str:
            raise OSError("permission denied")

        result = check_nct6775(read_modules=boom)
        assert result.ok is False

    def test_substring_match_does_not_false_positive(self) -> None:
        # A module whose name *contains* nct6775 in the middle should
        # NOT match — we only accept lines starting with one of the
        # family names.
        contents = "fake_nct6775_dontmatch 65536 0 - Live 0x0000\n"
        result = check_nct6775(read_modules=lambda: contents)
        assert result.ok is False


class TestCheckAll:
    def test_returns_status_for_each_prereq(self) -> None:
        statuses = check_all(
            which=lambda cmd: "/usr/bin/" + cmd,
            run=lambda argv: _completed(0),
            read_modules=lambda: "nct6775 65536 0 - Live 0x0000\n",
        )
        # Three checks, three statuses, all OK in this fake env.
        assert len(statuses) == 3
        ids = {s.id for s in statuses}
        assert ids == {"sensors", "nct6775", "smartd"}
        assert all(s.ok for s in statuses)

    def test_returns_failing_when_nothing_installed(self) -> None:
        statuses = check_all(
            which=lambda cmd: None,
            run=lambda argv: _completed(1),
            read_modules=lambda: "",
        )
        assert len(statuses) == 3
        assert all(not s.ok for s in statuses)

    def test_each_status_has_install_command(self) -> None:
        statuses = check_all(
            which=lambda cmd: None,
            run=lambda argv: _completed(1),
            read_modules=lambda: "",
        )
        for s in statuses:
            assert s.install_command, f"{s.id} missing install_command"
            assert s.friendly_message, f"{s.id} missing friendly_message"


@pytest.mark.parametrize(
    "fn",
    [check_sensors, check_smartd, check_nct6775],
)
def test_each_check_returns_prereqstatus(fn: object) -> None:
    # Smoke: every check function returns the same dataclass type so
    # the dashboard can iterate them uniformly.
    assert callable(fn)
    result = fn()
    assert isinstance(result, PrereqStatus)
