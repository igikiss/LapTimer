# tests/test_lap_timer.py
import unittest
from unittest.mock import Mock, patch
from lap_timer import LapTimer

class TestLapTimer(unittest.TestCase):
    def setUp(self):
        self.mock_lidar = Mock()
        self.config = {
            'timing': {'crossing_threshold': 50, 'debounce_time': 2.0}
        }
        
    def test_singleton_pattern(self):
        timer1 = LapTimer(self.mock_lidar, self.config)
        timer2 = LapTimer.get_instance()
        self.assertIs(timer1, timer2)
        
    def test_lap_timing_logic(self):
        # Test crossing detection, debouncing, etc.
        pass