# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the data model and aggregator."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from thermall.model import (
    DeviceSnapshot,
    DriveHealthEvent,
    Fan,
    Gpu,
    NvmeDrive,
    Reading,
    Severity,
    aggregate,
)


class TestReading:
    def test_label_prefers_display_label(self) -> None:
        r = Reading(raw_label="AUXTIN0", value=45.0, unit="C", display_label="VRM (CPU)")
        assert r.label == "VRM (CPU)"

    def test_label_falls_back_to_raw(self) -> None:
        r = Reading(raw_label="AUXTIN0", value=45.0, unit="C")
        assert r.label == "AUXTIN0"

    def test_with_label_returns_new_reading_without_mutating(self) -> None:
        original = Reading(raw_label="AUXTIN0", value=45.0, unit="C")
        relabelled = original.with_label("VRM (CPU)")
        assert original.display_label is None
        assert relabelled.display_label == "VRM (CPU)"
        assert relabelled.raw_label == original.raw_label
        assert relabelled.value == original.value

    def test_with_severity_returns_new_reading_without_mutating(self) -> None:
        original = Reading(raw_label="Tctl", value=85.0, unit="C")
        graded = original.with_severity(Severity.WARN)
        assert original.severity is Severity.UNKNOWN
        assert graded.severity is Severity.WARN

    def test_frozen_disallows_mutation(self) -> None:
        r = Reading(raw_label="Tctl", value=85.0, unit="C")
        with pytest.raises((AttributeError, TypeError)):
            r.value = 90.0  # type: ignore[misc]


class TestFan:
    def test_label_prefers_display_label(self) -> None:
        f = Fan(raw_label="fan6", rpm=1200, display_label="NVMe heatsink")
        assert f.label == "NVMe heatsink"

    def test_label_falls_back_to_raw(self) -> None:
        f = Fan(raw_label="fan6", rpm=1200)
        assert f.label == "fan6"

    def test_is_stopped_at_zero_rpm(self) -> None:
        assert Fan(raw_label="fan6", rpm=0).is_stopped is True
        assert Fan(raw_label="fan6", rpm=1).is_stopped is False


class TestDeviceSnapshot:
    def _now(self) -> datetime:
        return datetime(2026, 5, 22, 18, 0, tzinfo=UTC)

    def test_empty_snapshot_has_no_warnings(self) -> None:
        snap = DeviceSnapshot(taken_at=self._now())
        assert snap.has_warnings is False
        assert snap.max_severity is Severity.UNKNOWN

    def test_warning_propagates_from_explicit_warnings_tuple(self) -> None:
        snap = DeviceSnapshot(taken_at=self._now(), warnings=("fan6 stopped",))
        assert snap.has_warnings is True

    def test_warning_propagates_from_reading_severity(self) -> None:
        cpu = Reading(raw_label="Tctl", value=95.0, unit="C", severity=Severity.CRIT)
        snap = DeviceSnapshot(taken_at=self._now(), cpu_temps=(cpu,))
        assert snap.has_warnings is True

    def test_max_severity_picks_highest_across_categories(self) -> None:
        cpu = Reading(raw_label="Tctl", value=85.0, unit="C", severity=Severity.WARN)
        vrm = Reading(raw_label="AUXTIN0", value=95.0, unit="C", severity=Severity.WARN)
        gpu = Gpu(
            index=0,
            name="GPU",
            temperature_c=90.0,
            fan_percent=80.0,
            power_watts=200.0,
            memory_used_mb=1024,
            memory_total_mb=8192,
            severity=Severity.CRIT,
        )
        snap = DeviceSnapshot(
            taken_at=self._now(),
            cpu_temps=(cpu,),
            vrm_temps=(vrm,),
            gpus=(gpu,),
        )
        assert snap.max_severity is Severity.CRIT

    def test_max_severity_ok_when_only_ok_readings(self) -> None:
        ok = Reading(raw_label="Tctl", value=40.0, unit="C", severity=Severity.OK)
        snap = DeviceSnapshot(taken_at=self._now(), cpu_temps=(ok,))
        assert snap.max_severity is Severity.OK

    def test_drive_health_events_contribute_to_warnings_and_severity(self) -> None:
        event = DriveHealthEvent(
            timestamp=self._now(),
            message="Device: /dev/nvme0, failed self-test",
            priority=3,
            severity=Severity.CRIT,
            device="/dev/nvme0",
        )
        snap = DeviceSnapshot(taken_at=self._now(), drive_health_events=(event,))
        assert snap.has_warnings is True
        assert snap.max_severity is Severity.CRIT

    def test_ok_drive_health_events_do_not_trigger_warning(self) -> None:
        event = DriveHealthEvent(
            timestamp=self._now(),
            message="Started smartd",
            priority=6,
            severity=Severity.OK,
        )
        snap = DeviceSnapshot(taken_at=self._now(), drive_health_events=(event,))
        assert snap.has_warnings is False


