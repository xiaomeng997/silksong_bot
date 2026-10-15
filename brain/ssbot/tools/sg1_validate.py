"""Task 1v1 SG1: the hero event macros (ssbot.combat.hero_macros) against full kinematic rollouts, and the move-data
format (ssbot.combat.move_data) against its sources (forum.md 55).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sg1_validate [--out C:/ssbot/data/m2_map/sg1] [--quick]

Grids (every cycle position q of the 50 Hz physics steps among the 60 fps frames, plus off-lattice alphas):
  jump   stand / ground jump holds x direction x run steps m x release-first r x the node's own key: per-frame box and
         rendered-pos error, apex frame / height, landing frame / x (the run after landing included: (e));
  slash  ground jump x press frame x key x jump after the press (T1's jpost) x a Clapper root box at offsets: the
         contact frame (the macro's sweep vs the rollout's own, same rule), then the bounce (rollout with EV_POGO on
         that contact vs the macro's spliced profile): per-frame error, bounce apex frame / height, landing frame /
         x, the pogo i-frame span;
  glide  the umbrella from an apex: landing and horizontal reach against the no-inertia cone;
  snap   the hull over q (the map has no q dimension): the per-frame spread of the swept box, and the off-lattice
         alphas' residual against the macro of their cycle position.
Writes validate.json (summary) and rows_*.npz.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from ssbot.combat.hero_macros import ALPHAS, HeroMacros, Sweep, key_mask
from ssbot.knowledge import kinematics as kin

OUT = Path(r"C:\ssbot\data\m2_map\sg1")
X0 = 31.0
ROOT_BOX = (-1.341, 1.873, -4.434, -0.532)        # the Clapper's root box in the slam antic (k >= 5), its frame
CL_POS_ABOVE_FLOOR = 4.434


def q_of_alpha(hm: HeroMacros, alpha: float) -> int:
    S = kin.initial_state(hm.params, X0, hm.stand_py, facing=1, ground=True, alpha=alpha)
    S[kin.VX], S[kin.MOVE] = hm.params.run_speed, 1
    ro = kin.rollout(S, np.full((1, 30), kin.B_RIGHT, np.int64), hm.params, hm.terrain)
    d = np.rint(np.diff(ro.phys[0, :, 0]) / hm.step_u).astype(int)
    for q in range(6):
        if (d == hm.st[q, 1:31]).all():
            return q
    raise RuntimeError(alpha)


def running(hm: HeroMacros, alpha: float, key0: int) -> np.ndarray:
    """A ground node at X0 holding key0 since the frame before (vx and the held move set)."""
    S = kin.initial_state(hm.params, X0, hm.stand_py, vx=key0 * hm.params.run_speed, facing=key0 or 1, ground=True,
                          alpha=alpha)
    S[kin.MOVE] = key0
    S[kin.PREV] = key_mask(key0)
    return S


def masks_of(keys: np.ndarray, h: int, press: int | None = None, jpost: int = 0) -> np.ndarray:
    m = np.array([key_mask(int(k)) for k in keys], np.int64)
    m[:h] |= kin.B_JUMP
    if press is not None:
        m[max(press - 3, 0):press + 3] |= kin.B_DOWN
        m[press] |= kin.B_ATTACK
        if jpost:
            m[press + 3:press + 19] |= kin.B_JUMP
    return m


def first_ground(fl: np.ndarray, after: int) -> int:
    g = np.flatnonzero((fl[after + 1:] & kin.F_GROUND) != 0)
    return after + 1 + int(g[0]) if len(g) else -1


def takeoff_land(fl: np.ndarray) -> tuple[int, int]:
    air = np.flatnonzero((fl & kin.F_GROUND) == 0)
    if not len(air):
        return -1, -1
    return int(air[0]), first_ground(fl, int(air[0]))


def stats(a, unit="u") -> dict:
    a = np.abs(np.asarray(a, float))
    if not len(a):
        return {"n": 0}
    return {"n": int(len(a)), "max": round(float(a.max()), 4), "p99": round(float(np.percentile(a, 99)), 4),
            "p50": round(float(np.median(a)), 4), "unit": unit}


def grid_jump(hm: HeroMacros, alphas: list[float], quick: bool) -> tuple[dict, dict]:
    holds = (0, 1, 2, 3, 5, 8, 12, 16, 20, 25, 30, 35, 40) if not quick else (0, 3, 12, 30)
    ms = (0, 3, 8, 15, 25, 40) if not quick else (0, 8, 25)
    rows = []
    T = 90
    for alpha in alphas:
        q = q_of_alpha(hm, alpha)
        cases, M = [], []
        for h in holds:
            for d in (1, -1):
                for m in ms:
                    for r in (0, 6):
                        for key0 in (0, 1):
                            keys, _ = hm.solve_keys(q, m, d, T, r)
                            cases.append((h, d, m, r, key0, keys))
                            M.append(masks_of(keys, h))
        M = np.array(M)
        S = np.stack([running(hm, alpha, key0) for (_, _, _, _, key0, _) in cases], axis=1)
        ro = kin.rollout(S, M, hm.params, hm.terrain, threads=4)
        for i, (h, d, m, r, key0, keys) in enumerate(cases):
            sw, _ = hm.sweep(X0, q, keys, "jump" if h else "stand", max(h, 1), key0)
            fl = ro.flags[i]
            t_off, t_land = takeoff_land(fl)
            n = (t_land + 20) if t_land > 0 else T
            n = min(n, T + 1)
            eb = np.abs(ro.box[i, 1:n] - sw.box[1:n])          # index 0 is the node itself (given, not predicted)
            ep = np.abs(ro.pos[i, 1:n] - sw.pos[1:n])
            ya, ym = ro.box[i, :n, 1], sw.box[:n, 1]
            m_off, m_land = takeoff_land(sw.flags[:n])
            row = {"alpha": alpha, "q": q, "h": h, "d": d, "m": m, "r": r, "key0": key0,
                   "ex": float(eb[:, [0, 2]].max()), "ey": float(eb[:, [1, 3]].max()),
                   "epx": float(ep[:, 0].max()), "epy": float(ep[:, 1].max()),
                   "apex_f": int(np.argmax(ym)) - int(np.argmax(ya)), "apex_y": float(ym.max() - ya.max()),
                   "land_f": (m_land - t_land) if (h and t_land > 0 and m_land > 0) else 0,
                   "land_x": float(sw.box[t_land, 0] - ro.box[i, t_land, 0]) if (h and t_land > 0) else 0.0,
                   "land_none": int(bool(h) and (t_land < 0) != (m_land < 0))}
            rows.append(row)
    return summarize(rows, ("ex", "ey", "epx", "epy", "apex_y", "land_x"), ("apex_f", "land_f")), {"rows": rows}


def summarize(rows: list[dict], u_keys, f_keys, by=("lattice",)) -> dict:
    out = {}
    for name, sel in (("lattice", lambda r: r["alpha"] in ALPHAS), ("off_lattice", lambda r: r["alpha"] not in ALPHAS)):
        rs = [r for r in rows if sel(r)]
        if not rs:
            continue
        out[name] = {k: stats([r[k] for r in rs]) for k in u_keys} | \
                    {k: stats([r[k] for r in rs], "frames") for k in f_keys} | {"rows": len(rs)}
        for k in ("land_none", "contact_mismatch"):
            if k in rs[0]:
                out[name][k] = int(sum(r[k] for r in rs))
    return out


def grid_slash(hm: HeroMacros, alphas: list[float], quick: bool) -> tuple[dict, dict]:
    holds = (3, 8, 14, 20, 30) if not quick else (8, 20)
    presses = (6, 10, 14, 18, 24, 30, 36) if not quick else (10, 18, 30)
    offs = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0) if not quick else (-1.0, 0.0, 1.0)
    T = 110
    rows = []
    cy = hm.floor_y + CL_POS_ABOVE_FLOOR
    for alpha in alphas:
        q = q_of_alpha(hm, alpha)
        cases, M = [], []
        for h in holds:
            for a in presses:
                for d in (1, 0, -1):
                    keys = np.full(T, d, np.int64)
                    for jp in (0, 1):
                        cases.append((h, a, d, jp, keys))
                        M.append(masks_of(keys, h, a, jp))
        M = np.array(M)
        S = kin.initial_state(hm.params, X0, hm.stand_py, facing=1, ground=True, alpha=alpha)
        miss = kin.rollout(S, M, hm.params, hm.terrain, threads=4)
        bounce_cases, EV = [], []
        for i, (h, a, d, jp, keys) in enumerate(cases):
            face = d if d else 1
            for off in offs:
                cx_c = miss.box[i, a + 1, 0] + hm.hw + off            # the box placed relative to the press x
                box = np.array([cx_c + ROOT_BOX[0], cx_c + ROOT_BOX[1], cy + ROOT_BOX[2], cy + ROOT_BOX[3]])
                tg = (lambda j, b=box: [b])
                rs = Sweep(miss.box[i], miss.pos[i], miss.flags[i], -1)
                c_r = hm.contact(rs, a + 1, face, tg)
                sw_m, c_m = hm.sweep(X0, q, keys, "jump", h, press=a, face=face, targets=tg, n=T + 1)
                cut = min(c_m if c_m >= 0 else T, c_r if c_r >= 0 else T)
                glide = bool(np.abs(miss.box[i, a + 1:cut + 1, 1] - sw_m.box[a + 1:cut + 1, 1]).max() > 1e-6)                     if cut > a + 1 else False
                row = {"alpha": alpha, "q": q, "h": h, "a": a, "d": d, "jp": jp, "off": off, "c_r": c_r, "c_m": c_m,
                       "contact_mismatch": int(c_r != c_m), "glide_before": int(glide)}
                rows.append(row)
                if c_r >= 0:
                    ev = np.zeros(T, np.int64)
                    ev[c_r - 1] = kin.EV_POGO
                    bounce_cases.append((len(rows) - 1, i, keys, h, a, face, c_r))
                    EV.append(ev)
        if not bounce_cases:
            continue
        Mb = np.array([M[i] for (_, i, *_rest) in bounce_cases])
        hit = kin.rollout(S, Mb, hm.params, hm.terrain, events=np.array(EV), threads=4)
        for b, (ri, i, keys, h, a, face, c) in enumerate(bounce_cases):
            sw, _ = hm.sweep(X0, q, keys, "jump", h, press=a, face=face, contact=c, n=T + 1)
            fl = hit.flags[b]
            t_land = first_ground(fl, c)
            n = min((t_land + 10) if t_land > 0 else T + 1, T + 1)
            eb = np.abs(hit.box[b, c:n] - sw.box[c:n])
            ep = np.abs(hit.pos[b, c:n] - sw.pos[c:n])
            ya, ym = hit.box[b, c:n, 1], sw.box[c:n, 1]
            m_land = first_ground(sw.flags, c)
            inv_r = np.flatnonzero((fl[c:c + 20] & kin.F_INVULN) != 0)
            inv_m = np.flatnonzero((sw.flags[c:c + 20] & kin.F_INVULN) != 0)
            pre = np.abs(hit.box[b, :c + 1] - sw.box[:c + 1]).max()
            rows[ri] |= {"pre": float(pre), "ex": float(eb[:, [0, 2]].max()), "ey": float(eb[:, [1, 3]].max()),
                         "epx": float(ep[:, 0].max()), "epy": float(ep[:, 1].max()),
                         "apex_f": int(np.argmax(ym)) - int(np.argmax(ya)), "apex_y": float(ym.max() - ya.max()),
                         "land_f": (m_land - t_land) if (t_land > 0 and m_land > 0) else 0,
                         "land_x": float(sw.box[t_land, 0] - hit.box[b, t_land, 0]) if t_land > 0 else 0.0,
                         "land_none": int((t_land < 0) != (m_land < 0)),
                         "inv_r": [int(inv_r[0]), int(inv_r[-1])] if len(inv_r) else None,
                         "inv_m": [int(inv_m[0]), int(inv_m[-1])] if len(inv_m) else None,
                         "contact_y": float(hit.box[b, c, 1] - hm.stand_y0)}
    # jp = 0: the macro's own inputs; jp = 1 (T1's jump re-held from press + 3) puts the jump key in the air, which
    # the macro does not model (the air hang near the apex, the umbrella while falling): reported apart
    br = [r for r in rows if "ex" in r and not r["jp"]]
    s = summarize(br, ("pre", "ex", "ey", "epx", "epy", "apex_y", "land_x"), ("apex_f", "land_f"))
    s["jp1_outside_macro"] = summarize([r for r in rows if "ex" in r and r["jp"]],
                                       ("pre", "ex", "ey", "apex_y"), ("apex_f", "land_f"))
    s["contacts"] = {"rows": len(rows), "with_contact_rollout": int(sum(r["c_r"] >= 0 for r in rows)),
                     "mismatch": int(sum(r["contact_mismatch"] for r in rows)),
                     "mismatch_jp0": int(sum(r["contact_mismatch"] for r in rows if not r["jp"])),
                     "mismatch_jp0_lattice": int(sum(r["contact_mismatch"] for r in rows
                                                     if not r["jp"] and r["alpha"] in ALPHAS)),
                     "mismatch_jp0_one_frame": int(sum(r["contact_mismatch"] for r in rows
                                                       if not r["jp"] and r["c_r"] >= 0 and r["c_m"] >= 0
                                                       and abs(r["c_r"] - r["c_m"]) == 1)),
                     "rows_jp0": int(sum(not r["jp"] for r in rows)),
                     "mismatch_jp1_vertical_changed_before": int(sum(r["contact_mismatch"] for r in rows
                                                                  if r["jp"] and r["glide_before"])),
                     "jp1_vertical_changed_before": int(sum(r["glide_before"] for r in rows if r["jp"])),
                     "mismatch_lattice": int(sum(r["contact_mismatch"] for r in rows if r["alpha"] in ALPHAS))}
    s["iframes"] = {"rollout_span": sorted({tuple(r["inv_r"]) for r in br if r["inv_r"]}),
                    "macro_span": sorted({tuple(r["inv_m"]) for r in br if r["inv_m"]}),
                    "disagree": int(sum(r["inv_r"] != r["inv_m"] for r in br))}
    cyv = np.array([r["contact_y"] for r in br])
    s["contact_height_above_stand"] = stats(cyv) if len(cyv) else {}
    if len(cyv):
        s["contact_height_above_stand"]["min"] = round(float(cyv.min()), 3)
    return s, {"rows": rows}


def grid_glide(hm: HeroMacros) -> dict:
    out = []
    for q in range(6):
        for h in (12, 30):
            p = hm.jump(h, q)
            for u in (0, 4, 8):
                for key in (-1, 0, 1):
                    g = hm.glide(h, q, u, key)
                    t_open = p.apex + u
                    land = g.land
                    x_open = g.box[t_open, 0]
                    dx = (g.box[land, 0] - x_open) if land > 0 else float("nan")
                    cone = hm.step_u * hm.reach_steps(q, land, t_open - 1) if land > 0 else float("nan")
                    out.append({"q": q, "h": h, "u": u, "key": key, "land": land, "plain_land": p.land,
                                "dx": round(float(dx), 3), "cone": round(float(cone), 3)})
    lands = [r["land"] - r["plain_land"] for r in out if r["land"] > 0]
    ratio = [abs(r["dx"]) / r["cone"] for r in out if r["key"] and r["land"] > 0 and r["cone"] > 0]
    return {"rows": len(out), "landing_later_frames": stats(lands, "frames"),
            "reach_over_run_cone": stats(ratio, "ratio"), "examples": out[:6] + out[-6:]}


def snap(hm: HeroMacros) -> dict:
    """The hull over q: per frame the spread of the swept box between the six cycle positions."""
    res = {}
    T = 80
    for h in (1, 3, 8, 12, 20, 30, 40):
        ys, xs = [], []
        for d, m in ((1, 0), (1, 20), (1, 40)):
            B = []
            for q in range(6):
                keys, _ = hm.solve_keys(q, m, d, T)
                B.append(hm.sweep(X0, q, keys, "jump", h, n=T + 1)[0].box)
            B = np.stack(B)
            ys.append((B[..., 1].max(0) - B[..., 1].min(0)).max())
            xs.append((B[..., 0].max(0) - B[..., 0].min(0)).max())
        res[f"h{h}"] = {"y_spread_max": round(float(max(ys)), 3), "x_spread_max": round(float(max(xs)), 3)}
    cls = hm.apex_classes()
    res["apex_spread"] = {"frames_max": int(max(max(c["apex"]) - min(c["apex"]) for c in cls)),
                          "height_max": round(float(max(max(c["height"]) - min(c["height"]) for c in cls)), 3),
                          "land_frames_max": int(max(max(c["land"]) - min(c["land"]) for c in cls))}
    return res


def move_data_checks() -> dict:
    from ssbot.combat.move_data import load_cl_slam, load_raster_move, raster_boxes
    from ssbot.combat.pogo_slam import SlamTimeline
    from ssbot.knowledge.hitbox_tables import load_templates
    spec = load_cl_slam()
    ref = [SlamTimeline.load()] + SlamTimeline.variants()
    worst = 0.0
    for r, m in zip(ref, spec.variants("t1")):
        ham = m.boxes["Slam Collider 1"].copy()
        sel = np.isfinite(m.boxes["Slam Collider 2"][:, 0])
        ham[sel] = m.boxes["Slam Collider 2"][sel]
        for x, y in ((r.root, m.boxes["root"]), (r.hammer, ham), (r.disp, m.disp)):
            worst = max(worst, float(np.abs(np.nan_to_num(x, nan=1e9) - np.nan_to_num(y, nan=1e9)).max()))
    obs = spec.variants("observed")
    t1_states = {(48, 4), (48, 5), (49, 4), (49, 5)}
    cover = sum(spec.states[0].share(a) * spec.states[1].share(s) for a, s in t1_states)
    tp, _ = load_templates(spec_path_npz(), prefix="CC_SLAM/anchor")
    tpl = tp["CC_SLAM/anchor"]
    nom = spec.timeline()
    cov = []
    for k in range(min(78, tpl.nt)):
        rb = raster_boxes(tpl, k, 1)
        for b in nom.damage(k):
            X, Y = np.meshgrid(np.linspace(b[0] + 1e-3, b[1] - 1e-3, 15), np.linspace(b[2] + 1e-3, b[3] - 1e-3, 15))
            inside = np.zeros(X.size, bool)
            for r_ in rb:
                inside |= (X.ravel() >= r_[0]) & (X.ravel() <= r_[1]) & (Y.ravel() >= r_[2]) & (Y.ravel() <= r_[3])
            cov.append(inside.mean())
    ev = load_raster_move("ChoirClapper", "CC_EVADE")
    return {"cl_slam_vs_slamtimeline_max_abs_diff": worst, "t1_variants": 9, "observed_variants": len(obs),
            "t1_antic_s0_share_of_slams": round(cover, 4),
            "antic_47_share": round(spec.states[0].share(47), 4), "slam2_5_share": round(spec.states[3].share(5), 4),
            "cc_slam_raster_covers_template_area": {"mean": round(float(np.mean(cov)), 4),
                                                    "min": round(float(np.min(cov)), 3),
                                                    "boxes_below_0.99": int(sum(c < 0.99 for c in cov)),
                                                    "boxes": len(cov)},
            "cc_evade": {"source": ev.source, "frames": ev.K, "box_slots": len(ev.tracks),
                         "states": [(s.name, s.nominal) for s in ev.states]}}


def spec_path_npz() -> Path:
    from ssbot.combat.move_data import FORUM
    return FORUM / "ChoirClapper_hitboxes.npz"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args(argv)
    from ssbot.tools.pogo_theory import load_kin
    params, terrain = load_kin()
    t0 = time.time()
    hm = HeroMacros(params, terrain)
    alphas = list(ALPHAS) + ([0.003, 0.13, 0.29, 0.4, 0.71, 0.88] if not a.quick else [0.13])
    res = {"cooldown_frames": [hm.cooldown(q) for q in range(6)], "iframes": [hm.iframes(q) for q in range(6)],
           "bounce_apex": [[hm.bounces[q].apex, round(float(hm.bounces[q].y[hm.bounces[q].apex]), 4)]
                           for q in range(6)],
           "step_u": hm.step_u}
    j, jr = grid_jump(hm, alphas, a.quick)
    res["jump"] = j
    s, sr = grid_slash(hm, alphas, a.quick)
    res["slash"] = s
    res["glide"] = grid_glide(hm)
    res["snap"] = snap(hm)
    res["apex_classes"] = hm.apex_classes()
    res["move_data"] = move_data_checks()
    res["seconds"] = round(time.time() - t0, 1)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / ("validate_quick.json" if a.quick else "validate.json")).write_text(json.dumps(res, indent=1), "utf-8")
    if not a.quick:
        (a.out / "rows_jump.json").write_text(json.dumps(jr["rows"]), "utf-8")
        (a.out / "rows_slash.json").write_text(json.dumps(sr["rows"]), "utf-8")
    print(json.dumps({k: res[k] for k in ("cooldown_frames", "iframes", "bounce_apex", "jump", "slash", "snap",
                                          "seconds")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
