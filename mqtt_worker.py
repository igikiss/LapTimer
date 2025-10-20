import paho.mqtt.client as mqtt
import json
import logging
import threading
import time
from typing import Optional, Dict, Any
from lap_timer import LapTimer

class MQTTWorker:
    """
    MQTT client for publishing lap timing data and race statistics.
    Publishes real-time lap events and status updates.
    """
    
    def __init__(self, config: dict):
        """
        Initialize MQTT worker with configuration.
        
        Args:
            config: Dictionary with 'mqtt' section containing:
                - host: MQTT broker hostname
                - port: MQTT broker port
                - client_id: MQTT client identifier
                - topics: Dict of topic names
                - publish_interval: Status publishing interval
        """
        self.config = config.get('mqtt', {})
        self.client = None
        self.connected = False
        self.running = False
        self.publish_thread = None
        
        # MQTT configuration
        self.host = self.config.get('host', 'localhost')
        self.port = self.config.get('port', 1883)
        self.client_id = self.config.get('client_id', 'pumptrack_timer')
        self.username = self.config.get('username')
        self.password = self.config.get('password')
        
        # Topic configuration
        topics = self.config.get('topics', {})
        self.topic_lap = topics.get('lap_time', 'pumptrack/lap')
        self.topic_status = topics.get('status', 'pumptrack/status')
        self.topic_stats = topics.get('statistics', 'pumptrack/stats')
        self.topic_health = topics.get('health', 'pumptrack/health')
        
        # Publishing configuration
        self.publish_interval = self.config.get('publish_interval', 2.0)  # seconds
        self.last_status_publish = 0
        
        logging.info(f"MQTT Worker initialized: broker={self.host}:{self.port}, client_id={self.client_id}")

    def start(self) -> bool:
        """Start MQTT client and publishing thread."""
        if self.running:
            return True
            
        if not self.connect():
            return False
            
        self.running = True
        self.publish_thread = threading.Thread(target=self._publish_loop, daemon=True)
        self.publish_thread.start()
        
        logging.info("MQTT Worker started")
        return True

    def stop(self):
        """Stop MQTT client and publishing thread."""
        self.running = False
        
        if self.publish_thread and self.publish_thread.is_alive():
            self.publish_thread.join(timeout=2.0)
            
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            
        logging.info("MQTT Worker stopped")

    def connect(self) -> bool:
        """Connect to MQTT broker."""
        try:
            # Handle both old and new paho-mqtt API versions
            try:
                # Create the client using keyword if supported, otherwise fall back to positional arg
                try:
                    self.client = mqtt.Client(client_id=self.client_id)
                except TypeError:
                    # Older paho-mqtt versions may not accept keyword args
                    self.client = mqtt.Client(self.client_id)
            except Exception:
                # Final fallback if anything unexpected happens
                self.client = mqtt.Client(self.client_id)
                
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_publish = self._on_publish
            
            # Set credentials if provided
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)
            
            # Connect with keepalive
            self.client.connect(self.host, self.port, 60)
            self.client.loop_start()
            
            # Wait for connection (with timeout)
            timeout = time.time() + 5.0
            while not self.connected and time.time() < timeout:
                time.sleep(0.1)
                
            return self.connected
            
        except Exception as e:
            logging.error(f"MQTT connection failed: {e}")
            return False

    def publish_lap_event(self, lap_time: Optional[float], status: str, lap_number: Optional[int] = None):
        """
        Publish lap timing event.
        
        Args:
            lap_time: Lap time in seconds (None for DNF)
            status: Lap status ('Completed' or 'DNF')
            lap_number: Lap number (optional)
        """
        if not self.connected or self.client is None:
            logging.warning("Cannot publish lap event: MQTT not connected or client not initialized")
            return False
            
        try:
            data = {
                'lap_time': lap_time,
                'status': status,
                'lap_number': lap_number,
                'timestamp': time.time(),
                'timestamp_iso': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime())
            }
            
            payload = json.dumps(data, indent=None)
            result = self.client.publish(self.topic_lap, payload, qos=1, retain=False)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logging.info(f"Published lap event: {status} - {lap_time}s" if lap_time else f"Published lap event: {status}")
                return True
            else:
                logging.error(f"Failed to publish lap event: {mqtt.error_string(result.rc)}")
                return False
                
        except Exception as e:
            logging.error(f"Error publishing lap event: {e}")
            return False

    def publish_race_status(self, force: bool = False):
        """
        Publish current race status and statistics.
        
        Args:
            force: Force publish even if interval hasn't elapsed
        """
        if not self.connected:
            return False
            
        current_time = time.time()
        if not force and current_time - self.last_status_publish < self.publish_interval:
            return False
            
        try:
            timer = LapTimer.get_instance()
            if not timer:
                logging.warning("Cannot publish status: LapTimer not available")
                return False
                
            # Get current status and statistics
            status = timer.get_status()
            stats = timer.get_race_statistics()
            
            # Prepare status payload
            status_data = {
                'running': status['running'],
                'current_state': status['current_state'],
                'current_lap_time': status['current_lap_time'],
                'reset_remaining': status['reset_remaining'],
                'total_laps': status['total_laps'],
                'total_dnf': status['total_dnf'],
                'best_lap': status['best_lap'],
                'last_lap_status': status['last_lap_status'],
                'timestamp': current_time,
                'timestamp_iso': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime())
            }
            
            # Prepare statistics payload
            stats_data = {
                'total_attempts': stats['total_attempts'],
                'completed_laps': stats['completed_laps'],
                'dnf_count': stats['dnf_count'],
                'completion_rate': stats['completion_rate'],
                'best_lap': stats['best_lap'],
                'average_lap': stats['average_lap'],
                'total_race_time': stats['total_race_time'],
                'last_5_laps': stats['last_5_laps'],
                'timestamp': current_time
            }
            
            # Prepare health payload
            health_data = {
                'lidar_healthy': status['lidar_healthy'],
                'current_distance': status['current_distance'],
                'lidar_status_message': status['lidar_status_message'],
                'connection_failures': status['connection_failures'],
                'reading_failures': status['reading_failures'],
                'timestamp': current_time
            }
            
            # Publish all data
            success = True
            success &= self._publish_json(self.topic_status, status_data)
            success &= self._publish_json(self.topic_stats, stats_data)
            success &= self._publish_json(self.topic_health, health_data)
            
            if success:
                self.last_status_publish = current_time
                logging.debug("Published race status and statistics")
            
            return success
            
        except Exception as e:
            logging.error(f"Error publishing race status: {e}")
            return False

    def _publish_json(self, topic: str, data: dict, qos: int = 0, retain: bool = False) -> bool:
        """Helper method to publish JSON data."""
        if not self.connected or self.client is None:
            logging.warning(f"Cannot publish to {topic}: MQTT not connected or client not initialized")
            return False
        try:
            payload = json.dumps(data, indent=None)
            result = self.client.publish(topic, payload, qos=qos, retain=retain)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logging.error(f"Error publishing to {topic}: {e}")
            return False

    def _publish_loop(self):
        """Background thread for periodic status publishing."""
        logging.info("MQTT publish loop started")
        
        while self.running:
            try:
                if self.connected:
                    self.publish_race_status()
                time.sleep(1.0)  # Check every second
            except Exception as e:
                logging.error(f"Error in MQTT publish loop: {e}")
                time.sleep(5.0)  # Wait longer on error
                
        logging.info("MQTT publish loop stopped")

    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connection callback."""
        if rc == 0:
            self.connected = True
            logging.info(f"MQTT connected to {self.host}:{self.port}")
            # Publish initial status
            self.publish_race_status(force=True)
        else:
            self.connected = False
            logging.error(f"MQTT connection failed: {mqtt.connack_string(rc)} (code {rc})")

    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback."""
        self.connected = False
        if rc != 0:
            logging.warning(f"MQTT unexpected disconnection: {mqtt.error_string(rc)}")
        else:
            logging.info("MQTT disconnected")

    def _on_publish(self, client, userdata, mid):
        """MQTT publish callback."""
        logging.debug(f"MQTT message {mid} published successfully")

    def is_connected(self) -> bool:
        """Check if MQTT client is connected."""
        return self.connected

    def get_status(self) -> Dict[str, Any]:
        """Get MQTT worker status."""
        return {
            'connected': self.connected,
            'running': self.running,
            'broker': f"{self.host}:{self.port}",
            'client_id': self.client_id,
            'topics': {
                'lap': self.topic_lap,
                'status': self.topic_status,
                'statistics': self.topic_stats,
                'health': self.topic_health
            }
        }

    def cleanup(self):
        """Cleanup MQTT resources."""
        self.stop()
        logging.info("MQTT Worker cleaned up")