# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for launcher module."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from thermall.launcher import desktop_file_content, install, xdg_data_home


class TestDesktopFileContent:
    """Tests for desktop_file_content pure function."""

    def test_default_exec(self) -> None:
        """Content has Exec=thermall when no exec path provided."""
        content = desktop_file_content(None)
        assert "Exec=thermall" in content

    def test_with_explicit_path(self) -> None:
        """Content has Exec=/usr/local/bin/thermall when path provided."""
        content = desktop_file_content("/usr/local/bin/thermall")
        assert "Exec=/usr/local/bin/thermall" in content

    def test_with_exec_containing_spaces(self) -> None:
        """Exec path with spaces is quoted for the Desktop Entry Specification."""
        content = desktop_file_content("/usr/local/bin/thermall app")
        assert 'Exec="/usr/local/bin/thermall app"' in content

    def test_with_exec_containing_special_chars(self) -> None:
        """Exec path escapes special command-line characters."""
        content = desktop_file_content('/opt/thermal"app$/thermall')
        assert 'Exec=/opt/thermal\\"app\\$/thermall' in content


class TestXdgDataHome:
    """Tests for xdg_data_home pure function."""

    def test_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Defaults to ~/.local/share when XDG_DATA_HOME not set."""
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        result = xdg_data_home()
        expected = Path.home() / ".local" / "share"
        assert result == expected

    def test_respects_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Respects $XDG_DATA_HOME when set."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        result = xdg_data_home()
        assert result == tmp_path


class TestInstall:
    """Tests for install function."""

    def test_install_writes_both_files(self, tmp_path: Path) -> None:
        """Install writes the desktop file and at least one icon PNG."""
        result = install(exec_path=None, uninstall=False, root_path=tmp_path)
        assert result == 0

        desktop_file = tmp_path / "applications" / "thermall.desktop"
        # Pick any size; the canonical desktop-launcher size on most DEs.
        icon_file = tmp_path / "icons" / "hicolor" / "48x48" / "apps" / "thermall.png"

        assert desktop_file.exists()
        assert icon_file.exists()
        assert "Exec=thermall" in desktop_file.read_text()

    def test_install_with_exec_path(self, tmp_path: Path) -> None:
        """Install with explicit exec path writes correct Exec line."""
        install(exec_path="/custom/path/thermall", uninstall=False, root_path=tmp_path)

        desktop_file = tmp_path / "applications" / "thermall.desktop"
        assert "Exec=/custom/path/thermall" in desktop_file.read_text()

    def test_install_then_install_is_idempotent(self, tmp_path: Path) -> None:
        """Second install call leaves content unchanged."""
        install(exec_path=None, uninstall=False, root_path=tmp_path)

        desktop_file = tmp_path / "applications" / "thermall.desktop"
        first_content = desktop_file.read_text()

        install(exec_path=None, uninstall=False, root_path=tmp_path)
        second_content = desktop_file.read_text()

        assert first_content == second_content

    def test_uninstall_removes_both_files(self, tmp_path: Path) -> None:
        """Uninstall removes the desktop file and the installed icon PNGs."""
        install(exec_path=None, uninstall=False, root_path=tmp_path)
        result = install(exec_path=None, uninstall=True, root_path=tmp_path)
        assert result == 0

        desktop_file = tmp_path / "applications" / "thermall.desktop"
        icon_file = tmp_path / "icons" / "hicolor" / "48x48" / "apps" / "thermall.png"

        assert not desktop_file.exists()
        assert not icon_file.exists()

    def test_uninstall_when_already_uninstalled_is_idempotent(self, tmp_path: Path) -> None:
        """Uninstall when nothing is installed exits 0."""
        result = install(exec_path=None, uninstall=True, root_path=tmp_path)
        assert result == 0

    def test_skips_update_desktop_database_if_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Silently skips update-desktop-database when not found."""
        # Mock shutil.which to return None for the updater commands
        original_which = shutil.which

        def mock_which(cmd: str) -> str | None:
            if cmd in ("update-desktop-database", "gtk-update-icon-cache"):
                return None
            return original_which(cmd)

        monkeypatch.setattr(shutil, "which", mock_which)

        # Should not raise, just skip
        result = install(exec_path=None, uninstall=False, root_path=tmp_path)
        assert result == 0

    def test_install_creates_intermediate_directories_if_missing(self, tmp_path: Path) -> None:
        """Install creates intermediate directories when missing."""
        # Ensure parent directories don't exist
        apps_dir = tmp_path / "applications"
        icons_dir = tmp_path / "icons" / "hicolor" / "48x48" / "apps"
        assert not apps_dir.exists()
        assert not icons_dir.exists()

        result = install(exec_path=None, uninstall=False, root_path=tmp_path)
        assert result == 0
        assert apps_dir.exists()
        assert icons_dir.exists()

    def test_install_with_exec_containing_spaces_escapes_correctly(self, tmp_path: Path) -> None:
        """Install with exec path containing spaces handles correctly."""
        result = install(
            exec_path="/usr/local/bin/thermal app", uninstall=False, root_path=tmp_path
        )
        assert result == 0

        desktop_file = tmp_path / "applications" / "thermall.desktop"
        content = desktop_file.read_text()
        assert 'Exec="/usr/local/bin/thermal app"' in content


