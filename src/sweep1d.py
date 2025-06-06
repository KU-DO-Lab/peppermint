import time
import concurrent
from qcodes.instrument import VisaInstrument
from typing import Optional, cast
import threading
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

    # @run_concurrent
    # def _start_keithley2450_sweep(self) -> None:
    #     """Dispatch for the Keithley 2450 hardware-driven sweep."""
    #     print("test")
    #
    #     with self.instrument.output_enabled.set_to(True):
    #         self.instrument.reset()
    #
    #         keithley = self.instrument
    #         keithley.sense.function("current" if self.parameter == "voltage" else "voltage")
    #         keithley.sense.range(1e-5)
    #         keithley.sense.four_wire_measurement(False)
    #
    #         keithley.source.function(self.parameter)
    #         keithley.source.range(0.2)
    #         keithley.source.sweep_setup(self.start_val, self.step_val, self.stop_val)
    #
    #         # Each measurement point saved immediately
    #         sweep_axis_values = keithley.source.sweep_axis()
    #         sweep_measurements = keithley.sense.sweep()
    #
    #         param_value_pairs = []
    #         for axis_val, meas_val in zip(sweep_axis_values, sweep_measurements):
    #             # Create individual parameter-value pairs for each data point
    #             single_measurement = [
    #                 (keithley.source.sweep_axis, axis_val),
    #                 (keithley.sense.sweep, meas_val)
    #             ]
    #
    #             self.datasaver.add_result(self.table_name, single_measurement)

    # def _measure_sweep(self) -> np.ndarray:
    #     source = cast(Keithley2450Source, self.parent.source)
    #     source.sweep_start()
    #     buffer_name = self.parent.buffer_name()
    #     buffer = cast(
    #         Keithley2450Buffer, self.parent.submodules[f"_buffer_{buffer_name}"]
    #     )
    #     end_idx = self.parent.npts()
    #     raw_data = buffer.get_data(1, end_idx, readings_only=True)
    #     raw_data_with_extra = buffer.get_data(1, end_idx)
    #     self.parent.sense.sweep._user_selected_data = raw_data_with_extra
    #     # Clear the trace so we can be assured that a subsequent measurement
    #     # will not be contaminated with data from this run.
    #     buffer.clear_buffer()
    #     return np.array([float(i) for i in raw_data])

    # @run_concurrent
    async def _start_keithley2450_sweep(self) -> None:
        """Dispatch for the Keithley 2450 hardware-driven sweep with continuous data collection."""
        # self.instrument.reset()
        keithley = self.instrument

        self.buffer_name = keithley.buffer_name()
        self.buffer = keithley.submodules[f"_buffer_{self.buffer_name}"]
        keithley.sense.function("current" if self.parameter == "voltage" else "voltage")
        keithley.sense.range(1e-5)
        keithley.sense.four_wire_measurement(False)
        keithley.source.function(self.parameter)
        keithley.source.range(2)
        keithley.source.sweep_setup(self.start_val, self.stop_val, self.step_val)
            
        # Initialize data collection variables
        self.is_collecting = True
        self.last_read_index = 0
        
        # with concurrent.futures.ThreadPoolExecutor() as executor:
        #     print("started")
        #     executor.submit(keithley.source.sweep_start())
        #     print("stopped")

        async def async_sweep_start(instr) -> None:
            instr.source.sweep.start()

        await async_sweep_start(keithley)
            
        end_idx: int = keithley.npts()
        print(f"start: {0}, stop: {end_idx}")
            
        while self.is_collecting:
            try:
                current_readings: int = self.buffer.number_of_readings() # type: ignore
                print(f"current readings: {current_readings}")
                
                if current_readings > self.last_read_index:
                    # Read new data from buffer
                    start_idx = self.last_read_index + 1
                    
                    raw_data = self.buffer.get_data(1, current_readings, readings_only=True)
                    print(raw_data)

        #     source_values = keithley._calculate_source_values(start_idx, end_idx)
            
        #     # Save each new data point
        #     new_points_count = 0
        #     for (source_val, meas_val) in zip(source_values, raw_data):
        #         param_value_pair = [
        #             (keithley.source.sweep_axis, source_val),
        #             (keithley.sense.sweep, meas_val)
        #         ]
        #         self.datasaver.add_result(self.table_name, param_value_pair)
        #         new_points_count += 1
                
        #         # Optional: Update live plot here
        #         # plotter.update_plot(source_val, meas_val)
            
        #     self.last_read_index = current_readings
        #     print(f"Saved {new_points_count} new data points")
                
                # Check if sweep is complete
                if current_readings >= keithley.npts():
                    print("Sweep completed - all data points collected")
                    self.is_collecting = False
                    break
                        
            except Exception as e:
                print(f"Error during data collection: {e}")
                self.is_collecting = False
                break
                
        # time.sleep(50e-3)
            
        #     # Clear the trace so we can be assured that a subsequent measurement
        #     # will not be contaminated with data from this run
        # self.buffer.clear_buffer()
        # print("Data collection finished and buffer cleared")
