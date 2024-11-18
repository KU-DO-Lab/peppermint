from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Tabs, Tab


class Peppermint(App):
    """A Textual app to manage stopwatches."""

    BINDINGS = [("d", "toggle_dark", "Toggle dark mode")]

    def compose(self) -> ComposeResult:
        """Create the child widgets for the app."""
        yield Header()
        yield Footer()

        yield Tabs(
            Tab("Instruments", id="instruments_tab"),
            Tab("Parameters", id="parameters_tab"),
            Tab("Temperature", id="temperature_tab"),
            Tab("Sweep1D", id="sweep1D_tab"),
            Tab("Sweep2D", id="sweep2D_tab"),
            Tab("Action Queue", id="queue_tab"),
        )

    def on_mount(self) -> None:
        """Focus the tabs when the app starts."""
        self.query_one(Tabs).focus()

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )


if __name__ == "__main__":
    app = Peppermint()
    app.run()
