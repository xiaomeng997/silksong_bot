"""Task 1v1 SG2: the score map (ssbot.combat.special_map) against data (forum.md 56): theory -> recordings.

    ../scripts/uv.cmd run python -m ssbot.tools.sg2_check [--out C:/ssbot/data/m2_map/sg2] [--skip-live]

(a) T1's targeted live trials (C:/ssbot/data/m2_pogo/target/b{1,2,3}_live.json; the person's points are the "P"
    groups): each trial's press state is looked up on the map (its jump tube h, the index whose height matches the
    logged press, the logged x at the press; every physics phase): the press certified (a robust strike with the
    trial's held key), the approach (the jump's frames before the press clear of the dilated damage), the jump-start
    and ground values. Precision / recall of "certified" and of "score above a threshold" against the trial's
    success; every certified failure with its attribution (jump after the press = not the map's path; press shift /
    late = execution; T1's theory on the logged path also predicts the loss = the logged path left the map's
    assumptions; otherwise model error).
(b) The 2026-10-12 live slam hits (C:/ssbot/data/m2_live_g s1 / s2 hit rows, the recordings in
    C:/ssbot/data/runs/m2): every frame from the antic entry to the hit on the map (ground node, or the airborne
    macro state whose heights match this frame and the previous one), the takeoff that committed the hero, and what
    the map's lookahead would have chosen there.
Writes <out>/check.json.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from ssbot.combat import special_map as sm
from ssbot.combat.pogo_slam import SLAM_K0
from ssbot.tools.special_map_build import OUT, setup

TRIALS = [Path(rf"C:\ssbot\data\m2_pogo\target\b{i}_live.json") for i in (1, 2, 3)]
LIVE = [Path(r"C:\ssbot\data\m2_live_g\s1.json"), Path(r"C:\ssbot\data\m2_live_g\s2.json")]
RUNS = Path(r"C:\ssbot\data\runs\m2")
HERO_PY = 1.553                     # hero pos above its box bottom standing (pogo_slam.HERO_STAND_DY)
# demo runs without hit rows in m2_live_g: every slam with an hp loss is taken from the recording (the person's rnv2nd
# 0.5x demo on 8720b7a: ep 2 had two Slam Collider 1 hits)
EXTRA_RUNS = ["20261012_203232_Forum_W_w7_eval_planner_oracle_x0.5_clashM"]
HIST = 5                           # frames of height history an airborne live state must match on the map


def load_trials() -> list[dict]:
    out = []
    for f in TRIALS:
        for t in json.loads(f.read_text("utf-8"))["trials"]:
            if t.get("success") is None or "state" not in t or t.get("state") not in SLAM_K0:
                continue
            t["batch"] = f.stem.split("_")[0]
            out.append(t)
    return out


class TrialCheck:
    def __init__(self, geo: sm.Geometry):
        self.g = geo
        self.disp = geo.spec.timeline(K=geo.K + 2).disp
        self.tube_of = {t.param: i for i, t in enumerate(geo.tubes) if t.kind == "jump"}
        self.rows: dict[int, dict] = {}

    def prep(self, i: int, t: dict) -> dict | None:
        g = self.g
        tg = t["target"]
        h = tg["h"]
        if h not in self.tube_of:
            return None
        kp = SLAM_K0[t["state"]] + int(round(float(t["t_state"]) * 60))
        side = 1 if tg["x0"] >= 0 else -1
        d_post = -side * int(tg["post"])
        d_pre = -side * int(tg["pre"])
        xp = float(t["dx"]) + float(self.disp[min(max(kp, 0), len(self.disp) - 1)])
        y_box = float(t["dy"]) + g.spec.pos_above_floor - HERO_PY
        return {"i": i, "kp": kp, "k_node": kp - 1, "h": h, "a": tg["a"], "side": side, "d_post": d_post,
                "d_pre": d_pre, "x_press": xp, "x_node": xp - d_pre * g.step, "y_box": y_box,
                "x0_plan": tg["x0"], "tau": tg["tau_j"]}

    def phase(self, pm: sm.PhaseMap, r: dict) -> dict:
        """The map's verdicts in phase pm.p: the tube index j (a-2..a+2) whose height best matches the press."""
        g = self.g
        ti = self.tube_of[r["h"]]
        t = g.tubes[ti]
        best = None
        for j in range(max(r["a"] - 2, 1), r["a"] + 3):
            if j >= t.n:
                continue
            k0 = r["k_node"] - j
            q0 = (pm.p - k0) % 6
            if j >= t.L[q0]:
                continue
            err = abs(float(t.y[q0, j]) - r["y_box"])
            if best is None or err < best[0]:
                best = (err, j, k0, q0)
        if best is None or not 0 <= r["k_node"] < g.K:
            return {"ok": False}
        err, j, k0, q0 = best
        # SG7 stage maps: the rows along the nominal timing's observations (antic 49, Slam 0 5 frames: the trial's kp
        # is on that clock); plain maps: the frame
        if getattr(g, "NR", 0):
            vn = next(i for i, v in enumerate(g.variants)
                      if v.frames["Slam Antic"] == 49 and v.frames["Slam 0"] == 5 and v.frames["Slam 2"] == 6)
            rowk = lambda k_: int(g.RM[vn, k_])
            Dk = lambda k_: g.DR[rowk(k_)]
        else:
            rowk = lambda k_: k_
            Dk = lambda k_: g.D[k_]
        xi = int(np.rint((r["x_node"] - g.cfg.x_lo) / g.step))
        if not 0 <= xi < g.NX:
            return {"ok": False}
        s = t.s0 + j
        sv = float(pm.SV[rowk(r["k_node"]), s, xi, r["d_post"] + 1])
        node = float(pm.S[rowk(r["k_node"]), s, xi])
        # the approach: the jump's frames 0..j along the pre key, back from the press node
        st = g.steps(pm.p)
        x = r["x_node"]
        safe = True
        for jj in range(j, -1, -1):
            k = k0 + jj
            if k < 0:
                break
            xk = int(np.rint((x - g.cfg.x_lo) / g.step))
            if 0 <= xk < g.NX and Dk(k)[g.TYB[ti, q0, jj], xk]:
                safe = False
            if jj >= 1:
                x -= r["d_pre"] * g.step * st[k]
        x0 = x
        x0i = int(np.rint((x0 - g.cfg.x_lo) / g.step))
        jump_v = float(pm.S[rowk(k0), t.s0, x0i]) if 0 <= k0 < g.K and 0 <= x0i < g.NX else np.nan
        ground_v = float(pm.S[rowk(k0), 0, x0i]) if 0 <= k0 < g.K and 0 <= x0i < g.NX else np.nan
        return {"ok": True, "j": j, "y_err": round(err, 3), "sv": sv, "node": node, "approach_safe": safe,
                "jump_v": jump_v, "ground_v": ground_v, "x0": round(x0, 3), "k0": k0}


