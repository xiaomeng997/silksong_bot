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

from ssbot.combat.enemy_tracker import AIM_AFTER, AIM_BINS
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
MIN_BIN = 8              # instances per fold for a bin of its own
MIN_COVER = 0.9         # a state is an aim state when its usable bins hold this share of the instances
MAX_R_BIN = 3.0          # a bin's held-out residual (u) for it to be used (its template is dilated by it)
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


def family_states(every: bool = True) -> dict:
    """(type key, family) -> (start states, states) from the committed tables: every attack family of every Forum type
    (every = True: a re-anchor at a later state's entry is never wider than the family's union from the start when it
    is certified; the hero-following CANDIDATES are the ones the overlay's yellow waits for), or CANDIDATES only."""
    from ssbot.core.forum import FORUM_TYPES
    out = {}
    for tk, sp in FORUM_TYPES.items():
        p = FORUM_DIR / f"{sp.enemy}.json"
        if not p.exists() or not (every or tk in CANDIDATES):
            continue
        d = json.loads(p.read_text("utf-8"))
        fams = [f for f in d["attacks"] if f not in (sp.idle_family, sp.entry_family)] if every else CANDIDATES[tk]
        for fam in fams:
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
    e_st, e_fi = np.asarray(cache["e_st"]), np.asarray(cache["e_fi"])
    hx, hy = np.asarray(cache["hx"], np.float64), np.asarray(cache["hy"], np.float64)
    st_l, fi_l = e_st.tolist(), e_fi.tolist()
    # every row's damage colliders (dealt > 0) as a slice of `order`, found once
    rows_all = np.arange(len(e_st))
    lo_l = np.searchsorted(ce_sorted, rows_all, "left").tolist()
    hi_l = np.searchsorted(ce_sorted, rows_all, "right").tolist()
    hurt_sorted = dealt[order] > 0
    out: dict = {}
    for (tk, fam), (starts, sts) in fams.items():
        if tk not in types:
            continue
        ti = types.index(tk)
        codes = {states.index(s): s for s in sts if s in states}
        if not codes:
            continue
        sel = np.flatnonzero((cache["e_tk"] == ti) & np.isin(e_st, list(codes)))
        if not len(sel):
            continue
        iids = cache["e_iid"][sel]
        for iid in np.unique(iids):
            rows = sel[iids == iid]
            rows = rows[np.argsort(e_fi[rows], kind="stable")].tolist()
            cur: list = []
            runs = []
            for r in rows:
                s = codes[st_l[r]]
                if cur:
                    prev = codes[st_l[cur[-1]]]
                    gap = fi_l[r] - fi_l[cur[-1]]
                    if gap > GAP_F or (s in starts and prev not in starts and s != prev):
                        runs.append(cur)
                        cur = []
                cur.append(r)
            if cur:
                runs.append(cur)
            for rr in runs:
                st = [codes[st_l[r]] for r in rr]
                if st[0] not in starts:
                    continue
                boxes = []
                for r in rr:
                    a, b = lo_l[r], hi_l[r]
                    boxes.append(cbox[order[a:b][hurt_sorted[a:b]]] if b > a else cbox[:0])
                out.setdefault((tk, fam), []).append({"key": (tk, fam),
                    "st": st, "t": T[cache["e_fi"][rr]],
                    "pos": np.stack([cache["e_x"][rr], cache["e_y"][rr]], axis=1).astype(np.float64),
                    "flip": np.asarray(cache["e_flip"][rr]), "hidden": np.asarray(cache["e_hidden"][rr]),
                    "hero": np.stack([hx[e_fi[rr]], hy[e_fi[rr]]], axis=1).astype(np.float64),
                    "vel": np.stack([cache["e_vx"][rr], cache["e_vy"][rr]], axis=1).astype(np.float64),
                    "boxes": boxes})
    return out


