"""Interaction-effect miner: what a hero attack does to the things it touches, found in recordings, not assumed.

A model-based planner can only use effects its model knows. The bot never hit a bell, it only dodged them, because no
model said a bell can be bounced on or knocked aside. This tool looks for such mechanics in any recordings (data-policy
fights, human sessions, sandbox probes), for every entity type, so the same pass finds them for a later boss or area.

Contact. A hero attack clip (CLIPS: Hunter slash, up slash, down spike) in its active time puts its box (the planner's
P17 boxes relative to the hurtbox centre, facing frame) into the world; an entity collider (circle or polygon,
enabled) that meets it is a contact. One event per (attack clip instance, entity): its first contact frame.
Outcomes over the next N frames (and 3N for slower consequences), each also measured on matched no-contact controls
(the same type_key and FSM state, its state time in the same 0.1 s bin, within reach of the hero, no attack box near it
for N frames either side):
  entity  dvx, dvy (velocity at +N minus the frame before), flip (vx changed sign), the FSM states it entered (FSM tap
          events), damage cooldown started (damage.can_cause_damage True -> False), hp lost;
  hero    dvy (max vy over the window minus vy before: a bounce), dvx_away (velocity change away from the entity: a
          recoil), hit (a damage event).
Tests: binary outcomes by Fisher's exact test, continuous ones by Mann-Whitney U (normal approximation, tie corrected),
Benjamini-Hochberg over all tests; an effect is flagged at q < 0.01 with |effect| at least 0.2 (proportion difference)
or 0.3 (Cliff's delta).
Also: a state-entry velocity table per (type_key, state) (median vx, |vx|, share moving right, vy at the frame of entry;
how bells launch and bounce), and the under-sampled (attack, type_key, state) combinations: the entity was within reach
in at least --min-exposure frames but met fewer than --min-n attacks of that kind. Those are the sandbox probe list
(every attack against every object at every phase, from savestates).

    ../scripts/uv.cmd run python -m ssbot.tools.effect_miner REC_DIR [REC_DIR ...] [--n 12] [--out effects.json]
        [--types Bell] [--cache DIR]

REC_DIR: a recording (with state.msgpack.zst) or a run directory (all recordings under rec/). Single-threaded; the
per-recording extract is cached (--cache) so a second pass with other settings does not decode again.
First findings (Bell Beast data-policy run 20261001_122249, 12 recordings, 263 fights): see the module's report in the
commit that added it.
"""
import argparse
import json
import math
import pickle
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.combat.planner import DOWN, SIDE, SPEAR, UP

# Hunter crest clips -> (attack kind, box, active clip time [s]). Active times: the box is out 1-4 frames after the
# press for a side slash (828 of 1037 presses hit, live run 20261002_081716), 2-7 for the up slash; the DownSpike clip
# is the spike itself (its antic and recovery are separate clips).
CLIPS = {"Slash": ("side", SIDE, 0.1), "SlashAlt": ("side", SIDE, 0.1), "UpSlash": ("up", UP, 0.13),
         "DownSpike": ("down", DOWN, 1.0), "NeedleThrow Throwing": ("spear", SPEAR, 0.1)}
KINDS = ("side", "up", "down", "spear")
REACH = 4.5          # an entity this close to the hurtbox centre counts as exposed to an attack
NEAR = 8.0           # extract radius


def _recordings(paths: list[Path]) -> list[Path]:
    out = []
    for p in paths:
        if (p / "state.msgpack.zst").exists():
            out.append(p)
        else:
            out += sorted(q.parent for q in p.glob("rec/**/state.msgpack.zst"))
    return out


def _shape(c: dict):
    v = c.get("verts_world") or []
    pts = np.array(v, float).reshape(-1, 2) if len(v) >= 6 else None
    if pts is None:
        return None
    if c.get("kind") == "circle" and c.get("r"):
        ctr = pts.mean(axis=0)
        return ("c", float(ctr[0]), float(ctr[1]), float(c["r"]))
    return ("p", pts)


