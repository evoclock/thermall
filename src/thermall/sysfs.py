# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Sysfs lookups for hardware identification.

Pure read-only helpers that turn `/sys` entries into useful identifiers
the rest of the app can join against lm-sensors chip names. No I/O
beyond `Path.read_text()` / `Path.iterdir()`; all paths are injectable
so tests can populate a fake `/sys` under `tmp_path`.

The first inhabitant is NVMe drive identification: lm-sensors collapses
chip names like `nvme-pci-0100` and `nvme-pci-0800` to the short form
`nvme` once the bus suffix is stripped, which loses drive identity when
a system has multiple SSDs. This module maps the original lm-sensors
chip name to the kernel-reported drive model so the dashboard can show
`CT4000P310SSD8` instead of two indistinguishable `nvme` rows.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

_DEFAULT_SYS_NVME = Path("/sys/class/nvme")


def nvme_devices(sys_class_nvme: Path | str = _DEFAULT_SYS_NVME) -> dict[str, str]:
    """Return `{chip_name: model_name}` for every visible NVMe device.

    `chip_name` matches the lm-sensors naming convention
    (`nvme-pci-<bus><devfn>`, hex with no separator) so callers can join
    directly against the chip key returned by `sensors -j`.

    `model_name` is the contents of `/sys/class/nvme/nvmeN/model`,
    stripped of trailing whitespace (the kernel pads to a fixed width).

    Devices with unreadable `address` or `model` files are skipped
    rather than aborting the whole lookup; one missing drive should not
    blank the entire mapping.
    """

    return dict(_iter_nvme_devices(Path(sys_class_nvme)))


def _iter_nvme_devices(root: Path) -> Iterator[tuple[str, str]]:
    """Yield `(chip_name, model_name)` for each `nvmeN/` under `root`."""

    if not root.is_dir():
        return
    for entry in sorted(root.iterdir()):
        if not entry.name.startswith("nvme") or not entry.is_dir():
            continue
        chip = _chip_name_from_address(_read_text(entry / "address"))
        model = _read_text(entry / "model")
        if chip is None or not model:
            continue
        yield chip, model


def _read_text(path: Path) -> str:
    """Read and strip a sysfs text file; empty string on any error."""

    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _chip_name_from_address(address: str) -> str | None:
    """Convert a PCI BDF address to its lm-sensors chip-name suffix.

    `0000:08:00.0` becomes `nvme-pci-0800` (bus 0x08, devfn 0x00).
    `0000:01:00.1` becomes `nvme-pci-0101` (bus 0x01, devfn 0x01).

    Returns `None` if `address` is empty or not in the canonical
    `DDDD:BB:DD.F` form. Permissive on the domain (any width) so future
    multi-domain systems still parse; strict on bus / device / function.
    """

    if not address:
        return None
    try:
        _, bus_dev_fn = address.split(":", 1)
        bus_hex, dev_fn = bus_dev_fn.split(":", 1)
        dev_hex, fn_str = dev_fn.split(".", 1)
        bus = int(bus_hex, 16)
        dev = int(dev_hex, 16)
        fn = int(fn_str, 16)
    except (ValueError, IndexError):
        return None
    if not (0 <= bus <= 0xFF and 0 <= dev <= 0x1F and 0 <= fn <= 0x7):
        return None
    devfn = (dev << 3) | fn
    return f"nvme-pci-{bus:02x}{devfn:02x}"
