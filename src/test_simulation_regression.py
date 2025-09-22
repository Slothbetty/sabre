#!/usr/bin/env python3
"""
Regression test for sabre.py simulation to ensure consistent results.
This test runs the simulation with a fixed configuration and compares
the output with a baseline to detect any changes.
"""

import os
import sys
import subprocess
import hashlib
import json
import tempfile
from pathlib import Path


class SimulationRegressionTest:
    def __init__(self):
        self.test_dir = Path(__file__).parent
        self.baseline_file = self.test_dir / "baseline_simulation_results.txt"
        self.test_config = {
            "network": "network.json",
            "movie": "movie.json", 
            "seek_config": "seeks.json",
            "abr": "bolae",
            "verbose": True,
            "graph": False
        }
    
    def run_simulation(self, output_file):
        """Run the simulation and return the output file path."""
        cmd = [
            sys.executable, "sabre.py",
            "-n", self.test_config["network"],
            "-m", self.test_config["movie"],
            "-sc", self.test_config["seek_config"],
            "-a", self.test_config["abr"],
            "-v" if self.test_config["verbose"] else "",
            "-g" if self.test_config["graph"] else ""
        ]
        # Remove empty strings from command
        cmd = [arg for arg in cmd if arg]
        
        with open(output_file, 'w') as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, 
                                  cwd=self.test_dir, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"Simulation failed with return code {result.returncode}")
        
        return output_file
    
    def generate_baseline(self):
        """Generate baseline results for comparison."""
        print("Generating baseline simulation results...")
        self.run_simulation(self.baseline_file)
        print(f"Baseline saved to: {self.baseline_file}")
        return self.baseline_file
    
    def get_file_hash(self, file_path):
        """Calculate SHA256 hash of a file."""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def compare_results(self, current_file, baseline_file):
        """Compare current results with baseline."""
        if not baseline_file.exists():
            raise FileNotFoundError(f"Baseline file not found: {baseline_file}")
        
        # Compare file hashes for exact match
        current_hash = self.get_file_hash(current_file)
        baseline_hash = self.get_file_hash(baseline_file)
        
        if current_hash == baseline_hash:
            return True, "Results are identical"
        
        # If hashes differ, do line-by-line comparison
        return self._detailed_comparison(current_file, baseline_file)
    
    def _detailed_comparison(self, current_file, baseline_file):
        """Perform detailed line-by-line comparison."""
        with open(current_file, 'r') as f:
            current_lines = f.readlines()
        with open(baseline_file, 'r') as f:
            baseline_lines = f.readlines()
        
        if len(current_lines) != len(baseline_lines):
            return False, f"Line count differs: current={len(current_lines)}, baseline={len(baseline_lines)}"
        
        differences = []
        for i, (current, baseline) in enumerate(zip(current_lines, baseline_lines)):
            if current.strip() != baseline.strip():
                differences.append(f"Line {i+1}: '{current.strip()}' vs '{baseline.strip()}'")
                if len(differences) >= 10:  # Limit to first 10 differences
                    differences.append("... (more differences)")
                    break
        
        if differences:
            return False, f"Found {len(differences)} differences:\n" + "\n".join(differences)
        
        return True, "Results match after normalization"
    
    def extract_key_metrics(self, result_file):
        """Extract key metrics from simulation results for comparison."""
        metrics = {}
        
        with open(result_file, 'r') as f:
            lines = f.readlines()
        
        # Extract key statistics from the end of the file
        for line in lines:
            line = line.strip()
            if "total played utility:" in line:
                metrics["total_played_utility"] = float(line.split(":")[1].strip())
            elif "total played bitrate:" in line:
                metrics["total_played_bitrate"] = float(line.split(":")[1].strip())
            elif "total play time:" in line:
                metrics["total_play_time"] = float(line.split(":")[1].strip())
            elif "total rebuffer:" in line:
                metrics["total_rebuffer"] = float(line.split(":")[1].strip())
            elif "rebuffer ratio:" in line:
                metrics["rebuffer_ratio"] = float(line.split(":")[1].strip())
            elif "total rebuffer events:" in line:
                metrics["total_rebuffer_events"] = float(line.split(":")[1].strip())
            elif "time average score:" in line:
                metrics["time_average_score"] = float(line.split(":")[1].strip())
        
        return metrics
    
    def compare_metrics(self, current_file, baseline_file, tolerance=1e-6):
        """Compare key metrics with tolerance for floating point differences."""
        current_metrics = self.extract_key_metrics(current_file)
        baseline_metrics = self.extract_key_metrics(baseline_file)
        
        differences = []
        for key in current_metrics:
            if key not in baseline_metrics:
                differences.append(f"Missing metric in baseline: {key}")
                continue
            
            current_val = current_metrics[key]
            baseline_val = baseline_metrics[key]
            
            if abs(current_val - baseline_val) > tolerance:
                differences.append(f"{key}: {current_val} vs {baseline_val} (diff: {abs(current_val - baseline_val)})")
        
        if differences:
            return False, f"Metric differences found:\n" + "\n".join(differences)
        
        return True, "All metrics match within tolerance"
    
    def run_test(self, generate_baseline=False):
        """Run the regression test."""
        if generate_baseline:
            self.generate_baseline()
            return True, "Baseline generated successfully"
        
        if not self.baseline_file.exists():
            return False, "Baseline file not found. Run with generate_baseline=True first."
        
        # Run current simulation
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
            current_file = Path(tmp.name)
        
        try:
            self.run_simulation(current_file)
            
            # Compare results
            exact_match, exact_msg = self.compare_results(current_file, self.baseline_file)
            if exact_match:
                return True, "Test passed: Results are identical"
            
            # If not exact match, try metric comparison
            metrics_match, metrics_msg = self.compare_metrics(current_file, self.baseline_file)
            if metrics_match:
                return True, f"Test passed: Metrics match within tolerance\nExact comparison: {exact_msg}"
            
            return False, f"Test failed:\nExact comparison: {exact_msg}\nMetrics comparison: {metrics_msg}"
        
        finally:
            # Clean up temporary file
            if current_file.exists():
                current_file.unlink()


def main():
    """Main function to run the regression test."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run simulation regression test")
    parser.add_argument("--generate-baseline", action="store_true",
                       help="Generate baseline results instead of testing")
    parser.add_argument("--verbose", action="store_true",
                       help="Print detailed output")
    
    args = parser.parse_args()
    
    test = SimulationRegressionTest()
    
    try:
        success, message = test.run_test(generate_baseline=args.generate_baseline)
        
        if success:
            print("✅ " + message)
            sys.exit(0)
        else:
            print("❌ " + message)
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
