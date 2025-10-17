# performance_monitor.py
class PerformanceMonitor:
    def __init__(self):
        self.metrics = {
            'update_times': [],
            'web_requests': 0,
            'lap_count': 0
        }
    
    def track_update_time(self, duration):
        self.metrics['update_times'].append(duration)
        if len(self.metrics['update_times']) > 100:
            self.metrics['update_times'].pop(0)