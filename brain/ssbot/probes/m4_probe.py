"""Map v2 stage M4a live probes (the mechanics the M3 search's plans lean on that M0 did not measure): forced setups on
Forum_W_w7 (one Clapper, Wanderer), recorded for ssbot.tools.m4_calib. The harness is M0's (ssbot.probes.m0_probe:
one ACTION per STATE latched at frame + 2, hero-only trials in the ~4 s before the Clapper drops in, Clapper trials
after its Roar; the hero invincible and silk 9 through the debug line server unless a trial says otherwise).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.probes.m4_probe --instance 0 --savestate fo_cl_w7w \
        --exps adash,adash_claw,gdash_jump,dash_end --trials 300 --seed 9100000 [--out C:/ssbot/data/runs/m2/map2_m4]
    ../scripts/uv.cmd run python -m ssbot.probes.m4_probe --instance 1 --savestate fo_cl_w7w \
        --exps hook_touch,hook_pd,bounce_jump --trials 120 --seed 9200000

Hero-only experiments (open loop; one per load, placed with randomize_start's dx near a wall, the dash toward the
room):
  adash       (a) / (b) the air dash: a jump held H frames, the dash pressed k frames after the jump's first frame
              (tapped 2-3 frames or held h frames: the Air Sprint Loop), the jump released before it or HELD through it
              (jh: the hang's gravity kept through the dash and the air sprint?), a direction key or none after the
              press, then a CANCEL c = 0 .. 24 frames after the dash press: none / attack (side) / down attack / jump
              (pressed and held: the umbrella) / the Clawline / the dash again.
  adash_claw  (a) the restore by the unhooked Clawline: a jump, the air dash (or none: the control group), the
              Clawline pressed c frames after the dash press (in the air sprint or after it), then the dash pressed
              at control + j: is the air dash back?
  gdash_jump  (b) the dash with jump on the ground: 'dj' a ground dash (tap, or held: the sprint) and the jump pressed
              j = 0 .. 16 frames after it and held H; 'jd' the jump pressed and held, the dash j = 0 .. 4 frames later.
  dash_end    (kin_jit leftover) a ground dash tapped, the dash key pressed again j = 5 .. 11 frames after the first
              press (around the dash's end frame) and held: the game stops, the model sprints (M0, 3 trials)?
Clapper experiments (after its Roar; many per load; the load is renewed when its HP drops below 60, after any HP
the hero lost, or after 75 s):
  hook_touch  (c) the hooked Clapper's body contact after the hook's control: the Clawline at the Idle Clapper from
              the ground 2.5 - 7 u away, then at control + k the air dash toward it ('dash', k 0 .. 16: the dash stops
              the forced bounce and carries her through its body), or the key toward it held ('walk'), or nothing.
              HALF THE TRIALS NOT INVINCIBLE (inv false): the real damage event; the invincible half shows the body's
              contact attempts (damage_blocked) without the knock-back.
  hook_pd     (a) / (c) the restore by the HOOKED Clawline: from 8.5 - 10 u a hop, the air dash toward the Idle
              Clapper, the Clawline pressed c frames after the dash press, then the air dash pressed toward it at
              control + j (is it back?); not invincible in half the trials.
  bounce_jump (d) a jump during the pogo bounce: the down slash on its head (M0's pogo approach), the jump pressed k
              = 2 .. 28 frames after the down slash press (contact ~ P + 3 / 4) and held J frames (the umbrella in
              the bounce?), a drift key or none.
Every trial is one line of <recording>/m4_trials.jsonl (as m0_trials.jsonl). Safety: instances 0 / 1 only; save
suppression on; the probe stops at STOP_AGENTS, HUMAN_PRACTICE, DEMO_SOON (re-appearing during the block) or
C:\\ssbot\\sandbox\\m4_probe.stop.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

from ssbot.ipc.oracle_link import OracleLink
from ssbot.probes import m0_probe as m0
from ssbot.probes.m0_probe import (
    M_A, M_CLAW, M_D, M_DASH, M_J, M_L, M_R, ROOM, WALL_L, WALL_R, X0, INTRO, PRE_SPAWN_F, PdLine, Runner, _seg, accepting,
    body_box, clapper, clip, control, hvy, hx, hyb, key_toward, on_ground, seq)

HERO_EXPS = ("adash", "adash_claw", "gdash_jump", "dash_end")
CLAP_EXPS = ("hook_touch", "hook_pd", "bounce_jump")
STOP_FILES = (r"C:\ssbot\sandbox\STOP_AGENTS", r"C:\ssbot\sandbox\HUMAN_PRACTICE", r"C:\ssbot\sandbox\DEMO_SOON",
              r"C:\ssbot\sandbox\m4_probe.stop")
OPT = {"force_cancel": "", "inv_share": 0.5}


def stop_requested() -> str | None:
    for p in STOP_FILES:
        if Path(p).exists():
            return p
    return None


def hp(s: dict) -> int:
    return int((s.get("hero") or {}).get("health") or 0)


def _dkeys(d: int) -> tuple[int, int]:
    return (M_R, M_L) if d > 0 else (M_L, M_R)


# ---- hero-only experiments (open loop) -----------------------------------------------------------------------------

CANCELS = ("none", "atk", "datk", "jump", "claw", "dash2")


def trial_adash(rng: random.Random, d: int) -> tuple[list[int], dict]:
    """(a) / (b): the air dash toward d (the room side), its cancels, the jump held through it or not."""
    md, mo = _dkeys(d)
    jh = rng.random() < 0.3
    k = rng.choice((rng.randint(3, 12), rng.randint(13, 26), rng.randint(27, 40)))
    if jh:
        H = k + rng.randint(4, 40)            # the jump still held at the press and m frames after it
    else:                                     # released before the press; full jumps for the late presses
        H = rng.randint(max(2, min(12, k - 12)), max(2, min(18, k - 1)))
    tap = rng.random() < 0.65
    h = rng.randint(2, 3) if tap else rng.randint(6, 45)
    after = rng.choice((0, md))               # the direction key after the press (the dash's own key is md)
    cancel = OPT["force_cancel"] or rng.choices(CANCELS, (30, 14, 14, 16, 12, 14))[0]
    c = rng.randint(0, 24)
    p = {"d": d, "jh": jh, "k": k, "H": H, "tap": tap, "h": h, "after": "d" if after else "0", "cancel": cancel, "c": c}
    n = k + max(h, c + 3) + 60
    m = [0] * n
    for i in range(n):
        if i < H:
            m[i] |= M_J
        if k <= i < k + h:
            m[i] |= M_DASH | md
        elif i >= k:
            m[i] |= after
    if cancel != "none":
        cm_ = {"atk": M_A | md, "datk": M_D | M_A, "jump": M_J, "claw": M_CLAW | md, "dash2": M_DASH | md}[cancel]
        f = k + c
        for i in range(f, min(f + (20 if cancel == "jump" else 2), n)):
            m[i] |= cm_
            if cancel == "datk":
                m[i] &= ~(M_L | M_R)
    return m, p


def trial_adash_claw(rng: random.Random, d: int) -> tuple[list[int], dict]:
    """(a): the restore by the unhooked Clawline (the dash at control)."""
    md, mo = _dkeys(d)
    pre = rng.random() < 0.75
    H = rng.randint(15, 18)                   # a full jump, the dash near its apex: the Clawline still airborne
    k = rng.randint(10, 20)
    c = rng.randint(2, 24)
    j = rng.randint(0, 8)
    p = {"d": d, "pre": pre, "H": H, "k": k, "c": c, "j": j}
    fc = k + c                                # the Clawline press (the same frame in the control group)
    f2 = fc + 32 + j                          # the dash again: control (P + ~32) + j, open loop
    n = f2 + 3 + 4 + 2 + 45
    m = [0] * n
    for i in range(n):
        if i < H:
            m[i] |= M_J
        if pre and k <= i < k + 2:
            m[i] |= M_DASH | md
        if fc <= i < fc + 3:
            m[i] |= M_CLAW | md
        # a 3-frame press at control + j and a second one 4 frames later (in case control came late)
        if f2 <= i < f2 + 3 or f2 + 7 <= i < f2 + 9:
            m[i] |= M_DASH | md
    return m, p


def trial_gdash_jump(rng: random.Random, d: int) -> tuple[list[int], dict]:
    """(b) on the ground: 'dj' dash then jump j frames after the dash press; 'jd' jump then dash j frames later."""
    md, mo = _dkeys(d)
    v = rng.choices(("dj", "jd"), (65, 35))[0]
    key = rng.choice((0, md))
    p: dict = {"d": d, "v": v, "key": "d" if key else "0"}
    if v == "dj":
        held = rng.random() < 0.3
        h = rng.randint(12, 30) if held else rng.randint(2, 3)
        j = rng.randint(0, 16)
        H = rng.randint(3, 18)
        p.update(held=held, h=h, j=j, H=H)
        n = max(h, j + H) + 70
        m = [key] * 4 + [0] * n
        for i in range(n):
            mm = key
            if i < h:
                mm |= M_DASH | md
            if j <= i < j + H:
                mm |= M_J
            m[4 + i] = mm
    else:
        H = rng.randint(6, 18)
        j = rng.randint(0, 4)
        h = rng.randint(2, 3)
        p.update(H=H, j=j, h=h)
        n = max(H, j + h) + 70
        m = [key] * 4 + [0] * n
        for i in range(n):
            mm = key
            if i < H:
                mm |= M_J
            if j <= i < j + h:
                mm |= M_DASH | md
            m[4 + i] = mm
    return m, p


def trial_dash_end(rng: random.Random, d: int) -> tuple[list[int], dict]:
    """The kin_jit leftover: the dash key pressed again around the ground dash's end frame and held."""
    md, mo = _dkeys(d)
    tap = rng.randint(2, 3)
    j = rng.randint(5, 11)
    key = rng.choice((0, md))
    hold2 = rng.randint(10, 30)
    p = {"d": d, "tap": tap, "j": j, "key": "d" if key else "0", "hold2": hold2}
    m = _seg(key, 4) + _seg(M_DASH | md, tap) + _seg(key, j - tap) + _seg(M_DASH | md, hold2) + _seg(key, 30) + \
        _seg(0, 20)
    return m, p


