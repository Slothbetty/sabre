import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Load the CSV file (replace 'your_csv_file.csv' with your actual file name)
file_path = 'sabre result graphs - bandwidth (5000-_3000-_1500-_300).csv'
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

# Create figure for bitrate vs time
fig_bitrate = go.Figure()

fig_bitrate.add_trace(go.Scatter(x=df_cleaned['BOLA_time'], y=df_cleaned['BOLA_bitrate'], mode='markers+lines', name='BOLA'))
fig_bitrate.add_trace(go.Scatter(x=df_cleaned['BOLAE_time'], y=df_cleaned['BOLAE_bitrate'], mode='markers+lines', name='BOLAE'))
fig_bitrate.add_trace(go.Scatter(x=df_cleaned['Dynamic_time'], y=df_cleaned['Dynamic_bitrate'], mode='markers+lines', name='Dynamic'))
fig_bitrate.add_trace(go.Scatter(x=df_cleaned['Dynamicdash_time'], y=df_cleaned['Dynamicdash_bitrate'], mode='markers+lines', name='Dynamicdash'))
fig_bitrate.add_trace(go.Scatter(x=df_cleaned['Throughput_time'], y=df_cleaned['Throughput_bitrate'], mode='markers+lines', name='Throughput'))

fig_bitrate.update_layout(
    title="Bitrate vs Time",
    xaxis_title="Time (s)",
    yaxis_title="Bitrate (kbps)",
    legend_title="Algorithm",
    hovermode="x unified"
)

# Create figure for rebuffer time vs time
fig_rebuffer = go.Figure()

fig_rebuffer.add_trace(go.Scatter(x=df_cleaned['BOLA_time'], y=df_cleaned['BOLA_rebuffer'], mode='markers+lines', name='BOLA'))
fig_rebuffer.add_trace(go.Scatter(x=df_cleaned['BOLAE_time'], y=df_cleaned['BOLAE_rebuffer'], mode='markers+lines', name='BOLAE'))
fig_rebuffer.add_trace(go.Scatter(x=df_cleaned['Dynamic_time'], y=df_cleaned['Dynamic_rebuffer'], mode='markers+lines', name='Dynamic'))
fig_rebuffer.add_trace(go.Scatter(x=df_cleaned['Dynamicdash_time'], y=df_cleaned['Dynamicdash_rebuffer'], mode='markers+lines', name='Dynamicdash'))
fig_rebuffer.add_trace(go.Scatter(x=df_cleaned['Throughput_time'], y=df_cleaned['Throughput_rebuffer'], mode='markers+lines', name='Throughput'))

fig_rebuffer.update_layout(
    title="Rebuffer Time vs Time",
    xaxis_title="Time (s)",
    yaxis_title="Rebuffer Time (s)",
    legend_title="Algorithm",
    hovermode="x unified"
)

# Show plots
fig_bitrate.show()
fig_rebuffer.show()