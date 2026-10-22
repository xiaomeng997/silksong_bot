"""Map v2 stage M0 calibration probe (docs/plans/forum_map_v2.md section 2, M0): forced setups on Forum_W_w7 (one
Clapper, Wanderer) that put Hornet in each situation the hero model has to know, recorded for ssbot.tools.m0_calib.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.probes.m0_probe --instance 0 --savestate fo_cl_w7w \
        --exps fl_atk,fl_claw,drift,claw_air,claw_gnd,dash_g,ds_whiff --trials 300 --seed 8100000 \
        [--out C:/ssbot/data/runs/m2/map2_m0]
    ../scripts/uv.cmd run python -m ssbot.probes.m0_probe --instance 1 --savestate fo_cl_w7w \
        --exps pogo,side,hook --trials 120 --seed 8200000

Hero-only experiments run in the ~4 s before the Clapper drops in (one trial per savestate load, the hero placed with
randomize_start's dx), so nothing hooks, hits or locks her:
  fl_atk    jump, open the umbrella, float t frames with a drift key, then the attack (down + attack, some side):
            'held' (jump still held), 'rel0' (jump released on the press frame), 'relk' (jump released k = 1..12
            frames before the press, a key g during the gap), 'infl' (pressed in the Inflate, jump held).
  fl_claw   the same with the Clawline: 'held', 'rel0', 'relk', 'infl', 'antic' (in the Umbrella Inflate Antic).
  drift     the float alone: the antic's key, then 2-4 key segments (none / toward / away) over 30-75 frames, then
            the release with a key during the Deflate; vx per frame against UmbrellaMotionX.
  claw_air  a jump, the Clawline pressed k frames after the take-off (vy +18 .. -25, a fall from the apex included),
            no target in its ray (the unhooked pull); at control + j a second action: the Clawline again, the down
            slash, the air dash, the umbrella or nothing.
  claw_gnd  the Clawline from standing, then the same second actions.
  dash_g    the ground dash twice, j = 4..40 frames apart (its cooldown), or held into the sprint (its speed profile)
            and released (the skid).
  ds_whiff  the down slash in the air with nothing below, a second press j = 12..24 frames after the first (the
            cadence after a whiff), and side slashes the same.
Clapper experiments (after its Roar; many per load; the load is renewed when its HP drops below 60):
  pogo      a full jump over its head and the down slash on it; then at j frames after the press the second down
            slash (the cadence after a pogo hit), the air dash (does a pogo give it back?) or nothing (the bounce and
            its i-frames).
  side      a low hop beside its body (her box 0.1 - 1.4 u clear of its body box) and the down slash into its side:
            a full bounce or not, the i-frames.
  hook      the Clawline at it while it is Idle (or walking) from the ground, 3 - 9.5 u away: the needle's hit, the
            dash, the damage and its Control FSM's next move (the 12-18 f reaction).
Every trial is one line of <recording>/m0_trials.jsonl (the experiment, its parameters, the frames). The hero is
made invincible after every load (PlayerData isInvincible through the debug line server, port 47631 + instance) and
her silk is kept at 9 (silk is not a constraint), so no hit or knock-back spoils a setup.

Safety: a free training instance (instances 0 / 1); save suppression on; the probe stops at STOP_AGENTS,
HUMAN_PRACTICE, DEMO_SOON (re-appearing during the block) or C:\\ssbot\\sandbox\\m0_probe.stop.
"""
from __future__ import annotations

import argparse
import json
import random
import socket
import sys
import time
from pathlib import Path

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleLink

M_L, M_R, M_U, M_D = mask("left"), mask("right"), mask("up"), mask("down")
M_J, M_A, M_DASH, M_CLAW = mask("jump"), mask("attack"), mask("dash"), mask("clawline")
CLAPPER = "Song Heavy Sentry"
INTRO = (None, "Init", "Rest", "Drop Antic", "Notify", "Drop In", "Enter Land", "Roar")
FLOOR = 3.015                    # the Forum floor (the standing box bottom)
WALL_L, WALL_R = 14.01, 48.99
X0 = 33.77                       # her x after fo_cl_w7w's load
HERO_EXPS = ("fl_atk", "fl_claw", "drift", "claw_air", "claw_gnd", "dash_g", "ds_whiff")
CLAP_EXPS = ("pogo", "side", "hook")
STOP_FILES = (r"C:\ssbot\sandbox\STOP_AGENTS", r"C:\ssbot\sandbox\HUMAN_PRACTICE", r"C:\ssbot\sandbox\DEMO_SOON",
              r"C:\ssbot\sandbox\m0_probe.stop")
PRE_SPAWN_F = 225                # frames after the load's first input frame that a hero-only trial may use


def stop_requested() -> str | None:
    for p in STOP_FILES:
        if Path(p).exists():
            return p
    return None


# ---- STATE readers ----------------------------------------------------------------------------------------------

def hero(s: dict) -> dict:
    return s.get("hero") or {}


def hx(s: dict) -> float:
    b = hero(s).get("box") or [0, 0, 0, 0]
    return 0.5 * (b[0] + b[2])


def hyb(s: dict) -> float:
    return float((hero(s).get("box") or [0, FLOOR, 0, 0])[1]) - FLOOR


def hvy(s: dict) -> float:
    return float((hero(s).get("vel") or [0, 0])[1])


def clip(s: dict) -> str:
    return str((hero(s).get("anim") or {}).get("clip") or "")


def accepting(s: dict) -> bool:
    return bool(hero(s).get("hero_accepting_input"))


_CS: dict = {}


def cs_bit(s: dict, name: str) -> bool:
    if not _CS:
        from ssbot.knowledge import kinematics as kin
        _CS.update({n: i for i, n in enumerate(kin.cstate_names())})
    i = _CS[name]
    cs = hero(s).get("cstate")
    return bool(cs) and bool((int(cs[i >> 6]) >> (i & 63)) & 1)


def on_ground(s: dict) -> bool:
    return cs_bit(s, "onGround")


def clapper(s: dict) -> dict | None:
    return next((e for e in s.get("ents") or () if e.get("type_key") == CLAPPER and not e.get("is_dead")
                 and (e.get("hp") or 0) > 0 and e.get("pos")), None)


def control(e: dict | None) -> str | None:
    for m in (e or {}).get("fsms") or ():
        if m.get("name") == "Control":
            return m.get("state")
    return None


def body_box(e: dict | None) -> tuple[float, float, float, float] | None:
    """The Clapper's body collider (its first box collider named like the object) as (x0, y0, x1, y1)."""
    for c in (e or {}).get("colliders") or ():
        if c.get("kind") == "box" and c.get("name") == CLAPPER and c.get("enabled", True):
            v = c.get("verts_world") or []
            xs, ys = v[0::2], v[1::2]
            if xs:
                return min(xs), min(ys), max(xs), max(ys)
    return None


def key_toward(x_from: float, x_to: float) -> int:
    return M_R if x_to >= x_from else M_L


# ---- the debug line server (PlayerData) ------------------------------------------------------------------------

class PdLine:
    """pdset through the oracle's debug line server (training-only probe setup), one connection kept open."""

    def __init__(self, instance: int):
        self.port = 47631 + instance
        self.sock = None
        self.f = None

    def _open(self):
        self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        self.f = self.sock.makefile("rw", encoding="utf-8", newline="\n")

    def set(self, **kv) -> dict:
        out = {}
        for attempt in range(2):
            try:
                if self.f is None:
                    self._open()
                for k, v in kv.items():
                    self.f.write(f"pdset {k} {v}\n")
                    self.f.flush()
                    out[k] = self.f.readline().strip()
                return out
            except OSError as e:                   # noqa: PERF203
                out["err"] = str(e)
                self.close()
        return out

    def close(self):
        try:
            if self.sock is not None:
                self.sock.close()
        except OSError:
            pass
        self.sock = self.f = None


