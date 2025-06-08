from sweep1d import *
import concurrent.futures

class ActionSequence:
    """Does the measuring.

    Encompasses the following tasks:
    (1) Sequentially operates to safely start any number of sweeps/sets, one at a time.
    (2) Automatically progress to the next action in the sequence.
    (3) Provides access to the satus of the sequence.
    """

    def __init__(self, sequence: list[Sweep1D]):
        self.sequence = sequence
        self.executor: None | concurrent.futures.ThreadPoolExecutor = None
        self.idx = -1 # Index of the sequence

    def start(self) -> None:
        if self.executor == None:
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def run(self) -> None:
        """Set up the sequence and run.

        Currently implemented as a concurrent.futures executor to avoid blocking.
        """
        if self.executor == None:
            ... # will have to work out how to notify properly here
        else:
            for (i, fn) in enumerate(self.sequence):
                future = self.executor.submit(fn.start)
                result = future.result()  # Blocks until the function is done
                self.idx = i

    def stop(self) -> None:
        """Totally stops the sequence. Requires status to be paused to prevent accidental stops."""
        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=True)
            self.executor = None
            self.idx = -1

    def status(self) -> tuple[str, int]:
        """Returns (running/idle, index)"""
        if self.executor == None: 
            return ("idle", -1)
        else:
            return ("running", self.idx)
