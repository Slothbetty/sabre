import pandas as pd
import matplotlib.pyplot as plt
import argparse

def generate_graph(abrarray):
    # Dictionary to store the DataFrame for each ABR algorithm
    dataframes = {}

    # List of colors
    colors = ['blue', 'orange', 'green', 'red', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan']
    marker = 'o'  # Use the same marker symbol

    # Load the data from each CSV file and store it in the dictionary
    for abr in abrarray:
        dataframes[abr] = pd.read_csv(f'{abr}.csv')

    # Plot network_bandwidth vs time for all ABR algorithms with logarithmic scale
    plt.figure(figsize=(10, 5))
    for i, abr in enumerate(abrarray):
        plt.plot(
            dataframes[abr]['time'], 
            dataframes[abr]['network_bandwidth'], 
            label=f'{abr} Network Bandwidth', 
            color=colors[i % len(colors)], 
            marker=marker,  # Use the same marker symbol
            alpha=0.8  # Set transparency
        )
    plt.xlabel('Time(ms)')
    plt.ylabel('Network Bandwidth(kbps)')
    # plt.yscale('log')  # Set y-axis to logarithmic scale
    plt.title("Network Bandwidth vs Time for All ABR Algorithms Seek")
    plt.legend()
    plt.grid(visible=True, which='both', linestyle='--', alpha=0.5)
    plt.show()

    # Plot bitrate vs time for all ABR algorithms with logarithmic scale
    plt.figure(figsize=(10, 5))
    for i, abr in enumerate(abrarray):
        plt.plot(
            dataframes[abr]['time'], 
            dataframes[abr]['bitrate'], 
            label=f'{abr} Bitrate', 
            color=colors[i % len(colors)], 
            marker=marker,  # Use the same marker symbol
            alpha=0.8  # Set transparency
        )
    plt.xlabel('Time(ms)')
    plt.ylabel('Bitrate(kbps)')
    # plt.yscale('log')  # Set y-axis to logarithmic scale
    plt.title("Bitrate vs Time for All ABR Algorithms Seek")
    plt.legend()
    plt.grid(visible=True, which='both', linestyle='--', alpha=0.5)
    plt.show()

    # Plot buffer_level vs time for all ABR algorithms with logarithmic scale
    plt.figure(figsize=(10, 5))
    for i, abr in enumerate(abrarray):
        plt.plot(
            dataframes[abr]['time'], 
            dataframes[abr]['buffer_level'], 
            label=f'{abr} Buffer Level', 
            color=colors[i % len(colors)], 
            marker=marker,  # Use the same marker symbol
            alpha=0.8  # Set transparency
        )
    plt.xlabel('Time(ms)')
    plt.ylabel('Buffer Level(ms)')
    # plt.yscale('log')  # Set y-axis to logarithmic scale
    plt.title("Buffer Level vs Time for All ABR Algorithms Seek")
    plt.legend()
    plt.grid(visible=True, which='both', linestyle='--', alpha=0.5)
    plt.show()

    # Plot rebuffer_time vs time for all ABR algorithms with logarithmic scale
    plt.figure(figsize=(10, 5))
    for i, abr in enumerate(abrarray):
        plt.plot(
            dataframes[abr]['time'], 
            dataframes[abr]['rebuffer_time'], 
            label=f'{abr} Rebuffer Time', 
            color=colors[i % len(colors)], 
            marker=marker,  # Use the same marker symbol
            alpha=0.8  # Set transparency
        )
    plt.xlabel('Time(ms)')
    plt.ylabel('Rebuffer Time(ms)')
    # plt.yscale('log')  # Set y-axis to logarithmic scale
    plt.title("Rebuffer Time vs Time for All ABR Algorithms Seek")
    plt.legend()
    plt.grid(visible=True, which='both', linestyle='--', alpha=0.5)
    plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate graphs for specified ABR algorithms')
    parser.add_argument('-a', '--abr', type=str, nargs='+', required=True, help='Array of ABR algorithms to use (space-separated)')
    args = parser.parse_args()

    # Pass the ABR algorithm array to the generate_graph function
    generate_graph(args.abr)
