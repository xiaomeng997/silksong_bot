"""The Tiny's dive from the Maestro's antic (the person 2026-10-10: "the bugs' dash path shows only once the dash has
started; if the Maestro directs them during its antic, the path should be known half a second earlier"). Measures the
chain Maestro Fire Antic -> Tiny Fire Ready -> Fire (dive) -> Brake / Pull Up / Wall Bonk -> Return on the Forum
caches and checks the simulator of ssbot.combat.are_types.tiny (simulate / dive_paths) against it:

  what is decided when: which Tiny (the FIRE READY frame), the Slash Point side (the hero's side of the Maestro at the
  antic entry), the FIRE time, the FIRE point (where the Tiny's flight to the Slash Point has got by then), the dive
  side (the hero's side of the Tiny at FIRE) and the slide's end (5 u past the hero);
  the residual of the predicted FIRE point and of the predicted path against the real one, per time since the antic
  entry the prediction was made at.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.tiny_early chain --set dev|fresh|r2|person [--out DIR]
    ../scripts/uv.cmd run python -m ssbot.tools.tiny_early png [--n 8]          # strips: antic -> dive -> return

Outputs under C:/ssbot/data/m2_forum_are/tiny_early (chain_<set>.json, png/).
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from ssbot.combat.are_types import tiny as TY

OUT = Path(r"C:\ssbot\data\m2_forum_are\tiny_early")
MA, TI = TY.MAESTRO, "Song Automaton Tiny"
AS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7)        # s since the antic entry the prediction is made at
US = (0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4, 1.6)        # s since the antic entry the path is compared at


def _tracks(c: dict, tk: str) -> dict:
    types = list(c["types"])
    if tk not in types:
        return {}
    sel = np.nonzero(c["e_tk"] == types.index(tk))[0]
    out = {}
    for iid in np.unique(c["e_iid"][sel]):
        r = sel[c["e_iid"][sel] == iid]
        r = r[np.argsort(c["e_fi"][r], kind="stable")]
        fi = c["e_fi"][r]
        keep = np.r_[True, np.diff(fi) > 0]          # one row per frame
        r, fi = r[keep], fi[keep]
        out[int(iid)] = dict(
            fi=fi, T=np.asarray(c["T"][fi], np.float64),
            st=[str(c["states"][s]) if s >= 0 else None for s in c["e_st"][r]],
            tin=c["e_tin"][r].astype(float), x=c["e_x"][r].astype(float), y=c["e_y"][r].astype(float),
            vx=c["e_vx"][r].astype(float), vy=c["e_vy"][r].astype(float), box=c["e_box"][r].astype(float),
            hx=c["hx"][fi].astype(float), hy=c["hy"][fi].astype(float), hbox=c["hbox"][fi].astype(float))
    return out


def _starts(tr: dict, name: str) -> list:
    st = tr["st"]
    return [j for j in range(len(st)) if st[j] == name and (j == 0 or st[j - 1] != name)]


def _hits(c: dict) -> dict:
    fidx = {int(f): i for i, f in enumerate(c["f"])}
    out: dict = {}
    for ev in c["events"]:
        if ev[1] == "hit":
            i = fidx.get(int(ev[0]))
            if i is not None:
                out.setdefault(int(ev[2].get("ent", -1)), []).append(float(c["T"][i]))
    return out


def events(c: dict) -> list[dict]:
    """Every Fire Ready -> Fire of one fight with its Maestro (the one whose Fire Antic started that frame)."""
    ma, ti = _tracks(c, MA), _tracks(c, TI)
    hits = _hits(c)
    antics = []
    for mid, m in ma.items():
        for q in _starts(m, "Fire Antic"):
            antics.append((float(m["T"][q] - m["tin"][q]), mid, q))
    out = []
    for iid, t in ti.items():
        for j0 in _starts(t, "Fire Ready"):
            jf = next((q for q in range(j0, len(t["st"])) if t["st"][q] != "Fire Ready"), None)
            if jf is None or t["st"][jf] != "Fire" or t["fi"][jf] - t["fi"][jf - 1] > 3:
                continue
            t0 = float(t["T"][j0] - t["tin"][j0])
            cand = [(abs(ta - t0), mid, q) for ta, mid, q in antics if abs(ta - t0) < 0.05]
            if not cand:
                out.append(dict(iid=iid, t0=t0, maestro=None))
                continue
            d, mid, q0 = min(cand, key=lambda z: (z[0], (ma[z[1]]["x"][z[2]] - t["x"][j0]) ** 2))
            m = ma[mid]
            # the end of the chain: back in Ready / Returned / Defend / Leave or the track ends
            je = next((q for q in range(jf, len(t["st"]))
                       if t["st"][q] not in ("Fire", "Brake", "Pull Up", "Wall Bonk", "Return")), len(t["st"]))
            tF = float(t["T"][jf] - t["tin"][jf])
            out.append(dict(iid=iid, mid=mid, t0=t0, dt0=d, tF=tF, j0=j0, jf=jf, je=je, q0=q0, t=t, m=m,
                            hit=any(t0 - 0.05 <= h <= t0 + 2.5 for h in hits.get(mid, []) + hits.get(iid, []))))
    return out


def _m_at(m: dict, T: float) -> tuple | None:
    q = int(np.searchsorted(m["T"], T + 1e-6)) - 1
    if q < 0 or abs(m["T"][q] - T) > 0.04:
        return None
    return float(m["x"][q]), float(m["y"][q]), float(m["vx"][q]), float(m["vy"][q])


def _contact(t: dict, j: int) -> bool:
    b, h = t["box"][j], t["hbox"][j]
    return bool(np.all(np.isfinite(b)) and np.all(np.isfinite(h)) and b[0] < h[2] and h[0] < b[2] and b[1] < h[3]
                and h[1] < b[3])


def analyse(ev: dict) -> dict | None:
    """The measurements of one event (None: no Maestro)."""
    if ev.get("maestro", True) is None:
        return None
    t, m = ev["t"], ev["m"]
    j0, jf, je, t0, tF = ev["j0"], ev["jf"], ev["je"], ev["t0"], ev["tF"]
    m0 = _m_at(m, float(t["T"][j0]))
    if m0 is None:
        return None
    sm = 1 if t["hx"][j0] >= m0[0] else -1
    # the FIRE point: the first Fire frame (the dive's velocity is set there, its first move is the next step)
    jl = jf - 1
    xF, yF = float(t["x"][jf]), float(t["y"][jf])
    side = 1 if t["vx"][jf] > 0 else -1
    r = dict(t0=t0, tF_t0=tF - t0, side=side, sm=sm, hit=ev["hit"], xF=xF, yF=yF,
             side_hero_F=int(1 if t["hx"][jf] >= t["x"][jl] else -1), side_hero_0=int(1 if t["hx"][j0] >= t["x"][j0]
                                                                                     else -1),
             mrel=[xF - m["x"][min(int(np.searchsorted(m["T"], tF)), len(m["T"]) - 1)] * 1.0,
                   yF - m["y"][min(int(np.searchsorted(m["T"], tF)), len(m["T"]) - 1)]])
    # how the chain ends (the states after Fire), Brake entry y, Fire duration
    sts = [t["st"][q] for q in range(jf, je)]
    r["states"] = list(dict.fromkeys(sts))
    jw = next((q for q in range(jf, je) if t["st"][q] == "Wall Bonk"), None)
    r["bonk_x"] = None if jw is None else float(t["x"][jw])
    jb = next((q for q in range(jf, je) if t["st"][q] == "Brake"), None)
    r["brake_y"] = None if jb is None else float(t["y"][jb])
    jp = next((q for q in range(jf, je) if t["st"][q] in ("Pull Up", "Wall Bonk")), None)
    r["fire_brake_s"] = None if jp is None else float(t["T"][jp] - t["tin"][jp] - tF)
    if jp is not None and t["st"][jp] == "Pull Up":
        r["pull_dx_hero"] = float(side * (t["x"][jp] - t["hx"][jp]))       # >= 5: passed the hero
    # first contact with the hero's box after FIRE (the dive's first damage) and during the antic
    jc = next((q for q in range(jf, je) if _contact(t, q)), None)
    r["contact_s"] = None if jc is None else float(t["T"][jc] - t0)
    r["contact_antic"] = any(_contact(t, q) for q in range(j0, jf))
    # predictions made at a s after the antic entry
    real = [(float(t["T"][q]), float(t["x"][q]), float(t["y"][q]), t["st"][q]) for q in range(j0, je)]
    pred = {}
    for a in AS:
        if a >= tF - t0 - 1e-6:
            break
        ja = int(np.searchsorted(t["T"], t0 + a - 1e-6))
        ja = min(max(ja, j0), jf - 1)
        ma = _m_at(m, float(t["T"][ja]))
        if ma is None:
            continue
        T = float(t["T"][ja])
        hx = float(t["hx"][ja])
        t_fire = max(t0 + TY.ANTIC_T - T, 0.0)
        rows = TY.simulate("ready", float(t["x"][ja]), float(t["y"][ja]), float(t["vx"][ja]), float(t["vy"][ja]), 0.0,
                           ma, sm, hx, t_fire=t_fire)
        k = next((i for i, z in enumerate(rows) if z[3] != "ready"), None)
        if k is None:
            continue
        px, py = rows[k][1], rows[k][2]
        side_p = 1 if hx >= px else -1
        # the same chain with the real side and the hero's real x at FIRE / while sliding (the hero-free part)
        rows_s = TY.simulate("ready", float(t["x"][ja]), float(t["y"][ja]), float(t["vx"][ja]), float(t["vy"][ja]),
                             0.0, ma, sm, float(t["hx"][min(jf + 15, je - 1)]), t_fire=t_fire, side=side)
        err, err_s = {}, {}
        for u in US:
            TT = t0 + u
            if TT > real[-1][0]:
                break
            q = int(np.searchsorted([z[0] for z in real], TT - 1e-6))
            q = min(q, len(real) - 1)
            if abs(real[q][0] - TT) > 0.04:
                continue
            x1, y1 = TY.at(rows, TT - T)
            x2, y2 = TY.at(rows_s, TT - T)
            err[u] = math.hypot(x1 - real[q][1], y1 - real[q][2])
            err_s[u] = math.hypot(x2 - real[q][1], y2 - real[q][2])
        reach = TY.HERO_REACH * t_fire
        pred[a] = dict(fire_err=math.hypot(px - xF, py - yF), fire_dx=px - xF, fire_dy=py - yF,
                       now_err=math.hypot(float(t["x"][ja]) - xF, float(t["y"][ja]) - yF),
                       side_ok=side_p == side, both=abs(hx - px) <= reach, hero_gap=abs(hx - px),
                       hero_dx_to_F=float(t["hx"][jf] - hx), path_err=err, path_err_side=err_s)
    r["pred"] = pred
    return r


def _q(v, ps=(50, 90, 95, 99, 100)) -> dict | None:
    v = [x for x in v if x is not None and np.isfinite(x)]
    if not v:
        return None
    return {f"p{p}" if p < 100 else "max": round(float(np.percentile(v, p)), 3) for p in ps} | {"n": len(v)}


def summary(rs: list[dict]) -> dict:
    rs = [r for r in rs if r is not None]
    clean = [r for r in rs if not r["hit"]]
    out = dict(events=len(rs), not_hit=len(clean),
               tF_t0=_q([r["tF_t0"] for r in rs]),
               side_hero_F=round(float(np.mean([r["side_hero_F"] == r["side"] for r in rs])), 4),
               side_hero_0=round(float(np.mean([r["side_hero_0"] == r["side"] for r in rs])), 4),
               slash_rel_x=_q([r["mrel"][0] * -r["sm"] for r in clean]), slash_rel_y=_q([r["mrel"][1] for r in clean]),
               brake_y=_q([r["brake_y"] for r in rs]),
               bonk_x_left=_q([r["bonk_x"] for r in rs if r["bonk_x"] is not None and r["bonk_x"] < 31.5]),
               bonk_x_right=_q([r["bonk_x"] for r in rs if r["bonk_x"] is not None and r["bonk_x"] >= 31.5]), fire_brake_s=_q([r["fire_brake_s"] for r in rs]),
               pull_dx_hero=_q([r.get("pull_dx_hero") for r in rs]),
               contact_s=_q([r["contact_s"] for r in rs]),
               contact_share=round(float(np.mean([r["contact_s"] is not None for r in rs])), 4),
               contact_antic=round(float(np.mean([r["contact_antic"] for r in rs])), 4),
               ends={})
    for r in rs:
        k = ">".join(r["states"])
        out["ends"][k] = out["ends"].get(k, 0) + 1
    out["ends"] = dict(sorted(out["ends"].items(), key=lambda z: -z[1])[:8])
    per = {}
    for a in AS:
        ps = [r["pred"][a] for r in clean if a in r["pred"]]
        if not ps:
            continue
        per[a] = dict(n=len(ps), fire_err=_q([p["fire_err"] for p in ps]), now_err=_q([p["now_err"] for p in ps]),
                      side_ok=round(float(np.mean([p["side_ok"] for p in ps])), 4),
                      both=round(float(np.mean([p["both"] for p in ps])), 4),
                      side_ok_or_both=round(float(np.mean([p["side_ok"] or p["both"] for p in ps])), 4),
                      hero_dx_to_F=_q([abs(p["hero_dx_to_F"]) for p in ps]),
                      path={u: _q([p["path_err"][u] for p in ps if u in p["path_err"]], (50, 90, 99)) for u in US},
                      path_side={u: _q([p["path_err_side"][u] for p in ps if u in p["path_err_side"]], (50, 90, 99))
                                 for u in US})
    out["pred"] = per
    return out


def cmd_chain(a) -> int:
    from ssbot.knowledge.forum_cache import load_cache
    from ssbot.tools.attack_range_build import _cache_files, _idle_priority, person_caches
    _idle_priority()
    if a.antic_t:
        TY.ANTIC_T = a.antic_t
    files = person_caches() if a.set == "person" else _cache_files(a.set)
    files = files[:a.limit] if a.limit else files
    rs = []
    for f in files:
        c = load_cache(f)
        for ev in events(c):
            r = analyse(ev)
            if r is not None:
                r["fight"] = f.stem
                rs.append(r)
    s = summary(rs)
    out = Path(a.out) if a.out else OUT
    out.mkdir(parents=True, exist_ok=True)
    (out / f"chain_{a.set}.json").write_text(json.dumps(s, indent=1, default=str), "utf-8")
    print(json.dumps({k: v for k, v in s.items() if k != "pred"}, default=str))
    for k, v in s["pred"].items():
        print(f"a {k}: n {v['n']} fire_err {v['fire_err']} now {v['now_err']['p50']} side {v['side_ok']} "
              f"both {v['both']} ok|both {v['side_ok_or_both']} herodx p95 {v['hero_dx_to_F']['p95']}")
        print("   path p50/p90 " + " ".join(f"{u}:{(w or {}).get('p50')}/{(w or {}).get('p90')}" for u, w in v["path"].items()))
        print("   side p50/p90 " + " ".join(f"{u}:{(w or {}).get('p50')}/{(w or {}).get('p90')}" for u, w in v["path_side"].items()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("chain")
    c.add_argument("--set", required=True, choices=("dev", "fresh", "r2", "person"))
    c.add_argument("--out", default=None)
    c.add_argument("--limit", type=int, default=0, help="the first N caches only")
    c.add_argument("--antic-t", type=float, default=0.0, help="override tiny.ANTIC_T (calibration)")
    a = ap.parse_args(argv)
    return {"chain": cmd_chain}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
