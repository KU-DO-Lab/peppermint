from datetime import datetime
import os
import threading
import webbrowser

from bokeh.palettes import Spectral11
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
from bokeh.server.server import Server

from watchdog.observers import Observer

from util import DatabaseChangeHandler


class LivePlotter: 
    """Real-time data plotter implementing multiple display modes.

    Peppermint uses SQLite to log data, which for each given measurement (collections of related values) 
    is packaged nicely in a table. Each plotter mounts an observer to the table it is assigned to watch,
    and when new entries appear this is reflected in the plot by streaming a ColumnDataSource.

    This dramatically reduces plotting overhead since only new points are sent to the canvas and I/O 
    is done one row at a time with SQL which costs no more than a few miliseconds.

    Note: this does not check the TABLE, just the file (potential bottleneck). This may be possible with 
    triggers but I (Grant) am far from an expert using SQL. Presently, we don't need to collect data crazy 
    fast but we can look into this if it becomes an issue.

    Available frontends for display are:
    (1) Bokeh: opens an interactive plot in a web browser, ideal for quality. The plotting library 
        is designed with data streaming in mind.
    (2) Textual (planned): ASCII display for fun and a quick glance
    """

    def __init__( 
        self, datasaver, table_name: str, max_points: int | None = 2**18, xaxis_key: str = "timestamp",
        xlabel: str = "x-axis", ylabel: str = "y-axis", title: str = "Title"
    ):
        self.datasaver = datasaver
        self.title = title 
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.table_name = table_name
        self.xaxis_key = xaxis_key
        
        # 1. Watchdog setup 
        self.observer = Observer()
        self.observer.schedule(
            event_handler=DatabaseChangeHandler(self.datasaver.path, self.update_plot), 
            path=os.path.dirname(self.datasaver.path)
        )
        
        # 2. Bokeh components
        self.colors = Spectral11[:32]
        self.source = ColumnDataSource()
        
        # 3. Initialize with existing data
        table_contents = self.datasaver.get_table_values(self.table_name)
        if table_contents:
            for key, value in table_contents.items():
                self.source.data[key] = value
        
        # 4. Create plot
        self.plot = figure(
            title=self.title,
            x_axis_label=self.xlabel,
            y_axis_label=self.ylabel,
            x_axis_type="datetime" if self.xaxis_key == "timestamp" else "linear",
        )
        self.plot.legend.location = "top_left"
        self.plot.legend.click_policy = "hide"

        
        # 5. Server setup (necessary for streaming)
        self.server = None
        self.browser_opened = False
        self.running = False
        self._doc = None  # Store reference to Bokeh document

    def _setup_traces(self) -> None:
        """Look at the columns in the table and add a line if it isn't there. Exceptions may be added as needed here."""
        exceptions = ["id", "timestamp"]
        for i, trace in enumerate(self.datasaver.get_columns(self.table_name)):

            if trace in exceptions: 
                continue

            self.plot.line(x=self.xaxis_key, y=trace, source=self.source, 
                           legend_label=trace, line_color=self.colors[i],)

    def _open_browser(self) -> None:
        """Open the web browser. Not handled by Bokeh automatically."""
        webbrowser.open("http://localhost:5006")
        self.browser_opened = True

    def update_plot(self) -> None:
        """Updates plot by streaming latest table values when watchdog detects a change."""
        if not self.server or not self._doc:
            return  # Server/document not ready yet
            
        data = self.datasaver.get_tail_values(self.table_name, 1)
        if data:
            # 1. Ensure timestamp is a plottable format
            for i, timestamp in enumerate(data["timestamp"]):
                if timestamp:
                    if len(timestamp) < 20:
                        # In the case there are not fractional seconds its up to us to format
                        data["timestamp"][i] = datetime.strptime(timestamp[:26], "%Y-%m-%d %H:%M:%S") 
                    else: 
                        # Fractional seconds:
                        data["timestamp"][i] = datetime.strptime(timestamp[:26], "%Y-%m-%d %H:%M:%S.%f") 

            # 2. Use server context to safely modify document from another thread
            def update_doc():
                try:
                    self._setup_traces()
                    # Ensure all keys exist in source
                    for key in data:
                        if key not in self.source.data:
                            self.source.data[key] = []
                    
                    # Stream the new data
                    self.source.stream(data)
                except Exception as e:
                    print(f"Error updating plot: {e}")
            
            # 3. Execute update within Bokeh's document context
            try:
                self.server.io_loop.add_callback(lambda: self._doc.add_next_tick_callback(update_doc))
            except Exception as e:
                print(f"Error scheduling update: {e}")

    def bkapp(self, doc):
        """Bokeh server app to run the plot."""
        self._doc = doc  # Store document reference
        doc.add_root(self.plot)
        doc.title = self.title
        
        if not self.running:
            self.running = True
            # Now it's safe to start the watchdog
            self.observer.start()

    def start(self) -> None:
        """Start the Bokeh server and open in browser."""
        if not self.server:
            self.server = Server({'/': self.bkapp}, port=5006)
            self.server.start()
            
            # Open browser in a separate thread
            if not self.browser_opened:
                browser_thread = threading.Thread(target=self._open_browser, daemon=True)
                browser_thread.start()

    def stop(self) -> None:
        """Stop the plotter and clean up resources."""
        self.running = False
        
        # Stop watchdog observer
        if hasattr(self, 'observer'):
            self.observer.stop()
            self.observer.join()
        
        # Stop Bokeh server
        if self.server:
            self.server.stop()
