"""The Clapper slam's down-slash theory (task 1v1 T1, the person's experiment method 2026-10-11, forum.md 46): the
real boxes per frame of the slam, measured from recordings, and from them where and when a Wanderer down slash
bounces off the Clapper and whether the hero then stays clear of the hammer (Slam Collider 1 / 2) and the body.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.pogo_theory slams <recordings / run dirs> [--glob BASE PATTERN] \
        --out C:/ssbot/data/m2_pogo/theory/slams.jsonl
    ../scripts/uv.cmd run python -m ssbot.tools.pogo_theory template C:/ssbot/data/m2_pogo/theory/slams.jsonl \
        --out <worktree>/knowledge/1.0.30000/enemies/forum/pogo_clapper_slam.json

slams: every CC_SLAM of a Clapper (Control enters Slam Antic) from its first frame to the first frame outside the
family, per recorded frame: the game time from the antic entry, the Control state and its time, the clip / frame, the
Clapper's position and velocity, flipX, the root hurtbox (its layer-11 box, which is also its body DamageHero) and the
enabled Slam Collider 1 / 2 boxes (the hammer: parry 4, the slash passes through it), and the hero (position,
velocity, health, the damage events naming their source). Boxes are axis aligned [x0, x1, y0, y1] in world units.

template: the slam in the Clapper's frame (x mirrored by its facing at the Slam 0 entry, the origin at its position at
the antic entry), per game frame from the antic entry: the boxes' spread over the slams, the lunge's displacement and
what it depends on.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CLAPPER = "Song Heavy Sentry"
SLAM = ("Slam Antic", "Slam 0", "Slam 1", "Slam Effects?", "Slam 2", "Slam Recover")
HAMMER = ("Slam Collider 1", "Slam Collider 2")


def _box(vs) -> list[float] | None:
    if not vs:
        return None
    xs, ys = vs[0::2], vs[1::2]
    return [round(min(xs), 3), round(max(xs), 3), round(min(ys), 3), round(max(ys), 3)]


def _control(e: dict) -> tuple[str | None, float]:
    for m in e.get("fsms") or ():
        if m.get("name") == "Control":
            return m.get("state"), float(m.get("t") or 0.0)
    return None, 0.0


def frame_of(e: dict, s: dict, t: float) -> dict:
    st, tin = _control(e)
    root, ham = None, {}
    for c in e.get("colliders") or ():
        nm = c.get("name") or ""
        if c.get("layer") == 11 and nm.startswith(CLAPPER) and root is None:
            root = _box(c.get("verts_world"))
        elif nm.startswith(HAMMER) and "Ally" not in nm and c.get("enabled"):
            ham[nm.split(" (")[0]] = _box(c.get("verts_world"))
    h = s.get("hero") or {}
    a = e.get("anim") or {}
    dmg = [((ev.get("d") or {}).get("source"), (ev.get("d") or {}).get("invuln"))
           for ev in s.get("ev") or () if ev.get("k") == "damage"]
    hpl = [(ev.get("d") or {}).get("source") for ev in s.get("ev") or ()
           if ev.get("k") == "hp" and (ev.get("d") or {}).get("delta", 0) < 0]
    return {"f": s["f"], "t": round(t, 4), "dt": s.get("dt"), "st": st, "tin": round(tin, 4), "clip": a.get("clip"),
            "af": a.get("frame"), "pos": [round(v, 3) for v in (e.get("pos") or [0, 0])[:2]],
            "vel": [round(v, 2) for v in (e.get("vel") or [0, 0])[:2]], "flip": bool(e.get("flipX")), "root": root,
            "ham": ham, "hero": [round(v, 3) for v in (h.get("pos") or [0, 0])[:2]],
            "hvel": [round(v, 2) for v in (h.get("vel") or [0, 0])[:2]], "hbox": h.get("box"),
            "hp": h.get("health"), "inv": h.get("invulnerable"), "dmg": dmg, "hpl": hpl,
            "clip_h": (h.get("anim") or {}).get("clip"), "mask": (s.get("input") or {}).get("mask", 0)}


def scan(rec: Path) -> list[dict]:
    from ssbot.tools.pogo_outcomes import _states, rec_name
    name = rec_name(rec)
    live: dict[int, dict] = {}
    out = []
    for s in _states(rec):
        dt = float(s.get("dt") or 0.0)
        seen = set()
        for e in s.get("ents") or ():
            if e.get("type_key") != CLAPPER or e.get("is_dead") or not e.get("pos"):
                continue
            iid = e.get("iid")
            seen.add(iid)
            st, _ = _control(e)
            cur = live.get(iid)
            if cur is not None and (st not in SLAM or (st == "Slam Antic" and cur["frames"][-1]["st"] != st)):
                out.append(live.pop(iid))
                cur = None
            if cur is None and st == "Slam Antic":
                cur = live[iid] = {"rec": name, "iid": iid, "f0": s["f"], "frames": [], "t": 0.0}
            if cur is not None:
                cur["frames"].append(frame_of(e, s, cur["t"]))
                cur["t"] += dt
        for iid in [k for k in live if k not in seen]:
            out.append(live.pop(iid))
    for cur in live.values():
        cur["open"] = True
        out.append(cur)
    for c in out:
        c.pop("t", None)
    return out


def build_template(paths: list[Path]) -> dict:
    """The slam in the Clapper's frame from 1x slams (every frame dt 1/60; lunges inside WALL_FREE): per state the
    median root box per frame in the state (x mirrored by the facing, relative to the current position), the hammer
    boxes per state, the state durations (frames) and the lunge (x displacement from the Slam 0 entry per frame)."""
    import numpy as np
    from collections import Counter, defaultdict
    root, ham, lunge, durs, ys = defaultdict(list), defaultdict(list), defaultdict(list), Counter(), []
    n = 0
    for p in paths:
        for line in p.read_text("utf-8").splitlines():
            r = json.loads(line)
            fr = r["frames"]
            sts = [x["st"] for x in fr]
            if r.get("open") or not all(q in sts for q in ("Slam 0", "Slam 2", "Slam Recover")):
                continue
            if any(abs(float(x["dt"] or 0) - 1 / 60) > 0.002 for x in fr):
                continue
            if not (WALL_FREE[0] < fr[0]["pos"][0] < WALL_FREE[1]):
                continue
            n += 1
            face = 1 if fr[0]["flip"] else -1
            i0 = sts.index("Slam 0")
            durs[tuple((s, sts.count(s)) for s in dict.fromkeys(sts))] += 1
            ki = Counter()
            for k, x in enumerate(fr):
                s = x["st"]
                j = ki[s]
                ki[s] += 1
                px, py = x["pos"]
                if x["root"]:
                    b = x["root"]
                    xs = sorted(((b[0] - px) * face, (b[1] - px) * face))
                    root[(s, j)].append((xs[0], xs[1], b[2] - py, b[3] - py))
                for nm, b in x["ham"].items():
                    xs = sorted(((b[0] - px) * face, (b[1] - px) * face))
                    ham[(s, nm)].append((xs[0], xs[1], b[2] - py, b[3] - py))
                if k >= i0:
                    lunge[k - i0].append((px - fr[i0]["pos"][0]) * face)
                if k == 0:
                    ys.append(py - (x["root"][2] if x["root"] else py))
    med = lambda v: [round(float(q), 3) for q in np.median(np.asarray(v), axis=0)]   # noqa: E731
    st_d = defaultdict(Counter)
    for seq, c in durs.items():
        for s, d in seq:
            st_d[s][d] += c
    out = {"n_slams": n, "pos_above_floor": round(float(np.median(ys)), 3),
           "durations": {s: dict(sorted(c.items())) for s, c in st_d.items()},
           "root": {s: [med(root[(s, j)]) for j in range(max(jj for (ss, jj) in root if ss == s) + 1)
                        if len(root[(s, j)]) >= 20] for s in SLAM if any(ss == s for ss, _ in root)},
           "hammer": {f"{s}|{nm}": med(v) for (s, nm), v in ham.items() if len(v) >= 20},
           "lunge": {str(k): [round(float(q), 3) for q in np.percentile(v, [10, 50, 90])]
                     for k, v in sorted(lunge.items()) if k <= 20 and len(v) >= 20},
           "lunge_vx": 30.0, "physics_dt": 0.02}
    return out


WALL_FREE = (19.5, 43.5)      # a lunge from here does not reach a wall (walls 15.29 / 47.65, lunge <= 4.2 u + body)
TERRAIN_REC = Path(r"C:\ssbot\data\m2_pogo\live\2026-10-11\TRAIN\pogo_probe_s704000")


def load_kin(rec: Path = TERRAIN_REC):
    """The Wanderer's kinematics parameters and the Forum terrain (from a recording's terrain message)."""
    from ssbot.knowledge import kinematics as kin
    from ssbot.record.recorder import RecordingReader
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    params = kin.HeroParams.load(CREST_PARAMS["Wanderer"])
    terrain = None
    for _, m in RecordingReader(rec).terrain():
        terrain = kin.Terrain2D.from_message(m, params.scene("Hang_04"))
        break
    return params, terrain


from ssbot.combat.pogo_slam import PRE_PROTECT_F  # noqa: E402

CHECK_S = 0.75                # game s after the press the check follows (the HP loss window of the lead's quick look)
PRE_F = 150                   # recorded frames before the press the state estimate reads


def _clapper_boxes(s: dict, iid: int) -> tuple[list | None, list, str | None]:
    """The Clapper's root box (its body DamageHero), its enabled hammer boxes [(name, box)] and its Control state."""
    e = next((x for x in s.get("ents") or () if x.get("iid") == iid), None)
    if e is None or e.get("is_dead"):
        return None, [], None
    f = frame_of(e, s, 0.0)
    return f["root"], list(f["ham"].items()), f["st"]


