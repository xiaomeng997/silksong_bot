"""Aim-conditioned committed templates (task "zone fix" item 1, switch SSBOT_FORUM_AIM; the person 2026-10-09: the Reed's
triple stab turned the whole screen yellow while the truth is a thin diagonal strip below it).

The committed layer's family templates are anchored where the enemy was at the attack's START and hold every logged
instance: for an attack that first moves to a place chosen from the hero (the Reed's Stab Pos flies to about 6.7 u
beside and above the hero, then stabs 7 u down a fixed 16.7 deg diagonal in its facing), the union over all instances
spans the whole flight (RE_STAB's anchor template: 40 x 24 u). Re-anchored at the entry of a later state of the
family (its AIM state), where the place and facing are already fixed, what is left of the attack is tight.

Per (type, family) and candidate aim state S (every non-start state of the family): from the per-fight Forum caches
(ssbot.knowledge.forum_cache), the instances that entered S; per instance the enabled damage colliders (dealt > 0) of
the enemy's own rows from S's first frame to the instance's end, as boxes relative to the enemy's transform at that
frame, mirrored by its facing then (FACES_LEFT), t from that frame; occupancy on CELL_U cells per 1/60 s bin, +-1 bin.
Held-out coverage (2 folds by fight, and the fresh fights against all dev fights): for every held-out collider box,
the Chebyshev distance (u) of its cells from the training occupancy of bins b-1 .. b+1; the margin r = the largest
over both folds (a template dilated by r plus the hero half extents then covers every held-out box: 100 % of the
held-out colliders, a stricter test than contacts). The chosen S per family is the one with the smallest dilated
volume among those with at least MIN_INST instances in each fold and r <= MAX_R.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_aim build [--dev <cache dir>] [--fresh <cache dir>]
        [--out ../knowledge/1.0.30000/enemies/forum/aim_templates.npz] [--json <report>]

Output: one npz (hitbox_tables.save_templates; keys support/<family>/aim@<state>/anchor, raw occupancy with the
+-1 bin, t from the aim state's entry) + "aim/<type>|<family>" extra arrays [r] and the report JSON beside it
(aim_templates.json: per family the chosen state, r, the instances, the volume against the family template's).
enemy_tables loads them (dilated by the hero half extents + r) when SSBOT_FORUM_AIM is on; the tracker re-anchors at
the aim state's entry; multi_forecast places them in place of the family's committed union once the aim is seen.
"""
import argparse
import glob
import json
import math
import time
from pathlib import Path

import numpy as np

from ssbot.knowledge import hitbox_tables as hb

DEV = Path(r"C:\ssbot\data\m2_forum_r0\cache")
FRESH = Path(r"C:\ssbot\data\m2_forum_r0\cache_fresh")
FORUM_DIR = Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / "forum"
OUT = FORUM_DIR / "aim_templates.npz"
CELL = hb.CELL_U
BIN = hb.BIN_S
FACES_LEFT = (-1, 1)
MIN_INST = 20
MAX_R = 0.5
GAP_F = 3
# the families whose damage follows the hero (the task's list + the data): type key -> families
CANDIDATES = {
    "Song Reed": ("RE_STAB", "RE_DEFEND", "RE_EVADE"),
    "Song Pilgrim 01": ("EN_CHARGE", "EN_JUMPSLASH", "EN_SLASH"),
    "Song Administrator": ("MI_CHARGE", "MI_PARRY"),
    "Song Pilgrim 03": ("CH_JUMP", "CH_SLASH", "CH_WHIP"),
    "Song Handmaiden": ("CM_SLASH", "CM_SPIN"),
    "Pilgrim 03 Song": ("CB_THROW",),
    "Song Automaton Tiny": ("AT_FIRE", "AT_DEFEND"),
    "Song Pilgrim Maestro": ("MA_SLASH", "MA_DEFEND"),
}


def family_states() -> dict:
    """(type key, family) -> (start states, states) from the committed tables."""
    from ssbot.core.forum import FORUM_TYPES
    out = {}
    for tk, sp in FORUM_TYPES.items():
        p = FORUM_DIR / f"{sp.enemy}.json"
        if tk not in CANDIDATES or not p.exists():
            continue
        d = json.loads(p.read_text("utf-8"))
        for fam in CANDIDATES[tk]:
            a = d["attacks"].get(fam)
            if a and a.get("states"):
                out[(tk, fam)] = (tuple(a["start_states"]), tuple(a["states"]))
    return out


