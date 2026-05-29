# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Foundational prerequisite checks for the thermall dashboard.

`check_all()` runs three lightweight checks at app startup:

1. `sensors` on PATH (lm-sensors installed).
2. `nct6775` kernel module loaded (motherboard sensors visible).
3. `smartmontools` service active (drive-health monitoring).

Failures surface as friendly `PrereqStatus` records the dashboard
turns into `HelpCard` widgets. Dismissals persist in the state file
(see `config.state_path()`) so a card the user has acknowledged
never reappears, even after a re-launch where the prereq remains
failed. The trade-off is intentional: dashboard quietness wins over
nag-card resurrection. Users who change their mind can delete the
state file or use the settings screen's reset.

All check functions are pure-ish: they accept injected lookups
(`shutil.which`, `subprocess.run`, `/proc/modules` reader) so tests
can simulate any prereq state without modifying the host.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# Map of prereq id to default friendly text. Stable strings; persisted
# verbatim in `state.toml` so a rename later breaks dismissals.
_PROC_MODULES: Final[Path] = Path("/proc/modules")


@dataclass(frozen=True, slots=True)
class PrereqStatus:
    """One foundational prerequisite's check result.

    `id` is the stable string used as the state-file key (e.g.
    `"sensors"`); a rename in a future version invalidates any user's
    dismissals for that prereq, which is acceptable for an MVP.
    `install_command` is the literal text the user copies and runs.
    `friendly_message` is the apple-level explanation (no error
    jargon, no exclamation marks).
    """

    id: str
    name: str
    ok: bool
    install_command: str
    friendly_message: str


# Type aliases for the injection points; keep signatures simple in
# tests while letting production callers rely on the defaults.
_WhichFn = Callable[[str], str | None]
_RunFn = Callable[[list[str]], "subprocess.CompletedProcess[str]"]
_ReadModulesFn = Callable[[], str]


def _default_run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=2.0, check=False)


def _default_read_modules() -> str:
    try:
        return _PROC_MODULES.read_text(encoding="utf-8")
    except OSError:
        return ""


def check_sensors(which: _WhichFn = shutil.which) -> PrereqStatus:
    """Verify lm-sensors is installed."""

    found = which("sensors")
    return PrereqStatus(
        id="sensors",
        name="lm-sensors",
        ok=found is not None,
        install_command="sudo apt install lm-sensors  # or pacman -S lm_sensors / dnf install lm_sensors",
        friendly_message=("Install lm-sensors to see CPU, motherboard, and storage temperatures."),
    )


def check_smartd(
    which: _WhichFn = shutil.which,
    run: _RunFn = _default_run,
) -> PrereqStatus:
    """Verify smartmontools is installed and the smartd service is active.

    Falls back gracefully when `systemctl` itself is unavailable
    (containers, restricted environments): in that case we report
    ok=False with a friendly message rather than raising.
    """

    systemctl = which("systemctl")
    if systemctl is None:
        return PrereqStatus(
            id="smartd",
            name="smartmontools",
            ok=False,
            install_command="sudo apt install smartmontools",
            friendly_message=("Install smartmontools to enable drive-failure warnings."),
        )

    try:
        result = run([systemctl, "is-active", "smartmontools"])
    except (subprocess.TimeoutExpired, OSError):
        result_ok = False
    else:
        result_ok = result.returncode == 0

    return PrereqStatus(
        id="smartd",
        name="smartmontools",
        ok=result_ok,
        install_command=(
            "sudo apt install smartmontools && sudo systemctl enable --now smartmontools"
        ),
        friendly_message=("Install smartmontools to enable drive-failure warnings."),
    )


def check_nct6775(read_modules: _ReadModulesFn = _default_read_modules) -> PrereqStatus:
    """Verify the nct6775 kernel module is loaded.

    Reads `/proc/modules` (world-readable, no privilege needed). Any
    name in the nct67xx family counts as a hit — that family covers
    most Nuvoton SuperIO chips on common ASUS / Gigabyte / MSI AMD
    boards. Unreadable `/proc/modules` reports ok=False.
    """

    try:
        contents = read_modules()
    except OSError:
        contents = ""

    has_module = any(
        line.startswith(name)
        for line in contents.splitlines()
        for name in ("nct6775", "nct6683", "nct6798")
    )

    return PrereqStatus(
        id="nct6775",
        name="nct6775",
        ok=has_module,
        install_command="sudo modprobe nct6775  # then add to /etc/modules-load.d/ for persistence",
        friendly_message=(
            "Load the nct6775 module to see your motherboard fans and VRM temperatures."
        ),
    )


def check_all(
    *,
    which: _WhichFn = shutil.which,
    run: _RunFn = _default_run,
    read_modules: _ReadModulesFn = _default_read_modules,
) -> tuple[PrereqStatus, ...]:
    """Run every foundational prereq check; return one status per check.

    Order is `(sensors, nct6775, smartd)` for stable cycling and
    consistent UI placement. All injection points share defaults; a
    test passing fakes for any subset still gets real defaults for
    the rest.
    """

    return (
        check_sensors(which=which),
        check_nct6775(read_modules=read_modules),
        check_smartd(which=which, run=run),
    )
