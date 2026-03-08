#!/usr/bin/env python3
"""
Unit tests for dynamic buffering with prefetch + seek behaviour.

Verifies that MultiRegionBuffer correctly:
- Prevents rebuffering when seeking to a prefetched chunk
- Triggers rebuffering when seeking outside buffered regions
- Preserves prefetch provenance through merges and seeks
- Tracks buffer levels accurately after seeks

Usage:
    python test_dynamic_buffering.py
    python test_dynamic_buffering.py -v
"""

import sys
import math
import unittest
from pathlib import Path

from buffer import BufferRegion, MultiRegionBuffer
from global_state import GlobalState, gs


def simulate_seek(buffer: MultiRegionBuffer, seek_to_ms: float) -> bool:
    """Simulate a seek and return whether rebuffering is needed.

    Mirrors the logic in sabre.py ``update_buffer_during_seek``:
    - If the seek target lands inside a buffered region, trim earlier
      chunks in that region and return False (no rebuffer).
    - Otherwise, clean up non-prefetch regions (linear buffer) while
      keeping prefetch regions intact, and return True (rebuffer).

    Returns True if rebuffering is required, False otherwise.
    """
    gs.current_playback_pos = seek_to_ms
    gs.buffer_fcc = 0

    region = buffer._find_region_of(seek_to_ms)
    if region:
        seek_pos_idx = buffer._pos_to_idx(seek_to_ms)
        region.pop_chunk(seek_pos_idx)
        if region.chunks:
            old_start_candidates = [
                s for s in list(buffer.region_starts)
                if s in buffer.region_map and buffer.region_map[s] is region
            ]
            for old_s in old_start_candidates:
                if old_s != region.start_idx:
                    del buffer.region_map[old_s]
                    buffer.region_starts.remove(old_s)
            if region.start_idx not in buffer.region_map:
                buffer.region_map[region.start_idx] = region
                buffer.region_starts.append(region.start_idx)
                buffer.region_starts.sort()
        else:
            for s in list(buffer.region_starts):
                if s in buffer.region_map and buffer.region_map[s] is region:
                    del buffer.region_map[s]
                    buffer.region_starts.remove(s)

        _cleanup_non_prefetch_before(buffer, seek_pos_idx)
        buffer.merge_adjacent_regions()
        return False  # no rebuffer
    else:
        _cleanup_non_prefetch_regions(buffer)
        buffer.merge_adjacent_regions()
        return True  # rebuffer


def _cleanup_non_prefetch_before(buffer: MultiRegionBuffer, seek_idx: int):
    """Remove non-prefetch regions whose end <= seek_idx (behind playback)."""
    for start in list(buffer.region_starts):
        if start not in buffer.region_map:
            continue
        r = buffer.region_map[start]
        if r.end_idx is not None and r.end_idx <= seek_idx:
            has_prefetch = any(
                idx in buffer.prefetch_indices
                for idx in range(r.start_idx, r.end_idx)
            )
            if not has_prefetch:
                del buffer.region_map[start]
                buffer.region_starts.remove(start)


def _cleanup_non_prefetch_regions(buffer: MultiRegionBuffer):
    """Remove all regions that contain no prefetch chunks."""
    for start in list(buffer.region_starts):
        if start not in buffer.region_map:
            continue
        r = buffer.region_map[start]
        if r.end_idx is None:
            del buffer.region_map[start]
            buffer.region_starts.remove(start)
            continue
        has_prefetch = any(
            idx in buffer.prefetch_indices
            for idx in range(r.start_idx, r.end_idx)
        )
        if not has_prefetch:
            del buffer.region_map[start]
            buffer.region_starts.remove(start)


