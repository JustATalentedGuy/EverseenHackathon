"""A single-slot live frame buffer keeps slow inference from building a FIFO backlog."""
import threading
import time

class LatestFrame:
    def __init__(self,cap):
        self.cap=cap;self.lock=threading.Lock();self.latest=None;self.done=False;self.stopped=threading.Event();self.serial=0
        self.thread=threading.Thread(target=self._read,daemon=True);self.thread.start()
    def _read(self):
        try:
            while not self.stopped.is_set():
                ok,frame=self.cap.read()
                if not ok:break
                with self.lock:
                    self.latest=(self.serial,frame,time.monotonic());self.serial+=1
        finally:self.done=True
    def take(self):
        with self.lock:
            item=self.latest;self.latest=None;return item
    def close(self):
        self.stopped.set();self.cap.release();self.thread.join(timeout=1)
