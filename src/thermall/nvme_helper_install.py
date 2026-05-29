# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Install and operate the thermall NVMe SMART polling helper."""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

HELPER_NAME = "thermall-nvme-poll"
SERVICE_NAME = "thermall-nvme-poll.service"
TIMER_NAME = "thermall-nvme-poll.timer"
OUTPUT_PATH = Path("/run/thermall/nvme.json")

Systemctl = Callable[[list[str]], int]
RunNvme = Callable[[str], str]


def noop_systemctl(_args: list[str]) -> int:
    """Test helper that pretends systemctl succeeded."""
    return 0


def real_systemctl(args: list[str]) -> int:
    """Run systemctl and return its exit code."""
    return subprocess.run(["systemctl", *args], check=False).returncode


def install(
    *,
    uninstall: bool,
    dry_run: bool,
    root: Path = Path("/"),
    euid: int | None = None,
    systemctl: Systemctl = real_systemctl,
) -> int:
    """Install or uninstall the systemd NVMe helper infrastructure."""
    effective_uid = os.geteuid() if euid is None else euid
    if effective_uid != 0:
        print(
            "install-nvme-helper writes to /usr/local/libexec and /etc/systemd/system; "
            "re-run with sudo",
            file=sys.stderr,
        )
        return 2

    files = _install_files(root)
    if dry_run:
        _print_dry_run(uninstall)
        return 0

    if uninstall:
        _systemctl(systemctl, ["disable", "--now", TIMER_NAME])
        for target in files:
            target.unlink(missing_ok=True)
        _systemctl(systemctl, ["daemon-reload"])
        print("NVMe helper removed.")
        return 0

    for target, source, mode in _source_file_plan(root):
        _copy_if_changed(source, target, mode)
    runtime_dir = root / "run/thermall"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_dir.chmod(0o755)
    _systemctl(systemctl, ["daemon-reload"])
    _systemctl(systemctl, ["enable", "--now", TIMER_NAME])
    print("NVMe helper installed.")
    return 0


def parse_smart_log(raw: str) -> dict[str, object]:
    """Parse the minimal fields thermall needs from `nvme smart-log`."""
    result: dict[str, object] = {"temperature_sensors_c": {}}
    sensors: dict[str, float] = {}

    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = key.strip().lower().replace(" ", "_")
        value = value.strip()
        if normalized == "critical_warning":
            result["critical_warning"] = int(value, 0)
        elif normalized == "temperature":
            result["temperature_c"] = _first_float(value)
        elif normalized.startswith("temperature_sensor_"):
            sensor_id = normalized.removeprefix("temperature_sensor_")
            sensors[sensor_id] = _first_float(value)

    result["temperature_sensors_c"] = sensors
    return result


def poll_nvme_devices(
    *,
    devices: Iterable[str],
    output_path: Path = OUTPUT_PATH,
    run_nvme: RunNvme | None = None,
) -> int:
    """Poll NVMe devices and atomically write parsed JSON for successful reads."""
    runner = _run_nvme if run_nvme is None else run_nvme
    parsed: dict[str, object] = {}
    for device in devices:
        try:
            parsed[device] = parse_smart_log(runner(device))
        except Exception as exc:  # pragma: no cover - exact error type depends on nvme-cli
            print(f"{device}: {exc}", file=sys.stderr)

    if not parsed:
        print("No NVMe SMART data collected.", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(parsed, sort_keys=True), encoding="utf-8")
    tmp_path.chmod(0o644)
    tmp_path.replace(output_path)
    output_path.chmod(0o644)
    return 0


def main() -> int:
    """Entry point for the systemd-run helper script."""
    devices = tuple(sorted(glob.glob("/dev/nvme*n1")))
    return poll_nvme_devices(devices=devices)


def _run_nvme(device: str) -> str:
    completed = subprocess.run(
        ["nvme", "smart-log", device],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _first_float(value: str) -> float:
    return float(value.split()[0])


def _systemctl(systemctl: Systemctl, args: list[str]) -> None:
    code = systemctl(args)
    if code != 0:
        raise RuntimeError(f"systemctl {' '.join(args)} failed with exit code {code}")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _packaging_dir() -> Path:
    return _repo_root() / "packaging"


def _install_files(root: Path) -> tuple[Path, Path, Path]:
    return (
        root / "usr/local/libexec" / HELPER_NAME,
        root / "etc/systemd/system" / SERVICE_NAME,
        root / "etc/systemd/system" / TIMER_NAME,
    )


def _source_file_plan(root: Path) -> tuple[tuple[Path, Path, int], ...]:
    helper, service, timer = _install_files(root)
    packaging = _packaging_dir()
    return (
        (helper, packaging / HELPER_NAME, 0o755),
        (service, packaging / SERVICE_NAME, 0o644),
        (timer, packaging / TIMER_NAME, 0o644),
    )


def _copy_if_changed(source: Path, target: Path, mode: int) -> None:
    source_bytes = source.read_bytes()
    if target.exists() and target.read_bytes() == source_bytes:
        target.chmod(mode)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    tmp_path.write_bytes(source_bytes)
    tmp_path.chmod(mode)
    tmp_path.replace(target)
    target.chmod(mode)


def _print_dry_run(uninstall: bool) -> None:
    action = "remove" if uninstall else "install"
    for path in (
        Path("/usr/local/libexec") / HELPER_NAME,
        Path("/etc/systemd/system") / SERVICE_NAME,
        Path("/etc/systemd/system") / TIMER_NAME,
    ):
        print(f"Would {action} {path}")
    if uninstall:
        print(f"Would run systemctl disable --now {TIMER_NAME}")
    print("Would run systemctl daemon-reload")
    if not uninstall:
        print(f"Would run systemctl enable --now {TIMER_NAME}")


if __name__ == "__main__":
    raise SystemExit(main())
