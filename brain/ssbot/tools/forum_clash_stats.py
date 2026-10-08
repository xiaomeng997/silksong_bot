"""Clash (NailClash) opportunities and outcomes in Forum recordings (forum_planner_plan R8: the EV_CLASH branch's
success rates by type x move x direction, from the R1 v2 labelled data and the person's practice sessions).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.forum_clash_stats <run dir | human session> ... --out clash.json
        [--max-fights N] [--inflate 0.3]

A swing is the frame the hero's attack cooldown jumps up (HeroController.DidAttack; STATE hero.tm.atk_cd), its slot
from the clip that frame (UpSlash / DownSlash* / WallSlash / Slash*), its active window from the crest's attack table
(knowledge/<build>/attacks/<crest>.json: live frames where sampled, else the clip's t_on / t_off; the Reaper down
slash: the FSM's antic + slash frames as the planner has them). A clash setup of an enemy e for a swing: inside the
window, one of e's enabled damage colliders with the clash bit (DamageHero.canClashTink: export parry bit 1) meets the
swing's clash reach (the slot's Clash Tink box, else its damage polygons; placed at the hero collider centre, mirrored
by the facing) at frame k_c, and none of e's enabled damage colliders touched the hero box (inflated by --inflate) on
a frame of the swing before k_c (a contact that came first is a hit the clash did not get to). This is the planner's
EV_CLASH premise (the swing out when the enemy's clashable layer arrives, before the hurtbox contact).
Outcome of a setup: clash = a NailClashEffect freeze starts in [k_c - 1, window end + 1] and the nearest enabled
clashable collider on the frame before belongs to e; other_clash = it belongs to another enemy (the hero is
invulnerable 0.15 s either way); hit = a damage event (or a Multihit special damage) from e's type, e the nearest of
its type, in [swing start, k_c + 12 frames] and no clash before it; neither = none of these (the enemy's collider did
not come on). The move is e's Control state at k_c and its attack family (the type's behaviour table); same_frame:
the inflated hero box already met e's collider at k_c.
Also per clash: what came in the next 0.5 s from the same enemy (another clash, a hit, the collider's name: the
multi-segment chains), and damage blocked within 0.2 s after (the two-sided rule: the parry i-frames take any enemy
damage).
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.combat.planner import _rect_meets_polys
from ssbot.ipc.ents import collider_points
from ssbot.knowledge.attack_shapes import AttackTable
from ssbot.knowledge.gauntlet_tables import FORUM_SPECS
from ssbot.train.gauntlet import in_play
from ssbot.train.wave_start import PARKED_STATES

FORUM_DIR = Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / "forum"
CD_JUMP = 0.15                   # atk_cd rising by more than this from one frame to the next: DidAttack
FAIL_F = 12                      # a hit from e up to this many frames after k_c is the setup's failure
CHAIN_F = 30                     # frames after a clash whose events from the same enemy are recorded (0.5 s)
BLOCK_F = 12                     # frames after a clash whose damage_blocked events are counted (0.2 s)
RPR_DOWN = (9, 20)               # Reaper down slash: antic 0.150 s, slash 0.167 s (forum_planner RPR_ANTIC_F / _SLASH_F)
CLASH_BIT = 1                    # export parry bits: 1 clash (canClashTink), 4 counter
PROJECTILES = {"Throwing Bell": "Pilgrim 03 Song", "Song Reed Pin Projectile": "Song Reed",
               "Spear": "Song Handmaiden", "handmaiden_spear_silk_explosion": "Song Handmaiden"}


def state_families() -> dict[str, dict[str, str]]:
    """{type key: {Control state: attack family}} from the behaviour tables (the first family listing a state)."""
    out: dict[str, dict[str, str]] = {}
    for p in sorted(FORUM_DIR.glob("*.json")):
        d = json.loads(p.read_text("utf-8"))
        if "attacks" not in d or not d.get("boss_type"):
            continue
        m = out.setdefault(d["boss_type"], {})
        for fam, a in d["attacks"].items():
            for st in a.get("states") or ():
                m.setdefault(st, fam)
    return out


def slot_of(clip: str | None, wall: bool) -> str | None:
    c = str(clip or "")
    if "Down" in c:
        return "down"
    if "Up" in c:
        return "up"
    if "Wall" in c or (wall and "Slash" in c):
        return "wall"
    if "Slash" in c or "Stab" in c:
        return "normal"
    return None


class Reach:
    """Per crest and slot: the clash reach polygons (facing frame, relative to the hero collider centre) and the
    active window in frames after the swing's frame."""

    def __init__(self):
        self.tabs: dict[str, AttackTable] = {}

    def get(self, crest: str, slot: str):
        tab = self.tabs.get(crest)
        if tab is None:
            tab = self.tabs[crest] = AttackTable.load(crest)
        sh = tab.shapes.get(slot) or tab.shapes.get("normal")
        if sh.clash_box:
            x0, x1, y0, y1 = sh.clash_box
            polys = (np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64),)
        else:
            polys = sh.polys
        if crest == "Reaper" and slot == "down":
            win = RPR_DOWN
        elif sh.frames:
            win = (int(sh.frames[0]), int(sh.frames[1]))
        else:
            win = (int(round(sh.t_on * 60)), max(int(round(sh.t_on * 60)), int(round(sh.t_off * 60)) - 1))
        return polys, win


