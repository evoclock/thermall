# thermall explainer

Plain-language overview of what thermall does, why it exists, and how it is
built. The README covers install and usage; this document covers design.

## What it does

Your computer has dozens of temperature and fan sensors scattered across the
motherboard, the CPU, every GPU, and every NVMe drive. Each sensor is
readable with a different command-line tool (`sensors`, `nvidia-smi`,
`nvme smart-log`), and each tool reports raw kernel names like `AUXTIN0`
and `fan6` that mean nothing without a manual. thermall reads all of them
every couple of seconds, applies a hardware-specific label map (so
`AUXTIN0` becomes `VRM (CPU)`), checks each reading against a warn /
critical threshold, and renders the whole picture in one terminal window
with green / amber / red colouring. If a fan stops spinning while the chip
it cools is climbing, you see it immediately instead of finding out hours
later from a thermal shutdown.

## Why it has to exist

The problem is correlation, not collection. `btop` shows CPU load
beautifully but does not know what fan number 6 is. `nvtop` shows GPU
detail but only GPU. Running `sensors` and `nvidia-smi` in two terminals
side by side works, but the mental cross-referencing between "fan 4
dropped to 0 RPM" and "the chipset is now at 85 C" is the whole job, and
humans are bad at it. thermall does the cross-referencing for you.

## How it is built: the assembly line metaphor

```text
   +----------+    +----------+    +------------+    +----------+
   |  Intake  | -> |  Sorter  | -> | Translate  | -> | Display  |
   |  3 work- |    | combines |    | + Grade    |    | Textual  |
   |  ers, 1  |    | into one |    | raw -> hu- |    | panels   |
   |  per     |    | snapshot |    | man labels |    | and      |
   |  source  |    |          |    |            |    | colours  |
   +-----^----+    +----------+    +------^-----+    +----------+
         |                                |
         | shells out to:           +-----+------+
         | sensors -j               |   Config   |
         | nvidia-smi               |   (TOML)   |
         | nvme smart-log           | rules and  |
         |                          | thresholds |
         |                          +------------+

   Front door: a Dispatcher (the CLI) decides whether `thermall` opens
   the interactive Display or just prints a summary (TTY vs pipe).
```

Four stations, each with one job:

### 1. Intake (`src/thermall/collectors.py`)

Three workers, one per data source. Each worker shells out to its assigned
tool (`sensors -j`, `nvidia-smi --query-gpu`, `nvme smart-log`), catches
the raw text, and turns it into a stack of standardised cards. Shelling
out is the only "messy" thing the workers do; the actual conversion from
raw text to card is a pure transformation you can test by handing the
worker a recorded string instead of running the tool. All three workers
share a common contract (the `Collector` abstract base class) so the rest
of the line does not have to care which source produced which card.

### 2. Sorter (`src/thermall/model.py`)

All the cards land on one desk. The Sorter staples them into a single
**snapshot** with a timestamp: a frozen object that says "as of 18:45:02
UTC, here is everything." Frozen means nothing downstream can accidentally
edit a card; if you want a "modified" card, you make a new one. The
snapshot also derives summary properties on demand (highest severity
present, whether any warning was raised) rather than storing them, so it
can never be in a self-contradictory state.

### 3. Translate + Grade (`src/thermall/mapping.py` and `src/thermall/config.py`)

The snapshot moves to the next desk. The Translator looks up each cryptic
label in the user's config (`AUXTIN0` resolves to `VRM (CPU)`). The Grader
compares each value against its category's threshold set (CPU warns at 80
C, crits at 90 C; VRM warns at 90, crits at 100; and so on) and stamps a
severity onto every card. The snapshot leaves this desk human-readable and
colour-codable. The config layer always returns a complete `Config`, with
sensible defaults when the user has not written a `~/.config/thermall/`
file, so the next station never has to guard against missing values.

### 4. Display (`src/thermall/dashboard.py`)

A Textual application (terminal-native GUI) takes the translated snapshot
and renders it. Header with the clock at the top, footer with key
shortcuts at the bottom, panels in the middle for CPU, VRM, GPUs, NVMe,
and fans. Refreshes every couple of seconds. The same five keys work
everywhere: `q` quits, `h` opens help, `t` cycles themes, `r` forces a
refresh, `?` shows the binding list.

### 5. Dispatcher (`src/thermall/cli.py`)

A fifth piece sits at the front door. When you run `thermall`, the
Dispatcher parses arguments, loads config, and checks whether your output
is going to a real terminal or to a pipe / script. Terminal: it opens the
Textual app. Pipe or test: it prints a text summary instead. Same binary,
useful in both contexts. The same convention `git diff`, `ls`, and `grep`
use.

## Why the assembly line shape

The shape is deliberate. External I/O lives at exactly one boundary (the
Intake station's subprocess calls). Everything past that boundary is pure
functions on immutable data. That choice pays off three ways:

1. **Tests do not need real hardware.** Recorded text strings get fed
   straight into the parsers, the rest of the line runs unchanged, and
   the test asserts on what the Sorter or the Grader produces. The CI run
   in GitHub Actions has no `sensors`, no GPU, and no NVMe device, yet it
   exercises every layer except the literal `subprocess.run` call.

2. **The same machinery works for adjacent features.** A "replay a saved
   session" mode, or a "compare two hosts side by side" mode, needs no
   architectural change. You feed different strings into the parsers and
   the line produces dashboards as usual.

3. **Bugs are usually localised.** A misread sensor shows up at the
   Intake station. A wrong human label or a misgraded threshold shows up
   at the Translate + Grade station. A layout glitch shows up at the
   Display station. You almost always know which station to look at
   before you start reading code.

## What works today vs what is stubbed

| Station    | Today                                                                       | Needs                                                                                  |
| ---------- | --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Intake     | Three workers; the shell-out plumbing; the abstract interface and contract  | The actual "read paperwork" step (parsers wait on real captured samples from the host) |
| Sorter     | done                                                                        | nothing                                                                                |
| Translate  | done                                                                        | nothing                                                                                |
| Grade      | done                                                                        | nothing                                                                                |
| Display    | Building frame; header; footer; key shortcuts; placeholder sign             | The actual panels showing data (waits on Intake)                                       |
| Dispatcher | done, with TTY split                                                        | nothing                                                                                |

In plain terms: the factory exists, every station is built and tested in
isolation, but two of the workers (the Intake parsers and the Display
panels) are still waiting for real materials. The materials are sample
outputs from `sensors -j`, `nvidia-smi`, and `nvme smart-log` on the
target hardware. Once those land in `tests/fixtures/`, the parsers know
what shape the paperwork takes and the assembly line starts producing
real dashboards.

## Where to look in the code

| Concept                       | File                                  |
| ----------------------------- | ------------------------------------- |
| The Intake workers            | `src/thermall/collectors.py`          |
| The card / snapshot data model | `src/thermall/model.py`              |
| The Translator and Grader     | `src/thermall/mapping.py`             |
| The configuration rules       | `src/thermall/config.py`              |
| The Display itself            | `src/thermall/dashboard.py`           |
| The Dispatcher (CLI)          | `src/thermall/cli.py`                 |
| Test fixture loader contract  | `tests/conftest.py`                   |
| Fixture sanitisation rules    | `tests/fixtures/README.md`            |

That is the whole tool: read three messy sources, fold them into one
immutable snapshot, label and colour-grade against a config, show it on
screen, and split sensibly between interactive and scripted use.
