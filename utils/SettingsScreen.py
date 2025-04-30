from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header


class SettingsScreen(Screen):
    # BINDINGS = [("escape", "app.pop_screen", "Pop screen")]

    def __init__(self) -> None:
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
