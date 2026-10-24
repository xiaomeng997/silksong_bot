"""Map v2 stage M4 G: THE PERSON'S GATE on w7 (HANDOFF 'Task map2 - stage M4' / 'G'): the per-episode check the gate
driver runs after every live episode (the stop rule), the gate report and the trace of a problem. Offline: it reads a
run's logs and its recording, it never touches a game instance.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.m4_gate check --run <run dir> --inst N [--exit <code>] [--map2]
        [--log <check.jsonl>]                                   exit 0: every episode passed, 2: a problem
    ../scripts/uv.cmd run python -m ssbot.tools.m4_gate baseline --manifest <file> [--manifest ...] --out <json>
    ../scripts/uv.cmd run python -m ssbot.tools.m4_gate report --manifest <file> --out <dir>
    ../scripts/uv.cmd run python -m ssbot.tools.m4_gate trace --run <run dir> --inst N --ep K --frame F [--span 90]

THE WIN (the person's rule of 2026-10-22): the Clapper killed with no HP lost. As every 1v1 summary since task 1v1 the
fight ends at the kill: hits after it (the TAIL - wave 8's members arriving before its start ends the episode, e.g. a
Throwing Bell; 12 of 60 recent default w7 episodes) are reported apart, not counted against the Clapper's kill.
A PROBLEM (the stop rule): no kill / a timeout / a harness failure / the worker's non-zero exit / a traceback in the
worker log / HP lost before the kill / map2 errors (its stats) / map2 not running (no per-tick log) with --map2 / her
behaviour beyond every default-planner episode of the baseline by a margin: the longest span she stood still while
engaged (STILL_F), the most left / right key reversals in a second (FLICKER_REV), the kill time (KILL_S), and map2's
owner switches in a second (OWN_SW).
THE SHARE (M4d2's measure, m4c_smoke.engaged_share): the per-tick log's engaged ticks (a Clapper observed, not the
intro / her Roar Lock / a pause) in which a map2 plan chose the keys; pooled = the sums over the episodes.
THE MOVES (the recognizers on the logs: the recording's own hit events on the Clapper, each credited to whoever sent
the keys of its press - the per-tick log's owner of that frame's keys): strike = a down slash landed, hook = a
Clawline landed (one per press), ride = >= 2 down slashes landed in one Jump / Air flight of the Clapper (P4), slam
strike = a down slash landed on it in Slam 0 / Slam 1 or Slam Antic j >= 44, CLAWSTRIKE = a hook pressed at Slam Antic
j 4 - 12 and a slam strike on it after; side = any other landed nail hit; the Clawline presses by owner and into a
slam's first window (m4c_smoke.claw_presses).
"""
from __future__ import annotations

import argparse
import bisect
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

CLAPPER = "Song Heavy Sentry"
DS_SRC = frozenset(("DownSlash", "DownSlash New", "DownSlashAlt"))
CLAW_SRC = frozenset(("Harpoon Damager", "Harpoon Dash Damager"))
INTRO = frozenset(("Init", "Notify", "Drop In", "Drop Antic", "Enter Land", "Roar", "Roar End", "Z Set",
                   "Start Battle?", "Dormant", "Fly In Ready", "Wait", "Idle Start"))
FLIGHT = frozenset(("Jump", "Air"))
B_ATTACK, B_LEFT, B_RIGHT = 1 << 1, 1 << 20, 1 << 21
M_CLAW = 1 << 4
STILL_TOL = 0.3            # u: 'still' = her centre within this of the span's first frame
# the misbehaviour bars (calibrated on the default planner's recent live w7 episodes: `baseline`, HANDOFF 'G')
STILL_F = 240              # frames she stands still while engaged
FLICKER_REV = 12           # left / right key reversals within 60 frames
KILL_S = 40.0              # in-game seconds to the kill
OWN_SW = 16                # map2 <-> fallback owner switches within 60 frames


def _attempts(run: Path, inst: int) -> list[dict]:
    p = run / f"attempts_i{inst}.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text("utf-8").splitlines() if x.strip()]


def _map2_rows(run: Path, inst: int) -> dict[int, list[dict]]:
    p = run / f"map2_i{inst}.jsonl"
    out: dict = defaultdict(list)
    if not p.exists():
        return out
    for x in p.read_text("utf-8").splitlines():
        if not x.strip():
            continue
        r = json.loads(x)
        if "f" in r:
            out[int(r.get("ep") or 0)].append(r)
    return out


