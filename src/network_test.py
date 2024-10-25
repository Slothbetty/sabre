import subprocess
import os
import argparse

class NetworkTest:
    def __init__(self, network_generator_script, sabre_script, plot_graphs_script, num_entries, duration, bandwidth_mean, bandwidth_std, latency_mean, latency_std, algorithm):
        self.network_generator_script = network_generator_script
        self.sabre_script = sabre_script
        self.plot_graphs_script = plot_graphs_script
        self.num_entries = num_entries
        self.duration = duration
        self.bandwidth_mean = bandwidth_mean
        self.bandwidth_std = bandwidth_std
        self.latency_mean = latency_mean
        self.latency_std = latency_std
        self.algorithm = algorithm

    def generate_network_json(self):
        command = [
            'python', self.network_generator_script,
            '-ne', str(self.num_entries),
            '-d', str(self.duration),
            '-bm', str(self.bandwidth_mean),
            '-bs', str(self.bandwidth_std),
            '-lm', str(self.latency_mean),
            '-ls', str(self.latency_std)
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Error generating network.json: {result.stderr}")
        print("network.json file has been generated.")

    def run_sabre(self):
        command = ['python', self.sabre_script, '-a', self.algorithm, '-g']
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Error running sabre.py: {result.stderr}")
        return result.stdout

    def call_extract_data(self, output, csv_file):
        output_file = 'output.txt'
        with open(output_file, 'w') as file:
            file.write(output)

        command = ['python', 'extract_data.py', output_file, csv_file]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Error running extract_data.py: {result.stderr}")
        print(f"Data has been written to {csv_file}")

    def call_plot_graphs(self):
        command = ['python', self.plot_graphs_script]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Error running plot_graphs.py: {result.stderr}")
        print("Graphs have been generated.")

    def execute(self):
        self.generate_network_json()
        output = self.run_sabre()
        print("Output from sabre.py:")
        print(output)
        self.call_extract_data(output, 'output.csv')
        # self.call_plot_graphs()

def main():
    parser = argparse.ArgumentParser(description='Run network test and capture output.')
    parser.add_argument('-ne', '--num_entries', type=int, required=True, help='Number of entries to generate')
    parser.add_argument('-d', '--duration', type=float, required=True, help='Duration in ms')
    parser.add_argument('-bm', '--bandwidth_mean', type=float, required=True, help='Mean bandwidth in kbps')
    parser.add_argument('-bs', '--bandwidth_std', type=float, required=True, help='Standard deviation of bandwidth in kbps')
    parser.add_argument('-lm', '--latency_mean', type=float, required=True, help='Mean latency in ms')
    parser.add_argument('-ls', '--latency_std', type=float, required=True, help='Standard deviation of latency in ms')
    parser.add_argument('-a', '--algorithm', type=str, required=True, help='Algorithm to use in sabre.py')

    args = parser.parse_args()

    network_test = NetworkTest(
        network_generator_script='network_generator.py',
        sabre_script='sabre.py',
        plot_graphs_script='plot_graphs.py',
        num_entries=args.num_entries,
        duration=args.duration,
        bandwidth_mean=args.bandwidth_mean,
        bandwidth_std=args.bandwidth_std,
        latency_mean=args.latency_mean,
        latency_std=args.latency_std,
        algorithm=args.algorithm
    )
    network_test.execute()

if __name__ == '__main__':
    main()