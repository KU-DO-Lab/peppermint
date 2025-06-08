# Developer information for `peppermint/src/`, updated 29 May 2025

## Files in this directory

1. `screens/`: contains the various textual screens which may be navigated to by the user.
2. `drivers/`: contains local copies of QCoDeS drivers.
3. `peppermint.py`: the application root.
4. `datasaver.py`: the DataSaver class which uses SQLite queries to reliably save data.
5. `actionsequence.py`: class combining instrument commands to form a sequence.
6. `liveplotter.py`: version 2 of the plotter which takes a table from a sql database and automatically plots all columns versus a supplied axis (default: time).
7. `simpleliveplotter.py`: **deprecated** and will be removed in the future. Basic plotting interface which requires data to be passed to a dequeue, which is prone to memory constraints and is overall more difficult to use.
8. `sweep1d.py`: primitive interface which takes an instrument and dispatches a sweep. Uses multiple dispatch pattern to supply unique functions which can be called in the same way but implement sweep for each instrument separately. **Will be deprecated in the future** in favor of a generic `Sweep` class which may be configured to sweep inner and outer parameters.
9. `themes.py`: additional color schemes which may be used by the user.
10. `utils.py`: broadly defined, general-use functions and classes which are not large enough or do not fit well into their own file. 
11. `loggingmixin.py`: mixin (class that contains methods for use by other classes without having to be the parent class of those other classes) related to logging. Specifically, responsible for managing the lifetime of logging. For example, consider we want to measure the temperature of the cryostat while sweeping. If we set it and forget it, we will not be continuously logging. Instead, we need something outside the Setter class which knows how often to, and when to start/stop measuring some value(s).
12. `./setter.py`:
