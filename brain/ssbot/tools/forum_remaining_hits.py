"""Remaining hits of the wave-0 de-saturation live rounds (task "remaining hits", forum.md §24): every hero hit of the
listed arms explained from the live logs and the recordings, the arms compared per minute (masks, hits landed, the
effective mask loss), and the A/B power of the protocol.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_remaining_hits collect
        --manifest r1=C:/ssbot/sandbox/w0d_manifest_a.txt --manifest r2=... [--arms r1:new,r2:newS] --out <dir>
        [--workers 2]
    ../scripts/uv.cmd run python -m ssbot.tools.forum_remaining_hits report --out <dir> [--json <file>]
        [--arms a,b] [--pool name=a+b] [--cmp x~y] [--did a1~b1~a2~b2] [--pairs x~y] [--focus a,b]
        [--hindsight <forum_hit_forensics out dir> ...]

A manifest line is "arm<TAB>chunk seed<TAB>instance<TAB>run dir" (the de-saturation drivers' w0d_manifest_*.txt); the
round label prefixes the arm ("r2:newS"). collect writes one JSON per episode (<out>/eps/<round>_<arm>_<run>_i<k>_ep<n>
.json, existing ones skipped):
  episode   the attempt row's numbers: in-game time, masks lost (hp_lost), hits, 2-mask chains, hits landed (STATE `hit`
            events: the effective mask loss = masks - landed / 4, plan §5 2026-10-08), kills, wave reached, the
            FORCED_RISK / late shares, tiers and modes, attack presses, nail clashes (NailClashEffect freezes).
  hits      one row per hit (a Multihit chain's tick and its Final Hit are one row with 2 masks, at the hook): source
            path / collider / type / iid; the source's control state at the contact and the attack it belongs to (the
            last family start state it entered, gauntlet_tables.FORUM_SPECS; idle family = no attack under way) with
            its start frame; the hero then and at the contact (airborne, attacking, recoiling, dashing, the frames
            until it could attack / dash again, the distance); body contacts and whether the hero walked into an idle
            body; the Reed's defence (RE_DEFEND, the counter) and whether the hero had swung at it in the 1.2 s before;
            a kill attempt (the planner's target is the source and an attack press in the last 0.5 s, or a hit landed
            on any enemy in the last 0.6 s); other enemies' damage colliders within 1.5 u; the clash table's Wanderer
            numbers for the family (clash.json); and the planner from the decision log (sampled densest near hits):
            tier / mode / goal / h / FORCED_RISK / n_safe / P / the alternatives at the attack's start and the last
            tick before the contact, the last logged tick with a safe row, the clash gate (h <= 2, RED, a pause
            pending), the escape check's verdict.
Also per episode the seconds, masks, hits and hits landed of each wave (gauntlet waves); per hit the clash geometry
(heuristic: the contact's collider within a Wanderer swing's reach on the facing side / above / below, in a clash state,
the hero free, in the 12 frames before) and the source re-resolved when the live hit log names another instance of the
type (it takes the first entity matching the path's type: often a sleeping Choristor).
report: per arm the ratios of sums (masks / min, landed / min, effective mask loss / min; wave 0 and the later waves
apart; kills, presses) with bootstrap intervals; unpaired bootstrap differences (--cmp), pooled arms (--pool), the
difference in differences against a same-round control (--did); per source the masks per minute and an exact Poisson
test against --base; for the --focus arms each hit's mechanisms and primary cause (MECHS: the first that holds) by
family, joined to forum_hit_forensics outputs (--hindsight: the open-loop hindsight of forum.md 19.1, the last tick
before the contact with a row the recorded future left clear; avoidable = 4-36 frames before); and the episodes per arm
an A/B needs for a 10 % / 20 % change (unpaired; paired by round, instance, chunk seed and episode), log survival too.
"""
import argparse
import json
import math
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

WINDOW_BEFORE_F = 120        # frames of the source's history searched for its attack start
STRIKE_BACK_S = 1.2          # a hero swing at a defending Reed this long before the hit (forum.md §17.7 / plan note)
KILL_PRESS_S = 0.5           # an attack press this long before a hit on the planner's target: a kill attempt
LANDED_BEFORE_S = 0.6        # a hit landed on any enemy this long before: trading
NEAR_OTHER_U = 1.5           # another enemy's damage collider this close to the hero box: "another enemy in contact"
WALK_IN_V = 2.0              # hero speed toward an idle body (u/s) over the last 6 frames: walked into it
LOCK_MAX_F = 90              # frames searched for the hero's next attack / dash (the lock after the attack's start)
GLIDE_FREE = ("Umbrella Float", "Umbrella Deflate", "Umbrella Turn")
# a Wanderer swing's reach from the hero's center (u): side in front, half height; up above; down below (plan sec. 5
# 2026-10-08: up slash to 3.39 u above, down slash to 2.16 u below the transform; side ~2.6 u, the slash shapes)
SLASH_REACH_U = (2.8, 1.4, 3.4, 2.2)
DEFEND_STATES = {"Song Reed": ("Defend", "Block", "Parry", "Multihit Clashed", "Counter"),
                 "Song Administrator": ("Parry", "Shove")}


# ---- inputs ----

def read_manifests(specs: list[str]) -> list[dict]:
    """[{round, arm, seed, inst, run}] from "label=path" manifest specs."""
    out = []
    for sp in specs:
        lab, _, p = sp.partition("=")
        for line in Path(p).read_text("utf-8-sig").splitlines():
            if not line.strip():
                continue
            name, seed, inst, rd = (line.split("\t") + ["", "", "", ""])[:4]
            if rd.strip():
                out.append({"round": lab, "arm": name.strip(), "seed": int(seed), "inst": int(inst),
                            "run": rd.strip()})
    return out


def _attempts(run: Path) -> list[dict]:
    rows = []
    for p in sorted(run.glob("attempts_i*.jsonl")):
        inst = int(p.stem.split("_i")[-1])
        for x in p.read_text("utf-8").splitlines():
            if x.strip():
                r = json.loads(x)
                r["_inst"] = inst
                rows.append(r)
    return rows


def _decisions(run: Path, inst: int) -> dict[int, list[dict]]:
    by = defaultdict(list)
    p = run / f"decisions_i{inst}.jsonl"
    if p.exists():
        with p.open("r", encoding="utf-8") as fh:
            for x in fh:
                if x.strip():
                    d = json.loads(x)
                    by[int(d.get("ep", -1))].append(d)
    return by


# ---- the recording, compact ----

def _bbox(v) -> tuple | None:
    if not v or len(v) < 6:
        return None
    xs, ys = v[0::2], v[1::2]
    return (min(xs), min(ys), max(xs), max(ys))


def fsm_timeline(rd, f0: int, f1: int) -> dict[int, tuple[list[int], list[str]]]:
    """{iid: (frames, states)} of the control FSMs' transitions (the recording's `fsm` events) up to f1: the STATE's
    exported state is None on some frames (the Choristor's Attack FSM), the events still carry every transition."""
    from ssbot.knowledge.gauntlet_tables import FORUM_SPECS
    ctl = {tk: sp.control_fsm for tk, sp in FORUM_SPECS.items()}
    tl: dict = defaultdict(lambda: ([], []))
    for ev in rd.events({"fsm"}):
        f = int(ev.get("frame") or 0)
        if f > f1:
            break
        d = ev.get("data") or {}
        obj = str(d.get("obj") or "")
        tk = next((t for t in ctl if obj == t or obj.startswith(t + " (")), None)
        if tk is None or d.get("fsm") != ctl[tk] or d.get("to") is None:
            continue
        a, b = tl[int(d.get("iid") or d.get("ent") or 0)]
        a.append(f)
        b.append(str(d["to"]))
    return dict(tl)


