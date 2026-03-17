#!/usr/bin/env python3
"""
Auto-generate seeks.json and test_prefetch_config.json for SABRE simulations.

Reads movie.json to determine segment count and duration, then generates
seek events and a matching prefetch config so that seeks land on
pre-downloaded segments (avoiding rebuffering with dynamic buffering).

Usage
-----
# Generate with defaults (3 random seeks, matching prefetch):
    python generate_configs.py

# 5 uniformly-spaced seeks:
    python generate_configs.py --num-seeks 5 --pattern uniform

# Random seeks with a fixed seed for reproducibility:
    python generate_configs.py --num-seeks 4 --pattern random --seed 42

# Forward-only seeks (each seek_to > previous seek_to):
    python generate_configs.py --pattern forward

# Custom buffer threshold (ms) for prefetch triggering:
    python generate_configs.py --buffer-threshold 15000

# Skip prefetch config generation:
    python generate_configs.py --no-prefetch

# Custom output paths:
    python generate_configs.py -os my_seeks.json -op my_prefetch.json

# Dry-run (print to stdout, don't write files):
    python generate_configs.py --dry-run
"""

import argparse
import json
import math
import random
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


def generate_seeks_uniform(
    num_seeks: int, total_s: float, seg_dur_ms: int, num_segments: int
) -> list[dict]:
    """Space seeks evenly across the movie timeline."""
    margin_s = seg_dur_ms / 1000.0 * 3
    usable = total_s - 2 * margin_s
    if usable <= 0 or num_seeks < 1:
        return []

    step = usable / (num_seeks + 1)
    seeks = []
    for i in range(1, num_seeks + 1):
        seek_when = round(margin_s + step * i, 1)
        jump_s = step * 0.8
        seek_to = round(min(seek_when + jump_s, total_s - margin_s), 1)
        if seek_to <= seek_when:
            seek_to = round(min(seek_when + seg_dur_ms / 1000.0, total_s - 1), 1)
        seeks.append({"seek_when": seek_when, "seek_to": seek_to})
    return seeks


def generate_seeks_random(
    num_seeks: int, total_s: float, seg_dur_ms: int, num_segments: int
) -> list[dict]:
    """Generate random seek events, sorted by seek_when."""
    margin_s = seg_dur_ms / 1000.0 * 3
    lo = margin_s
    hi = total_s - margin_s
    if hi <= lo or num_seeks < 1:
        return []

    when_times = sorted(random.uniform(lo, hi) for _ in range(num_seeks))
    min_gap = seg_dur_ms / 1000.0 * 2
    for i in range(1, len(when_times)):
        if when_times[i] - when_times[i - 1] < min_gap:
            when_times[i] = when_times[i - 1] + min_gap

    seeks = []
    for w in when_times:
        if w >= hi:
            break
        to_lo = max(0, w - total_s * 0.3)
        to_hi = min(total_s - margin_s, w + total_s * 0.3)
        seek_to = random.uniform(to_lo, to_hi)
        while abs(seek_to - w) < seg_dur_ms / 1000.0:
            seek_to = random.uniform(to_lo, to_hi)
        seeks.append({
            "seek_when": round(w, 1),
            "seek_to": round(seek_to, 1),
        })
    return seeks


def generate_seeks_forward(
    num_seeks: int, total_s: float, seg_dur_ms: int, num_segments: int
) -> list[dict]:
    """Generate forward-only seeks (skip-ahead pattern, like ad-skipping)."""
    margin_s = seg_dur_ms / 1000.0 * 3
    usable = total_s - 2 * margin_s
    if usable <= 0 or num_seeks < 1:
        return []

    chunk = usable / (num_seeks + 1)
    seeks = []
    cursor = margin_s
    for _ in range(num_seeks):
        seek_when = round(cursor + chunk * 0.6, 1)
        seek_to = round(cursor + chunk, 1)
        if seek_to >= total_s - margin_s:
            break
        seeks.append({"seek_when": seek_when, "seek_to": seek_to})
        cursor = seek_to
    return seeks


