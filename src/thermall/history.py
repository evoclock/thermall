# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Per-reading temperature history for the dashboard's chart panels.

`HistoryStore` is a bounded ring buffer per sensor label; the dashboard
records every collected reading on every refresh tick, and panels read
back a window of recent samples for the BrailleChart widget.

Storage is intentionally in-memory only. Persistence to disk is a
future task; v1 charts reset to empty on every dashboard launch.
"""

from __future__ import annotations

from collections import deque
from typing import Final

DEFAULT_MAX_SAMPLES: Final[int] = 60
"""Default history depth. 60 samples at 2 s refresh = 2 min of history."""


class HistoryStore:
    """Bounded per-label ring buffer of sensor values.

    One independent buffer per `label`. Each `record()` appends; once the
    buffer hits `max_samples` the oldest sample is dropped. `get()`
    returns a tuple snapshot (defensive copy) of the current buffer.

    Not thread-safe; the dashboard refresh loop is single-threaded.
    """

    def __init__(self, max_samples: int = DEFAULT_MAX_SAMPLES) -> None:
        if max_samples < 1:
            raise ValueError(f"max_samples must be >= 1, got {max_samples}")
        self._max = max_samples
        self._buf: dict[str, deque[float]] = {}

    @property
    def max_samples(self) -> int:
        return self._max

    def record(self, label: str, value: float) -> None:
        """Append `value` to the buffer for `label`, evicting if at cap."""

        if label not in self._buf:
            self._buf[label] = deque(maxlen=self._max)
        self._buf[label].append(value)

    def get(self, label: str) -> tuple[float, ...]:
        """Snapshot the current samples for `label`; empty tuple if none."""

        return tuple(self._buf.get(label, ()))

    def labels(self) -> tuple[str, ...]:
        """Every label that has at least one recorded sample."""

        return tuple(self._buf.keys())

    def clear(self) -> None:
        """Drop all history. Used when the user explicitly resets."""

        self._buf.clear()
