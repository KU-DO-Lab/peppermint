import pyvisa
from qcodes.instrument import VisaInstrument
from textual.widgets import OptionList, Select
from utils.drivers.Lakeshore_336 import LakeshoreModel336
from utils.drivers.Keithley_2450 import Keithley2450
from textual.reactive import reactive
from typing import Optional

# stolen from Spearmint
def safe_set(p, value, last_try=False):
    """
    Alerts the user when a parameter can not be set to the chosen value.
    
    Parameters
    ---------
    p:
        The parameter to be set.
    value:
        The desired value.
    last_try:
        Flag to stop attempting to set the value.
    """
    
    ret = None
    try:
        ret = p.set(value)
    except Exception as e:
        if last_try is False:
            print(f"Couldn't set {p.name} to {value}. Trying again.", e)
            time.sleep(1)
            return safe_set(p, value, last_try=True)
        else:
            print(f"Still couldn't set {p.name} to {value}. Giving up.", e)
            raise ParameterException(f"Couldn't set {p.name} to {value}.", set=True)
    return ret

# stolen from Spearmint
def safe_get(p, last_try=False):
    """
    Alerts the user when a parameter's value can not be obtained.
    
    Parameters
    ---------
    p:
        The parameter to be measured.
    last_try:
        Flag to stop attempting to set the value.
    """
    
    ret = None
    try:
        ret = p.get()
    except Exception as e:
        if last_try is False:
            print(f"Couldn't get {p.name}. Trying again.", e)
            time.sleep(1)
            return safe_get(p, last_try=True)
        else:
            print(f"Still couldn't get {p.name}. Giving up.", e)
            raise ParameterException(f'Could not get {p.name}.', set=False)
    return ret


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

def match_instrument_name_to_object(name: str, instrument_list) -> Optional[VisaInstrument]:
    """
    Fields on screen have to be rendered using the instrument's name field, since we can't just write an instrument 
    object to the widget, that doesn't make sense. We still pull these names from a single list of instruments, so 
    if we, say, select a name of an instrument in one widget and want to use the result of that to render the parameters
    of that instrument, we will need to match the name of the instrument to the instrument object.
    """
    try:
        return next(inst for inst in instrument_list if inst.name == name)
    except StopIteration:
        return None

# This and connect instrument should be renamed to something a bit clearer.
def auto_connect_instrument(address: str, name=None, args=[], kwargs={}):
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
        print(IDN)
        inst.close()
    except Exception as e:
        # We need this to fail otherwise the app will incorrectly add the instrument to the list of available instruments. 
        inst.close()
        raise(f"Error querying IDN : {e}")
    
    # Reference connect_device() from Spearmint for a superior function.
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

def list_avail_instrument_params(instrument: VisaInstrument) -> None:
    """
    Lists available parameters for the instrument passed.
    """
    for key, p in instrument.parameters.items():
        print(p.full_name)
    for name, submodule in instrument.submodules.items():
        if hasattr(submodule, 'parameters'):
            for key, p in submodule.parameters.items():
                ...
 
