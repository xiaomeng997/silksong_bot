"""Compact per-fight caches of the Forum recordings (M2 Forum round R0, docs/plans/forum_planner_plan.md §5): one pass
over a fight's STATEs keeps what the offline Forum products (ssbot.knowledge.forum_products), the support recall
(ssbot.tools.support_recall --encounter Forum) and the open-loop replay (ssbot.tools.forum_simul) read, so they do not
decode the recordings again.

    cache = extract_fight(fight)                 # behaviour_tables.Fight; about 10 s for a 15-min gauntlet
    save_cache(cache, path); cache = load_cache(path)

Arrays (F frames, E entity rows, C collider rows, A ally rows; float32 unless noted):
  f (int64), T (float64: game time since the fight's first frame, the scanner's clock: dt x frame gap), dt
  hero: hx hy hvx hvy, hbox [F, 4] (STATE hero.box, the physics box), hface (int8), hclip (int16, `names`)
  e_fi (int32 frame index), e_iid (int64), e_tk (int16, `types`), e_x e_y e_vx e_vy, e_flip (int8), e_st (int16,
     `states`: the first FSM's state), e_tin (its time in state), e_hp (nan: none), e_hidden (int8), e_box [E, 4]
     (bounding box of the enabled damage colliders: support_threat or multi-hit; nan: none), e_parry (int8: OR of
     their parry bits), e_mw (int8: a multi-hit collider is among them)
  c_ei (int32 entity row), c_name (int16, `names`), c_box [C, 4], c_parry (int8), c_dealt (int8), c_eff (int8):
     every enabled damage collider of those rows
  a_fi, a_iid (int64), a_name (int16, `names`), a_x a_y a_vx, a_st (int16, `states`), a_box [A, 4], a_scale (int8):
     the oracle's allies export (Garmond Fighter, Cogfly), when the recording has it
  types, states, names: string tables; events: the fight's events of EVENT_KINDS as (frame, kind, data) JSON
  meta: fight id, recording, f0, f1, outcome
"""
import gzip
import json
import math
from pathlib import Path

import numpy as np

from ssbot.ipc.ents import DAMAGE_SRC, SRC_BITS
from ssbot.knowledge.behaviour_tables import Fight, fight_states, multi_wounder_threat, support_threat

EVENT_KINDS = ("fsm", "damage", "damage_blocked", "hit", "freeze", "special_damage", "catastrophe", "harness")
STATE_KEYS = ("dt", "hero", "ents", "ev", "allies")
NAN4 = (math.nan,) * 4


class _Tab:
    def __init__(self):
        self.idx: dict[str, int] = {}

    def __call__(self, s) -> int:
        if s is None:
            return -1
        s = str(s)
        i = self.idx.get(s)
        if i is None:
            i = self.idx[s] = len(self.idx)
        return i

    def array(self) -> np.ndarray:
        return np.array(list(self.idx), dtype=object)


def _box(verts) -> tuple:
    if not verts or len(verts) < 2:
        return NAN4
    xs, ys = verts[0::2], verts[1::2]
    return (min(xs), min(ys), max(xs), max(ys))


