import time
import logging
import math
from typing import Optional, List, Tuple

# Handle platform-specific imports gracefully
try:
    import board
    import neopixel
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False
    logging.warning("Hardware libraries not available - running in simulation mode")

class LEDDisplay:
    """
    WS2812-5x5 LED matrix display for pumptrack lap timer.
    Shows race status, lap times, and system health visually.
    """
    
    def __init__(self, config: dict):
        """Initialize LED matrix."""
        self.simulation_mode = not HARDWARE_AVAILABLE
        
        if self.simulation_mode:
            logging.info("LED Display running in simulation mode (no hardware)")
            self._init_simulation_mode(config)
            return
            
        # Hardware mode initialization
        self._init_hardware_mode(config)
    
    def _init_simulation_mode(self, config: dict):
        """Initialize simulation mode for development."""
        led_config = config.get('led_display', {})
        self.num_pixels = led_config.get('num_pixels', 25)
        self.brightness = led_config.get('brightness', 0.3)
        
        # Create color definitions (same as hardware)
        self.colors = {
            'off': (0, 0, 0),
            'red': (255, 0, 0),
            'green': (0, 255, 0),
            'blue': (0, 0, 255),
            'yellow': (255, 255, 0),
            'purple': (128, 0, 128),
            'white': (255, 255, 255),
            'orange': (255, 165, 0)
        }
        
        # Create patterns (same as hardware)
        self._init_patterns()
        logging.info("LED Display initialized in simulation mode")
    
    def _init_hardware_mode(self, config: dict):
        """Initialize hardware mode for Raspberry Pi."""
        led_config = config.get('led_display', {})
        self.pin = getattr(board, led_config.get('pin', 'D18'))
        self.num_pixels = led_config.get('num_pixels', 25)
        self.brightness = led_config.get('brightness', 0.3)
        
        # Initialize NeoPixel strip
        self.pixels = neopixel.NeoPixel(
            self.pin, 
            self.num_pixels, 
            brightness=self.brightness,
            auto_write=False
        )
        
        # Create color definitions
        self.colors = {
            'off': (0, 0, 0),
            'red': (255, 0, 0),
            'green': (0, 255, 0),
            'blue': (0, 0, 255),
            'yellow': (255, 255, 0),
            'purple': (128, 0, 128),
            'white': (255, 255, 255),
            'orange': (255, 165, 0)
        }
        
        # Create patterns
        self._init_patterns()
        
        # Initialize display
        self.clear()
        logging.info("LED Display initialized in hardware mode")
    
    def _init_patterns(self):
        """Initialize LED patterns."""
        self.patterns = {
            'checkmark': [
                0, 0, 0, 0, 1,
                0, 0, 0, 1, 0,
                1, 0, 1, 0, 0,
                0, 1, 0, 0, 0,
                0, 0, 0, 0, 0
            ],
            'x_mark': [
                1, 0, 0, 0, 1,
                0, 1, 0, 1, 0,
                0, 0, 1, 0, 0,
                0, 1, 0, 1, 0,
                1, 0, 0, 0, 1
            ],
            'circle': [
                0, 1, 1, 1, 0,
                1, 0, 0, 0, 1,
                1, 0, 0, 0, 1,
                1, 0, 0, 0, 1,
                0, 1, 1, 1, 0
            ],
            'dot': [
                0, 0, 0, 0, 0,
                0, 0, 0, 0, 0,
                0, 0, 1, 0, 0,
                0, 0, 0, 0, 0,
                0, 0, 0, 0, 0
            ],
            'ready': [
                0, 1, 1, 1, 0,
                1, 0, 1, 0, 1,
                1, 1, 1, 1, 1,
                1, 0, 1, 0, 1,
                0, 1, 1, 1, 0
            ],
            'ready_ring': [
                1, 1, 1, 1, 1,
                1, 0, 0, 0, 1,
                1, 0, 0, 0, 1,
                1, 0, 0, 0, 1,
                1, 1, 1, 1, 1
            ]
        }

    def show_race_status(self, status: str):
        """Display race status pattern."""
        if self.simulation_mode:
            logging.debug(f"LED Display (simulated): {status}")
            return
            
        if status == 'waiting_for_first_crossing':
            self.show_pattern('ready_ring', 'yellow', pulse=True)
        elif status == 'timing_lap':
            self.show_pattern('circle', 'blue', pulse=True)
        elif status == 'waiting_for_next_racer':
            self.show_pattern('checkmark', 'green')
        elif status == 'waiting_after_dnf':
            self.show_pattern('x_mark', 'red')
        else:
            self.clear()

    def show_lap_result(self, lap_time: float, status: str):
        """Show lap completion result with animation."""
        if self.simulation_mode:
            logging.info(f"LED Display (simulated): Lap result - {status}, {lap_time}s")
            return
            
        if status == 'Completed':
            if lap_time < 20.0:  # Fast lap
                self.animate_wave('green', duration=2.0)
            elif lap_time < 25.0:  # Good lap
                self.show_pattern('checkmark', 'green')
                time.sleep(1)
            else:  # Slower lap
                self.show_pattern('checkmark', 'yellow')
                time.sleep(1)
        else:  # DNF
            self.animate_flash('red', flashes=3)

    def show_pattern(self, pattern_name: str, color: str, pulse: bool = False):
        """Display a pattern in specified color."""
        if self.simulation_mode:
            logging.debug(f"LED Display (simulated): Pattern '{pattern_name}' in {color}")
            return
            
        if pattern_name not in self.patterns:
            return
            
        pattern = self.patterns[pattern_name]
        color_rgb = self.colors.get(color, self.colors['white'])
        
        for i, pixel_on in enumerate(pattern):
            if pixel_on:
                self.pixels[i] = color_rgb
            else:
                self.pixels[i] = self.colors['off']
                
        self.pixels.show()
        
        if pulse:
            # Use the new smooth pulse animation
            self.animate_pulse(color, duration=1.5)

    def animate_wave(self, color: str, duration: float = 2.0):
        """Animate a wave effect across the matrix."""
        if self.simulation_mode:
            logging.debug(f"LED Display (simulated): Wave animation in {color}")
            return
            
        color_rgb = self.colors.get(color, self.colors['white'])
        steps = 10
        
        for step in range(steps):
            self.clear()
            # Create wave pattern
            for i in range(25):
                row, col = divmod(i, 5)
                if (row + col + step) % 3 == 0:
                    self.pixels[i] = color_rgb
            self.pixels.show()
            time.sleep(duration / steps)

    def animate_flash(self, color: str, flashes: int = 3):
        """Flash the entire matrix."""
        if self.simulation_mode:
            logging.debug(f"LED Display (simulated): Flash animation in {color}")
            return
            
        color_rgb = self.colors.get(color, self.colors['white'])
        
        for _ in range(flashes):
            self.fill(color_rgb)
            time.sleep(0.2)
            self.clear()
            time.sleep(0.2)

    def show_countdown(self, seconds: int):
        """Show countdown number (1-5)."""
        if self.simulation_mode:
            logging.debug(f"LED Display (simulated): Countdown {seconds}")
            return
            
        # Simple number patterns for 1-5
        numbers = {
            1: [0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 1, 1, 0],
            2: [0, 1, 1, 1, 0, 1, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 1, 1, 1, 1],
            3: [1, 1, 1, 1, 0, 0, 0, 0, 1, 0, 0, 1, 1, 1, 0, 0, 0, 0, 1, 0, 1, 1, 1, 1, 0],
            4: [1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0],
            5: [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0]
        }
        
        if 1 <= seconds <= 5:
            pattern = numbers[seconds]
            for i, pixel_on in enumerate(pattern):
                if pixel_on:
                    self.pixels[i] = self.colors['orange']
                else:
                    self.pixels[i] = self.colors['off']
            self.pixels.show()

    def fill(self, color: Tuple[int, int, int]):
        """Fill entire matrix with color."""
        if self.simulation_mode:
            return
        self.pixels.fill(color)
        self.pixels.show()

    def clear(self):
        """Clear the display."""
        if self.simulation_mode:
            return
        self.pixels.fill(self.colors['off'])
        self.pixels.show()

    def cleanup(self):
        """Cleanup LED resources."""
        if not self.simulation_mode:
            self.clear()
        logging.info("LED Display cleaned up")

    def animate_pulse(self, color: str, duration: float = 2.0):
        """Smooth brightness pulsing animation."""
        if self.simulation_mode:
            logging.debug(f"LED Display (simulated): Pulse animation in {color}")
            return
            
        # Set the pattern/color first
        color_rgb = self.colors.get(color, self.colors['white'])
        self.pixels.fill(color_rgb)
        
        steps = 30
        for i in range(steps):
            # Sine wave for smooth pulsing (fixed syntax)
            brightness = (math.sin(i / steps * math.pi * 2) * 0.4 + 0.5)  # ← Fixed parentheses
            self.pixels.brightness = max(0.1, min(1.0, brightness))
            self.pixels.show()
            time.sleep(duration / steps)
        
        # Reset to original brightness
        self.pixels.brightness = self.brightness

    def animate_heartbeat(self, color: str, duration: float = 2.0):
        """Heartbeat-style double pulse animation."""
        if self.simulation_mode:
            logging.debug(f"LED Display (simulated): Heartbeat in {color}")
            return
            
        color_rgb = self.colors.get(color, self.colors['white'])
        self.pixels.fill(color_rgb)
        
        # Double pulse pattern
        for beat in range(2):  # Two beats
            for i in range(15):  # Quick pulse
                brightness = (math.sin(i / 15 * math.pi) * 0.6 + 0.4)
                self.pixels.brightness = max(0.1, min(1.0, brightness))
                self.pixels.show()
                time.sleep(0.05)
            time.sleep(0.2)  # Pause between beats
    
        self.pixels.brightness = self.brightness

    def animate_breathing(self, color: str, duration: float = 4.0):
        """Slow breathing-style pulse."""
        if self.simulation_mode:
            logging.debug(f"LED Display (simulated): Breathing in {color}")
            return
            
        color_rgb = self.colors.get(color, self.colors['white'])
        self.pixels.fill(color_rgb)
        
        steps = 60  # More steps for smoother breathing
        for i in range(steps):
            # Slower, more gentle sine wave
            brightness = (math.sin(i / steps * math.pi * 2) * 0.3 + 0.4)
            self.pixels.brightness = max(0.1, min(0.7, brightness))  # Lower max
            self.pixels.show()
            time.sleep(duration / steps)
    
        self.pixels.brightness = self.brightness