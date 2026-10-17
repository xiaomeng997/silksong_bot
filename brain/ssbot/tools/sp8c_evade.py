"""The Clapper's evades in the 1v1 runs (task 1v1 SP8c, forum.md 74): per Evade Scuttle where she is at its start
and on the first frame after it (After Scuttle reads Slam Range there: Close at <= 8.28 u centre to centre, Far at >=
8.36), the move it picks next, the hits on it during the slide and in the next move's cycle (its start to the start
of the move after), HP lost from the slide's start to the end of that cycle (with the sources), and
the SSBOT_FORUM_EVADE_CHASE script's record (dash frame, presses, end). Distances are centre to centre (the hero's
box centre, the Clapper's transform), + = in front.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sp8c_evade collect --manifest C:/ssbot/sandbox/1v1sp8ct1_manifest.txt \
        [--arms sp8c] --out C:/ssbot/data/m2_play/sp8c/t1/evade.json
    ../scripts/uv.cmd run python -m ssbot.tools.sp8c_evade report --in C:/ssbot/data/m2_play/sp8c/t1/evade.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from ssbot.combat import slam_play as sp
from ssbot.tools.sp3_jumps import _hp_events, _rows, pct

EVADE = "Evade Scuttle"
MOVES = {"Slam Antic": "slam", "Spell Antic": "cast", "Jump Antic": "jump", "Cast Slam Antic": "jcast",
         "Evade Scuttle": "evade", "Escape Jump": "escape"}
CLOSE_U = 8.28                     # After Scuttle: Close Range at <= 8.28 u (human_two: 0 of 198 off)
GATE_U = 8.0                       # the trial's success: within this at the slide's end ...
#                                    ... and no HP lost from its start to the end of the next move's cycle


def _rel(s: dict, e: dict) -> float:
    return (sp.hero_x(s) - float(e["pos"][0])) * (1 if e.get("flipX") else -1)


def evades_of(states: list[dict], label: dict, hero_attacks, runs: list[dict]) -> list[dict]:
    hp_ev = _hp_events(states)
    st_of = []
    for s in states:
        e = sp.clapper(s)
        st, tin = sp.control(e)
        st_of.append((st, tin, e))
    n = len(states)
    starts = []          # move starts: (index, move)
    for i in range(n):
        st, tin, e = st_of[i]
        if st in MOVES:
            pst, ptin, _ = st_of[i - 1] if i else (None, 0.0, None)
            if pst != st or tin < ptin:
                starts.append((i, MOVES[st]))
    out = []
    for si, (i, mv) in enumerate(starts):
        if mv != "evade":
            continue
        st, tin, e = st_of[i]
        if e is None or len(sp.clappers(states[i])) != 1:
            continue
        j = i
        while j + 1 < n and st_of[j + 1][0] == EVADE and st_of[j + 1][1] >= st_of[j][1]:
            j += 1
        nxt = next(((k, m) for k, m in starts[si + 1:si + 2]), None)
        after = st_of[j + 1] if j + 1 < n else (None, 0.0, None)
        h0 = states[i].get("hero") or {}
        b0 = h0.get("box")
        d_after = _rel(states[j + 1], after[2]) if after[2] is not None else None
        f0 = int(states[i]["f"])
        hits = []
        for k in range(i, j + 1):
            for ev in states[k].get("ev") or ():
                d = ev.get("d") or {}
                if ev.get("k") == "hit" and d.get("src") in hero_attacks and d.get("type_key") == sp.CLAPPER:
                    dealt = d.get("dealt", d.get("amount"))
                    if dealt is None or float(dealt) > 0:
                        hits.append({"k": k - i, "src": str(d.get("src")), "x": round(_rel(states[k], st_of[k][2]), 2)})
        cyc = None
        if nxt is not None:
            k1 = nxt[0]
            k2 = starts[si + 2][0] if si + 2 < len(starts) else n
            ch = 0
            for k in range(k1, k2):
                for ev in states[k].get("ev") or ():
                    d = ev.get("d") or {}
                    if ev.get("k") == "hit" and d.get("src") in hero_attacks and d.get("type_key") == sp.CLAPPER:
                        dealt = d.get("dealt", d.get("amount"))
                        ch += int(dealt is None or float(dealt) > 0)
            cyc = {"hits": ch, "frames": k2 - k1, "full": si + 2 < len(starts),
                   "x0": round(_rel(states[k1], st_of[k1][2]), 2) if st_of[k1][2] is not None else None}
        # HP lost from the slide's start to the end of the next move's cycle (a cast's bombs come after its antic)
        f_lim = (int(states[min(n - 1, starts[si + 2][0] if si + 2 < len(starts) else n - 1)]["f"])
                 if nxt is not None else int(states[-1]["f"]))
        hurt = [{"df": f - f0, "hp": a, "src": s_[-40:]} for f, a, s_ in hp_ev if f0 <= f <= f_lim]
        xs = [round(_rel(states[k], st_of[k][2]), 2) for k in range(i, j + 2) if k < n and st_of[k][2] is not None]
        room = (float(e["pos"][0]) - sp.WALL_L) if e.get("flipX") else (sp.WALL_R - float(e["pos"][0]))
        # the run may start later in the slide (the slam playbook's way out still had the keys)
        run = next((r for r in runs if f0 - 3 <= int(r.get("f0") or -99) <= f0 + (j - i)), None)
        out.append({**label, "f": f0, "nf": j - i + 1, "d0": round(_rel(states[i], e), 2),
                    "feet0": round(float(b0[1]) - 3.015, 2) if b0 else None,
                    "ground0": bool(sp.on_ground(states[i])), "room": round(room, 2),
                    "d_end": xs[-2] if len(xs) >= 2 else None, "d_after": None if d_after is None else round(d_after, 2),
                    "after": after[0], "next": nxt[1] if nxt is not None else None,
                    "next_gap": (nxt[0] - j) if nxt is not None else None, "d_min": min(xs) if xs else None,
                    "hits": hits, "cycle": cyc, "hurt": hurt, "chase": run})
    return out


def collect(manifests: list[str], arms: set | None, out: Path) -> None:
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.forum_demo import HERO_ATTACKS
    from ssbot.tools.slam_play_live import manifest
    E, eps = [], []
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
            lab = {"arm": arm, "run": run.name, "inst": inst, "ep": int(row.get("episode", -1))}
            ec = (row.get("policy") or {}).get("evade_chase") or row.get("evade_chase") or {}
            runs = list(ec.get("chase_runs") or [])
            E.extend(evades_of(states, lab, HERO_ATTACKS, runs))
            hp = [(f, a, s_) for f, a, s_ in _hp_events(states) if f <= f1]
            eps.append({**lab, "kill": row.get("f_kill") is not None, "fight_s": round((f1 - f0) / 60.0, 2),
                        "outcome": row.get("outcome"), "hp_hits": len(hp), "hp_src": [s_[-40:] for _, _, s_ in hp],
                        "evade_chase": {k: v for k, v in ec.items() if k != "chase_runs"}})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"evades": E, "episodes": eps}), "utf-8")
    print(f"{len(E)} evades, {len(eps)} episodes -> {out}")


def summarize(E: list[dict], eps: list[dict]) -> dict:
    by = defaultdict(list)
    for x in E:
        by[x["arm"]].append(x)
    out = {}
    for arm, L in sorted(by.items()):
        n = len(L)
        ch = [x for x in L if x.get("chase")]
        close = [x for x in L if x["d_after"] is not None and x["d_after"] <= CLOSE_U]
        ok = [x for x in L if x["d_after"] is not None and x["d_after"] <= GATE_U and not x["hurt"]]
        hurt = [x for x in L if x["hurt"]]
        cyc = defaultdict(lambda: [0, 0, 0])
        for x in L:
            c = x.get("cycle")
            if c and c["full"]:
                cyc[x["next"]][0] += 1
                cyc[x["next"]][1] += c["hits"]
                cyc[x["next"]][2] += c["frames"]
        E_ = [e for e in eps if e["arm"] == arm]
        fs = sum(e["fight_s"] for e in E_)
        d = {"n": n, "episodes": len(E_), "evades_per_ep": round(n / max(1, len(E_)), 2),
             "chase_runs": len(ch), "dash": sum(1 for x in ch if x["chase"].get("dash_k") is not None),
             "presses": sum(len(x["chase"].get("presses") or ()) for x in ch),
             "chase_ends": dict(Counter(f'{x["chase"]["end"]}/{x["chase"]["why"]}' for x in ch)),
             "d0": pct([x["d0"] for x in L]), "d_after": pct([x["d_after"] for x in L]),
             "d_min": pct([x["d_min"] for x in L]), "ground0": sum(x["ground0"] for x in L),
             "close": len(close), "close_share": round(len(close) / max(1, n), 3),
             "gate_ok": len(ok), "gate_share": round(len(ok) / max(1, n), 3),
             "next": dict(Counter(x["next"] for x in L)),
             "next_close": dict(Counter(x["next"] for x in close)),
             "next_far": dict(Counter(x["next"] for x in L if x not in close)),
             "hits_in_evade": sum(len(x["hits"]) for x in L),
             "hits_in_evade_per": round(sum(len(x["hits"]) for x in L) / max(1, n), 3),
             "hits_in_evade_after_k5": sum(1 for x in L for h in x["hits"] if h["k"] >= 5),
             "cycle_by_next": {k: {"n": v[0], "hits_per": round(v[1] / max(1, v[0]), 2),
                                   "s_per": round(v[2] / max(1, v[0]) / 60.0, 2),
                                   "h_s": round(60.0 * v[1] / max(1, v[2]), 3)} for k, v in sorted(cyc.items(),
                                                                                                  key=lambda t: str(t[0]))},
             "hurt": len(hurt), "hurt_src": dict(Counter(h["src"] for x in hurt for h in x["hurt"])),
             "hurt_rows": [{"run": x["run"], "inst": x["inst"], "ep": x["ep"], "f": x["f"], "d0": x["d0"],
                            "d_after": x["d_after"], "next": x["next"], "hurt": x["hurt"],
                            "chase": (x.get("chase") or {}).get("why")} for x in hurt][:12],
             "fight_s": round(fs, 1), "kills": sum(e["kill"] for e in E_),
             "hp_hitless": sum(1 for e in E_ if e["hp_hits"] == 0)}
        out[arm] = d
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--manifest", action="append", required=True)
    c.add_argument("--arms", default="")
    c.add_argument("--out", required=True)
    r = sub.add_parser("report")
    r.add_argument("--in", dest="inp", required=True)
    r.add_argument("--json", default="")
    a = ap.parse_args()
    if a.cmd == "collect":
        collect(a.manifest, set(x for x in a.arms.split(",") if x) or None, Path(a.out))
        return 0
    d = json.loads(Path(a.inp).read_text("utf-8"))
    res = summarize(d["evades"], d["episodes"])
    for arm, v in res.items():
        print(f"== {arm}")
        for k, x in v.items():
            print(f"  {k}: {json.dumps(x)}")
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
