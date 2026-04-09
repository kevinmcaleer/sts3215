# 
# 
# 

from machine import UART, Pin
import time

class STS3215:
    """Minimal driver for Feetech STS3215 serial bus servos."""
    
    # Instruction types
    INST_PING = 0x01
    INST_READ = 0x02
    INST_WRITE = 0x03
    
    # Register addresses
    REG_ID = 5
    REG_BAUD_RATE = 6
    REG_TORQUE_ENABLE = 40
    REG_GOAL_POSITION = 42
    REG_GOAL_SPEED = 46
    REG_PRESENT_POSITION = 56
    REG_PRESENT_SPEED = 58
    REG_PRESENT_LOAD = 60
    REG_PRESENT_VOLTAGE = 62
    REG_PRESENT_TEMPERATURE = 63
    
    def __init__(self, uart_id=0, tx_pin=0, rx_pin=1, baudrate=1_000_000, dir_pin=None):
        self.uart = UART(uart_id, baudrate=baudrate, tx=Pin(tx_pin), rx=Pin(rx_pin))
        # Optional direction pin for half-duplex control via tri-state buffer
        self.dir_pin = Pin(dir_pin, Pin.OUT) if dir_pin else None
        
    def _checksum(self, packet):
        """Calculate checksum: ~(sum of ID + Length + params) & 0xFF."""
        return (~sum(packet[2:])) & 0xFF
    
    def _send(self, servo_id, instruction, params=None):
        """Send a command packet to a servo."""
        if params is None:
            params = []
        length = len(params) + 2  # params + instruction + checksum
        packet = [0xFF, 0xFF, servo_id, length, instruction] + params
        packet.append(self._checksum(packet))
        
        if self.dir_pin:
            self.dir_pin.value(1)  # TX mode
            
        self.uart.write(bytes(packet))
        
        if self.dir_pin:
            time.sleep_us(100)
            self.dir_pin.value(0)  # RX mode
    
    def _receive(self, servo_id):
        """Read a response packet from a servo."""
        time.sleep_ms(2)
        if self.uart.any():
            header = self.uart.read(4)
            if header and len(header) == 4 and header[0] == 0xFF and header[1] == 0xFF:
                data_len = header[3]
                data = self.uart.read(data_len)
                if data:
                    return list(data[1:-1])  # Strip error byte and checksum
        return None
    
    def ping(self, servo_id):
        """Ping a servo to check if it's online."""
        self.uart.read()  # Flush
        self._send(servo_id, self.INST_PING)
        time.sleep_ms(5)
        return self.uart.any() > 0
    
    def set_torque(self, servo_id, enable=True):
        """Enable or disable torque on a servo."""
        self._send(servo_id, self.INST_WRITE, 
                   [self.REG_TORQUE_ENABLE, 1, int(enable)])
    
    def move(self, servo_id, position, speed=0):
        """
        Move servo to a position.
        
        Args:
            servo_id: Servo ID (0-253)
            position: Target position (0-4095 maps to 0-360 degrees)
            speed: Movement speed (0 = max speed, 1-4095)
        """
        pos_l = position & 0xFF
        pos_h = (position >> 8) & 0xFF
        time_l = 0
        time_h = 0
        spd_l = speed & 0xFF
        spd_h = (speed >> 8) & 0xFF
        
        self._send(servo_id, self.INST_WRITE,
                   [self.REG_GOAL_POSITION, 2,
                    pos_l, pos_h, time_l, time_h, spd_l, spd_h])
    
    def read_position(self, servo_id):
        """Read the current position (0-4095)."""
        self.uart.read()  # Flush
        self._send(servo_id, self.INST_READ,
                   [self.REG_PRESENT_POSITION, 2])
        data = self._receive(servo_id)
        if data and len(data) >= 2:
            return data[0] | (data[1] << 8)
        return None
    
    def read_temperature(self, servo_id):
        """Read the servo temperature in degrees Celsius."""
        self.uart.read()  # Flush
        self._send(servo_id, self.INST_READ,
                   [self.REG_PRESENT_TEMPERATURE, 1])
        data = self._receive(servo_id)
        if data and len(data) >= 1:
            return data[0]
        return None
    
    def set_id(self, current_id, new_id):
        """
        Change the ID of a servo.
        Only connect ONE servo when changing IDs.
        """
        self._send(current_id, self.INST_WRITE,
                   [self.REG_ID, 1, new_id])
        time.sleep_ms(50)


def degrees_to_position(degrees):
    """Convert degrees (0-360) to position value (0-4095)."""
    return int((degrees / 360) * 4095)


def position_to_degrees(position):
    """Convert position value (0-4095) to degrees (0-360)."""
    return (position / 4095) * 360