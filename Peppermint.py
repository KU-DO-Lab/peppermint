import pyvisa
from qcodes.instrument import VisaInstrument
from utils.util import *
from textual import on
from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Tabs, Label, TabbedContent, TabPane, OptionList, Select

class Peppermint(App):
    """A Textual app to manage instruments."""
    CSS_PATH = "Peppermint.tcss"

    # Not implemented yet, but we will want to have different bindings for each page.
    BINDINGS = []
    TMP_BINDINGS = []
    PARAMETERS_TAB_BINDINGS = []
    INSTRUMENTS_TAB_BINDINGS = [
        Binding("m", "manual_connect", "Connect an Instrument Manually", show=True),
    ]
    
    # Lists for the instruments are reactive, since they can change
    detected_instruments: reactive[list[str]] = reactive(list)
    connected_instruments: reactive[list[VisaInstrument]] = reactive(list) 

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
                self.connected_instrument_list.add_option(instrument.name)

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        
        with TabbedContent():
            with TabPane("Instruments", id="instruments_tab"):
                self.detected_instrument_list: OptionList = OptionList(*self.detected_instruments)
                self.connected_instrument_list: OptionList = OptionList()  # Start empty
                yield Horizontal(
                    Vertical(Label("Detected Instruments"), self.detected_instrument_list),
                    Vertical(Label("Connected Instruments"), self.connected_instrument_list),
                )
            with TabPane("Parameters", id="parameters_tab"):
                instrument_options: list[tuple[str, str]] = [(element.name, element.name) for element in self.connected_instruments]
                self.parameters_connected_instrument_list = Select[str](options=instrument_options)
                self.available_parameters: OptionList = OptionList()
                self.followed_parameters: DataTable = DataTable()
                self.set_parameters: DataTable = DataTable()
                yield Horizontal(
                    # I am very bad at CSS, this needs changed to use it lmao -Grant
                    Vertical(
                        Label("Followed Parameters"), self.followed_parameters
                    ),
                    Vertical(
                        Label("Connected Instruments"), self.parameters_connected_instrument_list,
                        Label("Available Parameters"), self.available_parameters
                    ),
                    Vertical(
                        Label("Set Parameters"), self.set_parameters
                    ),
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

        # Grab the actual instrument object from the name of the instrument in the select menu
        selected_instrument: Optional[VisaInstrument] = next(
            (inst for inst in self.connected_instruments if inst.name == self.parameters_connected_instrument_list.value),
            None  # If for whatever reason an instrument can't be found this is set to none
        )

        if selected_instrument is None:
            return

        available_parameters = get_avail_instrument_params(selected_instrument)
        self.available_parameters.clear_options()
        for param in available_parameters:
            self.available_parameters.add_option(param)

        
    
    def connect_instrument(self, instrument_address: str) -> bool:
        """
        Connect to an instrument and update the connected instruments list.

        Returns True if connection was successful. Would probably be better to have this fail and handle the error instead.
        """
        try:
            # TODO: need to prompt for an instrument name here
            #       we can forcibly set the name to be "dummy" in development to use a simulated keithley.

            # Do the connection procses here- right now it just tries the auto-connect, but we will later handle manual connections here
            new_instrument = auto_connect_instrument(name="dummy", address=instrument_address)
            
            # Create a new list with the additional instrument
            new_connected = self.connected_instruments.copy()
            new_connected.append(new_instrument)
            self.connected_instruments = new_connected  # Trigger reactive update
            update_select(self.parameters_connected_instrument_list, [instrument.name for instrument in new_connected])
            
            return True
        except Exception as e:
            print(f"Error connecting to {instrument_address}: {e}")
            return False

if __name__ == "__main__":
    app = Peppermint()
    app.run()
