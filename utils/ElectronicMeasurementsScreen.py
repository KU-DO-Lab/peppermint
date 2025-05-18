from typing import Any, Dict
from qcodes.dataset import Measurement
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Footer, Header, Input, ListItem, ListView, Rule, Select, Static, Button

from utils.drivers.Keithley_2450 import Keithley2450
from utils.util import Sweep1D

class SweepSequenceItem(ListItem):
    def __init__(self) -> None:
        super().__init__()
        ...

class SweepCreatorItem(ListItem):
    def __init__(self) -> None:
        super().__init__()
        self.instruments = self.app.state.connected_instruments # must turn this into a select later
        print(self.instruments)

    def compose(self) -> ComposeResult:
        yield Vertical(
            # Select(options=self.instruments),
            Horizontal( 
                Select(options=[("Voltage", 1)], classes="inline-select"), 
                Input(placeholder="Start", type="number", classes="input-field", id="start-field"), 
                Input(placeholder="Stop", type="number", classes="input-field", id="stop-field"), 
                Input(placeholder="Step", type="number", classes="input-field", id="step-field"), 
                classes="sweep-info"
            ),
            classes="short-listitem"
        )

    def on_mount(self) -> None:
        print(self.app.state.connected_instruments)
        select = self.query_one(Select)

class ElectronicMeasurementsScreen(Screen):
    """UI for making a sequence of actions.

    Currently this represents sweeps. The sweeps menu is meant to be very broad and expandable. It has two parts:
    (1) The left column begins as an empty list to which a new entry can be added. Each entry represents a sweep 1D. 
        I am not sure how to make this clear yet, but this is how multi-parameter sweeps are implemented. Imagine 
        the first parameter stepping once, sweeping the second parameter, then repeating. Often only one or two parameters 
        will need to be added.
    (2) The right column is a sequence of events, going downwards in order from top to bottom. In the future, we will plan 
        to expand beyond sweeps and allow parameters to be sent to the sequence too.
    """

    def __init__(self) -> None:
        super().__init__()
        allowed_SMUs = [Keithley2450]
        connected_SMUs = []
        self.experiments = {}
        self.measurements: Dict[str, Measurement] = {}
        self.datasavers: Dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        self.sweeps_configurator = ListView(classes="outlined-container-fill-horizontal", id="sweep-info")
        self.sweeps_sequence = ListView(
            ListItem(Static("A name:"), Static("Sweep1D()")),
            classes="info"
        )

        yield Header()
        yield Horizontal(

            # Left side info
            Vertical(
                Static("Sweep Creator", classes="label"),
                self.sweeps_configurator,
                Horizontal(
                    Button("Append to Sequence", classes="inline-left", id="append-sweep-to-sequence"),
                    Button("+", classes="inline-right", id="create-list-item"),
                    Button("-", classes="inline-right", id="remove-list-item"),
                    classes="container-fill-horizontal",
                ),
                id="sweep-creator" 
            ),

            # Right side information
            Vertical(
                Vertical(Static("Sweeps", classes="centered-subtitle"), classes="centered-widget"),
                Horizontal(self.sweeps_sequence, classes="accent-container"),
                Rule(),
                id="measurement-sequence",
            ),
        )
        yield Footer()

    def create_list_item(self) -> None:
        """Append a new sweep widget to the configuration column"""
        self.sweeps_configurator.append(SweepCreatorItem())

    def remove_list_item(self) -> None:
        """Append a new sweep widget to the configuration column"""
        idx = self.sweeps_configurator.index # selected idx
        self.sweeps_configurator.pop(idx) # remove it

    def append_sweep_to_sequence(self) -> None:
        """Turn each item in the list into a single sweep and add it to the list."""
        children = self.query_one("#sweep-info", ListView).children
        for (i, child) in enumerate(children):
            start = child.query_one("#start-field", Input).value
            stop = child.query_one("#stop-field", Input).value
            step = child.query_one("#step-field", Input).value

            # only implemented sweep1D atm, will upgrade to a generic later
            # Sweep1D()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle the pressed event for buttons on this screen."""
        handlers = {
            "create-list-item": self.create_list_item,
            "remove-list-item": self.remove_list_item,
            "append-sweep-to-sequence": self.append_sweep_to_sequence,
        }

        handler = handlers.get(str(event.button.id))
        if handler:
            handler()
