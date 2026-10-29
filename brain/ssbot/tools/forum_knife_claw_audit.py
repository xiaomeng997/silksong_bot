"""Audit the existing local hook model on historical, real latched inputs.

The target boxes are the recorded target trajectory. This deliberately isolates
the hero component; it does not validate enemy forecasts, a closed-loop plant,
or treatment effects. The 34 success cases are development data, not a holdout.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np


POSITION_TOL_U = 0.25
CONTROL_TOL_F = 1


def body_box(state: dict, iid: int) -> np.ndarray:
    """The selected entity's root damage body, never its range triggers."""
    ent = next((e for e in state.get("ents", ()) if int(e.get("iid", -1)) == iid), None)
    if ent is None:
        raise ValueError("target missing")
    roots = []
    for c in ent.get("colliders", ()):
        if (c.get("kind") != "box" or not c.get("enabled", True)
                or c.get("layer") != 11 or not c.get("damage")
                or not str(c.get("name", "")).startswith("Song Heavy Sentry")):
            continue
        v = np.asarray(c.get("verts_world", ()), dtype=float)
        if len(v) < 8 or len(v) % 2 or not np.isfinite(v).all():
            raise ValueError("invalid target body vertices")
        roots.append(np.array([v[0::2].min(), v[1::2].min(), v[0::2].max(), v[1::2].max()]))
    if len(roots) != 1:
        raise ValueError(f"expected one root body, found {len(roots)}")
    return roots[0]


def require_frames(states: list, first: int, last: int) -> dict:
    frames = {}
    for s in states:
        f = int(s["f"])
        if f in frames:
            raise ValueError(f"duplicate STATE {f}")
        frames[f] = s
    if sorted(frames) != list(range(first, last + 1)):
        raise ValueError("raw STATE gap or wrong range")
    for s in states:
        if any(not isinstance(s.get(k), (int, float)) or not math.isfinite(s[k]) or s[k] < 0
               for k in ("dt", "udt", "fs")):
            raise ValueError("missing/invalid raw timing")
        if s["fs"] != int(s["fs"]):
            raise ValueError("fractional physics count")
        if not isinstance((s.get("act") or {}).get("mask"), int):
            raise ValueError("missing latched mask")
    return frames


