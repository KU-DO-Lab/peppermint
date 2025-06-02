# Developer information for `peppermint/src/drivers/`, updated 29 May 2025

This folder simply contains drivers for our instruments. In general, these are local copies of the QCoDeS driver, and may be swapped out for the one hosted on the python package repository. **HOWEVER**, some of these "official" QCoDeS drivers do not support every feature needed, in which case they may be added by modifying the drivers here. At the time of writing, only the Lakeshore 336 driver has features which do not exist in the official repository.
