import os
from typing import Generic, Optional
from dataclasses import dataclass
import logging

import pyvisa
from qcodes.parameters import Parameter, ParameterBase
from qcodes.instrument import VisaInstrument
from rich.text import Text
from utils.drivers import Lakeshore_336
from utils.util import *
from textual import on
from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.screen import Screen, ModalScreen
from textual.containers import Horizontal, Vertical, Grid, Container
from textual.widgets import DataTable, Footer, Header, Static, Label, TabbedContent, TabPane, OptionList, Select, Button, Placeholder, ListView, ListItem


@dataclass
class SharedState():
    """Class for keeping track of the state of the application."""
    def __init__(self):
        super().__init__()  # must be super init-ed for reactivity.
        detected_instruments: reactive[list[str]] = reactive(list) 
        connected_instruments: reactive[list[VisaInstrument]] = reactive(list) 
        read_parameters: reactive[list[Parameter]] = reactive(list)
        write_parameters: reactive[list[Parameter]] = reactive(list)
        database_path: str = ""

class ManualConnectionDialog(ModalScreen):
    """TODO: make this do something, add the right widgets"""

    BINDINGS = [("escape", "app.pop_screen", "Pop screen")]

    def compose(self) -> ComposeResult:
        yield Grid(
            Label("Manual Connection", id="title"),
            Placeholder("Placeholder.", id="tmp"),
            # Input(placeholder="A number", type="number"),
            Button("Cancel", variant="primary", id="cancel"),
            Button("Confirm", variant="primary", id="confirm"),
            id="dialog",
        )