# ---- the runner ---------------------------------------------------------------------------------------------------

class Runner:
    """One ACTION per STATE at frame + 2 (as kin_excite); a trial is a generator that receives each STATE and yields
    the mask to latch two frames later (open-loop sequences ignore the state)."""

    def __init__(self, link: OracleLink, pd: PdLine, savestate: str, rng: random.Random, log, seed: int):
        self.link, self.pd, self.savestate, self.rng, self.log, self.seed = link, pd, savestate, rng, log, seed
        self.f_load = None          # the first input frame after the current load
        self.n_load = 0
        self.last_stop = None

    # -- loads
    def load(self, dx: float = 0.0, facing: str = "random") -> dict:
        self.link.rpc("input.release", timeout_s=10)
        r0 = self.link.rpc("savestate.load", timeout_s=60, name=self.savestate, timeout=50)
        s = self.link.wait_state(lambda s: accepting(s) and on_ground(s), timeout_s=30,
                                 newer_than=int((r0 or {}).get("frame") or self.link.frame))
        self.n_load += 1
        r = self.link.rpc("randomize_start", timeout_s=30, seed=self.seed * 1000 + self.n_load, hp=[7, 7],
                          silk=[9, 9], dx=[dx, dx], facing=facing, wait_frames=[0, 0])
        pdr = self.pd.set(isInvincible="true", silk=9)
        s = self.link.wait_state(lambda s: accepting(s) and on_ground(s), timeout_s=10,
                                 newer_than=max(self.link.frame, int((r or {}).get("frame_done") or 0)))
        self.f_load = s["f"]
        return {"dx_req": dx, "dx": r.get("dx"), "x": hx(s), "facing": r.get("facing"), "f_load": self.f_load,
                "n_load": self.n_load, "f_loaded": (r0 or {}).get("frame"), "pd": pdr}

    def refill(self):
        self.pd.set(silk=9, isInvincible="true")

    # -- running
    def run(self, gen, max_frames: int = 600) -> dict | None:
        """Drive gen until it ends (StopIteration value = its result) or max_frames pass."""
        next(gen)
        last = self.link.frame
        res = None
        f0 = None
        n = 0
        try:
            while n < max_frames:
                s = self.link.wait_state(newer_than=last, timeout_s=3.0)
                last = s["f"]
                if f0 is None:
                    f0 = last + 2
                m = gen.send(s)
                self.link.act(last + 2, int(m), hold_frames=0)
                n += 1
        except StopIteration as e:
            res = e.value
        self.link.act(self.link.frame + 2, 0, hold_frames=0)
        out = dict(res or {})
        out.setdefault("f0", f0)
        out["f1"] = self.link.frame
        return out

    def write(self, rec: dict):
        self.log.write(json.dumps(rec, default=str) + "\n")
        self.log.flush()


ROOM = 1 << 30                   # a mask marker: add the direction key toward the side with more room


def room_key(s: dict) -> int:
    x = hx(s)
    return M_R if (WALL_R - x) >= (x - WALL_L) else M_L


def seq(masks: list[int], result: dict):
    """An open-loop generator: one mask per frame, then returns result (with f_first = the first latched frame). A
    mask with the ROOM marker gets the key toward the side with more room (decided on its first frame)."""
    s = yield
    f_first = None
    rk = None
    for m in masks:
        if f_first is None:
            f_first = s["f"] + 2
        if m & ROOM:
            if rk is None:
                rk = room_key(s)
                result = dict(result, room_key="R" if rk == M_R else "L", room_x=hx(s))
            m = (m & ~ROOM & ~(M_L | M_R)) | rk
        s = yield m
    result = dict(result)
    result["f_first"] = f_first
    return result


def _seg(m: int, n: int) -> list[int]:
    return [int(m)] * max(int(n), 0)


# ---- hero-only experiments (open loop) -----------------------------------------------------------------------------