def _tl_state(tl: dict, iid: int, f: int) -> str | None:
    import bisect
    v = tl.get(iid)
    if not v:
        return None
    k = bisect.bisect_right(v[0], f) - 1
    return v[1][k] if k >= 0 else None


# a contact's family from its collider when the source's state history does not give one
COLLIDER_FAMILY = (("Whip Hit", "CH_WHIP"), ("Spin", "CH_JUMP"), ("Slash Hit", "CH_SLASH"),
                   ("JumpSlash Damager", "EN_JUMPSLASH"), ("Charge Damager", "EN_CHARGE"), ("P1 Damager", "EN_SLASH"),
                   ("P2 Damager", "EN_SLASH"), ("Stab Hit", "RE_STAB"), ("ParrySlash", "RE_DEFEND"),
                   ("Throwing Bell", "CB_THROW"), ("Spear", "CM_SPIN"), ("spear_silk_explosion", "CM_SPIN"))


def compact_frames(states, tl: dict | None = None) -> list[dict]:
    """Per STATE: the hero (box, velocity, clip, cstate flags, can), the sent keys, the enemies (iid, type, position,
    velocity, main state and its time, enabled damage colliders as boxes, hp), the events of interest. tl: the FSM
    event timeline (fsm_timeline) filling a state the STATE does not export."""
    from ssbot.ipc.ents import SRC_BITS
    from ssbot.knowledge.behaviour_tables import multi_wounder_threat, support_threat
    from ssbot.tools.forum_demo import _cs_index, _flags, _main_state
    idx = _cs_index()
    tl = tl or {}
    hm, mw = SRC_BITS["health_manager"], SRC_BITS["multi_wounder"]
    out = []
    for s in states:
        h = s.get("hero") or {}
        fl = _flags(h.get("cstate"), idx) if h.get("cstate") else {}
        ents = []
        for e in s.get("ents") or ():
            if e.get("hidden") or e.get("is_dead"):
                continue
            src = int(e.get("src") or 0)
            dmg = []
            for c in e.get("colliders") or ():
                # the planner's rule (forum_hit_forensics.damage_polys): a support threat, or a multi-hit hook exported
                # with damage 0 on a multi_wounder entity (the Choristor's Whip Hit n, the Reed's ParrySlash Hit)
                if support_threat(c) or (multi_wounder_threat(c) and src & mw):
                    bb = _bbox(c.get("verts_world"))
                    if bb is not None:
                        dmg.append((str(c.get("name")), bb))
            if not (src & hm or src & mw or dmg):
                continue
            st, tin = _main_state(e)
            if st is None:
                st = _tl_state(tl, int(e.get("iid") or 0), int(s["f"]))
            p = e.get("pos") or (0.0, 0.0)
            v = e.get("vel") or (0.0, 0.0)
            ents.append((int(e.get("iid") or 0), str(e.get("type_key")), float(p[0]), float(p[1]), float(v[0]),
                         float(v[1]), st, tin, dmg, e.get("hp"), bool(src & hm)))
        evs = []
        for ev in s.get("ev") or ():
            k = ev.get("k")
            if k in ("damage", "special_damage", "hit", "die", "damage_blocked"):
                evs.append((k, ev.get("d") or {}))
            elif k == "freeze":
                d = ev.get("d") or {}
                if d.get("phase") == "start":
                    evs.append(("freeze", {"type": d.get("type")}))
        can = h.get("can") or {}
        out.append({"f": int(s["f"]), "box": h.get("box"), "vel": h.get("vel") or (0.0, 0.0),
                    "clip": (h.get("anim") or {}).get("clip"), "fl": fl, "can_atk": bool(can.get("attack")),
                    "can_dash": bool(can.get("dash")), "act": int((s.get("act") or {}).get("mask") or 0),
                    "ents": ents, "ev": evs, "facing": h.get("facing")})
    return out


# ---- per episode ----

def _center(b) -> tuple[float, float]:
    return 0.5 * (b[0] + b[2]), 0.5 * (b[1] + b[3])


def _gap(a, b) -> float:
    """Distance between two boxes (0 when they overlap)."""
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def _short(path: str | None) -> str:
    p = str(path or "")
    return p.split("/")[-1] if "/" in p else p


def _is_body(path: str, tk: str | None) -> bool:
    p = str(path or "")
    last = _short(p)
    return bool(tk) and (last == tk or last.startswith(tk + " (") or "Body" in last or p.startswith("Wave "))


def _dec_view(d: dict | None, f_ref: int | None = None) -> dict | None:
    if d is None:
        return None
    fi = d.get("fi") or {}
    esc = fi.get("esc") or {}
    alts = d.get("alts") or []
    return {"f": d.get("f"), "df": None if f_ref is None else int(f_ref) - int(d.get("f") or 0),
            "plan": d.get("plan"), "tier": d.get("tier"), "mode": d.get("mode"), "goal": d.get("goal"),
            "h": d.get("h"), "forced": d.get("forced"), "S": d.get("S"), "n_safe": d.get("n_safe"),
            "n_ok": d.get("n_ok"), "P": d.get("P"), "J": d.get("J"), "tgt": d.get("tgt"),
            "tgt_type": d.get("tgt_type"), "pending": d.get("pending"),
            "alts_S1": sum(1 for a in alts if a and a[1] == 1), "alts_n": len(alts),
            "alts_P": [a[2] for a in alts][:5], "kill_prims": d.get("kill_prims") or [],
            "esc_fail": esc.get("fail"), "esc_why": esc.get("why"), "esc_cut": esc.get("cut"),
            "seen": fi.get("seen"), "seen_cf": fi.get("seen_cf"), "clash": d.get("clash"),
            "attack_plan": "ATTACK" in str(d.get("plan") or "") or "attack" in str(d.get("plan") or "")}


def _wanderer_clash(cj: dict, tk: str | None, fam: str | None) -> dict | None:
    if not tk or not fam:
        return None
    out = {}
    for slot in ("side", "up", "down"):
        v = (cj.get("p_fail") or {}).get(f"{tk}|{fam}|{slot}")
        if v is None:
            continue
        w = (v.get("by_crest") or {}).get("Wanderer") or {}
        out[slot] = {"n_eff": v.get("n_eff"), "p_fail": v.get("p_fail"), "p_hit": v.get("p_hit"),
                     "W_n": w.get("n"), "W_clash": w.get("clash"), "W_hit": w.get("hit"), "W_p_fail": w.get("p_fail")}
    return out or None


_DEC_CACHE: dict = {}


def _episode_decisions(run: str, inst: int, ep: int) -> list[dict]:
    """The decision log of one episode (the worker keeps the last run's file parsed)."""
    key = (run, inst)
    if key not in _DEC_CACHE:
        _DEC_CACHE.clear()
        _DEC_CACHE[key] = _decisions(Path(run), inst)
    return _DEC_CACHE[key].get(ep, [])


