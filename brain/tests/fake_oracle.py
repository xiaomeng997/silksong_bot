"""A minimal IPC v1 oracle over real TCP for offline tests (and for dry-running probes without the game):
sends HELLO, waits for the brain's HELLO, then streams synthetic STATE frames; answers ping and symbols.check, and
with marker=True frame.marker (the STATEs then carry "mk" while it is on, at the vision mask's place of a 1280x720
client).

    python tests/fake_oracle.py --instance 7 --fps 60        # then: python -m ssbot.probes.m1_record --instance 7
"""
import argparse
import socket
import sys
import threading
import time
from pathlib import Path

import msgpack

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ssbot.ipc.framing import BASE_PORT, BUTTONS, HEADER, MsgType, encode  # noqa: E402
from ssbot.record import synthetic as syn  # noqa: E402
from ssbot.vision import mask as vmask  # noqa: E402


class FakeOracle:
    def __init__(self, port: int = 0, fps: float = 0.0, skip: set[int] = frozenset(), terrain_at: tuple = (),
                 symbols: object = None, marker: bool = False):
        self.srv = socket.create_server(("127.0.0.1", port))
        self.port = self.srv.getsockname()[1]
        self.instance = self.port - BASE_PORT
        self.fps = fps
        self.skip = set(skip)
        self.terrain_at = terrain_at
        self.symbols = {"ok": True, "total": 3, "failed": []} if symbols is None else symbols
        self.marker = marker
        self.mk: dict | None = None        # STATE "mk" while the marker is on
        self.rpcs: list[tuple[str, dict]] = []
        self.go = threading.Event()        # start streaming STATE
        self.brain_hello = threading.Event()
        self.sent: list[bytes] = []
        self.seq = 0
        self.lock = threading.Lock()
        self.conn: socket.socket | None = None
        self.stop = threading.Event()
        threading.Thread(target=self._serve, daemon=True).start()

    def _send(self, t: MsgType, payload: dict) -> bytes:
        with self.lock:
            self.seq += 1
            raw = encode(t, self.seq, msgpack.packb(payload))
            self.conn.sendall(raw)
            return raw

    def _serve(self) -> None:
        self.conn, _ = self.srv.accept()
        h = syn.hello(str(self.instance))
        h["buttons"] = list(BUTTONS)
        h["rpcs"] = ["ping", "symbols.check"] + (["frame.marker"] if self.marker else [])
        self._send(MsgType.HELLO, h)
        threading.Thread(target=self._read, daemon=True).start()
        self.brain_hello.wait(10)

    def _read(self) -> None:
        try:
            while not self.stop.is_set():
                head = self._recv(4)
                body = self._recv(int.from_bytes(head, "little"))
                t = body[0]
                payload = msgpack.unpackb(body[HEADER.size - 4:], raw=False)
                if t == MsgType.HELLO:
                    self.brain_hello.set()
                elif t == MsgType.RPC_REQ:
                    name = payload["name"]
                    self.rpcs.append((name, payload.get("args") or {}))
                    if name == "ping":
                        res = {"id": payload["id"], "ok": True, "result": "pong"}
                    elif name == "symbols.check":
                        res = {"id": payload["id"], "ok": True, "result": self.symbols}
                    elif name == "frame.marker" and self.marker:
                        args = payload.get("args") or {}
                        cell = args.get("size") or vmask.cell_px(720)
                        self.mk = {"drawn": True, "corner": "tr", "cell": cell, "grid": [2, 12], "us": 1.0,
                                   "rect": [float(v) for v in vmask.marker_rect(1280, 720, "tr", cell)]} \
                            if args.get("on") else None
                        res = {"id": payload["id"], "ok": True, "result": {"on": self.mk is not None, "corner": "tr",
                                                                            "cell": cell}}
                    else:
                        res = {"id": payload["id"], "ok": False, "error": f"unknown rpc '{name}'"}
                    self._send(MsgType.RPC_RES, res)
        except (OSError, ConnectionError):
            pass

    def _recv(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.conn.recv(n - len(buf))
            if not chunk:
                raise ConnectionError
            buf += chunk
        return buf

    def stream(self, frames: range) -> None:
        """Send STATE (and TERRAIN) frames once go is set; paced at fps if > 0."""
        self.go.wait(10)
        period = 1 / self.fps if self.fps else 0
        t = time.perf_counter()
        for f in frames:
            if self.stop.is_set():
                return
            try:
                if f in self.terrain_at:
                    self.sent.append(self._send(MsgType.TERRAIN, syn.terrain()))
                if f not in self.skip:
                    s = syn.state(f)
                    s["mk"] = self.mk
                    self.sent.append(self._send(MsgType.STATE, s))
            except OSError:  # the brain went away
                return
            if period:
                t += period
                time.sleep(max(0.0, t - time.perf_counter()))

    def close(self) -> None:
        self.stop.set()
        for s in (self.conn, self.srv):
            try:
                s and s.close()
            except OSError:
                pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", type=int, default=7)
    ap.add_argument("--fps", type=float, default=60.0)
    ap.add_argument("--seconds", type=float, default=3600)
    a = ap.parse_args()
    fo = FakeOracle(BASE_PORT + a.instance, fps=a.fps, terrain_at=(1000,))
    print(f"fake oracle on {fo.port}")
    fo.brain_hello.wait()
    time.sleep(0.5)  # let the brain subscribe
    fo.go.set()
    fo.stream(range(1000, 1000 + int(a.seconds * a.fps)))
