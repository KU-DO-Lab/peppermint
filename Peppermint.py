import os
import logging
from numpy._core.numerictypes import floating
import pyvisa
import argparse
import numpy as np
import asyncio

from utils.drivers.Lakeshore_336 import LakeshoreModel336CurrentSource
from utils.util import *
from typing import Any, Dict, Generic, Optional
from dataclasses import dataclass
from qcodes.dataset import Measurement, initialise_or_create_database_at, load_or_create_experiment
from qcodes.parameters import GroupParameter, Parameter, ParameterBase
from qcodes.instrument import VisaInstrument
from textual import on
from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.screen import Screen, ModalScreen
from textual.containers import Horizontal, Vertical, Grid, Container
from textual.widgets import Footer, Header, RadioButton, RadioSet, Rule, Static, Label, TabbedContent, TabPane, OptionList, Select, Button, Placeholder, ListView, ListItem, Collapsible, Pretty, TextArea


@dataclass
class SharedState():
    """Class for keeping track of the state of the application."""
    def __init__(self):
        super().__init__()  # must be super init-ed for reactivity.
        detected_instruments: reactive[list[str]] = reactive(list) 
        connected_instruments: reactive[list[VisaInstrument]] = reactive(list) 
        read_parameters: reactive[list[Parameter]] = reactive(list)
        write_parameters: reactive[list[Parameter]] = reactive(list)
        database_path: str = ""

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
        """Handle instrument selection from the detected instruments list."""
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