def check_one(params, terrain, W: list[dict], i0: int, row: dict) -> dict:
    """The theory on one recorded down slash: the hero's state before the press (the logged pose, velocity and
    cstate), the logged inputs and frame times after it, the Clapper's logged boxes per frame (row clappers[0]); the
    predicted contact (the slash polygon on the predicted path against the root box in the active window), the
    predicted hit / miss branch and its first damage (the hero's box against the hammer and the body, i-frames from
    the rollout, the body off for 0.5 s after the contact) against what happened."""
    import numpy as np
    from ssbot.combat.pogo_model import ACTIVE, meets, slash_poly
    from ssbot.knowledge import kinematics as kin
    from ssbot.tools.pogo_check import real_contact
    iid = row["clappers"][0]["iid"]
    tr = kin.Trace.from_states(W, params, mask_source="input" if not any((s.get("act") or {}).get("mask") for s in W) else "act")
    start = kin.estimate_state(tr, [i0 - 1], params, terrain=terrain)
    n = len(W) - i0
    masks = tr.mask[i0:i0 + n][None]
    dt = tr.dt[i0:i0 + n][None]
    fs = tr.fs[i0:i0 + n][None]
    tcum = np.concatenate([[0.0], np.cumsum(tr.dt[i0:i0 + n])])     # game time at rollout index j (j = 0: press-1)
    tp = tcum[1]                                                     # the press frame's
    miss = kin.rollout(start, masks, params, terrain, dt=dt, fs=fs)
    facing = 1 if float((W[i0].get("hero") or {}).get("facing") or 1) >= 0 else -1
    fl = miss.flags[0]
    boxes = [_clapper_boxes(W[i0 - 1 + j], iid) if j >= 1 else (None, [], None) for j in range(n + 1)]
    g = np.flatnonzero((fl[1:] & kin.F_GROUND) != 0)
    last = int(g[0]) if len(g) else n
    sp = slash_poly(facing)
    cj = -1
    for j in range(1, last + 1):
        el = tcum[j] - tp
        if el < (ACTIVE[0] - 0.5) / 60 or el > (ACTIVE[1] + 0.5) / 60:
            continue
        rb = boxes[j][0]
        if rb is None:
            continue
        poly = np.array([[rb[0], rb[2]], [rb[1], rb[2]], [rb[1], rb[3]], [rb[0], rb[3]]])
        if meets(sp + miss.pos[0, j], poly):
            cj = j
            break

    def first_damage(ro, j_from, contact_j):
        fl_ = ro.flags[0]
        gg = np.flatnonzero((fl_[j_from + 1:] & kin.F_GROUND) != 0)
        jl = j_from + 1 + int(gg[0]) if len(gg) else n
        for j in range(max(j_from, 1), n + 1):
            if tcum[j] - tp > CHECK_S:
                break
            if fl_[j] & kin.F_INVULN:
                continue
            if contact_j is not None and contact_j - PRE_PROTECT_F <= j < contact_j:
                continue
            hx0, hy0, hx1, hy1 = ro.box[0, j]
            rb, ham, _ = boxes[j]
            srcs = [(nm, b) for nm, b in ham]
            if rb is not None:
                srcs.append(("body", rb))
            for nm, b in srcs:
                if b[0] < hx1 and b[1] > hx0 and b[2] < hy1 and b[3] > hy0:
                    return {"t": round(float(tcum[j] - tp), 4), "src": nm, "landed_before": j > jl}
        return None

    pred_miss = first_damage(miss, 1, None)
    if cj >= 0 and pred_miss is not None and pred_miss["t"] < tcum[max(cj - PRE_PROTECT_F, 0)] - tp - 1e-6:
        cj = -1                                                      # hit before the contact: the slash is cancelled
    pred_hit = None
    if cj >= 0:
        ev = np.zeros((1, n), np.int64)
        ev[0, cj - 1] = kin.EV_POGO
        hit = kin.rollout(start, masks, params, terrain, events=ev, dt=dt, fs=fs)
        pred_hit = first_damage(hit, 1, cj)
    fc = real_contact(row)
    # the damage rule alone: the logged hero box and invulnerability against the logged boxes
    jc_real = next((j for j in range(1, n + 1) if W[i0 - 1 + j]["f"] == fc), None) if fc is not None else None
    # every real bounce contact in the window (a chain's earlier ones too): vy -10 then the pogo within 3 frames
    vys = [float(((x.get("hero") or {}).get("vel") or [0, 0])[1]) for x in W]
    tw = np.concatenate([[0.0], np.cumsum([float(x.get("dt") or 0.0) for x in W[1:]])])
    contacts_w = [i for i in range(len(W) - 1) if abs(vys[i] + 10.0) < 0.05 and any(v >= 15.0 for v in vys[i + 1:i + 4])]

    def rule(iframes: str, delay: int, need_step: bool, pre: int = 0, length: float = 0.16):
        """The first damage on the logged path: iframes 'first' (0.16 s from this slash's first contact) or 'each'
        (from every contact, earlier slashes' included); delay: a hammer collider hurts from the frame after the one
        it is logged enabled on (its box then); need_step: only frames with a physics step detect."""
        first_c = None if jc_real is None else i0 - 1 + jc_real
        for j in range(1, n + 1):
            if tcum[j] - tp > CHECK_S:
                break
            iw = i0 - 1 + j
            h = W[iw].get("hero") or {}
            # the previous frame's flag: the frame that takes a hit already logs the hurt i-frames it started
            if (W[iw - 1].get("hero") or {}).get("invulnerable") or not h.get("box"):
                continue
            if need_step and not (W[iw].get("fs") or 0):
                continue
            cs = contacts_w if iframes == "each" else ([first_c] if first_c is not None else [])
            if any(c is not None and -pre / 60 - 1e-6 <= tw[iw] - tw[c] < length for c in cs):
                continue
            hx0, hy0, hx1, hy1 = h["box"]
            rb, ham, _ = boxes[j]
            srcs = list(_clapper_boxes(W[iw - delay], iid)[1]) if delay and iw - delay >= 0 else list(ham)
            if rb is not None:
                srcs.append(("body", rb))
            hit_src = [(nm, round(min(b[1], hx1) - max(b[0], hx0), 3), round(min(b[3], hy1) - max(b[2], hy0), 3))
                       for nm, b in srcs if b[0] < hx1 and b[1] > hx0 and b[2] < hy1 and b[3] > hy0]
            if hit_src:
                return {"t": round(float(tcum[j] - tp), 4), "src": hit_src}
        return None
    real_rule = rule("first", 0, False, PRE_PROTECT_F, 0.16)
    real_rules = {f"{a}|{d}|{int(st)}|{pr}|{ln}": rule(a, d, st, pr, ln) for a in ("first", "each") for d in (0, 1)
                  for st in (False, True) for pr in (0, 1, 2, 3) for ln in (0.16, 0.2)}
    loss = None
    lethal_block = (row.get("hp0") or 9) <= 2        # a probe's LethalBlock: a lethal hit is blocked (no HP loss)
    if row.get("loss_f") is not None and row.get("loss_t") is not None and row["loss_t"] <= CHECK_S:
        loss = {"t": row["loss_t"], "src": row.get("loss_src")}
    st = boxes[1][2]
    return {"rec": row["session"], "f0": row["f0"], "state": row["clappers"][0]["state"], "t_state": row["clappers"][0]["t"],
            "pred_bounce": cj >= 0, "pred_contact_t": round(float(tcum[cj] - tp), 4) if cj >= 0 else None,
            "real_bounce": fc is not None, "real_contact_t": (round(float(row["t_of"][str(fc)]) - float(row["t_of"].get(str(row["f0"]), 0.0)), 4)
                                                         if fc is not None and str(fc) in row["t_of"] else None),
            "pred_loss": pred_hit if cj >= 0 else pred_miss, "pred_miss_loss": pred_miss, "real_loss": loss,
            "state_press": st, "hits": bool(row["hits"]), "real_rule": real_rule, "real_rules": real_rules,
            "hp0": row.get("hp0"), "lethal_block": lethal_block}


