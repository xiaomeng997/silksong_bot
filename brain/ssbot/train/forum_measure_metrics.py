"""Independent offline HP/event accounting on original, frame-indexed STATEs."""
from __future__ import annotations

import math

DOWN = {"DownSlash", "DownSlash New", "DownSlashAlt"}
# The game's own quit-to-menu path after a real quit: Quit_To_Menu, then hero/game None, then Menu_Title (live
# e390 3555..3592, e4 2987..3024). Sending the quit keys is not this; a paused gameplay scene is not this.
QUIT_SCENES = frozenset({"Quit_To_Menu", "Menu_Title"})


def audit_states(states, *, wake_f: int, end_f: int, target_ids=(), allow_zero_exposure=False) -> dict:
    problems, frames = [], {}
    for state in states:
        f = state["f"]
        if f in frames:
            if frames[f] != state:
                problems.append("conflicting records for one STATE frame")
            continue  # repeated reading of the same original record
        frames[f] = state
    ordered = sorted(frames)
    window = [f for f in ordered if wake_f <= f <= end_f]
    if not window or window[0] != wake_f or window[-1] != end_f:
        problems.append("missing window boundary")
    if len(window) != end_f - wake_f + 1:
        problems.append("raw STATE gap")
    events = []
    for record_f in ordered:
        for index, event in enumerate(frames[record_f].get("ev") or ()):
            ef = event.get("f")
            if not isinstance(ef, int):
                if wake_f <= record_f <= end_f:
                    problems.append("event missing its original frame")
                continue
            if wake_f <= ef <= end_f:
                events.append({"f": ef, "q": event.get("q"), "record_f": record_f,
                               "index": index, "kind": event.get("k"), "data": event.get("d") or {}})
    events.sort(key=lambda e: (e["f"], e["q"] if isinstance(e["q"], (int, float)) else e["record_f"], e["index"]))
    hp_delta, losses = {}, []
    for event in events:
        if event["kind"] != "hp":
            continue
        data = event["data"]
        delta, blue = data.get("delta"), data.get("blue_delta")
        if not isinstance(delta, (int, float)) or not isinstance(blue, (int, float)):
            problems.append("hp event missing health/blue delta")
            continue
        change = delta + blue
        hp_delta[event["f"]] = hp_delta.get(event["f"], 0) + change
        if change < 0:
            losses.append({"f": event["f"], "record_f": event["record_f"], "event_index": event["index"],
                           "amount": -change, "source": data.get("source"), "src": data.get("src")})
    previous = None
    before = [f for f in ordered if f < wake_f]
    if before:
        hero = frames[before[-1]].get("hero") or {}
        if isinstance(hero.get("health"), (int, float)) and isinstance(hero.get("health_blue"), (int, float)):
            previous = hero["health"] + hero["health_blue"]
    game_s = 0.0
    quit_f, unloaded = None, []
    for f in window:
        state = frames[f]
        dt = state.get("dt")
        if not isinstance(dt, (int, float)) or not math.isfinite(dt) or dt < 0:
            problems.append("invalid/missing raw dt")
        else:
            game_s += dt
        game = state.get("game") if isinstance(state.get("game"), dict) else None
        scene = None if game is None else game.get("scene")
        if (quit_f is not None and "hero" in state and state["hero"] is None
                and (game is None or scene in QUIT_SCENES)):
            # The game itself showed Quit_To_Menu with the hero loaded and HP read; the character is now unloaded on
            # that path, so this frame has no HP to read. An HP change here still cannot be checked.
            if f in hp_delta:
                problems.append("hp event after real-quit unload")
            unloaded.append(f)
            continue
        if unloaded:
            problems.append("hero or gameplay scene after real-quit unload")
        hero = state.get("hero") or {}
        h, b = hero.get("health"), hero.get("health_blue")
        if not isinstance(h, (int, float)) or not isinstance(b, (int, float)):
            problems.append("missing health snapshot")
            continue
        total, change = h + b, hp_delta.get(f, 0)
        if previous is not None and previous + change != total:
            problems.append(f"HP conservation mismatch at {f}")
        previous = total
        if quit_f is None and scene == "Quit_To_Menu":
            quit_f = f
    if game_s < 0 or (game_s == 0 and not allow_zero_exposure):
        problems.append("zero game exposure")

    targets = set(target_ids)
    hammers, active, phase, idles, idle_active = [], {}, {}, [], {}
    for event in events:
        data, f = event["data"], event["f"]
        iid = data.get("ent")
        if iid not in targets:
            continue
        if event["kind"] == "fsm" and data.get("fsm") == "Control":
            to = data.get("to")
            run = active.get(iid)
            if run is not None and phase.get(iid) == "Slam 0" and to != "Slam 0":
                run["exit_f"] = f
            if to == "Slam Antic":
                run = {"iid": iid, "entry_f": f, "slam0_f": None, "exit_f": None,
                       "down_hits": [], "antic_kill": False, "boundary_hits": []}
                hammers.append(run)
                active[iid] = run
            elif to == "Slam 0" and run is not None:
                run["slam0_f"] = f
            if iid in idle_active and to != "Idle":
                idle_active[iid]["exit_f"] = f
                del idle_active[iid]
            if to == "Idle":
                idle = {"iid": iid, "entry_f": f, "exit_f": None, "hits": []}
                idles.append(idle)
                idle_active[iid] = idle
            phase[iid] = to
        elif event["kind"] == "hit":
            run = active.get(iid)
            key = [event["record_f"], event["index"]]
            if iid in idle_active and (data.get("dealt") or 0) > 0:
                idle_active[iid]["hits"].append(key)
            if run is not None:
                if data.get("dead") and run["slam0_f"] is None:
                    run["antic_kill"] = True
                if data.get("src") in DOWN and (data.get("dealt") or 0) > 0 and run["slam0_f"] is not None:
                    if run["exit_f"] == f or run["slam0_f"] == f:
                        run["boundary_hits"].append(key)
                    elif phase.get(iid) == "Slam 0":
                        run["down_hits"].append(key)
    denominator = [r for r in hammers if r["slam0_f"] is not None]
    hit = sum(bool(r["down_hits"]) for r in denominator)
    unknown = sum(not r["down_hits"] and (r["exit_f"] is None or bool(r["boundary_hits"])) for r in denominator)
    L = sum(loss["amount"] for loss in losses)
    return {"complete": not problems, "problems": sorted(set(problems)), "L": L, "T": game_s,
            "real_quit_unload": None if not unloaded else {"quit_scene_f": quit_f, "first_f": unloaded[0],
                                                           "last_f": unloaded[-1], "frames": len(unloaded)},
            "HP_per_min": 60 * L / game_s if game_s > 0 else None, "losses": losses,
            "hp_conservation": not problems,
            "hammers": hammers, "hammer_counts": {"entered_slam0": len(denominator), "hit": hit,
                "unknown": unknown, "antic_kills": sum(r["antic_kill"] for r in hammers)},
            "hammer_hit_rate": hit / len(denominator) if denominator and not unknown else None,
            "idles": idles, "idle_without_hit": sum(not r["hits"] for r in idles),
            "event_time": "original ev.f/q; same-frame strike boundaries remain unresolved"}