class ParametersScreen(Screen):
    """Everything that will be displayed on the "Parameters" Tab."""

    BINDINGS = [
        ("r", "set_parameter_read", "Set Read Param"),
        ("w", "set_parameter_write", "Set Write Param"),
    ]

    def compose(self) -> ComposeResult: 
        yield Header()
        instrument_options: list[tuple[str, str]] = [(instrument.name, instrument.name) for instrument in self.app.state.connected_instruments]
        self.connected_instrument_list = Select[str](options=instrument_options)
        self.available_parameters: ListView = ListView()
        self.read_parameters: ListView = ListView()
        self.write_parameters: ListView = ListView()
        yield Horizontal(
            Vertical(
                Label("Read Parameters"), self.read_parameters
            ),
            Vertical(
                Label("Connected Instruments"), self.connected_instrument_list,
                Label("Available Parameters"), self.available_parameters
            ),
            Vertical(
                Label("Set Parameters"), self.write_parameters
            ))
        yield Footer()

    async def on_screen_resume(self) -> None:
        """Handle the ScreenResume event."""
        # Perform some action when the screen is resumed
        self.connected_instrument_list.clear()
        self.instrument_options: list[tuple[str, str]] = [(instrument.name, instrument.name) for instrument in self.app.state.connected_instruments]
        self.connected_instrument_list.set_options(self.instrument_options)

    @on(Select.Changed)
    def handle_parameter_instrument_changed(self, event: Select.Changed) -> None:
        """Fetch the new parameters for an instrument when that instrument is changed."""

        # Grab the actual instrument object from the name of the instrument in the select menu
        selected_instrument: Optional[VisaInstrument] = next(
            (inst for inst in self.app.state.connected_instruments if inst.name == self.connected_instrument_list.value),
            None  # If for whatever reason an instrument can't be found this is set to none
        )

        if selected_instrument is None:
            return

        self.available_parameters.clear()  
        self.read_parameters.clear()  
        self.write_parameters.clear()  
        for key, p in selected_instrument.parameters.items():
            if p in self.app.state.read_parameters:
                self.available_parameters.append(ListItem(Static(p.full_name, classes="read")))
                self.action_set_parameter_read(provided_param=p.full_name)
            elif p in self.app.state.write_parameters:
                self.available_parameters.append(ListItem(Static(p.full_name, classes="write")))
                self.action_set_parameter_write(provided_param=p.full_name)
            else:
                self.available_parameters.append(ListItem(Static(p.full_name)))
        for name, submodule in selected_instrument.submodules.items():
            if hasattr(submodule, 'parameters'):
                for key, p in submodule.parameters.items():
                    # self.available_parameters.append(ListItem(Static(p.full_name)))
                    if p in self.app.state.read_parameters:
                        self.available_parameters.append(ListItem(Static(p.full_name, classes="read")))
                        self.action_set_parameter_read(provided_param=p.full_name)
                    elif p in self.app.state.write_parameters:
                        self.available_parameters.append(ListItem(Static(p.full_name, classes="write")))
                        self.action_set_parameter_write(provided_param=p.full_name)
                    else:
                        self.available_parameters.append(ListItem(Static(p.full_name)))

    def action_set_parameter_read(self, provided_param: Optional[str]=None) -> None:
        """Sets parameter to active read mode, appending it to the list of reading parameters if it is not yet there."""

        selected: ListItem | None = self.available_parameters.highlighted_child

        if not provided_param:
            if not selected or "read" in selected.classes or "write" in selected.classes:
                self.notify("Already reading/writing parameter" if selected else "No parameter selected")
                return

        try:
            if provided_param:
                full_param_name: str = provided_param
            else:
                full_param_name: str = str(selected.children[0].render()._renderable) # type: ignore

            instrument: Optional[VisaInstrument] = next(
                inst for inst in self.app.state.connected_instruments 
                if inst.name == self.connected_instrument_list.value
            )

            if instrument:
                stripped_param_name: str = str(full_param_name)[len(instrument.name) + 1:]
            else:
                raise ValueError("No instrument selected")

            # It's necessary to search submodules a majority of the time, so this loop iterates through the available 
            # submodules, trying to find if one matches. Any parameter will be named as "submodule_parameter", 
            # so this should work, at least for qcodes devices
            submodule_name = None
            for sub_name in instrument.submodules:
                if stripped_param_name.startswith(f"{sub_name}_"):
                    submodule_name = sub_name
                    break

            if submodule_name: 
                doubly_stripped_param_name: str = str(stripped_param_name)[len(submodule_name) + 1:]
                submodule = instrument.submodules[submodule_name]
                param: GroupParameter | ParameterBase = submodule.parameters[doubly_stripped_param_name]
            else:
                param: GroupParameter | ParameterBase = instrument.parameters[stripped_param_name]

            if not param.gettable:
                self.notify("parameter is not writeable!")
                return
            
            if selected:
                selected.add_class("read")

            if param not in self.app.state.read_parameters:
                self.app.state.read_parameters.append(param) # in case the parameter needs to be accessed in a database

            # self.read_parameters.append(ListItem(ParameterWidget(param)))
            self.read_parameters.append(ListItem(Collapsible(
                Pretty(param.get()), 
                classes="parameter_entry",
                title=full_param_name,
            ))) # Fallback, idk why the widget version is broken

        except (AttributeError, IndexError):
            self.notify("Invalid parameter widget structure")
        except StopIteration:
            self.notify("No instrument selected")
        except Exception as e:
            self.notify(f"Error: {str(e)}")

    def action_set_parameter_write(self, provided_param=None) -> None:
        """
        Assign the parameter active write mode.

        TODO: switching back-forth from read/write, set experiment
        """
        selected: ListItem | None = self.available_parameters.highlighted_child
        
        if not provided_param:
            if not selected or "read" in selected.classes or "write" in selected.classes:
                self.notify("Already reading/writing parameter" if selected else "No parameter selected")
                return

        try:
            if provided_param:
                full_param_name = provided_param
            else:
                full_param_name: str = str(selected.children[0].render()._renderable) # type: ignore

            instrument: Optional[VisaInstrument] = next(
                inst for inst in self.app.state.connected_instruments 
                if inst.name == self.connected_instrument_list.value
            )

            if instrument:
                stripped_param_name: str = str(full_param_name)[len(instrument.name) + 1:]
            else:
                raise ValueError("No instrument selected")

            # It's necessary to search submodules a majority of the time, so this loop iterates through the available 
            # submodules, trying to find if one matches. Any parameter will be named as "submodule_parameter", 
            # so this should work, at least for qcodes devices
            submodule_name = None
            for sub_name in instrument.submodules:
                if stripped_param_name.startswith(f"{sub_name}_"):
                    submodule_name = sub_name
                    break
            if submodule_name: 
                doubly_stripped_param_name: str = str(stripped_param_name)[len(submodule_name) + 1:]
                submodule = instrument.submodules[submodule_name]
                param: GroupParameter | ParameterBase = submodule.parameters[doubly_stripped_param_name]
            else:
                param: GroupParameter | ParameterBase = instrument.parameters[stripped_param_name]

            if not param.settable:
                self.notify("parameter is not writeable!")
                return 

            if selected:
                selected.add_class("write")

            self.app.state.write_parameters.append(param) # in case the parameter needs to be accessed in a database
            # self.write_parameters.append(ListItem(ParameterWidget(param, readonly=False)))
            self.write_parameters.append(ListItem(Collapsible(
                Pretty(param.get()), 
                classes="parameter_entry",
                title=full_param_name,
            ))) # Fallback, idk why the widget version is broken

        except (AttributeError, IndexError):
            self.notify("Invalid parameter widget structure")
        except StopIteration:
            self.notify("No instrument selected")
        except Exception as e:
            self.notify(f"Error: {str(e)}")

