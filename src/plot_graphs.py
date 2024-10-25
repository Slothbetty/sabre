import pandas as pd
import matplotlib.pyplot as plt

# Load the CSV file (replace 'your_csv_file.csv' with your actual file name)
file_path = 'output.csv'
df = pd.read_csv(file_path)

# Clean the dataframe by renaming columns and preparing the data for plotting
df_cleaned = df.copy()

# Rename columns for better understanding
df_cleaned.columns = ['BOLA_time', 'BOLA_bitrate', 'BOLA_rebuffer', 'BOLAE_time', 'BOLAE_bitrate', 'BOLAE_rebuffer', 
                      'Dynamic_time', 'Dynamic_bitrate', 'Dynamic_rebuffer', 'Dynamicdash_time', 'Dynamicdash_bitrate',
                      'Dynamicdash_rebuffer', 'Throughput_time', 'Throughput_bitrate', 'Throughput_rebuffer']

# Convert relevant columns to numeric, skipping headers
df_cleaned = df_cleaned.drop(0)  # Drop the header row
df_cleaned = df_cleaned.apply(pd.to_numeric, errors='coerce')

# Plot bitrate vs time for all algorithms
plt.figure(figsize=(10, 6))
plt.plot(df_cleaned['BOLA_time'], df_cleaned['BOLA_bitrate'], label='BOLA', marker='o')
plt.plot(df_cleaned['BOLAE_time'], df_cleaned['BOLAE_bitrate'], label='BOLAE', marker='x')
plt.plot(df_cleaned['Dynamic_time'], df_cleaned['Dynamic_bitrate'], label='Dynamic', marker='s')
plt.plot(df_cleaned['Dynamicdash_time'], df_cleaned['Dynamicdash_bitrate'], label='Dynamicdash', marker='d')
plt.plot(df_cleaned['Throughput_time'], df_cleaned['Throughput_bitrate'], label='Throughput', marker='*')

plt.xlabel("Time (s)")
plt.ylabel("Bitrate (kbps)")
plt.title("Bitrate vs Time")
plt.legend()
plt.grid(True)
plt.show()

# Plot rebuffer_time vs time for all algorithms
plt.figure(figsize=(10, 6))
plt.plot(df_cleaned['BOLA_time'], df_cleaned['BOLA_rebuffer'], label='BOLA', marker='o')
plt.plot(df_cleaned['BOLAE_time'], df_cleaned['BOLAE_rebuffer'], label='BOLAE', marker='x')
plt.plot(df_cleaned['Dynamic_time'], df_cleaned['Dynamic_rebuffer'], label='Dynamic', marker='s')
plt.plot(df_cleaned['Dynamicdash_time'], df_cleaned['Dynamicdash_rebuffer'], label='Dynamicdash', marker='d')
plt.plot(df_cleaned['Throughput_time'], df_cleaned['Throughput_rebuffer'], label='Throughput', marker='*')

plt.xlabel("Time (s)")
plt.ylabel("Rebuffer Time (s)")
plt.title("Rebuffer Time vs Time")
plt.legend()
plt.grid(True)
plt.show()
