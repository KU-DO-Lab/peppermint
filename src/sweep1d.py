import time
from qcodes.dataset.threading import ParamMeasT
from qcodes.instrument import VisaInstrument
from typing import Any, Optional, cast

from qcodes.parameters import Parameter
from datasaver import DataSaver
from drivers.Keithley_2450 import Keithley2450
from drivers.M4G_qcodes_official import CryomagneticsModel4G
from live_plotter import LivePlotter, LivePlotterManager
from logging_scheduler import ContinuousLogger, LoggingStrategy, MeasurementContext, SweepStrategy
from peppermint_measurements import Measurement
from util import run_concurrent


class Sweep1D(Measurement):
    """Simplest sweep type. Will be upgraded to a generic class in the future. """

    def __init__(self, datasaver: DataSaver, plot_manager: LivePlotterManager, table_name: str, instrument: VisaInstrument, 
                 parameter: Optional[float | None] = None, start_val: Optional[float | None] = None, stop_val: Optional[float | None] = None,
                 step_val: Optional[int | None] = None, rate: Optional[float | None] = None) -> None:

        # ContinuousLogger integration
        self._logger = ContinuousLogger(datasaver, table_name, polling_rate=0.2)

        # Plotting-specific attributes
        self._datasaver = datasaver
        self._table_name = table_name
        self._plot_manager = plot_manager
        
        # Sweep-specific attributes
        self._instrument = instrument
        self._parameter = parameter
        self._start_val = start_val
        self._stop_val = stop_val
        self._step_count = step_val
        self._sweep_active = False
        self._stop_requested = False
        
        # Parameters for data collection
        self._source_param: Optional[Parameter] = None
        self._sense_param: Optional[Parameter] = None
        self.buffer = None
        self.buffer_name = None
        self.lifetime: Optional[SweepStrategy] | None = None
        
        # Axis data for sweep
        self._axis_data: list[float] = []
        self._previous_buffer_size = 0

    def start(self) -> None:
        """Handler for a sweep based on the class construction."""
        handlers = {
            Keithley2450: self._start_keithley2450_sweep,
            CryomagneticsModel4G: self._start_cryomagneticsm4g_sweep,
        }

        handler = handlers.get(type(self._instrument))  # type: ignore
        if handler:
            handler()

    def _start_cryomagneticsm4g_sweep(self) -> None:
        """Dispatch for the Cryomagnetics Model 4G sweep.

        The model 4G effectively exposes 2 parameters: ramp rate and setpoint.
        Sweeps are accomplished by setting the first end of the sweep, ramping there, then repeating
        for the tail end of the sweep.
        """
        m4g = cast(CryomagneticsModel4G, self._instrument)

        m4g.reset()
        m4g.operating_mode(True)  # Remote mode

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
        if not self._step_count or not self._start_val or not self._stop_val:
            raise ValueError("Sweep parameters not properly configured")

        if self._sweep_active:
            raise RuntimeError("Sweep already active, cannot start new sweep")

        # Setup and initiate the sweep
        keithley = cast(Keithley2450, self._instrument)
        self.buffer_name = keithley.buffer_name()
        self.buffer = keithley.submodules[f"_buffer_{self.buffer_name}"]
        self.lifetime = SweepStrategy(self._instrument, cast(int, self._step_count))

        # 1. Setup the sweep
        self._sense_param = None
        self._source_param = None

        try: 
            keithley.sense.function("current" if self._parameter == "voltage" else "voltage")
            keithley.sense.range(1e-5 if self._parameter == "voltage" else 2)
            keithley.sense.four_wire_measurement(False)
            keithley.source.function(self._parameter)
            keithley.source.range(2 if self._parameter == "voltage" else 1e-5)
            keithley.source.sweep_setup(cast(float, self._start_val), cast(float, self._stop_val), cast(int, self._step_count))

            # declare the sense param and source param as their actual objects
            if self._parameter == "voltage":
                self._sense_param = cast(Parameter, keithley.submodules["_sense_current"].current)
                self._source_param = cast(Parameter, keithley.submodules["_source_voltage"].voltage)
            else:
                self._sense_param = cast(Parameter, keithley.submodules["_sense_voltage"].voltage)
                self._source_param = cast(Parameter, keithley.submodules["_source_current"].current)

        except Exception as e:
            print(f"Failed to set up Keithley sweep, check that all parameters are being set correctly: {e}")

        if not self._source_param or not self._sense_param:
            return

        # 2. Configure the plotter and start it.
        try:
            plotter = LivePlotter(
                self._datasaver,
                self._table_name,
                title = "Temperature Monitor",
                xlabel = f"{source_param.full_name}",       # type: ignore
                ylabel = f"{sense_param.full_name}",        # type: ignore
                xaxis_key = f"{source_param.full_name}",    # type: ignore
            )

            self._plot_manager.add_plotter(plotter)

        except Exception as e:
            print(f"Error in starting plotter for Keithley 2450: {e}")

        # 3. initiate the sweep
        try:
            cmd_args = keithley.source._sweep_arguments.copy()          # type: ignore
            cmd_args["function"] = keithley.source._proper_function     # type: ignore

            cmd = (
                ":SOURce:SWEep:{function}:LINear {start},{stop},"
                "{step_count},{delay},{sweep_count},{range_mode},"
                "{fail_abort},{dual},'{buffer_name}'".format(**cmd_args)
            )

            keithley.write(cmd)
            keithley.write(":INITiate")

        except Exception as e:
            print(f"Error initiating sweep: {e}")

        # 4. Begin data collection:
        try:
            self._sweep_active = True
            self._stop_requested = False

            self._previous_buffer_size = 0
            self._logger.start_logging(
                data_source=self._get_new_data_keithley,
                strategy=self.lifetime
            )

        except Exception as e:
            print(f"Error in data collection startup for Keithley 2450: {e}")
        finally:
            keithley.reset()

    def _get_new_data_keithley(self) -> list[tuple[Parameter, Any]]:
        """Data source function for ContinuousLogger.
        
        Returns new data points since last call, or empty list if no new data.
        """
        if not self.buffer or not self._source_param or not self._sense_param:
            return []
        
        try:
            # Get current buffer data
            current_buffer_size = cast(int, self.buffer.number_of_readings())
            
            if current_buffer_size <= self._previous_buffer_size:
                return []  # No new data
            
            # Get all data from buffer
            data_block: list[Any] = self.buffer.get_data(1, current_buffer_size)
            
            # Extract only new data
            new_sense_data = data_block[self._previous_buffer_size:]
            new_axis_data = self._axis_data[self._previous_buffer_size:self._previous_buffer_size + len(new_sense_data)]
            
            # Update tracking
            self._previous_buffer_size = current_buffer_size
            
            # Format as parameter-value pairs
            data_points = []
            for axis_val, sense_val in zip(new_axis_data, new_sense_data):
                data_points.append((self._source_param, axis_val))
                data_points.append((self._sense_param, sense_val))
            
            return data_points
            
        except Exception as e:
            print(f"Error getting data points: {e}")
            return []

    def is_active(self) -> bool:
        """Check if a sweep is currently running."""
        return self._sweep_active and self._logger.is_logging

    def end_data_collection(self) -> None:
        """Terminate data logging."""
        if not self._sweep_active:
            print("No active sweep to stop")
            return

        self._stop_requested = True

        # Stop the hardware sweep if it's still running
        try:
            if hasattr(self, '_instrument') and self._instrument:
                if type(self._instrument) == Keithley2450:
                    keithley = cast(Keithley2450, self._instrument)
                    keithley.abort()

        except Exception as e:
            print(f"Error during cleanup in end_data_collection: {e}")

        finally:
            # Ensure instrument is reset regardless of errors
            try:
                if hasattr(self, '_instrument') and self._instrument:
                    if type(self._instrument) == Keithley2450:
                        cast(Keithley2450, self._instrument).reset()
            except Exception as e:
                print(f"Error resetting instrument: {e}")
