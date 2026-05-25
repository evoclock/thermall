# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for built-in board label profiles."""

from __future__ import annotations

from thermall.board_profiles import PROFILES, BoardProfile, find_profile


class TestProfilesShape:
    """Structural invariants every shipped profile must hold."""

    def test_profiles_tuple_has_at_least_one_entry(self) -> None:
        # Reduced from three per the spec revision; one verified profile
        # is better than three speculative ones.
        assert len(PROFILES) >= 1

    def test_each_profile_has_non_empty_labels(self) -> None:
        for profile in PROFILES:
            assert profile.labels, f"profile {profile.product} has no labels"

    def test_each_profile_has_vendor_and_product(self) -> None:
        for profile in PROFILES:
            assert profile.vendor.strip()
            assert profile.product.strip()

    def test_profile_labels_have_no_empty_values(self) -> None:
        for profile in PROFILES:
            for raw, human in profile.labels.items():
                assert human.strip(), f"profile {profile.product} key {raw!r} maps to empty"

    def test_each_profile_is_frozen(self) -> None:
        # The dataclass uses frozen=True; mutation must raise.
        import pytest

        for profile in PROFILES:
            with pytest.raises((AttributeError, TypeError)):
                profile.vendor = "anything"  # type: ignore[misc]


class TestFindProfile:
    """Lookup contract."""

    def test_find_profile_exact_match_returns_b550f(self) -> None:
        result = find_profile("ASUSTeK COMPUTER INC.", "ROG STRIX B550-F GAMING WIFI II")
        assert result is not None
        assert result.product == "ROG STRIX B550-F GAMING WIFI II"

    def test_find_profile_is_case_insensitive(self) -> None:
        result = find_profile("asustek computer inc.", "rog strix b550-f gaming wifi ii")
        assert result is not None

    def test_find_profile_handles_mixed_case(self) -> None:
        result = find_profile("AsUsTeK CoMpUtEr Inc.", "RoG StRiX B550-F GAMING WIFI II")
        assert result is not None

    def test_find_profile_handles_trailing_whitespace(self) -> None:
        # DMI files end with `\n`; Linux strips on read but defensive
        # extra whitespace from any source is tolerated.
        result = find_profile("ASUSTeK COMPUTER INC.\n", "ROG STRIX B550-F GAMING WIFI II  ")
        assert result is not None

    def test_find_profile_handles_leading_whitespace(self) -> None:
        result = find_profile("  ASUSTeK COMPUTER INC.", "  ROG STRIX B550-F GAMING WIFI II")
        assert result is not None


class TestFindProfileMisses:
    """Misses return None, never raise."""

    def test_find_profile_returns_none_for_unknown_vendor(self) -> None:
        assert find_profile("Unknown Vendor", "Any Board") is None

    def test_find_profile_returns_none_for_known_vendor_wrong_product(self) -> None:
        assert find_profile("ASUSTeK COMPUTER INC.", "Made-up Board") is None

    def test_find_profile_returns_none_for_none_vendor(self) -> None:
        assert find_profile(None, "ROG STRIX B550-F GAMING WIFI II") is None

    def test_find_profile_returns_none_for_none_product(self) -> None:
        assert find_profile("ASUSTeK COMPUTER INC.", None) is None

    def test_find_profile_returns_none_for_both_none(self) -> None:
        assert find_profile(None, None) is None

    def test_find_profile_returns_none_for_empty_strings(self) -> None:
        assert find_profile("", "") is None

    def test_find_profile_returns_none_for_whitespace_only(self) -> None:
        assert find_profile("   ", "   ") is None


class TestB550FProfileContents:
    """The B550-F profile must cover the sensors that fixture verifies."""

    def _b550f(self) -> BoardProfile:
        result = find_profile("ASUSTeK COMPUTER INC.", "ROG STRIX B550-F GAMING WIFI II")
        assert result is not None
        return result

    def test_includes_cpu_package_and_per_ccd(self) -> None:
        labels = self._b550f().labels
        assert "k10temp Tctl" in labels
        assert "k10temp Tccd1" in labels
        assert "k10temp Tccd2" in labels

    def test_includes_all_five_auxtin_temps(self) -> None:
        labels = self._b550f().labels
        for n in range(5):
            assert f"nct6798 AUXTIN{n}" in labels, f"AUXTIN{n} missing"

    def test_includes_systin_and_cputin(self) -> None:
        labels = self._b550f().labels
        assert "nct6798 SYSTIN" in labels
        assert "nct6798 CPUTIN" in labels

    def test_includes_all_seven_fan_headers(self) -> None:
        labels = self._b550f().labels
        for n in range(1, 8):
            assert f"nct6798 fan{n}" in labels, f"fan{n} missing"

    def test_includes_nvme_composite(self) -> None:
        labels = self._b550f().labels
        assert "nvme Composite" in labels

    def test_notes_explain_neutral_labels(self) -> None:
        # The labels we ship are deliberately generic for AUXTIN and
        # fan slots; notes must explain why so users know to customise.
        notes = self._b550f().notes
        assert notes
        assert "AUXTIN" in notes or "fan" in notes
