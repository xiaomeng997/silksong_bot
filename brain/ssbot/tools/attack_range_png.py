"""World-space pictures of the attack-range estimate on the person's frames (tools.attack_range_build [--type] png;
the type module's CASES, a few frames per family, the worst rows of the person / fresh evals): per frame
the estimate at k = 0 (filled) and k = 12 (outlined), its hero-centre region at k = 0 (thin yellow: where the hero
transform must not be), the enemy's REAL damage colliders now (thick red) and over the next 12 game frames (thin red,
the frame at +12 magenta), the hero's hurtbox and transform, a 1 u grid and the numbers of compare() at k 0 / 12."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ssbot.combat.attack_range import (FT, HERO_DY, HERO_HALF, bin_of, contours, hazards_at, hero_space, load_table,
                                       poly_mask, union)
from ssbot.tools.attack_range_build import compare, frame_polys, load_tracks, segment

PX_U = 40
FAM_COLOR = (60, 160, 255)        # BGR orange: the estimate
K12_COLOR = (255, 220, 80)        # BGR light blue: the estimate at k = 12


def _find(tracks, sess: str, f: int, iid: int | None = None):
    """(track, frame index) of the enemy in play nearest to frame f of the session / fight (the one in a family
    instance first; that enemy when iid is given: several of the type can be in play)."""
    best = None
    for tr in tracks:
        if not str(tr["fight"]).startswith(sess) or (iid is not None and int(tr["iid"]) != int(iid)):
            continue
        j = int(np.searchsorted(tr["f"], f))
        for jj in (j - 1, j):
            if 0 <= jj < len(tr["f"]) and abs(int(tr["f"][jj]) - f) <= 2 and not tr["hidden"][jj] \
                    and tr["st"][jj] and abs(tr["x"][jj]) < 200:
                score = (0 if tr["cols"][jj] else 1, abs(int(tr["f"][jj]) - f))
                if best is None or score < best[0]:
                    best = (score, tr, jj)
    return (best[1], best[2]) if best else (None, None)


def _target(T, j: int, k: int):
    t = T[j] + k * FT - 1e-6
    jt = int(np.searchsorted(T, t, "left"))
    return jt if jt < len(T) else None


def draw_frame(tr: dict, j: int, tab, shapes: dict, why: str = "") -> np.ndarray | None:
    import cv2
    f1 = int(tab.meta.get("face_flip1", 1))
    insts, idx = segment(tr, tab.spec, f1)
    T = tr["T"]
    est, info, s = {}, "", 1
    for k in (0, 12):
        est[k], _, info0, s = _estimate(tr, insts, idx, tab, shapes, j, k)
        info = info or info0
    jt = {k: _target(T, j, k) for k in range(13)}
    real = {k: frame_polys(tr, jt[k], shapes) for k in jt if jt[k] is not None}
    cmp_ = {k: compare(est[k], poly_mask(real.get(k, [])), s) for k in (0, 12) if k in real}
    hx, hy = float(tr["hx"][j]), float(tr["hy"][j])
    hbox = (hx - HERO_HALF[0], hy + HERO_DY - HERO_HALF[1], hx + HERO_HALF[0], hy + HERO_DY + HERO_HALF[1])
    # the view: everything drawn, plus 2 u
    pts = [np.array([[hbox[0], hbox[1]], [hbox[2], hbox[3]]])]
    for m in est.values():
        bb = m.bbox()
        if bb:
            pts.append(np.array([[bb[0], bb[1]], [bb[2], bb[3]]]))
    for ps in real.values():
        pts += ps
    allp = np.vstack(pts)
    x0, y0 = allp.min(axis=0) - 2.0
    x1, y1 = allp.max(axis=0) + 2.0
    y0 = min(y0, 2.5)
    lines = [f"{tr['fight']} raw frame {int(tr['f'][j])}  {tab.spec.short} iid {tr['iid']}  state {tr['st'][j]}  {why}",
             info]
    for k, c in cmp_.items():
        ratio = c["aE"] / c["aR"] if c["aR"] > 0 else float("nan")
        miss = ", ".join(f"{sd} {v[0]:.2f} u" for sd, v in c["miss"].items()) or "none"
        exc = ", ".join(f"{sd} {v[0]:.2f}" for sd, v in c["exc"].items()) or "none"
        lines.append(f"k {k:2d}: estimate {c['aE']:.1f} u^2 vs real {c['aR']:.1f} u^2 (hero-centre) RATIO "
                     f"{ratio:.2f}  covered {c['aI'] / c['aR'] if c['aR'] else float('nan'):.0%}  miss {miss}  "
                     f"excess reach {exc}")
    lines.append("filled orange = estimate k 0 (raw colliders); light blue = estimate k 12; thin yellow = hero-centre "
                 "region of k 0; red = real now, thin red = real +1..+11 f, magenta = real +12 f; white = hero hurtbox")
    top = 20 * (len(lines) + 1)
    if (x1 - x0) * PX_U + 40 < 1500:                 # room for the text lines
        pad = (1500 - 40 - (x1 - x0) * PX_U) / PX_U / 2
        x0, x1 = x0 - pad, x1 + pad
    W = int((x1 - x0) * PX_U) + 40
    H = int((y1 - y0) * PX_U) + 40 + top
    img = np.full((H, W, 3), 22, np.uint8)

    def px(x, y):
        return int(round(20 + (x - x0) * PX_U)), int(round(top + 20 + (y1 - y) * PX_U))

    def poly(p, col, th, fill=None):
        q = np.asarray([px(a, b) for a, b in np.asarray(p).reshape(-1, 2)], np.int32)
        if fill is not None:
            ov = img.copy()
            cv2.fillPoly(ov, [q], fill)
            cv2.addWeighted(ov, 0.45, img, 0.55, 0, img)
        if th:
            cv2.polylines(img, [q], True, col, th, cv2.LINE_AA)
    for gx in range(int(np.floor(x0)), int(np.ceil(x1)) + 1):
        cv2.line(img, px(gx, y0), px(gx, y1), (40, 40, 40) if gx % 2 else (55, 55, 55), 1)
    for gy in range(int(np.floor(y0)), int(np.ceil(y1)) + 1):
        cv2.line(img, px(x0, gy), px(x1, gy), (40, 40, 40) if gy % 2 else (55, 55, 55), 1)
    cv2.line(img, px(x0, 3.0), px(x1, 3.0), (120, 120, 120), 2)
    for c in contours(est[0]):
        poly(c, FAM_COLOR, 2, fill=FAM_COLOR)
    for c in contours(hero_space(est[0])):
        poly(c, (80, 230, 255), 1)
    for c in contours(est[12]):
        poly(c, K12_COLOR, 2)
    for k in range(1, 12):
        for p in real.get(k, []):
            poly(p, (70, 70, 190), 1)
    for p in real.get(12, []):
        poly(p, (220, 80, 220), 2)
    for p in real.get(0, []):
        poly(p, (60, 60, 255), 2)
    cv2.rectangle(img, px(hbox[0], hbox[3]), px(hbox[2], hbox[1]), (255, 255, 255), 2)
    cv2.circle(img, px(hx, hy), 4, (255, 255, 255), -1, cv2.LINE_AA)
    ex, ey = float(tr["x"][j]), float(tr["y"][j])
    cv2.circle(img, px(ex, ey), 4, FAM_COLOR, -1, cv2.LINE_AA)
    # scale: 1 u and the hero's width
    sx, sy = px(x0 + 0.5, y0 + 0.6)
    cv2.line(img, (sx, sy), (sx + PX_U, sy), (235, 235, 235), 3)
    cv2.putText(img, "1 u", (sx, sy - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (235, 235, 235), 1, cv2.LINE_AA)
    cv2.line(img, (sx + 2 * PX_U, sy), (sx + 2 * PX_U + int(0.4554 * PX_U), sy), (255, 255, 255), 3)
    cv2.putText(img, "hero width 0.46 u", (sx + 2 * PX_U, sy - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (235, 235, 235), 1,
                cv2.LINE_AA)
    for i, t in enumerate(lines):
        cv2.putText(img, t, (10, 18 + 20 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (235, 235, 235), 1, cv2.LINE_AA)
    return img


def pick_frames(tracks, tab, sessions=("20261009_085824", "20261009_161454"), per_fam: int = 2) -> list:
    """(session, raw f, why): a few frames per family of the person's own fights (antic, middle, end, and the idle
    frames right after it), and (Choristor) the frames of the whip that follows frame 5690."""
    f1 = int(tab.meta.get("face_flip1", 1))
    out, seen = [], {}
    for tr in tracks:
        sess = str(tr["fight"]).split("/")[0]
        if sess not in sessions:
            continue
        insts, idx = segment(tr, tab.spec, f1)
        for n, r in enumerate(insts):
            inst = r["inst"]
            fr = r["frames"]
            if tab.spec.short == "Choristor" and sess == "20261009_085824" and \
                    any(abs(int(tr["f"][q]) - 5690) <= 1 for q in fr):
                for q in fr[::max(1, len(fr) // 8)]:
                    out.append((sess, int(tr["f"][q]), f"the whip after 5690 ({tr['st'][q]})", tr["iid"]))
                continue
            if seen.get(inst.fam, 0) >= per_fam or r["interrupted"]:
                continue
            seen[inst.fam] = seen.get(inst.fam, 0) + 1
            for q in (fr[0], fr[len(fr) // 3], fr[2 * len(fr) // 3], fr[-1]):
                out.append((sess, int(tr["f"][q]), f"{inst.fam} #{seen[inst.fam]} ({tr['st'][q]})", tr["iid"]))
            if (inst.fam == "CH_SLASH" or tab.spec.hazards) and r["j1"] + 1 < len(tr["f"]):
                for d in (1, 6, 12) if inst.fam == "CH_SLASH" else (12, 30):
                    q = min(r["j1"] + d, len(tr["f"]) - 1)
                    if idx[q] < 0:
                        out.append((sess, int(tr["f"][q]), f"after {inst.fam} +{d} f ({tr['st'][q]})", tr["iid"]))
    return out


def cmd_png(a) -> int:
    import cv2
    from ssbot.combat.are_types import module_of
    from ssbot.tools.attack_range_build import out_dir, spec_of
    spec = spec_of(getattr(a, "type", None))
    mod = module_of(spec.type_key)
    tab = load_table(None, spec)
    shapes = tab.meta.get("shapes") or {}
    sessions = tuple(getattr(mod, "SESSIONS", ()))
    tracks = load_tracks("person", spec=spec, sessions=sessions)
    out = Path(a.out) if getattr(a, "out", None) else out_dir(spec) / "png"
    out.mkdir(parents=True, exist_ok=True)
    frames = [tuple(c) + (None,) for c in getattr(mod, "CASES", ())] + pick_frames(tracks, tab, sessions)
    worst = worst_frames(out_dir(spec) / "rows_person.pkl", getattr(a, "worst", 8))
    frames += [w for w in worst if w[0].split("/")[0] in sessions]
    fresh = worst_frames(out_dir(spec) / "rows_fresh.pkl", getattr(a, "worst", 8) // 2)
    ftracks = load_tracks("fresh", spec=spec) if fresh else []
    index = []
    for pool, items in ((tracks, frames), (ftracks, fresh)):
        for sess, f, why, iid in items:
            tr, j = _find(pool, sess, f, iid)
            if tr is None:
                print(f"{sess} f {f}: no {spec.short} in play")
                continue
            img = draw_frame(tr, j, tab, shapes, why)
            if img is None:
                continue
            tag = "worst_" if why.startswith("worst") else ""
            fn = out / (f"{tag}{sess.replace('/', '_')}_f{f}_{str(tr['st'][j]).replace(' ', '_').replace('?', '')}"
                        ".png")
            cv2.imwrite(str(fn), img)
            index.append({"png": fn.name, "fight": sess, "f": f, "why": why, "state": tr["st"][j]})
    (out / "index.json").write_text(json.dumps(index, indent=1), "utf-8")
    print(f"{len(index)} PNGs in {out}")
    return 0


def _estimate(tr, insts, idx, tab, shapes, j: int, k: int):
    """(estimate raw, its hazard part or None, info line, facing) of frame j at look-ahead k, as eval_track makes it
    (the target time is the frame that reaches t + k / 60)."""
    from ssbot.tools.attack_range_build import _active_view
    spec = tab.spec
    f1 = int(tab.meta.get("face_flip1", 1))
    T = tr["T"]
    jt = _target(T, j, k)
    tt = float(T[jt]) if jt is not None else float(T[j]) + k * FT
    inst = insts[idx[j]]["inst"] if idx[j] >= 0 else None
    if inst is not None:
        b = bin_of(float(T[j]) - inst.t0)
        bt = bin_of(tt - inst.t0)
        br = inst.branch if (inst.branch_t is not None and inst.branch_t <= T[j] + 1e-9) else None
        dec = inst.dec if (inst.dec is not None and inst.dec["t"] <= T[j] + 1e-9) else None
        E = tab.place(inst.fam, br, bt, (inst.x0, inst.y0), inst.s, inst.hero_du,
                      now=(float(tr["x"][j]), float(tr["y"][j])), b_now=b, dec=dec, st_now=tr["st"][j])
        info = (f"{inst.fam} branch {br or 'pending (union)'}{' -> ' + str(inst.branch) if br is None else ''}  "
                f"bin {b} ({b * FT:.2f} s since the antic start)  anchor ({inst.x0:.2f}, {inst.y0:.2f}) "
                f"facing {'+x' if inst.s > 0 else '-x'}" + (f"  hero du {inst.hero_du:.2f}" if inst.fam in spec.aim
                                                          else ""))
        if inst.fam in spec.decide:
            info += (f"  decided at bin {dec['b']}: s {dec['s']:+d}, landing u {dec['L']:.2f}" if dec else
                     "  aim PENDING (not drawn past its decision)")
        s = inst.s
    else:
        E = poly_mask(frame_polys(tr, j, shapes, spec.body_names))
        info = "idle: the exact body now, for every k (no growth)"
        s = f1 if tr["flip"][j] else -f1
    H = None
    if spec.hazards:
        sp = sorted(((hz, *r["inst"].trig[hz.name]) for r in insts for hz in spec.hazards
                     if hz.name in r["inst"].trig and r["inst"].trig[hz.name][0] <= T[j] + 1e-9), key=lambda q: q[1])
        H = hazards_at(tab, sp, _active_view(inst, float(T[j])), float(T[j]), (float(tr["x"][j]), float(tr["y"][j])),
                       tt)
        if H.m.size and H.m.any():
            info += "  + hazards"
        E = union([E, H])
    return E, H, info, s


def worst_frames(rows_path: Path, n: int = 8) -> list:
    """(fight, f, why) of the worst main rows (not next, not interrupted) of an eval: the largest miss distance at
    k 0 / 12 first, then the largest precision ratio at k 12 (one per instance)."""
    import pickle
    if not rows_path.exists():
        return []
    with open(rows_path, "rb") as fh:
        rows = pickle.load(fh)
    main = [r for r in rows if not r["next"] and not r["int"] and r["k"] in (0, 12)]
    out, seen = [], set()

    def add(r, why):
        key = (r["fight"], r["iid"], r["fam"], r["f"] // 30)
        if key in seen:
            return
        seen.add(key)
        out.append((str(r["fight"]), int(r["f"]), why, r["iid"]))
    miss = sorted(main, key=lambda r: -max([v[0] for v in r["miss"].values()] or [0.0]))
    for r in miss[:n]:
        if r["miss"]:
            add(r, f"worst miss k {r['k']} {r['fam']}: " + ", ".join(f"{k} {v[0]:.2f} u" for k, v in r["miss"].items()))
    rat = sorted([r for r in main if r["aR"] > 0 and r["k"] == 12], key=lambda r: -r["aE"] / r["aR"])
    for r in rat[:max(2, n // 2)]:
        add(r, f"worst ratio k 12 {r['fam']}: {r['aE'] / r['aR']:.2f}")
    return out
