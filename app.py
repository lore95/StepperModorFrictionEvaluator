# app_orchestrator.py

import threading
import asyncio
import sys

# Import from the modular structure
from Utils import config
from Controllers.motorcontroller import MotorController
from Controllers.sensorcontroller import AsyncSensorReader
from Views.mainwindow import MainWindow

# --- Helper Function for BLE Thread ---
def run_ble_loop(loop):
    """Target function for the background BLE thread."""
    asyncio.set_event_loop(loop)
    loop.run_forever()

def main():
    """Initializes controllers, views, and starts the application."""
    
    print("--- Initializing Hardware Control App ---")

    # 1. Initialize Controllers
    motor_controller = MotorController(config.SERIAL_PORT, config.BAUD_RATE)
    sensor_reader = AsyncSensorReader(config.BLE_ADDRESS, config.UART_TX_CHAR_UUID)
    
    # 2. Initialize Asynchronous Environment
    ble_loop = asyncio.new_event_loop() 
    ble_thread = threading.Thread(target=run_ble_loop, args=(ble_loop,), daemon=True)
    ble_thread.start()

    # 3. Initialize View (The Tkinter Window)
    # Pass the instantiated controllers and the asyncio loop to the view.
    app = MainWindow(motor_controller, sensor_reader, ble_loop)

    # Set up cleanup hook
    app.protocol("WM_DELETE_WINDOW", lambda: on_closing(app, motor_controller, ble_loop, ble_thread))

    # 4. Start the GUI loop
    print("--- Starting GUI Main Loop ---")
    app.mainloop()


def on_closing(app, motor_controller, ble_loop, ble_thread):
    """Handles graceful shutdown of all resources."""
    print("\n--- Shutting down application ---")
    
    # 1. Close Motor connection (Serial)
    motor_controller.close()
    
    # 2. Stop the background BLE asyncio loop
    if ble_loop.is_running():
        # Schedule the stop method to run on the BLE thread
        ble_loop.call_soon_threadsafe(ble_loop.stop)
        # Wait briefly for the thread to exit
        ble_thread.join(timeout=1)
    
    # 3. Close the GUI window
    app.cleanup()
    
    print("Shutdown complete. Goodbye.")
    sys.exit(0)


if __name__ == "__main__":
    main()