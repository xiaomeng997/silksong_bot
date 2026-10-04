"""The slow motion a kill starts, measured from recordings (task "STUCK at 15 HP" fixer round, 2026-10-04; DESIGN
§3.7.2 I3, §3.7.3): per freeze type a death starts (BossDeathSlow, EnemyBattleEndSlow, BigEnemyDeathSlow, EnemyDeath
...), how much game time and real time pass from the killing hit to the first pausable frame. The killing-blow rule
(combat.safety_filter.kill_certified) certifies a kill only when the hero's plan stays out of the support for that
much game time after the latest killing hit (plus a margin), so the window has to be the one of the kill's own kind.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.kill_window <run or recording dir> [...] [--json out.json]
        [--per-type 400] [--write-knowledge]

Per freeze start of a death type (event "freeze", phase "start", type ending in "DeathSlow" / "BattleEndSlow" or
"EnemyDeath"): the killing hit is the last "hit" event with dead = true (or hp_after <= 0) at most KILL_LOOKBACK frames
before it (none: the freeze start frame, flagged no_hit); G is the first STATE frame after the start with pause.blk 0
and the game not paused, and the first pausable frame is G + 1 (the time scale comes back in the freeze's coroutine,
after InputHandler's Update: docs/facts/1.0.30000/pause_quit.md 7.2). game_s = sum of STATE dt over (hit, G + 1],
real_s = sum of udt, frames = G + 1 - hit. Censored (not counted): a harness operation other than a savestate load /
randomized start inside the window, a pause, a scene change, or no open gate within MAX_F frames. A savestate load
inside the window (every Bell Beast eval kill: the harness reloads 77 frames after it, in the slow motion) does not
censor it: the FreezeMoment runs on unscaled time, the load's frame carries its 0.29 s of udt and udt x ts of dt, and
the slow motion goes on in the reloaded room (quit_map: TIME_SLOWED "entry" frames), so the integral is the same; such
windows are flagged harness_inside.
Damage scaling (HealthManager.ApplyDamageScaling, a per-enemy LevelNMult by nailUpgrades, rounded): every "hit" event
gives dealt (the attacker's HitInstance.DamageDealt) and dmg (the HP the target lost; the hp clamp at -1000 never
bites). Only the hero's needle-damage hits count: attack "Nail" or "Heavy" (the Silkspear) with dealt equal to the
plain swing's nailDamage or the Silkspear's 3 x nailDamage at the recording's needle level (NEEDLE_BY_SCENE: the M2
saves, Bell Beast nailUpgrades 0, the Forum's fo_A 1, docs/facts/1.0.30000/forum.md); the helper's and the Cogfly's
hits are "Generic", and the fixed 5 damagers scale at level -1 (x 1). Per enemy type and level the multiplier's
upper bound is min over those hits of (dmg + 0.5) / dealt (m_sup), its lower bound max of (dmg - 0.5) / dealt.
--write-knowledge writes knowledge/1.0.30000/kill_windows.json: per type n / max / p99 of game_s and real_s and the
encounters (scenes) it was seen in; ENCOUNTER_SCENES maps an encounter to its scene.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

KILL_LOOKBACK = 8
BENIGN_OPS = ("savestate.load", "randomize_start")
MAX_F = 600
DEATH_SUFFIX = ("DeathSlow", "BattleEndSlow")
DEATH_TYPES = ("EnemyDeath",)
ENCOUNTER_SCENES = {"BellBeast": ("Bone_05",), "Forum": ("Hang_04",)}
NEEDLE_BY_SCENE = {"Bone_05": 0, "Hang_04": 1}       # the M2 saves' nailUpgrades
NEEDLE_DAMAGE = (5, 9, 13, 17, 21)
KNOWLEDGE = Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "kill_windows.json"


def recordings(paths: list[Path]):
    for p in paths:
        if (p / "events.jsonl").is_file():
            yield p
            continue
        yield from sorted(x.parent for x in p.glob("rec/*/*/*/events.jsonl"))


def is_death(t: str | None) -> bool:
    return bool(t) and (t.endswith(DEATH_SUFFIX) or t in DEATH_TYPES)


def scan(rec: Path, per_type: int, counts: dict, pairs: dict | None = None) -> list[dict]:
    from ssbot.record.recorder import RecordingReader
    starts, kills, harness = [], [], []
    with (rec / "events.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            if '"freeze"' not in line and '"hit"' not in line and '"harness"' not in line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            k, d, fr = e.get("kind"), e.get("data") or {}, e.get("frame") or 0
            if k == "freeze" and d.get("phase", "start") == "start" and is_death(d.get("type")):
                starts.append((fr, d.get("type"), d))
            elif k == "hit":
                num = isinstance(d.get("dealt"), (int, float)) and isinstance(d.get("dmg"), (int, float))
                if pairs is not None and num and not d.get("crit") and d["dealt"] > 0 \
                        and d.get("attack") in ("Nail", "Heavy"):
                    key = (str(d.get("type_key")), int(d["dealt"]), int(d["dmg"]))
                    pairs[key] = pairs.get(key, 0) + 1
                if d.get("dead") or (isinstance(d.get("hp_after"), (int, float)) and d["hp_after"] <= 0):
                    kills.append((fr, d.get("type_key"), d.get("src")))
            elif k == "harness":
                harness.append((fr, d.get("op")))
    r = RecordingReader(rec)
    out = []
    kills_f = np.array([k[0] for k in kills], np.int64)
    harness_f = np.array(sorted(f for f, op in harness if op not in BENIGN_OPS), np.int64)
    benign_f = np.array(sorted(f for f, op in harness if op in BENIGN_OPS), np.int64)
    for f0, typ, d in starts:
        if counts[typ] >= per_type:
            continue
        i = np.searchsorted(kills_f, f0, side="right") - 1
        hit = kills[i] if i >= 0 and f0 - kills_f[i] <= KILL_LOOKBACK else None
        h = hit[0] if hit else f0
        rows = list(r.states(h, h + MAX_F, keys=("dt", "udt", "ts", "pause", "game")))
        g, scene, cens = None, None, None
        for s in rows:
            game = s.get("game") or {}
            scene = scene or game.get("scene")
            if game.get("paused"):
                cens = "paused"
                break
            if game.get("scene") and scene and game.get("scene") != scene:
                cens = "scene change"
                break
            if s["f"] > f0 and int((s.get("pause") or {}).get("blk") or 0) == 0:
                g = s["f"]
                break
        if g is None and cens is None:
            cens = "no open gate"
        if g is not None and len(harness_f) and ((harness_f >= h) & (harness_f <= g + 2)).any():
            cens = "harness"
        inside = bool(g is not None and len(benign_f) and ((benign_f >= h) & (benign_f <= g + 2)).any())
        rec_row = {"rec": str(rec), "type": typ, "f_hit": h, "f_start": f0, "no_hit": hit is None,
                   "victim": hit[1] if hit else None, "src": hit[2] if hit else None, "scene": scene,
                   "preset": [d.get("down"), d.get("wait"), d.get("up"), d.get("speed")], "censored": cens,
                   "harness_inside": inside}
        if cens is None:
            by_f = {s["f"]: s for s in rows}
            win = [by_f[f] for f in range(h + 1, g + 2) if f in by_f]
            rec_row.update(g=g, frames=g + 1 - h, game_s=round(sum(float(s.get("dt") or 0.0) for s in win), 5),
                           real_s=round(sum(float(s.get("udt") or 0.0) for s in win), 4),
                           missing=(g + 1 - h) - len(win))
            counts[typ] += 1
        out.append(rec_row)
    return out


def first_scene(rec: Path) -> str | None:
    from ssbot.record.recorder import RecordingReader
    for s in RecordingReader(rec).states(None, None, keys=("game",)):
        sc = (s.get("game") or {}).get("scene")
        if sc:
            return sc
    return None


def summarise(rows: list[dict], kills_only: bool = True) -> dict:
    """Per freeze type, the measured windows; kills_only: only those a hero's killing hit started (EnemyDeath also
    comes with the hero's own damage hit-stop in these recordings, never within KILL_LOOKBACK of a kill)."""
    by = defaultdict(list)
    for x in rows:
        if x.get("censored") is None and not (kills_only and x["no_hit"]):
            by[x["type"]].append(x)
    out = {}
    for typ, xs in sorted(by.items()):
        g = np.array([x["game_s"] for x in xs])
        rl = np.array([x["real_s"] for x in xs])
        fr = np.array([x["frames"] for x in xs])
        out[typ] = {"n": len(xs), "game_s_max": round(float(g.max()), 4), "game_s_p99": round(float(np.percentile(g, 99)), 4),
                    "game_s_p50": round(float(np.percentile(g, 50)), 4), "game_s_min": round(float(g.min()), 4),
                    "real_s_max": round(float(rl.max()), 4), "real_s_p50": round(float(np.percentile(rl, 50)), 4),
                    "frames_max": int(fr.max()), "frames_min": int(fr.min()),
                    "no_hit": sum(x["no_hit"] for x in xs),
                    "scenes": sorted({x["scene"] for x in xs if x.get("scene")}),
                    "victims": sorted({str(x["victim"]) for x in xs if x.get("victim")})[:20],
                    "censored": sum(1 for y in rows if y["type"] == typ and y.get("censored")),
                    "harness_inside": sum(bool(x.get("harness_inside")) for x in xs)}
    return out


