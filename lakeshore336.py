from qcodes import VisaInstrument
#Dont worry about lakeshore yet amdsen is fixing somthing
class Lakeshore336(VisaInstrument):
    def __init__(self, name, address, **kwargs):
        super().__init__(name, address, terminator='\n', **kwargs)
        
        self.add_parameter(
            name="self_test",
            get_cmd="*TST?",
            docstring="The Model 336 reports status based on test done at power up."
        )
        self.add_parameter(
            name="temperature_k",
            get_cmd="KRDG?",
            docstring="Displays the instruments temperature in kelvin"
        )
        self.add_parameter(
            name="temperature_c",
            get_cmd="CRDG?",
            docstring="Displays the instruments temperature in Celsius"
        )
        self.add_parameter(
            name="alarm",
            get_cmd=self._get_alarm,
            #set_cmd=self._set_alarm,
            docstring="Displays the instruments temperature insius"
        )
    def _get_alarm(self):  
        a = self.ask("ALARM? A")  
        return a
    def _set_alarm(self, input, is_on, high, low, deadband, is_latch, is_audible, is_visible):
        None
        #alarm_str = f"{input},{is_on},{high},{low},{deadband}, {is_latch}, {is_audible}, {is_visible}"
        #return alarm_str
        
        
        
