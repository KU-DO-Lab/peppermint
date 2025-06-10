import threading
import time
from typing import Any, Callable, Protocol

from bokeh.core.property.singletons import Optional
from qcodes.parameters import Parameter

from datasaver import DataSaver


class MeasurementContext:
    """Context manager for automatic measurement cleanup."""
    
    def __init__(self, measurement):
        self.measurement = measurement
    
    def __enter__(self):
        return self.measurement
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self.measurement, 'stop'):
            self.measurement.stop()

class LoggingStrategy(Protocol):
    """Protocol defining the interface for different logging strategies."""
    
    def should_continue_logging(self) -> bool:
        """Return True if logging should continue, False otherwise."""
        ...
    
    def cleanup(self) -> None:
        """Cleanup resources when logging stops."""
        ...


class ContinuousLogger:
    """A flexible logger that can handle different measurement lifetimes."""
    
    def __init__(self, datasaver: DataSaver, table_name: str, polling_rate: float = 0.2):
        self._datasaver = datasaver
        self._table_name = table_name
        self._polling_rate = polling_rate
        self._logging_thread: Optional[threading.Thread] | None = None
        self._stop_event = threading.Event()
        self._is_logging = False
        self._lock = threading.Lock()
        
    def start_logging(self, data_source: Callable[[], list[tuple[Parameter, Any]]], 
                     strategy: LoggingStrategy) -> None:
        """Start continuous logging with the given strategy."""
        with self._lock:
            if self._is_logging:
                raise RuntimeError("Logger is already running")
            
            self._stop_event.clear()
            self._is_logging = True
            self._logging_thread = threading.Thread(
                target=self._logging_loop,
                args=(data_source, strategy),
                daemon=True
            )
            self._logging_thread.start()
    
    def stop_logging(self) -> None:
        """Stop the continuous logging."""
        with self._lock:
            if not self._is_logging:
                return
            
            self._stop_event.set()
            if self._logging_thread and self._logging_thread.is_alive():
                self._logging_thread.join(timeout=5.0)
            self._is_logging = False
    
    def _logging_loop(self, data_source: Callable[[], list[tuple[Parameter, Any]]], 
                     strategy: LoggingStrategy) -> None:
        """Main logging loop that runs in a separate thread."""
        try:
            while not self._stop_event.is_set() and strategy.should_continue_logging():
                try:
                    data_points = data_source()
                    if data_points:
                        for param, value in data_points:
                            self._datasaver.add_result(self._table_name, [(param, value)])
                except Exception as e:
                    print(f"Error during logging: {e}")
                
                time.sleep(self._polling_rate)
        finally:
            strategy.cleanup()
    
    @property
    def is_logging(self) -> bool:
        return self._is_logging

class ManualStopStrategy:
    """Strategy for measurements that log until manually stopped (like Setter)."""
    
    def __init__(self):
        self._should_continue = True
    
    def should_continue_logging(self) -> bool:
        return self._should_continue
    
    def stop(self) -> None:
        """Manually stop the logging."""
        self._should_continue = False
    
    def cleanup(self) -> None:
        pass


class SweepStrategy:
    """Strategy for sweep measurements that log until sweep completion."""
    
    def __init__(self, instrument, expected_points: int):
        self._instrument = instrument
        self._expected_points = expected_points
        self._buffer = None
        
        # Get buffer reference for Keithley instruments
        if hasattr(instrument, 'buffer_name'):
            buffer_name = instrument.buffer_name()
            self._buffer = instrument.submodules.get(f"_buffer_{buffer_name}")
    
    def should_continue_logging(self) -> bool:
        if self._buffer:
            current_readings = self._buffer.number_of_readings()
            return current_readings < self._expected_points
        return True  # Fallback for other instruments
    
    def cleanup(self) -> None:
        pass


class TimeBasedStrategy:
    """Strategy for measurements that log for a specific duration."""
    
    def __init__(self, duration_seconds: float):
        self._end_time = time.time() + duration_seconds
    
    def should_continue_logging(self) -> bool:
        return time.time() < self._end_time
    
    def cleanup(self) -> None:
        pass
