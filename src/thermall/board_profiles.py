# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Built-in motherboard label profiles.

Auto-populated defaults that turn cryptic kernel sensor names into
human labels for boards we have verified. The lookup is consumed by
`thermall.config` (auto-detect happens there); this module is pure
data plus a small match helper.

Adding a new board profile is a community-friendly contribution path:
write a `BoardProfile` against your own verified hardware, add it to
`PROFILES`, ship a test asserting the profile is found. Do not guess
labels for boards you do not have access to; per
`writing-style.md` § 5, methodological claims (and label claims are
methodological in spirit) cite primary sources or are omitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BoardProfile:
    """A per-board mapping of raw sensor labels to human-readable names.

    `vendor` and `product` match the strings reported by Linux DMI
    (`/sys/devices/virtual/dmi/id/board_vendor` and `board_name`).
    `labels` keys are the `<chip> <sensor>` form produced by
    `SensorsCollector` (chip name with the `-pci-NNNN` or `-isa-NNNN`
    bus suffix stripped, joined with the sensor name by a single space).
    """

    vendor: str
    product: str
    labels: dict[str, str] = field(default_factory=dict)
    notes: str = ""


# ASUS ROG STRIX B550-F GAMING WIFI II — the development / test
# machine. Labels verified against `sensors -j` output captured with
# `nct6775 force_id=0xd428` loaded; see
# `tests/fixtures/sensors_output.json`.
#
# Notes on neutrality: AUXTIN0..4 are auxiliary temperature inputs
# whose physical sensor varies by motherboard model and BIOS revision.
# Naming them "VRM (CPU)" / "PCH" / etc. would require per-board
# verification we have not done (the user's specific board may match
# common community mappings, but we do not assert this without
# primary-source confirmation). Same logic for fan1..fan7. The user
# customises by editing `~/.config/thermall/config.toml` after first
# launch.
_B550F_LABELS: dict[str, str] = {
    "k10temp Tctl": "CPU package",
    "k10temp Tccd1": "CPU CCD1",
    "k10temp Tccd2": "CPU CCD2",
    "nct6798 SYSTIN": "Motherboard",
    "nct6798 CPUTIN": "CPU socket",
    "nct6798 AUXTIN0": "Aux temp 0",
    "nct6798 AUXTIN1": "Aux temp 1",
    "nct6798 AUXTIN2": "Aux temp 2",
    "nct6798 AUXTIN3": "Aux temp 3",
    "nct6798 AUXTIN4": "Aux temp 4",
    "nct6798 fan1": "Fan 1",
    "nct6798 fan2": "Fan 2",
    "nct6798 fan3": "Fan 3",
    "nct6798 fan4": "Fan 4",
    "nct6798 fan5": "Fan 5",
    "nct6798 fan6": "Fan 6",
    "nct6798 fan7": "Fan 7",
    "nvme Composite": "NVMe SSD",
}


PROFILES: tuple[BoardProfile, ...] = (
    BoardProfile(
        vendor="ASUSTeK COMPUTER INC.",
        product="ROG STRIX B550-F GAMING WIFI II",
        labels=_B550F_LABELS,
        notes=(
            "Verified against tests/fixtures/sensors_output.json on the "
            "development host with `nct6775 force_id=0xd428` loaded. "
            "AUXTIN0..4 and fan1..7 use neutral names because the "
            "physical sensor / fan-header assignment varies per board "
            "and per build; rename them in ~/.config/thermall/config.toml "
            "to match your wiring."
        ),
    ),
)


def find_profile(vendor: str | None, product: str | None) -> BoardProfile | None:
    """Return the `BoardProfile` matching `(vendor, product)`, or None.

    Matching is case-insensitive and tolerates leading / trailing
    whitespace (DMI files often end with a newline). Returns `None`
    when either argument is `None` or empty, or when no profile in
    `PROFILES` matches.
    """

    if not vendor or not product:
        return None

    vendor_norm = vendor.strip().casefold()
    product_norm = product.strip().casefold()

    for profile in PROFILES:
        if (
            profile.vendor.strip().casefold() == vendor_norm
            and profile.product.strip().casefold() == product_norm
        ):
            return profile
    return None