class InstrumentsScreen(Screen):
    """Everything that will be displayed on the "Instruments" Tab."""

    BINDINGS = [("m", "app.push_screen('manual_connection_dialog')", "Manual Connection"), ("b", "app.dismiss()")]

    def compose(self) -> ComposeResult:
        yield Header()
        self.detected_instrument_list: OptionList = OptionList(*self.app.shared_state.detected_instruments)
        self.connected_instrument_list: OptionList = OptionList(*self.app.shared_state.connected_instruments)  # Start empty
        yield Horizontal(
            Vertical(Label("Detected Instruments"), self.detected_instrument_list),
            Vertical(Label("Connected Instruments"), self.connected_instrument_list),
        )
        yield Footer()

    @on(OptionList.OptionSelected)
    def handle_detected_instruments_optionlist_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle instrument selection from the detected instruments list."""
        # Only handle events from the detected instruments list
        if event.option_list is not self.detected_instrument_list:
            return

        option = event.option_list.get_option_at_index(event.option_index)
        instrument_address = option.prompt

        try:
            self.connect_instrument(str(instrument_address))
            self.notify(f"Successfully connected to {instrument_address}")
        except Exception as e:
            self.notify("Failed to connect to instrument\nTry manually connecting.")
            logging.error(f"Failed to connect to {instrument_address}: {e}")

    def connect_instrument(self, instrument_address: str) -> None:
        """Connect to an instrument and update the connected instruments list. """
        # TODO: need to prompt for an instrument name here
        #       we can forcibly set the name to be "dummy" in development to use a simulated keithley.

        # Do the connection procses here- right now it just tries the auto-connect, but we will later handle manual connections here
        # new_instrument = auto_connect_instrument(address=instrument_address)
        new_instrument = auto_connect_instrument(name="dummy", address=instrument_address)

        # Create a new list with the additional instrument
        # directly overwriting this way is necessary to update the reactive variable
        new_connected = self.app.shared_state.connected_instruments.copy()
        new_connected.append(new_instrument)
        self.app.shared_state.connected_instruments = new_connected  # Trigger reactive update
        self.watch_connected_instruments(self.app.shared_state.connected_instruments)
        

    def watch_connected_instruments(self, connected_instruments: list) -> None:
        """React to changes in connected instruments list."""
        if hasattr(self, 'connected_instrument_list'):
            self.connected_instrument_list.clear_options()
            for instrument in connected_instruments:
                self.connected_instrument_list.add_option(instrument.name)


class ParametersScreen(Screen):
    """Everything that will be displayed on the "Parameters" Tab."""

    BINDINGS = [
        ("r", "set_parameter_read", "Set Read Param"),
        ("w", "set_parameter_write", "Set Write Param"),
    ]

    def compose(self) -> ComposeResult: 
        yield Header()
        instrument_options: list[tuple[str, str]] = [(instrument.name, instrument.name) for instrument in self.app.shared_state.connected_instruments]
        self.connected_instrument_list = Select[str](options=instrument_options)
        self.available_parameters: ListView = ListView()
        self.read_parameters: ListView = ListView()
        self.write_parameters: ListView = ListView()
        yield Horizontal(
            # I am very bad at CSS, this needs changed to use it lmao -Grant
            Vertical(
                Label("Read Parameters"), self.read_parameters
            ),
            Vertical(
                Label("Connected Instruments"), self.connected_instrument_list,
                Label("Available Parameters"), self.available_parameters
            ),
            Vertical(
                Label("Set Parameters"), self.write_parameters
            ))
        yield Footer()

    async def on_screen_resume(self) -> None:
        """Handle the ScreenResume event."""
        # Perform some action when the screen is resumed
        self.connected_instrument_list.clear()
        self.instrument_options: list[tuple[str, str]] = [(instrument.name, instrument.name) for instrument in self.app.shared_state.connected_instruments]
        self.connected_instrument_list.set_options(self.instrument_options)

    @on(Select.Changed)
    def handle_parameter_instrument_changed(self, event: Select.Changed) -> None:
        """Fetch the new parameters for an instrument when that instrument is changed."""

        # Grab the actual instrument object from the name of the instrument in the select menu
        selected_instrument: Optional[VisaInstrument] = next(
            (inst for inst in self.app.shared_state.connected_instruments if inst.name == self.connected_instrument_list.value),
            None  # If for whatever reason an instrument can't be found this is set to none
        )

        if selected_instrument is None:
            return

        self.available_parameters.clear()
        for key, p in selected_instrument.parameters.items():
            self.available_parameters.append(ListItem(Static(p.name)))
        for name, submodule in selected_instrument.submodules.items():
            if hasattr(submodule, 'parameters'):
                for key, p in submodule.parameters.items():
                    self.available_parameters.append(ListItem(Static(p.name)))

    def action_set_parameter_read(self) -> None:
        """Sets parameter to active read mode"""
        selected: ListItem | None = self.available_parameters.highlighted_child
        
        if not selected or "read" in selected.classes or "write" in selected.classes:
            self.notify("Already reading/writing parameter" if selected else "No parameter selected")
            return

        try:
            param_name: str = str(selected.children[0].render()._renderable) # type: ignore
            instrument: Optional[VisaInstrument] = next(
                inst for inst in self.app.shared_state.connected_instruments 
                if inst.name == self.connected_instrument_list.value
            )
            
            if not instrument:
                raise ValueError("No instrument selected")
                
            param: ParameterBase = instrument.parameters[param_name]

            if not param.gettable:
                self.notify("parameter is not writeable!")
                return
            
            selected.add_class("read")
            self.app.shared_state.read_parameters.append(param) # in case the parameter needs to be accessed in a database
            self.read_parameters.append(ListItem(ParameterWidget(param, readonly=True)))

        except (AttributeError, IndexError):
            self.notify("Invalid parameter widget structure")
        except StopIteration:
            self.notify("No instrument selected")
        except Exception as e:
            self.notify(f"Error: {str(e)}")

    def action_set_parameter_write(self) -> None:
        """
        Assign the parameter active write mode.

        TODO: switching back-forth from read/write, set experiment
        """
        selected: ListItem | None = self.available_parameters.highlighted_child
        
        if not selected or "read" in selected.classes or "write" in selected.classes:
            self.notify("Already reading/writing parameter" if selected else "No parameter selected")
            return

        try:
            param_name: str = str(selected.children[0].render()._renderable) # type: ignore
            instrument: Optional[VisaInstrument] = next(
                inst for inst in self.app.shared_state.connected_instruments 
                if inst.name == self.connected_instrument_list.value
            )
            
            if not instrument:
                raise ValueError("No instrument selected")
                
            param: ParameterBase = instrument.parameters[param_name]

            if not param.settable:
                self.notify("parameter is not writeable!")
                return 

            selected.add_class("write")
            self.app.shared_state.write_parameters.append(param) # in case the parameter needs to be accessed in a database
            self.write_parameters.append(ListItem(ParameterWidget(param, readonly=False)))

        except (AttributeError, IndexError):
            self.notify("Invalid parameter widget structure")
        except StopIteration:
            self.notify("No instrument selected")
        except Exception as e:
            self.notify(f"Error: {str(e)}")
        

class TemperatureScreen(Screen):

    """TODO"""
    BINDINGS = [
        ("s", "setpoint", "Adjust Setpoint"),
    ] 

    ROWS = [
        ("Channel A:", "N/A"),
        ("Channel B:", "N/A"),
        ("Channel C:", "N/A"),
        ("Channel D:", "N/A"),
    ]

    def compose(self) -> ComposeResult:
        allowed_monitor_types = (LakeshoreModel336)
        self.allowed_temperature_monitors = [inst for inst in self.app.shared_state.connected_instruments if isinstance(inst, allowed_monitor_types)] # type: ignore
        self.instrument_options: list[tuple[str, str]] = [(instrument.name, instrument.name) for instrument in self.allowed_temperature_monitors]
        self.temperature_monitors_select = Select[str](self.instrument_options)

        self.status_table = Container(
            Horizontal(Label("Channel A:    "), Label("", id="channel_A")),
            Horizontal(Label("Channel B:    "), Label("", id="channel_B")),
            Horizontal(Label("Channel C:    "), Label("", id="channel_C")),
            Horizontal(Label("Channel D:    "), Label("", id="channel_D")),
        )

        # This mess should probably be rewritten by someone with a nonzero amount of css skill
        yield Header()
        yield Container(
        Horizontal(
            Horizontal(Static("Temperature Controller:     ", classes="label"), self.temperature_monitors_select, classes="temp_controller_instrument"),
            Vertical(Static("Status:", classes="label"), self.status_table, classes="temp_controller_status"),
            Container(Placeholder(), classes="temp_controller_controls"),
            classes="short_container"
        ),
        Container()
        )
        yield Footer()

    async def on_screen_resume(self) -> None:
        """Handle the ScreenResume event."""
        # Perform some action when the screen is resumed
        self.temperature_monitors_select.clear()
        self.instrument_options: list[tuple[str, str]] = [(instrument.name, instrument.name) for instrument in self.allowed_temperature_monitors]
        self.temperature_monitors_select.set_options(self.instrument_options)

class Sweep1DScreen(Screen):
    """TODO"""
    BINDINGS = [] 

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Sweep1D", id="sweep1D_tab"):
                yield Label()
        yield Footer()


class Sweep2DScreen(Screen):
    """TODO"""
    BINDINGS = [] 

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Sweep2D", id="sweep2D_tab"):
                yield Label()
        yield Footer()


class ActionQueueScreen(Screen):
    """TODO"""
    BINDINGS = [] 

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Action Queue", id="queue_tab"):
                yield Label()
        yield Footer()

class MainScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="main-menu-grid"):
            with Container(id="left-pane"):
                yield Button("Instruments", id="isnt_button")
                yield Button("Parameters", id="param_button")
                yield Button("Temperature", id="temp_button")
                yield Button("Experiments", id="exp_button")
                yield Button("Settings", id="settings_button")
            with Container(id="inst-list"):
                yield Label("Connected Instruments")
                yield ListView(*self.app.shared_state.connected_instruments)

    @on(Button.Pressed, "#isnt_button")
    def inst_button(self):
        self.app.push_screen("instrument_screen")

    @on(Button.Pressed, "#param_button")
    def param_button(self):
        self.app.push_screen("parameter_screen")

    @on(Button.Pressed, "#isnt_button")
    def temp_button(self):
        self.app.push_screen("temperature_screen")

        
class Peppermint(App):
    """A Textual app to manage instruments."""

    shared_state = SharedState()
    shared_state.detected_instruments = [ instr for instr in pyvisa.ResourceManager().list_resources() ]
    shared_state.connected_instruments = []
    shared_state.write_parameters = []
    shared_state.read_parameters = []
    shared_state.database_path = os.path.join(os.getcwd(), "TMP_experiment_container.db") # this is a horrible temporary thing, this should be set on startup or in experiments menu

    CSS_PATH = "Peppermint.css"

    BINDINGS = [
        ("i", "push_screen('instrument_screen')", "Instruments"),
        ("p", "push_screen('parameter_screen')", "Parameters"),
        ("t", "push_screen('temperature_screen')", "Temperature"),
        ("a", "push_screen('main_screen')", "Main Screen")
    ]

    SCREENS = { 
        "instrument_screen": InstrumentsScreen, #type: ignore
        "parameter_screen": ParametersScreen, #type: ignore
        "temperature_screen": TemperatureScreen, #type: ignore
        "manual_connection_dialog": ManualConnectionDialog, #type: ignore
        "main_screen": MainScreen
    }
    
    def on_mount(self) -> None:
        self.push_screen('main_screen')
        # initialise_or_create_database_at(self.shared_state.database_path) # again, this is a temporary thing, this should be initialized on demand or in experiments menu

if __name__ == "__main__":
    app = Peppermint()
    app.run()
