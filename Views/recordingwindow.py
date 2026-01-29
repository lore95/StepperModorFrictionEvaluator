import tkinter as tk
from tkinter import messagebox
import threading
import asyncio
import subprocess
import os
import re
import numpy as np
import matplotlib.pyplot as plt
import csv
from typing import Optional

from Utils import config
from Utils.calculateDynamicAndStaticFriciton import (
    estimate_static_dynamic_forces,
    load_time_force,
    clean_time_force_for_friction
)

class RecordingWindow(tk.Toplevel):
    """
    The second application screen for inputting test parameters and starting the recording.
    Now the view is divided into three rows:
      1. Distance and speed inputs
      2. Direction selection (clockwise or counter‑clockwise)
      3. Action buttons (Start Recording, Plot, and Cancel)
    """

    def __init__(self, master, motor_controller, sensor_reader):
        super().__init__(master)
        self.master = master
        self.title("Recording Parameters")
        self.geometry("500x350")
        self.configure(bg="black")

        # --- Dependency Injection ---
        self.motor_controller = motor_controller
        self.sensor_reader = sensor_reader

        # --- Variables ---
        self.cm_input = tk.StringVar(self)
        self.speed_input = tk.StringVar(self)
        self.weight_input = tk.StringVar(self)
        self.turfID_input = tk.StringVar(self)

        # direction_input holds the selected direction: 1 for CCW, 0 for CW, -1 if none selected
        self.direction_input = tk.IntVar(self, value=-1)

        # --- UI Setup ---
        self._create_widgets()

        self.cm_input.trace_add("write", lambda *args: self._validate_inputs())
        self.speed_input.trace_add("write", lambda *args: self._validate_inputs())
        self.weight_input.trace_add("write", lambda *args: self._validate_inputs())
        self.turfID_input.trace_add("write", lambda *args: self._validate_inputs())

        # CRITICAL: Use custom protocol to handle manual window close
        self.protocol("WM_DELETE_WINDOW", self.close_window_or_exit)

    def _create_widgets(self):
        """Creates the input boxes and buttons laid out in three rows."""
        # Parent frame to hold everything
        main_frame = tk.Frame(self, bg="black", padx=20, pady=20)
        main_frame.pack(expand=True, fill="both")

        # Title
        title_label = tk.Label(
            main_frame,
            text="Set Motor Parameters",
            bg="black",
            fg="darkgray",
            font=("Helvetica", 16, "bold"),
        )
        title_label.pack(pady=10)

        # Row 1: Distance and Speed
        row1 = tk.Frame(main_frame, bg="black")
        row1.pack(pady=10, fill="x")

        # Distance input
        dist_label = tk.Label(row1, text="Distance (cm):", bg="black", fg="darkgray", font=config.FONT)
        dist_label.grid(row=0, column=0, padx=5, pady=5, sticky="e")
        dist_entry = tk.Entry(row1, textvariable=self.cm_input, width=10, font=config.FONT, justify="center")
        dist_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # Speed input
        speed_label = tk.Label(row1, text="Speed (m/s):", bg="black", fg="darkgray", font=config.FONT)
        speed_label.grid(row=0, column=2, padx=5, pady=5, sticky="e")
        speed_entry = tk.Entry(row1, textvariable=self.speed_input, width=10, font=config.FONT, justify="center")
        speed_entry.grid(row=0, column=3, padx=5, pady=5, sticky="w")

        weight_label = tk.Label(row1, text="weight (kg):", bg="black", fg="darkgray", font=config.FONT)
        weight_label.grid(row=1, column=0, padx=5, pady=5, sticky="e")
        weight_entry = tk.Entry(row1, textvariable=self.weight_input, width=10, font=config.FONT, justify="center")
        weight_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")


        turf_label = tk.Label(row1, text="Turf/lane ID (10 char):", bg="black", fg="darkgray", font=config.FONT)
        turf_label.grid(row=1, column=2, padx=5, pady=5, sticky="e")
        turf_entry = tk.Entry(row1, textvariable=self.turfID_input, width=10, font=config.FONT, justify="center")
        turf_entry.grid(row=1, column=3, padx=5, pady=5, sticky="w")

        # Row 2: Direction selection buttons
        row2 = tk.Frame(main_frame, bg="black")
        row2.pack(pady=10)

        dir_label = tk.Label(row2, text="Direction:", bg="black", fg="darkgray", font=config.FONT)
        dir_label.pack(side=tk.LEFT, padx=5)

        # Counter‑clockwise button (green)
        self.ccw_button = tk.Button(
            row2,
            text="Reel Out",
            width=15,
            bg="green",
            fg="darkgray",
            activebackground="darkgreen",
            command=lambda: self._set_direction(1),
            font=config.FONT,
        )
        self.ccw_button.pack(side=tk.LEFT, padx=5)

        # Clockwise button (red)
        self.cw_button = tk.Button(
            row2,
            text="Reel In",
            width=15,
            bg="red",
            fg="darkgray",
            activebackground="darkred",
            command=lambda: self._set_direction(0),
            font=config.FONT,
        )
        self.cw_button.pack(side=tk.LEFT, padx=5)

        # Row 3: Action buttons
        row3 = tk.Frame(main_frame, bg="black")
        row3.pack(pady=20)
        

        # Start Recording button (initially disabled)
        self.start_btn = tk.Button(
            row3,
            text="Start Recording",
            command=self._start_recording,
            state=tk.DISABLED,
            fg="darkgray",
            bg="darkred",
            activebackground="red",
            width=config.BUTTON_WIDTH,
            height=config.BUTTON_HEIGHT,
            font=config.FONT,
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)

        # Plot button (always available)
        self.plot_btn = tk.Button(
            row3,
            text="Plot",
            command=self._launch_plot,
            fg="darkgray",
            bg="blue",
            activebackground="navy",
            width=config.BUTTON_WIDTH,
            height=config.BUTTON_HEIGHT,
            font=config.FONT,
        )
        self.plot_btn.pack(side=tk.LEFT, padx=5)

        # Close button to dismiss this window (does not quit the entire app)
        self.close_btn = tk.Button(
            row3,
            text="Close",
            command=self.close_window_or_exit,
            fg="darkgray",
            bg="gray",
            activebackground="darkgray",
            width=config.BUTTON_WIDTH,
            height=config.BUTTON_HEIGHT,
            font=config.FONT,
        )
        self.close_btn.pack(side=tk.LEFT, padx=5)
        
        row4 = tk.Frame(main_frame, bg="black")
        row4.pack(pady=20)
        # compare friction between turf_ids
        self.close_btn = tk.Button(
            row4,
            text="Copare friction",
            command=self.compare_friction,
            fg="darkgray",
            bg="gray",
            activebackground="darkgray",
            width=config.BUTTON_WIDTH,
            height=config.BUTTON_HEIGHT,
            font=config.FONT,
        )
        self.close_btn.pack(side=tk.LEFT, padx=5)
        # Status label at the bottom
        self.status_label = tk.Label(
            main_frame,
            text="Status: Ready",
            bg="black",
            fg="yellow",
            font=config.FONT,
        )
        self.status_label.pack(pady=5)

    def _set_direction(self, value: int):
        """Sets the direction variable and updates button styles."""
        self.direction_input.set(value)
        # Update button colours to indicate selection
        if value == 1:
            # CCW selected
            self.ccw_button.config(relief=tk.SUNKEN)
            self.cw_button.config(relief=tk.RAISED)
        elif value == 0:
            # CW selected
            self.cw_button.config(relief=tk.SUNKEN)
            self.ccw_button.config(relief=tk.RAISED)
        # Validate inputs whenever direction changes
        self._validate_inputs()

    def _validate_inputs(self):
        """Validates input fields and direction selection; enables/disables Start button."""
        cm_valid = False
        speed_valid = False
        weight_valid = False
        turfID_valid = False
        direction_valid = self.direction_input.get() in (0, 1)

        try:
            cm_val = int(self.cm_input.get())
            if cm_val > 0:
                cm_valid = True
        except ValueError:
            pass

        try:
            speed_val = float(self.speed_input.get())
            # The speed should be positive but not exceed 1.0 m/s as per config
            if 0.0 < speed_val <= 1.0:
                speed_valid = True
        except ValueError:
            pass
        try:
            weight_val = float(self.weight_input.get())
            # The weight should be positive but not exceed 100 kg as per config
            if 0.0 < weight_val <= 200.0:
                weight_valid = True
        except ValueError:
            pass
        try:
            turfID_valid = self.turfID_input.get()
            # The turfID should be between 0 and 10 chars
            if len(turfID_valid) < 10 and len(turfID_valid) > 0: 
                turfID_valid = True
        except ValueError:
            pass

        # All conditions must be met: motor and sensor connected, valid cm, valid speed,weight insterted, and direction selected
        if (
            #TODO reanable after testing # self.motor_controller.is_connected
            # and self.sensor_reader.is_connected
            cm_valid
            and speed_valid
            and direction_valid
            and weight_valid
            and turfID_valid
        ):
            self.start_btn.config(state=tk.NORMAL, bg="green", activebackground="lightgreen")
            self.status_label.config(text="Status: Input Valid", fg="lightgreen")
        else:
            self.start_btn.config(state=tk.DISABLED, bg="darkred", activebackground="red")
            self.status_label.config(text="Status: Enter Valid Parameters", fg="yellow")

    def _start_recording(self):
        """Action when 'Start Recording' is pressed."""
        try:
            distance_cm = int(self.cm_input.get())
            speed_mps = float(self.speed_input.get())
            weight_kg = int(self.weight_input.get())
            turf_id = self.turfID_input.get()
            direction = int(self.direction_input.get())  # 1 = CCW, 0 = CW
        except ValueError:
            messagebox.showerror("Input Error", "Check Distance (cm) and Speed (m/s) fields.")
            return

        self.status_label.config(text="Status: STARTING RECORDING...", fg="cyan")
        self.start_btn.config(state=tk.DISABLED)

        # Start the data acquisition and motor movement in a background thread
        threading.Thread(
            target=self._recording_task,
            args=(distance_cm, speed_mps, weight_kg, direction,turf_id),
            daemon=True,
        ).start()

    def _launch_plot(self):
        """Launches the plot.py script located in the Utils folder."""
        try:
            # Use subprocess to run the script asynchronously; you may adjust the python executable
            subprocess.Popen(["python", "Utils/plotfilebyname.py"])
        except Exception as exc:
            messagebox.showerror("Plot Error", f"Could not launch plot script:\n{exc}")

    def _recording_task(self, distance_cm, speed_mps, weight, direction, turf_id):
        """Coordinates the motor movement and sensor data logging simultaneously."""
        ble_loop = self.master.ble_loop

        try:
            print("\n*** RECORDING STARTED ***")

            # 1. Start continuous sensor data logging
            asyncio.run_coroutine_threadsafe(self.sensor_reader.start_reading(), ble_loop).result(timeout=5)

            # 2. Send the motor move command (Synchronous/Blocking operation)
            motor_output_future = asyncio.run_coroutine_threadsafe(
                self.motor_controller.async_run_command(
                    self.motor_controller.send_move_command, distance_cm, speed_mps, direction
                ),
                ble_loop,
            )
            motor_output = motor_output_future.result()
            print(f"[MOTOR] Command Response: {motor_output.strip()}")

            # 3. Wait for Motor Movement to Complete (rough estimation)
            time_to_wait = max(10, distance_cm / (speed_mps * 100)) + 1
            print(f"[WAIT] Waiting for movement completion ({time_to_wait:.1f} s)...")
            asyncio.run_coroutine_threadsafe(asyncio.sleep(time_to_wait), ble_loop).result()

            # 4. Stop sensor data acquisition and save data
            asyncio.run_coroutine_threadsafe(self.sensor_reader.stop_reading(speed_mps,distance_cm,weight,turf_id), ble_loop).result(timeout=5)

            print("*** RECORDING FINISHED ***")

            # Update GUI from the main thread
            if self.winfo_exists():
                self.after(0, lambda: self._recording_finished(True))

        except Exception as e:
            # Emergency stop sensor reading and save if error occurs
            asyncio.run_coroutine_threadsafe(self.sensor_reader.stop_reading(speed_mps,distance_cm,weight,turf_id), ble_loop)
            print(f"FATAL ERROR during recording task: {e}")

            if self.winfo_exists():
                self.after(0, lambda: self._recording_finished(False))

    def _recording_finished(self, success: bool):
        """Updates the GUI after the recording is complete and initiates shutdown."""
        # Re-enable the Start button so the user can run another recording
        self.start_btn.config(state=tk.NORMAL, bg="darkred")
        if success:
            # When recording is finished successfully, update the status but do NOT
            # automatically quit the application. Instead, the user can press the
            # "Quit" button if they want to exit. Leave the window open for
            # subsequent recordings.
            self.status_label.config(
                text="Status: Recording Complete! Data Saved.", fg="lightgreen"
            )
        else:
            # In case of failure, inform the user via the label and a message box.
            self.status_label.config(
                text="Status: Recording Failed. Check logs.", fg="red"
            )
            messagebox.showerror(
                "Recording Error", "The recording failed. See console log for details."
            )

    def _initiate_shutdown(self):
        """
        Triggers the final disconnection and closes the main application via the root window.
        """
        print("\n[SHUTDOWN] Initiating cleanup and exit from Recording Window.")
        # 1. Disconnect Motor (Synchronous)
        self.motor_controller.close()
        # 2. Disconnect Sensor (Asynchronous)
        try:
            ble_loop = self.master.ble_loop
            asyncio.run_coroutine_threadsafe(self.sensor_reader.disconnect_device(), ble_loop)
            print("[SHUTDOWN] Scheduled BLE disconnection.")
        except Exception as e:
            print(f"[SHUTDOWN] Warning: Could not schedule BLE disconnect. Error: {e}")
        # 3. Close the entire application by quitting the root Tkinter loop
        self.master.quit()

    def close_window_or_exit(self):
        """Destroys the secondary window or initiates full exit based on user choice."""
        if messagebox.askyesno(
            "Exit Application", "Recording is complete/aborted. Do you want to close the entire application?"
        ):
            # Use the safer shutdown sequence
            self._initiate_shutdown()
        else:
            # If user chooses not to exit, just destroy this window and show the main one
            self.destroy()
            self.master.deiconify()

    def compare_friction(self):
        readings_dir = "readings"
        if not os.path.isdir(readings_dir):
            messagebox.showerror("Compare friction", f"'{readings_dir}' folder not found.")
            return

        folders = sorted(
            d for d in os.listdir(readings_dir)
            if os.path.isdir(os.path.join(readings_dir, d))
        )

        if not folders:
            messagebox.showinfo("Compare friction", "No folders found.")
            return

        # ---- popup ----
        top = tk.Toplevel(self)
        top.title("Select folders to compare")

        tk.Label(top, text="Select at least two folders:").pack(padx=10, pady=(10, 0))

        lb = tk.Listbox(top, selectmode="multiple", height=min(15, len(folders)))
        lb.pack(padx=10, pady=10, fill="both", expand=True)

        for f in folders:
            lb.insert("end", f)

        def _toggle(event):
            idx = lb.nearest(event.y)
            if idx in lb.curselection():
                lb.selection_clear(idx)
            else:
                lb.selection_set(idx)
            return "break"

        lb.bind("<ButtonRelease-1>", _toggle)

        def _parse_weight(fname: str) -> Optional[float]:
            m = re.search(r"_(\d+(?:\.\d+)?)kg_grip_data\.csv$", fname)
            return float(m.group(1)) if m else None

        def _on_select():
            selected = [lb.get(i) for i in lb.curselection()]
            if len(selected) < 2:
                messagebox.showwarning("Compare friction", "Select at least 2 folders.")
                return

            static_by_folder = {}
            dynamic_by_folder = {}
            all_weights = set()

            for folder in selected:
                fpath = os.path.join(readings_dir, folder)
                s_map, d_map = {}, {}

                for fname in os.listdir(fpath):
                    if not fname.endswith("kg_grip_data.csv"):
                        continue

                    w = _parse_weight(fname)
                    if w is None:
                        continue

                    csv_path = os.path.join(fpath, fname)

                    try:
                        df = load_time_force(csv_path)

                        df_clean = clean_time_force_for_friction(
                            df,
                            spike_window=21,
                            spike_sigmas=6.0,
                            drop_sigmas=8.0,
                            drop_min_consecutive=2,
                            spike_replace="median",
                        )

                        res = estimate_static_dynamic_forces(df_clean, include_peak_in_dynamic=False)
                        Fs = res["Fs_max"]
                        Fk = res["Fk_mean"]

                        s_map.setdefault(w, []).append(Fs)
                        d_map.setdefault(w, []).append(Fk)
                        all_weights.add(w)

                        # Optional: if you want to see what window it used
                        # print(f"[{folder}] {fname} w={w}kg Fs={Fs:.2f}N (peak@{res['peak_idx']}) "
                        #       f"Fk={Fk:.2f}N (dyn_n={res['dynamic_n']} trough@{res['trough_idx']})")

                    except Exception as e:
                        print(f"[COMPARE] Skipping {csv_path}: {e}")

                if s_map:
                    static_by_folder[folder] = s_map
                    dynamic_by_folder[folder] = d_map

            if len(static_by_folder) < 2:
                messagebox.showerror("Compare friction", "Not enough usable data.")
                return

            weights = sorted(all_weights)

            # ---- Static plot ----
            plt.figure()
            for folder, wmap in static_by_folder.items():
                xs, ys = [], []
                for w in weights:
                    if w in wmap:
                        xs.append(w)
                        ys.append(np.mean(wmap[w]))
                if xs:
                    plt.plot(xs, ys, marker="o", label=folder)
                    # Label each point with its force value
                    for x, y in zip(xs, ys):
                        plt.annotate(
                            f"{y:.1f}",
                            (x, y),
                            textcoords="offset points",
                            xytext=(0, 6),
                            ha="center",
                            fontsize=8,
                        )

            plt.xlabel("Weight (kg)")
            plt.ylabel("Static friction force Fs,max (cN)")
            plt.title("Static friction comparison")
            plt.grid(True)
            plt.legend()
            plt.tight_layout()
            plt.show()

            # ---- Dynamic plot ----
            plt.figure()
            for folder, wmap in dynamic_by_folder.items():
                xs, ys = [], []
                for w in weights:
                    if w in wmap:
                        xs.append(w)
                        ys.append(np.mean(wmap[w]))
                if xs:
                    plt.plot(xs, ys, marker="o", label=folder)
                    # Label each point with its force value
                    for x, y in zip(xs, ys):
                        plt.annotate(
                            f"{y:.1f}",
                            (x, y),
                            textcoords="offset points",
                            xytext=(0, 6),
                            ha="center",
                            fontsize=8,
                        )

            plt.xlabel("Weight (kg)")
            plt.ylabel("Dynamic friction force Fk (cN)")
            plt.title("Dynamic friction comparison")
            plt.grid(True)
            plt.legend()
            plt.tight_layout()
            plt.show()

            top.destroy()

        btns = tk.Frame(top)
        btns.pack(padx=10, pady=(0, 10), fill="x")

        tk.Button(btns, text="Select", command=_on_select).pack(side="right")
        tk.Button(btns, text="Cancel", command=top.destroy).pack(side="right", padx=(0, 8))

        top.grab_set()
        top.focus_set()