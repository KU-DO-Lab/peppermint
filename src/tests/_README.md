# Developer information for `peppermint/src/tests/`, updated 29 May 2025

All pytest-based tests are located here. Simulated drivers are used for the instruments (QCoDeS/pyvisa-sim) so that drivers may be tested. At the time of writing, files have been significantly moved around, and these tests will require some small changes in path/module loading to ensure everything plays nicely.