def _frames(row: dict) -> list[dict]:
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.forum_remaining_hits import compact_frames, fsm_timeline
    rd = RecordingReader(row["recording"])
    return compact_frames(rd.states(row["f_wake"], row["f_end"]), fsm_timeline(rd, row["f_wake"], row["f_end"]))


def _clapper(x: dict):
    """The (first) Clapper of a frame: (iid, x, y, state, j) or None."""
    for e in x["ents"]:
        if e[1] == CLAPPER and (e[9] is None or float(e[9]) > 0):
            j = None if e[7] is None else int(round(float(e[7]) * 60.0))
            return (e[0], e[2], e[3], e[6], j)
    return None


def _centre(b):
    return (0.5 * (b[0] + b[2]), 0.5 * (b[1] + b[3])) if b else None


def behaviour(fr: list[dict], f_kill: int | None) -> dict:
    """Her behaviour while engaged (the Clapper out of its intro, before the kill): the longest still span (frames), the
    most left / right key reversals within 60 frames (and where)."""
    eng = []
    started = False
    for x in fr:
        if f_kill is not None and x["f"] > f_kill:
            break
        c = _clapper(x)
        if c is None:
            continue
        if not started and c[3] not in INTRO and c[3] is not None:
            started = True
        if started and x.get("clip") != "Roar Lock":
            eng.append(x)
    still, still_at, cur0, cur_n, cur_f = 0, None, None, 0, None
    for x in eng:
        p = _centre(x["box"])
        if p is None:
            continue
        if cur0 is not None and abs(p[0] - cur0[0]) <= STILL_TOL and abs(p[1] - cur0[1]) <= STILL_TOL:
            cur_n = x["f"] - cur_f
        else:
            cur0, cur_f, cur_n = p, x["f"], 0
        if cur_n > still:
            still, still_at = cur_n, cur_f
    revs, last = [], 0
    for x in eng:
        a = x["act"]
        d = -1 if (a & B_LEFT and not a & B_RIGHT) else 1 if (a & B_RIGHT and not a & B_LEFT) else 0
        if d:
            if last and d != last:
                revs.append(x["f"])
            last = d
    rmax, rat = 0, None
    for i, f in enumerate(revs):
        k = bisect.bisect_right(revs, f + 59) - i
        if k > rmax:
            rmax, rat = k, f
    return {"engaged_f": len(eng), "still_f": still, "still_at": still_at, "lr_rev_60": rmax, "lr_rev_at": rat}


def owner_at(rows: list[dict]):
    """frame -> who sent that frame's keys (a tick at f sends f + 2; a skipped tick's frame keeps the last ACTION)."""
    fs = [int(r["f"]) + 2 for r in rows]
    own = [str(r.get("own")) for r in rows]

    def at(f: int) -> str | None:
        k = bisect.bisect_right(fs, int(f)) - 1
        return own[k] if k >= 0 else None
    return at


def _press_before(fr: list[dict], i: int, bit: int, back: int) -> int | None:
    """The frame of the last rising edge of `bit` in the sent keys at or before fr[i] (within back frames)."""
    f0 = fr[i]["f"] - back
    for k in range(i, 0, -1):
        if fr[k]["f"] < f0:
            break
        if (fr[k]["act"] & bit) and not (fr[k - 1]["act"] & bit):
            return fr[k]["f"]
    return None