def analyse_episode(job: dict) -> dict:
    from ssbot.knowledge.gauntlet_tables import FORUM_SPECS
    from ssbot.knowledge.kinematics import B_ATTACK
    from ssbot.record.recorder import RecordingReader
    row = job["row"]
    dec = _episode_decisions(job["run"], int(row["_inst"]), int(row["episode"]))
    t0 = time.perf_counter()
    rd = RecordingReader(row["recording"])
    fr = compact_frames(rd.states(row["f_wake"], row["f_end"]), fsm_timeline(rd, row["f_wake"], row["f_end"]))
    by_f = {x["f"]: i for i, x in enumerate(fr)}
    cj = job["clash"]
    pol = row.get("policy") or {}
    gl = row.get("gauntlet") or {}
    dt = 1.0 / 60.0
    # ---- episode numbers ----
    landed, kills, clashes, landed_f = 0, 0, 0, []
    by_target = Counter()
    for x in fr:
        for k, d in x["ev"]:
            if k == "hit":
                landed += 1
                landed_f.append((x["f"], d.get("ent"), d.get("type_key")))
                by_target[str(d.get("type_key"))] += 1
                kills += bool(d.get("dead"))
            elif k == "freeze" and "NailClash" in str(d.get("type")):
                clashes += 1
    presses = 0
    prev = 0
    for x in fr:
        a = x["act"] & B_ATTACK
        presses += bool(a and not prev)
        prev = a
    modes = pol.get("modes") or {}
    hl = pol.get("hit_log") or []
    fu = {int(a[0]): int(a[2]) for a in (pol.get("follow_ups") or ()) if len(a) >= 3}   # final f -> tick f
    tick_used = set(fu.values())
    ep = {"round": job["round"], "arm": job["arm"], "run": Path(job["run"]).name, "inst": row["_inst"],
          "chunk_seed": job["seed"], "ep": row["episode"], "seed": row.get("seed"), "code_rev": row.get("code_rev"),
          "env": row.get("env"), "outcome": row.get("outcome"), "reason": row.get("reason"),
          "t": float(row.get("ingame_s") or 0.0), "masks": int(row.get("hp_lost") or 0),
          "hits": int(row.get("hits") or 0), "chains": sum(1 for h in hl if h.get("kind") == "tick"),
          "landed": landed, "landed_by": dict(by_target), "kills": int((gl.get("kills") or {}).get("n") or 0),
          "kills_ev": kills, "wave": int(gl.get("wave_reached") or 0), "ticks": int(pol.get("ticks") or 0),
          "forced": int(pol.get("forced_risk_ticks") or 0), "late": int(pol.get("late_ticks") or 0),
          "modes": modes, "presses": presses, "clashes": clashes,
          "plan_change": (pol.get("keys") or {}).get("plan_change_rate"),
          "audit": {k: v for k, v in (pol.get("audit") or {}).items() if isinstance(v, (int, float))},
          "hp_start": (row.get("rand") or {}).get("hp")}
    # per wave (gauntlet waves: the frame each started): seconds, masks, hits, landed
    wv = sorted((int(w.get("wave") or 0), int(w.get("f") or 0)) for w in (gl.get("waves") or ()))
    f_end = int(row.get("f_end") or (fr[-1]["f"] if fr else 0))
    per = {}
    for k, (w, f0) in enumerate(wv):
        f1 = wv[k + 1][1] if k + 1 < len(wv) else f_end
        per[str(w)] = {"t": round((f1 - f0) * dt, 2),
                       "masks": sum(int(h.get("amount") or 1) for h in hl if f0 <= int(h.get("f") or 0) < f1),
                       "hits": sum(1 for h in hl if h.get("kind") == "damage" and f0 <= int(h.get("f") or 0) < f1),
                       "landed": sum(1 for lf, _, _ in landed_f if f0 <= lf < f1)}
    ep["per_wave"] = per
    # ---- hits ----
    specs = {tk: (dict(sp.attack_starts), set(sp.decision_states), sp.idle_family) for tk, sp in FORUM_SPECS.items()}
    dec = sorted(dec, key=lambda d: int(d.get("f") or 0))
    dec_f = np.array([int(d.get("f") or 0) for d in dec], np.int64)
    hits = []
    for h in hl:
        kind = h.get("kind")
        f = int(h.get("f") or 0)
        if kind == "tick" and f in tick_used:
            continue                                       # its Final Hit's row
        tick_f = fu.get(f) if kind == "damage" else (f if kind == "tick" else None)
        f_c = tick_f if tick_f is not None else f          # the contact: the hook for a chain
        masks = int(h.get("amount") or 1) + (1 if (kind == "damage" and tick_f is not None) else 0)
        path = str(h.get("path") or "")
        tk = h.get("src_type")
        sid = h.get("src_id")
        i_c = by_f.get(f_c)
        rec = {"f": f, "f_c": f_c, "t": h.get("t"), "kind": kind, "chain": tick_f is not None, "masks": masks,
               "path": path, "collider": _short(path), "type": tk, "src_id": sid, "wave": h.get("wave_v"),
               "log": {k: h.get(k) for k in ("S", "forced", "mode", "tier", "h", "unpred")}}
        if i_c is None:
            hits.append(rec)
            continue
        hb = fr[i_c]["box"] or fr[max(i_c - 1, 0)]["box"]
        # the source entity: the logged iid, else the entity whose damage collider is the path's / nearest the hero
        cand = None
        for i in (i_c, i_c - 1, i_c - 2):
            if i < 0:
                continue
            for e in fr[i]["ents"]:
                if sid is not None and e[0] == sid:
                    cand = e
                    break
            if cand is not None:
                break
        if cand is None and hb is not None:
            best = None
            for i in (i_c - 1, i_c, i_c - 2):
                if i < 0:
                    continue
                for e in fr[i]["ents"]:
                    for nm, bb in e[8]:
                        if nm and (nm == rec["collider"] or nm in path or e[1] in path):
                            g = _gap(hb, bb)
                            if best is None or g < best[0]:
                                best = (g, e)
                if best is not None:
                    break
            cand = best[1] if best is not None else None
        if cand is None and hb is not None and kind == "tick":
            # a Multihit tick whose Final Hit is not in the log: the damage collider nearest the hero names it (a whip
            # segment / counter hook entity), its owner the nearest enemy of the family's type
            best = None
            for i in (i_c - 1, i_c):
                if 0 <= i < len(fr):
                    for e in fr[i]["ents"]:
                        for nm, bb in e[8]:
                            g = _gap(hb, bb)
                            if g <= 0.75 and (best is None or g < best[0]):
                                best = (g, e, nm, bb, i)
            if best is not None:
                _, e, nm, bb, i = best
                path = f"{e[1]}/{nm}"
                rec["path_guess"], rec["collider"] = path, nm
                cf_ = next((fm for key, fm in COLLIDER_FAMILY if key in path), None)
                owner = {"CH": "Song Pilgrim 03", "RE": "Song Reed", "EN": "Song Pilgrim 01",
                         "MI": "Song Administrator"}.get((cf_ or "")[:2])
                if owner is None and e[10]:
                    cand = e
                elif owner is not None:
                    cx, cy = _center(bb)
                    own = [(math.hypot(x[2] - cx, x[3] - cy), x) for x in fr[i]["ents"] if x[1] == owner]
                    if own:
                        cand = min(own, key=lambda z: z[0])[1]
        if cand is not None:
            sid = cand[0]
            tk = tk or cand[1]
            rec["src_id"], rec["type"] = sid, tk
        rec["pin"] = "Pin Projectile" in path
        sp = specs.get(tk or "")
        st_c = cand[6] if cand is not None else None
        rec["state"] = st_c
        # the attack the contact belongs to: the source's last start state of the collider's family (a named attack
        # collider, COLLIDER_FAMILY), else of any family, a decision state first meaning no attack under way (idle)
        cf = next((fm for key, fm in COLLIDER_FAMILY if key in path), None)

        def attack_of(iid):
            starts, decide, idle = sp
            for i in range(i_c, max(i_c - WINDOW_BEFORE_F * 3, -1), -1):
                e = next((x for x in fr[i]["ents"] if x[0] == iid), None)
                if e is None:
                    break
                if e[6] in starts and (cf is None or starts[e[6]] == cf):
                    j = i                                   # walk back to its entry
                    while j > 0:
                        e2 = next((x for x in fr[j - 1]["ents"] if x[0] == iid), None)
                        if e2 is None or e2[6] != e[6]:
                            break
                        j -= 1
                    return starts[e[6]], fr[j]["f"], e[6]
                if cf is None and e[6] in decide:
                    return idle, None, None
                # (a state not exported, a mid-attack state or another family's start: keep walking back)
            return None, None, None
        fam, f_a, st_a = None, None, None
        if sp is not None and sid is not None:
            fam, f_a, st_a = attack_of(sid)
            if cf is not None and fam is None and i_c > 0:
                # the live log names a type's first instance (a sleeping one): the instance of that type whose attack
                # of the collider's family is under way, nearest the hero
                alt = []
                for e in fr[i_c - 1]["ents"]:
                    if e[1] == tk and e[0] != sid:
                        fa = attack_of(e[0])
                        if fa[0] == cf and hb is not None:
                            alt.append((math.hypot(e[2] - _center(hb)[0], e[3] - _center(hb)[1]), e, fa))
                if alt:
                    _, cand, (fam, f_a, st_a) = min(alt, key=lambda z: z[0])
                    rec["src_fixed"] = [sid, cand[0]]
                    sid = cand[0]
                    rec["src_id"], st_c = sid, cand[6]
                    rec["state"] = st_c
            if fam is None:
                fam = cf or sp[2]
        elif cf is not None:
            fam = cf
        if rec["pin"]:
            # a pin: its spawn (the first frame a pin entity is that near its contact path) and its thrower's throw
            fam = "RE_THROW"
            pin = None
            for i in (i_c - 1, i_c, i_c - 2):
                if 0 <= i < len(fr) and hb is not None:
                    ps = [(min(_gap(hb, bb) for _, bb in e[8]) if e[8] else 9e9, e) for e in fr[i]["ents"]
                          if "Pin" in e[1]]
                    if ps:
                        pin = min(ps, key=lambda z: z[0])[1]
                        break
            if pin is not None:
                rec["src_id"] = pin[0]
                j = i_c
                while j > 0 and any(x[0] == pin[0] for x in fr[j - 1]["ents"]):
                    j -= 1
                f_a = fr[j]["f"]
                st_a = "pin spawn"
        rec["family"], rec["f_a"], rec["state_a"] = fam, f_a, st_a
        rec["wind_s"] = None if f_a is None else round((f_c - f_a) * dt, 3)
        rec["body"] = _is_body(path, tk) and not rec["pin"]
        rec["idle_body"] = bool(rec["body"] and sp is not None and fam == sp[2])
        # the hero at the attack's start and at the contact
        i_a = by_f.get(f_a) if f_a is not None else None

        def hero_at(i):
            if i is None or not (0 <= i < len(fr)):
                return None
            x = fr[i]
            fl = x["fl"]
            lock = 0
            inflate = 0
            for j in range(i, min(i + LOCK_MAX_F, len(fr))):
                c = str(fr[j]["clip"] or "")
                inflate = inflate + 1 if c == "Umbrella Inflate" else 0
                # free: can attack / dash, or a glide phase whose attack / dash press the Umbrella Float FSM honours
                # (Inflate after 0.075 s, Float Idle, Deflate: movement_kinematics.md 1.2)
                if fr[j]["can_atk"] or fr[j]["can_dash"] or c in GLIDE_FREE or inflate > 4:
                    break
                lock += 1
            e = next((y for y in x["ents"] if y[0] == sid), None) if sid is not None else None
            dist = None
            if e is not None and x["box"]:
                cx, cy = _center(x["box"])
                dist = round(math.hypot(e[2] - cx, e[3] - cy), 2)
            return {"air": not fl.get("onGround", True), "attacking": bool(fl.get("attacking")),
                    "recoil": bool(fl.get("recoiling")), "dash": bool(fl.get("dashing") or fl.get("airDashing")),
                    "clip": x["clip"], "can_atk": x["can_atk"], "can_dash": x["can_dash"], "lock_f": lock,
                    "dist": dist}
        rec["hero_a"] = hero_at(i_a)
        rec["hero_c"] = hero_at(i_c - 1)
        # the bot's own swings and landed hits before the contact
        pf = []
        prev = 0
        for j in range(max(i_c - 90, 0), i_c + 1):
            a = fr[j]["act"] & B_ATTACK
            if a and not prev:
                pf.append(fr[j]["f"])
            prev = a
        rec["press_before_f"] = [f_c - p for p in pf][-4:]
        rec["landed_before_f"] = [f_c - lf for lf, _, _ in landed_f if 0 <= f_c - lf <= 90]
        rec["landed_on_src_before_f"] = [f_c - lf for lf, ent, _ in landed_f if ent == sid and 0 <= f_c - lf <= 90]
        # the hero walked into an idle body: moving toward it over the last 6 frames, it slow
        if rec["body"] and cand is not None and hb is not None:
            j0 = max(i_c - 6, 0)
            if fr[j0]["box"] and fr[i_c - 1]["box"]:
                c0, c1 = _center(fr[j0]["box"]), _center(fr[i_c - 1]["box"])
                n = max(i_c - 1 - j0, 1)
                vx, vy = (c1[0] - c0[0]) / (n * dt), (c1[1] - c0[1]) / (n * dt)
                ex, ey = cand[2] - c1[0], cand[3] - c1[1]
                d = math.hypot(ex, ey) or 1.0
                rec["hero_toward"] = round((vx * ex + vy * ey) / d, 2)
                rec["src_speed"] = round(math.hypot(cand[4], cand[5]), 2)
                rec["walked_in"] = bool(rec["hero_toward"] > WALK_IN_V and rec["src_speed"] < WALK_IN_V)
        # defence / counter
        ds = DEFEND_STATES.get(tk or "")
        rec["defence"] = bool(ds and ((st_c and any(w in st_c for w in ds)) or "Parry" in path or "Counter" in path
                                      or fam in ("RE_DEFEND", "MI_PARRY")))
        if rec["defence"]:
            rec["swung_at_before_f"] = [f_c - p for p in pf if 0 <= f_c - p <= STRIKE_BACK_S * 60]
        # other enemies' damage colliders near the hero at the contact
        if hb is not None and i_c > 0:
            others = set()
            for e in fr[i_c - 1]["ents"]:
                if e[0] == sid or "Pin" in e[1] and rec["pin"]:
                    continue
                if any(_gap(hb, bb) <= NEAR_OTHER_U for _, bb in e[8]):
                    others.add(e[1])
            rec["others_near"] = sorted(others)
        rec["clash_table"] = _wanderer_clash(cj, tk, fam)
        # clash geometry (heuristic, not the planner's EV_CLASH): in the 12 frames before the contact, the contact's
        # collider within a Wanderer side slash's reach in front of the hero (or an up / down slash's above / below),
        # the source in one of its family's clash states, the hero free to swing
        cs_ok = set((cj.get("clash_states") or {}).get(f"{tk}|{fam}", ()))
        geo = []
        for j in range(max(i_c - 12, 0), i_c):
            x = fr[j]
            if not x["box"] or not (x["can_atk"] or str(x["clip"] or "") in GLIDE_FREE):
                continue
            e = next((y for y in x["ents"] if y[0] == sid), None)
            if e is None or (cs_ok and e[6] not in cs_ok):
                continue
            cx, cy = _center(x["box"])
            face = 1 if (x["facing"] or 1) > 0 else -1
            # the contact's collider: on the source, or on a child entity named like it (a whip segment)
            boxes = [bb for y in x["ents"] if y[0] == sid or y[1] == rec["collider"] for nm, bb in y[8]
                     if nm == rec["collider"] or y[1] == rec["collider"] or (rec["body"] and y[0] == sid)]
            for bb in boxes:
                bx, by_ = _center(bb)
                dxf = (bx - cx) * face
                side = 0 <= dxf <= SLASH_REACH_U[0] and abs(by_ - cy) <= SLASH_REACH_U[1]
                up = abs(bx - cx) <= SLASH_REACH_U[1] and 0 <= by_ - cy <= SLASH_REACH_U[2]
                down = abs(bx - cx) <= SLASH_REACH_U[1] and 0 <= cy - by_ <= SLASH_REACH_U[3]
                if side or up or down:
                    geo.append(f_c - x["f"])
                    break
        rec["clash_geo_f"] = geo[:1] + geo[-1:] if geo else []
        # the planner (decision log, sampled)
        k_c = int(np.searchsorted(dec_f, f_c, side="left")) - 1   # last tick before the contact
        d_c = dec[k_c] if k_c >= 0 and f_c - int(dec_f[k_c]) <= 30 else None
        d_a = None
        if f_a is not None:
            k_a = int(np.searchsorted(dec_f, f_a, side="right")) - 1
            d_a = dec[k_a] if k_a >= 0 and f_a - int(dec_f[k_a]) <= 30 else None
        rec["dec_c"] = _dec_view(d_c, f_c)
        if d_c is not None and sid is not None:
            sj = next((x for x in (d_c.get("subj") or ()) if x and x[0] == sid), None)
            rec["src_hp"] = sj[3] if sj else None
        rec["dec_a"] = _dec_view(d_a, f_a)
        lo = (f_a if f_a is not None else f_c - 60) - 6
        win = [d for d in dec[max(k_c - 400, 0):k_c + 1] if lo <= int(d.get("f") or 0) < f_c]
        rec["win_ticks"] = len(win)
        rec["win_frames"] = f_c - lo
        rec["win_forced"] = sum(1 for d in win if d.get("forced"))
        rec["win_safe"] = sum(1 for d in win if (d.get("n_safe") or 0) > 0)
        rec["win_gate"] = sum(1 for d in win if (d.get("h") or 9) <= 2 or d.get("tier") == "RED" or d.get("pending"))
        rec["win_attack_plans"] = sum(1 for d in win if "ATTACK" in str(d.get("plan") or ""))
        rec["win_clash"] = sum(1 for d in win if d.get("clash"))
        rec["win_tgt_src"] = sum(1 for d in win if sid is not None and d.get("tgt") == sid)
        rec["win_esc_fail"] = sum(1 for d in win if ((d.get("fi") or {}).get("esc") or {}).get("fail"))
        last_safe = None
        for d in reversed(dec[max(k_c - 600, 0):k_c + 1]):
            if (d.get("n_safe") or 0) > 0 and int(d.get("f") or 0) < f_c:
                last_safe = f_c - int(d["f"])
                break
        rec["last_safe_f"] = last_safe
        hits.append(rec)
    return {"episode": ep, "hits": hits, "secs": round(time.perf_counter() - t0, 1)}