def extract(rec: Path, types: tuple[str, ...] = ()) -> dict:
    """Per frame: hero (x, y, vx, vy, facing, clip, clip t, hurtbox) and the entities with an enabled collider
    within NEAR: (iid, type_key, state, state t, x, y, vx, vy, can_cause_damage, hp, shapes); FSM tap and damage events."""
    from ssbot.record.recorder import RecordingReader
    r = RecordingReader(rec)
    frames, fsm, dmg = [], [], []
    for s in r.states(0, 10 ** 9):
        f = s["f"]
        for ev in s.get("ev") or ():
            k = ev.get("k")
            d = ev.get("d") or {}
            if k == "fsm" and d.get("iid") is not None:
                fsm.append((f, d["iid"], d.get("to")))
            elif k == "damage":
                dmg.append((f, str(d.get("source"))))
        h = s.get("hero") or {}
        box = h.get("box")
        if not box or not h.get("pos"):
            continue
        cx, cy = 0.5 * (box[0] + box[2]), 0.5 * (box[1] + box[3])
        ents = []
        for e in s.get("ents") or ():
            tk = e.get("type_key") or ""
            if types and not any(t in tk for t in types):
                continue
            p = e.get("pos")
            if not p or abs(p[0] - cx) > NEAR or abs(p[1] - cy) > NEAR:
                continue
            shapes = [sh for c in e.get("colliders") or () if c.get("enabled") and (sh := _shape(c))]
            if not shapes:
                continue
            c0 = (e.get("colliders") or [{}])[0]
            fs = (e.get("fsms") or [{}])[0]
            ents.append((e["iid"], tk, fs.get("state"), fs.get("t") or 0.0, p[0], p[1],
                         *(e.get("vel") or (0.0, 0.0)), (c0.get("damage") or {}).get("can_cause_damage"),
                         e.get("hp"), shapes))
        a = h.get("anim") or {}
        frames.append((f, cx, cy, *(h.get("vel") or (0.0, 0.0)), h.get("facing") or 1, a.get("clip"),
                       a.get("t") or 0.0, ents))
    return {"frames": frames, "fsm": fsm, "dmg": dmg}


def _attack_rect(cx, cy, face, box):
    x0, x1, y0, y1 = box
    return (cx + x0, cy + y0, cx + x1, cy + y1) if face >= 0 else (cx - x1, cy + y0, cx - x0, cy + y1)


def _meets(rect, sh) -> bool:
    rx0, ry0, rx1, ry1 = rect
    if sh[0] == "c":
        _, x, y, r = sh
        dx = max(rx0 - x, 0.0, x - rx1)
        dy = max(ry0 - y, 0.0, y - ry1)
        return dx * dx + dy * dy <= r * r
    pts = sh[1]
    if pts[:, 0].max() < rx0 or pts[:, 0].min() > rx1 or pts[:, 1].max() < ry0 or pts[:, 1].min() > ry1:
        return False
    if ((pts[:, 0] >= rx0) & (pts[:, 0] <= rx1) & (pts[:, 1] >= ry0) & (pts[:, 1] <= ry1)).any():
        return True
    # separating axes of the polygon's edges (the rectangle's own axes passed the AABB test above)
    corners = np.array([[rx0, ry0], [rx1, ry0], [rx1, ry1], [rx0, ry1]])
    for i in range(len(pts)):
        ex, ey = pts[(i + 1) % len(pts)] - pts[i]
        ax = np.array([-ey, ex])
        a, b = pts @ ax, corners @ ax
        if a.max() < b.min() or b.max() < a.min():
            return False
    return True


