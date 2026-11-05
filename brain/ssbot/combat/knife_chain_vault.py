"""Idle-Clapper vault table primitives: near pogo / far Clawline, shared exit.

The existing v0 interpreter runs this family. Callers must supply the selected
entry request; importing/loading this module never chooses a target or starts a
run. The manual-air B2 owner can load it with the explicit default-off VAULT
switch. Candidate arbitration, geometry and send/acceptance stay in that owner.

Primitive implementation and table derive from the reviewed Opus task46
prototype. Its evidence is nominal HERO2, not actual game action acceptance or
an opponent-reaction model. Observed target movement or a hit after the buddy
is free hands control back instead of blindly playing a three-slash tail.
"""
from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path

import numpy as np

from ssbot.combat import claw_strike as CS
from ssbot.combat import dslash
from ssbot.combat import knife_chain_eval as CV
from ssbot.combat import knife_chain_slam as KS
from ssbot.combat import pogo_model as PM
from ssbot.combat import slam_play as SP
from ssbot.combat.knife_chain_format import MASK_NAMES as B, ChainVocabulary
from ssbot.combat.knife_chain_observations import pogo_marker
from ssbot.knowledge.attack_shapes import AttackTable, polys_overlap

CHAIN = "vault_idle"
VOCAB = ChainVocabulary(clocks=frozenset({"antic", "mask", "press", "claw_press", "ctrl", "bounce"}),
                        directions=frozenset())
LITERALS = frozenset({"<", "<=", ">", ">="})
TARGET_STATES = ("Idle", "Walk", "Dmg Attack")      # a hit target passes Dmg Attack; anything else is a move
BUDDY_LOCK_STATES = SP.TWO_JUMP_ST                  # the other's jump-cast states before landing (slam_play.py:172)
HX, HY, FT = 0.25, 1.0395, 1.0 / 60.0               # her collider half sizes (kinematics.py:119), the frame
GRAV = 72.0                                         # slam_play.GRAV: her vy falls 1.2 per frame in the air
_ATK = AttackTable.load("Wanderer")


def _key(d):
    return B["R"] if d > 0 else B["L"]


def _body(e):
    """The target's body box (x0, y0, x1, y1) from its enabled collider in this STATE; None when absent."""
    from .knife_chain_air import body_box
    return body_box(e)  # real body names include numbered variants, e.g. (2)/(3)


def _rect(b):
    return np.array([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]], float)


def side_meets(cx, cy, face, box):
    """Both side-slash polygons (Slash, AltSlash: the alternation is unknown) at her centre facing face meet box."""
    q, qs = _rect(box), np.array([0, 4], np.int64)
    return all(polys_overlap(*_ATK[slot].world(cx, cy, face), q, qs) for slot in ("normal", "alt"))


def _centre_next(x):
    """Her box centre at the end of frame f + 1, the state the mask frame F = f + 2 starts from (the keys in flight
    for f + 1: run.sent; knife_chain_slam.v_x_at_mask's rule with lag 0), and the vertical one-frame projection."""
    cx = KS.v_x_at_mask(x, x.cfg["AIR_U"])
    b = x.obs.h.get("box")
    cy = 0.5 * (float(b[1]) + float(b[3])) if b else x.obs.y_pos
    vy = x.obs.vy
    if not x.obs.ground:
        cy += (vy - GRAV * FT) * FT
    return cx, cy


def _atk_ready_next(x):
    cd = x.obs.atk_cd
    return cd is not None and cd - FT <= 1e-9


