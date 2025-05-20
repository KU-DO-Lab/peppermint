import pyvisa
import numpy as np
import M4G 
import qcodes as qc
from Lakeshore_336 import LakeshoreModel336
from Keithley_2450 import Keithley2450
#Main is for experimenting for now
from qcodes.dataset import (
    LinSweep,
    Measurement,
    dond,
    experiments,
    initialise_or_create_database_at,
    load_by_run_spec,
    load_or_create_experiment,
    plot_dataset,
)

alarm_336 = dict(
    #The default alarm settings for the 336
    
    input = 1,              #Specifies which input to configure: A - D
    is_on = False,          #Determines whether the instrument checks the alarm for this input, where 0 = off and 1 = on.
    high = 0,               #Sets the value the source is checked against to activate the high alarm.
    low = 0,                #Sets the value the source is checked against to activate low alarm.
    deadband = 0,           #Sets the value that the source must change outside of an alarm condition to deactivate an unlatched alarm.
    latch_enabled = False,  #Specifies a latched alarm (remains active after alarm condition correction) where 0 = off (no latch) and 1 = on.
    is_audible = False,     #Specifies if the internal speaker will beep when an alarm condition occurs. Valid entries: 0 = off, 1 = on.
    is_visible = False      #Specifies if the Alarm LED on the instrument front panel will blink when an alarm condition occurs. Valid entries: 0 = off, 1 = on
)

ls336 = LakeshoreModel336("ls336", "GPIB0::1::INSTR")
tm620 = LakeshoreModel336("tm620", "GPIB0::2::INSTR") # we can access TM620 channels via daisy chaining through LS336
                                                      # we will need to modify this driver to use whichever termination character
                                                      # cryomagnetics uses, since it is different from lakeshore's
k2450 = Keithley2450("k2450", "USB0::0x05E6::0x2450::04586138::INSTR")
instruments = [ls336, tm620, k2450]

def list_avail_instrument_params(index):
    if len(instruments) > 0:
        instrument = instruments[index] # we will need to wrap this in smth to dynamically set the instrument when we are editing params;
                                        # i.e. we will have a menu to edit params, then list instruments. Tab/Shift+Tab changes instrument,
                                        # left/right sets the param to follow/set
        for key, p in instrument.parameters.items():
            print(p.full_name)
        for name, submodule in instrument.submodules.items():
            if hasattr(submodule, 'parameters'):
                for key, p in submodule.parameters.items():
                    ...
                    
list_avail_instrument_params(0)

print(ls336.IDN())

for ch in ls336.channels:
    print(f"{ch.short_name} {ch.temperature()} {ch.units()}") 
    

#ls336.channels.A.setpoint(-271.55)
#ls336.channels.A.Sample.setpoint()
#ls336.Output.setpoint()
#print(dir(ls336.output_1))
#ls336.output_1.setpoint_ramp_rate()
ls336.output_1.setpoint_ramp_enabled(1)
ls336.output_1.setpoint_ramp_rate(1)
print(ls336.output_1.setpoint_ramp_enabled())


print(ls336.output_1.setpoint_ramp_rate())

print(ls336.output_1.setpoint())
#ls336.output_1.setpoint(1.6)
ls336.output_1.setpoint_ramp_group([1,1])
print(ls336.output_1.output())
