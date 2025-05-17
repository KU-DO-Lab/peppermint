import logging
from utils.util import *
from textual import on
from textual.app import ComposeResult
from textual.screen import Screen, ModalScreen
from textual.containers import Horizontal, Vertical, Grid
from textual.widgets import Footer, Header, Label, OptionList, Button, Placeholder

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
        self.detected_instrument_list: OptionList = OptionList(*self.app.state.detected_instruments)
        self.connected_instrument_list: OptionList = OptionList(*self.app.state.connected_instruments)  # Start empty
        yield Horizontal(
            Vertical(Label("Detected Instruments"), self.detected_instrument_list),
            Vertical(Label("Connected Instruments"), self.connected_instrument_list),
        )
        yield Footer()

    @on(OptionList.OptionSelected)
    def handle_detected_instruments_optionlist_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle instrument selection from the detected instruments list.

        Whenever an item on the list is selected, pass the ID off to the connect_instrument() 
        function. Also takes care of errors and logging.
        """
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
        # Do the connection procses here- right now it just tries the auto-connect, but we will later handle manual connections here
        if self.app.simulated_mode: 
            new_instrument = auto_connect_instrument(name=f"simulated_{self.app.simulated_mode}", address=instrument_address)
        else:
            new_instrument = auto_connect_instrument(address=instrument_address)

        # Create a new list with the additional instrument
        # directly overwriting this way is necessary to update the reactive variable
        new_connected = self.app.state.connected_instruments.copy()
        new_connected.append(new_instrument)
        self.app.state.connected_instruments = new_connected  # Trigger reactive update
        self.watch_connected_instruments(self.app.state.connected_instruments)
        

    def watch_connected_instruments(self, connected_instruments: list) -> None:
        """React to changes in connected instruments list."""
        if hasattr(self, 'connected_instrument_list'):
            self.connected_instrument_list.clear_options()
            for instrument in connected_instruments:
                self.connected_instrument_list.add_option(instrument.name)
