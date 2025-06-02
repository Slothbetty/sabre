import argparse
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(
        description="Run sabre.py with –v and –sc, and write all output to a named file."
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="Path to the file where sabre.py’s stdout+stderr should be written."
    )
    parser.add_argument(
        "-s", "--seek-config",
        default="seeks.json",
        help="Path to your seeks.json (passed to sabre.py). Default: %(default)s"
    )
    args = parser.parse_args()

    # Build the sabre.py command:
    cmd = [sys.executable, "sabre.py", "-v", "-sc", args.seek_config]

    # Open the output file and redirect both stdout and stderr into it:
    with open(args.output, "w") as out:
        subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT)

if __name__ == "__main__":
    main()