def _poly_world(polys, cx: float, cy: float, face: int):
    f = 1.0 if face >= 0 else -1.0
    vs = [np.c_[cx + f * p[:, 0], cy + p[:, 1]] for p in polys]
    return np.ascontiguousarray(np.concatenate(vs)), np.cumsum([0] + [len(p) for p in vs]).astype(np.int64)


def _aabb(c: dict):
    pts = collider_points(c)
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    r = float(c.get("r") or 0.0) if c.get("kind") == "circle" else 0.0
    return min(xs) - r, min(ys) - r, max(xs) + r, max(ys) + r


def _gap(a, b) -> float:
    return max(a[0] - b[2], b[0] - a[2], 0.0) + max(a[1] - b[3], b[1] - a[3], 0.0)


def frames_of(src: Path, max_fights: int | None):
    """(unit id, iterator of STATE dicts) per fight of a run dir, or one per human session (Hang_04 frames only)."""
    if (src / "state.raw.zst").exists():
        from ssbot.ipc.framing import MsgType
        from ssbot.tools.forum_demo import _stream

        def it():
            for t, m in _stream(src / "state.raw.zst"):
                if t == MsgType.STATE and ((m.get("game") or {}).get("scene") == "Hang_04"):
                    yield m
        yield f"human/{src.name}", it()
        return
    from ssbot.knowledge.behaviour_tables import fight_states, run_fights
    fights, _ = run_fights(src)
    for fi in fights[:max_fights] if max_fights else fights:
        yield fi.id, fight_states(fi, keys=("f", "hero", "ents", "ev"))


def _enemies(s: dict) -> list[dict]:
    return [e for e in s.get("ents") or () if e.get("type_key") in FORUM_SPECS and (e.get("hp") or 0) > 0
            and not e.get("is_dead") and in_play(e)
            and not any(fs.get("state") in PARKED_STATES for fs in e.get("fsms") or ())]


def _cols(e: dict):
    """(aabb, clash) of e's enabled damaging colliders."""
    out = []
    for c in e.get("colliders") or ():
        d = c.get("damage") or {}
        if not c.get("enabled") or not d or not d.get("can_cause_damage") or not d.get("eff"):
            continue
        bb = _aabb(c)
        if bb is not None:
            out.append((bb, bool(int(d.get("parry") or 0) & CLASH_BIT), str(c.get("name") or "")))
    return out


def _control_state(e: dict) -> str | None:
    ctl = FORUM_SPECS[e["type_key"]].control_fsm
    for fs in e.get("fsms") or ():
        if fs.get("name") == ctl:
            return fs.get("state")
    return None


def _src_type(src: str | None) -> str | None:
    if not src:
        return None
    head = src.split("/")[0].replace("(Clone)", "").strip()
    for k, v in PROJECTILES.items():
        if head.startswith(k):
            return v
    if head == "Colliders":
        return "Song Administrator"
    parts = src.split("/")
    for p in parts:
        name = p.split(" (")[0].replace("(Clone)", "").strip()
        if name in FORUM_SPECS:
            return name
    return None


