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
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    from ssbot.knowledge.kinematics import cstate_names
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.combat_run import load_attempts
    names = cstate_names()
    out = []
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
