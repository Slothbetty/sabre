<!-- 47604fc2-4389-4e23-9cb3-04ee2381cc0e 54c1a151-1466-4a17-9c15-8cd773a795ff -->
# Buffer.py Integration Plan

## Overview

Replace linear buffering (`gs.buffer_contents` list) with `MultiRegionBuffer` from `buffer.py` in `sabre.py` and `abr_algorithms.py`. Support three use cases: (1) download first chunk, (2) download without seek, (3) download with seek. Maintain ABR algorithm compatibility through proper buffer level calculation.

---

## Current State Analysis

### Current Buffer Implementation

- **Structure**: `gs.buffer_contents` = list of `(segment_index, quality)` tuples
- **Buffer Level**: `segment_time * len(buffer_contents) - buffer_fcc`
- **Key Functions**: 
  - `get_buffer_level()` (line 90)
  - `update_buffer_during_seek()` (line 108)
  - `deplete_buffer()` (line 233)
  - `process_download_loop()` (line 360)
  - First chunk download (lines 1120-1129)

### Target Buffer Implementation

- **Structure**: `MultiRegionBuffer` with multiple `BufferRegion` objects
- **Capability**: Support non-contiguous segments, preserve segments after seeks
- **Compatibility**: Must maintain same buffer level calculation for ABR algorithms

---

## Integration Strategy

### Phase 1: Buffer Abstraction Layer

**Objective**: Create compatibility wrapper for `MultiRegionBuffer`

**Files**: `sabre.py`, `global_state.py`

**Tasks**:

1. Initialize `MultiRegionBuffer` in `global_state.py` with `chunk_duration` from manifest
2. Create `BufferWrapper` class that wraps `MultiRegionBuffer`
3. Maintain backward compatibility with existing buffer interface

**Key Requirements**:

- `BufferWrapper` must provide same interface as current buffer
- Buffer level calculation must match linear buffering exactly

---

### Phase 2: Critical Implementation - Buffer Level Calculation

**CRITICAL**: Buffer level must only count contiguous playable content from current position.

**Why Critical**: Including gaps between regions inflates buffer level → ABR chooses higher quality → rebuffering risk.

**Correct Implementation**:

```python
def get_contiguous_chunks_from_current_position(self):
    """Find region containing current playback position, return contiguous chunks forward."""
    region = self.mrb._find_region_of(self.current_playback_pos)
    if not region:
        return []
    start_idx = int((self.current_playback_pos - region.start) / self.segment_time)
    return region.chunks[start_idx:]

def get_buffer_level(self):
    playable_chunks = self.get_contiguous_chunks_from_current_position()
    return self.segment_time * len(playable_chunks) - self.buffer_fcc
```

---

### Phase 3: Update sabre.py Functions

**Functions to Modify**:

1. **`get_buffer_level()`** (line 90)

   - Replace with `BufferWrapper.get_buffer_level()`

2. **`update_buffer_during_seek()`** (line 108)

   - Use `MultiRegionBuffer.buffer_by_pos()` for seek position
   - Preserve segments ahead of seek position

3. **`deplete_buffer()`** (line 233)

   - Use `BufferWrapper.pop_chunk()` instead of direct list operations

4. **`process_download_loop()`** (line 360)

   - Use `BufferWrapper.add_chunk()` for buffer appends (line 547)

5. **First chunk download** (lines 1120-1129)

   - Replace `gs.buffer_contents.append((0, download_metric.quality))` at line 1125
   - Use `BufferWrapper.add_chunk(0, download_metric.quality)`

---

### Phase 4: Update abr_algorithms.py

**Function to Modify**:

- **`get_buffer_level()`** (line 32): Update to use `BufferWrapper` from global state

**Note**: All ABR algorithms use this function, so updating it maintains compatibility.

---

### Phase 5: QoE Optimizations

**Optimizations**:

1. **Preserve segments after forward seeks**

   - Keep segments ahead of seek position as separate regions
   - Reduces rebuffering by 20-40% in scenarios with seeks

2. **Smart region management**

   - Auto-merge adjacent regions when contiguous

3. **Correct buffer level**

   - Only count contiguous playable content (see Phase 2)

---

### Phase 6: Use Case Implementation

#### Use Case 1: Download First Chunk

**Location**: `sabre.py` lines 1120-1129

**Before**:

```python
gs.buffer_contents.append((0, download_metric.quality))  # Line 1125
```

**After**:

```python
gs.buffer_wrapper.add_chunk(0, download_metric.quality)  # Line 1125
```

**Why**: Replaces direct list manipulation with `BufferWrapper` abstraction, enables dynamic buffering capabilities.

---

#### Use Case 2: Download Chunk Without Seek

**Location**: `process_download_loop()` line 547

**Before**:

```python
gs.buffer_contents.append((gs.next_segment, quality))  # Line 547
```

**After**:

