"""Low-HP check (Q1 / Q1a, DESIGN §3.7.4, the person's rule of 2026-10-03; M2 W5): per episode of a combat_run run with
injected hits that leave h = 1 or 2 (ssbot.train.hit_injection, SSBOT_INJECT_LEAVE_HP), what the bot did after the
hit, measured from the recordings:

    cd brain
    $env:SSBOT_INJECT_LEAVE_HP="1,2,3"; $env:SSBOT_INJECT_MIN_SILK="9"
    ../scripts/uv.cmd run python -m ssbot.tools.combat_run run --instances 4 --encounter BellBeast --mode eval
        --policy planner --view oracle --inject-hits 1.0 --start-silk 9 9 --silk-reserve --threads 4 --seed 105000
    ../scripts/uv.cmd run python -m ssbot.tools.lowhp_check C:/ssbot/data/runs/m2/<run> [--json out.json]

Per trial (the injected hit: the first "damage" event at or after the injector's send frame):
  hit         frame, HP after it, h after it against the Bell Beast's 2-mask hits (1-2 HP: h 1; 3-4: h 2)
  window      G, the gate's opening (first frame with pause.blk 0 after the hit; a press pauses from G + 1,
              pause_quit constants) and the i-frames' end (hero.tm.inv 0, else hero.invulnerable false), frames after
              the hit
  quit        the supervisor's first PAUSE_PENDING frame (policy.first_pending_f) and its reasons, the first paused
              frame (game.paused); latency from the hit (frames, real s from STATE q) and from G ("after_opening": 1 is
              the first pausable frame); "inside": G < the pause, the hero still invulnerable on it (tm.inv > 0,
              inv_left_at_pause s; the paused game freezes the i-frames' clock, so their end is not recorded)
  bind        the first Bind after the hit (cstate isBinding onset), whether it completed (health up while binding or
              on its last frame) and whether a hit landed while binding (a damage event; the would-be-hit check)
  outcome     the attempt's outcome and reason
  ramp999     the freeze's shape: the STATE before G was the ramp's last shut frame (blk 3, ts >= 0.999); the oracle
              then pauses on G + 1, otherwise on G + 2 (every injected hit so far had it: G = +15)
  silk        silk at the hit and the first frame after it with silk >= 9 (Q1a's gathering at h 2)
  second      a later hit taking h 2 to h 1 (a natural hit: Q6 no longer quits at h 2, DESIGN §3.7.4 Q6 of
              2026-10-03), its post-hit window as above and the frames from it to PAUSE_PENDING
--q1 (any run): every episode whose first PAUSE_PENDING was a Q1, its hit (the last damage to <= 2 HP before it),
injected or natural, and its post-hit window, summarised by view, hit source and ramp999.
Summary per target h: trials, quits / pauses and their latency, inside share, binds started / completed / hit,
outcomes; the expected rule: h 1 -> quit in the post-hit window, never a Bind; h 2 -> heal first (a Bind when the
commit test passes), no quit from the hit itself.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from ssbot.tools.postmortem import find_recording

STATE_KEYS = ("f", "q", "ev", "hero", "game", "pause", "ts")
QPC = 1e7
WORST = 2            # Bell Beast: every hit 2 masks


def h_after(hp: int, worst: int = WORST) -> int:
    """hits_to_death for a hero at hp against `worst`-mask hits, no blue, no mask (the supervisor's own recurrence)."""
    n = 0
    while True:
        n += 1
        if hp - worst >= 1:
            hp -= worst
            continue
        return n


def _tm(s: dict) -> dict:
    t = (s.get("hero") or {}).get("tm")
    return t if isinstance(t, dict) else {}


def window(states: list[dict], fh: int) -> dict:
    """The post-hit window of the hit at frame fh, from the recording: G (the first STATE with pause.blk 0 after it),
    ramp999 (the STATE before G was the freeze ramp's last shut frame: blk 3 with ts >= 0.999, the shape where the
    oracle presses one frame early and pauses on G + 1; without it the observed gate puts the pause on G + 2;
    pause_quit.hit_ramp_open_at), the first paused frame and how far after G it came, the i-frames left on it.
    Frames are counted from the hit."""
    by_f = {s["f"]: s for s in states}
    hit = by_f.get(fh) or {}
    after = [s for s in states if s["f"] > fh]
    opening = next((s for s in after if (s.get("pause") or {}).get("blk") == 0), None)
    prev = None if opening is None else by_f.get(opening["f"] - 1)
    ramp999 = None if prev is None else ((prev.get("pause") or {}).get("blk") == 3 and (prev.get("ts") or 0) >= 0.999)
    paused = next((s for s in after if (s.get("game") or {}).get("paused")), None)
    inv_end = next((s for s in after if (_tm(s).get("inv") is not None and not _tm(s)["inv"] > 0)
                    or (_tm(s).get("inv") is None and (s.get("hero") or {}).get("invulnerable") is False)), None)
    rel = (lambda s: None if s is None else s["f"] - fh)
    return {"opening": rel(opening), "ramp999": ramp999, "paused": rel(paused),
            "paused_s": None if paused is None else round(((paused.get("q") or 0) - (hit.get("q") or 0)) / QPC, 4),
            "after_opening": None if paused is None or opening is None else paused["f"] - opening["f"],
            "inside": None if paused is None or opening is None else
            opening["f"] < paused["f"] and (inv_end is None or paused["f"] < inv_end["f"])
            and (_tm(paused).get("inv") is None or _tm(paused)["inv"] > 0),
            "inv_left_at_pause": None if paused is None or _tm(paused).get("inv") is None
            else round(float(_tm(paused)["inv"]), 3)}


def q1_pause(row: dict, states: list[dict]) -> dict | None:
    """Any run (--q1): the episode's Q1 quit after a hit, measured in the post-hit window (window()), and whether that
    hit was the injector's (sent at most 4 frames before it) or the boss's own (natural): the oracle's press timing
    depends on the freeze's shape (ramp999), which the injected hits did not vary (every one in 20261003_111244 ...
    122030 had G = +15 after a 0.999 frame; fixer review 2026-10-03)."""
    pol = row.get("policy") or {}
    pend = pol.get("first_pending_f")
    reasons = pol.get("first_pending_reasons") or []
    if pend is None or not any(r.startswith("Q1") for r in reasons):
        return None
    cause = "hit" if any(r.startswith("Q1") and "post-hit" in r for r in reasons) else \
        "no_hit" if any(r.startswith("Q1") and "no hit" in r for r in reasons) else "unlabelled"
    hits = [s for s in states if s["f"] <= pend and any(e.get("k") == "damage" for e in s.get("ev") or ())
            and ((s.get("hero") or {}).get("health") or 9) <= 2]
    out = {"pending_reasons": reasons[:3], "cause": cause, "outcome": row.get("outcome")}
    if not hits:
        out["hit_f"] = None
        return out
    fh = hits[-1]["f"]
    sent = [x["f"] for x in ((pol.get("inject") or {}).get("sent") or ())]
    out.update(hit_f=fh, pending=pend - fh,
               source="injected" if any(0 <= fh - x <= 4 for x in sent) else "natural",
               kind=(pol.get("inject") or {}).get("kind"), **window(states, fh))
    return out


def summarize_q1(items: list[dict]) -> dict:
    """Per view, hit source and freeze shape: the Q1 pauses' frame after G, the share inside the window, latency."""
    out: dict = {}
    for x in items:
        if x.get("hit_f") is None:
            out.setdefault("no_hit_or_unmatched", Counter())[f"{x.get('view')} {x.get('cause')}"] += 1
            continue
        key = f"{x.get('view')} {x.get('source')} ramp999={x.get('ramp999')}"
        o = out.setdefault(key, {"n": 0, "paused": 0, "after_opening": Counter(), "opening": Counter(), "inside": 0,
                                 "paused_s": [], "pending": Counter()})
        o["n"] += 1
        o["opening"][x.get("opening")] += 1
        o["pending"][x.get("pending")] += 1
        if x.get("paused") is not None:
            o["paused"] += 1
            o["after_opening"][x.get("after_opening")] += 1
            o["inside"] += bool(x.get("inside"))
            o["paused_s"].append(x.get("paused_s"))
    for k, o in out.items():
        if isinstance(o, dict):
            ps = [v for v in o.pop("paused_s") if v is not None]
            o["paused_s"] = {"min": min(ps), "max": max(ps)} if ps else None
            for c in ("after_opening", "opening", "pending"):
                o[c] = dict(sorted(o[c].items(), key=lambda kv: (kv[0] is None, kv[0] or 0)))
        else:
            out[k] = dict(o)
    return out


def trial(row: dict, states: list[dict], names: list[str]) -> dict | None:
    from ssbot.tools.pause_stress import _cs
    pol = row.get("policy") or {}
    inj = pol.get("inject") or {}
    sent = [x["f"] for x in inj.get("sent") or ()]
    if not sent:
        return None
    f_sent = sent[0]
    hit = next((s for s in states if s["f"] >= f_sent and any(e.get("k") == "damage" for e in s.get("ev") or ())),
               None)
    out = {"target_hp": inj.get("target_hp"), "kind": inj.get("kind"), "sent_f": f_sent,
           "outcome": row.get("outcome"), "reason": (row.get("reason") or "")[:120]}
    if hit is None:
        out["took"] = False
        return out
    fh = hit["f"]
    after = [s for s in states if s["f"] > fh]
    hp1 = next(((s.get("hero") or {}).get("health") for s in [hit] + after[:3]
                if (s.get("hero") or {}).get("health") is not None), None)
    q0 = hit.get("q") or 0

    def first(pred, src=after):
        return next((s for s in src if pred(s)), None)

    def rel(s):
        return None if s is None else s["f"] - fh

    def tm(s):
        t = (s.get("hero") or {}).get("tm")
        return t if isinstance(t, dict) else {}
    opening = first(lambda s: (s.get("pause") or {}).get("blk") == 0)
    inv_end = first(lambda s: (tm(s).get("inv") is not None and not tm(s)["inv"] > 0)
                    or (tm(s).get("inv") is None and (s.get("hero") or {}).get("invulnerable") is False))
    paused = first(lambda s: (s.get("game") or {}).get("paused"))
    pend = pol.get("first_pending_f")
    bind0 = first(lambda s: _cs(names, s).get("isBinding"))
    bind = None
    if bind0 is not None:
        during = [s for s in after if s["f"] >= bind0["f"]]
        end = next((s for s in during if not _cs(names, s).get("isBinding")), None)
        seg = [s for s in during if end is None or s["f"] <= end["f"]]
        hps = [(s.get("hero") or {}).get("health") for s in seg if (s.get("hero") or {}).get("health") is not None]
        hit_in = [s["f"] - fh for s in seg if any(e.get("k") == "damage" for e in s.get("ev") or ())]
        bind = {"start": bind0["f"] - fh, "end": rel(end), "hp_before": hps[0] if hps else None,
                "hp_after": hps[-1] if hps else None, "completed": bool(hps and max(hps) > hps[0]),
                "hit_during": hit_in}
    out.update(took=True, hit_f=fh, hp_after=hp1, h_after=None if hp1 is None else h_after(int(hp1)),
               opening=rel(opening), inv_end=rel(inv_end), pending=None if pend is None else pend - fh,
               pending_reasons=pol.get("first_pending_reasons"), paused=rel(paused),
               paused_s=None if paused is None else round(((paused.get("q") or 0) - q0) / QPC, 4),
               after_opening=None if paused is None or opening is None else paused["f"] - opening["f"],
               inside=None if paused is None or opening is None else
               opening["f"] < paused["f"] and (inv_end is None or paused["f"] < inv_end["f"])
               and (tm(paused).get("inv") is None or tm(paused)["inv"] > 0),
               inv_left_at_pause=None if paused is None or tm(paused).get("inv") is None
               else round(float(tm(paused)["inv"]), 3),
               bind=bind, later_hits=[s["f"] - fh for s in after if any(e.get("k") == "damage"
                                                                         for e in s.get("ev") or ())][:5])
    out["ramp999"] = window(states, fh)["ramp999"]
    # silk after the hit (Q1a's gathering: DESIGN §3.7.4 Q6, the person's rule of 2026-10-03, fights on at h 2)
    silk = [((s.get("hero") or {}).get("silk"), s["f"] - fh) for s in [hit] + after]
    out["silk_at_hit"] = silk[0][0]
    out["silk9_f"] = next((df for v, df in silk if v is not None and v >= 9), None)
    # the second hit, which takes h 2 to h 1 (no Q6 at h 2 any more): Q1 in its post-hit window, a natural hit
    sec = next((s for s in after if any(e.get("k") == "damage" for e in s.get("ev") or ())
                and ((s.get("hero") or {}).get("health") or 9) <= 2 and (hp1 or 0) > 2), None)
    if sec is not None:
        out["second"] = {"f": sec["f"] - fh, "pending": None if pend is None else pend - sec["f"],
                         "bound_before": bool(bind and bind["start"] < sec["f"] - fh), **window(states, sec["f"])}
    return out


def _pct(v: list, p: float):
    v = sorted(x for x in v if x is not None)
    return v[min(len(v) - 1, int(p / 100.0 * len(v)))] if v else None


def summarize(trials: list[dict]) -> dict:
    out: dict = {"trials": len(trials), "took": sum(bool(t.get("took")) for t in trials)}
    by_h: dict = {}
    for t in trials:
        if not t.get("took"):
            continue
        by_h.setdefault(t["h_after"], []).append(t)
    for h, ts in sorted(by_h.items(), key=lambda kv: (kv[0] is None, kv[0])):
        pz = [t for t in ts if t.get("paused") is not None]
        binds = [t["bind"] for t in ts if t.get("bind")]
        out[f"h{h}"] = {
            "trials": len(ts), "hp_after": dict(Counter(t["hp_after"] for t in ts)),
            "paused": len(pz), "pending_frames_after_hit": dict(Counter(t["pending"] for t in ts)),
            "paused_frames_after_hit": {"min": _pct([t["paused"] for t in pz], 0),
                                        "p50": _pct([t["paused"] for t in pz], 50),
                                        "max": _pct([t["paused"] for t in pz], 100)},
            "paused_s_after_hit": {"min": _pct([t["paused_s"] for t in pz], 0),
                                   "p50": _pct([t["paused_s"] for t in pz], 50),
                                   "max": _pct([t["paused_s"] for t in pz], 100)},
            "paused_after_opening": dict(Counter(t["after_opening"] for t in pz)),
            "inside_window": sum(bool(t["inside"]) for t in pz),
            "inv_left_at_pause_s": {"min": _pct([t.get("inv_left_at_pause") for t in pz], 0),
                                    "max": _pct([t.get("inv_left_at_pause") for t in pz], 100)},
            "opening_frames": dict(Counter(t["opening"] for t in ts)),
            "inv_end_frames": {"min": _pct([t["inv_end"] for t in ts], 0), "max": _pct([t["inv_end"] for t in ts], 100)},
            "binds_started": len(binds), "binds_completed": sum(b["completed"] for b in binds),
            "binds_hit": sum(bool(b["hit_during"]) for b in binds),
            "bind_start_frames_after_hit": sorted(b["start"] for b in binds),
            "outcomes": dict(Counter(t["outcome"] for t in ts)),
            "reasons": dict(Counter((t.get("reason") or "")[:60] for t in ts if t.get("reason")).most_common(6)),
            "ramp999": dict(Counter(t.get("ramp999") for t in ts)),
            "paused_after_opening_by_ramp999": {str(r): dict(Counter(t["after_opening"] for t in pz
                                                                     if t.get("ramp999") == r))
                                                for r in (True, False, None)},
            "silk_at_hit": dict(Counter(t.get("silk_at_hit") for t in ts)),
            "silk9_frames_after_hit": sorted(t["silk9_f"] for t in ts if t.get("silk9_f") is not None),
        }
        sec = [t["second"] for t in ts if t.get("second")]
        if sec:
            spz = [x for x in sec if x.get("paused") is not None]
            out[f"h{h}"]["second_hit"] = {
                "n": len(sec), "after_a_bind": sum(x["bound_before"] for x in sec),
                "pending_frames_after": dict(Counter(x.get("pending") for x in sec)),
                "paused": len(spz), "inside_window": sum(bool(x.get("inside")) for x in spz),
                "paused_after_opening_by_ramp999": {str(r): dict(Counter(x["after_opening"] for x in spz
                                                                         if x.get("ramp999") == r))
                                                    for r in (True, False, None)},
                "opening_frames": dict(Counter(x.get("opening") for x in sec)),
                "paused_s": {"min": _pct([x.get("paused_s") for x in spz], 0),
                             "max": _pct([x.get("paused_s") for x in spz], 100)},
                "inv_left_at_pause_s": {"min": _pct([x.get("inv_left_at_pause") for x in spz], 0),
                                        "max": _pct([x.get("inv_left_at_pause") for x in spz], 100)}}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--q1", action="store_true",
                    help="any run: every Q1 quit after a hit in its post-hit window, by hit source and freeze shape")
    a = ap.parse_args(argv)
    from ssbot.knowledge.kinematics import cstate_names
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.combat_run import load_attempts
    names = cstate_names()
    out = []
    if a.q1:
        for run in a.runs:
            for row in load_attempts(run):
                pol = row.get("policy") or {}
                if not row.get("recording") or row.get("f_end") is None or pol.get("first_pending_f") is None:
                    continue
                if not any(r.startswith("Q1") for r in pol.get("first_pending_reasons") or ()):
                    continue
                start = max(row["f_end"] - row["acts"] - (row.get("late_states") or 0), pol["first_pending_f"] - 600)
                states = list(RecordingReader(find_recording(run, row)).states(start, row["f_end"] + 30,
                                                                               keys=STATE_KEYS))
                x = q1_pause(row, states)
                if x is None:
                    continue
                x.update(run=run.name, instance=row.get("instance"), episode=row.get("episode"), view=pol.get("view"))
                out.append(x)
                if not a.quiet:
                    print(json.dumps({k: x.get(k) for k in ("run", "episode", "view", "cause", "source", "kind",
                                                            "pending", "opening", "ramp999", "paused",
                                                            "after_opening", "inside", "inv_left_at_pause")}),
                          flush=True)
        s = summarize_q1(out)
        print(json.dumps(s, indent=1, default=str))
        if a.json:
            a.json.write_text(json.dumps({"summary": s, "items": out}, indent=1, default=str), "utf-8")
        return 0
    for run in a.runs:
        for row in load_attempts(run):
            if not row.get("recording") or not (row.get("policy") or {}).get("inject"):
                continue
            start = row["f_end"] - row["acts"] - (row.get("late_states") or 0)
            states = list(RecordingReader(find_recording(run, row)).states(start, row["f_end"] + 30, keys=STATE_KEYS))
            t = trial(row, states, names)
            if t is None:
                continue
            t.update(run=run.name, instance=row.get("instance"), episode=row.get("episode"),
                     view=(row.get("policy") or {}).get("view"))
            out.append(t)
            if not a.quiet:
                print(json.dumps({k: t.get(k) for k in ("view", "episode", "target_hp", "took", "hp_after", "h_after",
                                                        "opening", "inv_end", "pending", "paused", "paused_s",
                                                        "after_opening", "inside", "bind", "outcome", "reason")}),
                      flush=True)
    s = summarize(out)
    print(json.dumps(s, indent=1))
    if a.json:
        a.json.write_text(json.dumps({"summary": s, "trials": out}, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