class TemperatureScreen(Screen):
    """The screen containing information related to the temperature controllers."""

    BINDINGS = [
        ("u", "initialize_plot", "Open Plot"),
        # ("s", "setpoint", "Adjust Setpoint"),
    ] 

    def __init__(self):
        super().__init__()
        self.polling_interval = 4
        self.update_timer = None
        self.active_channel = None
        self.is_dragging = False
        self.is_sweeping = False
 
        self.experiments = {}
        self.measurements: Dict[str, Measurement] = {}
        self.datasavers: Dict[str, Any] = {}
        self.stats_buffer: Dict[str, Dict[str, Any]] = {} # we might want to run continuous statistics over a range of data.
        
        self.chA_temperature_widget = Static("N/A", id="channel_A", classes="inline-label")
        self.chB_temperature_widget = Static("N/A", id="channel_B", classes="inline-label")
        self.chC_temperature_widget = Static("N/A", id="channel_C", classes="inline-label")
        self.chD_temperature_widget = Static("N/A", id="channel_D", classes="inline-label")

        # Channel widget mappings
        # C and D are disabled for now since they don't output anything on our system.
        # We really want a switch to enable or disable them.
        self.channel_widgets = {
            'A': self.chA_temperature_widget,
            'B': self.chB_temperature_widget,
            # 'C': self.chC_temperature_widget,
            # 'D': self.chD_temperature_widget
        }
        
        # Initialize experiments for each channel
        for channel in list(self.channel_widgets.keys()): # [A,B,C,D]
            exp_name = f"Temperature_Channel_{channel}"
            self.experiments[channel] = load_or_create_experiment(
                experiment_name=exp_name,
                sample_name="Lakeshore Auto Monitor"
            )

        self.plotter = SimpleLivePlotter(
            channels=list(self.channel_widgets.keys()),
            title="Automated Temperature Monitor",
            xlabel="time (s)",
            ylabel="temperature (k)",
            use_timestamps=True,
        )

            
    def compose(self) -> ComposeResult:
        """Define all widgets for this screen."""
        self.allowed_monitor_types = (LakeshoreModel336)
        self.allowed_temperature_monitors = [inst for inst in self.app.state.connected_instruments if isinstance(inst, self.allowed_monitor_types)]
        self.instrument_options: list[tuple[str, str]] = [(instrument.name, instrument.name) for instrument in self.allowed_temperature_monitors]

        self.heater_mode = RadioSet(
            RadioButton("off", value=True), 
            RadioButton("closed_loop", tooltip="feedback loop (automatic)"), 
            RadioButton("open_loop", tooltip="no feedback loop (manual)"),
            # RadioButton("zone", tooltip="Not yet implemented", disabled=True),
            id="heater-mode",
        )

        self.output_range = RadioSet(
            RadioButton("off", value=True), 
            RadioButton("low"), 
            RadioButton("medium"), 
            RadioButton("high"),
            id="output-range",
        )

        self.status_table = ListView(
            ListItem(Horizontal(Static("Channel A: ", classes="inline-label"), self.chA_temperature_widget, classes="container"), classes="inline-label", id="listitem-A"),
            ListItem(Horizontal(Static("Channel B: ", classes="inline-label"), self.chB_temperature_widget, classes="container"), classes="inline-label", id="listitem-B"),
            ListItem(Horizontal(Static("Channel C: ", classes="inline-label"), self.chC_temperature_widget, classes="container"), classes="inline-label", id="listitem-C"),
            ListItem(Horizontal(Static("Channel D: ", classes="inline-label"), self.chD_temperature_widget, classes="container"), classes="inline-label", id="listitem-D"),
            classes="info"
        )

        yield Header()
        with TabbedContent("Working", "Experimental"):
            yield Horizontal(
                # Left side controller settings
                Vertical(
                    Horizontal(
                        Button("", tooltip="Heater range settings. Heater mode can be set to closed loop or open loop which have different purposes:\n\n1. Open loop: for PID-controlled setpoint magic.\n2. Closed loop: for pushing a constant current through the heating element.", disabled=True, classes="tooltip"),
                        Vertical( Static("Heater Mode:    ", classes="label"), self.heater_mode, id="heater-mode-container" ),
                        Vertical( Static("Output Range:    ", classes="label"), self.output_range, id="output-range-container" ),
                        classes="temperature-controller-controls",
                    ),

                    Vertical( 
                        Button("", tooltip="PID values for the heating element's setpoint control. If the heater never stabilizes, adjust P. If the heater never reaches the setpoint raise I by double. If it instead  oscillates about it for too long, lower by a half. Raising and lowering D may help it get to the setpoint faster. Manual output forcibly sets the heater output % without regard for setpoint.", disabled=True, classes="tooltip"),
                        Static("PID:", classes="label"), 
                        Horizontal(Static("P:", classes="label"), Input(placeholder="...", type="number", classes="input-field", id="P"), classes="container"), 
                        Horizontal(Static("I:", classes="label"), Input(placeholder="...", type="number", classes="input-field", id="I"), classes="container"), 
                        Horizontal(Static("D:", classes="label"), Input(placeholder="...", type="number", classes="input-field", id="D"), classes="container"), 
                        Horizontal(Static("Manual Output:", classes="label"), Input(placeholder="...", type="number", classes="input-field", id="manual-output"), classes="container"), 
                        id="PID-container", 
                        classes="outlined-container" 
                    ),

                    Horizontal( 
                        Button("", tooltip="Go to a setpoint! Only works in closed loop mode.", disabled=True, classes="tooltip"),
                        Static("Setpoint:", classes="label"), Input(placeholder="...", disabled=False, type="number", classes="input-field", id="setpoint-field"), # need to check enabled on screen change, Static("(K)", classes="label"),
                        Button("Confirm!", id="setpoint-start", classes="confirmation"),
                        classes="temperature-controller-controls",
                    ),
                    classes="container"
                ),

                Vertical(
                    Button("", tooltip="For maintaining a gentle ascent/descent at a fixed rate.\n\nCurrently requires supervision to change output ranges AND watch over 'I' since different ranges may demand higher/lower values", disabled=True, classes="tooltip"),
                    Static("Setpoint Dragging:", classes="inline-label"), 
                    Horizontal(
                        Static("Target Rate", classes="label"), 
                        Input(placeholder="...", type="number", classes="input-field", id="setpoint-dragging-rate-field"), 
                        classes="container"
                    ),
                    Horizontal(
                        Horizontal(Static("P:", classes="label"), Input(placeholder="20", type="number", classes="input-field", id="dragging-p-field"), classes="container"),
                        Horizontal(Static("I:", classes="label"), Input(placeholder="1e-4", type="number", classes="input-field", id="dragging-i-field"), classes="container"),
                        Horizontal(Static("D:", classes="label"), Input(placeholder="10", type="number", classes="input-field", id="dragging-d-field"), classes="container"),
                        classes="container"
                    ),
                    Horizontal(
                        Button("Go!", id="setpoint-dragging-start", classes="confirmation"),
                        Button("Stop!", id="setpoint-dragging-stop", classes="confirmation"),
                        classes="container"
                    ),
                    classes="outlined-container",
                ),


                # Right side information
                Vertical(
                    Container(Static("Information", classes="centered-subtitle"), classes="centered-widget"),
                    Horizontal(Static("Active Channel:", classes="label"), self.status_table, classes="accent-container"),

                    Rule(),

                    Horizontal(Static("Output %:", classes="label"), Static("...", id="output-percentage", classes="label"), classes="accent-container"),
                    Horizontal(Static("Mean:", classes="label"), Static("N/A", id="stats-mean", classes="label"), classes="accent-container"),
                    Horizontal(Static("Std:", classes="label"), Static("N/A", id="stats-std", classes="label"), classes="accent-container"),
                    Horizontal(Static("Gradient:", classes="label"), Static("N/A", id="stats-gradient", classes="label"), classes="accent-container"),
                    Horizontal(Static("Acceleration:", classes="label"), Static("N/A", id="stats-acceleration", classes="label"), classes="accent-container"),
                    Horizontal(Static("Output Variation:", classes="label"), Static("N/A", id="stats-output-variation", classes="label"), classes="accent-container"),
                    
                    Horizontal(Button("", classes="right-aligned-widget", id="refresh-stats-button"), classes="right-aligned-widget"),
                    id="temperature-controller-status",
                ), classes="container"
            )

            yield Container(
                Vertical(
                    Static("Sweep", classes="centered-subtitle"),
                            Horizontal(Static("Setpoints:", classes="label"), TextArea.code_editor("2, 5, 10, 20, 40", language="python", show_line_numbers=False, id="sweep-setpoints-field", classes="input-field"), classes="container"),
                            Horizontal(Static("Action at Setpoint:", classes="label"), TextArea.code_editor("print('Hello!'), print(World!)", language="python", show_line_numbers=False, id="sweep-actions-field", classes="input-field"), classes="container"),
                        Button("Go!", id="start-sweep", classes="confirmation"),
                        classes="container"
                ),
                    classes="outlined-container"
            )

        yield Footer()

    def initialize_measurements(self) -> None:
        """Initialize separate measurements for each channel"""
        for param in self.app.state.read_parameters:
            if not (hasattr(param, 'name_parts') and param.name_parts[-1] == "temperature"):
                continue
                
            channel = param.name_parts[1]  # Extract channel label (A, B, C, D)
            
            # Create new measurement for this channel
            measurement = Measurement(self.experiments[channel])
            measurement.register_parameter(param)
            
            # Store measurement and create a new run (datasaver)
            # each channel has its own datasaver, I could not get it to operate well pushing everything to one.
            self.measurements[channel] = measurement
            self.datasavers[channel] = measurement.run().__enter__()
            
    def poll_temperature_controller(self) -> None:
        self.get_output_percentage()
        temperatures: Dict[str, float] = self.get_temperatures(self.fetch_gettable_channels_and_parameters)

        if self.is_sweeping:
            self.is_dragging = False # ensure that only one automated task with the controller is happening at once 

        if self.is_dragging:
            self.is_sweeping = False # ensure that only one automated task with the controller is happening at once 
            p = float(self.query_one("#dragging-p-field", Input).value)
            i = float(self.query_one("#dragging-i-field", Input).value)
            d = float(self.query_one("#dragging-d-field", Input).value)
            threshold: float = 1.0 # stop when within 1 degree
            target_gradient: float = float(self.query_one("#setpoint-dragging-rate-field", Input).value)
            stop: float = float(self.query_one("#setpoint-dragging-stop-field", Input).value)
            setp = self.guess_next_setpoint_for_dragging(threshold=threshold, stop=stop, target_gradient=target_gradient, p=p, i=i, d=d)

            print(f"Mean: {self.stats_buffer["A"]["mean"]}")
            print(f"Gradient: {self.stats_buffer["A"]["gradient"]}")
            print(f"Acceleration: {self.stats_buffer["A"]["acceleration"]}")
            print(f"Instantaneous Output Variation: {self.stats_buffer["A"]["output_variation"]}")
            print(f"Setpoint: {setp}")

            self.go_to_setpoint(setp)
        
    def get_output_percentage(self) -> None:
        if not self.allowed_temperature_monitors[0] or self.app.simulated_mode:
            return

        channel = self.get_channel()
        if not channel:
            return
        
        self.query_one("#output-percentage", Static).update(str(channel.output()))

    def fetch_gettable_channels_and_parameters(self) -> Dict[str, ParameterBase]:
        """Return the parameter to get each temperature from."""
        channels_to_get = {}
        for param in self.app.state.read_parameters:
            if not (hasattr(param, 'name_parts') and param.name_parts[-1] == "temperature"):
                continue

            channel = param.name_parts[1]  # Extract channel label (A, B, C, D)
            channels_to_get[channel] = param  # Map the channel label to the parameter
        
        return channels_to_get

    async def sweep_temperature(self, setpoints: Optional[list[float]] = [], actions: Optional[list[Any]] = []) -> None:
        """Start/Stop functionality for temperature sweeps."""
        print(f"starting sweep")
        try: 
            setpoint_input = str(self.query_one("#sweep-setpoints-field", TextArea).text).split(",")
            setpoints = list(map(float, setpoint_input))
            print(setpoints)
        except asyncio.CancelledError:
            print(f"sweeps are stopping")
        finally:
            print(f"sweeps finished")

    def get_temperatures(self, fetch_channels_function) -> Dict[str, float]:
        """Get and record temperatures for each channel."""

        data: Dict[str, float] = {}
        things_to_get: Dict[str, ParameterBase] = fetch_channels_function()

        for channel_name, param in things_to_get.items():
            # Update widget
            if channel_name in self.channel_widgets:
                value = param.get()
                self.channel_widgets[channel_name].update(str(value))

                # Data to be returned
                data[channel_name] = value
                
                # Record data for this channel
                # Saved to the QCoDeS run which gets started when this screen is initialized.
                if channel_name in self.datasavers and self.datasavers[channel_name]:
                    self.datasavers[channel_name].add_result( (param, value) )

                # Update the plot
                if self.plotter:
                    current_time = time.time()
                    self.plotter.update(channel_name, x=current_time, y=value)

                # Update statistics
                if channel_name not in self.stats_buffer:
                    self.stats_buffer[channel_name] = {"raw_data": [], "mean": float("nan"), "std": float("nan"), "gradient": float("nan"), "acceleration": float("nan"), "sum": 0.0, "output_variation": 0.0}

                self.stats_buffer[channel_name]["raw_data"].append(value)
                self.get_statistics(channel_name)
                self.stats_buffer[channel_name].update(self.get_statistics(channel_name))

                # It's not very elegant, but we need the heater object to get the output of it.
                if not self.app.simulated_mode: # type: ignore
                    previous_output: float = float(self.query_one("#stats-output-variation", Static).children[0].render()._renderable)
                    heater_channel: LakeshoreModel336CurrentSource = self.get_channel()
                    self.stats_buffer[channel_name]["output_variation"].update(previous_output - heater_channel.output())

                # update the widgets on screen
                self.query_one("#stats-mean", Static).update(str(self.stats_buffer[channel_name]["mean"]))
                self.query_one("#stats-std", Static).update(str(self.stats_buffer[channel_name]["std"]))
                self.query_one("#stats-gradient", Static).update(str(self.stats_buffer[channel_name]["gradient"]))
                self.query_one("#stats-acceleration", Static).update(str(self.stats_buffer[channel_name]["acceleration"]))
                self.query_one("#stats-output-variation", Static).update(str(self.stats_buffer[channel_name]["output_variation"]))

        return data

    def get_statistics(self, channel: str) -> Dict[str, Any]:
        """Some very basic statistics running on some buffer of points from the temperature controller. It's worth noting this is limited by the resolution of collected data."""

        previous_gradient: np.float32 = self.stats_buffer[channel]["gradient"]

        mean: np.float32 = np.sqrt(np.mean(np.square(self.stats_buffer[channel]["raw_data"]))) if len(self.stats_buffer[channel]["raw_data"]) > 0 else np.floating("nan")
        std: np.float32 = np.std(self.stats_buffer[channel]["raw_data"]) if len(self.stats_buffer[channel]["raw_data"]) > 0 else np.floating("nan")
        sum: np.float32 = self.stats_buffer[channel]["sum"] + (self.stats_buffer[channel]["raw_data"][-1] if len(self.stats_buffer[channel]["raw_data"]) > 0 else 0.0)
        gradient: np.float32 = np.float32((self.stats_buffer[channel]["raw_data"][-1] - self.stats_buffer[channel]["raw_data"][-2]) * 1/self.polling_interval if len(self.stats_buffer[channel]["raw_data"]) > 1 else 0.0)
        acceleration: np.float32 = np.float32((gradient - previous_gradient) * 1/self.polling_interval)

        return {"std": std, "mean": mean, "gradient": gradient, "sum": sum, "acceleration": acceleration}

    async def on_screen_resume(self) -> None:
        """ 
        Handle the ScreenResume event. 
        Whenever the temperature screen is opened, we need to make sure every temperature monitor parameter is running. 
        """

        self.allowed_temperature_monitors = [inst for inst in self.app.state.connected_instruments if isinstance(inst, self.allowed_monitor_types)]

        if len(self.allowed_temperature_monitors) <= 0: 
            self.notify("please connect the Lakeshore 336!")
            return

        # this spits out a list of parameters, which have their name split as: "instrument, submodule, parameter"
        # for a lakeshore 336, it has channels/submodules ABCD. this will differ with other controllers
        required_submodules = set(self.channel_widgets.keys()) # [A,B,C,D]
        parameters: list[list[str]] | None = [param.name_parts for param in self.app.state.read_parameters]

        # Extract the labels for "temperature" parameters
        existing_labels = { param[1] for param in parameters if len(param) > 2 and param[-1] == "temperature" }
        missing_labels = required_submodules - existing_labels

        for label in missing_labels:
            submodule = self.allowed_temperature_monitors[0].submodules[label]
            param: GroupParameter | ParameterBase = submodule.parameters['temperature']
            self.app.state.read_parameters.append(param)
        
        self.active_channel = self.allowed_temperature_monitors[0].output_1 # set channel "A" active at the start
        self.initialize_measurements()
        self.populate_fields() # fields like PID, setpoint, heater mode need to be aquired and updated.
        self.start_temperature_polling()

    def populate_fields(self) -> None:
        """Fill in information to the submittable fields when the screen is booted up"""
        if not self.allowed_temperature_monitors[0]:
            return
        
        # if self.allowed_temperature_monitors[0].full_name == "simulated_lakeshore336":
        if self.app.simulated_mode:
            self.get_temperatures(self.fetch_gettable_channels_and_parameters)
            return

        channel = self.get_channel()
        if not channel:
            return

        # key/index dictionary for the heater mode and output range:
        # query a name and use this to pick the corresponding index of the radio set widget
        heater_modes = {"off": 0, "closed_loop": 1, "open_loop": 2, "zone": 3}
        output_ranges = {"off": 0, "low": 1, "medium": 2, "high": 3}

        # self.heater_mode.pressed_index = int(heater_modes[str(channel.mode)])
        # self.output_range.pressed_index = int()
        # self.output_range.Changed(self. output_range, )

        self.query_one("#P", Input).value = str(channel.P())
        self.query_one("#I", Input).value = str(channel.I())
        self.query_one("#D", Input).value = str(channel.D())
        self.query_one("#output-percentage", Static).update(str(channel.output()))
        self.query_one("#setpoint-field", Input).value = str(channel.setpoint())
        self.query_one("#manual-output", Input)
        
        self.get_temperatures(self.fetch_gettable_channels_and_parameters)

        print(f"{channel.print_readable_snapshot()}")

    def start_setpoint_dragging(self) -> None: 
        p, i, d = 50, 0.5, 10
        threshold: float = 1.0 # stop when within 1 degree
        target_gradient: float = float(self.query_one("#setpoint-dragging-rate-field", Input).value)
        stop: float = float(self.query_one("#setpoint-dragging-stop-field", Input).value)

        if stop == "" or threshold == "" or target_gradient == "":
            self.notify("please input all dragging parameters")
            return

        self.is_dragging = True
        self.guess_next_setpoint_for_dragging(stop, threshold, target_gradient, p, i, d)

    def stop_setpoint_dragging(self) -> None:
        # print("stopping")
        self.notify("stopping dragging")
        self.is_dragging = False

    def guess_next_setpoint_for_dragging(self, stop, threshold, target_gradient: float, p: float, i: float, d: float) -> float:
        """Guess the next setpoint when using the 'setpoint dragging' feature.

        This implementation uses a PID algorithm to adjust the setpoint for maintaining a steady descent rate.
        """
        channel_mapping = {"output_1": "A", "output_2": "B", "output_3": "C", "output_4": "D"}
        channel: str | None = channel_mapping.get(self.active_channel.name_parts[-1])
        if not channel:
            self.notify("Something went wrong, channel not found for setpoint dragging!")
            self.stop_setpoint_dragging()
            return stop

        # Fetch required values from stats_buffer
        current_gradient = self.stats_buffer[channel]["gradient"]
        current_setpoint = self.stats_buffer[channel]["raw_data"][-1]  # Assume last value is the current setpoint

        # Calculate PID terms
        error = target_gradient - current_gradient  # Proportional term
        integral = self.stats_buffer[channel]["raw_data"][-1]

        # Compute PID output
        output = p * error + i * integral + d * current_gradient

        # Adjust the setpoint based on the PID output
        next_setpoint = current_setpoint + output

        # # Constrain the next setpoint within reasonable limits
        # next_setpoint = max(min(next_setpoint, stop), threshold)

        return next_setpoint

    def get_channel(self) -> LakeshoreModel336CurrentSource | None:
        try:
            channel_mapping={"output_1": "A", "output_2": "B", "output_3": "C", "output_4": "D"}
            channel=self.active_channel
            channel.input_channel(channel_mapping.get(self.active_channel.name_parts[-1]))

            return channel

        except Exception as e:
            print(f"Error: {e}")


    def go_to_setpoint(self, setp) -> None: 
        channel = self.get_channel()
        if not channel:
            return

        channel.setpoint(float(setp))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle the pressed event for buttons on this screen."""

        handlers = {
            "setpoint-start": lambda: (self.go_to_setpoint(self.query_one("#setpoint-field", Input).value) 
                                       if self.query_one("#setpoint-field", Input).value.strip() != "" 
                                       else None),
            "setpoint-dragging-start": self.start_setpoint_dragging,
            "setpoint-dragging-stop": self.stop_setpoint_dragging,
            "refresh-stats-button": lambda: self.stats_buffer.clear(),
            "start-sweep": asyncio.create_task(self.sweep_temperature()),
        }
        
        handler = handlers.get(str(event.button.id))
        if handler:
            handler()

    def change_active_channel(self, channel: str) -> None:
        
        if len(self.allowed_temperature_monitors) <= 0:
            return
        
        lake = self.allowed_temperature_monitors[0]
        heaters = { "A": lake.output_1, "B": lake.output_2, "C": lake.output_3, "D": lake.output_4 }
        self.active_channel = heaters[channel]
        self.populate_fields()
        # self.fetch_gettable_channels_and_parameters()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        handlers = {
            "listitem-A": lambda: self.change_active_channel("A"),
            "listitem-B": lambda: self.change_active_channel("B"),
            "listitem-C": lambda: self.change_active_channel("C"),
            "listitem-D": lambda: self.change_active_channel("D")
        }

        handler = handlers.get(str(event.item.id))
        if handler:
            handler()

    def set_heater_mode(self, channel: LakeshoreModel336CurrentSource, mode: str) -> None:
        channel.mode(mode)

    def set_output_range(self, channel: LakeshoreModel336CurrentSource, mode: str) -> None:
        channel.output_range(mode)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle changes in any RadioSet. Does nothing in simulated mode since these actions aren't in the val_mapping."""

        if self.app.simulated_mode or not event.radio_set.id:
            return 

        channel = self.get_channel()
        if not channel:
            return

        # Map RadioSet IDs to their corresponding handling logic
        handlers = {
            "heater-mode": self.set_heater_mode,
            "output-range": self.set_output_range
        }

        # Call the appropriate handler if the RadioSet ID exists in the map
        handler = handlers.get(str(event.radio_set.id))
        if handler:
            handler(channel, str(event.pressed.label))
            
        channel.print_readable_snapshot()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if not event.input.id:
            return

        channel = self.get_channel()
        if not channel:
            return

        handlers = {
            "P": lambda: channel.P(float(event.value)),
            "I": lambda: channel.I(float(event.value)),
            "D": lambda: channel.D(float(event.value)),
            "manual-output": lambda: channel.manual_output(event.value),
        }

        handler = handlers.get(str(event.input.id))
        if handler:
            handler()

        channel.print_readable_snapshot()

    def start_temperature_polling(self) -> None:
        self.start_time = time.time()
        # self.stop_temperature_polling()
        self.update_timer = self.set_interval(self.polling_interval, self.poll_temperature_controller)

    def stop_temperature_polling(self) -> None:
        """Check if there is a update_timer and then stop it. Meant to be called when the screen is closed."""
        if self.update_timer:
            self.update_timer.stop()
        self.plotter.stop()

    def cleanup_all(self) -> None:
        self.stop_temperature_polling()
        self.plotter.stop()

    def action_initialize_plot(self) -> None:
        """Initialize and display a Matplotlib plot for channels A, B, C, and D."""
        self.plotter.start()

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

    @on(Button.Pressed, "#isnt_button")
    def temp_button(self):
        self.app.push_screen("temperature_screen")

        
