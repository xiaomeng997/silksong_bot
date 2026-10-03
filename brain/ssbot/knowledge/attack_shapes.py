"""Hero attack shapes per crest (M2 W8; DESIGN §3.5.6 "use each crest's down polygon"): the game's damage collider
polygons of every swing, placed at the hero, with the window in which each is out, as data the planner and the
audit tools read (knowledge/<build>/attacks/<crest>.json, built by ssbot.tools.attack_table_build).

    tab = AttackTable.load("Reaper")
    sh = tab["down"]                         # AttackShape: polys in the facing frame, active window, hit src name
    P, starts = sh.world(cx, cy, face)        # world polygons at the hurtbox centre (cx, cy), facing +-1
    hit = tab.meets("normal", cx, cy, face, target_verts, target_starts)

Why polygons and not boxes: the down-slash audit (probes.md "M2: down-slash whiffs", run 20261002_152649) showed
the clash polygon's bounding box predicted 120 false contacts in 464 Hunter down spikes, the damage polygon 25.
Coordinates: x forward along the facing, y up, relative to the hero collider centre (STATE hero.box centre), the
frame the planner and attack_shape_audit already use. Polygons come from the oracle's slash.dump (world space as
the transforms are, the swing's own scale applied: "shapes_swing" when it differs from the idle localScale); the
active window is the NailSlash clip's first two non-"Bounce" animation events (the collider is enabled between
them), or, where the live per-frame sampling (tools/attack_table_build --live) saw it, the frames it was enabled.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
ROOT = REPO / "knowledge" / "1.0.30000" / "attacks"


@dataclass(frozen=True)
class AttackShape:
    slot: str                      # normal, alt, up, alt_up, wall, down, alt_down, dash_stab, charge, taunt
    src: str                       # name(s) of the damaging object(s), "|"-joined (the "hit" event's d.src)
    polys: tuple                   # of [n, 2] float arrays: damage collider outlines, facing frame
    t_on: float                    # active window in scaled s after the swing starts (StartSlash)
    t_off: float
    frames: tuple = ()             # (first, last) rendered frame after the attack's start frame the collider is on,
    #                                as sampled live; () when only the clip timing is known
    damage_mult: float = 1.0       # nail damage multiplier of the damager
    clash_box: tuple = ()          # (x0, x1, y0, y1) of the Clash Tink polygon (parry / clash reach), facing frame
    source: str = ""

    @property
    def box(self) -> tuple[float, float, float, float]:
        """(x0, x1, y0, y1) over all polygons, facing frame."""
        v = np.concatenate(self.polys)
        return float(v[:, 0].min()), float(v[:, 0].max()), float(v[:, 1].min()), float(v[:, 1].max())

    def world(self, cx: float, cy: float, face: int) -> tuple[np.ndarray, np.ndarray]:
        """(verts [m, 2], starts [k + 1]) of the polygons placed at the hurtbox centre with the facing (+1 right),
        in the concatenated form the planner's polygon kernels take."""
        f = 1.0 if face >= 0 else -1.0
        vs = [np.c_[cx + f * p[:, 0], cy + p[:, 1]] for p in self.polys]
        return np.ascontiguousarray(np.concatenate(vs)), np.cumsum([0] + [len(p) for p in vs]).astype(np.int64)


@dataclass
class AttackTable:
    crest: str
    build: str
    config: dict                   # attack duration / cooldown / recovery, down slash type, from the crest config
    shapes: dict = field(default_factory=dict)      # slot -> AttackShape
    recoil: dict = field(default_factory=dict)      # nail recoil on a hit (velocity, steps), from the decomp + logs
    notes: list = field(default_factory=list)

    def __getitem__(self, slot: str) -> AttackShape:
        return self.shapes[slot]

    def __contains__(self, slot: str) -> bool:
        return slot in self.shapes

    def by_src(self, src: str) -> AttackShape | None:
        return next((s for s in self.shapes.values() if src in s.src.split("|")), None)

    def meets(self, slot: str, cx: float, cy: float, face: int, verts: np.ndarray, starts: np.ndarray) -> bool:
        """Some polygon of the swing at (cx, cy, face) overlaps some target polygon (verts / starts as world())."""
        P, ps = self.shapes[slot].world(cx, cy, face)
        return polys_overlap(P, ps, np.asarray(verts, float), np.asarray(starts, np.int64))

    @classmethod
    def load(cls, crest: str, root: Path = ROOT) -> "AttackTable":
        d = json.loads((Path(root) / f"{crest.lower()}.json").read_text(encoding="utf-8"))
        shapes = {}
        for k, s in d["shapes"].items():
            shapes[k] = AttackShape(slot=k, src=s["src"], polys=tuple(np.asarray(p, float) for p in s["polys"]),
                                    t_on=float(s["t_on"]), t_off=float(s["t_off"]),
                                    frames=tuple(s.get("frames") or ()), damage_mult=float(s.get("damage_mult", 1.0)),
                                    clash_box=tuple(s.get("clash_box") or ()), source=s.get("source", ""))
        return cls(d["crest"], d["build"], d.get("config", {}), shapes, d.get("recoil", {}), d.get("notes", []))

    def to_json(self) -> dict:
        return {"crest": self.crest, "build": self.build, "config": self.config, "recoil": self.recoil,
                "notes": self.notes,
                "shapes": {k: {"src": s.src, "polys": [np.round(p, 4).tolist() for p in s.polys], "t_on": s.t_on,
                               "t_off": s.t_off, "frames": list(s.frames), "damage_mult": s.damage_mult,
                               "clash_box": list(s.clash_box), "source": s.source}
                           for k, s in self.shapes.items()}}

    def save(self, root: Path = ROOT) -> Path:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        p = root / f"{self.crest.lower()}.json"
        p.write_text(json.dumps(self.to_json(), indent=1) + "\n", encoding="utf-8")
        return p


def _poly_overlap(a: np.ndarray, b: np.ndarray) -> bool:
    """Two convex-or-not simple polygons overlap: an edge pair crosses, or a vertex of one lies inside the other."""
    def inside(p, poly):
        x, y = p
        c = False
        n = len(poly)
        for i in range(n):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % n]
            if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                c = not c
        return c

    def cross(p, q, r, s):
        def orient(a_, b_, c_):
            return (b_[0] - a_[0]) * (c_[1] - a_[1]) - (b_[1] - a_[1]) * (c_[0] - a_[0])
        d1, d2 = orient(r, s, p), orient(r, s, q)
        d3, d4 = orient(p, q, r), orient(p, q, s)
        return (d1 * d2 < 0) and (d3 * d4 < 0)

    if a[:, 0].max() < b[:, 0].min() or b[:, 0].max() < a[:, 0].min() or \
            a[:, 1].max() < b[:, 1].min() or b[:, 1].max() < a[:, 1].min():
        return False
    na, nb = len(a), len(b)
    for i in range(na):
        for j in range(nb):
            if cross(a[i], a[(i + 1) % na], b[j], b[(j + 1) % nb]):
                return True
    return inside(a[0], b) or inside(b[0], a)


def polys_overlap(P: np.ndarray, ps: np.ndarray, Q: np.ndarray, qs: np.ndarray) -> bool:
    """Any polygon of (P, ps) overlaps any of (Q, qs) (concatenated verts + starts). Pure Python: for audits and
    offline tools; the planner has its own compiled test (planner._poly_meets_polys)."""
    for i in range(len(ps) - 1):
        a = P[ps[i]:ps[i + 1]]
        for j in range(len(qs) - 1):
            if _poly_overlap(a, Q[qs[j]:qs[j + 1]]):
                return True
    return False
