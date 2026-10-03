"""Attack shape audit for any crest (generalizes tools/attack_shape_audit, which checked the Hunter down spike): does
the attack table's damage polygon (knowledge/<build>/attacks/<crest>.json), placed at the recorded hero over the
swing's active frames, meet the recorded enemy colliders exactly when the game registers a hit from that swing?

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.attack_hit_audit <run dir | recording> [...] --crest Reaper
        [--instances 3] [--episodes 20] [--slack 1] [--json out.json]

Swings from the recorded hero: an onset of cState.attacking is a slash (up while upAttacking, the wall slash while
wall sliding, else normal or alt by cState.altAttack right after it: Attack() sets it after a normal slash and
clears it after the alternate one); the Reaper down slash (Custom, Crest Attacks FSM) is the first frame of its
"v3 Down Slash" clip (its damage starts with the clip: StartSlash in the FSM's Rpr Downslash state). Frame k of a
swing counts from its first frame (k = 0). Active frames: the table's live-sampled frames when it has them, else
ceil(t_on * 60) .. ceil(t_off * 60), widened by --slack frames each way. Contact: some frame's polygon meets some
enabled collider of a living, visible entity with a health manager (not the hero's own). Hit: a "hit" event whose
src is one of the slot's damagers, from the swing's first frame to its last active frame + --slack + 2. Confusion
per slot (TP contact and hit, FP contact only, FN hit only, TN neither) and contact frame minus hit frame.

A hit on the hero ends the swing: HeroController.TakeDamage cancels the attack (CancelAttack), so a "damage" event (or
a blocked-lethal "catastrophe" of cause damage) at swing frame k_d leaves only the frames before k_d to make contact,
and a swing hit before its first active frame never swings (Bell Beast Reaper data 20261002_225836, slack 0: all 22
normal false positives of the first audit had the hero hit at k = 1..5, no true positive before k = 6). Such swings
are counted per slot as "cancelled" (and "cancelled_before_active" when no active frame was left).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

FPS = 60.0


def _cs_bits(names: list[str], wanted: tuple[str, ...]) -> dict[str, int]:
    return {n: names.index(n) for n in wanted}


def _flag(words, bit: int) -> bool:
    return bool((words[bit >> 6] >> (bit & 63)) & 1)


def _targets(s: dict) -> tuple[np.ndarray, np.ndarray] | None:
    from ssbot.ipc.ents import is_hidden
    vs = []
    for e in s.get("ents") or ():
        if is_hidden(e) or e.get("hp") is None or (e.get("hp") or 0) <= 0:
            continue
        for c in e.get("colliders") or ():
            if not c.get("enabled"):
                continue
            v = np.asarray(c["verts_world"], float).reshape(-1, 2)
            if c.get("kind") == "circle" and len(v):
                r = float(c.get("r") or 0.0) / math.cos(math.pi / 8)
                ang = np.pi / 8 + np.arange(8) * np.pi / 4
                v = v[0][None, :] + r * np.stack([np.cos(ang), np.sin(ang)], axis=1)
            if len(v) >= 3:
                vs.append(v)
            elif len(v) == 2:
                vs.append(np.vstack([v, v[::-1] + 1e-4]))
    if not vs:
        return None
    return np.concatenate(vs), np.cumsum([0] + [len(v) for v in vs]).astype(np.int64)


def swings(S: list[dict], names: list[str]) -> list[tuple[int, str]]:
    """(index into S, slot) of every swing start."""
    b = _cs_bits(names, ("attacking", "upAttacking", "altAttack", "wallSliding"))
    out = []
    prev_att = False
    prev_clip = None
    prev_wall = False
    for i, s in enumerate(S):
        h = s.get("hero") or {}
        w = h.get("cstate")
        clip = (h.get("anim") or {}).get("clip")
        if not w:
            prev_att, prev_clip = False, clip
            continue
        att = _flag(w, b["attacking"])
        wall = _flag(w, b["wallSliding"])
        if att and not prev_att:
            if _flag(w, b["upAttacking"]):
                slot = "up"
            elif wall or prev_wall:
                slot = "wall"
            else:
                slot = "normal" if _flag(w, b["altAttack"]) else "alt"
            out.append((i, slot))
        if clip == "v3 Down Slash" and prev_clip != "v3 Down Slash":
            out.append((i, "down"))
        prev_att, prev_clip, prev_wall = att, clip, wall
    return out


def hero_hit(s: dict) -> bool:
    """The hero took damage in this frame (TakeDamage ran: a "damage" event, or a lethal one LethalBlock stopped)."""
    for e in s.get("ev") or ():
        k = e.get("k")
        if k == "damage" or (k == "catastrophe" and (e.get("d") or {}).get("cause") == "damage"):
            return True
    return False


def _contact(s: dict, tab, slot: str) -> bool:
    """The slot's polygon at the recorded hero box meets an enemy collider in this frame."""
    h = s.get("hero") or {}
    if not h.get("box"):
        return False
    tg = _targets(s)
    if tg is None:
        return False
    bx = h["box"]
    face = 1 if (h.get("facing") or 1) >= 0 else -1
    return bool(tab.meets(slot, 0.5 * (bx[0] + bx[2]), 0.5 * (bx[1] + bx[3]), face, tg[0], tg[1]))


