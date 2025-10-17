import time
import logging
from typing import Optional, Tuple, List, Dict
from threading import Lock
from lidar import LidarSensor  # Assuming LidarSensor is defined in this module


class LapTimer:
    """
    Lap timer for bike pumptrack race, detecting crossings between 10 cm and 4 meters,
    saving lap times, resetting after 5 seconds, debouncing crossings, and handling DNF autoreset.
    """

    _instance = None
    _lock = Lock()

    @classmethod
    def get_instance(cls) -> Optional['LapTimer']:
        """Return the singleton instance of LapTimer."""
        with cls._lock:
            return cls._instance

    def __init__(self, lidar_sensor: 'LidarSensor', config: dict):
        """
        Initialize the LapTimer with a LidarSensor instance and configuration.
        
        Args:
            lidar_sensor: LidarSensor instance for distance readings.
            config: Dictionary with keys:
                - 'lap_timer': Dict containing 'min_crossing_distance', 'max_crossing_distance',
                              'min_lap_time', 'max_lap_time', 'reset_delay', 'crossing_debounce',
                              'state_names', 'dnf_callback'
        """
        with self.__class__._lock:
            if self.__class__._instance is not None:
                raise RuntimeError("LapTimer is a singleton; use get_instance() to access it")
            self.__class__._instance = self

        self.lidar_sensor = lidar_sensor
        self.config = config
        self.is_running = False
        self.lap_times: List[float] = []  # Only completed lap times
        self.lap_results: List[Tuple[Optional[float], str]] = []  # (time, status: "Completed" or "DNF")
        self.current_lap_start: Optional[float] = None
        self.last_crossing_time: Optional[float] = None
        self.reset_timer: Optional[float] = None
        self.min_crossing_distance = config.get('lap_timer', {}).get('min_crossing_distance', 10)  # cm
        self.max_crossing_distance = config.get('lap_timer', {}).get('max_crossing_distance', 400)  # cm
        self.min_lap_time = config.get('lap_timer', {}).get('min_lap_time', 1.0)  # seconds
        self.max_lap_time = config.get('lap_timer', {}).get('max_lap_time', 60.0)  # 1 minute
        self.reset_delay = config.get('lap_timer', {}).get('reset_delay', 5.0)  # seconds
        self.crossing_debounce = config.get('lap_timer', {}).get('crossing_debounce', 0.2)  # 200ms
        self.last_detection_time = 0
        self.last_valid_distance: Optional[int] = None
        self.dnf_callback = config.get('lap_timer', {}).get('dnf_callback', None)  # Optional callback
        self.state_names = config.get('lap_timer', {}).get('state_names', {
            'idle': 'Idle',
            'waiting_for_first_crossing': 'Waiting for Racer',
            'timing_lap': 'Timing Lap',
            'waiting_for_next_racer': 'Waiting for Next Racer',
            'waiting_after_dnf': 'Waiting After DNF'
        })

        # Validate configuration
        if self.crossing_debounce < 0.05 or self.crossing_debounce > 1.0:
            logging.warning(f"Invalid crossing_debounce {self.crossing_debounce}s, using 0.2s")
            self.crossing_debounce = 0.2
        if self.max_lap_time < 10.0 or self.max_lap_time > 300.0:
            logging.warning(f"Invalid max_lap_time {self.max_lap_time}s, using 60.0s")
            self.max_lap_time = 60.0

        logging.info(f"LapTimer initialized: crossing_range={self.min_crossing_distance}-{self.max_crossing_distance}cm, "
                     f"min_lap_time={self.min_lap_time}s, max_lap_time={self.max_lap_time}s, "
                     f"reset_delay={self.reset_delay}s, crossing_debounce={self.crossing_debounce}s")

    def start_race(self) -> bool:
        """
        Start the race, initializing the sensor and clearing previous data.
        """
        with self.__class__._lock:
            if not self.lidar_sensor.is_connected():
                logging.error("Cannot start race: LIDAR not connected")
                return False
            if not hasattr(self.lidar_sensor, 'get_health_status'):
                logging.error("Cannot start race: LIDAR missing get_health_status method")
                return False
            health = self.lidar_sensor.get_health_status()
            if not health['healthy']:
                logging.error(f"Cannot start race: LIDAR unhealthy ({health['status_message']})")
                return False
            if not self.lidar_sensor.is_running:
                if not self.lidar_sensor.start_continuous_reading():
                    logging.error("Failed to start LIDAR continuous reading")
                    return False
            if not self.is_running:
                self.is_running = True
                self.lap_times.clear()
                self.lap_results.clear()
                self.current_lap_start = None
                self.last_crossing_time = None
                self.reset_timer = None
                self.last_detection_time = 0
                self.last_valid_distance = None
                logging.info("Race started")
                return True
            return False

    def stop_race(self) -> None:
        """
        Stop the race, finalizing any ongoing lap and clearing state.
        """
        with self.__class__._lock:
            if self.is_running:
                self.is_running = False
                if self.current_lap_start is not None and self.reset_timer is None:
                    current_time = time.time()
                    lap_time = current_time - self.current_lap_start
                    if lap_time >= self.min_lap_time:
                        self.lap_times.append(lap_time)
                        self.lap_results.append((lap_time, "Completed"))
                        logging.info(f"Final lap recorded: {lap_time:.3f}s")
                    else:
                        self.lap_results.append((None, "DNF"))
                        logging.info("Final lap aborted (too short): DNF")
                        if callable(self.dnf_callback):
                            self.dnf_callback(lap_time)
                self.current_lap_start = None
                self.last_crossing_time = None
                self.reset_timer = None
                self.last_detection_time = 0
                self.last_valid_distance = None
                logging.info("Race stopped")

    def detect_crossing(self) -> Tuple[bool, Optional[float]]:
        """
        Detect if a racer crosses the finish line based on LIDAR distance (10–400 cm)
        with debouncing to prevent multiple triggers.
        
        Returns:
            Tuple of (crossing_detected: bool, timestamp: Optional[float]).
        """
        if not hasattr(self.lidar_sensor, 'get_health_status'):
            logging.warning("LIDAR missing get_health_status method")
            return False, None
        health = self.lidar_sensor.get_health_status()
        if not health['healthy']:
            logging.debug(f"No crossing: LIDAR unhealthy ({health['status_message']})")
            return False, None

        distance, _, _, timestamp = self.lidar_sensor.get_reading()
        if (distance is not None and 
            self.min_crossing_distance <= distance <= self.max_crossing_distance):
            # Debounce check
            if self.last_detection_time is not None and timestamp - self.last_detection_time >= self.crossing_debounce:
                # Check distance consistency for adaptive debouncing
                if (self.last_valid_distance is None or 
                    abs(distance - self.last_valid_distance) <= 10):  # ±10 cm tolerance
                    self.last_detection_time = timestamp
                    self.last_valid_distance = distance
                    logging.debug(f"Crossing detected: {distance}cm")
                    return True, timestamp
                else:
                    logging.debug(f"Crossing debounced (inconsistent distance): {distance}cm vs {self.last_valid_distance}cm")
            else:
                logging.debug(f"Crossing debounced (time): {distance}cm")
        else:
            if distance is not None:
                logging.debug(f"No crossing: distance {distance}cm outside range")
            else:
                logging.debug("No crossing: invalid distance reading")
        
        return False, None

    def update(self) -> Optional[Tuple[Optional[float], str]]:
        """
        Update the lap timer state, handling crossings, reset delay, and DNF autoreset.
        
        Returns:
            Optional[Tuple[Optional[float], str]]: (lap_time, status) if a lap is completed or DNF, else None.
        """
        with self.__class__._lock:
            if not self.is_running:
                return None

            health = self.lidar_sensor.get_health_status()
            if not health['healthy']:
                logging.warning(f"LIDAR unhealthy: {health['status_message']}")
                return None

            current_time = time.time()

            # Check if in reset delay period (after completion or DNF)
            if self.reset_timer is not None:
                if current_time - self.reset_timer >= self.reset_delay:
                    logging.info("Reset delay complete, ready for new racer")
                    self.current_lap_start = None
                    self.last_crossing_time = None
                    self.reset_timer = None
                    self.last_detection_time = 0
                    self.last_valid_distance = None
                else:
                    # Allow crossings to interrupt reset delay for new racer
                    crossing_detected, timestamp = self.detect_crossing()
                    if crossing_detected:
                        self.current_lap_start = timestamp
                        self.last_crossing_time = timestamp
                        self.reset_timer = None
                        self.last_detection_time = timestamp
                        self.last_valid_distance = self.lidar_sensor.get_reading()[0]
                        logging.info("Crossing detected during reset, starting new lap")
                        return None
                return None

            # Check for DNF (max lap time exceeded)
            if (self.current_lap_start is not None and 
                current_time - self.current_lap_start >= self.max_lap_time):
                lap_time = current_time - self.current_lap_start
                self.lap_results.append((None, "DNF"))
                self.reset_timer = current_time
                self.last_detection_time = 0
                self.last_valid_distance = None
                logging.info(f"Lap exceeded max_lap_time ({self.max_lap_time}s): DNF, "
                             f"waiting {self.reset_delay}s for next racer")
                if callable(self.dnf_callback):
                    self.dnf_callback(lap_time)
                return (None, "DNF")

            # Detect crossing
            crossing_detected, timestamp = self.detect_crossing()
            if crossing_detected:
                if self.last_crossing_time is None:
                    # First crossing: start lap timing
                    self.current_lap_start = timestamp
                    self.last_crossing_time = timestamp
                    logging.info("First crossing detected, lap timing started")
                    return None
                else:
                    # Subsequent crossing: check min_lap_time
                    if timestamp is not None and self.last_crossing_time is not None:
                        time_since_last = timestamp - self.last_crossing_time
                        if time_since_last >= self.min_lap_time:
                            if timestamp is not None and self.current_lap_start is not None:
                                lap_time = timestamp - self.current_lap_start
                                self.lap_times.append(lap_time)
                                self.lap_results.append((lap_time, "Completed"))
                                self.last_crossing_time = timestamp
                                self.reset_timer = timestamp  # Start 5-second reset delay
                                logging.info(f"Lap {len(self.lap_times)} completed: {lap_time:.3f}s, "
                                             f"waiting {self.reset_delay}s for next racer")
                                return (lap_time, "Completed")
            return None

    def get_lap_times(self) -> List[float]:
        """Return the list of completed lap times."""
        return self.lap_times

    def get_lap_results(self) -> List[Tuple[Optional[float], str]]:
        """Return the list of lap results (time, status)."""
        return self.lap_results

    def get_best_lap(self) -> Optional[float]:
        """Return the fastest completed lap time or None if no laps completed."""
        return min(self.lap_times) if self.lap_times else None

    def get_total_laps(self) -> int:
        """Return the total number of completed laps."""
        return len(self.lap_times)

    def get_total_dnf(self) -> int:
        """Return the total number of DNF laps."""
        return sum(1 for _, status in self.lap_results if status == "DNF")

    def get_race_statistics(self) -> Dict:
        """Get comprehensive race statistics."""
        completed_laps = [time for time, status in self.lap_results if status == "Completed"]
        completed_laps_filtered = [t for t in completed_laps if t is not None]
        dnf_count = sum(1 for _, status in self.lap_results if status == "DNF")
        
        return {
            'total_attempts': len(self.lap_results),
            'completed_laps': len(completed_laps_filtered),
            'dnf_count': dnf_count,
            'completion_rate': len(completed_laps_filtered) / len(self.lap_results) * 100 if self.lap_results else 0,
            'best_lap': min(completed_laps_filtered) if completed_laps_filtered else None,
            'average_lap': sum(completed_laps_filtered) / len(completed_laps_filtered) if completed_laps_filtered else None,
            'total_race_time': sum(completed_laps_filtered) if completed_laps_filtered else 0,
            'last_5_laps': completed_laps_filtered[-5:] if len(completed_laps_filtered) >= 5 else completed_laps_filtered
        }

    def get_status(self) -> Dict:
        """
        Get current race status for monitoring/display.
        
        Returns:
            Dict with keys:
                - running: bool, whether the race is active
                - total_laps: int, number of completed laps
                - total_dnf: int, number of DNF laps
                - best_lap: float or None, fastest completed lap time
                - current_state: str, current race state
                - current_lap_time: float or None, elapsed time for current lap
                - reset_remaining: float or None, remaining reset delay time
                - last_lap_status: str or None, status of last lap (Completed, DNF, or None)
                - lidar_healthy: bool, whether LiDAR is healthy
                - current_distance: int or None, latest distance in cm
                - lidar_status_message: str, LiDAR health status message
                - connection_failures: int, recent connection failures
                - reading_failures: int, recent reading failures
        """
        with self.__class__._lock:
            current_time = time.time()
            status = {
                'running': self.is_running,
                'total_laps': len(self.lap_times),
                'total_dnf': self.get_total_dnf(),
                'best_lap': self.get_best_lap(),
                'current_state': self.state_names['idle'],
                'current_lap_time': None,
                'reset_remaining': None,
                'last_lap_status': self.lap_results[-1][1] if self.lap_results else None,
                'lidar_healthy': False,
                'current_distance': None,
                'lidar_status_message': "Unknown",
                'connection_failures': 0,
                'reading_failures': 0
            }

            # Add LIDAR health
            if hasattr(self.lidar_sensor, 'get_health_status'):
                health = self.lidar_sensor.get_health_status()
                status['lidar_healthy'] = health.get('healthy', False)
                status['current_distance'] = health.get('current_distance')
                status['lidar_status_message'] = health.get('status_message', "Unknown")
                status['connection_failures'] = health.get('connection_failures', 0)
                status['reading_failures'] = health.get('reading_failures', 0)
                max_reading_age = self.config.get('lidar', {}).get('max_reading_age', 0.5)
                is_data_fresh = health.get('last_reading_age', float('inf')) < max_reading_age
            else:
                logging.warning("LidarSensor missing get_health_status method")
                status['lidar_status_message'] = "Health status unavailable"
                is_data_fresh = False

            # Determine current state and timing
            if self.reset_timer is not None and is_data_fresh:
                status['current_state'] = (self.state_names['waiting_after_dnf']
                                         if self.lap_results and self.lap_results[-1][1] == "DNF"
                                         else self.state_names['waiting_for_next_racer'])
                status['reset_remaining'] = max(0, self.reset_delay - (current_time - self.reset_timer))
            elif self.current_lap_start is not None and is_data_fresh:
                status['current_state'] = self.state_names['timing_lap']
                status['current_lap_time'] = current_time - self.current_lap_start
            elif self.is_running:
                status['current_state'] = self.state_names['waiting_for_first_crossing']

            return status

    def cleanup(self) -> None:
        """Cleanup resources and stop the race."""
        with self.__class__._lock:
            self.stop_race()
            self.__class__._instance = None
            logging.info("LapTimer cleaned up")

    def manual_reset(self) -> bool:
        """Manually reset current lap (for emergency situations)"""
        with self.__class__._lock:
            if self.current_lap_start is not None:
                logging.info("Manual reset triggered")
                self.current_lap_start = None
                self.last_crossing_time = None
                self.reset_timer = time.time()  # Start reset delay
                return True
            return False