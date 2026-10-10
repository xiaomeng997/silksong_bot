"""World-space pictures of the attack-range estimate on the person's frames (tools.attack_range_build png): per frame
the estimate at k = 0 (filled) and k = 12 (outlined), its hero-centre region at k = 0 (thin yellow: where the hero
transform must not be), the enemy's REAL damage colliders now (thick red) and over the next 12 game frames (thin red,
the frame at +12 magenta), the hero's hurtbox and transform, a 1 u grid and the numbers of compare() at k 0 / 12."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ssbot.combat.attack_range import FT, HERO_DY, HERO_HALF, bin_of, contours, hero_space, load_table, poly_mask
from ssbot.tools.attack_range_build import compare, frame_polys, load_tracks, segment

# (session, raw frame, why): the person's own cases first
CASES = (("20261009_085824", 5690, "whip antic, frame 5690 (the person)"),
         ("20261009_161454", 2916, "Battle Idle, frame 2916 (the person)"))
PX_U = 40
FAM_COLOR = (60, 160, 255)        # BGR orange: the estimate
K12_COLOR = (255, 220, 80)        # BGR light blue: the estimate at k = 12


def _find(tracks, sess: str, f: int):
    """(track, frame index) of the Choristor in play nearest to raw frame f of the session (the one in a family
    instance first)."""
    best = None
    for tr in tracks:
        if not str(tr["fight"]).startswith(sess):
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
    est, info = {}, ""
    if idx[j] >= 0:
        r = insts[idx[j]]
        inst = r["inst"]
        b = bin_of(float(T[j]) - inst.t0)
        br = inst.branch if (inst.branch_t is not None and inst.branch_t <= T[j] + 1e-9) else None
        for k in (0, 12):
            est[k] = tab.place(inst.fam, br, b + k, (inst.x0, inst.y0), inst.s, inst.hero_du,
                               now=(float(tr["x"][j]), float(tr["y"][j])), b_now=b)
        info = (f"{inst.fam} branch {br or 'pending (union)'}{' -> ' + str(inst.branch) if br is None else ''}  "
                f"bin {b} ({b * FT:.2f} s since the antic start)  anchor ({inst.x0:.2f}, {inst.y0:.2f}) "
                f"facing {'+x' if inst.s > 0 else '-x'}" + (f"  hero du {inst.hero_du:.2f}" if inst.fam in tab.spec.aim
                                                          else ""))
        s = inst.s
    else:
        body = frame_polys(tr, j, shapes, tab.spec.body)
        for k in (0, 12):
            est[k] = poly_mask(body)
        info = "idle: the exact body now, for every k (no growth)"
        s = f1 if tr["flip"][j] else -f1
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
    lines = [f"{tr['fight']} raw frame {int(tr['f'][j])}  Choristor iid {tr['iid']}  state {tr['st'][j]}  {why}", info]
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
    frames right after a Slash Recover), and the frames of the whip that follows frame 5690."""
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
            if sess == "20261009_085824" and any(abs(int(tr["f"][q]) - 5690) <= 1 for q in fr):
                for q in fr[::max(1, len(fr) // 8)]:
                    out.append((sess, int(tr["f"][q]), f"the whip after 5690 ({tr['st'][q]})"))
                continue
            if seen.get(inst.fam, 0) >= per_fam or r["interrupted"]:
                continue
            seen[inst.fam] = seen.get(inst.fam, 0) + 1
            for q in (fr[0], fr[len(fr) // 3], fr[2 * len(fr) // 3], fr[-1]):
                out.append((sess, int(tr["f"][q]), f"{inst.fam} #{seen[inst.fam]} ({tr['st'][q]})"))
            if inst.fam == "CH_SLASH" and r["j1"] + 1 < len(tr["f"]):
                for d in (1, 6, 12):
                    q = min(r["j1"] + d, len(tr["f"]) - 1)
                    if idx[q] < 0:
                        out.append((sess, int(tr["f"][q]), f"after Slash Recover +{d} f ({tr['st'][q]})"))
    return out


def cmd_png(a) -> int:
    import cv2
    tab = load_table()
    shapes = tab.meta.get("shapes") or {}
    tracks = load_tracks("person", sessions=("20261009_085824", "20261009_161454"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    frames = list(CASES) + pick_frames(tracks, tab)
    index = []
    for sess, f, why in frames:
        tr, j = _find(tracks, sess, f)
        if tr is None:
            print(f"{sess} f {f}: no Choristor in play")
            continue
        img = draw_frame(tr, j, tab, shapes, why)
        if img is None:
            continue
        fn = out / f"{sess}_f{f}_{str(tr['st'][j]).replace(' ', '_').replace('?', '')}.png"
        cv2.imwrite(str(fn), img)
        index.append({"png": fn.name, "session": sess, "f": f, "why": why, "state": tr["st"][j]})
    (out / "index.json").write_text(json.dumps(index, indent=1), "utf-8")
    print(f"{len(index)} PNGs in {out}")
    return 0
