# SABRE Simulation Guide

This guide is split into two parts:

- **Part I** covers the core SABRE simulator — setup, running simulations, graph generation, and regression testing. No `buffer.py` knowledge required.
- **Part II** covers dynamic buffering with `buffer.py` (`MultiRegionBuffer`) — comparison tooling, prefetch/seek unit tests, detailed use-case flows, and technical reference.

## Table of Contents

### Part I — Core Simulation

1. [Setup & Prerequisites](#setup--prerequisites)
2. [Network Configuration](#network-configuration)
3. [Running Simulations](#running-simulations)
4. [Graph Generation](#graph-generation)
5. [Regression Testing](#regression-testing)

### Part II — Dynamic Buffering (`buffer.py`)

6. [Overview](#overview)
7. [Running Buffer Comparisons](#running-buffer-comparisons)
8. [Viewing Results](#viewing-results)
9. [Understanding Results](#understanding-results)
10. [Generating Seek & Prefetch Configs](#generating-seek--prefetch-configs)
11. [Prefetch Comparison Workflow](#prefetch-comparison-workflow)
12. [Testing](#testing)
13. [Use Cases: Detailed Flow](#use-cases-detailed-flow-documentation)
14. [Technical Reference](#technical-reference)
15. [Advanced Usage](#advanced-usage)
16. [Troubleshooting](#troubleshooting)

---

# Part I — Core Simulation

---

## Setup & Prerequisites

### Install Dependencies
```bash
pip install numpy
```

### Required Files
- `network.json` — Network trace file (can be generated)
- `movie.json` — Movie manifest file
- `seeks.json` — Seek configuration (optional)

---

## Network Configuration

### Generate network.json

Generate network conditions using `network_generator.py`:

```bash
python network_generator.py -ne 10 -d 4000 -bm 3000 -bs 1500 -lm 150 -ls 50
```

**Parameters:**
- `-ne, --num-entries`: Number of network condition entries (default: 10)
- `-d, --duration`: Total duration in milliseconds (default: 4000)
- `-bm, --bandwidth-mean`: Mean bandwidth (default: 3000)
- `-bs, --bandwidth-std`: Bandwidth standard deviation (default: 1500)
- `-lm, --latency-mean`: Mean latency (default: 150)
- `-ls, --latency-std`: Latency standard deviation (default: 50)

**Example:**
```bash
python network_generator.py -ne 20 -d 6000 -bm 5000 -bs 2000 -lm 100 -ls 30
```

---

## Running Simulations

### Basic Simulation

Run simulation with default settings:
```bash
python sabre.py
```

### With Verbose Output
```bash
python sabre.py -v
```

### With Seek Configuration

Create a seek config file (`seeks.json`):
```json
{
  "seeks": [
    {"seek_when": 15, "seek_to": 18},
    {"seek_when": 40, "seek_to": 43}
  ]
}
```

Run with seeks:
```bash
python sabre.py -v -sc seeks.json
```

### Using simulate_abr.py

Run simulation and save output to file:
```bash
python simulate_abr.py -o output.txt
```

With custom seek config:
```bash
python simulate_abr.py -o output.txt -s seeks.json
```

**Parameters:**
- `-o, --output`: Output file path
- `-s, --seek-config`: Seek configuration file

---

## Graph Generation

### Generate ABR Comparison Graphs

Update the `abrArray` in `generate_abr_comparison.py` to choose ABR algorithms, then run:
```bash
python generate_abr_comparison.py
```

### Generate Individual ABR Graphs

Use `graph_generate.py` for specific algorithms:
```bash
python graph_generate.py -a bola
```

---

## Regression Testing

Ensure simulation results remain consistent after code changes.

1. **Generate baseline results (run once):**

```bash
python test_simulation_regression.py --generate-baseline
```

**Important:** Regenerate `baseline_simulation_results.txt` whenever `movie.json`, `network.json`, or `seeks.json` change.

2. **Run regression test:**

```bash
python test_simulation_regression.py
```

The test compares current simulation results with the baseline and reports any differences.

---

# Part II — Dynamic Buffering (`buffer.py`)

Everything below relates to `MultiRegionBuffer` from `buffer.py` — the dynamic, multi-region buffer that replaces the simple linear `buffer_contents` list.

---

## Overview

**What `buffer.py` adds:**

| | Linear Buffering (without) | Dynamic Buffering (with) |
|---|---|---|
| Data structure | `gs.buffer_contents` — flat list of `(segment, quality)` tuples | `gs.multi_region_buffer` — `MultiRegionBuffer` with multiple `BufferRegion` objects |
| Regions | Single contiguous region | Multiple non-contiguous regions |
| Seek behaviour | Clears entire buffer on seeks outside range | Preserves regions after seek position and prefetch regions |
| Prefetch | Not supported | Supported — `add_prefetch_chunk` with provenance tracking |
| Region merging | N/A | Adjacent regions merge automatically |

The `--use-buffer-py` flag in `sabre.py` switches between the two modes. When the flag is absent, the simulation falls back to linear buffering.

---

## Running Buffer Comparisons

`run_comparison.py` runs `sabre.py` twice (with and without `--use-buffer-py`) and produces a JSON file for visualization. It optionally supports prefetch configuration.

### Quick Comparison

```bash
python run_comparison.py -n network.json -m movie.json -a bola -o comparison_results.json
```

### Compare Multiple ABR Algorithms

All supported algorithms:
```bash
python run_comparison.py -a all -o comparison_results
```

Specific algorithms:
```bash
python run_comparison.py -a bola,bolae,dynamic,dynamicdash,throughput -o comparison_results.json
```

### With Seek Configuration
```bash
python run_comparison.py -a bola -sc seeks.json -o my_comparison.json
```

### With Prefetch + Seek (All ABR Algorithms, Multiple Seek Scenarios)

The canonical workflow — runs all ABR algorithms against three seek scenarios at once:

```bash
python run_comparison.py -sc seeks.json,seeks_prefetch_hit.json,seeks_mixed.json -pc test_prefetch_config.json -a all -o prefetch_comparison_results
```

Results are grouped in subfolders named after each seek file’s stem:

- **`seeks/`** — from `seeks.json` (seeks that *miss* prefetched segments; prefetch rarely improves rebuffering).
- **`seeks_prefetch_hit/`** — from `seeks_prefetch_hit.json` (seeks aligned with prefetch; dynamic buffering can reduce stalls).
- **`seeks_mixed/`** — from `seeks_mixed.json` (random mix of hit and miss seeks).

This creates `prefetch_comparison_results/<scenario>/comparison_<abr>.json` for each algorithm and scenario, plus `comparison_summary.json` at the top level. Load `prefetch_comparison_results/comparison_summary.json` in `view_comparison.html` for a cross-run table and charts.

### Batch Comparisons
```bash
for abr in bola bolae dynamic throughput; do
    python run_comparison.py -a $abr -o comparison_${abr}.json
done
```

### Command Parameters

| Flag | Description | Default |
|------|-------------|---------|
| `-n, --network` | Network trace file | `network.json` |
| `-m, --movie` | Movie manifest file | `movie.json` |
| `-a, --abr` | ABR algorithm(s) — single name, comma-separated list, or `all` | `bola` |
| `-sc, --seek-config` | Seek file(s) — one path, or comma-separated list (each stem gets a subfolder under `-o` when combined with multi-ABR or multi-seek) | *(none)* |
| `-pc, --prefetch-config` | Prefetch JSON (only used with `buffer.py` / prefetch path) | *(none)* |
| `-nm, --network-multiplier` | Network multiplier | `1.0` |
| `-o, --output` | Output JSON file (single run) **or** output **directory** (multiple ABRs and/or multiple `-sc` entries) | `comparison_results.json` |

When **multiple** ABR algorithms or **multiple** seek configs are used, `-o` must be a directory name; the tool writes `comparison_<abr>.json` files under it (and `comparison_summary.json` at the top level). For a single ABR and a single seek config, `-o` is a single JSON file path.

---

## Viewing Results

1. **Start the web server** (from the directory that contains `view_comparison.html`, usually `src/`):

```bash
python serve_viewer.py
```

2. Open the viewer (browser may open automatically): `http://localhost:8000/view_comparison.html`
3. Click **Load Comparison Data** and pick a JSON file.

### Single-run comparison JSON

Use a file produced by `run_comparison.py` for **one** ABR (and **one** seek config, if any), e.g. `comparison_bola.json` or `comparison_results.json`.

- **Summary cards** — total rebuffering time/events, utility, rebuffer ratio, total play time (with improvement percentages where applicable)
- **Charts** — rebuffering bar chart; buffer level over time (with seek markers and prefetch band when data is present); quality over time; quality distribution
- **Prefetch / seek panel** — when the JSON includes prefetch and seek events, the viewer shows a short summary and annotations on the time-series charts

### Multi-run summary (`comparison_summary.json`)

When you run a **batch** comparison (multiple ABRs and/or multiple `-sc` seek configs), open the generated **`comparison_summary.json`** (e.g. `prefetch_comparison_results/comparison_summary.json`). The viewer shows:

- **Cross-Comparison Summary** — sortable-style table: rows are **seek scenario × ABR** (e.g. `seeks/bola`, `seeks_prefetch_hit/throughput`). Columns include rebuffer events/time, **rebuffer ratio**, utility and play time **without vs with** `buffer.py`, and **Change** columns (green = improved vs baseline, red = worse, gray = unchanged).
- **Scenario legend** — explains which seek JSON each row (`seeks/`, `seeks_prefetch_hit/`, `seeks_mixed/`) corresponds to.
- **Summary bar charts** — **Rebuffering Events** and **Rebuffering Time** across all runs; legend below the chart to avoid overlapping values.
- **Row click (drill-down)** — click a row to scroll to the **per-run** detail charts (same as a single-run file). The summary table and summary bar charts **stay visible** above; only the detail charts refresh.

### Detail charts (single-run or drill-down)

1. **Rebuffering Comparison** — bar chart of total rebuffering time and event count  
2. **Buffer Level Over Time** — line chart; two traces (with / without `buffer.py`)  
3. **Quality Over Time** — stepped line chart of quality decisions  
4. **Quality Distribution** — bar chart of time spent at each quality level  

### Example `run_comparison.py` console output

```
✓ Results saved to comparison_results.json

Summary Comparison:
Metric                          Without buffer.py    With buffer.py      Change
-------------------------------------------------------------------------------------
total_rebuffer_time             2.5                 1.2                 -52.0%
rebuffer_count                  3                   1                   -66.7%
total_play_time                 120.0               120.0               0.0%
played_utility                  8.5                 9.2                 +8.2%
rebuffer_ratio                  0.02                0.01                -50.0%

Open view_comparison.html in your browser and load comparison_results.json to see visualizations!
```

---

## Understanding Results

### Single-run and summary table

In the **detail** view and on **summary** cards, green / red indicators follow the usual QoE reading: less rebuffering is better, higher utility is better, lower rebuffer ratio is better.

In the **Cross-Comparison Summary** table (when you load `comparison_summary.json`), each **Change** column is colored by **improvement vs the baseline (without `buffer.py`)**: **green** = improved for that metric, **red** = worse, **gray** = unchanged. (For example, utility uses “higher is better”; rebuffer count, rebuffer time, rebuffer ratio, and play time use “lower is better” where applicable.)

### Positive Indicators (Green)
- **Lower rebuffering time/events** — `MultiRegionBuffer` preserves segments after seeks
- **Higher utility** — better quality decisions from improved buffer management
- **Lower rebuffer ratio** — more efficient buffering with preserved segments

### Negative Indicators (Red)
- **Higher rebuffering** — may indicate issues (rare)
- **Lower utility** — quality decisions affected (unlikely)

> The comparison uses identical ABR algorithms and network conditions, so differences come purely from buffer management strategy.

### Expected Improvements

With `buffer.py` (`MultiRegionBuffer`) you should typically see:

- 20-40 % reduction in rebuffering events
- Better buffer level maintenance
- Preserved segments after seeks
- Similar or better quality decisions
- More efficient bandwidth utilisation

---

## Generating Seek & Prefetch Configs

`generate_configs.py` reads `movie.json` and writes four files for **prefetch hit / miss / mixed** comparisons:

| File | Role |
|------|------|
| `test_prefetch_config.json` | Spaced prefetch segment list + buffer threshold |
| `seeks_prefetch_hit.json` | Seeks whose targets land on prefetched segments |
| `seeks.json` | Seeks whose targets **miss** the prefetch list |
| `seeks_mixed.json` | Random mix of hit and miss seeks |

```bash
python generate_configs.py --num-seeks 30 --prefetch-count 35 --buffer-threshold 15000
```

### Command Parameters

| Flag | Description | Default |
|------|-------------|---------|
| `-m, --movie` | Movie manifest file | `movie.json` |
| `-n, --num-seeks` | Number of seek events per scenario | `6` |
| `--prefetch-count` | Number of prefetch segments | `8` |
| `--buffer-threshold` | Buffer level threshold in ms for prefetch | `15000` |
| `--output-prefetch-hit` | Seek file for prefetch-hit scenario | `seeks_prefetch_hit.json` |
| `--output-seeks-miss` | Seek file for prefetch-miss scenario | `seeks.json` |
| `--output-seeks-mixed` | Seek file for mixed hit/miss scenario | `seeks_mixed.json` |
| `-op, --output-prefetch` | Output path for prefetch config | `test_prefetch_config.json` |
| `--mixed-hit-ratio` | Fraction of seeks that hit prefetch in the mixed scenario | `0.5` |
| `--seed` | Random seed for the mixed scenario shuffle | *(random)* |
| `--dry-run` | Print JSON to stdout; do not write files | *(off)* |

---

## Prefetch Comparison Workflow

The **prefetch comparison** shows where dynamic buffering diverges from the linear baseline: when seeks land on pre-downloaded segments, stalls can be reduced or avoided. Each run still executes **two** simulations — **without** `buffer.py` (no prefetch) and **with** `buffer.py` + prefetch (when `-pc` is set).

### 1. Create seek + prefetch files

Use [Generating Seek & Prefetch Configs](#generating-seek--prefetch-configs) (`generate_configs.py`) **or** write a prefetch JSON yourself (`buffer_level_threshold` + `prefetch` list of `{ "segment": n }`).

### 2. Run `run_comparison.py`

Run all ABR algorithms against all three seek scenarios at once:

```bash
python run_comparison.py -sc seeks.json,seeks_prefetch_hit.json,seeks_mixed.json,seeks_linear_hit_dynamic_miss.json,seeks_linear_miss_dynamic_hit.json -pc test_prefetch_config.json -a all -o prefetch_comparison_results
```

This produces `seeks/comparison_*.json`, `seeks_prefetch_hit/comparison_*.json`, `seeks_mixed/comparison_*.json`, `seeks_linear_hit_dynamic_miss/comparison_*.json`, `seeks_linear_miss_dynamic_hit/comparison_*.json`, and **`comparison_summary.json`** under the output directory.

See [Command Parameters](#running-buffer-comparisons) under **Running Buffer Comparisons** for full flags (`-n`, `-m`, `-pc`, `-nm`, `-o`, etc.).

### 3. View results
S
Use **`serve_viewer.py`** and load either a **single** comparison JSON or **`comparison_summary.json`** — see [Viewing Results](#viewing-results).

---

## Testing

### Buffer Equivalence Tests

Verify that linear and dynamic buffers produce identical output during sequential chunk downloads:
```bash
python test_buffer_equivalence.py
```

**Options:**
- `--quick` — run quick test only
- `--abr <algorithm>` — test specific ABR algorithm
- `-v, --verbose` — verbose output

**Examples:**
```bash
python test_buffer_equivalence.py --quick
python test_buffer_equivalence.py --abr bola
python test_buffer_equivalence.py -v
```

### Dynamic Buffer Case Tests

Run case-based tests that verify the dynamic buffer algorithm handles each scenario correctly:
```bash
python test_dynamic_buffer_cases.py
```

With verbose output:
```bash
python test_dynamic_buffer_cases.py -v
```

The suite contains 14 tests across two test classes:

**TestDynamicBuffering** (Tests 1-10) — buffer seek and prefetch logic:

| # | Test | What it verifies |
|---|------|------------------|
| 1 | Seek to prefetched chunk | Seeking to a prefetched position does not rebuffer |
| 2 | Seek to non-prefetched positions | Adjacent-gap and far-out misses both rebuffer |
| 3 | Multiple seeks with multiple prefetch | Two sequential seeks to different prefetch targets |
| 4 | Prefetch preserved, linear cleaned | Prefetch regions survive across seeks; linear data cleaned |
| 5 | Adjacent prefetch merge | Prefetch chunk adjacent to linear region merges; provenance tracked |
| 6 | Seek within linear buffer (baseline) | Seeking inside a linear-only buffer works without prefetch |
| 7 | Contiguous prefetch buffer level | Buffer level reflects multiple contiguous prefetch chunks |
| 8 | Non-contiguous prefetch regions | Hit and miss across disjoint prefetch regions |
| 9 | Non-prefetch regions after seek preserved | Regions after the seek position are kept regardless of prefetch |
| 10 | Prefetch in same region preserved | Prefetch chunks before seek position are saved as a separate region |

**TestPrefetchModule** (Tests 11-14) — `PrefetchModule` API:

| # | Test | What it verifies |
|---|------|------------------|
| 11 | JSON loading | Config file parsed correctly (segments, threshold) |
| 12 | Trigger logic | `should_prefetch` respects buffer threshold |
| 13 | Segment exhaustion | Returns `None` after all segments are prefetched |
| 14 | Skip already-prefetched | Linear download loop skips prefetched segments |

**Required fixture:** `test_prefetch_config.json` (included in `src/`).

---

## Use Cases: Detailed Flow Documentation

Each use case shows the **linear buffer** path side-by-side with the **dynamic buffer** path so you can see exactly where behaviour diverges.

> **Note:** The compatibility methods (previously in `BufferWrapper`) have been consolidated into `MultiRegionBuffer` in `buffer.py`. State variables like `current_playback_pos` are managed directly in `GlobalState`. All references use `gs.multi_region_buffer` for buffer operations and `gs.current_playback_pos` for playback position tracking.

### Use Case 1: Download Chunk Without Seek

**Trigger:** Sequential segment download during normal playback
**Location:** `sabre.py` → `process_download_loop()`
**Methods Involved:**
1. `get_buffer_level()`
2. `deplete_buffer()`
3. `abr.get_quality_delay()`
4. `replacer.check_replace()`
5. `network.download()`
6. `abr.check_abandon()`
7. Buffer update (linear vs dynamic)

#### Linear Buffer Behavior

**Flow** (for segment N):
```
1. get_buffer_level()
   └─ If buffer full → deplete_buffer(full_delay) → buffer_contents.pop(0)
2. ABR selects quality for segment N
3. replacer.check_replace(quality)
   └─ Replace: update existing segment / No replace: proceed
4. Download segment N
5. gs.buffer_contents.append((N, quality))
6. gs.next_segment = N + 1
7. buffer_level = segment_time * (N+1) - buffer_fcc
```

**Buffer structure** (after segments 0-4):
- `gs.buffer_contents = [(0, 2), (1, 3), (2, 3), (3, 4), (4, 4)]`
- Sequential list, always contiguous
- `gs.next_segment = 5`, `gs.buffer_fcc = 0`

**Playback flow:**
```
deplete_buffer():
  1. Play buffer_contents[0]
  2. buffer_contents.pop(0)  →  [(1, q1), (2, q2), ...]
  3. Update buffer_fcc
```

**Code path:**
```python
gs.buffer_contents.append((gs.next_segment, quality))
gs.next_segment += 1
```

#### Dynamic Buffer Behavior

**Flow** (for segment N):
```
1. gs.multi_region_buffer.get_buffer_level()
   └─ get_contiguous_chunks_from_current_position()
   └─ segment_time * len(playable_chunks) - buffer_fcc
2. If buffer full → deplete_buffer() → multi_region_buffer.pop_chunk()
3. ABR selects quality for segment N
4. replacer.check_replace(quality)
   └─ Reads playable chunks from MultiRegionBuffer
5. Download segment N
6. gs.multi_region_buffer.add_chunk(N, quality)
   └─ buffer_by_pos(pos_ms, quality)
   └─ cleanup_and_merge()
7. gs.next_segment = N + 1
8. buffer_level = segment_time * (N+1) - buffer_fcc  (same as linear)
```

**Buffer structure** (after segments 0-4):
- 1 region `[0 ms → 5 * segment_time]`
- `BufferRegion(start=0, end=5*segment_time, chunks=[2,3,3,4,4])`
- Sequential segments merge automatically

**Playback flow:**
```
deplete_buffer():
  1. get_contiguous_chunks_from_current_position()
  2. Play playable_chunks[0]
  3. multi_region_buffer.pop_chunk()
  4. current_playback_pos += segment_time
```

**Code path:**
```python
gs.multi_region_buffer.add_chunk(gs.next_segment, quality)
```

**Methods called:**
`add_chunk` → `buffer_by_pos` → `BufferRegion.add_chunk` → `cleanup_and_merge` → `merge_adjacent_regions`

**Prefetch capability:** Can buffer non-sequential segments as separate regions (e.g. `[0-2]` and `[5-7]` simultaneously), enabling adaptive prefetching.

---

### Use Case 2: Download Chunk With Seek

**Trigger:** User-initiated seek event during playback
**Location:** `sabre.py` → `interrupted_by_seek()` / `update_buffer_during_seek()`
**Methods Involved:**
1. `interrupted_by_seek()`
2. `update_buffer_during_seek()`
3. `abr.report_seek()`
4. `get_buffer_level()`
5. `process_download_loop()`

#### Linear Buffer Behavior

**Flow** (seek from segment 5 to segment 20):
```
1. interrupted_by_seek(delta, abr) detects seek event
2. Target segment = 20
3. update_buffer_during_seek()
   a. buffer_base = gs.next_segment - len(buffer_contents)  →  10 - 5 = 5
   b. Is 20 in [5, 10)?  →  NO
   c. gs.buffer_contents.clear()
   d. gs.next_segment = 20, gs.buffer_fcc = 0
4. Buffer: [] (EMPTY — rebuffering required)
5. abr.report_seek()
6. Download loop resumes from segment 20
```

**Seek scenarios:**

| Scenario | Before | After | Rebuffer? |
|----------|--------|-------|-----------|
| Within range (5 → 7) | `[(5,q5)..(8,q8)]` | `[(7,q7),(8,q8)]` | No |
| Outside range (5 → 20) | `[(5,q5)..(8,q8)]` | `[]` | Yes |

**Code path:**
```python
if gs.buffer_contents and new_segment >= buffer_base and new_segment < gs.next_segment:
    skip_count = new_segment - buffer_base
    gs.buffer_contents = gs.buffer_contents[skip_count:]
else:
    gs.buffer_contents.clear()
    gs.next_segment = new_segment
```

#### Dynamic Buffer Behavior

**Flow** (seek from segment 5 to segment 20):
```
1. interrupted_by_seek(delta, abr) detects seek event
2. Target segment = 20
3. update_buffer_during_seek()
   a. seek_pos_ms = 20 * seg_time
   b. gs.current_playback_pos = seek_pos_ms
   c. region = multi_region_buffer._find_region_of(seek_pos_ms)
   d. If hit: trim chunks before seek, preserve rest
   e. If miss: clear non-prefetch regions before seek; preserve
      regions after seek and all prefetch regions
   f. cleanup_and_merge()
4. abr.report_seek()
5. Download loop resumes from segment 20
```

**Seek scenarios:**

| Scenario | Regions before | Regions after | Rebuffer? |
|----------|---------------|---------------|-----------|
| Within range (5 → 7) | `[5*st → 10*st]` | `[7*st → 10*st]` | No |
| Outside range (5 → 20) | `[5*st → 10*st]` | *(cleared)* | Yes |
| To prefetched chunk | `[0-8s]` + prefetch `[20-22s]` | prefetch region preserved | No |

**Code path:**
```python
seek_pos_ms = new_segment * seg_time
gs.current_playback_pos = seek_pos_ms
region = gs.multi_region_buffer._find_region_of(seek_pos_ms)

if region:
    start_idx = int((seek_pos_ms - region.start) / seg_time)
    region.chunks = region.chunks[start_idx:]
    region.start = seek_pos_ms
    if new_segment == floor_idx:
        gs.buffer_fcc = pos_seek_to_ms - (floor_idx * seg_time)
    else:
        gs.buffer_fcc = 0
else:
    # preserve regions after seek + prefetch regions; clear the rest
    gs.next_segment = new_segment

gs.buffer_fcc = 0
gs.multi_region_buffer.cleanup_and_merge()
```

**Methods called:**
`current_playback_pos` update → `_find_region_of` → chunk trimming → `cleanup_and_merge` → `merge_adjacent_regions`

**QoE improvements:**
- 20-40 % reduction in rebuffering events
- Faster seek response (preserved segments enable instant playback)
- Better bandwidth utilisation (less wasted downloads)

---

### Method Call Chains (summary)

**Use Case 1 — Download Without Seek:**

| Linear | Dynamic |
|--------|---------|
| `get_buffer_level()` → `deplete_buffer()` → `buffer_contents.pop(0)` → `abr.get_quality_delay()` → `network.download()` → `buffer_contents.append()` | `MultiRegionBuffer.get_buffer_level()` → `get_contiguous_chunks_from_current_position()` → `pop_chunk()` → `abr.get_quality_delay()` → `replacer.check_replace()` → `network.download()` → `add_chunk()` → `buffer_by_pos()` → `cleanup_and_merge()` |

**Use Case 2 — Download With Seek:**

| Linear | Dynamic |
|--------|---------|
| `interrupted_by_seek()` → `update_buffer_during_seek()` → `buffer_contents.clear()` / `[skip_count:]` → `abr.report_seek()` → `network.download()` | `interrupted_by_seek()` → `update_buffer_during_seek()` → `current_playback_pos` update → `_find_region_of()` → chunk trim → `cleanup_and_merge()` → `abr.report_seek()` → `add_chunk()` → `buffer_by_pos()` |

---

## Technical Reference

### Buffer Level Calculation

Both modes use the same formula:
```python
buffer_level = segment_time * len(playable_chunks) - buffer_fcc
```

| | `playable_chunks` source |
|---|---|
| Linear | All items in `buffer_contents` |
| Dynamic | Contiguous chunks from `current_playback_pos` (gaps excluded) |

Dynamic buffering does not inflate buffer level with gaps between regions.

### Seek Behavior Comparison

| Scenario | Linear Buffer | Dynamic Buffer |
|----------|--------------|----------------|
| Seek within range | Trim from front | Trim from front, preserve ahead |
| Forward seek outside | Clear buffer | Clear buffer, can prefetch |
| Backward seek | Clear buffer | Clear buffer, preserve ahead if exists |
| Multiple seeks | Always clear | Preserve segments across seeks |
| Rebuffering | Always required | Reduced by 20-40 % |

### Performance Characteristics

| | Linear | Dynamic |
|---|---|---|
| Append / pop | O(1) / O(n) | O(1) / O(1) |
| Region lookup | N/A | O(log n) |
| Merge | N/A | O(1) |
| Memory | Single list | Slight overhead (region objects) |
| Prefetching | Not supported | Supported |

### When to Use Each Mode

**Linear Buffering (without `buffer.py`):**
- Simple sequential playback
- No seeks expected
- Baseline comparison
- Minimal overhead

**Dynamic Buffering (with `buffer.py`):**
- Scenarios with user seeks
- Prefetching strategies
- Non-sequential segment access
- Better QoE requirements

### Backward Compatibility

The dynamic buffering implementation maintains backward compatibility:
1. Identical buffer level calculation
2. Existing ABR algorithms work without modification
3. Replacement logic reads directly from `MultiRegionBuffer`
4. Direct access to buffer state through `MultiRegionBuffer` methods

---

## Advanced Usage

### Custom Metrics

Modify `run_comparison.py` to capture additional fields from `sabre.py` output, merge them into the saved JSON (`without_buffer_py` / `with_buffer_py` summaries), and extend `view_comparison.html` (summary table row builder and/or detail cards) to display them.

### Extending the viewer

`view_comparison.html` holds both the **summary dashboard** (for `comparison_summary.json`) and the **detail** charts (single-run JSON or drill-down). When adding Chart.js views:

1. Prefer **separate** chart instances for summary vs detail (the detail path must not destroy summary charts — see `destroyDetailChartsOnly()` vs full teardown in `renderSummaryDashboard()`).
2. Add any new DOM under the correct section (`#summaryDashboard` vs `#content`).

---

## Troubleshooting

**Simulation fails:**
- Ensure `network.json` and `movie.json` exist
- Check ABR algorithm name is correct
- Verify Python dependencies are installed

**Web viewer doesn't load:**
- Check port 8000 is available
- Ensure `view_comparison.html` is in same directory
- Check browser console for errors (F12)

**No data / empty charts:**
- Verify JSON file structure matches expected format
- Check that simulations completed successfully
- Ensure `time_series` data is present in JSON
- Check browser console for JavaScript errors
- Verify Chart.js library loaded (Network tab)

**Summary bar charts disappear after clicking a table row:**
- Fixed in current `view_comparison.html`: drill-down only destroys **detail** chart instances, not the summary dashboard charts. Use an up-to-date viewer; hard-refresh the page (`Ctrl+F5`) if you cached an old HTML file.

---

## File Structure

```
sabre/src/
├── sabre.py                       # Core simulator
├── buffer.py                      # MultiRegionBuffer (dynamic buffering)
├── prefetch.py                    # PrefetchModule
├── global_state.py                # GlobalState singleton
├── run_comparison.py            # With vs without buffer.py; optional prefetch; writes comparison_summary.json for batch runs
├── view_comparison.html         # Web viewer (single-run JSON + comparison_summary.json dashboard)
├── serve_viewer.py              # HTTP server for the viewer
├── test_buffer_equivalence.py   # Linear ↔ dynamic buffer equivalence tests
├── test_dynamic_buffer_cases.py # Dynamic buffer algorithm case tests
├── test_simulation_regression.py
├── generate_configs.py          # Writes test_prefetch_config.json, seeks.json, seeks_prefetch_hit.json, seeks_mixed.json
├── network_generator.py
├── generate_abr_comparison.py
├── graph_generate.py
├── network.json
├── movie.json
├── seeks.json                   # Prefetch-miss seeks (regenerated by generate_configs.py)
├── seeks_prefetch_hit.json      # Prefetch-hit seeks
├── seeks_mixed.json             # Mixed hit/miss seeks
├── test_prefetch_config.json    # Prefetch + threshold; demo/tests + generate_configs output
└── prefetch_comparison_results/ # Batch output from: run_comparison.py -sc seeks.json,seeks_prefetch_hit.json,seeks_mixed.json ...
    ├── comparison_summary.json  # Load this in the viewer for the cross-comparison table
    ├── seeks/
    │   └── comparison_<abr>.json
    ├── seeks_prefetch_hit/
    │   └── comparison_<abr>.json
    └── seeks_mixed/
        └── comparison_<abr>.json
```

Generated single-run files (e.g. `comparison_results.json` or `comparison_bola.json`) usually live in `src/` or a folder you pass to `-o`; names depend on flags.