class Peppermint(App):
    """A Textual app to manage instruments."""
    
    def __init__(self, simulated_mode: Optional[str | None] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.simulated_mode: Optional[str | None] = simulated_mode
        self.state: SharedState = SharedState()
        self.state.detected_instruments = [ instr for instr in pyvisa.ResourceManager().list_resources() ]
        self.state.connected_instruments = []
        self.state.write_parameters = []
        self.state.read_parameters = []
        self.state.database_path = os.path.join(os.getcwd(), "TMP_experiment_container.db") # this is a horrible temporary thing, this should be set on startup or in experiments menu

    CSS_PATH = "Peppermint.css"

    BINDINGS = [
        ("i", "push_screen('instrument_screen')", "Instruments"),
        ("p", "push_screen('parameter_screen')", "Parameters"),
        ("t", "push_screen('temperature_screen')", "Temperature"),
        ("a", "push_screen('main_screen')", "Main Screen")
    ]

    SCREENS = { 
        "instrument_screen": InstrumentsScreen, #type: ignore
        "parameter_screen": ParametersScreen, #type: ignore
        "temperature_screen": TemperatureScreen, #type: ignore
        "manual_connection_dialog": ManualConnectionDialog, #type: ignore
        "main_screen": MainScreen
    }
    
    def on_mount(self) -> None:
        self.theme = "nord"
        self.push_screen('main_screen')
        initialise_or_create_database_at(self.state.database_path) # again, this is a temporary thing, this should be initialized on demand or in experiments menu

    async def on_exit(self):
        # Perform cleanup tasks here
        print("Application is exiting. Performing cleanup...")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Peppermint")
    # parser.add_argument("--simulated-instruments", default=False, action="store_true", help="Run using a simulated dummy instrument")
    parser.add_argument(
        "--simulated-instruments",
        nargs="?",             # Argument can have 0 or 1 values
        const="default",       # Value used if the argument is present but no string is provided
        default=None,          # Value used if the argument is not provided
        help="Either lakeshore or keithley. Forcibly uses simulated drivers for one or the other for testing purposes."
    )
    args = parser.parse_args()

    Peppermint(simulated_mode=args.simulated_instruments).run()