class TestNvmeDrive:
    def test_defaults(self) -> None:
        d = NvmeDrive(device="/dev/nvme0n1", composite_temp_c=43.0)
        assert d.sensor_temps_c == ()
        assert d.critical_warning == 0
        assert d.severity is Severity.UNKNOWN


class TestAggregate:
    def test_empty_returns_snapshot(self) -> None:
        snap = aggregate()
        assert snap.cpu_temps == ()
        assert snap.vrm_temps == ()
        assert snap.other_temps == ()
        assert snap.fans == ()
        assert snap.gpus == ()
        assert snap.nvmes == ()
        assert snap.warnings == ()
        assert snap.taken_at is not None

    def test_aggregate_routes_cpu_temp_to_cpu_temps(self) -> None:
        r = Reading(raw_label="k10temp Tctl", value=50.0, unit="C")
        snap = aggregate(temperatures=(r,))
        assert r in snap.cpu_temps
        assert r not in snap.other_temps
        assert r not in snap.vrm_temps

    def test_aggregate_routes_vrm_temp_to_vrm_temps(self) -> None:
        r = Reading(raw_label="nct6798 AUXTIN0", value=85.0, unit="C")
        snap = aggregate(temperatures=(r,))
        assert r in snap.vrm_temps
        assert r not in snap.other_temps
        assert r not in snap.cpu_temps

    def test_aggregate_routes_other_temp_to_other_temps(self) -> None:
        # SYSTIN is not CPU and not VRM; lands in "other".
        r = Reading(raw_label="nct6798 SYSTIN", value=42.0, unit="C")
        snap = aggregate(temperatures=(r,))
        assert r in snap.other_temps
        assert r not in snap.cpu_temps
        assert r not in snap.vrm_temps

    def test_aggregate_routes_nvme_composite_to_other_temps(self) -> None:
        # NVMe composite temperatures from sensors -j land in "other";
        # the storage panel consumes them from there. Richer SMART data
        # flows through the `nvmes` field via the helper-service path.
        r = Reading(raw_label="nvme Composite", value=38.0, unit="C")
        snap = aggregate(temperatures=(r,))
        assert r in snap.other_temps

    def test_aggregate_routes_multiple_categories_in_one_call(self) -> None:
        cpu = Reading(raw_label="k10temp Tctl", value=72.0, unit="C")
        vrm = Reading(raw_label="nct6798 AUXTIN1", value=88.0, unit="C")
        other = Reading(raw_label="nct6798 SYSTIN", value=40.0, unit="C")
        nvme = Reading(raw_label="nvme Composite", value=38.0, unit="C")
        snap = aggregate(temperatures=(cpu, vrm, other, nvme))
        assert snap.cpu_temps == (cpu,)
        assert snap.vrm_temps == (vrm,)
        assert other in snap.other_temps
        assert nvme in snap.other_temps

    def test_fans_pass_through(self) -> None:
        f = Fan(raw_label="fan6", rpm=1200)
        snap = aggregate(fans=(f,))
        assert snap.fans == (f,)

    def test_warnings_pass_through(self) -> None:
        snap = aggregate(warnings=("fan6 stopped",))
        assert snap.warnings == ("fan6 stopped",)

    def test_drive_health_events_pass_through(self) -> None:
        event = DriveHealthEvent(
            timestamp=datetime(2026, 5, 22, 18, 0, tzinfo=UTC),
            message="Started smartd",
            priority=6,
            severity=Severity.OK,
        )
        snap = aggregate(drive_health_events=(event,))
        assert snap.drive_health_events == (event,)