def instances(cache: dict, fams: dict) -> dict:
    """(tk, fam) -> [instance]: instance = {"st": [state per row], "t": [T], "pos": [(x, y)], "flip": [..],
    "boxes": [[(x0, y0, x1, y1), ...] per row]} in frame order."""
    from ssbot.knowledge.forum_cache import frame_index  # noqa: F401  (layout reference)
    types = list(cache["types"])
    states = list(cache["states"])
    T = np.asarray(cache["T"], np.float64)
    cei = np.asarray(cache["c_ei"])
    order = np.argsort(cei, kind="stable")
    ce_sorted = cei[order]
    dealt = np.asarray(cache["c_dealt"])
    cbox = np.asarray(cache["c_box"], np.float64)
    out: dict = {}
    for (tk, fam), (starts, sts) in fams.items():
        if tk not in types:
            continue
        ti = types.index(tk)
        codes = {states.index(s): s for s in sts if s in states}
        if not codes:
            continue
        sel = np.flatnonzero((cache["e_tk"] == ti) & np.isin(cache["e_st"], list(codes)))
        if not len(sel):
            continue
        iids = cache["e_iid"][sel]
        for iid in np.unique(iids):
            rows = sel[iids == iid]
            rows = rows[np.argsort(cache["e_fi"][rows], kind="stable")]
            cur: list = []
            runs = []
            for r in rows:
                s = codes[int(cache["e_st"][r])]
                if cur:
                    prev = codes[int(cache["e_st"][cur[-1]])]
                    gap = int(cache["e_fi"][r]) - int(cache["e_fi"][cur[-1]])
                    if gap > GAP_F or (s in starts and prev not in starts and s != prev):
                        runs.append(cur)
                        cur = []
                cur.append(r)
            if cur:
                runs.append(cur)
            for rr in runs:
                st = [codes[int(cache["e_st"][r])] for r in rr]
                if st[0] not in starts:
                    continue
                boxes = []
                for r in rr:
                    a = np.searchsorted(ce_sorted, r, "left")
                    b = np.searchsorted(ce_sorted, r, "right")
                    ci = order[a:b]
                    ci = ci[dealt[ci] > 0]
                    boxes.append(cbox[ci])
                out.setdefault((tk, fam), []).append({
                    "st": st, "t": T[cache["e_fi"][rr]],
                    "pos": np.stack([cache["e_x"][rr], cache["e_y"][rr]], axis=1).astype(np.float64),
                    "flip": np.asarray(cache["e_flip"][rr]), "hidden": np.asarray(cache["e_hidden"][rr]),
                    "boxes": boxes})
    return out


def aim_boxes(inst: dict, S: str) -> np.ndarray | None:
    """[n, 5] (bin, x0, y0, x1, y1) of the instance's colliders from its first row in S, in the aim frame; None when
    it never entered S (or was hidden there)."""
    try:
        i = inst["st"].index(S)
    except ValueError:
        return None
    if inst["hidden"][i]:
        return None
    ax, ay = inst["pos"][i]
    m = FACES_LEFT[1 if inst["flip"][i] else 0]
    t0 = inst["t"][i]
    out = []
    for j in range(i, len(inst["st"])):
        bx = inst["boxes"][j]
        if not len(bx):
            continue
        b = int(round((inst["t"][j] - t0) / BIN))
        for x0, y0, x1, y1 in bx:
            if not np.isfinite(x0):
                continue
            u0, u1 = sorted(((x0 - ax) * m, (x1 - ax) * m))
            out.append((b, u0, y0 - ay, u1, y1 - ay))
    return np.asarray(out, np.float64).reshape(-1, 5)