def check(recs: list[Path], rows_path: list[Path], out: Path) -> list[dict]:
    """check_one over every row (a down slash with a Clapper within 9 u) of the given recordings."""
    from collections import defaultdict, deque
    from ssbot.tools.pogo_outcomes import _states, rec_name, recordings
    params, terrain = load_kin()
    rows_by = defaultdict(dict)
    for p in rows_path:
        for line in p.read_text("utf-8").splitlines():
            r = json.loads(line)
            if r["clappers"]:
                rows_by[r["session"]][r["f0"]] = r
    res = []
    with out.open("w", encoding="utf-8") as fo:
        for rec in recordings(recs):
            name = rec_name(rec)
            rows = rows_by.get(name)
            if not rows:
                continue
            post = 130
            buf: deque = deque(maxlen=PRE_F + post + 2)
            pend = sorted(rows)
            for s in _states(rec):
                buf.append(s)
                while pend and s["f"] >= pend[0] + post:
                    f0 = pend.pop(0)
                    W = list(buf)
                    i0 = next((i for i, x in enumerate(W) if x["f"] == f0), None)
                    if i0 is None or i0 < 10:
                        continue
                    try:
                        o = check_one(params, terrain, W, i0, rows[f0])
                    except Exception as ex:  # noqa: BLE001
                        o = {"rec": name, "f0": f0, "error": repr(ex)}
                    fo.write(json.dumps(o) + "\n")
                    fo.flush()
                    res.append(o)
                if not pend:
                    break
            print(name, len(rows), flush=True)
    return res


