# performance_monitor.py
import time
import logging
import cProfile
import pstats
import io
from functools import wraps
from typing import Callable, Any

class PerformanceMonitor:
    """
    Performance monitoring with timing, profiling, and metrics tracking.
    """
    
    def __init__(self, enable_profiling: bool = False):
        self.metrics = {
            'update_times': [],
            'web_requests': 0,
            'lap_count': 0,
            'function_calls': {}
        }
        self.enable_profiling = enable_profiling
        self.profiler = cProfile.Profile() if enable_profiling else None
        self.logger = logging.getLogger(__name__)
    
    def track_update_time(self, duration: float):
        """Track update/loop times."""
        self.metrics['update_times'].append(duration)
        if len(self.metrics['update_times']) > 100:
            self.metrics['update_times'].pop(0)
    
    def track_function_call(self, func_name: str, duration: float):
        """Track individual function execution times."""
        if func_name not in self.metrics['function_calls']:
            self.metrics['function_calls'][func_name] = {
                'count': 0,
                'total_time': 0.0,
                'avg_time': 0.0,
                'min_time': float('inf'),
                'max_time': 0.0
            }
        
        stats = self.metrics['function_calls'][func_name]
        stats['count'] += 1
        stats['total_time'] += duration
        stats['avg_time'] = stats['total_time'] / stats['count']
        stats['min_time'] = min(stats['min_time'], duration)
        stats['max_time'] = max(stats['max_time'], duration)
    
    def get_metrics(self) -> dict:
        """Get current performance metrics."""
        metrics = self.metrics.copy()
        
        if self.metrics['update_times']:
            import statistics
            metrics['update_stats'] = {
                'avg': statistics.mean(self.metrics['update_times']),
                'min': min(self.metrics['update_times']),
                'max': max(self.metrics['update_times']),
                'median': statistics.median(self.metrics['update_times'])
            }
        
        return metrics
    
    def start_profiling(self):
        """Start CPU profiling."""
        if self.enable_profiling and self.profiler:
            self.profiler.enable()
            self.logger.info("Profiling started")
    
    def stop_profiling(self, output_file: str = None):
        """Stop CPU profiling and print/save results."""
        if self.enable_profiling and self.profiler:
            self.profiler.disable()
            self.logger.info("Profiling stopped")
            
            # Print to console
            s = io.StringIO()
            ps = pstats.Stats(self.profiler, stream=s).sort_stats('cumulative')
            ps.print_stats(20)  # Top 20 functions
            self.logger.info(f"Profile results:\n{s.getvalue()}")
            
            # Save to file if requested
            if output_file:
                ps.dump_stats(output_file)
                self.logger.info(f"Profile saved to {output_file}")
    
    def profile_function(self, func: Callable) -> Callable:
        """Decorator to profile individual functions."""
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                self.track_function_call(func.__name__, duration)
                if duration > 0.1:  # Log slow functions
                    self.logger.warning(f"{func.__name__} took {duration:.3f}s")
        return wrapper
    
    def log_performance_summary(self):
        """Log a summary of performance metrics."""
        metrics = self.get_metrics()
        
        self.logger.info("=== Performance Summary ===")
        self.logger.info(f"Web requests: {metrics['web_requests']}")
        self.logger.info(f"Lap count: {metrics['lap_count']}")
        
        if 'update_stats' in metrics:
            stats = metrics['update_stats']
            self.logger.info(f"Update time - Avg: {stats['avg']:.3f}s, "
                           f"Min: {stats['min']:.3f}s, Max: {stats['max']:.3f}s")
        
        if metrics['function_calls']:
            self.logger.info("\nFunction Call Statistics:")
            for func_name, stats in sorted(
                metrics['function_calls'].items(),
                key=lambda x: x[1]['total_time'],
                reverse=True
            )[:10]:  # Top 10 functions
                self.logger.info(
                    f"  {func_name}: {stats['count']} calls, "
                    f"avg {stats['avg_time']*1000:.1f}ms, "
                    f"total {stats['total_time']:.2f}s"
                )