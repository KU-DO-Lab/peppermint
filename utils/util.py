import pyvisa
from qcodes.dataset import plot_dataset
from qcodes.instrument import VisaInstrument
from qcodes.parameters import ParameterBase
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.events import Compose
from textual.widget import Widget
from textual.widgets import Collapsible, Input, OptionList, Pretty, Select, Static, Switch
from utils.drivers.Lakeshore_336 import LakeshoreModel336
from utils.drivers.Keithley_2450 import Keithley2450
from textual.reactive import reactive
from typing import Optional
import time
from typing import Dict, List, Any, Callable, Optional

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from queue import Queue
import threading
from collections import deque
from typing import List, Dict, Any, Tuple

class SimpleLivePlotter:
    def __init__(
        self,
        channels: List[str],
        datasavers: Dict[str, Any],
        max_points: int = 1000,
        xlabel: str = "X-AXIS",
        ylabel: str = "Y-AXIS",
        title: str = "A LIVE Plot"
    ):
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
        
        self.fig = None
        self.ax = None
        self.plot_lines = {}
        self.plot_start_time = time.time()
        self.running = False
        self.animation = None
        self.plot_thread = None  # Thread for running the plot

    def setup_plot(self) -> None:
        """Initialize the plot."""
        self.fig, self.ax = plt.subplots(figsize=(10, 6))
        self.ax.set_title(self.title)
        self.ax.set_xlabel(self.xlabel)
        self.ax.set_ylabel(self.ylabel)
        self.ax.grid(True)
        
        for channel in self.channels:
            line, = self.ax.plot([], [], label=channel)
            self.plot_lines[channel] = line
            
        self.ax.legend()

    def _plot_worker(self):
        """Worker function to run the plot in a separate thread."""
        self.setup_plot()
        self.running = True
        
        def animate(frame):
            if not self.running:
                return []
                
            while not self.data_queue.empty():
                channel, x, y = self.data_queue.get()
                self.plot_data[channel]["x"].append(x)
                self.plot_data[channel]["y"].append(y)
                self.plot_lines[channel].set_data(
                    list(self.plot_data[channel]["x"]),
                    list(self.plot_data[channel]["y"])
                )

            self.ax.relim()
            self.ax.autoscale_view()
            return list(self.plot_lines.values())

        self.animation = FuncAnimation(
            self.fig, 
            animate,
            interval=50,
            blit=True
        )
        plt.show()  # Blocking call; handles GUI event loop

    def start(self) -> None:
        """Start the plotter in its own thread."""
        if not self.plot_thread:
            self.plot_thread = threading.Thread(target=self._plot_worker, daemon=True)
            self.plot_thread.start()

    def update(self, channel: str, x: float, y: float) -> None:
        """Add new data to the queue."""
        if channel in self.channels:
            self.data_queue.put((channel, x, y))

    def stop(self) -> None:
        """Stop the plot and clean up resources."""
        self.running = False
        if self.animation:
            self.animation.event_source.stop()
        if self.fig:
            plt.close(self.fig)
            self.fig = None
        if self.plot_thread:
            self.plot_thread.join()
            self.plot_thread = None
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
