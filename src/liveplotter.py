from datetime import datetime
import os
import threading
from typing import Set
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
        xlabel: str = "x-axis", ylabel: str = "y-axis", title: str = "Title",
        batch_size: int = 100, update_interval: float = 0.1
    ):
        self.datasaver = datasaver
        self.title = title 
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.table_name = table_name
        self.xaxis_key = xaxis_key
        self.batch_size = batch_size
        self.update_interval = update_interval
        
        # Performance optimization state
        self.last_processed_id = 0  # Track last processed row ID
        self.known_columns: Set[str] = set()  # Cache column names
        self.traces_initialized = False  # Track if traces are set up
        self.pending_updates = False  # Flag to batch multiple file change events
        self.update_lock = threading.Lock()
        
        # 1. Watchdog setup 
        self.observer = Observer()
        self.observer.schedule(
            event_handler=DatabaseChangeHandler(self.datasaver.path, self._mark_for_update), 
            path=os.path.dirname(self.datasaver.path)
        )
        
        # 2. Bokeh components
        self.colors = Spectral11[:32]
        self.source = ColumnDataSource()
        
        # 3. Initialize with existing data and cache columns
        self._initialize_data_and_schema()
        
        # 4. Create plot
        self.plot = figure(
            title=self.title,
            x_axis_label=self.xlabel,
            y_axis_label=self.ylabel,
            x_axis_type="datetime" if self.xaxis_key == "timestamp" else "linear",
        )
        self.plot.legend.location = "top_left"
        self.plot.legend.click_policy = "hide"

        # 5. Server setup
        self.server = None
        self.browser_opened = False
        self.running = False
        self._doc = None
        
        # 6. Batch update timer
        self.update_timer = None

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
            
        exceptions = {"id", "timestamp"}
        
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
        """Updates plot by streaming latest table values in batches."""
        if not self.server or not self._doc:
            return
        
        try:
            # 1. Check for schema changes (only occasionally)
            schema_changed = self._update_column_cache()
            
            # 2. Get batched data using get_tail_values
            # Calculate how many rows we need to fetch
            rows_to_fetch = min(self.batch_size, 1000)  # Cap at reasonable limit
            
            # Get recent data
            all_recent_data = self.datasaver.get_tail_values(self.table_name, rows_to_fetch)
            
            if not all_recent_data or not any(all_recent_data.values()):
                return
            
            # 3. Filter to only new rows (those with ID > last_processed_id)
            if 'id' not in all_recent_data:
                # Fallback: if no ID column, process all data (less efficient)
                data = all_recent_data
            else:
                # Filter for new rows only
                new_indices = [i for i, row_id in enumerate(all_recent_data['id']) 
                              if row_id > self.last_processed_id]
                
                if not new_indices:
                    return  # No new data
                
                # Extract only the new rows
                data = {}
                for column in all_recent_data:
                    data[column] = [all_recent_data[column][i] for i in new_indices]
            
            # 4. Batch timestamp parsing
            if "timestamp" in data:
                data["timestamp"] = self._parse_timestamps_batch(data["timestamp"])
            
            # 5. Update last processed ID
            if 'id' in data and data['id']:
                self.last_processed_id = max(data['id'])
            
            # 6. Schedule document update
            def update_doc():
                try:
                    # Only setup traces if schema changed
                    if schema_changed or not self.traces_initialized:
                        self._setup_traces()
                    
                    # Ensure all keys exist in source
                    for key in data:
                        if key not in self.source.data:
                            self.source.data[key] = []
                    
                    # Stream the batched data
                    self.source.stream(data)
                    
                except Exception as e:
                    print(f"Error updating plot: {e}")
            
            # Execute update within Bokeh's document context
            self.server.io_loop.add_callback(
                lambda: self._doc.add_next_tick_callback(update_doc)
            )
            
        except Exception as e:
            print(f"Error in batch update: {e}")

    def bkapp(self, doc):
        """Bokeh server app to run the plot."""
        self._doc = doc
        doc.add_root(self.plot)
        doc.title = self.title
        
        if not self.running:
            self.running = True
            # Setup initial traces
            self._setup_traces()
            # Start the watchdog
            self.observer.start()

    def start(self) -> None:
        """Start the Bokeh server and open in browser."""
        if not self.server:
            self.server = Server({'/': self.bkapp}, port=5006)
            self.server.start()
            
            if not self.browser_opened:
                browser_thread = threading.Thread(target=self._open_browser, daemon=True)
                browser_thread.start()

    def _open_browser(self) -> None:
        """Open the web browser."""
        webbrowser.open("http://localhost:5006")
        self.browser_opened = True

    def stop(self) -> None:
        """Stop the plotter and clean up resources."""
        self.running = False
        
        # Cancel pending timer
        if self.update_timer:
            self.update_timer.cancel()
        
        # Stop watchdog observer
        if hasattr(self, 'observer'):
            self.observer.stop()
            self.observer.join()
        
        # Stop Bokeh server
        if self.server:
            self.server.stop()
