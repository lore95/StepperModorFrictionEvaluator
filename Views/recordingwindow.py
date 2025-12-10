# views/recording_window.py

import tkinter as tk
from tkinter import messagebox
# ADD THIS LINE:
import threading 
import asyncio # You also need asyncio for run_coroutine_threadsafe

from Utils import config
class RecordingWindow(tk.Toplevel):
    """
    The second application screen for inputting test parameters and starting the recording.
    """
    
    def __init__(self, master, motor_controller, sensor_reader):
        super().__init__(master)
        self.master = master # Reference to the main window (optional)
        self.title("Recording Parameters")
        self.geometry("500x350")
        self.configure(bg="black")
        
        # --- Dependency Injection ---
        self.motor_controller = motor_controller
        self.sensor_reader = sensor_reader
        
        # --- Variables ---
        self.cm_input = tk.StringVar(self)
        self.speed_input = tk.StringVar(self)
        
        # --- UI Setup ---
        self._create_widgets()

        # Monitor inputs for validation
        self.cm_input.trace_add("write", lambda *args: self._validate_inputs())
        self.speed_input.trace_add("write", lambda *args: self._validate_inputs())

        # Ensure that if the master window closes, this one does too
        self.protocol("WM_DELETE_WINDOW", self.close_window)

    def _create_widgets(self):
        """Creates the input boxes and button."""
        main_frame = tk.Frame(self, bg="black", padx=20, pady=20)
        main_frame.pack(expand=True, fill="both")

        # Title Label
        title_label = tk.Label(main_frame, text="Set Motor Parameters", bg="black", fg="white", font=("Helvetica", 16, "bold"))
        title_label.pack(pady=10)

        # 1. Centimeters Input (Integer)
        cm_frame = tk.Frame(main_frame, bg="black")
        cm_frame.pack(pady=10)
        tk.Label(cm_frame, text="Centimeters (int):", bg="black", fg="white", font=config.FONT).pack(side=tk.LEFT, padx=5)
        self.cm_entry = tk.Entry(cm_frame, textvariable=self.cm_input, width=15, font=config.FONT, justify='center')
        self.cm_entry.pack(side=tk.LEFT, padx=5)

        # 2. Speed Input (Float)
        speed_frame = tk.Frame(main_frame, bg="black")
        speed_frame.pack(pady=10)
        tk.Label(speed_frame, text="Speed (float, max 1.0):", bg="black", fg="white", font=config.FONT).pack(side=tk.LEFT, padx=5)
        self.speed_entry = tk.Entry(speed_frame, textvariable=self.speed_input, width=15, font=config.FONT, justify='center')
        self.speed_entry.pack(side=tk.LEFT, padx=5)

        # 3. Start Recording Button
        self.start_btn = tk.Button(
            main_frame,
            text="Start Recording",
            command=self._start_recording,
            state=tk.DISABLED,  # Starts disabled
            fg="white", bg="darkred", activebackground="red",
            width=config.BUTTON_WIDTH, height=config.BUTTON_HEIGHT, font=config.FONT
        )
        self.start_btn.pack(pady=20)
        
        # Connection Status Label (for real-time feedback)
        self.status_label = tk.Label(main_frame, text="Status: Ready", bg="black", fg="yellow")
        self.status_label.pack(pady=5)

    def _validate_inputs(self):
        """Validates input fields and enables/disables the Start button."""
        cm_valid = False
        speed_valid = False
        
        try:
            # Validate Centimeters: Must be a positive integer
            cm_val = int(self.cm_input.get())
            if cm_val > 0:
                cm_valid = True
        except ValueError:
            pass # cm_valid remains False

        try:
            # Validate Speed: Must be a float between 0.0 and 1.0
            speed_val = float(self.speed_input.get())
            if 0.0 < speed_val <= 1.0:
                speed_valid = True
        except ValueError:
            pass # speed_valid remains False

        # Check overall condition
        if self.motor_controller.is_connected and self.sensor_reader.is_connected and cm_valid and speed_valid:
            self.start_btn.config(state=tk.NORMAL, bg="green", activebackground="lightgreen")
            self.status_label.config(text="Status: Input Valid")
        else:
            self.start_btn.config(state=tk.DISABLED, bg="darkred", activebackground="red")
            self.status_label.config(text="Status: Enter Valid Parameters")

    def _start_recording(self):
        """Action when 'Start Recording' is pressed."""
        
        try:
            distance_cm = int(self.cm_input.get())
            speed_mps = float(self.speed_input.get())
        except ValueError:
            messagebox.showerror("Input Error", "Check Centimeters (int) and Speed (float) fields.")
            return

        self.status_label.config(text="Status: STARTING RECORDING...", fg="cyan")
        self.start_btn.config(state=tk.DISABLED)

        # Start the data acquisition and motor movement in a background thread
        threading.Thread(target=self._recording_task, args=(distance_cm, speed_mps), daemon=True).start()

    def _recording_task(self, distance_cm, speed_mps):
        """
        Coordinates the motor movement and sensor data logging simultaneously.
        This runs in a dedicated thread.
        """
        try:
            print("\n*** RECORDING STARTED ***")
            
            # --- SETUP ---
            # Get the BLE loop from the main window reference
            ble_loop = self.master.ble_loop 
            
            # 1. Start continuous sensor data logging
            # Schedule the start_reading coroutine on the background BLE loop
            start_sensor_future = asyncio.run_coroutine_threadsafe(
                self.sensor_reader.start_reading(), ble_loop
            )
            start_sensor_future.result(timeout=5) # Wait for confirmation that logging started
            
            # 2. Send the motor move command (Synchronous/Blocking operation)
            print(f"[MOTOR] Moving {distance_cm} cm at {speed_mps} m/s...")
            
            # CRITICAL: Use the async wrapper from the MotorController to execute the blocking command
            motor_output_future = asyncio.run_coroutine_threadsafe(
                 self.motor_controller.async_run_command(
                     self.motor_controller.send_move_command, distance_cm, speed_mps, 1
                 ),
                 ble_loop # Use the BLE loop for thread management
            )
            
            # NOTE: We assume the motor moves immediately after the command is sent.
            # The future result will only return after the command is fully sent, not necessarily after the movement is complete.
            motor_output = motor_output_future.result() 
            print(f"[MOTOR] Command Response: {motor_output.strip()}")

            # 3. Wait for Motor Movement to Complete
            # Assuming the motor move command takes 'distance / speed' seconds, 
            # plus some margin (e.g., 2 seconds max motor run time for the initial start).
            
            # Example calculation: 100cm @ 0.1 m/s (10 cm/s) = 10 seconds of movement.
            time_to_wait = max(10, distance_cm / (speed_mps * 100)) + 1 # +1 second margin
            print(f"[WAIT] Waiting for movement completion ({time_to_wait:.1f} s)...")
            
            # Must use asyncio.run_coroutine_threadsafe with asyncio.sleep for the wait
            asyncio.run_coroutine_threadsafe(
                asyncio.sleep(time_to_wait), ble_loop
            ).result() 

            # 4. Stop sensor data acquisition and Save Data
            stop_sensor_future = asyncio.run_coroutine_threadsafe(
                self.sensor_reader.stop_reading(), ble_loop
            )
            stop_sensor_future.result(timeout=5) # Wait for saving to complete
            
            print("*** RECORDING FINISHED ***")
            
            # Schedule GUI update back on the main Tkinter thread
            self.after(0, lambda: self._recording_finished(True))

        except Exception as e:
            # Emergency stop sensor reading if error occurs
            asyncio.run_coroutine_threadsafe(self.sensor_reader.stop_reading(), ble_loop)
            print(f"FATAL ERROR during recording task: {e}")
            self.after(0, lambda: self._recording_finished(False))
    def _recording_finished(self, success):
        """Updates the GUI after the recording is complete."""
        self.start_btn.config(state=tk.NORMAL)
        if success:
            self.status_label.config(text="Status: Recording Complete! Data Saved.", fg="lightgreen")
        else:
            self.status_label.config(text="Status: Recording Failed. Check logs.", fg="red")
            messagebox.showerror("Recording Error", "The recording failed. See console log for details.")

    def close_window(self):
        """Destroys the secondary window."""
        self.destroy()
        # Optionally, re-enable the StartApp button on the main window if needed