def _outcomes(X: dict, i: int, iid, n: int) -> dict | None:
    """Outcomes for entity iid around frame index i (the contact frame, or a control frame)."""
    fr = X["frames"]
    if i < 1 or i + n >= len(fr) or fr[i + n][0] - fr[i - 1][0] > n + 4:
        return None

    def ent(j):
        for e in fr[j][8]:
            if e[0] == iid:
                return e
        return None
    e0, e1, e3 = ent(i - 1), ent(i + n), ent(min(i + 3 * n, len(fr) - 1))
    if e0 is None:
        return None
    f0, f1 = fr[i][0], fr[i][0] + n
    out = {}
    if e1 is not None:
        out["ent_dvx"] = e1[6] - e0[6]
        out["ent_dvy"] = e1[7] - e0[7]
        out["ent_flip"] = abs(e0[6]) > 0.5 and np.sign(e1[6]) != np.sign(e0[6])
    if e3 is not None and abs(e3[6]) > 0.5:
        out["ent_right_3n"] = e3[6] > 0
    # the side it moves to after its next state change (a bell's next ground bounce): vx 2 frames after the first
    # FSM entry at least 3 frames after the contact, within 3N
    nxt = [ff for (ff, ii, t) in X["fsm_by"].get(iid, ()) if f0 + 3 <= ff <= f0 + 3 * n]
    if nxt:
        j = i + (min(nxt) - f0) + 2
        en = ent(j) if j < len(fr) else None
        if en is not None and abs(en[6]) > 0.5:
            out["ent_next_side_right"] = en[6] > 0
            out["ent_next_side_away"] = (en[6] > 0) == (fr[i - 1][1] < e0[4])
    cds = [e[8] for j in range(i, i + n + 1) if (e := ent(j)) is not None]
    out["ent_cooldown"] = e0[8] is True and any(c is False for c in cds)
    hps = [e[9] for j in range(i, i + n + 1) if (e := ent(j)) is not None and e[9] is not None]
    out["ent_hp_lost"] = bool(e0[9] is not None and hps and min(hps) < e0[9])
    for st in {t for (ff, ii, t) in X["fsm_by"].get(iid, ()) if f0 <= ff <= f1}:
        out[f"ent_enters:{st}"] = True
    h0 = fr[i - 1]
    out["hero_dvy"] = max(fr[j][4] for j in range(i, i + n + 1)) - h0[4]
    side = 1.0 if h0[1] >= e0[4] else -1.0                       # away from the entity
    out["hero_dvx_away"] = side * (fr[min(i + 4, len(fr) - 1)][3] - h0[3])
    tk = e0[1]
    out["hero_hit"] = any(f0 <= ff <= f1 and tk.split("/")[-1] in src for ff, src in X["dmg"])
    return out


