"""Pause stress test summary (DESIGN §3.7.5 G1 fault injection; M2 W5): one trial per episode of a combat_run run with
--inject-hits (ssbot.train.hit_injection: one fault per episode, a hit through hurt.special down to 1 HP, a
supervisor quit trigger with no damage, or both on one tick, so the supervisor must pause and, with --real-quit 1.0,
quit to the main menu), measured from the run's recordings.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.launcher -n 1 --first 4 --detach
    ../scripts/uv.cmd run python -m ssbot.tools.combat_run run --instances 4 --encounter BellBeast --mode eval
        --policy planner --view oracle --real-quit 1.0 --inject-hits 0.5 --threads 4 --episodes 100 --seed 100000
    ../scripts/uv.cmd run python -m ssbot.tools.pause_stress C:/ssbot/data/runs/m2/<run> [--json out.json]

Per trial:
  fault      the frame the fault reached the game: the damage event of the injected hit the game took (hit, menu), or
             the supervisor's first PAUSE_PENDING frame (trigger: injected before the policy's tick on that STATE)
  moment     the injection kind, fault type and planned offset; the hero's state as the fault arrived (the frame
             before a hit's damage frame: on it the hurt has already set her state); the nearest hard moments within
             +-12 frames of the fault, as fault - moment: kill (BossDeathSlow, a death state, a hit leaving the boss
             at <= 0 HP), stun (BossStun), bounce (downSpikeBouncing onset), clash (parrying onset, or a nail recoil
             with no hit or damage within 2 frames: a tink off an object without health, the bells), cast (the first
             frame of a NeedleThrow clip: a Silkspear), hurt (a damage event other than the injected hit: a real
             hit's hit-stun), menu (hit faults only: the first frame the loop's Pause press is latched after
             PAUSE_PENDING, the frame the pause menu opens when the gate lets it: a hit landing within 3 frames of it
             closes the gate under the press); "special" when one is within +-3 frames (G1: >= 30 % of the faults)
  latency    first pausable frame (STATE pause.blk 0) of the open-gate stretch the pause came in, the supervisor's
             first PAUSE_PENDING frame, the first Pause latch, the first paused frame (game.paused); latency =
             paused - first pausable, in frames (G1: p99.9 <= 6); key_waits: frames the loop's press waited for the
             key guard
  keys       menu-visible frames (from the first paused frame to the main menu) carrying a latched key (STATE
             act.hf.latched) other than Pause before the menu first accepts input, and other than Pause / Up / Down /
             Enter after (the only keys the quit sequence presses, and only on a ready menu): a planner key held or
             replayed into the menu (DESIGN §3.8.2: Z submits, X / A cancel, m0:N16) must never happen. edges: such
             keys newly pressed on a paused frame; per key counts. Before the menu key guard (safety.key_guard), the
             37 gate / live QUITs (20261002_123347 ... 152649) had a movement key latched 1-2 frames into the pause
             in 9 and newly pressed on the pause frame in 4. pause_key_frames_paused: the loop's own in-flight press
             after the pause (within the 230 ms budget)
  unpauses   paused -> running transitions before the quit reached the main menu (must be 0; real quits only: an
             emulated quit is resumed by the harness); the machine's own
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
NEAR = 12
HARD = ("kill", "stun", "bounce", "clash", "cast", "hurt", "menu")
STATE_KEYS = ("f", "q", "ev", "hero", "act", "game", "pause", "ts", "menu")


def _cs(names: list[str], s: dict) -> dict[str, bool]:
    from ssbot.tools.cstate import decode
    w = (s.get("hero") or {}).get("cstate")
    try:
        return decode(w, names) if w else {}
    except ValueError:
        return {}


FLOOR_HERO_Y = 3.5677        # the hero transform's y standing on the Bone_05 floor


def _latched(s: dict) -> int:
    return int((((s.get("act") or {}).get("hf") or {}).get("latched")) or 0)


def moments(states: list[dict], names: list[str], death_states: tuple[str, ...] = ("Death Broadcast",),
            skip_damage: tuple[int, ...] = ()) -> dict:
    """Frames of the hard moments in a stretch of STATEs: kill, stun, bounce, clash, cast, hurt (damage events not at
    the frames in skip_damage); plus hits dealt."""
    out: dict[str, list[int]] = {"kill": [], "stun": [], "bounce": [], "clash": [], "cast": [], "hurt": [], "hit": []}
    prev: dict[str, bool] = {}
    prev_clip = None
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
                hp = d.get("hp_after")
                if d.get("dead") or (isinstance(hp, (int, float)) and hp <= 0):
                    out["kill"].append(f)
            elif k == "damage":
                dmg.add(f)
                if f not in skip_damage:
                    out["hurt"].append(f)
        cs = _cs(names, s)
        for name, key in (("downSpikeBouncing", "bounce"), ("parrying", "clash")):
            if cs.get(name) and not prev.get(name):
                out[key].append(f)
        rec = cs.get("recoilingLeft") or cs.get("recoilingRight")
        if rec and not (prev.get("recoilingLeft") or prev.get("recoilingRight")) and not cs.get("recoilFrozen"):
            recoil_on.append(f)
        clip = str(((s.get("hero") or {}).get("anim") or {}).get("clip") or "")
        if clip.startswith("NeedleThrow") and prev_clip is not None and not prev_clip.startswith("NeedleThrow"):
            out["cast"].append(f)
        prev, prev_clip = cs, clip
    for f in recoil_on:
        if not any(abs(f - g) <= 2 for g in hits | dmg):
            out["clash"].append(f)
    out["hit"] = sorted(hits)
    return {k: sorted(set(v)) for k, v in out.items()}


def _ready(s: dict) -> bool:
    from ssbot.safety.pause_quit import cues_from_state
    return bool(cues_from_state(s).menu_ready)


def trial(row: dict, states: list[dict], names: list[str], natural: bool = False) -> dict | None:
    """One trial; natural: also an attempt without an injection whose supervisor paused (its first PAUSE_PENDING is
    the fault frame, kind "natural"), e.g. the QUITs of a gate run, as a baseline."""
    pol = row.get("policy") or {}
    inj = pol.get("inject")
    if not inj and natural and pol.get("first_pending_f") is not None:
        inj = {"kind": "natural", "fault": "trigger", "offset": 0, "sent": [], "replies": []}
    if not inj:
        return None
    fault = inj.get("fault") or "hit"
    took = [r for r in inj.get("replies") or () if isinstance(r, dict) and r.get("take_health_calls")
            and r.get("hp_after", 9) < r.get("hp_before", 0)]
    out = {"kind": inj.get("kind"), "fault": fault, "offset": inj.get("offset"), "fallback": inj.get("fallback"),
           "sent": len(inj.get("sent") or ()), "took": bool(took), "outcome": row.get("outcome"),
           "reason": row.get("reason")}
    pend = pol.get("first_pending_f")
    by_f = {s["f"]: s for s in states}
    fh = None
    if took:
        fh = took[-1]["frame"]
        dmg = [s["f"] for s in states if fh - 1 <= s["f"] <= fh + 3 and any(e.get("k") == "damage"
                                                                             for e in s.get("ev") or ())]
        fh = dmg[0] if dmg else fh
    if fault == "trigger":
        ff = pend if pend is not None else inj.get("trigger_f")
    else:
        ff = fh
    out["injected"] = ff is not None
    if ff is None:
        return out
    # the hero as the fault arrived: for a hit the frame before the damage frame (on the damage frame the hurt has
    # already set her state; the first summary read hero_state there and counted 0 airborne hits of 112)
    s0 = (by_f.get(ff - 1) or by_f.get(ff) or {}) if fh is not None else (by_f.get(ff) or {})
    h = s0.get("hero") or {}
    near = moments([s for s in states if ff - NEAR <= s["f"] <= ff + NEAR], names,
                   skip_damage=() if fh is None else (fh,))
    after_pend = [s for s in states if pend is not None and s["f"] >= pend]
    press = next((s["f"] for s in after_pend if _latched(s) & BIT["pause"]), None)
    if fh is not None and press is not None:
        near["menu"] = [press]
    off = {k: min((ff - m for m in v), key=abs) for k, v in near.items() if v}
    special = {k: v for k, v in off.items() if k in HARD and abs(v) <= SPECIAL_WINDOW}
    after = [s for s in states if s["f"] >= ff]
    paused = next((s["f"] for s in after if (s.get("game") or {}).get("paused")), None)
    # pausable for good: the first frame of the open-gate stretch the pause came in (a hit after the fault closes the
    # gate again: 20261002_162847 i2 ep 12, PAUSE_PENDING 2 frames before a hit, read 21 frames from the first open
    # frame, 4 from the reopening)
    pausable = None
    for s in after:
        if paused is not None and s["f"] >= paused:
            break
        if (s.get("pause") or {}).get("blk"):
            pausable = None
        elif pausable is None:
            pausable = s["f"]
    if paused is None:
        pausable = next((s["f"] for s in after if not (s.get("pause") or {}).get("blk")
                         and not (s.get("game") or {}).get("paused")), None)
    menu = next((s for s in after if (s.get("game") or {}).get("gs") == GS_MAIN_MENU), None)
    foreign, edges, last_edge, pause_after, unpauses, was, prev = 0, 0, None, 0, 0, False, 0
    per_key: Counter = Counter()
    pause_frame_keys = None
    ready_seen = False
    for s in after:
        g = s.get("game") or {}
        if menu is not None and s["f"] >= menu["f"]:
            break
        p = bool(g.get("paused"))
        latched = _latched(s)
        if p:
            ready_seen = ready_seen or _ready(s)
            allowed = BIT["pause"] | (MENU_KEYS if ready_seen else 0)
            bad = latched & ~allowed
            if s["f"] == paused:
                pause_frame_keys = latched & ~BIT["pause"]
            if bad:
                foreign += 1
                per_key.update(k for k in KEYS if bad & BIT[k])
                if latched & ~prev & ~allowed:
                    edges += 1                     # a key pressed on a paused frame (a queued tap replayed)
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
    rel = lambda f: None if f is None else f - ff  # noqa: E731
    out.update(
        fault_f=ff, hit_f=fh, hero_state=h.get("hero_state"), vy=round(((h.get("vel") or [0, 0])[1]), 2),
        clip=(h.get("anim") or {}).get("clip"), latched_at_fault=_latched(s0),
        airborne=bool(h.get("hero_state") == 3 or (h.get("pos") or [0, 0])[1] > FLOOR_HERO_Y + 0.1),
        moments=off, special=special,
        first_pausable=rel(pausable), pending=rel(pend), press=rel(press), paused=rel(paused),
        latency=None if paused is None or pausable is None else paused - pausable,
        key_waits=rq.get("key_waits"), key_waits_expired=rq.get("key_waits_expired"),
        foreign_key_frames_paused=foreign, foreign_edges_paused=edges, last_foreign_edge=last_edge,
        foreign_keys=dict(per_key), pause_frame_keys=pause_frame_keys,
        pause_key_frames_paused=pause_after,
        unpauses=unpauses if rq.get("armed") else None,     # an emulated quit is resumed by the harness on purpose
        machine_unpauses=rq.get("unexpected_unpauses"), wrong_submits=rq.get("wrong_submits"),
        main_menu=menu is not None, to_menu_frames=None if menu is None or paused is None else menu["f"] - paused,
        to_menu_s=menu_s, real_quit=bool(rq.get("armed")))
    return out


def _pct(v: list, p: float):
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))] if v else None


def summarize(trials: list[dict]) -> dict:
    inj = [t for t in trials if t.get("injected", t.get("took"))]
    lat = sorted(t["latency"] for t in inj if t.get("latency") is not None)
    share = lambda ts: round(sum(bool(t.get("special")) for t in ts) / len(ts), 3) if ts else None  # noqa: E731
    by_kind = {}
    for k in sorted({t.get("kind") for t in inj}, key=str):
        ts = [t for t in inj if t.get("kind") == k]
        by_kind[str(k)] = {"n": len(ts), "special": share(ts)}
    offs: Counter = Counter()
    for t in inj:
        for v in (t.get("special") or {}).values():
            offs[v] += 1
    return {"trials": len(trials), "injected": len(inj), "hits_taken": sum(bool(t.get("took")) for t in trials),
            "kinds": dict(Counter(t["kind"] for t in trials)),
            "faults": dict(Counter(t.get("fault", "hit") for t in trials)),
            "special_share": share(inj),
            "special_share_without_menu": round(sum(any(k != "menu" for k in (t.get("special") or {}))
                                                    for t in inj) / len(inj), 3) if inj else None,
            "special_kinds": dict(Counter(k for t in inj for k in (t.get("special") or {}))),
            "special_offsets": dict(sorted(offs.items())),
            "special_by_kind": by_kind,
            "airborne_share": round(sum(bool(t.get("airborne")) for t in inj) / len(inj), 3) if inj else None,
            "paused": sum(t.get("paused") is not None for t in inj),
            "latency_frames": {"p50": _pct(lat, 50), "p99": _pct(lat, 99), "p999": _pct(lat, 99.9),
                               "max": lat[-1] if lat else None, "over_6": sum(v > 6 for v in lat)},
            "key_waits_trials": sum(bool(t.get("key_waits")) for t in inj),
            "key_waits_expired": sum(t.get("key_waits_expired") or 0 for t in inj),
            "pause_frame_with_game_keys": sum(bool(t.get("pause_frame_keys")) for t in inj),
            "foreign_keys_while_paused": sum(t.get("foreign_key_frames_paused") or 0 for t in inj),
            "foreign_edges_while_paused": sum(t.get("foreign_edges_paused") or 0 for t in inj),
            "foreign_keys_by_key": dict(sum((Counter(t.get("foreign_keys") or {}) for t in inj), Counter())),
            "last_foreign_edge_after_pause_max": max((t["last_foreign_edge"] for t in inj
                                                      if t.get("last_foreign_edge") is not None), default=None),
            "pause_key_frames_after_pause_max": max((t.get("pause_key_frames_paused") or 0 for t in inj),
                                                    default=0),
            "unintended_unpauses": sum(t.get("unpauses") or 0 for t in inj)
            + sum(t.get("machine_unpauses") or 0 for t in inj),
            "wrong_submits": sum(t.get("wrong_submits") or 0 for t in inj),
            "main_menu": sum(bool(t.get("main_menu")) for t in inj),
            "to_menu_s_max": max((t["to_menu_s"] for t in inj if t.get("to_menu_s") is not None), default=None),
            "outcomes": dict(Counter(t.get("outcome") for t in trials))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--quiet", action="store_true", help="only the summary")
    ap.add_argument("--natural", action="store_true",
                    help="also attempts without an injection whose supervisor paused (gate / live QUITs: a baseline)")
    a = ap.parse_args(argv)
    from ssbot.knowledge.kinematics import cstate_names
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.combat_run import load_attempts
    names = cstate_names()
    out = []
    for run in a.runs:
        for row in load_attempts(run):
            pol = row.get("policy") or {}
            if not row.get("recording") or not (pol.get("inject") or (a.natural and pol.get("first_pending_f"))):
                continue
            start = row["f_end"] - row["acts"] - (row.get("late_states") or 0)
            states = list(RecordingReader(find_recording(run, row)).states(start, row["f_end"] + 60, keys=STATE_KEYS))
            t = trial(row, states, names, natural=a.natural)
            if t is None:
                continue
            t.update(run=run.name, instance=row.get("instance"), episode=row.get("episode"))
            out.append(t)
            if not a.quiet:
                print(json.dumps({k: t.get(k) for k in ("instance", "episode", "kind", "fault", "offset", "took",
                                                        "fault_f", "airborne", "special", "first_pausable",
                                                        "pending", "press", "paused", "latency", "key_waits",
                                                        "foreign_key_frames_paused", "pause_frame_keys", "unpauses",
                                                        "wrong_submits", "to_menu_s", "outcome")}), flush=True)
    s = summarize(out)
    print(json.dumps(s, indent=1))
    if a.json:
        a.json.write_text(json.dumps({"summary": s, "trials": out}, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
