# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Pure data model for thermall.

Immutable dataclasses for what each collector returns, plus `aggregate()` to
compose them into a single `DeviceSnapshot`. No I/O in this module;
collectors construct these and the UI consumes them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Self


class Severity(StrEnum):
    """Threshold-graded severity for any numeric reading."""

    OK = "ok"
    WARN = "warn"
    CRIT = "crit"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Reading:
    """A single numeric reading with a unit and optional threshold severity.

    `raw_label` carries the kernel sensor name (e.g. `AUXTIN0`, `Tctl`). The
    UI prefers `display_label` when available; the mapping layer resolves
    `raw_label` to a human label and writes it back.
    """

    raw_label: str
    value: float
    unit: str
    display_label: str | None = None
    severity: Severity = Severity.UNKNOWN

    def with_label(self, display_label: str) -> Self:
        return type(self)(
            raw_label=self.raw_label,
            value=self.value,
            unit=self.unit,
            display_label=display_label,
            severity=self.severity,
        )

    def with_severity(self, severity: Severity) -> Self:
        return type(self)(
            raw_label=self.raw_label,
            value=self.value,
            unit=self.unit,
            display_label=self.display_label,
            severity=severity,
        )

    @property
    def label(self) -> str:
        """Best label for display: human if mapped, raw otherwise."""

        return self.display_label or self.raw_label


@dataclass(frozen=True, slots=True)
class Fan:
    """A fan reading.

    Stored separately from temperature readings because the threshold model is
    different. A fan at 0 RPM is a CRIT condition only if the corresponding
    component is hot; the aggregator layer decides that.
    """

    raw_label: str
    rpm: int
    display_label: str | None = None

    @property
    def label(self) -> str:
        return self.display_label or self.raw_label

    @property
    def is_stopped(self) -> bool:
        return self.rpm == 0


@dataclass(frozen=True, slots=True)
class Gpu:
    """A GPU device snapshot (one entry per visible GPU)."""

    index: int
    name: str
    temperature_c: float
    fan_percent: float | None
    power_watts: float | None
    memory_used_mb: int | None
    memory_total_mb: int | None
    severity: Severity = Severity.UNKNOWN


@dataclass(frozen=True, slots=True)
class NvmeDrive:
    """An NVMe device snapshot (one entry per visible drive)."""

    device: str  # e.g. /dev/nvme0n1
    composite_temp_c: float
    sensor_temps_c: tuple[float, ...] = ()
    critical_warning: int = 0
    severity: Severity = Severity.UNKNOWN


@dataclass(frozen=True, slots=True)
class DriveHealthEvent:
    """A single smartd-emitted event from the systemd journal.

    Represents one warning or status message smartd wrote about a drive.
    `device` is parsed best-effort from `message` (smartd's format varies
    by version and drive type). `severity` is derived from the journal
    priority and message keywords; see `severity_for_journal_record` in
    the collector module.
    """

    timestamp: datetime
    message: str
    priority: int  # systemd journal priority: 0 emerg .. 7 debug
    severity: Severity = Severity.UNKNOWN
    device: str | None = None


# Categories that show severity colour inside their own panels but
# do NOT drive the dashboard-wide status verdict. VRM and motherboard
# thermistors (the `vrm_temps` group, and the SYSTIN / PCH / AUXTIN
# readings that land in `other_temps` under the "other" category)
# typically idle in the 60-85°C range on modern AMD boards; treating
# them as primary indicators makes "Running warm" the default state,
# which buries genuine CPU / GPU / NVMe alerts.
ADVISORY_CATEGORIES: frozenset[str] = frozenset({"vrm", "other"})


