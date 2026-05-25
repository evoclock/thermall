# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for the composited animated `SettingsAnimation` widget.

Verbatim port of the ChatGPT-generated prototype script the user
pasted on 2026-05-23: three sprite stacks (fan / wind / thermometer)
composited onto a 64x18 canvas, three frames cycled at ~7 Hz.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from thermall.widgets.settings_animation import (
    _CANVAS_HEIGHT,
    _CANVAS_WIDTH,
    _FAN_FRAMES,
    _FRAME_COUNT,
    _PALETTE,
    _THERMOMETER_FRAMES,
    _WIND_FRAMES,
    SettingsAnimation,
    _build_frame,
    _overlay,
    _render_frame,
)


class _Host(App[None]):
    def __init__(self, anim: SettingsAnimation) -> None:
        super().__init__()
        self._anim = anim

    def compose(self) -> ComposeResult:
        yield self._anim


class TestFrameAssets:
    def test_three_frames_per_sprite_stack(self) -> None:
        assert _FRAME_COUNT == 3
        assert len(_FAN_FRAMES) == _FRAME_COUNT
        assert len(_WIND_FRAMES) == _FRAME_COUNT
        assert len(_THERMOMETER_FRAMES) == _FRAME_COUNT

    def test_fan_sprites_are_22_wide_13_tall(self) -> None:
        for idx, frame in enumerate(_FAN_FRAMES):
            assert len(frame) == 13, f"fan frame {idx} height {len(frame)} != 13"
            assert len(frame[0]) == 22, f"fan frame {idx} width {len(frame[0])} != 22"

    def test_wind_sprites_are_11_wide_3_tall(self) -> None:
        for idx, frame in enumerate(_WIND_FRAMES):
            assert len(frame) == 3, f"wind frame {idx} height {len(frame)} != 3"
            assert len(frame[0]) == 11, f"wind frame {idx} width {len(frame[0])} != 11"

    def test_thermometer_sprites_are_7_wide_10_tall(self) -> None:
        for idx, frame in enumerate(_THERMOMETER_FRAMES):
            assert len(frame) == 10, f"thermo frame {idx} height {len(frame)} != 10"
            assert len(frame[0]) == 7, f"thermo frame {idx} width {len(frame[0])} != 7"

    def test_palette_covers_every_symbol_used_in_sprites(self) -> None:
        used: set[str] = set()
        for stack in (_FAN_FRAMES, _WIND_FRAMES, _THERMOMETER_FRAMES):
            for frame in stack:
                for row in frame:
                    used.update(row)
        missing = used - set(_PALETTE.keys())
        assert not missing, f"sprites use symbols absent from palette: {missing}"


class TestOverlay:
    def test_dots_are_transparent(self) -> None:
        canvas = ["....."] * 3
        sprite = ("XYZ",)
        result = _overlay(canvas, sprite, row_offset=1, col_offset=1)
        assert result[1] == ".XYZ."

    def test_overlay_does_not_paint_through_dots(self) -> None:
        canvas = ["KKKKK"] * 3
        # The sprite's dot positions must NOT overwrite the canvas's K.
        sprite = (".X.",)
        result = _overlay(canvas, sprite, row_offset=1, col_offset=1)
        assert result[1] == "KKXKK"

    def test_overlay_out_of_bounds_rows_ignored(self) -> None:
        canvas = ["..."] * 2
        # Row offset puts the sprite below the canvas — should not raise.
        sprite = ("XXX",)
        result = _overlay(canvas, sprite, row_offset=5, col_offset=0)
        assert result == ["..."] * 2

    def test_overlay_out_of_bounds_cols_ignored(self) -> None:
        canvas = ["..."] * 1
        sprite = ("XXXXX",)
        result = _overlay(canvas, sprite, row_offset=0, col_offset=1)
        # Only the cols that fit get painted; X at col 1 and col 2.
        assert result[0] == ".XX"


class TestBuildFrame:
    def test_canvas_dimensions(self) -> None:
        for idx in range(_FRAME_COUNT):
            frame = _build_frame(idx)
            assert len(frame) == _CANVAS_HEIGHT
            assert all(len(row) == _CANVAS_WIDTH for row in frame)

    def test_frames_differ(self) -> None:
        # All three composited frames must be distinct or the
        # animation is invisible.
        rendered = [tuple(_build_frame(i)) for i in range(_FRAME_COUNT)]
        assert rendered[0] != rendered[1]
        assert rendered[1] != rendered[2]
        assert rendered[0] != rendered[2]

    def test_fan_pixels_land_at_top_left_region(self) -> None:
        # Fan offset is (2, 0). Row 2 col 7 should be K in frame 0
        # (first K of the topmost "KKKKKKKK" line).
        frame = _build_frame(0)
        assert frame[3][7] == "K"

    def test_thermometer_pixels_land_at_right_region(self) -> None:
        # Thermometer offset is (4, 49). Bottom row of the thermometer
        # (".KKKKK.") lands at canvas row 13, col 49.
        frame = _build_frame(0)
        assert frame[13][50] == "K"


class TestRenderFrame:
    def test_emits_each_active_palette_hex(self) -> None:
        rendered = _render_frame(_build_frame(2))
        for symbol, hex_value in _PALETTE.items():
            if hex_value is None or symbol == "B":
                # B never appears in the user's sprites; skip.
                continue
            assert f"#{hex_value}" in rendered, f"missing colour {symbol} -> #{hex_value}"

    def test_uses_two_space_cells(self) -> None:
        rendered = _render_frame(_build_frame(0))
        assert "]  [/]" in rendered

    def test_newline_per_row_except_last(self) -> None:
        rendered = _render_frame(_build_frame(0))
        assert rendered.count("\n") == _CANVAS_HEIGHT - 1

    def test_all_dots_row_produces_no_background_markup(self) -> None:
        all_dots = ["." * _CANVAS_WIDTH]
        rendered = _render_frame(all_dots)
        assert "[on #" not in rendered


class TestAnimationControl:
    def test_starts_at_frame_zero(self) -> None:
        assert SettingsAnimation().frame == 0

    def test_advance_cycles_modularly(self) -> None:
        anim = SettingsAnimation()
        seen = {anim.frame}
        for _ in range(_FRAME_COUNT):
            anim._advance()
            seen.add(anim.frame)
        assert seen == set(range(_FRAME_COUNT))
        assert anim.frame == 0


class TestMounting:
    @pytest.mark.asyncio
    async def test_mounts_and_starts_timer(self) -> None:
        anim = SettingsAnimation()
        app = _Host(anim)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert anim.is_mounted
            assert anim._timer is not None

    @pytest.mark.asyncio
    async def test_advance_updates_rendered_content(self) -> None:
        anim = SettingsAnimation()
        app = _Host(anim)
        async with app.run_test() as pilot:
            await pilot.pause()
            before = str(anim.content)
            anim._advance()
            await pilot.pause()
            after = str(anim.content)
            assert before != after

    @pytest.mark.asyncio
    async def test_unmount_stops_timer(self) -> None:
        anim = SettingsAnimation()
        app = _Host(anim)
        async with app.run_test() as pilot:
            await pilot.pause()
            await anim.remove()
            await pilot.pause()
            assert anim._timer is None
