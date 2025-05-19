from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
from bokeh.server.server import Server
from bokeh.palettes import Spectral11
import pyvisa
from qcodes.dataset import Measurement, initialise_database, new_experiment, plot_dataset
from qcodes.instrument import VisaInstrument
from typing import Optional, List
import time, datetime
import webbrowser # to open the bokeh plot automatically without blocking the terminal
from queue import Queue
import threading
from collections import deque
from utils.drivers.Lakeshore_336 import LakeshoreModel336
from utils.drivers.Keithley_2450 import Keithley2450

from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
from bokeh.palettes import Spectral11
from queue import Queue
from collections import deque
import time
import threading
import webbrowser
import datetime
from typing import List

class Sweep1D:
    """Simplest sweep type. Will be upgraded to a generic class in the future. """

    def __init__(self, instrument: VisaInstrument, parameter: str, start: float, stop: float, step: float) -> None:
        self.instrument = instrument
        self.parameter = parameter 
        self.start_val = start
        self.stop_val = stop 
        self.step_val = step
        self.done_signal = threading.Event

    def start(self) -> None:
        """Handler for a sweep based on the class construction."""
        handlers = {
            Keithley2450: self.start_keithley_sweep,
        }

        handler = handlers.get(type(self.instrument)) # type: ignore
        if handler:
            handler()

    def connect_to_database(self) -> None:
        """Append an entry to the tracked parameters and ensure it appears in the database/experiment."""
        # initialise_database()
        # experiment = new_experiment(name="Keithley_2450_example", sample_name="no sample")
        ...

    async def start_keithley_sweep(self) -> None:
        """Implementation of Keithley 2450 hardware-driven sweep."""

        print("sweeping keithley!")

        initialise_database()
        experiment = new_experiment(name="Keithley_2450_example", sample_name="no sample")

        keithley = self.instrument
        keithley.sense.function("voltage")
        keithley.sense.auto_range(True)

        keithley.source.function("current")
        keithley.source.auto_range(True)
        keithley.source.limit(2)
        keithley.source.sweep_setup(0, 1e-6, 10)

        keithley.sense.four_wire_measurement(True)

        meas = Measurement(exp=experiment)
        meas.register_parameter(keithley.sense.sweep)

        with meas.run() as datasaver:
            datasaver.add_result(
                (keithley.source.sweep_axis, keithley.source.sweep_axis()),
                (keithley.sense.sweep, keithley.sense.sweep()),
            )

            dataid = datasaver.run_id

        plot_dataset(datasaver.dataset)

class ActionSequence:
    """Does the measuring.

    Encompasses the following tasks:
    (1) Sequentially operates to safely start any number of sweeps/sets, one at a time.
    (2) Automatically progress to the next action in the sequence.
    (3) Provides access to the satus of the sequence.
    """

    def __init__(self, sequence: list[Sweep1D]):
        self.sequence = sequence

    async def start(self) -> None:
        """Initialize the first sweep in the sequence, create a worker thread, and progress the sequence.

        Implementations of sweeps in QCoDeS follows the pattern of the function returning implying it finishes. 
        Therefore a timer will not be used
        """

        for (i, fn) in enumerate(self.sequence):
            print(f"sweeping {i}")
            fn.start()

        # def run_sequence() -> None:
        #     for (i, f) in enumerate(self.sequence):
        #         print(f"sweeping {i}")
        #         f.start()
        #
        # thread = threading.Thread(target=run_sequence)
        # thread.start()
        # thread.join() # block the thread until it finishes

    def pause(self) -> None:
        """Pauses the current sweep."""
        ...

    def stop(self) -> None:
        """Totally stops the sequence. Requires status to be paused to prevent accidental stops."""
        ...

    def status(self) -> tuple[str, int]:
        """Returns (start/idle/paused, index)"""
        ...

