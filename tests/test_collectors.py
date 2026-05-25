# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the collector layer.

Structural tests (ABC enforcement, command/argv pinning) run
unconditionally. Parse tests load fixtures via the `fixture_loader`
conftest helper, which `pytest.skip`s with a clear remediation message
when the fixture is absent.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from thermall.collectors import (
    Collector,
    NvidiaCollector,
    NvmeCollector,
    SensorsCollector,
    SmartdJournalCollector,
    severity_for_journal_record,
)
from thermall.model import Fan, Reading, Severity


class TestCollectorBase:
    def test_collector_is_abstract(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            Collector()  # type: ignore[abstract]

    def test_subclasses_pin_command_and_argv(self) -> None:
        assert SensorsCollector.command == "sensors"
        assert SensorsCollector.argv == ("sensors", "-j")
        assert NvidiaCollector.command == "nvidia-smi"
        assert NvmeCollector.command == "nvme"
        # NvmeCollector overrides live() to enumerate devices; argv is a
        # placeholder rather than a single canonical call.
        assert NvmeCollector.argv == ("nvme", "smart-log")
        # SmartdJournalCollector uses SYSLOG_IDENTIFIER for distro
        # portability (Debian/Ubuntu unit name differs from Arch/Fedora).
        assert SmartdJournalCollector.command == "journalctl"
        assert "SYSLOG_IDENTIFIER=smartd" in SmartdJournalCollector.argv


class TestSensorsCollector:
    def test_parse_raises_on_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="invalid JSON"):
            SensorsCollector.parse("not json at all")

    def test_parse_empty_object_returns_two_empty_tuples(self) -> None:
        readings, fans = SensorsCollector.parse("{}")
        assert readings == ()
        assert fans == ()

    def test_parse_skips_adapter_field(self) -> None:
        raw = '{"chip-pci-0001": {"Adapter": "PCI adapter", "temp1": {"temp1_input": 50.0}}}'
        readings, _ = SensorsCollector.parse(raw)
        assert len(readings) == 1
        assert readings[0].value == 50.0

    def test_parse_separates_temps_and_fans(self) -> None:
        raw = (
            '{"nct-isa-0290": '
            '{"Adapter": "ISA", '
            '"Tctl": {"temp1_input": 45.0}, '
            '"fan1": {"fan1_input": 1200.0}}}'
        )
        readings, fans = SensorsCollector.parse(raw)
        assert len(readings) == 1
        assert isinstance(readings[0], Reading)
        assert readings[0].unit == "C"
        assert len(fans) == 1
        assert isinstance(fans[0], Fan)
        assert fans[0].rpm == 1200

    def test_parse_strips_chip_bus_suffix_for_label(self) -> None:
        raw = '{"k10temp-pci-00c3": {"Adapter": "x", "Tctl": {"temp1_input": 44.0}}}'
        readings, _ = SensorsCollector.parse(raw)
        # Bus suffix dropped, sensor name preserved
        assert readings[0].raw_label == "k10temp Tctl"

    def test_parse_preserves_nvme_bus_suffix(self) -> None:
        # Multiple NVMe drives produce multiple `nvme-pci-XXXX` chips;
        # preserve the suffix so the storage panel can distinguish them
        # via `thermall.sysfs.nvme_devices`. Without this, both drives
        # would collide on `nvme Composite`.
        raw = (
            '{"nvme-pci-0100": {"Adapter": "x",'
            ' "Composite": {"temp1_input": 39.0}},'
            ' "nvme-pci-0800": {"Adapter": "x",'
            ' "Composite": {"temp1_input": 40.0}}}'
        )
        readings, _ = SensorsCollector.parse(raw)
        labels = sorted(r.raw_label for r in readings)
        assert labels == ["nvme-pci-0100 Composite", "nvme-pci-0800 Composite"]

    def test_parse_preserves_nvme_suffix_for_sub_sensors(self) -> None:
        # Single drive can expose Composite plus Sensor 1, Sensor 2,
        # etc. All sub-sensors must carry the same chip suffix.
        raw = (
            '{"nvme-pci-0100": {"Adapter": "x",'
            ' "Composite": {"temp1_input": 39.0},'
            ' "Sensor 1": {"temp2_input": 41.0}}}'
        )
        readings, _ = SensorsCollector.parse(raw)
        labels = sorted(r.raw_label for r in readings)
        assert labels == ["nvme-pci-0100 Composite", "nvme-pci-0100 Sensor 1"]

    def test_parse_ignores_threshold_fields(self) -> None:
        # _max, _crit, _alarm are metadata; only _input is the live reading.
        raw = (
            '{"nvme-pci-0800": {"Adapter": "x", '
            '"Composite": {"temp1_input": 39.85, "temp1_max": 82.85, '
            '"temp1_crit": 89.85, "temp1_alarm": 0.0}}}'
        )
        readings, _ = SensorsCollector.parse(raw)
        assert len(readings) == 1
        assert readings[0].value == 39.85
        # And the label still carries the chip suffix.
        assert readings[0].raw_label == "nvme-pci-0800 Composite"

    def test_parse_fixture_produces_expected_chips(
        self, fixture_loader: Callable[[str], str]
    ) -> None:
        raw = fixture_loader("sensors_output.json")
        readings, _ = SensorsCollector.parse(raw)
        labels = {r.raw_label for r in readings}
        # k10temp exposes the CPU package and per-CCD readings
        assert "k10temp Tctl" in labels
        # Each NVMe exposes a Composite reading
        nvme_composites = [r for r in readings if r.raw_label.endswith("Composite")]
        assert len(nvme_composites) >= 1