# ---- Clapper experiments (closed loop) --------------------------------------------------------------------------------

def _wait_idle(rng: random.Random, s: dict, dmin: float, dmax: float, max_wait: int = 900):
    """Yield-driven wait (a sub-generator): she keeps dmin .. dmax from the Clapper until it is Idle there, standing
    and facing it. Returns the last state or None."""
    n = 0
    prev = None
    while n < max_wait:
        e = clapper(s)
        st = control(e)
        if e is not None and accepting(s) and on_ground(s):
            dx = float(e["pos"][0]) - hx(s)
            if st == "Idle" and dmin <= abs(dx) <= dmax and (prev != "Idle" or rng.random() < 0.25):
                return s
            mid = 0.5 * (dmin + dmax)
            want = None
            if abs(dx) < dmin - 0.2 or (st != "Idle" and abs(dx) < mid - 0.8):
                want = M_L if dx > 0 else M_R
                xn = hx(s) + (-1 if dx > 0 else 1) * 1.0
                if not (WALL_L + 1.0 < xn < WALL_R - 1.0):
                    want = None
            elif abs(dx) > dmax + 0.2 or (st != "Idle" and abs(dx) > mid + 0.8):
                want = M_R if dx > 0 else M_L
            if want is not None:
                prev = st
                s = yield want
                n += 1
                continue
        prev = st
        s = yield 0
        n += 1
    return None


