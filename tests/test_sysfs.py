# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the sysfs hardware-identification helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from thermall.sysfs import _chip_name_from_address, nvme_devices


class TestChipNameFromAddress:
    def test_zero_function_encodes_correctly(self) -> None:
        assert _chip_name_from_address("0000:08:00.0") == "nvme-pci-0800"
        assert _chip_name_from_address("0000:01:00.0") == "nvme-pci-0100"

    def test_nonzero_function_packed_into_devfn(self) -> None:
        # devfn = (device << 3) | function
        # 01:00.1 -> devfn = (0 << 3) | 1 = 0x01 -> nvme-pci-0101
        assert _chip_name_from_address("0000:01:00.1") == "nvme-pci-0101"
        # 02:1f.7 -> devfn = (0x1f << 3) | 7 = 0xff -> nvme-pci-02ff
        assert _chip_name_from_address("0000:02:1f.7") == "nvme-pci-02ff"

    def test_large_bus_number(self) -> None:
        # Bus 0xfe is valid.
        assert _chip_name_from_address("0000:fe:00.0") == "nvme-pci-fe00"

    def test_uppercase_input_normalised_to_lowercase(self) -> None:
        # lm-sensors emits lowercase hex; sysfs is already lowercase but
        # be defensive against uppercase input.
        assert _chip_name_from_address("0000:AB:00.0") == "nvme-pci-ab00"

    def test_empty_returns_none(self) -> None:
        assert _chip_name_from_address("") is None

    def test_missing_colon_returns_none(self) -> None:
        assert _chip_name_from_address("not-an-address") is None

    def test_missing_function_returns_none(self) -> None:
        # No "." separator between device and function.
        assert _chip_name_from_address("0000:01:00") is None

    def test_non_hex_returns_none(self) -> None:
        assert _chip_name_from_address("0000:gg:00.0") is None

    def test_out_of_range_function_returns_none(self) -> None:
        # PCI function is 3 bits (0-7); 8 is invalid.
        assert _chip_name_from_address("0000:01:00.8") is None

    def test_out_of_range_device_returns_none(self) -> None:
        # PCI device is 5 bits (0-31); 0x20 is invalid.
        assert _chip_name_from_address("0000:01:20.0") is None


class TestNvmeDevices:
    def test_missing_sys_class_nvme_returns_empty(self, tmp_path: Path) -> None:
        # `/sys/class/nvme` does not exist on systems with no NVMe
        # subsystem (older kernels, containers, CI runners).
        assert nvme_devices(tmp_path / "missing") == {}

    def test_empty_sys_class_nvme_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "nvme").mkdir()
        assert nvme_devices(tmp_path / "nvme") == {}

    def test_single_drive_mapped_to_model(self, tmp_path: Path) -> None:
        root = tmp_path / "nvme"
        _write_drive(root, "nvme0", address="0000:01:00.0", model="CT4000P310SSD8")
        result = nvme_devices(root)
        assert result == {"nvme-pci-0100": "CT4000P310SSD8"}

    def test_multiple_drives_each_mapped(self, tmp_path: Path) -> None:
        root = tmp_path / "nvme"
        _write_drive(root, "nvme0", address="0000:01:00.0", model="CT4000P310SSD8")
        _write_drive(root, "nvme1", address="0000:08:00.0", model="KINGSTON SNV2S2000G")
        result = nvme_devices(root)
        assert result == {
            "nvme-pci-0100": "CT4000P310SSD8",
            "nvme-pci-0800": "KINGSTON SNV2S2000G",
        }

    def test_model_trailing_whitespace_stripped(self, tmp_path: Path) -> None:
        # The kernel pads model to a fixed width with trailing spaces.
        root = tmp_path / "nvme"
        _write_drive(
            root, "nvme0", address="0000:01:00.0", model="CT4000P310SSD8                  "
        )
        assert nvme_devices(root) == {"nvme-pci-0100": "CT4000P310SSD8"}

    def test_skips_drive_with_missing_address(self, tmp_path: Path) -> None:
        # Permission denied or missing file: skip that drive only.
        root = tmp_path / "nvme"
        nvme0 = root / "nvme0"
        nvme0.mkdir(parents=True)
        (nvme0 / "model").write_text("CT4000P310SSD8\n")
        # No address file written
        assert nvme_devices(root) == {}

    def test_skips_drive_with_missing_model(self, tmp_path: Path) -> None:
        root = tmp_path / "nvme"
        nvme0 = root / "nvme0"
        nvme0.mkdir(parents=True)
        (nvme0 / "address").write_text("0000:01:00.0\n")
        # No model file
        assert nvme_devices(root) == {}

    def test_skips_drive_with_malformed_address(self, tmp_path: Path) -> None:
        # Garbage in address file should not blow up; just skip.
        root = tmp_path / "nvme"
        _write_drive(root, "nvme0", address="garbage", model="CT4000P310SSD8")
        _write_drive(root, "nvme1", address="0000:08:00.0", model="KINGSTON SNV2S2000G")
        assert nvme_devices(root) == {"nvme-pci-0800": "KINGSTON SNV2S2000G"}

    def test_ignores_non_nvme_entries(self, tmp_path: Path) -> None:
        # `/sys/class/nvme/` contains nvmeN block-device nodes and may
        # contain other entries (uevent, subsystem symlinks). Only walk
        # entries that look like nvmeN.
        root = tmp_path / "nvme"
        root.mkdir()
        (root / "subsystem").mkdir()
        (root / "uevent").write_text("KERNEL=nvme\n")
        _write_drive(root, "nvme0", address="0000:01:00.0", model="CT4000P310SSD8")
        assert nvme_devices(root) == {"nvme-pci-0100": "CT4000P310SSD8"}

    def test_string_path_accepted(self, tmp_path: Path) -> None:
        # Callers in tests pass Path; the production caller passes the
        # default string constant. Both work.
        root = tmp_path / "nvme"
        _write_drive(root, "nvme0", address="0000:01:00.0", model="CT4000P310SSD8")
        assert nvme_devices(str(root)) == {"nvme-pci-0100": "CT4000P310SSD8"}

    def test_default_path_runs_without_error(self) -> None:
        # On the test machine the real path may or may not exist; we
        # only assert the function does not raise and returns a dict.
        result = nvme_devices()
        assert isinstance(result, dict)


def _write_drive(root: Path, name: str, *, address: str, model: str) -> None:
    """Helper: create a fake `nvmeN/` entry under `root` with address+model."""

    drive_dir = root / name
    drive_dir.mkdir(parents=True)
    (drive_dir / "address").write_text(address + "\n")
    (drive_dir / "model").write_text(model + "\n")


# Sanity: importable but no side effects
def test_module_has_public_api() -> None:
    from thermall import sysfs

    assert hasattr(sysfs, "nvme_devices")
    assert callable(sysfs.nvme_devices)


@pytest.mark.parametrize(
    "address,expected",
    [
        ("0000:00:00.0", "nvme-pci-0000"),
        ("0000:ff:00.0", "nvme-pci-ff00"),
        ("0000:00:1f.7", "nvme-pci-00ff"),
    ],
)
def test_chip_name_corner_values(address: str, expected: str) -> None:
    assert _chip_name_from_address(address) == expected
