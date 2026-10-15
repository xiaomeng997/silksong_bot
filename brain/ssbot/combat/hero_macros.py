"""Hero event macros for the space-time map (task 1v1 SG1; the person's design 2026-10-12..14, forum.md 55): the
moves the map builder (SG2) chains between its nodes, on top of the kinematics model (ssbot.knowledge.kinematics /
kin_jit, Wanderer, the Forum save's abilities), proven against full rollouts by ssbot.tools.sg1_validate.

Why macros work. Normal movement has no horizontal inertia (vx = direction key x 8.25 u/s on the ground and in the
air), and in the open (no wall in reach) the horizontal input never changes the vertical motion. So a move splits into
  * a vertical profile per event class (a ground jump with the jump key held h frames; a down-slash bounce; an
    umbrella fall), tabulated once from rollouts, and
  * a horizontal schedule: the key held over some frames moves the body one run step STEP_U = 8.25 x 0.02 = 0.165 u
    per 50 Hz physics step.
The 50 Hz steps fall among the 60 fps frames with a 6-frame cycle (5 steps in 6 frames; frame j of a node with cycle
position q has no step iff (j - q) % 6 == 0); q advances as q' = (q - n) % 6 after n frames. The map has no q
dimension: SG2 takes the hull over q (sweep_hull) or pairs q with the enemy's motion phase.

Frame clock (as T1 / pogo_slam): a node at frame k is the hero state at the end of frame k (after its Update). keys[i]
/ masks[i] is the input of frame k + 1 + i (read by that frame's Update); index j of a sweep is the state at the end of
frame k + j (j = 0: the node). A key read in frame f's Update moves the body in the physics steps of frame f + 1 on
(keff[j] = keys[j - 2]; keff[1] = the key the node already held, i.e. the sign of its vx).

Coordinates: x is the hero's box centre in the map frame (along the enemy's facing, relative to its anchor;
ssbot.combat.move_data); a key +1 moves +x. The slash polygon is mirrored with the hero's facing in that frame
(slash_poly(face)). y is absolute (the Forum floor FLOOR_Y): box bottom, box = [x - 0.25, y, x + 0.25, y + 2.079].
The slash hangs off the rendered transform (pos: lerp of the poses before / after the last physics step), not the box.

Event classes (what the model says; sg1_validate measures it):
  ground jump h: the jump key held for frames 1..h; apex and landing per h; h >= 25 is the full 5.50 u jump; holding
    the key past the apex (h > ~28) hangs at the top (air-hang gravity) and lands later: separate classes.
  bounce: EV_POGO on the contact frame c; the rise is fixed (+4.09 u over the contact frame's box, apex at c + 22 /
    23): the jump key held or pressed from c - 6 to c + 2 changes nothing (jumped_steps -20 blocks the release cut
    and the pogo's jump steps run anyway); a jump press from c + 3 on opens the umbrella (a glide, lower). So the
    model has ONE bounce apex class, not two (the person's "extend with jump" class does not exist in the model).
  pogo i-frames: F_INVULN on frames c .. c + 8 (8 physics steps, 0.16 s).
  attack cooldown: a second press swings only from press + COOLDOWN_F (19) frames on (16-18: no swing, no queue).
  umbrella: a jump press in the air while falling opens it (M_GLIDE); its horizontal has inertia (not the 0.165 u
    lattice): glide() tabulates the fall and the reach per frame from rollouts.
  The Wanderer down-slash "thrust" (15 u/s down) is not in the kinematics model (movement_kinematics.md: down + dash
  unmodelled), so it is not a candidate input here.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ssbot.combat.pogo_model import ACTIVE, slash_poly
from ssbot.combat.pogo_slam import CX, FLOOR_Y, HERO_STAND_DY, PRE_PROTECT_F, clip_band
from ssbot.knowledge import kinematics as kin

M_R, M_L, M_J, M_D, M_A = kin.B_RIGHT, kin.B_LEFT, kin.B_JUMP, kin.B_DOWN, kin.B_ATTACK
# node alpha at the centre of cycle position q's interval: frame j of the node has no physics step iff (j - q) % 6 == 0
# for alpha in [(q - 1) / 6, q / 6) (mod 1); alpha = q / 6 itself sits on an edge (the 0.016666 s frame decides)
ALPHAS = tuple(((q - 0.5) / 6) % 1.0 for q in range(6))
COOLDOWN_F = 19                              # measured by HeroMacros.cooldown(); asserted in the tests
IFRAMES = (0, 8)                             # F_INVULN frames c + 0 .. c + 8 after a contact on frame c


# what SG2 must add because the map has no cycle-position dimension and the hero is not on the lattice
# (sg1_validate over every q and off-lattice alphas; forum.md 55): the swept box is exact per q, so take the hull over
# q (sweep_hull): it is one run step wide in x and up to 0.63 u tall in y (apex frame +-2, landing +-3 frames);
# the rendered pos (the slash's anchor) is off by <= 0.014 u in x / 0.052 u in y inside a q bin, so a strike cell
# must hold with the target box shrunk by RENDER_U; the contact frame may then move one frame (6 of 8,820 rows);
# the cycle slips one frame per ~5,000 frames (frame time 0.016666 s vs 1/60 s): a node within 0.0033 of a bin edge
# may be one step / one frame off over a 100-frame macro.
MARGINS = {"hull_x_u": 0.165, "hull_y_u": 0.631, "apex_frames": 2, "land_frames": 3, "render_x_u": 0.014,
           "render_y_u": 0.052, "contact_frames": 1, "lattice_x_u": 0.0825}
RENDER_U = (0.02, 0.06)                      # target shrink (x, y) for a robust contact against the render residual


def key_mask(k: int) -> int:
    return M_R if k > 0 else (M_L if k < 0 else 0)


@dataclass
class VProfile:
    """The vertical part of one event class from a node with cycle position q. y: box bottom per sweep index,
    relative to the reference (a ground jump: the standing box bottom; a bounce: the contact frame's box bottom);
    py: rendered pos y minus box bottom; flags: kinematics F_* bits; apex: index of the highest box; land: first
    grounded index after leaving the ground (-1: not within the table; free-space profiles: see HeroMacros.landing)."""
    kind: str
    param: int
    q: int
    y: np.ndarray
    py: np.ndarray
    flags: np.ndarray
    apex: int
    land: int


@dataclass
class Sweep:
    """A macro under one horizontal schedule: per sweep index the hero box (x0, y0, x1, y1), the rendered pos
    (x, y) and flags; land = landing index (-1: none)."""
    box: np.ndarray
    pos: np.ndarray
    flags: np.ndarray
    land: int


class HeroMacros:
    def __init__(self, params: kin.HeroParams, terrain: kin.Terrain2D | None, x_world: float = CX,
                 floor_y: float = FLOOR_Y, T: int = 150, holds=range(1, 41)):
        self.params, self.terrain, self.T = params, terrain, T
        self.xw = x_world                                  # where the tables' rollouts stand (open floor)
        self.floor_y = floor_y
        self.stand_py = floor_y + HERO_STAND_DY            # hero.pos y standing (the Forum's; settled below)
        if terrain is not None:                            # settle on this terrain's floor (its skin)
            S = kin.initial_state(params, x_world, self.stand_py, facing=1, ground=True)
            self.stand_py = float(kin.rollout(S, np.zeros((1, 12), np.int64), params, terrain).phys[0, -1, 1])
        self.hw = params.half_width
        self.H = params.foot + params.head + 0.0           # box height (foot below pos, head above)
        self.step_u = params.run_speed * params.fdt
        self._build_steps()
        self.stand_y0 = float(self._stand_box_y0)
        self.holds = tuple(holds)
        self.jumps = {}                                    # (h, q) -> VProfile
        self._build_jumps()
        self.bounces = {qc: self._bounce_profile(qc) for qc in range(6)}
        self._glides = {}

    # ---- rollouts the tables come from ----
    def _start(self, q: int, y: float | None = None, vy: float = 0.0, ground: bool = True) -> np.ndarray:
        return kin.initial_state(self.params, self.xw, self.stand_py if y is None else y, vy=vy, facing=1,
                                 ground=ground, alpha=ALPHAS[q])

    def _roll(self, S, masks, events=None, terrain="default"):
        terr = self.terrain if terrain == "default" else terrain
        return kin.rollout(S, np.asarray(masks, np.int64), self.params, terr, events=events, threads=4)

    def _build_steps(self):
        """The step cycle and the render lag, from runs (key held from mask 0) of 60 frames (the walls are 16 u away)
        at each q; the cycle rule is checked there and extended periodically (period 6)."""
        T, n = self.T, 60
        rule = np.array([[0 if (j - q) % 6 == 0 else 1 for j in range(T + 1)] for q in range(6)])
        rule[:, 0] = 0
        lag = np.zeros((6, T + 1))
        for q in range(6):
            ro = self._roll(self._start(q), np.full((1, n), M_R, np.int64))
            d = np.rint(np.diff(ro.phys[0, :, 0]) / self.step_u).astype(np.int64)
            assert (d[1:] == rule[q, 2:n + 1]).all(), "the 6-frame step cycle does not hold"
            S1 = self._start(q)                            # frame 1 moves with the node's own vx
            S1[kin.VX], S1[kin.MOVE] = self.params.run_speed, 1
            r1 = self._roll(S1, np.zeros((1, 3), np.int64))
            assert int(np.rint((r1.phys[0, 1, 0] - r1.phys[0, 0, 0]) / self.step_u)) == rule[q, 1], "frame 1 step"
            lr = (ro.phys[0, :, 0] - ro.pos[0, :, 0]) / self.step_u
            lag[q] = [lr[12 + (j - 12) % 6] for j in range(T + 1)]   # periodic, from frames past the start
            if q == 0:
                self._stand_box_y0 = ro.box[0, 0, 1]
        self.st = rule
        self.lag = lag

    def _build_jumps(self):
        T = self.T
        for q in range(6):
            M = np.zeros((len(self.holds), T), np.int64)
            for i, h in enumerate(self.holds):
                M[i, :h] = M_J
            ro = self._roll(self._start(q), M)
            for i, h in enumerate(self.holds):
                y = ro.box[i, :, 1] - ro.box[i, 0, 1]
                fl = ro.flags[i]
                g = (fl & kin.F_GROUND) != 0
                off = np.flatnonzero(~g)
                land = -1
                if len(off):
                    back = np.flatnonzero(g[off[0]:])
                    land = int(off[0] + back[0]) if len(back) else -1
                self.jumps[(h, q)] = VProfile("jump", h, q, y, ro.pos[i, :, 1] - ro.box[i, :, 1], fl.copy(),
                                              int(np.argmax(y)), land)

    def _bounce_profile(self, qc: int) -> VProfile:
        """Free space (no terrain): the contact on sweep index 1 of a falling start, relative to that frame's box."""
        T = self.T
        q0 = (qc + 1) % 6                                  # node one frame before the contact
        S = self._start(q0, y=self.stand_py + 30.0, vy=-6.0, ground=False)
        ev = np.zeros((1, T), np.int64)
        ev[0, 0] = kin.EV_POGO
        ro = self._roll(S, np.zeros((1, T), np.int64), ev, terrain=None)
        y = ro.box[0, 1:, 1] - ro.box[0, 1, 1]
        return VProfile("bounce", 0, qc, y, ro.pos[0, 1:, 1] - ro.box[0, 1:, 1], ro.flags[0, 1:].copy(),
                        int(np.argmax(y)), -1)

    # ---- (a) ground steps / horizontal schedules ----
    def q_after(self, q: int, n: int) -> int:
        return (q - n) % 6

    def keff(self, keys: np.ndarray, key0: int = 0) -> np.ndarray:
        """[.., T+1] the key that drives each sweep index's physics steps (index 0 unused)."""
        keys = np.asarray(keys)
        out = np.zeros(keys.shape[:-1] + (keys.shape[-1] + 1,), np.int64)
        out[..., 1] = key0
        out[..., 2:] = keys[..., :-1]
        return out

    def run_x(self, x0, keys: np.ndarray, q: int, key0: int = 0) -> np.ndarray:
        """[.., T+1] box centre x under keys [.., T] (values -1 / 0 / +1) from a node at x0 with cycle position q."""
        ke = self.keff(keys, key0)
        n = ke.shape[-1]
        return np.asarray(x0)[..., None] + self.step_u * np.cumsum(self.st[q, :n] * ke, axis=-1)

    def pos_x(self, cx: np.ndarray, keys: np.ndarray, q: int, key0: int = 0) -> np.ndarray:
        """The rendered x: the box centre pulled back by the render lag of the last physics step's displacement."""
        ke = self.keff(keys, key0)
        n = ke.shape[-1]
        st = self.st[q, :n]
        idx = np.where(st > 0, np.arange(n), 0)
        last = np.maximum.accumulate(idx)                  # the latest frame with a step
        d = self.step_u * np.take_along_axis(ke, np.broadcast_to(last, ke.shape), axis=-1)
        d = np.where(last > 0, d, key0 * self.step_u)
        return cx - self.lag[q, :n] * d

    def ground_step(self, x: float, key: int, q: int, key0: int = 0) -> tuple[float, int]:
        """(a) one frame on the ground: the node's own key (key0, read last frame) moves the body in this frame's
        step; `key` is read now and moves from the next frame on. Returns (x', q')."""
        return x + self.step_u * key0 * self.st[q, 1], self.q_after(q, 1)

    def solve_keys(self, q: int, steps: int, direction: int, T: int, r: int = 0) -> tuple[np.ndarray, int]:
        """Keys [T]: `direction` held from mask frame r until it has driven `steps` physics steps, then released
        (the person: toward m frames then release; r > 0 = release-first). Returns (keys, last driven sweep index;
        -1 when the steps do not fit in T)."""
        keys = np.zeros(T, np.int64)
        if steps <= 0:
            return keys, r
        got, t = 0, r
        while t < T and got < steps:
            keys[t] = direction
            got += self.st[q, t + 2] if t + 2 <= self.T else 1
            t += 1
        return keys, (t + 1 if got >= steps else -1)

    def apex_node(self, x0: float, q: int, h: int, x_target: float, r: int = 0, key0: int = 0) -> dict | None:
        """(b) a ground jump with hold h from the node (x0, q) to its apex at the lattice point nearest x_target: the
        keys (toward the target from mask frame r for m = |dx| / STEP_U steps, then released), the apex (sweep index,
        x, box bottom) and the sweep to the landing. None: the target is out of the apex's reach."""
        p = self.jumps[(h, q)]
        d0 = key0 * self.step_u * self.st[q, 1]                 # the node's own key moves frame 1
        m = int(round(abs(x_target - x0 - d0) / self.step_u))
        direction = 1 if x_target >= x0 + d0 else -1
        if m > self.reach_steps(q, p.apex, r):
            return None
        n = (p.land + 1) if p.land > 0 else len(p.y)
        keys, _ = self.solve_keys(q, m, direction, n - 1, r)
        sw, _ = self.sweep(x0, q, keys, "jump", h, key0, n=n)
        return {"keys": keys, "apex": p.apex, "x": float(sw.box[p.apex, 0] + self.hw), "y": float(sw.box[p.apex, 1]),
                "land": p.land, "x_land": float(sw.box[p.land, 0] + self.hw) if p.land > 0 else None,
                "q_apex": self.q_after(q, p.apex), "sweep": sw}

    def cone(self, q: int, n: int, key0: int = 0) -> tuple[float, float]:
        """(c) the horizontal reach after n frames from a node with cycle position q holding key0: the displacement
        interval [lo, hi] over every schedule (no inertia: the run cone; the umbrella stays inside it, sg1_validate)."""
        d0 = key0 * self.step_u * self.st[q, 1]
        w = self.step_u * self.reach_steps(q, n)
        return d0 - w, d0 + w

    def reach_steps(self, q: int, n: int, r: int = 0) -> int:
        """Physics steps a key held from mask frame r can drive by sweep index n (the horizontal cone's half width
        / STEP_U, the node's own key aside)."""
        return int(self.st[q, r + 2:n + 1].sum()) if n >= r + 2 else 0

    # ---- (b) ground jump, (c) apex -> fall, (e) landing ----
    def jump(self, h: int, q: int) -> VProfile:
        return self.jumps[(h, q)]

    def apex_classes(self) -> list[dict]:
        """The distinct (apex frame, apex height, landing frame) of the ground jumps, per hold over the six q."""
        out = []
        for h in self.holds:
            ps = [self.jumps[(h, q)] for q in range(6)]
            out.append({"h": h, "apex": [p.apex for p in ps], "height": [round(float(p.y[p.apex]), 4) for p in ps],
                        "land": [p.land for p in ps]})
        return out

    def track(self, kind: str, param: int, q: int, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(box bottom y absolute, pos y - box bottom, flags) for n sweep indexes of a ground node: "stand" (no
        jump) or "jump" with hold `param`."""
        if kind == "stand":
            fl = np.full(n, kin.F_GROUND, np.int64)
            return np.full(n, self.stand_y0), np.full(n, self.jumps[(1, q)].py[0]), fl
        p = self.jumps[(param, q)]
        if n > len(p.y):
            raise ValueError("sweep longer than the jump table")
        return self.stand_y0 + p.y[:n], p.py[:n].copy(), p.flags[:n].copy()

    def splice_bounce(self, y: np.ndarray, py: np.ndarray, fl: np.ndarray, c: int, q: int) -> int:
        """In place: from contact index c of a track whose node has cycle position q, the bounce (the free-space
        profile of the contact frame's cycle position, clipped at the floor). Returns the landing index (-1)."""
        b = self.bounces[(q - c) % 6]
        m = min(len(y) - c, len(b.y))
        y[c + 1:c + m] = y[c] + b.y[1:m]
        py[c + 1:c + m] = b.py[1:m]
        fl[c:c + m] = b.flags[:m]
        y[c + m:] = y[c + m - 1]
        land = -1
        below = np.flatnonzero((y[c + 1:] <= self.stand_y0 + 1e-6)) + c + 1
        below = below[below > c + b.apex]
        if len(below):
            land = int(below[0])
            y[land:] = self.stand_y0
            fl[land:] = (fl[land:] | kin.F_GROUND) & ~kin.F_JUMPING
        # the rendered y after the contact: the body minus the render lag of the last physics step's displacement
        # (the free-space profile's own render offset holds only once a step has run after the contact, and not on
        # the landing frames)
        for j in range(c + 1, len(y)):
            L = j
            while L > 0 and (q - L) % 6 == 0:
                L -= 1
            py[j] = self.params.foot - self.lag[q, j] * (y[L] - y[L - 1])
        return land

    def sweep(self, x0: float, q: int, keys: np.ndarray, kind: str = "stand", param: int = 1, key0: int = 0,
              press: int | None = None, face: int | None = None, targets=None, contact: int | None = None,
              alt: bool | None = None, n: int | None = None) -> tuple[Sweep, int]:
        """A macro from a ground node (x0, cycle position q) under the horizontal schedule keys [n - 1] (-1 / 0 / +1):
        stand (ground steps) or a ground jump (hold `param`); optionally a down slash pressed on mask index `press`
        (the press frame = sweep index press + 1) with the slash facing `face` (default: the key held at the press,
        else the last key, else +1) against targets(j) -> [m, 4] boxes; its contact (or the given `contact`) splices
        the bounce in. Returns (the sweep, the contact index or -1)."""
        n = len(keys) + 1 if n is None else n
        keys = np.asarray(keys)[:n - 1]
        y, py, fl = self.track(kind, param, q, n)
        y, py, fl = y.copy(), py.copy(), fl.copy()
        land = -1
        if kind == "jump":
            land = self.jumps[(param, q)].land if self.jumps[(param, q)].land < n else -1
        cx = self.run_x(x0, keys, q, key0)[:n]
        px = self.pos_x(cx, keys, q, key0)[:n]
        sw = Sweep(np.stack([cx - self.hw, y, cx + self.hw, y + self.H], axis=-1), np.stack([px, y + py], axis=-1),
                   fl, land)
        c = -1
        if press is not None:
            if face is None:
                held = keys[:press + 1][keys[:press + 1] != 0]
                face = int(held[-1]) if len(held) else (key0 or 1)
            pj = press + 1
            c = contact if contact is not None else (self.contact(sw, pj, face, targets, alt) if targets else -1)
            if c >= 0:
                land = self.splice_bounce(y, py, fl, c, q)
                sw = Sweep(np.stack([cx - self.hw, y, cx + self.hw, y + self.H], axis=-1),
                           np.stack([px, y + py], axis=-1), fl, land)
        return sw, c

    def landing(self, sw: Sweep, after: int = 0) -> int:
        """The first grounded index after `after` (-1: none)."""
        g = np.flatnonzero((sw.flags[after + 1:] & kin.F_GROUND) != 0)
        return after + 1 + int(g[0]) if len(g) else -1

    # ---- (d) the down slash: contact, bounce, i-frames, cooldown ----
    def contact_interval(self, pos_rel: np.ndarray, face: int, box: np.ndarray, alt: bool | None = None
                         ) -> tuple[float, float] | None:
        """The open interval of hero x offsets (added to pos_rel's x) for which the slash at rendered pos pos_rel
        meets the box (x0, x1, y0, y1): T1's rule (the polygon clipped to the box's y band)."""
        r = clip_band(slash_poly(face, alt) + pos_rel, box[2], box[3])
        if r is None or not np.isfinite(box[0]):
            return None
        return box[0] - r[1], box[1] - r[0]

    def contact(self, sw: Sweep, press_j: int, face: int, boxes, alt: bool | None = None) -> int:
        """The first sweep index in press_j + ACTIVE where the slash meets a target box (boxes(j) -> [n, 4] x0, x1,
        y0, y1 at sweep index j), -1: none. No swing when grounded on press_j - 1 (a grounded down + attack is a
        side slash); the swing ends on landing."""
        if press_j < 1 or (sw.flags[press_j - 1] & kin.F_GROUND):
            return -1
        g = np.flatnonzero((sw.flags[press_j:] & kin.F_GROUND) != 0)
        last = press_j + int(g[0]) - 1 if len(g) else len(sw.flags) - 1
        for j in range(press_j + ACTIVE[0], min(press_j + ACTIVE[1], last) + 1):
            for b in boxes(j):
                iv = self.contact_interval(sw.pos[j] - np.array([sw.box[j, 0] + self.hw, 0.0]), face, b, alt)
                cx = sw.box[j, 0] + self.hw
                if iv is not None and iv[0] < cx < iv[1]:
                    return j
        return -1

    def bounce(self, qc: int) -> VProfile:
        """The bounce from a contact on a frame with cycle position qc (sweep index 0 = the contact frame)."""
        return self.bounces[qc]

    def iframes(self, qc: int) -> tuple[int, int]:
        inv = np.flatnonzero((self.bounces[qc].flags & kin.F_INVULN) != 0)
        return int(inv[0]), int(inv[-1])

    def cooldown(self, q: int = 0, press: int = 10) -> int:
        """Frames from a press to the first second press that swings (rollout, jump held: airborne)."""
        T = press + 40
        M = np.zeros((25, T), np.int64)
        M[:, :30] = M_J
        M[:, press] |= M_A
        for i, d in enumerate(range(5, 30)):
            M[i, press + d] |= M_A
        ro = self._roll(self._start(q), M)
        for i, d in enumerate(range(5, 30)):
            att = (ro.flags[i] & kin.F_ATTACKING) != 0
            on = np.flatnonzero(att[1:] & ~att[:-1]) + 1
            if (on > press + 1).any():
                return d
        return -1

    # ---- the umbrella (an alternative fall input) ----
    def glide(self, h: int, q: int, u: int, key: int = 0) -> Sweep:
        """A ground jump h whose fall opens the umbrella with a jump press u frames after the apex (held to the
        landing), with `key` held from the press: rollout (the glide has horizontal inertia)."""
        ck = (h, q, u, key)
        if ck not in self._glides:
            p = self.jumps[(h, q)]
            t0 = p.apex + u
            T = self.T
            m = np.zeros((1, T), np.int64)
            m[0, :h] = M_J
            m[0, t0 - 1:] |= M_J
            m[0, t0 - 1:] |= key_mask(key)
            ro = self._roll(self._start(q), m)
            fl = ro.flags[0]
            g = np.flatnonzero((fl[p.apex:] & kin.F_GROUND) != 0)
            self._glides[ck] = Sweep(ro.box[0] - np.array([self.xw, 0, self.xw, 0]),
                                     ro.pos[0] - np.array([self.xw, 0]), fl.copy(), p.apex + int(g[0]) if len(g) else -1)
        return self._glides[ck]

    # ---- the hull over q (the map has no q dimension) ----
    def sweep_hull(self, x0: float, keys: np.ndarray, kind: str = "jump", param: int = 1, key0: int = 0,
                   **kw) -> np.ndarray:
        """[n, 4] per index the union box (x0, y0, x1, y1) over the six cycle positions: the conservative swept box
        of a macro for the map, which has no q dimension."""
        B = np.stack([self.sweep(x0, q, keys, kind, param, key0, **kw)[0].box for q in range(6)])
        return np.stack([B[..., 0].min(0), B[..., 1].min(0), B[..., 2].max(0), B[..., 3].max(0)], axis=-1)


__all__ = ["HeroMacros", "VProfile", "Sweep", "ALPHAS", "COOLDOWN_F", "IFRAMES", "PRE_PROTECT_F", "MARGINS", "RENDER_U",
           "key_mask"]
