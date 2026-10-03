"""Pause stress test summary (DESIGN §3.7.5 G1 fault injection; M2 W5): one trial per episode of a combat_run run with
--inject-hits (ssbot.train.hit_injection: one hit per episode through hurt.special, HP down to 1, so the supervisor's
Q1 must pause and, with --real-quit 1.0, quit to the main menu), measured from the run's recordings.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.launcher -n 4 --detach
    ../scripts/uv.cmd run python -m ssbot.tools.combat_run run --instances 0,1,2,3 --encounter BellBeast --mode eval
        --policy planner --view oracle --real-quit 1.0 --inject-hits --episodes 50 --seed 80000
    ../scripts/uv.cmd run python -m ssbot.tools.pause_stress C:/ssbot/data/runs/m2/<run> [--json out.json]

Per trial (the injected hit = the hurt.special reply that the game took, take_health_calls > 0):
  moment     the injection kind and its planned offset; at the hit frame the hero's state (airborne, vy, clip) and the
             nearest special moments within +-10 frames: kill (BossDeathSlow freeze or the boss's death state), stun
             (BossStun freeze), bounce (downSpikeBouncing onset), clash (parrying onset, or a nail recoil with no hit
             or damage within 2 frames: a tink off an object without health, the Bell Beast's bells); "special" when
             one is within +-3 frames (G1: >= 30 % of the injections)
  latency    first pausable frame after the hit (STATE pause.blk 0), the supervisor's first PAUSE_PENDING frame, the
             first paused frame (game.paused); latency = paused - first pausable, in frames (G1: p99.9 <= 6)
  keys       while paused, frames on which the game saw (STATE act.hf.latched) a key other than the menu keys the
             quit sequence presses (up, down, enter), and such keys newly pressed on a paused frame (edges): the
             planner's keys must never reach the menu. The oracle's HoldFilter replays every queued edge, so a planner
             tap whose press it deferred (min release) can still be latched after the switch to the pause keys: in
             the 37 gate / live QUITs (20261002_123347 ... 152649) a movement key was latched 1-2 frames into the
             pause in 9 and newly pressed on the pause frame itself in 4, never later, never jump / attack; the menu
             takes no input for 8-9 frames after the pause. The Pause key's own frames after the pause (the in-flight
             press, within the 230 ms budget)
  unpauses   paused -> running transitions before the quit reached the main menu (must be 0); the machine's own
             count (real_quit.unexpected_unpauses) and its wrong Submits (real_quit.wrong_submits, must be 0)
  menu       time from the pause to the main menu (frames and seconds, STATE q)
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from ssbot.tools.postmortem import find_recording

KEYS = ("jump", "attack", "dash", "bind", "clawline", "needolin", "quickcast", "taunt", "inventory", "map", "tools",
        "journal", "quests", "quickmap", "pause", "enter", "paneleft", "paneright", "up", "down", "left", "right")
BIT = {k: 1 << i for i, k in enumerate(KEYS)}          # ssbot.ipc.framing.BUTTONS order (tests check it)
MENU_KEYS = BIT["up"] | BIT["down"] | BIT["enter"]
GS_MAIN_MENU = 1
SPECIAL_WINDOW = 3
STATE_KEYS = ("f", "q", "ev", "hero", "act", "game", "pause", "ts")


def _cs(names: list[str], s: dict) -> dict[str, bool]:
    from ssbot.tools.cstate import decode
    w = (s.get("hero") or {}).get("cstate")
    try:
        return decode(w, names) if w else {}
    except ValueError:
        return {}


def moments(states: list[dict], names: list[str], death_states: tuple[str, ...] = ("Death Broadcast",)) -> dict:
    """Frames of the special moments in a stretch of STATEs: kill, stun, bounce, clash; plus hits dealt."""
    out: dict[str, list[int]] = {"kill": [], "stun": [], "bounce": [], "clash": [], "hit": []}
    prev: dict[str, bool] = {}
    hits, dmg, recoil_on = set(), set(), []
    for s in states:
        f = s["f"]
        for ev in s.get("ev") or ():
            k, d = ev.get("k"), ev.get("d") or {}
            if k == "freeze" and d.get("type") == "BossDeathSlow" and d.get("reason") is None:
                out["kill"].append(f)
            elif k == "freeze" and d.get("type") == "BossStun" and d.get("reason") is None:
                out["stun"].append(f)
            elif k == "fsm" and d.get("to") in death_states:
                out["kill"].append(f)
            elif k == "hit":
                hits.add(f)
            elif k == "damage":
                dmg.add(f)
        cs = _cs(names, s)
        for name, key in (("downSpikeBouncing", "bounce"), ("parrying", "clash")):
            if cs.get(name) and not prev.get(name):
                out[key].append(f)
        rec = cs.get("recoilingLeft") or cs.get("recoilingRight")
        if rec and not (prev.get("recoilingLeft") or prev.get("recoilingRight")) and not cs.get("recoilFrozen"):
            recoil_on.append(f)
        prev = cs
    for f in recoil_on:
        if not any(abs(f - g) <= 2 for g in hits | dmg):
            out["clash"].append(f)
    out["hit"] = sorted(hits)
    return {k: sorted(set(v)) for k, v in out.items()}


def trial(row: dict, states: list[dict], names: list[str]) -> dict | None:
    pol = row.get("policy") or {}
    inj = pol.get("inject")
    if not inj:
        return None
    took = [r for r in inj.get("replies") or () if isinstance(r, dict) and r.get("take_health_calls")
            and r.get("hp_after", 9) < r.get("hp_before", 0)]
    out = {"kind": inj.get("kind"), "offset": inj.get("offset"), "fallback": inj.get("fallback"),
           "sent": len(inj.get("sent") or ()), "took": bool(took), "outcome": row.get("outcome"),
           "reason": row.get("reason")}
    if not took:
        return out
    by_f = {s["f"]: s for s in states}
    fh = took[-1]["frame"]
    dmg = [s["f"] for s in states if fh - 1 <= s["f"] <= fh + 3 and any(e.get("k") == "damage"
                                                                         for e in s.get("ev") or ())]
    fh = dmg[0] if dmg else fh
    s0 = by_f.get(fh) or {}
    h = s0.get("hero") or {}
    near = moments([s for s in states if fh - 12 <= s["f"] <= fh + 12], names)
    off = {k: min((f - fh for f in v), key=abs) for k, v in near.items() if v}
    special = {k: v for k, v in off.items() if k != "hit" and abs(v) <= SPECIAL_WINDOW}
    after = [s for s in states if s["f"] >= fh]
    pausable = next((s["f"] for s in after if not (s.get("pause") or {}).get("blk")
                     and not (s.get("game") or {}).get("paused")), None)
    paused = next((s["f"] for s in after if (s.get("game") or {}).get("paused")), None)
    menu = next((s for s in after if (s.get("game") or {}).get("gs") == GS_MAIN_MENU), None)
    foreign, edges, last_edge, pause_after, unpauses, was, prev = 0, 0, None, 0, 0, False, 0
    for s in after:
        g = s.get("game") or {}
        if menu is not None and s["f"] >= menu["f"]:
            break
        p = bool(g.get("paused"))
        latched = int((((s.get("act") or {}).get("hf") or {}).get("latched")) or 0)
        if p:
            if latched & ~(MENU_KEYS | BIT["pause"]):
                foreign += 1
                if latched & ~prev & ~(MENU_KEYS | BIT["pause"]):
                    edges += 1                     # a planner key pressed on a paused frame (a queued tap replayed)
                    last_edge = s["f"] - (paused if paused is not None else s["f"])
            if latched & BIT["pause"]:
                pause_after += 1
        elif was and g.get("gs") is not None and g.get("gs") != GS_MAIN_MENU and g.get("scene"):
            unpauses += 1
        was, prev = p, latched
    rq = pol.get("real_quit") or {}
    q = lambda f: (by_f.get(f) or {}).get("q")  # noqa: E731
    menu_s = None
    if menu is not None and paused is not None and q(paused) and menu.get("q"):
        menu_s = round((menu["q"] - q(paused)) / 1e7, 3)
    out.update(
        hit_f=fh, hero_state=h.get("hero_state"), vy=round(((h.get("vel") or [0, 0])[1]), 2),
        clip=(h.get("anim") or {}).get("clip"), airborne=h.get("hero_state") == 3, moments=off, special=special,
        first_pausable=None if pausable is None else pausable - fh,
        pending=None if pol.get("first_pending_f") is None else pol["first_pending_f"] - fh,
        paused=None if paused is None else paused - fh,
        latency=None if paused is None or pausable is None else paused - pausable,
        foreign_key_frames_paused=foreign, foreign_edges_paused=edges, last_foreign_edge=last_edge,
        pause_key_frames_paused=pause_after, unpauses=unpauses,
        machine_unpauses=rq.get("unexpected_unpauses"), wrong_submits=rq.get("wrong_submits"),
        main_menu=menu is not None, to_menu_frames=None if menu is None or paused is None else menu["f"] - paused,
        to_menu_s=menu_s, real_quit=bool(rq.get("armed")))
    return out


def summarize(trials: list[dict]) -> dict:
    took = [t for t in trials if t.get("took")]
    lat = sorted(t["latency"] for t in took if t.get("latency") is not None)

    def pct(v, p):
        return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))] if v else None
    return {"trials": len(trials), "hits_taken": len(took), "kinds": dict(Counter(t["kind"] for t in trials)),
            "special_share": round(sum(bool(t.get("special")) for t in took) / len(took), 3) if took else None,
            "special_kinds": dict(Counter(k for t in took for k in (t.get("special") or {}))),
            "airborne_share": round(sum(bool(t.get("airborne")) for t in took) / len(took), 3) if took else None,
            "paused": sum(t.get("paused") is not None for t in took),
            "latency_frames": {"p50": pct(lat, 50), "p99": pct(lat, 99), "max": lat[-1] if lat else None,
                               "over_6": sum(v > 6 for v in lat)},
            "foreign_keys_while_paused": sum(t.get("foreign_key_frames_paused") or 0 for t in took),
            "foreign_edges_while_paused": sum(t.get("foreign_edges_paused") or 0 for t in took),
            "last_foreign_edge_after_pause_max": max((t["last_foreign_edge"] for t in took
                                                      if t.get("last_foreign_edge") is not None), default=None),
            "pause_key_frames_after_pause_max": max((t.get("pause_key_frames_paused") or 0 for t in took),
                                                    default=0),
            "unintended_unpauses": sum(t.get("unpauses") or 0 for t in took)
            + sum(t.get("machine_unpauses") or 0 for t in took),
            "wrong_submits": sum(t.get("wrong_submits") or 0 for t in took),
            "main_menu": sum(bool(t.get("main_menu")) for t in took),
            "to_menu_s_max": max((t["to_menu_s"] for t in took if t.get("to_menu_s") is not None), default=None),
            "outcomes": dict(Counter(t.get("outcome") for t in trials))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.knowledge.kinematics import cstate_names
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.combat_run import load_attempts
    names = cstate_names()
    out = []
    for run in a.runs:
        for row in load_attempts(run):
            if not (row.get("policy") or {}).get("inject") or not row.get("recording"):
                continue
            start = row["f_end"] - row["acts"] - (row.get("late_states") or 0)
            states = list(RecordingReader(find_recording(run, row)).states(start, row["f_end"] + 60, keys=STATE_KEYS))
            t = trial(row, states, names)
            if t is None:
                continue
            t.update(run=run.name, instance=row.get("instance"), episode=row.get("episode"))
            out.append(t)
            print(json.dumps({k: t.get(k) for k in ("instance", "episode", "kind", "offset", "took", "hit_f",
                                                    "airborne", "special", "first_pausable", "pending", "paused",
                                                    "latency", "foreign_key_frames_paused", "foreign_edges_paused",
                                                    "unpauses",
                                                    "wrong_submits", "to_menu_s", "outcome")}), flush=True)
    s = summarize(out)
    print(json.dumps(s, indent=1))
    if a.json:
        a.json.write_text(json.dumps({"summary": s, "trials": out}, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
