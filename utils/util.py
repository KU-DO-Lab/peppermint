import pyvisa
from textual.widgets import OptionList, Select

def update_option_list(option_list: OptionList, items: list):
    """Helper method to update an OptionList's contents."""
    option_list.clear_options()
    for item in items:
        option_list.add_option(item)

def update_select(select_list: Select, items: list):
    """Helper method to update an Select's contents."""
    select_list.set_options(
        [(element, element) for element in items]
    )

# This and connect instrument should be renamed to something a bit clearer.
def auto_connect_instrument(address: str) -> None:
    """
    Attempts to automatically detect and connect to an instrument by querying IDN
    the result is matched to a driver and instantiate a connection and return

    This should return with the instrument object, not None.
    """
    rm = pyvisa.ResourceManager()
    # inst = rm.open_resource(address)
    # IDN = inst.query("*IDN?")
    # match IDN:
    #     case "IDN for keithley":
    #         ...
    #     case "IDN for lakeshore":
    #         ...
    #     case "IDN for TM620":
    #         ...
    #     case "IDN for M4G":
    #         ...
    ...

def list_avail_instrument_params(instrument):
    """
    Lists available parameters for the instrument passed.
    """
    # if len(instruments) > 0:
    #     instrument = instruments[index] # we will need to wrap this in smth to dynamically set the instrument when we are editing params;
    #                                     # i.e. we will have a menu to edit params, then list instruments. Tab/Shift+Tab changes instrument,
    #                                     # left/right sets the param to follow/set
    for key, p in instrument.parameters.items():
        print(p.full_name)
    for name, submodule in instrument.submodules.items():
        if hasattr(submodule, 'parameters'):
            for key, p in submodule.parameters.items():
                ...
 