def _job_safe(job: dict) -> dict:
    try:
        return analyse_episode(job)
    except Exception as e:     # one bad episode leaves the rest
        import traceback
        return {"error": repr(e)[:500], "trace": traceback.format_exc()[-2000:], "job": {k: job[k] for k in (
            "round", "arm", "run", "seed")}, "ep": job["row"].get("episode"), "inst": job["row"].get("_inst")}


def _init() -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass


def collect(a) -> int:
    out = Path(a.out)
    (out / "eps").mkdir(parents=True, exist_ok=True)
    cj = json.loads((Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / "forum"
                     / "clash.json").read_text("utf-8"))
    runs = read_manifests(a.manifest)
    keep = set(a.arms.split(",")) if a.arms else None
    jobs = []
    for r in runs:
        lab = f"{r['round']}:{r['arm']}"
        if keep is not None and lab not in keep:
            continue
        run = Path(r["run"])
        for row in _attempts(run):
            if row.get("outcome") == "HARNESS_FAIL":
                continue
            name = f"{r['round']}_{r['arm']}_{run.name}_i{row['_inst']}_ep{row['episode']}.json"
            if (out / "eps" / name).exists():
                continue
            row.pop("attacks", None)
            jobs.append({"round": r["round"], "arm": r["arm"], "run": str(run), "seed": r["seed"], "row": row,
                         "clash": cj, "name": name})
    print(f"{len(jobs)} episodes to do", flush=True)
    t0 = time.perf_counter()
    done = 0

    def write(job, res):
        nonlocal done
        done += 1
        if "error" in res:
            print("ERROR", job["name"], res["error"], res.get("trace", "")[-600:], flush=True)
            return
        (out / "eps" / job["name"]).write_text(json.dumps(res), "utf-8")
        if done % 20 == 0:
            print(f"{done}/{len(jobs)} {time.perf_counter() - t0:.0f}s", flush=True)
    if a.workers <= 1:
        _init()
        for j in jobs:
            write(j, _job_safe(j))
    else:
        with ProcessPoolExecutor(a.workers, initializer=_init) as ex:
            for j, res in zip(jobs, ex.map(_job_safe, jobs, chunksize=1)):
                write(j, res)
    print(f"done {done} in {time.perf_counter() - t0:.0f}s", flush=True)
    return 0


