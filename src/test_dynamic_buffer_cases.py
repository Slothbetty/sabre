#!/usr/bin/env python3
"""
Case-based tests for the dynamic buffer algorithm.

Each test covers a specific scenario (seek hit/miss, prefetch provenance,
region preservation, adjacent merges, buffer level accuracy, PrefetchModule
API) to verify the dynamic buffer handles it correctly.

Usage:
    python test_dynamic_buffer_cases.py
    python test_dynamic_buffer_cases.py -v
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).parent
sys.path.insert(0, str(SRC_DIR))

from buffer import MultiRegionBuffer
from global_state import GlobalState, gs
from prefetch import PrefetchModule
from sabre import multi_region_buffer_seek


# ---------------------------------------------------------------------------
# MultiRegionBuffer + seek unit tests (Tests 1-10)
# ---------------------------------------------------------------------------

class TestDynamicBuffering(unittest.TestCase):
    """Unit tests that directly manipulate MultiRegionBuffer and GlobalState."""

    def setUp(self):
        GlobalState._initialized = False
        gs.__init__()
        self.chunk_duration = 2000  # 2 s chunks
        self.buffer = MultiRegionBuffer(self.chunk_duration)
        gs.multi_region_buffer = self.buffer
        gs.current_playback_pos = 0
        gs.buffer_fcc = 0

    # ------------------------------------------------------------------ #
    # Test 1: Positive seek -- seek to prefetched chunk, no rebuffer      #
    # ------------------------------------------------------------------ #
    def test_seek_to_prefetched_chunk_no_rebuffer(self):
        for seg in range(4):
            self.buffer.add_chunk(seg, quality=2)

        self.buffer.add_prefetch_chunk(5, quality=5)

        rebuffer = multi_region_buffer_seek(self.buffer, 10000, self.chunk_duration)
        self.assertFalse(rebuffer, "Seek to prefetched chunk should NOT rebuffer")
        self.assertIsNotNone(
            self.buffer._find_region_of(10000),
            "Region at 10000 ms should exist after seek",
        )
        self.assertEqual(
            self.buffer.get_buffer_level(), self.chunk_duration,
            "Buffer level should equal one chunk duration (2000 ms)",
        )

    # ------------------------------------------------------------------ #
    # Test 2: Seek to non-prefetched positions, rebuffer                  #
    #         (covers adjacent gap AND far-out miss)                      #
    # ------------------------------------------------------------------ #
    def test_seek_to_non_prefetched_rebuffers(self):
        for seg in range(4):
            self.buffer.add_chunk(seg, quality=2)

        self.buffer.add_prefetch_chunk(5, quality=3)

        # Adjacent gap: chunk 4 sits between linear end and prefetch start
        rebuffer = multi_region_buffer_seek(self.buffer, 8000, self.chunk_duration)
        self.assertTrue(rebuffer, "Seek to gap at chunk 4 should rebuffer")

        # Far-out miss: chunk 8 is well beyond any buffered region
        rebuffer = multi_region_buffer_seek(self.buffer, 16000, self.chunk_duration)
        self.assertTrue(rebuffer, "Seek to 16000 ms (chunk 8, no data) should rebuffer")
        self.assertIsNone(
            self.buffer._find_region_of(16000),
            "No region should exist at 16000 ms",
        )

    # ------------------------------------------------------------------ #
    # Test 3: Multiple seeks with multiple prefetch chunks                #
    # ------------------------------------------------------------------ #
    def test_multiple_seeks_with_multiple_prefetch(self):
        for seg in range(4):
            self.buffer.add_chunk(seg, quality=2)

        self.buffer.add_prefetch_chunk(5, quality=4)
        self.buffer.add_prefetch_chunk(10, quality=4)

        rebuffer = multi_region_buffer_seek(self.buffer, 10000, self.chunk_duration)
        self.assertFalse(rebuffer)
        self.assertEqual(
            self.buffer.get_buffer_level(), self.chunk_duration,
            "Buffer level should be one chunk after first seek",
        )

        rebuffer = multi_region_buffer_seek(self.buffer, 20000, self.chunk_duration)
        self.assertFalse(rebuffer)
        self.assertEqual(
            self.buffer.get_buffer_level(), self.chunk_duration,
            "Buffer level should be one chunk after second seek",
        )

    # ------------------------------------------------------------------ #
    # Test 4: Prefetch preserved, linear cleaned after seek               #
    #         (covers region survival across two sequential seeks)        #
    # ------------------------------------------------------------------ #
    def test_prefetch_regions_preserved_after_seek(self):
        for seg in range(4):
            self.buffer.add_chunk(seg, quality=2)

        self.buffer.add_prefetch_chunk(5, quality=4)
        self.buffer.add_prefetch_chunk(10, quality=4)

        multi_region_buffer_seek(self.buffer, 10000, self.chunk_duration)

        self.assertIsNotNone(
            self.buffer._find_region_of(20000),
            "Chunk 10 region should be preserved after seeking to chunk 5",
        )
        self.assertIn(10, self.buffer.prefetch_indices,
                       "Prefetch provenance for chunk 10 should survive")

        multi_region_buffer_seek(self.buffer, 20000, self.chunk_duration)

        self.assertIsNone(
            self.buffer._find_region_of(0),
            "Linear buffer at 0 ms should be cleaned up after seek",
        )
        self.assertIn(5, self.buffer.prefetch_indices,
                       "Prefetch provenance for chunk 5 should survive")

    # ------------------------------------------------------------------ #
    # Test 5: Adjacent prefetch merges, provenance tracked                #
    # ------------------------------------------------------------------ #
    def test_adjacent_prefetch_merges_provenance_tracked(self):
        for seg in range(4):
            self.buffer.add_chunk(seg, quality=2)

        self.buffer.add_prefetch_chunk(4, quality=5)

        valid_regions = [s for s in self.buffer.region_starts if s in self.buffer.region_map]
        self.assertEqual(
            len(valid_regions), 1,
            "Adjacent prefetch should merge into single region",
        )

        self.assertIn(4, self.buffer.prefetch_indices,
                       "Prefetch index 4 should remain after merge")
        self.assertNotIn(0, self.buffer.prefetch_indices,
                          "Linear chunk 0 should NOT be in prefetch_indices")

    # ------------------------------------------------------------------ #
    # Test 6: Seek within linear buffer (baseline, no prefetch)           #
    # ------------------------------------------------------------------ #
    def test_seek_within_linear_buffer_no_prefetch(self):
        for seg in range(8):
            self.buffer.add_chunk(seg, quality=3)

        rebuffer = multi_region_buffer_seek(self.buffer, 4000, self.chunk_duration)
        self.assertFalse(rebuffer, "Seek within linear buffer should not rebuffer")

        expected_level = self.chunk_duration * 6  # chunks 2,3,4,5,6,7 remain
        self.assertEqual(
            self.buffer.get_buffer_level(), expected_level,
            f"Buffer level should reflect 6 remaining chunks ({expected_level} ms)",
        )

    # ------------------------------------------------------------------ #
    # Test 7: Buffer level reflects contiguous prefetch after seek        #
    # ------------------------------------------------------------------ #
    def test_buffer_level_reflects_contiguous_prefetch(self):
        self.buffer.add_prefetch_chunk(10, quality=4)
        self.buffer.add_prefetch_chunk(11, quality=4)
        self.buffer.add_prefetch_chunk(12, quality=4)

        rebuffer = multi_region_buffer_seek(self.buffer, 20000, self.chunk_duration)
        self.assertFalse(rebuffer)
        self.assertEqual(
            self.buffer.get_buffer_level(), self.chunk_duration * 3,
            "Buffer level should be 3 contiguous prefetch chunks (6000 ms)",
        )

    # ------------------------------------------------------------------ #
    # Test 8: Non-contiguous prefetch regions -- hit and miss             #
    # ------------------------------------------------------------------ #
    def test_noncontiguous_prefetch_regions(self):
        self.buffer.add_prefetch_chunk(5, quality=3)
        self.buffer.add_prefetch_chunk(20, quality=3)

        rebuffer = multi_region_buffer_seek(self.buffer, 10000, self.chunk_duration)
        self.assertFalse(rebuffer)

        self.assertIsNotNone(self.buffer._find_region_of(40000))

        rebuffer = multi_region_buffer_seek(self.buffer, 30000, self.chunk_duration)
        self.assertTrue(rebuffer, "Seek to gap between prefetch regions should rebuffer")

        self.assertIn(5, self.buffer.prefetch_indices)
        self.assertIn(20, self.buffer.prefetch_indices)
        self.assertIsNotNone(
            self.buffer._find_region_of(40000),
            "Prefetch region at chunk 20 should survive a miss at chunk 15",
        )

    # ------------------------------------------------------------------ #
    # Test 9: Non-prefetch regions after seek position are preserved      #
    # ------------------------------------------------------------------ #
    def test_regions_after_seek_preserved(self):
        """All regions after the seek position are kept, regardless of
        whether they contain prefetch chunks."""
        for seg in range(4):
            self.buffer.add_chunk(seg, quality=2)

        for seg in range(20, 23):
            self.buffer.add_chunk(seg, quality=3)

        rebuffer = multi_region_buffer_seek(self.buffer, 20000, self.chunk_duration)
        self.assertTrue(rebuffer, "Seek to gap should rebuffer")

        self.assertIsNone(
            self.buffer._find_region_of(0),
            "Non-prefetch region before seek should be cleaned",
        )

        self.assertIsNotNone(
            self.buffer._find_region_of(40000),
            "Non-prefetch region AFTER seek position should be preserved",
        )

    # ------------------------------------------------------------------ #
    # Test 10: Prefetch chunks in same region preserved during seek       #
    # ------------------------------------------------------------------ #
    def test_prefetch_in_same_region_preserved(self):
        """When seeking within a region that contains prefetch chunks before
        the seek position, those prefetch chunks are saved and re-inserted
        as a separate region."""
        self.buffer.add_prefetch_chunk(3, quality=5)
        self.buffer.add_prefetch_chunk(4, quality=5)
        self.buffer.add_chunk(5, quality=2)
        self.buffer.add_chunk(6, quality=2)
        self.buffer.add_chunk(7, quality=2)

        valid_regions = [s for s in self.buffer.region_starts if s in self.buffer.region_map]
        self.assertEqual(len(valid_regions), 1, "Should be one merged region")

        rebuffer = multi_region_buffer_seek(self.buffer, 12000, self.chunk_duration)
        self.assertFalse(rebuffer)

        self.assertIsNotNone(
            self.buffer._find_region_of(6000),
            "Prefetch chunk 3 (at 6000 ms) should be preserved",
        )
        self.assertIn(3, self.buffer.prefetch_indices)
        self.assertIn(4, self.buffer.prefetch_indices)

        self.assertIsNotNone(
            self.buffer._find_region_of(12000),
            "Region at seek position should exist",
        )
        self.assertEqual(
            self.buffer.get_buffer_level(), self.chunk_duration * 2,
            "Buffer level should be 2 chunks (6 and 7) at seek position",
        )


# ---------------------------------------------------------------------------
# PrefetchModule unit tests (Tests 11-14)
# ---------------------------------------------------------------------------

class TestPrefetchModule(unittest.TestCase):
    """Unit tests for PrefetchModule loading, trigger logic, and exhaustion."""

    FIXTURE = SRC_DIR / "test_prefetch_config_fixture.json"

    def setUp(self):
        self.pm = PrefetchModule(str(self.FIXTURE))

    # ------------------------------------------------------------------ #
    # Test 11: JSON loading                                               #
    # ------------------------------------------------------------------ #
    def test_json_loading(self):
        self.assertEqual(self.pm.pending_segments, [5, 10, 15])
        self.assertEqual(self.pm.completed_segments, set())
        self.assertEqual(self.pm.buffer_threshold_ms, 20000)

    # ------------------------------------------------------------------ #
    # Test 12: Trigger logic                                              #
    # ------------------------------------------------------------------ #
    def test_trigger_logic(self):
        self.assertFalse(
            self.pm.should_prefetch(10000),
            "Should NOT prefetch when buffer < threshold",
        )
        self.assertTrue(
            self.pm.should_prefetch(25000),
            "Should prefetch when buffer > threshold",
        )

    # ------------------------------------------------------------------ #
    # Test 13: Segment exhaustion                                         #
    # ------------------------------------------------------------------ #
    def test_segment_exhaustion(self):
        for seg in [5, 10, 15]:
            self.assertIsNotNone(self.pm.get_next_prefetch_segment())
            self.pm.mark_prefetched(seg)
        self.assertIsNone(self.pm.get_next_prefetch_segment())
        self.assertFalse(self.pm.should_prefetch(99999))

    # ------------------------------------------------------------------ #
    # Test 14: Skip already-prefetched during linear download             #
    # ------------------------------------------------------------------ #
    def test_skip_already_prefetched(self):
        """Simulate the linear download loop skipping prefetched segments.

        In sabre.py, the download loop checks ``gs.next_segment in
        buffer.prefetch_indices`` and increments ``gs.next_segment`` to
        avoid re-downloading prefetched chunks.
        """
        GlobalState._initialized = False
        gs.__init__()
        chunk_duration = 2000
        buf = MultiRegionBuffer(chunk_duration)
        gs.multi_region_buffer = buf
        gs.current_playback_pos = 0
        gs.buffer_fcc = 0
        gs.next_segment = 0

        buf.add_prefetch_chunk(3, quality=5)
        buf.add_prefetch_chunk(6, quality=5)

        downloaded = []
        for _ in range(10):
            if gs.next_segment >= 10:
                break
            if gs.next_segment in buf.prefetch_indices:
                gs.next_segment += 1
                continue
            downloaded.append(gs.next_segment)
            buf.add_chunk(gs.next_segment, quality=2)
            gs.next_segment += 1

        self.assertNotIn(3, downloaded,
                          "Segment 3 should be skipped (already prefetched)")
        self.assertNotIn(6, downloaded,
                          "Segment 6 should be skipped (already prefetched)")
        self.assertIn(0, downloaded)
        self.assertIn(1, downloaded)
        self.assertIn(4, downloaded)
        self.assertIn(5, downloaded)


if __name__ == "__main__":
    unittest.main()