K_STATE0 = {"Slam Antic": 0, "Slam 0": 49, "Slam 1": 54, "Slam 2": 57, "Slam Recover": 63}


def person_points(rows_path: Path) -> list[dict]:
    """The person's down slashes during a Clapper slam that bounced without an HP loss within CHECK_S: the press state
    (slam frame from the antic entry, dx along the Clapper's facing, dy from its position, vy)."""
    from ssbot.tools.pogo_check import real_contact
    out = []
    for line in rows_path.read_text("utf-8").splitlines():
        r = json.loads(line)
        if not r["clappers"]:
            continue
        c = r["clappers"][0]
        if c["state"] not in K_STATE0 or real_contact(r) is None:
            continue
        if r.get("loss_t") is not None and r["loss_t"] <= CHECK_S:
            continue
        face = 1 if c["flipX"] else -1
        h = r["hero0"]
        out.append({"rec": r["session"], "f0": r["f0"], "state": c["state"], "t": c["t"],
                    "k": K_STATE0[c["state"]] + int(round(float(c["t"]) * 60)),
                    "dx": round((h["pos"][0] - c["pos"][0]) * face, 3), "dy": round(h["pos"][1] - c["pos"][1], 3),
                    "vy": round(float((h.get("vel") or [0, 0])[1]), 2)})
    return out


def make_targets(rows_path: Path, out_dir: Path, rep_center: int = 3, seed: int = 46) -> dict:
    """The targeted trials (the person's method): (A) the person's success points reproduced, (B) one robust centre
    per distinct success region the theory predicts (the contact's slam state x the horizontal after the press x the
    jump held after it x vy class at the press), (C) scans around every centre: the jump frame +-1..6 (the press
    time), x0 +-0.3..1.2 u, the other horizontals after the press (incl. against the motion), the jump held +-4
    frames. Every target carries the theory's prediction under each timing variant (antic 48 / 49, Slam 0 4 / 5, the
    lunge's physics phase)."""
    import random
    import numpy as np
    from ssbot.combat.pogo_slam import FLOOR_Y, SlamTheory, SlamTimeline
    params, terrain = load_kin()
    th = SlamTheory(params, terrain)
    tl = SlamTimeline.load()
    variants = SlamTimeline.variants()
    paths = th.paths(hs=(3, 7, 11, 16), as_=range(6, 31, 2))
    miss = th.miss_rollouts(paths)
    taus = np.arange(4, 71)
    x0s = np.round(np.arange(0.5, 9.0001, 0.1), 2)
    cy = tl.pos_y + FLOOR_Y
    cells = []
    for i, p in enumerate(paths):
        o = th.cells(tl, p, miss, i, 1, x0s, taus, cy)
        cells.append(o)
    states = np.array(tl.state + ["after"] * 400)

    def outcome(o, ti, xi):
        c = int(o["contact"][ti, xi])
        return {"bounce": c >= 0, "hit_safe": bool(c >= 0 and not o["hit_bad"][ti, xi]),
                "miss_safe": bool(not o["miss_bad"][ti, xi]),
                "contact_state": str(states[int(o["contact_k"][ti, xi])]) if c >= 0 else None}

    def pred_all(pi, tau, x0):
        """The prediction for path pi at (tau, x0) under every timing variant."""
        p = paths[pi]
        res = []
        for v in variants:
            o = th.cells(v, p, miss, pi, 1, np.array([x0]), np.array([tau]), cy)
            res.append(outcome(o, 0, 0))
        return {k: round(sum(r[k] for r in res) / len(res), 3) for k in ("bounce", "hit_safe", "miss_safe")} | {
            "contact_state": sorted({r["contact_state"] for r in res if r["contact_state"]})}

    def target(pi, tau, x0, group, note):
        p = paths[pi]
        if not (4 <= tau <= 75 and 0.3 <= x0 <= 9.5):
            return None
        o = th.cells(tl, p, miss, pi, 1, np.array([x0]), np.array([tau]), cy)
        if not o["valid"][0, 0]:
            return None
        return {"group": group, "note": note, "path": pi, "tau_j": int(tau), "x0": round(float(x0), 2), "h": p.h, "a": p.a,
                "pre": p.pre, "post": p.post, "jpost": p.jpost, "k_press": int(tau + p.a),
                "dx_press": round(float(o["dxp"][0, 0]), 3), "dy_press": round(float(o["dyp"]), 3),
                "vy_press": round(float(o["vyp"]), 2), "pred": outcome(o, 0, 0), "pred_var": pred_all(pi, tau, x0),
                "masks": [int(m) for m in p.masks]}

    tg: list[dict] = []
    centres = []
    # (A) the person's success points
    pts = person_points(rows_path)
    for q in pts:
        best = None
        for pi, o in enumerate(cells):
            kp = o["kp"][:, None]
            d = (np.abs(kp - q["k"]) / 1.0) ** 2 + ((o["dxp"] - q["dx"]) / 0.3) ** 2 + ((o["dyp"] - q["dy"]) / 0.3) ** 2 \
                + ((o["vyp"] - q["vy"]) / 3.0) ** 2
            d = np.where(o["valid"], d, np.inf)
            ti, xi = np.unravel_index(np.argmin(d), d.shape)
            if best is None or d[ti, xi] < best[0]:
                best = (float(d[ti, xi]), pi, int(taus[ti]), float(x0s[xi]))
        if best is not None and best[0] < 6.0:
            centres.append(("A", best[1], best[2], best[3], f"person {q['rec']} f{q['f0']} {q['state']} t{q['t']}"))
    # (B) one robust centre per distinct predicted success region
    clusters: dict = {}
    for pi, o in enumerate(cells):
        p = paths[pi]
        ok = (o["contact"] >= 0) & ~o["hit_bad"] & ~o["miss_bad"] & o["valid"]
        if not ok.any():
            continue
        # robustness: the success holds for the neighbours (tau +-2, x0 +-0.3)
        r = ok.copy()
        for dt_ in (-2, -1, 1, 2):
            r &= np.roll(ok, dt_, axis=0)
        for dx_ in (-3, -1, 1, 3):
            r &= np.roll(ok, dx_, axis=1)
        for ti, xi in zip(*np.nonzero(r)):
            ck = int(o["contact_k"][ti, xi])
            vc = "rise" if o["vyp"] > 3 else ("fall" if o["vyp"] < -3 else "apex")
            key = (str(states[ck]), p.post, p.jpost, vc, bool(o["dxp"][ti, xi] < 0))
            clusters.setdefault(key, []).append((pi, int(taus[ti]), float(x0s[xi])))
    rng = random.Random(seed)
    per_state: dict = {}
    for key, lst in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        if len(lst) < 20 or per_state.get(key[0], 0) >= 3:
            continue
        per_state[key[0]] = per_state.get(key[0], 0) + 1
        pi, tau, x0 = rng.choice(lst)
        centres.append(("B", pi, tau, x0, "region " + "|".join(map(str, key)) + f" ({len(lst)} robust cells)"))
    # (C) the scans
    for g, pi, tau, x0, note in centres:
        for _ in range(rep_center):
            tg.append(target(pi, tau, x0, g, note))
        for dt_ in (-6, -4, -2, -1, 1, 2, 4, 6):
            tg.append(target(pi, tau + dt_, x0, g + "C_tau", f"{note} tau{dt_:+d}"))
        for dx_ in (-1.2, -0.6, -0.3, 0.3, 0.6, 1.2):
            tg.append(target(pi, tau, x0 + dx_, g + "C_x0", f"{note} x0{dx_:+.1f}"))
        p = paths[pi]
        for q, pp in enumerate(paths):
            if (pp.h, pp.a, pp.pre, pp.jpost) == (p.h, p.a, p.pre, p.jpost) and pp.post != p.post:
                tg.append(target(q, tau, x0, g + "C_post", f"{note} post{pp.post:+d}"))
            if (pp.a, pp.pre, pp.post, pp.jpost) == (p.a, p.pre, p.post, p.jpost) and abs(pp.h - p.h) == 4:
                tg.append(target(q, tau, x0, g + "C_h", f"{note} h{pp.h}"))
    tg = [t for t in tg if t is not None]
    for n, t in enumerate(tg):
        t["id"] = n
    order = list(range(len(tg)))
    rng.shuffle(order)
    out_dir.mkdir(parents=True, exist_ok=True)
    halves = [[tg[i] for i in order[0::2]], [tg[i] for i in order[1::2]]]
    for k, h in enumerate(halves):
        (out_dir / f"t_i{k}.jsonl").write_text("".join(json.dumps(t) + "\n" for t in h), "utf-8")
    meta = {"n": len(tg), "centres": [(g, pi, tau, x0, note) for g, pi, tau, x0, note in centres],
            "person_points": pts, "n_clusters": len(clusters)}
    (out_dir / "targets_meta.json").write_text(json.dumps(meta, indent=1), "utf-8")
    return meta


