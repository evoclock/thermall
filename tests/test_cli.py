# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the CLI surface."""

from __future__ import annotations

import pytest

from thermall.cli import build_parser, main


class TestParser:
    def test_version_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["--version"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "thermall " in out

    def test_default_args(self) -> None:
        args = build_parser().parse_args([])
        assert args.refresh is None
        assert args.config is None
        assert args.tmux is False

    def test_refresh_override(self) -> None:
        args = build_parser().parse_args(["--refresh", "5"])
        assert args.refresh == 5.0


class TestMain:
    def test_show_config_path_returns_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["--show-config-path"])
        assert rc == 0
        assert "thermall/config.toml" in capsys.readouterr().out

    def test_tmux_subcommand_not_implemented_returns_2(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main(["--tmux"])
        assert rc == 2
        assert "not yet implemented" in capsys.readouterr().err

    def test_default_in_non_tty_prints_scaffold_summary(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Under pytest, sys.stdout is not a TTY, so the CLI takes the
        # non-interactive branch and prints a summary instead of trying to
        # launch the Textual app.
        rc = main([])
        assert rc == 0
        out = capsys.readouterr().out
        assert "thermall" in out
        assert "scaffold" in out
        assert "not a TTY" in out