class TestNvidiaCollector:
    def test_empty_string_returns_empty_tuple(self) -> None:
        assert NvidiaCollector.parse("") == ()

    def test_parse_single_row(self) -> None:
        raw = "NVIDIA GeForce RTX 4070, 52, 39, 78.43, 1234, 12288"
        gpus = NvidiaCollector.parse(raw)
        assert len(gpus) == 1
        gpu = gpus[0]
        assert gpu.index == 0
        assert gpu.name == "NVIDIA GeForce RTX 4070"
        assert gpu.temperature_c == 52.0
        assert gpu.fan_percent == 39.0
        assert gpu.power_watts == 78.43
        assert gpu.memory_used_mb == 1234
        assert gpu.memory_total_mb == 12288

    def test_parse_handles_na_values(self) -> None:
        raw = "NVIDIA T4, 60, [N/A], [N/A], 500, 16000"
        gpus = NvidiaCollector.parse(raw)
        assert gpus[0].fan_percent is None
        assert gpus[0].power_watts is None
        assert gpus[0].memory_used_mb == 500

    def test_parse_multiple_rows_indexes_in_order(self) -> None:
        raw = (
            "NVIDIA GeForce RTX 3060, 54, 34, 52.98, 2425, 12288\n"
            "NVIDIA GeForce RTX 5070 Ti, 46, 0, 9.69, 15, 16303\n"
        )
        gpus = NvidiaCollector.parse(raw)
        assert len(gpus) == 2
        assert gpus[0].index == 0
        assert gpus[1].index == 1
        assert gpus[0].name == "NVIDIA GeForce RTX 3060"
        assert gpus[1].name == "NVIDIA GeForce RTX 5070 Ti"

    def test_parse_fixture(self, fixture_loader: Callable[[str], str]) -> None:
        raw = fixture_loader("nvidia_smi_output.csv")
        gpus = NvidiaCollector.parse(raw)
        # Test machine has two GPUs
        assert len(gpus) >= 1
        for gpu in gpus:
            assert gpu.temperature_c > 0
            assert gpu.name.startswith("NVIDIA")


