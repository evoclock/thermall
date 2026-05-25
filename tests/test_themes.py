# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for thermall.themes."""

from __future__ import annotations

import pytest
from textual.theme import Theme

from thermall.themes import (
    ALL_THEMES,
    DEFAULT_THEME,
    THEME_CYCLE,
    THERMALL_DEFAULT,
    THERMALL_PACIFIC_NORTHWEST,
    next_theme_name,
)

EXPECTED_THEME_NAMES = {
    "thermall-default",
    "thermall-pacific-northwest",
    "thermall-clay-court",
    "thermall-power-station",
}


class TestThemeCycle:
    def test_default_is_first_in_cycle(self) -> None:
        assert THEME_CYCLE[0] == DEFAULT_THEME

    def test_default_is_thermall_default(self) -> None:
        # The curated default after the theme winnow.
        assert DEFAULT_THEME == "thermall-default"

    def test_cycle_has_four_themes(self) -> None:
        # Pin the count so a silent removal is caught by tests.
        assert len(THEME_CYCLE) == 4

    def test_cycle_contains_named_palettes(self) -> None:
        assert set(THEME_CYCLE) == EXPECTED_THEME_NAMES

    def test_cycle_entries_are_unique(self) -> None:
        assert len(set(THEME_CYCLE)) == len(THEME_CYCLE)

    def test_all_themes_match_cycle_order(self) -> None:
        # ALL_THEMES tuple defines the cycle; THEME_CYCLE is derived
        # from it.
        assert tuple(t.name for t in ALL_THEMES) == THEME_CYCLE


class TestNextThemeName:
    def test_each_step_advances(self) -> None:
        # Cycle order: default -> pacific-northwest -> clay-court ->
        # power-station -> default.
        assert next_theme_name("thermall-default") == "thermall-pacific-northwest"
        assert next_theme_name("thermall-pacific-northwest") == "thermall-clay-court"
        assert next_theme_name("thermall-clay-court") == "thermall-power-station"

    def test_last_wraps_to_first(self) -> None:
        last = THEME_CYCLE[-1]
        assert next_theme_name(last) == DEFAULT_THEME

    def test_unknown_theme_falls_back_to_default(self) -> None:
        assert next_theme_name("dracula") == DEFAULT_THEME

    def test_empty_string_falls_back_to_default(self) -> None:
        assert next_theme_name("") == DEFAULT_THEME

    @pytest.mark.parametrize("name", list(THEME_CYCLE))
    def test_round_trip_returns_to_start_after_full_cycle(self, name: str) -> None:
        current = name
        for _ in range(len(THEME_CYCLE)):
            current = next_theme_name(current)
        assert current == name

    def test_dropped_theme_names_fall_back_to_default(self) -> None:
        # Themes that existed in earlier iterations and have since
        # been dropped (or renamed) must not silently match the cycle
        # by name. Anyone holding a stale config gets the default.
        dropped = (
            "thermall-miami",
            "thermall-tron",
            "thermall-vhs-betamax",
            "thermall-classic-80s",
            "thermall-70s-brown",
            "thermall-pulp-art",
            "thermall-jukebox",
            "thermall-space-age",
        )
        for name in dropped:
            assert next_theme_name(name) == DEFAULT_THEME


class TestThemeStructure:
    @pytest.mark.parametrize("theme", list(ALL_THEMES))
    def test_required_colour_tokens_present(self, theme: Theme) -> None:
        for token in (
            "primary",
            "secondary",
            "accent",
            "success",
            "warning",
            "error",
            "foreground",
            "background",
            "surface",
            "panel",
        ):
            value = getattr(theme, token)
            assert isinstance(value, str)
            assert len(value) > 0, f"{theme.name}: empty {token}"

    @pytest.mark.parametrize("theme", list(ALL_THEMES))
    def test_theme_is_dark(self, theme: Theme) -> None:
        assert theme.dark is True, f"{theme.name} should be a dark theme"

    @pytest.mark.parametrize("theme", list(ALL_THEMES))
    def test_severity_colours_are_distinct(self, theme: Theme) -> None:
        # OK / WARN / CRIT must be three different colour values so
        # the ThresholdLabel and chart cells are visually distinct.
        severity_colours = {theme.success, theme.warning, theme.error}
        assert len(severity_colours) == 3, (
            f"{theme.name} reuses a colour across success/warning/error"
        )


class TestThermallDefault:
    """Default theme; explicit pin of its identity."""

    def test_name(self) -> None:
        assert THERMALL_DEFAULT.name == "thermall-default"

    def test_is_default(self) -> None:
        assert THERMALL_DEFAULT.name == DEFAULT_THEME


class TestThermallPacificNorthwest:
    def test_name(self) -> None:
        assert THERMALL_PACIFIC_NORTHWEST.name == "thermall-pacific-northwest"

    def test_background_darker_than_surface(self) -> None:
        bg_hex = THERMALL_PACIFIC_NORTHWEST.background
        surf_hex = THERMALL_PACIFIC_NORTHWEST.surface
        assert bg_hex is not None, "pacific-northwest theme must define background"
        assert surf_hex is not None, "pacific-northwest theme must define surface"
        bg = int(bg_hex.lstrip("#"), 16)
        surf = int(surf_hex.lstrip("#"), 16)
        assert bg < surf
