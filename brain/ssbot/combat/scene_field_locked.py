"""Locked-branch SceneView adapter for scene_field_events.build (Sol task 43 item 2; hand-portable, not wired in).

Where it would run (a default-off, low-frequency shadow; nothing here changes ordering, safety or keys sent):
ForumPlannerPolicy.act after `res = self.planner.tick(...)`, reading only objects that tick already holds:

    trk     = self.v2feed.trk           RangeTracker fed every STATE up to f (V2Feed.feed; attack_range.py:799 T)
    frame   = f                         the STATE frame trk was fed to (V2Feed.f_fed); logs only, never the lock frame
    room    = room_of_state(s)          (STATE game.scene, STATE room.seq) of this tick
    arenas  = {"Hang_04": forum_arena(F.WALL_L, F.WALL_R, F.FLOOR_Y, F.DOME)}   ssbot.core.forum statics, per scene
    bombs   = b2_bombs                  this tick's UNFILTERED rune_bombs.frames(trk.rune.predict(T), T) rows
                                        (forum_planner_policy.py:1076); predict() has side effects, so never call it
                                        again here.  fplan.rs.bombs_all is cut at on_k <= 130 (forum_v2.py:735) while
                                        the task 41 template evaluation reaches about 4.5 s past the origin, so a cut
                                        list is passed with bombs_complete=False and refused (unknown, not empty)
    pend    = fplan.rs.pend             forum_v2.pending_aims(trk) of this tick (forum_v2.py:738)

Scope (exactly the existing scene_field_events.project scope, nothing wider): two live Clappers, one locked
CC_JUMP_CAST (RangeTracker Inst.dec set), the other Clapper's Control in Idle / Walk, no pending unlocked aim, no
observed damager entity.  Anything else returns {'status': 'insufficient_coverage', 'reason', 'detail', 'aux'}: a
missing room / arena / bomb list / pending list is unknown (never an empty obstacle list), an observed hazard entity
or a third live enemy is reported and refused (never dropped), a dead or hidden Clapper leaves RangeTracker.now and
the scene is refused.  The hero, candidates, labels and future frames are never read.

Time: t_origin_s = trk.T and every decision age come from the same tick's tracker.  The cache key binds the room,
the caster's Move instance (its tracker start t0) and the true lock (Inst.dec['t'], the tracker time of the decision
state's entry, attack_range.py:690-691) as tracker-frame bins; never the current frame, a position or a clock, so a
second cast with the same s / b is a new key and adjacent ticks of one Move reuse the cached field.

No ssbot import, no file read, no environment or path change; the caller injects scene_field_events.cache_key.
"""
from __future__ import annotations

import math

SCOPE = {"enemy": "Song Heavy Sentry", "n_clappers": 2, "move": "CC_JUMP_CAST", "other_states": ("Idle", "Walk"),
         "layer": "ground"}
KEY_VERSION = "task43-locked-key-v1"
FT = 1.0 / 60.0


def _insufficient(reason: str, detail: str, aux: dict | None = None) -> dict:
    return {"status": "insufficient_coverage", "reason": reason, "detail": detail, "scope": dict(SCOPE), "aux": aux}


def _bin(t: float) -> int:
    """attack_range.bin_of: the tracker-frame bin of a tracker time."""
    return int(math.floor(float(t) / FT + 0.5))


def room_of_state(state: dict):
    """(scene name, room sequence) of a STATE (game.scene, room.seq); None when either is missing."""
    g = state.get("game") or {}
    r = state.get("room") or {}
    sc, seq = g.get("scene"), r.get("seq")
    if not isinstance(sc, str) or not sc or not isinstance(seq, int):
        return None
    return (sc, int(seq))


def forum_arena(wall_l: float, wall_r: float, floor_y: float, dome) -> dict:
    """The build's arena dict from ssbot.core.forum statics (WALL_L, WALL_R, FLOOR_Y, DOME)."""
    return {"walls_x": [float(wall_l), float(wall_r)], "floor_y": float(floor_y),
            "dome_lower_edge": [[float(p), float(q)] for p, q in dome]}


