# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Command-line entry point for thermall.

Parses `argv`, loads config, launches the Textual dashboard. When stdout
is not a TTY (running under pytest, piped, redirected) the CLI falls back
to printing a scaffold summary instead so callers in non-interactive
contexts get usable output.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from thermall import __version__
from thermall.config import Config, default_config_path, load
from thermall.dashboard import run as run_dashboard
from thermall.screens import show_if_no_config

# Configure basic logging for install subcommands (messages go to stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thermall",
        description=(
            "Terminal UI dashboard for cooling-system observability on Linux. "
            "Shows fan RPMs, motherboard sensors, CPU/GPU/NVMe temperatures, "
            "and threshold-graded warnings in one screen."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"thermall {__version__}",
    )
    parser.add_argument(
        "--refresh",
        type=float,
        default=None,
        metavar="SECONDS",
        help="refresh interval in seconds (overrides config)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help=f"path to config TOML (default: {default_config_path()})",
    )
    parser.add_argument(
        "--tmux",
        action="store_true",
        help="launch in tmux composition mode (btop + nvtop + thermall)",
    )
    parser.add_argument(
        "--show-config-path",
        action="store_true",
        help="print the resolved config path and exit",
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="available subcommands")

    install_launcher_parser = subparsers.add_parser(
        "install-launcher",
        help="install .desktop file and icon for desktop integration",
        description=(
            "Installs a .desktop file to ~/.local/share/applications/ and copies "
            "the icon to ~/.local/share/icons/hicolor/scalable/apps/ so thermall "
            "appears in your desktop environment's application menu."
        ),
    )
    install_launcher_parser.add_argument(
        "--exec",
        type=str,
        default=None,
        metavar="PATH",
        help="path to thermall executable (default: use 'thermall' on PATH)",
    )
    install_launcher_parser.add_argument(
        "--uninstall",
        action="store_true",
        help="remove installed desktop files instead of installing",
    )

    nvme_helper = subparsers.add_parser(
        "install-nvme-helper",
        help="install the root-owned NVMe SMART polling systemd timer",
        description=(
            "Installs or removes the hardened systemd service and timer that poll "
            "NVMe SMART data into /run/thermall/nvme.json. This command writes to "
            "/usr/local/libexec and /etc/systemd/system, so run it with sudo."
        ),
    )
    nvme_helper.add_argument(
        "--uninstall",
        action="store_true",
        help="remove the installed helper, service, and timer",
    )
    nvme_helper.add_argument(
        "--dry-run",
        action="store_true",
        help="print the changes that would be made without writing files",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == "install-launcher":
        # Import here to avoid circular imports
        from thermall.launcher import install as install_launcher

        return install_launcher(exec_path=args.exec, uninstall=args.uninstall)

    if args.subcommand == "install-nvme-helper":
        from thermall.nvme_helper_install import install as install_nvme_helper

        return install_nvme_helper(uninstall=args.uninstall, dry_run=args.dry_run)

    if args.show_config_path:
        print(default_config_path())
        return 0

    config = load(args.config)
    if args.refresh is not None:
        config = _override_refresh(config, args.refresh)

    # After loading config, check if first-run wizard should show
    if show_if_no_config(config):
        # First run: dashboard will push FirstRunScreen on top
        # The screen will save config and pop itself when done
        pass

    if args.tmux:
        print("thermall: tmux composition mode not yet implemented", file=sys.stderr)
        return 2

    if not sys.stdout.isatty():
        # Non-interactive context (pytest, pipe, redirect): print a summary
        # rather than trying to launch the Textual app, which would block on
        # a terminal that isn't there.
        print(f"thermall {__version__} (scaffold)")
        print(f"refresh: {config.refresh_seconds}s; theme: {config.theme}")
        print(f"thresholds: {sorted(config.thresholds)}")
        print("dashboard panels not yet populated; stdout is not a TTY")
        return 0

    return run_dashboard(config, show_wizard=show_if_no_config(config))


def _override_refresh(config: Config, refresh: float) -> Config:
    return Config(
        refresh_seconds=refresh,
        theme=config.theme,
        labels=config.labels,
        thresholds=config.thresholds,
        tmux_layout=config.tmux_layout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
