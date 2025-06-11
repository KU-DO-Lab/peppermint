import sys
import atexit
from bokeh.plotting import figure
import pyvisa
import argparse

from textual.app import App
from textual.theme import Theme

from live_plotter import LivePlotterApp, LivePlotterManager
from screens.instruments_screen import InstrumentsScreen, ManualConnectionDialog, SplashScreen
from screens.main_screen import MainScreen
from screens.parameters_screen import ParametersScreen
from screens.settings_screen import SettingsScreen
from screens.temperature_screen import TemperatureScreen
from screens.measurements_screen import MeasurementsScreen
from util import *
from datasaver import DataSaver
from themes import *
from typing import Optional
from dataclasses import dataclass, field
from qcodes.parameters import Parameter
from qcodes.instrument import VisaInstrument
from textual.reactive import reactive

@dataclass
class SharedState:
    """Dataclass for keeping track of the state of the application. 
    Important global variables (such as the parameters and what instruments are being used) are saved using this.
    """
    # Define attributes at class level with default values
    detected_instruments: reactive[list[str]] = field(default_factory=lambda: reactive(list))
    connected_instruments: reactive[list[VisaInstrument]] = field(default_factory=lambda: reactive(list))
    read_parameters: reactive[list[Parameter]] = field(default_factory=lambda: reactive(list))
    write_parameters: reactive[list[Parameter]] = field(default_factory=lambda: reactive(list))
    # database_path: str = ""
    # experiment: Experiment | None = None
    plot_server: LivePlotterApp | None = None
    datasaver: DataSaver | None = None
    plot_manager: LivePlotterManager | None = None
    
    def __post_init__(self):
        """Called after dataclass initialization."""
        super().__init__()
        
class Peppermint(App):
    """The app."""
    
    def __init__(self, simulated_mode: Optional[str | None] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.simulated_mode: Optional[str | None] = simulated_mode
        self.state: SharedState = SharedState()
        rm = pyvisa.ResourceManager() if sys.platform.startswith("win") else pyvisa.ResourceManager("@py") # py backend works better on unix
        self.state.detected_instruments = [ instr for instr in rm.list_resources() ]
        self.state.connected_instruments = []
        self.state.write_parameters = []
        self.state.read_parameters = []
        self.state.datasaver = DataSaver("./datasaver.db")
        self.state.plot_server = LivePlotterApp()
        self.state.plot_server.initialize()

        p = figure(width=400, height=400)
        p.line([1, 2, 3, 4, 5], [6, 7, 2, 4, 5], line_width=2)

        self.state.plot_server.attach_figure(p)
        self.state.plot_manager = LivePlotterManager(self.state.plot_server)

    CSS_PATH = "peppermint.css"

    BINDINGS = [
        ("i", "push_screen('instrument_screen')", "Instruments"),
        ("p", "push_screen('parameter_screen')", "Parameters"),
        ("e", "push_screen('electronic_measurements_screen')", "Electronic Measurements"),
        ("t", "push_screen('temperature_screen')", "Temperature Control"),
        ("a", "push_screen('main_screen')", "Main Screen")
    ]

    SCREENS = { 
        # "main_screen": MainScreen,
        "instrument_screen": InstrumentsScreen,
        "parameter_screen": ParametersScreen,
        "temperature_screen": TemperatureScreen,
        "electronic_measurements_screen": MeasurementsScreen,
        "manual_connection_dialog": ManualConnectionDialog,
        "settings_screen": SettingsScreen,
        "measurement_initializer_dialog": MeasurementInitializerDialog,
        "splash_screen": SplashScreen,
    }
    
    def on_mount(self) -> None:
        available_themes: dict[str, Theme] = BUILTIN_THEMES
        for theme in available_themes.values():
            self.register_theme(theme)
        self.theme = "oxocarbon"

        self.push_screen('instrument_screen')
        self.push_screen('splash_screen')
        # initialise_or_create_database_at(self.state.database_path) # again, this is a temporary thing, this should be initialized on demand or in experiments menu 

# Run the application, check args at the start
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

@atexit.register 
def exit_handler() -> None: 
    ...
