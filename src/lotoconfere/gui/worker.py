"""Running a check without freezing the window.

Every call into the service goes through here, because all of them can reach the
network and a teimosinha of 24 contests is 24 requests with a pause between
them. The window stays live, reports progress per contest, and can be told to
stop.

The worker never touches a widget. It emits what it found and the window draws
it, which is the only arrangement Qt allows and also the only one that keeps the
GUI thin.
"""

import threading
from collections.abc import Callable, Iterator

from PySide6.QtCore import QObject, QThread, Signal

from lotoconfere.service import ContestResult


class RunWorker(QObject):
    """Consumes an iterator of contest results on a worker thread."""

    found = Signal(object)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, produce: Callable[[], Iterator[ContestResult]]) -> None:
        super().__init__()
        self._produce = produce

    def run(self) -> None:
        try:
            for answer in self._produce():
                self.found.emit(answer)
        except Exception as error:
            # A worker thread that raises takes the whole app down with it, and
            # the person is left with a window that stopped. Anything unexpected
            # becomes a message instead.
            self.failed.emit(str(error))
        self.finished.emit()


class Job:
    """One running check: its thread, its worker, and the way to stop it.

    Kept as an object rather than a pile of attributes on the window because the
    thread has to outlive the function that started it, and forgetting that is
    how Qt segfaults.
    """

    def __init__(self, produce: Callable[[threading.Event], Iterator[ContestResult]]) -> None:
        self.cancel = threading.Event()
        self.thread = QThread()
        self.worker = RunWorker(lambda: produce(self.cancel))
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        # No setParent here: Qt refuses a parent that lives in another thread,
        # and an object moved to a thread must not have one. What keeps the
        # worker alive is this Job holding it, and the screen holding the Job.

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        """Ask it to stop at the next contest boundary, and wait for it."""
        self.cancel.set()
        self.thread.quit()
        self.thread.wait(5000)

    def running(self) -> bool:
        return bool(self.thread.isRunning())
