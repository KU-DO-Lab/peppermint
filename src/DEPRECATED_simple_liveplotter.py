from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
from bokeh.server.server import Server
from bokeh.palettes import Spectral11
from typing import List
import time, datetime
import webbrowser # to open the bokeh plot automatically without blocking the terminal
from queue import Queue
import threading
from collections import deque

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

class SimpleLivePlotter:
    """(DEPRECATED) Real-time data plotter using Bokeh for external GUI.

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
