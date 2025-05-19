# Developer information for `peppermint/utils/`, updated 19 May 2025

## Structure

This folder contains the following things: 

1. Python files for each screen
2. Utility scripts used in these screens (util.py)
3. Driver related things, including local copies of the QCoDeS drivers (as there are certain features we need to modify) and simulation drivers for Keithley 2450 and Lakeshore 336 instruments as well as tests (pytest) for the drivers.

## Screen Structure 

Peppermint is implemented in textual (python) for development speed and ease. Most primary functions are broken into a more easily digestible screen with widgets to control certain features Each screen that can be shown has a home in its own file. Please see the [docs](https://textual.textualize.io/guide/screens/) for a more detailed explanation.

1. Initialize the screen class with certain parameters local to the entire screen, such as datasavers or settings that are required for the screen. Note: Measurement objects and global settings will eventually be handled properly in the global scope and may appear in these screens at the time of writing.
2. Compose and update widgets relevant to the screen. 
3. Handle events and messages

## utils.py

Utils.py contains many important functions and classes used throughout the project. A rundown of these are as follows.
1. Sweep1D: Simplest interface for sweeping a parameter for any instrument. Contains sub-implementations for sweeping on the different instrument types.
2. ActionSequence: Class implementing the functionality to preform many sweeps/sets in sequence. 
3. SimpleLivePlotter: Class implementing the plot worker for rendering data. Currently requires data to be passed into a queue, and should be replaced with an implementation that utilizes textual concurrency to plot from an experiment/datasaver.
4. auto_connect_instrument(): master function for connecting an instrument given an address. Currently very simple and will require prompting the user for more information.
5. match_instrument_name_to_object(): step through the connected instruments and return the instrument object given the name. Each instrument must have a unique name (QCoDeS) so this is guaranteed to be accurate.
