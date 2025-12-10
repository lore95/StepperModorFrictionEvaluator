import threading
import asyncio
import sys
import time # Added for join timeout

# Import from the modular structure
from Utils import config
from Controllers.motorcontroller import MotorController
from Controllers.sensorcontroller import AsyncSensorReader
from Views.mainwindow import MainWindow

# --- Helper Function for BLE Thread ---
def run_ble_loop(loop):
    """Target function for the background BLE thread."""
    asyncio.set_event_loop(loop)
    print("--- BLE Asynchronous Loop Started ---")
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        # Graceful exit if Ctrl+C is hit while running
        pass
    except Exception as e:
        print(f"[BLE-LOOP] Fatal error: {e}")

def main():
    """Initializes controllers, views, and starts the application."""
    
    print("--- Initializing Hardware Control App ---")

    # 1. Initialize Controllers
    # NOTE: Ensure config defines SERIAL_PORT, BAUD_RATE, BLE_ADDRESS, and UART_TX_CHAR_UUID
    motor_controller = MotorController(config.SERIAL_PORT, config.BAUD_RATE)
    
    # 2. Initialize Asynchronous Environment
    ble_loop = asyncio.new_event_loop() 
    ble_thread = threading.Thread(target=run_ble_loop, args=(ble_loop,), daemon=True)
    ble_thread.start()
    
    # Pass the event loop to the sensor reader
    sensor_reader = AsyncSensorReader(config.BLE_ADDRESS, config.UART_TX_CHAR_UUID)
    
    # 3. Initialize View (The Tkinter Window)
    app = MainWindow(motor_controller, sensor_reader, ble_loop)

    # Set up cleanup hook: This runs when the user closes the main window via the X button.
    app.protocol("WM_DELETE_WINDOW", lambda: cleanup_and_exit(app, motor_controller, ble_loop, ble_thread))

    # 4. Start the GUI loop
    print("--- Starting GUI Main Loop ---")
    app.mainloop()

def cleanup_and_exit(app, motor_controller, ble_loop, ble_thread):
    """Handles graceful shutdown of all resources."""
    print("\n--- Shutting down application ---")
    
    # 1. Close Motor connection (Synchronous)
    motor_controller.close()
    
    # 2. Stop the background BLE asyncio loop
    if ble_loop.is_running():
        # Schedule the stop method to run on the BLE thread
        print("[SHUTDOWN] Signaling asyncio loop to stop...")
        ble_loop.call_soon_threadsafe(ble_loop.stop)
        
        # Wait for the thread to exit cleanly
        ble_thread.join(timeout=1)
    
    # 3. Close the GUI window
    app.cleanup()
    
    print("Shutdown complete. Goodbye.")
    sys.exit(0)


if __name__ == "__main__":
    # Add a check to ensure dependencies are available
    if not hasattr(config, 'SERIAL_PORT'):
         print("FATAL: Please ensure 'Utils/config.py' is correctly defined.")
         sys.exit(1)
         
    main()