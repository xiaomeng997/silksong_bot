"""Fit the Forum loadout's measured parameters (ssbot.knowledge.kinematics HeroParams "*_t" of the animation-timed FSM
states) from excitation recordings (probes/kin_excite_forum), report what the logs say about the decompiled rules,
and write knowledge/1.0.30000/kinematics/hero_reaper_forum.json.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.kin_fit_forum <recording> [...] [--out <json>] [--dry-run]

Phase lengths: for every run of a mode (classify_modes with the Forum loadout) the frames each phase clip shows
(GLIDE_CLIPS, RPR_CLIPS, SPRINT_CLIPS) from the phase's first frame to the frame before the next phase's: an FSM state
that ends when its clip completes shows for L frames when its threshold t (scaled s, counted from the frame after
entry, as the model counts) lies in ((L - 1) dt, L dt]; the fit takes t = (L - 0.5) / 60 at the median L of runs that
ended in the next phase (not cut short by a landing, a hit or a cancel), and reports the spread. Checks (decomp
values, not fitted): vy while clinging, the wall slide's per-frame vy change after the stick time, the wall jump's
first x speeds, the dash's x speed, the glide's settled vy.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.knowledge import kinematics as km

PHASE_PARAMS = {
    km.M_GLIDE: {0: "glide_antic_t", 1: "glide_inflate_t", 3: "glide_deflate_t"},
    km.M_RPR_DS: {0: "rpr_antic_t", 1: "rpr_slash_t"},
    km.M_SPRINT: {0: "air_sprint_time"},
}


def phase_runs(tr: km.Trace, modes: np.ndarray) -> dict:
    """(mode, phase) -> list of (frames, next phase or None, clip sequence) per run."""
    clip = np.array(tr.clips, dtype=object)[tr.clip]
    out = defaultdict(list)
    i, n = 0, len(tr)
    while i < n:
        m = int(modes[i])
        if m not in PHASE_PARAMS:
            i += 1
            continue
        j = i
        while j < n and modes[j] == m:
            j += 1
        tab = {km.M_GLIDE: km.GLIDE_CLIPS, km.M_RPR_DS: km.RPR_CLIPS, km.M_SPRINT: km.SPRINT_CLIPS}[m]
        ph = [tab.get(c, -1) for c in clip[i:j]]
        k = 0
        while k < len(ph):
            p = ph[k]
            q = k
            while q < len(ph) and ph[q] == p:
                q += 1
            nxt = ph[q] if q < len(ph) else None
            out[(m, p)].append((q - k, nxt, tuple(dict.fromkeys(clip[i + k:i + q]))))
            k = q
        i = j
    return out


def fit(paths: list[str], params: km.HeroParams) -> tuple[dict, dict]:
    from ssbot.tools.kin_check import load_source
    fitted: dict = {}
    report: dict = {"phases": {}, "checks": {}, "clips_seen": Counter()}
    vy_cling, dvy_slide, wj_vx, dash_vx, glide_vy = [], [], [], [], []
    for path in paths:
        tr, terrains = load_source(path, params)
        modes = km.classify_modes(tr, forum=True)
        for c in np.array(tr.clips, dtype=object)[tr.clip][modes >= km.M_GLIDE]:
            report["clips_seen"][str(c)] += 1
        for (m, p), runs in phase_runs(tr, modes).items():
            key = f"{km.MODE_NAMES[m]}/{p}"
            r = report["phases"].setdefault(key, {"lengths": Counter(), "next": Counter(), "clips": Counter()})
            for L, nxt, clips in runs:
                r["next"][str(nxt)] += 1
                r["clips"][" > ".join(map(str, clips))] += 1
                if nxt is not None and nxt != p:
                    r["lengths"][L] += 1
        cling = tr.flag("wallClinging")
        slide = tr.flag("wallSliding") & ~cling
        vy = tr.vel[:, 1]
        vy_cling += vy[cling & np.r_[False, cling[:-1]]].tolist()
        # sliding frames after the stick time: vy changes by WALLSLIDE_ACCEL * dt per frame (+ any gravity)
        run = km._since(km._onset(slide), np.ones(len(tr)), include_onset=True)
        sel = slide & np.r_[False, slide[:-1]] & (run > 12)
        dvy_slide += ((vy[1:] - vy[:-1])[sel[1:]] / np.maximum(tr.dt[1:][sel[1:]], 1e-6)).tolist()
        jon = km._onset(tr.flag("jumping")) & np.r_[False, tr.flag("wallSliding")[:-1]]
        for i in np.flatnonzero(jon):
            wj_vx.append(np.abs(tr.vel[i:i + 12, 0]).round(2).tolist())
        dash_vx += np.abs(tr.vel[tr.flag("dashing"), 0]).tolist()
        glide_vy += vy[(modes == km.M_GLIDE) & (np.array(tr.clips, dtype=object)[tr.clip] == "Umbrella Float")].tolist()
    for key, r in report["phases"].items():
        m_name, p = key.split("/")
        m = km.MODE_NAMES.index(m_name)
        name = PHASE_PARAMS.get(m, {}).get(int(p))
        if name and r["lengths"]:
            Ls = np.repeat(list(r["lengths"].keys()), list(r["lengths"].values()))
            L = float(np.median(Ls))
            fitted[name] = round((L - 0.5) / 60.0, 5)
            r["fit"] = {name: fitted[name], "median_frames": L, "n": int(len(Ls))}
        r["lengths"] = dict(sorted(r["lengths"].items()))
        r["next"] = dict(r["next"])
        r["clips"] = dict(r["clips"].most_common(6))
    q = lambda a: ({"n": len(a), "p5": round(float(np.percentile(a, 5)), 3),  # noqa: E731
                    "p50": round(float(np.percentile(a, 50)), 3), "p95": round(float(np.percentile(a, 95)), 3)}
                   if len(a) else {"n": 0})
    report["checks"] = {"vy_while_clinging": q(vy_cling), "slide_dvy_per_s_after_stick": q(dvy_slide),
                        "wall_jump_abs_vx_first_frames": wj_vx[:8], "dash_abs_vx": q(dash_vx),
                        "glide_float_vy": q(glide_vy)}
    report["clips_seen"] = dict(report["clips_seen"].most_common(40))
    return fitted, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--out", type=Path, default=km.DEFAULT_PARAMS.parent / "hero_reaper_forum.json")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    from ssbot.probes.kin_excite_forum import forum_params
    p = forum_params()
    fitted, report = fit(a.sources, p)
    print(json.dumps(report, indent=1, default=str))
    print("fitted:", fitted)
    if not a.dry_run:
        d = p.to_json()
        d.update(fitted)
        d["source"] = dict(d.get("source") or {})
        for k in fitted:
            d["source"][k] = f"kin_fit_forum (median logged phase length) on {', '.join(map(str, a.sources))}"
        d["fit"] = dict(d.get("fit") or {})
        d["fit"]["forum"] = {"sources": [str(s) for s in a.sources], "fitted": fitted,
                             "checks": report["checks"]}
        out = km.HeroParams.from_json(d)
        print("wrote", out.save(a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
