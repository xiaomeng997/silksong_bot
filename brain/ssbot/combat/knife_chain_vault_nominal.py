"""Nominal path of the Idle vault family's near entry (ported Task 79 component; private model only).

compile_near runs the bound vault table (knife_chain_vault, VaultAnchor + v0) on PRIVATE runner copies:
  1. one real preview: the caller's runner copied, the request opened (or the existing Run continued), one step on the
     real STATE `raw` with the real sim -> the first offered mask (origin + 2) and `first_draft` (that copy as it is
     after this one real observation; no model future ever enters it);
  2. the model future: another copy of that draft stepped on observations generated from the same nominal hero model
     (knife_chain_nominal._hero) and the existing two-beat pipeline (the queued origin + 1 key, then the table's masks
     two frames ahead), until the table itself closes the Run.
Nothing here is a receipt: a modeled hit / bounce never credits the real Run, which the executor still advances only
on an observed target DownSlash hit plus pogo_marker.

Model rules, all existing (no new motion rule):
  - hero: NominalStepper / hold_one (HERO2, HoldFilter);
  - down-slash contact (opus/vault_chain46 / #136 closed loop): the swing airborne (F_ATTACKING on the press frame or
    the next, not grounded the frame before), no ground since the press, both down polygons (pogo_model.slash_poly,
    both shapes) at the press facing meet the target body on press + pogo_model.ACTIVE; that frame is re-run with
    EV_POGO, its pre-contact flags kept as the check flags (knife_chain_nominal.compile_path's rule);
  - side contact: both side polygons (knife_chain_vault.side_meets) at the swing's onset facing meet the body on
    onset + 1 .. 7; that frame is re-run with EV_RECOIL_L / R and the body pushed 0.06 u per physics step for 8 steps
    (the Clapper's 0.48 u hit knock-back, claw_strike.py's docstring);
  - target: its body and root from `raw`, held in Idle (its reaction to hits is UNKNOWN; recorded in assumptions);
  - buddy (the other Clapper): its observed Control state while game < buddy_lock_until, then POST_LOCK_STATE. The
    clock is the caller's, from the locked move's own model: finite and known, never a recording's future;
  - hit events on the frames of modeled contacts.
Termination: the table's own close of the Run (done / handback). Anything else raises NominalUnsupported: no queued
key or more than one, an unknown clock, no admitted Run, the near press swung on the ground (a ground Slash), no
modeled down-slash contact, an abort, or max_frames without a close (the horizon is not a handback).
The path's stage is "approach": every body and hazard stays in the caller's check; it is not a CC_SLAM admission.
DEPENDENCY (found here, not fixed here): the table's exits read the target through knife_chain_vault._body, which only
matches a collider named exactly "Song Heavy Sentry"; recorded STATEs name it "Song Heavy Sentry (2)" / "(3)". On those
the over link can never clear (vault_clear_of_far_edge), air / ground slashes never act and the far entry never opens,
so this function faithfully raises NominalUnsupported ("landed before passing the far edge"). With a prefix match (as
knife_chain_air.body_box) it reproduces Task 78 (opus/vault_nominal79/compare79_prefix_body.json).
press_frame / contact_frame are this down slash's mask frame and modeled contact frame.
"""
from __future__ import annotations

import math

import numpy as np

from ssbot.knowledge import kinematics as km
from . import knife_chain_vault as KV
from . import pogo_model as PM
from .air_chain import ChainSim
from .knife_chain_air import body_box
from .knife_chain_format import MASK_NAMES as B
from .knife_chain_nominal import NominalPath, NominalUnsupported, _hero, logical_copy
from .knife_chain_step import NominalStepper, hold_one
from .slam_play import control

PUSH_U, PUSH_STEPS = 0.06, 8
POST_LOCK_STATE = "Slam 2"        # the first Control state after a jump's landing; the table reads lock / non-lock only
SIDE_ONSET_MAX = 12               # a side press whose swing has not begun within this many frames is dropped (#136)