def audit(states: list[dict], tab, names: list[str], slack: int) -> dict:
    conf: dict[str, Counter] = defaultdict(Counter)
    lead: dict[str, list] = defaultdict(list)
    hit_k: dict[str, list] = defaultdict(list)
    cancelled: dict[str, Counter] = defaultdict(Counter)
    hurt = np.array([hero_hit(s) for s in states], dtype=bool)
    for i0, slot in swings(states, names):
        if slot not in tab:
            continue
        sh = tab[slot]
        if sh.frames:
            k0, k1 = sh.frames
        else:
            k0, k1 = int(math.ceil(sh.t_on * FPS - 1e-6)), int(math.ceil(sh.t_off * FPS - 1e-6))
        k0, k1 = max(k0 - slack, 0), k1 + slack
        srcs = set(sh.src.split("|"))
        hk = next((k for k in range(0, k1 + 3) if i0 + k < len(states) for e in states[i0 + k].get("ev") or ()
                   if e.get("k") == "hit" and (e.get("d") or {}).get("src") in srcs), None)
        kd = next((k for k in range(0, k1 + 1) if i0 + k < len(states) and hurt[i0 + k]), None)
        if kd is not None:
            cancelled[slot]["cancelled"] += 1
            cancelled[slot]["cancelled_before_active"] += int(kd <= k0)
            k1 = kd - 1
        first = next((k for k in range(k0, k1 + 1) if i0 + k < len(states)
                      and _contact(states[i0 + k], tab, slot)), None)
        pred, act = first is not None, hk is not None
        if (kd is not None and first is None and kd >= k0 and i0 + kd < len(states)
                and _contact(states[i0 + kd], tab, slot)):
            # first contact in the very frame the hero is hit: which of the two the step handles first decides
            cancelled[slot]["contact_on_damage_frame"] += 1
            cancelled[slot]["contact_on_damage_frame_hit"] += int(act)
        conf[slot]["TP" if pred and act else "FP" if pred else "FN" if act else "TN"] += 1
        if pred and act:
            lead[slot].append(first - hk)
        if act:
            hit_k[slot].append(hk)
    return {"confusion": {k: dict(v) for k, v in conf.items()},
            "contact_minus_hit": {k: dict(Counter(v)) for k, v in lead.items()},
            "hit_frame_k": {k: dict(Counter(v)) for k, v in hit_k.items()},
            "cancelled": {k: dict(v) for k, v in cancelled.items()}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--crest", default="Reaper")
    ap.add_argument("--instances", default="0,1,2,3")
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--slack", type=int, default=1)
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args(argv)
    from ssbot.knowledge.attack_shapes import AttackTable
    from ssbot.knowledge.kinematics import cstate_names
    from ssbot.record.recorder import RecordingReader
    from ssbot.tools.coverage_map import recordings
    tab = AttackTable.load(a.crest)
    names = cstate_names()
    total: dict = {"confusion": defaultdict(Counter), "contact_minus_hit": defaultdict(Counter),
                   "hit_frame_k": defaultdict(Counter), "cancelled": defaultdict(Counter)}
    n = 0
    for path, f0, f1 in recordings(a.paths, [int(x) for x in a.instances.split(",")], a.episodes):
        S = list(RecordingReader(path).states(f0, f1, keys=("hero", "ents", "ev")))
        r = audit(S, tab, names, a.slack)
        for key in total:
            for slot, c in r[key].items():
                total[key][slot].update(c)
        n += 1
    out = {"crest": a.crest, "spans": n, "slack": a.slack,
           **{k: {s: dict(sorted(c.items(), key=str)) for s, c in v.items()} for k, v in total.items()}}
    print(json.dumps(out, indent=1))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
