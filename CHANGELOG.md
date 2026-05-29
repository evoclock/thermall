# Changelog

All notable changes to thermall live here.

## 0.1.2 (2026-05-29)

### Changed

- **Licence changed from MIT to GNU Affero General Public License v3
  (AGPLv3) plus a Section 7(b) author-attribution clause.** AGPLv3 is
  OSI-approved and delivers a structural source-disclosure obligation
  for any conveyance or network-exposed deployment; the §7(b)
  additional term preserves author attribution explicitly. Both
  obligations are waived under a commercial licence, available for
  for-profit entities and any use in a paid product or service. Same
  pattern landed across the evoclock product line during the licence
  consolidation pass; see README for the plain-English version.
- `pyproject.toml`: licence field updated to `{ file = "LICENSE" }`;
  PyPI classifier added (`License :: OSI Approved :: GNU Affero
  General Public License v3 or later (AGPLv3+)`); project URLs
  corrected from `jgamboa/thermall` to `evoclock/thermall`.
- `LICENSE` now contains: a project preamble identifying the work and
  pointing at the §7(b) additional terms, the verbatim FSF AGPLv3
  text, the Section 7(b) additional terms requiring author
  attribution preservation in source headers and user-facing primary
  documentation, and a Commercial Licence Option notice pointing to
  a forthcoming `COMMERCIAL.md`.
- SPDX headers across 63 source / test / doc / script files updated
  from `MIT` to `AGPL-3.0-or-later`.
- README licence section rewritten with plain-English guidance
  distinguishing open-source adoption from commercial adoption; CI,
  licence, and Python-version badges added at the top.
- README installation instructions updated to use `sfw uv tool
  install` instead of `pipx install`, consistent with the project's
  package-install discipline.
- README acknowledgements section updated to drop named model
  identifiers; Claude Code and Hermes are now described as
  "spec-driven agents executing implementation tasks under that
  direction" rather than as "planning collaborators".
- `docs/design_rationale.md`: two internal phrasings revised
  (cosmetic, no behavioural impact); supply-chain paragraph updated
  to reflect the `sfw uv tool install` flow.

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
- **Release workflow**: tag-triggered (`v*.*.*`) build sanity check;
  wheel + sdist uploaded as workflow artifacts. Distribution is via
  GitHub install, not PyPI.

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
sfw uv tool install --python python3.11 "thermall @ git+https://github.com/evoclock/thermall.git"
thermall install-launcher
```

## 0.1.0 (2026-04-XX)

Initial scaffold and feature implementation. Internal milestones
collapsed into the 0.1.1 changelog above for the first public release.
