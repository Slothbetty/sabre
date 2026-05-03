#!/usr/bin/env python3
"""
Convert an entry from a chunks JSON (e.g. chunks_1_200.json) into a
movie.json compatible with sabre.py.

Usage:
    python chunks_to_movie.py <chunks_file> --list
    python chunks_to_movie.py <chunks_file> --index 0 -o real_trace/movie.json
    python chunks_to_movie.py <chunks_file> --video-id Qg9LxRHLbAk -o movie.json
    python chunks_to_movie.py <chunks_file> --all -o real_trace/movies/
"""

import argparse
import json
import sys
from pathlib import Path

# Allow non-ASCII characters (e.g. video titles) on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_chunks(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("chunks JSON must be a top-level array")
    return data


def to_movie(entry):
    return {
        "segment_duration_ms": entry["segment_duration_ms"],
        "bitrates_kbps": entry["bitrates_kbps"],
        "segment_sizes_bits": entry["segment_sizes_bits"],
    }


def print_info(entry, movie, file=sys.stderr):
    segs = len(movie["segment_sizes_bits"])
    quals = len(movie["bitrates_kbps"])
    print(f"  video_id   : {entry.get('video_id', '?')}", file=file)
    print(f"  title      : {entry.get('title', '')}", file=file)
    print(f"  duration   : {entry.get('duration_s', '?')} s", file=file)
    print(f"  segments   : {segs} × {movie['segment_duration_ms']} ms", file=file)
    print(f"  qualities  : {quals} levels", file=file)
    print(f"  resolutions: {entry.get('resolutions', '?')}", file=file)
    print(f"  bitrates   : {movie['bitrates_kbps']} kbps", file=file)


def main():
    parser = argparse.ArgumentParser(
        description="Convert a chunks JSON entry to movie.json for sabre.py"
    )
    parser.add_argument("chunks", help="Path to chunks JSON file (e.g. chunks_1_200.json)")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true",
                       help="List all videos in the chunks file")
    group.add_argument("--index", type=int, metavar="N",
                       help="Convert the video at index N (0-based)")
    group.add_argument("--video-id", metavar="ID",
                       help="Convert the video with this video_id")
    group.add_argument("--all", action="store_true",
                       help="Batch-convert all videos; -o must be a directory")

    parser.add_argument("-o", "--output", metavar="PATH",
                        help="Output file path (or directory for --all). "
                             "Omit to print JSON to stdout.")
    args = parser.parse_args()

    chunks = load_chunks(args.chunks)

    if args.list:
        print(f"{'#':>3}  {'video_id':<14}  {'dur':>4}  {'segs':>4}  {'max res':<10}  title")
        print("-" * 80)
        for i, v in enumerate(chunks):
            res = (v.get("resolutions") or ["?"])[-1]
            segs = len(v.get("segment_sizes_bits") or [])
            title = (v.get("title") or "")[:45]
            print(f"{i:3d}  {v.get('video_id','?'):<14}  "
                  f"{v.get('duration_s','?'):>4}s  {segs:>4}  {res:<10}  {title}")
        return

    if args.all:
        out_dir = Path(args.output or "movies")
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, v in enumerate(chunks):
            vid = v.get("video_id", f"video_{i}")
            out_path = out_dir / f"movie_{i:03d}_{vid}.json"
            movie = to_movie(v)
            with open(out_path, "w") as f:
                json.dump(movie, f)
            segs = len(movie["segment_sizes_bits"])
            print(f"  [{i:3d}] {out_path.name}  ({segs} segs)")
        print(f"\nWrote {len(chunks)} movie files to {out_dir}/")
        return

    # Single-video path
    if args.index is not None:
        if not (0 <= args.index < len(chunks)):
            print(f"Error: index {args.index} out of range (0–{len(chunks)-1})",
                  file=sys.stderr)
            sys.exit(1)
        entry = chunks[args.index]
    else:
        matches = [v for v in chunks if v.get("video_id") == args.video_id]
        if not matches:
            print(f"Error: video_id '{args.video_id}' not found", file=sys.stderr)
            sys.exit(1)
        entry = matches[0]

    movie = to_movie(entry)
    print_info(entry, movie)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(movie, f)
        print(f"Wrote {out_path}", file=sys.stderr)
    else:
        json.dump(movie, sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
