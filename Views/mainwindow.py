# views/main_window.py

import tkinter as tk
from tkinter import messagebox # Needed for error popups
import threading
import asyncio
import sys # Added for error handling

# Import config for button styling
from Utils import config 
from Views.recordingwindow import RecordingWindow # NEW IMPORT

class MainWindow(tk.Tk):
    """
    The main Tkinter application window (The View).
    It handles UI layout and delegates connection logic to the controllers.
    """
    
    def __init__(self, motor_controller, sensor_reader, ble_loop):
        super().__init__()
        self.title("Hardware Control App")
        self.geometry("400x300")
        self.configure(bg="black")
        
        # --- Dependency Injection ---
        self.motor_controller = motor_controller
        self.sensor_reader = sensor_reader
        self.ble_loop = ble_loop
        
        # --- State Variables ---
        self.motor_connected = False
        self.sensor_connected = False
        self.recording_window = None # Initialize as None
        # --- GUI Setup ---
        self._create_widgets()
        
    def _create_widgets(self):
        frame = tk.Frame(self, bg="black")
        frame.pack(expand=True, padx=20, pady=20)

        # --- Row 0: Motor ---
        self.motor_btn = self._create_button(frame, text="Motor", command=self._start_motor_connection_thread)
        self.motor_btn.grid(row=0, column=0, padx=(10, 4), pady=10, sticky="ew")

        self.motor_status = tk.Label(frame, width=2, bg="red")  # status dot
        self.motor_status.grid(row=0, column=1, padx=(0, 10), pady=10)

        # --- Row 1: Sensor ---
        self.sensor_btn = self._create_button(frame, text="ForceSensor", command=self._start_sensor_connection_async)
        self.sensor_btn.grid(row=1, column=0, padx=(10, 4), pady=10, sticky="ew")

        self.sensor_status = tk.Label(frame, width=2, bg="red")
        self.sensor_status.grid(row=1, column=1, padx=(0, 10), pady=10)

        # --- Row 2: Start ---
        self.start_app_btn = self._create_button(frame, text="StartApp", command=self._start_application)
        self.start_app_btn.grid(row=2, column=0, padx=10, pady=10, sticky="ew")

        self.start_status = tk.Label(frame, width=2, bg="red")
        self.start_status.grid(row=2, column=1, padx=(0, 10), pady=10)

        # initial colors
        self._set_button_color(self.motor_btn, "red")
        self._set_button_color(self.sensor_btn, "red")
        self._set_button_color(self.start_app_btn, "red")
        
    def _create_button(self, parent, text, command, state=tk.NORMAL):
        """Helper function to create a standardized button."""
        # Using placeholder values for config if it's not defined
        font_config = getattr(config, 'FONT', ("Helvetica", 10))
        width_config = getattr(config, 'BUTTON_WIDTH', 12)
        height_config = getattr(config, 'BUTTON_HEIGHT', 1)

        return tk.Button(
            parent,
            text=text,
            command=command,
            fg="black", 
            activeforeground="white",
            relief=tk.RAISED,
            width=width_config,
            height=height_config,
            font=font_config,
            state=state
        )

    # --- UI Update Methods ---
    def _set_button_color(self, button: tk.Button, color: str):
        button.config(bg=color, activebackground=color)

    def _set_status_color(self, which: str, color: str):
        if which == "motor":
            self.motor_status.config(bg=color)
        elif which == "sensor":
            self.sensor_status.config(bg=color)
        elif which == "start":
            self.start_status.config(bg=color)

    def _check_start_condition(self):
        if self.motor_connected and self.sensor_connected:
            self._set_button_color(self.start_app_btn, "green")
            self._set_status_color("start", "green")
            self.start_app_btn.config(state=tk.NORMAL)
        else:
            self._set_button_color(self.start_app_btn, "red")
            self._set_status_color("start", "red")
            #TODO self.start_app_btn.config(state=tk.DISABLED)
    # --- MOTOR CONNECTION LOGIC (Synchronous Thread) ---

    def _start_motor_connection_thread(self):
        """Handles connection/disconnection state and starts the connection task in a thread."""
        if self.motor_connected:
            # Disconnection logic
            self.motor_controller.close()
            self.motor_connected = False
            self._update_button_color(self.motor_btn, "red")
            self.motor_btn.config(text="Motor", state=tk.NORMAL)
            self._check_start_condition()
            return

        # Connection logic
        self.motor_btn.config(state=tk.DISABLED, text="Connecting...")
        thread = threading.Thread(target=self._motor_connection_task)
        thread.daemon = True 
        thread.start()

    def _motor_connection_task(self):
        """Delegates work: Calls the controller method."""
        success = self.motor_controller.connect_to_pico()
        
        # Use winfo_exists() check before scheduling the callback
        if self.winfo_exists():
            self.after(0, lambda: self._handle_motor_connection_result(success))

    def _handle_motor_connection_result(self, success):
        self.motor_connected = success
        color = "green" if success else "red"
        text = "Motor (OK)" if success else "Motor (FAIL)"

        self._set_button_color(self.motor_btn, color)
        self._set_status_color("motor", color)
        self.motor_btn.config(text=text, state=tk.NORMAL)

        self._check_start_condition()

    # --- SENSOR CONNECTION LOGIC (Asyncio Threadsafe) ---
    def _start_sensor_connection_async(self):
        """Schedules the sensor connection task or disconnection coroutine."""
        
        if self.sensor_connected:
            # --- DISCONNECTION LOGIC ---
            self.sensor_btn.config(state=tk.DISABLED, text="Disconnecting...")
            
            # Call the disconnect coroutine
            asyncio.run_coroutine_threadsafe(
                self.sensor_reader.disconnect_device(), self.ble_loop
            ).add_done_callback(self._handle_sensor_disconnection_callback)
            
            return
        
        # --- CONNECTION LOGIC ---
        self.sensor_btn.config(state=tk.DISABLED, text="Connecting...")
        
        # Schedule the connection coroutine
        asyncio.run_coroutine_threadsafe(
            self.sensor_reader.connect_device(), self.ble_loop
        ).add_done_callback(self._handle_sensor_connection_callback)

    def _handle_sensor_connection_callback(self, future):
        """Called when the async connect_device task is complete (succeeded or failed)."""
        
        # --- CRITICAL FIX: Check if the Tkinter object is valid FIRST ---
        if not self.winfo_exists():
            print("[GUI-WARNING] MainWindow closed before sensor connection result was received.")
            return

        try:
            # Get the result (True/False) from connect_device
            success = future.result() 
        except Exception as e:
            # Log the error, but don't crash the main thread
            print(f"[SENSOR] Connection task failed with exception: {e}", file=sys.stderr)
            success = False
        
        # Safely schedule the GUI update on the main thread
        self.after(0, lambda: self._handle_sensor_result(success))


    def _handle_sensor_disconnection_callback(self, future):
        """Handles GUI update after the explicit close command is executed."""
        
        # --- CRITICAL FIX: Check if the Tkinter object is valid FIRST ---
        if not self.winfo_exists():
            print("[GUI-WARNING] MainWindow closed before sensor disconnection result was received.")
            return
            
        try:
            future.result()
        except Exception as e:
            print(f"[SENSOR] Disconnection task failed: {e}", file=sys.stderr)
        
        # Safely schedule the GUI update on the main thread
        self.after(0, lambda: self._handle_sensor_result(False))

    def _handle_sensor_result(self, success):
        self.sensor_connected = success
        color = "green" if success else "red"
        text = "Sensor (OK)" if success else "ForceSensor (FAIL)"

        self._set_button_color(self.sensor_btn, color)
        self._set_status_color("sensor", color)
        self.sensor_btn.config(text=text, state=tk.NORMAL)

        self._check_start_condition()

    # --- APPLICATION START ---
    def _start_application(self):
        """Action for the StartApp button: Hides this window and opens the RecordingWindow."""
        print("\n*** APPLICATION STARTED ***")
        
        #TODO Enable after testing
        # if not (self.motor_connected and self.sensor_connected):
        #     messagebox.showwarning("Connection Required", "Both Motor and Force Sensor must be connected to proceed.")
        #     return

        # 1. Hide the current window
        self.withdraw()
        
        # 2. Open the new recording screen, passing the controllers
        self.recording_window = RecordingWindow(self, self.motor_controller, self.sensor_reader)
        
        # When the recording window closes, show the main window again
        self.recording_window.protocol("WM_DELETE_WINDOW", self._on_recording_window_close)

    def _on_recording_window_close(self):
        """Called when the Recording Window is closed by the user."""
        if self.recording_window:
            self.recording_window.destroy()
            self.recording_window = None
        
        self.deiconify() # Show the main connection window again
        self.start_app_btn.config(state=tk.NORMAL) # Re-enable the StartApp button

    # --- Cleanup method (called by orchestrator) ---
    def cleanup(self):
        """Closes the window."""
        self.destroy()