# thermall design rationale

Companion to `explainer_doc.md`. The explainer answers "what is
thermall and how does it work"; this document answers "why does it
look like this and not something simpler". Intended for people
evaluating, forking, or maintaining the project.

## The honest first question

A reasonable engineer looking at this codebase will ask: **isn't
this overkill for a tool that shows sensor numbers?** A shell
script wrapping `sensors`, `nvidia-smi`, and `nvme smart-log` with
`awk` for parsing and ANSI escape codes for colour could be
~200 lines. People ship those all the time. Why does thermall
have a 1000+ line source tree, six widgets, four collectors,
multiple convention docs, and 300+ tests?

The short answer: the bash version works for "monitor my own
machine, today, in the terminal I'm already in". thermall is built
for a different goal — installable, polished, secure, multi-host
portable. The complexity is the gap between those two goals.

The rest of this document walks through which parts of that
complexity are central and which are honestly over-engineered.

## What the bash equivalent cannot reach without becoming thermall

Five capabilities push the design past wrapper-script size:

### 1. Friendly defaults out of the box

A bash version shows `AUXTIN0`. thermall shows `VRM (CPU)` because
it ships a per-board label profile and auto-detects the board via
DMI on first run. The user does not edit a TOML file to get a
usable dashboard.

The cost is the `BoardProfile` data type, the `find_profile()`
lookup, the `detect_board()` reader, the per-category phrase
override on `ThresholdSet`. Maybe 200 LOC. Without it, the tool
shows you cryptic kernel sensor names and you find another tool.

### 2. Per-source graceful degradation

A bash version aborts on the first missing tool. thermall's
per-collector try / except catches the absence of `nvidia-smi`,
`nvme-cli`, `smartd`, or `nct6775` independently, surfaces a
friendly install hint in the affected panel, and renders
everything else normally.

This shows up in the `Collector.live()` boundary, in
`refresh.collect_snapshot()`, and in every panel's empty-state
hint. It is what makes thermall installable on a machine that
does not yet have all the prereqs without the dashboard breaking.

### 3. Threshold consistency

A bash version hard-codes warn / crit per sensor with `awk` if-
statements. thermall has one `ThresholdSet` abstraction with
per-category overrides driven by config. Changing the warn phrase
from "warm" to "running hot" is editing a dict, not sed-ing the
script. Adding a new category is adding an entry to
`_DEFAULT_THRESHOLDS`, not duplicating the colouring logic.

The cost is the `mapping.py` module: `resolve`, `grade_reading`,
`grade_many`, `category_for`, `ThresholdSet`, `phrase_for`. About
150 LOC. Provides a consistent surface across CPU / VRM / GPU /
NVMe panels.

### 4. Test surface

thermall has 300+ tests because the codebase is split into pure-
function layers (parsers, mapping, grading, config) that can be
exercised against recorded strings. The `tests/fixtures/`
directory holds real `sensors -j`, `nvidia-smi`, and
`smartd_journal.json` captures so the parsers run against
production data without ever invoking subprocess.

A bash version is "run it and eyeball it". That is fine for a
personal script. For a tool that multiple agents commit to and
multiple users install, the test discipline is what lets each
commit merge without manual smoke. The investment in pure
functions is paid back by the speed and confidence of the test
suite.

### 5. Privilege model

The most consequential difference. A naive bash equivalent would
do `sudo nvme smart-log` per refresh — terrible UX (password
prompt every two seconds) and a worse security posture than
necessary. thermall's default path is fully unprivileged
(`smartd` via `journalctl`); the opt-in advanced path uses a
hardened systemd helper service rather than `setcap` on `nvme`.

This is the only point in the design where the answer "use the
shell wrapper" is genuinely unworkable. Every other layer is a
matter of UX quality and test discipline; the privilege boundary
is a security architecture decision.

The trade-off is documented at length in
`README.md` § "Drive health monitoring" and in the project scope
doc. The summary: granting `CAP_SYS_ADMIN` to the `nvme` binary
(what `setcap` does) gives every local user the union of every
`nvme-cli` subcommand, including `nvme format`, `nvme fw-commit`,
and `nvme read` of raw block ranges. The helper service achieves
the same data access with a much smaller blast radius. thermall
ships the helper-based path; it explicitly does not document the
`setcap` recipe even though one-line versions circulate online.

## What is honestly over-engineered

Listed without defence:

1. **The `Reading` / `Fan` / `Gpu` / `NvmeDrive` data-model split.**
   Useful for typing and for keeping each panel narrow, but a
   rewrite from scratch would probably collapse them into one
   record type with optional fields. ~50 LOC of ceremony saved.
2. **Reactive snapshot setter + `remove_children` + remount in
   every panel.** Works correctly. More careful than the actual
   update pattern needs given how rarely the structure changes
   between refreshes; a `update()` re-render on the existing tree
   would be enough for most cases.
3. **`category_for` heuristic.** Routes readings into cpu / vrm /
   nvme / gpu / other buckets by substring matching `raw_label`.
   Useful when it works, occasionally wrong on weird boards. The
   alternative (let users assign categories in config) is more
   typing per user but less inference per maintainer; tradable.

