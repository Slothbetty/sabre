#!/usr/bin/env python3
"""
Generate prefetch + seek configs for SABRE comparison demos.

Writes three files in one run:
  - test_prefetch_config.json  — spaced prefetch segment list + buffer threshold
  - seeks_prefetch_hit.json    — seeks that land on prefetched segments
  - seeks.json                 — same seek_when schedule; seek_to miss prefetch

Usage
-----
    python generate_configs.py

    python generate_configs.py --num-seeks 6 --prefetch-count 8 --buffer-threshold 15000
"""

import argparse
import json
import math
import sys
from pathlib import Path


def load_movie(movie_path: str) -> dict:
    with open(movie_path) as f:
        return json.load(f)


def movie_info(movie_data: dict) -> tuple[int, int, float]:
    """Return (num_segments, segment_duration_ms, total_duration_s)."""
    seg_dur_ms = movie_data["segment_duration_ms"]
    num_seg = len(movie_data["segment_sizes_bits"])
    total_s = num_seg * seg_dur_ms / 1000.0
    return num_seg, seg_dur_ms, total_s


def segment_index_for_time(time_s: float, seg_dur_ms: int) -> int:
    """Map a seek-to time (seconds) to the segment index the simulator will use."""
    pos_ms = time_s * 1000
    floor_idx = math.floor(pos_ms / seg_dur_ms)
    prev_boundary = floor_idx * seg_dur_ms
    delta = pos_ms - prev_boundary
    if delta < seg_dur_ms / 2:
        return floor_idx
    else:
        return floor_idx + 1


