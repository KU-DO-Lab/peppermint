from random import random
import subprocess
import threading
import time
import webbrowser

from bokeh.application.application import Application
from bokeh.application.handlers.function import FunctionHandler
from bokeh.document import Document
from bokeh.layouts import column
from bokeh.models import Button, Div, GridBox, ScrollBox
from bokeh.models.layouts import Column
from bokeh.palettes import RdYlBu3
from bokeh.plotting import figure, curdoc
from bokeh.server.server import Server


class bkapp():
    def __init__(self, port=5006) -> None:
        self._server: Server | None = None
        self._server_thread: threading.Thread | None = None
        self.port: int = port
        self._doc: Document | None = None
        self.layout: Column | GridBox | ScrollBox | None = None
        self.running = False
        self._browser_opened = False

    def create_app(self, doc):
        """Create the Bokeh application"""
        self._doc = doc

    def initialize(self):
        """Open browser and start server in own thread."""
        if self.running:
            print("Server is already running")
            return

        if not self._browser_opened:
            try:
                browser_thread = threading.Thread(target=lambda: webbrowser.open("http://localhost:5006"), daemon=True)
                browser_thread.start()
                self._browser_opened = True
            except Exception as e:
                print(f"Failed to start browser for plot application on port {self.port}: {e}")

        handler = FunctionHandler(self.create_app)
        app = Application(handler)

        def start_server():
            self._server = Server({'/': app}, port=self.port)
            self._server.start()
            self._server.show('/')

        self.server_thread = threading.Thread(target=start_server, daemon=True)
        self.server_thread.start()

    def attach_figure(self, fig: figure) -> None:
        """Call to attach a figure."""
        if self._doc:
            self._doc.add_root(fig)
