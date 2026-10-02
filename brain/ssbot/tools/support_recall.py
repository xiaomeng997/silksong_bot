"""Support recall of the threat forecast on logged fights (M2 W3 stage A): every contact frame must lie inside the
support forecast made L frames earlier.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.support_recall C:/ssbot/data/runs/m2/<run> [--recordings i2_002,i3_002]
        [--lags 2,3,4] [--view oracle|ve] [--table DIR] [--margin 0] [--max-fights N] [--json out.json]

Contacts are what the behaviour builder validates its templates against (ssbot.knowledge.behaviour_tables): every
"damage" frame and every frame of a "damage_blocked" stretch (first_f..last_f, the hero touched while in i-frames).
The pairing is the planner's: the contact at frame c counts as covered when the hero box of c at t_c or the box of
c - 1 at t_(c-1) is inside the forecast's support, the forecast being made from the WorldState of frame c - L
(origin t_(c-L), nothing later used). The query is the planner's own: SupportQuery on the support templates dilated
by the hero hurtbox (plus --margin), the box centre tested.

Views: "oracle" feeds OracleBackend; "ve" adds the ObservabilityFilter (the vision-equivalent view; no noise and no
delay here: the lag L stands for the delay), "ve_dust" with the dust cues (planner_policy.DUST_TELL). Two passes per
recording: the events alone give the contact frames, then
the backend, filter and tracker run over every frame and forecast only at the frames some contact needs.
--table points the forecaster at another behaviour build (a held-out build: C:/ssbot/data/m2_heldout/tables holds
one without i2_002 / i3_002 and the trial run).
"""
import argparse
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


def fights_of(run: Path, recordings: set[str] | None) -> list[dict]:
    rows = []
    for p in sorted(run.glob("attempts_i*.jsonl")):
        for line in p.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            a = json.loads(line)
            if a.get("f_wake") is None or a.get("f_end") is None or not a.get("recording"):
                continue
            rec = Path(a["recording"])
            if not rec.is_dir():
                found = list(run.glob(f"rec/*/*/{rec.name}"))
                rec = found[0] if found else rec
            if recordings and rec.name not in recordings:
                continue
            rows.append({"rec": rec, "f0": int(a["f_wake"]), "f1": int(a["f_end"]),
                         "id": f"{run.name}/i{a.get('instance')}/ep{a.get('episode')}"})
    return rows


def contacts_of(reader, f0: int, f1: int) -> dict[int, str]:
    """Contact frames in [f0, f1] -> source (damage frames and blocked stretches)."""
    out: dict[int, str] = {}
    for s in reader.states(f0, f1 + 600, keys=("f", "ev")):
        for ev in s.get("ev") or ():
            k, d = ev.get("k"), ev.get("d") or {}
            if k == "damage" and f0 <= s["f"] <= f1:
                out[s["f"]] = str(d.get("source"))
            elif k == "damage_blocked" and isinstance(d.get("first_f"), int) and isinstance(d.get("last_f"), int):
                for c in range(max(f0, d["first_f"]), min(f1, d["last_f"]) + 1):
                    out.setdefault(c, str(d.get("source")))
    return out


