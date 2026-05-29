# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the config loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from thermall.config import (
    DEFAULT_REFRESH_SECONDS,
    DEFAULT_THEME,
    Config,
    default_config_path,
    detect_board,
    load,
)
from thermall.mapping import ThresholdSet


class TestDefaults:
    def test_load_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        # Pass an empty dmi_root so auto-detection finds nothing; this
        # test specifically exercises the "no file, no board" branch.
        # On real machines load() will auto-populate labels from the
        # detected board, which is the user-visible behaviour.
        config = load(tmp_path / "does_not_exist.toml", dmi_root=tmp_path / "no_dmi")
        assert config.refresh_seconds == DEFAULT_REFRESH_SECONDS
        assert config.theme == DEFAULT_THEME
        assert config.labels == {}
        assert "cpu" in config.thresholds
        assert "vrm" in config.thresholds

    def test_default_config_object(self) -> None:
        config = Config()
        assert config.refresh_seconds == DEFAULT_REFRESH_SECONDS
        assert config.thresholds["cpu"].warn == 80.0
        assert config.thresholds["cpu"].crit == 90.0


class TestPathResolution:
    def test_default_config_path_respects_xdg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/xdg")
        assert default_config_path() == Path("/custom/xdg/thermall/config.toml")

    def test_default_config_path_falls_back_to_home_dotconfig(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("HOME", "/home/test")
        # Path.home() reads $HOME on Linux.
        assert default_config_path() == Path("/home/test/.config/thermall/config.toml")


class TestTomlLoading:
    def test_loads_general_overrides(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(
            """
            [general]
            refresh_seconds = 5
            theme = "mono"
            """,
            encoding="utf-8",
        )
        config = load(cfg_file)
        assert config.refresh_seconds == 5.0
        assert config.theme == "mono"

    def test_loads_labels(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(
            """
            [labels]
            "AUXTIN0" = "VRM (CPU)"
            "fan6" = "NVMe heatsink"
            """,
            encoding="utf-8",
        )
        # Empty dmi_root so auto-detection does not merge in board labels.
        config = load(cfg_file, dmi_root=tmp_path / "no_dmi")
        assert config.labels == {
            "AUXTIN0": "VRM (CPU)",
            "fan6": "NVMe heatsink",
        }

    def test_loads_thresholds(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(
            """
            [thresholds.cpu]
            warn = 70
            crit = 85
            """,
            encoding="utf-8",
        )
        config = load(cfg_file)
        assert config.thresholds["cpu"] == ThresholdSet(category="cpu", warn=70.0, crit=85.0)
        # untouched categories keep defaults
        assert config.thresholds["vrm"].warn == 90.0

    def test_invalid_toml_raises_value_error(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("not = valid = toml", encoding="utf-8")
        with pytest.raises(ValueError, match="invalid TOML"):
            load(cfg_file)

    def test_partial_config_merges_over_defaults(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(
            """
            [general]
            theme = "high-contrast"
            """,
            encoding="utf-8",
        )
        config = load(cfg_file)
        assert config.theme == "high-contrast"
        assert config.refresh_seconds == DEFAULT_REFRESH_SECONDS


# Fixed strings matching the one shipped BoardProfile (ASUS B550-F).
# Tests that need a "matching" DMI use these; tests that need a miss
# use anything else.
_B550F_VENDOR = "ASUSTeK COMPUTER INC."
_B550F_PRODUCT = "ROG STRIX B550-F GAMING WIFI II"


def _write_dmi(root: Path, *, vendor: str | None, product: str | None) -> Path:
    """Create a fake DMI sysfs tree under `root` for tests.

    Pass `None` for a field to leave that file absent.
    """

    root.mkdir(parents=True, exist_ok=True)
    if vendor is not None:
        (root / "board_vendor").write_text(vendor + "\n", encoding="utf-8")
    if product is not None:
        (root / "board_name").write_text(product + "\n", encoding="utf-8")
    return root


class TestDetectBoard:
    def test_returns_profile_when_dmi_matches(self, tmp_path: Path) -> None:
        dmi = _write_dmi(tmp_path / "dmi", vendor=_B550F_VENDOR, product=_B550F_PRODUCT)
        profile = detect_board(dmi)
        assert profile is not None
        assert profile.product == _B550F_PRODUCT

    def test_returns_none_when_dmi_root_missing(self, tmp_path: Path) -> None:
        # Path that does not exist at all.
        assert detect_board(tmp_path / "nope") is None

    def test_returns_none_when_only_vendor_present(self, tmp_path: Path) -> None:
        dmi = _write_dmi(tmp_path / "dmi", vendor=_B550F_VENDOR, product=None)
        assert detect_board(dmi) is None

    def test_returns_none_when_only_product_present(self, tmp_path: Path) -> None:
        dmi = _write_dmi(tmp_path / "dmi", vendor=None, product=_B550F_PRODUCT)
        assert detect_board(dmi) is None

    def test_returns_none_when_product_unknown(self, tmp_path: Path) -> None:
        dmi = _write_dmi(tmp_path / "dmi", vendor=_B550F_VENDOR, product="No Such Board")
        assert detect_board(dmi) is None

    def test_returns_none_when_vendor_unknown(self, tmp_path: Path) -> None:
        dmi = _write_dmi(tmp_path / "dmi", vendor="Made Up", product=_B550F_PRODUCT)
        assert detect_board(dmi) is None

    def test_strips_trailing_whitespace(self, tmp_path: Path) -> None:
        # DMI files always end with a newline; the detector must strip it.
        dmi = tmp_path / "dmi"
        dmi.mkdir()
        (dmi / "board_vendor").write_text(_B550F_VENDOR + "\n\n", encoding="utf-8")
        (dmi / "board_name").write_text("  " + _B550F_PRODUCT + "  \n", encoding="utf-8")
        profile = detect_board(dmi)
        assert profile is not None

    def test_handles_permission_denied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Simulate the rare case where DMI files exist but are
        # unreadable for this user. detect_board() must swallow the
        # PermissionError and return None rather than propagating.
        dmi = _write_dmi(tmp_path / "dmi", vendor=_B550F_VENDOR, product=_B550F_PRODUCT)

        original_read_text = Path.read_text

        def deny(self: Path, *args: object, **kwargs: object) -> str:
            if self.parent == dmi:
                raise PermissionError(13, "denied", str(self))
            return original_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "read_text", deny)
        assert detect_board(dmi) is None

    def test_returns_none_when_dmi_is_a_file_not_a_directory(self, tmp_path: Path) -> None:
        # Edge case: somebody passes a regular file rather than a dir.
        weird = tmp_path / "not_a_dir"
        weird.write_text("oops", encoding="utf-8")
        assert detect_board(weird) is None


class TestLoadWithBoardDetection:
    def test_load_with_no_config_and_matching_board_populates_labels(self, tmp_path: Path) -> None:
        dmi = _write_dmi(tmp_path / "dmi", vendor=_B550F_VENDOR, product=_B550F_PRODUCT)
        config = load(path=tmp_path / "absent.toml", dmi_root=dmi)
        # detected_board reflects the match
        assert config.detected_board is not None
        assert _B550F_PRODUCT in config.detected_board
        # Labels populated from the B550-F profile
        assert "k10temp Tctl" in config.labels
        assert config.labels["k10temp Tctl"] == "CPU package"

    def test_load_with_no_config_and_no_board_match_keeps_defaults(self, tmp_path: Path) -> None:
        config = load(path=tmp_path / "absent.toml", dmi_root=tmp_path / "no_dmi")
        assert config.detected_board is None
        assert config.labels == {}

    def test_user_labels_override_autodetected(self, tmp_path: Path) -> None:
        dmi = _write_dmi(tmp_path / "dmi", vendor=_B550F_VENDOR, product=_B550F_PRODUCT)
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(
            """
            [labels]
            "k10temp Tctl" = "My CPU"
            "nct6798 fan6" = "NVMe heatsink"
            """,
            encoding="utf-8",
        )
        config = load(path=cfg_file, dmi_root=dmi)
        # User explicit value wins
        assert config.labels["k10temp Tctl"] == "My CPU"
        # User added value present
        assert config.labels["nct6798 fan6"] == "NVMe heatsink"
        # Auto-detected values still present for keys user did not override
        assert config.labels["k10temp Tccd1"] == "CPU CCD1"

    def test_detected_board_field_none_when_no_match(self, tmp_path: Path) -> None:
        config = load(path=tmp_path / "absent.toml", dmi_root=tmp_path / "nope")
        assert config.detected_board is None

    def test_default_thresholds_unchanged_by_autodetect(self, tmp_path: Path) -> None:
        # Autodetect only touches labels (and the detected_board field);
        # thresholds keep their _DEFAULT_THRESHOLDS values.
        dmi = _write_dmi(tmp_path / "dmi", vendor=_B550F_VENDOR, product=_B550F_PRODUCT)
        config = load(path=tmp_path / "absent.toml", dmi_root=dmi)
        assert config.thresholds["cpu"].warn == 80.0
        assert config.thresholds["cpu"].crit == 90.0
        assert config.thresholds["vrm"].warn == 90.0

    def test_existing_test_default_load_still_works_without_dmi(self, tmp_path: Path) -> None:
        # No dmi_root passed; default points at the real /sys/.../dmi/id.
        # On the CI runner the lookup either returns a profile or None,
        # and either is fine. We assert the call does not raise and
        # returns a Config.
        config = load(path=tmp_path / "absent.toml")
        assert isinstance(config, Config)
        # We do not assert detected_board's value because it depends on
        # whichever host the test runs on.
