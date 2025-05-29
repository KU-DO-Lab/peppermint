from contextlib import contextmanager
from functools import wraps
import os
import re
import sqlite3
from bokeh.application.application import Application
from bokeh.application.handlers.function import FunctionHandler
from bokeh.io import show
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
from bokeh.server.server import Server
from bokeh.palettes import Spectral11
import pyvisa
from qcodes.instrument import VisaInstrument
from typing import Any, Generator, Optional, List, Sequence, Tuple
import time, datetime
import webbrowser # to open the bokeh plot automatically without blocking the terminal
from queue import Queue
import threading
from collections import deque

from qcodes.parameters import Parameter
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static
from textual.worker import get_current_worker
from utils.drivers.Lakeshore_336 import LakeshoreModel336
from utils.drivers.Keithley_2450 import Keithley2450

from bokeh.plotting import figure
from bokeh.models import ColumnDataSource
from bokeh.palettes import Spectral11
from queue import Queue
from collections import deque
import time
import threading
import concurrent.futures
import webbrowser
import datetime
from typing import List

from utils.drivers.M4G_qcodes_official import CryomagneticsModel4G
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, LoggingEventHandler

def run_concurrent(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(func, *args, **kwargs)
            return future
    return wrapper

class DataSaver:
    def __init__(self, path: str) -> None:
        self.path = path
        self.local = threading.local()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a thread-local SQLite connection."""
        if not hasattr(self.local, 'connection'):
            conn = sqlite3.connect(self.path)
            self.local.connection = conn
        return self.local.connection

    @contextmanager
    def ds_connection(self) -> Generator[Any, Any, Any]:
        """Provides a connection to use with the "with" statement."""
        conn = self.get_connection()
        try:
            yield conn 
        finally:
            pass

    @contextmanager
    def ds_cursor(self) -> Generator[Any, Any, Any]:
        """Provides a cursor to use with the "with" statement."""
        cursor = self.get_connection().cursor()
        try:
            yield cursor 
        finally:
            pass

    def get_tables(self) -> List[str]:
        """Grab all of the tables in the opened db.

        Useful for auto-creating a new table to work on.
        """

        query = f"""
        SELECT 
            name
        FROM 
            sqlite_schema
        WHERE 
            type ='table' AND 
            name NOT LIKE 'sqlite_%';
        """

        with self.ds_connection() as conn:
            res = conn.execute(query)
            tables = [row[0] for row in res.fetchall()]

        return tables

    def get_columns(self, table_name):
        """Returns column names from a table"""

        query = f"""SELECT name FROM PRAGMA_TABLE_INFO("{table_name}");"""

        with self.ds_connection() as conn:
            res = conn.execute(query)
            names = [col[0] for col in res.fetchall()]

        return names

    def register_table(self, name) -> str:
        """Create a table/experiment in the database. If table exists, registers with name_# for duplicates."""

        tables = self.get_tables()
        pattern = re.compile(rf"^{re.escape(name)}(?:_(\d+))?$")
        indices = []

        for table_name in tables:
            match = pattern.match(table_name)
            if match:
                # If there is an index, parse it, else treat it as index 0
                index = int(match.group(1)) if match.group(1) else 0
                indices.append(index)

        next_index = max(indices) + 1 if indices else 0

        if next_index == 0:
            new_table_name = name
        else:
            new_table_name = f"{name}_{next_index}"

        create_table = f"""
        CREATE TABLE IF NOT EXISTS "{new_table_name}" (
            id INTEGER PRIMARY KEY
        );
        """

        with self.ds_connection() as conn:
            conn.execute(create_table)
            conn.commit()

        return new_table_name

    def _column_exists(self, table_name: str, column_name: str) -> bool:
        """Check if a column exists in the specified table."""

        try:
            with self.ds_connection() as conn:
                cursor = conn.execute(f'PRAGMA table_info("{table_name}");')
                columns = [row[1] for row in cursor.fetchall()]  # row[1] is the column name
            return column_name in columns
        except sqlite3.Error:
            return False

    def _ensure_column_exists(self, table_name: str, column_name: str, column_type: str = "NUMERIC") -> None:
        """Ensure a column exists in the table, create it if it doesn't."""

        if not self._column_exists(table_name, column_name):
            try:
                query = f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_type};'
                with self.ds_connection() as conn:
                    conn.execute(query)
                    conn.commit()
                print(f"Added column '{column_name}' to table '{table_name}'")
            except sqlite3.Error as e:
                print(f"Error adding column '{column_name}': {e}")
                raise

    def _ensure_table_exists(self, table_name: str) -> None:
        """Ensure the table exists with proper param/value structure."""

        query = f"""
        CREATE TABLE IF NOT EXISTS "{table_name}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            param TEXT NOT NULL,
            value NUMERIC NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
        with self.ds_connection() as conn:
            conn.execute(query)
            conn.commit()

    def add_result(self, table_name: str, param_value_pair: list[tuple[Parameter, float]]) -> None:
        """Add a set of values to a table. Automatically creates columns for the parameters if they do not exist."""

        if not param_value_pair:
            return
        
        self._ensure_table_exists(table_name)
        
        # Ensure all columns exist
        for parameter, _ in param_value_pair:
            self._ensure_column_exists(table_name, f"{parameter.full_name}", "NUMERIC")
        
        # Insert all values in one row
        column_names = [f'"{param.full_name}"' for param, _ in param_value_pair]  # Fixed: use underscore
        values = [value for _, value in param_value_pair]
        
        columns_str = ", ".join(column_names)
        placeholders = ", ".join(["?" for _ in values]) # Use placeholders to let SQLite insert the values below
        
        query = f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders});'

        with self.ds_cursor() as cursor:
            cursor.execute(query, values) # Pass the query and values now

        with self.ds_connection() as conn:
            conn.commit()

    def get_column_values(self, table_name: str, column_name: str) -> List[Any] | None:
        """Grab all of the data from a column. Should only really be used to query a few rows, use streaming otherwise."""

        if not self._column_exists(table_name, column_name):
            return None

        query = f'SELECT "{column_name}" FROM "{table_name}"'
        with self.ds_cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            rows = [row[0] for row in rows]

        return rows

    def get_table_values(self, table_name: str) -> dict | None:
        """Returns the entire table as a dict[column_name: List[values]]."""
        query = f'SELECT * FROM "{table_name}"'

        with self.ds_cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        columns = rows[0].keys() if rows else []
        data = {col: [] for col in columns}

        for row in rows:
            for col in columns:
                data[col].append(row[col])

        return data

    def get_tail_values(self, table_name: str, tail: int) -> dict[str, Sequence[Any]]:
        """Returns dict[column: list_of_values] containing the last number of entries determined by tail."""

        query = f'SELECT * FROM "{table_name}" ORDER BY ID DESC LIMIT ?'

        with self.ds_cursor() as cursor:
            cursor.execute(query, (tail,))
            rows = cursor.fetchall()

            columns = [desc[0] for desc in cursor.description]

        # Transpose rows to column-wise data
        data = {col: [] for col in columns}
        for row in rows:
            for col, val in zip(columns, row):
                data[col].append(val)

        return dict(data)

class Sweep1D:
    """Simplest sweep type. Will be upgraded to a generic class in the future. """

    def __init__(self, instrument: VisaInstrument, parameter: Optional[float | None] = None, start: Optional[float | None] = None, stop: Optional[float | None] = None,
                 step: Optional[float | None] = None, rate: Optional[float | None] = None) -> None:
        self.instrument = instrument
        self.parameter = parameter 
        self.start_val = start
        self.stop_val = stop 
        self.step_val = step
        self.rate_val = rate
        self.done_signal = threading.Event

    def start(self) -> None:
        """Handler for a sweep based on the class construction."""
        handlers = {
            Keithley2450: self.start_keithley2450_sweep,
            CryomagneticsModel4G: self.start_cryomagneticsm4g_sweep,
        }

        handler = handlers.get(type(self.instrument)) # type: ignore
        if handler:
            handler()

    def start_cryomagneticsm4g_sweep(self) -> None:
        """Dispatch for the Cryomagnetics Model 4G sweep.

        The model 4G effectively exposes 2 parameters: ramp rate and setpoint.
        Sweeps are accomplished by setting the first end of the sweep, ramping there, then repeating
        for the tail end of the sweep.
        """
        self.instrument.reset()
        self.instrument.operating_mode(True) # remote mode

    def start_keithley2450_sweep(self) -> None:
        """Dispatch for the Keithley 2450 hardware-driven sweep."""

        # initialise_database()
        # experiment = new_experiment(name="Keithley_2450_example", sample_name="no sample")
        self.instrument.output_enabled.set_to(True)
        self.instrument.reset()

        self.instrument.terminals("front")
        self.instrument.source.function("current")
        self.instrument.source.current(1e-6)  # Put 1uA through the resistor
        current_setpoint = self.instrument.source.current()

        voltage = self.instrument.sense.function("voltage")
        with self.instrument.output_enabled.set_to(True):
            voltage = self.instrument.sense.voltage()

        # self.instrument.sense.function("voltage")
        # self.instrument.sense.auto_range(True)
        #
        # self.instrument.source.function("current")
        # self.instrument.source.auto_range(True)
        # self.instrument.source.limit(2)
        # self.instrument.source.sweep_setup(0, 1e-6, 10)

        # keithley.sense.four_wire_measurement(True)
        #
        # meas = Measurement(exp=experiment)
        # meas.register_parameter(keithley.sense.sweep)
        #
        # with meas.run() as datasaver:
        #     datasaver.add_result(
        #         (keithley.source.sweep_axis, keithley.source.sweep_axis()),
        #         (keithley.sense.sweep, keithley.sense.sweep()),
        #     )
        #
        #     dataid = datasaver.run_id
        #
        # plot_dataset(datasaver.dataset)

class ActionSequence:
    """Does the measuring.

    Encompasses the following tasks:
    (1) Sequentially operates to safely start any number of sweeps/sets, one at a time.
    (2) Automatically progress to the next action in the sequence.
    (3) Provides access to the satus of the sequence.
    """

    def __init__(self, sequence: list[Sweep1D]):
        self.sequence = sequence
        self.executor: None | concurrent.futures.ThreadPoolExecutor = None
        self.idx = -1 # Index of the sequence

    def start(self) -> None:
        if self.executor == None:
            self.executor =  concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def run(self) -> None:
        """Set up the sequence and run.

        Currently implemented as a concurrent.futures executor to avoid blocking.
        """
        if self.executor == None:
            ... # will have to work out how to notify properly here
        else:
            for (i, fn) in enumerate(self.sequence):
                future = self.executor.submit(fn.start)
                result = future.result()  # Blocks until the function is done
                self.idx = i

    def stop(self) -> None:
        """Totally stops the sequence. Requires status to be paused to prevent accidental stops."""
        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=True)
            self.executor = None
            self.idx = -1

    def status(self) -> tuple[str, int]:
        """Returns (running/idle, index)"""
        if self.executor == None: 
            return ("idle", -1)
        else:
            return ("running", self.idx)

class DatabaseChangeHandler(FileSystemEventHandler):
    def __init__(self, db_path, action):
        self.db_path = db_path
        self.last_modified = os.path.getmtime(db_path)
        self.action = action
    
    def on_modified(self, event):
        if event.src_path == self.db_path:
            current_time = os.path.getmtime(self.db_path)
            if current_time > self.last_modified:
                self.last_modified = current_time
                self.handle_database_change()
    
    def handle_database_change(self):
        self.action()

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
    (2) Textual (WIP): ASCII display for fun and a quick glance
    """

    def __init__( 
        self, datasaver, table_name: str, max_points: int = 2**18, 
        xlabel: str = "x-axis", ylabel: str = "y-axis", title: str = "Title"
    ):
        self.datasaver = datasaver
        self.title = title 
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.table_name = table_name
        
        # 1. Watchdog setup 
        self.observer = Observer()
        self.observer.schedule(
            event_handler=DatabaseChangeHandler(self.datasaver.path, self.update_plot), 
            path=os.path.dirname(self.datasaver.path)
        )
        
        # 2. Bokeh components
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
            tools="xpan,xwheel_zoom,xbox_zoom,reset"
        )
        self.plot.x_range.follow = "end"
        self.plot.x_range.follow_interval = 100
        self.plot.x_range.range_padding = 0
        self.plot.line(x='id', y='simulated_lakeshore336_B_temperature', source=self.source)
        
        # 5. Server setup (necessary for streaming)
        self.server = None
        self.browser_opened = False
        self.running = False
        self._doc = None  # Store reference to Bokeh document

    def _open_browser(self):
        """Open the web browser. Not handled by Bokeh automatically."""
        webbrowser.open("http://localhost:5006")
        self.browser_opened = True

    def update_plot(self) -> None:
        """Updates plot by streaming latest table values when watchdog detects a change."""
        if not self.server or not self._doc:
            return  # Server/document not ready yet
            
        data = self.datasaver.get_tail_values(self.table_name, 1)
        if data:
            # Use server context to safely modify document from another thread
            def update_doc():
                try:
                    # Ensure all keys exist in source
                    for key in data:
                        if key not in self.source.data:
                            self.source.data[key] = []
                    
                    # Stream the new data
                    self.source.stream(data)
                except Exception as e:
                    print(f"Error updating plot: {e}")
            
            # Execute update within Bokeh's document context
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
    elif name == "simulated_cryomagnetics4g":
        return CryomagneticsModel4G("simulated_cryomagnetics4g", address="GPIB::1::INSTR", pyvisa_sim_file="cryo4g.yaml", max_current_limits={0: (0.0, 0.0)}, coil_constant=10.0,)

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

class MeasurementInitializerDialog(ModalScreen):
    def __init__(self):
        ...

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("Initialize a Measurement", classes="title"), 
            Horizontal(
                Static("Path: ", classes="inline"), Input(placeholder=f"{datetime.date.day}/{datetime.date.month}/{datetime.date.year}", classes="inline"), 
                Static("Path: ", classes="inline"), Input(placeholder="./Experiments/", classes="inline"), 
                classes="container-fill-horizontal"
            )
        )

def safe_query_value(container, selector, widget_type):
    try:
        return container.query_one(selector, widget_type).value
    except Exception:
        return None  # or some default value
