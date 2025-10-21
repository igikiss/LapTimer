#!/usr/bin/env python3
"""
Example of how to add profiling to the Lap Timer application.
"""

# Example 1: Add profiling to main.py
# =====================================

from profiler import timeit, time_block, FunctionTimer, start_profiling, stop_profiling

# Create a global timer
timer = FunctionTimer()

# Example: Profile the main loop
@timeit
def main_loop():
    """Main application loop."""
    # Your existing code here
    pass

# Example: Profile specific functions in lap_timer.py
@timer.track
def process_distance_reading(distance):
    """Process LIDAR distance reading."""
    # Your existing code here
    pass

# Example: Use time_block for specific operations
def some_operation():
    with time_block("LIDAR reading"):
        # Read from LIDAR
        pass
    
    with time_block("LED update"):
        # Update LED display
        pass


# Example 2: Enable global profiling
# ===================================

def main_with_profiling():
    """Main function with profiling enabled."""
    import signal
    
    # Start profiling
    start_profiling()
    
    # Register cleanup handler
    def cleanup_handler(signum, frame):
        stop_profiling("lap_timer_profile.prof")
        # ... rest of cleanup
        exit(0)
    
    signal.signal(signal.SIGINT, cleanup_handler)
    
    # Run your application
    # ... your main code here


# Example 3: Profile a specific module
# =====================================

from profiler import profile

@profile("lidar_profile.prof")
def read_lidar_data():
    """Read data from LIDAR sensor."""
    # Your LIDAR code here
    pass


# Example 4: Add to webserver.py
# ===============================

from profiler import timeit

class WebServer:
    @timeit
    def api_get_status(self):
        """Get race status - with timing."""
        # Your existing code
        pass
    
    @timeit
    def api_start_race(self):
        """Start race - with timing."""
        # Your existing code
        pass


# Example 5: Monitor performance continuously
# ============================================

from performance_monitor import PerformanceMonitor

# Initialize with profiling enabled
perf_monitor = PerformanceMonitor(enable_profiling=True)

# Use the decorator
@perf_monitor.profile_function
def critical_function():
    """This function will be tracked."""
    pass

# Print summary periodically
import threading
import time

def print_stats_periodically():
    while True:
        time.sleep(60)  # Every minute
        perf_monitor.log_performance_summary()

stats_thread = threading.Thread(target=print_stats_periodically, daemon=True)
stats_thread.start()


# Example 6: Quick profiling of entire application
# =================================================

if __name__ == "__main__":
    import cProfile
    import pstats
    
    # Profile the entire application
    profiler = cProfile.Profile()
    profiler.enable()
    
    try:
        # Run your main application
        # main()
        pass
    finally:
        profiler.disable()
        
        # Print results
        stats = pstats.Stats(profiler)
        stats.sort_stats('cumulative')
        stats.print_stats(50)  # Top 50 functions
        
        # Save to file
        stats.dump_stats('full_profile.prof')
        print("\nProfile saved to full_profile.prof")
        print("View with: python -m pstats full_profile.prof")