def moves(fr: list[dict], rows: list[dict], f_kill: int | None) -> dict:
    """The recognizers on the logs (module doc): landed hits on the Clapper by kind, each credited to the owner of its
    press's keys (no per-tick log: 'fallback')."""
    at = owner_at(rows) if rows else (lambda f: None)
    by_f = {x["f"]: i for i, x in enumerate(fr)}
    hits = []
    seen_claw = set()
    for i, x in enumerate(fr):
        for k, d in x["ev"]:
            if k != "hit" or d.get("type_key") != CLAPPER:
                continue
            dealt = d.get("dealt", d.get("amount"))
            if dealt is not None and float(dealt) <= 0:
                continue
            src = str(d.get("src"))
            c = _clapper(fr[i - 1] if i > 0 else x) or _clapper(x)
            if src in CLAW_SRC:
                fp = _press_before(fr, i, M_CLAW, 90)
                if fp in seen_claw:
                    continue
                seen_claw.add(fp)
                kind = "hook"
            elif src in DS_SRC:
                fp = _press_before(fr, i, B_ATTACK, 30)
                kind = "strike"
            else:
                fp = _press_before(fr, i, B_ATTACK, 30)
                kind = "side" if src in ("Slash", "AltSlash", "UpSlash", "WallSlash") else "other:" + src
            own = at(fp) if fp is not None else at(x["f"])
            pst = None
            if fp is not None and fp in by_f:
                pc = _clapper(fr[by_f[fp]])
                pst = None if pc is None else (pc[3], pc[4])
            hits.append({"f": x["f"], "kind": kind, "src": src, "press": fp, "own": own or "fallback",
                         "st": None if c is None else c[3], "j": None if c is None else c[4], "press_st": pst,
                         "after_kill": f_kill is not None and x["f"] > f_kill})
    # rides: >= 2 strikes in one flight (consecutive strikes whose Clapper states stay in Jump / Air)
    rides = []
    cur = []
    for h in hits:
        if h["kind"] == "strike" and h["st"] in FLIGHT:
            if cur and h["f"] - cur[-1]["f"] > 90:
                if len(cur) >= 2:
                    rides.append(cur)
                cur = []
            cur.append(h)
        elif h["kind"] == "strike":
            if len(cur) >= 2:
                rides.append(cur)
            cur = []
    if len(cur) >= 2:
        rides.append(cur)
    slam = [h for h in hits if h["kind"] == "strike" and (h["st"] in ("Slam 0", "Slam 1") or
                                                          (h["st"] == "Slam Antic" and (h["j"] or 0) >= 44))]
    cstrikes = []
    for h in hits:
        if h["kind"] == "hook" and h["press_st"] and h["press_st"][0] == "Slam Antic" and \
                h["press_st"][1] is not None and 4 <= h["press_st"][1] <= 12:
            s = next((q for q in slam if 0 < q["f"] - h["f"] <= 120), None)
            if s is not None:
                cstrikes.append((h, s))

    def by_own(lst, key=lambda q: q["own"]):
        c = Counter()
        for q in lst:
            c["m2" if key(q) == "m2" else "fallback"] += 1
        return dict(c)
    return {"hits": hits,
            "strike": by_own([h for h in hits if h["kind"] == "strike"]),
            "hook": by_own([h for h in hits if h["kind"] == "hook"]),
            "side": by_own([h for h in hits if h["kind"] == "side"]),
            "ride": by_own(rides, key=lambda r: "m2" if all(q["own"] == "m2" for q in r) else "fallback"),
            "slam_strike": by_own(slam),
            "clawstrike": by_own(cstrikes, key=lambda p: "m2" if p[0]["own"] == "m2" else "fallback")}


def owner_switches(rows: list[dict]) -> tuple[int, int | None]:
    sw = []
    prev = None
    for r in rows:
        m = bool(r.get("m2"))
        if prev is not None and m != prev:
            sw.append(int(r["f"]))
        prev = m
    best, at = 0, None
    for i, f in enumerate(sw):
        k = bisect.bisect_right(sw, f + 59) - i
        if k > best:
            best, at = k, f
    return best, at


def map2_episode(rows: list[dict]) -> dict:
    from ssbot.tools.m4c_smoke import claw_presses, engaged_share
    own = Counter(str(r.get("own")) for r in rows)
    commits = [r["commit"] for r in rows if r.get("commit")]
    ends = Counter()
    cur = None
    for r in rows:
        if r.get("commit"):
            cur = r["commit"]["pid"]
        elif cur is not None and not (r.get("m2") and r.get("pid") == cur):
            ends[str(r.get("why"))] += 1
            cur = None
    sw, sw_at = owner_switches(rows)
    chk = Counter(c[2] for r in rows for c in r.get("chk") or ())
    return {"rows": len(rows), **engaged_share(rows), "claw": claw_presses(rows), "own": dict(own.most_common()),
            "commits": len(commits), "commit_steps": Counter(str(s) for c in commits for s in (c.get("steps") or ())),
            "plan_end": dict(ends.most_common()), "checks": dict(chk.most_common(8)),
            "own_sw_60": sw, "own_sw_at": sw_at, "late": sum(1 for r in rows if r.get("late")),
            "audit": [r["audit"] for r in rows if r.get("audit")][:20],
            "bot_ms_p99": float(np.percentile([r.get("ms") or 0 for r in rows], 99)) if rows else None}