def _private_observation(raw, iids):
    """raw with private copies of the hero lanes and of these entities' fsms / colliders (all else read-only)."""
    s = dict(raw)
    h = dict(raw.get("hero") or {})
    for name in ("tm", "can", "anim"):
        h[name] = dict(h.get(name) or {})
    h.pop("cstate_int", None)               # an observed counter lane: the model's marker is _hero's cstate bit only
    s["hero"] = h
    ents = []
    for e in raw.get("ents") or ():
        if e.get("iid") in iids:
            e = dict(e)
            e["fsms"] = [dict(fs) for fs in e.get("fsms") or ()]
            e["colliders"] = [dict(c) for c in e.get("colliders") or ()]
            e["pos"] = list(e.get("pos") or (0.0, 0.0))
        ents.append(e)
    s["ents"] = ents
    return s


def _entity(s, iid):
    return next((e for e in s.get("ents") or () if e.get("iid") == iid), None)


def _set_control(e, state):
    for fs in e.get("fsms") or ():
        if fs.get("name") == "Control":
            if fs.get("state") != state:
                fs.update(state=state, t=0.0)
            return
    e.setdefault("fsms", []).append({"name": "Control", "state": state, "t": 0.0})


def _set_body(e, box, dx):
    for c in e.get("colliders") or ():
        if c.get("layer") == 11 or str(c.get("name", "")).startswith("Song Heavy Sentry"):
            c["verts_world"] = [float(box[0]), float(box[1]), float(box[2]), float(box[1]),
                                float(box[2]), float(box[3]), float(box[0]), float(box[3])]
    e["pos"] = [float(e["pos"][0]) + dx, float(e["pos"][1])]


def _clear_short_bounce(s):
    """_hero owns downSpikeBouncing; the observed downSpikeBouncingShort bit is not a model lane: clear it."""
    names = km.cstate_names()
    if "downSpikeBouncingShort" not in names:
        return
    i = names.index("downSpikeBouncingShort")
    bits = list(s["hero"].get("cstate") or [])
    if i // 64 < len(bits):
        bits[i // 64] = int(bits[i // 64]) & ~(1 << (i % 64))
        s["hero"]["cstate"] = bits


def _mask_of(row):
    return int(sum(1 << i for i, v in enumerate(np.asarray(row).ravel()) if v))


def _down_meets(pos, face, box):
    q = np.array([[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]]], float)
    return all(PM.meets(PM.slash_poly(face, alt) + np.asarray(pos, float), q) for alt in (False, True))


