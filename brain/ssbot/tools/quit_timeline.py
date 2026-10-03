"""Quit timelines (M2 W5 / W7; DESIGN §3.7.3-3.7.5, §3.5.6): for every QUIT episode of eval runs, what happened
between the hit and the pause, so a quit can be told apart from a heal that was possible.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.quit_timeline C:/ssbot/data/runs/m2/<run> [<run> ...]
        [--replay] [--instance N] [--episode N] [--json out.json]

Per QUIT episode (attempts_i<N>.jsonl outcome QUIT; hits from the recording's "damage" events, not policy.hits_taken,
which misses hits on STATEs the live loop skipped as late: 7 of 26 QUITs of run 20261002_152649 had hits_taken []):
  hits      frame, HP / silk after it, and its phases from STATE: hit-stop end (ts back to 1), first pausable frame
            (pause.blk 0; probe P7: 250 ms after an enemy hit), recoil end (tm.recoil 0), control back (hero_state not
            NO_INPUT and control not relinquished), i-frames end (tm.inv 0)
  trigger   the first PAUSE_PENDING tick (policy.first_pending_f) and its reasons, frames since the hit, the hero's
            control state there (free / freeze / recoil / locked:<clip>), the boss state, the plan and how many
            FORCED_RISK ticks led up to it (decisions_i<N>.jsonl logs every FORCED_RISK tick)
  pause     the first pause press at or after the trigger (STATE act.mask bit "pause"), the first paused frame
            (game.paused), and whether the gate was open at the trigger
  silk      at the hit and the most silk between the hit and the pause (the Bind needs 9, supervisor.BIND_SILK)
With --replay the episode's recording drives a fresh PlannerPolicy open loop (ssbot.tools.postmortem: the planner is
deterministic given the STATEs, so the replayed decisions match the live ones unless a live tick ran late), and for
every tick from the hit to the pause it records:
  bind      the tactics' commit test at the hero's position (Forecast.t_min >= T_BIND_S + DELTA_B_S = 1.52 s, silk >= 9,
            HP <= max - playbook bind.hp_missing_min, the decision's allowlist; supervisor.bind_allowed) and the
            planner's own Bind rollout (Planner._bind: the 100-frame macro outside the support and the hazards); a
            verified window is a tick where both pass with the hero in control, within 2 s of the hit and before the
            pause
  clear     at FORCED_RISK ticks, how long the best allowed candidate stays out of the support (the latest first contact
            over the allowed, non-Hz candidates, from the planner's own tick: Planner.tick's locals at return) and how
            long the chosen plan does; FORCED_RISK within the design horizon (DESIGN §3.5.4, H = 0.8 s) means the best
            candidate meets the support within it. The adaptive horizon (playbook long_horizon, up to 2 s through a
            committed charge) makes FORCED_RISK an open-loop statement about the whole charge, which the closed loop
            usually escapes: at h >= 3, 2266 of 3006 FORCED_RISK streaks of the gate and live runs (20261002_123347 ...
            152649) began in Charge Emerge and 13 of them (0.6 %) were followed by a hit within 3 s.
The summary counts the triggers by kind and the episodes with a verified Bind window.
"""
import argparse
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

from ssbot.tools.postmortem import episode_rows, find_recording

PAUSE_BIT = 14                  # ssbot.ipc.framing.BUTTONS index of "pause"
HS_NO_INPUT = 7                 # HeroController.ActorStates.no_input
H_DESIGN_F = 48                 # DESIGN §3.5.4 H = 0.8 s at 60 fps
BIND_WINDOW_F = 120             # "a verified Bind window in the 2 s after the hit"
STATE_KEYS = ("f", "ev", "hero", "act", "game", "pause", "ts")


def control(s: dict) -> str:
    """The hero's control at one STATE: freeze (hit-stop, ts < 1), recoil (hurt, no input), locked:<clip> (a committed
    lock: Bind, cast, down-slash antic), no_input:<clip>, or free."""
    h = s.get("hero") or {}
    ts = s.get("ts")
    clip = (h.get("anim") or {}).get("clip")
    if ts is not None and ts < 0.999:
        return "freeze"
    tm = h.get("tm") or {}
    if h.get("hero_state") == HS_NO_INPUT and (tm.get("recoil") or 0) > 0:
        return "recoil"
    if h.get("control_relinquished"):
        return f"locked:{clip}"
    if h.get("hero_state") == HS_NO_INPUT:
        return f"no_input:{clip}"
    return "free"


