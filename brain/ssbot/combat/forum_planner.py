"""The Forum's fast layer (forum_planner_plan §4.1 / §4.4 items 2-3 / §4.5, round R3): the L1 planner over the
MultiForecast, with the Forum vocabulary and a two-stage check that keeps the tick in budget. The Bell Beast planner
(combat.planner.Planner) is not touched: ForumPlanner is its subclass, the Forum switch is which class the glue makes.

Per tick (the lexicographic order and every rule of Planner.tick unless named here):
  candidates  the posture family of the start state (ground / air / wall: candidates.build_forum; T = 36 frames, the
              0.6 s horizon of §4.5) = the core evasion set (56 rows: wait, move, 3 jump holds x 3 ways, dash either
              way, each with idle / run either way / a full jump) + the posture's attack pieces x every continuation,
              plus CONTINUE (the previous plan carried on).
  stage 1     every row rolled out on the nominal lane only; its box centre against the support (MultiForecast
              .occupied: the templates are dilated by the hero hurtbox, so this is the nominal box's exact test).
              Necessary: a row in contact here is in contact in stage 2 too (the hull holds the nominal box, the hull
              test is conservative for its sub-boxes, frames invulnerable in every lane are invulnerable in the
              nominal one), so its S = 1 is final without the envelope. J, Hz and U (kill_frames) on the nominal lane.
  stage 2     the envelope (bounds_lo lanes' hull, Planner._contacts) in chunks of `chunk` rows, in this order: the
              core rows that passed stage 1 (always, whatever the deadline: §4.4 item 2), CONTINUE, the K_b best of
              the rest by (Hz, Hz_soft, U, -J) and up to `sibs` rows sharing each of the 8 best rows' first piece (V
              needs two safe ways on with the same first piece), then the rest in that order. After the priority
              part it stops at the first chunk that leaves a safe row; inside it, once deadline_ms has passed and a
              safe row exists. Without a safe row it goes on to the end (a slow tick, counted: `overrun`, never
              FORCED_RISK by itself: §4.4 item 3).
  hit effects within each chunk, rows with a predicted nail hit (Reaper shapes, every target; the first hit) are
              rolled out again with its effect (side / wall slash: recoil away, up slash: recoil down, down slash:
              bounce) and checked again: S = miss branch | hit branch (DESIGN 3.5.6). The hit branch also meets the
              hit enemy's reaction (hero_caused.json TOOK DAMAGE exits: a Clapper's Idle -> Dmg Attack, a Reed's
              Alert -> Stab Pos, a Minister's Chase -> Range Check, a Maestro's Fly -> Summon?, an Envoy's Charge,
              ...): MultiForecaster.forecast_reaction from the hit frame. At most hitfx_k rows a tick get the hit
              branch and react_k reaction forecasts; a row with a predicted hit beyond those caps is S = 1.
  selection   only rows whose S is known: enveloped, or in contact at stage 1. The chosen plan with S = 0 is always an
              enveloped one (audit: `audit`). FORCED_RISK: no enveloped row is safe after all were checked; P
              (MultiForecast.prob) only for the p_k best of those by first contact, then J.
  unmodelled  a row that presses attack while dashing / sprinting is vetoed (the Reaper's dash stab is R7's).
  U / I3      the killing blow is the one that may end the battle (forum_kill_hp: the final wave's last members),
              FilterContext.kill_hp from it; not certified in R3 (no kill branches): such a blow passes only under I3.
Scores only (GoalPrefs: hit_w per enemy iid, stance, the risk map): no prefs field reaches stage 1's S, Hz, U or the
core rows' envelope, so the core rows' S / Hz / U are the same under any prefs (tests/test_forum_planner.py).
"""
import math
import time
from dataclasses import dataclass, field

import numba
import numpy as np

from ssbot.combat import candidates as cmod
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.combat.planner import (KillPlan, MACRO_MARGIN, PlannerConfig, PlanResult, Planner, _is_macro,
                                  _rect_meets_polys)
from ssbot.combat.safety_filter import (R_KILL, REASONS, FilterContext, hazard_flags, i3_kill_allowed, kill_frames,
                                        kill_window_frames, unpausable, veto)