def _umbrella_open(rng: random.Random, d: int, md: int, mo: int, p: dict) -> list[int]:
    """Stand, jump (held H), release r frames, then hold jump (the umbrella), the antic's key e for its ~6 frames."""
    H = rng.randint(11, 18)
    r = rng.randint(2, 6)
    e = rng.choice((0, d, -d))
    me = 0 if e == 0 else (md if e == d else mo)
    p.update(H=H, r=r, e=e)
    return _seg(M_J, H) + _seg(0, r) + _seg(M_J | me, 6)


def _drift_keys(rng: random.Random, d: int, md: int, mo: int, n: int, p: dict, base: int = M_J) -> list[int]:
    """n frames of the float (jump held) in 1-3 key segments (each none / toward d / away)."""
    out: list[int] = []
    segs = []
    left = n
    k = rng.randint(1, 3)
    for i in range(k):
        L = left if i == k - 1 else rng.randint(0, left)
        g = rng.choice((0, d, -d))
        segs.append((g, L))
        out += _seg(base | (0 if g == 0 else (md if g == d else mo)), L)
        left -= L
    p["drift"] = segs
    return out


def trial_fl(rng: random.Random, kind: str) -> tuple[list[int], dict]:
    """fl_atk / fl_claw: the umbrella, a float of t frames after its Inflate (or a press inside the antic / Inflate),
    then the attack or the Clawline in one of the variants."""
    d = rng.choice((-1, 1))
    md, mo = (M_R, M_L) if d > 0 else (M_L, M_R)
    p: dict = {"d": d}
    m = _umbrella_open(rng, d, md, mo, p)
    if kind == "fl_atk":
        v = rng.choices(("held", "rel0", "relk", "infl", "side_held", "side_relk"), (25, 20, 40, 12, 10, 8))[0]
        press = M_D | M_A
        if v.startswith("side"):
            press = M_A
            v = v[5:]
            p["side"] = True
    else:
        v = rng.choices(("held", "rel0", "relk", "infl", "antic"), (25, 15, 18, 15, 12))[0]
        press = M_CLAW | ROOM
    p["v"] = v
    # m so far ends 6 frames into the umbrella (the antic); the Inflate runs ~11-12 frames more
    if v == "antic":
        m = m[:-6] + _seg(M_J, rng.randint(1, 4))
        m += _seg(M_J | press, 3) + _seg(M_J, 10) + _seg(0, 60)
    elif v == "infl":
        m += _seg(M_J, rng.randint(1, 11))
        m += _seg(M_J | press, 3) + _seg(M_J, 14) + _seg(0, 45)
    else:
        t = rng.randint(12, 50)               # jump-held frames after the antic (the Inflate's ~12 included)
        p["t"] = t
        m += _drift_keys(rng, d, md, mo, t, p)
        if v == "held":
            m += _seg(M_J | press, 3) + _seg(M_J, 16) + _seg(0, 45)
        elif v == "rel0":
            m += _seg(press, 3) + _seg(0, 55)
        else:
            k = rng.randint(1, 12)
            g = rng.choice((0, d, -d))
            mg = 0 if g == 0 else (md if g == d else mo)
            p.update(k=k, g=g)
            m += _seg(mg, k) + _seg(press | mg, 3) + _seg(mg, 10) + _seg(0, 45)
    return m, p


def trial_drift(rng: random.Random) -> tuple[list[int], dict]:
    d = rng.choice((-1, 1))
    md, mo = (M_R, M_L) if d > 0 else (M_L, M_R)
    p: dict = {"d": d}
    m = _umbrella_open(rng, d, md, mo, p)
    n = rng.randint(30, 75)
    m += _drift_keys(rng, d, md, mo, n, p)
    g = rng.choice((0, d, -d))
    p.update(n=n, g=g)
    m += _seg(0 if g == 0 else (md if g == d else mo), 25) + _seg(0, 20)
    return m, p