def _contact_setup(buf, i0, iid, a, b, inflate, clash_at, hits, hit_owner, fams, crest, slot, acc):
    """The planner's EV_CLASH rule on the recording: e's first contact with the inflated hero box in the swing (any
    damage collider, the body included) falls inside the swing's active window -> clash / hit / neither, keyed by e's
    move at the contact and whether e was in front of the facing (a side slash covers only the front)."""
    n = len(buf)
    k_h = None
    for k in range(i0, min(n, i0 + b + 2)):
        ent = buf[k]["ents"].get(iid)
        if ent is None:
            continue
        hb = buf[k]["box"]
        big = (hb[0] - inflate, hb[1] - inflate, hb[2] + inflate, hb[3] + inflate)
        if any(_gap(bb, big) == 0.0 for bb, _, _ in ent[2]):
            k_h = k
            break
    if k_h is None or k_h < i0 + a or k_h == i0:
        return None
    tk, st, cols, pos = buf[k_h]["ents"][iid]
    fam = fams.get(tk, {}).get(st or "", "?")
    hb = buf[k_h]["box"]
    dx = pos[0] - 0.5 * (hb[0] + hb[2])
    side = "front" if dx * buf[i0]["face"] >= 0 else "behind"
    out = "neither"
    t_out = None
    for k in range(i0, min(n, k_h + 3)):
        for c in clash_at.get(k, ()):
            out, t_out = ("clash" if c[1] == iid else "other_clash"), k
            break
        if t_out is not None:
            break
    if out != "clash":
        for j, (hi, htk, hsrc) in enumerate(hits):
            if hi < i0 or hi > k_h + FAIL_F:
                continue
            if htk == tk and hit_owner[j] == iid and (t_out is None or hi <= t_out):
                out = "hit"
                break
    clashable = any(cl for _, cl, _ in cols)
    acc["contact_setups"][f"{crest}|{tk}|{fam}|{slot}|{side}|{int(clashable)}"][out] += 1
    return k_h, tk, fam, side, out