def episode(run: Path, inst: int, row: dict, m2rows: list[dict] | None, with_frames: bool = True) -> dict:
    hp = int(row.get("hp_lost") or 0)
    tail = int(row.get("tail_hp_lost") or 0)
    e = {"run": run.name, "inst": inst, "ep": int(row["episode"]), "seed": row.get("seed"),
         "code_rev": row.get("code_rev"), "outcome": row.get("outcome"), "reason": row.get("reason"),
         "f_wake": row.get("f_wake"), "f_kill": row.get("f_kill"), "kill_s": row.get("kill_s"),
         "ingame_s": row.get("ingame_s"), "hp_lost": hp, "tail_hp_lost": tail, "hp_before_kill": hp - tail,
         "hit_sources": row.get("hit_sources"), "late_states": row.get("late_states"),
         "loop_gap_ms_max": row.get("loop_gap_ms_max"), "recording": row.get("recording")}
    pol = row.get("policy") or {}
    m = pol.get("map2")
    if m:
        e["map2_errors"] = len(m.get("errors") or [])
        e["map2_first_errors"] = (m.get("errors") or [])[:3]
        e["map2_counts"] = m.get("counts")
        e["map2_share_stats"] = m.get("share_m2")
    e["forced_risk_ticks"] = pol.get("forced_risk_ticks")
    e["ticks"] = pol.get("ticks")
    e["late_ticks"] = pol.get("late_ticks")
    if m2rows is not None:
        e["map2"] = map2_episode(m2rows)
    if with_frames and row.get("recording") and row.get("f_wake") is not None:
        try:
            fr = _frames(row)
            e["beh"] = behaviour(fr, row.get("f_kill"))
            e["moves"] = moves(fr, m2rows or [], row.get("f_kill"))
        except Exception as ex:  # noqa: BLE001 - a broken recording is a problem in itself
            e["frames_error"] = repr(ex)[:300]
    e["hp_drops"] = hp_drops(run, inst, int(row["episode"]))
    return e


def hp_drops(run: Path, inst: int, ep: int) -> list:
    """Her HP losses from the decision log (its rows are kept around every hit): (frame, hp before, hp after)."""
    p = run / f"decisions_i{inst}.jsonl"
    if not p.exists():
        return []
    out, prev = [], None
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            if int(r.get("ep") or 0) != ep or r.get("hp") is None:
                continue
            hp = int(r["hp"])
            if prev is not None and hp < prev:
                out.append((int(r["f"]), prev, hp))
            prev = hp
    return out


def problems(e: dict, need_map2: bool, exit_code: int | None = None) -> list[str]:
    p = []
    if exit_code not in (None, 0):
        p.append(f"exit {exit_code}")
    if e.get("outcome") != "CLEAR":
        p.append(f"outcome {e.get('outcome')} {e.get('reason') or ''}".strip())
    if e.get("f_kill") is None:
        p.append("no kill")
    if e.get("hp_before_kill", 0) > 0:
        p.append(f"HP lost before the kill: {e['hp_before_kill']}")
    if e.get("map2_errors"):
        p.append(f"map2 errors {e['map2_errors']}: {str(e.get('map2_first_errors'))[:200]}")
    if need_map2 and not (e.get("map2") or {}).get("rows"):
        p.append("map2 not running (no per-tick log rows)")
    if e.get("frames_error"):
        p.append("recording: " + e["frames_error"])
    b = e.get("beh") or {}
    if b.get("still_f", 0) > STILL_F:
        p.append(f"stood still {b['still_f']} f from {b.get('still_at')} (bar {STILL_F})")
    if b.get("lr_rev_60", 0) > FLICKER_REV:
        p.append(f"flicker: {b['lr_rev_60']} left/right reversals in 60 f from {b.get('lr_rev_at')} (bar {FLICKER_REV})")
    if e.get("kill_s") is not None and float(e["kill_s"]) > KILL_S:
        p.append(f"kill time {e['kill_s']} s (bar {KILL_S})")
    m = e.get("map2") or {}
    if m.get("own_sw_60", 0) > OWN_SW:
        p.append(f"owner flicker: {m['own_sw_60']} map2/fallback switches in 60 f from {m.get('own_sw_at')} "
                 f"(bar {OWN_SW})")
    return p