FLOOR_Y_HERO = 4.568          # hero.pos y standing on the Forum floor
WINDOWS = (("antic 0-24", 0, 25), ("antic 25-39", 25, 40), ("antic 40-48", 40, 49), ("slam0", 49, 54),
           ("slam1", 54, 57), ("slam2", 57, 63), ("recover", 63, 78), ("after", 78, 200))


def window_of(k: int) -> str:
    return next(nm for nm, lo, hi in WINDOWS if lo <= k < hi)


def make_targets2(out_dir: Path, first: list[dict], seed: int = 47, name: str = "t2", approach: bool = False,
                  skip_covered: bool = True, rep: int = 3, tau_scan=(-4, -2, 2, 4), x0_scan=(-0.6, -0.3, 0.3, 0.6),
                  press2=(12, 16, 20, 24), id0: int = 10000) -> dict:
    """Batch 2 with the corrected theory (PRE_PROTECT_F): one robust centre per (press window, front / behind, layer
    'success' = both branches safe or 'hit' = the bounce branch safe) not covered by batch 1, small scans (jump frame
    +-2 / 4, x0 +-0.3 / 0.6), and a second press after the bounce (12 / 16 / 20 / 24 frames after the first) on the
    batch-1 centres whose bounce the theory predicts in every timing variant. approach: only cells and targets whose
    approach (the jump to the press) is not hit in the nominal timing (batch 3: 43-48 % of the batch-1 / 2 trials were
    hit before the press)."""
    import random
    import numpy as np
    from ssbot.combat.pogo_slam import FLOOR_Y, M_A, M_D, SlamTheory, SlamTimeline
    params, terrain = load_kin()
    th = SlamTheory(params, terrain)
    tl = SlamTimeline.load()
    variants = SlamTimeline.variants()
    paths = th.paths(hs=(3, 7, 11, 16), as_=range(6, 31, 2))
    miss = th.miss_rollouts(paths)
    taus = np.arange(4, 71)
    x0s = np.round(np.arange(2.2, 9.0001, 0.1), 2)
    cy = tl.pos_y + FLOOR_Y
    rng = random.Random(seed)
    covered = {(window_of(t["k_press"]), t["dx_press"] >= 0) for t in first if t["group"] in ("A", "B")}
    clusters: dict = {}
    for pi, p in enumerate(paths):
        o = th.cells(tl, p, miss, pi, 1, x0s, taus, cy)
        hit = (o["contact"] >= 0) & ~o["hit_bad"] & o["valid"]
        if approach:
            hit &= ~o["pre_bad"]
        for layer, ok in (("success", hit & ~o["miss_bad"]), ("hit", hit & o["miss_bad"])):
            r = ok.copy()
            for d in (-2, -1, 1, 2):
                r &= np.roll(ok, d, axis=0)
            for d in (-3, 3):
                r &= np.roll(ok, d, axis=1)
            for ti, xi in zip(*np.nonzero(r)):
                key = (window_of(int(o["kp"][ti])), bool(o["dxp"][ti, xi] >= 0), layer)
                clusters.setdefault(key, []).append((pi, int(taus[ti]), float(x0s[xi])))

    def pred_all(p, pi, tau, x0):
        res = []
        for v in variants:
            o = th.cells(v, p, miss, pi, 1, np.array([x0]), np.array([tau]), cy)
            c = int(o["contact"][0, 0])
            res.append((c >= 0, c >= 0 and not o["hit_bad"][0, 0], not o["miss_bad"][0, 0]))
        return {k: round(sum(r[i] for r in res) / len(res), 3) for i, k in enumerate(("bounce", "hit_safe", "miss_safe"))}

    def target(pi, tau, x0, group, note, masks=None, press2=None):
        p = paths[pi]
        o = th.cells(tl, p, miss, pi, 1, np.array([x0]), np.array([tau]), cy)
        if not o["valid"][0, 0] or x0 < 2.2 or (approach and o["pre_bad"][0, 0]):
            return None
        c = int(o["contact"][0, 0])
        pv = pred_all(p, pi, tau, x0)
        return {"group": group, "note": note, "path": pi, "tau_j": int(tau), "x0": round(float(x0), 2), "h": p.h,
                "a": p.a, "pre": p.pre, "post": p.post, "jpost": p.jpost, "k_press": int(tau + p.a), "press2": press2,
                "dx_press": round(float(o["dxp"][0, 0]), 3), "dy_press": round(float(o["dyp"]), 3),
                "vy_press": round(float(o["vyp"]), 2),
                "pred": {"bounce": c >= 0, "hit_safe": bool(c >= 0 and not o["hit_bad"][0, 0]),
                         "miss_safe": bool(not o["miss_bad"][0, 0])}, "pred_var": pv,
                "masks": [int(m) for m in (p.masks if masks is None else masks)]}

    tg, centres = [], []
    for key, lst in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        if (skip_covered and (key[0], key[1]) in covered) or len(lst) < 10:
            continue
        pi, tau, x0 = rng.choice(lst)
        note = f"T2 {key[0]} {'front' if key[1] else 'behind'} {key[2]} ({len(lst)} robust cells)"
        centres.append((pi, tau, x0, note))
        g = "B" + name[1:]
        tg += [target(pi, tau, x0, g, note) for _ in range(rep)]
        tg += [target(pi, tau + d, x0, g + "C_tau", f"{note} tau{d:+d}") for d in tau_scan]
        tg += [target(pi, tau, x0 + d, g + "C_x0", f"{note} x0{d:+.1f}") for d in x0_scan]
    # the second press after the bounce
    seen = set()
    for t in first:
        if t["group"] not in ("A", "B") or t["note"] in seen or t["pred_var"]["bounce"] < 1.0:
            continue
        seen.add(t["note"])
        for d in press2:
            m = list(t["masks"])
            a2 = t["a"] + d
            if a2 + 3 >= len(m):
                continue
            for j in range(a2 - 3, a2 + 3):
                m[j] |= M_D
            m[a2] |= M_A
            tt = target(t["path"], t["tau_j"], t["x0"], "P" + name[1:], f"{t['note']} press2 +{d}", masks=m, press2=d)
            if tt is not None:
                tg += [tt, dict(tt)]
    tg = [t for t in tg if t is not None]
    for n, t in enumerate(tg):
        t["id"] = id0 + n
    order = list(range(len(tg)))
    rng.shuffle(order)
    out_dir.mkdir(parents=True, exist_ok=True)
    for k in (0, 1):
        (out_dir / f"{name}_i{k}.jsonl").write_text("".join(json.dumps(tg[i]) + "\n" for i in order[k::2]), "utf-8")
    meta = {"n": len(tg), "centres": centres, "clusters": {"|".join(map(str, k)): len(v) for k, v in clusters.items()}}
    (out_dir / f"targets{name[1:]}_meta.json").write_text(json.dumps(meta, indent=1), "utf-8")
    return meta