def scan(unit: str, states, reach: Reach, fams: dict, inflate: float, acc: dict) -> None:
    buf: list[dict] = []          # the frames of the fight (only what the scan needs)
    for s in states:
        h = s.get("hero") or {}
        if not h.get("box"):
            continue
        ents = _enemies(s)
        buf.append({"f": s["f"], "box": tuple(h["box"]), "face": 1 if (h.get("facing") or 1) >= 0 else -1,
                    "cd": (h.get("tm") or {}).get("atk_cd"), "clip": (h.get("anim") or {}).get("clip"),
                    "wall": bool((h.get("wall") or [False])[0]) if isinstance(h.get("wall"), list) else False,
                    "crest": h.get("crest") or "Reaper",
                    "ents": {e["iid"]: (e["type_key"], _control_state(e), _cols(e),
                                        tuple(e.get("pos") or (0.0, 0.0))[:2]) for e in ents},
                    "ev": [(ev.get("k"), ev.get("d") or {}) for ev in s.get("ev") or ()
                           if ev.get("k") in ("freeze", "damage", "special_damage", "damage_blocked")]})
    if not buf:
        return
    n = len(buf)
    # clash events: index, owner iid (nearest clashable collider on the frame before), collider name
    clashes = []
    hits = []                     # (index, type key or None, source)
    blocked = []
    for i, fr in enumerate(buf):
        for k, d in fr["ev"]:
            if k == "freeze" and d.get("phase") == "start" and d.get("type") == "NailClashEffect":
                pv = buf[i - 1] if i else fr
                hb = pv["box"]
                best = None
                for iid, (tk, st, cols, pos) in pv["ents"].items():
                    for bb, cl, name in cols:
                        if cl:
                            g = _gap(bb, hb)
                            if best is None or g < best[0]:
                                best = (g, iid, tk, st, name)
                clashes.append((i, best[1] if best else None, best[2] if best else None,
                                best[3] if best else None, best[4] if best else None))
            elif k == "damage":
                hits.append((i, _src_type(d.get("source")), str(d.get("source"))))
            elif k == "special_damage" and "Multihit" in str(d.get("fsm") or ""):
                hits.append((i, "?multihit", "Multihit"))
            elif k == "damage_blocked":
                blocked.append((i, str(d.get("why")), _src_type(d.get("source"))))
    clash_at = defaultdict(list)
    for c in clashes:
        clash_at[c[0]].append(c)
    hit_idx = [h[0] for h in hits]

    def nearest_of_type(i: int, tk: str):
        fr = buf[i]
        hb = fr["box"]
        best = None
        for iid, (t, st, cols, pos) in fr["ents"].items():
            if t != tk or not cols:
                continue
            g = min(_gap(bb, hb) for bb, _, _ in cols)
            if best is None or g < best[0]:
                best = (g, iid)
        return best[1] if best else None
    # the hit's enemy: for a typed source the nearest enemy of that type on the frame before; a Multihit tick: the
    # chain's owner is the nearest enemy whose clashable / damaging collider touched within 70 frames (left None)
    hit_owner = []
    for i, tk, src in hits:
        hit_owner.append(nearest_of_type(max(i - 1, 0), tk) if tk and tk in FORUM_SPECS else None)
    i = 1
    while i < n:
        fr, pv = buf[i], buf[i - 1]
        if fr["cd"] is None or pv["cd"] is None or fr["cd"] - pv["cd"] <= CD_JUMP:
            i += 1
            continue
        slot = slot_of(fr["clip"], fr["wall"])
        if slot is None and i + 1 < n:
            slot = slot_of(buf[i + 1]["clip"], buf[i + 1]["wall"])
        crest = fr["crest"]
        acc["swings"][f"{crest}/{slot}"] += 1
        if slot is None:
            i += 1
            continue
        polys, (a, b) = reach.get(crest, slot)
        i0 = i
        for iid in fr["ents"]:
            cs = _contact_setup(buf, i0, iid, a, b, inflate, clash_at, hits, hit_owner, fams, crest, slot, acc)
            cl = _clash_setup(buf, i0, iid, a, b, polys, inflate, clash_at, hits, hit_owner, fams, crest, slot, unit,
                              fr["face"], acc)
            # the union (an opportunity the planner's rule may see either way: the attack meets the clash reach first,
            # or reaches the hurtbox while the swing is out), keyed at its first frame
            u = [x for x in (cs, cl) if x is not None]
            if u:
                first = min(u, key=lambda x: x[0])
                outs = {x[-1] for x in u}
                out = next(o for o in ("clash", "hit", "other_clash", "neither") if o in outs)
                acc["union_setups"][f"{crest}|{first[1]}|{first[2]}|{slot}|{first[3]}"][out] += 1
        i += 1
    _after(clashes, hits, blocked, buf, fams, acc)
    acc["clashes"] += len(clashes)
    acc["hits"] += len(hits)
    acc["frames"] += n