class TestNvmeCollector:
    def test_empty_string_returns_empty_tuple(self) -> None:
        assert NvmeCollector.parse("") == ()

    def test_parse_minimum_block(self) -> None:
        raw = (
            "Smart Log for NVME device:nvme0n1 namespace-id:ffffffff\n"
            "critical_warning                          : 0\n"
            "temperature                               : 42 C (315 Kelvin)\n"
        )
        drives = NvmeCollector.parse(raw)
        assert len(drives) == 1
        assert drives[0].device == "/dev/nvme0n1"
        assert drives[0].composite_temp_c == 42.0
        assert drives[0].critical_warning == 0

    def test_parse_hex_critical_warning(self) -> None:
        raw = (
            "Smart Log for NVME device:nvme1n1 namespace-id:ffffffff\n"
            "critical_warning                          : 0x4\n"
            "temperature                               : 50 C\n"
        )
        drives = NvmeCollector.parse(raw)
        assert drives[0].critical_warning == 4
        assert drives[0].device == "/dev/nvme1n1"

    def test_parse_extracts_sensor_temps(self) -> None:
        raw = (
            "Smart Log for NVME device:nvme0n1 namespace-id:ffffffff\n"
            "temperature                               : 43 C\n"
            "temperature_sensor_1                      : 43 C\n"
            "temperature_sensor_2                      : 50 C\n"
        )
        drives = NvmeCollector.parse(raw)
        assert drives[0].sensor_temps_c == (43.0, 50.0)

    def test_parse_returns_empty_when_no_temperature_line(self) -> None:
        # If the header is there but no temperature key, the drive is
        # unusable for thermall's purposes.
        raw = (
            "Smart Log for NVME device:nvme0n1 namespace-id:ffffffff\n"
            "critical_warning                          : 0\n"
        )
        assert NvmeCollector.parse(raw) == ()

    def test_parse_two_concatenated_blocks(self) -> None:
        # Simulates what live() returns when enumerating two devices.
        raw = (
            "Smart Log for NVME device:nvme0n1 namespace-id:ffffffff\n"
            "critical_warning                          : 0\n"
            "temperature                               : 40 C\n"
            "\n"
            "Smart Log for NVME device:nvme1n1 namespace-id:ffffffff\n"
            "critical_warning                          : 0\n"
            "temperature                               : 45 C\n"
        )
        drives = NvmeCollector.parse(raw)
        assert len(drives) == 2
        assert {d.device for d in drives} == {"/dev/nvme0n1", "/dev/nvme1n1"}
        assert {d.composite_temp_c for d in drives} == {40.0, 45.0}

    def test_parse_fixture(self, fixture_loader: Callable[[str], str]) -> None:
        raw = fixture_loader("nvme_smart_output.txt")
        drives = NvmeCollector.parse(raw)
        # Fixture currently has one drive (nvme0n1); the parser still
        # works for the multi-drive concatenated case (see above).
        assert len(drives) >= 1
        d = drives[0]
        assert d.device.startswith("/dev/nvme")
        assert 0 < d.composite_temp_c < 100

    def test_devices_returns_sorted_tuple_of_nvme_paths(self) -> None:
        # Cannot assert specific contents without depending on the test
        # host, but the return shape and ordering are contractual.
        devs = NvmeCollector.devices()
        assert isinstance(devs, tuple)
        assert list(devs) == sorted(devs)
        for path in devs:
            assert path.startswith("/dev/nvme")
            assert path.endswith("n1")


class TestSeverityForJournalRecord:
    def test_low_priority_always_crit(self) -> None:
        for prio in (0, 1, 2, 3):
            assert severity_for_journal_record(prio, "any message") is Severity.CRIT

    def test_priority_4_defaults_to_warn(self) -> None:
        assert severity_for_journal_record(4, "anything") is Severity.WARN

    def test_priority_6_with_no_keywords_is_ok(self) -> None:
        assert severity_for_journal_record(6, "Starting smartd") is Severity.OK

    def test_crit_keyword_elevates_low_priority(self) -> None:
        assert severity_for_journal_record(6, "Device: /dev/sda, failed self-test") is Severity.CRIT

    def test_warn_keyword_elevates_to_warn(self) -> None:
        assert (
            severity_for_journal_record(6, "Device: /dev/nvme0, temperature exceeded threshold")
            is Severity.WARN
        )

    def test_smart_usage_attribute_change_is_not_warn(self) -> None:
        # smartd's routine value-changed log embeds an attribute name
        # that may contain "Temperature" (as the attribute label) but
        # is informational, not a temperature alert. Pin that this
        # specific shape stays OK.
        message = (
            "Device: /dev/sdb [SAT], "
            "SMART Usage Attribute: 194 Temperature_Celsius changed from 33 to 34"
        )
        assert severity_for_journal_record(6, message) is Severity.OK

    def test_smart_usage_attribute_for_offline_uncorrectable_is_not_crit(self) -> None:
        # Same shape as above but with an attribute name that embeds
        # a CRIT keyword. The "SMART Usage Attribute" prefix demotes
        # to OK because a value change for that attribute is normal
        # SMART telemetry, not a fault report.
        message = (
            "Device: /dev/sda [SAT], "
            "SMART Usage Attribute: 198 Offline_Uncorrectable changed from 0 to 0"
        )
        assert severity_for_journal_record(6, message) is Severity.OK

    def test_temperature_above_threshold_is_warn(self) -> None:
        # Real temperature warnings keep matching: smartd says
        # "above threshold" / "reached critical limit" when there's
        # an actual fault. Pin that the tightened keyword list still
        # catches them.
        message = "Device: /dev/sda, Temperature 65 Celsius above threshold 60 Celsius"
        assert severity_for_journal_record(6, message) is Severity.WARN

    def test_reached_critical_limit_is_warn(self) -> None:
        message = "Device: /dev/sda, Temperature 65 Celsius reached critical limit of 60 Celsius"
        assert severity_for_journal_record(6, message) is Severity.WARN

    def test_debug_priority_with_no_keywords_is_unknown(self) -> None:
        assert severity_for_journal_record(7, "debug noise") is Severity.UNKNOWN

    def test_cant_monitor_attribute_is_not_crit(self) -> None:
        # smartd emits diagnostic notices that contain a _CRIT_KEYWORDS
        # substring ("Offline_Uncorrectable_Count") but describe
        # smartd's own monitoring inability, not drive health. The
        # dashboard should NOT surface these as "Needs attention".
        message = "Device: /dev/sda, Can't monitor Offline_Uncorrectable_Count Attribute"
        assert severity_for_journal_record(6, message) is Severity.OK

    def test_no_longer_monitoring_is_not_crit(self) -> None:
        message = "Device: /dev/sdb, no longer monitoring Pending sector count"
        assert severity_for_journal_record(6, message) is Severity.OK

    def test_genuine_uncorrectable_event_still_crit(self) -> None:
        # Without the informational prefix, "uncorrectable" remains a
        # CRIT keyword. Pin the discriminator so the demotion only
        # fires when smartd is explicitly disclaiming its own ability.
        message = "Device: /dev/sda, 5 Currently unreadable (pending) and uncorrectable sectors"
        assert severity_for_journal_record(6, message) is Severity.CRIT


