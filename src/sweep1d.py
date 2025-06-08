from concurrent.futures import ThreadPoolExecutor
import time
import concurrent
from qcodes.dataset import new_data_set
from qcodes.instrument import VisaInstrument
from typing import Optional, cast
import threading

from qcodes.parameters import Parameter
from datasaver import DataSaver
from drivers.Keithley_2450 import Keithley2450, Keithley2450Buffer, Keithley2450Source
import threading
from drivers.M4G_qcodes_official import CryomagneticsModel4G
from util import run_concurrent


class Sweep1D:
    """Simplest sweep type. Will be upgraded to a generic class in the future. """

    def __init__(self, datasaver: DataSaver, table_name: str, instrument: VisaInstrument, 
                 parameter: Optional[float | None] = None, start: Optional[float | None] = None, stop: Optional[float | None] = None,
                 step: Optional[float | None] = None, rate: Optional[float | None] = None) -> None:

        self.instrument = instrument
        self.parameter = parameter 
        self.start_val = start
        self.stop_val = stop 
        self.step_val = step
        self.rate_val = rate
        self.done_signal = threading.Event
        self.datasaver = datasaver
        self.table_name = table_name
        self.last_read_index = 0
        self.is_collecting = False
        self.reader_ready = threading.Event()


    def start(self) -> None:
        """Handler for a sweep based on the class construction."""
        handlers = {
            Keithley2450: self._start_keithley2450_sweep,
            CryomagneticsModel4G: self._start_cryomagneticsm4g_sweep,
        }

        handler = handlers.get(type(self.instrument)) # type: ignore
        if handler:
            handler()

    def _start_cryomagneticsm4g_sweep(self) -> None:
        """Dispatch for the Cryomagnetics Model 4G sweep.

        The model 4G effectively exposes 2 parameters: ramp rate and setpoint.
        Sweeps are accomplished by setting the first end of the sweep, ramping there, then repeating
        for the tail end of the sweep.
        """
        self.instrument.reset()
        self.instrument.operating_mode(True) # remote mode

    @run_concurrent
    def _start_keithley2450_sweep(self) -> None:
        """Dispatch for the Keithley 2450 hardware-driven sweep with continuous data collection.

        Does two things: 
        (1) initializes a sweep on the instrument in a non-blocking manner (necessary but may be dangerous, as no *WAI is used so that we may read).
        (2) reads the buffer at a polling rate (0.2 sec) and appends this to a datasaver table.

        todo:
            sweep setup may include redundant steps.
        """

        keithley = cast(Keithley2450, self.instrument) 
        self.buffer_name = keithley.buffer_name()
        self.buffer = keithley.submodules[f"_buffer_{self.buffer_name}"]
        
        # Setup instrument
        keithley.sense.function("current" if self.parameter == "voltage" else "voltage")
        keithley.sense.range(1e-5)
        keithley.sense.four_wire_measurement(False)
        keithley.source.function(self.parameter)
        keithley.source.range(2)
        keithley.source.sweep_setup(self.start_val, self.stop_val, self.step_val)

        # declare the sense param and source param as their actual objects
        if self.parameter == "voltage":
            sense_param = cast(Parameter, keithley.submodules["_sense_current"].current)
            source_param = cast(Parameter, keithley.submodules["_source_voltage"].voltage)
        else:
            sense_param = cast(Parameter, keithley.submodules["_sense_voltage"].voltage)
            source_param = cast(Parameter, keithley.submodules["_source_current"].current)

        try:
            cmd_args = keithley.source._sweep_arguments.copy()
            cmd_args["function"] = keithley.source._proper_function

            cmd = (
                ":SOURce:SWEep:{function}:LINear {start},{stop},"
                "{step_count},{delay},{sweep_count},{range_mode},"
                "{fail_abort},{dual},'{buffer_name}'".format(**cmd_args)
            )
    #
            keithley.write(cmd)
            keithley.write(":INITiate")

        except Exception as e:
            print(f"Error initiating sweep: {e}")

        if not self.step_val:
            return

        previous_buffer_size = 0 # compare with reading to subtract off data that has been logged already
        while cast(int, self.buffer.number_of_readings()) < self.step_val:
            time.sleep(0.2) # polling rate

            data_block: list[float] = self.buffer.get_data(1, self.buffer.number_of_readings()) # type: ignore
            new_sense_data: list[float] = data_block[previous_buffer_size:] # trim off old data

            axis: list[float] = keithley.source.sweep_axis() # just a linspace between start stop with steps.
            new_axis_data: list[float] = axis[previous_buffer_size:] # trim it down to append with sense_data

            previous_buffer_size: int = len(new_sense_data) # update length

            if data_block:
                source_data: list[tuple[Parameter, float]] = list(zip([source_param for _ in new_axis_data], new_axis_data))
                sense_data: list[tuple[Parameter, float]] = list(zip([sense_param for _ in new_sense_data], new_sense_data)) 

                # bundle both up and append to the table
                for _, (source_tup, sense_tup) in enumerate(zip(source_data, sense_data)):
                    self.datasaver.add_result(self.table_name, [source_tup, sense_tup])
