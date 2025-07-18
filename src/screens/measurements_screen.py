from ctypes import cast
from typing import Dict
from qcodes.dataset import Measurement
from qcodes.instrument import VisaInstrument
from textual import on
from textual.app import ComposeResult
from textual.containers import Center, Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Collapsible, Footer, Header, Input, ListItem, ListView, Rule, Select, Static, Button
from textual.widgets import Input, Select, ListView

from drivers.Keithley_2450 import Keithley2450
from drivers.M4G_qcodes_official import CryomagneticsModel4G
from util import safe_query_value
from sweep1d import Sweep1D
from action_sequence import ActionSequence
import datetime

class SweepSequenceItem(ListItem):
    """Widget and runner implementation for a sweep.

    Displays as an entry in the rightmost column of the screen. This is responsible for:
    (1) Returning and the widget to be rendered
    (2) Handling reactive changes to the widget, including color changes to indicate run status
    (3) Handling the sweep for the objects contained in the widget: e.g. some outer function loops 
    over each sweep to be called down the list by making calls to this class.

    Currently takes Sweep1D objects, which are slated to be replaced with generic sweeps in the future.
    """
    def __init__(self, sweep: Sweep1D) -> None:
        super().__init__()
        self.sweep: Sweep1D = sweep
        self.active: bool = False

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(f"Sweep1D(name={self.sweep._instrument.name}, param={self.sweep._parameter}, start={self.sweep._start_val}, stop={self.sweep._stop_val}, step={self.sweep._step_count})"),
            classes="inline"
        )

class SweepCreatorItem(Collapsible):
    def __init__(self) -> None:
        super().__init__()
        self.instruments = self.app.state.connected_instruments
        self.select_options = [(instr.name, instr) for instr in self.instruments]
        self.main_horizontal = Horizontal(classes="container-horizontal-fill") # Contains fields to configure sweep

    def compose(self) -> ComposeResult:
            yield self.main_horizontal

    async def on_screen_resume(self) -> None:
        """Handle the ScreenResume event."""
        self.instruments: list[VisaInstrument] = self.app.state.connected_instruments
        # Update select options if the select already exists
        try:
            instrument_select = self.query_one("#instrument-field", Select)
            instrument_select.set_options([(instr.name, instr) for instr in self.instruments])
        except:
            # Select doesn't exist yet, will be created in initial setup
            pass

    async def clear_and_setup_widgets(self, widgets_to_add):
        """Helper method to clear parameter widgets and add new ones."""
        # Clear all widgets except the instrument select
        ignored_ids = ["instrument-field", "remove-sequence-item", "move-list-item-up", "move-list-item-down", "instrument-settings"]
        children_to_remove = []
        for child in self.main_horizontal.children:
            if child.id not in ignored_ids:
                children_to_remove.append(child)
        
        for child in children_to_remove:
            await child.remove()
        
        # Add the parameter-specific widgets
        for widget in widgets_to_add:
            self.main_horizontal.mount(widget)

    async def set_keithley_widgets(self) -> None:
        """Set up widgets for Keithley sweep configuration."""
        keithley_widgets = [
            Select(options=[("Voltage", "voltage"), ("Current", "current")], classes="inline", id="parameter-field"),
            Input(placeholder="Start", value="1", type="number", classes="inline", id="start-field"),
            Input(placeholder="Stop", value="0", type="number", classes="inline", id="stop-field"),
            Input(placeholder="# Steps", value="50", type="number", classes="inline", id="step-field")
        ]
        await self.clear_and_setup_widgets(keithley_widgets)

    async def set_cryomagneticsm4g_widgets(self) -> None:
        """Set up widgets for CryomagneticsM4G sweep configuration."""
        m4g_widgets = [
            Input(placeholder="Start", type="number", classes="inline", id="start-field"),
            Input(placeholder="Stop", type="number", classes="inline", id="stop-field"),
            Input(placeholder="Rate", type="number", classes="inline", id="rate-field")
        ]
        await self.clear_and_setup_widgets(m4g_widgets)

    def setup_initial_widgets(self) -> None:
        """Set up initial widgets (just the instrument select)."""
        self.main_horizontal.mount(
            Vertical(            
                Button("󰜷", classes="short", id="move-list-item-up"), 
                Button("-", classes="short", id="remove-list-item"),
                Button("󰜮", classes="short", id="move-list-item-down"), 
                classes="container-15",
                id="instrument-settings"
            ),
            Select(options=self.select_options, classes="inline", id="instrument-field"),
        )

    @on(Select.Changed)
    async def select_changed(self, event: Select.Changed) -> None:
        """Handle the select changed event."""
        if event.select.id == "instrument-field":
            handlers = {
                Keithley2450: self.set_keithley_widgets,
                CryomagneticsModel4G: self.set_cryomagneticsm4g_widgets,
            }

            handler = handlers.get(type(event.value))
            if handler:
                await handler()

    async def on_mount(self) -> None:
        """Set up initial widgets when the component mounts."""
        self.setup_initial_widgets()

