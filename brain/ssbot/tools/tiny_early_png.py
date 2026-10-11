"""PNG strips of the Tiny's dive drawn from the Maestro's antic (ssbot.tools.tiny_early, forum.md sec. 40): one image per
Maestro Fire Antic, four panels = what is drawn 0.0 / 0.2 / 0.4 / 0.6 s after the antic entry against what the Tiny
really did (antic -> FIRE -> dive -> slide / wall -> pull up / return).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.tiny_early_png [--set person] [--n 8]

Colours: red line = the Tiny's real path from the antic entry to its return (red dot: its real FIRE point; dark red
box: where it is at the panel's time); orange band = the predicted path if the hero holds (box: the predicted FIRE
point); yellow band = the variants the hero can still make (the other side, a longer slide); white = the hero at the
panel's time (tick: its x at FIRE); magenta = the Maestro; grey = floor and walls.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ssbot.combat.are_types import tiny as TY
from ssbot.tools.tiny_early import OUT, _m_at, analyse, events, frame_dt

PANELS = (0.0, 0.2, 0.4, 0.6)
X0, X1, Y0, Y1, PX = 13.0, 50.0, 2.0, 20.0, 18.0
TINY_W, TINY_H = 1.0, 1.08


def _p(x: float, y: float) -> tuple:
    return int(round((x - X0) * PX)), int(round((Y1 - y) * PX))


def _box(img, x, y, w, h, col, th=1):
    import cv2
    cv2.rectangle(img, _p(x - w / 2, y + h / 2), _p(x + w / 2, y - h / 2), col, th)


def _band(img, rows, col, alpha):
    import cv2
    pts = np.array([_p(r[1], r[2]) for r in rows if r[3] not in ("ret", "done")], np.int32)
    if len(pts) < 2:
        return
    ov = img.copy()
    cv2.polylines(ov, [pts], False, col, int(TINY_W * PX), cv2.LINE_AA)
    cv2.addWeighted(ov, alpha, img, 1 - alpha, 0, img)
    cv2.polylines(img, [pts], False, col, 1, cv2.LINE_AA)


def panel(ev: dict, r: dict, a: float) -> np.ndarray:
    import cv2
    t, m = ev["t"], ev["m"]
    j0, jf, je, t0 = ev["j0"], ev["jf"], ev["je"], ev["t0"]
    W, H = int((X1 - X0) * PX), int((Y1 - Y0) * PX)
    img = np.full((H + 40, W, 3), 30, np.uint8)
    sub = img[40:]
    cv2.line(sub, _p(X0, 3.0), _p(X1, 3.0), (110, 110, 110), 2)
    for xw in (TY.X_WALLS[0] - 0.5, TY.X_WALLS[1] + 0.5):
        cv2.line(sub, _p(xw, Y0), _p(xw, Y1), (110, 110, 110), 2)
    ja = int(np.searchsorted(t["T"], t0 + a - 1e-6))
    ja = min(max(ja, j0), jf - 1)
    T = float(t["T"][ja])
    ma = _m_at(m, T)
    hx = float(t["hx"][ja])
    t_fire = max(t0 + TY.ANTIC_WAIT + TY.ANTIC_FRAMES * frame_dt(t, j0, jf) - T, 0.0)
    head = f"{a:.1f} s after the antic entry: FIRE in {t_fire:.2f} s"
    if ma is not None:
        vs = TY.variants(float(t["x"][ja]), float(t["y"][ja]), float(t["vx"][ja]), float(t["vy"][ja]), ma, r["sm"],
                         hx, t_fire)
        for rows, ok in sorted(vs, key=lambda z: z[1]):
            _band(sub, rows, (0, 165, 255) if ok else (0, 230, 255), 0.35 if ok else 0.18)
        base = vs[0][0]
        k = next((i for i, z in enumerate(base) if z[3] != "ready"), len(base) - 1)
        _box(sub, base[k][1], base[k][2], TINY_W, TINY_H, (0, 165, 255), 2)
        err = float(np.hypot(base[k][1] - r["xF"], base[k][2] - r["yF"]))
        side_p = 1 if hx >= base[k][1] else -1
        head += f" | FIRE point err {err:.2f} u, side {'ok' if side_p == r['side'] else 'WRONG'}"
        head += ", both sides drawn" if len(vs) > 2 else ""
        _box(sub, ma[0], ma[1], 1.76, 1.95, (255, 0, 255), 1)
    pts = np.array([_p(float(t["x"][q]), float(t["y"][q])) for q in range(j0, je)], np.int32)
    cv2.polylines(sub, [pts], False, (40, 40, 255), 2, cv2.LINE_AA)
    cv2.circle(sub, _p(r["xF"], r["yF"]), 5, (40, 40, 255), -1)
    _box(sub, float(t["x"][ja]), float(t["y"][ja]), TINY_W, TINY_H, (0, 0, 160), -1)
    hb = t["hbox"][ja]
    if np.all(np.isfinite(hb)):
        cv2.rectangle(sub, _p(hb[0], hb[3]), _p(hb[2], hb[1]), (255, 255, 255), 2)
    else:
        _box(sub, hx, float(t["hy"][ja]), 0.5, 1.3, (255, 255, 255), 2)
    hxf = float(t["hx"][jf])
    cv2.line(sub, _p(hxf, 2.4), _p(hxf, 3.6), (255, 255, 255), 2)
    cv2.putText(img, head, (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (230, 230, 230), 1, cv2.LINE_AA)
    return img


def strip(ev: dict, r: dict, title: str) -> np.ndarray:
    import cv2
    ps = [panel(ev, r, a) for a in PANELS]
    top = np.hstack([ps[0], np.full((ps[0].shape[0], 6, 3), 80, np.uint8), ps[1]])
    bot = np.hstack([ps[2], np.full((ps[2].shape[0], 6, 3), 80, np.uint8), ps[3]])
    img = np.vstack([top, np.full((6, top.shape[1], 3), 80, np.uint8), bot])
    hdr = np.full((34, img.shape[1], 3), 15, np.uint8)
    cv2.putText(hdr, title, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)
    return np.vstack([hdr, img])


def pick(rs: list, n: int) -> list:
    """Varied events: the hero far / near (both sides drawn), a wall bonk, a slide past the hero, a short dive."""
    out, seen = [], set()
    kinds = [("near the FIRE point (both sides drawn)", lambda r: r["pred"].get(0.0, {}).get("both")),
             ("wall bonk", lambda r: "Wall Bonk" in r["states"]),
             ("slide past the hero, pull up", lambda r: "Brake" in r["states"] and "Pull Up" in r["states"]),
             ("pull up in the air", lambda r: "Brake" not in r["states"] and "Pull Up" in r["states"]),
             ("side WRONG at the antic entry", lambda r: not r["pred"].get(0.0, {}).get("side_ok", True))]
    while len(out) < n:
        added = False
        for why, f in kinds:
            for i, (ev, r) in enumerate(rs):
                if i in seen or r["hit"] or "Return" not in r["states"] or not f(r):
                    continue
                seen.add(i)
                out.append((ev, r, why))
                added = True
                break
            if len(out) >= n:
                break
        if not added:
            break
    return out


def main(argv=None) -> int:
    import cv2
    from ssbot.knowledge.forum_cache import load_cache
    from ssbot.tools.attack_range_build import _cache_files, _idle_priority, person_caches
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", default="person", choices=("dev", "fresh", "r2", "person"))
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    _idle_priority()
    out = Path(a.out) if a.out else OUT / "png"
    out.mkdir(parents=True, exist_ok=True)
    files = person_caches() if a.set == "person" else _cache_files(a.set)
    rs = []
    for f in files:
        c = load_cache(f)
        for ev in events(c):
            r = analyse(ev)
            if r is not None:
                fr = c["f_raw"] if "f_raw" in c else c["f"]
                r["fight"], r["frame"] = f.stem, int(fr[ev["t"]["fi"][ev["j0"]]])
                rs.append((ev, r))
        if len(rs) > 40 * a.n:
            break
    index = []
    for ev, r, why in pick(rs, a.n):
        title = f"{r['fight']} frame {r['frame']} ({a.set}): {why}; chain {' > '.join(r['states'])}"
        name = f"{r['fight']}_f{r['frame']}.png"
        cv2.imwrite(str(out / name), strip(ev, r, title))
        index.append({"png": name, "why": why, "states": r["states"], "hit": r["hit"]})
        print(name, why)
    (out / f"index_{a.set}.json").write_text(json.dumps(index, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
