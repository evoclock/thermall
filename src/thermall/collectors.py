# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Sensor / GPU / NVMe data collection.

A `Collector` reads from one underlying source (`sensors -j`,
`nvidia-smi --query-gpu`, `nvme smart-log`) and returns normalised model
objects. Each subclass pins `command` and `argv` and implements `parse()`
against raw stdout. `available()` checks PATH; `live()` runs the
subprocess. Parsers are pure with respect to their input.
"""

from __future__ import annotations

import glob
import json
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import ClassVar

from thermall.model import DriveHealthEvent, Fan, Gpu, NvmeDrive, Reading, Severity


class CollectorUnavailableError(RuntimeError):
    """Raised when the underlying tool is not on PATH or returns no data."""


class Collector(ABC):
    """Common contract for all data sources."""

    command: ClassVar[str]
    argv: ClassVar[tuple[str, ...]]

    @classmethod
    def available(cls) -> bool:
        """True when the underlying command is on PATH."""

        return shutil.which(cls.command) is not None

    @classmethod
    def live(cls, *, timeout_seconds: float = 5.0) -> str:
        """Run the underlying command and return its stdout.

        Raises `CollectorUnavailableError` if the binary is missing or
        returns a non-zero exit code.
        """

        if not cls.available():
            raise CollectorUnavailableError(f"{cls.command} not on PATH")
        try:
            result = subprocess.run(
                cls.argv,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CollectorUnavailableError(
                f"{cls.command} timed out after {timeout_seconds}s"
            ) from exc
        if result.returncode != 0:
            raise CollectorUnavailableError(
                f"{cls.command} exited {result.returncode}: {result.stderr.strip()}"
            )
        return result.stdout

    @classmethod
    @abstractmethod
    def parse(cls, raw: str) -> object:
        """Convert raw stdout to typed model objects.

        Subclasses pin the return type.
        """


# Chip name suffix patterns from lm-sensors: "k10temp-pci-00c3",
# "nct6798-isa-0290", "nvme-pci-0800". The leading short form (before the
# bus suffix) is what users put in their config; we expose it as the
# chip prefix in raw_label.
_CHIP_SUFFIX = re.compile(r"-(?:pci|isa|virtual|acpi)-[0-9a-f]+$", re.IGNORECASE)


def _chip_short(chip_full: str) -> str:
    """Strip the bus suffix from a sensors chip name.

    `k10temp-pci-00c3` becomes `k10temp`. Chip names that do not match the
    expected suffix pattern (some virtual / synthetic chips) pass through
    unchanged.

    NVMe chips are a deliberate exception: each SSD on the system shows
    up as its own `nvme-pci-<bus><devfn>` chip, and stripping the suffix
    would collapse every drive's `Composite` reading to the same label
    (`nvme Composite`). The storage panel needs the chip name intact so
    it can resolve the drive model via `thermall.sysfs.nvme_devices`.
    Other chip families (k10temp, nct67xx, ...) do not collide on real
    hardware and stay short for readability.
    """

    if chip_full.startswith("nvme-"):
        return chip_full
    return _CHIP_SUFFIX.sub("", chip_full)


class SensorsCollector(Collector):
    """Collects from `sensors -j` (lm-sensors)."""

    command: ClassVar[str] = "sensors"
    argv: ClassVar[tuple[str, ...]] = ("sensors", "-j")

    @classmethod
    def parse(cls, raw: str) -> tuple[tuple[Reading, ...], tuple[Fan, ...]]:
        """Parse `sensors -j` JSON; returns `(temperatures, fans)`.

        Walks every chip, every sensor under each chip, finds the
        `*_input` reading, and produces a `Reading` (for `temp*`) or a
        `Fan` (for `fan*`). Voltage (`in*`) and other sensor types are
        ignored at this layer.
        """

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"sensors -j produced invalid JSON: {exc}") from exc

        if not isinstance(data, dict):
            return ((), ())

        readings: list[Reading] = []
        fans: list[Fan] = []

        for chip_full, chip_data in data.items():
            if not isinstance(chip_data, dict):
                continue
            chip = _chip_short(chip_full)
            for sensor_name, sensor_values in chip_data.items():
                if sensor_name == "Adapter" or not isinstance(sensor_values, dict):
                    continue
                input_key, input_value = _find_input(sensor_values)
                if input_key is None or input_value is None:
                    continue
                label = f"{chip} {sensor_name}"
                if input_key.startswith("fan"):
                    fans.append(Fan(raw_label=label, rpm=round(float(input_value))))
                elif input_key.startswith("temp"):
                    readings.append(Reading(raw_label=label, value=float(input_value), unit="C"))

        return tuple(readings), tuple(fans)


def _find_input(sensor_values: dict[str, object]) -> tuple[str | None, float | None]:
    """Locate the live `*_input` field in a sensor's value dict.

    sensors output puts the live reading under a key like `temp1_input` or
    `fan1_input`, alongside threshold metadata (`temp1_max`, `temp1_crit`,
    `temp1_alarm`) that we ignore at the collector layer.
    """

    for key, value in sensor_values.items():
        if key.endswith("_input") and isinstance(value, int | float):
            return key, float(value)
    return None, None


class NvidiaCollector(Collector):
    """Collects from `nvidia-smi --query-gpu=... --format=csv`."""

    command: ClassVar[str] = "nvidia-smi"
    argv: ClassVar[tuple[str, ...]] = (
        "nvidia-smi",
        "--query-gpu=name,temperature.gpu,fan.speed,power.draw,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    )

    @classmethod
    def parse(cls, raw: str) -> tuple[Gpu, ...]:
        """Parse the CSV stdout into a tuple of `Gpu`.

        One row per GPU. Cards reporting `[N/A]` (common for fan speed on
        passively cooled cards, power on integrated GPUs) become `None` on
        the corresponding field.
        """

        if not raw.strip():
            return ()

        gpus: list[Gpu] = []
        for index, line in enumerate(raw.strip().splitlines()):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) != 6:
                continue
            name, temp, fan, power, mem_used, mem_total = parts
            gpus.append(
                Gpu(
                    index=index,
                    name=name,
                    temperature_c=float(temp),
                    fan_percent=_optional_float(fan),
                    power_watts=_optional_float(power),
                    memory_used_mb=_optional_int(mem_used),
                    memory_total_mb=_optional_int(mem_total),
                )
            )
        return tuple(gpus)


def _optional_float(value: str) -> float | None:
    """Convert a CSV cell to float, or `None` if it is `[N/A]` / blank."""

    value = value.strip()
    if not value or value == "[N/A]":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _optional_int(value: str) -> int | None:
    """Convert a CSV cell to int, or `None` if it is `[N/A]` / blank."""

    value = value.strip()
    if not value or value == "[N/A]":
        return None
    try:
        return int(value)
    except ValueError:
        return None


_NVME_DEVICE_LINE = re.compile(r"NVME device\s*:\s*(\S+)", re.IGNORECASE)
_NVME_SENSOR_LINE = re.compile(r"^temperature[_ ]sensor[_ ](\d+)$", re.IGNORECASE)
_NVME_BLOCK_SPLIT = re.compile(r"(?=Smart Log for NVME device:)")


class NvmeCollector(Collector):
    """Collects from `nvme smart-log` for every visible NVMe device.

    Enumerates `/dev/nvme*n1` rather than assuming a single device. Each
    `smart-log` call is independent; failures on one device (permission
    denied, drive disappeared) do not stop the others.

    Often needs `CAP_SYS_ADMIN`. If `nvme` returns non-zero on every
    visible device, `live()` raises `CollectorUnavailableError` and the
    aggregator simply omits this layer. Users can grant the capability
    once with `sudo setcap 'cap_sys_admin+ep' "$(which nvme)"` so the
    binary works as a normal user thereafter.
    """

    command: ClassVar[str] = "nvme"
    # `argv` from the base class is the "single canonical invocation"
    # contract, which does not fit a per-device tool. We keep a
    # placeholder so structural tests can still assert the field, but
    # `live()` is overridden below to enumerate devices.
    argv: ClassVar[tuple[str, ...]] = ("nvme", "smart-log")

    @classmethod
    def devices(cls) -> tuple[str, ...]:
        """Enumerate visible NVMe namespace-1 device paths.

        Glob pattern: `/dev/nvme*n1`. Sorted for stable ordering across
        runs. Returns an empty tuple on systems with no NVMe drives.
        """

        return tuple(sorted(glob.glob("/dev/nvme*n1")))

    @classmethod
    def live(cls, *, timeout_seconds: float = 5.0) -> str:
        """Run `nvme smart-log` for every visible NVMe device.

        Concatenates the per-device stdout, separated by a blank line so
        the parser can split them back into individual blocks. Skips
        devices that fail individually; raises only if every device
        fails or no devices exist.
        """

        if not cls.available():
            raise CollectorUnavailableError(f"{cls.command} not on PATH")

        devices = cls.devices()
        if not devices:
            raise CollectorUnavailableError("no /dev/nvme*n1 devices visible")

        chunks: list[str] = []
        errors: list[str] = []
        for device in devices:
            try:
                result = subprocess.run(
                    ("nvme", "smart-log", device),
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                errors.append(f"{device}: timeout")
                continue
            if result.returncode != 0:
                errors.append(f"{device}: rc={result.returncode} {result.stderr.strip()}")
                continue
            chunks.append(result.stdout)

        if not chunks:
            raise CollectorUnavailableError(
                "nvme smart-log failed on all devices: " + "; ".join(errors)
            )
        return "\n".join(chunks)

    @classmethod
    def parse(cls, raw: str) -> tuple[NvmeDrive, ...]:
        """Parse concatenated `nvme smart-log` output into one drive per block.

        Splits the input at each `Smart Log for NVME device:` header,
        then parses each block independently. For each block reads the
        device name from the header line, the composite `temperature`,
        every `temperature_sensor_N`, and the `critical_warning` flag.
        """

        if not raw.strip():
            return ()

        blocks = [b for b in _NVME_BLOCK_SPLIT.split(raw) if b.strip()]
        drives: list[NvmeDrive] = []
        for block in blocks:
            drive = cls._parse_one_block(block)
            if drive is not None:
                drives.append(drive)
        return tuple(drives)

    @classmethod
    def _parse_one_block(cls, raw: str) -> NvmeDrive | None:
        device = "/dev/nvme0n1"
        composite: float | None = None
        sensor_temps: list[float] = []
        critical_warning = 0

        for line in raw.splitlines():
            stripped = line.strip()
            device_match = _NVME_DEVICE_LINE.search(stripped)
            if device_match:
                device = f"/dev/{device_match.group(1)}"
                continue
            if ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            key = key.strip().lower()
            value = value.strip()
            if key == "temperature":
                composite = _first_celsius(value)
            elif _NVME_SENSOR_LINE.match(key):
                temp = _first_celsius(value)
                if temp is not None:
                    sensor_temps.append(temp)
            elif key == "critical_warning":
                critical_warning = _parse_int_maybe_hex(value)

        if composite is None:
            return None
        return NvmeDrive(
            device=device,
            composite_temp_c=composite,
            sensor_temps_c=tuple(sensor_temps),
            critical_warning=critical_warning,
        )


def _first_celsius(value: str) -> float | None:
    """Extract the first numeric Celsius reading from a smart-log value.

    `nvme smart-log` formats temperature like `39 C (312 Kelvin)` or
    `39 C`. We take the leading number and ignore the rest.
    """

    parts = value.split()
    if not parts:
        return None
    try:
        return float(parts[0])
    except ValueError:
        return None


def _parse_int_maybe_hex(value: str) -> int:
    """Parse an integer that may be decimal or `0x`-prefixed hex.

    `critical_warning` is sometimes formatted as `0x0` and sometimes as
    plain `0`. `int(value, 0)` honours the prefix when present.
    """

    try:
        return int(value, 0)
    except ValueError:
        return 0


# Match `/dev/nvme0`, `/dev/nvme0n1`, `/dev/sda`, `/dev/sda1`. Captures
# the full path so the collector can store it verbatim.
_DRIVE_PATH = re.compile(r"/dev/(?:nvme\d+(?:n\d+)?|sd[a-z]\d*|hd[a-z]\d*|vd[a-z]\d*)")

# Smartd message keywords that elevate severity above what the journal
# priority alone implies. smartd often logs warnings at priority 4
# (warning) but some operationally-critical events at priority 5 / 6
# (notice / info) — these strings bump them to WARN or CRIT regardless.
_CRIT_KEYWORDS = (
    "failed",
    "failure",
    "uncorrectable",
    "previously-recorded",
    "selftest failed",
)
_WARN_KEYWORDS = (
    "spare",
    "below threshold",
    "above threshold",
    "reached critical limit",
    "currently too hot",
    "reallocated",
    "pending sector",
    "exceeded",
    "percent-used",
    "wearout",
)

# Informational-not-alarm patterns. smartd emits diagnostic notices
# that match _CRIT_KEYWORDS / _WARN_KEYWORDS substrings (the
# "Can't monitor Offline_Uncorrectable_Count" diagnostic, or the
# routine "SMART Usage Attribute: NNN Temperature_Celsius changed
# from X to Y" log) but are about smartd's own capability or its
# normal attribute-change accounting — not drive-health alerts.
# These demote severity back to OK so the dashboard doesn't surface
# a non-actionable "Needs attention" line.
_INFORMATIONAL_PATTERNS = (
    "can't monitor",
    "cannot monitor",
    "no longer monitoring",
    "no longer being monitored",
    "could not monitor",
    # smartd's routine "attribute moved" log; the value-change
    # itself is normal SMART telemetry. A real warning has
    # "above threshold" / "reached critical limit" wording in
    # addition, which the WARN check catches before this demoter
    # matters when both apply.
    "smart usage attribute",
)


def severity_for_journal_record(priority: int, message: str) -> Severity:
    """Map a smartd journal record to a `Severity`.

    Combines systemd journal priority (0 emergency ... 7 debug) with a
    keyword scan on the message body. Priority 0-3 is always CRIT.
    Priority 4 is WARN by default. Priority 5-6 is OK unless a critical
    or warning keyword is present in the message, in which case the
    keyword wins — UNLESS the message also matches an informational
    pattern (smartd's own "Can't monitor X" diagnostics, which embed
    a CRIT keyword as the attribute name but are not health alarms).
    """

    if priority <= 3:
        return Severity.CRIT
    if priority == 4:
        return Severity.WARN

    lowered = message.lower()
    # Informational-not-alarm always wins; smartd's "Can't monitor
    # Offline_Uncorrectable_Count" matches both _CRIT_KEYWORDS and
    # this pattern, and the dashboard should not flag the user.
    if any(pattern in lowered for pattern in _INFORMATIONAL_PATTERNS):
        return Severity.OK
    if any(kw in lowered for kw in _CRIT_KEYWORDS):
        return Severity.CRIT
    if any(kw in lowered for kw in _WARN_KEYWORDS):
        return Severity.WARN
    if priority == 7:
        return Severity.UNKNOWN
    return Severity.OK


def _extract_device(message: str) -> str | None:
    """Best-effort device path extraction from a smartd message body."""

    match = _DRIVE_PATH.search(message)
    return match.group(0) if match else None


class SmartdJournalCollector(Collector):
    """Collects drive-health events from `smartd` via the systemd journal.

    Queries `journalctl SYSLOG_IDENTIFIER=smartd -o json` rather than
    `-u <unit>` so the collector is portable across distros: the unit
    name is `smartmontools.service` on Debian / Ubuntu but
    `smartd.service` on Arch / Fedora / openSUSE, while the syslog
    identifier is always `smartd`.

    Requires no privilege beyond journal read access (typically granted
    to the `adm` or `systemd-journal` group, which is the first user's
    default on Debian / Ubuntu). On distros where the user is not in
    those groups by default, the first-run setup screen detects an
    empty result and surfaces a `sudo usermod -aG systemd-journal $USER`
    fix-up hint.
    """

    command: ClassVar[str] = "journalctl"
    argv: ClassVar[tuple[str, ...]] = (
        "journalctl",
        "SYSLOG_IDENTIFIER=smartd",
        "-o",
        "json",
        "--since",
        "24 hours ago",
    )

    @classmethod
    def parse(cls, raw: str) -> tuple[DriveHealthEvent, ...]:
        """Parse `journalctl -o json` output (one JSON object per line).

        Each line is a complete journal record. Malformed lines are
        skipped rather than raising; an empty journal returns an empty
        tuple.
        """

        if not raw.strip():
            return ()

        events: list[DriveHealthEvent] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue

            message = str(record.get("MESSAGE", ""))
            if not message:
                continue

            timestamp = _parse_journal_timestamp(record.get("__REALTIME_TIMESTAMP"))
            if timestamp is None:
                continue

            priority = _parse_journal_priority(record.get("PRIORITY"))
            severity = severity_for_journal_record(priority, message)
            device = _extract_device(message)

            events.append(
                DriveHealthEvent(
                    timestamp=timestamp,
                    message=message,
                    priority=priority,
                    severity=severity,
                    device=device,
                )
            )
        return tuple(events)


def _parse_journal_timestamp(raw: object) -> datetime | None:
    """`__REALTIME_TIMESTAMP` is microseconds since Unix epoch, as a string."""

    if raw is None:
        return None
    try:
        microseconds = int(str(raw))
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(microseconds / 1_000_000, tz=UTC)


def _parse_journal_priority(raw: object) -> int:
    """`PRIORITY` is a string '0'..'7'. Default to 6 (info) if absent or junk."""

    if raw is None:
        return 6
    try:
        priority = int(str(raw))
    except (TypeError, ValueError):
        return 6
    return max(0, min(7, priority))
