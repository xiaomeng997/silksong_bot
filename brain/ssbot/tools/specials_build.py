"""The special-move table, offline (task 1v1 T3, forum.md 48; ssbot.combat.specials).

  build   the Clapper slam's down-slash entries from T1's theory grids (C:/ssbot/data/m2_pogo/theory/region_*.npz, one
          GridAcc per timing variant: per press frame x dx x dy x vy class x side x key after the press x jump after the
          press, the paths' outcomes), coarsened to 3-frame x 0.5 u x 0.5 u cells; an entry per cell x vy class x key
          (along the Clapper's facing) whose robust share (the minimum over the variants and over the cell's sub-cells)
          is at least --thr; 'both' (the locked-move rule) else 'bounce' (the bounce safe, the miss branch not). The
          targeted live trials of T1 (b1..b3_live.json) are counted into each entry.
  eval    open loop on the recorded slams (slams_bot.jsonl: every Clapper slam in the bot's recordings, the hero per
          frame): how often entries apply (press frames still ahead while the hero is within reach), how often an
          arrive-and-strike row exists from the hero's state (specials.strike_rows), whether the hero was in an
          entry's cell anyway (hindsight) and the hits taken in those slams.

  scripts/uv.cmd run python -m ssbot.tools.specials_build build --out-json ...
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

from ssbot.combat import specials as sp

THEORY = Path("C:/ssbot/data/m2_pogo/theory")
TARGET = Path("C:/ssbot/data/m2_pogo/target")
KB, XB, YB = 3, 2, 2        # coarse cell: 3 frames x 2 x 2 native 0.25 u cells


def robust_shares(paths: list[Path]) -> tuple[dict, dict]:
    """Per channel (4: both safe, 2: bounce + its branch safe, 1: bounce) the robust share [KP, nx, ny, vc, side,
    post, jpost] (minimum over the variants; nan where a variant has no path through the cell)."""
    out, meta = {}, None
    for p in paths:
        z = np.load(p, allow_pickle=False)
        c = z["c"]
        meta = json.loads(str(z["meta"]))
        n = c[0].astype(np.float32)
        for ch in (4, 2, 1):
            s = np.where(n > 0, c[ch] / np.maximum(n, 1), np.nan).astype(np.float32)
            out[ch] = s if ch not in out else np.fmin(np.where(np.isnan(s), -1, s), np.where(np.isnan(out[ch]), -1, out[ch]))
            out[ch] = np.where(out[ch] < 0, np.nan, out[ch])
        del c, n
    return out, meta


def build(paths: list[Path], thr: float, min_cov: float = 0.5) -> tuple[list[sp.Entry], dict]:
    R, meta = robust_shares(paths)
    KP, DX0, DY0, B = meta["KP"], meta["DX0"], meta["DY0"], meta["B"]
    _, nx, ny, nvc, nside, npost, njp = R[4].shape
    kb_n, xb_n, yb_n = KP // KB, nx // XB, ny // YB
    sh = {}
    for ch in (4, 2):
        a = R[ch][:kb_n * KB, :xb_n * XB, :yb_n * YB].reshape(kb_n, KB, xb_n, XB, yb_n, YB, nvc, nside, npost, njp)
        fin = np.isfinite(a)
        cov = fin.mean(axis=(1, 3, 5))
        mn = np.where(fin, a, np.inf).min(axis=(1, 3, 5))
        sh[ch] = np.where((cov >= min_cov) & np.isfinite(mn), mn, -1.0)     # [kb, xb, yb, vc, side, post, jp]
    # the key along the Clapper's facing: front paths (side 0) move 'toward' = -x, behind paths (side 1) +x; post
    # index 0 toward, 1 none, 2 away
    keys = {1: ((0, 2), (1, 0)), -1: ((0, 0), (1, 2)), 0: ((0, 1), (1, 1))}
    ents = []
    for key, combos in keys.items():
        best = {}
        for ch in (4, 2):
            st = np.stack([sh[ch][:, :, :, :, si, pi, :] for si, pi in combos], axis=-2)   # [kb, xb, yb, vc, 2, jp]
            st = st.reshape(st.shape[:4] + (-1,))
            best[ch] = (st.max(axis=-1), st.argmax(axis=-1) % njp)
        g = best[4][0] >= thr
        y = (~g) & (best[2][0] >= thr)
        for cert, m, ch in (("both", g, 4), ("bounce", y, 2)):
            for kb, xb, yb, vc in zip(*np.nonzero(m)):
                k0, dx0, dy0 = int(kb) * KB, DX0 + int(xb) * XB * B, DY0 + int(yb) * YB * B
                ents.append(sp.Entry(
                    id=f"CL_SLAM|k{k0}|dx{dx0:+.2f}|dy{dy0:+.2f}|vy{int(vc)}|key{key:+d}",
                    type_key="Song Heavy Sentry", move="CL_SLAM", kind="down", k0=k0, k1=k0 + KB - 1,
                    dx0=round(dx0, 3), dx1=round(dx0 + XB * B, 3), dy0=round(dy0, 3), dy1=round(dy0 + YB * B, 3),
                    vy=int(vc), key=int(key), jpost=int(best[ch][1][kb, xb, yb, vc]), cert=cert,
                    share=round(float(best[ch][0][kb, xb, yb, vc]), 3)))
    ents.sort(key=lambda e: (e.k0, e.dx0, e.dy0, e.vy, e.key))
    return ents, meta


def live_trials() -> list[dict]:
    from ssbot.combat.pogo_slam import SLAM_K0
    out = []
    for b in ("b1", "b2", "b3"):
        p = TARGET / f"{b}_live.json"
        if not p.exists():
            continue
        for t in json.loads(p.read_text("utf-8"))["trials"]:
            if "skip" in t or t.get("f_press") is None or t.get("state") not in SLAM_K0 or (t.get("hp0") or 0) < 3:
                continue
            k = SLAM_K0[t["state"]] + int(round(float(t["t_state"]) * 60))
            out.append({"k": k, "dx": t["dx"], "dy": t["dy"], "vy": t["vy"], "ok": bool(t.get("success")),
                        "bounce": bool(t.get("bounce")), "batch": b})
    return out


def attach_live(ents: list[sp.Entry], trials: list[dict]) -> list[sp.Entry]:
    out = []
    for e in ents:
        hit = [t for t in trials if e.has(t["k"], t["dx"], t["dy"], t["vy"])]
        out.append(sp.Entry(**{**e.__dict__, "live_n": len(hit), "live_ok": sum(t["ok"] for t in hit)}))
    return out


def cmd_build(a) -> int:
    paths = sorted(THEORY.glob("region_a*.npz")) + [THEORY / "region_nominal.npz"]
    t0 = time.time()
    ents, meta = build(paths, a.thr)
    ents = [e for e in ents if e.k1 <= a.kmax]
    trials = live_trials()
    ents = attach_live(ents, trials)
    tab = sp.SpecialTable(ents)
    m = {"source": [p.name for p in paths], "thr": a.thr, "kmax": a.kmax, "cell": [KB, XB * meta["B"], YB * meta["B"]],
         "built": time.strftime("%Y-%m-%d %H:%M"), "trials": len(trials)}
    p = tab.save("CL_SLAM", Path(a.dir), m)
    cnt = Counter((e.cert, "front" if e.dx0 >= 0 else "behind") for e in ents)
    # the live check per cert: trials whose press fell in any entry of that cert
    rep = {"entries": len(ents), "by_cert_side": {f"{k[0]}/{k[1]}": v for k, v in sorted(cnt.items())},
           "trials": len(trials), "s": round(time.time() - t0, 1), "path": str(p)}
    for cert in ("both", "bounce"):
        es = [e for e in ents if e.cert == cert]
        tin = [t for t in trials if any(e.has(t["k"], t["dx"], t["dy"], t["vy"]) for e in es)]
        rep[f"live_{cert}"] = {"n": len(tin), "ok": sum(t["ok"] for t in tin), "bounce": sum(t["bounce"] for t in tin)}
    tout = [t for t in trials if not any(e.has(t["k"], t["dx"], t["dy"], t["vy"]) for e in ents)]
    rep["live_outside"] = {"n": len(tout), "ok": sum(t["ok"] for t in tout)}
    by_k = Counter()
    for e in ents:
        by_k[(e.cert, (e.k0 // 10) * 10)] += 1
    rep["by_k10"] = {f"{c}/{k}": v for (c, k), v in sorted(by_k.items())}
    print(json.dumps(rep, indent=1))
    return 0


def cmd_eval(a) -> int:
    """Open loop on the recorded slams."""
    from ssbot.combat.pogo_slam import SlamTimeline
    from ssbot.knowledge import kinematics as kin
    from ssbot.tools.pogo_theory import load_kin
    tab = sp.SpecialTable.load()
    lut = tab.lut("CL_SLAM")
    tl = SlamTimeline.load()
    params, terrain = load_kin(Path(a.terrain_rec)) if a.terrain_rec else (None, None)
    rows_out = []
    n_slam = 0
    t_rows = []
    with open(a.slams, encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            if a.rec_filter and a.rec_filter not in s["rec"]:
                continue
            n_slam += 1
            if a.limit and n_slam > a.limit:
                break
            fr = s["frames"]
            hp0 = fr[0].get("hp")
            hit = any(f.get("dmg") for f in fr) or (hp0 is not None and min((f.get("hp") or hp0) for f in fr) < hp0)
            k_hit = None
            for f in fr:
                if f.get("dmg"):
                    k_hit = sp.move_frame("Song Heavy Sentry", f["st"], f["tin"])
                    k_hit = k_hit and k_hit[1]
                    break
            o = {"rec": s["rec"], "f0": s["f0"], "hit": bool(hit), "k_hit": k_hit, "in_cell": [], "apply": 0,
                 "reach": [], "near": 0}
            for f in fr:
                mf = sp.move_frame("Song Heavy Sentry", f["st"], f["tin"])
                if mf is None or not f.get("hero"):
                    continue
                k = mf[1]
                face = 1 if f["flip"] else -1
                dx = (f["hero"][0] - f["pos"][0]) * face
                dy = f["hero"][1] - f["pos"][1]
                vy = (f.get("hvel") or [0, 0])[1]
                if any(e.has(k, dx, dy, vy) for e in tab.by_move.get("CL_SLAM", ()) if e.cert in sp.CERT_OK):
                    o["in_cell"].append(k)
                if abs(dx) < 12:
                    o["near"] += 1
                app = tab.applicable("CL_SLAM", k, 36)
                if app and abs(dx) < 12:
                    o["apply"] += 1
                    if params is not None and k % a.every == 0 and (k_hit is None or k < k_hit):
                        ground = (f.get("clip_h") or "") not in ("Airborne", "Jump", "Fall", "DownSlash", "DownSlashAlt",
                                                                  "Double Jump", "Land") and abs(vy) < 0.05
                        S = kin.initial_state(params, f["hero"][0], f["hero"][1], vx=(f.get("hvel") or [0, 0])[0],
                                              vy=vy, facing=1 if (f.get("hvel") or [1])[0] >= 0 else -1, ground=ground)
                        xa = f["pos"][0] - face * tl.disp[min(k, len(tl.disp) - 1)]
                        t1 = time.perf_counter()
                        r = sp.strike_rows(params, terrain, S, lut, k, xa, f["pos"][1], face, tl.disp, 36)
                        t_rows.append((time.perf_counter() - t1) * 1e3)
                        if len(r.cmd):
                            o["reach"].append([k, len(r.cmd), r.tried, sorted({e.id for e in r.entry})[:3]])
            rows_out.append(o)
    N = len(rows_out)
    hits = [o for o in rows_out if o["hit"]]
    rep = {"slams": N, "hit": len(hits),
           "apply_any": sum(o["apply"] > 0 for o in rows_out),
           "reach_any": sum(bool(o["reach"]) for o in rows_out),
           "reach_any_hit_slams": sum(bool(o["reach"]) for o in hits),
           "in_cell_any": sum(bool(o["in_cell"]) for o in rows_out),
           "in_cell_hit": sum(bool(o["in_cell"]) and o["hit"] for o in rows_out),
           "near_slams": sum(o["near"] > 0 for o in rows_out),
           "rows_ms_p50": float(np.percentile(t_rows, 50)) if t_rows else None,
           "rows_ms_p90": float(np.percentile(t_rows, 90)) if t_rows else None,
           "rows_n_p50": float(np.median([r[1] for o in rows_out for r in o["reach"]])) if any(o["reach"] for o in rows_out) else 0,
           "tried_p50": float(np.median([r[2] for o in rows_out for r in o["reach"]])) if any(o["reach"] for o in rows_out) else 0}
    by_rec = Counter()
    for o in rows_out:
        tag = o["rec"].split("/")[0]
        by_rec[(tag, "slams")] += 1
        by_rec[(tag, "hit")] += o["hit"]
        by_rec[(tag, "reach")] += bool(o["reach"])
    rep["by_rec"] = {}
    for (tag, k), v in by_rec.items():
        rep["by_rec"].setdefault(tag, {})[k] = v
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            for o in rows_out:
                fh.write(json.dumps(o) + "\n")
    print(json.dumps(rep, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="specials_build")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("build")
    a1.add_argument("--thr", type=float, default=0.8)
    a1.add_argument("--kmax", type=int, default=77, help="the last press frame (the slam ends: Slam Recover 63 + 15)")
    a1.add_argument("--dir", default=str(sp.DIR))
    a2 = sub.add_parser("eval")
    a2.add_argument("--slams", default=str(THEORY / "slams_bot.jsonl"))
    a2.add_argument("--terrain-rec", default=None, help="a recording dir for the Forum terrain (rows need it)")
    a2.add_argument("--rec-filter", default=None)
    a2.add_argument("--limit", type=int, default=0)
    a2.add_argument("--every", type=int, default=4, help="strike rows every this many slam frames")
    a2.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    return {"build": cmd_build, "eval": cmd_eval}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