# ---- report ----

K_SET = (1, 2, 3, 4, 6, 9, 12, 15, 18, 24, 30, 36, 45, 60, 75, 90)   # forum_hit_forensics' ticks before a hit
B_DEFAULT = 2000


def _mins(e) -> float:
    return e["t"] / 60.0


def _w0(e, k):
    return ((e.get("per_wave") or {}).get("0") or {}).get(k, 0)


def _later(e, k):
    return sum(v.get(k, 0) for w, v in (e.get("per_wave") or {}).items() if w != "0")


def eff(e) -> float:
    """The person's effective mask loss of an episode: masks lost - hits landed / 4 (plan sec. 5, 2026-10-08)."""
    return e["masks"] - e["landed"] / 4.0


# metric -> (numerator, denominator) per episode; a ratio of sums over the arm's episodes
METRICS = {
    "masks/min": (lambda e: e["masks"], _mins), "hits/min": (lambda e: e["hits"], _mins),
    "landed/min": (lambda e: e["landed"], _mins), "eff/min": (eff, _mins),
    "w0 masks/min": (lambda e: _w0(e, "masks"), lambda e: _w0(e, "t") / 60.0),
    "w0 landed/min": (lambda e: _w0(e, "landed"), lambda e: _w0(e, "t") / 60.0),
    "w0 eff/min": (lambda e: _w0(e, "masks") - _w0(e, "landed") / 4.0, lambda e: _w0(e, "t") / 60.0),
    "later masks/min": (lambda e: _later(e, "masks"), lambda e: _later(e, "t") / 60.0),
    "later landed/min": (lambda e: _later(e, "landed"), lambda e: _later(e, "t") / 60.0),
    "kills/ep": (lambda e: e["kills"], lambda e: 1.0), "t": (lambda e: e["t"], lambda e: 1.0),
    "presses/min": (lambda e: e["presses"], _mins), "clashes/min": (lambda e: e["clashes"], _mins),
}


