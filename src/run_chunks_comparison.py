#!/usr/bin/env python3
"""
Pipeline 2 — Chunks-based ABR comparison runner.

Converts a video from chunks_1_200.json into a full 5-scenario ABR comparison
without needing any real browser trace. The synthetic network trace and all 5
seek + prefetch configs are generated automatically from the video's own data.

All generated inputs and results are written to chunks_trace/.

Usage:
    python run_chunks_comparison.py --index 0
    python run_chunks_comparison.py --video-id Qg9LxRHLbAk
    python run_chunks_comparison.py --index 4 --bandwidth-mean 2000 --bandwidth-std 500

Steps (all automatic):
    1. Extract movie.json from the chunks entry
    2. Generate a synthetic network trace to cover the video's duration
    3. Generate 5 seek files + prefetch_config.json via generate_configs.py
    4. Run run_comparison.py for all 5 scenarios x all ABR algorithms
    5. Results land in chunks_trace/results/comparison_summary.json
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from generate_configs import generate_comparison_bundle, movie_info

SCRIPT_DIR  = Path(__file__).parent
CHUNKS_DIR  = SCRIPT_DIR / "chunks_trace"

DEFAULT_CHUNKS         = "real_trace/chunks_1_200.json"
DEFAULT_BANDWIDTH_MEAN = 4000   # kbps
DEFAULT_BANDWIDTH_STD  = 1500
DEFAULT_LATENCY_MEAN   = 80     # ms
DEFAULT_LATENCY_STD    = 20
ENTRY_DURATION_MS      = 5000   # 5 s per network entry
NUM_NETWORK_ENTRIES    = 120    # 120 × 5 s = 600 s total, covers any video


# ── helpers ────────────────────────────────────────────────────────────────────

def run(cmd):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=SCRIPT_DIR)
    if result.returncode != 0:
        print(f"ERROR: command failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"  wrote {path.relative_to(SCRIPT_DIR)}")


def load_chunks_entry(chunks_path, index=None, video_id=None):
    with open(chunks_path, encoding="utf-8") as f:
        chunks = json.load(f)
    if not isinstance(chunks, list):
        raise ValueError(f"{chunks_path} must be a top-level JSON array")
    if index is not None:
        if not (0 <= index < len(chunks)):
            raise IndexError(f"index {index} out of range (0-{len(chunks) - 1})")
        return chunks[index]
    matches = [v for v in chunks if v.get("video_id") == video_id]
    if not matches:
        raise KeyError(f"video_id '{video_id}' not found in {chunks_path}")
    return matches[0]


def entry_to_movie(entry):
    return {
        "segment_duration_ms": entry["segment_duration_ms"],
        "bitrates_kbps":       entry["bitrates_kbps"],
        "segment_sizes_bits":  entry["segment_sizes_bits"],
    }


def generate_network(num_entries, duration_ms, bw_mean, bw_std, lat_mean, lat_std):
    rng = np.random.default_rng()
    entries = []
    for _ in range(num_entries):
        bw  = max(100, int(rng.normal(bw_mean,  bw_std)))
        lat = max(1,   int(rng.normal(lat_mean, lat_std)))
        entries.append({
            "duration_ms":    int(duration_ms),
            "bandwidth_kbps": bw,
            "latency_ms":     lat,
        })
    return entries


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Run 5-scenario ABR comparison from a chunks JSON video entry"
    )
    parser.add_argument(
        "--chunks", default=DEFAULT_CHUNKS, metavar="PATH",
        help=f"Chunks JSON file (default: {DEFAULT_CHUNKS})",
    )
    id_group = parser.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--index",    type=int, metavar="N", help="0-based video index")
    id_group.add_argument("--video-id", metavar="ID",          help="video_id string")

    parser.add_argument("--bandwidth-mean",   type=float, default=DEFAULT_BANDWIDTH_MEAN,
                        help=f"Mean network bandwidth in kbps (default: {DEFAULT_BANDWIDTH_MEAN})")
    parser.add_argument("--bandwidth-std",    type=float, default=DEFAULT_BANDWIDTH_STD,
                        help=f"Bandwidth std dev in kbps (default: {DEFAULT_BANDWIDTH_STD})")
    parser.add_argument("--latency-mean",     type=float, default=DEFAULT_LATENCY_MEAN,
                        help=f"Mean latency in ms (default: {DEFAULT_LATENCY_MEAN})")
    parser.add_argument("--latency-std",      type=float, default=DEFAULT_LATENCY_STD,
                        help=f"Latency std dev in ms (default: {DEFAULT_LATENCY_STD})")
    parser.add_argument("--num-seeks",        type=int,   default=6,
                        help="Seek events per scenario (default: 6)")
    parser.add_argument("--prefetch-count",   type=int,   default=8,
                        help="Number of prefetch segments (default: 8)")
    parser.add_argument("--buffer-threshold", type=int,   default=15000,
                        help="Buffer level threshold in ms for prefetch (default: 15000)")
    parser.add_argument("--seed",             type=int,   default=None,
                        help="Random seed for mixed-scenario shuffle")
    args = parser.parse_args()

    # ── 1. Extract movie ───────────────────────────────────────────────────────
    entry      = load_chunks_entry(args.chunks, index=args.index, video_id=args.video_id)
    movie_data = entry_to_movie(entry)
    num_segs, seg_dur_ms, total_s = movie_info(movie_data)
    vid   = entry.get("video_id", "?")
    title = entry.get("title", "")
    res   = (entry.get("resolutions") or ["?"])[-1]

    print(f"Video:   [{args.index if args.index is not None else args.video_id}] {vid}")
    print(f"Title:   {title}")
    print(f"Content: {num_segs} segments x {seg_dur_ms} ms = {total_s:.1f} s, up to {res}")
    print()

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(CHUNKS_DIR / "movie.json", movie_data)

    # ── 2. Generate synthetic network ──────────────────────────────────────────
    network = generate_network(
        NUM_NETWORK_ENTRIES, ENTRY_DURATION_MS,
        args.bandwidth_mean, args.bandwidth_std,
        args.latency_mean,   args.latency_std,
    )
    write_json(CHUNKS_DIR / "network.json", network)
    print(f"  ({NUM_NETWORK_ENTRIES} entries x {ENTRY_DURATION_MS} ms, "
          f"bw ~{args.bandwidth_mean}+/-{args.bandwidth_std} kbps, "
          f"lat ~{args.latency_mean}+/-{args.latency_std} ms)")

    # ── 3. Generate seek + prefetch configs ────────────────────────────────────
    print("\nGenerating seek and prefetch configs ...")
    (
        prefetch_cfg,
        seeks_hit_cfg,
        seeks_miss_cfg,
        seeks_mixed_cfg,
        seeks_lin_hit_dyn_miss_cfg,
        seeks_lin_miss_dyn_hit_cfg,
    ) = generate_comparison_bundle(
        num_seeks=args.num_seeks,
        total_s=total_s,
        seg_dur_ms=seg_dur_ms,
        num_segments=num_segs,
        buffer_threshold_ms=args.buffer_threshold,
        prefetch_count=args.prefetch_count,
        seed=args.seed,
    )

    seek_files = {
        "seeks.json":                         seeks_miss_cfg,
        "seeks_prefetch_hit.json":            seeks_hit_cfg,
        "seeks_mixed.json":                   seeks_mixed_cfg,
        "seeks_linear_hit_dynamic_miss.json": seeks_lin_hit_dyn_miss_cfg,
        "seeks_linear_miss_dynamic_hit.json": seeks_lin_miss_dyn_hit_cfg,
    }
    for fname, data in seek_files.items():
        write_json(CHUNKS_DIR / fname, data)

    write_json(CHUNKS_DIR / "prefetch_config.json", prefetch_cfg)
    pf_segs = [s["segment"] for s in prefetch_cfg["prefetch"]]
    print(f"  prefetch segments: {pf_segs}")

    # ── 4. Run all 5 scenarios ─────────────────────────────────────────────────
    sc_arg = ",".join(
        str((CHUNKS_DIR / f).relative_to(SCRIPT_DIR))
        for f in seek_files
    )
    run([
        sys.executable, "run_comparison.py",
        "-n", str((CHUNKS_DIR / "network.json").relative_to(SCRIPT_DIR)),
        "-m", str((CHUNKS_DIR / "movie.json").relative_to(SCRIPT_DIR)),
        "-sc", sc_arg,
        "-pc", str((CHUNKS_DIR / "prefetch_config.json").relative_to(SCRIPT_DIR)),
        "-a", "all",
        "-o", str((CHUNKS_DIR / "results").relative_to(SCRIPT_DIR)),
    ])

    print("\nDone. Load chunks_trace/results/comparison_summary.json in the viewer.")


if __name__ == "__main__":
    main()
