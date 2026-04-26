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
    REG_MODEL = 3
    REG_ID = 5
    REG_BAUD_RATE = 6
    REG_TORQUE_ENABLE = 40
    REG_ACC = 41
    REG_GOAL_POSITION = 42
    REG_GOAL_SPEED = 46
    REG_PRESENT_POSITION = 56
    REG_PRESENT_SPEED = 58
    REG_PRESENT_LOAD = 60
    REG_PRESENT_VOLTAGE = 62
    REG_PRESENT_TEMPERATURE = 63
    REG_MOVING = 66
    
    def __init__(self, uart_id=0, tx_pin=0, rx_pin=1, baudrate=1_000_000, dir_pin=None):
        self.uart = UART(uart_id, baudrate=baudrate, tx=Pin(tx_pin), rx=Pin(rx_pin))
        # Optional direction pin for half-duplex control via tri-state buffer
        self.dir_pin = Pin(dir_pin, Pin.OUT) if dir_pin else None
        
    def _checksum(self, packet):
        """Calculate checksum: ~(sum of ID + Length + params) & 0xFF."""
        return (~sum(packet[2:])) & 0xFF
    
    def _read_exact(self, n, timeout_ms=20):
        """Read exactly n bytes from the UART, or return None on timeout."""
        buf = b""
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while len(buf) < n and time.ticks_diff(deadline, time.ticks_ms()) > 0:
            chunk = self.uart.read(n - len(buf))
            if chunk:
                buf += chunk
        return buf if len(buf) == n else None

    def _send(self, servo_id, instruction, params=None):
        """Send a command packet to a servo."""
        if params is None:
            params = []
        length = len(params) + 2  # params + instruction + checksum
        packet = [0xFF, 0xFF, servo_id, length, instruction] + params
        packet.append(self._checksum(packet))
        pkt = bytes(packet)

        # Discard any stale bytes (e.g. a previous ACK) before transmitting.
        self.uart.read()

        if self.dir_pin:
            self.dir_pin.value(1)  # TX mode

        self.uart.write(pkt)

        # Wait for the packet to finish clocking out. At 1 Mbaud each byte
        # takes ~10 us; add margin but stay well below the servo's ~500 us
        # reply turnaround so we don't eat the response below.
        time.sleep_us(len(pkt) * 10 + 200)

        if self.dir_pin:
            self.dir_pin.value(0)  # RX mode
            # Half-duplex wiring loops TX back onto RX; discard that echo.
            # On full-duplex wiring (no dir_pin) there is no echo, and reading
            # here would swallow a fast servo reply that has already arrived.
            self.uart.read()

    def _receive(self, servo_id):
        """Read a response packet from a servo, verifying its framing."""
        header = self._read_exact(4, timeout_ms=20)
        if (not header
                or header[0] != 0xFF or header[1] != 0xFF
                or header[2] != servo_id):
            return None
        body = self._read_exact(header[3], timeout_ms=20)
        if not body:
            return None
        return list(body[1:-1])  # Strip error byte and checksum
    
    def ping(self, servo_id):
        """Ping a servo to check if it's online."""
        self._send(servo_id, self.INST_PING)
        return self._receive(servo_id) is not None

    def read_model(self, servo_id):
        """Read the model number register. Returns the raw 16-bit value, or None."""
        self._send(servo_id, self.INST_READ,
                   [self.REG_MODEL, 2])
        data = self._receive(servo_id)
        if data and len(data) >= 2:
            return data[0] | (data[1] << 8)
        return None

    def set_torque(self, servo_id, enable=True):
        """Enable or disable torque on a servo."""
        self._send(servo_id, self.INST_WRITE,
                   [self.REG_TORQUE_ENABLE, int(enable)])
    
    def move(self, servo_id, position, speed=0, acc=50):
        """
        Move servo to a position.

        Args:
            servo_id: Servo ID (0-253)
            position: Target position (0-4095 maps to 0-360 degrees)
            speed: Movement speed (0 = max speed, 1-4095)
            acc: Acceleration (0-254)
        """
        pos_l = position & 0xFF
        pos_h = (position >> 8) & 0xFF
        time_l = 0
        time_h = 0
        spd_l = speed & 0xFF
        spd_h = (speed >> 8) & 0xFF

        self._send(servo_id, self.INST_WRITE,
                   [self.REG_ACC, acc,
                    pos_l, pos_h, time_l, time_h, spd_l, spd_h])
    
    def read_position(self, servo_id):
        """Read the current position (0-4095)."""
        self._send(servo_id, self.INST_READ,
                   [self.REG_PRESENT_POSITION, 2])
        data = self._receive(servo_id)
        if data and len(data) >= 2:
            return data[0] | (data[1] << 8)
        return None
    
    def read_pos_speed(self, servo_id):
        """Read current position and speed. Returns (position, speed) or (None, None)."""
        self._send(servo_id, self.INST_READ,
                   [self.REG_PRESENT_POSITION, 4])
        data = self._receive(servo_id)
        if data and len(data) >= 4:
            position = data[0] | (data[1] << 8)
            speed = data[2] | (data[3] << 8)
            # Handle signed values (bit 15 is sign)
            if position > 32767:
                position -= 65536
            if speed > 32767:
                speed -= 65536
            return position, speed
        return None, None

    def read_moving(self, servo_id):
        """Read whether the servo is currently moving. Returns 1 if moving, 0 if stopped."""
        self._send(servo_id, self.INST_READ,
                   [self.REG_MOVING, 1])
        data = self._receive(servo_id)
        if data and len(data) >= 1:
            return data[0]
        return None

    def read_temperature(self, servo_id):
        """Read the servo temperature in degrees Celsius."""
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
                   [self.REG_ID, new_id])
        time.sleep_ms(50)


def degrees_to_position(degrees):
    """Convert degrees (0-360) to position value (0-4095)."""
    return int((degrees / 360) * 4095)


def position_to_degrees(position):
    """Convert position value (0-4095) to degrees (0-360)."""
    return (position / 4095) * 360