class TestSmartdJournalCollector:
    def test_empty_returns_empty_tuple(self) -> None:
        assert SmartdJournalCollector.parse("") == ()
        assert SmartdJournalCollector.parse("   \n  \n") == ()

    def test_skips_malformed_lines_silently(self) -> None:
        raw = (
            'not json\n{"MESSAGE":"ok","PRIORITY":"6","__REALTIME_TIMESTAMP":"1700000000000000"}\n'
        )
        events = SmartdJournalCollector.parse(raw)
        assert len(events) == 1
        assert events[0].message == "ok"

    def test_parses_minimum_record(self) -> None:
        raw = (
            '{"MESSAGE":"Started smartd","PRIORITY":"6","__REALTIME_TIMESTAMP":"1700000000000000"}'
        )
        events = SmartdJournalCollector.parse(raw)
        assert len(events) == 1
        e = events[0]
        assert e.message == "Started smartd"
        assert e.priority == 6
        assert e.severity is Severity.OK
        assert e.device is None
        assert e.timestamp.year == 2023  # 1700000000 unix => Nov 2023

    def test_extracts_device_path_from_message(self) -> None:
        raw = (
            '{"MESSAGE":"Device: /dev/nvme0, FAILED SELF-TEST",'
            '"PRIORITY":"3","__REALTIME_TIMESTAMP":"1700000000000000"}'
        )
        events = SmartdJournalCollector.parse(raw)
        assert events[0].device == "/dev/nvme0"
        assert events[0].severity is Severity.CRIT

    def test_skips_record_with_no_message(self) -> None:
        raw = '{"PRIORITY":"6","__REALTIME_TIMESTAMP":"1700000000000000"}'
        assert SmartdJournalCollector.parse(raw) == ()

    def test_skips_record_with_no_timestamp(self) -> None:
        raw = '{"MESSAGE":"orphan","PRIORITY":"6"}'
        assert SmartdJournalCollector.parse(raw) == ()

    def test_missing_priority_defaults_to_6(self) -> None:
        raw = '{"MESSAGE":"no priority field","__REALTIME_TIMESTAMP":"1700000000000000"}'
        events = SmartdJournalCollector.parse(raw)
        assert events[0].priority == 6

    def test_parses_fixture(self, fixture_loader: Callable[[str], str]) -> None:
        raw = fixture_loader("smartd_journal.json")
        events = SmartdJournalCollector.parse(raw)
        # 72 lines in the fixture; the parser should produce events for
        # every line that has both MESSAGE and __REALTIME_TIMESTAMP.
        assert len(events) > 0
        # Every event has the four required fields populated.
        for e in events:
            assert e.message
            assert 0 <= e.priority <= 7
            assert e.timestamp is not None
            assert e.severity is not None

    # Edge cases below: boundary values, malformed input, mixed batches.

    def test_priority_out_of_range_low_clamps_to_zero(self) -> None:
        raw = '{"MESSAGE":"weird","PRIORITY":"-5","__REALTIME_TIMESTAMP":"1700000000000000"}'
        events = SmartdJournalCollector.parse(raw)
        assert events[0].priority == 0
        # Priority 0 (emergency) is always CRIT
        assert events[0].severity is Severity.CRIT

    def test_priority_out_of_range_high_clamps_to_seven(self) -> None:
        raw = '{"MESSAGE":"weird","PRIORITY":"99","__REALTIME_TIMESTAMP":"1700000000000000"}'
        events = SmartdJournalCollector.parse(raw)
        assert events[0].priority == 7

    def test_non_numeric_priority_defaults_to_six(self) -> None:
        raw = '{"MESSAGE":"bad prio","PRIORITY":"info","__REALTIME_TIMESTAMP":"1700000000000000"}'
        events = SmartdJournalCollector.parse(raw)
        assert events[0].priority == 6

    def test_non_numeric_timestamp_skips_record(self) -> None:
        raw = '{"MESSAGE":"bad ts","PRIORITY":"6","__REALTIME_TIMESTAMP":"yesterday"}'
        assert SmartdJournalCollector.parse(raw) == ()

    def test_empty_message_field_skips_record(self) -> None:
        # Empty string MESSAGE is treated the same as missing; smartd
        # never emits empty messages in practice and we have no
        # actionable event without one.
        raw = '{"MESSAGE":"","PRIORITY":"6","__REALTIME_TIMESTAMP":"1700000000000000"}'
        assert SmartdJournalCollector.parse(raw) == ()

    def test_mixed_valid_and_invalid_batch(self) -> None:
        raw = (
            "not json\n"
            '{"MESSAGE":"first","PRIORITY":"6","__REALTIME_TIMESTAMP":"1700000000000000"}\n'
            "   \n"
            '{"MESSAGE":"bad ts","PRIORITY":"6","__REALTIME_TIMESTAMP":"oops"}\n'
            '{"MESSAGE":"second","PRIORITY":"4","__REALTIME_TIMESTAMP":"1700000001000000"}\n'
            "[1,2,3]\n"
        )
        events = SmartdJournalCollector.parse(raw)
        # Two valid records survive; non-JSON, blank, bad-ts, and
        # non-object lines are all skipped without raising.
        assert len(events) == 2
        assert events[0].message == "first"
        assert events[1].message == "second"
        assert events[1].severity is Severity.WARN

    def test_only_first_device_path_extracted_when_multiple_present(self) -> None:
        raw = (
            '{"MESSAGE":"comparing /dev/nvme0 and /dev/sda1",'
            '"PRIORITY":"6","__REALTIME_TIMESTAMP":"1700000000000000"}'
        )
        events = SmartdJournalCollector.parse(raw)
        assert events[0].device == "/dev/nvme0"

    def test_message_with_no_device_path_returns_none(self) -> None:
        raw = (
            '{"MESSAGE":"smartd starting up","PRIORITY":"6",'
            '"__REALTIME_TIMESTAMP":"1700000000000000"}'
        )
        events = SmartdJournalCollector.parse(raw)
        assert events[0].device is None

    def test_unicode_in_message_is_preserved(self) -> None:
        raw = (
            '{"MESSAGE":"smartd: °C threshold café",'
            '"PRIORITY":"6","__REALTIME_TIMESTAMP":"1700000000000000"}'
        )
        events = SmartdJournalCollector.parse(raw)
        assert "°C" in events[0].message
        assert "café" in events[0].message

    def test_keyword_severity_is_case_insensitive(self) -> None:
        # severity_for_journal_record lowercases the message; verify
        # uppercase keywords still trigger elevation.
        raw = (
            '{"MESSAGE":"DEVICE /dev/sda: FAILED",'
            '"PRIORITY":"6","__REALTIME_TIMESTAMP":"1700000000000000"}'
        )
        events = SmartdJournalCollector.parse(raw)
        assert events[0].severity is Severity.CRIT

    def test_extra_unknown_fields_are_ignored(self) -> None:
        # Journal records carry many fields; we only care about four.
        raw = (
            '{"MESSAGE":"ok","PRIORITY":"6","__REALTIME_TIMESTAMP":"1700000000000000",'
            '"_HOSTNAME":"host","_PID":"1234","_UID":"0","RANDOM_THING":"x"}'
        )
        events = SmartdJournalCollector.parse(raw)
        assert len(events) == 1
        assert events[0].message == "ok"

    def test_top_level_array_silently_skipped(self) -> None:
        # `journalctl` always emits objects, but defensively the parser
        # treats arrays / scalars at top level as malformed.
        raw = '[{"MESSAGE":"wrong-shape"}]'
        assert SmartdJournalCollector.parse(raw) == ()
