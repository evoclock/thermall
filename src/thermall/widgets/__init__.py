# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Reusable Textual widgets for the thermall dashboard."""

from thermall.widgets.cpu_panel import CpuPanel
from thermall.widgets.fans_panel import FansPanel
from thermall.widgets.gpu_panel import GpuPanel
from thermall.widgets.status_header import StatusHeader
from thermall.widgets.storage_panel import StoragePanel
from thermall.widgets.threshold_label import ThresholdLabel
from thermall.widgets.vrm_panel import VrmPanel

__all__ = [
    "CpuPanel",
    "FansPanel",
    "GpuPanel",
    "StatusHeader",
    "StoragePanel",
    "ThresholdLabel",
    "VrmPanel",
]
