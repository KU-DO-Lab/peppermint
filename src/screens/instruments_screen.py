import logging
from bokeh.models import Switch, Title
from textual.reactive import reactive
from util import *
from textual import on
from textual.app import ComposeResult
from textual.screen import Screen, ModalScreen
from textual.containers import Center, Container, Horizontal, HorizontalGroup, Vertical, Grid, VerticalScroll
from textual.widgets import Footer, Header, Input, Label, OptionList, Button, Placeholder, Select

class SplashScreen(ModalScreen):
    BINDINGS = [("escape", "app.pop_screen", "Close")]

    def compose(self) -> ComposeResult:
        VERSION = 0.1

        leaf_color: str = self.app.theme_variables["primary"]
        title_color: str = self.app.theme_variables["accent"]

        print(leaf_color)
        TITLE = f"""[bold]
    [{leaf_color}] | [/]        [{title_color}]      ____                                       _       __               [/]
  [{leaf_color}] .'|'. [/]      [{title_color}]     / __ \\___  ____  ____  ___  _________ ___  (_)___  / /_             [/]
 [{leaf_color}] /.'|\\ \\ [/]   [{title_color}]      / /_/ / _ \\/ __ \\/ __ \\/ _ \\/ ___/ __ `__ \\/ / __ \\/ __/      [/]
 [{leaf_color}] | /|'.| [/]     [{title_color}]   / ____/  __/ /_/ / /_/ /  __/ /  / / / / / / / / / / /_                [/] 
  [{leaf_color}] \\ |\\/ [/]    [{title_color}]    /_/    \\___/ .___/ .___/\\___/_/  /_/ /_/ /_/_/_/ /_/\\__/           [/] 
   [{leaf_color}] \\|/ [/]      [{title_color}]             /_/   /_/                                                    [/]
    [{leaf_color}] ` [/]          
"""

        INFO = """
• [bold]Currently in the works:[/bold] setpoints and wait instances for measurements.
• [bold]Check your browswer[/bold], a window to show data collection should appear!
   (Note, this may be reopened at any time with [bold]'f1'[/bold])
• [bold]Bindings are listed below.[/bold] Don't forget you can also press [bold]'ctrl+p'[/bold] to
    show useful info!
        """

        yield Vertical(
            Center(Label(TITLE)),
            Label(INFO),
            Container(Label(f"Version: [bold]{VERSION}[/bold] {" "*8} Press [bold]'ESC'[/bold] to close this dialog."), id="center-middle"),
            id="splash"
        )

class ManualConnectionDialog(ModalScreen):
    BINDINGS = [("escape", "app.pop_screen", "Cancel")]

    def compose(self) -> ComposeResult:
        with Container(classes="dialog") as container:
            with Horizontal(classes="container-fill-horizontal"):
                yield Select(options=[("Keithley", "keithley"), ("Lakeshore", "lakeshore"), ("Cryomagnetics Model 4G", "cryomagnetics4g")], id="instrument-type", classes="inline")
                yield Input(placeholder="Address", id="instrument-address", classes="inline")
            with Horizontal(classes="confirmation"):
                yield Button("Cancel", variant="primary", id="cancel")
                yield Button("Confirm", variant="primary", id="confirm")
            container.border_title = "[bold]Manual Connection"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle the pressed event for buttons on this screen."""
        handlers = {
            "cancel": lambda: self.app.pop_screen,
            "confirm": self.connect_instrument(self.query_one("#instrument-type", Select).value, self.query_one("#instrument-address", Input).value),
        }

        handler = handlers.get(str(event.button.id))
        if handler:
            handler()

    def connect_instrument(self, instrument_type: str, instrument_address: str, simulated_override: bool = True) -> None:
        """Connect to an instrument and update the connected instruments list. """
        # TODO: need to prompt for an instrument name here
        # Do the connection procses here- right now it just tries the auto-connect, but we will later handle manual connections here

        if simulated_override: 
            new_instrument = auto_connect_instrument(name=f"simulated_{instrument_type}", address=instrument_address)
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


class InstrumentsScreen(Screen):
    """Everything that will be displayed on the "Instruments" Tab."""

    BINDINGS = [("m", "app.push_screen('manual_connection_dialog')", "Manual Connection")]

    def compose(self) -> ComposeResult:
        self.detected_instrument_list: OptionList = OptionList(*self.app.state.detected_instruments)
        self.connected_instrument_list: OptionList = OptionList(*self.app.state.connected_instruments)

        yield Header()
        with HorizontalGroup(classes="short-container"):
            with VerticalScroll(id="detected-instruments") as container:
                yield self.detected_instrument_list
                container.border_title = "[bold]Detected Instruments"
            with VerticalScroll(id="connected-instruments") as container:
                yield self.connected_instrument_list
                container.border_title = "[bold]Connected Instruments"
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

    def connect_instrument(self, instrument_address: str, simulated_override: bool = False) -> None:
        """Connect to an instrument and update the connected instruments list."""
        # TODO: need to prompt for an instrument name here
        # Do the connection procses here- right now it just tries the auto-connect, but we will later handle manual connections here
        if self.app.simulated_mode or simulated_override: 
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
                
    async def on_screen_resume(self) -> None:
        """Handle the ScreenResume event."""

        # Refresh the connected instruments when the screen is reloaded.
        self.connected_instrument_list.clear_options()
        for instrument in self.app.state.connected_instruments:
            self.connected_instrument_list.add_option(instrument.name)
