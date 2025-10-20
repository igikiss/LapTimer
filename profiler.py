#!/usr/bin/env python3
"""
Profiling utilities for the Lap Timer application.
Provides decorators and context managers for performance monitoring.
"""

import time
import logging
import functools
import cProfile
import pstats
import io
from contextlib import contextmanager
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

# Global profiler instance
_profiler: Optional[cProfile.Profile] = None


def timeit(func: Callable) -> Callable:
    """
    Decorator to measure function execution time.
    
    Usage:
        @timeit
        def my_function():
            pass
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            elapsed = time.perf_counter() - start
            logger.debug(f"{func.__name__} took {elapsed*1000:.2f}ms")
    return wrapper


def profile(output_file: Optional[str] = None):
    """
    Decorator to profile a function with cProfile.
    
    Usage:
        @profile("my_function.prof")
        def my_function():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            profiler = cProfile.Profile()
            profiler.enable()
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                profiler.disable()
                
                # Print stats
                s = io.StringIO()
                ps = pstats.Stats(profiler, stream=s)
                ps.sort_stats('cumulative')
                ps.print_stats(20)
                
                logger.info(f"\nProfile for {func.__name__}:\n{s.getvalue()}")
                
                # Save to file if requested
                if output_file:
                    ps.dump_stats(output_file)
                    logger.info(f"Profile saved to {output_file}")
        
        return wrapper
    return decorator


@contextmanager
def time_block(name: str):
    """
    Context manager to time a block of code.
    
    Usage:
        with time_block("my operation"):
            # code to time
            pass
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        logger.info(f"{name} took {elapsed*1000:.2f}ms")


def start_profiling():
    """Start global profiling."""
    global _profiler
    if _profiler is None:
        _profiler = cProfile.Profile()
        _profiler.enable()
        logger.info("Global profiling started")


def stop_profiling(output_file: str = "profile_results.prof"):
    """Stop global profiling and save results."""
    global _profiler
    if _profiler:
        _profiler.disable()
        
        # Print stats
        s = io.StringIO()
        ps = pstats.Stats(_profiler, stream=s)
        ps.sort_stats('cumulative')
        ps.print_stats(30)
        
        logger.info(f"\nGlobal Profile Results:\n{s.getvalue()}")
        
        # Save to file
        ps.dump_stats(output_file)
        logger.info(f"Profile saved to {output_file}")
        
        _profiler = None


class FunctionTimer:
    """
    Class-based timer for tracking multiple function calls.
    
    Usage:
        timer = FunctionTimer()
        
        @timer.track
        def my_function():
            pass
        
        # Later:
        timer.print_stats()
    """
    
    def __init__(self):
        self.timings = {}
    
    def track(self, func: Callable) -> Callable:
        """Decorator to track function timing."""
        func_name = func.__name__
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed = time.perf_counter() - start
                
                if func_name not in self.timings:
                    self.timings[func_name] = []
                self.timings[func_name].append(elapsed)
        
        return wrapper
    
    def print_stats(self):
        """Print timing statistics for all tracked functions."""
        logger.info("\n=== Function Timing Statistics ===")
        
        for func_name, times in sorted(
            self.timings.items(),
            key=lambda x: sum(x[1]),
            reverse=True
        ):
            count = len(times)
            total = sum(times)
            avg = total / count
            min_time = min(times)
            max_time = max(times)
            
            logger.info(
                f"{func_name:30s}: "
                f"calls={count:4d}, "
                f"total={total*1000:7.1f}ms, "
                f"avg={avg*1000:6.2f}ms, "
                f"min={min_time*1000:6.2f}ms, "
                f"max={max_time*1000:6.2f}ms"
            )
    
    def reset(self):
        """Reset all timing data."""
        self.timings.clear()


# Example usage in main.py:
if __name__ == "__main__":
    # Example 1: Using @timeit decorator
    @timeit
    def example_function():
        time.sleep(0.1)
    
    example_function()
    
    # Example 2: Using time_block context manager
    with time_block("database query"):
        time.sleep(0.05)
    
    # Example 3: Using FunctionTimer
    timer = FunctionTimer()
    
    @timer.track
    def tracked_function():
        time.sleep(0.02)
    
    for _ in range(5):
        tracked_function()
    
    timer.print_stats()
