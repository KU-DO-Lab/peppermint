import os
import pyvisa
import argparse

from textual.app import App

from utils.util import *
from typing import Optional
from dataclasses import dataclass
from qcodes.dataset import initialise_or_create_database_at, load_or_create_experiment
from qcodes.parameters import Parameter
from qcodes.instrument import VisaInstrument
from textual.reactive import reactive

from utils.InstrumentsScreen import *
from utils.TemperatureScreen import *
from utils.ParametersScreen import *
from utils.SettingsScreen import *
from utils.ElectronicMeasurementsScreen import *
from utils.MainScreen import *

@dataclass
class SharedState():
    """Dataclass for keeping track of the state of the application. 

    Important global variables are saved using this.
    """
    def __init__(self):
        super().__init__()  # must be super init-ed for reactivity.
        detected_instruments: reactive[list[str]] = reactive(list) 
        connected_instruments: reactive[list[VisaInstrument]] = reactive(list) 
        read_parameters: reactive[list[Parameter]] = reactive(list)
        write_parameters: reactive[list[Parameter]] = reactive(list)
        database_path: str = ""
        
class Peppermint(App):
    """A Textual app to manage instruments."""
    
    def __init__(self, simulated_mode: Optional[str | None] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.simulated_mode: Optional[str | None] = simulated_mode
        self.state: SharedState = SharedState()
        self.state.detected_instruments = [ instr for instr in pyvisa.ResourceManager().list_resources() ]
        self.state.connected_instruments = []
        self.state.write_parameters = []
        self.state.read_parameters = []
        self.state.database_path = os.path.join(os.getcwd(), "TMP_experiment_container.db") # this is a horrible temporary thing, this should be set on startup or in experiments menu

    CSS_PATH = "Peppermint.css"

    BINDINGS = [
        ("i", "push_screen('instrument_screen')", "Instruments"),
        ("p", "push_screen('parameter_screen')", "Parameters"),
        ("e", "push_screen('electronic_measurements_screen')", "Electronic Measurements"),
        ("t", "push_screen('temperature_screen')", "Temperature Control"),
        ("a", "push_screen('main_screen')", "Main Screen")
    ]

    SCREENS = { 
        "main_screen": MainScreen,
        "instrument_screen": InstrumentsScreen, #type: ignore
        "parameter_screen": ParametersScreen, #type: ignore
        "temperature_screen": TemperatureScreen, #type: ignore
        "electronic_measurements_screen": ElectronicMeasurementsScreen, # type: ignore
        "manual_connection_dialog": ManualConnectionDialog, #type: ignore
        "settings_screen": SettingsScreen, #type: ignore
    }
    
    def on_mount(self) -> None:
        self.theme = "nord"
        self.push_screen('main_screen')
        initialise_or_create_database_at(self.state.database_path) # again, this is a temporary thing, this should be initialized on demand or in experiments menu

    async def on_exit(self):
        # Perform cleanup tasks here
        print("Application is exiting. Performing cleanup...")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Peppermint")
    # parser.add_argument("--simulated-instruments", default=False, action="store_true", help="Run using a simulated dummy instrument")
    parser.add_argument(
        "--simulated-instruments",
        nargs="?",             # Argument can have 0 or 1 values
        const="default",       # Value used if the argument is present but no string is provided
        default=None,          # Value used if the argument is not provided
        help="Either lakeshore or keithley. Forcibly uses simulated drivers for one or the other for testing purposes."
    )
    args = parser.parse_args()

    Peppermint(simulated_mode=args.simulated_instruments).run()
