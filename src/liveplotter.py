from datetime import datetime
import os
import threading
import time
from typing import Callable, Set
import uuid
import webbrowser

from bokeh.core.property.singletons import Optional
from bokeh.io import curdoc
from bokeh.layouts import column
from bokeh.palettes import Spectral11
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
from bokeh.server.server import Server

from watchdog.observers import Observer

from util import DatabaseChangeHandler

import threading
import webbrowser

from bokeh.application.application import Application
from bokeh.application.handlers.function import FunctionHandler
from bokeh.document import Document
from bokeh.models import Button, Div, GridBox, ScrollBox
from bokeh.models.layouts import Column
from bokeh.plotting import figure
from bokeh.server.server import Server

class LivePlotterApp():
    def __init__(self, port=5006) -> None:
        self._server: Server | None = None
        self.port: int = port
        self._doc: Document | None = None
        self.running = False
        self._browser_opened = False

    def create_app(self, doc):
        self._doc = doc

        # A Div that shows loaded status
        div = Div(text="<b>📡 Document loaded!</b>", width=200, height=30)

        # A Button you can click to test interactivity
        btn = Button(label="Test button", button_type="success")
        btn.on_click(lambda: print("Button clicked!"))

        # Add widgets to the document root
        doc.add_root(column(div, btn))

    def initialize(self):
        """Open browser and start server in own thread."""
        if self.running:
            print("Server is already running")
            return

        def start():
            self._server = Server({'/': self.create_app}, port=self.port, allow_websocket_origin=['localhost:5006', '127.0.0.1:5006'])
            self._server.start()
            self._server.show('/')
            self._server.io_loop.start()

        self._thread = threading.Thread(target=start, daemon=True)
        self._thread.start()

    def attach_figure(self, fig: figure) -> None:
        if self._doc:
            def add():
                try:
                    self._doc.add_root(fig)
                except Exception as e:
                    print(f"Error: {e}")

            self._doc.add_next_tick_callback(add)

    def get_doc(self):
        try:
            return curdoc()
        except RuntimeError:
            return None

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
            self, 
            datasaver, 
            table_name: str, 
            max_points: int | None = 2**18, 
            xaxis_key: str = "timestamp",
            xlabel: str = "x-axis", 
            ylabel: str = "y-axis", 
            title: str = "Title",
            batch_size: int = 100, 
            update_interval: float = 0.1,
            width: int = 600,
            height: int = 400
        ):
        self._doc: Document | None = None
        self.datasaver = datasaver
        self.title = title 
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.table_name = table_name
        self.xaxis_key = xaxis_key
        self.batch_size = batch_size
        self.update_interval = update_interval
        self.max_points = max_points
        self.width = width
        self.height = height

        # Generate unique ID for this plotter instance
        self.plotter_id = str(uuid.uuid4())[:8]

        # Performance optimization state
        self.last_processed_id = 0
        self.known_columns: Set[str] = set()
        self.traces_initialized = False
        self.pending_updates = False
        self.update_lock = threading.Lock()
        self.is_active = False

        # Callbacks for external notification
        self.update_callbacks: list[Callable] = []

        # Bokeh components
        self.colors = Spectral11[:32]
        self.source = ColumnDataSource()
        self.plot: figure | None = None

        # Watchdog setup
        self.observer = Observer()
        self.observer.schedule(
            event_handler=DatabaseChangeHandler(self.datasaver.path, self._mark_for_update), 
            path=os.path.dirname(self.datasaver.path)
        )

        self.update_timer = None

        # Initialize and create the figure
        self._initialize_data_and_schema()
        self._create_figure()

    def _create_figure(self) -> figure:
        self.plot = figure(
            title=self.title,
            x_axis_label=self.xlabel,
            y_axis_label=self.ylabel,
            x_axis_type="datetime" if self.xaxis_key == "timestamp" else "linear",
        )
        self.plot.legend.location = "top_left"
        self.plot.legend.click_policy = "hide"

        self._setup_traces()

        return self.plot

    def _initialize_data_and_schema(self) -> None:
        """Initialize plot data and cache the table schema."""
        # Get existing data
        table_contents = self.datasaver.get_table_values(self.table_name)
        if table_contents:
            for key, value in table_contents.items():
                self.source.data[key] = value

            # Set last processed ID to the highest existing ID
            if 'id' in table_contents and table_contents['id']:
                self.last_processed_id = max(table_contents['id'])

        # Cache column information
        self._update_column_cache()

    def _update_column_cache(self) -> bool:
        """Update the cached column information. Returns True if schema changed."""
        current_columns = set(self.datasaver.get_columns(self.table_name))
        schema_changed = current_columns != self.known_columns

        if schema_changed:
            self.known_columns = current_columns
            self.traces_initialized = False  # Force trace re-initialization

        return schema_changed

    def _setup_traces(self) -> None:
        """Set up plot traces only when needed (schema changes or first run)."""
        if self.traces_initialized:
            return

        exceptions = {"id", "timestamp", self.xaxis_key}

        # Clear existing traces if this is a re-initialization
        if hasattr(self.plot, 'renderers'):
            # Remove old line renderers
            self.plot.renderers = [r for r in self.plot.renderers if not hasattr(r, 'glyph')]

        # Add traces for new columns
        for i, trace in enumerate(self.known_columns):
            if trace in exceptions: 
                continue

            # Only add if not already in source data
            if trace not in self.source.data:
                self.source.data[trace] = []

            self.plot.line(
                x=self.xaxis_key, y=trace, source=self.source, 
                legend_label=trace, line_color=self.colors[i % len(self.colors)]
            )

        self.traces_initialized = True

    def _mark_for_update(self) -> None:
        """Mark that an update is needed (called by watchdog). Uses batching to avoid rapid updates."""
        with self.update_lock:
            if not self.pending_updates:
                self.pending_updates = True
                # Schedule batched update after a short delay
                if self.update_timer:
                    self.update_timer.cancel()
                self.update_timer = threading.Timer(self.update_interval, self._process_batched_update)
                self.update_timer.start()

    def _process_batched_update(self) -> None:
        """Process batched updates with optimized queries."""
        with self.update_lock:
            self.pending_updates = False
            self.update_plot()

    def _parse_timestamps_batch(self, timestamps: list) -> list:
        """Efficiently parse a batch of timestamps."""
        parsed = []
        for timestamp in timestamps:
            if not timestamp:
                parsed.append(None)
                continue

            try:
                # Try the most common format first
                if len(timestamp) < 20:
                    parsed.append(datetime.strptime(timestamp[:19], "%Y-%m-%d %H:%M:%S"))
                else:
                    parsed.append(datetime.strptime(timestamp[:26], "%Y-%m-%d %H:%M:%S.%f"))
            except ValueError:
                # Fallback for edge cases
                parsed.append(None)

        return parsed

    def update_plot(self) -> None:
        """Queue up a batched update; do all Bokeh work on the app thread."""
        try:
            # 1. Background work
            # Check schema, fetch rows, parse timestamps, filter new rows:
            schema_changed = self._update_column_cache()
            rows_to_fetch = min(self.batch_size, 1000)
            recent = self.datasaver.get_tail_values(self.table_name, rows_to_fetch)
            if not recent or not any(recent.values()):
                return

            if 'id' in recent:
                new_idxs = [i for i, rid in enumerate(recent['id']) if rid > self.last_processed_id]
                if not new_idxs:
                    return
                data = {col: [recent[col][i] for i in new_idxs] for col in recent}
            else:
                data = recent

            if 'timestamp' in data:
                data['timestamp'] = self._parse_timestamps_batch(data['timestamp'])

            new_last_id = max(data.get('id', [self.last_processed_id]))

            # 2. Schedule the Bokeh updates
            if self._doc:
                def _bokeh_update():
                    # a) If schema changed, re-init traces under lock
                    if schema_changed or not self.traces_initialized:
                        # update column cache again inside main thread
                        self._update_column_cache()
                        self._setup_traces()

                    # b) Update last_processed_id
                    self.last_processed_id = new_last_id

                    # c) Ensure every key exists in the CDS
                    for k in data:
                        if k not in self.source.data:
                            self.source.data[k] = []

                    # d) Stream the new data
                    self.source.stream(data)

                    # e) Fire callbacks
                    for cb in self.update_callbacks:
                        try:
                            cb()
                        except Exception as e:
                            print("Error in update callback:", e)

                self._doc.add_next_tick_callback(_bokeh_update)

        except Exception as e:
            print(f"Error in batch update for {self.table_name}: {e}")

    def start(self, doc) -> None:
        self._doc = doc
        self.observer.start()

    def get_figure(self) -> figure | None:
        if self.plot:
            return self.plot

class LivePlotterManager:
    """Manager class to handle multiple LivePlotter instances with LivePlotterApp."""

    def __init__(self, app: 'LivePlotterApp'):
        self.app = app
        self.plotters: dict[str, LivePlotter] = {}

    def add_plotter(self, plotter: LivePlotter) -> None:
        """Add a LivePlotter to the manager and attach its figure to the app."""
        plotter_id = plotter.plotter_id

        if plotter_id in self.plotters:
            print(f"Plotter {plotter_id} already exists")
            return

        self.plotters[plotter_id] = plotter

        # Attach figure to the app
        if self.app._doc:
            fig = plotter.get_figure()
            if fig:
                self.app.attach_figure(fig)

        plotter.start(doc=self.app._doc)

        print(f"Added plotter {plotter_id} for table {plotter.table_name}")
