import re
import pandas as pd
import sys

def extract_data(input_file, csv_file):
    with open(input_file, 'r') as file:
        content = file.read()

    # Regular expression to extract the data
    pattern = r'\[(\d+)\].*bitrate=(\d+)(.*rebuffer_time=(\d+\.?\d*))?'

    # Find all matches in the content
    matches = re.findall(pattern, content)

    # Prepare the data for CSV
    data = []
    for match in matches:
        time = int(match[0]) / 1000  # convert time from ms to seconds
        bitrate = int(match[1])
        rebuffer_time = float(match[2]) if match[2] else 0  # convert rebuffer_time from ms to seconds, if available
        data.append([time, bitrate, rebuffer_time])

    # Convert to DataFrame
    df = pd.DataFrame(data, columns=['Time (s)', 'Bitrate', 'Rebuffer Time (s)'])

    # Write the DataFrame to a CSV file
    df.to_csv(csv_file, index=False)

if __name__ == '__main__':
    input_file = sys.argv[1]
    csv_file = sys.argv[2]
    extract_data(input_file, csv_file)