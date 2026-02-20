import pandas as pd
import matplotlib.pyplot as plt
import os
import glob

def find_latest_csv(directory="readings"):
    files = glob.glob(os.path.join(directory, "*.csv"))
    if not files:
        print(f"No CSV files found in {directory}")
        return None
    return max(files, key=os.path.getctime)


def plot_grip_data(filepath, *, plot_mode="force"):
    """
    plot_mode:
        'raw'       -> Raw_V3
        'filtered'  -> Raw_V3_Filtered
        'force'     -> Force_N
    """
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return

    print(f"Loaded: {os.path.basename(filepath)}")
    print(f"Data points: {len(df)}")

    # --- column selection ---
    if plot_mode == "raw":
        value_col = "Raw_V3"
        label = "Raw V3"
        ylabel = "Raw ADC Units"
    elif plot_mode == "filtered":
        value_col = "Raw_V3_Filtered"
        label = "Filtered Raw V3"
        ylabel = "Raw ADC Units"
    elif plot_mode == "force":
        value_col = "Force_N"
        label = "Force"
        ylabel = "Force (N)"
    else:
        raise ValueError("plot_mode must be 'raw', 'filtered', or 'force'")

    required = {"Host_Time_s", value_col}
    if not required.issubset(df.columns):
        print(f"CSV missing required columns: {required}")
        return

    # --- numeric coercion ---
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df["Host_Time_s"] = pd.to_numeric(df["Host_Time_s"], errors="coerce")
    df.dropna(subset=["Host_Time_s", value_col], inplace=True)

    if df.empty:
        print("No valid data to plot.")
        return

    # --- relative time ---
    t0 = df["Host_Time_s"].iloc[0]
    df["Time_s"] = df["Host_Time_s"] - t0

    # --- plot ---
    plt.figure(figsize=(12, 6))
    plt.plot(df["Time_s"], df[value_col], label=label)
    plt.xlabel("Time since start (s)")
    plt.ylabel(ylabel)
    plt.title(f"{label} vs Time\n{os.path.basename(filepath)}")
    plt.grid(True, alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    latest_file = find_latest_csv()
    if latest_file:
        plot_grip_data(latest_file, plot_mode="force")   # or "raw", "filtered"