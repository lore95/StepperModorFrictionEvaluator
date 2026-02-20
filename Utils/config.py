# utils/config.py

import platform
import serial.tools.list_ports

# ====================================================================
# MOTOR (SERIAL) CONFIGURATION
# ====================================================================

# NOTE: You must update this to match the serial port of your Pico W.
# Example for macOS: '/dev/tty.usbmodem101'
# Example for Windows: 'COM3'
SERIAL_PORT = '/dev/tty.usbmodem101' 
BAUD_RATE = 115200
BLE_ID = "09916A0D-1C88-FFB7-9BCC-005191B357F9"
# ====================================================================
# FORCE SENSOR (BLE) CONFIGURATION
# ====================================================================

# NOTE: You must update these UUIDs and address for your device.

# Data FROM device TO PC (Notify)
UART_TX_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
# Data FROM PC TO device (Write)
UART_RX_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

# Device address configuration
# NOTE: Update the address that matches your OS and device.
SERVICE_ADDRESS = "6e400001-b5a3-f393-e0a9-e50e24dcca9e" 


# ====================================================================
# GUI CONFIGURATION
# ====================================================================

BUTTON_WIDTH = 15
BUTTON_HEIGHT = 2
FONT = ("Helvetica", 12, "bold")