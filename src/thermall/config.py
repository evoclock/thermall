# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Load and validate thermall configuration from TOML.

Config lives at `~/.config/thermall/config.toml` (XDG-compliant). If absent,
built-in defaults are used and the caller can prompt the user to write a
starter file (see `cli`).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from thermall.board_profiles import BoardProfile, find_profile
from thermall.mapping import ThresholdSet
from thermall.model import Severity

DEFAULT_REFRESH_SECONDS = 2.0
DEFAULT_THEME = "default"

# Standard Linux DMI sysfs root. World-readable, no privilege needed.
# Overridable for tests via `detect_board(dmi_root=...)` and
# `load(dmi_root=...)`.
DEFAULT_DMI_ROOT = Path("/sys/devices/virtual/dmi/id")

_DEFAULT_THRESHOLDS: dict[str, ThresholdSet] = {
    "cpu": ThresholdSet(
        category="cpu",
        warn=80.0,
        crit=90.0,
        severity_phrases={
            Severity.OK: "cool",
            Severity.WARN: "CPU running hot",
            Severity.CRIT: "CPU critical",
        },
    ),
    "vrm": ThresholdSet(
        category="vrm",
        warn=90.0,
        crit=100.0,
        severity_phrases={
            Severity.OK: "cool",
            Severity.WARN: "VRM running hot",
            Severity.CRIT: "VRM critical",
        },
    ),
    "gpu": ThresholdSet(
        category="gpu",
        warn=75.0,
        crit=85.0,
        severity_phrases={
            Severity.OK: "cool",
            Severity.WARN: "GPU running hot",
            Severity.CRIT: "GPU critical",
        },
    ),
    "nvme": ThresholdSet(
        category="nvme",
        warn=60.0,
        crit=75.0,
        severity_phrases={
            Severity.OK: "cool",
            Severity.WARN: "drive running warm",
            Severity.CRIT: "drive critical",
        },
    ),
}


@dataclass(frozen=True, slots=True)
class Config:
    """Validated thermall configuration."""

    refresh_seconds: float = DEFAULT_REFRESH_SECONDS
    theme: str = DEFAULT_THEME
    labels: dict[str, str] = field(default_factory=dict)
    thresholds: dict[str, ThresholdSet] = field(default_factory=lambda: dict(_DEFAULT_THRESHOLDS))
    tmux_layout: str = "3-pane"
    detected_board: str | None = None

    def to_toml(self) -> str:
        """Serialize config to TOML string."""
        lines = ["[general]"]
        lines.append(f"refresh_seconds = {self.refresh_seconds}")
        lines.append(f'theme = "{self.theme}"')
        lines.append(f'tmux_layout = "{self.tmux_layout}"')

        if self.labels:
            lines.append("")
            lines.append("[labels]")
            for raw, display in sorted(self.labels.items()):
                lines.append(f"  {raw!r} = {display!r}")

        lines.append("")
        lines.append("[thresholds]")
        for cat, ts in sorted(self.thresholds.items()):
            lines.append(f"  [thresholds.{cat}]")
            lines.append(f"    warn = {ts.warn}")
            lines.append(f"    crit = {ts.crit}")

        return "\n".join(lines)


def default_config_path() -> Path:
    """XDG path to the user's config file."""

    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "thermall" / "config.toml"


def state_path() -> Path:
    """XDG path to the user's state file (separate from config).

    State is mutable runtime data (dismissed help-cards, future
    layout preferences) versus config which represents intended
    settings. Both live under the same XDG dir so users see them
    together.
    """

    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "thermall" / "state.toml"


def load_dismissed(path: Path | None = None) -> set[str]:
    """Return the set of prereq ids the user has dismissed.

    Missing state file: empty set. Malformed TOML: empty set (treat
    a corrupt state file as a soft reset rather than blocking the
    dashboard on a startup error).
    """

    target = path or state_path()
    if not target.exists():
        return set()

    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return set()

    dismissed = raw.get("help_cards", {}).get("dismissed", [])
    if not isinstance(dismissed, list):
        return set()
    return {str(item) for item in dismissed}


def write_dismissal(prereq_id: str, path: Path | None = None) -> None:
    """Append `prereq_id` to the dismissed list in the state file.

    Idempotent: dismissing the same id twice is a no-op. Creates the
    state file and its parent directory if needed.
    """

    target = path or state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = load_dismissed(target)
    if prereq_id in existing:
        return
    existing.add(prereq_id)
    _write_dismissed_set(target, existing)


