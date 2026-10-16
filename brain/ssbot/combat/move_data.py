"""One move-data format for every (enemy, move) (task 1v1 SG1, the person's space-time map design 2026-10-12..14,
forum.md 55): what the map builder (SG2) and later moves read instead of slam-only code (pogo_slam.SlamTimeline,
specials.MOVES, special_mode._TL, T1's constants).

A move is a sequence of states. Each state has the frame counts it was seen to last (with how often), and the boxes
the enemy shows in it, per frame in the state. A timing variant picks one frame count per state (and a physics phase
for the motion); MoveSpec.timeline builds its per-frame arrays.

    spec = load_cl_slam()                       # knowledge/.../pogo_clapper_slam.json (the source SlamTimeline reads)
    tl = spec.timeline()                         # nominal timing; spec.variants("t1") = T1's nine, ("observed") all seen
    tl.box("Slam Collider 1", k)                 # [.., 4] x0, x1, y0, y1 with the lunge applied (nan: off)
    tl.damage(k), tl.targets(k)                  # every box that hurts the hero / that a slash must touch at frame k
    spec2 = load_raster_move("ChoirClapper", "CC_EVADE")   # a move from the hitbox rasters (damage only, no target)

Frame clock (every move): k = 0 is the first frame the enemy's FSM reads the move's first state (the antic); one frame
= 1/60 s of game time; the boxes are the ones exported for that frame. Motion (a lunge) is set on a state's entry frame
and moves the enemy in 0.02 s physics steps (MoveSpec.motion; the raster moves have it baked into the boxes).

Frame of reference (every move): x along the enemy's facing (+x = the side it faces) relative to its transform
position at k = 0 (the "anchor"); y relative to that position's y, which stands pos_above_floor above the floor. The
hero's map coordinate is the same: hero x relative to the anchor along the facing. The facing rule says when the
facing is fixed (the Clapper: it faces the hero at k = 0 and never turns during the move).

Box roles: "hurt" = touching it damages the hero (a DamageHero collider); "target" = the strike target: a slash that
touches it lands (an enemy hurtbox: a hit and a bounce); "tink" = a clashable attack collider (bounce, no damage). A
box with no role is drawn only. The Clapper's root box is "hurt" + "target" (its body DamageHero and its hurtbox are
the same collider); its hammer, Slam Collider 1 / 2, is "hurt" only (parry 4: a slash passes through it). A strike
cell of the map is a hero state whose slash polygon meets a "target" box over the slash's active frames.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
FORUM = REPO / "knowledge" / "1.0.30000" / "enemies" / "forum"
MOVES_DIR = REPO / "knowledge" / "1.0.30000" / "moves"
SLAM_TEMPLATE = FORUM / "pogo_clapper_slam.json"

HURT, TARGET, TINK = "hurt", "target", "tink"
FRAME_S = 1.0 / 60.0          # the theory's frame (SlamTimeline's ft)
PHYSICS_DT = 0.02

CLOCK = ("k = 0: the first frame the FSM reads the move's first state; 1 frame = 1/60 s game time; boxes as exported "
         "for that frame; motion in 0.02 s physics steps")
FRAME_REF = ("x along the enemy's facing relative to its transform position at k = 0; y relative to that position "
             "(pos_above_floor above the floor)")


@dataclass
class StateSpec:
    """One state of a move: the frame counts seen (count -> how many instances) and the nominal one."""
    name: str
    frames: dict
    nominal: int

    def share(self, n: int) -> float:
        tot = sum(self.frames.values())
        return self.frames.get(n, 0) / tot if tot else 0.0


@dataclass
class Track:
    """A named box over the move. by_state: state -> [n, 4] (x0, x1, y0, y1) per frame in the state (the last row
    repeats when the state lasts longer; a nan row = off; a state not listed = off). by_frame: [K, 4] per move frame
    k instead (raster sources: the timing spread is already in the union). after: the box past the last state (None:
    off; "last": the move's last row stays, as SlamTimeline does)."""
    name: str
    roles: frozenset
    by_state: dict = field(default_factory=dict)
    by_frame: np.ndarray | None = None
    after: np.ndarray | None = None
    poly: np.ndarray | None = None     # SG7: the collider's real shape when it is a polygon ([m, 2] x, y in the same
                                       # frame as the boxes, without the motion); the box is its bounding box


@dataclass
class Motion:
    """A constant velocity along the facing (u/s), set on from_state's entry frame (in its Update, after that frame's
    physics) and kept until to_state's entry frame's Update (that frame's own steps still move): the enemy moves
    vx * dt in every 0.02 s physics step of the frames in between. The physics phase (where the 50 Hz steps fall among
    the 60 fps frames) is a timing variant: n steps after the entry = floor((k - k0) * FRAME_S / dt - phase) + 1."""
    vx: float
    from_state: str
    to_state: str


@dataclass
class MoveTimeline:
    """One timing variant, per move frame k (0 .. K-1)."""
    enemy: str
    move: str
    name: str
    state: list
    entry: dict                  # state -> entry frame
    boxes: dict                  # track name -> [K, 4] x0, x1, y0, y1 without the motion (nan: off)
    roles: dict                  # track name -> frozenset
    disp: np.ndarray             # [K] displacement along the facing (motion)
    pos_y: float
    end_k: int                   # the move's last frame (the last state's last frame)
    weight: float = 1.0          # the variant's share of the instances (independent states assumed)
    polys: dict = field(default_factory=dict)   # track name -> [m, 2] polygon (SG7; tracks without one: absent)
    frames: dict = field(default_factory=dict)  # state -> its frame count in this variant
    phase: float = 0.5           # the motion's physics phase

    @property
    def K(self) -> int:
        return len(self.state)

    def box(self, name: str, k) -> np.ndarray:
        """[.., 4] the track's box at frames k (clipped to the timeline) with the motion applied."""
        kk = np.clip(np.asarray(k), 0, self.K - 1)
        b = self.boxes[name][kk].copy()
        b[..., 0] += self.disp[kk]
        b[..., 1] += self.disp[kk]
        return b

    def _with(self, role: str, k: int) -> np.ndarray:
        out = [self.box(n, k) for n, r in self.roles.items() if role in r]
        out = [b for b in out if np.isfinite(b[0])]
        return np.array(out, float).reshape(-1, 4)

    def damage(self, k: int) -> np.ndarray:
        """[n, 4] every box that hurts the hero at frame k (motion applied)."""
        return self._with(HURT, k)

    def damage_shapes(self, k: int) -> list:
        """SG7: [(box [4], polygon [m, 2] or None)] of every shape that hurts the hero at frame k, motion applied (the
        same order as damage(k))."""
        out = []
        for n, r in self.roles.items():
            if HURT not in r:
                continue
            b = self.box(n, k)
            if not np.isfinite(b[0]):
                continue
            pg = self.polys.get(n)
            if pg is not None:
                pg = np.asarray(pg, float).copy()
                pg[:, 0] += self.disp[int(np.clip(k, 0, self.K - 1))]
            out.append((b, pg))
        return out

    def targets(self, k: int) -> np.ndarray:
        """[n, 4] every strike target at frame k (motion applied)."""
        return self._with(TARGET, k)


@dataclass
class MoveSpec:
    enemy: str
    move: str
    source: str
    states: list                 # [StateSpec] in order
    tracks: list                 # [Track]
    motion: list = field(default_factory=list)
    pos_above_floor: float = 0.0
    facing_rule: str = ""
    clock: str = CLOCK
    frame_ref: str = FRAME_REF
    phases: tuple = (0.5,)       # physics phases the variants take (the motion's step timing)
    nominal_phase: float = 0.5
    K: int = 160
    physics_dt: float = PHYSICS_DT
    notes: str = ""

    # ---- timelines ----
    def timeline(self, frames: dict | None = None, phase: float | None = None, K: int | None = None,
                 name: str | None = None) -> MoveTimeline:
        """The per-frame arrays of one timing variant: frames = {state: frame count} (missing: nominal)."""
        frames = dict(frames or {})
        phase = self.nominal_phase if phase is None else phase
        K = self.K if K is None else K
        seq = [(s.name, int(frames.get(s.name, s.nominal))) for s in self.states]
        state, entry = [], {}
        for s, n in seq:
            entry[s] = len(state)
            state += [s] * n
        end_k = len(state) - 1
        state = (state + ["after"] * K)[:K]
        boxes = {}
        for t in self.tracks:
            if t.by_frame is not None:
                b = np.full((K, 4), np.nan)
                n = min(K, len(t.by_frame))
                b[:n] = t.by_frame[:n]
                if t.after is not None and n < K:
                    b[n:] = t.after
                boxes[t.name] = b
                continue
            rows = []
            for s, n in seq:
                tb = t.by_state.get(s)
                for j in range(n):
                    rows.append(np.full(4, np.nan) if tb is None else np.asarray(tb[min(j, len(tb) - 1)], float))
            if isinstance(t.after, str):                    # "last": the move's last row stays
                fill = rows[-1] if rows else np.full(4, np.nan)
            else:
                fill = np.full(4, np.nan) if t.after is None else np.asarray(t.after, float)
            rows += [fill] * max(K - len(rows), 0)
            boxes[t.name] = np.asarray(rows[:K], float)
        disp = np.zeros(K)
        for m in self.motion:
            k0, k2 = entry[m.from_state], entry[m.to_state]
            step = m.vx * self.physics_dt
            for k in range(k0 + 1, K):
                kk = min(k, k2)
                n = np.floor((kk - k0) * FRAME_S / self.physics_dt - phase + 1e-9) + 1 if kk > k0 else 0
                disp[k] += step * max(n, 0)
        w = 1.0
        for s, n in seq:
            st = next(x for x in self.states if x.name == s)
            if len(st.frames) > 1:
                w *= st.share(n)
        tag = name or "".join(f"{s[:1]}{n}" for s, n in seq) + f"p{phase}"
        return MoveTimeline(self.enemy, self.move, tag, state, entry, boxes,
                            {t.name: t.roles for t in self.tracks}, disp, self.pos_above_floor, end_k, w,
                            {t.name: np.asarray(t.poly, float) for t in self.tracks if t.poly is not None},
                            dict(seq), float(phase))

    def variants(self, policy: str = "t1", min_share: float = 0.0) -> list[MoveTimeline]:
        """The timing variants. "t1": T1's nine for CL_SLAM (nominal + antic 48/49 x Slam 0 4/5 x phase 0.2/0.8);
        "observed": every combination of the seen frame counts with share >= min_share x every phase (weights:
        the product of the states' shares, the phase split evenly); "nominal": one."""
        if policy == "nominal":
            return [self.timeline()]
        if policy == "t1":
            if (self.enemy, self.move) != ("Song Heavy Sentry", "CL_SLAM"):
                raise ValueError("policy t1 is CL_SLAM's")
            out = [self.timeline(name="nominal")]
            for a, s0, p in itertools.product((48, 49), (4, 5), (0.2, 0.8)):
                out.append(self.timeline({"Slam Antic": a, "Slam 0": s0}, p))
            return out
        opts = [[n for n in sorted(s.frames) if s.share(n) >= min_share] or [s.nominal] for s in self.states]
        out = []
        for combo in itertools.product(*opts):
            fr = {s.name: n for s, n in zip(self.states, combo)}
            for p in self.phases:
                tl = self.timeline(fr, p)
                tl.weight /= len(self.phases)
                out.append(tl)
        return out

    # ---- the canonical file (knowledge/1.0.30000/moves/<enemy key>__<move>.json) ----
    def to_dict(self) -> dict:
        def arr(a):
            if a is None:
                return None
            a = np.round(np.asarray(a, float), 6)
            return np.where(np.isfinite(a), a, None).tolist()      # nan (off) -> null
        return {"format": "ssbot.move_data/1", "enemy": self.enemy, "move": self.move, "source": self.source,
                "clock": self.clock, "frame_ref": self.frame_ref, "facing_rule": self.facing_rule,
                "pos_above_floor": self.pos_above_floor, "phases": list(self.phases),
                "nominal_phase": self.nominal_phase, "K": self.K, "physics_dt": self.physics_dt, "notes": self.notes,
                "states": [{"name": s.name, "frames": {str(k): v for k, v in s.frames.items()}, "nominal": s.nominal}
                           for s in self.states],
                "motion": [{"vx": m.vx, "from": m.from_state, "to": m.to_state} for m in self.motion],
                "tracks": [{"name": t.name, "roles": sorted(t.roles),
                            "by_state": {s: arr(b) for s, b in t.by_state.items()},
                            "by_frame": arr(t.by_frame),
                            "after": t.after if isinstance(t.after, str) else arr(t.after),
                            **({"poly": arr(t.poly)} if t.poly is not None else {})} for t in self.tracks]}

    @classmethod
    def from_dict(cls, d: dict) -> "MoveSpec":
        def arr(a):
            return None if a is None else np.asarray(a, dtype=float)     # null -> nan
        return cls(d["enemy"], d["move"], d["source"],
                   [StateSpec(s["name"], {int(k): v for k, v in s["frames"].items()}, s["nominal"]) for s in d["states"]],
                   [Track(t["name"], frozenset(t["roles"]), {s: arr(b) for s, b in t["by_state"].items()},
                          arr(t["by_frame"]), t["after"] if isinstance(t["after"], str) else arr(t["after"]),
                          arr(t.get("poly")))
                    for t in d["tracks"]],
                   [Motion(m["vx"], m["from"], m["to"]) for m in d["motion"]], d["pos_above_floor"],
                   d["facing_rule"], d["clock"], d["frame_ref"], tuple(d["phases"]), d["nominal_phase"], d["K"],
                   d["physics_dt"], d.get("notes", ""))

    def save(self, path: Path | None = None) -> Path:
        path = Path(path) if path else MOVES_DIR / f"{self.enemy.replace(' ', '_')}__{self.move}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), allow_nan=False), "utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "MoveSpec":
        return cls.from_dict(json.loads(Path(path).read_text("utf-8")))


# ---- loaders ----
# SG7 (forum.md 63): Slam Collider 1 / 2 are PolygonCollider2Ds (the oracle exports kind "poly" and their world
# vertices); rigid in the Clapper's frame (x along its facing, y relative to its position): the median of 15,560 / 25,390
# recorded frames, max vertex deviation 0.0009 u (ssbot.tools.sg7_c2rule); their bounding boxes are the template's
# hammer boxes to 0.001 u. The template keeps the boxes; load_cl_slam(poly=True) attaches these shapes.
HAMMER_POLY = {
    "Slam Collider 1": ((-1.91, 2.854), (1.739, 3.129), (4.067, 2.645), (6.089, 1.524), (6.236, 0.505),
                        (5.297, 0.014), (1.966, -3.185)),
    "Slam Collider 2": ((2.399, 0.754), (4.067, 2.645), (6.089, 1.523), (7.755, -4.194), (7.166, -4.987),
                        (0.674, -3.62)),
}


# SG7 review (forum.md 63.5): the physics order. A frame runs its physics step (the lunge moves the Clapper, triggers
# fire with the colliders enabled now) before Update (the FSM leaves Slam 1 / Slam 2 and disables that hammer), so a
# hammer collider still hurts in the first frame of the next state, at that frame's position (the lunge's last step
# lands on the Slam 2 entry frame). Recordings: 30 of 315 Slam Collider 1 hp losses are logged on a Slam 2 frame, 2
# Slam Collider 2 losses on a Slam Recover frame; carried one frame, the polygon covers every hammer hp loss but 2
# (box: 9 missed). load_cl_slam(carry=True) adds that frame; the defaults keep the old maps.
HAMMER_CARRY = {"Slam 1": "Slam 2", "Slam 2": "Slam Recover"}


def load_cl_slam(path: Path = SLAM_TEMPLATE, K: int = 160, poly: bool = False, carry: bool = False) -> MoveSpec:
    """CL_SLAM (the Clapper's slam) from the template SlamTimeline reads: the root box per frame in each state (its
    last row repeats; past the move the last recover box stays), the hammer (Slam Collider 1 in Slam 1, Slam Collider
    2 in Slam 2) and the lunge (30 u/s from the Slam 0 entry to the Slam 2 entry). Nominal and T1's variants keep
    Slam 1 3, Slam 2 6, Slam Recover 15 frames, as SlamTimeline does; "observed" also takes antic 47, Slam 2 5 and
    Recover 14 / 16 (the durations the 1,661 template slams showed)."""
    t = json.loads(Path(path).read_text("utf-8"))
    dur = t["durations"]
    nominal = {"Slam Antic": 49, "Slam 0": 5, "Slam 1": 3, "Slam 2": 6, "Slam Recover": 15}
    states = [StateSpec(s, {int(k): v for k, v in dur[s].items()}, nominal[s]) for s in nominal]
    root = {s: np.asarray(b, float) for s, b in t["root"].items()}
    tracks = [Track("root", frozenset({HURT, TARGET}), root, after="last")]
    for key, b in t["hammer"].items():
        s, nm = key.split("|")
        pg = None
        if poly and nm in HAMMER_POLY:
            pg = np.asarray(HAMMER_POLY[nm], float)
            bb = [pg[:, 0].min(), pg[:, 0].max(), pg[:, 1].min(), pg[:, 1].max()]
            if np.abs(np.asarray(bb) - np.asarray(b, float)).max() > 0.01:
                raise ValueError(f"{nm}: the polygon's bounding box {bb} is not the template box {b}")
        by_state = {s: np.asarray([b], float)}
        if carry and s in HAMMER_CARRY:          # on in the next state's first frame only (a nan row = off after it)
            by_state[HAMMER_CARRY[s]] = np.asarray([b, [np.nan] * 4], float)
        tracks.append(Track(nm, frozenset({HURT}), by_state, poly=pg))
    motion = [Motion(float(t.get("lunge_vx", 30.0)), "Slam 0", "Slam 2")]
    return MoveSpec("Song Heavy Sentry", "CL_SLAM", f"{Path(path).name} ({t['n_slams']} slams)", states, tracks,
                    motion, float(t["pos_above_floor"]),
                    "faces the hero at k = 0 (the antic entry) and never turns during the move (0 of 2,328 slams)",
                    phases=(0.2, 0.8), nominal_phase=0.5, K=K, physics_dt=float(t.get("physics_dt", 0.02)),
                    notes="root = body DamageHero + hurtbox; Slam Collider 1 / 2 = the hammer (parry 4: a slash passes "
                          "through it, no bounce); bounce i-frames cover both (pogo_slam)")


def raster_boxes(tpl, k: int, tol_bins: int = 1) -> np.ndarray:
    """[n, 4] x0, x1, y0, y1 covering a hitbox template's occupancy at frame k (+- tol_bins: the export lag rule of
    hitbox_tables for raw templates)."""
    from ssbot.knowledge.hitbox_tables import mask_boxes
    m = np.zeros((tpl.ny, tpl.nx), bool)
    for b in range(k - tol_bins, k + tol_bins + 1):
        m |= tpl.plane(b)
    bx = mask_boxes(m).astype(float)
    if not len(bx):
        return np.zeros((0, 4))
    c = tpl.cell
    return np.stack([(bx[:, 0] + tpl.ix0) * c, (bx[:, 2] + tpl.ix0) * c, (bx[:, 1] + tpl.iy0) * c,
                     (bx[:, 3] + tpl.iy0) * c], axis=1)


def load_raster_move(enemy_key: str, family: str, enemy: str | None = None, tol_bins: int = 1,
                     model_dir: Path = FORUM) -> MoveSpec:
    """A move from the behaviour model's hitbox rasters (<enemy_key>_hitboxes.npz "<family>/anchor": the union over
    every logged instance of the enabled damage colliders, 0.05 u cells grown by one cell, per 1/60 s bin from the
    attack start, in the anchor frame, so the motion and the timing spread are inside the boxes) and its state timing
    (<enemy_key>.json attacks.<family>.state_entry_s / duration_s). Each frame's occupancy (+- tol_bins) becomes a few
    boxes (exact cover, hitbox_tables.mask_boxes), stored as box slots "dmg#i" (nan where a frame has fewer).
    Damage only: a raster cannot give the strike target (a grown union is optimistic for a slash), so no box has the
    "target" role; a strike map of such a move needs a body track from the recordings first."""
    from ssbot.knowledge.hitbox_tables import load_templates
    meta = json.loads((model_dir / f"{enemy_key}.json").read_text("utf-8"))
    att = meta["attacks"][family]
    tpls, _ = load_templates(model_dir / f"{enemy_key}_hitboxes.npz", prefix=f"{family}/anchor")
    tpl = tpls[f"{family}/anchor"]
    per = [raster_boxes(tpl, k, tol_bins) for k in range(tpl.nt)]
    n_slot = max((len(b) for b in per), default=0)
    tracks = []
    for i in range(n_slot):
        a = np.full((tpl.nt, 4), np.nan)
        for k, b in enumerate(per):
            if i < len(b):
                a[k] = b[i]
        tracks.append(Track(f"dmg#{i}", frozenset({HURT}), by_frame=a))
    ent = att.get("state_entry_s", {})
    # the main path only: a state most instances enter (CC_EVADE's "Start Battle?" is the 40 deaths of 7,923)
    names = [s for s in att["states"] if s in ent and ent[s].get("n", 0) >= 0.5 * att.get("n", 0)]
    names.sort(key=lambda s: ent[s]["p50"])
    end_s = att.get("duration_s", {}).get("p50", tpl.nt * FRAME_S)
    states = []
    for i, s in enumerate(names):
        t0 = ent[s]["p50"]
        t1 = ent[names[i + 1]]["p50"] if i + 1 < len(names) else end_s
        nom = max(int(round((t1 - t0) * 60)), 1)
        states.append(StateSpec(s, {nom: 1}, nom))
    return MoveSpec(enemy or meta.get("boss_type", enemy_key), family,
                    f"{enemy_key}_hitboxes.npz {family}/anchor ({tpl.n_instances} instances, tol {tol_bins} bin) + "
                    f"{enemy_key}.json state timing", states, tracks, [], 0.0,
                    "anchor frame: +x = the facing at the attack start (the behaviour tables' direction rule)",
                    K=tpl.nt, notes="raster union over instances: motion and timing spread inside the boxes; boxes grown "
                                    "by one 0.05 u cell; y relative to the anchor; no strike target in this source")


__all__ = ["HURT", "TARGET", "TINK", "StateSpec", "Track", "Motion", "MoveTimeline", "MoveSpec", "load_cl_slam",
           "load_raster_move", "raster_boxes", "SLAM_TEMPLATE", "MOVES_DIR", "CLOCK", "FRAME_REF", "HAMMER_POLY",
           "HAMMER_CARRY"]
