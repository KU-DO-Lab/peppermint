import pyvisa
import numpy as np
import M4G 
import qcodes as qc
import Lakeshore_336
from lakeshore336 import Lakeshore336 
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

lakeshore = Lakeshore_336.LakeshoreBaseOutput(Lakeshore_336.LakeshoreBase("lake", "GPIB0::1::INSTR"), "lake_out", 0)
#lakeshore = Lakeshore_336.LakeshoreBaseOutput("lake", "GPIB0::1::INSTR")
for x in lakeshore.parameters:
    print(x)
#print(lakeshore.alarm())
