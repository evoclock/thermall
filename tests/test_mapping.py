# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for label resolution and threshold grading."""

from __future__ import annotations

import pytest

from thermall.mapping import (
    DEFAULT_PHRASES,
    ThresholdSet,
    category_for,
    grade_many,
    grade_reading,
    resolve,
    resolve_many,
)
from thermall.model import Reading, Severity


class TestResolve:
    def test_exact_match_returns_mapped_label(self) -> None:
        assert resolve("AUXTIN0", {"AUXTIN0": "VRM (CPU)"}) == ("VRM (CPU)", True)

    def test_case_insensitive_fallback(self) -> None:
        assert resolve("auxtin0", {"AUXTIN0": "VRM (CPU)"}) == ("VRM (CPU)", True)

    def test_passthrough_on_miss(self) -> None:
        assert resolve("fanX", {"fan6": "NVMe heatsink"}) == ("fanX", False)

    def test_empty_map_passes_through(self) -> None:
        assert resolve("Tctl", {}) == ("Tctl", False)

    def test_exact_match_preferred_over_case_insensitive(self) -> None:
        m = {"Tctl": "CPU package", "tctl": "wrong"}
        assert resolve("Tctl", m) == ("CPU package", True)


class TestResolveMany:
    def test_batches_all_inputs(self) -> None:
        labels = ["AUXTIN0", "Tctl", "fanX"]
        m = {"AUXTIN0": "VRM (CPU)", "Tctl": "CPU package"}
        result = resolve_many(labels, m)
        assert result == {
            "AUXTIN0": ("VRM (CPU)", True),
            "Tctl": ("CPU package", True),
            "fanX": ("fanX", False),
        }

    def test_empty_input_returns_empty_dict(self) -> None:
        assert resolve_many([], {"k": "v"}) == {}


class TestThresholdSet:
    def test_grade_below_warn_is_ok(self) -> None:
        ts = ThresholdSet(category="cpu", warn=80.0, crit=90.0)
        assert ts.grade(50.0) is Severity.OK

    def test_grade_at_warn_is_warn(self) -> None:
        ts = ThresholdSet(category="cpu", warn=80.0, crit=90.0)
        assert ts.grade(80.0) is Severity.WARN

    def test_grade_between_warn_and_crit_is_warn(self) -> None:
        ts = ThresholdSet(category="cpu", warn=80.0, crit=90.0)
        assert ts.grade(85.0) is Severity.WARN

    def test_grade_at_crit_is_crit(self) -> None:
        ts = ThresholdSet(category="cpu", warn=80.0, crit=90.0)
        assert ts.grade(90.0) is Severity.CRIT

    def test_grade_above_crit_is_crit(self) -> None:
        ts = ThresholdSet(category="cpu", warn=80.0, crit=90.0)
        assert ts.grade(95.0) is Severity.CRIT


class TestGradeReading:
    def test_grade_reading_returns_new_reading_with_severity(self) -> None:
        r = Reading(raw_label="Tctl", value=85.0, unit="C")
        ts = ThresholdSet(category="cpu", warn=80.0, crit=90.0)
        graded = grade_reading(r, ts)
        assert graded.severity is Severity.WARN
        assert r.severity is Severity.UNKNOWN


class TestGradeMany:
    def test_routes_by_heuristic_category(self) -> None:
        cpu = Reading(raw_label="Tctl", value=85.0, unit="C")
        vrm = Reading(raw_label="AUXTIN0", value=95.0, unit="C")
        unknown = Reading(raw_label="mystery", value=99.0, unit="C")
        thresholds = {
            "cpu": ThresholdSet(category="cpu", warn=80.0, crit=90.0),
            "vrm": ThresholdSet(category="vrm", warn=90.0, crit=100.0),
        }
        graded = grade_many([cpu, vrm, unknown], thresholds)
        assert graded[0].severity is Severity.WARN
        assert graded[1].severity is Severity.WARN
        assert graded[2].severity is Severity.UNKNOWN

    def test_empty_input(self) -> None:
        assert grade_many([], {}) == []