def contacts(X: dict, n: int) -> tuple[list, list, Counter]:
    """Contact events [(kind, tk, state, t bin, frame index, iid, facing, hero x - entity x)], control frames
    [(tk, state, t bin, frame index, iid)] and exposure counts per (kind, tk, state)."""
    fr = X["frames"]
    X["fsm_by"] = defaultdict(list)
    for ev in X["fsm"]:
        X["fsm_by"][ev[1]].append(ev)
    ev_out, seen = [], set()
    touched = defaultdict(set)              # iid -> frame indices with an attack box near it
    clip_id = 0
    prev_clip = None
    for i, (f, cx, cy, vx, vy, face, clip, ct, ents) in enumerate(fr):
        if clip != prev_clip or (i and fr[i - 1][0] != f - 1):
            clip_id += 1
        prev_clip = clip
        spec = CLIPS.get(clip)
        if spec is None or ct > spec[2]:
            continue
        kind, box, _ = spec
        rect = _attack_rect(cx, cy, face, box)
        grown = (rect[0] - 1.0, rect[1] - 1.0, rect[2] + 1.0, rect[3] + 1.0)
        for e in ents:
            if any(_meets(grown, sh) for sh in e[10]):
                touched[e[0]].add(i)
            if (clip_id, e[0]) in seen or not any(_meets(rect, sh) for sh in e[10]):
                continue
            seen.add((clip_id, e[0]))
            ev_out.append((kind, e[1], e[2], round(e[3] // 0.1 * 0.1, 1), i, e[0], face, cx - e[4]))
    ctrl, expo = [], Counter()
    for i, (f, cx, cy, vx, vy, face, clip, ct, ents) in enumerate(fr):
        for e in ents:
            if abs(e[4] - cx) > REACH or abs(e[5] - cy) > REACH:
                continue
            for k in KINDS:
                expo[(k, e[1], e[2])] += 1
            near = touched.get(e[0])
            if near and any(j in near for j in range(i - n, i + n + 1)):
                continue
            ctrl.append((e[1], e[2], round(e[3] // 0.1 * 0.1, 1), i, e[0]))
    return ev_out, ctrl, expo


def state_entry(X: dict) -> dict:
    """(type_key, state) -> velocities at the first frame seen in that state, per state instance."""
    last = {}
    out = defaultdict(list)
    for f, cx, cy, vx, vy, face, clip, ct, ents in X["frames"]:
        for e in ents:
            key = (e[0], e[2])
            if last.get(e[0]) != e[2]:
                out[(e[1], e[2])].append((e[6], e[7]))
            last[e[0]] = e[2]
    return out


# ---- statistics ---------------------------------------------------------------------------------------------------

def fisher_p(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]] (hypergeometric, probabilities <= the observed one)."""
    n1, n2, k, N = a + b, c + d, a + c, a + b + c + d

    def lp(x):
        return (math.lgamma(n1 + 1) - math.lgamma(x + 1) - math.lgamma(n1 - x + 1) + math.lgamma(n2 + 1)
                - math.lgamma(k - x + 1) - math.lgamma(n2 - k + x + 1) - math.lgamma(N + 1) + math.lgamma(k + 1)
                + math.lgamma(N - k + 1))
    lo, hi = max(0, k - n2), min(k, n1)
    p0 = lp(a)
    return min(1.0, sum(math.exp(lp(x)) for x in range(lo, hi + 1) if lp(x) <= p0 + 1e-7))


def mann_whitney(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """(two-sided p by the normal approximation with tie correction, Cliff's delta x vs y)."""
    n1, n2 = len(x), len(y)
    allv = np.concatenate([x, y])
    order = allv.argsort(kind="mergesort")
    ranks = np.empty(len(allv))
    sv = allv[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1
        i = j + 1
    U = ranks[:n1].sum() - n1 * (n1 + 1) / 2
    delta = 2 * U / (n1 * n2) - 1
    _, cnt = np.unique(sv, return_counts=True)
    N = n1 + n2
    var = n1 * n2 / 12 * ((N + 1) - (cnt ** 3 - cnt).sum() / (N * (N - 1)))
    if var <= 0:
        return 1.0, float(delta)
    z = (U - n1 * n2 / 2) / math.sqrt(var)
    return float(math.erfc(abs(z) / math.sqrt(2))), float(delta)


def bh(ps: list[float]) -> list[float]:
    m = len(ps)
    order = np.argsort(ps)
    q = np.empty(m)
    run = 1.0
    for rank in range(m - 1, -1, -1):
        i = order[rank]
        run = min(run, ps[i] * m / (rank + 1))
        q[i] = run
    return q.tolist()


def analyse(Xs: list[dict], n: int, min_n: int, min_exposure: int, max_ctrl: int = 3000, seed: int = 0) -> dict:
    rng = random.Random(seed)
    ev_all, ctrl_all, expo = [], [], Counter()
    entry = defaultdict(list)
    for xi, X in enumerate(Xs):
        e, c, x = contacts(X, n)
        ev_all += [(xi, *v) for v in e]
        ctrl_all += [(xi, *v) for v in c]
        expo.update(x)
        for k, v in state_entry(X).items():
            entry[k] += v
    by_key = defaultdict(list)
    for v in ev_all:
        by_key[(v[1], v[2], v[3])].append(v)
    ctrl_by = defaultdict(list)
    for v in ctrl_all:
        ctrl_by[(v[1], v[2], v[3])].append(v)
    tests, groups = [], {}
    for key, evs in sorted(by_key.items()):
        kind, tk, st = key
        out_c = [o for v in evs if (o := _outcomes(Xs[v[0]], v[5], v[6], n)) is not None]
        bins = Counter(v[4] for v in evs)
        pool = [v for b in bins for v in ctrl_by.get((tk, st, b), ())]
        rng.shuffle(pool)
        out_k = [o for v in pool[:max_ctrl] if (o := _outcomes(Xs[v[0]], v[4], v[5], n)) is not None]
        groups[key] = {"contacts": len(out_c), "controls": len(out_k),
                       "facing_dx": [round(float(v[8]), 2) for v in evs][:20]}
        if not out_c or not out_k:
            continue
        names = sorted({k for o in out_c + out_k for k in o})
        for nm in names:
            a = [o[nm] for o in out_c if nm in o]
            b = [o.get(nm, False) if nm.startswith("ent_enters:") else o[nm] for o in out_k if
                 nm in o or nm.startswith("ent_enters:")]
            if len(a) < 2 or len(b) < 2:
                continue
            if isinstance(a[0], (bool, np.bool_)):
                x1, x2 = sum(map(bool, a)), sum(map(bool, b))
                p = fisher_p(x1, len(a) - x1, x2, len(b) - x2)
                eff = x1 / len(a) - x2 / len(b)
                tests.append({"key": key, "outcome": nm, "kind": "rate", "contact": round(x1 / len(a), 3),
                              "control": round(x2 / len(b), 3), "n": [len(a), len(b)], "effect": round(eff, 3),
                              "p": p})
            else:
                xa, xb = np.array(a, float), np.array(b, float)
                p, d = mann_whitney(xa, xb)
                tests.append({"key": key, "outcome": nm, "kind": "shift", "contact": round(float(np.median(xa)), 2),
                              "control": round(float(np.median(xb)), 2), "n": [len(a), len(b)],
                              "effect": round(d, 3), "p": p})
    if tests:
        for t, q in zip(tests, bh([t["p"] for t in tests])):
            t["q"] = q
            t["flag"] = q < 0.01 and abs(t["effect"]) >= (0.2 if t["kind"] == "rate" else 0.3)
    under = []
    for (kind, tk, st), ex in sorted(expo.items()):
        nc = groups.get((kind, tk, st), {}).get("contacts", 0)
        if ex >= min_exposure and nc < min_n:
            under.append({"attack": kind, "type_key": tk, "state": st, "exposure_frames": ex, "contacts": nc})
    ent_tab = {}
    for (tk, st), v in sorted(entry.items()):
        a = np.array(v, float)
        ent_tab[f"{tk} | {st}"] = {"n": len(a), "vx_med": round(float(np.median(a[:, 0])), 2),
                                   "abs_vx_med": round(float(np.median(np.abs(a[:, 0]))), 2),
                                   "abs_vx_iqr": [round(float(q), 2) for q in np.percentile(np.abs(a[:, 0]), [25, 75])],
                                   "right_share": round(float((a[:, 0] > 0.5).mean()), 3),
                                   "left_share": round(float((a[:, 0] < -0.5).mean()), 3),
                                   "vy_med": round(float(np.median(a[:, 1])), 2)}
    return {"n": n, "groups": {" | ".join(k): v for k, v in groups.items()},
            "effects": [dict(t, key=" | ".join(t["key"])) for t in sorted(tests, key=lambda t: t["p"])],
            "under_sampled": under, "state_entry": ent_tab}


def report(res: dict) -> str:
    lines = [f"contact groups (attack | type | state): {len(res['groups'])}"]
    for k, g in res["groups"].items():
        lines.append(f"  {k}: {g['contacts']} contacts, {g['controls']} controls")
    lines.append("flagged effects (q < 0.01, |effect| >= 0.2 rate / 0.3 Cliff's delta):")
    for t in res["effects"]:
        if t.get("flag"):
            lines.append(f"  {t['key']} :: {t['outcome']} contact {t['contact']} vs control {t['control']} "
                         f"(n {t['n'][0]}/{t['n'][1]}, effect {t['effect']}, q {t['q']:.2g})")
    lines.append(f"under-sampled (attack, type, state): {len(res['under_sampled'])}")
    for u in res["under_sampled"][:60]:
        lines.append(f"  {u['attack']:5s} {u['type_key']} | {u['state']}: {u['contacts']} contacts in "
                     f"{u['exposure_frames']} exposed frames")
    lines.append("state entry velocities:")
    for k, v in res["state_entry"].items():
        lines.append(f"  {k}: n {v['n']} vx {v['vx_med']} |vx| {v['abs_vx_med']} {v['abs_vx_iqr']} "
                     f"R {v['right_share']} L {v['left_share']} vy {v['vy_med']}")
    return "\n".join(lines)


def _idle() -> None:
    import os
    import sys
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        k.SetPriorityClass(k.GetCurrentProcess(), 0x40)
    else:
        os.nice(19)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--min-n", type=int, default=5)
    ap.add_argument("--min-exposure", type=int, default=300)
    ap.add_argument("--types", nargs="*", default=[])
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--idle", action="store_true", help="run at idle priority (beside live game instances)")
    a = ap.parse_args()
    if a.idle:
        _idle()
    Xs = []
    for rec in _recordings(a.paths):
        cp = a.cache / f"{rec.parent.name}_{rec.name}.pkl" if a.cache else None
        if cp is not None and cp.exists():
            Xs.append(pickle.loads(cp.read_bytes()))
            continue
        X = extract(rec, tuple(a.types))
        if cp is not None:
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_bytes(pickle.dumps(X))
        Xs.append(X)
        print(rec.name, len(X["frames"]), "frames", flush=True)
    res = analyse(Xs, a.n, a.min_n, a.min_exposure)
    print(report(res))
    if a.out:
        a.out.write_text(json.dumps(res, indent=1, default=str), "utf-8")


if __name__ == "__main__":
    main()
