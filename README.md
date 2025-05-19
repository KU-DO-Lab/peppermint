# peppermint

 <img align="right" width="250" alt="clock" src="" />
A short description with an image of the application.

## Installation 

Clone this repository and install dependencies with [poetry](https://python-poetry.org/). Then start the application using `python Peppermint.py`.

For developers, it is recommended to also install [textual-dev](https://textual.textualize.io/guide/devtools/) (included in pyproject.toml) which provides a debug console via `textual console`. To log the application to the console, run Peppermint with `textual run --dev Peppermint.py`. This allows debugging of the application at runtime.
Additionally, if you want to work on the project remotely (i.e., you can't plug into an instrument) you can run the program using `--simulated-instruments lakeshore` or `--simulated-instruments keithley` to load Lakeshore 336 or Keithley 2450 drivers. Another way to do this is to add an instrument manually by pressing `m` on the instruments screen.

## Features

### Adding Instruments

Instruments can be added automatically by a user or (in the future) routinely when the application starts. Parameter tracking is handled automatically when preforming any kind of measurement, so all data is always saved.

### Temperature Monitoring and Automation

Our environment implements a Lakeshore 336 temperature controller, for which we expose many important controls and collect data from in real-time.

### Automation of Transport Measurement

Peppermint implements a versatile environment to configure a sequence of actions to be preformed by the instruments. Any measurement can be constructed from a sequence of building blocks: sets and sweeps.

## Showcase


<!--Just a placeholder table, we'd want to put gifs showcasing these features later...-->
<table>
<tr>
  <td>
  ![instruments](https://github.com/user-attachments/assets/)
  </td>
  <td>
![parameters](https://github.com/user-attachments/assets/)
  </td>
</tr>
<tr>
  <td>
  ![temperature monitoring](https://github.com/user-attachments/assets/)
  </td>
  <td>
![sweeping](https://github.com/user-attachments/assets/)
  </td>
</tr>
<tr>
<td>
![sequences](https://github.com/user-attachments/assets/)
</td>
<td>
![experiments](https://github.com/user-attachments/assets/)
</td>
</tr>
</table>