class VaultAnchor:
    """Run life of the vault table.  open(request) comes from Root's native arbitration (not from this table):
    {"iid": target, "over_dir": +1 / -1 (the side she ends on), "near": {"h", "p", "before"} or None,
     "far": {"d", "p"} or None, "nogo": [[x_lo, x_hi], ...] (ground x she must not walk into: the lit circle
     footprint + margin, from the field), "x_end": the far-edge x she must pass (for the bomb path span)}."""

    def __init__(self, chains, cfg):
        self.chains, self.cfg = chains, cfg
        self.var_defaults = dict(chains[CHAIN].vars)
        self.request = None

    def reset(self, R):
        R.run = None
        R.done = []
        self.request = None
        self.refused = []

    def open(self, request):
        self.request = deepcopy(request)

    def close(self, x, kind, why):
        R, run = x.R, x.run
        if run is None:
            return
        run.closed = kind
        run.v["why"] = run.v.get("why") or why
        run.v["closed_f"] = x.obs.f if x.obs is not None else None
        R.done.append(run)
        R.run = None
        x.run = None

    def reopen_wanted(self, why):
        return False

    def read_value(self, x, name, value):
        return None

    def clock(self, x, name):
        v, F = x.v, x.obs.F
        if name == "mask":
            return F
        if name == "antic":
            return F - v["F_open"]
        if name == "press":
            r = v.get("row")
            return None if r is None else F - r["press_F"]
        if name == "claw_press":
            return None if v.get("cs") is None else F - v["cs"].f_press
        if name == "ctrl":
            return None if v.get("f_ctrl") is None else x.obs.f - v["f_ctrl"]
        if name == "bounce":
            return None if v.get("bounce_f") is None else x.obs.f - v["bounce_f"]
        raise KeyError(name)

    def _observe(self, x):
        """Press-bound observation memory (knife_chain_observations: a controller keeps the press-bound hit itself):
        the first target DownSlash hit at or after the down press, the bounce when that hit and pogo_marker are both
        seen, every other hit on the target, and whether a hit came while the other Clapper was out of its jump cast."""
        v, s, f = x.v, x.obs.s, x.obs.f
        others = [o for o in SP.clappers(s) if o.get("iid") != v["iid"]]
        locked = any(SP.control(o)[0] in BUDDY_LOCK_STATES for o in others)
        v["buddy_locked"] = locked
        row = v.get("row")
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            src = str(d.get("src") or "")
            if ev.get("k") != "hit" or (d.get("ent") if d.get("ent") is not None else d.get("iid")) != v["iid"]:
                continue
            if "Harpoon" in src:
                continue
            ef = ev.get("f", f)
            if type(ef) is not int or ef > f:
                continue
            if "DownSlash" in src:
                if row is not None and ef >= row["press_F"] and v.get("down_hit_f") is None:
                    v["down_hit_f"] = ef
            elif ef not in v.get("side_hits", ()):
                v["side_hits"] = [*v.get("side_hits", []), ef]
            if not locked and v.get("unlocked_hit_f") is None:
                v["unlocked_hit_f"] = ef
        if not v.get("bounced") and v.get("down_hit_f") is not None and pogo_marker(s):
            v["bounced"], v["bounce_f"] = True, f

    def step(self, R, f, s, ground, accepting, t_game, skip, sim, guard, bombs):
        t = f / 60.0 if t_game is None else float(t_game)
        run = R.run
        if run is None:
            if self.request is None:
                return None
            req, self.request = self.request, None
            e = next((o for o in SP.clappers(s) if o.get("iid") == req["iid"]), None)
            if e is None:
                self.refused.append([f, "target absent"])
                return None
            v = dict(self.var_defaults)
            v.update(iid=req["iid"], face=1 if e.get("flipX") else -1, over_dir=int(req["over_dir"]), req=req,
                     F_open=f + KS.SEND, f_open=f, hp0=int((s.get("hero") or {}).get("health") or 0), side_hits=[])
            run = R.run = CV.Run(CHAIN, self.chains[CHAIN].start, v)
        v = run.v
        e = next((o for o in SP.clappers(s) if o.get("iid") == v["iid"]), None)
        if e is None:
            self.close(CV.X(R, run, None), "abort", "vault: target dead or absent")
            return None
        st, tin = SP.control(e)
        obs = KS.Obs(f, s, ground, accepting, t, sim, guard, bombs, e, st, tin)
        x = CV.X(R, run, obs)
        self._observe(x)
        if obs.hp < v["hp0"]:
            self.close(x, "abort", "vault: hurt")
            return None
        return R.eval_link(x)