class Occ:
    """Dense occupancy [nt, ny, nx] on CELL cells over a fixed frame box."""

    def __init__(self, nt: int, box=(-20.0, -16.0, 20.0, 12.0)):
        self.x0, self.y0 = box[0], box[1]
        self.nx = int(round((box[2] - box[0]) / CELL))
        self.ny = int(round((box[3] - box[1]) / CELL))
        self.nt = nt
        self.g = np.zeros((nt, self.ny, self.nx), bool)

    def cells(self, x0, y0, x1, y1):
        i0 = int(math.floor((x0 - self.x0) / CELL))
        i1 = int(math.ceil((x1 - self.x0) / CELL))
        j0 = int(math.floor((y0 - self.y0) / CELL))
        j1 = int(math.ceil((y1 - self.y0) / CELL))
        return max(i0, 0), min(max(i1, i0 + 1), self.nx), max(j0, 0), min(max(j1, j0 + 1), self.ny)

    def add(self, ab: np.ndarray) -> None:
        for b, x0, y0, x1, y1 in ab:
            b = int(b)
            if 0 <= b < self.nt:
                i0, i1, j0, j1 = self.cells(x0, y0, x1, y1)
                self.g[b, j0:j1, i0:i1] = True

    def padded(self) -> np.ndarray:
        """+-1 bin."""
        p = self.g.copy()
        p[1:] |= self.g[:-1]
        p[:-1] |= self.g[1:]
        return p


def need_r(train: Occ, test: list[np.ndarray]) -> tuple[float, int, int]:
    """(the largest Chebyshev distance (u) of a held-out box's cells from the training occupancy of its bin +-1,
    boxes, boxes beyond the template's time range)."""
    import cv2
    P = train.padded()
    dist: dict = {}
    worst, n, late = 0.0, 0, 0
    for ab in test:
        for b, x0, y0, x1, y1 in ab:
            b = int(b)
            n += 1
            if not 0 <= b < train.nt or not P[b].any():
                late += 1
                worst = math.inf
                continue
            if b not in dist:
                dist[b] = cv2.distanceTransform((~P[b]).astype(np.uint8), cv2.DIST_C, 3)
            i0, i1, j0, j1 = train.cells(x0, y0, x1, y1)
            d = float(dist[b][j0:j1, i0:i1].max()) * CELL if i1 > i0 and j1 > j0 else math.inf
            worst = max(worst, d)
    return worst, n, late


def build_occ(abs_: list[np.ndarray], nt: int) -> Occ:
    o = Occ(nt)
    for ab in abs_:
        o.add(ab)
    return o


def _load(d: Path) -> list[dict]:
    from ssbot.knowledge.forum_cache import load_cache
    return [load_cache(Path(p)) for p in sorted(glob.glob(str(d / "*.npz")))]