def repredict(trials: list[dict]) -> dict:
    """The final theory at each trial's plan (path, jump frame, start x; nominal timing and the 8 variants), the
    approach included (a hit between the jump and the press: 'H0', the press state never reached), against what
    happened (H0 = hurt before any down slash; else S / BL / N / NL with the loss before the landing)."""
    from collections import Counter
    import numpy as np
    from ssbot.combat.pogo_slam import FLOOR_Y, SlamTheory, SlamTimeline
    params, terrain = load_kin()
    th = SlamTheory(params, terrain)
    tls = [SlamTimeline.load()] + SlamTimeline.variants()
    paths = th.paths(hs=(3, 7, 11, 16), as_=range(6, 31, 2))
    miss = th.miss_rollouts(paths)
    cy = tls[0].pos_y + FLOOR_Y

    def cls(b, l):
        return ("S" if not l else "BL") if b else ("N" if not l else "NL")
    conf, conf_pv = Counter(), Counter()
    rows = []
    for o in trials:
        tg = o["target"]
        if tg.get("press2") or o.get("skip") in ("no slam", "antic seen too late") or (o.get("hp0") or 9) <= 2:
            continue
        if o.get("skip") not in (None, "no down slash"):
            continue
        res = []
        for tl in tls:
            c = th.cells(tl, paths[tg["path"]], miss, tg["path"], 1, np.array([tg["x0"]]), np.array([tg["tau_j"]]), cy)
            b = int(c["contact"][0, 0]) >= 0
            res.append((bool(c["pre_bad"][0, 0]), b, b and not c["hit_bad"][0, 0], not c["miss_bad"][0, 0]))
        pre, b, hs, ms = res[0]
        pred = "H0" if pre else cls(b, not (hs if b else ms))
        frac = {k: round(sum(r[i] for r in res) / len(res), 2) for i, k in enumerate(("pre_bad", "bounce", "hit_safe", "miss_safe"))}
        real = "H0" if o.get("skip") == "no down slash" else cls(o["bounce"], o["loss_air"])
        conf[(real, pred)] += 1
        pv = "H0" if frac["pre_bad"] >= 0.5 else cls(frac["bounce"] >= 0.5, not ((frac["hit_safe"] if frac["bounce"] >= 0.5 else frac["miss_safe"]) >= 0.5))
        conf_pv[(real, pv)] += 1
        rows.append({"n": o["n"], "rec": o.get("rec"), "real": real, "pred": pred, "pred_var_cls": pv, "frac": frac,
                     "late": o.get("late")})

    def summ(c):
        n = sum(c.values())
        return {"n": n, "agree": round(sum(v for (a, b), v in c.items() if a == b) / max(n, 1), 3),
                "confusion": {f"{a}->{b}": v for (a, b), v in sorted(c.items())}}
    return {"nominal": summ(conf), "majority_of_variants": summ(conf_pv), "rows": rows}


