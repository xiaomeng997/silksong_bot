"""The Clapper's jump moves in the 1v1 recordings (task 1v1 SP3, the person's request of 2026-10-16: after it jumps,
go behind it instead of fleeing; forum.md 67).

Per jump (CC_JUMP: Jump Antic > Jump > Air > Slam 2 > Slam Recover; CC_JUMP_CAST: Cast Slam Antic > Cast Slam Antic 2
> Jump > Air > Slam 2 > Slam Recover, the rune circle after the landing), from the live 1v1 runs (run manifests of
1v1_live.ps1) or the person's demo (C:/ssbot/data/m2_map/human_1015/fights.pkl):
- the take-off: the Clapper's x and facing at the antic entry and at the aim (the first STATE in Jump / Air), its
  velocity on the first Air frame, the hero's transform x at the aim (the FSM's Jump Aim reads it: target = hero x - 5
  x facing, vx = clamp(target - x, +-12)); the landing (the first Slam 2 STATE) against that formula (wall effects);
- the arc: the Clapper's y and x along the flight (game frames from the aim), its body box bottom;
- the hurt shapes relative to the landing (x along the jump's facing, + = in front; y above the floor): the body box
  in Air / Slam 2 / Slam Recover / Idle, Slam Collider 2's polygon, the rune circle's centre and the frames it is lit;
- the walls: the room behind the landing (its centre to the wall on its back side);
- the hero: the path relative to the landing (+ = in front), where she was at the landing and at the move's end, the
  crossing under it (the frame she passes its centre and the clearance between her box top and its body bottom while
  under it), her landed hits on it (from behind / in front), the HP-loss hits (source, the Clapper's state) from the
  antic to 90 frames after the move (and the rune circle's burst);
- what comes next: the Clapper's next attack family after the move, how long after the move's end, and where the
  hero was then (centre to centre, + = in front of its new facing).

Distances are centre to centre (the hero's box centre, the Clapper's transform), u.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sp3_jumps collect --manifest C:/ssbot/sandbox/1v1sp2_manifest.txt \
        [--manifest ...] [--arms rn,rnplay] --out C:/ssbot/data/m2_play/sp3/jumps_sp2.json
    ../scripts/uv.cmd run python -m ssbot.tools.sp3_jumps report --in C:/ssbot/data/m2_play/sp3/jumps_sp2.json
    ../scripts/uv.cmd run python -m ssbot.tools.sp3_jumps trials --in <collected.json> [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.combat import slam_play as sp

CLAPPER = sp.CLAPPER
WALL_L, WALL_R = sp.WALL_L, sp.WALL_R
FLOOR = 3.01                       # the floor's y (the Clapper's body box bottom standing, the hero's box bottom)
GROUND_Y = 7.449                   # the Clapper's transform y on the ground
JUMP_ANTICS = {"Jump Antic": "CC_JUMP", "Cast Slam Antic": "CC_JUMP_CAST"}
MOVE_STATES = ("Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2", "Cast Jump", "Jump Aim", "Jump", "Air",
               "Charged?", "Slam Effects?", "Slam 2", "Slam Recover")
AIR = ("Jump", "Air")
ATTACK_STARTS = {"Slam Antic": "CC_SLAM", "Spell Antic": "CC_CAST", "Jump Antic": "CC_JUMP",
                 "Cast Slam Antic": "CC_JUMP_CAST", "Evade Scuttle": "CC_EVADE"}
AFTER_F = 90                       # frames after the move's end kept for the hero's path / hits
RUNE_R = 7.187


def pct(v, qs=(10, 50, 90)):
    v = [x for x in v if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return [round(float(np.percentile(v, q)), 2) for q in qs] if v else None


def _bbox(vs):
    if not vs:
        return None
    xs, ys = vs[0::2], vs[1::2]
    return (min(xs), max(xs), min(ys), max(ys))


def _hero_tx(s: dict) -> float:
    """The hero's transform x (the FSM's Jump Aim reads the transform)."""
    h = s.get("hero") or {}
    p = h.get("pos")
    return float(p[0]) if p else sp.hero_x(s)


def _cols(e: dict) -> dict:
    out = {}
    for c in e.get("colliders") or ():
        if c.get("enabled") and c.get("damage"):
            out[str(c.get("name"))] = (c.get("kind"), c.get("verts_world"))
    return out


def _rune(s: dict, near_x: float) -> tuple | None:
    """(x, y, lit) of the rune slam damager nearest near_x (a circle hazard of the rune slam's size)."""
    best = None
    for o in s.get("ents") or ():
        if o.get("type_key") != "damager" or not o.get("pos"):
            continue
        for c in o.get("colliders") or ():
            bb = _bbox(c.get("verts_world"))
            if bb is None or abs((bb[1] - bb[0]) - 2 * RUNE_R) > 0.6:
                continue
            x = float(o["pos"][0])
            d = abs(x - near_x)
            if best is None or d < best[0]:
                best = (d, x, float(o["pos"][1]), bool(c.get("enabled")))
    return None if best is None else best[1:]


def _hp_events(states: list[dict]) -> list[tuple[int, int, str]]:
    out, dmg = [], []
    for s in states:
        for ev in s.get("ev") or ():
            k, d = ev.get("k"), ev.get("d") or {}
            if k == "hp" and (d.get("delta") or 0) < 0:
                out.append((int(s["f"]), -int(d.get("delta")), str(d.get("source"))))
            elif k == "damage":
                dmg.append((int(s["f"]), str(d.get("source"))))
    if not out:
        for a, b in zip(states, states[1:]):
            ha, hb = (a.get("hero") or {}).get("health"), (b.get("hero") or {}).get("health")
            if ha is not None and hb is not None and hb < ha:
                src = next((s_ for f_, s_ in dmg if abs(f_ - int(b["f"])) <= 3), "?")
                out.append((int(b["f"]), ha - hb, src))
    return out


def jumps_of(states: list[dict], label: dict, hero_attacks) -> list[dict]:
    """Every jump move in one episode's STATEs (the module docstring)."""
    by_i = {int(s["f"]): i for i, s in enumerate(states)}
    hp_ev = _hp_events(states)
    out = []
    prev = None
    n = len(states)
    for i, s in enumerate(states):
        e = sp.clapper(s)
        st = sp.control(e)[0]
        if st in JUMP_ANTICS and prev not in MOVE_STATES:
            j = _one(states, i, e, st, hp_ev, hero_attacks)
            if j is not None:
                j.update(label)
                out.append(j)
        prev = st
    return out


def _one(states, i, e, st, hp_ev, hero_attacks) -> dict | None:
    n = len(states)
    fam = JUMP_ANTICS[st]
    face = 1 if e.get("flipX") else -1
    iid = e.get("iid")
    x0 = float(e["pos"][0])
    s0 = states[i]
    ij = il = ir = ie = None
    for j in range(i, min(n, i + 400)):
        c = sp.clapper(states[j])
        if c is None or c.get("iid") != iid:
            ie = j
            break
        sj = sp.control(c)[0]
        if sj in AIR and ij is None:
            ij = j
        if sj == "Slam 2" and il is None:
            il = j
        if sj == "Slam Recover" and ir is None:
            ir = j
        if sj not in MOVE_STATES:
            ie = j
            break
    if ij is None or il is None or ie is None:
        return None
    f = lambda j: int(states[j]["f"])
    cj = sp.clapper(states[ij])
    cl = sp.clapper(states[il])
    xj, xl = float(cj["pos"][0]), float(cl["pos"][0])
    # the aim: the hero's transform x on the frame before the first Jump / Air STATE (Jump Aim runs in that step)
    hx_aim = _hero_tx(states[ij - 1]) if ij > i else _hero_tx(states[ij])
    hx_aim2 = _hero_tx(states[ij])
    tgt = hx_aim - 5.0 * face
    pred = xj + 0.916 * max(-12.0, min(12.0, tgt - xj))
    # the first Air frame's velocity
    va = next(((float(sp.clapper(states[j])["vel"][0]), float(sp.clapper(states[j])["vel"][1]))
               for j in range(ij, il) if sp.control(sp.clapper(states[j]))[0] == "Air"), (None, None))
    rel = lambda x: (x - xl) * face                       # + = in front of the landing (the jump's facing)
    # the arc (STATE frames from the aim; dt-weighted game frames too)
    arc, tg = [], 0.0
    for j in range(ij, il + 1):
        c = sp.clapper(states[j])
        cols = _cols(c)
        body = _bbox(cols.get(CLAPPER, (None, None))[1])
        arc.append((j - ij, round(tg * 60, 1), round((float(c["pos"][0]) - xj) * face, 3), round(float(c["pos"][1]), 3),
                    None if body is None else round(body[2], 3)))
        tg += float(states[j].get("dt") or 0.0)
    # shapes relative to the landing
    shapes = {}
    for j in range(il, min(ie + 25, n)):
        c = sp.clapper(states[j])
        if c is None:
            break
        sj = sp.control(c)[0]
        for name, (kind, vs) in _cols(c).items():
            if not vs:
                continue
            key = f"{sj}|{name}"
            if key in shapes:
                continue
            xs = [round(rel(v), 3) for v in vs[0::2]]
            ys = [round(v - FLOOR, 3) for v in vs[1::2]]
            shapes[key] = {"k": j - il, "kind": kind, "x": xs, "y": ys}
    # the rune circle (CC_JUMP_CAST): centre and lit frames from the landing
    rune = None
    if fam == "CC_JUMP_CAST":
        lit, cen = [], None
        for j in range(il, min(n, il + 160)):
            r = _rune(states[j], xl + face * 6.48)
            if r is None:
                continue
            cen = cen or (round(rel(r[0]), 3), round(r[1] - FLOOR, 3))
            if r[2]:
                lit.append(j - il)
        rune = {"centre": cen, "lit": [min(lit), max(lit)] if lit else None, "lit_frames": lit}
    # the hero's path
    path = []
    under = []
    j_end = min(n, ie + AFTER_F)
    cross = None
    for j in range(i, j_end):
        sj_ = states[j]
        h = sj_.get("hero") or {}
        b = h.get("box")
        c = sp.clapper(sj_)
        if not b:
            continue
        hx = 0.5 * (b[0] + b[2])
        cst = sp.control(c)[0] if c else None
        path.append((j - il, round(rel(hx), 3), round(float(b[1]) - FLOOR, 3), int(sp.on_ground(sj_)),
                     (h.get("anim") or {}).get("clip"), cst))
        if c is not None and ij <= j <= il:
            body = _bbox(_cols(c).get(CLAPPER, (None, None))[1])
            if body is not None and b[0] < body[1] and b[2] > body[0]:
                under.append((j - il, round(body[2] - float(b[3]), 3)))
            if cross is None and j > ij:
                cx_now = float(c["pos"][0])
                prev_s = states[j - 1]
                pb = (prev_s.get("hero") or {}).get("box")
                if pb:
                    a0 = (0.5 * (pb[0] + pb[2]) - float(sp.clapper(prev_s)["pos"][0])) * face
                    a1 = (hx - cx_now) * face
                    if a0 > 0 >= a1:
                        cross = j - il
    hb_l = (states[il].get("hero") or {}).get("box")
    hb_e = (states[ie].get("hero") or {}).get("box") if ie < n else None
    # landed hits and HP loss
    hits, hurt = [], []
    fa, fe = f(i), f(min(ie, n - 1))
    for j in range(i, j_end):
        sj_ = states[j]
        for ev in sj_.get("ev") or ():
            k_, d = ev.get("k"), ev.get("d") or {}
            if k_ == "hit" and d.get("type_key") == CLAPPER and d.get("src") in hero_attacks:
                dealt = d.get("dealt", d.get("amount"))
                if dealt is None or float(dealt) > 0:
                    b = (sj_.get("hero") or {}).get("box")
                    c = sp.clapper(sj_)
                    side = None
                    if b and c is not None:
                        cf = 1 if c.get("flipX") else -1
                        side = round((0.5 * (b[0] + b[2]) - float(c["pos"][0])) * cf, 2)
                    hits.append({"k": j - il, "src": str(d.get("src")), "x_now": side,
                                 "st": sp.control(c)[0] if c else None})
    rune_end = il + (rune["lit"][1] if rune and rune.get("lit") else 0)
    f_hurt_end = f(min(max(j_end, rune_end + 10) - 1, n - 1))
    for (fh, amt, src) in hp_ev:
        if fa <= fh <= f_hurt_end:
            jh = next((j for j in range(i, n) if f(j) >= fh), None)
            c = sp.clapper(states[jh]) if jh is not None else None
            b = (states[jh].get("hero") or {}).get("box") if jh is not None else None
            hurt.append({"k": (jh - il) if jh is not None else None, "amount": amt, "src": src[-40:],
                         "st": sp.control(c)[0] if c else None,
                         "x_land": None if not b else round(rel(0.5 * (b[0] + b[2])), 2)})
    # next attack
    nxt = None
    for j in range(ie, min(n, ie + 400)):
        c = sp.clapper(states[j])
        if c is None or c.get("iid") != iid:
            break
        sj = sp.control(c)[0]
        if sj in ATTACK_STARTS:
            b = (states[j].get("hero") or {}).get("box")
            cf = 1 if c.get("flipX") else -1
            nxt = {"fam": ATTACK_STARTS[sj], "df": j - ie,
                   "x": None if not b else round((0.5 * (b[0] + b[2]) - float(c["pos"][0])) * cf, 2),
                   "cx_shift": round((float(c["pos"][0]) - xl) * face, 2)}
            break
    hx0 = sp.hero_x(s0)
    return {
        "fam": fam, "f": f(i), "face": face, "x0": round(x0, 3), "rel0": round((hx0 - x0) * face, 3),
        "ground0": int(sp.on_ground(s0)), "k_aim": ij - i, "k_land": il - i, "k_rec": None if ir is None else ir - i,
        "k_end": ie - i, "xj": round(xj, 3), "xl": round(xl, 3), "dland": round((xl - x0) * face, 3),
        "vx": None if va[0] is None else round(va[0] * face, 3), "vy": va[1],
        "hx_aim": round(hx_aim, 3), "hx_aim2": round(hx_aim2, 3), "rel_aim": round((hx_aim - xj) * face, 3),
        "pred": round(pred, 3), "land_err": round((xl - pred) * face, 3),
        "room_back": round((xl - WALL_L) if face > 0 else (WALL_R - xl), 3),
        "room_front": round((WALL_R - xl) if face > 0 else (xl - WALL_L), 3),
        "x0_room_back": round((x0 - WALL_L) if face > 0 else (WALL_R - x0), 3),
        "hero_land": None if not hb_l else round(rel(0.5 * (hb_l[0] + hb_l[2])), 3),
        "hero_end": None if not hb_e else round(rel(0.5 * (hb_e[0] + hb_e[2])), 3),
        "cross": cross, "under": under, "arc": arc, "shapes": shapes, "rune": rune, "path": path,
        "hits": hits, "hurt": hurt, "next": nxt,
    }


def _rows(run: Path, inst: int) -> list[dict]:
    p = run / f"attempts_i{inst}.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()]


def collect(manifests: list[str], arms: set | None, out: Path) -> None:
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.forum_demo import HERO_ATTACKS
    from ssbot.tools.slam_play_live import manifest
    res = []
    eps = []
    for arm, inst, run in manifest(manifests, arms):
        for row in _rows(run, inst):
            if not row.get("recording") or row.get("f_wake") is None:
                continue
            f0, f1 = int(row["f_wake"]), int(row.get("f_kill") or row["f_end"])
            try:
                states = list(RecordingReader(row["recording"]).states(f0, f1))
            except Exception as ex:                      # noqa: BLE001 - a broken recording is skipped and named
                print("skip", run.name, inst, row.get("episode"), ex)
                continue
            lab = {"arm": arm, "run": run.name, "inst": inst, "ep": int(row.get("episode", -1)),
                   "code": row.get("code_rev")}
            J = jumps_of(states, lab, HERO_ATTACKS)
            eps.append({**lab, "jumps": len(J), "f_wake": f0, "f_end": f1, "kill": row.get("f_kill") is not None,
                        "fight_s": round((f1 - f0) / 60.0, 2)})
            res.extend(J)
            print(arm, run.name, inst, row.get("episode"), len(J), flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"episodes": eps, "jumps": res}, default=str), "utf-8")
    print("jumps", len(res), "episodes", len(eps))