def _first_state(e: dict):
    for f in e.get("fsms") or ():
        if f.get("name") == "Control":
            return f.get("state"), None if f.get("t") is None else float(f["t"])
    return None, 0.0


def _body_box(e: dict, prefix: str):
    """([x0, y0, x1, y1], enabled) of the entity's own box collider named after it (task 33 / #126 pick)."""
    for c in e.get("colliders") or e.get("cols") or ():
        v = c.get("verts_world")
        if c.get("kind") == "box" and str(c.get("name", "")).startswith(prefix) and v and len(v) >= 6:
            xs, ys = v[0::2], v[1::2]
            return [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))], c.get("enabled")
    return None, None


def _hazard_ents(ents) -> list:
    """The frame's hazard-category entities, as the task 33 scene builder lists them (observed damagers)."""
    out = []
    for e in ents or ():
        if e.get("category") != "hazard":
            continue
        cs = [{"kind": c.get("kind"), "enabled": bool(c.get("enabled")), "r": c.get("r"),
               "verts_world": list(c.get("verts_world") or []) or None} for c in e.get("colliders") or ()]
        out.append({"iid": e.get("iid"), "type_key": e.get("type_key"),
                    "pos": [float(v) for v in (e.get("pos") or [])[:2]], "colliders": cs})
    return out


def _live_enemy_ents(ents) -> list:
    """Enemy entities in play in the frame (not dead, not hidden, not parked off-stage at |z| > 5, not in 'Dead')."""
    out = []
    for e in ents or ():
        if e.get("category") != "enemy" or e.get("is_dead") or e.get("hidden"):
            continue
        p = e.get("pos") or ()
        if len(p) > 2 and abs(float(p[2])) > 5.0:
            continue
        st, _ = _first_state(e)
        if st == "Dead":
            continue
        out.append(e)
    return out


