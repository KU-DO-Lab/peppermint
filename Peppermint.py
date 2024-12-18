import os
from typing import Any, Dict, Optional
from dataclasses import dataclass
import logging

import pyvisa
from qcodes.dataset import Measurement, initialise_or_create_database_at, load_or_create_experiment
from qcodes.parameters import GroupParameter, Parameter, ParameterBase
from qcodes.instrument import VisaInstrument
from utils.util import *
from textual import on
from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.screen import Screen, ModalScreen
from textual.containers import Horizontal, Vertical, Grid, Container
from textual.widgets import Footer, Header, Static, Label, TabbedContent, TabPane, OptionList, Select, Button, Placeholder, ListView, ListItem

import time
import matplotlib
import matplotlib.pyplot as plt
matplotlib.use("GTK3Agg")


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
        #       we can forcibly set the name to be "dummy" in development to use a simulated keithley.

        # Do the connection procses here- right now it just tries the auto-connect, but we will later handle manual connections here
        new_instrument = auto_connect_instrument(address=instrument_address)
        # new_instrument = auto_connect_instrument(name="dummy", address=instrument_address)

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
            # I am very bad at CSS, this needs changed to use it lmao -Grant
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
        for key, p in selected_instrument.parameters.items():
            self.available_parameters.append(ListItem(Static(p.full_name)))
        for name, submodule in selected_instrument.submodules.items():
            if hasattr(submodule, 'parameters'):
                for key, p in submodule.parameters.items():
                    self.available_parameters.append(ListItem(Static(p.full_name)))

    def action_set_parameter_read(self) -> None:
        """Sets parameter to active read mode"""
        selected: ListItem | None = self.available_parameters.highlighted_child
        
        if not selected or "read" in selected.classes or "write" in selected.classes:
            self.notify("Already reading/writing parameter" if selected else "No parameter selected")
            return

        try:
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

                # DEBUGGING, KEEP AROUND
                # ill never forgive microsoft employees for the crimes they've committed
                print(dir(param))
                print(param.get)
                print(param.gettable)
                print(param.get_raw)
                print(param.get_latest)
                print(f"Parameter type: {type(param)}")
                print(f"Parameter mappings: {param.val_mapping if hasattr(param, 'val_mapping') else 'No val_mapping'}")
                print(f"Parameter validators: {param.validators if hasattr(param, 'validators') else 'No validators'}")
            else:
                param: GroupParameter | ParameterBase = instrument.parameters[stripped_param_name]

            if not param.gettable:
                self.notify("parameter is not writeable!")
                return
            
            selected.add_class("read")
            self.app.state.read_parameters.append(param) # in case the parameter needs to be accessed in a database
            self.read_parameters.append(ListItem(ParameterWidget(param, readonly=True)))

        except (AttributeError, IndexError):
            self.notify("Invalid parameter widget structure")
        except StopIteration:
            self.notify("No instrument selected")
        except Exception as e:
            self.notify(f"Error: {str(e)}")

    def action_set_parameter_write(self) -> None:
        """
        Assign the parameter active write mode.

        TODO: switching back-forth from read/write, set experiment
        """
        selected: ListItem | None = self.available_parameters.highlighted_child
        
        if not selected or "read" in selected.classes or "write" in selected.classes:
            self.notify("Already reading/writing parameter" if selected else "No parameter selected")
            return

        try:
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

                # DEBUGGING, KEEP AROUND
                # ill never forgive microsoft employees for the crimes they've committed
                print(dir(param))
                print(param.get)
                print(param.gettable)
                print(param.get_raw)
                print(param.get_latest)
                print(f"Parameter type: {type(param)}")
                print(f"Parameter mappings: {param.val_mapping if hasattr(param, 'val_mapping') else 'No val_mapping'}")
                print(f"Parameter validators: {param.validators if hasattr(param, 'validators') else 'No validators'}")
            else:
                param: GroupParameter | ParameterBase = instrument.parameters[stripped_param_name]

            if not param.settable:
                self.notify("parameter is not writeable!")
                return 

            selected.add_class("write")
            self.app.state.write_parameters.append(param) # in case the parameter needs to be accessed in a database
            self.write_parameters.append(ListItem(ParameterWidget(param, readonly=False)))

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
        ("s", "setpoint", "Adjust Setpoint"),
    ] 

    def __init__(self):
        super().__init__()
        self.polling_frequency = 1.0
        self.update_timer = None
        
        self.experiments = {}
        self.measurements: Dict[str, Measurement] = {}
        self.datasavers: Dict[str, Any] = {}
        
        self.chA_temperature = Static("N/A", id="channel_A")
        self.chC_temperature = Static("N/A", id="channel_C")
        self.chB_temperature = Static("N/A", id="channel_B")
        self.chD_temperature = Static("N/A", id="channel_D")

        # Channel widget mappings
        self.channel_widgets = {
            'A': self.chA_temperature,
            'B': self.chB_temperature,
            'C': self.chC_temperature,
            'D': self.chD_temperature
        }
        
        # Initialize experiments for each channel
        for channel in ['A', 'B', 'C', 'D']:
            exp_name = f"Temperature_Channel_{channel}"
            self.experiments[channel] = load_or_create_experiment(
                experiment_name=exp_name,
                sample_name="Lakeshore Auto Monitor"
            )

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

    def get_temperatures(self) -> None:
        """Get and record temperatures for each channel"""
        for param in self.app.state.read_parameters:
            if not (hasattr(param, 'name_parts') and param.name_parts[-1] == "temperature"):
                continue
                
            channel = param.name_parts[1] # Extract channel label (A, B, C, D)            

            # Update widget
            if channel in self.channel_widgets:
                value = param.get()
                self.channel_widgets[channel].update(str(value))
                
                # Record data for this channel
                # Saved to the QCoDeS run which gets started when this screen is initialized.
                if channel in self.datasavers and self.datasavers[channel]:
                    print(channel, param, value)
                    self.datasavers[channel].add_result( (param, value) )

    def cleanup(self) -> None:
        """Clean up the datasavers when done"""
        for datasaver in self.datasavers.values():
            if datasaver:
                datasaver.__exit__(None, None, None)
        
    def compose(self) -> ComposeResult:
        """Define all widgets for this screen."""
        allowed_monitor_types = (LakeshoreModel336)
        self.allowed_temperature_monitors = [inst for inst in self.app.state.connected_instruments if isinstance(inst, allowed_monitor_types)] # type: ignore
        self.instrument_options: list[tuple[str, str]] = [(instrument.name, instrument.name) for instrument in self.allowed_temperature_monitors]
        self.temperature_monitors_select = Select[str](self.instrument_options)

        self.status_table = Container(
            Horizontal(Label("Channel A:    "), self.chA_temperature),
            Horizontal(Label("Channel B:    "), self.chB_temperature),
            Horizontal(Label("Channel C:    "), self.chC_temperature),
            Horizontal(Label("Channel D:    "), self.chD_temperature),
        )

        # This mess should probably be rewritten by someone with a nonzero amount of css skill
        yield Header()
        yield Container(
        Horizontal(
            Horizontal(Static("Temperature Controller:     ", classes="label"), self.temperature_monitors_select, classes="temp_controller_instrument"),
            Vertical(Static("Status:", classes="label"), self.status_table, classes="temp_controller_status"),
            Container(Placeholder(), classes="temp_controller_controls"),
            classes="short_container"
        ),
        Container()
        )
        yield Footer()

    async def on_screen_resume(self) -> None:
        """ 
        Handle the ScreenResume event. 
        Whenever the temperature screen is opened, we need to make sure every temperature monitor parameter is running. 
        """

        if len(self.allowed_temperature_monitors) <= 0: 
            self.notify("please connect the Lakeshore 336!")
            return

        self.temperature_monitors_select.clear()
        self.instrument_options: list[tuple[str, str]] = [(instrument.name, instrument.name) for instrument in self.allowed_temperature_monitors]
        self.temperature_monitors_select.set_options(self.instrument_options)

        # this spits out a list of parameters, which have their name split as: "instrument, submodule, parameter"
        # for a lakeshore 336, it has channels/submodules ABCD. this will differ with other controllers
        required_submodules = {'A', 'B', 'C', 'D'}
        parameters: list[list[str]] | None = [param.name_parts for param in self.app.state.read_parameters]

        # Extract the labels for "temperature" parameters
        existing_labels = { param[1] for param in parameters if len(param) > 2 and param[-1] == "temperature" }
        missing_labels = required_submodules - existing_labels

        for label in missing_labels:
            submodule = self.allowed_temperature_monitors[0].submodules[label]
            param: GroupParameter | ParameterBase = submodule.parameters['temperature']
            self.app.state.read_parameters.append(param)
        
        self.initialize_measurements()
        self.get_temperatures()
        self.start_temperature_polling()

    def start_temperature_polling(self) -> None:
        self.stop_temperature_polling()
        self.update_timer = self.set_interval(1/self.polling_frequency, self.get_temperatures)

    def stop_temperature_polling(self) -> None:
        """Check if there is a update_timer and then stop it. Meant to be called when the screen is closed."""
        if self.update_timer:
            self.update_timer.stop()

    def action_initialize_plot(self) -> None:
        """Initialize and display a Matplotlib plot for channels A, B, C, and D."""
        self.fig, self.ax = plt.subplots()
        self.ax.set_title("Channel Temperatures")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Temperature (K)")

        # Store time and temperature data for each channel
        self.plot_data = {channel: {"time": [], "temperature": []} for channel in ['A', 'B', 'C', 'D']}
        self.plot_lines = {}

        # Initialize lines for each channel in the plot
        for channel in ['A', 'B', 'C', 'D']:
            line, = self.ax.plot([], [], label=f"Channel {channel}")
            self.plot_lines[channel] = line

        self.ax.legend()
        plt.show(block=False)

        self.start_plot_update()

    def start_plot_update(self) -> None:
        """Start polling data and updating the plot."""
        self.plot_start_time = time.time()
        self.update_timer = self.set_interval(1 / self.polling_frequency, self.update_plot)

    def update_plot(self) -> None:
        """Poll data, update the Matplotlib plot, and refresh it."""
        current_time = time.time() - self.plot_start_time

        for param in self.app.state.read_parameters:
            if not (hasattr(param, 'name_parts') and param.name_parts[-1] == "temperature"):
                continue

            channel = param.name_parts[1]
            value = param.get()

            # Update stored data
            self.plot_data[channel]["time"].append(current_time)
            self.plot_data[channel]["temperature"].append(value)

            # Update plot line data
            self.plot_lines[channel].set_xdata(self.plot_data[channel]["time"])
            self.plot_lines[channel].set_ydata(self.plot_data[channel]["temperature"])

        # Adjust axes limits dynamically
        self.ax.relim()
        self.ax.autoscale_view()

        # Redraw the plot
        self.fig.canvas.flush_events()
        self.fig.canvas.draw()


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

    def __init__(self):
        super().__init__()
        self.state = SharedState()
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
        self.push_screen('main_screen')
        initialise_or_create_database_at(self.state.database_path) # again, this is a temporary thing, this should be initialized on demand or in experiments menu

if __name__ == "__main__":
    app = Peppermint()
    app.run()