def _until_control(s: dict, n_max: int = 80):
    """Yield 0 until she has control after the Harpoon clips. Returns (state, frames waited)."""
    n = 0
    seen = False
    while n < n_max:
        if clip(s).startswith("Harpoon"):
            seen = True
        if seen and accepting(s):
            break
        s = yield 0
        n += 1
    return s, n


def gen_hook_touch(rng: random.Random, R: Runner):
    """(c): hook the Idle Clapper, then into its body at control + k."""
    p: dict = {}
    s = yield
    inv = rng.random() >= OPT["inv_share"]
    p["inv"] = inv
    R.pd.set(isInvincible="true" if inv else "false")
    p["hp0"] = hp(s)
    s = yield from _wait_idle(rng, s, 2.5, 7.0)
    if s is None:
        return dict(p, skip="no idle")
    e = clapper(s)
    dx = float(e["pos"][0]) - hx(s)
    p["start"] = {"f": s["f"], "x": hx(s), "cx": float(e["pos"][0]), "st": control(e), "box": body_box(e)}
    toward = M_R if dx > 0 else M_L
    p["f_press"] = s["f"] + 2
    for i in range(3):
        s = yield (M_CLAW | toward)
    act = rng.choices(("dash", "walk", "none"), (80, 10, 10))[0]
    # the dash enters its body (the gap at control ~0.8 - 4 u) a few frames later and crosses its 3.6 u in ~9 frames:
    # k <= 8 mostly spans the Harpoon FSM's Idle (control + 12 / 13)
    k = (rng.randint(0, 8) if rng.random() < 0.75 else rng.randint(9, 16)) if act == "dash" else rng.randint(0, 4)
    p.update(act=act, k=k)
    s, n = yield from _until_control(s)
    p["f_ctrl_seen"] = s["f"]
    p["ctrl_state"] = {"y": hyb(s), "vy": hvy(s), "x": hx(s), "clip": clip(s), "box": body_box(clapper(s))}
    for i in range(k):
        s = yield 0
    p["f_act"] = s["f"] + 2
    e = clapper(s)
    tw = key_toward(hx(s), float(e["pos"][0])) if e is not None else toward
    if act == "dash":
        for i in range(2):
            s = yield (M_DASH | tw)
        for i in range(24):
            s = yield tw
    elif act == "walk":
        for i in range(40):
            s = yield tw
    for i in range(50):
        s = yield 0
    p["hp1"] = hp(s)
    return p


