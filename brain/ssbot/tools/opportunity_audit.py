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
(the action latency), then each option over 48 frames, nominal lane: side slash, up-slash (side key towards the
boss), jump + side slash, jump + up-slash, jump + down attack, Silkspear, each towards the boss. An option hits when
its attack box (planner.SIDE / UP / DOWN / SPEAR in the planner's active windows) meets the boss's enabled collider
polygons recorded for that frame; it is safe when none of its hero boxes meets an enabled damaging collider of any
entity recorded for that frame (hindsight: the real future, not the support). The bot's outcome is the recorded hit
events in the same 48 frames. A missed opportunity: some safe option hits, the bot dealt none. Tables per boss
attack group (fight_stats groups) and option.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

T = 48


def _options(face: int):
    from ssbot.knowledge.kinematics import B_ATTACK, B_DOWN, B_JUMP, B_LEFT, B_QUICKCAST, B_RIGHT, B_UP
    side = B_RIGHT if face > 0 else B_LEFT
    opts = {}
    m = np.zeros(T, np.int64); m[0:2] = side; m[1:4] |= B_ATTACK; opts["side"] = m
    m = np.zeros(T, np.int64); m[0:6] = side | B_UP; m[1:4] |= B_ATTACK; opts["up"] = m
    m = np.zeros(T, np.int64); m[0:24] |= B_JUMP; m[10:12] |= side; m[11:14] |= B_ATTACK; opts["jump_side"] = m
    m = np.zeros(T, np.int64); m[0:24] |= B_JUMP; m[8:14] |= side | B_UP; m[9:12] |= B_ATTACK; opts["jump_up"] = m
    m = np.zeros(T, np.int64); m[0:24] |= B_JUMP; m[16:22] |= side | B_DOWN; m[17:20] |= B_ATTACK; opts["jump_down"] = m
    m = np.zeros(T, np.int64); m[0:3] = side; m[0:3] |= B_QUICKCAST; opts["spear"] = m
    return opts


def _polys(e: dict) -> list[np.ndarray]:
    return [np.asarray(c["verts_world"], float).reshape(-1, 2) for c in e.get("colliders") or () if c.get("enabled")]


def _meets(rect, polys) -> bool:
    from ssbot.combat.planner import _rect_meets_polys
    if not polys:
        return False
    flat = np.concatenate(polys)
    starts = np.cumsum([0] + [len(q) for q in polys]).astype(np.int64)
    return bool(_rect_meets_polys(rect[0], rect[1], rect[2], rect[3], flat, starts, 0.0, 0.0))


def audit_run(run: Path, every: int, episodes: int) -> dict:
    from ssbot.combat import planner as pl
    from ssbot.knowledge import kinematics as kin
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.fight_stats import GROUP_OF
    from ssbot.tools.postmortem import episode_rows, find_recording
    from ssbot.train.encounters import BELL_BEAST
    params = kin.HeroParams.load()
    geo = {1: (pl.SIDE, 0, 6), 2: (pl.UP, 2, 8), 3: (pl.DOWN, 0, 16), 4: (pl.SPEAR, 17, 20)}
    kind_of = {"side": 1, "up": 2, "jump_side": 1, "jump_up": 2, "jump_down": 3, "spear": 4}
    stats = defaultdict(Counter)
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
                          and (e.get("data") or {}).get("type_key") == "Bone Beast") if hasattr(r, "events") else []
            by_f = {s["f"]: s for s in states}
            trk = kin.StateTracker(params, terrain)
            for n, s in enumerate(states):
                trk.push(s)
                if n % every or n + T + 3 >= len(states):
                    continue
                boss = next((e for e in s.get("ents") or () if e.get("type_key") == "Bone Beast"), None)
                hb = (s.get("hero") or {}).get("box")
                if boss is None or not hb or not _polys(boss):
                    continue
                st = (boss.get("fsms") or [{}])[0].get("state")
                hx = 0.5 * (hb[0] + hb[2])
                bx = boss["pos"][0]
                if abs(bx - hx) > 9.0:
                    continue
                try:
                    start = trk.state().copy()
                except Exception:
                    continue
                face = 1 if bx >= hx else -1
                f0 = s["f"]
                pre = np.array([((by_f.get(f0 + k) or {}).get("act") or {}).get("mask", 0) or 0 for k in (1, 2)],
                               np.int64)
                opts = _options(face)
                cmd = np.stack([np.concatenate([pre, m])[:T + 2] for m in opts.values()])
                latched, _ = kin.hold_filter(cmd, kin.HoldState.idle(len(cmd)))
                roll = kin.rollout(start, latched, params, terrain)
                samples += 1
                group = GROUP_OF.get(st, "other")
                any_hit = False
                for c, name in enumerate(opts):
                    kind = kind_of[name]
                    g, w0, w1 = geo[kind]
                    k0 = None
                    for k in range(1, T + 2):
                        if kind == 4 and roll.mode[c, k] == kin.M_CAST and roll.mode[c, k - 1] != kin.M_CAST:
                            k0 = k
                        elif kind == 3 and roll.mode[c, k] == kin.M_DS_SPIKE and roll.mode[c, k - 1] != kin.M_DS_SPIKE:
                            k0 = k
                        elif kind in (1, 2) and roll.flags[c, k] & kin.F_ATTACKING and not roll.flags[c, k - 1] \
                                & kin.F_ATTACKING:
                            k0 = k
                        if k0 is not None:
                            break
                    hit = safe = False
                    if k0 is not None:
                        for j in range(k0 + w0, min(T + 2, k0 + w1)):
                            sj = by_f.get(f0 + j)
                            if sj is None:
                                continue
                            bj = next((e for e in sj.get("ents") or () if e.get("type_key") == "Bone Beast"), None)
                            cx = 0.5 * (roll.box[c, j, 0] + roll.box[c, j, 2])
                            cy = 0.5 * (roll.box[c, j, 1] + roll.box[c, j, 3])
                            x0, x1 = (cx + g[0], cx + g[1]) if face > 0 else (cx - g[1], cx - g[0])
                            if bj is not None and _meets((x0, cy + g[2], x1, cy + g[3]), _polys(bj)):
                                hit = True
                                break
                    safe = True
                    for j in range(1, T + 2):
                        sj = by_f.get(f0 + j)
                        if sj is None:
                            continue
                        dmg = [p for e in sj.get("ents") or () for c2 in e.get("colliders") or ()
                               if c2.get("enabled") and (c2.get("damage") or {}).get("dealt")
                               for p in [np.asarray(c2["verts_world"], float).reshape(-1, 2)]]
                        if dmg and _meets(tuple(roll.box[c, j]), dmg):
                            safe = False
                            break
                    stats[(group, name)]["n"] += 1
                    stats[(group, name)]["hit"] += hit
                    stats[(group, name)]["safe_hit"] += hit and safe
                    any_hit |= hit and safe
                bot = any(f0 <= h <= f0 + T for h in hits)
                stats[(group, "bot")]["n"] += 1
                stats[(group, "bot")]["hit"] += bot
                stats[(group, "missed")]["n"] += 1
                stats[(group, "missed")]["hit"] += any_hit and not bot
    return {"samples": samples, "table": {f"{g}/{o}": dict(v) for (g, o), v in sorted(stats.items())}}


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