def prf(pred: np.ndarray, real: np.ndarray) -> dict:
    tp = int((pred & real).sum())
    fp = int((pred & ~real).sum())
    fn = int((~pred & real).sum())
    tn = int((~pred & ~real).sum())
    return {"n": int(len(pred)), "pred": int(pred.sum()), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(tp / max(tp + fp, 1), 3), "recall": round(tp / max(tp + fn, 1), 3)}


def attribute(t: dict) -> str:
    tg = t["target"]
    if tg.get("jpost"):
        return "path: jump pressed after the press (umbrella / hang: not the map's path)"
    if t.get("press_shift") not in (0, None) or t.get("late") or t.get("gaps"):
        return f"execution: press shift {t.get('press_shift')} late {t.get('late')} gaps {t.get('gaps')}"
    th = t.get("theory") or {}
    if th.get("pred_loss") is not None or not th.get("pred_bounce", True):
        return "logged path: T1's theory on the logged inputs also predicts the loss / no bounce"
    return "model error: the theory on the logged path predicts success"


def check_trials(geo: sm.Geometry, maps: list[sm.PhaseMap], trials: list[dict]) -> dict:
    tc = TrialCheck(geo)
    rows = []
    for i, t in enumerate(trials):
        r = tc.prep(i, t)
        if r is None:
            continue
        ph = [tc.phase(pm, r) for pm in maps]
        if not all(v["ok"] for v in ph):
            continue
        cert = [np.isfinite(v["sv"]) and v["approach_safe"] for v in ph]
        rows.append({"i": i, "batch": t["batch"], "group": t["target"].get("group"), "note": t["target"].get("note"),
                     "success": bool(t["success"]), "bounce": bool(t.get("bounce")), "loss_src": t.get("loss_src"),
                     "kp": r["kp"], "x_press": round(r["x_press"], 3), "side": r["side"], "h": r["h"],
                     "d_post": r["d_post"], "jpost": t["target"].get("jpost"),
                     "cert_all": bool(all(cert)), "cert_any": bool(any(cert)),
                     "press_any": bool(any(np.isfinite(v["sv"]) for v in ph)),
                     "approach_all": bool(all(v["approach_safe"] for v in ph)),
                     "node_min": float(min(v["node"] for v in ph)), "jump_min": float(min(v["jump_v"] for v in ph)),
                     "ground_min": float(min(v["ground_v"] for v in ph)),
                     "y_err": max(v["y_err"] for v in ph), "attr": attribute(t)})
    succ = np.array([r["success"] for r in rows])
    out = {"n": len(rows), "success_rate": round(float(succ.mean()), 3) if len(rows) else None}
    for nm, key in (("certified_all_phases", "cert_all"), ("certified_any_phase", "cert_any"),
                    ("press_certified_any_phase", "press_any")):
        out[nm] = prf(np.array([r[key] for r in rows]), succ)
    for thr in (0.0, 1.0, 1.5):
        out[f"jump_value_ge_{thr:g}"] = prf(np.array([r["jump_min"] >= thr for r in rows]), succ)
        out[f"node_value_ge_{thr:g}"] = prf(np.array([r["node_min"] >= thr for r in rows]), succ)
    person = [r for r in rows if str(r["group"]).startswith("P")]
    if person:
        ps = np.array([r["success"] for r in person])
        out["person_points"] = {"n": len(person), "success_rate": round(float(ps.mean()), 3),
                                "certified_all_phases": prf(np.array([r["cert_all"] for r in person]), ps)}
    no_jpost = [r for r in rows if not r["jpost"]]
    if no_jpost:
        s2 = np.array([r["success"] for r in no_jpost])
        out["no_jump_after_press"] = {"n": len(no_jpost), "success_rate": round(float(s2.mean()), 3),
                                      "certified_all_phases": prf(np.array([r["cert_all"] for r in no_jpost]), s2)}
    fails = [r for r in rows if r["cert_all"] and not r["success"]]
    att = {}
    for r in fails:
        att[r["attr"].split(":")[0]] = att.get(r["attr"].split(":")[0], 0) + 1
    out["certified_failures"] = {"n": len(fails), "by_cause": att, "rows": fails}
    out["y_err_p90"] = round(float(np.quantile([r["y_err"] for r in rows], 0.9)), 3) if rows else None
    # success by the map's verdict, per press-frame band (the person's window and the rest)
    bands = {"k<42": lambda k: k < 42, "k42-47": lambda k: 42 <= k <= 47, "k48-55": lambda k: 48 <= k <= 55,
             "k>=56": lambda k: k >= 56}
    out["by_band"] = {}
    for nm, f in bands.items():
        rr = [r for r in rows if f(r["kp"])]
        if rr:
            c = [r for r in rr if r["cert_all"]]
            nc = [r for r in rr if not r["cert_all"]]
            out["by_band"][nm] = {"n": len(rr), "cert": len(c),
                                  "cert_success": round(np.mean([r["success"] for r in c]), 3) if c else None,
                                  "uncert_success": round(np.mean([r["success"] for r in nc]), 3) if nc else None}
    out["rows"] = rows
    return out