def trial_dash(rng: random.Random, d: int) -> tuple[list[int], dict]:
    md = M_R if d > 0 else M_L
    v = rng.choice(("twice", "twice", "sprint"))
    p: dict = {"d": d, "v": v}
    if v == "twice":
        j = rng.randint(4, 40)
        key = rng.choice((0, 1))              # the direction key held through (0: the dash goes the facing way)
        mk = md if key else 0
        tap = rng.choice((2, 3, 4))
        p.update(j=j, key=key, tap=tap)
        m = _seg(mk, 6) + _seg(M_DASH | mk, tap) + _seg(mk, max(j - tap, 0)) + _seg(M_DASH | mk, tap) + _seg(mk, 30) \
            + _seg(0, 20)
    else:
        h = rng.randint(20, 70)
        rel = rng.choice(("none", "key", "opp"))
        p.update(h=h, rel=rel)
        mo = M_L if d > 0 else M_R
        m = _seg(md, 4) + _seg(M_DASH | md, h) + _seg({"none": 0, "key": md, "opp": mo}[rel], 30) + _seg(0, 15)
    return m, p


def trial_whiff(rng: random.Random) -> tuple[list[int], dict]:
    """A jump held H frames; the down slash (or a side slash) at k1, again at k1 + j and k1 + j + 20 (2-frame
    presses): the cadence after a whiff."""
    d = rng.choice((-1, 1))
    md = M_R if d > 0 else M_L
    side = rng.random() < 0.3
    press = M_A if side else (M_D | M_A)
    H = rng.randint(12, 18)
    k1 = rng.randint(3, 9)
    j = rng.randint(12, 24)
    mv = md if rng.random() < 0.5 else 0
    p = {"d": d, "side": side, "H": H, "k1": k1, "j": j, "mv": bool(mv)}
    n = k1 + j + 20 + 40
    m = [(M_J if i < H else 0) | mv for i in range(n)]
    for f in (k1, k1 + j, k1 + j + 20):
        for i in (f, f + 1):
            m[i] |= press
    return m, p


# ---- closed-loop experiments ------------------------------------------------------------------------------------------

def gen_claw(rng: random.Random, air: bool, d: int):
    """claw_air / claw_gnd: the Clawline (no target) and a second action at control + j."""
    md, mo = (M_R, M_L) if d > 0 else (M_L, M_R)
    p: dict = {"d": d, "air": air}
    s = yield
    if air:
        H = rng.randint(4, 18)
        k = rng.randint(2, 45)                # press frame after the jump's first frame
        p.update(H=H, k=k)
        for i in range(k):
            s = yield (M_J if i < H else 0)
    p["press_state"] = {"f": s["f"], "y": hyb(s), "vy": hvy(s), "x": hx(s), "clip": clip(s), "g": on_ground(s)}
    f_press = s["f"] + 2
    for i in range(3):
        s = yield (M_CLAW | md)
    second = rng.choice(("claw", "claw", "atk", "dash", "umb", "none"))
    j = rng.randint(0, 22)
    p.update(second=second, j=j, f_press=f_press)
    # wait for control (accepting input after the Harpoon clips), at most 70 frames
    n = 0
    seen_harpoon = False
    while n < 90:
        if clip(s).startswith("Harpoon"):
            seen_harpoon = True
        if seen_harpoon and accepting(s):
            break
        s = yield 0
        n += 1
    p["f_ctrl_seen"] = s["f"]
    p["ctrl_state"] = {"y": hyb(s), "vy": hvy(s), "x": hx(s), "clip": clip(s), "g": on_ground(s)}
    for i in range(j):
        s = yield 0
    act = {"claw": M_CLAW | mo, "atk": M_D | M_A, "dash": M_DASH | md, "umb": M_J, "none": 0}[second]
    p["f_second"] = s["f"] + 2
    for i in range(3):
        s = yield act
    hold = M_J if second == "umb" else 0
    for i in range(50):
        s = yield hold
    return p