class TestDynamicBuffering(unittest.TestCase):
    """Tests for prefetch + seek behaviour of MultiRegionBuffer."""

    CHUNK_DURATION = 2000  # 2 s per chunk

    def setUp(self):
        GlobalState._initialized = False
        gs.__init__()
        self.buffer = MultiRegionBuffer(self.CHUNK_DURATION)
        gs.multi_region_buffer = self.buffer
        gs.current_playback_pos = 0
        gs.buffer_fcc = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_linear(self, start_idx: int, count: int, quality: float = 1.0):
        """Add *count* sequential chunks starting at *start_idx*."""
        for i in range(count):
            self.buffer.add_chunk(start_idx + i, quality)

    def _add_prefetch(self, segment_index: int, quality: float = 5.0):
        self.buffer.add_prefetch_chunk(segment_index, quality)

    def _valid_region_count(self) -> int:
        return len([s for s in self.buffer.region_starts if s in self.buffer.region_map])

    # ------------------------------------------------------------------
    # Test 1: Positive seek – seek to prefetched chunk, no rebuffer
    # ------------------------------------------------------------------
    def test_seek_to_prefetched_chunk_no_rebuffer(self):
        self._add_linear(0, 4)        # chunks 0-3  (0-8 s)
        self._add_prefetch(5)         # chunk 5     (10-12 s)

        rebuffer = simulate_seek(self.buffer, 10000)

        self.assertFalse(rebuffer, "Should NOT rebuffer when seeking to prefetched chunk")
        self.assertIsNotNone(self.buffer._find_region_of(10000))
        self.assertGreater(self.buffer.get_buffer_level(), 0)

    # ------------------------------------------------------------------
    # Test 2: Negative case – seek to non-prefetched position, rebuffer
    # ------------------------------------------------------------------
    def test_seek_outside_prefetch_rebuffers(self):
        self._add_linear(0, 4)        # chunks 0-3  (0-8 s)
        self._add_prefetch(5)         # chunk 5     (10-12 s)

        rebuffer = simulate_seek(self.buffer, 16000)

        self.assertTrue(rebuffer, "Should rebuffer when seeking outside any buffered region")
        self.assertIsNone(self.buffer._find_region_of(16000))

    # ------------------------------------------------------------------
    # Test 3: Multiple seeks with multiple prefetch chunks
    # ------------------------------------------------------------------
    def test_multiple_seeks_to_prefetch(self):
        self._add_linear(0, 4)
        self._add_prefetch(5)         # 10-12 s
        self._add_prefetch(10)        # 20-22 s

        rebuffer1 = simulate_seek(self.buffer, 10000)
        self.assertFalse(rebuffer1, "First seek to prefetch should not rebuffer")

        rebuffer2 = simulate_seek(self.buffer, 20000)
        self.assertFalse(rebuffer2, "Second seek to prefetch should not rebuffer")

    # ------------------------------------------------------------------
    # Test 4: Seek near but outside prefetch range
    # ------------------------------------------------------------------
    def test_seek_near_prefetch_rebuffers(self):
        self._add_linear(0, 4)        # 0-8 s
        self._add_prefetch(5)         # 10-12 s

        rebuffer = simulate_seek(self.buffer, 14000)

        self.assertTrue(rebuffer, "Seeking to gap between regions should rebuffer")

    # ------------------------------------------------------------------
    # Test 5: Prefetch regions preserved after seek
    # ------------------------------------------------------------------
    def test_prefetch_regions_preserved_after_seek(self):
        self._add_linear(0, 4)
        self._add_prefetch(5)         # 10-12 s
        self._add_prefetch(10)        # 20-22 s

        simulate_seek(self.buffer, 10000)

        self.assertIn(10, self.buffer.prefetch_indices,
                       "Prefetch index 10 should survive seek to index 5")
        found = False
        for start, region in self.buffer.region_map.items():
            if region.exists(10):
                found = True
                break
        self.assertTrue(found, "Region containing chunk 10 should still exist")

    # ------------------------------------------------------------------
    # Test 6: Adjacent prefetch merges with linear buffer, provenance tracked
    # ------------------------------------------------------------------
    def test_adjacent_prefetch_merges_provenance(self):
        self._add_linear(0, 4)        # chunks 0-3
        self._add_prefetch(4)         # chunk 4 – adjacent

        self.assertEqual(self._valid_region_count(), 1,
                         "Adjacent regions should merge into one")
        self.assertIn(4, self.buffer.prefetch_indices,
                       "Prefetch provenance should survive merge")
        self.assertNotIn(0, self.buffer.prefetch_indices,
                          "Linear chunks should not be marked as prefetch")

    # ------------------------------------------------------------------
    # Test 7: Prefetch chunk quality preserved after seek
    # ------------------------------------------------------------------
    def test_prefetch_quality_preserved(self):
        self._add_linear(0, 4, quality=1.0)
        self._add_prefetch(5, quality=5.0)

        simulate_seek(self.buffer, 10000)

        region = self.buffer._find_region_of(10000)
        self.assertIsNotNone(region)
        self.assertEqual(region.chunks[0], 5.0,
                         "Prefetched chunk should retain its original quality")

    # ------------------------------------------------------------------
    # Test 8: Buffer level reflects contiguous prefetch after seek
    # ------------------------------------------------------------------
    def test_buffer_level_after_prefetch_seek(self):
        self._add_linear(0, 4)
        for idx in (5, 6, 7):
            self._add_prefetch(idx)

        simulate_seek(self.buffer, 10000)

        expected = 3 * self.CHUNK_DURATION   # 3 contiguous prefetch chunks
        self.assertAlmostEqual(self.buffer.get_buffer_level(), expected, delta=1,
                               msg="Buffer level should equal 3 * chunk_duration after seeking to prefetch block")

    # ------------------------------------------------------------------
    # Test 9: Multiple non-contiguous prefetch regions
    # ------------------------------------------------------------------
    def test_noncontiguous_prefetch_regions(self):
        self._add_prefetch(5)         # 10-12 s
        self._add_prefetch(10)        # 20-22 s
        self._add_prefetch(15)        # 30-32 s

        self.assertEqual(self._valid_region_count(), 3,
                         "Three separate prefetch regions expected")

        rebuffer_hit = simulate_seek(self.buffer, 20000)
        self.assertFalse(rebuffer_hit, "Seek to prefetch region should not rebuffer")

        rebuffer_miss = simulate_seek(self.buffer, 14000)
        self.assertTrue(rebuffer_miss, "Seek to gap should rebuffer")

    # ------------------------------------------------------------------
    # Test 10: Seek within linear buffer (baseline)
    # ------------------------------------------------------------------
    def test_seek_within_linear_buffer(self):
        self._add_linear(0, 6)        # 0-12 s

        rebuffer = simulate_seek(self.buffer, 4000)

        self.assertFalse(rebuffer, "Seeking within linear buffer should not rebuffer")
        self.assertGreater(self.buffer.get_buffer_level(), 0)

    # ------------------------------------------------------------------
    # Test 11: Seek to prefetch cleans linear, preserves prefetch
    # ------------------------------------------------------------------
    def test_seek_cleans_linear_preserves_prefetch(self):
        self._add_linear(0, 6)        # 0-12 s
        self._add_prefetch(10)        # 20-22 s
        self._add_prefetch(15)        # 30-32 s

        rebuffer = simulate_seek(self.buffer, 20000)

        self.assertFalse(rebuffer)

        # Linear region (0-12 s) should be cleaned up
        self.assertIsNone(self.buffer._find_region_of(0),
                          "Linear region before seek should be cleaned up")

        # Prefetch chunk 15 should still exist
        found_15 = any(r.exists(15) for r in self.buffer.region_map.values())
        self.assertTrue(found_15, "Prefetch chunk 15 should survive seek")
        self.assertTrue({10, 15} <= self.buffer.prefetch_indices)


