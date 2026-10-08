"""Wave-0 attack instances and what the hero did about each, the bot's eval runs beside the person's demos (task
"wave-0 forensics", forum.md §19): the same situations, the two answers.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_attack_outcomes --bot C:/ssbot/data/runs/m2/<run> [...]
        --human C:/ssbot/data/human/<session>[@label] [...] [--cache <dir>] [--json out.json]

An attack instance: an enemy's control FSM entering a family start state (gauntlet_tables.FORUM_SPECS, the behaviour
tables' families) while wave 0 runs (room.battles "Battle Scene" wave 0, started, not completed). Its window ends at the
next family start or idle-family state of that enemy, at most WINDOW_S of game time. Per instance: the hero's offset
from the enemy at the start (dx toward the enemy's facing, dy), whether the hero was hit by that enemy (a damage event
whose source names its type) inside the window, and what the hero did in it: airborne at the start, the share of
frames airborne, a dash, a jump press, attack presses, the change of |dx| (away > 0), the least distance. Per family
and source (bot / human-1x / human-0.5x): instances with the hero within NEAR_U at the start, the share that hit, and
the response mix of the hit and the clean ones. Also per source: wave-0 time, hits per minute, kills.

The person's sessions are read with forum_demo.scan (state.raw.zst; --cache keeps the pass), the bot's recordings with
RecordingReader over each attempt row's f_wake .. f_end (an eval episode is wave 0 to its QUIT)."""
import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.knowledge.gauntlet_tables import FORUM_SPECS

WINDOW_S = 1.6
NEAR_U = 8.0
BATTLE = "Battle Scene"
TYPES = ("Song Pilgrim 01", "Song Pilgrim 03", "Song Reed")
SHORT = {"Song Pilgrim 01": "Envoy", "Song Pilgrim 03": "Choristor", "Song Reed": "Reed"}


def _spec_maps() -> dict:
    """{type: (start state -> family, decision states, flip mirror)} from FORUM_SPECS."""
    return {tk: (dict(FORUM_SPECS[tk].attack_starts), set(FORUM_SPECS[tk].decision_states),
                 tuple(FORUM_SPECS[tk].flip_mirror)) for tk in TYPES}


def frames_from_states(states) -> list[dict]:
    """Compact frames (the forum_demo scan's rows + live enemies + events) from STATE dicts."""
    from ssbot.tools.forum_demo import _main_state
    from ssbot.train.gauntlet import live_enemies
    out = []
    for m in states:
        h = m.get("hero") or {}
        b = next((x for x in (m.get("room") or {}).get("battles") or () if x.get("name") == BATTLE), None)
        pos = h.get("pos") or [None, None]
        live = []
        for e in live_enemies(m):
            st, _ = _main_state(e)
            live.append((e.get("iid"), e.get("type_key"), e["pos"][0], e["pos"][1], st, e.get("flipX")))
        evs = []
        for ev in m.get("ev") or ():
            if ev.get("k") in ("damage", "die"):
                evs.append((ev.get("k"), (ev.get("d") or {}).get("source")))
        out.append({"f": m["f"], "dt": float(m.get("udt") or m.get("dt") or 0.0) * float(m.get("ts") or 1.0)
                    if m.get("udt") is not None else float(m.get("dt") or 0.0),
                    "x": pos[0], "y": pos[1], "cs": h.get("cstate"), "mask": (m.get("input") or {}).get("mask"),
                    "act": (m.get("act") or {}).get("mask"),
                    "wave": (b.get("wave") if b and b.get("started") and not b.get("completed") else None),
                    "live": live, "ev": evs, "hp": h.get("health")})
    return out


def frames_from_scan(s: dict) -> list[dict]:
    """Compact frames from a forum_demo scan (the person's sessions)."""
    ev_by_f = defaultdict(list)
    for f, k, d in s["events"]:
        if k in ("damage", "die"):
            ev_by_f[f].append((k, (d or {}).get("source")))
    out = []
    for r, live in zip(s["rows"], s["ents"]):
        out.append({"f": r["f"], "dt": (r["udt"] or 0.0) * (r["ts"] if r["ts"] is not None else 1.0),
                    "x": r["x"], "y": r["y"], "cs": r["cs"], "mask": r["mask"], "act": None,
                    "wave": r["b_wave"] if r["b_started"] and not r["b_completed"] else None,
                    "live": [(e[0], e[1], e[2], e[3], e[5], e[7]) for e in live], "ev": ev_by_f.get(r["f"], []),
                    "hp": r["hp"]})
    return out


