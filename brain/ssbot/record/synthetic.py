"""Synthetic oracle messages for offline tests and viewer demos (no game needed).

The base STATE fields mirror oracle/src/Export/FrameExporter.cs and BasicExporters.cs exactly; "hero", "ents" and
TERRAIN follow DESIGN §3.1.2 / §4.3 and are only a plausible shape: their real layout comes from the packages that
export them, which is why the viewer resolves them defensively.
"""
import math

import msgpack

from ssbot.ipc.framing import MsgType, encode

QPC_FREQ = 10_000_000


def hello(instance: str = "0") -> dict:
    return {"role": "oracle", "schema": 1, "plugin": "0.1.0", "game": "1.0.30000", "instance": instance,
            "qpc_freq": QPC_FREQ, "rpcs": ["ping"], "buttons": []}


def state(f: int, *, drop: int = 0, events: list | None = None, scene: str = "Tut_01", hero: bool = True,
          ents: bool = True, blk: int = 0, q0: int = 10_000_000_000) -> dict:
    t = f / 60.0
    s = {
        "f": f, "q": q0 + f * QPC_FREQ // 60, "fc": f * 5 // 6, "fs": 1, "udt": 1 / 60, "dt": 1 / 60, "ts": 1.0,
        "fdt": 0.02, "focus": False, "cost_us": 15 + f % 7, "drop": drop,
        "cost_ex": {"ctx": 1, "base": 4, "game": 5, "pause": 2, "enqueue": 3},
        "act": {"mask": 0, "ack": 0, "applied": -1, "target": -1, "stale": 0, "lost": False},
        "ev": events or [],
        "game": {"gs": 4, "ui": 5, "menu": 0, "paused": False, "slowed": 0, "transition": False, "entered": True,
                 "scene_raw": scene, "scene": scene, "gate": "left1", "next": scene, "additive": [scene],
                 "memory": False, "pd_mode": 0, "t_live": 100.0 + t, "t_saved": 100.0, "t_sess": t, "t_start": 0.0,
                 "cheat": 0},
        "pause": {"blk": blk, "dsq": False, "dinv": False, "inv": False, "bench": False, "interact": False,
                  "preload": False, "hero_input": True},
    }
    if hero:
        s["hero"] = {"pos": [20.0 + 5 * math.sin(t), 10.0 + abs(math.sin(2 * t))], "vel": [5 * math.cos(t), 0.0],
                     "facing": 1, "health": 5 - (f // 300) % 3, "maxHealth": 5, "healthBlue": 0,
                     "silk": (f // 60) % 10, "silk_max": 9}
    if ents:
        x = 30.0 + 3 * math.cos(t)
        s["ents"] = [{"iid": 1, "type_key": "Crawler", "category": "enemy", "pos": [x, 9.0], "hp": 10,
                      "colliders": [{"shape": "box", "enabled": True, "damage": {"dealt": 1},
                                     "verts": [[x - .5, 8.5], [x + .5, 8.5], [x + .5, 9.5], [x - .5, 9.5]]}]}]
    return s


def camera(x: float, y: float, *, screen: tuple[int, int] = (1280, 720), ppu: float = 40.0, dist: float = 38.1
           ) -> dict:
    """STATE "cam" of a perspective camera at (x, y, -dist) looking along +z, like the game's main camera, scaled so a
    unit on the z = 0 plane spans `ppu` px. V/P are column-major (CameraExporter.WriteMatrix): V = worldToCameraMatrix
    (camera space looks down -z), P = OpenGL-style projectionMatrix."""
    w, h = screen
    f = 2.0 * dist * ppu / h           # cot(fov / 2): ppu = f * h / (2 * dist) on the z = 0 plane
    near, far = 0.3, 1000.0
    V = [[1, 0, 0, -x], [0, 1, 0, -y], [0, 0, -1, -dist], [0, 0, 0, 1]]
    P = [[f * h / w, 0, 0, 0], [0, f, 0, 0], [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)],
         [0, 0, -1, 0]]

    def col_major(m):
        return [float(m[r][c]) for c in range(4) for r in range(4)]

    return {"src": 1, "cb_us": 1.0, "V": col_major(V), "P": col_major(P), "pos": [x, y, -dist],
            "pos_eof": [x, y, -dist], "shake": [0.0, 0.0], "rect": [0.0, 0.0, 1.0, 1.0],
            "pixel_rect": [0.0, 0.0, float(w), float(h)], "rt": None, "screen": [float(w), float(h)],
            "fov": math.degrees(2 * math.atan(1 / f)), "ortho": False, "ortho_size": 5.0, "is_camera_main": True}


def terrain(scene: str = "Tut_01") -> dict:
    return {"scene": scene, "variant": "",
            "solids": [[[0, 0], [60, 0], [60, 8], [0, 8]], [[0, 8], [2, 8], [2, 30], [0, 30]]],
            "hazards": [{"type": 2, "verts": [[40, 8], [44, 8], [44, 8.5], [40, 8.5]]}]}


def progress() -> dict:
    return {"skills": {"dash": True}, "rosaries": 120}


def wire(msg_type: MsgType, seq: int, payload: dict) -> bytes:
    return encode(msg_type, seq, msgpack.packb(payload))


def stream(frames: range, *, skip: set[int] = frozenset(), drop_at: dict[int, int] | None = None,
           terrain_at: tuple[int, ...] = (), event_every: int = 0):
    """Yields (msg_type, wire frame) like OracleLink.subscribe_raw would, in arrival order."""
    seq = 0
    drops = 0
    for f in frames:
        if drop_at and f in drop_at:
            drops = drop_at[f]
        if f in terrain_at:
            seq += 1
            yield MsgType.TERRAIN, wire(MsgType.TERRAIN, seq, terrain())
        if f in skip:
            continue
        evs = [{"k": "TEST", "f": f, "q": 0, "d": {"i": f, "b": b"\x00\x01"}}] if event_every and f % event_every == 0 else []
        seq += 1
        yield MsgType.STATE, wire(MsgType.STATE, seq, state(f, drop=drops, events=evs, blk=5 if f % 120 < 15 else 0))
