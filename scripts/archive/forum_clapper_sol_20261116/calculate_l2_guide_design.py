"""Small, non-policy arithmetic for the user-review L2 draft. No runtime writes."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

D = Path("C:/Users/Meng/.codex/worktrees/forum-knife-rows/silksong_bot")
FILES = ["brain/ssbot/combat/jump_behind.py", "brain/ssbot/combat/tactics/clapper_middle.py",
         "brain/ssbot/combat/tactics/gauntlet.py", "brain/ssbot/knowledge/hero2.py",
         "brain/ssbot/combat/are_types/clapper.py"]


def constants(file, names):
    out = {}
    for node in ast.parse((D/file).read_text(encoding="utf-8-sig")).body:
        if isinstance(node, ast.Assign):
            ns = [x.id for x in node.targets if isinstance(x, ast.Name)]
            if ns and any(n in names for n in ns):
                value = eval(compile(ast.Expression(node.value), file, "eval"), {"__builtins__": {}})
                out.update({n: value for n in ns if n in names})
    return out


G = constants(FILES[2], {"TWO_KEY_S", "TWO_RUN_U_S", "TWO_SPRINT_U_S", "JT"})
JB = constants(FILES[0], {"NUM"})["NUM"]
FDT = constants(FILES[3], {"FDT"})["FDT"]
# Use the owning helper as written, without importing policy/planner or running a benchmark.
tree = ast.parse((D/FILES[2]).read_text(encoding="utf-8-sig"))
fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_two_sprint_s")
fn.decorator_list = []
G.update(TWO_DASH_U=2.8, TWO_DASH_S=.1)
scope = {**G, "__builtins__": {"max": max}}
exec(compile(ast.Module(body=[fn], type_ignores=[]), FILES[2], "exec"), scope)
travel = scope["_two_sprint_s"]
hazard = next(n for n in ast.walk(ast.parse((D/FILES[4]).read_text(encoding="utf-8-sig")))
              if isinstance(n, ast.Call) and any(k.arg == "name" and isinstance(k.value, ast.Constant)
              and k.value.value == "rune slam" for k in n.keywords))
hz = {k.arg: ast.literal_eval(k.value) for k in hazard.keywords if k.arg in {"du_by_face", "box_w", "radius"}}
RUNE_REACH = max(hz["du_by_face"]) + hz["box_w"]/2

# Frozen standing-body example from the earlier raw f2639 read. This is an
# illustrative envelope, not a universal enemy-motion or body-width bound.
b = 2.2515621185302734
K = b + 2*G["JT"]["pad"] + G["JT"]["gap_u"]


def estimate(gap, radius, deadline, j=19.0, closure=0.):
    w0 = j + gap
    w = w0 - closure
    start = w0 - 4.
    limit = w - radius - K
    wall_limit = 14.01 + (JB["wall_push_u"] if j-14.01 < JB["push_from_u"] else JB["wall_back_u"])
    saturated_land = max(wall_limit, j + .916*12)
    if saturated_land <= limit:
        h = start
        reason = "no guide needed at this start; saturated landing already leaves the chosen gap"
    else:
        h = min(start, j+5+(limit-j)/.916)
        reason = "nearest sufficient guide point in the unsaturated model"
    land = max(wall_limit, j+.916*max(-12., min(12., h-5-j)))
    # The sampled front body is 2.0453128815u in Jump Antic, plus hero .25 and pad .25.
    front_min = j+2.0453128814697266+.25+.25
    fits = land <= limit+1e-9 and h >= front_min
    dist = max(0., start-h)
    move = travel(dist, 0.) if fits else None
    return {
        "gap_roots_initial_u": gap, "walker_closure_sensitivity_u": closure,
        "jumper_x": j, "walker_x_assumed_at_stand": w, "start_hero_x": start,
        "radius_u": radius, "earliest_aim_s": deadline, "landing_limit_x": limit,
        "wall_landing_min_x": wall_limit, "geometry_possible_in_frozen_example": fits,
        "guide_x": h if fits else None, "guide_from_jumper_root_u": h-j if fits else None,
        "outbound_u": dist if fits else None, "travel_s_nominal_helper": move,
        "latest_departure_s_before_brake_and_release_cost": deadline-.1-move if fits and dist>0 else None,
        "return_to_walker_front_dash_ready_s": travel(abs(w-4-h),0.) if fits else None,
        "return_to_walker_front_without_dash_s": (G["TWO_KEY_S"]+abs(w-4-h)/G["TWO_RUN_U_S"] if abs(w-4-h)>0 else 0.) if fits else None,
        "reason": reason if fits else "wall push / front body removes the algebraic guide solution",
    }


rows = [estimate(20., 7.76, .48), estimate(25., 7.76, .48),
        estimate(20., RUNE_REACH, .88), estimate(25., RUNE_REACH, .88),
        estimate(30., RUNE_REACH, .88, j=16.)]
raw_j = 18.963390350341797
raw_w = 29.390012741088867
raw_h = 20.2496395111084
raw_examples = []
for r in [7.76, RUNE_REACH]:
    limit = raw_w-r-K
    wall_min = 14.01+JB["wall_back_u"]
    raw_examples.append({"reach_u": r, "required_landing_max_x": limit,
                         "wall_landing_min_x": wall_min,
                         "short_of_current_gap_criterion_u": wall_min-limit})

result = {
    "purpose": "draft guide geometry and travel arithmetic, not policy replay, performance, or live validation",
    "source_paths_sha256": {p: hashlib.sha256((D/p).read_bytes()).hexdigest() for p in FILES},
    "constants": {"key_delay_nominal_s": G["TWO_KEY_S"], "dash_u": 2.8, "dash_s": .1,
                  "sprint_u_s": G["TWO_SPRINT_U_S"], "normal_run_u_s": G["TWO_RUN_U_S"],
                  "physics_step_s": FDT, "standing_body_inward_extent_example_u": b,
                  "landing_to_walker_extra_u": K, "earliest_aim_s": [.48, .88],
                  "planning_reserve_s": .1, "rune_hazard_spec": hz, "full_rune_reach_used_u": RUNE_REACH,
                  "legacy_JT_reach_c_u": G["JT"]["reach_c"]},
    "formula": "L=wall_rule(J,J+.916*clamp(H-5-J,-12,12)); L<=W-R-K; Hmax=J+5+(W-R-K-J)/.916 before saturation",
    "saturation_no_guide_root_separation_u": {"jump_hammer": 7.76+K+.916*12,
                                              "full_delayed_rune_footprint_both_facings": RUNE_REACH+K+.916*12},
    "rows": rows,
    "walker_closure_sensitivity_not_a_motion_bound": [estimate(20.,RUNE_REACH,.88,closure=x) for x in [0.,1.,2.,3.,4.]],
    "sample_existing_record": {"record": "sol/demos/w13_observe_bait_20261106T055356Z/run/rec/2026-11-05/TRAIN/i0_000",
                               "f": 2639, "jumper_x": raw_j, "walker_x": raw_w, "hero_x": raw_h,
                               "root_gap_u": raw_w-raw_j, "arithmetic_only": raw_examples},
    "excluded_costs_and_uncertainty": [
        "walker motion must use predicted inward body edge throughout the relevant event window, not frozen W",
        "release, request/compute delay, braking/hold and supported path are not proved by this scalar travel helper",
        "return dash availability must follow the outbound dash cooldown; the 0.425s reset is not presumed free",
        "full rune envelope uses current HazardSpec both-facings maximum, not older JT reach_c=13.67 or landing hammer alone",
        "walls, actual landing uncertainty/ceiling branch, front-body sweep, input and hazard checks remain",
        "60Hz input/STATE frames are not 50Hz physical steps; seconds here are nominal game time",
        "extreme-distance clipping is piecewise; do not operate exactly at its threshold without margin",
    ],
}
print(json.dumps(result, ensure_ascii=False, indent=2))