# ---- the report ----

def _behind_safe(J: list[dict]) -> dict:
    """Per offset u behind the landing (centre to centre) and frame after the landing: does a standing hero box (0.5 x
    2.08 at the floor) touch any recorded hurt shape of the landing (the shapes' first frames per state)? A summary of
    the reach behind of every shape kind."""
    reach = defaultdict(list)
    for j in J:
        for key, sh in (j.get("shapes") or {}).items():
            st, name = key.split("|", 1)
            reach[f"{st}|{name}"].append(min(sh["x"]))
        r = j.get("rune")
        if r and r.get("centre"):
            reach["rune circle|back edge"].append(r["centre"][0] - RUNE_R)
    return {k: {"n": len(v), "min_x": pct(v, (0, 50, 100))} for k, v in sorted(reach.items())}


def report(path: Path) -> dict:
    d = json.loads(Path(path).read_text("utf-8"))
    J = d["jumps"]
    out = {"n": len(J), "by_fam": dict(Counter(j["fam"] for j in J)), "by_arm": dict(Counter(j["arm"] for j in J))}
    for fam in ("CC_JUMP", "CC_JUMP_CAST"):
        F = [j for j in J if j["fam"] == fam]
        if not F:
            continue
        o = {"n": len(F)}
        o["k_aim"] = pct([j["k_aim"] for j in F])
        o["k_land"] = pct([j["k_land"] for j in F])
        o["k_end"] = pct([j["k_end"] for j in F])
        o["rel0"] = pct([j["rel0"] for j in F])
        o["rel_aim"] = pct([j["rel_aim"] for j in F])
        o["dland"] = pct([j["dland"] for j in F])
        o["land_err_abs"] = pct([abs(j["land_err"]) for j in F], (50, 90, 99))
        o["hero_land"] = pct([j["hero_land"] for j in F])
        o["behind_at_land"] = sum(1 for j in F if (j["hero_land"] or 0) < 0)
        o["crossed_under"] = sum(1 for j in F if j["cross"] is not None)
        o["hurt"] = sum(1 for j in F if j["hurt"])
        o["hurt_src"] = dict(Counter(h["src"][-25:] + "@" + str(h["st"]) for j in F for h in j["hurt"]))
        o["hits"] = sum(len(j["hits"]) for j in F)
        o["hits_behind"] = sum(1 for j in F for h in j["hits"] if (h["x_now"] or 0) < 0)
        o["next"] = dict(Counter((j["next"] or {}).get("fam") for j in F))
        o["reach_behind"] = _behind_safe(F)
        out[fam] = o
    return out