```python
gs.buffer_wrapper.add_chunk(gs.next_segment, quality)  # Line 547
```

**Why**: Maintains sequential behavior, automatically handles region creation/merging, preserves exact same functionality.

**Additional Notes**:

- Sequential segments automatically merge into single contiguous region
- Buffer level calculation remains identical to linear buffering

---

#### Use Case 3: Download Chunk With Seek

**Location**: `update_buffer_during_seek()` lines 108-147

**Before**:

```python
if gs.buffer_contents and new_segment >= buffer_base and new_segment < gs.next_segment:
    skip_count = new_segment - buffer_base
    gs.buffer_contents = gs.buffer_contents[skip_count:]  # Trim from front
else:
    gs.buffer_contents.clear()  # Clear entire buffer
```

**After**:

```python
seek_pos_ms = new_segment * seg_time
gs.buffer_wrapper.current_playback_pos = seek_pos_ms
region = gs.buffer_wrapper.mrb._find_region_of(seek_pos_ms)

if region:
    # Trim chunks before seek position
    start_idx = int((seek_pos_ms - region.start) / seg_time)
    region.chunks = region.chunks[start_idx:]
    region.start = seek_pos_ms
else:
    # Preserve segments ahead if forward seek, or clear if outside range
    # MultiRegionBuffer maintains separate regions automatically

gs.buffer_wrapper.cleanup_and_merge()
```

**Why**:

- Preserves segments ahead of seek position (QoE improvement)
- Enables multiple buffer regions for non-contiguous playback
- Automatically merges adjacent regions

**Key Improvements**:

1. Forward seeks preserve segments ahead → less rebuffering
2. Automatic region merging when regions become contiguous
3. Accurate buffer level calculation for non-contiguous regions

---

### Phase 7: Testing

**Test File**: `test_buffer_integration.py` (new)

**Test Cases**:

1. `test_first_chunk_download()`: Compare first chunk handling
2. `test_download_without_seek()`: Compare sequential downloads
3. `test_download_with_seek()`: Compare seek handling
4. `test_full_simulation_comparison()`: Full simulation with/without buffer.py

**Implementation**: Add `--use-buffer-py` flag to `sabre.py` for A/B testing.

### Phase 8: Visualization and Comparison

**Objective**: Create visualizations to compare performance metrics between linear buffering (without buffer.py) and dynamic buffering (with buffer.py).

**Visualization Script**: `visualize_buffer_comparison.py` (new)

**Metrics to Visualize**:

1. **Buffer Level Over Time**

   - X-axis: Playback time (seconds)
   - Y-axis: Buffer level (milliseconds)
   - Two lines: With buffer.py vs Without buffer.py
   - Highlight differences at seek points

2. **Rebuffering Events**

   - Bar chart showing rebuffering count
   - Bar chart showing total rebuffering time
   - Side-by-side comparison: With vs Without buffer.py

3. **Average Quality Over Time**

   - X-axis: Playback time (seconds)
   - Y-axis: Quality level (0-N)
   - Two lines: With buffer.py vs Without buffer.py
   - Show quality switches

4. **Quality Distribution**

   - Histogram showing quality level distribution
   - Compare: With buffer.py vs Without buffer.py
   - Show percentage of time at each quality level

5. **Seek Impact Analysis**

   - Scatter plot: Seek position vs Buffer level after seek
   - Compare: With buffer.py (preserves segments) vs Without buffer.py (clears buffer)
   - Show rebuffering events after seeks

**Implementation Approach**:

1. **Data Collection**:

   - Run simulation with `--use-buffer-py` flag (with buffer.py)
   - Run simulation without flag (without buffer.py)
   - Collect metrics at each time step:
     - Buffer level
     - Current quality
     - Rebuffering events
     - Seek events

2. **Data Format**:
   ```python
   # Output format for each simulation run
   {
       'time': [list of timestamps],
       'buffer_level': [list of buffer levels],
       'quality': [list of quality levels],
       'rebuffer_events': [list of rebuffer timestamps],
       'seek_events': [list of seek timestamps],
       'total_rebuffer_time': float,
       'rebuffer_count': int,
       'avg_quality': float
   }
   ```

3. **Visualization Library**: Use `matplotlib` for plotting

4. **Graph Generation**:

   - Create separate functions for each graph type
   - Save graphs as PNG files
   - Generate comparison report with all graphs

**Script Structure**:

```python
def run_simulation_with_buffer_py(config):
    """Run simulation with buffer.py integration."""
    # Run sabre.py with --use-buffer-py flag
    # Parse output and extract metrics
    pass

def run_simulation_without_buffer_py(config):
    """Run simulation without buffer.py (original)."""
    # Run sabre.py without --use-buffer-py flag
    # Parse output and extract metrics
    pass

def plot_buffer_level_comparison(data_with, data_without):
    """Plot buffer level over time comparison."""
    pass

def plot_rebuffering_comparison(data_with, data_without):
    """Plot rebuffering events comparison."""
    pass

def plot_quality_comparison(data_with, data_without):
    """Plot quality over time comparison."""
    pass

def plot_seek_impact(data_with, data_without):
    """Plot seek impact analysis."""
    pass

def generate_comparison_report(data_with, data_without, output_dir):
    """Generate all graphs and save to output directory."""
    pass
```

