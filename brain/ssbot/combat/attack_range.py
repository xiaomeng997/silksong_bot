"""Attack-range estimate (ARE, Task "attack range", the person 2026-10-10; docs/plans/forum_planner_plan.md sec. 5):
where an enemy's attack can really deal damage, per family and time since its antic start, with NO margin. Margins
are a later, decision-time choice (from the estimation error or from the bot's attack goal), not part of this.
One enemy at a time; the first is the Choristor (Song Pilgrim 03).

Model, per family F, branch B and time bin b (game frames since the antic start: the first frame the tracker sees
the family's start state), built from R0 dev only (tools.attack_range_build build):
  shape[F, B][b]  the union, over the clean R0 dev instances (not hit, no nail clash), of every real damage collider
                  of the enemy at bin b (attack + Body Damager + the multi-hit Whip Hit exported with dealt 0, the
                  rule of tools.zone_overlay.hurts), RELATIVE to the enemy's own position at that frame, in the
                  facing frame of the antic start (u forward, v up); a CELL u raster, cropped per bin. An instance that
                  has ended (left the family's states) contributes its idle body at its end position.
  disp[F, B][b]   the enemy's displacement from the anchor at bin b (u, v): the median over the instances. CH_JUMP:
                  u = ratio[b] x L, the landing predicted from the hero's offset at the antic start (L = alpha du +
                  beta, clamped to +-L_MAX). After the last bin: the last value (the idle body stays there).
  walls           the enemy's x stays inside the recorded extremes (the arena walls stop the lunges).
  branches        CH_SLASH combo / single (decided at Combo?), CH_HOP back / forward / up (Hop Check), CH_WHIP multi /
                  plain: a branch is known once its first state is seen; before that the estimate is the union of the
                  branches' estimates (the classifier's decision points).
  idle            Battle Idle and every state outside the families: the exact current body (its Body Damager now),
                  for every k: no growth, and no attack that has not started (group 2 is not part of this round).

The estimate at (enemy, k) is shape[b + k] placed at the enemy's predicted position for bin b + k (anchor + disp,
mirrored by the facing, x clamped by the walls). Hero-centre space (where the hero TRANSFORM must not be): the raw
region dilated by the hero hurtbox (HeroBox 0.4554 x 2.2498 u at (0, -0.38) from the hero transform). Nothing else.

Rasters live on one world lattice: cell ix covers x in [ix CELL, (ix + 1) CELL), row 0 of a mask is its lowest row.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
FORUM = REPO / "knowledge" / "1.0.30000" / "enemies" / "forum"
FT = 1.0 / 60.0
CELL = 0.05
HERO_HALF = (0.2277, 1.1249)          # HeroBox 0.4554 x 2.2498 u (the hurtbox) ...
HERO_DY = -0.38                       # ... centred 0.38 u below the hero transform
MW_SRC_BIT = 8                        # ipc.ents SRC_BITS["multi_wounder"]
PARKED = ("Ready", "Dormant", "Sleep", "Wait")


@dataclass(frozen=True)
class EnemySpec:
    type_key: str
    short: str
    fam_states: dict           # family -> its states (antic start .. end of recovery)
    start: dict                # state -> family (entering it starts an instance)
    primary: dict              # family -> the antic state whose re-entry restarts the family
    branch: dict               # family -> {state: branch} (the first marker seen decides)
    branches: dict             # family -> the branch names (one name: no branch)
    aim: frozenset             # families whose u displacement scales with the hero's offset at the antic start
    body: str                  # the body damager collider's name
    table: str                 # the table's file stem under FORUM


CHORISTOR = EnemySpec(
    type_key="Song Pilgrim 03", short="Choristor",
    fam_states={
        "CH_SLASH": frozenset({"Slash Antic", "Slash Antic Jump", "Slash 1", "Slash 2", "Slash End", "Combo?",
                               "ComboSlash Antic1", "ComboSlash Antic2", "ComboSlash 1", "ComboSlash 2", "ComboSlash 3",
                               "Slash Recover"}),
        "CH_WHIP": frozenset({"Whip Antic", "Whip 1", "Whip 2", "Whip 3", "Whip 4", "Whip 5", "Whip 6", "Whip End",
                              "Multiwhip"}),
        "CH_JUMP": frozenset({"Jump Antic", "Wait for Ground", "Jump Launch", "Jump Rise", "Jump Spin", "Spin Slash",
                              "Spin Slash End", "Quick Land"}),
        "CH_HOP": frozenset({"Hop Antic", "Hop Back", "Hop Forward", "Hop Up", "Ground Check", "Hop Land",
                             "Cancel To Hop Back", "Hop Check"}),
        "CH_ENTRY": frozenset({"Battle Wake", "Enter Antic 2", "Enter Leap 2", "Enter Fall", "Enter Land",
                               "Enter Idle", "Enter Antic", "Enter Leap"}),
    },
    start={"Slash Antic": "CH_SLASH", "Whip Antic": "CH_WHIP", "Jump Antic": "CH_JUMP", "Hop Antic": "CH_HOP",
           "Cancel To Hop Back": "CH_HOP", "Battle Wake": "CH_ENTRY", "Enter Antic 2": "CH_ENTRY",
           "Enter Leap 2": "CH_ENTRY"},
    primary={"CH_SLASH": "Slash Antic", "CH_WHIP": "Whip Antic", "CH_JUMP": "Jump Antic", "CH_HOP": "Hop Antic",
             "CH_ENTRY": "Battle Wake"},
    branch={"CH_SLASH": {"ComboSlash Antic1": "combo", "ComboSlash Antic2": "combo", "ComboSlash 1": "combo",
                         "ComboSlash 2": "combo", "ComboSlash 3": "combo", "Slash Recover": "single"},
            "CH_HOP": {"Hop Back": "back", "Cancel To Hop Back": "back", "Hop Forward": "forward", "Hop Up": "up"},
            # Multiwhip follows Whip k only when the whip caught the hero; a whip that runs to Whip 6 is plain
            "CH_WHIP": {"Multiwhip": "multi", "Whip 6": "plain", "Whip End": "plain"}},
    branches={"CH_SLASH": ("single", "combo"), "CH_HOP": ("back", "forward", "up"), "CH_WHIP": ("plain", "multi"),
              "CH_JUMP": ("main",), "CH_ENTRY": ("main",)},
    aim=frozenset({"CH_JUMP"}),
    body="Body Damager",
    table="attack_range_choristor",
)
SPECS = {CHORISTOR.type_key: CHORISTOR}


def hurts(dealt: int, eff: int, src: int) -> bool:
    """tools.zone_overlay.hurts on the exported fields: dealt > 0, or a multi-hit collider exported with dealt 0."""
    return dealt > 0 or (not dealt and eff != 0 and bool(int(src or 0) & MW_SRC_BIT))


# ------------------------------------------------------------------------------------------------ rasters

@dataclass
class Mask:
    """A world raster on the lattice: m [ny, nx] bool, m[0, 0] is cell (ix0, iy0) (row 0 = lowest y)."""
    m: np.ndarray
    ix0: int
    iy0: int

    def area(self, cell: float = CELL) -> float:
        return float(self.m.sum()) * cell * cell

    def bbox(self, cell: float = CELL):
        """(x0, y0, x1, y1) in world u of the set cells, or None."""
        rr, cc = np.nonzero(self.m)
        if not len(rr):
            return None
        return ((self.ix0 + cc.min()) * cell, (self.iy0 + rr.min()) * cell, (self.ix0 + cc.max() + 1) * cell,
                (self.iy0 + rr.max() + 1) * cell)


def empty_mask() -> Mask:
    return Mask(np.zeros((0, 0), bool), 0, 0)


def poly_mask(polys, cell: float = CELL, pad: int = 1) -> Mask:
    """The lattice cells whose centres lie inside any of the polygons (world u; cv2's fill, 1/16 cell precision:
    cells within half a cell of an edge are included, so a raster is at most one cell (0.05 u) larger per side; the
    estimate and the real colliders are rasterized the same way)."""
    import cv2
    polys = [np.asarray(p, np.float64).reshape(-1, 2) for p in polys if p is not None and len(p) >= 3]
    if not polys:
        return empty_mask()
    allp = np.vstack(polys)
    ix0 = int(math.floor(allp[:, 0].min() / cell)) - pad
    iy0 = int(math.floor(allp[:, 1].min() / cell)) - pad
    nx = int(math.floor(allp[:, 0].max() / cell)) + pad - ix0 + 1
    ny = int(math.floor(allp[:, 1].max() / cell)) + pad - iy0 + 1
    img = np.zeros((ny, nx), np.uint8)
    pts = [np.round(((p / cell) - (ix0 + 0.5, iy0 + 0.5)) * 16.0).astype(np.int32) for p in polys]
    cv2.fillPoly(img, pts, 1, lineType=cv2.LINE_8, shift=4)
    return Mask(img.astype(bool), ix0, iy0)


def union(masks) -> Mask:
    masks = [m for m in masks if m is not None and m.m.size and m.m.any()]
    if not masks:
        return empty_mask()
    if len(masks) == 1:
        return masks[0]
    ix0 = min(m.ix0 for m in masks)
    iy0 = min(m.iy0 for m in masks)
    ix1 = max(m.ix0 + m.m.shape[1] for m in masks)
    iy1 = max(m.iy0 + m.m.shape[0] for m in masks)
    out = np.zeros((iy1 - iy0, ix1 - ix0), bool)
    for m in masks:
        out[m.iy0 - iy0:m.iy0 - iy0 + m.m.shape[0], m.ix0 - ix0:m.ix0 - ix0 + m.m.shape[1]] |= m.m
    return Mask(out, ix0, iy0)


def on_canvas(m: Mask, ix0: int, iy0: int, shape) -> np.ndarray:
    """m on the canvas whose cell (0, 0) is (ix0, iy0) (cut where it leaves it)."""
    out = np.zeros(shape, bool)
    if not m.m.size:
        return out
    ny, nx = shape
    r0, c0 = m.iy0 - iy0, m.ix0 - ix0
    a0, b0 = max(r0, 0), max(c0, 0)
    a1, b1 = min(r0 + m.m.shape[0], ny), min(c0 + m.m.shape[1], nx)
    if a1 > a0 and b1 > b0:
        out[a0:a1, b0:b1] = m.m[a0 - r0:a1 - r0, b0 - c0:b1 - c0]
    return out


def hero_kernel(cell: float = CELL) -> tuple[np.ndarray, tuple[int, int]]:
    """(kernel, anchor) of cv2.dilate taking a raw damage raster (row 0 lowest) to hero-centre space: hero cell p is
    set when an occupied cell q (a CELL square) meets the hurtbox at p: |q_x - p_x| <= hx + c/2 and
    q_y - p_y in [HERO_DY - hy - c/2, HERO_DY + hy + c/2]."""
    hx, hy = HERO_HALF
    ni = int(math.floor((hx + cell / 2) / cell + 1e-9))
    lo = int(math.ceil((HERO_DY - hy - cell / 2) / cell - 1e-9))
    hi = int(math.floor((HERO_DY + hy + cell / 2) / cell + 1e-9))
    return np.ones((hi - lo + 1, 2 * ni + 1), np.uint8), (ni, -lo)


def hero_space(m: Mask, cell: float = CELL) -> Mask:
    """The hero-centre region of a raw damage raster (the only growth of the estimate)."""
    import cv2
    if not m.m.size or not m.m.any():
        return empty_mask()
    k, (ax, ay) = hero_kernel(cell)
    ph, pw = k.shape[0], k.shape[1]
    img = np.zeros((m.m.shape[0] + 2 * ph, m.m.shape[1] + 2 * pw), np.uint8)
    img[ph:ph + m.m.shape[0], pw:pw + m.m.shape[1]] = m.m
    d = cv2.dilate(img, k, anchor=(ax, ay), borderType=cv2.BORDER_CONSTANT, borderValue=0)
    return Mask(d.astype(bool), m.ix0 - pw, m.iy0 - ph)


def contours(m: Mask, cell: float = CELL) -> list[np.ndarray]:
    """Outer outlines of a mask as world polygons (cell corners)."""
    import cv2
    if not m.m.size or not m.m.any():
        return []
    img = np.zeros((m.m.shape[0] + 2, m.m.shape[1] + 2), np.uint8)
    img[1:-1, 1:-1] = m.m
    up = cv2.resize(img, (img.shape[1] * 2, img.shape[0] * 2), interpolation=cv2.INTER_NEAREST)
    cs, _ = cv2.findContours(up, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cs:
        p = c.reshape(-1, 2).astype(np.float64)
        # doubled raster: pixel edge 2i is the cell edge i; contour pixels lie inside, so push out half a pixel
        x = (m.ix0 - 1 + (p[:, 0] + 0.5) / 2.0) * cell
        y = (m.iy0 - 1 + (p[:, 1] + 0.5) / 2.0) * cell
        out.append(np.stack([x, y], axis=1))
    return out


# ------------------------------------------------------------------------------------------------ the table

@dataclass
class Template:
    """One family / branch: per bin the cropped shape raster (template lattice: cell iu covers u in
    [iu CELL, (iu + 1) CELL)), its crop origin and the median displacement; JUMP: the u ratio of the landing."""
    nb: int
    shape: list            # [nb] of np.ndarray [nv, nu] bool (row 0 = lowest v)
    origin: np.ndarray     # [nb, 2] int (iu0, iv0)
    disp: np.ndarray       # [nb, 2] float (u, v)
    ratio: np.ndarray | None = None   # [nb] (aim families)
    n: int = 0


@dataclass
class RangeTable:
    spec: EnemySpec
    templates: dict                 # (family, branch) -> Template
    meta: dict = field(default_factory=dict)
    cell: float = CELL

    @property
    def walls(self) -> tuple[float, float]:
        w = self.meta.get("walls") or (-1e9, 1e9)
        return float(w[0]), float(w[1])

    def facing(self, flip) -> int:
        """+1 / -1: the facing of an entity whose flipX is `flip` (measured from the attack colliders)."""
        f1 = int(self.meta.get("face_flip1", 1))
        return f1 if flip else -f1

    def branch_by_rule(self, fam: str, hero_du: float) -> str | None:
        """A pending branch already certain from the hero's offset at the antic start (meta branch_rule, the R0 dev
        extremes: CH_HOP goes forward only when the hero is farther than Hop Distance, so below the nearest forward
        hop it is back, beyond the farthest back hop it is forward); None: still open (the union)."""
        r = (self.meta.get("branch_rule") or {}).get(fam)
        if not r:
            return None
        if hero_du < r["lo"]:
            return r["below"]
        if hero_du > r["hi"]:
            return r["above"]
        return None

    def landing(self, hero_du: float) -> float:
        a, b = self.meta.get("jump_fit", (1.0, 0.0))
        lm = float(self.meta.get("jump_lmax", 15.0))
        return float(min(max(a * hero_du + b, -lm), lm))

    def place(self, fam: str, branch: str | None, b: int, anchor: tuple, s: int, hero_du: float = 0.0,
              now: tuple | None = None, b_now: int | None = None) -> Mask:
        """The raw estimate of bin b of an instance anchored at anchor = (x, y) with facing s: the union over the
        family's branches when branch is None. With now = the enemy's observed position at bin b_now, the position is
        re-anchored there: now + (the template's displacement at b - at b_now), so only the displacement still to
        come is predicted (what has happened is observed)."""
        brs = self.spec.branches.get(fam, ("main",))
        if branch is None:
            branch = self.branch_by_rule(fam, hero_du)
        if branch is not None and (fam, branch) in self.templates:
            brs = (branch,)
        return union([self._place1(self.templates[(fam, br)], b, anchor, s, hero_du, fam, now, b_now)
                      for br in brs if (fam, br) in self.templates])

    def position(self, tp: Template, b: int, anchor: tuple, s: int, hero_du: float, fam: str) -> tuple:
        bb = min(max(b, 0), tp.nb - 1)
        du, dv = float(tp.disp[bb, 0]), float(tp.disp[bb, 1])
        if tp.ratio is not None and fam in self.spec.aim:
            du = float(tp.ratio[bb]) * self.landing(hero_du)
        lo, hi = self.walls
        return min(max(anchor[0] + s * du, lo), hi), anchor[1] + dv

    def _place1(self, tp: Template, b: int, anchor: tuple, s: int, hero_du: float, fam: str,
                now: tuple | None = None, b_now: int | None = None) -> Mask:
        bb = min(max(b, 0), tp.nb - 1)
        sh = tp.shape[bb]
        if sh is None or not sh.size:
            return empty_mask()
        px, py = self.position(tp, b, anchor, s, hero_du, fam)
        if now is not None and b_now is not None:
            qx, qy = self.position(tp, b_now, anchor, s, hero_du, fam)
            lo, hi = self.walls
            px, py = min(max(now[0] + px - qx, lo), hi), now[1] + py - qy
        return place_shape(sh, int(tp.origin[bb, 0]), int(tp.origin[bb, 1]), px, py, s, self.cell)


def place_shape(sh: np.ndarray, iu0: int, iv0: int, px: float, py: float, s: int, cell: float = CELL) -> Mask:
    """A template-lattice raster (cell iu centre (iu + 0.5) c) at world (px, py), facing s, on the world lattice."""
    iy0 = iv0 + int(math.floor(py / cell + 0.5))
    if s >= 0:
        return Mask(sh, iu0 + int(math.floor(px / cell + 0.5)), iy0)
    iu1 = iu0 + sh.shape[1] - 1
    return Mask(sh[:, ::-1], int(math.floor(px / cell - 0.5)) - iu1, iy0)


def table_path(spec: EnemySpec = CHORISTOR, root: Path = FORUM) -> Path:
    return root / f"{spec.table}.npz"


def save_table(t: RangeTable, path: Path) -> Path:
    arrs: dict = {}
    keys = []
    for (fam, br), tp in sorted(t.templates.items()):
        key = f"{fam}|{br}"
        keys.append({"key": key, "nb": tp.nb, "n": tp.n, "aim": tp.ratio is not None})
        sizes = np.array([[s.shape[0], s.shape[1]] for s in tp.shape], np.int32)
        bits = np.concatenate([np.packbits(s.reshape(-1)) if s.size else np.zeros(0, np.uint8) for s in tp.shape])
        arrs[f"{key}/sizes"] = sizes
        arrs[f"{key}/bits"] = bits
        arrs[f"{key}/origin"] = tp.origin.astype(np.int32)
        arrs[f"{key}/disp"] = tp.disp.astype(np.float32)
        if tp.ratio is not None:
            arrs[f"{key}/ratio"] = tp.ratio.astype(np.float32)
    meta = dict(t.meta, keys=keys, cell=t.cell, type_key=t.spec.type_key)
    arrs["meta"] = np.frombuffer(json.dumps(meta).encode("utf-8"), np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrs)
    return path


def load_table(path: Path | None = None, spec: EnemySpec = CHORISTOR) -> RangeTable:
    path = Path(path) if path is not None else table_path(spec)
    z = np.load(path)
    meta = json.loads(bytes(z["meta"]).decode("utf-8"))
    spec = SPECS.get(meta.get("type_key"), spec)
    tps = {}
    for k in meta["keys"]:
        key = k["key"]
        sizes = z[f"{key}/sizes"]
        bits = z[f"{key}/bits"]
        shapes, o = [], 0
        for ny, nx in sizes:
            n = int(ny) * int(nx)
            nbytes = (n + 7) // 8
            shapes.append(np.unpackbits(bits[o:o + nbytes])[:n].reshape(int(ny), int(nx)).astype(bool))
            o += nbytes
        ratio = z[f"{key}/ratio"] if f"{key}/ratio" in z.files else None
        fam, br = key.split("|")
        tps[(fam, br)] = Template(nb=int(k["nb"]), shape=shapes, origin=z[f"{key}/origin"], disp=z[f"{key}/disp"],
                                  ratio=ratio, n=int(k.get("n", 0)))
    return RangeTable(spec=spec, templates=tps, meta=meta, cell=float(meta.get("cell", CELL)))


# ------------------------------------------------------------------------------------------------ segmentation

@dataclass
class Inst:
    """One family instance of one enemy: anchored at the first frame the tracker saw its start state."""
    fam: str
    t0: float
    x0: float
    y0: float
    s: int
    hero_du: float
    branch: str | None = None
    branch_t: float | None = None
    states: list = field(default_factory=list)


class Segmenter:
    """The family instances of one enemy from its per-frame state (the same rule offline and live): an instance
    starts when a start state is entered from outside the family, or when the family's primary antic is entered
    again; it ends at the first state outside the family's states (then the enemy is idle)."""

    def __init__(self, spec: EnemySpec):
        self.spec = spec
        self.cur: Inst | None = None
        self.prev: str | None = None

    def step(self, st: str | None, T: float, x: float, y: float, s: int, hero_x: float | None,
             tin: float = 0.0) -> Inst | None:
        """One frame: st and tin (its time in state) of the enemy's first FSM, game time T. A new instance is
        anchored here, its time origin back-dated by tin (the state's entry, also when first seen late)."""
        sp = self.spec
        cur = self.cur
        if cur is not None:
            fs = sp.fam_states[cur.fam]
            restart = st == sp.primary.get(cur.fam) and self.prev != st
            if st not in fs or restart:
                self.cur = cur = None
        if cur is None and st in sp.start and self.prev != st:
            fam = sp.start[st]
            du = 0.0 if hero_x is None else (hero_x - x) * s
            self.cur = cur = Inst(fam=fam, t0=T - max(float(tin or 0.0), 0.0), x0=x, y0=y, s=s, hero_du=du)
        if cur is not None:
            if not cur.states or cur.states[-1] != st:
                cur.states.append(st)
            br = sp.branch.get(cur.fam, {}).get(st)
            if cur.branch is None and br is not None:
                cur.branch, cur.branch_t = br, T
        self.prev = st
        return cur


def bin_of(t: float) -> int:
    return int(math.floor(t / FT + 0.5))


# ------------------------------------------------------------------------------------------------ live tracking

def _first_state(e: dict) -> tuple[str | None, float]:
    for f in e.get("fsms") or ():
        return f.get("state"), float(f.get("t") or 0.0)
    return None, 0.0


def _parked(e: dict) -> bool:
    if e.get("hidden") or e.get("is_dead"):
        return True
    p = e.get("pos") or (0.0, 0.0, 0.0)
    if len(p) > 2 and abs(float(p[2])) > 5.0:      # the waiting later-wave members sit at z -15
        return True
    st, _ = _first_state(e)
    return st is None or any(w in str(st) for w in PARKED)


def body_polys(e: dict, name: str) -> list[np.ndarray]:
    out = []
    for c in e.get("cols") or e.get("colliders") or ():
        v = c.get("verts_world")
        if c.get("name") == name and c.get("enabled") and v and len(v) >= 6:
            out.append(np.asarray(v, np.float64).reshape(-1, 2))
    return out


@dataclass
class Estimate:
    iid: int
    k: int
    raw: Mask
    fam: str | None            # None: idle (the body now)
    branch: str | None
    b: int | None              # the bin of the frame shown (b + k is placed)
    pos: tuple


class RangeTracker:
    """Feeds on game-frame STATEs (as tools.zone_overlay ZoneEngine.feed gets them) and gives the attack-range
    estimate of every tracked enemy at look-ahead k."""

    def __init__(self, tables: dict | None = None):
        if tables is None:
            tables = {}
            for tk, sp in SPECS.items():
                p = table_path(sp)
                if p.exists():
                    tables[tk] = load_table(p, sp)
        self.tables = tables
        self.reset()

    def reset(self) -> None:
        self.T = 0.0
        self.segs: dict = {}
        self.now: dict = {}         # iid -> (type key, entity dict, inst or None)
        self.hero: tuple | None = None

    def feed(self, s: dict) -> None:
        dt = s.get("dt")
        self.T += FT if dt is None else float(dt)
        h = (s.get("hero") or {}).get("pos")
        self.hero = (float(h[0]), float(h[1])) if h else None
        now = {}
        for e in s.get("ents") or ():
            tk = e.get("type_key")
            tab = self.tables.get(tk)
            if tab is None or _parked(e):
                continue
            iid = int(e.get("iid") or -1)
            st, tin = _first_state(e)
            p = e.get("pos") or (0.0, 0.0)
            sgn = tab.facing(e.get("flipX"))
            seg = self.segs.get(iid)
            if seg is None:
                seg = self.segs[iid] = Segmenter(tab.spec)
            inst = seg.step(st, self.T, float(p[0]), float(p[1]), sgn, None if self.hero is None else self.hero[0],
                            tin)
            now[iid] = (tk, e, inst)
        self.now = now
        for iid in [i for i in self.segs if i not in now]:
            del self.segs[iid]

    def estimate(self, iid: int, k: int) -> Estimate | None:
        if iid not in self.now:
            return None
        tk, e, inst = self.now[iid]
        tab = self.tables[tk]
        p = e.get("pos") or (0.0, 0.0)
        if inst is None:
            return Estimate(iid, k, poly_mask(body_polys(e, tab.spec.body), tab.cell), None, None, None,
                            (float(p[0]), float(p[1])))
        b = bin_of(self.T - inst.t0)
        now = (float(p[0]), float(p[1]))
        m = tab.place(inst.fam, inst.branch, b + k, (inst.x0, inst.y0), inst.s, inst.hero_du, now=now, b_now=b)
        return Estimate(iid, k, m, inst.fam, inst.branch, b, now)

    def estimates(self, k: int) -> list[Estimate]:
        return [x for x in (self.estimate(i, k) for i in sorted(self.now)) if x is not None]
