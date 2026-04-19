#!/usr/bin/env python3
"""
Run all 5 real-trace prefetch scenarios then merge into a single comparison_summary.json.

Usage:
    python run_real_trace_comparison.py
"""

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
TRACE_UUID = "56329467-babb-4d75-bb58-70f3906369fe"

SCENARIOS = [
    "seeks_miss",
    "prefetch_hit",
    "mixed",
    "linear_hit_dynamic_miss",
    "linear_miss_dynamic_hit",
]

NETWORK  = f"real_trace/network_{TRACE_UUID}.json"
SEEKS    = f"real_trace/seeks_{TRACE_UUID}.json"
MOVIE    = "synthetic/movie.json"


def run(cmd):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=SCRIPT_DIR)
    if result.returncode != 0:
        print(f"ERROR: command failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)


def main():
    for scenario in SCENARIOS:
        prefetch_cfg = f"real_trace/prefetch_config_real_{scenario}.json"
        output_dir   = f"real_trace/results/{scenario}"
        run([
            sys.executable, "run_comparison.py",
            "-n", NETWORK,
            "-m", MOVIE,
            "-sc", SEEKS,
            "-pc", prefetch_cfg,
            "-a", "all",
            "-o", output_dir,
        ])

    print("\n>>> Merging scenario summaries ...")
    run([sys.executable, "merge_real_trace_summaries.py"])
    print("\nDone. Load real_trace/results/comparison_summary.json in the viewer.")


if __name__ == "__main__":
    main()
