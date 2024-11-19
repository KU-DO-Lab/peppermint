import pyvisa

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
