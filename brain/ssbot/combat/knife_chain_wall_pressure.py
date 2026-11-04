"""Finite wall-side landing or one conditional downslash, never a safety gate.

The caller owns the real bounce, move identity, all-owner geometry, continuation
admission and sending.  This module reads only the current body/terrain and the
actual S0, HoldFilter and queued prefix.  It never injects a future pogo event.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from types import SimpleNamespace as NS

import numpy as np

from ssbot.knowledge import kinematics as K
from . import pogo_model as PM
from .forum_v2 import FOCUS_M
from .knife_chain_air import body_box, complete_hf, model_path, _contact_mask
from .knife_chain_format import MASK_NAMES as B
from .knife_chain_nominal import NominalPath
from .knife_chain_vault import strike_program


@dataclass(frozen=True)
class PressureProposal:
    kind: str
    F0: int
    commands: np.ndarray
    path: NominalPath
    contact_frame: int | None
    landing_frame: int | None
    floor_span: tuple[float, float] | None
    recipe: str
    press_frame: int | None = None

    def mask_at(self, F):
        """Only the verified absolute row; an ended row needs a new decision."""
        i = F - self.F0
        return int(self.commands[i]) if type(i) is int and 0 <= i < len(self.commands) else None


def _terrain(sim, body, wall_side):
    """None = unknown; span None in a result = observed floor/wall cannot fit."""
    p = sim.params
    try:
        h = np.asarray(sim.terrain.hseg, float).reshape(-1, 3)
        v = np.asarray(sim.terrain.vseg, float).reshape(-1, 3)
        slopes = np.asarray(sim.terrain.slopes, float).reshape(-1, 4)
        if (not len(h) or not len(v) or not np.isfinite(h).all() or not np.isfinite(v).all()
                or not np.isfinite(slopes).all()
                or np.any(h[:, 1] >= h[:, 2]) or np.any(v[:, 1] >= v[:, 2])):
            return None
        floors = h[h[:, 0] <= body[1] + p.skin + 1e-7]
        if not len(floors):
            return None
        cx = float((body[0] + body[2]) / 2)
        known_empty = None
        for y in sorted(set(float(q) for q in floors[:, 0]), reverse=True):
            bottom, top = y + p.skin, y + p.skin + p.foot + p.head
            walls = [float(x) for x, a, b in v
                     if (x - cx) * wall_side > 0 and a < top and b > bottom]
            if not walls:
                continue
            wall = min(walls, key=lambda x: (x - cx) * wall_side)
            edge = body[2] if wall_side > 0 else body[0]
            corridor = sorted((edge, wall))
            rows = sorted((float(a), float(b)) for fy, a, b in floors if abs(fy - y) <= 1e-7
                          and a < corridor[1] and b > corridor[0])
            if not rows:
                continue  # an unrelated high platform cannot erase this gap's floor
            merged = []
            for a, b in rows:
                if merged and a <= merged[-1][1] + 1e-7:
                    merged[-1][1] = max(merged[-1][1], b)
                else:
                    merged.append([a, b])
            if wall_side > 0:
                lo, hi = body[2] + FOCUS_M + p.half_width, wall - p.skin - p.half_width
            else:
                lo, hi = wall + p.skin + p.half_width, body[0] - FOCUS_M - p.half_width
            spans = [(max(lo, a + p.half_width), min(hi, b - p.half_width)) for a, b in merged]
            spans = [(a, b) for a, b in spans if b - a > 1e-7]
            if spans:
                span = max(spans, key=lambda q: q[1] - q[0])
                # Remote sloping scenery does not invalidate an axis-supported
                # gap. A slope crossing THIS full standing box is unknown.
                if any(min(a, c) < span[1] + p.half_width and max(a, c) > span[0] - p.half_width
                       and min(b, d) < top and max(b, d) > bottom for a, b, c, d in slopes):
                    return None
                return span, y, wall, v
            if known_empty is None:
                known_empty = (None, y, wall, v)
        return known_empty
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def _path(sim, state, game, plan, commands, *, press=None, contact=None):
    f = state["f"]
    proxy = NS(iid=plan.iid, move=plan.move, origin=f, entry_k=0,
               press_k=None if press is None else press - f, contact_frame=contact)
    return model_path(sim, proxy, np.asarray(commands, np.int64), game)


def _wall_free(path, sim, walls):
    """No wall slide/cling/contact anywhere, including the immutable prefix."""
    z, p = path.states, sim.params
    if np.any(np.abs(z[[K.CLING, K.WSIDE, K.WTOUCH]]) > 1e-7):
        return False
    pad = p.skin + p.wall_contact
    for x, a, b in walls:
        vertical = (z[K.PY] - p.foot < b) & (z[K.PY] + p.head > a)
        touching = np.abs(z[K.PX] - x) <= p.half_width + pad + 1e-7
        if np.any(vertical & touching):
            return False
    return True


def _toward(x, aim):
    return B["R"] if x < aim else B["L"] if x > aim else 0


def _align_row(sim, state, game, plan, aim, frames, *, span=None, walls=()):
    """One physical-root release seed and at most three adjacent release rows.

    FixedUpdate moves with the previous Update's MOVE. The desired row starts
    after the immutable prefix, and HoldFilter can delay its neutral edge too.
    Render interpolation is therefore not a release-clock measurement.
    """
    direction = _toward(float(np.asarray(sim.start).reshape(K.K)[K.PX]), aim)
    commands = np.full(frames, direction, np.int64)
    if direction:
        probe = _path(sim, state, game, plan, commands)
        px = probe.states[K.PX]
        reached = (px >= aim) if direction == B["R"] else (px <= aim)
        at = np.flatnonzero(reached & (np.arange(len(reached)) >= 1))
        if len(at):
            prefix = len(sim.prefix)
            cut = max(0, min(frames, int(at[0]) - prefix - 1))
            seeded = commands.copy()
            seeded[cut:] = 0
            from .holdfilter import hold_filter_jit
            latched, _ = hold_filter_jit(np.r_[sim.prefix, seeded][None], sim.hold)
            held = np.flatnonzero(latched[0] & direction)
            actual_release = int(held[-1]) + 1 if len(held) else 0
            cut = max(0, cut - max(0, actual_release - (prefix + cut)))
            cuts = sorted({max(0, min(frames, cut + delta)) for delta in (-1, 0, 1)})
            rows = np.full((len(cuts), frames), direction, np.int64)
            for i, release in enumerate(cuts):
                rows[i, release:] = 0
            # This is the sole bounded neighbor batch, not a timing pool.
            roll = sim.roll(rows)
            p = sim.params
            scores = []
            for i, release in enumerate(cuts):
                xy = roll.phys[i]
                free = not np.any(np.abs(roll.final[[K.CLING, K.WSIDE, K.WTOUCH], i]) > 1e-7)
                for x, a, b in walls:
                    touch = (np.abs(xy[:, 0] - x) <= p.half_width + p.skin + p.wall_contact + 1e-7)
                    vertical = (xy[:, 1] - p.foot < b) & (xy[:, 1] + p.head > a)
                    if np.any(touch & vertical):
                        free = False
                x_end = float(roll.final[K.PX, i])
                inside = (span is not None and span[0] <= x_end <= span[1]
                          and bool(roll.flags[i, -1] & K.F_GROUND)
                          and abs(roll.final[K.VX, i]) <= 1e-6)
                scores.append((not free, span is not None and not inside, abs(x_end - aim), release))
            commands = rows[min(range(len(cuts)), key=lambda i: scores[i])].copy()
    return commands


def _side(sim, state, game, plan, span, floor_y, walls, frames):
    commands = _align_row(sim, state, game, plan, sum(span) / 2, frames, span=span, walls=walls)
    path = _path(sim, state, game, plan, commands)
    p, z = sim.params, path.states
    stable = ((z[K.GROUND] > 0) & (z[K.PX] >= span[0]) & (z[K.PX] <= span[1])
              & (np.abs(z[K.PY] - (floor_y + p.skin + p.foot)) <= 1e-5)
              & (np.abs(z[K.VX]) <= 1e-6))
    # Three neutral grounded samples prove the finite row ends in the gap.
    for j in range(2, len(stable) - 2):
        if stable[j:j + 3].all() and not commands[j - 2:j + 1].any():
            row = commands[:j + 1].copy()
            path = _path(sim, state, game, plan, row)
            if not _wall_free(path, sim, walls):
                return None
            path = replace(path, stage="approach", end="handback", assumptions={**path.assumptions,
                "basis": "current body/wall/floor; fixed centre approach then neutral",
                "release_basis": "physical root; actual prefix/HF; at most three adjacent releases in one batch",
                "floor_span": list(span), "full_width_floor_support": True,
                "all_owner_safety": "caller", "future_pogo_injected": False})
            return PressureProposal("side", state["f"] + 2, row, path, None,
                                    state["f"] + j, span, "centre_then_neutral")
    return None


def _stomp(sim, state, game, plan, body, wall_side, wall, walls, frames, floor_span=None):
    S = np.asarray(sim.start).reshape(K.K)
    if S[K.GROUND] > 0 or S[K.MODE] not in (K.M_NORMAL, K.M_GLIDE, K.M_DS_ANTIC, K.M_DS_SPIKE):
        return None
    # Keep the existing direct suffix honest: do not improvise a glide cancel.
    if S[K.MODE] == K.M_GLIDE:
        return None
    mid = float((body[0] + body[2]) / 2)
    aim = float((mid + (body[2] if wall_side > 0 else body[0])) / 2)
    p = sim.params
    aim = min(aim, wall - p.half_width - p.skin - p.wall_contact) if wall_side > 0 else max(
        aim, wall + p.half_width + p.skin + p.wall_contact)
    if (aim - mid) * wall_side < 0:
        return None
    aligned = _align_row(sim, state, game, plan, aim, frames, walls=walls)
    recipes = [("coast", np.zeros(frames, np.int64)), ("align_then_neutral", aligned)]
    if abs(S[K.VX]) > 1e-6:
        brake = np.zeros(frames, np.int64)
        brake[:1] = B["L"] if S[K.VX] > 0 else B["R"]
        recipes.append(("one_brake_then_coast", brake))
    seen = set()
    for name, drift in recipes:
        key = drift.tobytes()
        if key in seen:
            continue
        seen.add(key)
        coast = _path(sim, state, game, plan, drift)
        # A real bounce may still carry the PREVIOUS swing/cooldown. Its
        # finite coast must recover before scheduling a new press; never count
        # that old swing as the next stroke's contact.
        ready = ((coast.states[K.MODE] == K.M_NORMAL) & (coast.states[K.ATTACKING] <= 0)
                 & (coast.states[K.ATK_CD] <= 1e-7) & (coast.states[K.GROUND] <= 0))
        free = np.flatnonzero(ready & (np.arange(len(ready)) >= 1))
        if not len(free):
            continue
        first_press = max(3, int(free[0]) + 1)
        boxes = np.broadcast_to(body, (len(coast.pos), 4))
        meets = _contact_mask(coast.pos, boxes)
        rear = (coast.pos[:, 0] - mid) * wall_side >= 0
        airborne = np.cumsum((coast.flags & K.F_GROUND) != 0) == 0
        possible = np.flatnonzero(meets & rear & airborne &
                                  (np.arange(len(meets)) >= first_press + PM.ACTIVE[0]))
        if not len(possible):
            continue
        # One geometry-derived press for this fixed recipe, no timing search.
        press = max(first_press - 2, int(possible[0]) - 2 - 4)
        if press + PM.ACTIVE[1] + 2 >= frames:
            continue
        row = strike_program(state["f"] + 2, 0, press, 1, 0)
        commands = drift.copy()
        n = min(len(row["masks"]), frames)
        commands[:n] |= np.asarray(row["masks"][:n], np.int64) & ~(B["L"] | B["R"])
        path = _path(sim, state, game, plan, commands, press=row["press_F"])
        prev = np.r_[bool(sim.hold.latched[0, B["A"].bit_length() - 1]), (path.latched[:-1] & B["A"]) != 0]
        edges = np.flatnonzero(((path.latched & (B["D"] | B["A"])) == (B["D"] | B["A"])) & ~prev)
        edges = edges[edges >= 1]
        if not len(edges):
            continue
        edge = int(edges[0]) + 1
        # Wanderer keeps MODE=NORMAL during its nail downslash; MODE=DS_* is
        # not its acceptance signal. Require a NEW modeled down attack onset.
        ds = ((path.flags & K.F_ATTACKING) != 0) & (path.states[K.ATK_PDIR] == 2)
        reset = np.r_[False, path.states[K.ATK_T, 1:] < path.states[K.ATK_T, :-1] - 1e-7]
        onsets = np.flatnonzero(ds & (~np.r_[False, ds[:-1]] | reset) & (np.arange(len(ds)) >= edge))
        if not len(onsets):
            continue
        onset = int(onsets[0])
        actual = _contact_mask(path.pos, np.broadcast_to(body, (len(path.pos), 4)))
        for j in range(onset + PM.ACTIVE[0], min(onset + PM.ACTIVE[1] + 1, len(actual))):
            if (path.flags[onset - 1:j + 1] & K.F_GROUND).any():
                break
            if not (path.flags[j] & K.F_ATTACKING) or not actual[j] or (path.pos[j, 0] - mid) * wall_side < 0:
                continue
            offered = commands[:j - 1].copy()
            contact = state["f"] + j
            final = _path(sim, state, game, plan, offered, press=state["f"] + onset, contact=contact)
            if not _wall_free(final, sim, walls):
                break
            final = replace(final, stage="strike", end="decision", contact_frame=contact, assumptions={**final.assumptions,
                "basis": "fixed coast/brake recipe; shared downslash suffix; observed body held still",
                "conditional_contact": True, "contact_shapes": "both slash alternations and both facings",
                "observed_floor_span": None if floor_span is None else list(floor_span),
                "all_owner_safety": "caller", "future_pogo_injected": False})
            return PressureProposal("stomp", state["f"] + 2, offered, final, contact, None, floor_span,
                                    name, state["f"] + onset)
    return None


def propose(sim, state, game, intent, plan, *, max_frames=96, allow_landing=True):
    """A finite motion/contact witness; None also covers unknown observations.

    intent is the existing tactics.modes.WallPressure.  Its projected span is
    deliberately not trusted: the complete standing geometry is rebuilt here.
    allow_landing=False tries the rear-air recipe after a caller rejects the
    landing path; the returned floor_span still reports known standing space.
    """
    try:
        f = state["f"]
        if (type(f) is not int or type(max_frames) is not int or not 16 <= max_frames <= 160
                or type(allow_landing) is not bool
                or sim.fo != f or sim.f != f or len(sim.prefix) != 1 or not complete_hf(state)
                or not np.isfinite(game) or getattr(intent, "target", None) != plan.iid
                or type(getattr(intent, "wall_side", None)) is not int or intent.wall_side not in (-1, 1)
                or getattr(intent, "kind", None) not in ("side", "stomp")):
            return None
        S = np.asarray(sim.start, float).reshape(K.K)
        if not np.isfinite(S).all() or np.any(np.abs(S[[K.CLING, K.WSIDE, K.WTOUCH]]) > 1e-7):
            return None
        hero = state.get("hero") or {}
        if hero.get("stunned") or hero.get("health", 0) <= 0 or "Wall" in str((hero.get("anim") or {}).get("clip", "")):
            return None
        enemy = next((e for e in state.get("ents") or () if e.get("iid") == plan.iid), None)
        if enemy is None or enemy.get("is_dead") or enemy.get("hp", 1) <= 0:
            return None
        body = None if enemy is None else body_box(enemy)
        if body is None or body[0] >= body[2] or body[1] >= body[3]:
            return None
        geometry = _terrain(sim, body, intent.wall_side)
        if geometry is None:
            return None
        span, floor, wall, walls = geometry
        if span is not None and allow_landing:
            return _side(sim, state, game, plan, span, floor, walls, max_frames)
        return _stomp(sim, state, game, plan, body, intent.wall_side, wall, walls, max_frames, span)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return None