def _clash_setup(buf, i0, iid, a, b, polys, inflate, clash_at, hits, hit_owner, fams, crest, slot, unit, face0, acc):
    """The clash reach meets one of e's clash colliders inside the window before any of e's colliders touched the
    inflated hero box: (k_c, type, family, side, outcome) or None."""
    n = len(buf)
    k_c = None
    touched_before = False
    same = False
    for k in range(i0, min(n, i0 + b + 1)):
        fk = buf[k]
        ent = fk["ents"].get(iid)
        if ent is None:
            continue
        tk, st, cols, pos = ent
        hb = fk["box"]
        big = (hb[0] - inflate, hb[1] - inflate, hb[2] + inflate, hb[3] + inflate)
        touch = any(_gap(bb, big) == 0.0 for bb, _, _ in cols)
        if k >= i0 + a:
            cx, cy = 0.5 * (hb[0] + hb[2]), 0.5 * (hb[1] + hb[3])
            v, stt = _poly_world(polys, cx, cy, fk["face"])
            meet = any(cl and _rect_meets_polys(bb[0], bb[1], bb[2], bb[3], v, stt, 0.0, 0.0)
                       for bb, cl, _ in cols)
            if meet:
                k_c, same = k, touch
                break
        if touch:
            touched_before = True
            break
    if k_c is None or touched_before:
        return None
    tk, st, cols, pos = buf[k_c]["ents"][iid]
    fam = fams.get(tk, {}).get(st or "", "?")
    dx = pos[0] - 0.5 * (buf[k_c]["box"][0] + buf[k_c]["box"][2])
    dy = pos[1] - 0.5 * (buf[k_c]["box"][1] + buf[k_c]["box"][3])
    out = "neither"
    t_out = None
    for k in range(max(i0, k_c - 1), min(n, i0 + b + 2)):
        for c in clash_at.get(k, ()):
            if c[1] == iid:
                out, t_out = "clash", k
            elif out != "clash":
                out, t_out = "other_clash", k
        if out == "clash":
            break
    if out not in ("clash",):
        for j, (hi, htk, hsrc) in enumerate(hits):
            if hi < i0 or hi > k_c + FAIL_F:
                continue
            if htk == tk and hit_owner[j] == iid and (t_out is None or hi <= t_out):
                out, t_out = "hit", hi
                break
    key = f"{crest}|{tk}|{fam}|{st}|{slot}"
    row = acc["setups"][key]
    row["n"] += 1
    row[out] += 1
    row["same_frame"] += int(same)
    row["same_frame_" + out] += int(same)
    side = "front" if dx * face0 >= 0 else "behind"
    acc["by_side"][f"{crest}|{tk}|{slot}|{side}"][out] += 1
    if len(acc["examples"][out]) < 40:
        acc["examples"][out].append({"unit": unit, "f": buf[i0]["f"], "k_c": k_c - i0, "type": tk,
                                     "state": st, "slot": slot, "crest": crest, "t_out": None if t_out is None
                                     else t_out - i0, "dx": round(dx, 2), "dy": round(dy, 2)})
    return k_c, tk, fam, side, out


def _after(clashes, hits, blocked, buf, fams, acc) -> None:
    """After each clash: the same enemy's next events (chains) and blocked damage (two-sided)."""
    for ci, owner, tk, st, name in clashes:
        fam = fams.get(tk or "", {}).get(st or "", "?")
        key = f"{buf[ci]['crest']}|{tk}|{fam}|{st}|{name}"
        row = acc["after_clash"][key]
        row["n"] += 1
        nxt = [c for c in clashes if ci < c[0] <= ci + CHAIN_F and c[1] == owner]
        row["reclash"] += int(bool(nxt))
        if nxt:
            row["reclash_gap_f"].append(nxt[0][0] - ci)
            row["reclash_names"][str(nxt[0][4])] += 1
        hx = [(hi, htk) for hi, htk, _ in hits if ci < hi <= ci + CHAIN_F and (htk == tk or htk == "?multihit")]
        row["hit_after"] += int(bool(hx))
        if hx:
            row["hit_gap_f"].append(hx[0][0] - ci)
        for bi, why, btk in blocked:
            if ci <= bi <= ci + BLOCK_F:
                acc["blocked_after_clash"][f"{why}|same={btk == tk}"] += 1


def _rate(a: int, n: int) -> float | None:
    return round(a / n, 4) if n else None


