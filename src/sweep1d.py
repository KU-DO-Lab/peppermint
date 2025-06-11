import time
from qcodes.instrument import VisaInstrument
from typing import Optional, cast

from qcodes.parameters import Parameter
from datasaver import DataSaver
from drivers.Keithley_2450 import Keithley2450
from drivers.M4G_qcodes_official import CryomagneticsModel4G
from live_plotter import LivePlotter, LivePlotterManager
from util import run_concurrent


class Sweep1D:
    """Simplest sweep type. Will be upgraded to a generic class in the future. """

    def __init__(self, datasaver: DataSaver, plot_manager: LivePlotterManager, table_name: str, instrument: VisaInstrument, 
                 parameter: Optional[float | None] = None, start: Optional[float | None] = None, stop: Optional[float | None] = None,
                 step: Optional[float | None] = None, rate: Optional[float | None] = None) -> None:

        self._instrument = instrument
        self._parameter = parameter 
        self._start_val = start
        self._stop_val = stop 
        self._step_val = step
        self._rate_val = rate
        self._datasaver = datasaver
        self._table_name = table_name
        self._plot_manager = plot_manager

    def start(self) -> None:
        """Handler for a sweep based on the class construction."""
        handlers = {
            Keithley2450: self._start_keithley2450_sweep,
            CryomagneticsModel4G: self._start_cryomagneticsm4g_sweep,
        }

        handler = handlers.get(type(self._instrument)) # type: ignore
        if handler:
            handler()

    def _start_cryomagneticsm4g_sweep(self) -> None:
        """Dispatch for the Cryomagnetics Model 4G sweep.

        The model 4G effectively exposes 2 parameters: ramp rate and setpoint.
        Sweeps are accomplished by setting the first end of the sweep, ramping there, then repeating
        for the tail end of the sweep.
        """
        self._instrument.reset()
        self._instrument.operating_mode(True) # remote mode

    @run_concurrent
    def _start_keithley2450_sweep(self) -> None:
        """Dispatch for the Keithley 2450 hardware-driven sweep with continuous data collection and plotting.

        Does three things: 
        (1) initializes/starts a plotter for the sweep
        (2) initializes a sweep on the instrument in a non-blocking manner (necessary but may be dangerous, as no *WAI is used so that we may read).
        (3) reads the buffer at a polling rate (0.2 sec) and appends this to a datasaver table.

        todo:
            1. Manage plotting lifetime
            2. Make action sequence elements non-blocking to the UI
            3. Dynamically set sense/source range based on the input (makes some assumptions currently)
            4. Sweep setup may include redundant steps, optimize it
        """

        keithley = cast(Keithley2450, self._instrument) 
        self.buffer_name = keithley.buffer_name()
        self.buffer = keithley.submodules[f"_buffer_{self.buffer_name}"]
        
        # Setup instrument
        keithley.sense.function("current" if self._parameter == "voltage" else "voltage")
        keithley.sense.range(1e-5 if self._parameter == "voltage" else 2)
        keithley.sense.four_wire_measurement(False)
        keithley.source.function(self._parameter)
        keithley.source.range(2 if self._parameter == "voltage" else 1e-5)
        keithley.source.sweep_setup(cast(float, self._start_val), cast(float, self._stop_val), cast(int, self._step_val))

        # declare the sense param and source param as their actual objects
        if self._parameter == "voltage":
            sense_param = cast(Parameter, keithley.submodules["_sense_current"].current)
            source_param = cast(Parameter, keithley.submodules["_source_voltage"].voltage)
        else:
            sense_param = cast(Parameter, keithley.submodules["_sense_voltage"].voltage)
            source_param = cast(Parameter, keithley.submodules["_source_current"].current)

        # overwrite the plotter and start it
        try:
            plotter = LivePlotter(
                self._datasaver,
                self._table_name,
                title = "Temperature Monitor",
                xlabel = f"{source_param.full_name}",
                ylabel = f"{sense_param.full_name}",
                xaxis_key = f"{source_param.full_name}",
            )

            self._plot_manager.add_plotter(plotter)

        except Exception as e:
            print(f"Error in starting sweep for Keithley 2450: {e}")

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

        if not self._step_val:
            return
        
        axis: list[float] = keithley.source.sweep_axis() # just a linspace between start stop with steps.
        previous_buffer_size: int = 0 # compare with reading to subtract off data that has been logged already
        while cast(int, self.buffer.number_of_readings()) < self._step_val:
            time.sleep(0.2) # polling rate

            data_block: list[float] = self.buffer.get_data(1, self.buffer.number_of_readings()) # type: ignore
            new_sense_data: list[float] = data_block[previous_buffer_size:] # trim off old data

            new_axis_data: list[float] = axis[previous_buffer_size:] # trim it down to append with sense_data

            previous_buffer_size: int = len(new_sense_data) # update length

            if data_block:
                source_data: list[tuple[Parameter, float]] = list(zip([source_param for _ in new_axis_data], new_axis_data))
                sense_data: list[tuple[Parameter, float]] = list(zip([sense_param for _ in new_sense_data], new_sense_data)) 

                # bundle both up and append to the table
                for _, (source_tup, sense_tup) in enumerate(zip(source_data, sense_data)):
                    self._datasaver.add_result(self._table_name, [source_tup, sense_tup])

        keithley.reset()
