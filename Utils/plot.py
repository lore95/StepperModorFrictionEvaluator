import pandas as pd
import matplotlib.pyplot as plt
import os
import glob

def find_latest_csv(directory='../readings'):
    """Finds the most recently created CSV file in the specified directory."""
    try:
        # 1. Look for all CSV files in the directory
        list_of_files = glob.glob(os.path.join(directory, '*.csv'))
        
        if not list_of_files:
            print(f"Error: No CSV files found in the '{directory}' directory.")
            return None

        # 2. Find the latest file based on the creation time
        latest_file = max(list_of_files, key=os.path.getctime)
        return latest_file
    except Exception as e:
        print(f"An error occurred while searching for the file: {e}")
        return None

def plot_grip_data(filepath):
    """Loads, cleans, and plots the grip sensor data from the CSV file."""
    
    # 1. Load the CSV file into a Pandas DataFrame
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        print(f"Error reading CSV file '{filepath}': {e}")
        return

    print(f"Successfully loaded file: {os.path.basename(filepath)}")
    print(f"Total data points: {len(df)}")
    
    # 2. Data Cleaning and Preparation
    
    # The 'Raw_Data_Line' column contains the force/sensor reading as a string.
    # We assume the device sends a single numeric value per line.
    
    try:
        # Convert the raw data column to a numeric type (float)
        df['Sensor_Value'] = pd.to_numeric(df['Raw_Data_Line'], errors='coerce')
        
        # Remove any rows where the sensor value couldn't be converted (non-numeric junk)
        df.dropna(subset=['Sensor_Value'], inplace=True)
        
        if df.empty:
            print("Error: After cleaning, no valid numeric sensor data remains to plot.")
            return
            
        # Convert the host timestamp to a relative time base (Time since Start)
        time_origin = df['Host_Time_s'].min()
        df['Time_s'] = df['Host_Time_s'] - time_origin
        
    except KeyError:
        print("Error: CSV file is missing expected columns ('Host_Time_s' or 'Raw_Data_Line').")
        return
    except Exception as e:
        print(f"Error during data cleaning: {e}")
        return
    
    # 3. Create the Plot
    
    plt.figure(figsize=(12, 6))
    
    # Plot Time_s on the X-axis and Sensor_Value on the Y-axis
    plt.plot(df['Time_s'], df['Sensor_Value'], label='Grip Sensor Reading', color='royalblue')
    
    # 4. Add Labels and Title
    plt.title(f'Grip Sensor Data Over Time (File: {os.path.basename(filepath)})', fontsize=14)
    plt.xlabel('Time since Motor Start (s)', fontsize=12)
    plt.ylabel('Sensor Value (e.g., Force/Pressure Unit)', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend()
    
    # Improve layout and display the plot
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    
    # Find the latest CSV file to plot
    latest_file = find_latest_csv()
    
    if latest_file:
        plot_grip_data(latest_file)