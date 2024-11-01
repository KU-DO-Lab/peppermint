import pyvisa
import numpy as np
import M4G 
import qcodes as qc
from lakeshore336 import Lakeshore336 

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
lakeshore = Lakeshore336("lake", "GPIB0::1::INSTR")
for x in lakeshore.parameters:
    print(x)
print(lakeshore.alarm())
