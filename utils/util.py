import pyvisa
from textual.widgets import OptionList, Select
from utils.drivers.Lakeshore_336 import LakeshoreModel336
from utils.drivers.Keithley_2450 import Keithley2450

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
def auto_connect_instrument(name: str, address: str, args=[], kwargs={}):
    """
    Attempts to automatically detect and connect to an instrument by querying IDN
    the result is matched to a driver and instantiate a connection and return

    This should return with the instrument object. Need to add type hinting
    """

    # If we need to test without access to the lab hardware, just create a dummy instrument
    if name == "dummy":
        return Keithley2450("dummy_keithley2450", address="GPIB::2::INSTR", pyvisa_sim_file="Keithley_2450.yaml")

    rm = pyvisa.ResourceManager()
    inst = rm.open_resource(address)
    IDN = ""
    
    try:
        IDN = inst.query("*IDN?")
        inst.close()
    except Exception as e:
        # We need this to fail otherwise the app will incorrectly add the instrument to the list of available instruments. 
        inst.close()
        raise(f"Error querying IDN : {e}")
    
    # TODO: prompt for name, kwargs
    # See connect_device() from Spearmint.
    match IDN.split(',')[1]:
        case "MODEL 2450":
            new_dev = Keithley2450("k2450", address, *args, **kwargs)
        case "MODEL336":
            new_dev = LakeshoreModel336("ls336", address, *args, **kwargs)
        case "IDN for TM620":
            ...
        case "4G":
            ...
    return new_dev

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
 
