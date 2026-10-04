"""Per-attack fight statistics of planner runs (M2 confirmation batches): hits dealt by the hero's attack source in
each boss attack, pogos per charge, hits dealt per burst, and the hits taken by the attack they came in.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.fight_stats C:/ssbot/data/runs/m2/<run> [<run> ...] [--json out.json]
        [--keys]

--keys adds the key economy section (ssbot.tools.key_economy.group: presses per second, plan change rate, decision
lead, flips), one entry per view (the runs' config.json "view"); the person's fight is in key_economy's own output.

Sources: the recordings' "hit" events (the hero's hits on the boss, data.src: Slash / AltSlash / UpSlash / DownSpike
/ Needle Damage ...), the attempts' hits_taken frames, and the decision logs (SSBOT_LOG_ALL=1: every tick) for the
boss's state at a frame: the Control state in the oracle view, the observable phase in the vision view, both mapped to
the attack groups below. Attack counts come from AttemptRecord.attacks (Control state entries).
"""
import argparse
import bisect
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

GROUPS = {
    "charge": ("Emerge Antic C", "Charge Emerge", "Charge Antic", "Charge", "emerge", "charge_antic", "charge",
               "dust_low"),
    "charge_end": ("Charge End",),
    "leap": ("Emerge Antic L", "Leap Out", "Descending", "leap", "dust_tall"),
    "leap_land": ("Leap Land",),
    "dig_in": ("Dig In",),
    "recover": ("recover",),
    "burst": ("Burst Pos", "Burst Antic", "Fire Bells", "Burst Out", "burst", "dust_burst", "burst_tell"),
    "burst_recovery": ("Burst Recovery",),
    "rage": ("Rage Pos", "Rage Antic", "Rage Burst", "Rage Roar", "Roar End", "roar", "roar_end"),
    "underground": ("Submerged", "Submerged Init", "Rage Submerge", "Rage Rumble", "Ptn L", "Ptn R", "hidden", "dust"),
}
GROUP_OF = {s: g for g, ss in GROUPS.items() for s in ss}


def state_index(run: Path, inst: str) -> tuple[list[int], list[str | None]]:
    fs, st = [], []
    p = run / f"decisions_i{inst}.jsonl"
    if p.exists():
        for line in p.open():
            d = json.loads(line)
            fs.append(d["f"])
            st.append(d.get("boss_state"))
    return fs, st


def at(fs: list[int], st: list, f: int, tol: int = 6):
    j = bisect.bisect_right(fs, f) - 1
    return st[j] if j >= 0 and f - fs[j] <= tol else None


def collect(runs: list[Path]) -> dict:
    dealt = Counter()
    taken = Counter()
    tinks = Counter()
    taken_src = Counter()
    attacks = Counter()
    episodes = 0
    for run in runs:
        for ap in sorted(run.glob("attempts_i*.jsonl")):
            inst = ap.stem.split("_i")[1]
            fs, st = state_index(run, inst)
            for line in ap.open():
                a = json.loads(line)
                if a.get("outcome") == "HARNESS_FAIL":
                    continue
                episodes += 1
                for k, v in (a.get("attacks") or {}).items():
                    attacks[k] += v
                srcs = list((a.get("hit_sources") or {}).keys())
                for f in (a.get("policy") or {}).get("hits_taken") or ():
                    g = GROUP_OF.get(at(fs, st, f), "other")
                    taken[g] += 1
                    for s in srcs:
                        taken_src[(g, s)] += 1
            for ev_p in run.glob(f"rec/*/*/i{inst}_*/events.jsonl"):
                for line in ev_p.open():
                    if '"fsm"' in line and "DropBell" in line and '"to": "Tink' in line:
                        # a hit on a drop bell (no HealthManager, no hit event): its FSM's Tink state, Right / Left
                        # from a side slash (the redirect), D from a down attack (a pogo off it)
                        to = json.loads(line)["data"].get("to", "")
                        tinks["side" if ("Right" in to or "Left" in to or " R " in to or " L " in to) else "down"] += 1
                        continue
                    if '"hit"' not in line:
                        continue
                    e = json.loads(line)
                    d = e.get("data") or {}
                    if e.get("kind") != "hit" or d.get("type_key") != "Bone Beast":
                        continue
                    s = at(fs, st, e["frame"])
                    if s is None:
                        continue
                    dealt[(GROUP_OF.get(s, "other"), d.get("src"))] += 1
    charges = attacks.get("Charge Antic", 0)
    p2 = attacks.get("Rage Antic", 0)
    bursts = attacks.get("Burst Antic", 0)
    leaps = attacks.get("Leap Out", 0)
    pogos = sum(v for (g, src), v in dealt.items() if g in ("charge", "charge_end") and "Down" in str(src))
    out = {"episodes": episodes, "attacks": dict(attacks),
           "hits_dealt": {f"{g}/{src}": v for (g, src), v in sorted(dealt.items(), key=lambda kv: (kv[0][0], -kv[1]))},
           "hits_taken_by_group": dict(taken), "hits_taken_by_group_source": {f"{g}/{s}": v for (g, s), v in
                                                                           taken_src.items()},
           "pogos_per_charge": round(pogos / charges, 3) if charges else None,
           "hits_dealt_per_burst": round(sum(v for (g, _), v in dealt.items() if g == "burst") / bursts, 3)
           if bursts else None,
           "hits_dealt_per_leap_in_air": round(sum(v for (g, _), v in dealt.items() if g == "leap") / leaps, 3)
           if leaps else None,
           "drop_bell_tinks": dict(tinks), "p2_fights": p2,
           "drop_bell_side_hits_per_p2_fight": round(tinks.get("side", 0) / p2, 3) if p2 else None,
           "hits_taken_in_charges": taken.get("charge", 0) + taken.get("charge_end", 0),
           "hits_taken_in_bursts": taken.get("burst", 0) + taken.get("burst_recovery", 0)}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--keys", action="store_true", help="add the key economy section, per view")
    a = ap.parse_args(argv)
    out = collect(a.runs)
    if a.keys:
        from ssbot.tools.key_economy import group
        views: dict[str, list[Path]] = {}
        for r in a.runs:
            cfg = r / "config.json"
            v = json.loads(cfg.read_text("utf-8")).get("view", "?") if cfg.exists() else "?"
            views.setdefault(v, []).append(r)
        out["keys"] = {v: group(rs) for v, rs in views.items()}
        for g in out["keys"].values():
            g.pop("_episodes", None)              # per-episode safety rows (key_economy --json keeps them)
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