class TestPrefetchModule(unittest.TestCase):
    """Tests for PrefetchModule loading, trigger logic, and exhaustion."""

    FIXTURE = Path(__file__).parent / "test_prefetch_config.json"

    def setUp(self):
        from prefetch import PrefetchModule
        self.pm = PrefetchModule(str(self.FIXTURE), buffer_threshold_ms=20000)

    # ------------------------------------------------------------------
    # Test 12: JSON loading
    # ------------------------------------------------------------------
    def test_json_loading(self):
        self.assertEqual(self.pm.pending_segments, [5, 10, 15])
        self.assertEqual(self.pm.completed_segments, set())

    # ------------------------------------------------------------------
    # Test 13: Trigger logic
    # ------------------------------------------------------------------
    def test_trigger_logic(self):
        self.assertFalse(self.pm.should_prefetch(10000),
                         "Should NOT prefetch when buffer < threshold")
        self.assertTrue(self.pm.should_prefetch(25000),
                        "Should prefetch when buffer > threshold")

    # ------------------------------------------------------------------
    # Test 14: Segment exhaustion
    # ------------------------------------------------------------------
    def test_segment_exhaustion(self):
        for seg in [5, 10, 15]:
            self.assertIsNotNone(self.pm.get_next_prefetch_segment())
            self.pm.mark_prefetched(seg)

        self.assertIsNone(self.pm.get_next_prefetch_segment(),
                          "No segments should remain after all are prefetched")
        self.assertFalse(self.pm.should_prefetch(99999),
                         "should_prefetch must be False when no segments remain")

    # ------------------------------------------------------------------
    # Test 15: Skip already-prefetched during linear download
    # ------------------------------------------------------------------
    def test_skip_prefetched_in_linear(self):
        """Simulate the skip logic from process_download_loop."""
        GlobalState._initialized = False
        gs.__init__()
        buf = MultiRegionBuffer(2000)
        gs.multi_region_buffer = buf
        gs.current_playback_pos = 0
        gs.buffer_fcc = 0

        buf.add_prefetch_chunk(5, 5.0)
        self.pm.mark_prefetched(5)

        gs.next_segment = 4
        # Linear download of segment 4
        buf.add_chunk(4, 1.0)
        gs.next_segment = 5

        # Skip logic: if next_segment is already prefetched, increment
        if gs.next_segment in buf.prefetch_indices:
            gs.next_segment += 1

        self.assertEqual(gs.next_segment, 6,
                         "Linear download should skip already-prefetched segment")


if __name__ == "__main__":
    unittest.main()
