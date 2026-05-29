# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for installing and running the NVMe helper infrastructure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from thermall import nvme_helper_install

FIXTURE = Path(__file__).parent / "fixtures" / "nvme_smart_output.txt"


def test_install_writes_three_files_into_tmp_path(tmp_path: Path) -> None:
    result = nvme_helper_install.install(
        uninstall=False,
        dry_run=False,
        root=tmp_path,
        euid=0,
        systemctl=nvme_helper_install.noop_systemctl,
    )

    assert result == 0
    assert (tmp_path / "usr/local/libexec/thermall-nvme-poll").exists()
    assert (tmp_path / "etc/systemd/system/thermall-nvme-poll.service").exists()
    assert (tmp_path / "etc/systemd/system/thermall-nvme-poll.timer").exists()


def test_uninstall_removes_three_files_from_tmp_path(tmp_path: Path) -> None:
    nvme_helper_install.install(
        uninstall=False,
        dry_run=False,
        root=tmp_path,
        euid=0,
        systemctl=nvme_helper_install.noop_systemctl,
    )

    result = nvme_helper_install.install(
        uninstall=True,
        dry_run=False,
        root=tmp_path,
        euid=0,
        systemctl=nvme_helper_install.noop_systemctl,
    )

    assert result == 0
    assert not (tmp_path / "usr/local/libexec/thermall-nvme-poll").exists()
    assert not (tmp_path / "etc/systemd/system/thermall-nvme-poll.service").exists()
    assert not (tmp_path / "etc/systemd/system/thermall-nvme-poll.timer").exists()


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    result = nvme_helper_install.install(
        uninstall=False,
        dry_run=True,
        root=tmp_path,
        euid=0,
        systemctl=nvme_helper_install.noop_systemctl,
    )

    assert result == 0
    assert list(tmp_path.rglob("*")) == []


def test_dry_run_prints_actions(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = nvme_helper_install.install(
        uninstall=False,
        dry_run=True,
        root=tmp_path,
        euid=0,
        systemctl=nvme_helper_install.noop_systemctl,
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "Would install /usr/local/libexec/thermall-nvme-poll" in output
    assert "Would install /etc/systemd/system/thermall-nvme-poll.service" in output
    assert "Would run systemctl daemon-reload" in output


def test_install_is_idempotent(tmp_path: Path) -> None:
    nvme_helper_install.install(
        uninstall=False,
        dry_run=False,
        root=tmp_path,
        euid=0,
        systemctl=nvme_helper_install.noop_systemctl,
    )
    helper = tmp_path / "usr/local/libexec/thermall-nvme-poll"
    first_content = helper.read_text(encoding="utf-8")
    first_mode = helper.stat().st_mode

    nvme_helper_install.install(
        uninstall=False,
        dry_run=False,
        root=tmp_path,
        euid=0,
        systemctl=nvme_helper_install.noop_systemctl,
    )

    assert helper.read_text(encoding="utf-8") == first_content
    assert helper.stat().st_mode == first_mode


def test_uninstall_when_nothing_installed_exits_zero(tmp_path: Path) -> None:
    result = nvme_helper_install.install(
        uninstall=True,
        dry_run=False,
        root=tmp_path,
        euid=0,
        systemctl=nvme_helper_install.noop_systemctl,
    )

    assert result == 0


def test_install_without_root_returns_2_with_friendly_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = nvme_helper_install.install(
        uninstall=False,
        dry_run=False,
        root=tmp_path,
        euid=1000,
        systemctl=nvme_helper_install.noop_systemctl,
    )

    assert result == 2
    assert (
        "install-nvme-helper writes to /usr/local/libexec and /etc/systemd/system; re-run with sudo"
    ) in capsys.readouterr().err


def test_helper_script_parsing_function_against_existing_fixture() -> None:
    parsed = nvme_helper_install.parse_smart_log(FIXTURE.read_text(encoding="utf-8"))

    assert parsed == {
        "critical_warning": 0,
        "temperature_c": 40.0,
        "temperature_sensors_c": {"1": 40.0},
    }


def test_helper_script_handles_no_nvme_devices_present(tmp_path: Path) -> None:
    output = tmp_path / "run/thermall/nvme.json"

    result = nvme_helper_install.poll_nvme_devices(
        devices=(),
        output_path=output,
        run_nvme=lambda _device: "",
    )

    assert result == 1
    assert not output.exists()


def test_helper_script_continues_when_one_device_fails(tmp_path: Path) -> None:
    fixture_text = FIXTURE.read_text(encoding="utf-8")
    output = tmp_path / "run/thermall/nvme.json"

    def fake_run(device: str) -> str:
        if device == "/dev/nvme0n1":
            raise RuntimeError("permission denied")
        return fixture_text

    result = nvme_helper_install.poll_nvme_devices(
        devices=("/dev/nvme0n1", "/dev/nvme1n1"),
        output_path=output,
        run_nvme=fake_run,
    )

    assert result == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert sorted(data) == ["/dev/nvme1n1"]
    assert data["/dev/nvme1n1"]["temperature_c"] == 40.0