def _row(F0, n, keys):
    """A key row from mask frame F0: masks[i] for mask frame F0 + i."""
    return {"F0": F0, "masks": [int(m) for m in keys[:n]]}


def distance_entry(cfg, hero, target_pos, box, direction, attack_cooldown):
    """The manual distance table (the person 11-02: by distance, no whole-skill pre-validation): a near jump when her
    box gap is inside NEAR_RECIPE box_gap and the roots are closer than HOP_RECIPE's range, else a small-hop hook
    inside HOP_RECIPE root_distance with the harpoon and silk. (kind, request part, gap, root distance); kind None
    outside both. Shared by the native entry and the ground approach so both read one table."""
    hb, hp = hero.get("box"), hero.get("pos")
    gap = float(box[0] - hb[2] if direction > 0 else hb[0] - box[2])
    root_distance = abs(float(target_pos[0]) - float(hp[0]))
    near, far = cfg["NEAR_RECIPE"], cfg["HOP_RECIPE"]
    if root_distance < far["root_distance"][0] and near["box_gap"][0] <= gap <= near["box_gap"][1]:
        press = near["close_press"] if gap < near["close_gap"] else near["press"]
        cd = (hero.get("tm") or {}).get("atk_cd")
        if type(cd) in (int, float) and math.isfinite(cd) and 0 <= cd <= attack_cooldown + 1e-6:
            # Start the jump now; wait for the CURRENT swing's cooldown in
            # this same row, rather than declining the whole escape action.
            press = max(press, math.ceil(cd * 60) - 1)
        return "near", {"h": near["hold"], "p": press, "before": near["before"]}, gap, root_distance
    silk = hero.get("silk")
    if (far["root_distance"][0] <= root_distance <= far["root_distance"][1]
            and (hero.get("can") or {}).get("harpoon") is True and type(silk) in (int, float)
            and math.isfinite(silk) and silk >= 1):
        return "hop_hook", {k: far[k] for k in ("hop", "claw_after", "d", "p")}, gap, root_distance
    return None, None, gap, root_distance


def strike_program(F0,hold,press,direction,drift):
    """One shared jump/downslash row, including the hook's no-jump suffix."""
    m=np.zeros(max(hold,press+dslash.POST_F),np.int64)
    m[:hold]|=B["J"];m[:drift]|=_key(direction)
    dslash.strike(m,press);m[press:]|=_key(direction)
    return _row(F0,len(m),m)|{"press_F":F0+press}