def summarise(acc: dict) -> dict:
    rows = []
    for key, r in sorted(acc["setups"].items()):
        crest, tk, fam, st, slot = key.split("|")
        rows.append({"crest": crest, "type": tk, "family": fam, "state": st, "slot": slot, "n": r["n"],
                     "clash": r["clash"], "other_clash": r["other_clash"], "hit": r["hit"], "neither": r["neither"],
                     "p_clash": _rate(r["clash"], r["n"]), "p_hit": _rate(r["hit"], r["n"]),
                     "same_frame": r["same_frame"], "same_frame_hit": r["same_frame_hit"],
                     "same_frame_clash": r["same_frame_clash"]})
    fam_rows = defaultdict(Counter)
    for r in rows:
        k = f"{r['crest']}|{r['type']}|{r['family']}|{r['slot']}"
        for x in ("n", "clash", "other_clash", "hit", "neither", "same_frame", "same_frame_hit"):
            fam_rows[k][x] += r[x]
    fams = []
    for k, c in sorted(fam_rows.items()):
        crest, tk, fam, slot = k.split("|")
        n = c["n"]
        # Wilson upper bound of the failure rate (95 %): what the planner should carry when n is small
        p = c["hit"] / n if n else 0.0
        z = 1.96
        ub = ((p + z * z / (2 * n) + z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)) if n else 1.0
        fams.append({"crest": crest, "type": tk, "family": fam, "slot": slot, **dict(c),
                     "p_clash": _rate(c["clash"], n), "p_hit": _rate(c["hit"], n), "p_hit_ub95": round(ub, 4)})
    after = []
    for key, r in sorted(acc["after_clash"].items()):
        crest, tk, fam, st, name = key.split("|")
        g = r["reclash_gap_f"]
        after.append({"crest": crest, "type": tk, "family": fam, "state": st, "collider": name, "n": r["n"],
                      "reclash": r["reclash"], "reclash_gap_f_p50": float(np.median(g)) if g else None,
                      "reclash_names": dict(r["reclash_names"]), "hit_after": r["hit_after"],
                      "hit_gap_f_p50": float(np.median(r["hit_gap_f"])) if r["hit_gap_f"] else None})
    contact = []
    for key, c in sorted(acc["contact_setups"].items()):
        crest, tk, fam, slot, side, cl = key.split("|")
        n = sum(c.values())
        contact.append({"crest": crest, "type": tk, "family": fam, "slot": slot, "side": side,
                        "clashable_collider_on": bool(int(cl)), "n": n, **dict(c),
                        "p_clash": _rate(c["clash"], n), "p_hit": _rate(c["hit"], n)})
    union = []
    for key, c in sorted(acc["union_setups"].items()):
        crest, tk, fam, slot, side = key.split("|")
        n = sum(c.values())
        union.append({"crest": crest, "type": tk, "family": fam, "slot": slot, "side": side, "n": n, **dict(c),
                      "p_clash": _rate(c["clash"], n), "p_hit": _rate(c["hit"], n)})
    return {"swings": dict(acc["swings"]), "clashes": acc["clashes"], "hits": acc["hits"], "frames": acc["frames"],
            "units": acc["units"], "by_family": fams, "by_state": rows, "contact_setups": contact,
            "union_setups": union,
            "after_clash": after,
            "blocked_after_clash": dict(acc["blocked_after_clash"]),
            "by_side": {k: dict(v) for k, v in sorted(acc["by_side"].items())}, "examples": acc["examples"]}


def new_acc() -> dict:
    return {"swings": Counter(), "setups": defaultdict(Counter), "by_side": defaultdict(Counter),
            "contact_setups": defaultdict(Counter), "union_setups": defaultdict(Counter),
            "after_clash": defaultdict(lambda: {"n": 0, "reclash": 0, "reclash_gap_f": [], "reclash_names": Counter(),
                                                "hit_after": 0, "hit_gap_f": []}),
            "blocked_after_clash": Counter(), "examples": defaultdict(list), "clashes": 0, "hits": 0, "frames": 0,
            "units": 0}


# never clashed whatever the data (forum.md: canClashTink 0 on the Clapper's body and slams, the Clawmaiden spear; the
# Bellbearer's bell has the counter bit only; the Tinies ram with their bodies), and the families that are bodies only
NEVER_TYPES = {"Song Heavy Sentry": "Clapper: body and slams canClashTink 0",
               "Song Automaton Tiny": "Tiny: rams with its body",
               "Pilgrim 03 Song": "Bellbearer: the bell has the counter bit only (redirect, no clash)"}
NEVER_FAMILIES = {("Song Handmaiden", "CM_SPIN"): "Clawmaiden spear and its explosion: canClashTink 0"}
BODY_SUFFIX = ("_IDLE", "_ENTRY", "_EVADE", "_TELE", "_LEAVE")