def gen_pogo(rng: random.Random, kind: str):
    """pogo / side on the Clapper: approach, the jump, the down slash at the planned moment, a second action."""
    p: dict = {"kind": kind}
    s = yield
    e = clapper(s)
    if e is None or body_box(e) is None:
        return {"skip": "no clapper"}
    bb = body_box(e)
    cx = 0.5 * (bb[0] + bb[2])
    side = 1 if hx(s) >= cx else -1
    pre_dash = kind == "pogo" and rng.random() < 0.35
    p["pre_dash"] = pre_dash
    if kind == "pogo":
        off = rng.uniform(-1.3, 1.3)
        p["off"] = off
        tx = cx + off
        if pre_dash:
            # the air dash + Air Sprint carries her ~6.4-7 u: start that far out on the roomier side
            side = 1 if (WALL_R - cx) >= (cx - WALL_L) else -1
            p["dash_from"] = side
    else:
        gap = rng.uniform(0.1, 1.4)           # her box edge to its body edge
        p["gap"] = gap
        tx = (bb[2] + 0.25 + gap) if side > 0 else (bb[0] - 0.25 - gap)
    # walk to tx (she passes through it: invincible), at most 150 frames
    for _ in range(150):
        e = clapper(s)
        bb = body_box(e) or bb
        cx = 0.5 * (bb[0] + bb[2])
        if kind == "pogo":
            tx = cx + p["off"] + (p["dash_from"] * 6.7 if pre_dash else 0.0)
        else:
            tx = (bb[2] + 0.25 + p["gap"]) if side > 0 else (bb[0] - 0.25 - p["gap"])
        if abs(hx(s) - tx) < 0.15 and on_ground(s) and accepting(s):
            break
        s = yield (key_toward(hx(s), tx) if abs(hx(s) - tx) >= 0.15 else 0)
    else:
        return dict(p, skip="no approach")
    e = clapper(s)
    bb = body_box(e) or bb
    p["start"] = {"f": s["f"], "x": hx(s), "box": bb, "st": control(e)}
    if kind == "pogo":
        H = rng.randint(12, 18)
        lead = rng.uniform(0.3, 1.6)          # press when her box bottom falls to its top + lead
        a_dash = rng.randint(3, 8)
        p.update(H=H, lead=lead, a_dash=a_dash if pre_dash else None)
        n = 0
        while n < 70:
            e = clapper(s)
            bb = body_box(e) or bb
            top = bb[3] - FLOOR
            if n > H and hvy(s) < 0 and hyb(s) <= top + lead:
                break
            m = M_J if n < H else 0
            if pre_dash and a_dash <= n < a_dash + 2:
                m |= M_DASH | (M_L if p["dash_from"] > 0 else M_R)
            s = yield m
            n += 1
        p["press_state"] = {"f": s["f"], "y": hyb(s), "vy": hvy(s), "x": hx(s), "box": bb}
    else:
        H = rng.randint(3, 9)
        k = rng.randint(3, 16)
        p.update(H=H, k=k)
        for i in range(k):
            s = yield (M_J if i < H else 0)
        p["press_state"] = {"f": s["f"], "y": hyb(s), "vy": hvy(s), "x": hx(s), "box": body_box(clapper(s))}
    f_press = s["f"] + 2
    p["f_press"] = f_press
    second = rng.choice(("ds", "ds", "dash", "none")) if kind == "pogo" else rng.choice(("ds", "none"))
    j = rng.randint(10, 26) if second == "ds" else rng.randint(4, 30)
    p.update(second=second, j=j)
    for i in range(2):
        s = yield (M_D | M_A)
    for i in range(j - 2):
        s = yield 0
    act = {"ds": M_D | M_A, "dash": M_DASH | (M_R if rng.random() < 0.5 else M_L), "none": 0}[second]
    p["f_second"] = s["f"] + 2
    for i in range(2):
        s = yield act
    for i in range(60):
        s = yield 0
    return p