def load_arms(out: Path, pools: list[str] | None = None) -> dict[str, list[dict]]:
    """{round:arm: episodes (each with its hit rows in _hits)}; pools "name=a+b" add the union of arms."""
    by = defaultdict(list)
    for p in sorted((out / "eps").glob("*.json")):
        r = json.loads(p.read_text("utf-8"))
        e = r["episode"]
        e["_hits"] = r["hits"]
        by[f"{e['round']}:{e['arm']}"].append(e)
    for sp in pools or ():
        name, _, parts = sp.partition("=")
        by[name] = [e for a in parts.split("+") for e in by.get(a, [])]
    return dict(by)


def ratio(eps, num, den) -> float:
    return float(sum(num(e) for e in eps) / max(sum(den(e) for e in eps), 1e-9))


def ratio_ci(eps, num, den, B=B_DEFAULT, seed=0) -> list[float]:
    x = np.array([float(num(e)) for e in eps])
    t = np.array([float(den(e)) for e in eps])
    rng = np.random.default_rng(seed)
    ix = rng.integers(0, len(x), (B, len(x)))
    bs = np.sort(x[ix].sum(1) / np.maximum(t[ix].sum(1), 1e-9))
    return [round(float(bs[int(0.025 * B)]), 3), round(float(bs[int(0.975 * B) - 1]), 3)]


def ratio_diff(ea, eb, num, den, B=B_DEFAULT, seed=0) -> dict:
    """Unpaired: ratio(b) - ratio(a), bootstrap 95 % interval, two-sided p (the resamples' share across 0)."""
    xa = np.array([float(num(e)) for e in ea])
    ta = np.array([float(den(e)) for e in ea])
    xb = np.array([float(num(e)) for e in eb])
    tb = np.array([float(den(e)) for e in eb])
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, len(xa), (B, len(xa)))
    ib = rng.integers(0, len(xb), (B, len(xb)))
    ds = np.sort(xb[ib].sum(1) / np.maximum(tb[ib].sum(1), 1e-9) - xa[ia].sum(1) / np.maximum(ta[ia].sum(1), 1e-9))
    d0 = xb.sum() / max(tb.sum(), 1e-9) - xa.sum() / max(ta.sum(), 1e-9)
    p = 2 * min(float((ds <= 0).mean()), float((ds >= 0).mean()))
    return {"d": round(float(d0), 3), "ci": [round(float(ds[int(0.025 * B)]), 3),
                                              round(float(ds[int(0.975 * B) - 1]), 3)], "p": round(min(p, 1.0), 3)}


def did(arms4: list[list[dict]], num, den, B=B_DEFAULT, seed=0) -> dict:
    """Difference in differences (b2 - a2) - (b1 - a1) of a ratio over four arms (a control a and a treatment b in
    two rounds), bootstrap over each arm's episodes: whether a treatment's edge over its round's control changed."""
    rng = np.random.default_rng(seed)
    xs = [(np.array([float(num(e)) for e in eps]), np.array([float(den(e)) for e in eps])) for eps in arms4]

    def r(x, t, ix=None):
        return (x[ix].sum(-1) / np.maximum(t[ix].sum(-1), 1e-9)) if ix is not None else x.sum() / max(t.sum(), 1e-9)
    a1, b1, a2, b2 = xs
    d0 = (r(*b2) - r(*a2)) - (r(*b1) - r(*a1))
    bs = []
    for x, t in xs:
        ix = rng.integers(0, len(x), (B, len(x)))
        bs.append(r(x, t, ix))
    ds = np.sort((bs[3] - bs[2]) - (bs[1] - bs[0]))
    p = 2 * min(float((ds <= 0).mean()), float((ds >= 0).mean()))
    return {"d": round(float(d0), 3), "ci": [round(float(ds[int(0.025 * B)]), 3),
                                              round(float(ds[int(0.975 * B) - 1]), 3)], "p": round(min(p, 1.0), 3)}


def pois_p(k1: int, t1: float, k2: int, t2: float) -> float:
    """Two-sided exact test of two Poisson rates (k1 in t1 vs k2 in t2), conditional on k1 + k2."""
    n = k1 + k2
    if n == 0:
        return 1.0
    q = t1 / (t1 + t2)
    pmf = [math.comb(n, i) * q ** i * (1 - q) ** (n - i) for i in range(n + 1)]
    return min(1.0, sum(x for x in pmf if x <= pmf[k1] * (1 + 1e-9)))


def label(h: dict) -> str:
    """A hit's source label: the attack family, its chain (2 masks) or body contact, the Reed pin."""
    if h.get("pin"):
        return "Reed pin"
    return (h.get("family") or "?") + (" chain" if h.get("chain") else "") + (" body" if h.get("body") else "")


def _press_on_src(h) -> bool:
    pb = h.get("press_before_f") or []
    return bool(pb and min(pb) <= KILL_PRESS_S * 60 and h.get("win_tgt_src"))


def _low_fail(h) -> bool:
    side = (h.get("clash_table") or {}).get("side") or {}
    n, k = side.get("W_n") or 0, side.get("W_hit") or 0
    return n >= 9 and k / n <= 0.10


def _landed_recent(h) -> bool:
    lb = h.get("landed_before_f") or []
    return bool(lb and min(lb) <= LANDED_BEFORE_S * 60)