def register(P):
    """The missing vault primitives, on a copy of the slam registry (knife_chain_fixed_hook.register's pattern)."""

    def target_ok(x):
        return x.obs.st in ("Idle", "Walk")

    def side_ok(x):
        # she starts on the near side and ends on over_dir's side of the target
        return (x.obs.cx - x.obs.hx) * x.v["over_dir"] > 0

    @P.guard("vault_approach_entry", doc="Task 179: the request asks for a ground approach; ground, accepting, target "
                                         "Idle / Walk, she is on the near side")
    def approach_entry(x):
        return bool(x.v["req"].get("approach") and x.obs.ground and x.obs.accepting and target_ok(x) and side_ok(x))

    @P.action("vault_approach_recipe",
              doc="Task 179 ground approach toward the far side (the person 11-05: over the walking one, never the "
                  "corner): ends when the other Clapper is out of its jump, she leaves the ground or input, the target "
                  "is no longer ahead / Idle / Walk or the approach outlives its frames; inside the manual distance "
                  "table it names that entry (near / hop hook) for the following try. Running keys only; no jump, "
                  "dash or hit claim, and every tick still passes the native current-step gate")
    def approach_recipe(x):
        v, o = x.v, x.obs
        a = v["req"].get("approach")
        if not a:
            return {"do": "abort", "why": "vault approach: no approach request"}
        if not v.get("buddy_locked"):
            return {"do": "abort", "why": "vault approach: the other Clapper's jump is over"}
        if not o.ground or not o.accepting:
            return {"do": "abort", "why": "vault approach: off the ground or input not accepted"}
        if not target_ok(x) or not side_ok(x):
            return {"do": "abort", "why": "vault approach: the target is no longer ahead and Idle / Walk"}
        if o.f - v["f_open"] > int(a["max_f"]):
            return {"do": "abort", "why": "vault approach: no table range within its frames"}
        box = _body(o.e)
        pos = o.e.get("pos")
        if box is None or not pos:
            return {"do": "abort", "why": "vault approach: target body unknown"}
        kind, part, _, _ = distance_entry(x.cfg, o.h, pos, box, v["over_dir"], o.sim.params.attack_cooldown)
        if kind == "near":
            v["req"] = {**v["req"], "near": part, "far": None}
        elif kind == "hop_hook":
            v["req"] = {**v["req"], "near": None, "far": part}
        return None

    @P.guard("vault_near_entry", doc="the request has a near row; ground, accepting, target Idle / Walk, she is on the "
                                     "near side, the attack is ready by the row's press")
    def near_entry(x):
        n = x.v["req"].get("near")
        if not n or not x.obs.ground or not x.obs.accepting or not target_ok(x) or not side_ok(x):
            return False
        cd = x.obs.atk_cd
        return cd is not None and cd - (int(n["p"]) + 1) * FT <= 1e-9

    @P.guard("vault_far_entry", doc="the request has a far plan; accepting, silk, can.harpoon, the press box bottom "
                                    "<= floor + 3.3 (claw_strike.py:114) and the body front <= 10.2 u (:116)")
    def far_entry(x):
        n = x.v["req"].get("far")
        o = x.obs
        if not n or not o.accepting or o.silk < 1 or (o.h.get("can") or {}).get("harpoon") is not True:
            return False
        if not target_ok(x) or not side_ok(x) or KS.g_harpoon(x):
            return False
        box = _body(o.e)
        if box is None or o.box_bottom > 3.3:
            return False
        front = box[0] if x.v["over_dir"] > 0 else box[2]
        return abs(front - o.hx) <= 10.2

    @P.action("vault_near_plan", doc="the planner's dslash ground row (J h, the key toward before the press for 'T', "
                                     "dslash.strike at p, the key toward kept on): var.row from the first mask frame")
    def near_plan(x):
        if x.v["row"] is not None:
            return
        n = x.v["req"]["near"]
        h, p = int(n["h"]), int(n["p"])
        F0 = x.obs.F
        x.v["row"] = strike_program(F0,h,p,x.v["over_dir"],p if n.get("before","T")=="T" else 0)|{"name":f"DS j{h}p{p}{n.get('before','T')}"}

    @P.action("vault_far_plan", doc="the requested fixed hop/Clawline, using claw_strike.plan_mask")
    def far_plan(x):
        if x.v["cs"] is not None:
            return
        F0 = x.obs.F
        req=x.v["req"]["far"]
        hop,after=int(req.get("hop",0)),int(req.get("claw_after",1))
        if hop<0 or (hop and after<max(3,hop)):
            return {"do":"abort","why":"vault: CLAW must allow the observed small hop before dispatch"}
        x.v.update(cs=CS.CsPlan(F0, hop, F0 + after, None),
                   cs_toward=x.v["over_dir"])

    @P.action("vault_far_strike", doc="from the observed control: the drift key toward d frames from the first mask "
                                      "frame, the down slash on control's mask p (dslash.strike), the key toward on")
    def far_strike(x):
        if x.v["row"] is not None:
            return
        n = x.v["req"]["far"]
        d, p = int(n["d"]), int(n["p"])
        x.v["f_ctrl"] = x.obs.f
        F0 = x.obs.F
        press_F = x.obs.f + 1 + p                  # mask index p after the control STATE frame
        L = press_F - F0 + dslash.POST_F
        if press_F <= F0 or L <= 0:
            return {"do": "abort", "why": "vault far: the planned press is not after the first mask frame"}
        x.v["row"] = strike_program(F0,0,press_F-F0,x.v["over_dir"],d)|{"name":f"CS d{d}p{p}"}

    @P.gen("vault_row_mask", doc="var.row's keys at the mask frame (none past the row)")
    def row_mask(x, m):
        r = x.v["row"]
        i = x.obs.F - r["F0"]
        return m | (r["masks"][i] if 0 <= i < len(r["masks"]) else 0)

    @P.guard("vault_bounced", doc="observed: a target DownSlash hit at or after the press and pogo_marker "
                                  "(knife_chain_observations.py; the B2 rule, knife_chain_b2.py:380-396)")
    def bounced(x):
        return bool(x.v.get("bounced"))

    @P.guard("vault_miss_hook_ready",doc="one observed miss may branch to an available in-air hook")
    def miss_hook_ready(x):
        if (x.v.get("fallback_hook") or x.v.get("down_hit_f") is not None or x.obs.ground or
                not x.obs.accepting or not side_ok(x)):return False
        box=_body(x.obs.e)
        return bool(box is not None and x.obs.h.get("can",{}).get("harpoon") is True and
                    x.obs.silk>=1 and x.obs.box_bottom<=3.3 and
                    abs((box[0] if x.v["over_dir"]>0 else box[2])-x.obs.hx)<=CS.CsCfg().reach)

    @P.action("vault_miss_hook_plan",doc="same Run: preserve failed near press, hook from actual airborne state")
    def miss_hook_plan(x):
        v=x.v;r=x.cfg["HOP_RECIPE"]
        v["near_miss_press"]=v["row"]["press_F"]
        v.update(fallback_hook=True,row=None,cs=None,f_ctrl=None)
        v["req"]={**v["req"],"near":None,"far":{"hop":0,"claw_after":1,"d":r["d"],"p":r["p"]}}

    @P.guard("vault_no_bounce", doc="the down slash's active frames (pogo_model.ACTIVE) and the observation lead are "
                                    "over without an observed bounce: the miss branch")
    def no_bounce(x):
        r = x.v["row"]
        # Opt1 permits the real input to apply two frames late. Do not call
        # that still-active swing a miss before its last possible hit report.
        return r is not None and not x.v.get("bounced") and x.obs.f > r["press_F"] + PM.ACTIVE[1] + 3

    @P.guard("vault_clear_of_far_edge", doc="her centre at the end of frame f + 1 is past the observed body's far "
                                            "edge by u")
    def clear_far(x, u):
        box = _body(x.obs.e)
        if box is None:
            return False
        d = x.v["over_dir"]
        far = box[2] if d > 0 else box[0]
        cx, _ = _centre_next(x)
        return (cx - far) * d >= u

    @P.guard("vault_landed_early", doc="on the ground again more than 2 frames after the bounce, before the far edge")
    def landed_early(x):
        b = x.v.get("bounce_f")
        return x.obs.ground and b is not None and x.obs.f > b + 2

    @P.guard("vault_over_body", doc="her centre at the end of frame f + 1 within the observed body's x span widened by "
                                    "her half width, with her box bottom at or above the body top: where the down-slash "
                                    "bounce leaves her; a hook bounce (no pogo invulnerability) starts over only from "
                                    "here, re-checked from the actual body and hero (#150b, #152)")
    def over_body(x):
        box = _body(x.obs.e)
        if box is None:
            return False
        cx, cy = _centre_next(x)
        return bool(box[0] - HX <= cx <= box[2] + HX and cy - HY >= box[3])

    @P.gen("vault_air_slash", doc="once in the fall: the key toward the body + A for 2 frames (a press edge) when the "
                                  "attack is ready and both side polygons meet the observed body from her next state")
    def air_slash(x, m):
        v = x.v
        F = x.obs.F
        back = -v["over_dir"]
        if v.get("air_press_F") is None:
            box = _body(x.obs.e)
            if box is None or not _atk_ready_next(x):
                return m
            cx, cy = _centre_next(x)
            if not side_meets(cx, cy - x.cfg["AIR_Y_OFF"], back, box):
                return m
            v["air_press_F"] = F
        p = v["air_press_F"]
        return m | (_key(back) | B["A"] if p <= F < p + 2 else 0)

    @P.gen("vault_ground_slash", doc="ground: A for 2 frames on a press edge when ready, facing the body and both side "
                                     "polygons meet it; else one walk step toward it that keeps body + margin and the "
                                     "no-go spans; no key during a swing")
    def ground_slash(x, m):
        v, o = x.v, x.obs
        F = o.F
        back = -v["over_dir"]
        p = v.get("g_press_F")
        if p is not None:
            if F < p + 2:
                return m | B["A"]
            hit = any(h >= p for h in v.get("side_hits", ()))
            if not hit and F < p + x.cfg["SWING_F"]:
                return m                                    # the swing (#136: A A, then no key until the contact)
            v["g_press_F"] = None
            v["n_side"] = v.get("n_side", 0) + 1
        box = _body(o.e)
        if box is None:
            return m
        cx, cy = _centre_next(x)
        facing = 1 if (o.facing or 0) >= 0 else -1
        meets = side_meets(cx, cy, back, box)
        if meets and _atk_ready_next(x) and facing == back:
            v["g_press_F"] = F
            return m | B["A"]
        if meets:
            return m | (_key(back) if facing != back else 0)
        near = box[2] if v["over_dir"] > 0 else box[0]     # the body edge facing her after the vault
        nxt = cx + back * x.cfg["WALK_U"] * 2
        gap_ok = (nxt - near) * v["over_dir"] >= HX + x.cfg["MARGIN_U"] + x.cfg["GAP_EXTRA"]
        nogo = any(lo - x.cfg["MARGIN_U"] <= nxt <= hi + x.cfg["MARGIN_U"] for lo, hi in v["req"].get("nogo") or ())
        return m | (_key(back) if gap_ok and not nogo else 0)

    @P.guard("vault_target_moved", doc="the target's Control state left Idle / Walk / Dmg Attack (a move began)")
    def target_moved(x):
        return x.obs.st not in TARGET_STATES

    @P.guard("vault_unlocked_hit", doc="a hit on the target was observed while no other Clapper was in its jump-cast "
                                       "states (forum.md:8454: the Idle target picks a move on that frame)")
    def unlocked_hit(x):
        return x.v.get("unlocked_hit_f") is not None

    @P.guard("vault_path_bomb", doc="a pending / lit small-rune row over her x span to the far edge (the fixed-hook "
                                    "entry's bomb rule, knife_chain_fixed_hook.py:27-37, for any owner)")
    def path_bomb(x):
        bk = x.obs.bombs
        if bk is None or not len(bk):
            return False
        from ssbot.combat.rune_bombs import HB_HX, BOMB_M
        xe = x.v["req"].get("x_end")
        lo, hi = sorted((x.obs.hx, x.obs.hx if xe is None else float(xe)))
        for row in bk:
            if len(row) != 6 or not all(math.isfinite(float(z)) for z in row):
                return True
            _, bx, _, radius, _, off = row
            if off >= 0 and lo - (radius + HB_HX + BOMB_M) <= bx <= hi + (radius + HB_HX + BOMB_M):
                return True
        return False

    @P.guard("vault_slashes_done", doc="var.n_side ground slashes swung")
    def slashes_done(x, n):
        return x.v.get("n_side", 0) >= n


def registry():
    P = deepcopy(KS.P)
    register(P)
    return P


def load_vault_runner(path=None, *, cfg=None):
    """load_bound_chains (all names bound before any link runs), then the existing ChainRunner on VaultAnchor."""
    from ssbot.combat.knife_chain_bindings import load_bound_chains
    reg = registry()
    if path is None:
        path = Path(__file__).with_name("knife_chain_vault_v01.json")
    chains, report = load_bound_chains(path, primitives=reg, observation_names=KS.OBS_NAMES,
                                       literal_names=LITERALS, vocabulary=VOCAB)
    if cfg:
        chains[CHAIN].cfg.update(cfg)
    runner = CV.ChainRunner(chains, VaultAnchor(chains, chains[CHAIN].cfg), reg, cfg0=chains[CHAIN].cfg,
                            observation_names=KS.OBS_NAMES, literal_names=LITERALS, vocabulary=VOCAB)
    return runner, report
