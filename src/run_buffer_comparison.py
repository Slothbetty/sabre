#!/usr/bin/env python3
"""
Run simulations with and without buffer.py and collect metrics for web visualization.
"""

import sys
import subprocess
import json
import argparse
import re
from pathlib import Path
from collections import defaultdict


def parse_simulation_output(output):
    """Parse verbose simulation output to extract metrics."""
    metrics = {
        'summary': {},
        'download_events': [],
        'rebuffer_events': [],
        'seek_events': []
    }
    
    lines = output.split('\n')
    current_time = 0
    
    # Parse download events and extract time-series data
    download_pattern = r'\[(\d+)-(\d+)\]\s+(\d+):\s+quality=(\d+).*?buffer_level=(-?\d+)->(-?\d+)'
    
    for line in lines:
        # Parse download events
        match = re.search(download_pattern, line)
        if match:
            start_time, end_time, segment, quality, bl_before, bl_after = match.groups()
            metrics['download_events'].append({
                'start_time': int(start_time),
                'end_time': int(end_time),
                'segment': int(segment),
                'quality': int(quality),
                'buffer_level_before': int(bl_before),
                'buffer_level_after': int(bl_after)
            })
        
        # Parse summary metrics
        if 'total rebuffer:' in line.lower():
            try:
                value = float(re.search(r':\s*([\d.]+)', line).group(1))
                metrics['summary']['total_rebuffer_time'] = value
            except:
                pass
        elif 'total rebuffer events:' in line.lower():
            try:
                value = float(re.search(r':\s*([\d.]+)', line).group(1))
                metrics['summary']['rebuffer_count'] = int(value)
            except:
                pass
        elif 'total play time:' in line.lower():
            try:
                value = float(re.search(r':\s*([\d.]+)', line).group(1))
                metrics['summary']['total_play_time'] = value
            except:
                pass
        elif 'total played utility:' in line.lower():
            try:
                value = float(re.search(r':\s*([\d.]+)', line).group(1))
                metrics['summary']['played_utility'] = value
            except:
                pass
        elif 'total played bitrate:' in line.lower():
            try:
                value = float(re.search(r':\s*([\d.]+)', line).group(1))
                metrics['summary']['played_bitrate'] = value
            except:
                pass
        elif 'rebuffer ratio:' in line.lower():
            try:
                value = float(re.search(r':\s*([\d.]+)', line).group(1))
                metrics['summary']['rebuffer_ratio'] = value
            except:
                pass
        elif 'rampup time:' in line.lower():
            try:
                value = float(re.search(r':\s*([\d.]+)', line).group(1))
                metrics['summary']['rampup_time'] = value
            except:
                pass
        elif 'startup time:' in line.lower() or 'time average played utility:' in line.lower():
            # Skip these for now
            pass
    
    # Build time series data from download events
    time_series = {
        'time_points': [],
        'buffer_levels': [],
        'qualities': [],
        'segments': []
    }
    
    for event in metrics['download_events']:
        # Add point at end of download
        time_series['time_points'].append(event['end_time'] / 1000.0)  # Convert to seconds
        time_series['buffer_levels'].append(event['buffer_level_after'] / 1000.0)  # Convert to seconds
        time_series['qualities'].append(event['quality'])
        time_series['segments'].append(event['segment'])
    
    metrics['time_series'] = time_series
    
    return metrics


def run_simulation(use_buffer_py, config):
    """Run a simulation and return parsed metrics."""
    script_dir = Path(__file__).parent
    cmd = [
        sys.executable, str(script_dir / 'sabre.py'),
        '-n', config['network'],
        '-m', config['movie'],
        '-a', config['abr'],
        '-nm', str(config.get('network_multiplier', 1.0)),
        '-v'  # Verbose mode for parsing
    ]
    
    if config.get('seek_config'):
        cmd.extend(['-sc', config['seek_config']])
    
    if use_buffer_py:
        cmd.append('--use-buffer-py')
    
    print(f"Running simulation {'WITH' if use_buffer_py else 'WITHOUT'} buffer.py...")
    # Capture stdout for parsing, but let stderr go through so debug output is visible
    result = subprocess.run(
        cmd,
        cwd=script_dir,
        stdout=subprocess.PIPE,  # Capture stdout for parsing
        stderr=None,  # Don't capture stderr - let it print to console
        text=True
    )
    
    if result.returncode != 0:
        print(f"Error: Simulation failed:\n{result.stdout}", file=sys.stderr)
        return None
    
    metrics = parse_simulation_output(result.stdout)
    return metrics


def main():
    parser = argparse.ArgumentParser(
        description='Compare simulation results with and without buffer.py'
    )
    parser.add_argument(
        '-n', '--network',
        default='network.json',
        help='Network trace file'
    )
    parser.add_argument(
        '-m', '--movie',
        default='movie.json',
        help='Movie manifest file'
    )
    parser.add_argument(
        '-a', '--abr',
        default='bola',
        help='ABR algorithm'
    )
    parser.add_argument(
        '-sc', '--seek-config',
        help='Seek configuration file'
    )
    parser.add_argument(
        '-nm', '--network-multiplier',
        type=float,
        default=1.0,
        help='Network multiplier'
    )
    parser.add_argument(
        '-o', '--output',
        default='comparison_results.json',
        help='Output JSON file'
    )
    
    args = parser.parse_args()
    
    config = {
        'network': args.network,
        'movie': args.movie,
        'abr': args.abr,
        'seek_config': args.seek_config,
        'network_multiplier': args.network_multiplier
    }
    
    # Run both simulations
    metrics_without = run_simulation(use_buffer_py=False, config=config)
    metrics_with = run_simulation(use_buffer_py=True, config=config)
    
    if metrics_without is None or metrics_with is None:
        print("Error: One or both simulations failed", file=sys.stderr)
        sys.exit(1)
    
    # Prepare comparison data
    comparison_data = {
        'config': config,
        'without_buffer_py': metrics_without,
        'with_buffer_py': metrics_with
    }
    
    # Write results to JSON file
    script_dir = Path(__file__).parent
    output_path = script_dir / args.output
    with open(output_path, 'w') as f:
        json.dump(comparison_data, f, indent=2)
    
    print(f"\n✓ Results saved to {output_path}")
    print("\nSummary Comparison:")
    print(f"{'Metric':<30} {'Without buffer.py':<20} {'With buffer.py':<20} {'Change':<15}")
    print("-" * 85)
    
    summary_keys = ['total_rebuffer_time', 'rebuffer_count', 'total_play_time', 
                    'played_utility', 'rebuffer_ratio']
    
    for key in summary_keys:
        val_without = metrics_without.get('summary', {}).get(key, 0)
        val_with = metrics_with.get('summary', {}).get(key, 0)
        
        if val_without != 0:
            change_pct = ((val_with - val_without) / val_without) * 100
            change_str = f"{change_pct:+.1f}%"
        else:
            change_str = "N/A"
        
        print(f"{key:<30} {str(val_without):<20} {str(val_with):<20} {change_str:<15}")
    
    print(f"\nOpen view_comparison.html in your browser and load {args.output} to see visualizations!")


if __name__ == '__main__':
    main()

