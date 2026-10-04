"""What outlives the Bell Beast (task "post-kill forecast", 2026-10-04; DESIGN §3.5.7, the person's question of
2026-10-04; docs/facts/1.0.30000/post_kill.md).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.post_kill scan <run> [<run> ...] [--json out.json]
    ../scripts/uv.cmd run python -m ssbot.tools.post_kill clears <run> [<run> ...] [--json out.json]
    ../scripts/uv.cmd run python -m ssbot.tools.post_kill cover <run> [<run> ...] [--json out.json]

scan    every kill in the recordings (Bone Beast Control -> Death Broadcast): the boss's state at the kill; what is
        live after it until the harness's next savestate load (train.episode.live_threats: frames, game s); the hero's
        damage events after it (source, game s); drop bells Antic -> Cancel and on which frames; and the attack bells'
        exact-path error after the kill (pogo_targets.simulate from their first frame after the kill, against the
        recorded centre, each sample within the forecast's time slack forecast.DET_SLACK_S).
clears  the eval CLEARs of runs made before the post-kill tail (the episode ended 60 frames after the kill, the
        recording a few frames later): per kill, did a source outlive the recorded frames (the tail would have gone
        on), and would the bells live on the last recorded frame have reached a hero standing still from there (the
        old harness sent zeros after the kill): each simulated to its End Timer (first bounce + 2 s; a drop bell to
        its Submerge, both bounce sides) against her last recorded hurtbox, dropped to the floor when she was in the
        air. The hero's i-frames and her motion in the slow motion are left out (an estimate of the exposure, not a
        replay: what the planner does there is the live run's to show).
cover   every hero contact after a kill (injected hits left out) against the forecast the kill was certified with
        (the last frame before it, the boss alive, 2 s horizon: the kill window and the plan's rollout) and against
        the post-death forecast 3 frames before the contact (support_recall's pairing: box of c or c - 1).
"""
import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

BOSS = "Bone Beast"
DEATH = "Death Broadcast"
SCENE = "Bone_05"
FLOOR_BOX_Y0 = 2.9                  # the hurtbox's bottom on the arena floor (hero box y0, grounded frames)
MAX_AFTER = 2000


def _recordings(runs: list[Path]):
    for run in runs:
        for ev in sorted(run.glob("rec/*/*/*/events.jsonl")):
            yield run, ev.parent


