from enum import Enum
import threading
from sweep1d import *
import concurrent.futures

class SequenceStatus(Enum):
    IDLE = "idle"
    RUNNING = "running" 
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"

class ActionSequence:
    """Manages sequential execution of non-blocking measurements.
    
    Encompasses the following tasks:
    (1) Sequentially operates to safely start any number of sweeps/sets, one at a time.
    (2) Automatically progresses to the next action after the current one completes.
    (3) Provides detailed status and control over the sequence execution.
    (4) Supports pausing, resuming, and graceful stopping.
    """
    
    def __init__(self, sequence: list[Measurement]):
        self.sequence = sequence
        self.executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self.idx: Optional[int] = None  # Index of current measurement. None implies not started.
        self._status = SequenceStatus.IDLE
        self._sequence_thread: Optional[threading.Thread] = None
        self._pause_event = threading.Event()
        self._stop_requested = False
        self._current_measurement: Optional[Measurement] = None
        
        # Set pause event initially (not paused)
        self._pause_event.set()
    
    def start(self) -> None:
        """Start the sequence execution in a background thread."""
        if self._status != SequenceStatus.IDLE:
            print(f"Cannot start sequence - current status: {self._status.value}")
            return
            
        if not self.sequence:
            print("No measurements in sequence")
            return
            
        self._status = SequenceStatus.RUNNING
        self._stop_requested = False
        self.idx = None
        
        # Start sequence execution in background thread
        self._sequence_thread = threading.Thread(
            target=self._run_sequence,
            daemon=True
        )
        self._sequence_thread.start()
        print("Sequence started")
    
    def _run_sequence(self) -> None:
        """Main sequence execution loop (runs in background thread)."""
        try:
            for i, measurement in enumerate(self.sequence):
                # Check for stop request
                if self._stop_requested:
                    print("Sequence stopped by request")
                    break
                
                # Wait if paused
                self._pause_event.wait()
                
                # Check for stop request again after potential pause
                if self._stop_requested:
                    print("Sequence stopped by request")
                    break
                
                # Update current measurement info
                self.idx = i
                self._current_measurement = measurement
                print(f"Starting measurement {i+1}/{len(self.sequence)}")
                
                # Start the measurement (non-blocking)
                try:
                    measurement.start()
                except Exception as e:
                    print(f"Error starting measurement {i}: {e}")
                    self._status = SequenceStatus.ERROR
                    return
                
                # Wait for this measurement to complete
                if not self._wait_for_current_measurement():
                    # Either stopped or error occurred
                    return
                
                print(f"Measurement {i+1}/{len(self.sequence)} completed")
            
            # Sequence completed successfully
            if not self._stop_requested:
                print("Sequence completed successfully")
                self._status = SequenceStatus.IDLE
            
        except Exception as e:
            print(f"Unexpected error in sequence execution: {e}")
            self._status = SequenceStatus.ERROR
        finally:
            self._cleanup_sequence()
    
    def _wait_for_current_measurement(self) -> bool:
        """Wait for the current measurement to complete.
        
        Returns:
            True if measurement completed normally, False if stopped or error.
        """
        if not self._current_measurement:
            return False
        
        poll_interval: float = 0.5
        
        while True:
            # Check for stop request
            if self._stop_requested:
                print("Stopping current measurement...")
                self._current_measurement.end_data_collection()
                return False
            
            # Handle pause
            if not self._pause_event.is_set():
                self._status = SequenceStatus.PAUSED
                print("Sequence paused")
                self._pause_event.wait()  # Wait until unpaused
                self._status = SequenceStatus.RUNNING
                print("Sequence resumed")
            
            # Check if measurement is still active
            try:
                if not self._current_measurement.is_active():
                    return True  # Measurement completed
            except Exception as e:
                print(f"Error checking measurement status: {e}")
                self._status = SequenceStatus.ERROR
                return False
            
            # Sleep before next check
            time.sleep(poll_interval)
    
    def _cleanup_sequence(self) -> None:
        """Clean up after sequence completion or termination."""
        if self._current_measurement:
            try:
                self._current_measurement.end_data_collection()
            except Exception as e:
                print(f"Error cleaning up current measurement: {e}")
        
        self._current_measurement = None
        self.idx = None
        if self._status != SequenceStatus.ERROR:
            self._status = SequenceStatus.IDLE
    
    def stop(self) -> None:
        """Stop the sequence execution gracefully."""
        if self._status == SequenceStatus.IDLE:
            print("Sequence is not running")
            return
            
        print("Stopping sequence...")
        self._status = SequenceStatus.STOPPING
        self._stop_requested = True
        
        # Resume if paused so stop can be processed
        if not self._pause_event.is_set():
            self._pause_event.set()
        
        # Wait for sequence thread to finish
        if self._sequence_thread and self._sequence_thread.is_alive():
            self._sequence_thread.join(timeout=5.0)
            
            if self._sequence_thread.is_alive():
                print("Warning: Sequence thread did not stop gracefully")
        
        self._status = SequenceStatus.IDLE
        print("Sequence stopped")
    
    def pause(self) -> None:
        """Pause the sequence after the current measurement completes."""
        if self._status != SequenceStatus.RUNNING:
            print(f"Cannot pause - sequence status: {self._status.value}")
            return
            
        self._pause_event.clear()
        print("Sequence will pause after current measurement")
    
    def resume(self) -> None:
        """Resume a paused sequence."""
        if self._status != SequenceStatus.PAUSED:
            print(f"Cannot resume - sequence status: {self._status.value}")
            return
            
        self._pause_event.set()
        print("Resuming sequence")
    
    def status(self) -> tuple[str, Optional[int], Optional[str]]:
        """Returns (status, current_index, current_measurement_info)."""
        measurement_info = None
        if self._current_measurement and hasattr(self._current_measurement, '__class__'):
            measurement_info = self._current_measurement.__class__.__name__
            
        return (self._status.value, self.idx, measurement_info)
    
    def is_running(self) -> bool:
        """Check if the sequence is currently running."""
        return self._status == SequenceStatus.RUNNING
    
    def is_paused(self) -> bool:
        """Check if the sequence is currently paused."""
        return self._status == SequenceStatus.PAUSED
    
    def get_progress(self) -> tuple[int, int]:
        """Get current progress as (current_index, total_count).
        
        Returns (0, total) if not started, (current+1, total) if running.
        """
        total = len(self.sequence)
        current = 0 if self.idx is None else self.idx + 1
        return (current, total)
    
    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """Wait for the sequence to complete. Useful if something needs to be done after the sequence.
        
        Args:
            timeout: Maximum time to wait in seconds. None for no timeout.
            
        Returns:
            True if sequence completed, False if timeout or still running.
        """
        if not self._sequence_thread:
            return True
            
        try:
            self._sequence_thread.join(timeout=timeout)
            return not self._sequence_thread.is_alive()
        except Exception as e:
            print(f"Error waiting for sequence completion: {e}")
            return False
