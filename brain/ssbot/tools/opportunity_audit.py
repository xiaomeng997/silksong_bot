"""Hindsight opportunity audit: at sampled decision frames of recorded fights, which attack options would have hit
the boss's ACTUAL future hurtbox and stayed clear of everything that actually hurt, against what the bot did. The
attack-outcome audit (predict_audit) checks only the chosen plan; this one finds the better plans not taken.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.opportunity_audit C:/ssbot/data/runs/m2/<run> [...] [--every 12]
        [--episodes 20] [--json out.json]
    ../scripts/uv.cmd run python -m ssbot.tools.opportunity_audit --human C:/ssbot/data/human/20260930_210337
        --frames 64275 68397                       # the person's hits per boss attack (hp drops), the benchmark

Per sampled frame (every `every` frames while the boss has an enabled collider within 9 u of the hero): the hero's
kinematic state from the recording (StateTracker, as the planner starts from it), the 2 frames of masks already sent
(the action latency), then each option of the planner's attack space over 48 frames, nominal lane (_options: side /
up / down attacks with the side key towards, away or none, no jump or holds 6 / 11 / 24, press frames, the down
attack's second press after a bounce, the Silkspear). Attacks are scored as the planner scores them (planner.
_attacks_of, its windows) against the boss's recorded future (its collider box per frame, the polygon of now moved
with it); a down hit is re-rolled with the bounce for the chain. An option is safe when none of its hero boxes meets
an enabled damaging collider of any entity recorded for that frame (hindsight: the real future, not the support).
The bot's outcome is the recorded hit events in the same 48 frames. A missed opportunity: some safe option hits, the
bot dealt none; the winning combinations are listed per boss attack group (fight_stats groups).
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

T = 48


def _polys(e: dict) -> list[np.ndarray]:
    return [np.asarray(c["verts_world"], float).reshape(-1, 2) for c in e.get("colliders") or () if c.get("enabled")]


def _meets(rect, polys) -> bool:
    from ssbot.combat.planner import _rect_meets_polys
    if not polys:
        return False
    flat = np.concatenate(polys)
    starts = np.cumsum([0] + [len(q) for q in polys]).astype(np.int64)
    return bool(_rect_meets_polys(rect[0], rect[1], rect[2], rect[3], flat, starts, 0.0, 0.0))


def _options(face: int) -> dict:
    """The planner's attack space around now: side and up slashes and down attacks with the side key towards the boss,
    away or none, after no jump or a jump held 6 / 11 / 24 frames, pressed 0 / 6 / 12 frames in (down: 4-20 frames,
    with a second down press 22 frames after the first: the chain after a bounce), and the Silkspear."""
    from ssbot.knowledge.kinematics import B_ATTACK, B_DOWN, B_JUMP, B_LEFT, B_QUICKCAST, B_RIGHT, B_UP
    toward = B_RIGHT if face > 0 else B_LEFT
    away = B_LEFT if face > 0 else B_RIGHT
    opts = {}
    for dn, key in (("toward", toward), ("away", away), ("none", 0)):
        for kind in ("side", "up", "down"):
            holds = (6, 11, 24) if kind == "down" else (0, 6, 11, 24)
            presses = (4, 8, 12, 16, 20) if kind == "down" else (0, 6, 12)
            for hold in holds:
                for pr in presses:
                    m = np.zeros(T, np.int64)
                    m[:hold] |= B_JUMP
                    m[pr:] |= key
                    extra = B_UP if kind == "up" else (B_DOWN if kind == "down" else 0)
                    if kind == "up" and not key:
                        continue                        # an up edge alone starts an interaction
                    for p2 in ((pr, pr + 22) if kind == "down" else (pr,)):
                        if p2 + 4 < T:
                            m[p2:p2 + 6] |= extra
                            m[p2 + 1:p2 + 4] |= B_ATTACK
                    opts[f"{kind}|{dn}|hold{hold}|press{pr}"] = m
    m = np.zeros(T, np.int64)
    m[0:3] = toward | B_QUICKCAST
    opts["spear|toward|hold0|press0"] = m
    return opts


def audit_run(run: Path, every: int, episodes: int) -> dict:
    from ssbot.combat import planner as pl
    from ssbot.knowledge import kinematics as kin
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.fight_stats import GROUP_OF
    from ssbot.tools.postmortem import episode_rows, find_recording
    from ssbot.train.encounters import BELL_BEAST
    params = kin.HeroParams.load()
    win = pl.WINDOWS["v2"]
    stats = defaultdict(Counter)
    wins = defaultdict(Counter)
    lanes_ok = defaultdict(Counter)
    samples = 0
    for ap in sorted(run.glob("attempts_i*.jsonl")):
        inst = int(ap.stem.split("_i")[1])
        for row in episode_rows(run, inst)[:episodes]:
            if not row.get("recording") or row.get("outcome") == "HARNESS_FAIL":
                continue
            r = RecordingReader(find_recording(run, row))
            terrain = kin.Terrain2D.empty()
            for _, msg in r.terrain():
                if msg.get("scene_raw") == BELL_BEAST.scene:
                    terrain = kin.Terrain2D.from_message(msg, params.scene(BELL_BEAST.scene))
            states = list(r.states(row["f_end"] - row["acts"], row["f_end"]))
            hits = sorted(e["frame"] for e in r.events() if e.get("kind") == "hit"
                          and (e.get("data") or {}).get("type_key") == "Bone Beast")
            trk = kin.StateTracker(params, terrain)
            for n, s in enumerate(states):
                trk.push(s)
                if n % every or n + T + 3 >= len(states):
                    continue
                boss = next((e for e in s.get("ents") or () if e.get("type_key") == "Bone Beast"), None)
                hb = (s.get("hero") or {}).get("box")
                if boss is None or not hb or not _polys(boss):
                    continue
                hx = 0.5 * (hb[0] + hb[2])
                if abs(boss["pos"][0] - hx) > 9.0:
                    continue
                try:
                    start = trk.state().copy()
                except Exception:
                    continue
                st = (boss.get("fsms") or [{}])[0].get("state")
                group = GROUP_OF.get(st, "other")
                face = 1 if boss["pos"][0] >= hx else -1
                fut = states[n:n + T + 3]
                # the boss's recorded future: per frame its enabled colliders' box (the polygon of now moved with it)
                bbox = np.zeros((T + 3, 4))
                okb = np.zeros(T + 3, np.bool_)
                dmg = []
                for j, sj in enumerate(fut):
                    bj = next((e for e in sj.get("ents") or () if e.get("type_key") == "Bone Beast"), None)
                    pj = _polys(bj) if bj else []
                    if pj:
                        v = np.concatenate(pj)
                        bbox[j] = (v[:, 0].min(), v[:, 1].min(), v[:, 0].max(), v[:, 1].max())
                        okb[j] = True
                    dmg.append([np.asarray(c2["verts_world"], float).reshape(-1, 2) for e in sj.get("ents") or ()
                                for c2 in e.get("colliders") or ()
                                if c2.get("enabled") and (c2.get("damage") or {}).get("dealt")])
                p0 = _polys(boss)
                flat = np.concatenate(p0)
                starts = np.cumsum([0] + [len(q) for q in p0]).astype(np.int64)
                base = np.array([bbox[0, 0], bbox[0, 1]])
                pre = np.array([((fut[k] if k < len(fut) else {}).get("act") or {}).get("mask", 0) or 0
                                for k in (1, 2)], np.int64)
                opts = _options(face)
                names = list(opts)
                cmd = np.stack([np.concatenate([pre, opts[k]])[:T] for k in names])
                latched, _ = kin.hold_filter(cmd, kin.HoldState.idle(len(cmd)))
                roll = kin.rollout(start, latched, params, terrain)
                samples += 1
                best, best_name = 0, None
                for c, name in enumerate(names):
                    lst = pl._attacks_of(np.ascontiguousarray(roll.box[c]), np.ascontiguousarray(roll.flags[c]),
                                         np.ascontiguousarray(roll.mode[c]), np.ascontiguousarray(latched[c]), face,
                                         bbox[:T + 1], okb[:T + 1], flat, starts, base, win)
                    nh = sum(1 for _, _, j in lst if j >= 0)
                    first_ds = next((j for kd, _, j in lst if kd == 3 and j >= 0), None)
                    if first_ds is not None:                      # the chain: the bounce, then the second press
                        ev = np.zeros((1, latched.shape[1]), np.int64)
                        ev[0, min(first_ds, latched.shape[1] - 1)] = kin.EV_POGO
                        r2 = kin.rollout(start, latched[c:c + 1], params, terrain, events=ev)
                        lst2 = pl._attacks_of(np.ascontiguousarray(r2.box[0]), np.ascontiguousarray(r2.flags[0]),
                                              np.ascontiguousarray(r2.mode[0]), np.ascontiguousarray(latched[c]),
                                              face, bbox[:T + 1], okb[:T + 1], flat, starts, base, win)
                        nh = max(nh, sum(1 for _, _, j in lst2 if j >= 0))
                        box_c = r2.box[0]
                    else:
                        box_c = roll.box[c]
                    safe = True
                    if nh:
                        for j in range(1, min(len(dmg), box_c.shape[0])):
                            if dmg[j] and _meets(tuple(box_c[j]), dmg[j]):
                                safe = False
                                break
                    kind = name.split("|")[0]
                    stats[(group, kind)]["n_options"] += 1
                    stats[(group, kind)]["safe_hitting"] += int(nh > 0 and safe)
                    if safe and nh > best:
                        best, best_name = nh, name
                if group in ("charge", "charge_end"):
                    # the pogo question: which (hold, press) combinations bounce in EVERY timing lane, head-on (the
                    # boss running at the hero) or from behind (the planner's gate)
                    bvx = (boss.get("vel") or [0, 0])[0]
                    side = "head_on" if bvx and np.sign(bvx) == np.sign(hx - boss["pos"][0]) else "behind"
                    dn = [k for k, nm in enumerate(names) if nm.startswith("down|")]
                    rl = kin.rollout(start, latched[dn], params, terrain, variants="bounds", lanes=True)
                    conn = np.zeros(len(dn), np.bool_)
                    pl._lanes_connect(np.ascontiguousarray(rl.var_box), np.ascontiguousarray(rl.var_flags),
                                      np.ascontiguousarray(rl.var_mode), np.ascontiguousarray(latched[dn]), face,
                                      bbox[:T + 1], okb[:T + 1], flat, starts, base, win, conn)
                    stats[(group, f"pogo_{side}")]["samples"] += 1
                    stats[(group, f"pogo_{side}")]["any_all_lanes"] += int(conn.any())
                    for k in np.flatnonzero(conn):
                        lanes_ok[side][names[dn[k]].split("|", 2)[2]] += 1
                bot = sum(1 for h in hits if fut[0]["f"] <= h <= fut[0]["f"] + T)
                stats[(group, "bot")]["samples"] += 1
                stats[(group, "bot")]["hit_samples"] += int(bot > 0)
                stats[(group, "missed")]["samples"] += 1
                if best > 0 and bot == 0:
                    stats[(group, "missed")]["missed"] += 1
                    wins[group][f"{best_name} ({best} hit{'s' if best > 1 else ''})"] += 1
    return {"samples": samples, "table": {f"{g}/{o}": dict(v) for (g, o), v in sorted(stats.items())},
            "winning_combos": {g: dict(c.most_common(6)) for g, c in wins.items()},
            "pogo_all_lanes_combos": {k: dict(c.most_common(10)) for k, c in lanes_ok.items()}}


def human(path: Path, f0: int, f1: int) -> dict:
    """The person's damage per boss attack group: boss hp drops by the Control state at the drop."""
    from ssbot.tools.fight_stats import GROUP_OF
    from ssbot.tools.raw_session import states as raw_states
    prev, prev_st = None, None
    dealt = Counter()
    entries = Counter()
    for s in raw_states(path):
        if not f0 <= s.get("f", -1) <= f1:
            continue
        b = next((e for e in s.get("ents") or () if e.get("type_key") == "Bone Beast"), None)
        if b is None:
            continue
        st = (b.get("fsms") or [{}])[0].get("state")
        if st != prev_st:
            entries[st] += 1
            prev_st = st
        hp = b.get("hp")
        if hp is not None and prev is not None and hp < prev:
            dealt[GROUP_OF.get(st, "other")] += prev - hp
        prev = hp if hp is not None else prev
    att = {"charge": entries.get("Charge Antic", 0), "leap": entries.get("Leap Out", 0),
           "burst": entries.get("Burst Out", 0)}     # Burst Antic runs underground: not in the older export
    return {"hp_dealt_by_group": dict(dealt), "attacks": att,
            "hp_per_attack": {g: round(dealt.get(g, 0) / n, 2) for g, n in att.items() if n}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", type=Path)
    ap.add_argument("--every", type=int, default=12)
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--human", type=Path, default=None)
    ap.add_argument("--frames", type=int, nargs=2, default=(64275, 68397))
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    out = {}
    if a.human:
        out["human"] = human(a.human, *a.frames)
    for run in a.runs:
        out[run.name] = audit_run(run, a.every, a.episodes)
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
