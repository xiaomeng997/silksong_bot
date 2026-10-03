"""Boss path audit: the planner's predicted boss hurtbox (Forecast.boss_box, the box its attacks are scored against
and the pogo gate checks) against the boss's recorded colliders, k frames ahead, per Control state at the origin.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.boss_path_audit C:/ssbot/data/runs/m2/<run> [--instances 0,1]
        [--episodes 4] [--states "Charge Antic,Charge"] [--json out.json]

Why (2026-10-02, the person watching the live check of main): head-on down spikes on the charge never hit, and from
behind the spike starts too high and ends before the boss arrives. The hit model reproduces the person's pogos with the
boss's LOGGED colliders (tools/pogo_repro: 5 of 5), so what is left is the predicted box: its x along the charge
(timing, anchor, speed profile) and its height (which polygon is moved along the path).

How: each episode's recording is replayed through the oracle backend and the forecaster (oracle view, the playbook's
no-hurtbox states), as the planner policy does; at every `--every`-th frame whose Control state is in --states, the
box predicted for k frames ahead (tk = k / 60 game s, the planner's rollout clock) is compared with the recorded
enabled colliders' bounding box at
  frame base   frame fo + k (what the planner's frame k meets: game time stands still in hit-stop frames, the
               rollout's frames do not);
  game base    the first frame whose game time is >= t(fo) + tk (the model's own accuracy).
Errors along the boss's motion (dir = the recorded box centre's displacement sign over the window): front = dir *
(predicted front edge - recorded front edge), > 0: the prediction is ahead (the boss arrives later than planned);
top = predicted top - recorded top, > 0: predicted taller (a spike planned to meet it is pressed too high). Also the
hittable flag (predicted ok vs recorded colliders enabled) and the share of hit-stop frames (ts 0) in the window.

--view degraded / degraded_dust (task V): the simulated final path instead (PlannerPolicy's DegradedOracleBackend:
ObservabilityFilter, SimpleNoise, DelayLine 2-4 frames, seeded from the episode's seed as the live run did; the
vision-equivalent forecaster with the attack fit and the hurtbox table). The origin is then the delayed WorldState's
frame (the box predicted for k frames after it is compared with the colliders of that frame + k), rows are keyed by
the recorded Control state at the origin, and per box side the errors carry min / p1 / p99 / max too: the box
uncertainty the vision view's pogo gate shrinks the box by is sized from them (--margins: written to
knowledge/1.0.30000/enemies/BellBeast_vision_box_margin.json, read by Forecast.certain_boss).
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from ssbot.core.bosses import BELL_BEAST_PHASES as PHASE_OF

KS = (3, 6, 9, 12, 18, 24, 30, 36, 42, 48)
CHARGE = ("Charge Emerge", "Charge Antic", "Charge", "Charge End")


def _box(e) -> tuple | None:
    vs = [np.asarray(c["verts_world"], float).reshape(-1, 2) for c in (e or {}).get("colliders") or ()
          if c.get("enabled")]
    if not vs:
        return None
    v = np.concatenate(vs)
    return float(v[:, 0].min()), float(v[:, 1].min()), float(v[:, 0].max()), float(v[:, 1].max())


def _boss(s):
    return next((e for e in s.get("ents") or () if e.get("type_key") == "Bone Beast"), None)


def _q(v):
    if not v:
        return None
    a = np.asarray(v)
    return [round(float(np.percentile(a, p)), 2) for p in (10, 50, 90)] + [len(a)]


def _q_wide(v):
    if not v:
        return None
    a = np.asarray(v)
    return [round(float(a.min()), 2)] + [round(float(np.percentile(a, p)), 2) for p in (1, 10, 50, 90, 99)] + \
        [round(float(a.max()), 2), len(a)]


def _control(s: dict) -> str | None:
    return ((_boss(s) or {}).get("fsms") or [{}])[0].get("state")


def audit_episode(states: list[dict], fc, want: set[str], every: int, out: dict, view: str = "oracle",
                  seed: int | None = None, wake_frame: int | None = None) -> None:
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.forecast import Forecast
    from ssbot.core.bosses import BOSSES
    fc.reset()
    spec = BOSSES[fc.model.boss_type]
    tg = np.zeros(len(states))
    boxes: list = [None] * len(states)
    frz = np.zeros(len(states), bool)
    clock = OracleBackend(bosses=[spec])
    for i, s in enumerate(states):
        boxes[i] = _box(_boss(s))
        frz[i] = float(s.get("ts", 1.0) or 0.0) == 0.0
        tg[i] = clock.feed(s).stamp.t_game_s
    if view == "oracle":
        be = OracleBackend(bosses=[spec])
    else:
        import random
        from ssbot.backends.degraded import DegradedOracleBackend
        from ssbot.backends.observability import ObservabilityFilter
        from ssbot.train.planner_policy import TELLS
        be = DegradedOracleBackend(OracleBackend(bosses=[spec]), ObservabilityFilter(bosses=[spec],
                                                                                    tells=TELLS[view]))
        be.reset(random.Random(seed).randrange(1 << 30))     # PlannerPolicy.reset's draw: the live run's noise
    idx = {s["f"]: i for i, s in enumerate(states)}
    preds = []
    woke = False
    for s in states:
        ws = be.feed(s)
        if ws is None or ws.stamp.frame not in idx:
            continue
        i = idx[ws.stamp.frame]
        if view != "oracle" and not woke and wake_frame is not None and ws.stamp.frame >= wake_frame:
            fc.notify_wake(ws.stamp.t_game_s)
            woke = True
        fc.update(ws)
        st = fc.tracker.state if view == "oracle" else _control(states[i])
        if st not in want or i % every or i + KS[-1] >= len(states):
            continue
        f = Forecast(fc, ws.stamp.t_game_s, 0.8, [], [], True, [], fc.boss)
        tk = np.arange(KS[-1] + 1) / 60.0
        bb, ok = f.boss_box(tk)
        hx = float(states[i]["hero"]["pos"][0])
        ph = f"{fc.tracker.ctx.phase}{'first' if fc.tracker.n_attacks <= 1 else ''}" if view == "oracle" else \
            f"{fc.tracker.shape_key(fc.hurtbox)}|flip{int(bool(fc.boss is not None and fc.boss.flip_x))}"
        preds.append((i, st, ph, round(ws.stamp.t_game_s - fc.tracker.t_entry, 3) if fc.tracker.t_entry is not None
                      else None, bb, ok, hx))
    for i, st, ph, tau, bb, ok, hx in preds:
        b0 = boxes[i]
        for k in KS:
            for base in ("frame", "game"):
                if base == "frame":
                    j = i + k
                else:
                    j = int(np.searchsorted(tg, tg[i] + k / 60.0 - 1e-6))
                    if j >= len(states):
                        continue
                bj = boxes[j]
                key = (st + "#" + str(ph), base, k)
                o = out.setdefault(key, defaultdict(list))
                o["n"].append(1)
                if not ok[k] or bj is None:
                    o["ok_mismatch"].append(int(bool(ok[k]) != (bj is not None)))
                    continue
                o["ok_mismatch"].append(0)
                p = bb[k]
                c_now = 0.5 * ((b0 or bj)[0] + (b0 or bj)[2])
                c_then = 0.5 * (bj[0] + bj[2])
                d = 1.0 if c_then > c_now + 1e-3 else (-1.0 if c_then < c_now - 1e-3 else 0.0)
                if d != 0.0:
                    pf, af = (p[2], bj[2]) if d > 0 else (p[0], bj[0])
                    o["front"].append(d * (pf - af))
                    # head-on: the hero ahead of the boss in its motion; else behind it (the boss comes from behind)
                    rel = "head_on" if d * (hx - c_now) > 0 else "behind"
                    o[f"front_{rel}"].append(d * (pf - af))
                o["cx"].append(0.5 * (p[0] + p[2]) - c_then)
                o["left"].append(p[0] - bj[0])
                o["right"].append(p[2] - bj[2])
                o["top"].append(p[3] - bj[3])
                o["bottom"].append(p[1] - bj[1])
                o["width"].append((p[2] - p[0]) - (bj[2] - bj[0]))
                o["frozen"].append(float(frz[i + 1:i + k + 1].mean()) if base == "frame" else 0.0)
                o["tau"].append(tau if tau is not None else np.nan)
                if PHASE_OF.get(_control(states[j]) or "") == PHASE_OF.get(_control(states[i]) or ""):
                    # still in the observable phase of the origin (the vision view's certain box is used only until
                    # the phase can end: Forecast.certain_boss)
                    for side, v in (("left", p[0] - bj[0]), ("right", p[2] - bj[2]), ("bottom", p[1] - bj[1]),
                                    ("top", p[3] - bj[3])):
                        o[f"same_{side}"].append(v)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--instances", default="0")
    ap.add_argument("--episodes", type=int, default=4)
    ap.add_argument("--states", default=",".join(CHARGE))
    ap.add_argument("--every", type=int, default=2)
    ap.add_argument("--view", default="oracle", choices=("oracle", "degraded", "degraded_dust"))
    ap.add_argument("--margins", type=Path, default=None,
                    help="vision views: write the pogo gate's box margins per phase and horizon (vision_margins)")
    ap.add_argument("--pad", type=float, default=0.1)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.combat.boss_model import BossModel
    from ssbot.combat.forecast import Forecaster, load_hurtbox
    from ssbot.combat.tactics import load_playbook
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.postmortem import episode_rows, find_recording
    model = BossModel.load("BellBeast")
    from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT
    fc = Forecaster(model, ORACLE if a.view == "oracle" else VISION_EQUIVALENT, templates={})
    pb = load_playbook("BellBeast")
    fc.no_hurtbox, fc.shape_from = pb.no_hurtbox, pb.shape_from
    if a.view != "oracle":                   # as PlannerPolicy builds the vision view's forecaster
        from ssbot.combat.attack_fit import AttackFit
        from ssbot.train.planner_policy import FUSION
        if FUSION:
            fc.tracker.fit = AttackFit(model)
        fc.hurtbox = load_hurtbox()
        fc.bell_tells = a.view == "degraded_dust"
    want = set(a.states.split(","))
    out: dict = {}
    n_ep = 0
    for inst in (int(x) for x in a.instances.split(",")):
        for row in episode_rows(a.run, inst)[:a.episodes]:
            if not row.get("recording") or row.get("outcome") == "HARNESS_FAIL":
                continue
            r = RecordingReader(find_recording(a.run, row))
            states = [s for s in r.states(row["f_end"] - row["acts"], row["f_end"])]
            audit_episode(states, fc, want, a.every, out, a.view, row.get("seed"), row.get("f_wake"))
            n_ep += 1
    rep = {"episodes": n_ep, "quantiles": "p10 / p50 / p90 / n", "rows": []}
    for (st, base, k), o in sorted(out.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        rep["rows"].append({"state": st, "base": base, "k": k, "n": len(o["n"]),
                            "ok_mismatch": round(float(np.mean(o["ok_mismatch"])), 3) if o["ok_mismatch"] else None,
                            **{m: _q(o[m]) for m in ("front", "front_head_on", "front_behind", "top", "bottom",
                                                     "width", "frozen")},
                            **({f"{m}_wide": _q_wide(o[m]) for m in ("left", "right", "top", "bottom")}
                               if a.view != "oracle" else {})})
    for x in rep["rows"]:
        print(json.dumps(x))
    if a.json:
        a.json.write_text(json.dumps(rep, indent=1), "utf-8")
    if a.margins and a.view != "oracle":
        doc = vision_margins(out, a.pad)
        doc["source"] = {"run": str(a.run), "instances": a.instances, "episodes_per_instance": a.episodes,
                         "view": a.view, "episodes": n_ep}
        a.margins.write_text(json.dumps(doc, indent=1), "utf-8")
        print(f"margins -> {a.margins}: {json.dumps(doc['phases'])}")
    return 0


MARGIN_BUCKETS = (6, 12, 24, 48)


def vision_margins(out: dict, pad: float) -> dict:
    """Per observable phase and horizon bucket (frames ahead <= k), how far the actual box can lie inside the
    predicted one on each side (left, right, bottom, top shrinks, u): the largest residual seen in that direction
    over every origin state and flip while the boss was still in the origin's observable phase (recorded), + pad.
    Frame base (the planner's frame k)."""
    agg: dict = {}
    for (key, base, k), o in out.items():
        if base != "frame" or not o.get("same_left"):
            continue
        phase = key.split("#")[1].split("|")[0]
        for kb in MARGIN_BUCKETS:
            if k > kb:
                continue
            m = agg.setdefault(phase, {}).setdefault(str(kb), [0.0, 0.0, 0.0, 0.0])
            m[0] = max(m[0], -float(np.min(o["same_left"])))
            m[1] = max(m[1], float(np.max(o["same_right"])))
            m[2] = max(m[2], -float(np.min(o["same_bottom"])))
            m[3] = max(m[3], float(np.max(o["same_top"])))
    phases = {ph: {kb: [round(max(0.0, v) + pad, 3) for v in m] for kb, m in d.items()} for ph, d in agg.items()}
    return {"buckets": list(MARGIN_BUCKETS), "pad": pad, "sides": ["left", "right", "bottom", "top"],
            "phases": phases}


if __name__ == "__main__":
    sys.exit(main())
