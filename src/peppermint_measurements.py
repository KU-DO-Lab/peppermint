from typing import Optional, Protocol

from logging_scheduler import LoggingStrategy


class Measurement(Protocol):
    """Defines the methods which all measurement implementations (set/sweep) should inherit."""

    lifetime: Optional[LoggingStrategy] | None

    def start(self) -> None:
        """Initiates the measurement, SEPARATE from the logging/data collection loop."""
        ...

    def is_active(self) -> bool:
        ...

    def end_data_collection(self) -> None:
        """Ends data collection. Use in conjunction with the MeasurementContext."""
        ...