def audit_case(case: dict, params, model: str = "legacy") -> dict:
    from ssbot.ipc.framing import mask
    from ssbot.knowledge import kinematics as km
    from ssbot.map2 import strike as sk
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.reflex_val import _her_state, _terrain

    fa, iid = int(case["fa"]), int(case["iid"])
    fp = fa + int(case["claw_k"])
    fc = fa + int(case["control_k"])
    attack = fa + int(case["start_k"])
    out = {"episode": case["ep"], "recording": case["recording"], "iid": iid,
           "press_f": fp, "control_f": fc, "attack_start_f": attack,
           "wave": case["wave"], "complete": False, "errors": []}
    try:
        rr = RecordingReader(case["recording"])
        end = max(fp + 62, attack + 2)
        raw = list(rr.states(fp - 1, end, keys=("f", "hero", "act", "dt", "udt", "fs", "ents", "ev")))
        frames = require_frames(raw, fp - 1, end)
        hp = frames[fp]["hero"]
        if not frames[fp]["act"]["mask"] & mask("clawline"):
            raise ValueError("listed hook press not latched")
        if not str((hp.get("anim") or {}).get("clip", "")).startswith("Harpoon Antic"):
            raise ValueError("listed hook was not accepted")
        if not frames[fc]["hero"]["hero_accepting_input"] or frames[fc - 1]["hero"]["hero_accepting_input"]:
            raise ValueError("listed control frame is not the observed recovery edge")
        if not str((frames[attack]["hero"].get("anim") or {}).get("clip", "")).startswith("DownSlash"):
            raise ValueError("listed down attack not observed")
        sp = _her_state(rr, case["recording"], fp - 1, params)
        if sp is None:
            raise ValueError("no supported pre-hook state")
        # Same input/physics boundary as the planner: model the press frame's
        # free flight, then enter the hook. Claw itself is not in km.rollout.
        step = frames[fp]
        free = km.rollout(sp, np.array([[step["act"]["mask"] & ~mask("clawline")]], np.int64),
                          params, _terrain(rr, case["recording"], params),
                          dt=np.array([step["dt"]]), fs=np.array([step["fs"]]),
                          udt=np.array([step["udt"]]), threads=1).final[:, 0]
        if model == "stepwise":
            # This component currently supports plain normal-control launches
            # only. Preserve the press-frame free rollout: a queued jump can
            # reset horizontal velocity in that frame's physics; copying the
            # previous velocity across that boundary is incorrect.
            if int(sp[km.MODE]) != km.M_NORMAL:
                raise ValueError("launch mode not yet supported by the local adapter")
        out["launch_free_velocity"] = [float(free[km.VX]), float(free[km.VY])]
        out["observed_entry_velocity"] = list(hp["vel"][:2])
        boxes = []
        for f in range(fp, fp + 63):
            try:
                boxes.append(body_box(frames[f], iid))
            except ValueError:
                if f <= fc:
                    raise
                # A target killed by the later down slash can disappear after
                # this component's endpoint. Its future body is unknown, not
                # the last live box carried forever.
                boxes.append(np.full(4, np.nan))
        boxes = np.stack(boxes)
        direction = 1 if (boxes[0, 0] + boxes[0, 2]) / 2 >= free[km.PX] else -1
        if model == "stepwise":
            from ssbot.map2.oldwin_claw import hook_variants
            hooks = hook_variants(free, direction, iid, boxes)
        else:
            hooks = [sk.claw_hook(free, 0, direction, iid, boxes, variant, phase)
                     for variant in sk.HOOK_VARIANTS for phase in range(6)]
        valid = [h for h in hooks if h.ok]
        out["all_rays_meet"] = len(valid) == len(hooks)
        out["model_rays"] = {f"{i}:{h.variant}": h.why or "hook" for i, h in enumerate(hooks)}
        if not valid:
            raise ValueError("all hook variants miss the recorded body")
        actual = np.asarray([frames[f]["hero"]["pos"][:2] for f in range(fp, fc + 1)], float)
        paths = np.stack([np.asarray([h.pos[min(k, len(h.pos) - 1)] for k in range(len(actual))])
                          for h in valid])
        lo, hi = paths.min(axis=0), paths.max(axis=0)
        residual = np.maximum(np.maximum(lo - actual, actual - hi), 0.0)
        controls = [h.ctrl for h in valid]
        ctrl = fc - fp
        control_ok = min(controls) - CONTROL_TOL_F <= ctrl <= max(controls) + CONTROL_TOL_F
        first_bad = np.flatnonzero((residual > POSITION_TOL_U).any(axis=1))
        out.update(complete=True, actual_control_after_press=ctrl,
                   model_control_range=[min(controls), max(controls)], control_covered=control_ok,
                   max_residual_u=residual.max(axis=0).tolist(),
                   first_position_failure_f=None if not len(first_bad) else fp + int(first_bad[0]),
                   attack_after_control=attack - fc, free_min_respected=attack - fc >= 10,
                   position_covered=not len(first_bad),
                   passed=control_ok and not len(first_bad) and attack - fc >= 10 and out["all_rays_meet"],
                   frames=[{"f": fp + k, "actual": actual[k].tolist(), "lo": lo[k].tolist(),
                            "hi": hi[k].tolist(), "residual": residual[k].tolist()}
                           for k in range(len(actual))])
        if model == "stepwise":
            from ssbot.map2.oldwin_claw import control_state
            # A second isolated component check starts at the real control
            # edge, with its measured pose/phase. It is not an end-to-end
            # claim that the forecast chose that exact edge.
            hc = frames[fc]["hero"]
            sc = _her_state(rr, case["recording"], fc, params)
            hook = SimpleNamespace(x_stop=(hc["box"][0] + hc["box"][2]) / 2,
                                   y_hold=hc["box"][1] + params.foot, d=direction)
            state = control_state(params, hook, _terrain(rr, case["recording"], params), alpha=sc[km.ALPHA])
            post_frames = [frames[f] for f in range(fc + 1, attack + 2)]
            post_masks = np.array([[s["act"]["mask"] for s in post_frames]], np.int64)
            post = km.rollout(state, post_masks, params, _terrain(rr, case["recording"], params),
                              dt=np.array([s["dt"] for s in post_frames]),
                              fs=np.array([s["fs"] for s in post_frames]),
                              udt=np.array([s["udt"] for s in post_frames]), threads=1)
            actual_pos = np.array([frames[fc]["hero"]["pos"][:2]] +
                                  [s["hero"]["pos"][:2] for s in post_frames])
            error = np.abs(post.pos[0] - actual_pos)
            starts = np.flatnonzero(((post.flags[0, 1:] & km.F_ATTACKING) != 0) &
                                    ((post.flags[0, :-1] & km.F_ATTACKING) == 0)) + 1
            predicted_start = None if not len(starts) else fc + int(starts[0])
            post_ok = bool(predicted_start == attack and int(post.final[km.ATK_PDIR, 0]) == 2
                           and (error <= POSITION_TOL_U).all() and state[km.INV_T] == 0)
            out["post_control"] = {"scope": "real control edge pose/phase plus real keys and timing",
                                   "max_error_u": error.max(axis=0).tolist(),
                                   "predicted_attack_start_f": predicted_start,
                                   "actual_attack_start_f": attack, "passed": post_ok,
                                   "initial_invulnerability_s": float(state[km.INV_T])}
            out["passed"] = bool(out["passed"] and post_ok)
            from ssbot.map2.oldwin_claw import rollout as claw_rollout
            full_masks = np.array([frames[f]["act"]["mask"] for f in range(fp, attack + 2)], np.int64)
            full_boxes = np.vstack((body_box(frames[fp - 1], iid), boxes))
            joined = claw_rollout(sp, full_masks, params, _terrain(rr, case["recording"], params),
                                  full_boxes, iid)
            actual_states = [frames[f] for f in range(fp - 1, attack + 2)]
            actual_boxes = np.array([s["hero"]["box"] for s in actual_states])
            bound = np.concatenate((joined.bound[..., :2].min(axis=0),
                                    joined.bound[..., 2:].max(axis=0)), axis=1)
            box_covered = bool((bound[:, :2] <= actual_boxes[:, :2] + 1e-6).all()
                               and (bound[:, 2:] >= actual_boxes[:, 2:] - 1e-6).all())
            box_residual = np.maximum(np.maximum(bound[:, :2] - actual_boxes[:, :2],
                                                 actual_boxes[:, 2:] - bound[:, 2:]), 0)
            failures = np.flatnonzero((box_residual > 1e-6).any(axis=1))
            start_frames = []
            for flags in joined.flags:
                rises = np.flatnonzero(((flags[1:] & km.F_ATTACKING) != 0) &
                                      ((flags[:-1] & km.F_ATTACKING) == 0)) + 1
                start_frames.append(None if not len(rises) else fp - 1 + int(rises[0]))
            attack_covered = all(f == attack for f in start_frames)
            out["compound"] = {"scope": "one pre-hook observed state, real fixed keys, nominal future clock; recorded target path",
                               "box_covered": box_covered, "all_attack_starts_match": attack_covered,
                               "max_box_residual_u": box_residual.max(axis=0).tolist(),
                               "first_box_failure_f": None if not len(failures) else fp - 1 + int(failures[0]),
                               "predicted_start_frames": sorted(set(start_frames), key=lambda x: -1 if x is None else x),
                               "model_outcomes": len(joined.final.T), "passed": box_covered and attack_covered}
            out["compound"]["zero_scaled_clock_frames"] = [
                {"f": int(s["f"]), "dt": s["dt"], "fs": s["fs"], "udt": s["udt"]}
                for s in actual_states if s["dt"] == 0]
            out["passed"] = bool(out["passed"] and out["compound"]["passed"])
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        out["errors"].append(f"{type(exc).__name__}: {exc}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model", choices=("legacy", "stepwise"), default="legacy")
    a = ap.parse_args(argv)
    from ssbot.map2.envelope import load_params
    cases = list(csv.DictReader(a.cases.read_text(encoding="utf-8-sig").splitlines()))
    if not cases:
        raise ValueError("empty development case list")
    params = load_params(hero2=True)
    results = []
    for i, case in enumerate(cases):
        result = audit_case(case, params, a.model)
        results.append(result)
        print(json.dumps({"case": i + 1, "episode": result["episode"], "complete": result["complete"],
                          "passed": result.get("passed", False), "errors": result["errors"]}), flush=True)
    report = {"purpose": __doc__, "model": a.model,
              "case_source_sha256": hashlib.sha256(a.cases.read_bytes()).hexdigest(),
              "position_tolerance_u": POSITION_TOL_U, "control_tolerance_f": CONTROL_TOL_F,
              "target_boxes": "recorded future target boxes; component audit only",
              "phase_domain": list(range(6)), "hook_variants": ["early", "late"],
              "dash_fixed_steps": [5, 6] if a.model == "stepwise" else [6],
              "render_interpolation": "both physics-pose endpoints" if a.model == "stepwise" else "legacy position",
              "stop_rule": "first 3u Dash Damager/body contact after physics" if a.model == "stepwise" else "exact gap",
              "cases": len(results), "complete": sum(r["complete"] for r in results),
              "passed": sum(r.get("passed", False) for r in results),
              "all_passed": all(r.get("passed", False) for r in results),
              "negative_or_unhooked_coverage": False, "production_enabled": False,
              "results": results}
    root = Path(__file__).resolve().parents[1]
    report["sources_sha256"] = {rel: hashlib.sha256((root / rel).read_bytes()).hexdigest() for rel in
                                ("tools/forum_knife_claw_audit.py", "map2/oldwin_claw.py", "map2/strike.py",
                                 "knowledge/kinematics.py", "knowledge/hero2.py")}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0 if report["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
