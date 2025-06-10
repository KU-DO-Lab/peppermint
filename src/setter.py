class Setter:
    """Set a parameter programmatically, and log/plot it continuously."""
    
    def __init__(self, parameter: Parameter, table_name: str, datasaver: DataSaver, 
                 polling_rate: float = 0.5):
        self._parameter = parameter
        self._datasaver = datasaver
        self._table_name = table_name
        self._logger = ContinuousLogger(datasaver, table_name, polling_rate)
        self._plotter: Optional[LivePlotter] = None
        self._strategy: Optional[ManualStopStrategy] = None
    
    def start(self, value: Any, enable_plotting: bool = True) -> None:
        """Set the value and start continuous logging and plotting."""
        # Set the parameter value
        self._parameter.set(value)
        
        # Start plotting if requested
        if enable_plotting:
            self._plotter = LivePlotter(
                self._datasaver,
                self._table_name,
                title=f"{self._parameter.full_name} Monitor",
                xlabel="Time",
                ylabel=f"{self._parameter.full_name}",
                xaxis_key="timestamp",
            )
            self._plotter.start()
        
        # Create strategy and start logging
        self._strategy = ManualStopStrategy()
        self._logger.start_logging(self._get_current_data, self._strategy)
    
    def stop(self) -> None:
        """Stop continuous logging and plotting."""
        if self._strategy:
            self._strategy.stop()
        
        self._logger.stop_logging()
        
        if self._plotter:
            self._plotter.stop()
            self._plotter = None
    
    def set_value(self, value: Any) -> None:
        """Update the parameter value while logging continues."""
        self._parameter.set(value)
    
    def get_value(self) -> Any:
        """Get the current parameter value."""
        return self._parameter.get()
    
    def _get_current_data(self) -> list[tuple[Parameter, Any]]:
        """Data source function for the logger."""
        current_value = self._parameter.get()
        timestamp = time.time()
        
        # Create a timestamp parameter for plotting
        # Note: You might want to create a proper timestamp Parameter
        return [(self._parameter, current_value)]
