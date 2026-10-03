"""Fit the Forum loadout's measured parameters (ssbot.knowledge.kinematics HeroParams "*_t" of the animation-timed FSM
states) from excitation recordings (probes/kin_excite_forum), report what the logs say about the decompiled rules,
and write knowledge/1.0.30000/kinematics/hero_reaper_forum.json.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.kin_fit_forum <recording> [...] [--out <json>] [--dry-run]

Phase lengths, in the model's convention: a phase entered in the Update of frame e (its timer counts from the frame
after) ends in the Update of frame e + L when its threshold t lies in ((L - 1) dt, L dt]; over the runs that ended
naturally (not cut short by a landing, a hit, a cancel) a single L gives the middle of that interval, two adjacent
ones (the frame-time jitter deciding) the boundary between them, which the timing lanes then carry both ways
(threshold()).
Where a phase ends is read from the log as follows:
  - a phase followed by another phase's clip (glide antic / inflate, Reaper antic, scramble antic, air sprint): the
    next clip's first frame;
  - the Reaper slash and its fall share "v3 Down Slash": the slash's x0.7 decay stops at its trigger frame (the last
    frame whose physics step decayed |vx|: the first step that keeps |vx| comes after it; both frames must have a
    step); the fall
    ends when control comes back with the downspike recovery (FinishDownspike), Fall 2 taking the frame before;
  - the last phase of a move (glide deflate, scramble end): control back (to the wall slide for the scramble end);
  - Hit Roof Soft (a scramble's roof ray in a FixedUpdate: the End clip with gravity back) counts from the roof step,
    whose Update already adds to the timer (an offset of one frame).
Checks (decomp values, not fitted): vy while clinging, the wall slide's per-frame vy change after the stick time, the
wall jump's first x speeds, the dash's x speed, the glide's settled vy, the scramble's first rise step.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.knowledge import kinematics as km

DT60 = 1.0 / 60.0


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) of each run of True."""
    d = np.diff(np.r_[0, mask.astype(np.int8), 0])
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def phase_lengths(tr: km.Trace, modes: np.ndarray, params: km.HeroParams) -> dict[str, list[tuple[int, bool]]]:
    """param name -> [(L frames, natural end)] over the trace's runs of the Forum FSM moves."""
    clip = np.array(tr.clips, dtype=object)[tr.clip]
    vx, vy, fs = np.abs(tr.vel[:, 0]), tr.vel[:, 1], tr.fs
    rec, slide = tr.flag("downSpikeRecovery"), tr.flag("wallSliding")
    hurt = tr.flag("recoilFrozen") | tr.flag("recoiling")
    out: dict[str, list[tuple[int, bool]]] = defaultdict(list)
    n = len(tr)

    def onset_of(i0: int, i1: int, names) -> int | None:
        for i in range(i0, i1):
            if clip[i] in names:
                return i
        return None

    for m, tab in ((km.M_GLIDE, km.GLIDE_CLIPS), (km.M_RPR_DS, km.RPR_CLIPS), (km.M_SPRINT, km.SPRINT_CLIPS),
                   (km.M_SCRAMBLE, km.SCRAMBLE_CLIPS)):
        for i0, i1 in _runs(modes == m):
            ph = np.array([tab.get(c, -1) for c in clip[i0:i1]])
            cut = i1 >= n or bool(hurt[i0:min(i1 + 1, n)].any())
            # phases followed by another phase's clip
            seq = [(int(ph[k]), i0 + k) for k in range(len(ph)) if k == 0 or ph[k] != ph[k - 1]]
            for (p, a), (q, b) in zip(seq, seq[1:]):
                name = {(km.M_GLIDE, 0): "glide_antic_t", (km.M_GLIDE, 1): "glide_inflate_t",
                        (km.M_RPR_DS, 0): "rpr_antic_t", (km.M_SCRAMBLE, 0): "scr_antic_t",
                        (km.M_SPRINT, 0): "air_sprint_time"}.get((m, p))
                if name and q == p + 1 and p >= 0:
                    out[name].append((b - a, not cut))
            if m == km.M_RPR_DS:
                e = onset_of(i0, i1, ("v3 Down Slash",))
                if e is None:
                    continue
                g = None
                for i in range(e + 1, min(i1, n - 1)):
                    if fs[i] > 0 and vx[i - 1] > 0 and abs(vx[i] / vx[i - 1] - 1.0) < 0.01:
                        g = i
                        break
                if g is None or fs[g - 1] == 0:
                    continue
                t_slash = g - 1                      # the trigger frame: its step still decayed
                out["rpr_slash_t"].append((t_slash - e, not cut))
                c = i1                               # control back (FinishDownspike)
                natural = not cut and c < n and bool(rec[c])
                out["rpr_fall_t"].append((c - 1 - t_slash, natural))
            elif m == km.M_GLIDE:
                e = onset_of(i0, i1, ("Umbrella Deflate",))
                if e is not None:
                    out["glide_deflate_t"].append((i1 - e, not cut and i1 < n and not tr.flag("onGround")[i1]))
            elif m == km.M_SCRAMBLE:
                e = onset_of(i0, i1, ("Wall Scramble End",))
                if e is None or e == i0:
                    continue
                if fs[e] > 0:
                    v0 = vy[e - 1] - (params.scr_force_held if tr.mask[e - 1] & km.B_DASH else params.scr_force) * params.fdt
                    roof = v0 >= params.scr_end_vy or                         abs(vy[e] - (v0 - params.gravity * params.fdt)) < abs(vy[e] - v0 * params.scr_end_decel)
                else:
                    roof = False
                rep = onset_of(e, i1, ("Wall Scramble Antic",))   # REPEAT DASH: the End cut short
                c = i1 if rep is None else rep
                if roof:
                    out["scr_roof_t"].append((c - e + 1, not cut and rep is None))
                else:
                    out["scr_end_t"].append((c - e, not cut and rep is None and c < n and bool(slide[c])))
    return out


