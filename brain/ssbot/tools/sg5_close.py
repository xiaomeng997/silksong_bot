"""Task 1v1 SG5 part 3: which moves the Clapper starts with the hero close (forum.md 61). Offline, from the collected
live Clapper 1v1 episodes (forum_remaining_hits collect: C:/ssbot/data/m2_live_g/col/eps, every arm).

Per episode, from the wave's activation to the kill: every move start of the Clapper (its Control state entering an
attack start, gauntlet_tables FORUM_SPECS attack_starts, or Escape Jump / Dmg Attack), the state it left (the decision
state: Idle / Walk / Close Range / Far Range / After Scuttle / Dmg Attack ...), the hero's distance at that frame
(hero box centre to the Clapper's transform, horizontal, u, centre to centre), airborne, and the hero's damage taken
during the move (the move start to the next decision state; hero `damage` events) and during the decision states
(body contact while it idles / walks). Bins: < 3.5, 3.5-5, 5-8.05 (Slam Range), 8.05-12, >= 12 u.

    ../scripts/uv.cmd run python -m ssbot.tools.sg5_close [--eps C:/ssbot/data/m2_live_g/col/eps] [--out <dir>]
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from ssbot.tools.sg4_budget import CLAPPER, attempt_row

EPS = Path("C:/ssbot/data/m2_live_g/col/eps")
OUT = Path(r"C:\ssbot\data\m2_map\sg5")
BINS = (0.0, 3.5, 5.0, 8.05, 12.0, 99.0)
BIN_NAMES = ("<3.5", "3.5-5", "5-8.05", "8.05-12", ">=12")
EXTRA_STARTS = {"Escape Jump": "CC_ESCAPE_JUMP", "Dmg Attack": "CC_DMG_ATTACK"}


def _bin(d: float) -> str:
    for i in range(len(BINS) - 1):
        if BINS[i] <= d < BINS[i + 1]:
            return BIN_NAMES[i]
    return BIN_NAMES[-1]


def analyse(e: dict) -> dict:
    from ssbot.knowledge.gauntlet_tables import FORUM_SPECS
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.forum_remaining_hits import compact_frames, fsm_timeline
    spec = FORUM_SPECS[CLAPPER]
    starts = dict(spec.attack_starts) | EXTRA_STARTS
    dec = frozenset(spec.decision_states) - {"Dmg Attack", "Escape Jump"}
    row = attempt_row(e["run"], int(e["inst"]), int(e["ep"]))
    rd = RecordingReader(row["recording"])
    f0, f1 = int(row["f_wake"]), int(row["f_kill"] or row["f_end"])
    fr = compact_frames(rd.states(f0, f1), fsm_timeline(rd, f0, f1))
    moves, dec_hits, hits = [], [], []
    last_move = None
    prev_st, prev_dec, cur = None, None, None
    near_dec_frames = 0
    for x in fr:
        cl = next((t for t in x["ents"] if t[1] == CLAPPER and t[10]), None)
        st = cl[6] if cl else None
        b = x["box"]
        hx = 0.5 * (b[0] + b[2]) if b else np.nan
        d = abs(hx - cl[2]) if (cl and b) else np.nan
        air = not x["fl"].get("onGround", True) if x["fl"] else False
        dmg = sum(1 for k, dd in x["ev"] if k == "damage")
        if dmg:
            # what hit: the source entity, the damage colliders overlapping the hero box (+0.3 u) on this frame
            srcs = sorted({str(dd.get("source", "")).split("/")[-1] for k, dd in x["ev"] if k == "damage"})
            cols = []
            if b:
                for t in x["ents"]:
                    for nm, bb in t[8]:
                        if bb[0] - 0.3 <= b[2] and bb[2] + 0.3 >= b[0] and bb[1] - 0.3 <= b[3] and bb[3] + 0.3 >= b[1]:
                            cols.append(f"{t[1]}:{nm}")
            hits.append({"f": x["f"], "state": st, "move": (cur or {}).get("move"), "last_move": last_move,
                         "d": round(float(d), 2), "src": srcs, "cols": sorted(set(cols))})
        if st != prev_st and st in starts:
            last_move = starts[st]
            cur = {"f": x["f"], "move": starts[st], "state": st, "from": prev_dec, "d": round(float(d), 2),
                   "air": bool(air), "dmg": 0, "end": None}
            moves.append(cur)
        elif st in dec:
            if cur is not None:
                cur["end"] = x["f"]
            cur = None
            prev_dec = st
            if d == d and d < 5.0:
                near_dec_frames += 1
            if dmg:
                dec_hits.append({"f": x["f"], "state": st, "d": round(float(d), 2), "n": dmg})
        if cur is not None and dmg:
            cur["dmg"] += dmg
        if st is not None:
            prev_st = st
    return {"run": e["run"], "inst": e["inst"], "ep": e["ep"], "arm": e.get("arm"), "moves": moves,
            "dec_hits": dec_hits, "hits": hits, "near_dec_frames": near_dec_frames, "frames": len(fr)}


def _hit_kinds(res: list[dict]) -> dict:
    """Hero damage frames by (the Clapper's move then, or "decision state after <move>"; the colliders touching)."""
    out = defaultdict(int)
    for r in res:
        for h in r.get("hits", ()):
            where = h["move"] or f"dec after {h['last_move']}"
            col = ",".join(c.split(":", 1)[1] for c in h["cols"]) or "none"
            out[f"{where} | {'<5' if h['d'] < 5 else '>=5'} | {col}"] += 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def summarise(res: list[dict]) -> dict:
    tab = defaultdict(lambda: defaultdict(int))
    dmg = defaultdict(lambda: defaultdict(int))
    frm = defaultdict(lambda: defaultdict(int))
    for r in res:
        for m in r["moves"]:
            if m["d"] != m["d"]:
                continue
            b = _bin(m["d"])
            tab[b][m["move"]] += 1
            dmg[b][m["move"]] += int(m["dmg"] > 0)
            if m["d"] < 5.0:
                frm[m["from"]][m["move"]] += 1
    out = {"episodes": len(res), "moves_by_bin": {b: dict(tab[b]) for b in BIN_NAMES},
           "moves_with_damage_by_bin": {b: dict(dmg[b]) for b in BIN_NAMES},
           "near_from_state": {k: dict(v) for k, v in frm.items()},
           "dec_hits": [h | {"run": r["run"], "ep": r["ep"]} for r in res for h in r["dec_hits"]],
           "near_dec_frames": int(sum(r["near_dec_frames"] for r in res)),
           "hits_by_kind": _hit_kinds(res),
           "frames": int(sum(r["frames"] for r in res))}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eps", type=Path, default=EPS)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    res = []
    for p in sorted(Path(a.eps).glob("*.json")):
        e = json.loads(p.read_text("utf-8"))["episode"]
        try:
            res.append(analyse(e))
        except Exception as ex:  # noqa: BLE001 - a broken recording is skipped and reported
            print("skip", p.name, repr(ex)[:200], flush=True)
    s = summarise(res)
    (a.out / "close_moves.json").write_text(json.dumps({"summary": s, "episodes": res}, indent=1), "utf-8")
    lines = [f"episodes {s['episodes']}, frames {s['frames']}, decision-state frames with the hero < 5 u "
             f"{s['near_dec_frames']}"]
    moves = sorted({m for b in s["moves_by_bin"].values() for m in b})
    lines.append("bin      " + " ".join(f"{m[3:]:>12}" for m in moves))
    for b in BIN_NAMES:
        lines.append(f"{b:8} " + " ".join(f"{s['moves_by_bin'][b].get(m, 0):>5} ({s['moves_with_damage_by_bin'][b].get(m, 0):>3}h)"
                                          for m in moves))
    lines.append("moves started < 5 u by the state they left: " + json.dumps(s["near_from_state"]))
    lines.append(f"hero damage frames in decision states: {len(s['dec_hits'])}")
    lines.append("hero damage frames by (move or decision state after a move | hero distance | colliders touching):")
    lines += [f"  {n:4} {k}" for k, n in s["hits_by_kind"].items()]
    (a.out / "close_moves.txt").write_text("\n".join(lines) + "\n", "utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
