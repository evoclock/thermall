# SPDX-FileCopyrightText: 2026 Julen Gamboa <j.a.r.gamboa@gmail.com>
# SPDX-License-Identifier: MIT

"""Tests for HistoryStore."""

from __future__ import annotations

import pytest

from thermall.history import DEFAULT_MAX_SAMPLES, HistoryStore


class TestHistoryStoreConstruction:
    def test_defaults(self) -> None:
        store = HistoryStore()
        assert store.max_samples == DEFAULT_MAX_SAMPLES
        assert store.labels() == ()

    def test_custom_max_samples(self) -> None:
        store = HistoryStore(max_samples=5)
        assert store.max_samples == 5

    def test_zero_max_samples_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_samples"):
            HistoryStore(max_samples=0)

    def test_negative_max_samples_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_samples"):
            HistoryStore(max_samples=-3)


class TestHistoryStoreRecording:
    def test_record_one_value(self) -> None:
        store = HistoryStore()
        store.record("cpu", 45.0)
        assert store.get("cpu") == (45.0,)

    def test_record_multiple_values_same_label(self) -> None:
        store = HistoryStore()
        for v in (45.0, 46.5, 47.0):
            store.record("cpu", v)
        assert store.get("cpu") == (45.0, 46.5, 47.0)

    def test_record_multiple_labels_independent(self) -> None:
        store = HistoryStore()
        store.record("cpu", 45.0)
        store.record("gpu", 70.0)
        store.record("cpu", 46.0)
        assert store.get("cpu") == (45.0, 46.0)
        assert store.get("gpu") == (70.0,)

    def test_eviction_at_max_samples(self) -> None:
        store = HistoryStore(max_samples=3)
        for v in (1.0, 2.0, 3.0, 4.0):
            store.record("cpu", v)
        assert store.get("cpu") == (2.0, 3.0, 4.0)

    def test_eviction_across_many_appends(self) -> None:
        store = HistoryStore(max_samples=5)
        for i in range(100):
            store.record("cpu", float(i))
        assert store.get("cpu") == (95.0, 96.0, 97.0, 98.0, 99.0)

    def test_get_unknown_label_returns_empty(self) -> None:
        store = HistoryStore()
        assert store.get("nonexistent") == ()

    def test_get_returns_tuple_not_deque(self) -> None:
        store = HistoryStore()
        store.record("cpu", 1.0)
        snap = store.get("cpu")
        assert isinstance(snap, tuple)


class TestHistoryStoreInspection:
    def test_labels_lists_recorded_labels(self) -> None:
        store = HistoryStore()
        store.record("cpu", 1.0)
        store.record("gpu", 2.0)
        store.record("cpu", 3.0)
        assert set(store.labels()) == {"cpu", "gpu"}

    def test_clear_drops_all_history(self) -> None:
        store = HistoryStore()
        store.record("cpu", 1.0)
        store.record("gpu", 2.0)
        store.clear()
        assert store.labels() == ()
        assert store.get("cpu") == ()
