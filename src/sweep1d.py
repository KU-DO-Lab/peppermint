from qcodes.instrument import VisaInstrument
from typing import Optional
import threading
from drivers.Keithley_2450 import Keithley2450
import threading
from drivers.M4G_qcodes_official import CryomagneticsModel4G


class Sweep1D:
    """Simplest sweep type. Will be upgraded to a generic class in the future. """

    def __init__(self, instrument: VisaInstrument, parameter: Optional[float | None] = None, start: Optional[float | None] = None, stop: Optional[float | None] = None,
                 step: Optional[float | None] = None, rate: Optional[float | None] = None) -> None:
        self.instrument = instrument
        self.parameter = parameter 
        self.start_val = start
        self.stop_val = stop 
        self.step_val = step
        self.rate_val = rate
        self.done_signal = threading.Event

    def start(self) -> None:
        """Handler for a sweep based on the class construction."""
        handlers = {
            Keithley2450: self.start_keithley2450_sweep,
            CryomagneticsModel4G: self.start_cryomagneticsm4g_sweep,
        }

        handler = handlers.get(type(self.instrument)) # type: ignore
        if handler:
            handler()

    def start_cryomagneticsm4g_sweep(self) -> None:
        """Dispatch for the Cryomagnetics Model 4G sweep.

        The model 4G effectively exposes 2 parameters: ramp rate and setpoint.
        Sweeps are accomplished by setting the first end of the sweep, ramping there, then repeating
        for the tail end of the sweep.
        """
        self.instrument.reset()
        self.instrument.operating_mode(True) # remote mode

    def start_keithley2450_sweep(self) -> None:
        """Dispatch for the Keithley 2450 hardware-driven sweep."""

        with self.instrument.output_enabled.set_to(True):
            self.instrument.reset()

            self.instrument.sense.function("voltage")
            self.instrument.sense.auto_range(True)
            self.instrument.source.function("current")
            self.instrument.source.auto_range(True)
            self.instrument.source.limit(2)
            self.instrument.source.sweep_setup(0, 1e-6, 10)

            print((self.instrument.sense.sweep, self.instrument.sense.sweep()))
