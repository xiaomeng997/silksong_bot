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
  - Hit Roof Soft (a scramble's roof ray in a FixedUpdate, or in Scramble Up's OnEnter: the End clip with gravity
    back) counts from the frame the End clip shows, whose Update already adds to the timer (threshold offset one
    frame; until 2026-10-03 the length also added that frame, so the offset counted twice: 0.1002 for an End clip
    that lasts 5 frames, 4 when the frame-time sum reaches 1/12 s).
The Reaper down slash's terrain thunk reach (rpr_thunk_reach0 / reach1 / reach_t, thunk_reach()): every physics step
of the slash phase is a thunk (|vx| decays by 0.7 x 0.715 in it instead of 0.7) or not; its height is the box centre
above the highest floor under the forward lobe (rpr_thunk_lobe0 .. lobe1 along the facing) and its time the phase
timer before the step (the model's MODE_T in rpr_thunk). The reach is the midpoint between the highest thunk and the
lowest step that did not thunk, separately before and after the split time (between the last early and the first
late thunk); frames with two steps are skipped (which step thunked is unknown).
Checks (decomp values, not fitted): vy while clinging, the wall slide's per-frame vy change after the stick time, the
wall jump's first x speeds, the dash's x speed, the glide's settled vy, the scramble's first rise step.
Every value this tool does not fit but the Forum model reads gets a "source" entry (HAND_SET).
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
                    f = params.scr_force_held if tr.mask[e - 1] & km.B_DASH else params.scr_force
                    v0 = vy[e - 1] - f * params.fdt
                    roof = v0 >= params.scr_end_vy or \
                        abs(vy[e] - (v0 - params.gravity * params.fdt)) < abs(vy[e] - v0 * params.scr_end_decel)
                else:
                    roof = False
                rep = onset_of(e, i1, ("Wall Scramble Antic",))   # REPEAT DASH: the End cut short
                c = i1 if rep is None else rep
                if roof:
                    out["scr_roof_t"].append((c - e, not cut and rep is None))
                else:
                    out["scr_end_t"].append((c - e, not cut and rep is None and c < n and bool(slide[c])))
    return out


def thunk_steps(tr: km.Trace, modes: np.ndarray, terrain, params: km.HeroParams) -> list[tuple[float, float, bool]]:
    """(phase timer before the step, box centre height over the floor under the lobe, thunked) for every one-step
    frame of every Reaper down slash's slash phase, up to its thunk."""
    clip = np.array(tr.clips, dtype=object)[tr.clip]
    out = []
    for i0, i1 in _runs(modes == km.M_RPR_DS):
        e = next((k for k in range(i0, i1) if clip[k] == "v3 Down Slash"), None)
        if e is None or terrain is None:
            continue
        face = 1.0 if tr.facing[e] >= 0 else -1.0
        t = 0.0
        for k in range(e + 1, i1):
            if tr.fs[k] == 0:
                t += float(tr.dt[k])
                continue
            v0, v1 = abs(tr.vel[k - 1, 0]), abs(tr.vel[k, 0])
            decay = params.rpr_slash_decel ** int(tr.fs[k])
            if v0 < 0.05 or v1 > 1.05 * decay * v0:
                break                          # the slash's decay stopped: its trigger frame passed
            thunk = v1 < 0.85 * decay * v0
            if tr.fs[k] == 1:
                px = 0.5 * (tr.box[k, 0] + tr.box[k, 2])
                cy = 0.5 * (tr.box[k, 1] + tr.box[k, 3])
                lo, hi = sorted((px + face * params.rpr_thunk_lobe0, px + face * params.rpr_thunk_lobe1))
                fl = [y for y, a, b in terrain.hseg if a < hi and b > lo and y <= cy]
                if fl:
                    out.append((round(t, 5), float(cy - max(fl)), bool(thunk)))
            t += float(tr.dt[k])
            if thunk:
                break
    return out


def thunk_reach(steps: list[tuple[float, float, bool]]) -> tuple[dict, dict]:
    """rpr_thunk_reach0 / reach1 / reach_t from thunk_steps over all recordings (see the module docstring)."""
    th = [(t, h) for t, h, k in steps if k]
    if not th:
        return {}, {"n_steps": len(steps), "thunks": 0}
    ts = sorted({t for t, _ in th})
    # split: the gap between consecutive thunk times where the early / late reaches separate best
    best = None
    for a, b in zip(ts, ts[1:]):
        split = 0.5 * (a + b)
        hi0 = max((h for t, h in th if t < split), default=-np.inf)
        hi1 = max((h for t, h in th if t >= split), default=-np.inf)
        lo0 = min((h for t, h, k in steps if not k and t < split), default=np.inf)
        lo1 = min((h for t, h, k in steps if not k and t >= split), default=np.inf)
        if hi0 < lo0 and hi1 < lo1 and hi1 > hi0 and (best is None or hi1 - hi0 > best[0]):
            best = (hi1 - hi0, split, hi0, lo0, hi1, lo1)
    if best is None:
        hi = max(h for _, h in th)
        lo = min((h for _, h, k in steps if not k), default=hi + 0.02)
        r = round(0.5 * (hi + min(lo, hi + 0.04)), 4)
        return {"rpr_thunk_reach0": r, "rpr_thunk_reach1": r}, {"n_steps": len(steps), "thunks": len(th),
                                                                "highest_thunk": hi, "lowest_miss": lo}
    _, split, hi0, lo0, hi1, lo1 = best
    fitted = {"rpr_thunk_reach0": round(0.5 * (hi0 + lo0), 4), "rpr_thunk_reach1": round(0.5 * (hi1 + lo1), 4),
              "rpr_thunk_reach_t": round(split, 4)}
    return fitted, {"n_steps": len(steps), "thunks": len(th), "early": [round(hi0, 3), round(lo0, 3)],
                    "late": [round(hi1, 3), round(lo1, 3)], "split_s": round(split, 4)}


# values the Forum model reads that no fit here sets: where each comes from (written into the params' "source")
HAND_SET = {
    "rpr_thunk_decel": "crest_attacks template, Rpr Downslash Thunk: DecelerateV2 0.715 (its SetVelocity2d y 28 is "
                       "disabled); live: the thunk step's |vx| ratio 0.7 x 0.715 = 0.50 (kin_fit_forum thunk_steps)",
    "rpr_thunk_lobe0": "hand-set x span of the floor the down slash's thunker meets (0.5 .. 2.2 u ahead of the body "
                       "centre); not separable in the excitation runs (every logged slash had one floor under the hero "
                       "and the lobe)",
    "rpr_thunk_lobe1": "see rpr_thunk_lobe0",
    "sprint_shift": "hornet_sprint template, Ground Sprint R / L OnEnter: Transform.Translate 0.05 u forward; live: "
                    "implied shift from the drawn position exactly 0.05 in 24 of 25 released ground dashes "
                    "(kn_excite_forum_s98200, movement_kinematics.md 1.3)",
    "sprint_grace": "hornet_sprint template: Sprint Grace 0.3 s (Regain Control To Idle under it)",
    "skid_decel": "hornet_sprint template, Skid End 1 / 2: DecelerateXY 0.85",
    "skid_decel_move": "hornet_sprint template, Skid End 1 / 2: 0.95 while moving the facing way",
    "skid_time": "animation clips Skid End 1 (0.2 s) + Skid End 2 (0.05 s) (herodynamic bundle, UnityPy)",
    "skid_min_speed": "hornet_sprint template, Skid SFX?: no skid under 4 u/s",
    "air_fall_clamp_lag": "one frame: the Air Sprint fall clamp (EaseFloat -10 -> -30, 1 s) reads a frame behind the "
                          "state's own time in every air sprint of kn_excite_forum_s98200 (fit run C; also seen in "
                          "the dev run D, s98300)",
    "scr_roof_ray": "CharacterBumpCheck.CheckForBump (top): ray 0.1 + 0.03 + |vy| fdt from 0.1 u under the box top",
    "scr_detach": "hornet_wall_scramble template, Detach: Translate x scale.x * 0.2",
    "wall_up_shove": "HeroController.Attack 4164: MovePosition 0.8 off the wall for an up slash while wall sliding",
}


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
    thunks: list[tuple[float, float, bool]] = []
    for path in paths:
        tr, terrains = load_source(path, params)
        modes = km.classify_modes(tr, forum=True)
        for si, name in enumerate(tr.scenes):
            if name in terrains and (tr.scene == si).any():
                thunks += thunk_steps(tr, np.where(tr.scene == si, modes, km.M_NORMAL), terrains[name], params)
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
    tf, trep = thunk_reach(thunks)
    fitted.update(tf)
    report["phases"]["rpr_thunk_reach"] = trep
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
            how = "thunk heights (thunk_reach)" if k.startswith("rpr_thunk") else "logged phase lengths (threshold)"
            d["source"][k] = f"kin_fit_forum, {how}, on {', '.join(map(str, a.sources))}"
        for k, v in HAND_SET.items():
            d["source"][k] = v
        d["fit"] = dict(d.get("fit") or {})
        d["fit"]["forum"] = {"sources": [str(s) for s in a.sources], "fitted": fitted,
                             "phases": report["phases"], "checks": report["checks"]}
        out = km.HeroParams.from_json(d)
        print("wrote", out.save(a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