def run_fight(fight: dict, fc, view: str, lags: list[int], stats: dict, misses: list, bosses) -> None:
    from ssbot.backends.observability import ObservabilityFilter
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.core.worldstate import VISION_EQUIVALENT
    from ssbot.record.recorder import RecordingReader

    r = RecordingReader(fight["rec"])
    f0, f1 = fight["f0"], fight["f1"]
    contacts = contacts_of(r, f0, f1)
    if not contacts:
        return
    need: dict[int, list[int]] = defaultdict(list)          # origin frame -> contact frames
    for c in contacts:
        for L in lags:
            need[c - L].append(c)
    backend = OracleBackend(bosses=bosses)
    filt = None
    if view in ("ve", "ve_dust"):
        from ssbot.train.planner_policy import DUST_TELL
        filt = ObservabilityFilter(bosses=bosses, tells=DUST_TELL if view == "ve_dust" else None)
    fc.reset()
    t_of: dict[int, float] = {}
    box_of: dict[int, tuple] = {}
    forecasts: dict[int, object] = {}
    state_of: dict[int, str] = {}
    start = f0 - 300                     # the wake chain needs the Control events before the wake frame
    for s in r.states(start, f1):
        f = s["f"]
        ws = backend.feed(s)
        if filt is not None:
            ws = filt.apply(ws)
        if f == f0 and view != "oracle":
            fc.notify_wake(ws.stamp.t_game_s)
        fc.update(ws)
        t_of[f] = ws.stamp.t_game_s
        b = (s.get("hero") or {}).get("box")
        box_of[f] = tuple(b[:4]) if b else None
        if f in need:
            forecasts[f] = fc.forecast(1.0)
            state_of[f] = str(fc.tracker.state)
    for c, src in sorted(contacts.items()):
        for L in lags:
            o = c - L
            fcast = forecasts.get(o)
            key = (view, L)
            stats[key]["n"] += 1
            if fcast is None or o not in t_of:
                stats[key]["no_origin"] += 1
                continue
            ok = False
            for fr in (c, c - 1):
                bx = box_of.get(fr)
                if bx is None or fr not in t_of:
                    continue
                x, y = 0.5 * (bx[0] + bx[2]), 0.5 * (bx[1] + bx[3])
                hit = fcast.occupied(np.array([[x]]), np.array([[y]]), np.array([t_of[fr] - t_of[o]]))
                if hit[0, 0]:
                    ok = True
                    break
            if ok:
                stats[key]["covered"] += 1
            else:
                bx = box_of.get(c)
                misses.append({"fight": fight["id"], "frame": c, "lag": L, "view": view, "source": src,
                               "state": state_of.get(o), "known": fcast.known, "roots": [
                                   (rt.state, round(rt.e_lo, 3), rt.ctx.family,
                                    None if rt.ctx.anchor is None else (rt.ctx.anchor.x, rt.ctx.anchor.mirror))
                                   for rt in fcast.roots],
                               "hero": None if bx is None else [round(v, 3) for v in bx],
                               "n_place": len(fcast.placements)})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--recordings", default="")
    ap.add_argument("--lags", default="2,3,4")
    ap.add_argument("--view", default="oracle,ve")
    ap.add_argument("--table", type=Path, default=None)
    ap.add_argument("--margin", type=float, default=0.0)
    ap.add_argument("--max-fights", type=int, default=0)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)

    from ssbot.combat.boss_model import BossModel
    from ssbot.combat.forecast import Forecaster, load_planner_templates
    from ssbot.core.bosses import BELL_BEAST
    from ssbot.core.worldstate import ORACLE, VISION_EQUIVALENT

    table = (a.table / "BellBeast.json") if a.table else None
    model = BossModel.load("BellBeast", table=table)
    npz = str(a.table / "BellBeast_hitboxes.npz") if a.table else None
    t0 = time.perf_counter()
    tpls = load_planner_templates(model, a.margin, npz)
    print(f"templates: {len(tpls)} in {time.perf_counter() - t0:.1f} s", flush=True)
    recs = {x for x in a.recordings.split(",") if x} or None
    fights = [f for run in a.runs for f in fights_of(run, recs)]
    if a.max_fights:
        fights = fights[: a.max_fights]
    lags = [int(x) for x in a.lags.split(",")]
    views = [v for v in a.view.split(",") if v]
    stats: dict = defaultdict(Counter)
    misses: list = []
    for v in views:
        fc = Forecaster(model, ORACLE if v == "oracle" else VISION_EQUIVALENT, margin=a.margin, templates=tpls)
        fc.bell_tells = v == "ve_dust"
        for i, fight in enumerate(fights):
            t1 = time.perf_counter()
            run_fight(fight, fc, v, lags, stats, misses, [BELL_BEAST])
            line = " ".join(f"L{L} {stats[(v, L)]['covered']}/{stats[(v, L)]['n']}" for L in lags)
            print(f"[{v}] {i + 1}/{len(fights)} {fight['id']} {time.perf_counter() - t1:.1f} s  {line}", flush=True)
    out = {"fights": len(fights), "lags": lags, "margin": a.margin, "table": str(a.table) if a.table else None,
           "recall": {f"{v}/L{L}": dict(stats[(v, L)]) for v in views for L in lags},
           "misses": misses[:500], "n_misses": len(misses),
           "miss_sources": dict(Counter(m["source"] for m in misses)),
           "miss_states": dict(Counter(f"{m['view']}:{m['state']}" for m in misses))}
    print(json.dumps({k: out[k] for k in ("recall", "n_misses", "miss_sources", "miss_states")}, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