def locked_scene(trk, *, frame=None, room=None, arenas=None, bombs=None, bombs_complete: bool = True, pend=None,
                 enemy_type: str = SCOPE["enemy"], body_prefix: str = SCOPE["enemy"], ft: float = FT) -> dict:
    """{'status': 'ok', 'scene', 't_origin_s', 'lock', 'aux'} for scene_field_events.build, or insufficient."""
    if not isinstance(getattr(trk, "ents", None), (list, tuple)):
        return _insufficient("entities_unknown", "no complete observed entity list")
    T = float(trk.T)
    aux = {"T_s": T, "frame": frame, "room": room, "bombs_complete": bool(bombs_complete),
           "n_bombs": None if bombs is None else len(bombs), "n_pending": None if pend is None else len(pend)}
    if not math.isfinite(T):
        return _insufficient("tracker_time_unknown", "trk.T is not finite", aux)
    if room is None:
        return _insufficient("room_unknown", "no (scene, room seq) for this tick", aux)
    arena = (arenas or {}).get(room[0])
    if arena is None:
        return _insufficient("arena_unknown", f"no static arena for scene {room[0]!r}", aux)
    if bombs is None:
        return _insufficient("small_runes_unknown", "no small-rune rows passed for this tick (unknown, not empty)", aux)
    if not bombs_complete:
        return _insufficient("small_runes_truncated", "the bomb rows are cut (e.g. rs.bombs_all at on_k <= 130); "
                             "the field's template evaluation reaches past the cut", aux)
    if pend is None:
        return _insufficient("pending_unknown", "no pending-aim list passed for this tick (fplan.rs.pend)", aux)
    if not all(len(b) == 6 and all(math.isfinite(float(v)) for v in b) for b in bombs):
        return _insufficient("small_runes_unknown", "nonfinite or malformed small-rune rows", aux)
    hazards = _hazard_ents(trk.ents)
    aux["observed_damager_ents"] = hazards
    live = _live_enemy_ents(getattr(trk, "ents", ()))
    clappers = []
    for iid, (tk, e, inst) in sorted(trk.now.items()):
        if tk == enemy_type:
            clappers.append((int(iid), e, inst))
    ids = {c[0] for c in clappers}
    others = [{"iid": e.get("iid"), "type_key": e.get("type_key")} for e in live
              if not (e.get("type_key") == enemy_type and int(e.get("iid") or -1) in ids)]
    aux["other_live_enemies"] = others
    aux["clappers"] = [{"iid": i, "control": _first_state(e)[0], "inst": None if inst is None else inst.fam,
                        "decided": None if inst is None else inst.dec is not None} for i, e, inst in clappers]
    if len(clappers) != SCOPE["n_clappers"]:
        return _insufficient("not_two_clappers", f"{len(clappers)} live Clappers in RangeTracker.now", aux)
    if others:
        return _insufficient("other_live_enemies", f"{len(others)} other enemy entities in play (not modelled)", aux)
    if hazards:
        return _insufficient("observed_damagers", f"{len(hazards)} hazard entities at the origin (existing scope)", aux)
    if len(pend):
        aux["pending"] = [{"iid": int(p["iid"]), "move": p.get("name"), "d_lo": p.get("d_lo"), "d_hi": p.get("d_hi")}
                          for p in pend]
        return _insufficient("aim_unlocked", f"{len(pend)} pending unlocked aims", aux)
    locked = [(i, e, inst) for i, e, inst in clappers if inst is not None and inst.dec is not None]
    casts = [x for x in locked if x[2].fam == SCOPE["move"]]
    if len(casts) != 1:
        return _insufficient("not_one_locked_jump_cast", f"{len(casts)} locked {SCOPE['move']}", aux)
    ci, ce, cinst = casts[0]
    oi, oe, oinst = next(x for x in clappers if x[0] != ci)
    ost, _ = _first_state(oe)
    if ost not in SCOPE["other_states"]:
        return _insufficient("other_not_idle_or_walk", f"other Control state {ost!r}", aux)
    rows = []
    for i, e, inst in sorted(clappers, key=lambda x: x[0]):
        bb, bb_on = _body_box(e, body_prefix)
        if bb is None:
            return _insufficient("missing_body_box", f"iid {i} has no named body box", aux)
        if not all(math.isfinite(v) for v in bb):
            return _insufficient("body_geometry_unknown", f"iid {i} has nonfinite body geometry", aux)
        tab = trk.tables.get(enemy_type)
        p = e.get("pos") or (float("nan"), float("nan"))
        if len(p) < 2 or not all(math.isfinite(float(q)) for q in p[:2]):
            return _insufficient("body_geometry_unknown", f"iid {i} has unknown root", aux)
        if not isinstance(e.get("flipX"), bool):
            return _insufficient("facing_unknown", f"iid {i} has no observed facing", aux)
        v = e.get("vel") or (0.0, 0.0)
        rows.append({"iid": i, "type_key": enemy_type, "root": [float(p[0]), float(p[1])],
                     "vel": [float(v[0]), float(v[1] if len(v) > 1 and v[1] is not None else 0.0)],
                     "flipX": e.get("flipX"), "facing_s": None if tab is None else int(tab.facing(e.get("flipX"))),
                     "body_box": bb, "body_enabled": bb_on,
                     "fsms": [{"name": f.get("name"), "state": f.get("state"),
                               "t": None if f.get("t") is None else float(f.get("t"))} for f in e.get("fsms") or ()]})
        if rows[-1]["facing_s"] is None:
            return _insufficient("facing_unknown", f"no RangeTracker table for {enemy_type!r}", aux)
    lk = []
    for i, e, inst in locked:
        d = inst.dec
        if not all(k in d and math.isfinite(float(d[k])) for k in ("t", "x", "y", "s", "L", "b")):
            return _insufficient("decision_unknown", f"iid {i} has incomplete decision", aux)
        s, L = int(d["s"]), float(d["L"])
        lk.append({"iid": i, "family": inst.fam,
                   "decision": {"b": int(d["b"]), "x": float(d["x"]), "y": float(d["y"]), "s": s, "L": L,
                                "decided_frames_ago": (T - float(d["t"])) / ft, "x_land": float(d["x"]) + s * L}})
    small = [{"owner": int(b[0]), "x": float(b[1]), "y": float(b[2]), "r": float(b[3]), "on_k": int(b[4]),
              "off_k": int(b[5])} for b in bombs]
    scene = {"arena": dict(arena, source="static arena of " + room[0]),
             "enemies": {"rows": rows},
             "aim": {"pending_unlocked": [], "locked": lk},
             "hazards": {"observed_damager_ents": hazards, "small_runes": {"rows": small}}}
    dec = cinst.dec
    lock = {"room": [room[0], int(room[1])], "caster_iid": ci, "other_iid": oi, "move": SCOPE["move"],
            "inst_t0_s": float(cinst.t0), "inst_t0_bin": _bin(cinst.t0), "lock_t_s": float(dec["t"]),
            "lock_bin": _bin(dec["t"]), "s": int(dec["s"]), "b": int(dec["b"]),
            "age_frames": (T - float(dec["t"])) / ft,
            "lock_frame_estimate": None if frame is None else int(frame) - int(round((T - float(dec["t"])) / ft))}
    return {"status": "ok", "scene": scene, "t_origin_s": T, "lock": lock, "aux": aux}


