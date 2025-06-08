import os
import pyvisa
import concurrent.futures
import datetime
import datetime

from functools import wraps
from typing import Any, Generator, Optional, List, Sequence, Tuple

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from qcodes.instrument import VisaInstrument
from drivers.Lakeshore_336 import LakeshoreModel336
from drivers.Keithley_2450 import Keithley2450
from drivers.M4G_qcodes_official import CryomagneticsModel4G

from watchdog.events import FileSystemEventHandler

def run_concurrent(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(func, *args, **kwargs)
            return future
    return wrapper

class DatabaseChangeHandler(FileSystemEventHandler):
    def __init__(self, db_path, action):
        self.db_path = db_path
        self.dir_path = os.path.dirname(db_path)
        self.base_name = os.path.basename(db_path)
        self.last_modified = os.path.getmtime(db_path)
        self.action = action

    def on_modified(self, event):
        if not event.is_directory and self._is_related_file(event.src_path):
            try:
                current_time = os.path.getmtime(self.db_path)
                if current_time > self.last_modified:
                    self.last_modified = current_time
                    self.handle_database_change()
            except FileNotFoundError:
                pass  # File might be locked or temporarily inaccessible

    def _is_related_file(self, path):
        return any(path.endswith(suffix) for suffix in [self.base_name, '-wal', '-journal'])

    def handle_database_change(self):
        self.action()


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

    rm = pyvisa.ResourceManager("@py")
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
