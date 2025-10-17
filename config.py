# config.py
# This file contains configuration settings for the application.
# MQTT broker settings
import json
import os
import logging

class Config:
    def __init__(self, config_file='timer_config.json'):
        self.config_file = config_file
        self.data = self.load_config()

    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            else:
                logging.warning(f"Config file {self.config_file} not found. Using default settings.")
                return {}
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON from config file: {e}")
            return {}
        except Exception as e:
            logging.error(f"Unexpected error occurred while loading config: {e}")
            return {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save_config()

    def save_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving config to file: {e}")

    def validate_config(self):
        """Validate configuration values."""
        required_keys = ['timing', 'web', 'lidar']
        for key in required_keys:
            if key not in self.data:
                raise ValueError(f"Missing required config section: {key}")
        
        # Validate numeric ranges
        timing = self.data['timing']
        if not 10 <= timing.get('crossing_threshold', 0) <= 200:
            raise ValueError("crossing_threshold must be 10-200 cm")