def compile_near(runner, raw, sim, game, *, request, buddy_iid, buddy_lock_until, max_frames=120, bombs=None):
    """NominalPath of the vault table from this tick to its own close; see the module docstring."""
    if type(max_frames) is not int or max_frames < 24:
        raise ValueError("max_frames must be an int >= 24")
    if not isinstance(buddy_lock_until, (int, float)) or isinstance(buddy_lock_until, bool) or not math.isfinite(buddy_lock_until):
        raise NominalUnsupported("buddy lock clock unknown")
    if sim.fo != sim.f or len(sim.prefix) != 1:
        raise NominalUnsupported("vault nominal needs the current origin and one queued key")
    if type(raw.get("f")) is not int or raw["f"] != int(sim.f):
        raise NominalUnsupported("STATE frame is not the sim origin")
    origin, game = int(sim.f), float(game)
    params, terrain = sim.params, sim.terrain

    # 1. the one real preview, on a private copy
    R0 = logical_copy(runner)
    if request is not None:
        if R0.run is not None:
            raise NominalUnsupported("a vault Run is active: continue it with request=None")
        R0.anchor.open(request)
    elif R0.run is None:
        raise NominalUnsupported("no vault Run to continue")
    S = np.asarray(sim.start, float).reshape(km.K).copy()
    accepting = bool((raw.get("hero") or {}).get("hero_accepting_input", True))
    first = R0.step(origin, raw, bool(S[km.GROUND] > 0), accepting, t_game=game, sim=sim, bombs=bombs)
    if first is None or R0.run is None:
        raise NominalUnsupported("vault table declined the real observation")
    iid = R0.run.v["iid"]
    first_draft = logical_copy(R0)

    # 2. the model future, on a copy of that draft
    R = logical_copy(R0)
    s = _private_observation(raw, {iid, buddy_iid})
    target, buddy = _entity(s, iid), _entity(s, buddy_iid)
    if target is None:
        raise NominalUnsupported("target absent")
    tb = body_box(target)
    if tb is None:
        raise NominalUnsupported("target body unknown")
    tb = [float(v) for v in tb]
    lock_state = None if buddy is None else control(buddy)[0]
    if lock_state is not None and lock_state not in KV.BUDDY_LOCK_STATES:
        lock_state = None                       # not locked now: the table already sees it free
    _set_control(target, "Idle")

    stepper = NominalStepper(params, terrain)
    hold = sim.hold.copy()
    init = stepper.run(S, frames=0)
    boxes, poses = [init.box[0, 0]], [init.pos[0, 0]]
    flags, checks = [int(init.flags[0, 0])], [int(init.flags[0, 0])]
    states, games, commands, latched = [S.copy()], [game], [], []
    desired = {origin + 1: int(sim.prefix[0]), origin + 2: int(first)}
    presses, pushes, hits = [], [], []
    # A live continuation after its real hit/bounce must not invent another
    # downslash. These are observed, press-bound memories in the real draft.
    observed_contact=R0.run.v.get("down_hit_f") if R0.run.v.get("bounced") else None
    contact=observed_contact
    press=(R0.run.v.get("row") or {}).get("press_F") if observed_contact is not None else None
    closed = None
    prev_m = _mask_of(sim.hold.latched[0])
    for step in range(1, max_frames + 1):
        F = origin + step
        cmd = desired.get(F)
        if cmd is None:
            raise NominalUnsupported("future input pipeline incomplete")
        m, hnext = hold_one(cmd, hold)
        old, prev_fl = S.copy(), flags[-1]
        game += float(params.frame_time) * float(S[km.TS]) * float(S[km.WF_S])
        ro = stepper.run(S, m)
        S = ro.final[:, 0].copy()
        box, pos, vel, fl = ro.box[0, -1], ro.pos[0, -1], ro.vel[0, -1], int(ro.flags[0, -1])
        checkfl = fl
        dx = 0.0                                # earlier hits' knock-back first (the body this frame), as run46 World
        for q in pushes:
            if q[0] > 1e-9:
                k = min(float(params.frame_time) / float(params.fdt), q[0])
                dx += q[1] * PUSH_U * k
                q[0] -= k
        if dx:
            tb = [tb[0] + dx, tb[1], tb[2] + dx, tb[3]]
        # a press edge: down when D is latched and she was airborne, else a side swing
        if m & B["A"] and not prev_m & B["A"]:
            kind = "down" if (m & B["D"]) and not (prev_fl & km.F_GROUND) else "side"
            presses.append({"kind": kind, "F": F, "face": 1 if old[km.FACE] >= 0 else -1, "onset": None, "done": False})
            if kind == "side" and press is None and contact is None and not hits:
                raise NominalUnsupported("near press swung on the ground (a ground Slash)")
            if kind == "down" and press is None:
                press = F
        event, src = 0, None
        for p in presses:
            if p["done"]:
                continue
            if p["kind"] == "down":
                pj = p["F"]
                if F > pj + PM.ACTIVE[1]:
                    p["done"] = True
                    continue
                if F < pj + PM.ACTIVE[0]:
                    continue
                swung = bool(flags[pj - origin] & km.F_ATTACKING) or bool(flags[pj - origin + 1] & km.F_ATTACKING)
                grounded = any(flags[k - origin] & km.F_GROUND for k in range(pj, F)) or bool(fl & km.F_GROUND)
                if not swung or bool(flags[pj - origin - 1] & km.F_GROUND) or grounded:
                    continue
                if _down_meets(pos, p["face"], tb):
                    event, src = km.EV_POGO, "DownSlash"
                    p["done"] = True
                    if contact is None:
                        contact = F
                    hits.append({"kind": "down", "F": F, "press": pj, "face": p["face"]})
                    break
            else:
                if p["onset"] is None:
                    if fl & km.F_ATTACKING and not prev_fl & km.F_ATTACKING:
                        p["onset"], p["onset_face"] = F, 1 if S[km.FACE] >= 0 else -1
                    elif F > p["F"] + SIDE_ONSET_MAX:
                        p["done"] = True
                    continue
                if F > p["onset"] + 7:
                    p["done"] = True
                    continue
                if F < p["onset"] + 1:
                    continue
                cx, cy = 0.5 * (box[0] + box[2]), 0.5 * (box[1] + box[3])
                if KV.side_meets(cx, cy, p["onset_face"], tb):
                    event = km.EV_RECOIL_L if p["onset_face"] > 0 else km.EV_RECOIL_R
                    src = "Slash"
                    p["done"] = True
                    hits.append({"kind": "side", "F": F, "press": p["F"], "onset": p["onset"], "face": p["onset_face"]})
                    pushes.append([float(PUSH_STEPS), p["onset_face"]])
                    break
        if event:
            ro = stepper.run(old, m, event=event)
            S = ro.final[:, 0].copy()
            box, pos, vel, fl = ro.box[0, -1], ro.pos[0, -1], ro.vel[0, -1], int(ro.flags[0, -1])
        commands.append(int(cmd))
        latched.append(int(m))
        prev_m = int(m)
        hold = hnext
        boxes.append(np.array(box))
        poses.append(np.array(pos))
        flags.append(fl)
        checks.append(checkfl)
        states.append(S.copy())
        games.append(game)
        # the model observation of frame F
        s["f"], s["dt"] = F, float(params.frame_time)
        s["ev"] = [] if src is None else [{"f": F, "k": "hit", "d": {"type_key": "Song Heavy Sentry", "iid": iid, "ent": iid, "src": src}}]
        _set_body(target, tb, dx)
        _set_control(target, "Idle")
        if buddy is not None and lock_state is not None:
            _set_control(buddy, lock_state if game < buddy_lock_until else POST_LOCK_STATE)
        _hero(s, S, box, pos, vel, fl)
        _clear_short_bounce(s)
        next_key = desired.get(F + 1)
        if next_key is None:
            raise NominalUnsupported("future input pipeline incomplete")
        R.observation_cutoff = F
        fsim = ChainSim(S, np.array([next_key], np.int64), hold, params, terrain, F, F)
        future_bombs=None
        if bombs is not None:
            future_bombs=np.asarray(bombs,float).copy()
            if future_bombs.size:
                future_bombs[:,4:6]-=F-origin
        mask = R.step(F, s, bool(fl & km.F_GROUND), bool(s["hero"].get("hero_accepting_input", True)),
                      t_game=game, sim=fsim, bombs=future_bombs)
        if mask is None:
            done = R.done[-1] if R.done else None
            if done is None or done.closed not in ("done", "handback"):
                why = None if done is None else done.v.get("why")
                raise NominalUnsupported(f"vault closed without a handback at {F}: {why}")
            closed = {"kind": done.closed, "why": done.v.get("why"), "link": done.lid,
                      "closed_f": done.v.get("closed_f"), "bounced": done.v.get("bounced"),
                      "unlocked_hit_f": done.v.get("unlocked_hit_f"), "n_side": done.v.get("n_side", 0)}
            break
        desired[F + 2] = int(mask)
    if closed is None:
        raise NominalUnsupported("vault did not close within max_frames (the horizon is not a handback)")
    if contact is None:
        raise NominalUnsupported("no modeled down-slash contact")
    through = origin + len(commands)
    if through + 1 not in desired:
        raise NominalUnsupported("missing next queued command at the close")
    assumptions = {"basis": "nominal HERO2 closed loop of the bound vault table; model observations only, never receipts",
                   "target_reaction": "UNKNOWN: the target is held Idle; modeled side hits push its body 0.48 u",
                   "buddy_lock": {"until_game_s": float(buddy_lock_until), "state_while_locked": lock_state,
                                  "state_after": POST_LOCK_STATE, "source": "caller's locked-move clock, not a recording"},
                   "contacts": hits, "close": closed, "admission": "none (stage approach; all bodies and hazards stay checked)"}
    return NominalPath(origin, "approach", np.asarray(commands, np.int64), np.asarray(latched, np.int64),
                       np.stack(states, axis=1), np.asarray(boxes), np.asarray(poses), np.asarray(flags, np.int64),
                       np.asarray(checks, np.int64), np.asarray(games), hold, s, R, int(desired[through + 1]),
                       "handback", press, contact, assumptions, None, first_draft)
