"""Brain-side client for the oracle IPC v1 (DESIGN §4.6).

A reader thread receives every message: the newest STATE is kept for polling, and optional subscribers (the
recorder) get every raw STATE frame in order. ACTIONs and RPCs can be sent from any thread.

    link = OracleLink(instance=0)
    s = link.wait_state(lambda s: s["game"]["gs"] == 4)
    link.act(link.frame + 2, mask("right"), hold_frames=30)
    link.rpc("ping")
"""
import socket
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future

import msgpack

from ssbot.ipc.framing import BUTTONS, HEADER, MAX_MESSAGE, SCHEMA_VERSION, MsgType, encode, port


class OracleError(RuntimeError):
    pass


class OracleLink:
    def __init__(self, instance: int = 0, host: str = "127.0.0.1", connect_timeout_s: float = 30.0):
        deadline = time.monotonic() + connect_timeout_s
        while True:
            try:
                self.sock = socket.create_connection((host, port(instance)), timeout=2.0)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock.settimeout(None)
        self._send_lock = threading.Lock()
        self._seq = 0
        self._rpc_id = 0
        self._rpc: dict[int, Future] = {}
        self._state_cv = threading.Condition()
        self._state: dict | None = None
        self._raw_subscribers: list[Callable[[int, bytes], None]] = []
        self._state_subscribers: list[Callable[[dict], None]] = []
        self.hello: dict | None = None
        self._hello_event = threading.Event()
        self.closed = False
        self._reader = threading.Thread(target=self._read_loop, name="OracleLink.read", daemon=True)
        self._reader.start()
        if not self._hello_event.wait(10):
            raise OracleError("no HELLO from the oracle")
        if self.hello.get("schema") != SCHEMA_VERSION:
            raise OracleError(f"schema mismatch: oracle {self.hello.get('schema')} != {SCHEMA_VERSION}")
        if tuple(self.hello.get("buttons", ())) != BUTTONS:
            raise OracleError("button table mismatch between oracle and brain")
        self._send(MsgType.HELLO, msgpack.packb({"role": "brain", "schema": SCHEMA_VERSION}))

    # ---- receiving -------------------------------------------------------------------------------------

    def subscribe_raw(self, fn: Callable[[int, bytes], None]) -> None:
        """fn(msg_type, whole_frame_bytes) for every STATE/TERRAIN/PROGRESS message, on the reader thread."""
        self._raw_subscribers.append(fn)

    def subscribe_state(self, fn: Callable[[dict], None]) -> None:
        """fn(state) for every decoded STATE, in order, on the reader thread (keep it short: it delays the reader).
        Unlike `state`/wait_state, which only see the latest STATE, no frame and so no event ("ev") is skipped."""
        self._state_subscribers.append(fn)

    def _recv_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("oracle closed the connection")
            buf += chunk
        return bytes(buf)

    def _read_loop(self) -> None:
        try:
            while True:
                head = self._recv_exact(4)
                length = int.from_bytes(head, "little")
                if length < HEADER.size - 4 or length > MAX_MESSAGE:
                    raise OracleError(f"bad frame length {length}")
                body = self._recv_exact(length)
                msg_type = body[0]
                payload = body[HEADER.size - 4:]
                if msg_type in (MsgType.STATE, MsgType.TERRAIN, MsgType.PROGRESS):
                    for fn in self._raw_subscribers:
                        fn(msg_type, head + body)
                if msg_type == MsgType.STATE:
                    state = msgpack.unpackb(payload, raw=False, strict_map_key=False)
                    for fn in self._state_subscribers:
                        fn(state)
                    with self._state_cv:
                        self._state = state
                        self._state_cv.notify_all()
                elif msg_type == MsgType.HELLO:
                    self.hello = msgpack.unpackb(payload, raw=False)
                    self._hello_event.set()
                elif msg_type == MsgType.RPC_RES:
                    res = msgpack.unpackb(payload, raw=False, strict_map_key=False)
                    fut = self._rpc.pop(res.get("id"), None)
                    if fut is not None:
                        if res.get("ok"):
                            fut.set_result(res.get("result"))
                        else:
                            fut.set_exception(OracleError(str(res.get("error"))))
        except (ConnectionError, OSError, OracleError) as e:
            self.closed = True
            for fut in list(self._rpc.values()):
                fut.set_exception(OracleError(f"link closed: {e}"))
            with self._state_cv:
                self._state_cv.notify_all()

    # ---- state -----------------------------------------------------------------------------------------

    @property
    def state(self) -> dict | None:
        return self._state

    @property
    def frame(self) -> int:
        return self._state["f"] if self._state else -1

    def wait_state(self, pred: Callable[[dict], bool] = lambda s: True, timeout_s: float = 10.0,
                   newer_than: int | None = None) -> dict:
        """Block until a STATE satisfies pred (and has frame > newer_than, if given). Missing keys count as False."""
        deadline = time.monotonic() + timeout_s
        with self._state_cv:
            while True:
                s = self._state
                if s is not None and (newer_than is None or s["f"] > newer_than):
                    try:
                        if pred(s):
                            return s
                    except (KeyError, TypeError):
                        pass
                left = deadline - time.monotonic()
                if left <= 0 or self.closed:
                    raise TimeoutError(f"state condition not met within {timeout_s}s (last frame {self.frame})")
                self._state_cv.wait(left)

    # ---- sending ---------------------------------------------------------------------------------------

    def _send(self, msg_type: MsgType, payload: bytes) -> None:
        with self._send_lock:
            self._seq += 1
            self.sock.sendall(encode(msg_type, self._seq, payload))

    def act(self, target_frame: int, buttons: int, hold_frames: int = 0, ack_seq: int = 0, flags: int = 0) -> None:
        """Hold exactly `buttons` from target_frame on (for hold_frames frames if > 0). flags: framing.ACTION_*
        (sent as a fifth element only when set)."""
        body = [target_frame, buttons, hold_frames, ack_seq] + ([flags] if flags else [])
        self._send(MsgType.ACTION, msgpack.packb(body))

    def rpc_async(self, name: str, /, **args) -> Future:
        fut: Future = Future()
        with self._send_lock:
            self._rpc_id += 1
            rid = self._rpc_id
        self._rpc[rid] = fut
        self._send(MsgType.RPC_REQ, msgpack.packb({"id": rid, "name": name, "args": args}))
        return fut

    def rpc(self, name: str, /, timeout_s: float = 10.0, **args):
        return self.rpc_async(name, **args).result(timeout_s)

    def close(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