class SimpleLivePlotter:
    """Real-time data plotter using Bokeh for external GUI.

    This class allows plotting real-time data using Bokeh, updating the plot
    periodically as new data is received. Bokeh is used instead of matplotlib,
    due to matplotlib's issues with threading/blocking'
    """

    def __init__(
        self,
        channels: List[str],
        max_points: int = 2**16,
        xlabel: str = "X-AXIS",
        ylabel: str = "Y-AXIS",
        title: str = "A LIVE Plot",
        use_timestamps: bool = False
    ):
        """Initialize the plotter with specified channels and plot parameters."""
        self.data_queue = Queue()
        self.title = title
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.channels = channels
        self.max_points = max_points
        self.use_timestamps = use_timestamps  # Flag to control x-axis format

        # Get colors from Bokeh's Spectral palette
        num_colors = max(11, len(channels))
        self.colors = Spectral11[:len(channels)]

        self.plot_data = {
            channel: {
                "x": deque(maxlen=max_points),
                "y": deque(maxlen=max_points)
            }
            for channel in channels
        }

        self.plot_lines = {}
        self.plot_start_time = time.time()
        self.running = False
        self.plot_thread = None
        self.sources = {channel: ColumnDataSource(data=dict(x=[], y=[])) for channel in channels}

        self.fig = figure(title=self.title, x_axis_label=self.xlabel, y_axis_label=self.ylabel, x_axis_type="datetime" if self.use_timestamps else "linear")
        self.fig.grid.grid_line_alpha = 0.3

        # Create plot lines with unique colors
        for i, channel in enumerate(self.channels):
            self.plot_lines[channel] = self.fig.line(
                'x', 'y',
                source=self.sources[channel],
                legend_label=channel,
                line_color=self.colors[i],
                line_width=2
            )
        self.fig.legend.location = "top_left"
        self.fig.legend.click_policy = "hide"

        self.server = None
        self.browser_opened = False

    def _update_plot(self):
        """Update the plot with new data."""
        while not self.data_queue.empty():
            channel, x, y = self.data_queue.get()
            if self.use_timestamps:
                # Convert x to a timestamp if use_timestamps is enabled
                x = datetime.datetime.fromtimestamp(x)
            self.plot_data[channel]["x"].append(x)
            self.plot_data[channel]["y"].append(y)
            self.sources[channel].data = {
                'x': list(self.plot_data[channel]["x"]),
                'y': list(self.plot_data[channel]["y"])
            }

    def _open_browser(self):
        """Open the web browser after a short delay to ensure server is ready."""
        time.sleep(1)
        webbrowser.open("http://localhost:5006")
        self.browser_opened = True

    def start(self) -> None:
        """Start the plotter and open in browser."""
        if not self.server:
            self.server = Server({'/': self.bkapp})
            self.server.start()
            
            # Open browser in a separate thread
            if not self.browser_opened:
                browser_thread = threading.Thread(target=self._open_browser, daemon=True)
                browser_thread.start()

    def bkapp(self, doc):
        """Bokeh server app to run the plot."""
        doc.add_root(self.fig)
        doc.add_periodic_callback(self._update_plot, 50)
        
        if not self.running:
            self.running = True
            if not self.plot_thread:
                self.plot_thread = threading.Thread(target=self._update_plot, daemon=True)
                self.plot_thread.start()

    def update(self, channel: str, x: float, y: float) -> None:
        """Add new data to the queue."""
        if channel in self.channels:
            self.data_queue.put((channel, x, y))

    def stop(self) -> None:
        """Stop the plot and clean up resources."""
        self.running = False
        if self.server:
            self.server.stop()

def match_instrument_name_to_object(name: str, instrument_list) -> Optional[VisaInstrument]:
    """
    Fields on screen have to be rendered using the instrument's name field, since we can't just write an instrument 
    object to the widget, that doesn't make sense. We still pull these names from a single list of instruments, so 
    if we, say, select a name of an instrument in one widget and want to use the result of that to render the parameters
    of that instrument, we will need to match the name of the instrument to the instrument object.
    """
    try:
        return next(inst for inst in instrument_list if inst.name == name)
    except StopIteration:
        return None

# This and connect instrument should be renamed to something a bit clearer.
def auto_connect_instrument(address: str, name=None, args=[], kwargs={}):
    """
    Attempts to automatically detect and connect to an instrument by querying IDN
    the result is matched to a driver and instantiate a connection and return the instrument itself

    TODO:
    - Type hinting
    - Prompt for name
    """

    # If we need to test without access to the lab hardware, just create a dummy instrument
    if name == "simulated_lakeshore":
        return LakeshoreModel336("simulated_lakeshore336", address="GPIB::2::INSTR", pyvisa_sim_file="lakeshore_model336.yaml")
    elif name == "simulated_keithley":
        return Keithley2450("simulated_keithley2450", address="GPIB::2::INSTR", pyvisa_sim_file="Keithley_2450.yaml")

    rm = pyvisa.ResourceManager()
    inst = rm.open_resource(address)
    IDN = ""
    
    try:
        IDN = inst.query("*IDN?")
        inst.close()
    except Exception as e:
        # We need this to fail otherwise the app will incorrectly add the instrument to the list of available instruments. 
        inst.close()
        raise(f"Error querying IDN : {e}")
    
    # Reference connect_device() from Spearmint for a superior function.
    match IDN.split(',')[1]:
        case "MODEL 2450":
            new_dev = Keithley2450("k2450", address, *args, **kwargs)
        case "MODEL336":
            new_dev = LakeshoreModel336("ls336", address, *args, **kwargs)
        case "IDN for TM620":
            ...
        case "4G":
            ...
    return new_dev