@dataclass(frozen=True, slots=True)
class DeviceSnapshot:
    """A single point-in-time snapshot of all collectors.

    The dashboard re-renders from a fresh `DeviceSnapshot` on each refresh
    tick. `taken_at` is wall-clock UTC; the UI may convert to local for
    display.
    """

    taken_at: datetime
    cpu_temps: tuple[Reading, ...] = ()
    vrm_temps: tuple[Reading, ...] = ()
    other_temps: tuple[Reading, ...] = ()
    fans: tuple[Fan, ...] = ()
    gpus: tuple[Gpu, ...] = ()
    nvmes: tuple[NvmeDrive, ...] = ()
    drive_health_events: tuple[DriveHealthEvent, ...] = ()
    smartd_available: bool = True
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def primary_temps(self) -> tuple[Reading, ...]:
        """All readings that count toward the dashboard-wide verdict.

        Excludes `vrm_temps` (always advisory) and `other_temps`
        entries whose `category_for(reading)` is in
        `ADVISORY_CATEGORIES`. NVMe composite readings (also in
        other_temps with category `nvme`) ARE counted because storage
        thermal alerts are actionable.
        """

        from thermall.mapping import category_for

        primaries: list[Reading] = list(self.cpu_temps)
        for reading in self.other_temps:
            if category_for(reading) not in ADVISORY_CATEGORIES:
                primaries.append(reading)
        return tuple(primaries)

    @property
    def has_warnings(self) -> bool:
        if self.warnings:
            return True
        if any(r.severity in (Severity.WARN, Severity.CRIT) for r in self.primary_temps):
            return True
        return any(e.severity in (Severity.WARN, Severity.CRIT) for e in self.drive_health_events)

    @property
    def max_severity(self) -> Severity:
        """Highest severity among primary indicators.

        Primary = CPU temps + storage (NVMe) temps + GPUs + drive
        health events. VRM and motherboard / chipset readings stay
        visible inside their panels but do not drive this verdict
        (see `ADVISORY_CATEGORIES`).
        """

        severities = [r.severity for r in self.primary_temps]
        severities.extend(g.severity for g in self.gpus)
        severities.extend(n.severity for n in self.nvmes)
        severities.extend(e.severity for e in self.drive_health_events)

        if Severity.CRIT in severities:
            return Severity.CRIT
        if Severity.WARN in severities:
            return Severity.WARN
        if Severity.OK in severities:
            return Severity.OK
        return Severity.UNKNOWN


def aggregate(
    *,
    temperatures: tuple[Reading, ...] = (),
    fans: tuple[Fan, ...] = (),
    gpus: tuple[Gpu, ...] = (),
    nvmes: tuple[NvmeDrive, ...] = (),
    drive_health_events: tuple[DriveHealthEvent, ...] = (),
    smartd_available: bool = True,
    warnings: tuple[str, ...] = (),
) -> DeviceSnapshot:
    """Build a `DeviceSnapshot` from already-collected pieces.

    Routes each `Reading` in `temperatures` into one of `cpu_temps`,
    `vrm_temps`, or `other_temps` via `thermall.mapping.category_for`.
    The "nvme" and "gpu" categories also land in `other_temps` for the
    snapshot's purposes: NVMe and GPU panels read their data from
    dedicated `nvmes` and `gpus` fields (different shape), and the
    `Reading`-based composite temps for those devices are surfaced
    alongside other miscellany.
    """

    # Imported here, not at module top, to avoid a circular import:
    # mapping imports from model.
    from thermall.mapping import category_for

    cpu: list[Reading] = []
    vrm: list[Reading] = []
    other: list[Reading] = []
    for reading in temperatures:
        category = category_for(reading)
        if category == "cpu":
            cpu.append(reading)
        elif category == "vrm":
            vrm.append(reading)
        else:
            other.append(reading)

    return DeviceSnapshot(
        taken_at=datetime.now(tz=UTC),
        cpu_temps=tuple(cpu),
        vrm_temps=tuple(vrm),
        other_temps=tuple(other),
        fans=fans,
        gpus=gpus,
        nvmes=nvmes,
        drive_health_events=drive_health_events,
        smartd_available=smartd_available,
        warnings=warnings,
    )