class TestPhraseFor:
    """Coverage for ThresholdSet.phrase_for + DEFAULT_PHRASES."""

    def test_default_phrases_has_every_severity_value(self) -> None:
        # Boundary: every Severity enum value must resolve, no KeyError.
        for severity in Severity:
            assert severity in DEFAULT_PHRASES
            assert DEFAULT_PHRASES[severity]  # non-empty

    def test_phrase_for_returns_default_when_severity_phrases_none(self) -> None:
        ts = ThresholdSet(category="x", warn=80.0, crit=90.0)
        assert ts.phrase_for(Severity.OK) == DEFAULT_PHRASES[Severity.OK]
        assert ts.phrase_for(Severity.WARN) == DEFAULT_PHRASES[Severity.WARN]
        assert ts.phrase_for(Severity.CRIT) == DEFAULT_PHRASES[Severity.CRIT]
        assert ts.phrase_for(Severity.UNKNOWN) == DEFAULT_PHRASES[Severity.UNKNOWN]

    def test_phrase_for_returns_override_when_present(self) -> None:
        ts = ThresholdSet(
            category="cpu",
            warn=80.0,
            crit=90.0,
            severity_phrases={Severity.WARN: "CPU running hot"},
        )
        assert ts.phrase_for(Severity.WARN) == "CPU running hot"

    def test_partial_override_uses_default_for_unset_values(self) -> None:
        ts = ThresholdSet(
            category="cpu",
            warn=80.0,
            crit=90.0,
            severity_phrases={Severity.WARN: "CPU hot"},
        )
        # Override hits
        assert ts.phrase_for(Severity.WARN) == "CPU hot"
        # Defaults fill in for the others
        assert ts.phrase_for(Severity.OK) == DEFAULT_PHRASES[Severity.OK]
        assert ts.phrase_for(Severity.CRIT) == DEFAULT_PHRASES[Severity.CRIT]
        assert ts.phrase_for(Severity.UNKNOWN) == DEFAULT_PHRASES[Severity.UNKNOWN]

    def test_empty_override_dict_falls_back_to_default(self) -> None:
        ts = ThresholdSet(category="x", warn=80.0, crit=90.0, severity_phrases={})
        for severity in Severity:
            assert ts.phrase_for(severity) == DEFAULT_PHRASES[severity]

    def test_phrase_is_never_empty_for_any_severity(self) -> None:
        # Same as the DEFAULT_PHRASES boundary check, but via phrase_for
        # on a ThresholdSet with no overrides.
        ts = ThresholdSet(category="x", warn=80.0, crit=90.0)
        for severity in Severity:
            assert ts.phrase_for(severity)

    def test_threshold_set_remains_frozen(self) -> None:
        # The new field must not break immutability.
        ts = ThresholdSet(category="x", warn=80.0, crit=90.0)
        with pytest.raises((AttributeError, TypeError)):
            ts.warn = 70.0  # type: ignore[misc]

    def test_default_thresholds_in_config_have_category_phrases(self) -> None:
        # The four built-in ThresholdSets in config._DEFAULT_THRESHOLDS
        # must have category-specific WARN phrases.
        from thermall.config import _DEFAULT_THRESHOLDS

        assert "CPU" in _DEFAULT_THRESHOLDS["cpu"].phrase_for(Severity.WARN)
        assert "VRM" in _DEFAULT_THRESHOLDS["vrm"].phrase_for(Severity.WARN)
        assert "GPU" in _DEFAULT_THRESHOLDS["gpu"].phrase_for(Severity.WARN)
        assert "drive" in _DEFAULT_THRESHOLDS["nvme"].phrase_for(Severity.WARN)

    def test_default_thresholds_have_category_specific_crit_phrases(self) -> None:
        from thermall.config import _DEFAULT_THRESHOLDS

        # Every CRIT phrase should be distinct from the default and reference
        # the category by name (CPU / VRM / GPU / drive).
        cpu_crit = _DEFAULT_THRESHOLDS["cpu"].phrase_for(Severity.CRIT)
        vrm_crit = _DEFAULT_THRESHOLDS["vrm"].phrase_for(Severity.CRIT)
        gpu_crit = _DEFAULT_THRESHOLDS["gpu"].phrase_for(Severity.CRIT)
        nvme_crit = _DEFAULT_THRESHOLDS["nvme"].phrase_for(Severity.CRIT)
        assert "CPU" in cpu_crit
        assert "VRM" in vrm_crit
        assert "GPU" in gpu_crit
        assert "drive" in nvme_crit
        # All four phrases are distinct strings.
        assert len({cpu_crit, vrm_crit, gpu_crit, nvme_crit}) == 4


