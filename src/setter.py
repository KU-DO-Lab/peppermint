from typing import Any
from qcodes.parameters import Parameter

from datasaver import DataSaver

class Setter():
    """Set a parameter programatically, and log/plot it continuously.

    The lifetime of a set parameter may be the entire duration of the measurement, necessitating
    logging outside the lifetime of the start function.
    """
    def __init__(self, parameter: Parameter, table_name: str, datasaver: DataSaver) -> None:
        self._parameter: Parameter = parameter
        self._datasaver: DataSaver = datasaver
        self._table_name: str = table_name

    def start(self, value: Any) -> None:
        """Call to set the value, start the plotter, and record value"""
        return self._parameter.get()

    def set_value(self) -> None: 
        pass
