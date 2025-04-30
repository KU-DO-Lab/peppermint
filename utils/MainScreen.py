from textual.screen import Screen
from utils.util import *
from textual import on
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Header, Label, Button, ListView

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
                yield ListView(*self.app.state.connected_instruments)

    @on(Button.Pressed, "#isnt_button")
    def inst_button(self):
        self.app.push_screen("instrument_screen")

    @on(Button.Pressed, "#param_button")
    def param_button(self):
        self.app.push_screen("parameter_screen")

    @on(Button.Pressed, "#temp_button")
    def temp_button(self):
        self.app.push_screen("temperature_screen")

    @on(Button.Pressed, "#exp_button")
    def exp_button(self):
        self.app.push_screen("electronic_measurements_screen")

    @on(Button.Pressed, "#settings_button")
    def settings_button(self):
        self.app.push_screen("settings_screen")

