# utils/config.py

import platform
import serial.tools.list_ports

# ====================================================================
# MOTOR (SERIAL) CONFIGURATION
# ====================================================================

# NOTE: You must update this to match the serial port of your Pico W.
# Example for macOS: '/dev/tty.usbmodem101'
# Example for Windows: 'COM3'
SERIAL_PORT = '/dev/tty.usbmodem1101' 
BAUD_RATE = 115200

# ====================================================================
# FORCE SENSOR (BLE) CONFIGURATION
# ====================================================================

# NOTE: You must update these UUIDs and address for your device.

# Data FROM device TO PC (Notify)
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E" 
# Data FROM PC TO device (Write)
UART_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"

# Device address configuration
# NOTE: Update the address that matches your OS and device.
BLE_ADDRESS = (
    # Example for Windows/Linux
    "F5:8B:A2:4C:AD:9C"  
    if platform.system() != "Darwin"
    # Example for macOS
    else "6375EA4B-23F2-5C9E-249F-5EC7660C1DA1" 
)

# ====================================================================
# GUI CONFIGURATION
# ====================================================================

BUTTON_WIDTH = 15
BUTTON_HEIGHT = 2
FONT = ("Helvetica", 12, "bold")