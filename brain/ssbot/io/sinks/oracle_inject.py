"""Training sink: send key sets to SsOracle over its M0 line protocol (127.0.0.1:47631).

The plugin latches the requested set once per frame and feeds it to the Input System, so the game
does not need focus. Replaced by the framed protocol in M1.
"""
import json
import socket
import time

PORT = 47631


class OracleClient:
    def __init__(self, host: str = "127.0.0.1", port: int = PORT, timeout_s: float = 2.0):
        self.sock = socket.create_connection((host, port), timeout=timeout_s)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.file = self.sock.makefile("rw", encoding="utf-8", newline="\n")

    def _call(self, line: str) -> str:
        self.file.write(line + "\n")
        self.file.flush()
        reply = self.file.readline().strip()
        if reply.startswith("err"):
            raise RuntimeError(f"{line!r}: {reply}")
        return reply

    def keys(self, *names: str) -> None:
        self._call("keys " + ",".join(names))

    def own(self, on: bool) -> None:
        self._call("own " + ("on" if on else "off"))

    def state(self) -> dict:
        return json.loads(self._call("state"))

    def tap(self, name: str, hold_s: float = 0.1) -> None:
        self.keys(name)
        time.sleep(hold_s)
        self.keys()

    def wait_for(self, pred, timeout_s: float, poll_s: float = 1 / 60) -> dict:
        deadline = time.perf_counter() + timeout_s
        while True:
            s = self.state()
            if pred(s):
                return s
            if time.perf_counter() > deadline:
                raise TimeoutError(f"condition not met within {timeout_s}s; last state {s}")
            time.sleep(poll_s)

    def close(self) -> None:
        try:
            self.keys()
        finally:
            self.sock.close()