def _cs_flags(cs, idx: dict[str, int]) -> dict[str, bool]:
    from ssbot.tools.forum_demo import _flags
    return _flags(cs, idx) if cs is not None else {}


def instances(frames: list[dict], src: str, specs: dict) -> list[dict]:
    """The wave-0 attack instances of one attempt's frames (see the module doc)."""
    from ssbot.knowledge import kinematics as kin
    from ssbot.tools.forum_demo import _cs_index
    idx = _cs_index()
    out = []
    t = 0.0
    T = []
    for fr in frames:
        t += fr["dt"]
        T.append(t)
    prev_st: dict = {}
    open_: dict = {}
    w0 = [i for i, fr in enumerate(frames) if fr["wave"] == 0]
    if not w0:
        return out
    i_a, i_z = w0[0], w0[-1]
    for i in range(i_a, i_z + 1):
        fr = frames[i]
        for iid, tk, ex, ey, st, flip in fr["live"]:
            if tk not in specs:
                continue
            starts, idle, mirror = specs[tk]
            ps = prev_st.get(iid)
            prev_st[iid] = st
            if st == ps:
                continue
            o = open_.get(iid)
            fam = starts.get(st)
            if o is not None and (fam is not None or st in idle):
                o["i1"] = i
                out.append(o)
                open_.pop(iid)
            if fam is not None and not fam.endswith("_ENTRY") and not fam.endswith("_AMBUSH"):
                face = mirror[1 if flip else 0]
                open_[iid] = {"src": src, "type": tk, "family": fam, "iid": iid, "i0": i, "i1": None,
                              "face": face, "ex": ex, "ey": ey}
    for o in open_.values():
        out.append(o)
    res = []
    for o in out:
        i0 = o["i0"]
        t0 = T[i0]
        i1 = o["i1"] if o["i1"] is not None else i_z
        while i1 > i0 and T[i1] - t0 > WINDOW_S:
            i1 -= 1
        hx, hy = frames[i0]["x"], frames[i0]["y"]
        if hx is None or o["ex"] is None:
            continue
        dx = (hx - o["ex"]) * o["face"]          # > 0: the hero in front of the enemy
        dy = hy - o["ey"]
        hit_t = None
        air = 0
        dash = jump = att = False
        dmin = math.inf
        ed = None
        for j in range(i0, i1 + 1):
            fr = frames[j]
            fl = _cs_flags(fr["cs"], idx)
            air += int(not fl.get("onGround", True))
            dash |= fl.get("dashing", False)
            m = fr["mask"] if fr["mask"] is not None else (fr["act"] or 0)
            pm = (frames[j - 1]["mask"] if frames[j - 1]["mask"] is not None else (frames[j - 1]["act"] or 0)) \
                if j > 0 else 0
            jump |= bool(m & kin.B_JUMP and not pm & kin.B_JUMP)
            att |= bool(m & kin.B_ATTACK and not pm & kin.B_ATTACK)
            e = next((x for x in fr["live"] if x[0] == o["iid"]), None)
            if e is not None and fr["x"] is not None:
                d = math.hypot(fr["x"] - e[2], fr["y"] - e[3])
                dmin = min(dmin, d)
                ed = abs(fr["x"] - e[2])
            for k, s_ in fr["ev"]:
                if k == "damage" and hit_t is None and s_ and SHORT_TYPES(s_) == o["type"]:
                    hit_t = T[j] - t0
        fl0 = _cs_flags(frames[i0]["cs"], idx)
        res.append({"src": o["src"], "type": o["type"], "family": o["family"], "t": round(t0 - T[i_a], 2),
                    "dx": round(dx, 2), "dy": round(dy, 2), "d0": round(math.hypot(dx, dy), 2),
                    "hit": hit_t is not None, "hit_t": None if hit_t is None else round(hit_t, 2),
                    "air0": not fl0.get("onGround", True), "air_share": round(air / max(i1 - i0 + 1, 1), 2),
                    "dash": dash, "jump": jump, "attack": att,
                    "away": None if ed is None else round(ed - abs(hx - o["ex"]), 2),
                    "dmin": None if dmin == math.inf else round(dmin, 2), "dur": round(T[i1] - t0, 2)})
    return res


