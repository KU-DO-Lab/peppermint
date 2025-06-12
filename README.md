# Peppermint

 <img align="right" width="250" alt="splash screen" src="https://github.com/user-attachments/assets/c87c31f3-cc14-4712-8eb6-de4c60afc650" />

TUI application developed by Ovchinnikov Resarch Group at the University of Kansas for easy, interactive transport measurements. 
 
## Installation 

Clone this repository and install dependencies with [poetry](https://python-poetry.org/). Then start the application using `poetry run Peppermint.py` (or equivalent commands, depending on your installation method). `poetry lock` and `poetry install` should be used to initialize your virtual environment and ensure that all packages are downloaded, once the repository is cloned.

For developers, it is recommended to also install [textual-dev](https://textual.textualize.io/guide/devtools/) (included in pyproject.toml) which provides a debug console via `textual console`. To log the application to the console, run Peppermint with `textual run --dev Peppermint.py`. This allows debugging of the application at runtime.

Additionally, if you want to work on the project remotely (i.e., you can't plug into an instrument) you can run the program using the `--simulated-instruments lakeshore` or `--simulated-instruments keithley` flags to load simulated Lakeshore 336 or Keithley 2450 drivers. Another way to do this is to add an instrument manually by pressing `m` on the instruments screen. At the time of writing, this does not properly refresh the instruments when adding a simulated instrument, so it may seem that it does not exist. Confirm this in the parameters screen (`p`).

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
   ![temperature monitoring](https://github.com/user-attachments/assets/b107f986-6a67-46d8-9a9e-ca96efde19d2)
  </td>
  <td>
![sweeping](https://github.com/user-attachments/assets/)
  </td>
</tr>
<tr>
<td>
 ![measurements](https://github.com/user-attachments/assets/698296f3-0794-44af-b5fb-00a512753a65)
</td>
<td>
![experiments](https://github.com/user-attachments/assets/)
</td>
</tr>
</table>