def _r(label: str, value: float = 50.0) -> Reading:
    """Helper to make a Reading for category_for tests."""

    return Reading(raw_label=label, value=value, unit="C")


class TestCategoryFor:
    """Routing heuristic for `category_for`."""

    # Happy path: each category returns its own bucket
    def test_cpu_via_tctl(self) -> None:
        assert category_for(_r("k10temp Tctl")) == "cpu"

    def test_cpu_via_tccd(self) -> None:
        assert category_for(_r("k10temp Tccd1")) == "cpu"

    def test_cpu_via_k10_prefix(self) -> None:
        assert category_for(_r("k10temp something")) == "cpu"

    def test_cpu_via_cpu_word(self) -> None:
        assert category_for(_r("intel cpu temp")) == "cpu"

    def test_vrm_via_auxtin(self) -> None:
        assert category_for(_r("nct6798 AUXTIN0")) == "vrm"

    def test_vrm_via_vrm_word(self) -> None:
        assert category_for(_r("VRM Core")) == "vrm"

    def test_nvme_via_composite(self) -> None:
        assert category_for(_r("nvme Composite")) == "nvme"

    def test_nvme_via_nvme_prefix(self) -> None:
        assert category_for(_r("nvme0n1 sensor")) == "nvme"

    def test_gpu_via_gpu_word(self) -> None:
        assert category_for(_r("GPU 0 hotspot")) == "gpu"

    # Unrecognised goes to "other", not empty string
    def test_unknown_returns_other(self) -> None:
        assert category_for(_r("nct6798 SYSTIN")) == "other"

    def test_chassis_sensors_return_other(self) -> None:
        # CPUTIN and SYSTIN are chassis-area sensors on Nuvoton chips,
        # not the CPU package temperature itself. "cpu" inside "cputin"
        # is a sub-word match per `_has_word`, so neither lands in cpu.
        assert category_for(_r("nct6798 CPUTIN")) == "other"
        assert category_for(_r("nct6798 SYSTIN")) == "other"

    def test_wifi_chip_returns_other(self) -> None:
        assert category_for(_r("mt7921_phy0 temp1")) == "other"

    # Edge cases
    def test_case_insensitive_uppercase(self) -> None:
        assert category_for(_r("K10TEMP TCTL")) == "cpu"

    def test_case_insensitive_lowercase(self) -> None:
        assert category_for(_r("nvidia gpu temp")) == "gpu"

    def test_case_insensitive_mixed(self) -> None:
        assert category_for(_r("NvIdIa GpU")) == "gpu"

    def test_empty_label_returns_other(self) -> None:
        assert category_for(_r("")) == "other"

    def test_substring_in_unrelated_word_does_not_match(self) -> None:
        # "auxiliarygpu" contains "gpu" but not as a discrete token;
        # _has_word should reject this. The reading is otherwise
        # unclassified, so it lands in "other".
        assert category_for(_r("auxiliarygpu sensor")) == "other"

    def test_substring_in_unrelated_word_does_not_match_cpu(self) -> None:
        # "cpuid" contains "cpu" but as part of a larger word.
        assert category_for(_r("cpuidentifier temp")) == "other"

    def test_vrm_wins_over_cpu_when_both_present(self) -> None:
        # A sensor labelled "CPU VRM" should land in vrm because the
        # VRM check runs first; this is the documented precedence.
        assert category_for(_r("CPU VRM core")) == "vrm"

    def test_returns_string_never_none(self) -> None:
        # Boundary: category_for must always return a string for any
        # input, never None and never empty.
        for label in ("", "  ", "asdf", "  cpu  ", "anything"):
            result = category_for(_r(label))
            assert isinstance(result, str)
            assert result  # non-empty