def gen_hook_pd(rng: random.Random, R: Runner):
    """(a) / (c): the hooked Clawline after an air dash; the air dash again at control + j."""
    p: dict = {}
    s = yield
    inv = rng.random() >= OPT["inv_share"]
    p["inv"] = inv
    R.pd.set(isInvincible="true" if inv else "false")
    p["hp0"] = hp(s)
    s = yield from _wait_idle(rng, s, 8.5, 10.0)
    if s is None:
        return dict(p, skip="no idle")
    e = clapper(s)
    dx = float(e["pos"][0]) - hx(s)
    toward = M_R if dx > 0 else M_L
    H = rng.randint(5, 9)
    kd = 2
    c = rng.randint(3, 16)
    j = rng.randint(0, 6)
    p.update(H=H, kd=kd, c=c, j=j)
    p["start"] = {"f": s["f"], "x": hx(s), "cx": float(e["pos"][0]), "st": control(e), "box": body_box(e)}
    p["f_jump"] = s["f"] + 2
    m = [(M_J if i < H else 0) | toward for i in range(kd)] + [M_DASH | toward | (M_J if kd + i < H else 0)
                                                              for i in range(2)]
    m += [(M_J if kd + 2 + i < H else 0) for i in range(max(c - 2, 0))]
    for mm in m:
        s = yield mm
    p["f_claw"] = s["f"] + 2
    for i in range(6):
        s = yield (M_CLAW | toward)
    s, n = yield from _until_control(s)
    p["f_ctrl_seen"] = s["f"]
    p["ctrl_state"] = {"y": hyb(s), "vy": hvy(s), "x": hx(s), "clip": clip(s), "box": body_box(clapper(s))}
    for i in range(j):
        s = yield 0
    p["f_act"] = s["f"] + 2
    e = clapper(s)
    tw = key_toward(hx(s), float(e["pos"][0])) if e is not None else toward
    for i in range(2):
        s = yield (M_DASH | tw)
    for i in range(20):
        s = yield tw
    for i in range(50):
        s = yield 0
    p["hp1"] = hp(s)
    return p


