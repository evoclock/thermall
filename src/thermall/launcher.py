# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Installer for desktop integration (launcher, icon)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

DESKTOP_TEMPLATE = """[Desktop Entry]
Type=Application
Version=1.0
Name=thermall
GenericName=Cooling Dashboard
Comment=Terminal UI for cooling-system observability (fans, temps, GPUs, NVMe)
Exec={exec_line}
Icon=thermall
Terminal=true
Categories=System;Monitor;HardwareSettings;Utility;
Keywords=temperature;fan;cooling;monitor;hardware;sensors;nct6775;nvidia-smi;
StartupNotify=false
"""

DESKTOP_FILENAME = "thermall.desktop"
ICON_BASENAME = "thermall"

# PNG sizes shipped under `src/thermall/icons/<size>x<size>/thermall.png`.
# Installed to `~/.local/share/icons/hicolor/<size>x<size>/apps/thermall.png`
# per the freedesktop icon-theme spec. Desktop environments pick the
# best-matching size automatically; we ship a wide set so dock /
# launcher / file-manager / task-switcher all have a clean source.
PNG_ICON_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256, 512)

# Scalable SVG variant — transparent source, used by DEs that prefer
# vector icons (most modern Linux desktops do).
SVG_ICON_NAME = "thermall.svg"


def xdg_data_home() -> Path:
    """Return the XDG data home directory, respecting $XDG_DATA_HOME.

    Defaults to ~/.local/share if not set.
    """
    home = os.environ.get("XDG_DATA_HOME")
    if home:
        return Path(home)
    return Path.home() / ".local" / "share"


def desktop_file_content(exec_path: str | None) -> str:
    """Return the desktop file content with the appropriate Exec line.

    Args:
        exec_path: If provided, use this as the Exec command path.
                   If None, use 'thermall' as the default.

    Returns:
        The desktop file content as a string.
    """
    exec_line = _desktop_exec_command(exec_path)
    return DESKTOP_TEMPLATE.format(exec_line=exec_line)


def _desktop_exec_command(exec_path: str | None) -> str:
    """Return a Desktop Entry Specification-safe Exec command."""
    if not exec_path:
        return "thermall"

    escaped = (
        exec_path.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    )
    if any(char.isspace() for char in escaped):
        return f'"{escaped}"'
    return escaped


def _get_package_path() -> Path:
    """Return the directory that holds the bundled icon source.

    The icon assets ship inside `src/thermall/icons/` so they are
    included in wheel builds (the `packaging/` directory at the repo
    root is development-only and not shipped when installed via
    uv tool, pipx, or pip).
    """

    return Path(__file__).resolve().parent


def _write_file_atomic(path: Path, content: bytes | str) -> None:
    """Write content to a file atomically (write to tmp, rename)."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    if isinstance(content, bytes):
        tmp_path.write_bytes(content)
    else:
        tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def _copy_file_idempotent(src: Path, dst: Path, *, binary: bool) -> bool:
    """Copy src -> dst only if content differs. Returns True if anything written."""
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if binary:
            if src.read_bytes() == dst.read_bytes():
                return False
        elif src.read_text(encoding="utf-8") == dst.read_text(encoding="utf-8"):
            return False
    if binary:
        _write_file_atomic(dst, src.read_bytes())
    else:
        _write_file_atomic(dst, src.read_text(encoding="utf-8"))
    return True


def _run_optional_command(cmd: str, args: list[str], logger: logging.Logger) -> None:
    """Run an optional command if available; log and skip silently if not."""
    if shutil.which(cmd) is None:
        logger.info(f"Skipping {cmd}: not found on PATH")
        return
    try:
        subprocess.run([cmd, *args], check=False, capture_output=True)
    except Exception as e:
        logger.warning(f"{cmd} failed: {e}")


def _iter_icon_targets(data_home: Path) -> list[tuple[Path, Path, bool]]:
    """Yield (source, destination, is_binary) for every icon variant.

    Sources live under `<package>/icons/`; destinations under
    `<data_home>/icons/hicolor/<N>x<N>/apps/`. Only PNG sizes are
    installed; the bundled SVG is the *source* mark (kept inside the
    package for README and design re-use) but is deliberately NOT
    installed to `hicolor/scalable/apps/` because most desktop
    environments prefer SVG when both are present, and the polished
    rounded-background PNG icon would never get rendered.
    """

    package_icons = _get_package_path() / "icons"
    hicolor = data_home / "icons" / "hicolor"

    targets: list[tuple[Path, Path, bool]] = []
    for size in PNG_ICON_SIZES:
        src = package_icons / f"{size}x{size}" / f"{ICON_BASENAME}.png"
        dst = hicolor / f"{size}x{size}" / "apps" / f"{ICON_BASENAME}.png"
        targets.append((src, dst, True))

    return targets


def install(exec_path: str | None, uninstall: bool, root_path: Path | None = None) -> int:
    """Install or uninstall the desktop launcher and icons.

    Args:
        exec_path: If provided, write this path into Exec= line.
        uninstall: If True, remove installed files instead of installing.
        root_path: Override for testing. If None, use real XDG_DATA_HOME.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    logger = logging.getLogger(__name__)

    data_home = xdg_data_home() if root_path is None else root_path

    apps_dir = data_home / "applications"
    icons_hicolor = data_home / "icons" / "hicolor"

    desktop_path = apps_dir / DESKTOP_FILENAME
    icon_targets = _iter_icon_targets(data_home)

    def log(msg: str) -> None:
        logger.info(msg)

    if uninstall:
        # Uninstall: remove files idempotently
        removed_any = False
        if desktop_path.exists():
            desktop_path.unlink()
            removed_any = True
        for _src, dst, _binary in icon_targets:
            if dst.exists():
                dst.unlink()
                removed_any = True

        # Legacy cleanup: older versions installed a scalable SVG that
        # we no longer ship. Remove it if present so the desktop stops
        # preferring it over the polished rounded-PNG icon variants.
        legacy_svg = icons_hicolor / "scalable" / "apps" / SVG_ICON_NAME
        if legacy_svg.exists():
            legacy_svg.unlink()
            removed_any = True

        # Re-run database updaters if we removed anything
        if removed_any:
            _run_optional_command("update-desktop-database", [str(apps_dir)], logger)
            _run_optional_command("gtk-update-icon-cache", ["-f", "-t", str(icons_hicolor)], logger)

        log("Desktop integration removed.")
        return 0

    # Install: create directories and write files
    apps_dir.mkdir(parents=True, exist_ok=True)

    # Desktop file
    if desktop_path.exists():
        existing_content = desktop_path.read_text(encoding="utf-8")
        new_content = desktop_file_content(exec_path)
        if existing_content != new_content:
            _write_file_atomic(desktop_path, new_content)
    else:
        _write_file_atomic(desktop_path, desktop_file_content(exec_path))

    # Icon variants
    installed_count = 0
    for src, dst, binary in icon_targets:
        if not src.exists():
            log(f"Skipping {src.relative_to(_get_package_path())} (source missing)")
            continue
        if _copy_file_idempotent(src, dst, binary=binary):
            installed_count += 1
        log(f"  -> {dst}")

    # Run optional database updaters
    _run_optional_command("update-desktop-database", [str(apps_dir)], logger)
    _run_optional_command("gtk-update-icon-cache", ["-f", "-t", str(icons_hicolor)], logger)

    log(f"Desktop file installed at {desktop_path}")
    log(f"Installed {installed_count} icon variants under {icons_hicolor}")
    return 0