# ---- (b) the 2026-10-12 live slam hits ----
def live_hits() -> list[dict]:
    seen, out = set(), []
    for f in LIVE:
        if not f.exists():
            continue
        for arm, v in json.loads(f.read_text("utf-8")).items():
            for r in v.get("hit_rows", []):
                if r.get("family") != "CC_SLAM":
                    continue
                key = (r["run"], r["ep"], r["f_a"])
                if key in seen:
                    continue
                seen.add(key)
                out.append({"arm": arm, "run": r["run"], "ep": r["ep"], "f_a": r["f_a"], "src": r["src"],
                            "state": r["state"], "t": r.get("t")})
    return out


def rec_dirs(run: str) -> list[Path]:
    base = RUNS / run / "rec"
    return sorted(p for p in base.glob("*/*/*") if p.is_dir()) if base.exists() else []


class LiveCheck:
    def __init__(self, geo: sm.Geometry, maps: list[sm.PhaseMap]):
        self.g, self.maps = geo, maps

    def locate(self, k: int, ys: list, x: float, tol: float = 0.06) -> dict:
        """The best map score of the airborne macro states at frame k whose heights match this frame and the
        HIST - 1 frames before (ys: newest first; every phase); none: the vertical is off the map (umbrella, air hang,
        recoil, wall)."""
        g = self.g
        xi = int(np.rint((x - g.cfg.x_lo) / g.step))
        if not (0 <= k < g.K and 0 <= xi < g.NX):
            return {"match": 0, "score": None}
        best, n, kinds = -np.inf, 0, set()
        J = g.SJ
        for pm in self.maps:
            q = (pm.p - k + J) % 6
            ok = (J >= len(ys) - 1) & (J < g.TL[g.ST, q]) & (g.kind[g.ST] != "ground")
            for i, yy in enumerate(ys):
                ok &= np.abs(g.TY[g.ST, q, np.maximum(J - i, 0)] - yy) <= tol
            idx = np.flatnonzero(ok)
            if len(idx):
                n += len(idx)
                sc = pm.S[k, idx, xi].astype(float)
                best = max(best, float(sc.max()))
                kinds |= {f"{g.tubes[g.ST[s]].kind}:{g.tubes[g.ST[s]].param:g}" for s in idx[np.argsort(-sc)[:3]]}
        return {"match": n, "score": best if n else None, "kinds": sorted(kinds)[:4]}

    def ground_options(self, k: int, x: float) -> dict:
        """What the lookahead would choose at a ground node: stand / left / right two frames ahead, or the best jump."""
        g = self.g
        out = {}
        for nm, d in (("left", -1), ("stand", 0), ("right", 1)):
            v = []
            for pm in self.maps:
                xi = int(np.rint((x + d * 2 * g.step - g.cfg.x_lo) / g.step))
                v.append(float(pm.S[min(k + 2, g.K - 1), 0, xi]) if 0 <= xi < g.NX else -np.inf)
            out[nm] = min(v)
        jb, jv = None, -np.inf
        for t in g.tubes:
            if t.kind != "jump":
                continue
            v = []
            for pm in self.maps:
                xi = int(np.rint((x - g.cfg.x_lo) / g.step))
                v.append(float(pm.S[min(k + 2, g.K - 1), t.s0 + 2, xi]) if 0 <= xi < g.NX else -np.inf)
            if min(v) > jv:
                jb, jv = t.param, min(v)
        out["jump"] = jv
        out["jump_h"] = jb
        return out

    def slam(self, sl: dict, hit: dict) -> dict:
        g = self.g
        # the map's frame clock is game time (1/60 s): a slowed run (x0.5) logs each game frame twice
        byk: dict = {}
        hp_lost = None
        for f in sl["frames"]:
            kk = int(round(float(f.get("t") or 0.0) * 60))
            byk[kk] = f
            if hp_lost is None and f.get("hpl"):
                hp_lost = kk
        fr = [byk.get(kk, byk[max(k_ for k_ in byk if k_ <= kk)]) for kk in range(max(byk) + 1)]
        if hp_lost is not None:
            fr[hp_lost] = dict(fr[hp_lost], hpl=fr[hp_lost].get("hpl") or ["hit"])
        cx0 = fr[0]["pos"][0]
        facing = 1 if fr[0]["flip"] else -1
        hx0 = 0.5 * (fr[0]["hbox"][0] + fr[0]["hbox"][2]) if fr[0].get("hbox") else fr[0]["hero"][0]
        rows = []
        k_hit = None
        for k, f in enumerate(fr):
            hb = f.get("hbox")
            if not hb:
                continue
            x = (0.5 * (hb[0] + hb[2]) - cx0) * facing
            y = hb[1] - g.floor
            ys = [(fr[k - i]["hbox"][1] - g.floor) for i in range(HIST) if k - i >= 0 and fr[k - i].get("hbox")]
            yprev = ys[1] if len(ys) > 1 else y
            ground = abs(y) < 0.03 and abs(y - yprev) < 0.01
            umbrella = "Umbrella" in str(f.get("clip_h") or "") or "Float" in str(f.get("clip_h") or "")
            if ground:
                xi = int(np.rint((x - g.cfg.x_lo) / g.step))
                sc = min(float(pm.S[k, 0, xi]) for pm in self.maps) if 0 <= k < g.K and 0 <= xi < g.NX else None
                loc = {"match": 1, "score": sc, "kinds": ["ground"]}
            elif umbrella or len(ys) < HIST:
                loc = {"match": 0, "score": None, "kinds": ["umbrella" if umbrella else "short history"]}
            else:
                loc = self.locate(k, ys, x)
            rows.append({"k": k, "f": f["f"], "x": round(x, 2), "y": round(y, 2), "ground": ground, **loc,
                         "inv": f.get("inv"), "dmg": f.get("dmg")})
            if k_hit is None and f.get("hpl"):
                k_hit = k
        k_hit = k_hit if k_hit is not None else len(rows) - 1
        pre = [r for r in rows if r["k"] <= k_hit]
        # the commit: the last takeoff (ground -> air) before the hit
        k_to = None
        for a, b in zip(pre[:-1], pre[1:]):
            if a["ground"] and not b["ground"]:
                k_to = a["k"]
        out = {"hit": hit, "facing": facing, "facing_check": int(np.sign((hx0 - cx0) * facing)), "k_hit": k_hit,
               "state_at_hit": fr[k_hit]["st"] if k_hit < len(fr) else None, "k0_state": pre[0] if pre else None,
               "takeoff_k": k_to}
        if k_to is not None:
            a = next(r for r in pre if r["k"] == k_to)
            out["takeoff"] = a
            out["after_takeoff"] = [r for r in pre if k_to < r["k"] <= k_to + 4]
            out["map_would"] = self.ground_options(k_to, a["x"])
        air_scores = [r["score"] for r in pre if not r["ground"] and r["match"]]
        out["airborne_frames"] = sum(1 for r in pre if not r["ground"])
        out["off_map_frames"] = sum(1 for r in pre if not r["ground"] and not r["match"])
        out["infeasible_frames"] = sum(1 for r in pre if r["score"] is not None and not np.isfinite(r["score"]))
        out["first_infeasible_k"] = next((r["k"] for r in pre if r["score"] is not None and not np.isfinite(r["score"])),
                                         None)
        out["air_score_max"] = max(air_scores) if air_scores else None
        fi = out["first_infeasible_k"]
        if fi is not None:
            last = [r for r in pre if r["k"] < fi and r["score"] is not None and np.isfinite(r["score"])]
            if last:
                out["last_feasible"] = last[-1]
                if last[-1]["ground"]:
                    out["map_would_last_feasible"] = self.ground_options(last[-1]["k"], last[-1]["x"])
        out["lead_frames"] = (k_hit - fi) if fi is not None else None
        out["frames"] = [r for r in pre if r["k"] % 3 == 0 or r["k"] >= k_hit - 6]
        return out