def scaling(pairs: dict) -> dict:
    """Per (enemy type, needle level): the bound on its damage-scaling multiplier, from every needle-damage (dealt,
    dmg) pair: dmg = RoundToInt(dealt * m) gives m < (dmg + 0.5) / dealt and m > (dmg - 0.5) / dealt."""
    out: dict = {}
    for (lv, tk, dealt, dmg), n in sorted(pairs.items()):
        nd = NEEDLE_DAMAGE[lv]
        if dealt not in (nd, 3 * nd):
            continue
        x = out.setdefault(tk, {}).setdefault(str(lv), {"m_sup": float("inf"), "m_inf": 0.0, "n": 0, "pairs": {}})
        x["m_sup"] = min(x["m_sup"], (dmg + 0.5) / dealt)
        x["m_inf"] = max(x["m_inf"], (dmg - 0.5) / dealt)
        x["n"] += n
        x["pairs"][f"{dealt}->{dmg}"] = n
    for v in out.values():
        for x in v.values():
            x["m_sup"], x["m_inf"] = round(x["m_sup"], 5), round(x["m_inf"], 5)
    return out


def knowledge(summary: dict, sources: list[str], scal: dict | None = None) -> dict:
    enc = {}
    for name, scenes in ENCOUNTER_SCENES.items():
        enc[name] = sorted(t for t, v in summary.items() if set(v["scenes"]) & set(scenes))
    return {"about": "game time from the killing hit to the first pausable frame (G + 1), per freeze type a hero's "
                     "killing hit started; built by ssbot.tools.kill_window (combat.safety_filter.KillKnowledge "
                     "reads it)",
            "kinds": {t: {k: v[k] for k in ("n", "game_s_max", "game_s_p99", "game_s_p50", "real_s_max",
                                             "frames_max", "scenes")} for t, v in summary.items()},
            "encounters": enc, "sources": sources,
            "scaling_about": "HealthManager.ApplyDamageScaling multiplier per enemy type_key and needle level "
                             "(nailUpgrades): m_sup = min over the recorded non-critical hits of (dmg + 0.5) / dealt",
            "scaling": scal or {}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", type=Path, nargs="+")
    ap.add_argument("--per-type", type=int, default=400, help="at most this many measured windows per type")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--write-knowledge", action="store_true")
    a = ap.parse_args(argv)
    counts: dict = defaultdict(int)
    rows = []
    srcs = []
    pairs: dict = {}
    for rec in recordings(a.paths):
        mine: dict = {}
        got = scan(rec, a.per_type, counts, mine)
        scene = next((x["scene"] for x in got if x.get("scene")), None) or first_scene(rec)
        lv = NEEDLE_BY_SCENE.get(scene)
        if lv is not None:
            for k, n in mine.items():
                pairs[(lv, *k)] = pairs.get((lv, *k), 0) + n
        if got:
            srcs.append(str(rec))
        rows.extend(got)
        print(f"{rec}: {len(got)} death freezes, measured so far {dict(counts)}", flush=True)
    summ = summarise(rows)
    other = summarise(rows, kills_only=False)
    scal = scaling(pairs)
    print(json.dumps(summ, indent=1))
    print("all death-type freezes, kills or not:", json.dumps({k: {kk: v[kk] for kk in ("n", "no_hit", "game_s_max",
                                                                                          "game_s_p99")}
                                                                for k, v in other.items()}))
    print(json.dumps({k: {lv: {kk: x[kk] for kk in ("m_sup", "m_inf", "n")} for lv, x in v.items()}
                      for k, v in scal.items()}, indent=1))
    if a.json:
        a.json.write_text(json.dumps({"summary": summ, "all": other, "scaling": scal, "rows": rows}, indent=1),
                          "utf-8")
    if a.write_knowledge:
        KNOWLEDGE.write_text(json.dumps(knowledge(summ, srcs, scal), indent=1) + "\n", "utf-8")
        print(f"wrote {KNOWLEDGE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