def SHORT_TYPES(path: str) -> str | None:
    from ssbot.tools.forum_a0_report import type_of
    return type_of(path, None)


def wave0_stats(frames: list[dict]) -> dict:
    """Wave-0 game time, hits (damage events), whether it was completed."""
    t = 0.0
    hits = 0
    w0 = False
    done = False
    for fr in frames:
        if fr["wave"] == 0:
            w0 = True
            t += fr["dt"]
            hits += sum(1 for k, _ in fr["ev"] if k == "damage")
        elif w0 and fr["wave"] is not None and fr["wave"] > 0:
            done = True
            break
    return {"t": t, "hits": hits, "done": done}


def bot_attempts(run: Path):
    from ssbot.record.recorder import RecordingReader
    for p in sorted(run.glob("attempts_i*.jsonl")):
        for x in p.read_text("utf-8").splitlines():
            if not x.strip():
                continue
            r = json.loads(x)
            if r.get("outcome") == "HARNESS_FAIL" or not r.get("recording"):
                continue
            rd = RecordingReader(r["recording"])
            yield frames_from_states(rd.states(r["f_wake"], r["f_end"]))


def human_attempts(session: Path, cache: Path | None):
    from ssbot.tools.forum_demo import attempts, load
    s = load(session, cache)
    frames = frames_from_scan(s)
    fi = {fr["f"]: i for i, fr in enumerate(frames)}
    for a in attempts(s):
        i0, i1 = fi.get(a["f0"]), fi.get(a["f1"])
        if i0 is None or i1 is None:
            continue
        yield frames[i0:i1 + 1]


def summarise(inst: list[dict], w0: dict) -> dict:
    out = {"wave0": {}, "families": {}}
    for src, v in w0.items():
        t = sum(x["t"] for x in v)
        out["wave0"][src] = {"attempts": len(v), "completed": sum(x["done"] for x in v), "game_s": round(t, 1),
                             "hits": sum(x["hits"] for x in v),
                             "hits_per_min": round(60 * sum(x["hits"] for x in v) / max(t, 1e-9), 2),
                             "median_s": round(float(np.median([x["t"] for x in v])), 2) if v else None}
    by = defaultdict(list)
    for x in inst:
        if x["d0"] <= NEAR_U:
            by[(x["family"], x["src"])].append(x)
    for (fam, src), xs in sorted(by.items()):
        hit = [x for x in xs if x["hit"]]
        ok = [x for x in xs if not x["hit"]]

        def mix(v):
            if not v:
                return None
            return {"n": len(v), "air0": round(np.mean([x["air0"] for x in v]), 2),
                    "air_share": round(float(np.mean([x["air_share"] for x in v])), 2),
                    "dash": round(np.mean([x["dash"] for x in v]), 2), "jump": round(np.mean([x["jump"] for x in v]), 2),
                    "attack": round(np.mean([x["attack"] for x in v]), 2),
                    "away_p50": round(float(np.median([x["away"] for x in v if x["away"] is not None] or [0])), 2),
                    "front": round(np.mean([x["dx"] > 0 for x in v]), 2),
                    "d0_p50": round(float(np.median([x["d0"] for x in v])), 2)}
        out["families"].setdefault(fam, {})[src] = {"n": len(xs), "hit_share": round(len(hit) / len(xs), 3),
                                                    "hit": mix(hit), "clean": mix(ok)}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bot", nargs="*", type=Path, default=[])
    ap.add_argument("--human", nargs="*", default=[], help="session dir[@label] (label default: human)")
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    specs = _spec_maps()
    inst, w0 = [], defaultdict(list)
    for run in a.bot:
        for frames in bot_attempts(run):
            inst += instances(frames, "bot", specs)
            w0["bot"].append(wave0_stats(frames))
    for h in a.human:
        path, _, label = h.partition("@")
        label = label or "human"
        for frames in human_attempts(Path(path), a.cache):
            st = wave0_stats(frames)
            if st["t"] <= 0:
                continue
            inst += instances(frames, label, specs)
            w0[label].append(st)
    out = summarise(inst, w0)
    js = json.dumps(out, indent=1, default=str)
    if a.json:
        a.json.write_text(json.dumps({"summary": out, "instances": inst}, default=str), "utf-8")
    print(js)
    return 0


if __name__ == "__main__":
    sys.exit(main())
