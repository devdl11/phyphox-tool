import socket
import json
import threading
from queue import Queue, Empty
import time


class PhyClosed(BaseException):
    pass


class Phyclient:
    TIMEMOUT = 5

    def __init__(self, port):
        self.port = port
        self.address = "127.0.0.1"
        self.doRun = False
        self.thread: threading.Thread or None = None
        self.queue = Queue()
        self.timeout = 0
        self.didReceiveData = False

    def _backgroundThread(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listener.bind((self.address, self.port))
        listener.settimeout(2)
        while self.doRun:
            try:
                data, remote = listener.recvfrom(2**13)
            except TimeoutError:
                if not self.didReceiveData:
                    continue
                self.timeout += 2
                if self.timeout > Phyclient.TIMEMOUT:
                    self.doRun = False
                continue
            if len(data) < 2**2:
                continue
            if not self.didReceiveData:
                self.didReceiveData = True
            self.queue.put(json.loads(data))

    def runListener(self):
        self.doRun = True
        self.thread = threading.Thread(target=self._backgroundThread, daemon=True)
        self.thread.start()

    def stopListener(self):
        self.doRun = False
        self.thread.join()

    def getData(self):
        while True:
            try:
                return self.queue.get(timeout=2)
            except (TimeoutError, Empty):
                if not self.doRun and self.timeout > Phyclient.TIMEMOUT:
                    raise PhyClosed
