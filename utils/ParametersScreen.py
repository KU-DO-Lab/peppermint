from utils.util import *
from typing import Optional
from qcodes.parameters import GroupParameter, ParameterBase
from qcodes.instrument import VisaInstrument
from textual.screen import Screen
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static, Label, Select, ListView, ListItem, Collapsible, Pretty


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