def live_report(trial_files: list[Path], rows_path: Path, check_path: Path) -> dict:
    """The targeted trials joined with their down slash (pogo_outcomes rows) and the theory on it (check): per trial
    the outcome (bounce = the real contact, loss = an HP loss within CHECK_S of the press, approach_loss = one before
    the press), the realized jump frame / start x / press state, the pre-registered prediction and the theory on the
    logged inputs; per centre (group A / B) and scan the success rates."""
    from collections import defaultdict
    from ssbot.tools.pogo_check import real_contact
    rows = {}
    for line in rows_path.read_text("utf-8").splitlines():
        r = json.loads(line)
        rows[(r["session"].split("/")[-1], r["f0"])] = r
    chk = {}
    for line in check_path.read_text("utf-8").splitlines():
        c = json.loads(line)
        chk[(c["rec"].split("/")[-1], c["f0"])] = c
    out = []
    for tf in trial_files:
        rec = tf.parent.name
        for line in tf.read_text("utf-8").splitlines():
            t = json.loads(line)
            if "f_press" not in t:
                out.append({"n": t["n"], "target": t["target"], "skip": t.get("skip") or t.get("error")})
                continue
            # the down slash of this trial: the press frame +- 2
            r = next((rows[(rec, f)] for f in range(t["f_press"] - 2, t["f_press"] + 3) if (rec, f) in rows), None)
            o = {"n": t["n"], "rec": rec, "target": t["target"], "late": t.get("late"), "gaps": t.get("gaps"),
                 "f_press": t["f_press"]}
            if r is None:
                o["skip"] = "no down slash"
                out.append(o)
                continue
            c = chk.get((rec, r["f0"]))
            cl = r["clappers"][0] if r["clappers"] else None
            fc = real_contact(r)
            o |= {"bounce": fc is not None, "loss": r.get("loss_t") is not None and r["loss_t"] <= CHECK_S,
                  "loss_t": r.get("loss_t"), "loss_src": r.get("loss_src"), "press_shift": r["f0"] - t["f_press"],
                  "state": cl and cl["state"], "t_state": cl and cl["t"],
                  "dx": cl and round((r["hero0"]["pos"][0] - cl["pos"][0]) * (1 if cl["flipX"] else -1), 3),
                  "dy": cl and round(r["hero0"]["pos"][1] - cl["pos"][1], 3),
                  "vy": round(float((r["hero0"].get("vel") or [0, 0])[1]), 2), "hp0": r.get("hp0"),
                  "theory": c and {k: c.get(k) for k in ("pred_bounce", "pred_loss", "pred_miss_loss", "real_rule")}}
            # the landing after the press (on the floor: hero.pos y at the standing height, no vertical speed)
            land = next((float(r["t_of"][str(x["f"])]) for x in r["hero"] if x["f"] > r["f0"] + 2
                         and str(x["f"]) in r["t_of"] and abs(float((x["vel"] or [0, 0])[1])) < 0.01
                         and float(x["pos"][1]) < FLOOR_Y_HERO + 0.05), None)
            o["land_t"] = land
            o["loss_air"] = o["loss"] and (land is None or float(r["loss_t"]) <= land + 1e-6)
            o["success"] = o["bounce"] and not o["loss"]
            out.append(o)
    # per centre: the centre trials and each scan's points
    by = defaultdict(list)
    for o in out:
        if o.get("skip"):
            continue
        tg = o["target"]
        base = tg["note"].split(" tau")[0].split(" x0")[0].split(" post")[0].split(" h")[0]
        by[(base, tg["group"], tg["note"])].append(o)
    table = []
    for (base, g, note), lst in sorted(by.items()):
        n = len(lst)
        table.append({"centre": base, "group": g, "point": note, "n": n,
                      "bounce": round(sum(o["bounce"] for o in lst) / n, 3),
                      "success": round(sum(o["success"] for o in lst) / n, 3),
                      "loss": round(sum(o["loss"] for o in lst) / n, 3),
                      "pred_success": lst[0]["target"]["pred_var"]["bounce"] and min(
                          lst[0]["target"]["pred_var"]["hit_safe"], lst[0]["target"]["pred_var"]["miss_safe"]),
                      "pred": lst[0]["target"]["pred"], "pred_var": lst[0]["target"]["pred_var"]})
    on_plan = [o for o in out if not o.get("skip") and not o.get("late") and not o.get("gaps")]
    return {"trials": out, "table": table, "widths": widths(out), "accuracy": accuracy(out),
            "accuracy_on_plan": accuracy(on_plan)}


def accuracy(trials: list[dict]) -> dict:
    """The theory on the trials, by outcome class (S = bounce without an HP loss, BL = bounce then a loss, N = no
    bounce no loss, NL = no bounce and a loss): the pre-registered prediction (the target's, nominal timing, the
    planned start) and the theory on the logged inputs and boxes (check); trials whose hero had <= 2 masks (the
    probe's LethalBlock) left out. The pre-registered branches end on the landing, so their HP loss is the one before
    it (loss_air); the check follows CHECK_S."""
    from collections import Counter

    def cls(b, l):
        return ("S" if not l else "BL") if b else ("N" if not l else "NL")
    pre, chk = Counter(), Counter()
    for o in trials:
        if o.get("skip") or (o.get("hp0") or 9) <= 2:
            continue
        real = cls(o["bounce"], o["loss_air"])      # the pre-registered branches end on the landing
        p = o["target"]["pred"]
        pre[(real, cls(p["bounce"], not (p["hit_safe"] if p["bounce"] else p["miss_safe"])))] += 1
        th = o.get("theory")
        if th:
            chk[(cls(o["bounce"], o["loss"]), cls(th["pred_bounce"], th["pred_loss"] is not None))] += 1

    def summ(c):
        n = sum(c.values())
        return {"n": n, "agree": round(sum(v for (a, b), v in c.items() if a == b) / max(n, 1), 3),
                "confusion": {f"{a}->{b}": v for (a, b), v in sorted(c.items())}}
    return {"pre_registered": summ(pre), "check": summ(chk)}


def widths(trials: list[dict]) -> list[dict]:
    """Per centre: the measured success (bounce, no HP loss) at the centre and along its jump-frame and start-x scans,
    the contiguous run of scan points around the centre with success >= 0.5 (its width: frames / u), and the theory's
    for the same points (pred_var: bounce and both branches safe, or bounce and the bounce branch safe)."""
    import re
    from collections import defaultdict
    by = defaultdict(lambda: defaultdict(list))
    for o in trials:
        if o.get("skip"):
            continue
        note = o["target"]["note"]
        m = re.search(r" (tau|x0)([+-][0-9.]+)$", note)
        if m:
            by[note[:m.start()]][(m.group(1), float(m.group(2)))].append(o)
        elif not re.search(r" (post|h|press2)", note):
            by[note][("tau", 0.0)].append(o)
            by[note][("x0", 0.0)].append(o)
    out = []
    for centre, pts in by.items():
        row = {"centre": centre}
        for dim in ("tau", "x0"):
            ks = sorted(k for d, k in pts if d == dim)
            if len(ks) < 3:
                continue
            seq = []
            for k in ks:
                lst = pts[(dim, k)]
                pv = lst[0]["target"]["pred_var"]
                seq.append({"d": k, "n": len(lst), "success": round(sum(x["success"] for x in lst) / len(lst), 2),
                            "bounce": round(sum(x["bounce"] for x in lst) / len(lst), 2),
                            "pred_hit": round(min(pv["bounce"], pv["hit_safe"]), 2),
                            "pred_both": round(min(pv["bounce"], pv["hit_safe"], pv["miss_safe"]), 2)})
            ok = [s["d"] for s in seq if s["success"] >= 0.5]
            row[dim] = seq
            row[dim + "_width"] = (max(ok) - min(ok)) if ok else None
            pk = [s["d"] for s in seq if s["pred_hit"] >= 0.5]
            row[dim + "_width_pred"] = (max(pk) - min(pk)) if pk else None
        out.append(row)
    return out


