import pyvisa
from utils.util import *
from textual import on
from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Tabs, Label, TabbedContent, TabPane, OptionList, Select

class Peppermint(App):
    """A Textual app to manage instruments."""
    CSS_PATH = "Peppermint.tcss"

    # Not implemented yet, but we will want to have different bindings for each page.
    BINDINGS = []
    TMP_BINDINGS = []
    INSTRUMENTS_TAB_BINDINGS = [
        Binding("c", "connect_selected", "Connect Instrument", show=True),
        Binding("m", "manual_connect", "Connect an Instrument Manually", show=True),
    ]
    
    # Lists for the instruments are reactive, since they can change
    detected_instruments = reactive(list)
    connected_instruments = reactive(list) # This is going to be a list of instrument objects, so we will have to think of a good way to manage display data for it.

    def __init__(self):
        super().__init__()
        # Initialize the lists in __init__ to avoid weirdness
        self.detected_instruments = [ instr for instr in pyvisa.ResourceManager().list_resources() ]
        self.connected_instruments = []

    def watch_connected_instruments(self, connected_instruments: list) -> None:
        """React to changes in connected instruments list."""
        if hasattr(self, 'connected_instrument_list'):
            self.connected_instrument_list.clear_options()
            for instrument in connected_instruments:
                self.connected_instrument_list.add_option(instrument)

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        
        with TabbedContent():
            with TabPane("Instruments", id="instruments_tab"):
                self.detected_instrument_list = OptionList(*self.detected_instruments)
                self.connected_instrument_list = OptionList()  # Start empty
                yield Horizontal(
                    Vertical(Label("Detected Instruments"), self.detected_instrument_list),
                    Vertical(Label("Connected Instruments"), self.connected_instrument_list),
                )
            with TabPane("Parameters", id="parameters_tab"):
                self.parameters_connected_instrument_list = Select([(element, element) for element in self.connected_instruments])
                self.available_parameters = OptionList()
                yield Horizontal(
                    Horizontal(),  # Left spacer
                    Vertical(
                        Label("Connected Instruments"), self.parameters_connected_instrument_list,
                        Label("Available Parameters"), self.available_parameters
                    ),
                    Horizontal()   # Right spacer
                )
            with TabPane("Temperature", id="temperature_tab"):
                yield Label()
            with TabPane("Sweep1D", id="sweep1D_tab"):
                yield Label()
            with TabPane("Sweep2D", id="sweep2D_tab"):
                yield Label()
            with TabPane("Action Queue", id="queue_tab"):
                yield Label()
        yield Footer()
    
    def on_mount(self) -> None:
        """Focus the tabs when the app starts."""
        self.query_one(Tabs).focus()

    @on(OptionList.OptionSelected)
    def handle_detected_instruments_optionlist_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle instrument selection from the detected instruments list."""
        # Only handle events from the detected instruments list
        if event.option_list is not self.detected_instrument_list:
            return

        option = event.option_list.get_option_at_index(event.option_index)
        instrument_address = option.prompt

        # Check if instrument is already connected
        if instrument_address in self.connected_instruments:
            self.notify("Instrument already connected")
            return

        if self.connect_instrument(instrument_address):
            self.notify(f"Successfully connected to {instrument_address}")
        else:
            self.notify("Failed to connect to instrument\nTry manually connecting.")

    @on(Select.Changed)
    def handle_parameter_instrument_changed(self, event: Select.Changed) -> None:
        """Fetch the new parameters for an instrument when that instrument is changed."""
        ...
    
    def connect_instrument(self, instrument_address: str) -> bool:
        """
        Connect to an instrument and update the connected instruments list.
        Returns True if connection was successful.
        """
        try:
            # Do the connection procses here- right now it just tries the auto-connect, but we will later handle
            # manual connection here.
            new_instrument = auto_connect_instrument(name="", address=instrument_address)
            
            # Create a new list with the additional instrument
            new_connected = self.connected_instruments.copy()
            new_connected.append(new_instrument)
            self.connected_instruments = new_connected  # Trigger reactive update
            update_select(self.parameters_connected_instrument_list, new_connected)
            
            return True
        except Exception as e:
            print(f"Error connecting to {instrument_address}: {e}")
            return False

if __name__ == "__main__":
    app = Peppermint()
    app.run()