def gen_hook(rng: random.Random, max_wait: int = 900):
    """The Clawline at the Clapper when it is Idle (or Walk) and she stands 3 - 9.5 u from it facing it."""
    p: dict = {}
    s = yield
    want = rng.choices(("Idle", "Walk"), (4, 1))[0]
    dmin, dmax = 3.0, 9.5
    p["want"] = want
    n = 0
    prev = None
    while n < max_wait:
        e = clapper(s)
        st = control(e)
        if e is not None and accepting(s) and on_ground(s):
            dx = float(e["pos"][0]) - hx(s)
            if st == want and dmin <= abs(dx) <= dmax and (want != "Idle" or prev != "Idle" or rng.random() < 0.25):
                break
            # keep a distance of ~6 u while waiting (walk away when closer than 4, toward when beyond 9)
            if abs(dx) < 4.5 and st not in ("Idle",):
                k = M_L if dx > 0 else M_R
                xn = hx(s) + (-1 if dx > 0 else 1) * 1.0
                if not (WALL_L + 1.0 < xn < WALL_R - 1.0):
                    k = 0
                prev = st
                s = yield k
                n += 1
                continue
            if abs(dx) > 9.0 and st not in ("Idle",):
                prev = st
                s = yield (M_R if dx > 0 else M_L)
                n += 1
                continue
        prev = st
        s = yield 0
        n += 1
    else:
        return dict(p, skip="no idle")
    e = clapper(s)
    dx = float(e["pos"][0]) - hx(s)
    p["start"] = {"f": s["f"], "x": hx(s), "cx": float(e["pos"][0]), "st": control(e),
                  "t": next((m.get("t") for m in e.get("fsms") or () if m.get("name") == "Control"), None),
                  "box": body_box(e)}
    toward = M_R if dx > 0 else M_L
    away = M_L if dx > 0 else M_R
    p["f_press"] = s["f"] + 2
    for i in range(3):
        s = yield (M_CLAW | toward)
    # the second action at control + j: the Clawline again (away from it: no target), the down slash or nothing
    second = rng.choices(("claw_away", "none", "atk"), (3, 2, 1))[0]
    j = rng.randint(0, 16)
    p.update(second=second, j=j)
    n = 0
    seen = False
    while n < 70:
        if clip(s).startswith("Harpoon"):
            seen = True
        if seen and accepting(s):
            break
        s = yield 0
        n += 1
    p["f_ctrl_seen"] = s["f"]
    p["ctrl_state"] = {"y": hyb(s), "vy": hvy(s), "x": hx(s), "clip": clip(s), "g": on_ground(s)}
    for i in range(j):
        s = yield 0
    act = {"claw_away": M_CLAW | away, "none": 0, "atk": M_D | M_A}[second]
    p["f_second"] = s["f"] + 2
    for i in range(3):
        s = yield act
    for i in range(90):
        s = yield 0
    return p