def aim_frame(inst: dict, i: int) -> tuple[int, int]:
    """(mirror, direction bin) of the instance at its row i: enemy_tracker.aim_frame, the trackers' own (forward = where
    it flies; the hero's direction at the aim does not fix the Reed's stab, forum.md §29.2, its own flight does: Stab
    1-5 slide along one line, the needle ahead of it)."""
    from ssbot.combat.enemy_tracker import aim_frame as tracker_frame
    vx, vy = inst["vel"][i]
    return tracker_frame(float(vx), float(vy), FACES_LEFT[1 if inst["flip"][i] else 0])


def aim_rel(inst: dict, S: str) -> int | None:
    """The direction bin at the instance's first row in S (None: it never entered S)."""
    try:
        i = inst["st"].index(S)
    except ValueError:
        return None
    return aim_frame(inst, i)[1]


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
    m = aim_frame(inst, i)[0]
    t0 = inst["t"][i]
    out = []
    stop = AIM_AFTER.get(inst.get("key"), ())
    for j in range(i, len(inst["st"])):
        if inst["st"][j] in stop:
            break
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


def _fight_instances(path: str, fams: dict) -> dict:
    from ssbot.knowledge.forum_cache import load_cache
    return instances(load_cache(Path(path)), fams)


def _low_priority() -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:  # noqa: BLE001  (not Windows / no psutil: normal priority)
        pass


def _load(d: Path) -> list[dict]:
    from ssbot.knowledge.forum_cache import load_cache
    return [load_cache(Path(p)) for p in sorted(glob.glob(str(d / "*.npz")))]


