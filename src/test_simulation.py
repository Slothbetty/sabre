#!/usr/bin/env python3
"""
Simple regression test for sabre.py simulation.
Ensures simulation results remain consistent after code changes.
"""

import os
import sys
import subprocess
import hashlib
from pathlib import Path


def run_simulation(output_file):
    """Run sabre.py simulation and save output to file."""
    cmd = [
        sys.executable, "sabre.py",
        "-n", "network.json",
        "-m", "movie.json", 
        "-sc", "seeks.json",
        "-a", "bolae",
        "-v"
    ]
    
    with open(output_file, 'w') as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, 
                              cwd=Path(__file__).parent, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"Simulation failed with return code {result.returncode}")
    
    return output_file


def get_file_hash(file_path):
    """Calculate SHA256 hash of a file."""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


def generate_baseline():
    """Generate baseline results for comparison."""
    baseline_file = "baseline_simulation_results.txt"
    print(f"Generating baseline simulation results...")
    run_simulation(baseline_file)
    print(f"✅ Baseline saved to: {baseline_file}")
    return baseline_file


def run_test():
    """Run regression test comparing current results with baseline."""
    baseline_file = "baseline_simulation_results.txt"
    current_file = "current_simulation_results.txt"
    
    if not os.path.exists(baseline_file):
        print(f"❌ Baseline file not found: {baseline_file}")
        print("Run 'python test_simulation.py --generate-baseline' first")
        return False
    
    print("Running current simulation...")
    run_simulation(current_file)
    
    # Compare file hashes
    current_hash = get_file_hash(current_file)
    baseline_hash = get_file_hash(baseline_file)
    
    if current_hash == baseline_hash:
        print("✅ Test PASSED: Results are identical")
        os.remove(current_file)  # Clean up
        return True
    else:
        print("❌ Test FAILED: Results differ")
        print(f"Current hash:  {current_hash}")
        print(f"Baseline hash: {baseline_hash}")
        print(f"Compare files: {current_file} vs {baseline_file}")
        return False


def main():
    """Main function."""
    if len(sys.argv) > 1 and sys.argv[1] == "--generate-baseline":
        generate_baseline()
    else:
        success = run_test()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