class TestInstallIntegration:
    """Integration tests that exercise real file operations."""

    def test_install_actual_filesystem(self, tmp_path: Path) -> None:
        """Full integration: install and verify files on real filesystem."""
        result = install(exec_path=None, uninstall=False, root_path=tmp_path)
        assert result == 0

        # Verify desktop file structure
        desktop_file = tmp_path / "applications" / "thermall.desktop"
        content = desktop_file.read_text()
        assert "[Desktop Entry]" in content
        assert "Type=Application" in content
        assert "Name=thermall" in content
        assert "Terminal=true" in content

        # Verify at least one icon PNG landed under hicolor and is a
        # real PNG (signature bytes), not an empty stub.
        png = tmp_path / "icons" / "hicolor" / "256x256" / "apps" / "thermall.png"
        assert png.exists()
        assert png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


class TestMultiSizeIcons:
    """Tests for the multi-size PNG icon install path."""

    def test_install_writes_all_png_sizes(self, tmp_path: Path) -> None:
        """Install copies every shipped PNG size to the matching hicolor dir."""

        from thermall.launcher import PNG_ICON_SIZES

        install(exec_path=None, uninstall=False, root_path=tmp_path)
        hicolor = tmp_path / "icons" / "hicolor"
        for size in PNG_ICON_SIZES:
            png = hicolor / f"{size}x{size}" / "apps" / "thermall.png"
            assert png.exists(), f"{size}x{size} PNG not installed"
            # Sanity: file is a real PNG, not a 0-byte stub
            assert png.stat().st_size > 200, f"{size}x{size} PNG suspiciously small"

    def test_install_does_not_write_svg_to_scalable(self, tmp_path: Path) -> None:
        """The SVG ships in the package but is NOT installed to hicolor.

        Reason: desktop environments prefer SVG over PNG when both are
        present in the icon theme. The pixel-art SVG looks worse than
        the polished rounded-background PNGs, so we install PNGs only
        and let the DE pick the closest size.
        """

        install(exec_path=None, uninstall=False, root_path=tmp_path)
        svg = tmp_path / "icons" / "hicolor" / "scalable" / "apps" / "thermall.svg"
        assert not svg.exists()

    def test_uninstall_removes_all_sizes(self, tmp_path: Path) -> None:
        from thermall.launcher import PNG_ICON_SIZES

        install(exec_path=None, uninstall=False, root_path=tmp_path)
        install(exec_path=None, uninstall=True, root_path=tmp_path)
        hicolor = tmp_path / "icons" / "hicolor"
        for size in PNG_ICON_SIZES:
            png = hicolor / f"{size}x{size}" / "apps" / "thermall.png"
            assert not png.exists()

    def test_idempotent_install_does_not_rewrite_unchanged_files(self, tmp_path: Path) -> None:
        """Second install with identical sources shouldn't bump mtimes."""

        install(exec_path=None, uninstall=False, root_path=tmp_path)
        png = tmp_path / "icons" / "hicolor" / "256x256" / "apps" / "thermall.png"
        first_mtime = png.stat().st_mtime_ns
        install(exec_path=None, uninstall=False, root_path=tmp_path)
        assert png.stat().st_mtime_ns == first_mtime
