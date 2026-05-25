# Changelog

All notable changes to thermall live here.

## 0.1.1 (2026-05-24)

First public release candidate. Functionally complete v1 surface.

### Added
- **Settings modal** (`s`): refresh interval (1/2/5/10 s), help-card
  reset, advanced docs. Composited pixel-art animation at the top
  when terminal >= 130x38; controls-only on smaller terminals so the
  Close button stays reachable without scroll.
- **Help overlay modal** (`h`): keybindings + per-panel guide +
  minimize behaviour + pointer to the README. Dismiss with Esc.
- **Minimize mode** (`m`): hides per-sensor detail rows + stopped
  fans, keeps panel headers + braille charts + spinning fans
  visible, expands the charts to 3x normal height to use the freed
  vertical space.
- **MinSizeHint**: btop-style "terminal too small" hint with live
  current/required dimensions when terminal < 90x28.
- **First-run wizard**: Accept / Skip / Edit flow for the auto-
  detected board profile + thresholds, runs on first launch when
  no config exists.
- **3x2 panel grid**: CPU + VRM + Fans + Storage take 1x1 cells in
  the left two columns; GpuPanel spans both rows in the third
  column so multi-GPU setups have vertical room.
- **Auto-detect motherboard** + friendly labels via the
  `board_profiles.py` registry. Ships with a B550-F profile;
  community contributions follow the same pattern.
- **Desktop launcher** (`thermall install-launcher`): writes a
  `.desktop` entry + 8 PNG icon sizes (16/24/32/48/64/128/256/512)
  to the freedesktop hicolor tree. Idempotent install + uninstall.
- **NVMe SMART helper** (`thermall install-nvme-helper`): hardened
  systemd timer for live SMART telemetry without granting
  `CAP_SYS_ADMIN` to the `nvme` binary itself.
- **CI** (GitHub Actions): ruff lint + format + mypy + pytest with
  >=80% coverage on Python 3.11 and 3.12.
- **Release workflow**: tag-triggered (`v*.*.*`) PyPI publish via
  Trusted Publishing (OIDC; no API token in repo secrets).

### Architecture decisions
- 5 panels, no animation in the dashboard body (running a 24/7
  animation on a cooling-monitoring tool would be poor optics).
  Animation lives only in the settings modal.
- ThresholdLabel widgets + braille charts re-render with the active
  theme on `t`-key press.
- VRM panel is *advisory*; does not drive the overall warm/critical
  verdict in StatusHeader. Per the user's note that VRM runs hot
  almost continuously on Nuvoton boards.
- smartd false-positives ("Can't monitor", "SMART Usage Attribute")
  are demoted from CRIT to informational in the collector.

### Install
```bash
pipx install --python python3.11 git+https://github.com/evoclock/thermall.git
thermall install-launcher
```

## 0.1.0 (2026-04-XX)

Initial scaffold and feature implementation. Internal milestones
collapsed into the 0.1.1 changelog above for the first public release.