def _events(rec: Path) -> dict:
    out = {"kills": [], "loads": [], "dmg": [], "cancel": []}
    with (rec / "events.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            if '"fsm"' in line and DEATH not in line and '"Cancel"' not in line:
                continue
            if not any(k in line for k in ('"fsm"', '"harness"', '"damage"', '"damage_blocked"', '"scene_leave"')):
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            k, d, f = e.get("kind"), e.get("data") or {}, e.get("frame") or 0
            if k == "fsm" and d.get("to") == DEATH and str(d.get("obj", "")).startswith(BOSS):
                out["kills"].append((f, d.get("from")))
            elif k == "fsm" and d.get("to") == "Cancel":
                out["cancel"].append((f, d.get("obj"), d.get("from")))
            elif (k == "harness" and d.get("op") == "savestate.load") or k == "scene_leave":
                # the end of the room's frames: a savestate load reloads Bone_05 itself (scene_leave a dozen frames
                # before the harness logs the load), so the scene name does not tell
                out["loads"].append(f)
            elif k in ("damage", "damage_blocked"):
                out["dmg"].append((f, k, str(d.get("source")), d.get("amount")))
    return out


def _kind(src: str) -> str:
    return "atk_bell" if "AtkBell" in src else "drop_bell" if "DropBell" in src else \
        "body" if BOSS in src else "injected" if "Hornet" in src else src


def _path_error(spec, samples: list[tuple[float, float, float]], x, y, vx, vy, nb) -> float:
    """Largest distance of the recorded centres from the simulated path, each at its best time inside the forecast's
    time slack band (forecast.DET_SLACK_S: the recorded centre is the last physics step's, up to a step before the
    frame's game time; the forecast places a copy every 0.02 s across the band, whose circles overlap)."""
    from ssbot.combat.forecast import DET_SLACK_S
    from ssbot.combat.pogo_targets import simulate
    if not samples:
        return 0.0
    t = np.array([s[0] for s in samples])
    errs = np.full(len(t), np.inf)
    for dt in np.linspace(min(DET_SLACK_S), max(DET_SLACK_S), 41):
        cx, cy, _ = simulate(spec, x, y, vx, vy, nb, None, np.maximum(t + dt, 0.0))
        errs = np.minimum(errs, np.hypot(cx - [s[1] for s in samples], cy - [s[2] for s in samples]))
    return float(errs.max())


def scan_kill(reader, fk: int, frm: str, end: int, ev: dict, spec_of) -> dict:
    from ssbot.backends.oracle_backend import entity_pos
    from ssbot.train.encounters import BELL_BEAST
    from ssbot.train.episode import live_threats
    g = 0.0
    live: dict = {}
    bells: dict = {}             # attack bell iid -> (start state, [(t, x, y)])
    last_f, last_threat_g = fk, None
    for s in reader.states(fk, end, keys=("dt", "ents", "game")):
        f = s["f"]
        if (s.get("game") or {}).get("scene") != SCENE:
            break
        if f > fk:
            g += s.get("dt") or 0.0
        last_f = f
        types = live_threats(s.get("ents"), BELL_BEAST.tail_armed)
        if types:
            last_threat_g = g
        for tk in types:
            a = live.setdefault(tk, {"f0": f - fk, "g0": round(g, 4)})
            a["f1"], a["g1"] = f - fk, round(g, 4)
        if f <= fk:
            continue
        for e in s.get("ents") or ():
            tk = e.get("type_key") or ""
            if "AtkBell" not in tk or e.get("hidden"):
                continue
            st = ((e.get("fsms") or [{}])[0] or {}).get("state")
            sp = spec_of(tk)
            if sp is None or st not in sp.states:
                continue
            px, py = entity_pos(e)
            b = bells.setdefault(e["iid"], {"tk": tk, "g0": g, "state0": st, "x": px, "y": py,
                                            "v": tuple((e.get("vel") or (0.0, 0.0))[:2]), "nb": sp.next_bounce.get(st, 0),
                                            "samples": []})
            b["samples"].append((g - b["g0"], px, py))
    errs = []
    for b in bells.values():
        sp = spec_of(b["tk"])
        errs.append(round(_path_error(sp, b["samples"], b["x"], b["y"], b["v"][0], b["v"][1], b["nb"]), 4))
    hits = [{"df": f - fk, "kind": k, "source": src, "src_kind": _kind(src), "amount": a}
            for f, k, src, a in ev["dmg"] if fk <= f <= last_f]
    return {"fk": fk, "from": frm, "frames": last_f - fk, "game_s": round(g, 4), "live": live,
            "last_threat_g": None if last_threat_g is None else round(last_threat_g, 4),
            "live_at_end": last_threat_g is not None and live and max(v["f1"] for v in live.values()) == last_f - fk,
            "atk_path_err": errs, "atk_path_samples": sum(len(b["samples"]) for b in bells.values()), "hits": hits,
            "cancel": [c for c in ev["cancel"] if c[0] == fk]}


def scan(runs: list[Path]) -> dict:
    from ssbot.combat.pogo_targets import TargetTracker
    from ssbot.record.recorder import RecordingReader
    spec_of = TargetTracker().spec_of
    rows = []
    cancels, cancel_at_kill = 0, 0
    for run, rec in _recordings(runs):
        ev = _events(rec)
        kf = {f for f, _ in ev["kills"]}
        cancels += len(ev["cancel"])
        cancel_at_kill += sum(1 for c in ev["cancel"] if c[0] in kf)
        if not ev["kills"]:
            continue
        reader = RecordingReader(rec)
        for fk, frm in ev["kills"]:
            end = min([x for x in ev["loads"] if x > fk] + [fk + MAX_AFTER]) - 1
            r = scan_kill(reader, fk, frm, end, ev, spec_of)
            r["rec"] = str(rec)
            r["run"] = run.name
            rows.append(r)
    by_from = defaultdict(Counter)
    for r in rows:
        by_from[r["from"]][" + ".join(sorted(k.split(" (")[0] for k in r["live"])) or "-"] += 1
    hits = Counter((h["src_kind"], h["kind"]) for r in rows for h in r["hits"])
    body = sorted(h["df"] for r in rows for h in r["hits"] if h["src_kind"] == "body")
    errs = sorted(e for r in rows for e in r["atk_path_err"])
    summ = {"kills": len(rows), "live_after_kill_by_state": {k: dict(v) for k, v in by_from.items()},
            "post_kill_damage_events": {f"{a}/{b}": n for (a, b), n in hits.items()},
            "body_contact_frames_max": body[-1] if body else None,
            "atk_bells_followed": len(errs), "atk_path_err_max_u": errs[-1] if errs else None,
            "atk_path_err_p99_u": errs[int(0.99 * (len(errs) - 1))] if errs else None,
            "cancel_transitions": cancels, "cancel_on_kill_frames": cancel_at_kill,
            "frames_after_kill_max": max((r["frames"] for r in rows), default=None)}
    return {"summary": summ, "kills": rows}


def _hits_standing(spec, x, y, vx, vy, nb, life, box, sides=(0,)) -> float | None:
    """Game s from now when a bell on this path first meets the box (circle vs AABB), None: never in its life."""
    from ssbot.combat.pogo_targets import simulate
    tk = np.arange(0, int(math.ceil((life if life is not None else 3.5) / 0.01)) + 1) * 0.01
    first = None
    for sd in sides:
        cx, cy, ok = simulate(spec, x, y, vx, vy, nb, life, tk, side=sd)
        dx = np.maximum(np.maximum(box[0] - cx, cx - box[2]), 0.0)
        dy = np.maximum(np.maximum(box[1] - cy, cy - box[3]), 0.0)
        hit = np.flatnonzero(ok & (dx * dx + dy * dy <= spec.r * spec.r))
        if len(hit):
            t = float(tk[hit[0]])
            first = t if first is None else min(first, t)
    return first


def clears(runs: list[Path]) -> dict:
    """Past eval CLEARs: the tail they would have had, and the standing hero's exposure (module docstring)."""
    from ssbot.backends.oracle_backend import entity_pos
    from ssbot.combat.pogo_targets import TargetTracker
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.combat_run import load_attempts
    from ssbot.tools.postmortem import find_recording
    from ssbot.train.encounters import BELL_BEAST
    from ssbot.train.episode import live_threats
    spec_of = TargetTracker().spec_of
    out = []
    readers: dict = {}
    for run in runs:
        for row in load_attempts(run):
            if row.get("unit") != "BellBeast" or row.get("mode") != "eval" or row.get("outcome") != "CLEAR" \
                    or not row.get("recording"):
                continue
            rec = find_recording(run, row)
            if not (rec / "events.jsonl").is_file():
                continue
            if rec not in readers:
                readers.clear()
                readers[rec] = (RecordingReader(rec), _events(rec))
            reader, ev = readers[rec]
            kills = [(f, s) for f, s in ev["kills"] if (row.get("f_wake") or 0) <= f <= (row.get("f_end") or 0)]
            if not kills:
                continue
            fk, frm = kills[0]
            end = min([x for x in ev["loads"] if x > fk] + [fk + MAX_AFTER]) - 1
            first_bounce: dict = {}
            g = 0.0
            last = None
            for s in reader.states(fk, end, keys=("dt", "ents", "game", "hero")):
                if (s.get("game") or {}).get("scene") != SCENE:
                    break
                if s["f"] > fk:
                    g += s.get("dt") or 0.0
                for e in s.get("ents") or ():
                    st = ((e.get("fsms") or [{}])[0] or {}).get("state")
                    if st == "First Bounce" and e["iid"] not in first_bounce:
                        first_bounce[e["iid"]] = g
                last = (s, g)
            if last is None:
                continue
            s, g_end = last
            live = live_threats(s.get("ents"), BELL_BEAST.tail_armed)
            hero = s.get("hero") or {}
            box = list((hero.get("box") or [0, 0, 0, 0])[:4])
            if box[1] > FLOOR_BOX_Y0 + 0.05:
                box = [box[0], FLOOR_BOX_Y0, box[2], FLOOR_BOX_Y0 + (box[3] - box[1])]
            t_hit = None
            srcs = []
            for e in s.get("ents") or ():
                tk = e.get("type_key") or ""
                if tk not in live:
                    continue
                sp = spec_of(tk)
                st = ((e.get("fsms") or [{}])[0] or {}).get("state")
                if sp is None or st not in sp.next_bounce:
                    srcs.append(tk)
                    continue
                nb = sp.next_bounce[st]
                life = None
                if sp.life_after_first_s is not None and nb >= 1:
                    fb = first_bounce.get(e["iid"])
                    life = (sp.life_after_first_s - (g_end - fb)) if fb is not None else sp.life_after_first_s
                elif sp.life_after_first_s is not None:
                    life = 1.2 + sp.life_after_first_s     # lands within ~0.9 s of the launch, then the timer
                sides = (1, -1) if nb < len(sp.bounces) and sp.bounces[nb].get("vx") == "random" else (0,)
                (x, y), (vx, vy) = entity_pos(e), (e.get("vel") or (0.0, 0.0))[:2]
                t = _hits_standing(sp, x, y, vx, vy, nb, life, box, sides)
                srcs.append(tk)
                if t is not None:
                    t_hit = t if t_hit is None else min(t_hit, t)
            out.append({"run": run.name, "instance": row.get("instance"), "episode": row.get("episode"),
                        "from": frm, "recorded_after_kill_f": s["f"] - fk, "recorded_game_s": round(g_end, 3),
                        "live_at_end": sorted(srcs), "standing_hit_in_s": None if t_hit is None else round(t_hit, 3),
                        "min_hp": row.get("min_hp"), "hp_end": hero.get("health")})
    n = len(out)
    live = [r for r in out if r["live_at_end"]]
    hit = [r for r in out if r["standing_hit_in_s"] is not None]
    summ = {"clears": n, "live_source_at_window_end": len(live),
            "by_state": dict(Counter(r["from"] for r in live)),
            "standing_hero_hit": len(hit),
            "standing_hit_at_h2_or_less": sum(1 for r in hit if (r.get("hp_end") or 5) <= 3),
            "standing_hit_lethal": sum(1 for r in hit if (r.get("hp_end") or 5) <= 2)}
    return {"summary": summ, "clears": out}


def cover(runs: list[Path], lag: int = 3, horizon_s: float = 2.0) -> dict:
    """Every hero contact after a kill (damage frames, damage_blocked stretches; injected hits left out) against two
    forecasts of this code: the one the kill was certified with (the last frame before the kill, the boss alive,
    the policy's horizon) and the post-death one `lag` frames before the contact (what the planner dodges with)."""
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.boss_model import BossModel
    from ssbot.combat.forecast import Forecaster, load_planner_templates
    from ssbot.core.bosses import BELL_BEAST as BB
    from ssbot.core.worldstate import ORACLE
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.combat_run import load_attempts
    from ssbot.tools.postmortem import find_recording
    from ssbot.tools.support_recall import contacts_of
    model = BossModel.load("BellBeast")
    fc = Forecaster(model, ORACLE, templates=load_planner_templates(model, 0.0))
    out = []
    for run in runs:
        for row in load_attempts(run):
            if row.get("unit") != "BellBeast" or not row.get("recording") or row.get("f_wake") is None:
                continue
            rec = find_recording(run, row)
            if not (rec / "events.jsonl").is_file():
                continue
            ev = _events(rec)
            kills = [f for f, _ in ev["kills"] if row["f_wake"] <= f <= row["f_end"]]
            if not kills:
                continue
            fk = kills[0]
            reader = RecordingReader(rec)
            cs = {c: src for c, src in contacts_of(reader, fk, row["f_end"]).items() if "Hornet" not in src}
            if not cs:
                continue
            backend = OracleBackend(bosses=[BB])
            fc.reset()
            t_of, box_of, fd = {}, {}, {}
            alive = None
            need = {c - lag for c in cs}
            for s in reader.states(row["f_wake"] - 300, max(cs)):
                ws = backend.feed(s)
                fc.update(ws)
                f = s["f"]
                t_of[f] = ws.stamp.t_game_s
                b = (s.get("hero") or {}).get("box")
                box_of[f] = tuple(b[:4]) if b else None
                if f == fk - 1:
                    alive = (f, fc.forecast(horizon_s))
                if f in need:
                    fd[f] = fc.forecast(1.0)

            def covered(fcast, o: int, c: int) -> bool | None:
                if fcast is None or o not in t_of:
                    return None
                for fr in (c, c - 1):
                    bx = box_of.get(fr)
                    if bx is None or fr not in t_of:
                        continue
                    x, y = 0.5 * (bx[0] + bx[2]), 0.5 * (bx[1] + bx[3])
                    if fcast.occupied(np.array([[x]]), np.array([[y]]), np.array([t_of[fr] - t_of[o]]))[0, 0]:
                        return True
                return False

            for c, src in sorted(cs.items()):
                dt_alive = None if alive is None else round(t_of.get(c, math.nan) - t_of[alive[0]], 3)
                out.append({"run": run.name, "episode": row.get("episode"), "df": c - fk, "source": src,
                            "src_kind": _kind(src), "alive_dt_s": dt_alive,
                            "alive_covered": None if alive is None or dt_alive is None or dt_alive > horizon_s
                            else covered(alive[1], alive[0], c),
                            "post_covered": covered(fd.get(c - lag), c - lag, c)})
    by = defaultdict(Counter)
    for r in out:
        by[r["src_kind"]][f"alive {r['alive_covered']} / post {r['post_covered']}"] += 1
    return {"summary": {"contacts": len(out), "by_source": {k: dict(v) for k, v in by.items()}}, "contacts": out}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("scan", "clears", "cover"))
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--glob", default=None, help="the runs are parent directories: take their subdirectories "
                                                 "matching this pattern (e.g. '*_BellBeast_eval_planner_oracle')")
    a = ap.parse_args(argv)
    runs = [r for p in a.runs for r in sorted(p.glob(a.glob)) if r.is_dir()] if a.glob else a.runs
    res = scan(runs) if a.cmd == "scan" else clears(runs) if a.cmd == "clears" else cover(runs)
    print(json.dumps(res["summary"], indent=1))
    if a.json:
        a.json.write_text(json.dumps(res, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