# a hit's mechanisms (several can hold) and its primary one: the first in this order (the fix that would act first)
MECHS = (
    ("pin", lambda h: h.get("pin")),
    ("Reed / Minister defence", lambda h: h.get("defence")),
    ("walked into an idle body", lambda h: h.get("walked_in") and h.get("idle_body")),
    ("locked at the attack's start", lambda h: (h.get("hero_a") or {}).get("lock_f", 0) >= 12),
    ("attacking its source (kill attempt / trade)", _press_on_src),
    ("clash geometry on a low-failure family, not clashed", lambda h: h.get("clash_geo_f") and _low_fail(h)),
    ("safe rows in the attack's window, lost", lambda h: h.get("win_safe")),
    ("saturated: no safe row in the window", lambda h: True),
)
FLAGS = (
    ("chain (2 masks)", lambda h: h.get("chain")),
    ("h <= 2 (no clash)", lambda h: ((h.get("log") or {}).get("h") or 9) <= 2),
    ("gliding at the contact", lambda h: "Umbrella" in str((h.get("hero_c") or {}).get("clip"))),
    ("landed a hit <= 0.6 s before", _landed_recent),
    ("another enemy within 1.5 u", lambda h: h.get("others_near")),
    ("source hp <= 2 swings (18)", lambda h: (h.get("src_hp") or 99) <= 18),
    ("live log named another instance", lambda h: h.get("src_fixed")),
)


def primary(h: dict) -> str:
    return next(n for n, fn in MECHS if fn(h))


def hindsight_index(dirs: list[str]) -> dict:
    """{(run, inst, ep): {tick frame: (hs_clear, replay pick's first contact, forced, seen-clear rows)}} from
    forum_hit_forensics outputs."""
    idx = {}
    for d in dirs:
        for p in sorted(Path(d).glob("*.json")):
            try:
                r = json.loads(p.read_text("utf-8"))
            except Exception:
                continue
            if "error" in r:
                continue
            idx[(r["run"], int(r["inst"]), int(r["ep"]))] = {
                int(t["f"]): (int(t.get("hs_clear") or 0), ((t.get("picks") or {}).get("replay") or [None, None])[1],
                              bool(t.get("forced")), int(t.get("seen_clear_hs") or 0))
                for t in r.get("ticks") or () if "hs_clear" in t}
    return idx


def hindsight_of(h: dict, ticks: dict) -> dict | None:
    """The last analysed tick before the contact that had a row the recorded future left clear (forum.md 19.1)."""
    have = [k for k in K_SET if (h["f_c"] - k) in ticks]
    if not have:
        return None
    clear = [k for k in have if ticks[h["f_c"] - k][0] > 0]
    k6 = ticks.get(h["f_c"] - 6)
    return {"last_clear_k": min(clear) if clear else None, "n_ticks": len(have),
            "pick_clear_6": None if k6 is None else (k6[1] is not None and k6[1] < 0),
            "seen_clear_6": None if k6 is None else k6[3] > 0}


def _kbin(k) -> str:
    if k is None:
        return "none within 1.5 s"
    if k <= 3:
        return "<= 3 f"
    if k <= 9:
        return "4-9 f"
    if k <= 18:
        return "12-18 f"
    return "24-36 f" if k <= 36 else "45-90 f"


def power(by: dict, arms: list[str], pairs: list[str], z=(1.96, 0.8416)) -> dict:
    """Episodes per arm for a 10 % / 20 % change of each rate (two-sided 5 %, power 80 %): the ratio's linearised
    per-episode values u = (x - r t) / mean(t); unpaired: their SD, paired (same round, instance, chunk seed,
    episode): the SD of the pairs' differences. Also log(survival)."""
    za, zb = z
    out = {}
    for name in ("hits/min", "masks/min", "eff/min", "w0 masks/min", "landed/min", "kills/ep"):
        num, den = METRICS[name]
        res = {}
        for arm in arms:
            eps = [e for e in by.get(arm, []) if den(e) > 0]
            if len(eps) < 10:
                continue
            x = np.array([float(num(e)) for e in eps])
            t = np.array([float(den(e)) for e in eps])
            r = x.sum() / t.sum()
            sd = float(((x - r * t) / t.mean()).std(ddof=1))
            res[arm] = {"rate": round(float(r), 3), "sd_u": round(sd, 3), "cv": round(sd / abs(r), 3) if r else None,
                        "n10": int(math.ceil(2 * ((za + zb) * sd / (0.1 * abs(r))) ** 2)) if r else None,
                        "n20": int(math.ceil(2 * ((za + zb) * sd / (0.2 * abs(r))) ** 2)) if r else None,
                        "mde80": round(float((za + zb) * sd * math.sqrt(2 / 80) / abs(r)), 3) if r else None}
        for pr in pairs:
            a, b = pr.split("~")
            ka = {(e["inst"], e["chunk_seed"], e["ep"]): e for e in by.get(a, [])}
            kb = {(e["inst"], e["chunk_seed"], e["ep"]): e for e in by.get(b, [])}
            com = [k for k in sorted(set(ka) & set(kb)) if den(ka[k]) > 0 and den(kb[k]) > 0]
            if len(com) < 10:
                continue
            xa = np.array([float(num(ka[k])) for k in com])
            ta = np.array([float(den(ka[k])) for k in com])
            xb = np.array([float(num(kb[k])) for k in com])
            tb = np.array([float(den(kb[k])) for k in com])
            ra, rb = xa.sum() / ta.sum(), xb.sum() / tb.sum()
            ua, ub = (xa - ra * ta) / ta.mean(), (xb - rb * tb) / tb.mean()
            r = 0.5 * (abs(ra) + abs(rb))
            sdd = float((ub - ua).std(ddof=1))
            res[pr] = {"pairs": len(com), "rho": round(float(np.corrcoef(ua, ub)[0, 1]), 3),
                       "n10": int(math.ceil(((za + zb) * sdd / (0.1 * r)) ** 2)),
                       "n20": int(math.ceil(((za + zb) * sdd / (0.2 * r)) ** 2)),
                       "mde80": round(float((za + zb) * sdd / math.sqrt(80) / r), 3)}
        out[name] = res
    res = {}
    for arm in arms:
        lt = np.log([max(e["t"], 1.0) for e in by.get(arm, [])])
        if len(lt) >= 10:
            sd = float(lt.std(ddof=1))
            res[arm] = {"sd_log_t": round(sd, 3), "n10": int(math.ceil(2 * ((za + zb) * sd / math.log(1.1)) ** 2)),
                        "n20": int(math.ceil(2 * ((za + zb) * sd / math.log(1.2)) ** 2))}
    out["log survival"] = res
    return out


