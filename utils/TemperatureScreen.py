from collections import deque
from typing import Any, Dict, Optional

from utils.drivers.Lakeshore_336 import LakeshoreModel336CurrentSource
from utils.util import *

import numpy as np
from qcodes.parameters import GroupParameter, MultiParameter, ParameterBase

from textual.screen import Screen
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.widgets import Footer, Header, Input, RadioButton, RadioSet, Rule, Static, TabbedContent, Button, ListView, ListItem, TextArea

class TemperatureMultiParameter(MultiParameter):
    def __init__(self, name, channels: list[str], parameters: list[ParameterBase]):
        self.channels = channels
        self.parameters = parameters

        super().__init__(
            name=name,
            names=["simulated_lakeshore336_A_temperature", "simulated_lakeshore336_B_temperature"],  # e.g., ["A", "B", "C", "D"]
            shapes=tuple(() for _ in channels),
            units=["K"] * len(channels),
            setpoints=tuple(() for _ in channels),
            setpoint_names=tuple(() for _ in channels),
            setpoint_units=tuple(() for _ in channels)
        )

    def get_raw(self):
        return tuple(param.get() for param in self.parameters)

class TemperatureScreen(Screen):
    """The screen containing information related to the temperature controllers."""

    BINDINGS = [
        ("f1", "initialize_plot", "Open Plot"),
        ("f2", "stop_plot", "Stop Plot"),
    ] 

    def __init__(self):
        super().__init__()
        self.polling_interval = 4
        self.update_timer = None
        self.active_channel = None
        self.is_dragging = False
        self.is_sweeping = False
 
        # Set up data logging
        date = datetime.datetime.now().strftime('%d.%b.%Y')
        self.table_name = self.app.state.datasaver.register_table(f"Temperature Monitor: {date}") # Resolves duplicates, so there may be a numeric tag at the end of the name and we assign this way.

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
        # for channel in list(self.channel_widgets.keys()): # [A,B,C,D]
        #     exp_name = f"Temperature_Channel_{channel}"
        #     self.experiments[channel] = load_or_create_experiment(
        #         experiment_name=exp_name,
        #         sample_name="Lakeshore Auto Monitor"
        #     )

        self.plotter = SimpleLivePlotter(
            channels=list(self.channel_widgets.keys()),
            title="Automated Temperature Monitor",
            xlabel="time (s)",
            ylabel="temperature (k)",
            use_timestamps=True,
        )

        self.plotter2 = LivePlotter(
            self.app.state.datasaver,
            self.table_name
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
                        Button("?", tooltip="Heater range settings. Heater mode can be set to closed loop or open loop which have different purposes:\n\n1. Open loop: for PID-controlled setpoint magic.\n2. Closed loop: for pushing a constant current through the heating element.", disabled=True, classes="tooltip"),
                        Vertical( Static("Heater Mode:    ", classes="label"), self.heater_mode, id="heater-mode-container" ),
                        Vertical( Static("Output Range:    ", classes="label"), self.output_range, id="output-range-container" ),
                        classes="temperature-controller-controls",
                    ),

                    Vertical( 
                        Button("?", tooltip="PID values for the heating element's setpoint control. If the heater never stabilizes, adjust P. If the heater never reaches the setpoint raise I by double. If it instead  oscillates about it for too long, lower by a half. Raising and lowering D may help it get to the setpoint faster. Manual output forcibly sets the heater output % without regard for setpoint.", disabled=True, classes="tooltip"),
                        Static("PID:", classes="label"), 
                        Horizontal(Static("P:", classes="label"), Input(placeholder="...", type="number", classes="input-field", id="P"), classes="container"), 
                        Horizontal(Static("I:", classes="label"), Input(placeholder="...", type="number", classes="input-field", id="I"), classes="container"), 
                        Horizontal(Static("D:", classes="label"), Input(placeholder="...", type="number", classes="input-field", id="D"), classes="container"), 
                        Horizontal(Static("Manual Output:", classes="label"), Input(placeholder="...", type="number", classes="input-field", id="manual-output"), classes="container"), 
                        id="PID-container", 
                        classes="outlined-container" 
                    ),

                    Horizontal( 
                        Button("?", tooltip="Go to a setpoint! Only works in closed loop mode.", disabled=True, classes="tooltip"),
                        Static("Setpoint:", classes="label"), Input(placeholder="...", disabled=False, type="number", classes="input-field", id="setpoint-field"), # need to check enabled on screen change, Static("(K)", classes="label"),
                        Button("Confirm!", id="setpoint-start", classes="confirmation"),
                        classes="temperature-controller-controls",
                    ),
                    classes="container"
                ),

                Vertical(
                    Button("?", tooltip="For maintaining a gentle ascent/descent at a fixed rate.\n\nCurrently requires supervision to change output ranges AND watch over 'I' since different ranges may demand higher/lower values", disabled=True, classes="tooltip"),
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
                            Horizontal(Static("Action at Setpoint:", classes="label"), TextArea.code_editor("print('Hello!'), print('World!')", language="python", show_line_numbers=False, id="sweep-actions-field", classes="input-field"), classes="container"),
                        Button("Go!", id="start-sweep", classes="confirmation"),
                        classes="container"
                ),
                    classes="outlined-container"
            )

        yield Footer()

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

            # print(f"Mean: {self.stats_buffer["A"]["mean"]}")
            # print(f"Gradient: {self.stats_buffer["A"]["gradient"]}")
            # print(f"Acceleration: {self.stats_buffer["A"]["acceleration"]}")
            # print(f"Instantaneous Output Variation: {self.stats_buffer["A"]["output_variation"]}")
            # print(f"Setpoint: {setp}")

            self.go_to_setpoint(setp)
        
    def get_output_percentage(self) -> None:
        if not self.allowed_temperature_monitors[0] or self.app.simulated_mode:
            return

        heater = self.get_channel()
        if not heater:
            return
        
        channel_mapping = {"output_1": "A", "output_2": "B", "output_3": "C", "output_4": "D"}
        channel_name: str | None = channel_mapping.get(self.active_channel.name_parts[-1])
        
        self.query_one("#output-percentage", Static).update(str(heater.output()))

        # Update statistics
        if channel_name not in self.stats_buffer:
            self.stats_buffer[channel_name] = {"raw_data": deque([], maxlen=128), "mean": float("nan"), "std": float("nan"), "gradient": float("nan"), "acceleration": float("nan"), "sum": 0.0, "output_percent": deque([], maxlen=2), "output_variation": 0.0}

        self.stats_buffer[channel_name]["output_percent"].append(float(heater.output()))


    def fetch_gettable_channels_and_parameters(self) -> Dict[str, ParameterBase]:
        """Return the parameter to get each temperature from."""
        channels_to_get = {}
        for param in self.app.state.read_parameters:
            if not (hasattr(param, 'name_parts') and param.name_parts[-1] == "temperature"):
                continue

            channel = param.name_parts[1]  # Extract channel label (A, B, C, D)
            channels_to_get[channel] = param  # Map the channel label to the parameter
        
        return channels_to_get

    def sweep_temperature(self, setpoints: Optional[list[float]] = [], actions: Optional[list[Any]] = []) -> None:
        """Start/Stop functionality for temperature sweeps."""
        # print(f"starting sweep")
        try: 
            setpoint_input = str(self.query_one("#sweep-setpoints-field", TextArea).text).split(",")
            setpoints = list(map(float, setpoint_input))
            actions = str(self.query_one("#sweep-actions-field", TextArea).text).split(",")

            # print(setpoints)
            [eval(f"lambda: {expr}") for expr in actions]

        except Exception as e:
            print(f"{e}")

    def check_temperature_stable(self) -> bool:
        ...

    def get_temperatures(self, fetch_channels_function) -> Dict[str, float]:
        """Get and record temperatures for each channel using MultiParameter."""

        # Fetch the parameter dict: channel_name -> Parameter
        things_to_get: Dict[str, ParameterBase] = fetch_channels_function()
        channel_names = list(things_to_get.keys())
        params = list(things_to_get.values())

        # Ensure we have the multi-parameter defined
        if not hasattr(self, 'multi_temp_param'):
            self.multi_temp_param = TemperatureMultiParameter('multi_temp', channel_names, params)

        # Get values from all parameters
        values = self.multi_temp_param.get_raw()
        current_time = time.time()

        # Build result tuples: (individual_param, value)
        result_tuples = [(param, value) for param, value in zip(params, values)]
        self.app.state.datasaver.add_result(self.table_name, result_tuples)

        data = {}

        for i, channel_name in enumerate(channel_names):
            value = values[i]
            data[channel_name] = value

            # Update widget
            if channel_name in self.channel_widgets:
                self.channel_widgets[channel_name].update(str(value))

            # Update plot
            if self.plotter:
                self.plotter.update(channel_name, x=current_time, y=value)

            # Update statistics buffer
            if channel_name not in self.stats_buffer:
                self.stats_buffer[channel_name] = {
                    "raw_data": deque([], maxlen=128),
                    "mean": float("nan"),
                    "std": float("nan"),
                    "gradient": float("nan"),
                    "acceleration": float("nan"),
                    "sum": 0.0,
                    "output_percent": deque([], maxlen=2),
                    "output_variation": 0.0
                }

            self.stats_buffer[channel_name]["raw_data"].append(value)
            self.stats_buffer[channel_name].update(self.get_statistics(channel_name))

            # Update UI widgets
            self.query_one("#stats-mean", Static).update(str(self.stats_buffer[channel_name]["mean"]))
            self.query_one("#stats-std", Static).update(str(self.stats_buffer[channel_name]["std"]))
            self.query_one("#stats-gradient", Static).update(str(self.stats_buffer[channel_name]["gradient"]))
            self.query_one("#stats-acceleration", Static).update(str(self.stats_buffer[channel_name]["acceleration"]))
            self.query_one("#stats-output-variation", Static).update(str(self.stats_buffer[channel_name]["output_variation"]))

        return data

    def get_statistics(self, channel: str) -> Dict[str, Any]:
        """Some very basic statistics running on some buffer of points from the temperature controller. It's worth noting this is limited by the resolution of collected data."""


        buf = self.stats_buffer[channel]
        previous_gradient: np.float32 = buf["gradient"]

        mean: np.float32 = np.sqrt(np.mean(np.square(buf["raw_data"]))) if len(buf["raw_data"]) > 0 else np.floating("nan")
        std: np.float32 = np.std(buf["raw_data"]) if len(buf["raw_data"]) > 0 else np.floating("nan")
        sum: np.float32 = buf["sum"] + (buf["raw_data"][-1] if len(buf["raw_data"]) > 0 else 0.0)
        gradient: np.float32 = np.float32((buf["raw_data"][-1] - buf["raw_data"][-2]) * 1/self.polling_interval if len(buf["raw_data"]) > 1 else 0.0)
        acceleration: np.float32 = np.float32((gradient - previous_gradient) * 1/self.polling_interval)
        output_variation: np.float32 = np.float32(buf["output_percent"][-1] - buf["output_percent"][-2]) if len(buf["output_percent"])>1 else np.float32("nan")

        return {"std": std, "mean": mean, "gradient": gradient, "sum": sum, "acceleration": acceleration, "output_variation": output_variation}

    async def on_screen_resume(self) -> None:
        """ 
        Handle the ScreenResume event. 
        Whenever the temperature screen is opened, we need to make sure every temperature monitor parameter is running. 
        """

        self.allowed_temperature_monitors = [inst for inst in self.app.state.connected_instruments if isinstance(inst, self.allowed_monitor_types)]

        if len(self.allowed_temperature_monitors) <= 0: 
            self.notify("Please connect the Lakeshore 336!")
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

        # print(f"{channel.print_readable_snapshot()}")

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

        last_ds = self.experiment.data_set(-1)  # Get the last run
        last_ds.export('latest_run.csv')


        handlers = {
            "setpoint-start": lambda: (self.go_to_setpoint(self.query_one("#setpoint-field", Input).value) 
                                       if self.query_one("#setpoint-field", Input).value.strip() != "" 
                                       else None),
            "setpoint-dragging-start": self.start_setpoint_dragging,
            "setpoint-dragging-stop": self.stop_setpoint_dragging,
            "refresh-stats-button": lambda: self.stats_buffer.clear(),
            "start-sweep": self.sweep_temperature,
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
            
        # channel.print_readable_snapshot()

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

        # channel.print_readable_snapshot()

    def start_temperature_polling(self) -> None:
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
        if not self.plotter.running:
            self.plotter.start()
        else:
            self.notify("Plotter already running!")

    def action_stop_monitoring(self) -> None:
        """Stop the plot"""
        if self.plotter.running:
            self.plotter.stop()
        else:
            self.notify("No plotter running!")