def cmd_check(a) -> int:
    run = Path(a.run)
    rows = _attempts(run, a.inst)
    m2 = _map2_rows(run, a.inst)
    wl = run / f"worker_i{a.inst}.log"
    tb = wl.read_text("utf-8", errors="ignore").count("Traceback") if wl.exists() else 0
    out = []
    bad = False
    if not rows:
        out.append({"run": run.name, "inst": a.inst, "problems": [f"no episode row (exit {a.exit})"]})
        bad = True
    for row in rows:
        e = episode(run, a.inst, row, m2.get(int(row["episode"])) if (a.map2 or m2) else None)
        pr = problems(e, a.map2, a.exit)
        if tb:
            pr.append(f"{tb} traceback(s) in {wl.name}")
        e["problems"] = pr
        bad |= bool(pr)
        out.append(e)
    if a.log:
        with open(a.log, "a", encoding="utf-8") as fh:
            for e in out:
                fh.write(json.dumps(e, default=str) + "\n")
    for e in out:
        mm = e.get("map2") or {}
        mv = e.get("moves") or {}
        print(f"{e.get('run')} i{e.get('inst')} ep{e.get('ep')}: {e.get('outcome')} kill {e.get('kill_s')} s "
              f"hp before kill {e.get('hp_before_kill')} tail {e.get('tail_hp_lost')} share "
              f"{mm.get('share_engaged')} ({mm.get('engaged_m2')} / {mm.get('engaged')}) strikes {mv.get('strike')} "
              f"hooks {mv.get('hook')} rides {mv.get('ride')} beh {e.get('beh')} PROBLEMS {e.get('problems')}",
              flush=True)
    return 2 if bad else 0


def _manifest(paths: list[str]) -> list[tuple[str, int, Path]]:
    out = []
    for p in paths:
        for line in Path(p).read_text("utf-8-sig").splitlines():
            q = line.strip().split("\t")
            if len(q) >= 4 and q[3]:
                out.append((q[0], int(q[2]), Path(q[3])))
    return out


def cmd_baseline(a) -> int:
    res = []
    for arm, inst, run in _manifest(a.manifest):
        for row in _attempts(run, inst):
            e = episode(run, inst, row, None)
            e["arm"] = arm
            e.pop("moves", None)
            res.append(e)
    keys = ("still_f", "lr_rev_60")
    summ = {k: _pct([(e.get("beh") or {}).get(k) for e in res]) for k in keys}
    summ["kill_s"] = _pct([e.get("kill_s") for e in res])
    summ["n"] = len(res)
    Path(a.out).write_text(json.dumps({"summary": summ, "episodes": res}, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summ))
    for e in sorted(res, key=lambda e: -(e.get("beh") or {}).get("still_f", 0))[:5]:
        print(e["run"], e["inst"], e["ep"], e.get("beh"))
    return 0


def _pct(v, qs=(50, 90, 100)):
    v = [float(x) for x in v if x is not None]
    return [round(float(np.percentile(v, q)), 2) for q in qs] if v else None