from ssbot.core.forum import FORUM_TYPES, FORUM_WAVES, WALL_L, WALL_R
from ssbot.knowledge import kinematics as kin
from ssbot.knowledge.attack_shapes import AttackTable
from ssbot.knowledge.knockback import knockback_hull
from ssbot.knowledge.kinematics import (B_ATTACK, B_DASH, B_JUMP, B_QUICKCAST, B_UP, F_ATTACKING, F_GROUND, F_INVULN,
                                        M_DASH, M_NORMAL, M_RPR_DS, M_SPRINT, HeroParams, HoldState, Terrain2D)

R_UNMOD = 6                       # veto reason: presses a move the model does not have (the dash stab)
REASONS_FORUM = dict(REASONS) | {R_UNMOD: "unmodelled move (attack while dashing)"}
SLOTS = ("normal", "up", "wall", "down")   # kernel slot order (_SHAPE_*)
K_SIDE, K_UP, K_WALL, K_DOWN = 1, 2, 3, 4  # first_kind codes
WALL_TOUCH_U = 0.15               # a box edge this close to the arena wall in the air: a side slash is the wall slash
TARGET_REACH_U = 14.0             # enemies farther than this from the hero are not scored (0.6 s: dash + run ~ 8 u)
RPR_ANTIC_F, RPR_SLASH_F = 9, 11  # Reaper down slash: antic 0.150 s, slash 0.167 s (hero_reaper_forum.json)
KILL_Z = 3.0                      # hp_est - z sigma: the least HP an enemy may have (forum_planner_plan §4.2 U)


@dataclass
class ForumConfig:
    T: int = 36                   # 0.6 s (§4.5)
    variants: str = "bounds_lo"
    chunk: int = 32
    K_b: int = 96
    sibs: int = 3
    deadline_ms: float = 11.0
    hitfx_k: int = 32
    react_k: int = 4
    K_tgt: int = 4
    p_k: int = 64


@dataclass
class EnvelopeAudit:
    """Per planner: ticks, chosen plans with S = 0 and of them enveloped (must be equal), FORCED_RISK ticks and of
    them the chosen plan enveloped / known in contact at stage 1, ticks past the deadline without a safe row
    (overrun), rows enveloped, hit branches, reaction forecasts, rows set S = 1 by a cap."""
    ticks: int = 0
    chosen_safe: int = 0
    chosen_safe_enveloped: int = 0
    forced: int = 0
    forced_enveloped: int = 0
    forced_stage1: int = 0
    overrun: int = 0
    deadline_cut: int = 0
    rows_enveloped: int = 0
    rows_stage1: int = 0
    hit_branches: int = 0
    reactions: int = 0
    capped: int = 0
    core_not_enveloped: int = 0   # core rows past stage 1 left without the envelope (must stay 0)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def posture_of(start: np.ndarray) -> str:
    st = np.asarray(start).reshape(kin.K, -1)[:, 0]
    if st[kin.WSIDE] != 0 or st[kin.CLING] > 0:
        return "wall"
    return "ground" if st[kin.GROUND] > 0 else "air"


