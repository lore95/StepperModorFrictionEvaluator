#!/usr/bin/env python3
import os
import glob
import re
import pandas as pd
import matplotlib.pyplot as plt

def parse_filename(filename):
    """
    Extract distance (cm) and speed (m/s) from a filename of the form
    '<timestamp>_<distance>cm_<speed>mps_grip_data.csv'.
    Returns (distance_cm, speed_mps) or (None, None) if parsing fails.
    """
    base = os.path.basename(filename)
    match = re.match(r'\\d+_(\\d+)cm_(\\d+p\\d+)mps', base)
    if match:
        dist = int(match.group(1))
        speed_str = match.group(2).replace('p', '.')
        return dist, float(speed_str)
    return None, None

def load_filtered_sensor(filepath):
    """
    Load a CSV file and return two pandas Series:
    relative time (seconds) and filtered friction force.
    Falls back to raw data if no filtered column is present.
    """
    df = pd.read_csv(filepath)
    # Use filtered data if available
    col = 'Filtered_Line' if 'Filtered_Line' in df.columns else 'Raw_Data_Line'
    df['force'] = pd.to_numeric(df[col], errors='coerce')
    df.dropna(subset=['force'], inplace=True)
    # Relative time from start
    t0 = df['Host_Time_s'].iloc[0]
    df['time'] = df['Host_Time_s'] - t0
    return df['time'], df['force']

def compare_friction(directory='readings'):
    files = sorted(glob.glob(os.path.join(directory, '*_grip_data.csv')))
    if not files:
        print(f"No grip data files found in {directory}")
        return

    plt.figure(figsize=(12, 6))
    for path in files:
        distance_cm, speed_mps = parse_filename(path)
        time_s, force = load_filtered_sensor(path)
        # Remove the first 10% of samples to eliminate ramp-up effects
        start = int(0.10 * len(time_s))
        t_trimmed = time_s.iloc[start:]
        f_trimmed = force.iloc[start:]
        label_parts = []
        if distance_cm is not None:
            label_parts.append(f"{distance_cm} cm")
        if speed_mps is not None:
            label_parts.append(f"{speed_mps:.2f} m/s")
        label = ", ".join(label_parts) if label_parts else os.path.basename(path)
        plt.plot(t_trimmed, f_trimmed, label=label)

    plt.title("Friction over time for multiple tests")
    plt.xlabel("Time since start (s)")
    plt.ylabel("Friction force (sensor units)")
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    # Adjust 'readings' if your files are stored elsewhere
    compare_friction('../readings')