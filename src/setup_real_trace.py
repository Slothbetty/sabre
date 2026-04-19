#!/usr/bin/env python3
"""
Given a parsed trace UUID, auto-generate the 5 prefetch scenario configs
and update TRACE_UUID in run_real_trace_comparison.py.

Usage:
    python setup_real_trace.py <uuid>

Run parse_real_traces.py first to produce seeks_<uuid>.json and
network_<uuid>.json, then run this script before run_real_trace_comparison.py.
"""

import json
import math
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BUFFER_THRESHOLD = 3500       # ms — must be reachable on throttled network
MIN_SIGNIFICANT_SEEK_S = 5.0  # seconds gap to count as a meaningful forward seek
FAR_MISS_OFFSET = 13          # segments past destination for "wrong target" scenarios


def load_json(path):
    with open(path) as f:
        return json.load(f)


def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  wrote {path.relative_to(SCRIPT_DIR)}")


def make_config(threshold, segments):
    return {
        "buffer_level_threshold": threshold,
        "prefetch": [{"segment": s} for s in segments],
    }


def find_miss_segs(all_dest_segs, num_segments):
    """Return [s, s+1] from the longest run of non-destination segments."""
    dest_set = set(all_dest_segs)
    best_start, best_len = None, 0
    run_start, run_len = None, 0
    for seg in range(num_segments):
        if seg not in dest_set:
            if run_start is None:
                run_start = seg
            run_len += 1
        else:
            if run_len > best_len:
                best_len, best_start = run_len, run_start
            run_start, run_len = None, 0
    if run_len > best_len:
        best_len, best_start = run_len, run_start

    if best_start is None or best_len < 2:
        raise ValueError("Cannot find 2 consecutive non-destination segments")

    mid = best_start + (best_len - 2) // 2
    return [mid, mid + 1]


def main():
    if len(sys.argv) < 2:
        print("Usage: python setup_real_trace.py <uuid>")
        sys.exit(1)

    uuid = sys.argv[1]
    seeks_path = SCRIPT_DIR / "real_trace" / f"seeks_{uuid}.json"

    if not seeks_path.exists():
        print(f"ERROR: {seeks_path} not found. Run parse_real_traces.py first.")
        sys.exit(1)

    seeks = load_json(seeks_path).get("seeks", [])

    movie = load_json(SCRIPT_DIR / "synthetic" / "movie.json")
    seg_s = movie["segment_duration_ms"] / 1000.0
    num_segments = len(movie["segment_sizes_bits"])

    all_dest_segs = [math.floor(s["seek_to"] / seg_s) for s in seeks]

    main_seek = max(seeks, key=lambda s: s["seek_to"] - s["seek_when"], default=None)
    if main_seek is None or (main_seek["seek_to"] - main_seek["seek_when"]) < MIN_SIGNIFICANT_SEEK_S:
        print("WARNING: No forward seek > 5 s found. Prefetch configs may not be meaningful.")

    main_dest = math.floor(main_seek["seek_to"] / seg_s) if main_seek else 0
    far_miss = min(main_dest + FAR_MISS_OFFSET, num_segments - 5)

    print(f"UUID:              {uuid}")
    print(f"Segment duration:  {seg_s}s  ({num_segments} segments total)")
    print(f"Seek destinations: {all_dest_segs} (segments)")
    if main_seek:
        print(f"Main seek:         {main_seek['seek_when']:.1f}s → {main_seek['seek_to']:.1f}s  (segment {main_dest})")
    print()

    cfg_dir = SCRIPT_DIR / "real_trace"

    miss_segs = find_miss_segs(all_dest_segs, num_segments)
    write_json(cfg_dir / "prefetch_config_real_seeks_miss.json",
               make_config(BUFFER_THRESHOLD, miss_segs))

    write_json(cfg_dir / "prefetch_config_real_prefetch_hit.json",
               make_config(BUFFER_THRESHOLD, [main_dest, main_dest + 1]))

    write_json(cfg_dir / "prefetch_config_real_mixed.json",
               make_config(BUFFER_THRESHOLD, [main_dest, main_dest + 1, far_miss, far_miss + 1]))

    write_json(cfg_dir / "prefetch_config_real_linear_hit_dynamic_miss.json",
               make_config(BUFFER_THRESHOLD, list(range(far_miss, far_miss + 5))))

    write_json(cfg_dir / "prefetch_config_real_linear_miss_dynamic_hit.json",
               make_config(BUFFER_THRESHOLD, list(range(main_dest, main_dest + 4))))

    # Update TRACE_UUID in run_real_trace_comparison.py
    runner = SCRIPT_DIR / "run_real_trace_comparison.py"
    text = runner.read_text()
    updated = re.sub(r'TRACE_UUID\s*=\s*"[^"]*"', f'TRACE_UUID = "{uuid}"', text)
    runner.write_text(updated)
    print(f"\n  updated TRACE_UUID in run_real_trace_comparison.py → {uuid}")
    print("\nDone. Run: python run_real_trace_comparison.py")


if __name__ == "__main__":
    main()
