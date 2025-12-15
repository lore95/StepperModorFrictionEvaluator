import tkinter as tk
from tkinter import messagebox
import threading
import asyncio
import subprocess

from Utils import config


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
        # direction_input holds the selected direction: 1 for CCW, 0 for CW, -1 if none selected
        self.direction_input = tk.IntVar(self, value=-1)

        # --- UI Setup ---
        self._create_widgets()

        self.cm_input.trace_add("write", lambda *args: self._validate_inputs())
        self.speed_input.trace_add("write", lambda *args: self._validate_inputs())

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
            fg="white",
            font=("Helvetica", 16, "bold"),
        )
        title_label.pack(pady=10)

        # Row 1: Distance and Speed
        row1 = tk.Frame(main_frame, bg="black")
        row1.pack(pady=10, fill="x")

        # Distance input
        dist_label = tk.Label(row1, text="Distance (cm):", bg="black", fg="white", font=config.FONT)
        dist_label.grid(row=0, column=0, padx=5, pady=5, sticky="e")
        dist_entry = tk.Entry(row1, textvariable=self.cm_input, width=10, font=config.FONT, justify="center")
        dist_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        # Speed input
        speed_label = tk.Label(row1, text="Speed (m/s):", bg="black", fg="white", font=config.FONT)
        speed_label.grid(row=1, column=0, padx=5, pady=5, sticky="e")
        speed_entry = tk.Entry(row1, textvariable=self.speed_input, width=10, font=config.FONT, justify="center")
        speed_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        # Row 2: Direction selection buttons
        row2 = tk.Frame(main_frame, bg="black")
        row2.pack(pady=10)

        dir_label = tk.Label(row2, text="Direction:", bg="black", fg="white", font=config.FONT)
        dir_label.pack(side=tk.LEFT, padx=5)

        # Counter‑clockwise button (green)
        self.ccw_button = tk.Button(
            row2,
            text="Counter‑clockwise",
            width=15,
            bg="green",
            fg="white",
            activebackground="darkgreen",
            command=lambda: self._set_direction(1),
            font=config.FONT,
        )
        self.ccw_button.pack(side=tk.LEFT, padx=5)

        # Clockwise button (red)
        self.cw_button = tk.Button(
            row2,
            text="Clockwise",
            width=15,
            bg="red",
            fg="white",
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
            fg="white",
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
            fg="white",
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
            fg="white",
            bg="gray",
            activebackground="darkgray",
            width=config.BUTTON_WIDTH,
            height=config.BUTTON_HEIGHT,
            font=config.FONT,
        )
        self.close_btn.pack(side=tk.LEFT, padx=5)

        # Quit button to exit the entire application
        self.quit_btn = tk.Button(
            row3,
            text="Quit",
            command=self._initiate_shutdown,
            fg="white",
            bg="darkred",
            activebackground="red",
            width=config.BUTTON_WIDTH,
            height=config.BUTTON_HEIGHT,
            font=config.FONT,
        )
        self.quit_btn.pack(side=tk.LEFT, padx=5)

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

        # All conditions must be met: motor and sensor connected, valid cm, valid speed, and direction selected
        if (
            self.motor_controller.is_connected
            and self.sensor_reader.is_connected
            and cm_valid
            and speed_valid
            and direction_valid
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
            direction = int(self.direction_input.get())  # 1 = CCW, 0 = CW
        except ValueError:
            messagebox.showerror("Input Error", "Check Distance (cm) and Speed (m/s) fields.")
            return

        self.status_label.config(text="Status: STARTING RECORDING...", fg="cyan")
        self.start_btn.config(state=tk.DISABLED)

        # Start the data acquisition and motor movement in a background thread
        threading.Thread(
            target=self._recording_task,
            args=(distance_cm, speed_mps, direction),
            daemon=True,
        ).start()

    def _launch_plot(self):
        """Launches the plot.py script located in the Utils folder."""
        try:
            # Use subprocess to run the script asynchronously; you may adjust the python executable
            subprocess.Popen(["python", "Utils/plot.py"])
        except Exception as exc:
            messagebox.showerror("Plot Error", f"Could not launch plot script:\n{exc}")

    def _recording_task(self, distance_cm, speed_mps, direction):
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
            asyncio.run_coroutine_threadsafe(self.sensor_reader.stop_reading(), ble_loop).result(timeout=5)

            print("*** RECORDING FINISHED ***")

            # Update GUI from the main thread
            if self.winfo_exists():
                self.after(0, lambda: self._recording_finished(True))

        except Exception as e:
            # Emergency stop sensor reading and save if error occurs
            asyncio.run_coroutine_threadsafe(self.sensor_reader.stop_reading(), ble_loop)
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