A from-scratch rewrite knowing the requirements would probably
be 20-25% smaller. The current shape exists because we built
each layer against tests as we went; the testability discipline
is what produces the abstraction overhead.

## What the project deliberately does NOT do

The "out of scope" decisions are as central as the
inclusions:

- **No tmux composition mode in v1.** A previous iteration
  shipped a flag that spawned three panes (`btop` + `nvtop` +
  thermall). Demoted from v1 to "advanced, post-v1" because it
  conflicts with the one-polished-dashboard aesthetic.
- **No `setcap` recipe in any documentation.** As above. The
  helper service is the documented advanced path; `polkit` gets
  a paragraph pointer. Users who specifically want `setcap` will
  find it online; thermall does not bless it.
- **No persistent history across runs.** When historical
  temperature graphs (sparklines) land in v1.5, they are
  in-memory only. Disk-backed history is a separate feature
  with separate security and storage trade-offs.
- **No AMD / Intel GPU support in v1.** The `nvidia-smi` collector
  is NVIDIA-only. AMD `rocm-smi` and Intel `intel_gpu_top`
  surfaces are different shapes; a v2 collector layer can add
  them without touching the unprivileged-default model.
- **No fan control.** v1 is read-only across the board. Writing
  fan curves or PWM values introduces a destructive failure
  mode that fundamentally changes the threat model; deferring
  until the read-only side is stable.

## Security architecture summary

The thing to understand if you are evaluating thermall for
security: **at runtime, thermall is a normal unprivileged
user-space Python program**. Nothing it does at refresh time
requires elevated capabilities.

The two privileged pieces (if installed) are:

1. The helper service from `thermall install-nvme-helper`. A
   small root-owned script invoked by a systemd timer. Hardened
   with `NoNewPrivileges`, `ProtectSystem=strict`,
   `ProtectHome`, `DeviceAllow=block-nvme rw` only,
   `SystemCallFilter` scoped to what `nvme smart-log` needs.
   Writes parsed JSON to `/run/thermall/nvme.json` which the
   user reads.
2. `smartd` itself. Managed by your distro, not by thermall.
   thermall only reads `smartd`'s journal output via
   `journalctl`.

The supply-chain story: thermall is installed via `sfw uv tool
install` (Socket Firewall plus uv) like any other Python tool in
the project's discipline. Compromise of the thermall package via
the PyPI surface (a future risk; not currently published) would
give the attacker your unprivileged user-space access — the same
access any other user-space tool has — but **could not** invoke
`nvme format`, flash firmware, or read raw drive blocks.
The helper service is the privilege boundary, and the helper
script does not take user input.

By contrast, granting `setcap 'cap_sys_admin+ep'` to `/usr/sbin/nvme`
(the popular online recipe we deliberately do not document)
gives any user-space code running as you the entire `nvme-cli`
surface area. A compromised pip dependency could call
`nvme fw-commit` and persist across OS reinstall.

This is the reason we put effort into the helper-service
architecture instead of "wrap the bash commands". The shape of
the privilege boundary is the architecturally interesting
decision; the rest is UX polish.

## Development model

For people maintaining or extending thermall: the project was
built by multiple AI agents (Claude and Hermes) working in
parallel under direction from the human owner. The development
model that produced the current state has a few notable rules
that may surprise contributors used to single-developer
workflows:

- **One agent = one worktree = one branch = one task.** Adopted
  after a staging-area collision incident where two agents'
  commits accidentally merged. Each task gets its own git
  worktree under `~/thermall-worktrees/<task-id>/` on a
  `<agent>/<task-id>` branch. Master is integration / review
  only.
- **Task board at `tasks/` (gitignored).** Coordination surface,
  not part of the shipped repo. Each task spec carries its own
  acceptance criteria, gate command, and out-of-scope items.
  The convention prevents scope creep; spec author and
  implementer are explicit.
- **Strict gates before merge.** `ruff check` + `ruff format
  --check` + `mypy src/` + `pytest --cov=thermall
  --cov-fail-under=80` must pass. CI re-runs the same gates on
  every push.
- **Edge-case test discipline.** Every parser / external-input
  test suite is expected to cover malformed input, boundary
  values, missing fields, and mixed valid / invalid batches —
  not only the happy path. Captured as a project memory after
  initial tests were judged too thin.

These conventions surface as project files (the conventions
docs and the test layout) and as the multi-commit-per-task
history (`claude/12c-cpu-panel`, `hermes/13a-install-launcher`,
etc.). Forks adopting a single-author model can drop the
worktree discipline; the gates and test discipline are worth
keeping regardless.

## Closing read

The honest summary if you are weighing thermall:

- For "personal monitor on one machine," a bash wrapper does
  the job in 200 lines.
- For "polished tool I can install on multiple machines without
  thinking about prereqs, with a sensible default and a safe
  opt-in for richer data, that I can extend later without
  rewriting from scratch," thermall's investment is
  appropriate.
- The most architecturally substantive part is the privilege
  boundary (helper service vs `setcap`). The rest is testable-
  by-construction layering.
- About 20-25% of the line count is paying for the testability
  and the UX polish. Whether that trade is worth it depends on
  what you are doing with the tool.
