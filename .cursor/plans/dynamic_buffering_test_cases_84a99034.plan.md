---
name: Dynamic buffering test cases
overview: Add a prefetch index set to MultiRegionBuffer for provenance tracking, then create test_dynamic_buffering.py with unit tests verifying prefetch + seek behavior (no rebuffer on prefetch hit, rebuffer on miss, provenance preserved through merges and seeks).
todos:
  - id: add-prefetch-index-set
    content: "Add `prefetch_indices: set` to MultiRegionBuffer; add `add_prefetch_chunk()` method; update `pop_chunk()` to remove from set"
    status: completed
  - id: create-test-file
    content: Create src/test_dynamic_buffering.py with unittest structure, setUp/tearDown for gs reset, and simulate_seek helper
    status: completed
  - id: test-positive-seek
    content: "Test 1: Seek to prefetched chunk position, verify no rebuffer"
    status: completed
  - id: test-negative-seek
    content: "Test 2: Seek to non-prefetched position, verify rebuffer occurs"
    status: completed
  - id: test-multiple-seeks
    content: "Test 3: Multiple prefetch chunks with multiple seeks all succeed"
    status: completed
  - id: test-near-prefetch
    content: "Test 4: Seek near but outside prefetch range, verify rebuffer"
    status: completed
  - id: test-preserve-regions
    content: "Test 5: Prefetch regions preserved after seeking to another prefetch region"
    status: completed
  - id: test-adjacent-merge
    content: "Test 6: Adjacent prefetch merges with linear buffer, but prefetch_indices still tracks provenance"
    status: completed
  - id: test-quality-preserved
    content: "Test 7: Prefetch chunk quality (high bitrate) preserved after seek"
    status: completed
  - id: test-buffer-level
    content: "Test 8: Buffer level correctly reflects contiguous prefetch chunks after seek"
    status: completed
  - id: test-noncontiguous-regions
    content: "Test 9: Multiple non-contiguous prefetch regions with seek hit/miss"
    status: completed
  - id: test-baseline-linear
    content: "Test 10: Seek within linear buffer (no prefetch) as baseline sanity check"
    status: completed
  - id: test-seek-cleanup
    content: "Test 11: Seek to prefetch position cleans linear chunks but preserves all prefetch chunks"
    status: completed
  - id: create-prefetch-module
    content: "Create src/prefetch.py with PrefetchModule class: loads JSON locations, buffer-threshold trigger, ABR-decided quality"
    status: completed
  - id: integrate-prefetch-sabre
    content: "Integrate prefetch into sabre.py process_download_loop: when buffer > threshold, download prefetch chunk instead of idling"
    status: completed
  - id: add-prefetch-cli-args
    content: "Add CLI args to sabre.py: --prefetch-config (JSON path), --prefetch-buffer-threshold (ms)"
    status: completed
  - id: test-prefetch-module
    content: "Add tests for prefetch module: JSON loading, trigger logic, ABR quality query, integration with simulation"
    status: completed
isProject: false
---

# Dynamic Buffering Test Cases

## Context

- `MultiRegionBuffer` in [buffer.py](src/buffer.py) supports non-contiguous regions, making it capable of holding prefetched chunks at arbitrary positions
- `update_buffer_during_seek` in [sabre.py](src/sabre.py) (lines 115-201) handles seek logic: if seek target is in a buffered region, no rebuffer; otherwise, buffer is cleared and rebuffer occurs
- Movie segments are 3000ms each in `movie.json`, but tests will use a configurable `chunk_duration` (2000ms) for clean alignment with the user's "10-12s" example
- The `GlobalState` singleton (`gs`) in [global_state.py](src/global_state.py) must be reset between tests since `get_buffer_level()` and `get_contiguous_chunks_from_current_position()` read `gs.current_playback_pos` and `gs.buffer_fcc`

## Step 0: Add prefetch provenance tracking to MultiRegionBuffer

Add a **prefetch index set** to [buffer.py](src/buffer.py) so we can distinguish prefetched chunks from linearly buffered ones, even after regions merge.

Changes to `MultiRegionBuffer`:

