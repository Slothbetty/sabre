#!/usr/bin/env python3
"""
Run all 5 real-trace prefetch scenarios then merge into a single comparison_summary.json.

When a non-default movie is supplied (via --chunks or -m), prefetch configs for all
5 scenarios are regenerated automatically from the real seek events and the movie's
actual segment structure, so results are always meaningful regardless of movie length.

Usage:
    # Default: synthetic movie + pre-built prefetch configs
    python run_real_trace_comparison.py

    # Real movie from chunks file (configs regenerated automatically)
    python run_real_trace_comparison.py --chunks real_trace/chunks_1_200.json --index 0
    python run_real_trace_comparison.py --chunks real_trace/chunks_1_200.json --video-id Qg9LxRHLbAk

    # Explicit movie.json (configs regenerated automatically)
    python run_real_trace_comparison.py -m real_trace/my_movie.json
"""

import json
import subprocess
import sys
import tempfile
import argparse
from pathlib import Path

from setup_real_trace import build_prefetch_configs

SCRIPT_DIR = Path(__file__).parent
TRACE_UUID = "56329467-babb-4d75-bb58-70f3906369fe"

SCENARIOS = [
    "seeks_miss",
    "prefetch_hit",
    "mixed",
    "linear_hit_dynamic_miss",
    "linear_miss_dynamic_hit",
]

NETWORK = f"real_trace/network_{TRACE_UUID}.json"
SEEKS   = f"real_trace/seeks_{TRACE_UUID}.json"


# ── helpers ────────────────────────────────────────────────────────────────────

def run(cmd):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=SCRIPT_DIR)
    if result.returncode != 0:
        print(f"ERROR: command failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)


def load_json(path, encoding="utf-8"):
    with open(path, encoding=encoding) as f:
        return json.load(f)


def write_temp_json(data):
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False,
        dir=SCRIPT_DIR, encoding="utf-8",
    )
    json.dump(data, tmp)
    tmp.close()
    return Path(tmp.name)


def load_chunks_entry(chunks_path, index=None, video_id=None):
    chunks = load_json(chunks_path)
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


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Run 5 real-trace ABR comparison scenarios"
    )
    movie_group = parser.add_mutually_exclusive_group()
    movie_group.add_argument(
        "-m", "--movie", metavar="PATH",
        help="Path to a movie.json (configs regenerated automatically for this movie)",
    )
    movie_group.add_argument(
        "--chunks", metavar="PATH",
        help="Path to a chunks JSON (e.g. chunks_1_200.json); "
             "use with --index or --video-id",
    )
    parser.add_argument(
        "--index", type=int, metavar="N",
        help="0-based index of the video to use from --chunks",
    )
    parser.add_argument(
        "--video-id", metavar="ID",
        help="video_id of the video to use from --chunks",
    )
    args = parser.parse_args()

    tmp_files = []  # temp paths cleaned up in the finally block

    # ── resolve movie data and path ────────────────────────────────────────────
    if args.chunks:
        if args.index is None and args.video_id is None:
            parser.error("--chunks requires --index N or --video-id ID")

        entry = load_chunks_entry(
            args.chunks,
            index=args.index,
            video_id=args.video_id,
        )
        movie_data = entry_to_movie(entry)
        vid = entry.get("video_id", "?")
        res = (entry.get("resolutions") or ["?"])[-1]
        n   = len(movie_data["segment_sizes_bits"])
        dur = n * movie_data["segment_duration_ms"] / 1000
        print(f"Using video: [{args.index if args.index is not None else args.video_id}] "
              f"{vid} — {entry.get('title', '')}")
        print(f"  {n} segments x {movie_data['segment_duration_ms']} ms "
              f"= {dur:.1f} s, up to {res}")

        tmp_movie = write_temp_json(movie_data)
        tmp_files.append(tmp_movie)
        movie_path = tmp_movie.relative_to(SCRIPT_DIR)
        regenerate_configs = True

    elif args.movie:
        movie_data  = load_json(args.movie)
        movie_path  = args.movie
        regenerate_configs = True

    else:
        movie_data  = None
        movie_path  = "synthetic/movie.json"
        regenerate_configs = False

    # ── build prefetch configs ─────────────────────────────────────────────────
    if regenerate_configs:
        print("\nRegenerating prefetch configs for this movie ...")
        seeks = load_json(SCRIPT_DIR / SEEKS).get("seeks", [])
        scenario_configs = build_prefetch_configs(movie_data, seeks)

        cfg_dir = SCRIPT_DIR / "real_trace"
        prefetch_paths = {}
        for scenario, cfg in scenario_configs.items():
            out_path = cfg_dir / f"prefetch_config_real_{scenario}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            print(f"  wrote {out_path.relative_to(SCRIPT_DIR)}")
            prefetch_paths[scenario] = out_path.relative_to(SCRIPT_DIR)
    else:
        prefetch_paths = {
            sc: f"real_trace/prefetch_config_real_{sc}.json"
            for sc in SCENARIOS
        }

    # ── run all scenarios ──────────────────────────────────────────────────────
    try:
        for scenario in SCENARIOS:
            run([
                sys.executable, "run_comparison.py",
                "-n", NETWORK,
                "-m", str(movie_path),
                "-sc", SEEKS,
                "-pc", str(prefetch_paths[scenario]),
                "-a", "all",
                "-o", f"real_trace/results/{scenario}",
            ])

        print("\n>>> Merging scenario summaries ...")
        run([sys.executable, "merge_real_trace_summaries.py"])
        print("\nDone. Load real_trace/results/comparison_summary.json in the viewer.")
    finally:
        for p in tmp_files:
            p.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
