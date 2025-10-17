#!/usr/bin/env python3
"""
Main entry point for Raspberry Pi lap timer system.
Integrates LIDAR sensor, lap timing, MQTT communication, and web interface.
"""

import logging
import signal
import sys
import time
from config import Config
from lidar import LidarSensor
from lap_timer import LapTimer
from webserver import WebServer
from mqtt_worker import MQTTWorker  # When you implement it
from LedDisplay import LEDDisplay  # New import for LED display

def setup_logging(config):
    """Configure logging based on config settings."""
    log_config = config.get('logging', {})
    logging.basicConfig(
        level=getattr(logging, log_config.get('level', 'INFO')),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_config.get('file', '/tmp/lap_timer.log')),
            logging.StreamHandler(sys.stdout)
        ]
    )

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logging.info("Shutdown signal received, cleaning up...")
    cleanup_and_exit()

def cleanup_and_exit():
    """Clean up resources and exit."""
    try:
        timer = LapTimer.get_instance()
        if timer:
            timer.cleanup()
    except Exception as e:
        logging.error(f"Error during cleanup: {e}")
    sys.exit(0)

def main():
    """Main application entry point."""
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Load configuration
        config = Config('timer_config.json')
        setup_logging(config.data)
        
        logging.info("Starting Pumptrack Lap Timer System")
        
        # Initialize components
        lidar = LidarSensor(config.data)
        lap_timer = LapTimer(lidar, config.data)
        web_server = WebServer(config.data)
        
        # Start services
        if not lidar.start_continuous_reading():
            logging.error("Failed to start LIDAR sensor")
            return 1
            
        if not web_server.start():
            logging.error("Failed to start web server")
            return 1
            
        logging.info(f"System ready - Web interface at {web_server.get_url()}")
        
        # Initialize MQTT worker
        mqtt_worker = MQTTWorker(config.data)
        if mqtt_worker.start():
            logging.info("MQTT Worker started successfully")
        else:
            logging.warning("MQTT Worker failed to start - continuing without MQTT")
        
        # Initialize LED display
        led_display = LEDDisplay(config.data)
        
        # Main loop
        while True:
            try:
                # Update lap timer
                result = lap_timer.update()
                status = lap_timer.get_status()
                
                # Update LED display
                led_display.show_race_status(status['current_state'])
                
                if result:
                    lap_time, lap_status = result
                    if lap_time is not None:
                        led_display.show_lap_result(lap_time, lap_status)
                        logging.info(f"Lap event: {lap_status} - {lap_time}s")
                    else:
                        logging.info(f"Lap event: {lap_status}")
                    # Publish lap event via MQTT
                    if mqtt_worker.is_connected():
                        mqtt_worker.publish_lap_event(lap_time if lap_time is not None else 0.0, lap_status, len(lap_timer.get_lap_times()))
                
                time.sleep(0.01)  # 100 Hz update rate
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                time.sleep(1)
                
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        return 1
    finally:
        cleanup_and_exit()

if __name__ == "__main__":
    sys.exit(main())

