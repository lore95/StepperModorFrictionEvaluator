import threading
import asyncio
import sys
import queue
import concurrent.futures
from tkinter import messagebox

from Utils import config
from Controllers.motorcontroller import MotorController
from Controllers.sensorcontroller import AsyncSensorReader
from Views.mainwindow import MainWindow


def run_ble_loop(loop):
    """Target function for the background BLE thread."""
    asyncio.set_event_loop(loop)
    print("--- BLE Asynchronous Loop Started ---")
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[BLE-LOOP] Fatal error: {e}")


def main():
    print("--- Initializing Hardware Control App ---")

    motor_controller = MotorController(config.SERIAL_PORT, config.BAUD_RATE)

    # BLE asyncio loop in a background thread
    ble_loop = asyncio.new_event_loop()
    ble_thread = threading.Thread(target=run_ble_loop, args=(ble_loop,), daemon=True)
    ble_thread.start()

    # Create sensor reader (popup callback will be attached after Tk is created)
    sensor_reader = AsyncSensorReader(config.BLE_ID, config.UART_TX_CHAR_UUID,    ble_loop)

    # Create GUI (Tk root)
    app = MainWindow(motor_controller, sensor_reader, ble_loop)

    # ---------- Thread-safe UI prompt system ----------
    ui_requests: "queue.Queue[tuple[str, str, concurrent.futures.Future]]" = queue.Queue()

    def _process_ui_requests():
        try:
            while True:
                title, msg, fut = ui_requests.get_nowait()
                try:
                    ans = messagebox.askyesno(title, msg)
                    if not fut.done():
                        fut.set_result(bool(ans))
                except Exception as e:
                    if not fut.done():
                        fut.set_exception(e)
        except queue.Empty:
            pass
        app.after(100, _process_ui_requests)

    app.after(100, _process_ui_requests)

    async def prompt_save_cb() -> bool:
        """
        Runs on BLE asyncio loop thread.
        Sends request to GUI thread and awaits response.
        """
        fut: concurrent.futures.Future = concurrent.futures.Future()
        ui_requests.put((
            "BLE Disconnected",
            "The BLE device disconnected.\n\nDo you want to save the data collected so far?",
            fut,
        ))
        return await asyncio.wrap_future(fut)

    # Attach callback
    sensor_reader.prompt_save_cb = prompt_save_cb
    # ---------------------------------------------------

    app.protocol("WM_DELETE_WINDOW", lambda: cleanup_and_exit(app, motor_controller, ble_loop, ble_thread))

    print("--- Starting GUI Main Loop ---")
    app.mainloop()


def cleanup_and_exit(app, motor_controller, ble_loop, ble_thread):
    print("\n--- Shutting down application ---")

    motor_controller.close()

    if ble_loop.is_running():
        print("[SHUTDOWN] Signaling asyncio loop to stop...")
        ble_loop.call_soon_threadsafe(ble_loop.stop)
        ble_thread.join(timeout=1)

    app.cleanup()
    print("Shutdown complete. Goodbye.")
    sys.exit(0)


if __name__ == "__main__":
    if not hasattr(config, "SERIAL_PORT"):
        print("FATAL: Please ensure 'Utils/config.py' is correctly defined.")
        sys.exit(1)

    main()