import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
import tkinter as tk
from tkinter import ttk, messagebox

READINGS_DIR = "readings"


def plot_grip_data(filepath, *, plot_mode="force"):
    """
    plot_mode:
      - "force"    -> Force_N
      - "raw"      -> Raw_V3
      - "filtered" -> Raw_V3_Filtered
    """
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        messagebox.showerror("Read error", f"Error reading:\n{filepath}\n\n{e}")
        return

    if "Host_Time_s" not in df.columns:
        messagebox.showerror("Bad file", "CSV missing required column 'Host_Time_s'.")
        return

    mode_map = {
        "force": ("Force_N", "Force (N)", "Force Over Time"),
        "raw": ("Raw_V3", "Raw V3 (ADC units)", "Raw V3 Over Time"),
        "filtered": ("Raw_V3_Filtered", "Filtered Raw V3 (ADC units)", "Filtered Raw V3 Over Time"),
    }

    if plot_mode not in mode_map:
        messagebox.showerror("Bad selection", f"Unknown plot mode: {plot_mode}")
        return

    value_col, y_label, title_prefix = mode_map[plot_mode]

    if value_col not in df.columns:
        messagebox.showerror(
            "Bad file",
            f"CSV missing required column '{value_col}'.\n"
            f"Found columns:\n{', '.join(df.columns)}"
        )
        return

    # Coerce to numeric
    df["Host_Time_s"] = pd.to_numeric(df["Host_Time_s"], errors="coerce")
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")

    df.dropna(subset=["Host_Time_s", value_col], inplace=True)
    if df.empty:
        messagebox.showinfo("No data", "No valid numeric data to plot.")
        return

    # Relative time base
    time_origin = df["Host_Time_s"].min()
    df["Time_s"] = df["Host_Time_s"] - time_origin

    # Plot
    plt.figure(figsize=(12, 6))
    plt.plot(df["Time_s"], df[value_col], label=value_col)
    plt.title(f"{title_prefix}\nFile: {os.path.basename(filepath)}", fontsize=14)
    plt.xlabel("Time since start (s)", fontsize=12)
    plt.ylabel(y_label, fontsize=12)
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.legend()
    plt.tight_layout()
    plt.show()


def pick_and_plot_from_readings():
    """Popup browser for readings/<folder>/<file>.csv then plot selected."""
    if not os.path.isdir(READINGS_DIR):
        messagebox.showerror("Missing folder", f"Folder not found: {READINGS_DIR}")
        return

    folders = sorted([
        name for name in os.listdir(READINGS_DIR)
        if os.path.isdir(os.path.join(READINGS_DIR, name))
    ])

    if not folders:
        messagebox.showinfo("No folders", f"No subfolders found in '{READINGS_DIR}'.")
        return

    win = tk.Toplevel()
    win.title("Select a reading file to plot")
    win.geometry("950x500")

    frm = ttk.Frame(win, padding=10)
    frm.pack(fill="both", expand=True)

    # --- plot mode selector ---
    top = ttk.Frame(frm)
    top.pack(fill="x", pady=(0, 10))

    ttk.Label(top, text="Plot:").pack(side="left")
    plot_mode_var = tk.StringVar(value="force")
    plot_mode_combo = ttk.Combobox(
        top,
        textvariable=plot_mode_var,
        state="readonly",
        values=["force", "raw", "filtered"],
        width=12,
    )
    plot_mode_combo.pack(side="left", padx=(6, 0))

    cols = ttk.Frame(frm)
    cols.pack(fill="both", expand=True)

    left = ttk.Frame(cols)
    left.pack(side="left", fill="both", expand=True)

    right = ttk.Frame(cols)
    right.pack(side="left", fill="both", expand=True, padx=(10, 0))

    ttk.Label(left, text="Folders").pack(anchor="w")
    folder_list = tk.Listbox(left, exportselection=False)
    folder_list.pack(fill="both", expand=True)

    ttk.Label(right, text="CSV files in selected folder").pack(anchor="w")
    file_list = tk.Listbox(right, exportselection=False)
    file_list.pack(fill="both", expand=True)

    for f in folders:
        folder_list.insert(tk.END, f)

    def load_files_for_selected_folder(_evt=None):
        file_list.delete(0, tk.END)
        sel = folder_list.curselection()
        if not sel:
            return
        folder_name = folder_list.get(sel[0])
        folder_path = os.path.join(READINGS_DIR, folder_name)

        files = sorted(glob.glob(os.path.join(folder_path, "*.csv")))
        for path in files:
            file_list.insert(tk.END, os.path.basename(path))

    folder_list.bind("<<ListboxSelect>>", load_files_for_selected_folder)

    def do_plot():
        fsel = folder_list.curselection()
        sel = file_list.curselection()
        if not fsel:
            messagebox.showwarning("Select folder", "Please select a folder.")
            return
        if not sel:
            messagebox.showwarning("Select file", "Please select a CSV file.")
            return

        folder_name = folder_list.get(fsel[0])
        file_name = file_list.get(sel[0])
        full_path = os.path.join(READINGS_DIR, folder_name, file_name)

        mode = plot_mode_var.get()
        win.destroy()
        plot_grip_data(full_path, plot_mode=mode)

    btns = ttk.Frame(frm)
    btns.pack(fill="x", pady=(10, 0))
    ttk.Button(btns, text="Plot selected file", command=do_plot).pack(side="right")
    ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right", padx=(0, 8))

    # preselect first folder to populate files
    folder_list.selection_set(0)
    load_files_for_selected_folder()


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    pick_and_plot_from_readings()
    root.mainloop()