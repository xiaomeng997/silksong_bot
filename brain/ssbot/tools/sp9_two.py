"""Two-Clapper live episodes, SP9's per-rule checks (task 1v1 SP9a, Forum_W_w13; the spec C:/ssbot/data/m2_play/switch/
answer.txt section 5, human_two/answer.txt R1-R10, buddy/answer.txt R1-R3), per arm from run manifests.

On top of ssbot.tools.sp7_two's episode (outcome, landed hits, HP-loss hits by source, slams struck, the geometry):
  kills        Clappers killed per episode (both = the battle's end)
  both alive   landed hits on the Clappers per second while both live (the person 1.5, SP7's two 0.64)
  S1 evades    every Evade Scuttle of F (the Clapper nearer to her at its start; not the ones cancelled into an Escape
               Jump): her distance (centre to centre: her box centre, its transform) at the start and at After Scuttle,
               Close (<= 8.28 u) at After Scuttle, how far she followed during the slide (u toward it); the run record
               of the chase script (TWO_CHASE) when the episode has one
  S2 idle runs every Idle run of F (entry -> the next state) while both live: her distance and |dy| at the entry, the
               first landed hit on it in the run (frames from the entry), ended by her hit (the next state Dmg Attack)
  S3 close     F's Spell Antic with her <= 8.28 u at its entry (close cast: hits on it from the antic entry to the end of
               Cast 2) and F's Slam Antic (focus slam: hits to the end of Slam Recover)
  S5 spacing   share of both-alive time with the other one (not F) within 4 u of her; within 4 u of the other one while
               F is in Slam Antic; within 2.5 u of a Clapper in Idle / Walk / Evade / Cast / Recover; SC2 hits per minute
  S6 opening   her x at the first Enter Land (wake = t 0 at the Drop Antic), the first landed hit's time and target, hits
               on c2 (the left one) before its first Idle and by t 4 / t 6, c2's HP when c3 first gets within 8.3 u
  gate         landed / s x time to the 3rd HP-loss hit (S8: >= 46)
F = the Clapper nearer to her (|dx|) on the event's first frame.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sp9_two --manifest C:/ssbot/sandbox/1v1sp7ab_manifest.txt \\
        --arms two [--base two] [--json out.json]
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

CLOSE_U = 8.28
IDLE_LIKE = ("Idle", "Walk", "Evade Scuttle", "Spell Antic", "Cast 1", "Cast 2", "Slam Recover")
CAST_END = ("Cast 2",)
SLAM_ST = sp.SLAM_STATES


def _hits_of(s: dict, HA) -> list[tuple[object, str]]:
    out = []
    for ev in s.get("ev") or ():
        k, d = ev.get("k"), ev.get("d") or {}
        if k == "hit" and d.get("type_key") == sp.CLAPPER and d.get("src") in HA:
            dealt = d.get("dealt", d.get("amount"))
            if dealt is None or float(dealt) > 0:
                out.append((d.get("ent") or d.get("iid") or d.get("target_iid"), str(d.get("src"))))
    return out


def _kills_of(s: dict) -> int:
    return sum(1 for ev in s.get("ev") or () if ev.get("k") == "hit" and (ev.get("d") or {}).get("type_key") == sp.CLAPPER
               and (ev.get("d") or {}).get("dead"))


def rules_pass(row: dict, f_wake: int, f_end: int, fk: int, policy: dict | None) -> dict:
    """The per-rule records of one episode (module docstring)."""
    from ssbot.record.recorder import RecordingReader
    HA = sp7_two._hero_attacks()
    states = list(RecordingReader(row["recording"]).states(f_wake - 400, f_end))
    prev: dict = {}
    prev_t: dict = {}             # iid -> its Control state time on the last frame
    evades, idles, closes = [], [], []
    open_ev: dict = {}
    open_idle: dict = {}
    open_close: dict = {}
    n_both = n_other4 = n_near25 = n_slam_other4 = n_slam_any = 0
    landed_both = 0
    landed_all = 0
    op = {"x_enter_land": None, "first_hit_t": None, "first_hit_tgt": None, "c2_hits_pre_idle": 0, "c2_hits_t4": 0,
          "c2_hits_t6": 0, "c2_hp_contact": None, "c2_idle_f": None, "x_wake": None}
    c2 = c3 = None
    hp_hits = []
    kills, kill_t = 0, []
    for s in states:
        f = int(s["f"])
        h = s.get("hero") or {}
        if not (h.get("box") or h.get("pos")):
            continue
        hx = sp.hero_x(s)
        hy = float((h.get("pos") or [0.0, 0.0])[1])
        cs = sp7_two.claps(s)
        hits = _hits_of(s, HA) if f_wake <= f <= fk else []
        landed_all += len(hits)
        k_here = _kills_of(s) if f_wake <= f <= f_end else 0
        if k_here:
            kills += k_here
            kill_t += [round((f - f_wake) / 60.0, 2)] * k_here
        if f == f_wake or (op["x_wake"] is None and f >= f_wake):
            op["x_wake"] = round(hx, 2)
        if cs and c2 is None and f >= f_wake:
            xs = sorted(cs, key=lambda e: float(e["pos"][0]))
            if len(xs) == 2:
                c2, c3 = xs[0]["iid"], xs[1]["iid"]
        by = {e["iid"]: e for e in cs}
        if len(cs) == 2 and f_wake <= f <= fk:
            n_both += 1
            landed_both += len(hits)
            near = min(cs, key=lambda e: abs(float(e["pos"][0]) - hx))
            other = next(e for e in cs if e["iid"] != near["iid"])
            n_other4 += abs(float(other["pos"][0]) - hx) < 4.0
            n_near25 += any(abs(float(e["pos"][0]) - hx) < 2.5 and sp.control(e)[0] in IDLE_LIKE for e in cs)
            for a, b in ((cs[0], cs[1]), (cs[1], cs[0])):
                if sp.control(a)[0] == "Slam Antic":
                    n_slam_any += 1
                    n_slam_other4 += abs(float(b["pos"][0]) - hx) < 4.0
        # the opening (t from the wake)
        t = (f - f_wake) / 60.0
        if f >= f_wake and c2 is not None:
            for iid, src in hits:
                if op["first_hit_t"] is None:
                    op["first_hit_t"], op["first_hit_tgt"] = round(t, 2), ("c2" if iid == c2 else "c3")
                if iid == c2:
                    op["c2_hits_pre_idle"] += op["c2_idle_f"] is None
                    op["c2_hits_t4"] += t <= 4.0
                    op["c2_hits_t6"] += t <= 6.0
            e2, e3 = by.get(c2), by.get(c3)
            if op["x_enter_land"] is None and e2 is not None and sp.control(e2)[0] == "Enter Land":
                op["x_enter_land"] = round(hx, 2)
            if op["c2_idle_f"] is None and e2 is not None and sp.control(e2)[0] == "Idle":
                op["c2_idle_f"] = f
            if op["c2_hp_contact"] is None and e2 is not None and e3 is not None and op["c2_idle_f"] is not None \
                    and abs(float(e3["pos"][0]) - hx) <= 8.3:
                op["c2_hp_contact"] = (e2.get("hp"), round(t, 2))
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if ev.get("k") == "hp" and (d.get("delta") or 0) < 0 and f_wake <= f <= fk:
                hp_hits.append(f)
        # per-Clapper state runs
        near_iid = min(cs, key=lambda e: abs(float(e["pos"][0]) - hx))["iid"] if cs else None
        for e in cs:
            iid = e["iid"]
            st, tin = sp.control(e)
            cx, cy = float(e["pos"][0]), float(e["pos"][1])
            d = abs(hx - cx)
            pst = prev.get(iid)
            # an Idle re-entry in one frame (a hit -> Dmg Attack -> Close / Far Range -> CANCEL -> Idle while its buddy
            # attacks): the state stays Idle, its state time starts again
            re_idle = st == "Idle" and pst == "Idle" and tin + 0.5 / 60.0 < prev_t.get(iid, 0.0)
            prev_t[iid] = tin
            hit_here = [x for x in hits if x[0] == iid]
            # S1: evades
            if iid in open_ev:
                r = open_ev[iid]
                r["hits"] += len(hit_here)
                if st != "Evade Scuttle":
                    r["next"] = st
                    r["d_end"] = round(d, 2)
                    r["follow"] = round((hx - r["hx0"]) * (1 if cx > r["hx0"] else -1), 2)
                    r["close"] = d <= CLOSE_U
                    if st != "Escape Jump" and r["F"]:
                        evades.append(r)
                    del open_ev[iid]
            if st == "Evade Scuttle" and pst != "Evade Scuttle" and len(cs) == 2 and f <= fk:
                open_ev[iid] = {"f": f, "t": round(t, 2), "d0": round(d, 2), "hx0": hx, "F": iid == near_iid,
                                "hits": 0}
            # S2: idle runs
            if iid in open_idle:
                r = open_idle[iid]
                if hit_here and r["first"] is None:
                    r["first"] = f - r["f"]
                if st != "Idle" or re_idle:
                    r["next"] = "Idle (re-entry)" if re_idle else st
                    r["len"] = f - r["f"]
                    # only Idle reacts to a hit (Dmg Attack decides at once, in the same frame)
                    r["by_hit"] = bool(hit_here)
                    if r["F"]:
                        idles.append(r)
                    del open_idle[iid]
            if st == "Idle" and (pst != "Idle" or re_idle) and len(cs) == 2 and f <= fk:
                open_idle[iid] = {"f": f, "t": round(t, 2), "from": pst, "d0": round(d, 2), "dy": round(hy - cy, 2),
                                  "F": iid == near_iid, "first": (0 if hit_here and not re_idle else None)}
            # S3: close moves
            if iid in open_close:
                r = open_close[iid]
                r["hits"] += len(hit_here)
                if st not in r["states"]:
                    r["end"] = st
                    closes.append(r)
                    del open_close[iid]
            if st in ("Spell Antic", "Slam Antic") and pst != st and len(cs) == 2 and f <= fk and iid == near_iid:
                kind = "cast" if st == "Spell Antic" else "slam"
                if kind == "slam" or d <= CLOSE_U:
                    open_close[iid] = {"f": f, "t": round(t, 2), "kind": kind, "d0": round(d, 2),
                                       "hits": len(hit_here),
                                       "states": ("Spell Antic", "Cast 1", "Cast 2") if kind == "cast" else SLAM_ST}
            prev[iid] = st
    # HP-loss hits after each event: an evade to its start + 120 frames (the next move's cycle), an Idle run to + 60, a
    # close cast to + 110 (ring 1's light + 25 frames ~ antic + 100), a focus slam to + 170
    for lst, win in ((evades, 120), (idles, 60)):
        for r in lst:
            r["hp"] = sum(1 for g in hp_hits if r["f"] <= g <= r["f"] + win)
    for r in closes:
        win = 110 if r["kind"] == "cast" else 170
        r["hp"] = sum(1 for g in hp_hits if r["f"] <= g <= r["f"] + win)
    fight_s = (fk - f_wake) / 60.0
    both_s = n_both / 60.0
    t3 = (hp_hits[2] - f_wake) / 60.0 if len(hp_hits) >= 3 else fight_s
    return {"evades": evades, "idles": idles, "closes": [{k: v for k, v in r.items() if k != "states"} for r in closes],
            "both_s": round(both_s, 2), "landed_both": landed_both,
            "landed_per_s_both": round(landed_both / both_s, 3) if both_s > 0 else None,
            "other4_share": round(n_other4 / max(n_both, 1), 4), "near25_share": round(n_near25 / max(n_both, 1), 4),
            "slam_other4_share": round(n_slam_other4 / max(n_slam_any, 1), 4), "slam_frames": n_slam_any,
            "opening": op, "t3_s": round(t3, 2), "kills_n": kills, "kill_t": kill_t, "landed_all": landed_all, "fight_s": round(fight_s, 2)}


def episode(arm: str, inst: int, run: Path, row: dict, dec: dict) -> dict:
    e = sp7_two.episode(arm, inst, run, row, dec)
    f_wake, f_end = int(row["f_wake"]), int(row["f_end"])
    fk = row.get("f_kill") or f_end
    r = rules_pass(row, f_wake, f_end, fk, row.get("policy"))
    pol = row.get("policy") or {}
    e.update(r)
    e["first_kill_s"] = r["kill_t"][0] if r["kill_t"] else None
    e["gate"] = round(e["landed"] / max(e["fight_s"], 1e-9) * r["t3_s"], 1)
    e["two_play"] = pol.get("two_play")
    e["evade_chase"] = {k: v for k, v in (pol.get("evade_chase") or {}).items() if k != "chase_runs"}
    return e


def _idlehit(ok: list[dict]) -> dict:
    """TWO_IDLEHIT's runs (policy two_play.idle_runs_rec: [f0, re, d0, k_press, k_hit, walk, why])."""
    R = [r for e in ok for r in ((e.get("two_play") or {}).get("idle_runs_rec") or ())]
    if not R:
        return {}
    pr = [r for r in R if r[3] is not None]
    hit = [r for r in R if r[4] is not None]
    return {"runs": len(R), "re": sum(1 for r in R if r[1]), "press": len(pr), "hit": len(hit),
            "hit_within_15": sum(1 for r in hit if r[4] <= 15), "k_press_p50": pct([r[3] for r in pr], (50,)),
            "k_hit_p10_50_90": pct([r[4] for r in hit]), "walk_runs": sum(1 for r in R if r[5]),
            "why": dict(Counter(r[6] for r in R))}


