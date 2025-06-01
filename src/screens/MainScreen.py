from textual.screen import Screen
from util import *
from textual import on
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Footer, Header, Label, Button, ListView, OptionList

class MainScreen(Screen):


    def compose(self) -> ComposeResult:
        self.title = "Peppermint"
        self.sub_title = "Cryogenics Measurement Suite"
        self.connected_instrument_list: OptionList = OptionList(*self.app.state.connected_instruments)  # Start empty

        yield Header(show_clock=True)
        with Container(id="main-menu-grid"):
            with Container(id="left-pane", classes="outlined-container-horizontal-fill"):
                yield Button("Instruments", id="isnt_button", classes="container-horizontal-fill")
                yield Button("Parameters", id="param_button", classes="container-horizontal-fill")
                yield Button("Temperature", id="temp_button", classes="container-horizontal-fill")
                yield Button("Measurements", id="exp_button", classes="container-horizontal-fill")
                yield Button("Settings", id="settings_button", classes="container-horizontal-fill")
            with Container(id="inst-list", classes="sidebar"):
                yield Label("Connected Instruments")
                yield self.connected_instrument_list
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "inst_button": lambda: self.app.push_screen("instrument_screen"),
            "param_button": lambda: self.app.push_screen("parameter_screen"),
            "temp_button": lambda: self.app.push_screen("temperature_screen"), 
            "meas_button": lambda: self.app.push_screen("electronic_measurements_screen"), 
            "settings_button": lambda: self.app.push_screen("settings_screen")
        }

        handler = handlers.get(str(event.button.id))
        if handler:
            handler()

    async def on_screen_resume(self) -> None:
        """Handle the ScreenResume event."""

        # Refresh the connected instruments when the screen is reloaded.
        self.connected_instrument_list.clear_options()
        for instrument in self.app.state.connected_instruments:
            self.connected_instrument_list.add_option(instrument.name)
