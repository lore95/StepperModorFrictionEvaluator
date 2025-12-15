import pandas as pd
import matplotlib.pyplot as plt
import os
import glob

def find_latest_csv(directory='readings'):
    """Finds the most recently created CSV file in the specified directory."""
    try:
        files = glob.glob(os.path.join(directory, '*.csv'))
        if not files:
            print(f"No CSV files found in {directory}")
            return None
        return max(files, key=os.path.getctime)
    except Exception as e:
        print(f"Error finding latest CSV: {e}")
        return None

def plot_grip_data(filepath):
    """Loads and plots the filtered grip sensor data from a CSV file."""
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return

    print(f"Successfully loaded file: {os.path.basename(filepath)}")
    print(f"Total data points: {len(df)}")

    # Choose filtered data if present, otherwise fall back to raw
    try:
        if 'Filtered_Line' in df.columns:
            # Use the filtered data column
            df['Sensor_Value'] = pd.to_numeric(df['Filtered_Line'], errors='coerce')
            trace_label = 'Filtered Sensor Reading'
        else:
            # Use the original raw column
            df['Sensor_Value'] = pd.to_numeric(df['Raw_Data_Line'], errors='coerce')
            trace_label = 'Grip Sensor Reading'

        df.dropna(subset=['Sensor_Value'], inplace=True)
        if df.empty:
            print("No valid numeric data to plot.")
            return

        # Convert timestamps to a relative time base
        time_origin = df['Host_Time_s'].min()
        df['Time_s'] = df['Host_Time_s'] - time_origin

    except KeyError:
        print("CSV file is missing required columns ('Host_Time_s' and a sensor column).")
        return

    # Plot the data
    plt.figure(figsize=(12, 6))
    plt.plot(df['Time_s'], df['Sensor_Value'], label=trace_label, color='royalblue')
    plt.title(f'{trace_label} Over Time\nFile: {os.path.basename(filepath)}', fontsize=14)
    plt.xlabel('Time since Motor Start (s)', fontsize=12)
    plt.ylabel('Sensor Value', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend()
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    latest_file = find_latest_csv()
    if latest_file:
        plot_grip_data(latest_file)