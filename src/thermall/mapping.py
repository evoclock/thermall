# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Resolve raw sensor data to display labels and threshold severities.

Pure functions; no I/O. Threshold values and label maps come from
`thermall.config`. The two responsibilities (label lookup and threshold
grading) live in one module because they share scope and tend to be
called together by the aggregator.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from thermall.model import Reading, Severity

# Module-level default phrasing per severity. Categories may override
# any subset of these via `ThresholdSet.severity_phrases`; missing keys
# in an override fall back here. Every Severity value must be present
# so phrase_for() can never raise KeyError.
DEFAULT_PHRASES: dict[Severity, str] = {
    Severity.OK: "cool",
    Severity.WARN: "running warm",
    Severity.CRIT: "needs attention",
    Severity.UNKNOWN: "no reading",
}


def resolve(raw_label: str, label_map: Mapping[str, str]) -> tuple[str, bool]:
    """Return `(human_label, was_mapped)` for a raw kernel sensor name.

    - `was_mapped` is `True` when an entry was found in `label_map`.
    - On miss, returns `(raw_label, False)` so the caller can still display
      a sensible label.

    Lookup is exact-match first, then case-insensitive, then passthrough.
    """

    if raw_label in label_map:
        return label_map[raw_label], True
    lower = raw_label.lower()
    for key, value in label_map.items():
        if key.lower() == lower:
            return value, True
    return raw_label, False


def resolve_many(
    raw_labels: list[str], label_map: Mapping[str, str]
) -> dict[str, tuple[str, bool]]:
    """Batch variant for callers that resolve many labels at once."""

    return {raw: resolve(raw, label_map) for raw in raw_labels}


@dataclass(frozen=True, slots=True)
class ThresholdSet:
    """Warn and critical thresholds for one sensor category.

    `category` is a short key like `cpu`, `vrm`, `gpu`, `nvme`. Both
    bounds are upper bounds (sensor crosses them upward as it heats).

    `severity_phrases` is an optional per-category override map of
    human-friendly phrases to display alongside readings (e.g. "CPU
    running hot" instead of the generic "running warm"). Keys present
    in this dict override `DEFAULT_PHRASES`; missing keys fall back to
    the default. The helper `phrase_for(severity)` resolves the lookup
    in one call and never raises.
    """

    category: str
    warn: float
    crit: float
    severity_phrases: dict[Severity, str] | None = field(default=None)

    def grade(self, value: float) -> Severity:
        if value >= self.crit:
            return Severity.CRIT
        if value >= self.warn:
            return Severity.WARN
        return Severity.OK

    def phrase_for(self, severity: Severity) -> str:
        """Return the user-facing phrase for `severity`.

        Lookup order: instance override (`self.severity_phrases`) then
        module-level `DEFAULT_PHRASES`. Always resolves to a non-empty
        string; never raises `KeyError` for any valid `Severity` value.
        """

        if self.severity_phrases is not None and severity in self.severity_phrases:
            return self.severity_phrases[severity]
        return DEFAULT_PHRASES[severity]


def grade_reading(reading: Reading, thresholds: ThresholdSet) -> Reading:
    """Return a new `Reading` with `severity` set per `thresholds`."""

    return reading.with_severity(thresholds.grade(reading.value))


def grade_many(
    readings: list[Reading], thresholds_by_category: dict[str, ThresholdSet]
) -> list[Reading]:
    """Grade a list of readings against per-category thresholds.

    Routes each reading to a threshold set via `category_for`. Readings
    whose category has no threshold entry retain their existing
    severity (`Severity.UNKNOWN` by default). Higher-level callers that
    already know which set applies should call `grade_reading` directly.
    """

    out: list[Reading] = []
    for reading in readings:
        chosen = thresholds_by_category.get(category_for(reading))
        if chosen is None:
            out.append(reading)
            continue
        out.append(grade_reading(reading, chosen))
    return out


def category_for(reading: Reading) -> str:
    """Classify a `Reading` into one of: `cpu`, `vrm`, `nvme`, `gpu`, `other`.

    Heuristic by `raw_label` substring match (case-insensitive). Order
    of checks is significant: more specific markers win over generic
    ones. Returns `"other"` for anything that does not match a known
    category; never returns an empty string.

    The mapping is intentionally a small, hand-curated heuristic rather
    than a configurable lookup: per-board variation is handled by
    label rewriting in `Config.labels`, not by inventing new categories.
    """

    label = reading.raw_label.lower()

    # VRM markers are checked before CPU so that an "AUXTIN" sensor
    # labelled with "CPU VRM" lands in VRM rather than CPU.
    if "auxtin" in label or "vrm" in label:
        return "vrm"

    if "tctl" in label or "tccd" in label or label.startswith("k10") or _has_word(label, "cpu"):
        return "cpu"

    if "composite" in label or label.startswith("nvme"):
        return "nvme"

    if _has_word(label, "gpu"):
        return "gpu"

    return "other"


def _has_word(label: str, word: str) -> bool:
    """True when `word` appears as a discrete token in `label`.

    Discrete means: surrounded by start-of-string, end-of-string, or
    non-alphanumeric characters. Prevents false matches where the
    substring appears inside an unrelated word
    (e.g. `auxiliarygpu` should not match `cpu`).
    """

    if word not in label:
        return False
    idx = 0
    while True:
        idx = label.find(word, idx)
        if idx < 0:
            return False
        before_ok = idx == 0 or not label[idx - 1].isalnum()
        end = idx + len(word)
        after_ok = end == len(label) or not label[end].isalnum()
        if before_ok and after_ok:
            return True
        idx = end
