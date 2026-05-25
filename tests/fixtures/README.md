# Test fixtures

Real, sanitised captures of the tooling outputs thermall consumes. Tests
read from these files instead of invoking subprocesses, keeping the test
suite fast, deterministic, and runnable in CI without hardware access.

## Required fixtures

| File                          | Source command                                                                                                          |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `sensors_output.json`         | `sensors -j`                                                                                                            |
| `nvidia_smi_output.csv`       | `nvidia-smi --query-gpu=name,temperature.gpu,fan.speed,power.draw,memory.used,memory.total --format=csv,noheader,nounits` |
| `nvme_smart_output.txt`       | `nvme smart-log /dev/nvme0n1` (or any visible NVMe device)                                                              |

Tests that depend on a missing fixture call `pytest.skip` with a clear
pointer to thermall task #9. Capture once per supported hardware
generation; sanitisation is mandatory (see below).

## Sanitisation checklist

Before committing a fixture:

1. Replace serial numbers (`Serial number:` lines in NVMe output) with
   `SERIAL-REDACTED`.
2. Replace any host-identifying device labels (`linux-julen`,
   user-modified hwmon labels) with neutral placeholders.
3. For NVIDIA fixtures: keep the GPU model name (e.g.
   `NVIDIA GeForce RTX 4070`) but redact the device UUID line if
   present (`--query-gpu=uuid`). The default query string does not
   request UUIDs.
4. For motherboard sensor fixtures, keep the chip identifier
   (`nct6798-isa-0290`) since it determines parser behaviour, but
   confirm no MAC address or other identifying values leak through.

When in doubt, run `grep -iE 'serial|uuid|mac|host|user'` over the
fixture file before committing.

## Adding a fixture for new hardware

If you add support for a new sensor chip, GPU vendor, or NVMe vendor,
add a parallel fixture named
`<vendor>__<chip>__<short_label>.{json,csv,txt}` so the matrix of
supported hardware is visible from the file listing alone.