def report(a) -> int:
    out = Path(a.out)
    by = load_arms(out, a.pool)
    arms = a.arms.split(",") if a.arms else sorted(by)
    focus = a.focus.split(",") if a.focus else arms
    res: dict = {"arms": {}, "diffs": {}, "sources": {}, "focus": {}, "mechanisms": {}, "families": {},
                 "hindsight": {}, "power": None}
    # ---- arms ----
    for arm in arms:
        eps = by.get(arm) or []
        if not eps:
            continue
        d = {"n": len(eps), "minutes": round(sum(_mins(e) for e in eps), 1),
             "t_med": round(float(np.median([e["t"] for e in eps])), 1),
             "wave0_cleared": sum(1 for e in eps if e["wave"] >= 1),
             "w0_share": round(sum(_w0(e, "t") for e in eps) / max(sum(e["t"] for e in eps), 1e-9), 3),
             "forced_share": round(sum(e["forced"] for e in eps) / max(sum(e["ticks"] for e in eps), 1), 3),
             "late_share": round(sum(e["late"] for e in eps) / max(sum(e["ticks"] for e in eps), 1), 3)}
        for name, (num, den) in METRICS.items():
            d[name] = round(ratio(eps, num, den), 3)
            if name in ("masks/min", "landed/min", "eff/min", "w0 eff/min", "kills/ep"):
                d[name + " ci"] = ratio_ci(eps, num, den)
        modes = Counter()
        for e in eps:
            modes.update(e.get("modes") or {})
        tk = max(sum(e["ticks"] for e in eps), 1)
        d["modes"] = {k: round(v / tk, 3) for k, v in modes.most_common() if v / tk >= 0.001}
        res["arms"][arm] = d
    # ---- differences ----
    for pr in a.cmp or ():
        x, y = pr.split("~")
        if x in by and y in by:
            res["diffs"][f"{y} - {x}"] = {name: ratio_diff(by[x], by[y], *METRICS[name]) for name in (
                "masks/min", "landed/min", "eff/min", "w0 masks/min", "w0 landed/min", "w0 eff/min", "kills/ep", "t",
                "presses/min")}
    for spec in a.did or ():
        q = spec.split("~")
        if len(q) == 4 and all(x in by for x in q):
            res.setdefault("did", {})[f"({q[3]} - {q[2]}) - ({q[1]} - {q[0]})"] = {
                name: did([by[x] for x in q], *METRICS[name]) for name in (
                    "masks/min", "landed/min", "eff/min", "w0 masks/min", "w0 landed/min", "w0 eff/min", "kills/ep",
                    "t")}
    # ---- sources: masks per arm and the Poisson test against the base ----
    cnt = {arm: Counter() for arm in arms}
    for arm in arms:
        for e in by.get(arm, []):
            for h in e["_hits"]:
                cnt[arm][label(h)] += h.get("masks") or 1
    mins = {arm: sum(_mins(e) for e in by.get(arm, [])) for arm in arms}
    keys = sorted(set().union(*cnt.values()), key=lambda k: -sum(cnt[x][k] for x in arms))
    for k in keys:
        if sum(cnt[x][k] for x in arms) < 10:
            continue
        res["sources"][k] = {}
        for arm in arms:
            v = {"masks": cnt[arm][k], "per_min": round(cnt[arm][k] / max(mins[arm], 1e-9), 3)}
            if a.base in cnt and arm != a.base:
                v["p_vs_base"] = round(pois_p(cnt[a.base][k], mins[a.base], cnt[arm][k], mins[arm]), 3)
            res["sources"][k][arm] = v
    # ---- the focus arms' hits: mechanisms, families, hindsight ----
    hidx = hindsight_index(a.hindsight or [])
    H = [(arm, e, h) for arm in focus for e in by.get(arm, []) for h in e["_hits"]]
    tot = sum(h.get("masks") or 1 for _, _, h in H)
    res["focus"] = {"arms": focus, "hits": len(H), "masks": tot,
                    "minutes": round(sum(sum(_mins(e) for e in by.get(x, [])) for x in focus), 1)}
    mech = defaultdict(lambda: {"hits": 0, "masks": 0, "hs_n": 0, "hs_avoid": 0, "families": Counter()})
    fam = defaultdict(lambda: {"hits": 0, "masks": 0, "primary": Counter(), "flags": Counter(), "hs_n": 0,
                               "hs_avoid": 0, "d0": [], "wind": []})
    kb = Counter()
    for arm, e, h in H:
        m = h.get("masks") or 1
        pm = primary(h)
        hs = None
        key = (e["run"], int(e["inst"]), int(e["ep"]))
        if key in hidx:
            hs = hindsight_of(h, hidx[key])
        avoid = None if hs is None else (hs["last_clear_k"] is not None and 4 <= hs["last_clear_k"] <= 36)
        for d_ in (mech[pm], fam[label(h)]):
            d_["hits"] += 1
            d_["masks"] += m
            if avoid is not None:
                d_["hs_n"] += 1
                d_["hs_avoid"] += bool(avoid)
        mech[pm]["families"][label(h)] += m
        f_ = fam[label(h)]
        f_["primary"][pm] += m
        for n, fn in FLAGS + MECHS[:-1]:
            if fn(h):
                f_["flags"][n] += m
        if (h.get("hero_a") or {}).get("dist") is not None:
            f_["d0"].append(h["hero_a"]["dist"])
        if h.get("wind_s") is not None:
            f_["wind"].append(h["wind_s"])
        if hs is not None:
            kb[_kbin(hs["last_clear_k"])] += 1
    res["mechanisms"] = {k: {"hits": v["hits"], "masks": v["masks"], "share": round(v["masks"] / max(tot, 1), 3),
                             "hindsight_n": v["hs_n"],
                             "avoidable": round(v["hs_avoid"] / v["hs_n"], 3) if v["hs_n"] else None,
                             "families": dict(v["families"].most_common(6))}
                         for k, v in sorted(mech.items(), key=lambda z: -z[1]["masks"])}
    res["families"] = {k: {"hits": v["hits"], "masks": v["masks"], "share": round(v["masks"] / max(tot, 1), 3),
                           "primary": dict(v["primary"].most_common()),
                           "flags": {n: round(c / v["masks"], 2) for n, c in v["flags"].most_common()},
                           "d0_med": round(float(np.median(v["d0"])), 2) if v["d0"] else None,
                           "wind_med": round(float(np.median(v["wind"])), 2) if v["wind"] else None,
                           "hindsight_n": v["hs_n"],
                           "avoidable": round(v["hs_avoid"] / v["hs_n"], 3) if v["hs_n"] else None}
                       for k, v in sorted(fam.items(), key=lambda z: -z[1]["masks"]) if v["masks"] >= 10}
    res["hindsight"] = {"episodes": sum(1 for arm in focus for e in by.get(arm, [])
                                        if (e["run"], int(e["inst"]), int(e["ep"])) in hidx),
                        "last_clear": dict(kb.most_common())}
    res["power"] = power(by, arms, a.pairs or [])
    txt = json.dumps(res, indent=1, ensure_ascii=False)
    if a.json:
        Path(a.json).write_text(txt, "utf-8")
    print(txt)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--manifest", action="append", required=True, help="label=path (the label prefixes the arms)")
    c.add_argument("--arms", default=None, help="round:arm,... (default: all)")
    c.add_argument("--out", required=True)
    c.add_argument("--workers", type=int, default=2)
    r = sub.add_parser("report")
    r.add_argument("--out", required=True)
    r.add_argument("--json", default=None)
    r.add_argument("--arms", default=None, help="the arms reported (default: all)")
    r.add_argument("--pool", action="append", help="name=a+b: an arm that pools others")
    r.add_argument("--base", default="r1:new", help="the arm the per-source Poisson tests compare with")
    r.add_argument("--cmp", action="append", help="x~y: y - x (unpaired bootstrap)")
    r.add_argument("--pairs", action="append", help="x~y: paired power (same round, instance, seed, episode)")
    r.add_argument("--did", action="append", help="a1~b1~a2~b2: difference in differences (b2 - a2) - (b1 - a1)")
    r.add_argument("--focus", default=None, help="the arms whose hits are explained (default: --arms)")
    r.add_argument("--hindsight", action="append", help="forum_hit_forensics output dirs of the focus arms' runs")
    a = ap.parse_args(argv)
    return collect(a) if a.cmd == "collect" else report(a)


if __name__ == "__main__":
    sys.exit(main())
