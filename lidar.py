import logging
import time
from threading import Thread, Event, Lock
from typing import Tuple, Optional, Dict

# Handle serial import gracefully
try:
    import serial
    from serial import SerialException
    SERIAL_AVAILABLE = True
except ImportError:
    serial = None  # type: ignore
    SerialException = Exception  # Fallback
    SERIAL_AVAILABLE = False
    logging.warning("PySerial not available - running in simulation mode")

class LidarSensor:
    """
    A robust interface for the TF-Mini LiDAR sensor with:
    - Thread-safe distance, signal strength, and temperature readings
    - Auto-reconnection on failure
    - Checksum validation
    - Configurable signal strength and distance filtering
    - Accurate temperature calculation
    - Health status monitoring
    """

    def __init__(self, config: dict):
        """
        Initialize the LiDAR sensor with configuration.
        
        Args:
            config (dict): Configuration dictionary with keys:
                - 'lidar': Dict containing 'port', 'baudrate', 'timeout', 'min_strength', 
                          'max_distance', 'max_reading_age'
        """
        self.config = config
        self.simulation_mode = not SERIAL_AVAILABLE
        self.serial_port = None
        self.is_running = False
        self.current_distance = None  # Distance in cm
        self.signal_strength = None   # Signal strength (0-65535, higher is better)
        self.temperature = None       # Temperature in Celsius
        self.last_reading_time = 0    # Timestamp of last valid reading
        self.reading_thread = None
        self.stop_event = Event()
        self.data_lock = Lock()      # Protects shared variables
        self.connection_failures = 0 # Tracks connection failures
        self.reading_failures = 0    # Tracks reading failures
        
        # Configure logging
        # logging.basicConfig(
        #     level=logging.INFO,
        #     format='%(asctime)s - %(levelname)s - %(message)s'
        # )
        self.logger = logging.getLogger(__name__)
        
        if self.simulation_mode:
            self.logger.info("LiDAR running in simulation mode (no hardware)")
        else:
            self.setup_serial_port()

    def setup_serial_port(self) -> bool:
        """Initialize or reinitialize the serial connection with retries."""
        max_retries = 3
        lidar_config = self.config.get('lidar', {})
        
        # Validate required config keys
        required_keys = ['port', 'baudrate']
        for key in required_keys:
            if key not in lidar_config:
                self.logger.warning(f"Missing config key 'lidar.{key}', using default")
        
        for attempt in range(max_retries):
            try:
                self.serial_port = serial.Serial(
                    port=lidar_config.get('port', '/dev/ttyS0'),
                    baudrate=lidar_config.get('baudrate', 115200),
                    timeout=lidar_config.get('timeout', 1.0),
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    bytesize=serial.EIGHTBITS
                )
                time.sleep(0.5)  # Allow stabilization
                self.serial_port.reset_input_buffer()
                
                with self.data_lock:
                    self.current_distance = None
                    self.signal_strength = None
                    self.temperature = None
                    self.last_reading_time = 0
                    self.connection_failures = 0
                    self.reading_failures = 0
                
                self.logger.info(f"LiDAR connected on {self.serial_port.name}")
                return True
                
            except SerialException as e:
                self.logger.warning(f"Connection attempt {attempt + 1} failed: {str(e)}")
                if self.serial_port:
                    self.serial_port.close()
                    self.serial_port = None
                time.sleep(1)
            except Exception as e:
                self.logger.error(f"Unexpected error during initialization: {str(e)}")
                if self.serial_port:
                    self.serial_port.close()
                    self.serial_port = None
                time.sleep(1)
        
        self.logger.error("LiDAR initialization failed after retries")
        self.serial_port = None
        return False

    def is_connected(self) -> bool:
        """Check if the LiDAR is connected and ready."""
        return self.serial_port is not None and self.serial_port.is_open

    def _validate_checksum(self, data: bytes) -> bool:
        """Verify the TF-Mini data packet checksum."""
        return sum(data[:8]) & 0xFF == data[8]

    def read_distance(self) -> Tuple[Optional[int], Optional[int], Optional[float]]:
        """
        Read a single distance measurement with validation and timeout.
        
        Returns:
            Tuple of (distance_cm, signal_strength, temperature_c) or (None, None, None)
        """
        if not self.is_connected():
            self.logger.debug("Serial port not available")
            return None, None, None
        
        try:
            if self.serial_port is not None:
                self.serial_port.reset_input_buffer()
            timeout_counter = 0
            max_timeout = 20  # ~20 ms at 100 Hz
            while timeout_counter < max_timeout:
                if self.serial_port is None:
                    self.logger.debug("Serial port became None during read")
                    break
                byte1 = self.serial_port.read(1)
                if byte1 == b'\x59':
                    if self.serial_port is None:
                        self.logger.debug("Serial port became None during read")
                        break
                    byte2 = self.serial_port.read(1)
                    if byte2 == b'\x59':
                        if self.serial_port is None:
                            self.logger.debug("Serial port became None during read")
                            break
                        data = self.serial_port.read(7)
                        if len(data) == 7:
                            full_data = b'\x59\x59' + data
                            if self._validate_checksum(full_data):
                                distance = data[0] + (data[1] << 8)
                                strength = data[2] + (data[3] << 8)
                                temp = (data[4] + (data[5] << 8)) / 100  # Corrected temperature
                                min_strength = self.config.get('lidar', {}).get('min_strength', 100)
                                max_distance = self.config.get('lidar', {}).get('max_distance', 1200)
                                if strength >= min_strength and distance < max_distance:
                                    self.logger.debug(f"Valid reading: distance={distance}cm, strength={strength}, temp={temp:.1f}C")
                                    return distance, strength, temp
                                else:
                                    self.logger.debug(f"Filtered: distance={distance}cm, strength={strength}")
                timeout_counter += 1
            self.logger.debug("No valid data within timeout")
            return None, None, None
        
        except SerialException as e:
            self.logger.error(f"Serial error: {str(e)}")
            if self.serial_port is not None:
                self.serial_port.close()
            self.serial_port = None
            return None, None, None
        except Exception as e:
            self.logger.error(f"Unexpected error: {str(e)}")
            return None, None, None

    def _continuous_read_loop(self):
        """Main thread loop for continuous LiDAR readings."""
        max_connection_failures = 10
        max_reading_failures = 50  # More tolerant for transient reading issues
        
        while self.is_running and not self.stop_event.is_set():
            if not self.is_connected():
                self.logger.warning("LiDAR disconnected. Reconnecting...")
                if not self.setup_serial_port():
                    self.connection_failures += 1
                    if self.connection_failures >= max_connection_failures:
                        self.logger.error("Too many consecutive connection failures, stopping")
                        self.is_running = False  # Notify LapTimer
                        break
                    time.sleep(min(self.connection_failures * 0.5, 5.0))  # Exponential backoff
                    continue
                self.connection_failures = 0
                self.reading_failures = 0  # Reset on successful connection
            
            distance, strength, temp = self.read_distance()
            if distance is not None:
                self.connection_failures = 0
                self.reading_failures = 0
                with self.data_lock:
                    self.current_distance = distance
                    self.signal_strength = strength
                    self.temperature = temp
                    self.last_reading_time = time.time()
            else:
                self.reading_failures += 1
                if self.reading_failures >= max_reading_failures:
                    self.logger.warning(f"Excessive reading failures ({self.reading_failures}), continuing to retry")
                    self.reading_failures = 0  # Reset but continue
            
            time.sleep(0.001)  # Minimize latency for 100 Hz sampling

    def start_continuous_reading(self) -> bool:
        """Start the continuous reading thread."""
        if self.simulation_mode:
            self.logger.info("LiDAR running in simulation mode - no continuous reading needed")
            self.is_running = True
            return True
            
        if not self.is_connected():
            self.logger.error("Cannot start: LiDAR not connected")
            return False
        if not self.is_running:
            self.is_running = True
            self.stop_event.clear()
            self.reading_thread = Thread(
                target=self._continuous_read_loop,
                daemon=True
            )
            self.reading_thread.start()
            self.logger.info("LiDAR continuous reading started")
            return True
        return False

    def stop_continuous_reading(self):
        """Stop the continuous reading thread."""
        if self.is_running:
            self.is_running = False
            self.stop_event.set()
            if self.reading_thread:
                self.reading_thread.join(timeout=2.0)
            self.logger.info("LiDAR continuous reading stopped")

    def get_reading(self) -> Tuple[Optional[int], Optional[int], Optional[float], float]:
        """
        Get the latest sensor readings and timestamp.
        
        Returns:
            Tuple of (distance_cm, signal_strength, temperature_c, timestamp)
        """
        if self.simulation_mode:
            # Return simulated data for testing
            return (None, None, None, 0)
            
        with self.data_lock:
            return (
                self.current_distance,
                self.signal_strength,
                self.temperature,
                self.last_reading_time
            )

    def get_health_status(self) -> Dict:
        """
        Get sensor health information.
        
        Returns:
            Dict with keys:
                - connected: bool, whether serial port is open
                - running: bool, whether reading thread is active
                - last_reading_age: float, seconds since last valid reading
                - current_distance: int or None, latest distance in cm
                - signal_strength: int or None, latest signal strength
                - temperature: float or None, latest temperature in Celsius
                - connection_failures: int, recent connection failures
                - reading_failures: int, recent reading failures
                - healthy: bool, whether sensor is operational
                - status_message: str, reason for unhealthy status if applicable
        """
        if self.simulation_mode:
            return {
                'connected': False,
                'running': self.is_running,
                'last_reading_age': 0,
                'current_distance': None,
                'signal_strength': None,
                'temperature': None,
                'connection_failures': 0,
                'reading_failures': 0,
                'healthy': True,
                'status_message': 'Simulation mode - no hardware'
            }
            
        with self.data_lock:
            time_since_last_reading = time.time() - self.last_reading_time
            lidar_config = self.config.get('lidar', {})
            min_strength = lidar_config.get('min_strength', 100)
            max_reading_age = lidar_config.get('max_reading_age', 0.5)  # Configurable
            is_healthy = (
                self.is_connected() and
                self.is_running and
                time_since_last_reading < max_reading_age and
                (self.signal_strength is None or self.signal_strength >= min_strength) and
                (self.temperature is None or 0 <= self.temperature <= 70)
            )
            status_message = "Sensor healthy"
            if not is_healthy:
                if not self.is_connected():
                    status_message = "Sensor disconnected"
                elif not self.is_running:
                    status_message = "Reading thread stopped"
                elif time_since_last_reading >= max_reading_age:
                    status_message = f"Stale readings (age: {time_since_last_reading:.2f}s)"
                elif self.signal_strength is not None and self.signal_strength < min_strength:
                    status_message = f"Low signal strength: {self.signal_strength}"
                elif self.temperature is not None and (self.temperature < 0 or self.temperature > 70):
                    status_message = f"Extreme temperature: {self.temperature:.1f}C"
            
            return {
                'connected': self.is_connected(),
                'running': self.is_running,
                'last_reading_age': time_since_last_reading,
                'current_distance': self.current_distance,
                'signal_strength': self.signal_strength,
                'temperature': self.temperature,
                'connection_failures': self.connection_failures,
                'reading_failures': self.reading_failures,
                'healthy': is_healthy,
                'status_message': status_message
            }

    def cleanup(self):
        """Safely stop and release all resources."""
        self.stop_continuous_reading()
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.serial_port = None
        self.logger.info("LiDAR cleanup complete")