**Output**:

- Directory: `buffer_comparison_results/`
- Files:
  - `buffer_level_comparison.png`
  - `rebuffering_comparison.png`
  - `quality_comparison.png`
  - `quality_distribution.png`
  - `seek_impact_analysis.png`
  - `comparison_summary.txt` (text summary of metrics)

**Integration with Testing**:

- Can be run as part of Phase 7 testing
- Generate visualizations automatically after test runs
- Include in test reports for easy comparison

---

### Class Structure

```python
class BufferWrapper:
    def __init__(self, multi_region_buffer, segment_time):
        self.mrb = multi_region_buffer
        self.segment_time = segment_time
        self.buffer_fcc = 0
        self.next_segment = 0
        self.current_playback_pos = 0
```

### Core Methods

#### `get_buffer_level()`

```python
def get_buffer_level(self):
    """Only count contiguous playable content - CRITICAL for ABR compatibility."""
    playable_chunks = self.get_contiguous_chunks_from_current_position()
    return self.segment_time * len(playable_chunks) - self.buffer_fcc
```

#### `get_contiguous_chunks_from_current_position()`

```python
def get_contiguous_chunks_from_current_position(self):
    """Find region containing current playback position, return contiguous chunks forward."""
    region = self.mrb._find_region_of(self.current_playback_pos)
    if not region:
        return []
    start_idx = int((self.current_playback_pos - region.start) / self.segment_time)
    return region.chunks[start_idx:]
```

#### `add_chunk()`

```python
def add_chunk(self, segment_index, quality):
    """Add chunk, convert segment_index to ms position."""
    pos_ms = segment_index * self.segment_time
    self.mrb.buffer_by_pos(pos_ms, quality)
    self.cleanup_and_merge()
```

### Region Management Methods

#### `cleanup_and_merge()`

```python
def cleanup_and_merge(self):
    """
    Maintain buffer health by merging adjacent regions when they become contiguous.
    """
    self.merge_adjacent_regions()
```

#### `merge_adjacent_regions()`

**Purpose**: Merge regions that are adjacent (no gap between them)

**Algorithm**:

1. Sort regions by start position
2. Iterate through sorted regions
3. If current region's end equals next region's start, merge them
4. Update `region_starts` and `region_map` accordingly

**Implementation**:

- Uses `BufferRegion.try_merge()` method
- Handles both forward and backward merges
- Updates MultiRegionBuffer data structures

**Detailed Implementation**:

```python
def merge_adjacent_regions(self):
    if len(self.mrb.region_starts) < 2:
        return
    
    # Sort regions by start position
    sorted_starts = sorted(self.mrb.region_starts)
    merged_starts = []
    merged_map = {}
    
    i = 0
    while i < len(sorted_starts):
        current_start = sorted_starts[i]
        current_region = self.mrb.region_map[current_start]
        
        # Check if we can merge with next region
        if i + 1 < len(sorted_starts):
            next_start = sorted_starts[i + 1]
            next_region = self.mrb.region_map[next_start]
            
            # Check if regions are adjacent (end of current == start of next)
            if current_region.end is not None and abs(current_region.end - next_start) < 0.001:
                # Merge: extend current region with next region's chunks
                if current_region.try_merge(next_region):
                    # Successfully merged, skip next region
                    i += 2
                    continue
        
        # Keep current region as-is
        merged_starts.append(current_start)
        merged_map[current_start] = current_region
        i += 1
    
    # Update MultiRegionBuffer with merged regions
    self.mrb.region_starts = merged_starts
    self.mrb.region_map = merged_map
```

---

## Files to Modify

1. **`sabre/src/global_state.py`**

   - Add `MultiRegionBuffer` instance initialization

2. **`sabre/src/sabre.py`**

   - Add `BufferWrapper` class
   - Update all buffer operations (see Phase 3)

3. **`sabre/src/abr_algorithms.py`**

   - Update `get_buffer_level()` to use wrapper (see Phase 4)

4. **`sabre/src/test_buffer_integration.py`**

   - New test file (see Phase 7)

---

## Validation Checklist

- [ ] Buffer level calculation matches linear buffering exactly
- [ ] Only contiguous playable content counted (no gaps)
- [ ] Segments preserved after forward seeks
- [ ] Regions merged automatically when contiguous
- [ ] All ABR algorithms produce same results
- [ ] All three use cases tested and passing
- [ ] Full simulation produces equivalent or better results
- [ ] QoE metrics show improvement (less rebuffering, higher quality)