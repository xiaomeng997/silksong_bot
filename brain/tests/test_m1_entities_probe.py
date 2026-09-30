"""Runs the m1_entities probe end to end against a fake oracle speaking IPC v1 (no game needed)."""
import socket
import threading
import time

import msgpack
import pytest

from ssbot.ipc.framing import BUTTONS, SCHEMA_VERSION, MsgType, encode, port
from ssbot.probes import m1_entities

INSTANCES = iter(range(931, 960))  # ports 47948+; far from the real instances, one per test (no port reuse)
STATES = ("Idle", "Walk", "Attack")


def _entity(frame: int) -> dict:
    state = STATES[(frame // 10) % 3]
    return {
        "iid": -500, "type_key": "Bone Hunter", "category": "enemy", "src": 3, "layer": 11,
        "pos": [10.0 + frame * 0.01, 5.0, 0.0], "vel": [0.6, 0.0], "gravity_scale": 1.0, "hp": 30, "is_dead": False,
        "inv": False, "fsms": [{"name": "Control", "state": state, "t": (frame % 10) / 60, "rt": (frame % 10) / 60}],
        "anim": {"clip": state, "frame": frame % 4, "n": 4}, "flipX": False, "render_aabb": [9.0, 4.0, 11.0, 6.5],
        "colliders": [{"kind": "box", "verts_world": [9.5, 4.0, 10.5, 4.0, 10.5, 6.0, 9.5, 6.0], "enabled": True,
                       "layer": 11, "damage": {"dealt": 1, "eff": 1, "hazard_type": 1, "flags": 0, "parry": 4,
                                               "parryable": False, "can_cause_damage": True}}],
    }


class FakeOracle:
    """enemies: put the enemy into "ents"; duplicate: list it twice in every 50th STATE (the dedupe bug)."""

    def __init__(self, enemies: bool = True, duplicate: bool = False):
        self.instance = next(INSTANCES)
        self.srv = socket.create_server(("127.0.0.1", port(self.instance)))
        self.enemies = enemies
        self.duplicate = duplicate
        self.all = False
        self.stop = threading.Event()
        self.seq = 0
        self.lock = threading.Lock()
        threading.Thread(target=self._serve, daemon=True).start()

    def _send(self, conn, t: MsgType, obj) -> None:
        with self.lock:
            self.seq += 1
            conn.sendall(encode(t, self.seq, msgpack.packb(obj, use_single_float=True)))

    def _serve(self) -> None:
        conn, _ = self.srv.accept()
        self._send(conn, MsgType.HELLO, {"role": "oracle", "schema": SCHEMA_VERSION, "plugin": "fake", "game": "1.0.30000",
                                         "instance": str(self.instance), "qpc_freq": 10_000_000,
                                         "rpcs": ["ping", "fsm.graph", "fsmtap.set", "ents.stats"], "buttons": list(BUTTONS)})
        threading.Thread(target=self._stream, args=(conn,), daemon=True).start()
        try:
            while not self.stop.is_set():
                n = int.from_bytes(self._recv(conn, 4), "little")
                body = self._recv(conn, n)
                if body[0] == MsgType.RPC_REQ:
                    req = msgpack.unpackb(body[8:], raw=False)
                    self._send(conn, MsgType.RPC_RES, {"id": req["id"], "ok": True, "result": self._rpc(req["name"], req["args"])})
        except (ConnectionError, OSError):
            pass

    @staticmethod
    def _recv(conn, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise ConnectionError
            buf += chunk
        return buf

    def _rpc(self, name: str, args: dict):
        if name == "fsmtap.set":
            self.all = args.get("all", self.all)
            return {"enabled": True, "all": self.all, "emitted": 0, "dropped": 0, "cached": 0}
        if name == "ents.stats":
            return {"included": 1}
        if name == "fsm.graph":
            g = {"iid": -500, "obj": "Bone Hunter", "fsm": "Control", "template": None, "start": "Idle", "active": "Walk",
                 "states": [{"name": s, "transitions": {"FINISHED": STATES[(i + 1) % 3]}, "actions": ["Wait"]}
                            for i, s in enumerate(STATES)],
                 "global": {}, "events": ["FINISHED"], "vars": {"float": {}, "int": {}, "bool": {}, "string": {}}}
            return g if args.get("fsm") else [g]
        return None

    def _stream(self, conn) -> None:
        f = 1000
        try:
            while not self.stop.is_set():
                f += 1
                ev = []
                if f % 10 == 0:
                    ev.append({"k": "fsm", "f": f, "q": f, "d": {
                        "iid": -500, "ent": -500, "obj": "Bone Hunter", "fsm": "Control",
                        "from": STATES[(f // 10 - 1) % 3], "to": STATES[(f // 10) % 3], "t_in_prev": 10 / 60,
                        "rt_in_prev": 10 / 60}})
                if self.all:
                    ev.append({"k": "fsm", "f": f, "q": f, "d": {"iid": 7, "ent": 7, "obj": "Lamp", "fsm": "FSM",
                                                                 "from": None, "to": "On", "t_in_prev": None,
                                                                 "rt_in_prev": None}})
                listed = [_entity(f)] if self.enemies else []
                if self.duplicate and f % 50 == 0:
                    listed.append(_entity(f))
                self._send(conn, MsgType.STATE, {
                    "f": f, "cost_us": 90, "drop": 0, "cost_ex": {"game": 5, "ents": 60}, "ev": ev,
                    "game": {"gs": 4, "scene": "Bone_04"}, "ents": listed})
                time.sleep(0.004)
        except OSError:
            pass


@pytest.fixture
def oracle():
    made = []

    def make(**kw) -> FakeOracle:
        made.append(FakeOracle(**kw))
        return made[-1]
    yield make
    for o in made:
        o.stop.set()
        o.srv.close()


def _run(monkeypatch, capsys, fake: FakeOracle, *extra: str) -> tuple[int, str]:
    monkeypatch.setattr("sys.argv", ["m1_entities", "--instance", str(fake.instance), "--seconds", "1", *extra])
    code = m1_entities.main()
    return code, capsys.readouterr().out


def test_probe_passes_on_consistent_stream(oracle, monkeypatch, capsys):
    code, out = _run(monkeypatch, capsys, oracle())
    assert code == 0
    assert "RESULT: PASS" in out
    assert "{'enemy': 1}" in out
    assert "fsm.graph Bone Hunter/Control" in out
    assert "FAIL" not in out
    assert "PASS  iids unique within each STATE" in out
    assert "PASS  damage colliders seen" in out
    assert "SKIP  hazards carry damage" in out


def test_probe_fails_on_duplicate_iids(oracle, monkeypatch, capsys):
    code, out = _run(monkeypatch, capsys, oracle(duplicate=True))
    assert code == 1
    assert "FAIL  iids unique within each STATE" in out


def test_probe_skips_without_enemies_but_fails_after_walking(oracle, monkeypatch, capsys):
    code, out = _run(monkeypatch, capsys, oracle(enemies=False))
    assert code == 0, out
    assert "SKIP  enemies in view" in out and "SKIP  damage colliders seen" in out
    code, out = _run(monkeypatch, capsys, oracle(enemies=False), "--walk", "0.3")
    assert code == 1
    assert "FAIL  enemies in view" in out and "FAIL  damage colliders seen" in out