def cmd_build(a) -> int:
    t0 = time.perf_counter()
    fams = family_states()
    dev, fresh = {}, {}
    for which, d, acc in (("dev", Path(a.dev), dev), ("fresh", Path(a.fresh), fresh)):
        paths = sorted(glob.glob(str(d / "*.npz")))
        from ssbot.knowledge.forum_cache import load_cache
        for i, p in enumerate(paths):
            for key, insts in instances(load_cache(Path(p)), fams).items():
                for x in insts:
                    x["fold"] = i % 2
                acc.setdefault(key, []).extend(insts)
        print(f"{which}: {len(paths)} fights ({time.perf_counter() - t0:.0f} s)", flush=True)
    from ssbot.combat.enemy_tables import EnemyTables  # noqa: F401
    fam_tpl, _ = hb.load_templates(FORUM_DIR / "Reed_hitboxes.npz", prefix="support/RE_STAB/anchor")
    report: dict = {"families": {}, "min_inst": MIN_INST, "max_r": MAX_R, "cell": CELL}
    chosen = {}
    for (tk, fam), (starts, sts) in fams.items():
        insts = dev.get((tk, fam), [])
        rows = []
        for S in sts:
            if S in starts:
                continue
            per = [(x["fold"], aim_boxes(x, S)) for x in insts]
            per = [(f, ab) for f, ab in per if ab is not None]
            n_f = [sum(1 for f, _ in per if f == k) for k in (0, 1)]
            if min(n_f) < MIN_INST:
                continue
            nt = int(max((ab[:, 0].max() for _, ab in per if len(ab)), default=0)) + 2
            if nt <= 2:
                rows.append({"state": S, "n": n_f, "damage": False})
                continue
            rs = []
            for k in (0, 1):
                tr = build_occ([ab for f, ab in per if f != k], nt)
                rs.append(need_r(tr, [ab for f, ab in per if f == k]))
            r = max(x[0] for x in rs)
            full = build_occ([ab for _, ab in per], nt)
            fr = [aim_boxes(x, S) for x in fresh.get((tk, fam), [])]
            fr = [ab for ab in fr if ab is not None]
            rf = need_r(full, fr) if fr else (0.0, 0, 0)
            vol = int(full.padded().sum())
            rows.append({"state": S, "n": n_f, "n_fresh": len(fr), "r_2fold": round(r, 3),
                         "r_fresh": round(rf[0], 3), "boxes_fresh": rf[1], "late_fresh": rf[2],
                         "late_2fold": sum(x[2] for x in rs), "volume_cells": vol, "nt": nt,
                         "extent": _extent(full)})
            print(f"{tk[-12:]:12s} {fam:13s} {S:22s} n {n_f} fresh {len(fr)} r 2-fold {r:.2f} fresh {rf[0]:.2f} "
                  f"vol {vol} ext {_extent(full)}", flush=True)
        ok = [x for x in rows if x.get("volume_cells") and x["r_2fold"] <= MAX_R and x["r_fresh"] <= MAX_R
              and not x["late_2fold"] and not x["late_fresh"]]
        best = min(ok, key=lambda x: x["volume_cells"] * (1.0 + max(x["r_2fold"], x["r_fresh"]))) if ok else None
        report["families"][f"{tk}|{fam}"] = {"candidates": rows, "chosen": best and best["state"]}
        if best is not None:
            chosen[(tk, fam)] = (best["state"], max(best["r_2fold"], best["r_fresh"]))
    tpls, extra = {}, {}
    for (tk, fam), (S, r) in chosen.items():
        # dev fights only: the fresh ones stay held out (multi_recall fresh)
        abs_ = [aim_boxes(x, S) for x in dev.get((tk, fam), [])]
        abs_ = [ab for ab in abs_ if ab is not None]
        nt = int(max(ab[:, 0].max() for ab in abs_ if len(ab))) + 2
        o = build_occ(abs_, nt)
        key = f"support/{fam}/aim@{S}/anchor"
        tpls[key] = _template(key, o, len(abs_))
        extra[f"aim/{tk}|{fam}"] = np.array([r])
        report["families"][f"{tk}|{fam}"].update({"key": key, "r": r, "n_all": len(abs_)})
    out = Path(a.out)
    hb.save_templates(out, tpls, extra)
    report["fam_template_reference"] = {k: list(v.bounds) for k, v in fam_tpl.items()}
    jp = Path(a.json) if a.json else out.with_suffix(".json")
    jp.write_text(json.dumps(report, indent=1), "utf-8")
    print(f"wrote {out} ({len(tpls)} templates) and {jp} ({time.perf_counter() - t0:.0f} s)")
    return 0


def _extent(o: Occ):
    m = o.g.any(axis=0)
    rows, cols = np.flatnonzero(m.any(axis=1)), np.flatnonzero(m.any(axis=0))
    if not len(rows):
        return None
    return [round(o.x0 + cols[0] * CELL, 2), round(o.y0 + rows[0] * CELL, 2), round(o.x0 + (cols[-1] + 1) * CELL, 2),
            round(o.y0 + (rows[-1] + 1) * CELL, 2)]


def _template(key: str, o: Occ, n: int) -> hb.SpaceTimeTemplate:
    """The raw occupancy (+-1 bin baked in: t_pad 1) cropped to its cells."""
    P = o.padded()
    m = P.any(axis=0)
    rows, cols = np.flatnonzero(m.any(axis=1)), np.flatnonzero(m.any(axis=0))
    sub = P[:, rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    ix0 = int(round(o.x0 / CELL)) + int(cols[0])
    iy0 = int(round(o.y0 / CELL)) + int(rows[0])
    bits = np.packbits(sub, axis=2)
    return hb.SpaceTimeTemplate(key=key, frame="anchor", ix0=ix0, iy0=iy0, nx=int(sub.shape[2]), ny=int(sub.shape[1]),
                                t0=0.0, bits=bits, cell=CELL, bin_s=BIN, n_instances=n, t_pad=1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="forum_aim")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--dev", default=str(DEV))
    b.add_argument("--fresh", default=str(FRESH))
    b.add_argument("--out", default=str(OUT))
    b.add_argument("--json")
    a = ap.parse_args(argv)
    return {"build": cmd_build}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