SAFE_AFTER_F = 60                  # a trial is safe without HP loss from the antic to the move's end + this (and the
#                                    rune circle's burst for a jump cast)


def trials(path: Path) -> dict:
    """Per arm, every jump as a trial (SP3's targeted live trials and the A/B): safe (no HP lost from the antic entry
    to the move's end + SAFE_AFTER_F frames, or to the rune circle's last lit frame + 10 for a jump cast), behind (the
    hero behind the landing at the landing frame), the hero's x then, the crossing under it, landed hits from the
    landing to the move's end + SAFE_AFTER_F (from behind / in front of its facing then), the HP-loss sources."""
    d = json.loads(Path(path).read_text("utf-8"))
    by = defaultdict(list)
    for j in d["jumps"]:
        by[j["arm"]].append(j)
    out = {}
    for arm, J in sorted(by.items()):
        rows = []
        for j in J:
            k_land, k_end = j["k_land"], j["k_end"]
            lim = k_end - k_land + SAFE_AFTER_F
            if j.get("rune") and j["rune"].get("lit"):
                lim = max(lim, j["rune"]["lit"][1] + 10)
            hurt = [h for h in j["hurt"] if h["k"] is not None and h["k"] <= lim]
            hits = [h for h in j["hits"] if h["k"] is not None and 0 <= h["k"] <= k_end - k_land + SAFE_AFTER_F]
            rows.append({"fam": j["fam"], "safe": not hurt, "behind": (j["hero_land"] or 0) < 0,
                         "hero_land": j["hero_land"], "rel_aim": j["rel_aim"], "room_back": j["room_back"],
                         "cross": j["cross"], "hits": len(hits), "hits_behind": sum(1 for h in hits
                                                                                   if (h["x_now"] or 0) < 0),
                         "hurt": [(h["k"], h["src"][-28:], h["st"], h["x_land"]) for h in hurt],
                         "next": (j["next"] or {}).get("fam"), "ep": f"{j['run'][:15]}_i{j['inst']}_e{j['ep']}"})
        o = {"jumps": len(rows), "by_fam": dict(Counter(r["fam"] for r in rows)),
             "safe": sum(r["safe"] for r in rows), "behind": sum(r["behind"] for r in rows),
             "safe_behind": sum(r["safe"] and r["behind"] for r in rows),
             "hero_land_p10_50_90": pct([r["hero_land"] for r in rows]),
             "hero_land_behind_p10_50_90": pct([r["hero_land"] for r in rows if r["behind"]]),
             "rel_aim_p10_50_90": pct([r["rel_aim"] for r in rows]),
             "crossed": sum(1 for r in rows if r["cross"] is not None),
             "hits": sum(r["hits"] for r in rows), "hits_behind": sum(r["hits_behind"] for r in rows),
             "hurt_src": dict(Counter(f"{h[1]}@{h[2]}" for r in rows for h in r["hurt"])),
             "unsafe": [r for r in rows if not r["safe"]],
             "next_after_behind": dict(Counter(r["next"] for r in rows if r["behind"]))}
        for fam in ("CC_JUMP", "CC_JUMP_CAST"):
            F = [r for r in rows if r["fam"] == fam]
            o[fam] = {"n": len(F), "safe": sum(r["safe"] for r in F), "behind": sum(r["behind"] for r in F),
                      "hits": sum(r["hits"] for r in F)}
        out[arm] = o
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trials")
    t.add_argument("--in", dest="inp", required=True)
    t.add_argument("--json", default="")
    c = sub.add_parser("collect")
    c.add_argument("--manifest", action="append", required=True)
    c.add_argument("--arms", default="")
    c.add_argument("--out", required=True)
    r = sub.add_parser("report")
    r.add_argument("--in", dest="inp", required=True)
    r.add_argument("--json", default="")
    a = ap.parse_args(argv)
    if a.cmd == "collect":
        collect(a.manifest, set(x for x in a.arms.split(",") if x) or None, Path(a.out))
    elif a.cmd == "trials":
        rep = trials(Path(a.inp))
        txt = json.dumps(rep, indent=1, default=str)
        for arm, o in rep.items():
            print(arm, {k: v for k, v in o.items() if k != "unsafe"})
            for u in o["unsafe"]:
                print("   unsafe", u)
        if a.json:
            Path(a.json).write_text(txt, "utf-8")
    else:
        rep = report(Path(a.inp))
        txt = json.dumps(rep, indent=1, default=str)
        print(txt)
        if a.json:
            Path(a.json).write_text(txt, "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