def wilson_ub(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 1.0
    p = k / n
    return (p + z * z / (2 * n) + z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def build_table(stats: list[dict], min_n: int = 10, kind: str = "union_setups") -> dict:
    """clash.json from forum_clash_stats outputs: per (type, family, slot) the union setups (the planner's EV_CLASH
    premise on the recordings: the enemy's attack meets the swing's clash reach first, or reaches the inflated hurtbox
    while the swing is out; a contact setup alone misses the clashes that kept the attack off the hurtbox), a side or
    wall slash only with the enemy in front, up / down whatever the horizontal side, both crests pooled (the rule
    conditions on the window, which is where the crests differ), p_fail = the Wilson 95 % upper bound of hit / n;
    keys with n < min_n, the NEVER types / families and the body-only families are left out (= not clashable)."""
    agg: dict = defaultdict(Counter)
    by_crest: dict = defaultdict(Counter)
    for st in stats:
        for r in st.get(kind) or ():
            slot = "side" if r["slot"] == "normal" else r["slot"]
            if slot in ("side", "wall") and r["side"] != "front":
                continue
            key = (r["type"], r["family"], slot)
            for x in ("clash", "hit", "neither", "other_clash"):
                agg[key][x] += int(r.get(x) or 0)
                by_crest[key + (r["crest"],)][x] += int(r.get(x) or 0)
    p_fail, left_out = {}, {}
    for (tk, fam, slot), c in sorted(agg.items()):
        n = sum(c.values())
        why = NEVER_TYPES.get(tk) or NEVER_FAMILIES.get((tk, fam)) or \
            ("body / movement family" if fam == "?" or fam.endswith(BODY_SUFFIX) else None) or \
            (f"n {n} < {min_n}" if n < min_n else None)
        row = {"n": n, **{x: c[x] for x in ("clash", "hit", "neither", "other_clash")},
               "p_hit": round(c["hit"] / n, 4) if n else None, "p_fail": round(wilson_ub(c["hit"], n), 4),
               "by_crest": {cr: dict(v) for (t2, f2, s2, cr), v in by_crest.items() if (t2, f2, s2) == (tk, fam, slot)}}
        if why:
            left_out[f"{tk}|{fam}|{slot}"] = {**row, "why": why}
        else:
            p_fail[f"{tk}|{fam}|{slot}"] = row
    return {"build": "1.0.30000", "rule": build_table.__doc__.split("\n\n")[0].replace("\n", " "),
            "min_n": min_n, "kind": kind, "p_fail": p_fail, "left_out": left_out,
            "never_types": NEVER_TYPES, "never_families": {f"{a}|{b}": v for (a, b), v in NEVER_FAMILIES.items()}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", nargs="+", help="run dirs (fights) or human sessions (state.raw.zst); with --table: the "
                                           "stats JSONs to merge")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-fights", type=int, default=None)
    ap.add_argument("--inflate", type=float, default=0.3)
    ap.add_argument("--table", action="store_true", help="build clash.json from stats JSONs")
    ap.add_argument("--min-n", type=int, default=10)
    a = ap.parse_args(argv)
    if a.table:
        tab = build_table([json.loads(Path(p).read_text("utf-8")) for p in a.src], a.min_n)
        tab["source"] = a.src
        Path(a.out).write_text(json.dumps(tab, indent=1) + "\n", encoding="utf-8")
        for k, v in tab["p_fail"].items():
            print(f"{k:50s} n {v['n']:5d} clash {v['clash']:4d} hit {v['hit']:3d} p_fail {v['p_fail']}")
        return 0
    reach, fams, acc = Reach(), state_families(), new_acc()
    for src in a.src:
        for unit, states in frames_of(Path(src), a.max_fights):
            scan(unit, states, reach, fams, a.inflate, acc)
            acc["units"] += 1
        print(f"{src}: units {acc['units']} swings {sum(acc['swings'].values())} clashes {acc['clashes']}", flush=True)
    out = summarise(acc)
    out["src"] = a.src
    out["inflate"] = a.inflate
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for r in sorted(out["by_family"], key=lambda r: -r["n"])[:40]:
        print(f"{r['crest']:8s} {r['type'][:22]:22s} {r['family']:12s} {r['slot']:6s} n {r['n']:5d} clash "
              f"{r['clash']:4d} hit {r['hit']:4d} other {r['other_clash']:3d} neither {r['neither']:4d} "
              f"p_hit {r['p_hit']} ub {r['p_hit_ub95']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