def cmd_build(a) -> int:
    t0 = time.perf_counter()
    fams = family_states()
    dev, fresh = {}, {}
    from concurrent.futures import ProcessPoolExecutor
    for which, d, acc in (("dev", Path(a.dev), dev), ("fresh", Path(a.fresh), fresh)):
        paths = sorted(glob.glob(str(d / "*.npz")))
        # about 30 s a fight in one process (214 dev + the fresh fights): one fight per worker task
        with ProcessPoolExecutor(max_workers=a.workers, initializer=_low_priority) as ex:
            for i, got in enumerate(ex.map(_fight_instances, paths, [fams] * len(paths), chunksize=1)):
                for key, insts in got.items():
                    for x in insts:
                        x["fold"] = i % 2
                    acc.setdefault(key, []).extend(insts)
        print(f"{which}: {len(paths)} fights ({time.perf_counter() - t0:.0f} s)", flush=True)
    from ssbot.combat.enemy_tables import EnemyTables  # noqa: F401
    fam_tpl, _ = hb.load_templates(FORUM_DIR / "Reed_hitboxes.npz", prefix="support/RE_STAB/anchor")
    report: dict = {"families": {}, "min_inst": MIN_INST, "min_bin": MIN_BIN, "max_r_bin": MAX_R_BIN,
                    "n_bins": AIM_BINS, "cell": CELL}
    chosen = {}
    for (tk, fam), (starts, sts) in fams.items():
        insts = dev.get((tk, fam), [])
        rows = []
        for S in sts:
            if S in starts or S in AIM_AFTER.get((tk, fam), ()):
                continue
            per = []
            for x in insts:
                ab, rel = aim_boxes(x, S), aim_rel(x, S)
                if ab is not None and rel is not None:
                    per.append((x["fold"], rel, ab))
            n_f = [sum(1 for f, _, _ in per if f == k) for k in (0, 1)]
            if min(n_f) < MIN_INST:
                continue
            nt_all = int(max((ab[:, 0].max() for _, _, ab in per if len(ab)), default=0)) + 2
            if nt_all <= 2:
                rows.append({"state": S, "n": n_f, "damage": False})
                continue
            vol_all = int(build_occ([ab for _, _, ab in per], nt_all).padded().sum())
            fr = []
            for x in fresh.get((tk, fam), []):
                ab, rel = aim_boxes(x, S), aim_rel(x, S)
                if ab is not None and rel is not None:
                    fr.append((rel, ab))
            bins = {}
            for b in sorted({b for _, b, _ in per}):
                pb = [(f, ab) for f, bb, ab in per if bb == b]
                nb = [sum(1 for f, _ in pb if f == k) for k in (0, 1)]
                if min(nb) < MIN_BIN:
                    continue
                nt = int(max((ab[:, 0].max() for _, ab in pb if len(ab)), default=0)) + 2
                rs = [need_r(build_occ([ab for f, ab in pb if f != k], nt), [ab for f, ab in pb if f == k])
                      for k in (0, 1)]
                full = build_occ([ab for _, ab in pb], nt)
                fb = [ab for bb, ab in fr if bb == b]
                rf = need_r(full, fb) if fb else (0.0, 0, 0)
                bins[b] = {"n": nb, "n_fresh": len(fb), "r_2fold": round(max(x[0] for x in rs), 3),
                           "r_fresh": round(rf[0], 3), "late": sum(x[2] for x in rs) + rf[2],
                           "volume_cells": int(full.padded().sum()), "nt": nt, "extent": _extent(full)}
            use = {b: v for b, v in bins.items() if not v["late"] and v["r_2fold"] <= MAX_R_BIN
                   and v["r_fresh"] <= MAX_R_BIN}
            # the expected dilated volume per instance: its bin's template, or (no usable bin) the unbinned one
            n_tot = len(per)
            ev = 0.0
            for _, b, _ in per:
                v = use.get(b)
                ev += v["volume_cells"] * (1.0 + max(v["r_2fold"], v["r_fresh"])) if v else vol_all * 4.0
            ev /= max(n_tot, 1)
            cover = sum(1 for _, b, _ in per if b in use) / max(n_tot, 1)
            rows.append({"state": S, "n": n_f, "n_fresh": len(fr), "volume_all": vol_all, "expected": round(ev),
                         "cover": round(cover, 3), "bins": bins, "used": sorted(use)})
            print(f"{tk[-12:]:12s} {fam:13s} {S:22s} n {n_f} fresh {len(fr)} vol {vol_all} expected {ev:.0f} "
                  f"cover {cover:.0%} bins " + " ".join(
                      f"{b}:{v['n'][0] + v['n'][1]}/r{max(v['r_2fold'], v['r_fresh']):.1f}/v{v['volume_cells']}"
                      f"{'' if b in use else 'x'}" for b, v in bins.items()), flush=True)
        # every state whose usable bins hold most instances: the tracker re-aims at each (enemy_tracker._aim_now)
        ok = [x for x in rows if x.get("used") and x["cover"] >= MIN_COVER]
        report["families"][f"{tk}|{fam}"] = {"candidates": rows, "chosen": [x["state"] for x in ok]}
        for x in ok:
            chosen[(tk, fam, x["state"])] = {b: max(x["bins"][b]["r_2fold"], x["bins"][b]["r_fresh"])
                                             for b in x["used"]}
    tpls, extra = {}, {}
    for (tk, fam, S), rb in chosen.items():
        keys = []
        for b, r in rb.items():
            # dev fights only: the fresh ones stay held out (multi_recall fresh)
            abs_ = [aim_boxes(x, S) for x in dev.get((tk, fam), [])
                    if aim_rel(x, S) is not None and aim_rel(x, S) == b]
            abs_ = [ab for ab in abs_ if ab is not None]
            nt = int(max(ab[:, 0].max() for ab in abs_ if len(ab))) + 2
            key = f"support/{fam}/aim@{S}#{b}/anchor"
            tpls[key] = _template(key, build_occ(abs_, nt), len(abs_))
            extra[f"aim/{tk}|{fam}@{S}#{b}"] = np.array([r])
            keys.append(key)
        report["families"][f"{tk}|{fam}"].setdefault("keys", []).extend(keys)
        report["families"][f"{tk}|{fam}"].setdefault("r", {})[S] = {str(b): r for b, r in rb.items()}
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
    b.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    return {"build": cmd_build}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