def extract_states(states, meta: dict | None = None) -> dict:
    """The cache arrays of a stream of STATE dicts (keys STATE_KEYS)."""
    types, sts, names = _Tab(), _Tab(), _Tab()
    F, T, DT, HX, HY, HVX, HVY, HB, HF, HC = [], [], [], [], [], [], [], [], [], []
    E = {k: [] for k in ("fi", "iid", "tk", "x", "y", "vx", "vy", "flip", "st", "tin", "hp", "hidden", "box", "parry",
                         "mw")}
    C = {k: [] for k in ("ei", "name", "box", "parry", "dealt", "eff")}
    A = {k: [] for k in ("fi", "iid", "name", "x", "y", "vx", "st", "box", "scale")}
    events: list = []
    last_f, t = None, 0.0
    for s in states:
        f = s.get("f")
        if not isinstance(f, int) or (last_f is not None and f <= last_f):
            continue
        dt = float(s.get("dt") or 0.0)
        if last_f is not None:
            t += dt * (f - last_f)
        last_f = f
        fi = len(F)
        F.append(f)
        T.append(t)
        DT.append(dt)
        h = s.get("hero") or {}
        p, v = h.get("pos") or (math.nan, math.nan), h.get("vel") or (math.nan, math.nan)
        HX.append(p[0])
        HY.append(p[1])
        HVX.append(v[0])
        HVY.append(v[1])
        b = h.get("box")
        HB.append(tuple(b[:4]) if b else NAN4)
        HF.append(int(h.get("facing") or 0))
        HC.append(names((h.get("anim") or {}).get("clip")))
        for e in s.get("ents") or ():
            if not int(e.get("src") or 0) & DAMAGE_SRC:
                continue
            ei = len(E["fi"])
            fs = e.get("fsms") or ()
            E["fi"].append(fi)
            E["iid"].append(int(e["iid"]))
            E["tk"].append(types(e.get("type_key")))
            pos, vel = e.get("pos") or (math.nan, math.nan), e.get("vel") or (math.nan, math.nan)
            E["x"].append(pos[0])
            E["y"].append(pos[1])
            E["vx"].append(vel[0])
            E["vy"].append(vel[1])
            E["flip"].append(1 if e.get("flipX") else 0)
            E["st"].append(sts(fs[0].get("state")) if fs else -1)
            E["tin"].append(float(fs[0].get("t") or 0.0) if fs else math.nan)
            E["hp"].append(math.nan if e.get("hp") is None else float(e["hp"]))
            E["hidden"].append(1 if e.get("hidden") else 0)
            bx, par, mw = None, 0, 0
            for c in e.get("colliders") or ():
                st_ = support_threat(c)
                mw_ = multi_wounder_threat(c) and bool(int(e.get("src") or 0) & SRC_BITS["multi_wounder"])
                if not (st_ or mw_):
                    continue
                cb = _box(c.get("verts_world"))
                if math.isnan(cb[0]):
                    continue
                d = c.get("damage") or {}
                C["ei"].append(ei)
                C["name"].append(names(c.get("name")))
                C["box"].append(cb)
                C["parry"].append(int(d.get("parry") or 0))
                C["dealt"].append(int(d.get("dealt") or 0))
                C["eff"].append(int(d.get("eff") or 0))
                par |= int(d.get("parry") or 0)
                mw |= int(mw_ and not d.get("dealt"))
                bx = cb if bx is None else (min(bx[0], cb[0]), min(bx[1], cb[1]), max(bx[2], cb[2]),
                                            max(bx[3], cb[3]))
            E["box"].append(bx or NAN4)
            E["parry"].append(par)
            E["mw"].append(mw)
        for a in s.get("allies") or ():
            p = a.get("pos") or (math.nan, math.nan)
            A["fi"].append(fi)
            A["iid"].append(int(a.get("iid") or 0))
            A["name"].append(names(a.get("name")))
            A["x"].append(p[0])
            A["y"].append(p[1])
            A["vx"].append((a.get("vel") or (math.nan,))[0])
            A["st"].append(sts(a.get("state")))
            b = a.get("box")
            A["box"].append(tuple(b[:4]) if b else NAN4)
            A["scale"].append(int(np.sign(a.get("scale_x") or 0)))
        for ev in s.get("ev") or ():
            if ev.get("k") in EVENT_KINDS:
                events.append((int(ev.get("f", f)), ev["k"], ev.get("d") or {}))
    f32 = lambda v: np.asarray(v, np.float32)  # noqa: E731
    out = {
        "f": np.asarray(F, np.int64), "T": np.asarray(T, np.float64), "dt": f32(DT), "hx": f32(HX), "hy": f32(HY),
        "hvx": f32(HVX), "hvy": f32(HVY), "hbox": f32(HB).reshape(-1, 4), "hface": np.asarray(HF, np.int8),
        "hclip": np.asarray(HC, np.int16),
        "e_fi": np.asarray(E["fi"], np.int32), "e_iid": np.asarray(E["iid"], np.int64),
        "e_tk": np.asarray(E["tk"], np.int16), "e_x": f32(E["x"]), "e_y": f32(E["y"]), "e_vx": f32(E["vx"]),
        "e_vy": f32(E["vy"]), "e_flip": np.asarray(E["flip"], np.int8), "e_st": np.asarray(E["st"], np.int16),
        "e_tin": f32(E["tin"]), "e_hp": f32(E["hp"]), "e_hidden": np.asarray(E["hidden"], np.int8),
        "e_box": f32(E["box"]).reshape(-1, 4), "e_parry": np.asarray(E["parry"], np.int8),
        "e_mw": np.asarray(E["mw"], np.int8),
        "c_ei": np.asarray(C["ei"], np.int32), "c_name": np.asarray(C["name"], np.int16),
        "c_box": f32(C["box"]).reshape(-1, 4), "c_parry": np.asarray(C["parry"], np.int8),
        "c_dealt": np.asarray(C["dealt"], np.int8), "c_eff": np.asarray(C["eff"], np.int8),
        "a_fi": np.asarray(A["fi"], np.int32), "a_iid": np.asarray(A["iid"], np.int64),
        "a_name": np.asarray(A["name"], np.int16), "a_x": f32(A["x"]), "a_y": f32(A["y"]), "a_vx": f32(A["vx"]),
        "a_st": np.asarray(A["st"], np.int16), "a_box": f32(A["box"]).reshape(-1, 4),
        "a_scale": np.asarray(A["scale"], np.int8),
        "types": types.array(), "states": sts.array(), "names": names.array(),
    }
    out["events"] = events
    out["meta"] = dict(meta or {})
    return out


def extract_fight(fight: Fight) -> dict:
    meta = {"id": fight.id, "path": str(fight.path), "f0": fight.f0, "f1": fight.f1, "outcome": fight.outcome}
    return extract_states(fight_states(fight, keys=STATE_KEYS), meta)


def cache_name(fight_id: str) -> str:
    return fight_id.replace("/", "__") + ".npz"


def save_cache(cache: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {k: (v.astype(str) if v.dtype == object else v) for k, v in cache.items()
              if isinstance(v, np.ndarray)}
    np.savez_compressed(path, **arrays)
    side = path.with_suffix(".json.gz")
    with gzip.open(side, "wt", encoding="utf-8") as fh:
        json.dump({"meta": cache.get("meta") or {}, "events": cache.get("events") or []}, fh)
    return path


def load_cache(path: Path) -> dict:
    path = Path(path)
    with np.load(path, allow_pickle=False) as z:
        out = {k: z[k] for k in z.files}
    for k in ("types", "states", "names"):
        out[k] = [str(x) for x in out[k]]
    with gzip.open(path.with_suffix(".json.gz"), "rt", encoding="utf-8") as fh:
        side = json.load(fh)
    out["meta"] = side["meta"]
    out["events"] = [tuple(e) for e in side["events"]]
    return out


def frame_index(cache: dict) -> dict[int, int]:
    """Frame number -> row of the frame arrays."""
    return {int(f): i for i, f in enumerate(cache["f"])}