def gen_bounce_jump(rng: random.Random, R: Runner):
    """(d): the down slash on its head, then the jump pressed k frames after the press and held J."""
    p: dict = {}
    s = yield
    e = clapper(s)
    if e is None or body_box(e) is None:
        return {"skip": "no clapper"}
    off = rng.uniform(-1.0, 1.0)
    p["off"] = off
    for _ in range(150):
        e = clapper(s)
        bb = body_box(e)
        if bb is None:
            return dict(p, skip="no body")
        cx = 0.5 * (bb[0] + bb[2])
        tx = cx + off
        if abs(hx(s) - tx) < 0.15 and on_ground(s) and accepting(s):
            break
        s = yield (key_toward(hx(s), tx) if abs(hx(s) - tx) >= 0.15 else 0)
    else:
        return dict(p, skip="no approach")
    bb = body_box(clapper(s))
    p["start"] = {"f": s["f"], "x": hx(s), "box": bb, "st": control(clapper(s))}
    H = rng.randint(12, 18)
    lead = rng.uniform(0.3, 1.4)
    p.update(H=H, lead=lead)
    n = 0
    while n < 70:
        bb = body_box(clapper(s)) or bb
        top = bb[3] - m0.FLOOR
        if n > H and hvy(s) < 0 and hyb(s) <= top + lead:
            break
        s = yield (M_J if n < H else 0)
        n += 1
    p["press_state"] = {"f": s["f"], "y": hyb(s), "vy": hvy(s), "x": hx(s), "box": bb}
    p["f_press"] = s["f"] + 2
    k = rng.randint(2, 28)
    J = rng.randint(4, 30)
    g = rng.choice((0, M_L, M_R))
    p.update(k=k, J=J, g={0: "0", M_L: "L", M_R: "R"}[g])
    for i in range(k):
        s = yield ((M_D | M_A) if i < 2 else 0)
    p["f_jump"] = s["f"] + 2
    for i in range(J):
        s = yield (M_J | g)
    for i in range(50):
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
    ap.add_argument("--seed", type=int, default=9100000)
    ap.add_argument("--minutes", type=float, default=60.0, help="stop after this many minutes")
    ap.add_argument("--out", default=r"C:\ssbot\data\runs\m2\map2_m4")
    ap.add_argument("--force-cancel", default="", help="adash: always this cancel")
    ap.add_argument("--inv-share", type=float, default=0.5, help="hook_touch / hook_pd: the share of invincible trials")
    a = ap.parse_args(argv)

    from ssbot.probes.common import load_slot
    from ssbot.record.recorder import Recorder

    exps = [x.strip() for x in re.split(r"[,:]", a.exps) if x.strip()]
    OPT.update(force_cancel=a.force_cancel, inv_share=a.inv_share)
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
        # an instance frozen at the title by a block's end (time scale 1e-4) takes no menu input: unfreeze first
        link.rpc("time.scale", timeout_s=10, scale=1.0)
        load_slot(link, 1)
        link.rpc("guards.set", save_suppression=True)
        link.rpc("fsmtap.set", all=True)
        link.rpc("time.scale", timeout_s=10, scale=1.0)
        rec = Recorder(link, out_dir=a.out, profile="TRAIN", episode=f"m4_i{a.instance}_s{a.seed}",
                       config={"probe": "m4_probe", "seed": a.seed, "trials": a.trials, "exps": exps,
                               "savestate": a.savestate, "instance": a.instance}).start()
        log = (rec.path / "m4_trials.jsonl").open("w", encoding="utf-8")
        R = Runner(link, pd, a.savestate, rng, log, a.seed)
        clap_load = None
        n = 0
        while n < a.trials and time.monotonic() < t_end:
            why = stop_requested()
            if why:
                print("stop:", why, flush=True)
                break
            exp = rng.choices(exps, w)[0]
            rec_line: dict = {"n": n, "exp": exp, "t": time.time()}
            if exp in HERO_EXPS:
                clap_load = None
                d = rng.choice((-1, 1))
                # near the wall behind her, the room ahead (the dash + air sprint + the Clawline's 10.6 u)
                xs = rng.uniform(WALL_L + 2.0, WALL_L + 5.0) if d > 0 else rng.uniform(WALL_R - 5.0, WALL_R - 2.0)
                info = R.load(dx=xs - X0, facing="right" if d > 0 else "left")
                fn = {"adash": trial_adash, "adash_claw": trial_adash_claw, "gdash_jump": trial_gdash_jump,
                      "dash_end": trial_dash_end}[exp]
                masks, p = fn(rng, d)
                res = R.run(seq(masks[:PRE_SPAWN_F], p), max_frames=min(len(masks), PRE_SPAWN_F) + 5)
                rec_line.update(load=info, res=res)
            else:
                st = link.state or {}
                h0 = hp(st)
                if clap_load is None or (clapper(st) or {}).get("hp", 0) < 60 or clapper(st) is None \
                        or time.monotonic() - clap_load > 75 or h0 < 7:
                    info = R.load(dx=rng.uniform(-6.0, 6.0), facing="random")
                    clap_load = time.monotonic()
                    try:
                        link.wait_state(lambda s: control(clapper(s)) not in INTRO and accepting(s), timeout_s=20)
                    except TimeoutError:
                        rec_line.update(load=info, res={"skip": "no spawn"})
                        R.write(rec_line)
                        n += 1
                        continue
                    rec_line["load"] = info
                R.refill()
                if exp == "hook_touch":
                    res = R.run(gen_hook_touch(rng, R), max_frames=1200)
                elif exp == "hook_pd":
                    res = R.run(gen_hook_pd(rng, R), max_frames=1200)
                else:
                    res = R.run(gen_bounce_jump(rng, R), max_frames=400)
                R.refill()                     # invincible again between trials
                rec_line["res"] = res
            R.write(rec_line)
            print(f"{n:4d} {exp:11s} {json.dumps(rec_line.get('res'), default=str)[:220]}", flush=True)
            n += 1
        log.close()
    finally:
        try:
            link.rpc("input.release", timeout_s=10)
        except Exception:  # noqa: BLE001
            pass
        try:
            pd.set(isInvincible="true")
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
