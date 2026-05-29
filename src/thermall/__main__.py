# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Allow `python -m thermall`."""

from thermall.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
