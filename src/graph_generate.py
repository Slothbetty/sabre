import pandas as pd
import matplotlib.pyplot as plt
import argparse

def generate_graph(abr):
    # Load the data from the CSV file
    data = pd.read_csv('output.csv')

    # Plot network_bandwidth vs time
    plt.figure(figsize=(10, 5))
    plt.plot(data['time'], data['network_bandwidth'], label='Network Bandwidth', marker='o')
    plt.xlabel('Time(ms)')
    plt.ylabel('Network Bandwidth(kbps)')
    plt.title(f"{abr} Network Bandwidth vs Time")
    plt.legend()
    plt.grid()
    plt.show()

    # Plot bitrate vs time
    plt.figure(figsize=(10, 5))
    plt.plot(data['time'], data['bitrate'], label='Bitrate', color='orange', marker='o')
    plt.xlabel('Time(ms)')
    plt.ylabel('Bitrate(kbps)')
    plt.title(f"{abr} Bitrate vs Time")
    plt.legend()
    plt.grid()
    plt.show()

    # Plot buffer_level vs time
    plt.figure(figsize=(10, 5))
    plt.plot(data['time'], data['buffer_level'], label='Buffer Level', color='green', marker='o')
    plt.xlabel('Time(ms)')
    plt.ylabel('Buffer Level(ms)')
    plt.title(f"{abr} Buffer Level vs Time")
    plt.legend()
    plt.grid()
    plt.show()

    # Plot rebuffer_time vs time
    plt.figure(figsize=(10, 5))
    plt.plot(data['time'], data['rebuffer_time'], label='Rebuffer Time', color='red', marker='o')
    plt.xlabel('Time(ms)')
    plt.ylabel('Rebuffer Time(ms)')
    plt.title(f"{abr} Rebuffer Time vs Time")
    plt.legend()
    plt.grid()
    plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate graph with specified ABR algorithm')
    parser.add_argument('-a', '--abr', type=str, required=True, help='ABR algorithm to use')
    args = parser.parse_args()
    
    generate_graph(args.abr)