def _first(states: list[dict], f0: int, pred) -> int | None:
    return next((s["f"] for s in states if s["f"] >= f0 and pred(s)), None)


def hit_phases(states: list[dict], fh: int) -> dict:
    """Frames after the hit at fh when the hit-stop ends, the pause gate opens, the recoil ends, control returns and the
    i-frames end (None: not within the recorded frames)."""
    rel = (lambda f: None if f is None else f - fh)  # noqa: E731
    tm = (lambda s: (s.get("hero") or {}).get("tm") or {})  # noqa: E731
    after = [s for s in states if s["f"] > fh]
    return {"freeze_end": rel(_first(after, fh, lambda s: (s.get("ts") or 0) >= 0.999)),
            "pausable": rel(_first(after, fh, lambda s: not (s.get("pause") or {}).get("blk"))),
            "recoil_end": rel(_first(after, fh, lambda s: not (tm(s).get("recoil") or 0))),
            "control": rel(_first(after, fh, lambda s: control(s) == "free")),
            "inv_end": rel(_first(after, fh, lambda s: not (tm(s).get("inv") or 0)))}


def decisions(run: Path, instance: int) -> dict[int, dict[int, dict]]:
    out: dict[int, dict[int, dict]] = {}
    p = run / f"decisions_i{instance}.jsonl"
    if p.is_file():
        for line in p.read_text("utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out.setdefault(r["ep"], {})[r["f"]] = r
    return out


def timeline(row: dict, states: list[dict], dec: dict[int, dict]) -> dict:
    """The episode's timeline from its attempts row, its recorded STATEs and its decision log rows (by frame)."""
    pol = row.get("policy") or {}
    by_f = {s["f"]: s for s in states}
    fp = pol.get("first_pending_f")
    hits = []
    for s in states:
        if any(e.get("k") == "damage" for e in s.get("ev") or ()):
            h = s.get("hero") or {}
            hits.append({"f": s["f"], "hp": h.get("health"), "silk": h.get("silk"), **hit_phases(states, s["f"])})
    before = [x for x in hits if fp is None or x["f"] <= fp]
    hit = before[-1] if before else None
    press = paused = None
    if fp is not None:
        press = _first(states, fp, lambda s: ((s.get("act") or {}).get("mask") or 0) & (1 << PAUSE_BIT))
        paused = _first(states, fp, lambda s: (s.get("game") or {}).get("paused"))
    streak, f = 0, fp
    while f is not None and f in dec and dec[f].get("forced"):
        streak, f = streak + 1, f - 1
    d0 = dec.get(fp, {}) if fp is not None else {}
    s0 = by_f.get(fp, {}) if fp is not None else {}
    end = paused or row["f_end"]
    silk_max = max(((s.get("hero") or {}).get("silk") or 0 for s in states
                    if hit is not None and hit["f"] <= s["f"] <= end), default=None)
    reasons = pol.get("first_pending_reasons") or []
    return {
        "outcome_reason": pol.get("outcome_reason") or row.get("reason"),
        "real_quit": bool((pol.get("real_quit") or {}).get("armed")),
        "hits": hits, "hit_f": None if hit is None else hit["f"],
        "trigger": None if fp is None else {
            "f": fp, "after_hit": None if hit is None else fp - hit["f"], "reasons": reasons,
            "ids": sorted({r.split(":", 1)[0] for r in reasons}),
            "control": control(s0) if s0 else None, "boss_state": d0.get("boss_state"), "plan": d0.get("plan"),
            "n_ok": d0.get("n_ok"), "n_safe": d0.get("n_safe"), "h": d0.get("h"), "hero": d0.get("hero"),
            "forced_streak": streak, "pausable": None if not s0 else not (s0.get("pause") or {}).get("blk")},
        "pause": {"press": press, "paused": paused,
                  "press_after_trigger": None if press is None or fp is None else press - fp,
                  "paused_after_trigger": None if paused is None or fp is None else paused - fp},
        "silk_at_hit": None if hit is None else hit["silk"], "silk_max": silk_max,
        "forced_ticks_after_hit": sorted(f for f, r in dec.items() if r.get("forced") and hit is not None
                                         and hit["f"] <= f <= (fp or row["f_end"])),
    }


# ---- replay -------------------------------------------------------------------------------------------------------

class _TickTap:
    """Captures Planner.tick's locals at its return (sys.setprofile on this thread, only while armed): the planner is
    read, never changed (ssbot/combat/planner.py belongs to the planner's owner)."""

    NAMES = ("ws", "start", "hold", "prefix", "f", "ctx", "t_hit", "ok", "hz", "S", "P", "T", "forced")

    def __init__(self, planner):
        self.code = type(planner).tick.__code__
        self.last: dict | None = None

    def __call__(self, frame, event, arg):
        if event == "return" and frame.f_code is self.code:
            loc = frame.f_locals
            self.last = {k: loc.get(k) for k in self.NAMES}

    def arm(self) -> None:
        self.last = None
        sys.setprofile(self)

    @staticmethod
    def disarm() -> None:
        sys.setprofile(None)


def replay(row: dict, rec_path: Path, tl: dict, threads: int = 2, pol=None, live_prefix: bool = True) -> dict:
    """Open-loop PlannerPolicy replay of one episode; per tick from the hit to the pause the Bind tests and, at
    FORCED_RISK ticks, how long the best and the chosen candidate stay clear of the support. live_prefix: the
    planner's prefix is the live masks (else the replay's own, as ssbot.tools.postmortem)."""
    import numpy as np

    from ssbot.core.primitives import Prim
    from ssbot.knowledge.kinematics import Terrain2D
    from ssbot.record.recorder import RecordingReader
    from ssbot.safety.supervisor import DELTA_B_S, T_BIND_S, bind_allowed
    from ssbot.train.encounters import BELL_BEAST
    from ssbot.train.planner_policy import PlannerPolicy

    pol = pol or PlannerPolicy(view=(row.get("policy") or {}).get("view", "oracle"), threads=threads)
    r = RecordingReader(rec_path)
    for _, m in r.terrain():
        if m.get("scene_raw") == BELL_BEAST.scene:
            pol.terrain = Terrain2D.from_message(m, pol.params.scene(BELL_BEAST.scene))

    class Tap:
        wake_frame = row.get("f_wake")
    start = row["f_end"] - row["acts"]
    pol.reset(random.Random(row["seed"]), BELL_BEAST)
    fh = tl["hit_f"]
    end = tl["pause"]["paused"] or row["f_end"]
    tap = _TickTap(pol.planner)
    ticks = []
    t_need = T_BIND_S + DELTA_B_S
    it = r.states(start, end + 1)
    nxt = next(it, None)
    while nxt is not None and nxt["f"] < end:
        s, nxt = nxt, next(it, None)
        f = s["f"]
        # the planner's prefix is what was sent for the frames after the WorldState's: the live masks (STATE act.mask
        # of the next frame, sent two frames earlier), not the replay's own choices, which drift from the live ones
        if live_prefix and nxt is not None and nxt["f"] == f + 1 and (nxt.get("act") or {}).get("mask") is not None:
            pol.sent[f + 1] = int(nxt["act"]["mask"])
        watch = fh is not None and fh <= f < end
        if watch:
            tap.arm()
        try:
            pol.act(s, Tap)
        finally:
            if watch:
                tap.disarm()
        if not watch or tap.last is None or pol.planner_last is None:
            continue
        L = tap.last
        res, ws, fc = pol.planner_last, L["ws"], L["f"]
        d = pol.decision
        hero = ws.hero.pos.v
        silk, hp, hpm = ws.res.silk.v, ws.res.hp.v, ws.res.hp_max.v
        t_min = fc.t_min(hero[0], hero[1], t_max=2.0)
        commit = bind_allowed(int(silk or 0), int(hp or 0), int(hpm or 0), int(d.h if d is not None and d.h is not None
                                                                              else 1), t_min)
        rollout_ok = bool(pol.planner._bind(ws, L["start"], L["hold"], L["prefix"], fc, L["ctx"])[0])
        tactics_ok = (silk is not None and silk >= 9 and hp is not None and hpm
                      and hp <= hpm - pol.pb.bind_hp_missing_min and (d is None or d.allows(Prim.BIND)))
        item = {"f": f, "control": control(s), "silk": silk, "hp": hp, "h": None if d is None else d.h,
                "t_min": None if math.isinf(t_min) else round(t_min, 3), "t_min_ok": t_min >= t_need,
                "commit_ok": commit.ok, "commit_why": commit.reason, "bind_rollout_ok": rollout_ok,
                "tactics_ok": bool(tactics_ok), "want_bind": res.name == "BIND", "forced": bool(res.forced_risk),
                "pending": bool(d is not None and d.pause_pending),
                "triggers": [] if d is None else [x for x in d.reasons if x[:2] in ("Q1", "Q2", "Q3", "Q6")]}
        if res.forced_risk and L["t_hit"] is not None:
            ok, hz, t_hit, P = np.asarray(L["ok"]), np.asarray(L["hz"]), np.asarray(L["t_hit"]), int(L["P"])
            cand = ok & ~hz
            best = int(t_hit[cand].max()) if cand.any() else 0
            item.update(clear_best_f=best - P, clear_chosen_f=int(t_hit[res.idx]) - P if 0 <= res.idx < len(t_hit)
                        else None, horizon_f=int(L["T"]), within_h=best - P <= H_DESIGN_F,
                        clear_glue_f=getattr(pol, "last_clear_f", None))
        ticks.append(item)
    out = summarize_replay(tl, ticks)
    out["prefix"] = "live" if live_prefix else "replay"
    return out


def summarize_replay(tl: dict, ticks: list[dict]) -> dict:
    fh = tl["hit_f"]
    fp = (tl["trigger"] or {}).get("f")
    win = [t for t in ticks if fh is not None and t["f"] - fh <= BIND_WINDOW_F]

    def verified(t):
        return t["control"] == "free" and t["tactics_ok"] and t["commit_ok"] and t["bind_rollout_ok"]
    trig = next((t for t in ticks if t["f"] == fp), None)
    if fp is not None and (trig is None or not trig["forced"]):
        # the replay's ticks are the live ones only up to drift (a live tick that ran late, the planner's own state):
        # the nearest FORCED_RISK tick within 5 frames stands in
        near = [t for t in ticks if t["forced"] and abs(t["f"] - fp) <= 5]
        trig = min(near, key=lambda t: abs(t["f"] - fp)) if near else trig
    old = next((t for t in ticks if t["forced"] and t["h"] is not None and t["h"] <= 2), None)
    new = next((t for t in ticks if t["pending"]), None)
    return {
        "ticks": len(ticks),
        "old_q6_f": None if old is None else old["f"],          # the first tick the old rule (any FORCED_RISK) fires
        "new_pending_f": None if new is None else new["f"],    # the replayed supervisor's (this code's) first pending
        "new_reasons": None if new is None else new["triggers"],
        "bind_window_2s": next((t["f"] - fh for t in win if verified(t)), None),
        "bind_window_any": next((t["f"] - fh for t in ticks if verified(t)), None),
        "t_min_ok_2s": sum(t["t_min_ok"] for t in win), "rollout_ok_2s": sum(t["bind_rollout_ok"] for t in win),
        "space_ok_2s": sum(t["t_min_ok"] and t["bind_rollout_ok"] and t["control"] == "free" for t in win),
        "space_ok_any": sum(t["t_min_ok"] and t["bind_rollout_ok"] and t["control"] == "free" for t in ticks),
        "silk9": sum((t["silk"] or 0) >= 9 for t in ticks), "bound": any(t["want_bind"] for t in ticks),
        "trigger_tick": trig,
        "forced_ticks": [{k: t.get(k) for k in ("f", "control", "clear_best_f", "clear_chosen_f", "horizon_f",
                                                  "within_h", "clear_glue_f", "h")} for t in ticks if t["forced"]],
    }


# ---- summary ------------------------------------------------------------------------------------------------------

def kind(item: dict) -> str:
    """Why the attempt ended, in one word: q6_long (FORCED_RISK only beyond the design horizon), q6_h (within it),
    q6_locked (the hero in a committed lock), q6 (not replayed), or the trigger ids."""
    t = item["timeline"]["trigger"] or {}
    ids = t.get("ids") or []
    if ids != ["Q6"]:
        return "+".join(ids) or "none"
    ctl = t.get("control") or ""
    if ctl != "free":
        return "q6_" + ctl.split(":")[0]
    tt = (item.get("replay") or {}).get("trigger_tick")
    if not tt or "within_h" not in tt:
        return "q6"
    return "q6_h" if tt["within_h"] else "q6_long"


def summary(items: list[dict]) -> dict:
    c = Counter(kind(x) for x in items)
    tls = [x["timeline"] for x in items]
    late = [t["trigger"]["after_hit"] for t in tls if t["trigger"] and t["trigger"]["after_hit"] is not None]
    lat = Counter(t["pause"]["paused_after_trigger"] for t in tls)
    rp = [x["replay"] for x in items if x.get("replay")]
    return {"episodes": len(items), "kinds": dict(c),
            "trigger_after_hit_frames": {"min": min(late, default=None), "max": max(late, default=None),
                                         "le_15": sum(v <= 15 for v in late)},
            "paused_after_trigger_frames": dict(lat),
            "silk9_after_hit": sum((t["silk_max"] or 0) >= 9 for t in tls),
            "replayed": len(rp),
            "new_rule_pending_before_the_live_pause": sum(r["new_pending_f"] is not None for r in rp),
            "new_rule_no_quit_before_the_live_pause": sum(r["new_pending_f"] is None for r in rp),
            "bind_window_2s": sum(r["bind_window_2s"] is not None for r in rp),
            "bind_window_any": sum(r["bind_window_any"] is not None for r in rp),
            "space_for_bind_2s": sum(r["space_ok_2s"] > 0 for r in rp)}


def quit_items(runs: list[Path], instance: int | None = None, episode: int | None = None):
    """(run, instance, episode, row, recording path) of every QUIT episode."""
    for run in runs:
        for p in sorted(run.glob("attempts_i*.jsonl")):
            inst = int(p.stem.rsplit("i", 1)[1])
            if instance is not None and inst != instance:
                continue
            for ep, row in enumerate(episode_rows(run, inst)):
                if row.get("outcome") == "QUIT" and (episode is None or ep == episode) and row.get("recording"):
                    yield run, inst, ep, row, find_recording(run, row)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--replay", action="store_true", help="open-loop PlannerPolicy replay: Bind windows, clearance")
    ap.add_argument("--instance", type=int, default=None)
    ap.add_argument("--episode", type=int, default=None)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)

    from ssbot.record.recorder import RecordingReader
    items, pol, decs = [], None, {}
    for run, inst, ep, row, rec in quit_items(a.runs, a.instance, a.episode):
        if (run, inst) not in decs:
            decs[(run, inst)] = decisions(run, inst)
        start = row["f_end"] - row["acts"]
        states = list(RecordingReader(rec).states(start, row["f_end"] + 1, keys=STATE_KEYS))
        tl = timeline(row, states, decs[(run, inst)].get(ep, {}))
        item = {"run": run.name, "instance": inst, "episode": ep, "timeline": tl}
        if a.replay and tl["hit_f"] is not None:
            if pol is None:
                from ssbot.train.planner_policy import PlannerPolicy
                pol = PlannerPolicy(view=(row.get("policy") or {}).get("view", "oracle"), threads=a.threads)
            item["replay"] = replay(row, rec, tl, pol=pol)
            if "clear_best_f" not in (item["replay"].get("trigger_tick") or {}) and tl["trigger"]:
                # the live trigger tick not reproduced (drift): once more with the replay's own prefix
                alt = replay(row, rec, tl, pol=pol, live_prefix=False)
                if "clear_best_f" in (alt.get("trigger_tick") or {}):
                    item["replay"] = alt
        items.append(item)
        t, p = tl["trigger"] or {}, tl["pause"]
        rp = item.get("replay") or {}
        tt = rp.get("trigger_tick") or {}
        print(f"{run.name[:15]} i{inst} ep{ep:<3d} {kind(item):10s} hit {tl['hit_f']} silk {tl['silk_at_hit']}->"
              f"{tl['silk_max']} trigger +{t.get('after_hit')} {t.get('control')} {t.get('boss_state')} "
              f"streak {t.get('forced_streak')} | press +{p['press_after_trigger']} paused +{p['paused_after_trigger']}"
              + (f" | clear best {tt.get('clear_best_f')} chosen {tt.get('clear_chosen_f')} glue "
                 f"{tt.get('clear_glue_f')} | old q6 {rp.get('old_q6_f')} new pending {rp.get('new_pending_f')} | "
                 f"bind 2s {rp.get('bind_window_2s')} any {rp.get('bind_window_any')} "
                 f"space {rp.get('space_ok_2s')}/{rp.get('space_ok_any')} silk9 {rp.get('silk9')}" if rp else ""),
              flush=True)
    s = summary(items)
    print(json.dumps(s, indent=1))
    if a.json:
        a.json.write_text(json.dumps({"summary": s, "items": items}, indent=1, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
