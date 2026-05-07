
import time
import logging
import functools
from contextlib import contextmanager

logger = logging.getLogger("image_scoring.performance")

class PerformanceTimer:
    def __init__(self, name, logger=None, level=logging.DEBUG, slow_threshold_ms=None):
        self.name = name
        self.logger = logger or logging.getLogger("image_scoring.performance")
        self.level = level
        self.slow_threshold_ms = slow_threshold_ms
        self.start_time = None
        self.end_time = None
        self.duration = 0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        self.duration = (self.end_time - self.start_time) * 1000  # ms
        if exc_type:
            self.logger.log(self.level, f"[PERF] {self.name} FAILED in {self.duration:.2f}ms: {exc_val}")
        elif self.slow_threshold_ms is not None and self.duration > self.slow_threshold_ms:
            self.logger.warning(f"[PERF] {self.name} SLOW: {self.duration:.2f}ms (threshold: {self.slow_threshold_ms}ms)")
        else:
            self.logger.log(self.level, f"[PERF] {self.name} finished in {self.duration:.2f}ms")

def time_execution(name=None, slow_threshold_ms=None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            op_name = name or func.__name__
            with PerformanceTimer(op_name, slow_threshold_ms=slow_threshold_ms):
                return func(*args, **kwargs)
        return wrapper
    return decorator

def log_metric(name, value, unit=""):
    logger.info(f"[METRIC] {name}: {value}{unit}")
