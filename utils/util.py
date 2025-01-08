from bokeh.plotting import figure, curdoc
from bokeh.models import ColumnDataSource
from bokeh.server.server import Server
import pyvisa
from qcodes.instrument import VisaInstrument
from textual.widgets import OptionList, Select, Input
from typing import Optional, Dict, List, Any
import time
from queue import Queue
import threading
from collections import deque
from utils.drivers.Lakeshore_336 import LakeshoreModel336
from utils.drivers.Keithley_2450 import Keithley2450

class SimpleLivePlotter:
    """Real-time data plotter using Bokeh for external GUI.

    This class allows plotting real-time data using Bokeh, updating the plot
    periodically as new data is received.
    """

    def __init__(
        self,
        channels: List[str],
        datasavers: Dict[str, Any],
        max_points: int = 1000,
        xlabel: str = "X-AXIS",
        ylabel: str = "Y-AXIS",
        title: str = "A LIVE Plot"
    ):
        """Initialize the plotter with specified channels, datasavers, and plot parameters.

        Args:
            channels (List[str]): A list of channels to plot.
            datasavers (Dict[str, Any]): A dictionary of datasavers associated with each channel.
            max_points (int, optional): Maximum number of data points to plot per channel. Default is 1000.
            xlabel (str, optional): Label for the X-axis. Default is "X-AXIS".
            ylabel (str, optional): Label for the Y-axis. Default is "Y-AXIS".
            title (str, optional): Title of the plot. Default is "A LIVE Plot".
        """
        self.data_queue = Queue()
        self.title = title
        self.xlabel = xlabel 
        self.ylabel = ylabel
        self.channels = channels
        self.datasavers = datasavers
        self.max_points = max_points
        
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
        
        self.fig = figure(title=self.title, x_axis_label=self.xlabel, y_axis_label=self.ylabel)
        self.fig.grid.grid_line_alpha = 0.3

        for channel in self.channels:
            self.plot_lines[channel] = self.fig.line(
                'x', 'y', source=self.sources[channel], legend_label=channel
            )
        self.fig.legend.location = "top_left"

        self.server = None

    def _update_plot(self):
        """Update the plot with new data.

        This function updates the plot with new data points from the data queue.
        It retrieves data for each channel and updates the corresponding plot line.
        """
        while not self.data_queue.empty():
            channel, x, y = self.data_queue.get()
            self.plot_data[channel]["x"].append(x)
            self.plot_data[channel]["y"].append(y)
            self.sources[channel].data = {
                'x': list(self.plot_data[channel]["x"]),
                'y': list(self.plot_data[channel]["y"])
            }
        print("Plot updated.")

    def _plot_worker(self):
        """Worker function to run the plot in a separate thread.

        This function starts a Bokeh server and adds periodic callbacks to update
        the plot at regular intervals.
        """
        self.running = True
        curdoc().add_periodic_callback(self._update_plot, 50)  # Update every 50ms
        print("Bokeh server started.")

    def start(self) -> None:
        """Start the plotter in its own thread, and initialize the server if needed.

        This function starts a background thread to handle plotting and, if necessary,
        starts a Bokeh server to serve the plot.

        Args:
            None
        """
        if not self.plot_thread:
            self.plot_thread = threading.Thread(target=self._plot_worker, daemon=True)
            self.plot_thread.start()

        if not self.server:
            self.server = Server({'/': self.bkapp}, port=5006)
            self.server.start()
            print("Bokeh server running on http://localhost:5006")

    def bkapp(self, doc):
        """Bokeh server app to run the plot.

        This function is used as the Bokeh application to render the plot in the
        Bokeh server. It adds the figure to the document and starts the plot updates.

        Args:
            doc (bokeh.document): The Bokeh document to add the figure to.
        """
        # Add the figure to the document
        doc.add_root(self.fig)
        # Ensure the data source is initialized before starting the plot updates
        doc.add_periodic_callback(self._update_plot, 509)  # Update every 500ms
        self.start()

    def update(self, channel: str, x: float, y: float) -> None:
        """Add new data to the queue.

        This function adds new data for a specific channel to the data queue for
        plotting.

        Args:
            channel (str): The channel to which the data belongs.
            x (float): The x-value (timestamp or measurement).
            y (float): The y-value (data point).
        """
        if channel in self.channels:
            self.data_queue.put((channel, x, y))
            print(f"Data updated for channel {channel}: ({x}, {y})")

    def stop(self) -> None:
        """Stop the plot and clean up resources.

        This function stops the Bokeh server and cleans up any resources associated
        with the plotter.

        Args:
            None
        """
        self.running = False
        if self.server:
            self.server.stop()
            print("Bokeh server stopped.")
        print("Plot stopped.")



# class ParameterWidget(Widget):
#     def __init__(self, param):
#         super().__init__()
#         self.param: ParameterBase = param
#         self.update_timer = None
#
#     def compose(self) -> ComposeResult:
#         yield Collapsible(
#             Pretty(self.param.get()),
#             Horizontal(
#                 Static("Live Update:     ", classes="label"), 
#                 Switch(id="live_toggle", value=False),
#                 classes="container"
#             ),
#             Input(id="update_freq", placeholder="Update Frequency (hz)"),
#             classes="parameter_entry",
#             title=self.param.full_name,
#         )
#
#     async def on_screen_suspend(self):
#         """When the screen is suspended pause everything"""
#         self.stop_updates()
#
#     async def on_screen_resume(self) -> None:
#         """restore previous state on screen resume"""
#         self.update_timer = self.set_interval(1.0, self.update_value)
#         self.restart_updates(self.update_timer)
#
#     def on_switch_changed(self, event: Switch.Changed) -> None:
#         if event.switch.value:
#             self.start_updates()
#         else:
#             self.stop_updates()
#
#     def on_input_changed(self, event: Input.Changed) -> None:
#         if event.input.value:
#             try:
#                 freq = float(event.input.value)
#                 self.restart_updates(freq)
#             except ValueError:
#                 pass
#
#     def on_mount(self) -> None:
#         self.start_updates()
#
#     def start_updates(self, freq=1.0):
#         self.stop_updates()
#         self.update_timer = self.set_interval(1/freq, self.update_value)
#
#     def stop_updates(self):
#         if self.update_timer:
#             self.update_timer.stop()
#
#     def restart_updates(self, freq):
#         self.start_updates(freq)
#
#     def update_value(self):
#         self.query_one(Pretty).update(self.param.get())

def update_option_list(option_list: OptionList, items: list):
    """Helper method to update an OptionList's contents."""
    option_list.clear_options()
    for item in items:
        option_list.add_option(item)

def update_select(select_list: Select, items: list):
    """Helper method to update an Select's contents."""
    select_list.set_options(
        [(element, element) for element in items]
    )

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
    the result is matched to a driver and instantiate a connection and return

    This should return with the instrument object. Need to add type hinting
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
