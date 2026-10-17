"""Two Clappers: every jump move at a wall (the escape jump: an evade with a wall within ~6 u behind it becomes an
Escape Jump, jump / jump cast alternating, no buddy check) in live w13 episodes, per arm (task 1v1 SP9b; the spec
C:/ssbot/data/m2_play/switch/answer.txt sections 2f / 4 / 5 S4, buddy/answer.txt section 4 and R4, human_two R8).

Per jump antic of either Clapper while both live (Jump Antic or Cast Slam Antic entered from another state):
  esc        the escape jump: from an Evade Scuttle shown <= 3 frames (Evade Scuttle -> Escape Jump on its entry), or
             from Idle / Walk / After Scuttle / Dmg Attack with its back (its centre to the wall behind it, against its
             facing) <= ESC_BACK_U and her inside its Slam Range (<= 8.3 u, |dy| <= 3.9) - Close Range cannot pick a jump
  back0      its back at the antic start (u); rel0 her x in front of it (centre to centre: her box centre, its
             transform; + = in front), d0 |dx|, ground0, her feet above the floor
  F          it was L2's target (decisions tgt) at the antic start; nearest: it was the Clapper nearer to her
  frames     f_a (antic start), f_take (Jump / Jump Aim / Cast Jump), f_land (first state past the jump), f_idle (its
             first Idle after the landing), f_next / next (its next move's start and state)
  hits       landed hits on it (src = the hero's attacks): antic, flight, land1 (landing .. + 60), land3 (+ 60 .. + 180);
             on the other one in the same spans
  hp         HP-loss events from f_a to the landing + 60 (the SP9b gate: through the landing + 1 s) and to + 180, with
             their source names
  her        rel_land (her x behind (-) / in front (+) of its landing x along the jump's facing), wall_land (her centre
             to the wall behind it at the landing), min_wall (her nearest to that wall from the landing to + 60)
  rune       the jump cast's circle (the damager collider of radius ~7.19 nearest its landing): her nearest box edge to
             its centre while lit, lit_hit (her box inside it while lit)
  other      B's state and |dx| from her at the antic start, B's move starts during F's jump (locked: none expected),
             B's first move after F's landing (state, frames after the landing)
  policy     the SP9b script records (two_play.esc_runs) when the episode has them

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sp9b_esc --manifest C:/ssbot/sandbox/1v1sp9ab_manifest.txt \\
        --arms sp9a [--json out.json] [--all]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.combat import slam_play as sp
from ssbot.tools import sp7_two
from ssbot.tools.slam_play_live import manifest, pct

ESC_BACK_U = 6.2
JUMP_ANTICS = ("Jump Antic", "Cast Slam Antic")
JUMP_ST = sp.TWO_JUMP_ST
MOVE_STARTS = ("Slam Antic", "Spell Antic", "Jump Antic", "Cast Slam Antic", "Evade Scuttle")
FLOOR = 3.015
RUNE_R = 7.187


def _back(e: dict) -> float:
    cx = float(e["pos"][0])
    return (cx - sp.WALL_L) if e.get("flipX") else (sp.WALL_R - cx)


def _hits(s: dict, HA) -> list[tuple[object, str]]:
    out = []
    for ev in s.get("ev") or ():
        d = ev.get("d") or {}
        if ev.get("k") == "hit" and d.get("type_key") == sp.CLAPPER and d.get("src") in HA:
            dealt = d.get("dealt", d.get("amount"))
            if dealt is None or float(dealt) > 0:
                out.append((d.get("ent") or d.get("iid") or d.get("target_iid"), str(d.get("src"))))
    return out


def _rune_circles(s: dict) -> list[tuple[float, float, bool]]:
    """(centre x, centre y, lit) of the big rune circles in a STATE."""
    out = []
    for o in s.get("ents") or ():
        if o.get("type_key") != "damager" or not o.get("pos"):
            continue
        for col in o.get("colliders") or ():
            vs = col.get("verts_world") or ()
            xs, ys = vs[0::2], vs[1::2]
            if xs and abs((max(xs) - min(xs)) - 2 * RUNE_R) <= 0.6:
                out.append((0.5 * (max(xs) + min(xs)), 0.5 * (max(ys) + min(ys)), bool(col.get("enabled"))))
                break
    return out


def scan(row: dict, dec_ep: dict | None = None) -> list[dict]:
    """The jump moves of one episode (module docstring)."""
    from ssbot.record.recorder import RecordingReader
    HA = sp7_two._hero_attacks()
    f_wake, f_end = int(row["f_wake"]), int(row["f_end"])
    fk = row.get("f_kill") or f_end
    states = list(RecordingReader(row["recording"]).states(f_wake, f_end + 200))
    by_f = {int(s["f"]): s for s in states}
    fl = sorted(by_f)
    ticks = dec_ep or {}
    tick_f = sorted(ticks)
    runs: dict = defaultdict(list)          # iid -> [(state, f0, f1)]
    hits_by_f: dict = {}
    hp_by_f: dict = defaultdict(list)
    for s in states:
        f = int(s["f"])
        for e in sp7_two.claps(s):
            st = sp.control(e)[0]
            r = runs[e["iid"]]
            if r and r[-1][0] == st and r[-1][2] == f - 1:
                r[-1][2] = f
            else:
                r.append([st, f, f])
        hh = _hits(s, HA)
        if hh:
            hits_by_f[f] = hh
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if ev.get("k") == "hp" and (d.get("delta") or 0) < 0:
                hp_by_f[f].append((-int(d.get("delta")), str(d.get("source")).split("/")[-1].replace("(Clone)", "")))

    def tick(f):
        i = int(np.searchsorted(tick_f, f, side="right")) - 1
        return ticks[tick_f[i]] if i >= 0 and f - tick_f[i] <= 6 else None

    def ent(f, iid):
        s = by_f.get(f)
        return next((e for e in sp7_two.claps(s) if e["iid"] == iid), None) if s else None

    def nhits(iid, a, b):
        return sum(1 for f in range(a, b) for x in hits_by_f.get(f, ()) if x[0] == iid)

    out = []
    for iid, R in runs.items():
        for i, (st, f0, f1) in enumerate(R):
            if st not in JUMP_ANTICS or f0 > fk or (i > 0 and R[i - 1][0] in JUMP_ANTICS + ("Cast Slam Antic 2",)):
                continue
            s = by_f[f0]
            cs = sp7_two.claps(s)
            if len(cs) != 2 or not (s.get("hero") or {}).get("box"):
                continue
            e = ent(f0, iid)
            o = next(c for c in cs if c["iid"] != iid)
            face = 1 if e.get("flipX") else -1
            hx = sp.hero_x(s)
            hy = float(((s.get("hero") or {}).get("box") or [0, 0, 0, 0])[1])
            cx = float(e["pos"][0])
            rel0 = (hx - cx) * face
            dy = float((s.get("hero") or {}).get("pos", [0, 0])[1]) - float(e["pos"][1])
            prev, plen = (R[i - 1][0], R[i - 1][2] - R[i - 1][1] + 1) if i > 0 else (None, 0)
            back0 = _back(e)
            in_range = abs(hx - cx) <= 8.3 and abs(dy) <= 3.9
            esc = (prev == "Evade Scuttle" and plen <= 3) or (
                prev in ("Idle", "Walk", "After Scuttle", "Dmg Attack") and back0 <= ESC_BACK_U and in_range)
            # the jump's frames
            f_take = f_land = f_idle = f_next = None
            nxt = None
            for st2, a2, b2 in R[i + 1:]:
                if f_take is None and st2 in ("Jump", "Jump Aim", "Cast Jump", "Air"):
                    f_take = a2
                if f_take is not None and f_land is None and st2 not in JUMP_ST:
                    f_land = a2
                    land_state = st2
                if f_land is not None and f_idle is None and st2 == "Idle":
                    f_idle = a2
                if f_land is not None and a2 > f_land and st2 in MOVE_STARTS:
                    f_next, nxt = a2, st2
                    break
            if f_take is None or f_land is None:
                continue
            el = ent(f_land, iid) or ent(f_land - 1, iid)
            x_land = float(el["pos"][0]) if el else None
            sl = by_f.get(f_land)
            her = {}
            if sl is not None and (sl.get("hero") or {}).get("box") and x_land is not None:
                hxl = sp.hero_x(sl)
                wall_x = sp.WALL_L if face > 0 else sp.WALL_R      # the wall behind it (it faced the hero at the antic)
                her = {"rel_land": round((hxl - x_land) * face, 2), "wall_land": round(abs(hxl - wall_x), 2),
                       "ground_land": sp.on_ground(sl)}
                mw = []
                for f in range(f_land, f_land + 61):
                    s2 = by_f.get(f)
                    if s2 is not None and (s2.get("hero") or {}).get("box"):
                        mw.append(abs(sp.hero_x(s2) - wall_x))
                her["min_wall"] = round(min(mw), 2) if mw else None
            # the jump cast's rune circle: her box against it while lit
            rune = None
            if st == "Cast Slam Antic":
                near_lit, lit_hit = None, False
                for f in range(f_land, f_land + 140):
                    s2 = by_f.get(f)
                    if s2 is None or not (s2.get("hero") or {}).get("box"):
                        continue
                    b = s2["hero"]["box"]
                    for rx, ry, lit in _rune_circles(s2):
                        if x_land is not None and abs(rx - (x_land + face * 6.5)) > 4.0:
                            continue
                        if lit:
                            # her box's nearest point to the centre
                            qx = min(max(rx, b[0]), b[2])
                            qy = min(max(ry, b[1]), b[3])
                            dd = float(np.hypot(qx - rx, qy - ry))
                            near_lit = dd if near_lit is None else min(near_lit, dd)
                            lit_hit = lit_hit or dd < RUNE_R
                rune = {"near_lit": None if near_lit is None else round(near_lit, 2), "lit_hit": lit_hit}
            hp1 = [(f - f0, a, src) for f in range(f0, f_land + 61) for a, src in hp_by_f.get(f, ())]
            hp3 = [(f - f0, a, src) for f in range(f0, f_land + 181) for a, src in hp_by_f.get(f, ())]
            # the other one: its move starts during F's jump, its first after F's landing
            orun = runs.get(o["iid"], ())
            o_during = [x[0] for x in orun if f0 < x[1] < f_land and x[0] in MOVE_STARTS]
            o_after = next(((x[0], x[1] - f_land) for x in orun if x[1] >= f_land and x[0] in MOVE_STARTS), None)
            tk = tick(f0) or {}
            out.append({
                "f_a": f0, "t": round((f0 - f_wake) / 60.0, 2), "iid": iid, "kind": "jump" if st == "Jump Antic" else "cast",
                "prev": prev, "plen": plen, "esc": bool(esc), "back0": round(back0, 2), "rel0": round(rel0, 2),
                "d0": round(abs(hx - cx), 2), "dy0": round(dy, 2), "ground0": sp.on_ground(s),
                "feet0": round(hy - FLOOR, 2), "F": tk.get("tgt") == iid if tk else None,
                "nearest": abs(hx - cx) <= abs(hx - float(o["pos"][0])), "goal0": tk.get("goal_why"),
                "k_take": f_take - f0, "k_land": f_land - f0, "land_state": land_state,
                "k_idle": None if f_idle is None else f_idle - f0, "next": nxt,
                "k_next": None if f_next is None else f_next - f_land,
                "land_back": None if x_land is None else round(_back(el), 2),
                "hits": {"antic": nhits(iid, f0, f_take), "flight": nhits(iid, f_take, f_land),
                         "land1": nhits(iid, f_land, f_land + 60), "land3": nhits(iid, f_land + 60, f_land + 180)},
                "hits_o": {"jump": nhits(o["iid"], f0, f_land), "land1": nhits(o["iid"], f_land, f_land + 60),
                           "land3": nhits(o["iid"], f_land + 60, f_land + 180)},
                "hp1": hp1, "hp3": hp3, "her": her, "rune": rune,
                "o_st0": sp.control(o)[0], "o_d0": round(abs(hx - float(o["pos"][0])), 2), "o_back0": round(_back(o), 2),
                "sep0": round(abs(cx - float(o["pos"][0])), 2), "o_during": o_during, "o_after": o_after,
                "fk": f_land + 180 <= fk,
            })
    out.sort(key=lambda r: r["f_a"])
    return out


def summarize(J: list[dict], n_ep: int) -> dict:
    E = [j for j in J if j["esc"]]
    out = {"episodes": n_ep, "jumps": len(J), "esc": len(E), "esc_per_ep": round(len(E) / max(n_ep, 1), 2)}
    for name, L in (("esc", E), ("esc_F", [j for j in E if j["F"]]), ("esc_near", [j for j in E if j["nearest"]]),
                    ("esc_jump", [j for j in E if j["kind"] == "jump"]), ("esc_cast", [j for j in E if j["kind"] == "cast"]),
                    ("other_jumps", [j for j in J if not j["esc"]])):
        if not L:
            continue
        safe1 = [j for j in L if not j["hp1"]]
        out[name] = {
            "n": len(L), "safe_land1": len(safe1), "safe_share": round(len(safe1) / len(L), 3),
            "hp1_src": dict(Counter(src for j in L for _, _, src in j["hp1"])),
            "hits_antic": round(float(np.mean([j["hits"]["antic"] for j in L])), 2),
            "hits_flight": round(float(np.mean([j["hits"]["flight"] for j in L])), 2),
            "hits_land1": round(float(np.mean([j["hits"]["land1"] for j in L])), 2),
            "hits_land3": round(float(np.mean([j["hits"]["land3"] for j in L])), 2),
            "hits_F_to_land1": round(float(np.mean([j["hits"]["antic"] + j["hits"]["flight"] + j["hits"]["land1"]
                                                    for j in L])), 2),
            "hits_o_to_land1": round(float(np.mean([j["hits_o"]["jump"] + j["hits_o"]["land1"] for j in L])), 2),
            "hits_o_land3": round(float(np.mean([j["hits_o"]["land3"] for j in L])), 2),
            "back0": pct([j["back0"] for j in L]), "rel0": pct([j["rel0"] for j in L]),
            "land_back": pct([j["land_back"] for j in L]), "k_land": pct([j["k_land"] for j in L]),
            "k_next": pct([j["k_next"] for j in L]), "next": dict(Counter(j["next"] for j in L)),
            "rel_land": pct([j["her"].get("rel_land") for j in L]),
            "behind_land": sum(1 for j in L if (j["her"].get("rel_land") or 0) < 0),
            "min_wall": pct([j["her"].get("min_wall") for j in L]),
            "prev": dict(Counter(f"{j['prev']}:{min(j['plen'], 4)}" for j in L)),
            "o_st0": dict(Counter(j["o_st0"] for j in L)), "o_d0": pct([j["o_d0"] for j in L]),
            "o_during": sum(1 for j in L if j["o_during"]),
            "o_after": dict(Counter(j["o_after"][0] if j["o_after"] else None for j in L)),
            "o_after_k": pct([j["o_after"][1] for j in L if j["o_after"]]),
            "rune_lit_hit": sum(1 for j in L if j["rune"] and j["rune"]["lit_hit"]),
            "goal0": dict(Counter(str(j["goal0"]).split(";")[-1].strip() for j in L).most_common(6)),
        }
    return out


def attach_runs(J: list[dict], row: dict) -> None:
    """The policy's SP9b records (two_play esc_runs, f_a = the STATE frame that first showed the antic) onto the
    scanned jumps (the recording's first antic frame; the same jump within 6 frames)."""
    tp = ((row.get("policy") or {}).get("two_play") or {}).get("esc") or {}
    runs = tp.get("esc_runs") or ()
    for j in J:
        r = next((r for r in runs if 0 <= r["f_a"] - j["f_a"] <= 6), None)
        j["run"] = r


def gate(J: list[dict]) -> dict:
    """The SP9b fixed-point gate per arm: F's escape jumps the arm's script took (run mode corner / switch), no HP lost
    from the antic to the landing + 60 frames; with the arm's own checks."""
    E = [j for j in J if j["esc"] and j.get("run") and j["run"].get("mode")]
    if not E:
        return {"n": 0}
    safe = [j for j in E if not j["hp1"]]
    out = {"n": len(E), "safe": len(safe), "share": round(len(safe) / len(E), 3),
           "by_kind": {k: [sum(1 for j in E if j["kind"] == k), sum(1 for j in safe if j["kind"] == k)]
                       for k in ("jump", "cast")},
           "hp1_src": dict(Counter(src for j in E for _, _, src in j["hp1"])),
           "safe_land3": sum(1 for j in E if not j["hp3"]),
           "hits_F_antic_flight_land1_land3": [round(float(np.mean([j["hits"][k] for j in E])), 2)
                                               for k in ("antic", "flight", "land1", "land3")],
           "hits_B_jump_land1_land3": [round(float(np.mean([j["hits_o"][k] for j in E])), 2)
                                       for k in ("jump", "land1", "land3")],
           "ends": dict(Counter(j["run"].get("end") for j in E))}
    corner = [j for j in E if j["run"]["mode"] == "corner"]
    if corner:
        hops = [j["run"]["hop"] for j in corner if j["run"].get("hop")]
        out["corner"] = {"n": len(corner), "behind_at_land": sum(1 for j in corner if (j["run"].get("u_land") or 0) < 0),
                         "exit": dict(Counter(j["run"].get("exit") for j in corner)),
                         "hops": len(hops), "hop_end": dict(Counter(h.get("end") for h in hops)),
                         "hop_b": pct([h.get("b") for h in hops]), "hop_u_end": pct([h.get("u_end") for h in hops]),
                         "rune_lit_hit": sum(1 for j in corner if j["rune"] and j["rune"]["lit_hit"])}
    sw = [j for j in E if j["run"]["mode"] == "switch"]
    if sw:
        pr = [j["run"].get("press") or {} for j in sw]
        out["switch"] = {"n": len(sw), "pressed": sum(1 for p in pr if p.get("f") is not None),
                         "press_f": pct([p.get("f") for p in pr]), "hit_in_tail": sum(1 for p in pr if
                                                                                  p.get("hit") is not None
                                                                                  and p["hit"] <= 22),
                         "b_next": dict(Counter(p.get("b_next") for p in pr)),
                         "b_next_close": sum(1 for p in pr if p.get("b_next") in ("Slam Antic", "Spell Antic",
                                                                                    "Evade Scuttle")),
                         "why": dict(Counter(p.get("why") for p in pr if p.get("why")))}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", action="append", required=True)
    ap.add_argument("--arms", default="")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--all", action="store_true", help="print every escape jump")
    a = ap.parse_args(argv)
    arms = set(filter(None, a.arms.split(",")))
    J = defaultdict(list)
    n_ep = Counter()
    for arm, inst, run in manifest(a.manifest, arms):
        dec = sp7_two._decisions(run, inst)
        p = run / f"attempts_i{inst}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("outcome") == "HARNESS_FAIL" or not row.get("recording"):
                continue
            n_ep[arm] += 1
            ep = f"{run.name[:15]}{run.name[-2:] if run.name.endswith('_2') else ''}_i{inst}_e{row['episode']}"
            jj = scan(row, dec.get(int(row["episode"]), {}))
            attach_runs(jj, row)
            for j in jj:
                j["ep"] = ep
                J[arm].append(j)
    res = {arm: summarize(v, n_ep[arm]) | {"gate": gate(v)} for arm, v in J.items()}
    for arm, v in res.items():
        print(arm, json.dumps(v, indent=1, default=str))
        if a.all:
            for j in J[arm]:
                if j["esc"]:
                    print(f"  {j['ep']} t {j['t']} {j['kind']} F {j['F']} back0 {j['back0']} rel0 {j['rel0']} "
                          f"prev {j['prev']}:{j['plen']} hits {j['hits']} o {j['hits_o']} hp1 {j['hp1']} her {j['her']} "
                          f"rune {j['rune']} next {j['next']}@{j['k_next']} o {j['o_st0']} {j['o_d0']} "
                          f"o_after {j['o_after']} goal {j['goal0']}")
                    r = j.get("run")
                    if r:
                        print(f"      run {r.get('mode')} why {r.get('why')!r} land {r.get('land')} u_land "
                              f"{r.get('u_land')} exit {r.get('exit')} hop {r.get('hop')} press {r.get('press')} "
                              f"rune {r.get('rune')} end {r.get('end')}@{r.get('f_end')} hp {r.get('hp')}")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps({"arms": res, "jumps": J}, indent=1, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