def build_spaced_prefetch_indices(num_segments: int, count: int) -> list[int]:
    """Pick `count` segment indices spread across the movie."""
    if count <= 0:
        return []
    margin = max(3, num_segments // 25)
    lo, hi = margin, num_segments - 1 - margin
    if hi <= lo:
        return [max(0, min(num_segments - 1, num_segments // 2))]

    if count == 1:
        return [(lo + hi) // 2]

    out: list[int] = []
    for i in range(count):
        t = i / (count - 1)
        idx = int(round(lo + t * (hi - lo)))
        idx = max(0, min(num_segments - 1, idx))
        out.append(idx)
    seen: set[int] = set()
    unique: list[int] = []
    for idx in sorted(out):
        if idx not in seen:
            seen.add(idx)
            unique.append(idx)
    while len(unique) < count and len(unique) < num_segments:
        for j in range(num_segments):
            if j not in seen:
                seen.add(j)
                unique.append(j)
                break
        else:
            break
    return sorted(unique[:count])


def seek_to_seconds_for_segment(seg_idx: int, seg_dur_ms: int) -> float:
    """
    Seek target time (seconds) in the first quarter of the segment so
    segment_index_for_time() in sabre matches seg_idx (midpoint can round up).
    """
    pos_ms = seg_idx * seg_dur_ms + seg_dur_ms * 0.25
    return round(pos_ms / 1000.0, 1)


def pick_spaced_subset(indices: list[int], count: int) -> list[int]:
    """Pick `count` values spread across sorted `indices` (may repeat if count > len)."""
    if not indices or count <= 0:
        return []
    idx_sorted = sorted(set(indices))
    if len(idx_sorted) <= count:
        out = []
        for i in range(count):
            out.append(idx_sorted[i % len(idx_sorted)])
        return out
    out = []
    for i in range(count):
        pos = int(round(i * (len(idx_sorted) - 1) / max(count - 1, 1)))
        out.append(idx_sorted[pos])
    return out


def build_seek_when_schedule(
    num_seeks: int, total_s: float, seg_dur_ms: int
) -> list[float]:
    """Spread seek_when times across playback (forward, non-overlapping)."""
    margin = seg_dur_ms / 1000.0 * 3
    if num_seeks < 1:
        return []
    hi = total_s - margin
    span = max(hi - margin - 40.0, num_seeks * 25.0)
    step = span / max(num_seeks + 1, 1)
    times = []
    t = margin + step * 0.8
    for _ in range(num_seeks):
        times.append(round(min(t, hi - 5.0), 1))
        t += step
    return times


def generate_seeks_for_segment_targets(
    segment_targets: list[int],
    seek_when_times: list[float],
    seg_dur_ms: int,
    num_segments: int,
) -> list[dict]:
    seeks = []
    for i, seg_idx in enumerate(segment_targets):
        seg_idx = max(0, min(num_segments - 1, seg_idx))
        st = seek_to_seconds_for_segment(seg_idx, seg_dur_ms)
        when = seek_when_times[i] if i < len(seek_when_times) else seek_when_times[-1]
        seeks.append({"seek_when": when, "seek_to": st})
    return seeks


def generate_comparison_bundle(
    num_seeks: int,
    total_s: float,
    seg_dur_ms: int,
    num_segments: int,
    buffer_threshold_ms: int,
    prefetch_count: int,
) -> tuple[dict, dict, dict]:
    """
    Build (test_prefetch_config, seeks_prefetch_hit, seeks_miss):
    one shared prefetch list; hit seeks land on prefetched segments;
    miss seeks land on segments outside that list.
    """
    prefetch_indices = build_spaced_prefetch_indices(num_segments, prefetch_count)
    prefetch_set = set(prefetch_indices)

    complement = [i for i in range(num_segments) if i not in prefetch_set]
    if len(complement) < num_seeks:
        raise ValueError(
            f"Not enough non-prefetched segments ({len(complement)}) for "
            f"{num_seeks} miss seeks — lower --prefetch-count or --num-seeks."
        )

    hit_targets = pick_spaced_subset(prefetch_indices, num_seeks)
    miss_targets = pick_spaced_subset(complement, num_seeks)

    schedule = build_seek_when_schedule(num_seeks, total_s, seg_dur_ms)

    seeks_hit = generate_seeks_for_segment_targets(
        hit_targets, schedule, seg_dur_ms, num_segments
    )
    seeks_miss = generate_seeks_for_segment_targets(
        miss_targets, schedule, seg_dur_ms, num_segments
    )

    prefetch_config = {
        "buffer_level_threshold": buffer_threshold_ms,
        "prefetch": [{"segment": s} for s in prefetch_indices],
    }

    return (
        prefetch_config,
        {"seeks": seeks_hit},
        {"seeks": seeks_miss},
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Write test_prefetch_config.json, seeks_prefetch_hit.json, and seeks.json "
            "(prefetch hit vs miss comparison)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-m", "--movie", default="movie.json",
        help="Movie manifest file (default: movie.json)",
    )
    parser.add_argument(
        "-n", "--num-seeks", type=int, default=6,
        help="Number of seek events per scenario (default: 6)",
    )
    parser.add_argument(
        "--prefetch-count",
        type=int,
        default=8,
        help="Number of prefetch segments (default: 8)",
    )
    parser.add_argument(
        "--buffer-threshold", type=int, default=15000,
        help="Buffer level threshold in ms (default: 15000)",
    )
    parser.add_argument(
        "-op", "--output-prefetch", default="test_prefetch_config.json",
        help="Output path for prefetch config (default: test_prefetch_config.json)",
    )
    parser.add_argument(
        "--output-prefetch-hit",
        default="seeks_prefetch_hit.json",
        help="Seek file for prefetch-hit scenario (default: seeks_prefetch_hit.json)",
    )
    parser.add_argument(
        "--output-seeks-miss",
        default="seeks.json",
        help="Seek file for prefetch-miss scenario (default: seeks.json)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print JSON to stdout; do not write files",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).parent
    movie_path = script_dir / args.movie
    if not movie_path.exists():
        print(f"Error: Movie file not found: {movie_path}", file=sys.stderr)
        sys.exit(1)

    movie_data = load_movie(str(movie_path))
    num_segments, seg_dur_ms, total_s = movie_info(movie_data)

    print(f"Movie: {num_segments} segments x {seg_dur_ms}ms = {total_s:.1f}s total")

    try:
        prefetch_config, seeks_hit_cfg, seeks_miss_cfg = generate_comparison_bundle(
            num_seeks=args.num_seeks,
            total_s=total_s,
            seg_dur_ms=seg_dur_ms,
            num_segments=num_segments,
            buffer_threshold_ms=args.buffer_threshold,
            prefetch_count=args.prefetch_count,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    pf_segs = [e["segment"] for e in prefetch_config["prefetch"]]
    print("\n--- Comparison bundle ---")
    print(f"Prefetch ({args.output_prefetch}): threshold={args.buffer_threshold}ms, "
          f"segments={pf_segs}")
    print(f"Seeks (hit):  {args.output_prefetch_hit} -> seek_to land on prefetched segments")
    print(f"Seeks (miss): {args.output_seeks_miss} -> same seek_when, seek_to miss prefetch")

    for label, cfg in (
        ("prefetch_hit", seeks_hit_cfg),
        ("prefetch_miss", seeks_miss_cfg),
    ):
        print(f"\n  {label}:")
        for i, s in enumerate(cfg["seeks"], 1):
            seg_idx = segment_index_for_time(s["seek_to"], seg_dur_ms)
            hit = "HIT" if seg_idx in set(pf_segs) else "miss"
            print(f"    {i}. when={s['seek_when']}s -> {s['seek_to']}s (seg {seg_idx}, {hit})")

    if args.dry_run:
        print("\n--- test_prefetch_config.json ---")
        print(json.dumps(prefetch_config, indent=2))
        print("\n--- seeks_prefetch_hit ---")
        print(json.dumps(seeks_hit_cfg, indent=2))
        print("\n--- seeks (miss) ---")
        print(json.dumps(seeks_miss_cfg, indent=2))
        print("\n(dry run — no files written)")
        return

    paths = [
        (script_dir / args.output_prefetch, prefetch_config),
        (script_dir / args.output_prefetch_hit, seeks_hit_cfg),
        (script_dir / args.output_seeks_miss, seeks_miss_cfg),
    ]
    for path, obj in paths:
        with open(path, "w") as f:
            json.dump(obj, f, indent=2)
            f.write("\n")
        print(f"\n-> Wrote {path}")

    print("\nRun multi-scenario comparison with:")
    print(
        f"  python run_comparison.py -sc {args.output_seeks_miss},"
        f"{args.output_prefetch_hit} -pc {args.output_prefetch} -a all -o prefetch_comparison_results"
    )


if __name__ == "__main__":
    main()