# ---- main -----------------------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--savestate", default="fo_cl_w7w")
    ap.add_argument("--exps", default=",".join(HERO_EXPS), help="experiments, separated by ',' or ':'")
    ap.add_argument("--weights", default="", help="weights for --exps, separated by ',' or ':' (default equal)")
    ap.add_argument("--trials", type=int, default=100)
    ap.add_argument("--seed", type=int, default=8100000)
    ap.add_argument("--minutes", type=float, default=60.0, help="stop after this many minutes")
    ap.add_argument("--out", default=r"C:\ssbot\data\runs\m2\map2_m0")
    a = ap.parse_args(argv)

    from ssbot.probes.common import load_slot
    from ssbot.record.recorder import Recorder

    import re
    exps = [x.strip() for x in re.split(r"[,:]", a.exps) if x.strip()]
    for x in exps:
        if x not in HERO_EXPS + CLAP_EXPS:
            raise SystemExit(f"unknown experiment {x}")
    w = [float(v) for v in re.split(r"[,:]", a.weights) if v.strip()] if a.weights else [1.0] * len(exps)
    rng = random.Random(a.seed)
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    pd = PdLine(a.instance)
    rec = None
    t_end = time.monotonic() + 60 * a.minutes
    try:
        load_slot(link, 1)
        link.rpc("guards.set", save_suppression=True)
        link.rpc("fsmtap.set", all=True)
        link.rpc("time.scale", timeout_s=10, scale=1.0)
        rec = Recorder(link, out_dir=a.out, profile="TRAIN", episode=f"m0_i{a.instance}_s{a.seed}",
                       config={"probe": "m0_probe", "seed": a.seed, "trials": a.trials, "exps": exps,
                               "savestate": a.savestate, "instance": a.instance}).start()
        log = (rec.path / "m0_trials.jsonl").open("w", encoding="utf-8")
        R = Runner(link, pd, a.savestate, rng, log, a.seed)
        clap_load = None
        n = 0
        while n < a.trials and time.monotonic() < t_end:
            why = stop_requested()
            if why:
                print("stop:", why, flush=True)
                break
            exp = rng.choices(exps, w)[0]
            t_wall = time.time()
            rec_line: dict = {"n": n, "exp": exp, "t": t_wall}
            if exp in HERO_EXPS:
                clap_load = None
                if exp == "dash_g":
                    d = rng.choice((-1, 1))
                    dx = (WALL_L + 3.0 - X0) if d > 0 else (WALL_R - 3.0 - X0)
                    if rng.random() < 0.5:
                        dx = (WALL_L + 9.0 - X0) if d > 0 else (WALL_R - 9.0 - X0)
                    info = R.load(dx=dx, facing="right" if d > 0 else "left")
                    masks, p = trial_dash(rng, d)
                    res = R.run(seq(masks, p), max_frames=len(masks) + 5)
                elif exp in ("claw_air", "claw_gnd"):
                    d = rng.choice((-1, 1))
                    # the needle flies 9.25 u, the pull ~6-8 u: 11 u free ahead, and behind the end for the
                    # second Clawline (the other way)
                    xs = rng.uniform(18.0, 37.0) if d > 0 else rng.uniform(26.0, 45.0)
                    info = R.load(dx=xs - X0, facing="right" if d > 0 else "left")
                    res = R.run(gen_claw(rng, exp == "claw_air", d), max_frames=PRE_SPAWN_F + 60)
                else:
                    info = R.load(dx=rng.uniform(-4.0, 4.0), facing="random")
                    if exp in ("fl_atk", "fl_claw"):
                        masks, p = trial_fl(rng, exp)
                    elif exp == "drift":
                        masks, p = trial_drift(rng)
                    else:
                        masks, p = trial_whiff(rng)
                    res = R.run(seq(masks, p), max_frames=len(masks) + 5)
                rec_line.update(load=info, res=res)
            else:
                if clap_load is None or (clapper(link.state or {}) or {}).get("hp", 0) < 60 \
                        or clapper(link.state or {}) is None or time.monotonic() - clap_load > 75:
                    info = R.load(dx=rng.uniform(-6.0, 6.0), facing="random")
                    clap_load = time.monotonic()
                    # wait for its Roar to end (it drops in ~4 s after the load)
                    try:
                        link.wait_state(lambda s: control(clapper(s)) not in INTRO and accepting(s), timeout_s=20)
                    except TimeoutError:
                        rec_line.update(load=info, res={"skip": "no spawn"})
                        R.write(rec_line)
                        n += 1
                        continue
                    rec_line["load"] = info
                R.refill()
                if exp == "hook":
                    res = R.run(gen_hook(rng), max_frames=1100)
                else:
                    res = R.run(gen_pogo(rng, exp), max_frames=400)
                rec_line["res"] = res
            R.write(rec_line)
            print(f"{n:4d} {exp:9s} {json.dumps(rec_line.get('res'), default=str)[:200]}", flush=True)
            n += 1
        log.close()
    finally:
        try:
            link.rpc("input.release", timeout_s=10)
        except Exception:  # noqa: BLE001
            pass
        try:
            link.rpc("fsmtap.set", all=False)
        except Exception:  # noqa: BLE001
            pass
        pd.close()
        if rec is not None:
            print("recording:", rec.close().get("path", rec.path), flush=True)
        link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