def _chase(ok: list[dict]) -> dict:
    out = Counter()
    for e in ok:
        for k, v in (e.get("evade_chase") or {}).items():
            if isinstance(v, (int, float)):
                out[k] += v
    return dict(out)


def summarize(E: list[dict]) -> dict:
    out = sp7_two.summarize(E)
    ok = [e for e in E if e.get("outcome") != "HARNESS_FAIL"]
    mins = sum(e["fight_s"] for e in ok) / 60.0
    ev = [x for e in ok for x in e.get("evades", ())]
    idl = [x for e in ok for x in e.get("idles", ())]
    cl = [x for e in ok for x in e.get("closes", ())]
    casts = [x for x in cl if x["kind"] == "cast"]
    slams = [x for x in cl if x["kind"] == "slam"]
    hit_first = [x["first"] for x in idl if x["first"] is not None]
    H = [h for e in ok for h in e["hits"] if h["before_kill"]]
    both_s = sum(e.get("both_s", 0.0) for e in ok)
    op = [e["opening"] for e in ok if e.get("opening")]
    out.update({
        "kills_clappers": sum(e.get("kills_n", 0) for e in ok),
        "survival_s_p10_50_90": pct([e["fight_s"] for e in ok]),
        "landed_per_s_both": round(sum(e.get("landed_both", 0) for e in ok) / both_s, 3) if both_s else None,
        "hp_hits_per_min": round(len(H) / mins, 2) if mins else None,
        "hp_hits_per_min_by_src": {k: round(v / mins, 2) for k, v in Counter(h["src"] for h in H).most_common()},
        "S1_evades": len(ev), "S1_close_share": round(sum(x["close"] for x in ev) / len(ev), 3) if ev else None,
        "S1_follow_p50": pct([x["follow"] for x in ev], (50,)), "S1_d_end_p10_50_90": pct([x["d_end"] for x in ev]),
        "S1_next": dict(Counter(x["next"] for x in ev)),
        "S1_close_safe_share": round(sum(1 for x in ev if x["close"] and not x.get("hp")) / len(ev), 3) if ev else None,
        "S2_hp_after_share": round(sum(1 for x in idl if x.get("hp")) / len(idl), 3) if idl else None,
        "S3_close_casts_safe": sum(1 for x in casts if not x.get("hp")),
        "S3_focus_slams_safe": sum(1 for x in slams if not x.get("hp")),
        "idlehit": _idlehit(ok),
        "open_script": dict(Counter(str((e.get("two_play") or {}).get("open", {}).get("done")) for e in ok)),
        "chase_runs": _chase(ok),
        "S2_idle_runs": len(idl), "S2_hit_ended_share": round(sum(x["by_hit"] for x in idl) / len(idl), 3) if idl
        else None,
        "S2_first_hit_s_p50": (round(float(np.median(hit_first)) / 60.0, 3) if hit_first else None),
        "S2_hit_within_15f_share": round(sum(1 for x in idl if x["first"] is not None and x["first"] <= 15) / len(idl), 3)
        if idl else None,
        "S2_d0_p10_50_90": pct([x["d0"] for x in idl]),
        "S2_in_83_share": round(sum(1 for x in idl if x["d0"] <= 8.3 and abs(x["dy"]) <= 3.9) / len(idl), 3) if idl
        else None,
        "S3_close_casts": len(casts), "S3_landed_per_close_cast": round(float(np.mean([x["hits"] for x in casts])), 2)
        if casts else None,
        "S3_focus_slams": len(slams), "S3_landed_per_focus_slam": round(float(np.mean([x["hits"] for x in slams])), 2)
        if slams else None,
        "S5_other4_share": round(float(np.mean([e.get("other4_share", 0.0) for e in ok])), 4) if ok else None,
        "S5_near25_share": round(float(np.mean([e.get("near25_share", 0.0) for e in ok])), 4) if ok else None,
        "S5_slam_other4_share": round(sum(e.get("slam_other4_share", 0) * e.get("slam_frames", 0) for e in ok)
                                      / max(sum(e.get("slam_frames", 0) for e in ok), 1), 4),
        "S5_sc2_per_min": round(sum(1 for h in H if "Slam Collider 2" in h["src"]) / mins, 2) if mins else None,
        "S6_x_enter_land_p10_50_90": pct([o["x_enter_land"] for o in op]),
        "S6_x_wake_p50": pct([o["x_wake"] for o in op], (50,)),
        "S6_first_hit_t_p50": pct([o["first_hit_t"] for o in op], (50,)),
        "S6_first_target": dict(Counter(o["first_hit_tgt"] for o in op)),
        "S6_c2_hits_pre_idle_mean": round(float(np.mean([o["c2_hits_pre_idle"] for o in op])), 2) if op else None,
        "S6_c2_hits_t4_mean": round(float(np.mean([o["c2_hits_t4"] for o in op])), 2) if op else None,
        "S6_c2_hits_t6_mean": round(float(np.mean([o["c2_hits_t6"] for o in op])), 2) if op else None,
        "S6_c2_hp_contact_p50": pct([o["c2_hp_contact"][0] for o in op if o.get("c2_hp_contact")], (50,)),
        "gate_p50": pct([e.get("gate") for e in ok], (50,)),
    })
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", action="append", required=True)
    ap.add_argument("--arms", default="")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--base", default="")
    a = ap.parse_args(argv)
    arms = set(filter(None, a.arms.split(",")))
    E = defaultdict(list)
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
                E[arm].append({"ep": f"{run.name}_e{row.get('episode')}", "arm": arm, "outcome": "HARNESS_FAIL",
                               "kill_s": None, "fight_s": 0.0, "first_kill_s": None, "landed": 0,
                               "hp_hits_before_kill": 0, "hp_lost_before_kill": 0, "hits": [], "moves": {},
                               "stack_share": 0.0, "between_share": 0.0, "near8_share": 0.0})
                continue
            E[arm].append(episode(arm, inst, run, row, dec))
    out = {arm: summarize(v) for arm, v in E.items()}
    for arm, v in out.items():
        print(arm)
        for k, x in v.items():
            if k not in ("hits_by_state",):
                print(f"  {k}: {x}")
        for e in E[arm]:
            if e.get("outcome") == "HARNESS_FAIL":
                print(f"  {e['ep']:28s} HARNESS_FAIL")
                continue
            print(f"  {e['ep']:28s} {e['outcome']:6s} kills {e['kills_n']} fight {e['fight_s']} landed {e['landed']} "
                  f"both/s {e.get('landed_per_s_both')} hp-hits {e['hp_hits_before_kill']} gate {e.get('gate')} "
                  f"open {e.get('opening')}")
    if a.base and a.base in E:
        ok = lambda v: [x for x in v if x.get("outcome") != "HARNESS_FAIL"]                       # noqa: E731
        both = lambda v: sum(x.get("landed_both", 0) for x in v) / max(sum(x.get("both_s", 0) for x in v), 1e-9)  # noqa
        pooled = lambda v: sum(x["landed"] for x in v) / max(sum(x["fight_s"] for x in v), 1e-9)  # noqa: E731
        hpm = lambda v: sum(x["hp_hits_before_kill"] for x in v) / max(sum(x["fight_s"] for x in v) / 60.0, 1e-9)  # noqa
        kills = lambda v: sum(x.get("kills_n", 0) for x in v) / max(len(v), 1)                  # noqa: E731
        surv = lambda v: float(np.median([x["fight_s"] for x in v]))                             # noqa: E731
        for arm in E:
            if arm == a.base:
                continue
            b, c = ok(E[a.base]), ok(E[arm])
            print(f"{arm} - {a.base}: landed/s both alive", sp7_two.boot(b, c, both),
                  "| landed/s", sp7_two.boot(b, c, pooled), "| HP hits/min", sp7_two.boot(b, c, hpm),
                  "| kills/episode", sp7_two.boot(b, c, kills), "| survival p50", sp7_two.boot(b, c, surv))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps({"arms": out, "episodes": E}, indent=1, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