- Add `self.prefetch_indices = set()` in `__init`__
- Add `add_prefetch_chunk(self, segment_index, quality)` method: calls `self.add_chunk(segment_index, quality)` then adds `segment_index` to `self.prefetch_indices`
- Update `pop_chunk()` to also call `self.prefetch_indices.discard(popped_idx)` when removing a chunk

This approach is minimally invasive -- merge logic, `BufferRegion`, and all existing methods remain untouched. The set is a parallel tracking structure.

## New File

Create `src/test_dynamic_buffering.py` using `unittest.TestCase`, consistent with existing [test_buffer_comparison.py](src/test_buffer_comparison.py).

## Helper

Add a `simulate_seek(buffer, seek_to_ms)` helper that mirrors the logic in `update_buffer_during_seek`:

- Sets `gs.current_playback_pos = seek_to_ms` and `gs.buffer_fcc = 0`
- Calls `buffer._find_region_of(seek_to_ms)` to check for a hit
- If hit: trims chunks before seek position in that region (via `pop_chunk`), returns `False` (no rebuffer)
- If miss: clears non-prefetch regions only (check each region's chunk indices against `buffer.prefetch_indices`), returns `True` (rebuffer)

## Test Cases

### Test 1: Positive seek -- seek to prefetched chunk, no rebuffer

- Linear buffer: add chunks 0-3 (0-8s)
- Prefetch: add chunk 5 (10-12s) at high quality via `add_prefetch_chunk`
- Seek to 10000ms (10s, chunk 5)
- Assert: `simulate_seek` returns `False` (no rebuffer)
- Assert: `buffer._find_region_of(10000)` returns a region
- Assert: `buffer.get_buffer_level()` = 2 (TODO)
- Assert: Seek to chunk 4(8s), it will rebuffer (TODO).

### Test 2: Negative case -- seek to non-prefetched position, rebuffer

- Linear buffer: add chunks 0-3 (0-8s)
- Prefetch: add chunk 5 (10-12s)
- Seek to 16000ms (16s, chunk 8 -- outside any buffered region)
- Assert: `simulate_seek` returns `True` (rebuffer)
- Assert: `buffer._find_region_of(16000)` returns `None`

### Test 3: Multiple seeks with multiple prefetch chunks

- Linear buffer: add chunks 0-3 (0-8s)
- Prefetch: add chunks 5 (10-12s) and 10 (20-22s)
- First seek to 10000ms -> no rebuffer, data found
- Then seek to 20000ms -> no rebuffer, data found
- Assert both seeks succeed without rebuffer
- Assert the buffer level of these two successful seeks(TODO).

### Test 4: Seek near but outside prefetch range

- Linear buffer: add chunks 0-3 (0-8s)
- Prefetch: add chunk 5 (10-12s)
- Seek to 8000ms (8s, chunk 4 -- gap between prefetch chunk 5 and nowhere)(TODO)
- Assert: rebuffer (no data at chunk 7)

### Test 5: Prefetch region preserved after seek

- Linear buffer: add chunks 0-3 (0-8s)
- Prefetch: add chunks 5 (10-12s) and 10 (20-22s)
- Seek to 10000ms (10s)
- Assert: chunk 10 region (20-22s) still exists in `buffer.region_map`
- Assert: `10 in buffer.prefetch_indices`
- Seek to 20000ms (20s)
- Assert: linear buffer region (0-8s) is cleaned up
- Assert: chunk 5 region (10-12s) still exists in `buffer.region_map`
- Assert: `5 in buffer.prefetch_indices`

### Test 6: Adjacent prefetch merges with linear buffer, provenance tracked

- Linear buffer: add chunks 0-3 (0-8s)
- Prefetch: add chunk 4 (8-10s) via `add_prefetch_chunk`
- Assert: regions merge into a single region 0-10s (`len(buffer.region_map) == 1`)
- Assert: `4 in buffer.prefetch_indices` (provenance survives merge)
- Assert: `0 not in buffer.prefetch_indices` (linear chunks are not marked as prefetch)

### Test 7: Seek within linear buffer (no prefetch needed -- baseline)

- Linear buffer: add chunks 0-5 (0-12s)
- No prefetch
- Seek to 4000ms (still within linear buffer)
- Assert: no rebuffer, buffer level reflects remaining chunks

## Test setUp / tearDown

Each test must reset the `GlobalState` singleton:

```python
def setUp(self):
    gs._initialized = False
    gs.__init__()
    self.chunk_duration = 2000  # 2s chunks
    self.buffer = MultiRegionBuffer(self.chunk_duration)
    gs.multi_region_buffer = self.buffer
    gs.current_playback_pos = 0
    gs.buffer_fcc = 0
```

---

## Prefetch Module Implementation

### New File: `src/prefetch.py`

Create a `PrefetchModule` class that decides **when** and **where** to prefetch.

**JSON config format** (location only, bitrate decided by ABR):

```json
{
  "prefetch": [
    {"segment": 5},
    {"segment": 10},
    {"segment": 15}
  ]
}
```

**PrefetchModule class:**

- `__init__(self, config_path: str, buffer_threshold_ms: float)` -- loads JSON, sets threshold
- `should_prefetch(self, buffer_level_ms: float) -> bool` -- returns `True` if `buffer_level_ms > buffer_threshold_ms` and there are remaining prefetch targets
- `get_next_prefetch_segment(self) -> int | None` -- returns next un-prefetched segment index, or `None` if all done
- `mark_prefetched(self, segment_index: int)` -- marks segment as completed (removes from pending list)
- `pending_segments: list[int]` -- remaining segments to prefetch
- `completed_segments: set[int]` -- segments already prefetched

### Integration in `sabre.py` -- `process_download_loop`

`TODO: prefetch_module should not be only called in full_delay > 0 condition. it should be determined by prefetch_module.should_prefetch(buffer_level) method.`

The natural insertion point is the **full buffer delay** check at [sabre.py line 521-528](src/sabre.py):

```python
full_delay = get_buffer_level(...) + segment_time - buffer_size
if full_delay > 0:
    # EXISTING: deplete buffer, network delay, report delay
    # NEW: instead of idling during full_delay, check if we should prefetch
```

When `full_delay > 0` (buffer is full) **and** `prefetch_module.should_prefetch(buffer_level)`:

1. Get next prefetch segment: `prefetch_seg = prefetch_module.get_next_prefetch_segment()`
2. Ask ABR for quality: `quality, delay = abr.get_quality_delay(prefetch_seg)`
3. Download via `network.download(size, prefetch_seg, quality, buffer_level)`
4. Deplete buffer during download time (handles playback/seeks)
5. Add to buffer: `gs.multi_region_buffer.add_prefetch_chunk(prefetch_seg, quality)`
6. Mark completed: `prefetch_module.mark_prefetched(prefetch_seg)`
7. Skip prefetched segments during linear download: if `gs.next_segment` is already in `buffer.prefetch_indices`, increment `gs.next_segment`

### CLI arguments (in `sabre.py`)

- `--prefetch-config` / `-pc`: path to prefetch JSON file (default: None, no prefetch)
- `--prefetch-buffer-threshold` / `-pbt`: buffer level threshold in ms for triggering prefetch (default: e.g. 20000ms)

### ABR integration

The ABR decides quality for prefetch chunks using the **existing** `abr.get_quality_delay(segment_index)` interface. No changes to ABR classes needed. The quality chosen will reflect the ABR's view of current conditions (throughput, buffer level). Since prefetch happens when buffer is high, ABR will typically choose a high quality -- matching the user's expectation: "Generally the prefetch chunk will have a high bitrate, because the prefetch chunk is already downloaded when the buffer level is high enough."

### Prefetch module tests (in `test_dynamic_buffering.py`)

- **Test 12**: JSON loading -- verify `PrefetchModule` correctly parses the config and lists pending segments
- **Test 13**: Trigger logic -- `should_prefetch` returns `True` only when buffer > threshold and segments remain
- **Test 14**: Segment exhaustion -- after all segments prefetched, `get_next_prefetch_segment()` returns `None`
- **Test 15**: Skip already-prefetched -- during linear download, prefetched segments are skipped (next_segment incremented)

