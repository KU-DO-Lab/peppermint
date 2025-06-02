from qcodes.instrument import VisaInstrument
from qcodes.parameters import Parameter


class Setter():
    def __init__(self, instrument: VisaInstrument, parameter: Parameter) -> None:
        self.instrument: VisaInstrument = instrument
        self.parameter: Parameter = parameter

    def start(self):
        pass

    def parse_value(self):
        pass

    def set_value(self):
        pass
