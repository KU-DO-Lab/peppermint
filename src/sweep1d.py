from concurrent.futures import ThreadPoolExecutor
import time
import concurrent
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

    # def _watch_buffer(self) -> None:
    #     """Continuously watch buffer for data changes."""
    #     last_seen_data = None
    #
    #     while self.is_collecting:
    #         try:
    #             # Always try to read the buffer - let the instrument handle empty states
    #             raw_data = self.buffer.get_data(1, self.step_val, readings_only=True)
    #
    #             if not raw_data: 
    #                 continue
    #
    #             # Only print when data actually changes
    #             if raw_data != last_seen_data:
    #                 print(f"Buffer update: {raw_data}")
    #                 last_seen_data = raw_data.copy() if hasattr(raw_data, 'copy') else list(raw_data)
    #
    #             time.sleep(0.01)
    #
    #         except Exception as e:
    #             # Don't break on exceptions - just log and continue
    #             print(f"Buffer read error: {e}")
    #             time.sleep(0.05)  # Longer delay after errors

    @run_concurrent
    def _start_keithley2450_sweep(self) -> None:
        """Dispatch for the Keithley 2450 hardware-driven sweep with continuous data collection."""

        keithley: Keithley2450 = self.instrument
        self.buffer_name = keithley.buffer_name()
        self.buffer = keithley.submodules[f"_buffer_{self.buffer_name}"]
        
        # Setup instrument
        keithley.sense.function("current" if self.parameter == "voltage" else "voltage")
        keithley.sense.range(1e-5)
        keithley.sense.four_wire_measurement(False)
        keithley.source.function(self.parameter)
        keithley.source.range(2)
        keithley.source.sweep_setup(self.start_val, self.stop_val, self.step_val)

        print("test")
        print(dir(keithley.submodules))
        print(keithley.submodules)
        print(dir(keithley.submodules["_sense_current"]))
        param = cast(
            Parameter, keithley.submodules["_sense_current"].current
        )
        # print(keithley.submodules["_sense_current"])

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

        time.sleep(1)
        # end_idx = keithley.actual_end()
        end_idx = keithley.npts()
        d: list[float] | None = self.buffer.get_data(1, end_idx) # type: ignore
        print(f"end: {end_idx}")

        if d:
            data = list(zip([param for _ in d], d))
            print(data)
            # self.datasaver.add_result(self.table_name, ))

        # def initiate_sweep():
        #         print("Sweep initiated.")
        #
        #         # Don't wait here - let it run asynchronously
        #
        #
        # def poll_keithley_data():
        #     time.sleep(0.2)
        #     for i in range(1, 5):
        #         try:
        #             time.sleep(0.1)
        #             print(keithley.ask(":SOURce1:SWEep:COUNt?"))
        #             # end_idx = keithley.npts()
        #             # raw_data = self.buffer.buffer_elements
        #             # # raw_data = self.buffer.get_data(1, end_idx, readings_only=True)
        #             # print(f"[Poll {i}] {raw_data}")
        #         except Exception as e:
        #             print(f"[Poll {i}] Error in Keithley 2450 sweep: {e}")

        # with ThreadPoolExecutor(max_workers=2) as executor:
        #     sweep_future = executor.submit(initiate_sweep)
        #     poll_future = executor.submit(poll_keithley_data)
        #     sweep_future.result()
        #     poll_future.result()
        
        # Initialize tracking - no buffer clearing
        # self.is_collecting = True
        
        # with ThreadPoolExecutor(max_workers=2) as executor:
        #     future_sweep = executor.submit(keithley.source.sweep_start)
        #
        #     # Brief delay to let sweep initialize and start populating buffer
        #     time.sleep(0.1)
        #     future_reader = executor.submit(self._watch_buffer)
        #
        #     # Wait for sweep to complete
        #     try:
        #         future_sweep.result()
        #     except Exception as e:
        #         print(f"Sweep error: {e}")
        #     finally:
        #         # Signal data collection to stop
        #         self.is_collecting = False
        #
        #     # Wait for reader to finish
        #     try:
        #         future_reader.result(timeout=2)
        #     except Exception as e:
        #         print(f"Reader cleanup error: {e}")
