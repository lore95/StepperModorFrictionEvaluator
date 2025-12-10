# controllers/motor_controller.py

import serial
import time
import serial.tools.list_ports
import asyncio # New import needed for the async wrapper

class MotorController:
    """Manages the serial connection for the motor device (e.g., Pico W)."""
    
    def __init__(self, port, baud_rate):
        self.port = port
        self.baud_rate = baud_rate
        self.serial = None
        self.is_connected = False 

    def _wait_for_prompt(self, timeout=5, prompt=b'>>>'): 
        """Waits for the MicroPython REPL prompt."""
        t_start = time.time()
        buffer = b''
        while time.time() - t_start < timeout: 
            if self.serial:
                data = self.serial.read_all()
                if data:
                    buffer += data
                    if prompt in buffer or b'MicroPython' in buffer:
                        return buffer.decode('utf-8', errors='ignore')
            time.sleep(0.01) 
        return buffer.decode('utf-8', errors='ignore')
    
    async def async_run_command(self, command_func, *args, **kwargs):
        """Runs a synchronous command in a separate thread, returning a Future."""
        return await asyncio.to_thread(command_func, *args, **kwargs)
    
    def _run_command(self, command, wait_time=0.1):
        """Sends a command and captures the response."""
        if not self.serial or not self.serial.is_open:
            print("[MOTOR] Error: Serial not connected for command.")
            return "ERROR: DISCONNECTED"
        
        self._wait_for_prompt(timeout=2.0)
        command_bytes = (command + '\r\n').encode('utf-8')
        self.serial.write(command_bytes)
        time.sleep(wait_time) 
        
        response = self.serial.read_all().decode('utf-8', errors='ignore')
        return response

    def send_move_command(self, distance_cm, speed_mps, direction=1):
        """Sends the motor move command and returns the full output string."""
        # Ensure conversion to float for safety, though motor firmware might handle it.
        distance_cm = float(distance_cm)
        speed_mps = float(speed_mps)
        
        # This is the actual command that drives the motor:
        command = f"motor.move_at_speed({distance_cm}, {speed_mps}, {direction})"
        
        # We need to consider how long the motor takes to move.
        # If the command is non-blocking (Pico starts moving and immediately returns 'OK'), 
        # the main app logic handles the waiting. If it's blocking, this call takes time.
        return self._run_command(command, wait_time=0.1)
    
    def connect_to_pico(self):
        """Establishes serial connection and verifies the prompt."""
        print(f"\n[MOTOR] Attempting connection to Pico on {self.port}...")
        try:
            # 1. Open the serial port
            ser = serial.Serial(self.port, self.baud_rate, timeout=0.01)
            time.sleep(2) 
            self.serial = ser
            
            # 2. Connection handshake (Soft reboot, exit Raw REPL)
            self.serial.write(b'\x04') # Ctrl-D
            time.sleep(0.5)
            self.serial.read_all() 
            self.serial.write(b'\x02') # Ctrl-B 
            
            # 3. Wait for standard REPL prompt
            boot_output = self._wait_for_prompt(timeout=2.0, prompt=b'>>>')
            
            if boot_output.strip().endswith('>>>'):
                print("[MOTOR] ✅ Connection established. Pico is ready.")
                self.is_connected = True
                return True
            else:
                print("[MOTOR] ❌ Connection failed: Prompt not received.")
                self.is_connected = False
                self.close()
                return False

        except serial.SerialException as e:
            print(f"[MOTOR] ❌ FATAL ERROR: Could not connect. Details: {e}")
            self.is_connected = False
            return False

    def close(self):
        """Closes the serial connection."""
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.is_connected = False
            print("[MOTOR] Connection closed.")
            
    # Add your run_command and send_move_command methods here for future use