PATTERNS = {
    "uniform": generate_seeks_uniform,
    "random": generate_seeks_random,
    "forward": generate_seeks_forward,
}


def build_prefetch_config(
    seeks: list[dict],
    seg_dur_ms: int,
    num_segments: int,
    buffer_threshold_ms: int,
) -> dict:
    """Build a prefetch config whose segments match the seek destinations."""
    seen = set()
    prefetch_segments = []
    for s in seeks:
        idx = segment_index_for_time(s["seek_to"], seg_dur_ms)
        idx = max(0, min(idx, num_segments - 1))
        if idx not in seen:
            seen.add(idx)
            prefetch_segments.append(idx)

    return {
        "buffer_level_threshold": buffer_threshold_ms,
        "prefetch": [{"segment": seg} for seg in sorted(prefetch_segments)],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Auto-generate seeks.json and test_prefetch_config.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-m", "--movie", default="movie.json",
        help="Movie manifest file (default: movie.json)",
    )
    parser.add_argument(
        "-n", "--num-seeks", type=int, default=3,
        help="Number of seek events to generate (default: 3)",
    )
    parser.add_argument(
        "-p", "--pattern", choices=PATTERNS.keys(), default="random",
        help="Seek generation pattern (default: random)",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--buffer-threshold", type=int, default=20000,
        help="Buffer level threshold in ms for prefetch triggering (default: 20000)",
    )
    parser.add_argument(
        "--no-prefetch", action="store_true",
        help="Skip generating prefetch config",
    )
    parser.add_argument(
        "-os", "--output-seeks", default="seeks.json",
        help="Output path for seeks config (default: seeks.json)",
    )
    parser.add_argument(
        "-op", "--output-prefetch", default="test_prefetch_config.json",
        help="Output path for prefetch config (default: test_prefetch_config.json)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print generated configs to stdout without writing files",
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

    if args.seed is not None:
        random.seed(args.seed)

    generator = PATTERNS[args.pattern]
    seeks = generator(args.num_seeks, total_s, seg_dur_ms, num_segments)

    if not seeks:
        print("Warning: no seek events generated (movie may be too short).", file=sys.stderr)

    seeks_config = {"seeks": seeks}

    print(f"\nGenerated {len(seeks)} seek event(s) using '{args.pattern}' pattern:")
    for i, s in enumerate(seeks, 1):
        seg_idx = segment_index_for_time(s["seek_to"], seg_dur_ms)
        print(f"  {i}. seek at {s['seek_when']}s -> {s['seek_to']}s (segment {seg_idx})")

    prefetch_config = None
    if not args.no_prefetch:
        prefetch_config = build_prefetch_config(
            seeks, seg_dur_ms, num_segments, args.buffer_threshold
        )
        print(f"\nPrefetch config: threshold={args.buffer_threshold}ms, "
              f"segments={[e['segment'] for e in prefetch_config['prefetch']]}")

    if args.dry_run:
        print("\n--- seeks.json ---")
        print(json.dumps(seeks_config, indent=2))
        if prefetch_config:
            print("\n--- test_prefetch_config.json ---")
            print(json.dumps(prefetch_config, indent=2))
        print("\n(dry run — no files written)")
        return

    seeks_path = script_dir / args.output_seeks
    with open(seeks_path, "w") as f:
        json.dump(seeks_config, f, indent=2)
        f.write("\n")
    print(f"\n-> Wrote {seeks_path}")

    if prefetch_config:
        prefetch_path = script_dir / args.output_prefetch
        with open(prefetch_path, "w") as f:
            json.dump(prefetch_config, f, indent=2)
            f.write("\n")
        print(f"-> Wrote {prefetch_path}")

    print("\nRun the comparison with:")
    seek_file = args.output_seeks
    if prefetch_config:
        pf_file = args.output_prefetch
        print(f"  python run_comparison.py -sc {seek_file} -pc {pf_file} -o prefetch_comparison_results.json")
    else:
        print(f"  python run_comparison.py -sc {seek_file} -o comparison_results.json")


if __name__ == "__main__":
    main()
