#!/usr/bin/env python3
"""
Regression test for sabre.py simulation to ensure consistent results.
This test runs the simulation with a fixed configuration and compares
the output with a baseline to detect any changes.
"""

import sys
import subprocess
import tempfile
import datetime
import difflib
from pathlib import Path

try:
    import git  # type: ignore
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False

class SimulationRegressionTest:
    def __init__(self):
        self.test_dir = Path(__file__).parent
        self.baseline_file = self.test_dir / "baseline_simulation_results.txt"
        self.test_config = {
            "network": "network.json",
            "movie": "movie.json", 
            "seek_config": "seeks.json",
            "verbose": True,
            "graph": True
        }
        # All available ABR algorithms
        self.abr_algorithms = ['bola', 'bolae', 'dynamic', 'dynamicdash', 'throughput']
    
    def run_simulation(self, output_file, abr_algorithm):
        """Run the simulation and return the output file path."""
        cmd = [
            sys.executable, "sabre.py",
            "-n", self.test_config["network"],
            "-m", self.test_config["movie"],
            "-sc", self.test_config["seek_config"],
            "-a", abr_algorithm,
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
    
    def get_git_branch(self):
        """Get current git branch name."""
        # Try using git command directly first
        try:
            result = subprocess.run(['git', 'branch', '--show-current'], 
                                  capture_output=True, text=True, cwd=self.test_dir)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        
        # Fallback to GitPython if available
        if GIT_AVAILABLE:
            try:
                repo = git.Repo(self.test_dir)
                return repo.active_branch.name
            except:
                pass
        
        # Final fallback
        return "unknown"
    
    def generate_baseline(self):
        """Generate baseline results for all ABR algorithms."""
        print("Generating baseline simulation results for all ABR algorithms...")
        
        # Get timestamp and branch info
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        branch = self.get_git_branch()
        
        # Create header for the baseline file
        header = f"""# Baseline Simulation Results
# Generated on: {timestamp}
# Git branch: {branch}
# ABR algorithms: {', '.join(self.abr_algorithms)}
# ================================================

"""
        
        with open(self.baseline_file, 'w') as baseline_f:
            baseline_f.write(header)
            
            for abr in self.abr_algorithms:
                print(f"Running simulation for ABR algorithm: {abr}")
                
                # Create temporary file for this ABR's output
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
                    temp_file = Path(tmp.name)
                
                try:
                    # Run simulation for this ABR
                    self.run_simulation(temp_file, abr)
                    
                    # Add separator and ABR name to baseline
                    baseline_f.write(f"\n# ================================================\n")
                    baseline_f.write(f"# ABR Algorithm: {abr}\n")
                    baseline_f.write(f"# ================================================\n\n")
                    
                    # Copy the results to baseline file
                    with open(temp_file, 'r') as temp_f:
                        baseline_f.write(temp_f.read())
                    
                    baseline_f.write("\n")
                    
                finally:
                    # Clean up temporary file
                    if temp_file.exists():
                        temp_file.unlink()
        
        print(f"Baseline saved to: {self.baseline_file}")
        return self.baseline_file
    
    
    def compare_results(self, baseline_file):
        """Compare current results with baseline for all ABR algorithms."""
        if not baseline_file.exists():
            raise FileNotFoundError(f"Baseline file not found: {baseline_file}")
        
        # Generate a new complete baseline file with current results
        print("Generating new baseline file for comparison...")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
            new_baseline_file = Path(tmp.name)
        
        try:
            # Generate new baseline with current results
            self._generate_new_baseline(new_baseline_file)
            
            # Compare the two complete baseline files
            return self._compare_baseline_files(new_baseline_file, baseline_file)
            
        finally:
            if new_baseline_file.exists():
                new_baseline_file.unlink()
    
    def _generate_new_baseline(self, output_file):
        """Generate a new baseline file with current simulation results."""
        # Get timestamp and branch info
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        branch = self.get_git_branch()
        
        # Create header for the new baseline file
        header = f"""# Baseline Simulation Results
# Generated on: {timestamp}
# Git branch: {branch}
# ABR algorithms: {', '.join(self.abr_algorithms)}
# ================================================

"""
        
        with open(output_file, 'w') as baseline_f:
            baseline_f.write(header)
            
            for abr in self.abr_algorithms:
                print(f"Running simulation for ABR algorithm: {abr}")
                
                # Create temporary file for this ABR's output
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
                    temp_file = Path(tmp.name)
                
                try:
                    # Run simulation for this ABR
                    self.run_simulation(temp_file, abr)
                    
                    # Add separator and ABR name to baseline
                    baseline_f.write(f"\n# ================================================\n")
                    baseline_f.write(f"# ABR Algorithm: {abr}\n")
                    baseline_f.write(f"# ================================================\n\n")
                    
                    # Copy the results to baseline file
                    with open(temp_file, 'r') as temp_f:
                        baseline_f.write(temp_f.read())
                    
                    baseline_f.write("\n")
                    
                finally:
                    # Clean up temporary file
                    if temp_file.exists():
                        temp_file.unlink()
    

    def _compare_baseline_files(self, new_baseline_file, original_baseline_file):
        """Compare baseline files using difflib, ignoring timestamp differences."""
        with open(new_baseline_file, 'r') as f:
            new_lines = f.readlines()
        with open(original_baseline_file, 'r') as f:
            original_lines = f.readlines()
        
        # Filter out timestamp and git branch lines for comparison
        def filter_lines(lines):
            filtered = []
            for i, line in enumerate(lines):
                # Skip timestamp and git branch lines
                if i == 1 and "# Generated on:" in line:
                    continue
                if i == 2 and "# Git branch:" in line:
                    continue
                filtered.append(line)
            return filtered
        
        filtered_new_lines = filter_lines(new_lines)
        filtered_original_lines = filter_lines(original_lines)
        
        # Use difflib to find differences
        differ = difflib.unified_diff(
            filtered_original_lines,
            filtered_new_lines,
            fromfile='original_baseline',
            tofile='new_baseline',
            lineterm=''
        )
        
        differences = list(differ)
        
        if differences:
            # Limit output to first 20 lines of diff
            diff_output = '\n'.join(differences[:20])
            if len(differences) > 20:
                diff_output += '\n... (more differences)'
            
            return False, f"Found differences between baseline files:\n{diff_output}"
        
        return True, "Baseline files match (ignoring timestamps and git branches)"
    
    
    def run_test(self, generate_baseline=False):
        """Run the regression test."""
        if generate_baseline:
            self.generate_baseline()
            return True, "Baseline generated successfully"
        
        if not self.baseline_file.exists():
            return False, "Baseline file not found. Run with generate_baseline=True first."
        
        try:
            # Compare results for all ABR algorithms
            exact_match, exact_msg = self.compare_results(self.baseline_file)
            if exact_match:
                return True, "Test passed: All ABR results match baseline"
            
            return False, f"Test failed: {exact_msg}"
        
        except Exception as e:
            return False, f"Test failed with error: {e}"


def main():
    """Main function to run the regression test."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run simulation regression test")
    parser.add_argument("--generate-baseline", action="store_true",
                       help="Generate baseline results instead of testing")
    
    args = parser.parse_args()
    
    test = SimulationRegressionTest()
    
    try:
        success, message = test.run_test(generate_baseline=args.generate_baseline)
        
        if success:
            print("[SUCCESS] " + message)
            sys.exit(0)
        else:
            print("[FAILED] " + message)
            sys.exit(1)
            
    except Exception as e:
        print(f"[ERROR] Test failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
