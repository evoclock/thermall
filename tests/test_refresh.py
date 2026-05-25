# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the refresh loop wiring.

Built RED-GREEN-REFACTOR. Collectors are mocked so tests are fast,
deterministic, and don't touch real subprocesses.
"""

from __future__ import annotations

import pytest

from thermall.collectors import CollectorUnavailableError
from thermall.config import Config
from thermall.model import DeviceSnapshot, Severity
from thermall.refresh import collect_snapshot

# ---------------------------------------------------------------------------
# Round 1 — structure: collect_snapshot returns a DeviceSnapshot
# ---------------------------------------------------------------------------


def test_collect_snapshot_returns_device_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock all three collectors' live() to raise unavailability; the
    # function must still return a usable empty DeviceSnapshot.
    from thermall import refresh as r

    monkeypatch.setattr(
        r.SensorsCollector, "live", classmethod(lambda cls: _raise_unavailable("sensors"))
    )
    monkeypatch.setattr(
        r.NvidiaCollector, "live", classmethod(lambda cls: _raise_unavailable("nvidia"))
    )
    monkeypatch.setattr(
        r.SmartdJournalCollector,
        "live",
        classmethod(lambda cls: _raise_unavailable("smartd")),
    )

    snap = collect_snapshot(Config(detected_board=None))
    assert isinstance(snap, DeviceSnapshot)


def _raise_unavailable(name: str) -> str:
    raise CollectorUnavailableError(f"{name} not on PATH")


# ---------------------------------------------------------------------------
# Round 2 — smartd_available reflects whether the smartd collector ran
# ---------------------------------------------------------------------------


def test_smartd_unavailable_sets_field_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from thermall import refresh as r

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(lambda cls: "{}"))
    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(
        r.SmartdJournalCollector,
        "live",
        classmethod(lambda cls: _raise_unavailable("smartd")),
    )

    snap = collect_snapshot(Config(detected_board=None))
    assert snap.smartd_available is False


def test_smartd_available_when_collector_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    from thermall import refresh as r

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(lambda cls: "{}"))
    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    # Return an empty journal stream; the parser handles it.
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))

    snap = collect_snapshot(Config(detected_board=None))
    assert snap.smartd_available is True


# ---------------------------------------------------------------------------
# Round 3 — sensors data is parsed and routed into snapshot fields
# ---------------------------------------------------------------------------


_SENSORS_FIXTURE = """
{
  "k10temp-pci-00c3": {
    "Adapter": "PCI adapter",
    "Tctl": {"temp1_input": 72.0}
  },
  "nct6798-isa-0290": {
    "Adapter": "ISA adapter",
    "AUXTIN0": {"temp4_input": 92.0},
    "SYSTIN": {"temp1_input": 40.0},
    "fan1": {"fan1_input": 1450.0}
  }
}
"""


def test_sensors_temps_routed_into_correct_snapshot_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from thermall import refresh as r

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(lambda cls: _SENSORS_FIXTURE))
    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))

    snap = collect_snapshot(Config(detected_board=None))

    cpu_labels = {r.raw_label for r in snap.cpu_temps}
    vrm_labels = {r.raw_label for r in snap.vrm_temps}
    other_labels = {r.raw_label for r in snap.other_temps}
    fan_labels = {f.raw_label for f in snap.fans}

    # Tctl is routed to cpu by category_for
    assert "k10temp Tctl" in cpu_labels
    # AUXTIN0 lands in vrm
    assert "nct6798 AUXTIN0" in vrm_labels
    # SYSTIN is chassis -> "other"
    assert "nct6798 SYSTIN" in other_labels
    # Fan parsed
    assert "nct6798 fan1" in fan_labels


def test_readings_are_graded_against_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    from thermall import refresh as r

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(lambda cls: _SENSORS_FIXTURE))
    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))

    snap = collect_snapshot(Config(detected_board=None))

    # Tctl at 72.0 is below cpu warn (80) -> OK
    tctl = next(r for r in snap.cpu_temps if r.raw_label == "k10temp Tctl")
    assert tctl.severity is Severity.OK
    # AUXTIN0 at 92.0 is between vrm warn (90) and crit (100) -> WARN
    aux = next(r for r in snap.vrm_temps if r.raw_label == "nct6798 AUXTIN0")
    assert aux.severity is Severity.WARN


# ---------------------------------------------------------------------------
# Round 4 — nvidia data populates `snapshot.gpus`
# ---------------------------------------------------------------------------


_NVIDIA_FIXTURE = (
    "NVIDIA GeForce RTX 3060, 54, 34, 52.98, 2425, 12288\n"
    "NVIDIA GeForce RTX 5070 Ti, 46, 0, 9.69, 15, 16303\n"
)


def test_nvidia_collector_populates_gpus_field(monkeypatch: pytest.MonkeyPatch) -> None:
    from thermall import refresh as r

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(lambda cls: "{}"))
    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: _NVIDIA_FIXTURE))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))

    snap = collect_snapshot(Config(detected_board=None))
    assert len(snap.gpus) == 2
    assert snap.gpus[0].name == "NVIDIA GeForce RTX 3060"
    assert snap.gpus[1].name == "NVIDIA GeForce RTX 5070 Ti"


def test_nvidia_unavailable_returns_empty_gpus(monkeypatch: pytest.MonkeyPatch) -> None:
    from thermall import refresh as r

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(lambda cls: "{}"))
    monkeypatch.setattr(
        r.NvidiaCollector,
        "live",
        classmethod(lambda cls: _raise_unavailable("nvidia")),
    )
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))

    snap = collect_snapshot(Config(detected_board=None))
    assert snap.gpus == ()


# ---------------------------------------------------------------------------
# Round 5 — smartd events populate `drive_health_events`
# ---------------------------------------------------------------------------


_SMARTD_FIXTURE = (
    '{"MESSAGE":"smartd 7.2 starting","PRIORITY":"6",'
    '"__REALTIME_TIMESTAMP":"1700000000000000"}\n'
    '{"MESSAGE":"Device: /dev/nvme0, failed self-test","PRIORITY":"3",'
    '"__REALTIME_TIMESTAMP":"1700000001000000"}\n'
)


def test_smartd_events_populate_drive_health_events(monkeypatch: pytest.MonkeyPatch) -> None:
    from thermall import refresh as r

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(lambda cls: "{}"))
    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: _SMARTD_FIXTURE))

    snap = collect_snapshot(Config(detected_board=None))
    assert snap.smartd_available is True
    assert len(snap.drive_health_events) == 2
    messages = [e.message for e in snap.drive_health_events]
    assert any("failed self-test" in m for m in messages)


# ---------------------------------------------------------------------------
# Round 6 — labels are resolved through config.labels
# ---------------------------------------------------------------------------


def test_labels_resolved_through_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from thermall import refresh as r

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(lambda cls: _SENSORS_FIXTURE))
    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))

    config = Config(
        detected_board=None,
        labels={
            "k10temp Tctl": "CPU package",
            "nct6798 AUXTIN0": "VRM (CPU)",
            "nct6798 fan1": "CPU fan",
        },
    )
    snap = collect_snapshot(config)

    tctl = next(r for r in snap.cpu_temps if r.raw_label == "k10temp Tctl")
    assert tctl.display_label == "CPU package"

    aux = next(r for r in snap.vrm_temps if r.raw_label == "nct6798 AUXTIN0")
    assert aux.display_label == "VRM (CPU)"

    cpu_fan = next(f for f in snap.fans if f.raw_label == "nct6798 fan1")
    assert cpu_fan.display_label == "CPU fan"


def test_unmapped_label_keeps_display_label_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from thermall import refresh as r

    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(lambda cls: _SENSORS_FIXTURE))
    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))

    # Empty labels dict; nothing gets mapped
    snap = collect_snapshot(Config(detected_board=None, labels={}))
    tctl = next(r for r in snap.cpu_temps if r.raw_label == "k10temp Tctl")
    assert tctl.display_label is None


# ---------------------------------------------------------------------------
# Round 7 — collector parser failures (malformed input) are caught
# ---------------------------------------------------------------------------


def test_sensors_parser_value_error_does_not_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from thermall import refresh as r

    # Live returns non-JSON; parse() raises ValueError; refresh swallows.
    monkeypatch.setattr(r.SensorsCollector, "live", classmethod(lambda cls: "not json at all"))
    monkeypatch.setattr(r.NvidiaCollector, "live", classmethod(lambda cls: ""))
    monkeypatch.setattr(r.SmartdJournalCollector, "live", classmethod(lambda cls: ""))

    snap = collect_snapshot(Config(detected_board=None))
    assert snap.cpu_temps == ()
    assert snap.vrm_temps == ()
    assert snap.other_temps == ()
    assert snap.fans == ()