def cmd_report(a) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    eps = []
    for arm, inst, run in _manifest(a.manifest):
        m2 = _map2_rows(run, inst)
        for row in _attempts(run, inst):
            e = episode(run, inst, row, m2.get(int(row["episode"])) if m2 else None)
            e["arm"] = arm
            e["problems"] = problems(e, arm != "h2")
            eps.append(e)
    eng = sum((e.get("map2") or {}).get("engaged", 0) for e in eps)
    em2 = sum((e.get("map2") or {}).get("engaged_m2", 0) for e in eps)
    tot = Counter()
    for e in eps:
        for k in ("strike", "hook", "side", "ride", "slam_strike", "clawstrike"):
            for o, n in ((e.get("moves") or {}).get(k) or {}).items():
                tot[f"{k}:{o}"] += n
        for o, n in ((e.get("map2") or {}).get("claw") or {}).items():
            tot[f"claw_press:{o}"] += n
    res = {"episodes": eps, "n": len(eps),
           "kills": sum(1 for e in eps if e.get("f_kill") is not None),
           "hitless_kills": sum(1 for e in eps if e.get("f_kill") is not None and e.get("hp_before_kill") == 0
                                and e.get("outcome") == "CLEAR"),
           "tail_hits": sum(e.get("tail_hp_lost") or 0 for e in eps),
           "pooled_share": round(em2 / max(1, eng), 4), "engaged": eng, "engaged_m2": em2,
           "moves": dict(sorted(tot.items())), "problems": {f"i{e['inst']}e{e['ep']}": e["problems"]
                                                            for e in eps if e["problems"]}}
    (out / "report.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "episodes"}, default=str))
    for e in eps:
        mm = e.get("map2") or {}
        mv = e.get("moves") or {}
        print(f"{e['arm']} {e['run']} i{e['inst']} ep{e['ep']} {e.get('outcome')} kill {e.get('kill_s')} hp<kill "
              f"{e.get('hp_before_kill')} tail {e.get('tail_hp_lost')} share {mm.get('share_engaged')} "
              f"({mm.get('engaged_m2')}/{mm.get('engaged')}) strike {mv.get('strike')} hook {mv.get('hook')} ride "
              f"{mv.get('ride')} slam {mv.get('slam_strike')} cs {mv.get('clawstrike')} side {mv.get('side')} claw "
              f"{mm.get('claw')} beh {e.get('beh')} problems {e['problems']}")
    return 0


def cmd_trace(a) -> int:
    """The frames around a problem: her box / velocity / clip / keys, the Clapper's state / frame / position, who sent
    the keys and the per-tick log's map2 fields (the plan id, frames since its anchor, committed frames left, her
    observed - planned position dh, the Clappers' observed vs planned dc, the checks, the commit)."""
    run = Path(a.run)
    row = next(r for r in _attempts(run, a.inst) if int(r["episode"]) == a.ep)
    rows = _map2_rows(run, a.inst).get(a.ep, [])
    at = owner_at(rows) if rows else (lambda f: None)
    by_tick = {int(r["f"]): r for r in rows}
    fr = _frames(row)
    lo, hi = a.frame - a.span, a.frame + a.span // 3
    commits = {}
    for r in rows:
        if r.get("commit"):
            commits[r["commit"]["pid"]] = (int(r["f"]), r["commit"])
    shown = set()
    for x in fr:
        if not lo <= x["f"] <= hi:
            continue
        c = _clapper(x)
        p = _centre(x["box"])
        line = (f"f {x['f']} ({x['f'] - a.frame:+d}) her {None if p is None else (round(p[0], 2), round(p[1], 2))} "
                f"v ({x['vel'][0]:.2f},{x['vel'][1]:.2f}) clip {x.get('clip')} keys {x['act']:#x} own {at(x['f'])} "
                f"clapper {None if c is None else (c[3], c[4], round(c[1], 2), round(c[2], 2))}")
        ev = [(k, {kk: d.get(kk) for kk in ('src', 'type_key', 'dealt', 'amount', 'source') if kk in d})
              for k, d in x["ev"]]
        if ev:
            line += f" ev {ev}"
        r = by_tick.get(x["f"])
        if r is not None:
            keep = {k: r[k] for k in ("why", "pid", "n", "left", "pc", "dh", "dc", "busy", "trig", "chk", "late",
                                      "ended", "claw", "cp", "verdict") if k in r}
            line += f" | m2 {keep}"
            pid = r.get("pid")
            if pid and pid in commits and pid not in shown:
                shown.add(pid)
                cf, cm = commits[pid]
                line += f"\n    COMMIT {pid} at f {cf}: {json.dumps(cm, default=str)[:1500]}"
        print(line)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--run", required=True)
    c.add_argument("--inst", type=int, required=True)
    c.add_argument("--exit", type=int, default=None)
    c.add_argument("--map2", action="store_true", help="map2 must be running (its per-tick log)")
    c.add_argument("--log", default="")
    b = sub.add_parser("baseline")
    b.add_argument("--manifest", action="append", required=True)
    b.add_argument("--out", required=True)
    r = sub.add_parser("report")
    r.add_argument("--manifest", action="append", required=True)
    r.add_argument("--out", required=True)
    t = sub.add_parser("trace")
    t.add_argument("--run", required=True)
    t.add_argument("--inst", type=int, required=True)
    t.add_argument("--ep", type=int, required=True)
    t.add_argument("--frame", type=int, required=True)
    t.add_argument("--span", type=int, default=90)
    a = ap.parse_args(argv)
    return {"check": cmd_check, "baseline": cmd_baseline, "report": cmd_report, "trace": cmd_trace}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
