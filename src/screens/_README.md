# Developer information for `peppermint/src/screens/`, updated 29 May 2025

## Files in this directory

1. `main_screen.py`: screen class for the main/splash screen. Should contain basic information about uptime, connected instruments, navigation, help, etc. Mostly untouched and could use some work.
2. `instruments_screen.py`: screen class for connecting to instruments. Should provide a list of detected instruments and connected instruments. Connecting to an instrument should attempt to auto-connect first, using the function in `../utils.py`. Also provides a modal screen to manually connect to instruments, which supports instantiating a simulated instrument. This screen needs many bug fixes and QOL improvements, such as letting the user rename/name instruments, preventing crashing from having duplicate names, etc.
3. `parameters_screen.py`: screen class to explore the parameters of an instrument and manually read/write things. Mostly intended for diagnostic use. Currently, only reading parameters is supported, and it barely works. Writing would be very useful to override certain settings, such as output enabled. Little in the way of data collection should be done here.
4. `temperature_screen.py`: screen class to manage the temperature controller outside of measurement environments. What this means is that this screen has operations to manipulate the temperature and view statistics/logging, and is useful for getting the system cooled/warmed, or for making adjustments manually, if it does not work well programmatically. Currently everything is implemented.
5. `measurements_screen.py`: screen class for configuring, starting, and monitoring the measurement status. Contains a column which allows sweeps, sets, and waits to be configured and added to the column which contains the sequence of actions to be done. Also contains buttons/binds to start/open/stop a `LivePlotter` instance. Additionally ensures that measurements are properly configured and all data is saved.
6. `settings_screen.py`: screen class for configuring settings, such as auto-connecting to instruments, presets for certain things, and generally controlling things that may be saved between uses. Currently empty.

## Screen Structure 

Peppermint is implemented using textual (python library) to provide an interactive application which is easy to work on. Most primary functions are broken into a more easily digestible screen with widgets to control certain features Each screen that can be shown has a home in its own file. Please see the [docs](https://textual.textualize.io/guide/screens/) for a more detailed explanation.

The basic flow of a screen class is as follows:
1. Initialize the screen class with certain parameters local to the entire screen, such as datasavers or settings that are required for the screen. Note: many global parameters are attached to `app.state`.
2. Compose and update widgets relevant to the screen. Please see [the docs](https://textual.textualize.io/widget_gallery/) for more information on which widgets can be used. While we are in the prototyping stage, we currently aim to make things readable and as pretty as we reasonably can. The [posting](https://posting.sh/) app is a fantastic example of great TUI design, so please use css styling to configure the style of the screen as you work.
3. Handle events and messages. Things such as the `on_widget_pressed` or `on_key_pressed` events are captured, and it is advised to use the multiple dispatch pattern to create a handler which responds to the `id` or other relevant parameters of the widget or key responsible for the event. This then dispatches a function by matching the key to a function/lambda value in a dictionary. Plenty of examples exist throughout each screen.
4. Handle screen unmounts and mounts. Certain fields may need to be refreshed when loading a screen.
