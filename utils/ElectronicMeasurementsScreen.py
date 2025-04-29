from typing import Any, Dict
from qcodes.dataset import Measurement
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Footer, Header, ListItem, ListView, Rule, Select, Static, Button

from utils.drivers.Keithley_2450 import Keithley2450

class ParameterListItem(ListItem):
    def __init__(self) -> None:
        self.sweep_type = "Outer"
        self.available_write_parameters = self.app.state.write_parameters

    def on_mount(self):
        yield ListItem(
            Static(self.sweep_type), Select(options=self.available_write_parameters)
        )

class ElectronicMeasurementsScreen(Screen):
    # BINDINGS = [("escape", "app.pop_screen", "Pop screen")]

    def __init__(self) -> None:
        super().__init__()
        allowed_SMUs = [Keithley2450]
        connected_SMUs = []
        self.experiments = {}
        self.measurements: Dict[str, Measurement] = {}
        self.datasavers: Dict[str, Any] = {}

    def compose(self) -> ComposeResult:

        self.user_sweeps_table = ListView(
            ListItem(Static("A name:"), Static("Sweep1D()")),
            classes="info"
        )

        yield Header()
        yield Horizontal(

            # Left side info
            Vertical(
                Static("Sweep Creator", classes="label"),
                ListView(
                    # ParameterListItem()
                ),
                Button("Go!", id="create-sweep", classes="confirmation"),
                id="sweep-creator"
            ),

            # Right side information
            Vertical(
                Vertical(Static("Sweeps", classes="centered-subtitle"), classes="centered-widget"),
                Horizontal(self.user_sweeps_table, classes="accent-container"),
                Rule(),
                # Horizontal(Button("", classes="right-aligned-widget", id="refresh-stats-button"), classes="right-aligned-widget"),
                id="temperature-controller-status",
            ),
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle the pressed event for buttons on this screen."""
        handlers = {
            "create-sweep": None
        }

        handler = handlers.get(str(event.button.id))
        if handler:
            handler()
