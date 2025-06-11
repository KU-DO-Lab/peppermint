from typing import Protocol

from loggingscheduler import LoggingStrategy


class Measurement(Protocol):
    """Defines the methods which all measurement implementations (set/sweep) should inherit."""

    lifetime: LoggingStrategy

    def start(self) -> None:
        """Initiates the measurement, SEPARATE from the logging/data collection loop."""
        ...
