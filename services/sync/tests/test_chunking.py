"""Chunking: known row counts split into the expected number of chunks, the
last chunk is shorter, and the split is deterministic across calls (which is
what makes `chunk_number` safe to reuse on a retry)."""

from __future__ import annotations

import pytest

from services.sync.chunking import chunked


def test_exact_multiple_of_chunk_size():
    chunks = list(chunked(range(20), 10))
    assert [len(c) for c in chunks] == [10, 10]


def test_last_chunk_is_shorter():
    chunks = list(chunked(range(25), 10))
    assert [len(c) for c in chunks] == [10, 10, 5]


def test_single_chunk_when_fewer_items_than_size():
    chunks = list(chunked(range(3), 10))
    assert [len(c) for c in chunks] == [3]


def test_empty_input_yields_no_chunks():
    assert list(chunked([], 10)) == []


def test_encounters_sized_split_matches_chunk_size_100():
    # 1159 raw rows -> 12 chunks (11 full, 1 of 59), matching the real file.
    chunks = list(chunked(range(1159), 100))
    assert len(chunks) == 12
    assert [len(c) for c in chunks[:-1]] == [100] * 11
    assert len(chunks[-1]) == 59


def test_chunking_is_deterministic():
    items = list(range(37))
    assert list(chunked(items, 10)) == list(chunked(items, 10))


def test_rejects_non_positive_size():
    with pytest.raises(ValueError):
        list(chunked([1, 2, 3], 0))