def _shapes(crest: str = "Reaper") -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The kernel's attack shapes: verts for facing +1 and -1 (concatenated over SLOTS), slot starts [len(SLOTS) + 1],
    active windows [len(SLOTS), 2] (frames after the attack's start; the down slash's from its antic's start)."""
    tab = AttackTable.load(crest)
    vs, st, win = [], [0], []
    for s in SLOTS:
        sh = tab[s]
        p = np.concatenate(sh.polys)
        vs.append(p)
        st.append(st[-1] + len(p))
        if s == "down":
            win.append((RPR_ANTIC_F, RPR_ANTIC_F + RPR_SLASH_F))
        else:
            f0, f1 = sh.frames if sh.frames else (int(round(sh.t_on * 60)), int(round(sh.t_off * 60)))
            win.append((int(f0), int(f1) + 1))
    v = np.concatenate(vs)
    vl = v.copy()
    vl[:, 0] = -vl[:, 0]
    return (np.ascontiguousarray(v), np.ascontiguousarray(vl), np.array(st, np.int64), np.array(win, np.int64))


@numba.njit(cache=True)
def _meets(tb0, tb1, tb2, tb3, verts, a, b, cx, cy):
    starts = np.empty(2, np.int64)
    starts[0], starts[1] = a, b
    return _rect_meets_polys(tb0, tb1, tb2, tb3, verts, starts, cx, cy)


@numba.njit(cache=True, parallel=True)
def _forum_score_kernel(box, flags, mode, latched, face0, tbox, tok, tw, vr, vl, st, win, wall_l, wall_r, wv, stance_x,
                        rx, rv, boss_x, max_hits, J, hits, first_f, first_t, first_k, first_face, risk, unmod):
    """J per row on the nominal lane over K targets (tbox [K, T1, 4], tok [K, T1], weights tw [K]): Reaper side / up /
    wall / down slash polygons in their active windows against each target's box (an attack counts each target it
    meets once, weighted); first_f / first_t / first_k / first_face: the first predicted hit (frame, target, kind,
    facing); unmod: an attack pressed while dashing or sprinting (the dash stab, not modelled)."""
    N, T1 = flags.shape
    K = tbox.shape[0]
    for c in numba.prange(N):
        face = face0
        fc = np.empty(T1, np.int64)
        cxs = np.empty(T1)
        cys = np.empty(T1)
        for k in range(T1):
            if k > 0:
                m = latched[c, k - 1]
                d = 1 if m & kin.B_RIGHT else (-1 if m & kin.B_LEFT else 0)
                if d != 0 and mode[c, k - 1] == M_NORMAL and (flags[c, k - 1] & F_ATTACKING) == 0:
                    face = d
            fc[k] = face
            cxs[k] = 0.5 * (box[c, k, 0] + box[c, k, 2])
            cys[k] = 0.5 * (box[c, k, 1] + box[c, k, 3])
        h = 0.0
        presses = 0
        jumps = 0
        for k in range(1, T1):
            jl = (latched[c, k - 1] & B_JUMP) != 0
            jp = k > 1 and (latched[c, k - 2] & B_JUMP) != 0
            if jl and not jp:
                jumps += 1
            if (latched[c, k - 1] & B_ATTACK) != 0 and (k < 2 or (latched[c, k - 2] & B_ATTACK) == 0):
                if mode[c, k - 1] == M_DASH or mode[c, k - 1] == M_SPRINT or mode[c, k] == M_DASH:
                    unmod[c] = True
            att = (flags[c, k] & F_ATTACKING) != 0 and (flags[c, k - 1] & F_ATTACKING) == 0
            dsk = mode[c, k] == M_RPR_DS and mode[c, k - 1] != M_RPR_DS
            if not (att or dsk):
                continue
            presses += 1
            if dsk:
                s, kind = 3, K_DOWN
            elif (latched[c, k - 1] & B_UP) != 0:
                s, kind = 1, K_UP
            elif (flags[c, k] & F_GROUND) == 0 and (box[c, k, 0] - wall_l < WALL_TOUCH_U
                                                     or wall_r - box[c, k, 2] < WALL_TOUCH_U):
                s, kind = 2, K_WALL
            else:
                s, kind = 0, K_SIDE
            a, b = st[s], st[s + 1]
            for t in range(K):
                got = False
                for j in range(k + win[s, 0], min(T1, k + win[s, 1])):
                    if not tok[t, j]:
                        continue
                    vv = vr if fc[j] > 0 else vl
                    if _meets(tbox[t, j, 0], tbox[t, j, 1], tbox[t, j, 2], tbox[t, j, 3], vv, a, b, cxs[j], cys[j]):
                        got = True
                        if first_f[c] < 0 or j < first_f[c]:
                            first_f[c], first_t[c], first_k[c], first_face[c] = j, t, kind, fc[j]
                        break
                if got:
                    h += tw[t]
        h = min(h, max_hits)
        waste = max(presses - h, 0.0)
        x_end = cxs[T1 - 1]
        r = np.interp(x_end, rx, rv)
        d_mean = 0.0
        for k in range(T1):
            d_mean += abs(cxs[k] - stance_x)
        d_mean /= T1
        v = wv[0] * h - wv[1] * waste - wv[2] * jumps - wv[3] * (0.5 * abs(x_end - stance_x) + 0.5 * d_mean) \
            - wv[4] * r
        if boss_x == boss_x:
            want = 1 if boss_x > x_end else -1
            if fc[T1 - 1] == want:
                v += wv[5]
        if flags[c, T1 - 1] & F_GROUND:
            v += wv[6]
        J[c] = v
        hits[c] = h
        risk[c] = r


def forum_kill_hp(mf, z: float = KILL_Z) -> float | None:
    """U's subject in the Forum (forum_planner_plan §4.2 "最后一击"): the least HP the battle's last members may have
    when one blow may end the battle (the 1.85 s slow motion that cannot be paused): the final wave running (or every
    wave done) and every member still alive at or below that blow, so the max over them of hp_est - z sigma; None while
    other waves are to come (an ordinary kill's freeze is YELLOW's, forum_yellow_kill_hp). mf: the MultiForecaster
    (hp_est from the hits seen; never ents.hp)."""
    w = getattr(mf, "waves", None)
    if w is None or not (w.done or w.wave >= len(FORUM_WAVES) - 1) or w.queued is not None:
        return None
    lo = [max(0.0, tr.hp_est - z * tr.hp_sd) for tr in mf.trackers.values()
          if tr.in_play and not tr.dead and tr.tk in {t for t in FORUM_WAVES[-1].types}]
    return max(lo) if lo else None


def kill_freeze_s(path=None) -> dict[str, float]:
    """The longest freeze a kill of each Forum type was seen to start (forum_products kill_freeze.json, s of real
    time), 0 for a type whose kills never froze."""
    import json
    from ssbot.combat.enemy_tables import FORUM_DIR
    p = path or FORUM_DIR / "kill_freeze.json"
    d = json.loads(p.read_text("utf-8"))
    out = {tk: 0.0 for tk in FORUM_TYPES}
    for k, v in (d.get("length") or {}).items():
        tk = k.split("|")[0]
        ms = (v.get("ms") or {}).get("max")
        if ms is not None:
            out[tk] = max(out.get(tk, 0.0), float(ms) / 1e3)
    return out


def forum_yellow_kill_hp(mf, freeze: dict[str, float], z: float = KILL_Z, min_freeze_s: float = 0.0
                         ) -> float | None:
    """YELLOW's per-enemy kill freeze (forum_planner_plan §4.4 item 7): the least HP (hp_est - z sigma) over the enemies
    in play whose type's kill was seen to freeze the game longer than min_freeze_s (kill_freeze_s); the supervisor's
    kill_prims withholds the damaging primitives whose next landed hit may take one of them to 0. None: none."""
    lo = [max(0.0, tr.hp_est - z * tr.hp_sd) for tr in mf.trackers.values()
          if tr.in_play and not tr.dead and freeze.get(tr.tk, 0.0) > min_freeze_s]
    return min(lo) if lo else None


class ForumPlanner(Planner):
    def __init__(self, params: HeroParams, terrain: Terrain2D, cfg: PlannerConfig | None = None,
                 fcfg: ForumConfig | None = None, crest: str = "Reaper"):
        self.fcfg = fcfg or ForumConfig()
        super().__init__(params, terrain, cfg or PlannerConfig(T=self.fcfg.T, variants=self.fcfg.variants))
        self.fsets = {p: cmod.build_forum(self.fcfg.T, p) for p in cmod.POSTURES}
        self.shapes = _shapes(crest)
        self.audit = EnvelopeAudit()
        self.last_info: dict = {}

    # ---- scoring ----

    def _forum_targets(self, ws, f, tk: np.ndarray, prefs) -> tuple[np.ndarray, np.ndarray, np.ndarray, list]:
        hx, hy = (float(ws.hero.pos.v[0]), float(ws.hero.pos.v[1])) if ws is not None and ws.hero is not None \
            else (0.0, 0.0)
        tg = [t for t in f.targets(tk) if not t.hazard]
        d = [math.hypot(0.5 * (t.box[0, 0] + t.box[0, 2]) - hx, 0.5 * (t.box[0, 1] + t.box[0, 3]) - hy) for t in tg]
        keep = [t for _, t in sorted(zip(d, tg), key=lambda z: z[0]) if _ <= TARGET_REACH_U][:self.fcfg.K_tgt]
        T1 = len(tk)
        if not keep:
            return np.zeros((0, T1, 4)), np.zeros((0, T1), bool), np.zeros(0), []
        hw = getattr(prefs, "hit_w", None) or {}
        return (np.ascontiguousarray(np.stack([t.box for t in keep]), np.float64),
                np.ascontiguousarray(np.stack([t.ok for t in keep])),
                np.array([float(hw.get(t.iid, 1.0)) for t in keep]), keep)

    def _score_forum(self, ws, roll, latched, start, f, prefs, tk):
        w = prefs.weights
        N, T1 = roll.flags.shape
        face0 = 1 if np.asarray(start).reshape(kin.K, -1)[kin.FACE, 0] >= 0 else -1
        tbox, tok, tw, keep = self._forum_targets(ws, f, tk, prefs)
        wv = np.array([w.get("hit", 10.0), w.get("waste", 0.6), w.get("jump", 0.15), w.get("stance", 0.6),
                       w.get("risk", 3.0), w.get("face", 0.3), w.get("ground", 0.2), 0.0])
        rx = prefs.risk_x if len(prefs.risk_x) else np.zeros(1)
        rv = prefs.risk if len(prefs.risk) else np.zeros(1)
        out = dict(J=np.zeros(N), hits=np.zeros(N), first_f=np.full(N, -1, np.int64), first_t=np.full(N, -1, np.int64),
                   first_k=np.zeros(N, np.int64), first_face=np.zeros(N, np.int64), risk=np.zeros(N),
                   unmod=np.zeros(N, np.bool_))
        vr, vl, st, win = self.shapes
        _forum_score_kernel(np.ascontiguousarray(roll.box), np.ascontiguousarray(roll.flags),
                            np.ascontiguousarray(roll.mode), np.ascontiguousarray(latched), face0,
                            tbox if len(keep) else np.zeros((0, T1, 4)), tok if len(keep) else np.zeros((0, T1), bool),
                            tw, vr, vl, st, win, WALL_L, WALL_R, wv, float(prefs.stance_x),
                            np.ascontiguousarray(rx, np.float64), np.ascontiguousarray(rv, np.float64),
                            prefs.boss_x if prefs.boss_x is not None else np.nan,
                            float(prefs.max_hits) if prefs.max_hits is not None else np.inf,
                            out["J"], out["hits"], out["first_f"], out["first_t"], out["first_k"], out["first_face"],
                            out["risk"], out["unmod"])
        out["targets"] = keep
        return out

    # ---- hit branches ----

    def _hit_branch(self, f, start, latched, sc, rows, tk, enemy_only, budget) -> np.ndarray:
        """S of the hit branch for rows (each with a predicted first hit): rolled out with the hit's effect from its
        frame, against the support and the hit enemy's reaction. budget: dict with hitfx / react counters (caps)."""
        T = latched.shape[1]
        ev = np.zeros((len(rows), T), np.int64)
        kinds, faces, fr = sc["first_k"][rows], sc["first_face"][rows], sc["first_f"][rows]
        j = np.clip(fr, 0, T - 1)                # as Planner._hit_effects: the event from the hit frame's index
        bits = np.where(kinds == K_DOWN, kin.EV_POGO, np.where(kinds == K_UP, kin.EV_RECOIL_DOWN,
                                                                 np.where(faces > 0, kin.EV_RECOIL_L, kin.EV_RECOIL_R)))
        ev[np.arange(len(rows)), j] = bits
        rh = kin.rollout(start, latched[rows], self.params, self.terrain, events=ev, variants=self.fcfg.variants,
                         threads=self.cfg.threads)
        skip = ((rh.flags_all & F_INVULN) != 0) if enemy_only else np.zeros(rh.flags_all.shape, bool)
        occ = self._contacts(f, rh.bound, tk, skip)
        s = occ.any(axis=1)
        # the hit enemy's reaction (hero_caused TOOK DAMAGE exits), one forecast per (enemy, hit frame)
        mf = getattr(f, "_fc", None)
        tg = sc["targets"]
        if mf is not None and hasattr(mf, "reaction_state"):
            for n, r in enumerate(rows):
                if s[n]:
                    continue
                t = tg[int(sc["first_t"][r])]
                to = mf.reaction_state(t.iid)
                if to is None:
                    continue
                key = (t.iid, int(fr[n]))
                rf = budget["react_cache"].get(key)
                if rf is None and key not in budget["react_cache"]:
                    if budget["react"] >= self.fcfg.react_k:
                        s[n] = True                          # past the cap: the reaction is unchecked
                        budget["capped"] += 1
                        continue
                    budget["react"] += 1
                    rf = mf.forecast_reaction(t.iid, to, f.origin_t + float(tk[min(fr[n], len(tk) - 1)]),
                                              f.horizon, f.origin_t)
                    budget["react_cache"][key] = rf
                if rf is not None:
                    o2 = self._contacts(rf, rh.bound[n:n + 1], tk, skip[n:n + 1])
                    s[n] |= bool(o2.any())
        return s

    # ---- the tick ----

    def tick(self, ws, start: np.ndarray, hold: HoldState, prefix: np.ndarray, f, prefs, ctx: FilterContext
             ) -> PlanResult:
        t0 = time.perf_counter()
        cfg, fcfg, params = self.cfg, self.fcfg, self.params
        prefix = np.asarray(prefix, np.int64).reshape(-1)
        P = len(prefix)
        posture = posture_of(start)
        cs, core0 = self.fsets[posture]
        N0, T = len(cs.cmd), cs.T
        cont = self.prev_cmd is not None
        rows_ = [cs.cmd]
        if cont:
            rows_.append(cmod.continue_plan(self.prev_cmd, 1, T)[None])
        cmd = np.concatenate(rows_)
        rem0 = self.jump_until - self.ticks
        if rem0 > 0:
            att = np.array([n.startswith("ATTACK") for n in cs.first_names])[cs.first]
            if att.any():
                cmd = cmd.copy()
                cmd[:N0][att, :min(rem0, T)] |= B_JUMP
        N = len(cmd)
        core = np.append(core0, False) if cont else core0.copy()
        full = np.empty((N, P + T), np.int64)
        full[:, :P] = prefix
        full[:, P:] = cmd
        ok, why = veto(cs, ctx)
        if cont:
            ok = np.append(ok, bool(ctx.allowed_mask.all()) or self._prev_allowed(ctx))
            why = np.append(why, 0 if ok[-1] else 1)
        latched, hold_end = hold_filter_jit(full, hold)
        t1 = time.perf_counter()
        # ---- stage 1: the nominal lane, its box centre against the support ----
        r1 = kin.rollout(start, latched, params, self.terrain, threads=cfg.threads)
        T1 = P + T + 1
        tk = np.arange(T1, dtype=np.float64) * params.frame_time
        enemy_only = not any(fm.hazard for fm in f.fc.model.families.values())
        cx = 0.5 * (r1.box[..., 0] + r1.box[..., 2])
        cy = 0.5 * (r1.box[..., 1] + r1.box[..., 3])
        occ1 = f.occupied(cx, cy, tk)
        if enemy_only:
            occ1 &= (r1.flags & F_INVULN) == 0
        occ1[:, 0] = False
        S1 = occ1.any(axis=1)
        t_hit = np.where(S1, occ1.argmax(axis=1), T1)
        t2 = time.perf_counter()
        sc = self._score_forum(ws, r1, latched, start, f, prefs, tk)
        J = sc["J"]
        if cont:
            J[-1] += prefs.weights.get("cont", 0.0)
        unm = sc["unmod"] & ok
        why[unm] = R_UNMOD
        ok &= ~sc["unmod"]
        hz = np.zeros(N, bool)
        hz_soft = np.zeros(N, bool)
        if ctx.hazards or ctx.soft:
            hull, kfl = knockback_hull(r1.box, params, self.terrain, threads=cfg.threads)
            hz, hz_soft = hazard_flags(hull, kfl, ctx)
        may_kill, k_lo, k_hi, in_flight = kill_frames(latched, r1.flags, r1.mode, P, ctx)
        # the Forum's final kill is not certified in R3 (no kill branches): it passes only under I3
        U = unpausable(may_kill | in_flight, ctx, None)
        veto_k = U & may_kill
        if veto_k.any():
            why[ok & veto_k] = R_KILL
            ok = ok & ~veto_k
        t3 = time.perf_counter()
        # ---- stage 2: the envelope, in priority order, with the deadline ----
        S = S1.copy()
        env = np.zeros(N, bool)
        bound = r1.box.copy()
        pass1 = ok & ~S1
        pre = np.lexsort((-J, U, hz_soft, hz))
        pre = pre[pass1[pre]]
        core_rows = pre[core[pre]]
        prio = [int(i) for i in core_rows]
        n_core = len(prio)
        if cont and pass1[N - 1] and not core[N - 1]:
            prio.append(N - 1)
        rest = [int(i) for i in pre if not core[i] and not (cont and i == N - 1)]
        top = rest[:fcfg.K_b]
        first = np.append(cs.first, -1) if cont else cs.first
        sib = []
        top_set = set(top)
        by_first: dict = {}
        for j in rest:
            by_first.setdefault(int(first[j]), []).append(j)
        for i in rest[:8]:
            if first[i] < 0:
                continue
            sib += [j for j in by_first[int(first[i])] if j != i and j not in top_set][:fcfg.sibs]
        seen = set(prio)
        for i in top + sib:
            if i not in seen:
                prio.append(i)
                seen.add(i)
        n_prio = len(prio)
        queue = prio + [i for i in rest if i not in seen]
        budget = {"hitfx": 0, "react": 0, "capped": 0, "react_cache": {}}
        has_hit = sc["first_f"] >= 0
        safe_any = False
        pos = 0
        overrun = False
        cut = False
        while pos < len(queue):
            ch = np.array(queue[pos:pos + fcfg.chunk], np.int64)
            pos += len(ch)
            r2 = kin.rollout(start, latched[ch], params, self.terrain, variants=fcfg.variants, threads=cfg.threads)
            skip = ((r2.flags_all & F_INVULN) != 0) if enemy_only else np.zeros(r2.flags_all.shape, bool)
            occ = self._contacts(f, r2.bound, tk, skip)
            s2 = occ.any(axis=1)
            S[ch] = s2
            env[ch] = True
            bound[ch] = r2.bound
            t_hit[ch] = np.where(s2, occ.argmax(axis=1), T1)
            hr = ch[~s2 & has_hit[ch]]
            if len(hr):
                room = fcfg.hitfx_k - budget["hitfx"]
                over = hr[max(room, 0):]
                hr = hr[:max(room, 0)]
                if len(over):
                    S[over] = True
                    budget["capped"] += len(over)
                if len(hr):
                    budget["hitfx"] += len(hr)
                    S[hr] |= self._hit_branch(f, start, latched, sc, hr, tk, enemy_only, budget)
            safe_now = bool((env & ok & ~S & ~hz).any())
            safe_any = safe_any or safe_now
            if pos >= n_core and safe_any:
                if pos >= n_prio:
                    break
                if (time.perf_counter() - t0) * 1e3 > fcfg.deadline_ms:
                    cut = pos < len(queue)
                    break
            if not safe_any and (time.perf_counter() - t0) * 1e3 > fcfg.deadline_ms and pos < len(queue):
                overrun = True
        t4 = time.perf_counter()
        known = env | S1
        safe = ok & env & ~S & ~hz
        self.last_safe, self.last_cs = safe, cs
        V = np.zeros(N, bool)
        counts = np.bincount(first[:N0][safe[:N0]], minlength=len(cs.first_names))
        V[:N0] = counts[first[:N0]] >= 2
        if cont:
            V[-1] = safe[-1]
        rem = self.jump_until - self.ticks
        keep = np.ones(N, bool)
        if rem > 0:
            wj = cmd[:, :min(rem, T, cfg.release_latency)]
            keep = ((wj & B_JUMP) != 0).all(axis=1) & ((wj & B_QUICKCAST) == 0).all(axis=1)
        bind_res = None
        if prefs.want_bind and ctx.want_bind:
            bind_res = self._bind(ws, start, hold, prefix, f, ctx)
        forced = not safe.any() and not (bind_res is not None and bind_res[0])
        Pc = np.zeros(N)
        sel = ok & known
        if forced and sel.any():
            cand = np.flatnonzero(sel)
            cand = cand[np.lexsort((-J[cand], -t_hit[cand]))][:fcfg.p_k]
            b = r1.box[cand]
            Pc[cand] = f.prob(0.5 * (b[..., 0] + b[..., 2]), 0.5 * (b[..., 1] + b[..., 3]), tk)
            sel = np.zeros(N, bool)
            sel[cand] = True
        zero = ~cmd.any(axis=1)
        idle_clear = int(min(t_hit[zero & known].min() if (zero & known).any() else T1, T1) - P) \
            if zero.any() else None
        t5 = time.perf_counter()
        a = self.audit
        a.ticks += 1
        a.rows_enveloped += int(env.sum())
        a.rows_stage1 += N
        a.hit_branches += budget["hitfx"]
        a.reactions += budget["react"]
        a.capped += budget["capped"]
        a.overrun += int(overrun)
        a.deadline_cut += int(cut)
        a.core_not_enveloped += int((core & pass1 & ~env).sum())
        if bind_res is not None and bind_res[0]:
            sel_cmd = self.bind.cmd[0]
            res = PlanResult(int(sel_cmd[0]), -2, "BIND", 0, False, 0.0, 1e3, True, n=N + 1,
                             n_allowed=int(ok.sum()) + 1, n_safe=int(safe.sum()) + 1, cmd=sel_cmd, path=bind_res[1])
        elif sel.any():
            mkeep = np.ones(N, bool)
            if cont and self.macro_until > self.ticks:
                mkeep = J >= J[N - 1] + MACRO_MARGIN
                mkeep[N - 1] = True
            order = np.lexsort((-J, -t_hit, Pc, ~V, ~mkeep, ~keep, S, U, hz_soft, hz))
            order = order[sel[order]]
            i = int(order[0])
            tail_ok = None
            carried = cont and i == N - 1 and self.prev_tail_ok
            if not forced and cfg.tail_k > 0 and not carried:
                ranked = order[safe[order]]
                i, tail_ok = self._tail_pick(f, r1, hold_end, ranked, P + T, i)
            elif carried:
                tail_ok = True
            self.prev_tail_ok = bool(tail_ok)
            sel_cmd = cmd[i]
            name = "CONTINUE" if cont and i == N - 1 else cs.name(i)
            res = PlanResult(int(sel_cmd[0]), i, name, int(S[i]), forced, float(Pc[i]), float(J[i]), bool(V[i]),
                             bool(hz[i]), bool(U[i]), N, int(ok.sum()), int(safe.sum()), sel_cmd, r1.box[i].copy(),
                             bound[i].copy(), hits=float(sc["hits"][i]))
            res.tail_ok = tail_ok
            if may_kill[i] or in_flight[i]:
                res.kill = KillPlan(own=bool(may_kill[i]), certified=False, i3=i3_kill_allowed(ctx),
                                    k_lo=int(k_lo[i]), k_hi=int(k_hi[i]),
                                    window=kill_window_frames(params.frame_time, ctx.kill_window_s), P=P)
            for j_ in order[1:6]:
                nm = "CONTINUE" if cont and j_ == N - 1 else cs.name(int(j_))
                res.alternatives.append((nm, int(S[j_]), round(float(Pc[j_]), 3), round(float(J[j_]), 2)))
            if not S[i]:
                a.chosen_safe += 1
                a.chosen_safe_enveloped += int(env[i])
            else:
                a.forced += int(forced)
                a.forced_enveloped += int(forced and env[i])
                a.forced_stage1 += int(forced and not env[i])
        else:
            sel_cmd = np.zeros(T, np.int64)
            res = PlanResult(0, -1, "NONE", 1, True, n=N)
            a.forced += 1
        res.vetoes = {REASONS_FORUM[k]: int(v) for k, v in zip(*np.unique(why, return_counts=True)) if k}
        res.idle_clear = idle_clear
        if len(sel_cmd) and sel_cmd[0] & B_JUMP:
            if self.jump_until <= self.ticks:
                held = sel_cmd & B_JUMP
                self.jump_until = self.ticks + (int(np.argmin(held != 0)) if (held == 0).any() else len(held))
        else:
            self.jump_until = -1
        if _is_macro(res.name):
            last = np.flatnonzero((sel_cmd & kin.B_DOWN) != 0)
            self.macro_until = self.ticks + (int(last[-1]) + 12 if len(last) else 0)
        elif res.name != "CONTINUE":
            self.macro_until = -1
        self.prev_cmd = sel_cmd
        self.prev_name = res.name
        self.ticks += 1
        t6 = time.perf_counter()
        self.last_info = {"posture": posture, "N": N, "stage1_pass": int(pass1.sum()), "enveloped": int(env.sum()),
                          "core": int(core.sum()), "core_pass": n_core, "prio": n_prio, "overrun": overrun,
                          "cut": cut, "hitfx": budget["hitfx"], "react": budget["react"], "capped": budget["capped"],
                          "S": S, "Hz": hz, "U": U, "core_mask": core, "env": env}
        res.t_ms = {"filter": (t1 - t0) * 1e3, "rollout": (t2 - t1) * 1e3, "score": (t3 - t2) * 1e3,
                    "envelope": (t4 - t3) * 1e3, "prob_bind": (t5 - t4) * 1e3, "select": (t6 - t5) * 1e3,
                    "total": (t6 - t0) * 1e3}
        return res
