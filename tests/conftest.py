# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Shared test fixtures and helpers.

Fixture files live in `tests/fixtures/`. Each fixture is a sanitised
capture of real tooling output (`sensors -j`, `nvidia-smi --query-gpu`,
`nvme smart-log`). Tests requesting a fixture get the file contents as a
string. If the requested fixture does not exist, the test is skipped with
a clear message pointing at thermall task #9 (capture fixtures).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_loader() -> Callable[[str], str]:
    """Return a callable `load(name) -> str` that reads `tests/fixtures/<name>`.

    Tests should call `fixture_loader("sensors_output.json")` and gracefully
    `pytest.skip` if the file is missing.
    """

    def load(name: str) -> str:
        path = FIXTURES_DIR / name
        if not path.exists():
            pytest.skip(
                f"fixture {name!r} missing; capture per thermall task #9 to enable this test"
            )
        return path.read_text(encoding="utf-8")

    return load
