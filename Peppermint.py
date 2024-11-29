from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass
import logging

import pyvisa
from qcodes.instrument import VisaInstrument
from utils.util import *
from textual import on
from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.binding import Binding
from textual.screen import Screen, ModalScreen
from textual.containers import Horizontal, Vertical, Grid
from textual.widgets import DataTable, Footer, Header, Tabs, Label, TabbedContent, TabPane, OptionList, Select, Input, Button, Placeholder, ListView, ListItem


@dataclass
class SharedState():
    """Class for keeping track of the state of the application."""
    def __init__(self):
        super().__init__()  # must be super init-ed for reactivity.
        detected_instruments: reactive[list[str]] = reactive(list) 
        connected_instruments: reactive[list[VisaInstrument]] = reactive(list) 


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

    BINDINGS = [("m", "app.push_screen('manual_connection_dialog')", "Manual Connection")]

    def compose(self) -> ComposeResult:
        yield Header()
        self.detected_instrument_list: OptionList = OptionList(*self.app.shared_state.detected_instruments)
        self.connected_instrument_list: OptionList = OptionList()  # Start empty
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

        # TODO: Check if instrument is already connected
        # print(self.app.shared_state.connected_instruments)
        # if instrument_address in [instrument.address for instrument in self.app.shared_state.connected_instruments]:
            # self.notify("Instrument already connected")
            # return

        try:
            self.connect_instrument(instrument_address)
            self.notify(f"Successfully connected to {instrument_address}")
        except Exception as e:
            self.notify("Failed to connect to instrument\nTry manually connecting.")

    def connect_instrument(self, instrument_address: str) -> None:
        """Connect to an instrument and update the connected instruments list. """
        try:
            # TODO: need to prompt for an instrument name here
            #       we can forcibly set the name to be "dummy" in development to use a simulated keithley.

            # Do the connection procses here- right now it just tries the auto-connect, but we will later handle manual connections here
            new_instrument = auto_connect_instrument(name="dummy", address=instrument_address)

            # Create a new list with the additional instrument
            new_connected = self.app.shared_state.connected_instruments.copy()
            new_connected.append(new_instrument)
            self.app.shared_state.connected_instruments = new_connected  # Trigger reactive update
            self.watch_connected_instruments(self.app.shared_state.connected_instruments)

        except Exception as e:
            logging.error(f"Failed to connect to {instrument_address}: {e}")

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
        self.followed_parameters: ListView = ListView()
        self.set_parameters: ListView = ListView()
        yield Horizontal(
            # I am very bad at CSS, this needs changed to use it lmao -Grant
            Vertical(
                Label("Followed Parameters"), self.followed_parameters
            ),
            Vertical(
                Label("Connected Instruments"), self.connected_instrument_list,
                Label("Available Parameters"), self.available_parameters
            ),
            Vertical(
                Label("Set Parameters"), self.set_parameters
            ))
        yield Footer()

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
            self.available_parameters.append(ListItem(Label(p.full_name)))

    def action_set_parameter_read(self) -> None:
        """Assign the parameter active read mode."""
        if "read" in self.available_parameters.highlighted_child.classes:
            self.notify("Already reading parameter")
            return 
        else:
            self.available_parameters.highlighted_child.add_class("read")

    def action_set_parameter_write(self) -> None:
        """Assign the parameter active write mode."""
        if "write" in self.available_parameters.highlighted_child.classes:
            self.notify("Already reading parameter")
            return 
        else:
            self.available_parameters.highlighted_child.add_class("write")





class TemperatureScreen(Screen):
    """TODO"""
    BINDINGS = [] 

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Temperature", id="temperature_tab"):
                yield Label()
        yield Footer()


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


class Peppermint(App):
    """A Textual app to manage instruments."""

    shared_state = SharedState()
    shared_state.detected_instruments = [ instr for instr in pyvisa.ResourceManager().list_resources() ]
    shared_state.connected_instruments = []

    CSS_PATH = "Peppermint.css"

    BINDINGS = [
        ("i", "push_screen('instrument_screen')", "Instruments"),
        ("p", "push_screen('parameter_screen')", "Parameters"),
    ]
    SCREENS = { 
        "instrument_screen": InstrumentsScreen, #type: ignore
        "parameter_screen": ParametersScreen, #type: ignore
        "manual_connection_dialog": ManualConnectionDialog, #type: ignore
    }

    def on_mount(self) -> None:
        self.push_screen('instrument_screen')


if __name__ == "__main__":
    app = Peppermint()
    app.run()