def clear_dismissed(path: Path | None = None) -> None:
    """Reset the dismissed list to empty.

    Used by the settings screen's "show all dismissed help cards
    again" action.
    """

    target = path or state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_dismissed_set(target, set())


def _write_dismissed_set(target: Path, dismissed: set[str]) -> None:
    """Write `dismissed` as a TOML list under `[help_cards] dismissed`."""

    items = sorted(dismissed)
    body = "[help_cards]\ndismissed = [" + ", ".join(f'"{x}"' for x in items) + "]\n"
    target.write_text(body, encoding="utf-8")


def write_config(config: Config, path: Path | None = None) -> None:
    """Persist `config` to TOML at `path` (default: `default_config_path()`).

    Creates parent dir if needed. Used by the settings screen when
    the user changes a value; every change saves immediately, no
    explicit "Save" step.
    """

    target = path or default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(config.to_toml(), encoding="utf-8")


def detect_board(dmi_root: Path | None = None) -> BoardProfile | None:
    """Read `board_vendor` and `board_name` from DMI; return matching profile.

    Returns `None` if either DMI file is missing or unreadable, or if
    `board_profiles.find_profile` returns no match. Never raises; an
    absent or permission-restricted DMI just produces a `None` result
    so callers can keep working with defaults.
    """

    root = dmi_root if dmi_root is not None else DEFAULT_DMI_ROOT
    try:
        vendor = (root / "board_vendor").read_text(encoding="utf-8").strip()
        product = (root / "board_name").read_text(encoding="utf-8").strip()
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        return None

    return find_profile(vendor, product)


def _apply_detected_board(config: Config, dmi_root: Path | None) -> Config:
    """Merge auto-detected labels into `config`; user labels win on conflict.

    Sets `Config.detected_board` to `"<vendor> <product>"` of the matched
    profile, or leaves it `None` when no match. The merge is
    `{**profile.labels, **config.labels}` so any user-provided key
    overrides the auto-detected default for the same raw label.
    """

    profile = detect_board(dmi_root)
    if profile is None:
        return config

    merged_labels: dict[str, str] = {**profile.labels, **config.labels}
    return Config(
        refresh_seconds=config.refresh_seconds,
        theme=config.theme,
        labels=merged_labels,
        thresholds=config.thresholds,
        tmux_layout=config.tmux_layout,
        detected_board=f"{profile.vendor} {profile.product}",
    )


def load(path: Path | None = None, dmi_root: Path | None = None) -> Config:
    """Load and validate config from `path`, with auto-detected board labels merged.

    Missing config file: return defaults plus any auto-detected labels.
    Malformed TOML: raise `ValueError` with the parser message.
    Partial config: merge user keys over defaults, then merge user labels
    over auto-detected labels (user always wins on label conflicts).

    `dmi_root` is an injectable override for the DMI sysfs root; tests
    pass `tmp_path` here. Production code calls `load()` with no
    arguments and gets the real `/sys/devices/virtual/dmi/id`.
    """

    target = path or default_config_path()
    if not target.exists():
        return _apply_detected_board(Config(), dmi_root)

    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"invalid TOML in {target}: {exc}") from exc

    return _apply_detected_board(_from_raw(raw), dmi_root)


def _from_raw(raw: dict[str, Any]) -> Config:
    general = raw.get("general", {})
    labels = dict(raw.get("labels", {}))

    thresholds: dict[str, ThresholdSet] = dict(_DEFAULT_THRESHOLDS)
    for category, entry in raw.get("thresholds", {}).items():
        if not isinstance(entry, dict):
            continue
        warn = float(
            entry.get("warn", thresholds[category].warn if category in thresholds else 0.0)
        )
        crit = float(
            entry.get("crit", thresholds[category].crit if category in thresholds else 0.0)
        )
        thresholds[category] = ThresholdSet(category=category, warn=warn, crit=crit)

    tmux = raw.get("tmux", {})

    return Config(
        refresh_seconds=float(general.get("refresh_seconds", DEFAULT_REFRESH_SECONDS)),
        theme=str(general.get("theme", DEFAULT_THEME)),
        labels={str(k): str(v) for k, v in labels.items()},
        thresholds=thresholds,
        tmux_layout=str(tmux.get("layout", "3-pane")),
    )
