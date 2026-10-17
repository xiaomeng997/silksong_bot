"""Two Clappers: every close slam / cast antic of the Clapper she is on (F) in live w13 episodes, per arm - the facts
for the antic switch and its gate (task 1v1 SP9c; the spec C:/ssbot/data/m2_play/switch/answer.txt 2b-2h, 3, 5 S7;
the person's plan notes of 2026-10-16 "switch target at the antic when the wall is near", "refined switch timing").

Per Slam Antic / Spell Antic of either Clapper while both live (entered from another state), with F = the Clapper she
is nearer to (|dx|) at the antic's first frame:
  close      she inside its Slam Range then (<= 8.3 u centre to centre, |dy| <= 3.9: Close Range picked it)
  back0      its centre to the wall behind it (against its facing) at the antic's first frame (u)
  sep0       F-B |dx| (u); B's state, its |dx| from her (o_d0), its back (o_back0)
  frames     f_a (antic start), f_off (its flag off: Slam 2 / Cast 2 entry), f_idle (its Idle after the move),
             f_next / next (its next move start), f_x_end (its x at f_idle), disp (its x change along its facing over
             the move: + = toward her)
  next_esc   its next move is a jump antic within ESC_BACK_U of its wall (an escape jump; the person's reason to switch)
  hits       landed hits on F from f_a to f_off / f_off to f_idle (the tail) / f_idle + 60; on B in the same spans
  hp         HP-loss events from f_a to f_idle + 60 (the SP9c gate window) and their sources
  trig       t81: back0 <= 8.1; pred: back0 + disp_est - WALK_BACK - KNOCK x hits_est < PRED_LINE (the person's refined
             trigger; the move's own displacement and hits from AswCfg); slam16: sep0 >= 16 u
  policy     the SP9c script's records (two_play.asw_runs) when the episode has them (f_a within 6 frames)

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sp9c_asw --manifest C:/ssbot/sandbox/1v1sp9bab_manifest.txt \\
        --arms rnjb,sp9bB [--json out.json] [--all]
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

ANTICS = {"Slam Antic": "slam", "Spell Antic": "cast"}
MOVE_STARTS = ("Slam Antic", "Spell Antic", "Jump Antic", "Cast Slam Antic", "Evade Scuttle")
OFF_ST = {"slam": ("Slam 2", "Slam Recover"), "cast": ("Cast 2",)}
ESC_BACK_U = 6.2
WALK_BACK = 2.1
KNOCK = 0.48
PRED_LINE = 5.4


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


def pred_back(back0: float, kind: str, disp: dict | None = None, hits: dict | None = None) -> float:
    """The person's refined trigger: its back after this move (its own displacement along its facing, + = away from the
    wall), the next walk-back WALK_BACK and her knock-back KNOCK per expected hit."""
    disp = disp or {"slam": 0.0, "cast": 0.0}
    hits = hits or {"slam": 2.0, "cast": 3.0}
    return back0 + disp.get(kind, 0.0) - WALK_BACK - KNOCK * hits.get(kind, 0.0)


def scan(row: dict, dec_ep: dict | None = None) -> list[dict]:
    from ssbot.record.recorder import RecordingReader
    HA = sp7_two._hero_attacks()
    f_wake, f_end = int(row["f_wake"]), int(row["f_end"])
    fk = row.get("f_kill") or f_end
    states = list(RecordingReader(row["recording"]).states(f_wake, f_end + 200))
    by_f = {int(s["f"]): s for s in states}
    ticks = dec_ep or {}
    tick_f = sorted(ticks)
    runs: dict = defaultdict(list)
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
            if st not in ANTICS or f0 > fk or (i > 0 and R[i - 1][0] == st):
                continue
            s = by_f[f0]
            cs = sp7_two.claps(s)
            if len(cs) != 2 or not (s.get("hero") or {}).get("box"):
                continue
            e = ent(f0, iid)
            o = next(c for c in cs if c["iid"] != iid)
            hx = sp.hero_x(s)
            cx, ox = float(e["pos"][0]), float(o["pos"][0])
            if abs(hx - cx) > abs(hx - ox):
                continue                                   # not the one she is on
            kind = ANTICS[st]
            face = 1 if e.get("flipX") else -1
            dy = float((s.get("hero") or {}).get("pos", [0, 0])[1]) - float(e["pos"][1])
            close = abs(hx - cx) <= 8.3 and abs(dy) <= 3.9
            prev = R[i - 1][0] if i > 0 else None
            f_off = f_idle = f_next = None
            nxt = None
            for st2, a2, b2 in R[i + 1:]:
                if f_off is None and st2 in OFF_ST[kind]:
                    f_off = a2
                if f_idle is None and st2 in ("Idle", "Walk"):
                    f_idle = a2
                if a2 > f0 and st2 in MOVE_STARTS:
                    f_next, nxt = a2, st2
                    break
            if f_off is None or f_idle is None:
                continue
            ei = ent(f_idle, iid) or ent(f_idle - 1, iid)
            disp = None if ei is None else round((float(ei["pos"][0]) - cx) * face, 2)
            nb = None
            if f_next is not None:
                en = ent(f_next, iid)
                nb = None if en is None else round(_back(en), 2)
            next_esc = nxt in ("Jump Antic", "Cast Slam Antic") and nb is not None and nb <= ESC_BACK_U
            g1 = f_idle + 60
            hp = [(f - f0, a, src) for f in range(f0, g1 + 1) for a, src in hp_by_f.get(f, ())]
            orun = runs.get(o["iid"], ())
            o_next = next(((x[0], x[1] - f0) for x in orun if x[1] > f0 and x[0] in MOVE_STARTS), None)
            tk = tick(f0) or {}
            back0 = _back(e)
            out.append({
                "f_a": f0, "t": round((f0 - f_wake) / 60.0, 2), "iid": iid, "kind": kind, "prev": prev,
                "close": close, "back0": round(back0, 2), "rel0": round((hx - cx) * face, 2),
                "d0": round(abs(hx - cx), 2), "dy0": round(dy, 2), "ground0": sp.on_ground(s),
                "sep0": round(abs(cx - ox), 2), "o_st0": sp.control(o)[0], "o_d0": round(abs(hx - ox), 2),
                "o_back0": round(_back(o), 2), "o_side": (ox - cx) * face > 0,
                "F": tk.get("tgt") == iid if tk else None, "goal0": tk.get("goal_why"),
                "k_off": f_off - f0, "k_idle": f_idle - f0, "next": nxt,
                "k_next": None if f_next is None else f_next - f_idle, "next_back": nb, "next_esc": next_esc,
                "disp": disp,
                "hits": {"lock": nhits(iid, f0, f_off), "tail": nhits(iid, f_off, f_idle),
                         "idle1": nhits(iid, f_idle, g1)},
                "hits_o": {"lock": nhits(o["iid"], f0, f_off), "tail": nhits(o["iid"], f_off, f_idle),
                           "idle1": nhits(o["iid"], f_idle, g1)},
                "hp": hp, "o_next": o_next, "full": g1 <= fk,
                "trig": {"t81": back0 <= 8.1, "pred": pred_back(back0, kind) < PRED_LINE,
                         "slam16": abs(cx - ox) >= 16.0},
            })
    out.sort(key=lambda r: r["f_a"])
    return out


def attach_runs(J: list[dict], row: dict) -> None:
    tp = ((row.get("policy") or {}).get("two_play") or {}).get("asw") or {}
    runs = tp.get("asw_runs") or ()
    for j in J:
        j["run"] = next((r for r in runs if 0 <= r["f_a"] - j["f_a"] <= 6), None)


def _cand(j: dict, trig: str) -> bool:
    """The antic switch's trigger on a recorded antic (no policy run needed): close, B not attacking, the wall test,
    slams only with F-B >= 16 u, B >= 4 u from F."""
    if not j["close"] or j["o_st0"] not in ("Idle", "Walk", "After Scuttle", "Evade Scuttle"):
        return False
    if j["kind"] == "slam" and not j["trig"]["slam16"]:
        return False
    if j["sep0"] < 4.0:
        return False
    return bool(j["trig"][trig])


def summarize(J: list[dict], n_ep: int, fight_s: float) -> dict:
    C = [j for j in J if j["close"]]
    out = {"episodes": n_ep, "fight_min": round(fight_s / 60.0, 2), "antics": len(J), "close": len(C)}
    for name, L in (("close_slam", [j for j in C if j["kind"] == "slam"]),
                    ("close_cast", [j for j in C if j["kind"] == "cast"]),
                    ("cand_t81", [j for j in J if _cand(j, "t81")]),
                    ("cand_pred", [j for j in J if _cand(j, "pred")]),
                    ("close_not_t81", [j for j in C if not j["trig"]["t81"]])):
        if not L:
            out[name] = {"n": 0}
            continue
        safe = [j for j in L if not j["hp"]]
        out[name] = {
            "n": len(L), "per_min": round(len(L) / max(fight_s / 60.0, 1e-6), 2),
            "slam_cast": [sum(1 for j in L if j["kind"] == "slam"), sum(1 for j in L if j["kind"] == "cast")],
            "safe": len(safe), "safe_share": round(len(safe) / len(L), 3),
            "hp_src": dict(Counter(src for j in L for _, _, src in j["hp"])),
            "hits_F_lock_tail_idle1": [round(float(np.mean([j["hits"][k] for j in L])), 2)
                                       for k in ("lock", "tail", "idle1")],
            "hits_B_lock_tail_idle1": [round(float(np.mean([j["hits_o"][k] for j in L])), 2)
                                       for k in ("lock", "tail", "idle1")],
            "back0": pct([j["back0"] for j in L]), "sep0": pct([j["sep0"] for j in L]),
            "o_d0": pct([j["o_d0"] for j in L]), "rel0": pct([j["rel0"] for j in L]),
            "disp_slam": pct([j["disp"] for j in L if j["kind"] == "slam"]),
            "disp_cast": pct([j["disp"] for j in L if j["kind"] == "cast"]),
            "k_off": pct([j["k_off"] for j in L]), "k_idle": pct([j["k_idle"] for j in L]),
            "next": dict(Counter(j["next"] for j in L)), "next_esc": sum(1 for j in L if j["next_esc"]),
            "o_st0": dict(Counter(j["o_st0"] for j in L)), "o_side": sum(1 for j in L if j["o_side"]),
            "F": sum(1 for j in L if j["F"]),
            "o_next": dict(Counter(j["o_next"][0] if j["o_next"] else None for j in L)),
        }
    return out


def gate(J: list[dict]) -> dict:
    """The SP9c fixed-point gate: F's close antics the arm's script took (a run with a mode), no HP lost from the antic
    to F's Idle + 60 frames; with the arm's own checks (first hit on B, in F's tail, B's next move)."""
    E = [j for j in J if j.get("run") and j["run"].get("mode")]
    if not E:
        return {"n": 0}
    safe = [j for j in E if not j["hp"]]
    runs = [j["run"] for j in E]
    out = {"n": len(E), "safe": len(safe), "share": round(len(safe) / len(E), 3),
           "by_kind": {k: [sum(1 for j in E if j["kind"] == k), sum(1 for j in safe if j["kind"] == k)]
                       for k in ("slam", "cast")},
           "hp_src": dict(Counter(src for j in E for _, _, src in j["hp"])),
           "hp_k": [h[0] for j in E for h in j["hp"]],
           "hits_F_lock_tail_idle1": [round(float(np.mean([j["hits"][k] for j in E])), 2)
                                      for k in ("lock", "tail", "idle1")],
           "hits_B_lock_tail_idle1": [round(float(np.mean([j["hits_o"][k] for j in E])), 2)
                                      for k in ("lock", "tail", "idle1")],
           "b_hit": sum(1 for r in runs if r.get("hit_b") is not None),
           "b_hit_k_off": pct([r.get("hit_b") for r in runs if r.get("hit_b") is not None]),
           "b_hit_in_tail": sum(1 for r in runs if r.get("hit_in_tail")),
           "b_next": dict(Counter(r.get("b_next") for r in runs)),
           "b_next_close": sum(1 for r in runs if r.get("b_next") in ("Slam Antic", "Spell Antic", "Evade Scuttle")),
           "lock_hits": sum(len(r.get("lock_hits") or ()) for r in runs),
           "ends": dict(Counter(r.get("end") for r in runs)),
           "lag": pct([r.get("lag") for r in runs])}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", action="append", required=True)
    ap.add_argument("--arms", default="")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--all", action="store_true", help="print every candidate / run")
    a = ap.parse_args(argv)
    arms = set(filter(None, a.arms.split(",")))
    J = defaultdict(list)
    n_ep = Counter()
    fight = Counter()
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
            fight[arm] += ((row.get("f_kill") or row["f_end"]) - row["f_wake"]) / 60.0
            ep = f"{run.name[:15]}{run.name[-2:] if run.name.endswith('_2') else ''}_i{inst}_e{row['episode']}"
            jj = scan(row, dec.get(int(row["episode"]), {}))
            attach_runs(jj, row)
            for j in jj:
                j["ep"] = ep
                J[arm].append(j)
    res = {arm: summarize(v, n_ep[arm], fight[arm]) | {"gate": gate(v)} for arm, v in J.items()}
    for arm, v in res.items():
        print(arm, json.dumps(v, indent=1, default=str))
        if a.all:
            for j in J[arm]:
                if _cand(j, "t81") or _cand(j, "pred") or j.get("run"):
                    print(f"  {j['ep']} t {j['t']} {j['kind']} back0 {j['back0']} pred "
                          f"{pred_back(j['back0'], j['kind']):.2f} sep0 {j['sep0']} o {j['o_st0']} {j['o_d0']} rel0 "
                          f"{j['rel0']} hits {j['hits']} o {j['hits_o']} hp {j['hp']} next {j['next']} esc "
                          f"{j['next_esc']} o_next {j['o_next']} disp {j['disp']}")
                    r = j.get("run")
                    if r:
                        print(f"      run {json.dumps(r, default=str)}")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps({"arms": res, "antics": J}, indent=1, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