def region(variant: str, out: Path, quick: bool = False) -> None:
    """The theory's grid for one timing variant ('nominal', or 'a48s4p0.2' style) into out (npz)."""
    import numpy as np
    from ssbot.combat.pogo_slam import SlamTheory, SlamTimeline
    params, terrain = load_kin()
    if variant == "nominal":
        tl = SlamTimeline.load()
    else:
        a, s, p = variant[1:3], variant[4], variant.split("p")[1]
        tl = SlamTimeline.load(antic=int(a), s0=int(s), phase=float(p))
    th = SlamTheory(params, terrain)
    paths = th.paths(hs=(5, 13), as_=range(8, 20, 3), pres=(1,), posts=(1,), jposts=(0,)) if quick else th.paths()
    x0s = np.round(np.arange(-9.0, 11.0001, 0.1), 3)
    taus = np.arange(-40, 95)
    acc = th.grid(tl, x0s, taus, paths)
    acc.save(out, {"variant": tl.name, "n_paths": len(paths)})
    print(tl.name, "paths", len(paths), "cells", int(acc.c[0].sum()), "bounce", int(acc.c[1].sum()),
          "bounce+hit safe", int(acc.c[2].sum()), "both safe", int(acc.c[4].sum()), flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("slams")
    a1.add_argument("recs", nargs="*", type=Path)
    a1.add_argument("--glob", nargs=2, metavar=("BASE", "PATTERN"), action="append", default=[])
    a1.add_argument("--out", type=Path, required=True)
    a2 = sub.add_parser("template")
    a2.add_argument("slams", nargs="+", type=Path)
    a2.add_argument("--out", type=Path, required=True)
    a3 = sub.add_parser("region")
    a3.add_argument("--variant", default="nominal")
    a3.add_argument("--quick", action="store_true")
    a3.add_argument("--out", type=Path, required=True)
    a4 = sub.add_parser("check")
    a4.add_argument("recs", nargs="*", type=Path)
    a4.add_argument("--glob", nargs=2, metavar=("BASE", "PATTERN"), action="append", default=[])
    a4.add_argument("--rows", type=Path, nargs="+", required=True)
    a4.add_argument("--out", type=Path, required=True)
    a5 = sub.add_parser("targets")
    a5.add_argument("--rows", type=Path, required=True, help="the person's rows (pogo_outcomes scan)")
    a5.add_argument("--out", type=Path, required=True)
    a6 = sub.add_parser("live")
    a6.add_argument("--trials", type=Path, nargs="+", required=True, help="target_trials.jsonl files")
    a6.add_argument("--rows", type=Path, required=True)
    a6.add_argument("--check", type=Path, required=True)
    a6.add_argument("--out", type=Path, required=True)
    a7 = sub.add_parser("targets2")
    a7.add_argument("--first", type=Path, nargs="+", required=True, help="batch-1 target files")
    a7.add_argument("--out", type=Path, required=True)
    a8 = sub.add_parser("repredict")
    a8.add_argument("live_json", type=Path)
    a8.add_argument("--out", type=Path, required=True)
    a9 = sub.add_parser("targets3")
    a9.add_argument("--meta2", type=Path, required=True)
    a9.add_argument("--first", type=Path, nargs="+", required=True)
    a9.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "targets3":
        first = [json.loads(x) for p in a.first for x in p.read_text("utf-8").splitlines() if x.strip()]
        meta = make_targets2(a.out, first, seed=48, name="t3", approach=True, skip_covered=False, rep=4,
                             tau_scan=(-8, -6, -4, -2, 2, 4, 6, 8), x0_scan=(-1.2, -0.6, -0.3, 0.3, 0.6, 1.2),
                             press2=(28, 32, 36, 40), id0=20000)
        print(json.dumps({k: v for k, v in meta.items() if k != "clusters"}, indent=1)[:3000])
        return 0
    if a.cmd == "repredict":
        rep = repredict(json.loads(a.live_json.read_text("utf-8"))["trials"])
        a.out.write_text(json.dumps(rep, indent=1), "utf-8")
        print(json.dumps({k: v for k, v in rep.items() if k != "rows"}, indent=1))
        return 0
    if a.cmd == "targets2":
        first = [json.loads(x) for p in a.first for x in p.read_text("utf-8").splitlines() if x.strip()]
        meta = make_targets2(a.out, first)
        print(json.dumps(meta, indent=1)[:5000])
        return 0
    if a.cmd == "live":
        rep = live_report(a.trials, a.rows, a.check)
        a.out.write_text(json.dumps(rep, indent=1), "utf-8")
        for row in rep["table"]:
            print(json.dumps(row)[:400])
        return 0
    if a.cmd == "targets":
        meta = make_targets(a.rows, a.out)
        print(json.dumps({k: v for k, v in meta.items() if k != "person_points"}, indent=1)[:6000])
        print("person points", len(meta["person_points"]))
        return 0
    if a.cmd == "check":
        extra = [d for base, pat in a.glob for d in sorted(Path(base).glob(pat)) if d.is_dir()]
        a.out.parent.mkdir(parents=True, exist_ok=True)
        check(list(a.recs) + extra, a.rows, a.out)
        return 0
    if a.cmd == "region":
        a.out.parent.mkdir(parents=True, exist_ok=True)
        region(a.variant, a.out, a.quick)
        return 0
    if a.cmd == "template":
        t = build_template(a.slams)
        a.out.write_text(json.dumps(t, indent=1), "utf-8")
        print(json.dumps(t)[:3000])
        return 0
    if a.cmd == "slams":
        from ssbot.tools.pogo_outcomes import recordings
        extra = [d for base, pat in a.glob for d in sorted(Path(base).glob(pat)) if d.is_dir()]
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with a.out.open("w", encoding="utf-8") as fo:
            for rec in recordings(list(a.recs) + extra):
                rows = scan(rec)
                for r in rows:
                    fo.write(json.dumps(r) + "\n")
                print(rec, len(rows), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
