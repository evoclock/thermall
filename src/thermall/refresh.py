# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Refresh loop: collect from every available source into one DeviceSnapshot.

`collect_snapshot(config)` runs the three unprivileged collectors
(sensors, nvidia-smi, smartd journal), catches per-collector
unavailability so one missing source does not break the others,
resolves human labels via `config.labels`, grades readings via
`config.thresholds`, and returns a `DeviceSnapshot`.

The opt-in NvmeCollector path (reading the helper-service JSON) is
deliberately not wired here for v1; the helper integration lands in
a separate task once the helper has soak time in the wild.
"""

from __future__ import annotations

from collections.abc import Mapping

from thermall.collectors import (
    CollectorUnavailableError,
    NvidiaCollector,
    SensorsCollector,
    SmartdJournalCollector,
)
from thermall.config import Config
from thermall.mapping import category_for, grade_reading, resolve
from thermall.model import (
    DeviceSnapshot,
    DriveHealthEvent,
    Fan,
    Gpu,
    Reading,
    aggregate,
)

# Explicit re-export list. Tests and other call sites reach for the
# collector classes through this module to monkeypatch them in one
# place; advertising them in __all__ keeps strict-mypy happy without
# scattering `from thermall.collectors import …` redundantly across
# every test file.
__all__ = [
    "CollectorUnavailableError",
    "Config",
    "DeviceSnapshot",
    "DriveHealthEvent",
    "Fan",
    "Gpu",
    "NvidiaCollector",
    "Reading",
    "SensorsCollector",
    "SmartdJournalCollector",
    "aggregate",
    "category_for",
    "collect_snapshot",
    "grade_reading",
    "resolve",
]


def collect_snapshot(config: Config) -> DeviceSnapshot:
    """Run all unprivileged collectors; return a single `DeviceSnapshot`.

    Each collector is invoked under its own try/except so one
    `CollectorUnavailableError` (binary missing, permission denied,
    timeout) does not abort the others. `smartd_available` on the
    returned snapshot is `True` when SmartdJournalCollector returned
    data, `False` when it raised; panels use this to distinguish
    "no events" from "no collector".

    Readings get human labels (via `mapping.resolve`) and per-category
    severity (via `mapping.grade_reading`) before aggregation; fans
    get human labels but no grading (the threshold model for fans is
    different and lives in the panel layer, not the threshold set).
    """

    readings, fans = _safe_sensors()
    gpus = _safe_nvidia()
    events, smartd_available = _safe_smartd()

    enriched_readings = tuple(_enrich_reading(r, config) for r in readings)
    enriched_fans = tuple(_enrich_fan(f, config.labels) for f in fans)

    return aggregate(
        temperatures=enriched_readings,
        fans=enriched_fans,
        gpus=gpus,
        drive_health_events=events,
        smartd_available=smartd_available,
    )


def _safe_sensors() -> tuple[tuple[Reading, ...], tuple[Fan, ...]]:
    """Run `SensorsCollector.live()`+`parse()`; empty result on failure."""

    try:
        raw = SensorsCollector.live()
    except CollectorUnavailableError:
        return (), ()
    try:
        return SensorsCollector.parse(raw)
    except (ValueError, NotImplementedError):
        return (), ()


def _safe_nvidia() -> tuple[Gpu, ...]:
    """Run `NvidiaCollector.live()`+`parse()`; empty result on failure."""

    try:
        raw = NvidiaCollector.live()
    except CollectorUnavailableError:
        return ()
    try:
        return NvidiaCollector.parse(raw)
    except (ValueError, NotImplementedError):
        return ()


def _safe_smartd() -> tuple[tuple[DriveHealthEvent, ...], bool]:
    """Run smartd collector; `(events, available)` tuple."""

    try:
        raw = SmartdJournalCollector.live()
    except CollectorUnavailableError:
        return (), False
    try:
        return SmartdJournalCollector.parse(raw), True
    except (ValueError, NotImplementedError):
        return (), True


def _enrich_reading(reading: Reading, config: Config) -> Reading:
    """Resolve human label, then grade severity against thresholds."""

    labelled = _with_resolved_label(reading, config.labels)
    category = category_for(labelled)
    thresholds = config.thresholds.get(category)
    if thresholds is None:
        return labelled
    return grade_reading(labelled, thresholds)


def _with_resolved_label(reading: Reading, label_map: Mapping[str, str]) -> Reading:
    """Apply the mapping layer's `resolve()` to the reading's label."""

    human, was_mapped = resolve(reading.raw_label, label_map)
    if was_mapped:
        return reading.with_label(human)
    return reading


def _enrich_fan(fan: Fan, label_map: Mapping[str, str]) -> Fan:
    """Resolve human label for a fan; fan is frozen so we construct fresh."""

    human, was_mapped = resolve(fan.raw_label, label_map)
    if was_mapped:
        return Fan(raw_label=fan.raw_label, rpm=fan.rpm, display_label=human)
    return fan