def threshold(lengths: list[int], offset: int, bias: float) -> tuple[float, str]:
    """The phase threshold from its logged lengths L (frames to the phase's end; `offset` 1 for a phase entered in
    a FixedUpdate, whose entry frame's Update already counts). One length: the middle of its interval,
    (L + offset - 0.5) / 60. Two adjacent lengths, the shorter at least 3 % (the frame-time jitter decides, as on
    the game's thresholds at exact multiples of 1/60 s): the boundary (L + offset) / 60, moved 0.4 timer_bias towards
    the majority so the nominal lane takes it and the -+ timer_bias lanes take both."""
    c = Counter(lengths)
    (a, na), *rest = c.most_common()
    b = next(((k, v) for k, v in rest if abs(k - a) == 1 and v >= 0.03 * len(lengths)), None)
    if b is None:
        return round((a + offset - 0.5) * DT60, 6), f"middle of L={a}"
    lo = min(a, b[0])
    return round((lo + offset) * DT60 + (0.4 * bias if a > lo else -0.4 * bias), 6), f"boundary L={lo}/{lo + 1}"


def fit(paths: list[str], params: km.HeroParams) -> tuple[dict, dict]:
    from ssbot.tools.kin_check import load_source
    fitted: dict = {}
    report: dict = {"phases": {}, "checks": {}, "clips_seen": Counter()}
    lengths: dict[str, list[tuple[int, bool]]] = defaultdict(list)
    vy_cling, dvy_slide, wj_vx, dash_vx, glide_vy, scr_first = [], [], [], [], [], []
    for path in paths:
        tr, terrains = load_source(path, params)
        modes = km.classify_modes(tr, forum=True)
        clip = np.array(tr.clips, dtype=object)[tr.clip]
        for c in clip[modes >= km.M_GLIDE]:
            report["clips_seen"][str(c)] += 1
        for k, v in phase_lengths(tr, modes, params).items():
            lengths[k] += [(int(L), bool(ok)) for L, ok in v]
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
        glide_vy += vy[(modes == km.M_GLIDE) & (clip == "Umbrella Float")].tolist()
        # the scramble's first rise step: AddForce2d OnEnter + the step's own (2 x 0.96 with the dash held)
        on = np.flatnonzero((clip == "Wall Scramble") & np.r_[True, clip[:-1] != "Wall Scramble"])
        for i in on:
            j = i + 1
            while j < len(tr) - 1 and tr.fs[j] == 0:
                j += 1
            scr_first.append(round(float(vy[j] - vy[i]), 3))
    for name, v in sorted(lengths.items()):
        nat = [L for L, ok in v if ok]
        r = {"lengths_natural": dict(sorted(Counter(nat).items())),
             "lengths_cut": dict(sorted(Counter(L for L, ok in v if not ok).items()))}
        if nat:
            fitted[name], how = threshold(nat, 1 if name == "scr_roof_t" else 0, params.timer_bias)
            r["fit"] = {"value": fitted[name], "rule": how, "n": len(nat),
                        "spread_frames": [int(min(nat)), int(max(nat))]}
        report["phases"][name] = r
    q = lambda a: ({"n": len(a), "p5": round(float(np.percentile(a, 5)), 3),  # noqa: E731
                    "p50": round(float(np.percentile(a, 50)), 3), "p95": round(float(np.percentile(a, 95)), 3)}
                   if len(a) else {"n": 0})
    report["checks"] = {"vy_while_clinging": q(vy_cling), "slide_dvy_per_s_after_stick": q(dvy_slide),
                        "wall_jump_abs_vx_first_frames": wj_vx[:8], "dash_abs_vx": q(dash_vx),
                        "glide_float_vy": q(glide_vy), "scramble_first_step_dvy": dict(Counter(scr_first))}
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
                             "phases": report["phases"], "checks": report["checks"]}
        out = km.HeroParams.from_json(d)
        print("wrote", out.save(a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