def field_key(cache_key_fn, scene: dict, lock: dict, config, inputs):
    """scene_field_events.cache_key with the true lock as lock_id, plus the room and the Move instance: only
    strings and integers (no time, frame, clock or position)."""
    base = cache_key_fn(scene, config, inputs, lock_id=int(lock["lock_bin"]))
    if base is None:
        return None
    return base + ((KEY_VERSION, str(lock["room"][0]), int(lock["room"][1]), int(lock["caster_iid"]),
                    int(lock["inst_t0_bin"])),)


def lock_coverage(scene: dict, inputs) -> dict:
    """Whether every conditional world still has its circle-off knot after the origin (scene_field_events
    _world_clocks arithmetic, 07acdeec :220-238): a lock whose event is over in some world has no complete field."""
    d = next(a["decision"] for a in scene["aim"]["locked"] if a["family"] == SCOPE["move"])
    xl = float(d["x_land"])
    branch = "wall" if (xl < inputs.wall_zone[0] or xl > inputs.wall_zone[1]) else "open"
    age = float(d["decided_frames_ago"]) / 60.0
    c = inputs.clock[branch]
    off = {w: c["lit"][w] - age + inputs.clock["lit_duration_s"] for w in ("early", "nominal", "late")}
    return {"branch": branch, "circle_off_after_origin_s": off, "complete": all(v > 1e-9 for v in off.values())}


def field_complete(fs) -> bool:
    """Every world of a built FieldSet keeps its circle-off knot (no degenerate single-knot world)."""
    return all(any(n == "circle_off" for n, _ in w["events_rel"]) for w in fs.meta["worlds"].values())


def field_for_tick(cache, events, view: dict, inputs, grid_cls, config, prepared=None):
    """One tick: (FieldSet or None, reason).  cache = scene_field_events.SceneFieldSetCache; events = the module."""
    if view.get("status") != "ok":
        return None, view.get("reason")
    cov = lock_coverage(view["scene"], inputs)
    if not cov["complete"]:
        return None, "lock_event_over"
    key = field_key(events.cache_key, view["scene"], view["lock"], config, inputs)
    if key is None:
        return None, "out_of_build_scope"
    fs = cache.get(key, view["t_origin_s"], lambda: events.build(view["scene"], inputs, grid_cls, config,
                                                                 t_origin_s=view["t_origin_s"], prepared=prepared))
    if not field_complete(fs):
        raise ValueError("built field is not complete although the lock coverage was")
    return fs, "ok"
