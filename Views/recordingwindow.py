# views/recording_window.py

import tkinter as tk
from tkinter import messagebox
import threading 
import asyncio 

from Utils import config
class RecordingWindow(tk.Toplevel):
    """
    The second application screen for inputting test parameters and starting the recording.
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
        
        # --- UI Setup ---
        self._create_widgets()

        self.cm_input.trace_add("write", lambda *args: self._validate_inputs())
        self.speed_input.trace_add("write", lambda *args: self._validate_inputs())

        # CRITICAL: Use custom protocol to handle manual window close
        self.protocol("WM_DELETE_WINDOW", self.close_window_or_exit)

    def _create_widgets(self):
        """Creates the input boxes and button."""
        main_frame = tk.Frame(self, bg="black", padx=20, pady=20)
        main_frame.pack(expand=True, fill="both")

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
            state=tk.DISABLED, 
            fg="white", bg="darkred", activebackground="red",
            width=config.BUTTON_WIDTH, height=config.BUTTON_HEIGHT, font=config.FONT
        )
        self.start_btn.pack(pady=20)
        
        self.status_label = tk.Label(main_frame, text="Status: Ready", bg="black", fg="yellow")
        self.status_label.pack(pady=5)

    def _validate_inputs(self):
        """Validates input fields and enables/disables the Start button."""
        cm_valid = False
        speed_valid = False
        
        try:
            cm_val = int(self.cm_input.get())
            if cm_val > 0:
                cm_valid = True
        except ValueError:
            pass

        try:
            speed_val = float(self.speed_input.get())
            if 0.0 < speed_val <= 1.0:
                speed_valid = True
        except ValueError:
            pass

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
        """Coordinates the motor movement and sensor data logging simultaneously."""
        ble_loop = self.master.ble_loop 
        
        try:
            print("\n*** RECORDING STARTED ***")
            
            # 1. Start continuous sensor data logging
            asyncio.run_coroutine_threadsafe(self.sensor_reader.start_reading(), ble_loop).result(timeout=5)
            
            # 2. Send the motor move command (Synchronous/Blocking operation)
            motor_output_future = asyncio.run_coroutine_threadsafe(
                 self.motor_controller.async_run_command(
                     self.motor_controller.send_move_command, distance_cm, speed_mps, 1
                 ),
                 ble_loop 
            )
            motor_output = motor_output_future.result() 
            print(f"[MOTOR] Command Response: {motor_output.strip()}")

            # 3. Wait for Motor Movement to Complete
            time_to_wait = max(10, distance_cm / (speed_mps * 100)) + 1 
            print(f"[WAIT] Waiting for movement completion ({time_to_wait:.1f} s)...")
            
            asyncio.run_coroutine_threadsafe(asyncio.sleep(time_to_wait), ble_loop).result() 

            # 4. Stop sensor data acquisition and Save Data
            asyncio.run_coroutine_threadsafe(self.sensor_reader.stop_reading(), ble_loop).result(timeout=5)
            
            print("*** RECORDING FINISHED ***")
            
            if self.winfo_exists():
                self.after(0, lambda: self._recording_finished(True))

        except Exception as e:
            # Emergency stop sensor reading and save if error occurs
            asyncio.run_coroutine_threadsafe(self.sensor_reader.stop_reading(), ble_loop)
            print(f"FATAL ERROR during recording task: {e}")
            
            if self.winfo_exists():
                self.after(0, lambda: self._recording_finished(False))

    def _recording_finished(self, success):
        """Updates the GUI after the recording is complete and initiates shutdown."""
        self.start_btn.config(state=tk.NORMAL)
        if success:
            self.status_label.config(text="Status: Recording Complete! Data Saved. Closing...", fg="lightgreen")
            
            # --- Initiate clean shutdown sequence ---
            if self.winfo_exists():
                # Schedule the shutdown on the main Tkinter thread
                self.after(500, self._initiate_shutdown) 
            
        else:
            self.status_label.config(text="Status: Recording Failed. Check logs.", fg="red")
            messagebox.showerror("Recording Error", "The recording failed. See console log for details.")

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
        if messagebox.askyesno("Exit Application", "Recording is complete/aborted. Do you want to close the entire application?"):
             # Use the safer shutdown sequence
             self._initiate_shutdown()
        else:
             # If user chooses not to exit, just destroy this window and show the main one
             self.destroy()
             self.master.deiconify()