def check_live(geo: sm.Geometry, maps: list[sm.PhaseMap]) -> dict:
    from ssbot.tools.pogo_theory import scan
    lc = LiveCheck(geo, maps)
    hits = live_hits()
    by_run: dict = {}
    for h in hits:
        by_run.setdefault(h["run"], []).append(h)
    out = []
    for run, hs in by_run.items():
        slams = []
        for d in rec_dirs(run):
            try:
                slams += scan(d)
            except Exception as ex:  # noqa: BLE001
                out.append({"run": run, "error": repr(ex)})
        for h in hs:
            sl = next((s for s in slams if abs(s["f0"] - h["f_a"]) <= 3), None)
            if sl is None:
                out.append({"hit": h, "error": "slam not found in the recording"})
                continue
            out.append(lc.slam(sl, h))
    for run in EXTRA_RUNS:
        for d in rec_dirs(run):
            try:
                sls = scan(d)
            except Exception as ex:  # noqa: BLE001
                out.append({"run": run, "error": repr(ex)})
                continue
            for sl in sls:
                lost = [f for f in sl["frames"] if f.get("hpl")]
                if lost:
                    h = {"arm": "demo", "run": run, "ep": None, "f_a": sl["f0"], "src": str(lost[0]["hpl"][0]),
                         "state": lost[0]["st"], "t": None}
                    out.append(lc.slam(sl, h))
                    hits.append(h)
    ok = [r for r in out if "error" not in r]
    summ = {"hits": len(hits), "located": len(ok),
            "takeoff_found": sum(1 for r in ok if r.get("takeoff_k") is not None),
            "infeasible_before_hit": sum(1 for r in ok if r["first_infeasible_k"] is not None),
            "off_map_airborne": sum(1 for r in ok if r["off_map_frames"] > 0),
            "airborne_at_k0": sum(1 for r in ok if r.get("k0_state") and not r["k0_state"]["ground"]),
            "k0_feasible": sum(1 for r in ok if r.get("k0_state") and r["k0_state"].get("score") is not None
                               and np.isfinite(r["k0_state"]["score"])),
            "k0_off_map": sum(1 for r in ok if r.get("k0_state") and r["k0_state"].get("score") is None),
            "lead_frames_median": float(np.median([r["lead_frames"] for r in ok if r.get("lead_frames") is not None]))
            if any(r.get("lead_frames") is not None for r in ok) else None,
            "first_infeasible_on_ground": sum(1 for r in ok if r.get("last_feasible") is not None
                                              and r["last_feasible"]["ground"]),
            "takeoff_after_infeasible_or_into": 0}
    for r in ok:
        if r.get("takeoff_k") is not None:
            aft = r.get("after_takeoff") or []
            sc = [a["score"] for a in aft if a.get("score") is not None]
            r["committed_into_infeasible"] = bool(sc) and not np.isfinite(min(sc))
            mw = r.get("map_would") or {}
            alt = max((mw.get(k, -np.inf) for k in ("left", "stand", "right")), default=-np.inf)
            r["map_ground_alternative"] = alt
        summ["takeoff_after_infeasible_or_into"] += int(bool(r.get("committed_into_infeasible")))
    return {"summary": summ, "rows": out}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--skip-live", action="store_true")
    ap.add_argument("--skip-trials", action="store_true")
    ap.add_argument("--config", default="", help="MapConfig overrides as JSON (the sensitivity runs)")
    ap.add_argument("--tag", default="")
    a = ap.parse_args(argv)
    t0 = time.time()
    cfg = sm.MapConfig(**json.loads(a.config)) if a.config else sm.MapConfig()
    geo = setup(cfg)
    b = sm.MapBuilder(geo)
    maps = [b.build(p, keep_full=True) for p in range(6)]
    res = {"seconds_build": round(time.time() - t0, 1), "config": cfg.key()}
    if not a.skip_trials:
        res["trials"] = check_trials(geo, maps, load_trials())
    if not a.skip_live:
        res["live"] = check_live(geo, maps)
    res["seconds"] = round(time.time() - t0, 1)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"check{('_' + a.tag) if a.tag else ''}.json").write_text(json.dumps(res, indent=1, default=float), "utf-8")
    tr = res.get("trials", {})
    print(json.dumps({k: tr[k] for k in tr if k not in ("rows", "certified_failures")}, indent=1, default=float))
    if tr:
        print(json.dumps({k: v for k, v in tr["certified_failures"].items() if k != "rows"}, default=float))
    if "live" in res:
        print(json.dumps(res["live"]["summary"], indent=1, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