class MeasurementsScreen(Screen):
    """UI for making a sequence of actions which will have data logging and plotting.

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
        self.experiments = {}
        self.measurements: Dict[str, Measurement] = {}
        date = datetime.datetime.now().strftime('%d.%b.%Y')
        self.table_name: str = self.app.state.datasaver.register_table(f"Measurement Test: {date}")

    def compose(self) -> ComposeResult:
        self.sweeps_configurator = ListView(id="action-creator-list")
        self.sweeps_sequence = ListView(id="sweep-sequence")

        yield Header()

        # Left: creator
        with Container(id="action-creator") as container:
            yield self.sweeps_configurator
            with Horizontal(classes="confirmation", id="sweep-creator-controls"):
                yield Button("Append to Sequence", classes="inline", id="append-sweep-to-sequence")
                yield Button("+", classes="inline", id="create-list-item")
            container.border_title = "[bold]Add Instruction"

        # Right sidebar
        with Container(classes="sidebar", id="measurement-sequence"):
            yield Center(Static("Sequence", classes="centered-subtitle"), classes="centered-widget")
            yield self.sweeps_sequence
            with Horizontal(classes="confirmation"):
                yield Button("Save!")
                yield Button("Start Sequence", id="start-sequence")
                yield Button("-", classes="inline-right", id="remove-sequence-item")

        yield Footer()
        
    def create_list_item(self) -> None:
        """Add an entry to the sweep configuration column."""
        self.sweeps_configurator.mount(SweepCreatorItem())

    def remove_list_item(self, widget: SweepCreatorItem | None) -> None:
        """Remove an entry from the sweep configuration column."""
        if widget:
            widget.remove()

    def move_list_item_up(self, widget: SweepCreatorItem | None) -> None:
        """Moves a list item up in the sequence."""
        if not widget:
            return 
        ...

    def move_list_item_down(self, widget: SweepCreatorItem | None) -> None:
        """Moves a list item up in the sequence."""
        if not widget:
            return 
        ...

    def remove_sequence_item(self) -> None:
        """Remove an entry from the sequence column."""
        idx = self.sweeps_sequence.index # selected idx
        self.sweeps_sequence.pop(idx) # remove it


    def append_sweep_to_sequence(self) -> None:
        """Turn each item in the list into a single sweep and add it to the list."""
        try:
            children = self.query_one("#action-creator-list", ListView).children
            for i, child in enumerate(children):
                instrument = safe_query_value(child, "#instrument-field", Select)
                parameter = safe_query_value(child, "#parameter-field", Select)
                start = safe_query_value(child, "#start-field", Input)
                stop = safe_query_value(child, "#stop-field", Input)
                step = safe_query_value(child, "#step-field", Input)
                rate = safe_query_value(child, "#rate-field", Input)

                if not (instrument and start and stop):
                    continue  # Required fields missing

                try:
                    start_val = float(start)
                    stop_val = float(stop)
                    step_val = int(step) if step else None
                    rate_val = float(rate) if rate else None
                except ValueError:
                    self.notify(f"Invalid number in sweep fields (item {i+1})")
                    continue

                match instrument:
                    case Keithley2450():
                        if not (parameter and step_val is not None):
                            continue
                        sweep = Sweep1D(
                            datasaver=self.app.state.datasaver,
                            plot_manager=self.app.state.plot_manager,
                            table_name=self.table_name,
                            instrument=instrument,
                            parameter=parameter,
                            start_val=start_val,
                            stop_val=stop_val,
                            step_val=step_val
                        )
                    case CryomagneticsModel4G():
                        if rate_val is None:
                            continue
                        sweep = Sweep1D(
                            datasaver=self.app.state.datasaver,
                            plot_manager=self.app.state.plot_manager,
                            table_name=self.table_name,
                            instrument=instrument,
                            start_val=start_val,
                            stop_val=stop_val,
                            rate=rate_val
                        )
                    case _:
                        sweep = None

                if sweep:
                    self.sweeps_sequence.append(SweepSequenceItem(sweep))

        except Exception as e:
            self.notify(f"Error: {e}")
            return

        self.sweeps_configurator.clear()

    def start_sequence(self) -> None:
        """Extract action object (sweep, set) from the elements in the sequence and start the runner."""
        actions = [fn.sweep for fn in self.sweeps_sequence.children]
        runner = ActionSequence(actions)
        runner.start()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle the pressed event for buttons on this screen."""
        handlers = {
            "create-list-item": self.create_list_item,
            "remove-list-item": self.remove_list_item,
            "move-list-item-up" : self.move_list_item_up,
            "move-list-item-down" : self.move_list_item_down,
            "append-sweep-to-sequence": self.append_sweep_to_sequence,
            "remove-sequence-item": self.remove_sequence_item,
            "start-sequence": self.start_sequence,
            "configure-save": lambda: self.app.push_screen('configure_save_dialog'),
        }

        widget: SweepCreatorItem | None = next(
            (elm for elm in event.button.ancestors if isinstance(elm, SweepCreatorItem)), 
            None
        )
        
        # hacky implementation to pass the widget if the handler needs it (sweep creator items), otherwise call normally
        handler = handlers.get(str(event.button.id))
        if handler:
            try:
                handler(widget)
            except:
                handler()
