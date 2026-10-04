"""The person's Forum (High Halls gauntlet) demo recordings: every attempt, wave by wave (M2 W8 / K1 input; facts in
docs/facts/1.0.30000/forum_human_demo.md).

    ..\\scripts\\uv.cmd run python -m ssbot.tools.forum_demo C:/ssbot/data/human/<session> [more sessions]
        [--json out.json] [--cache <dir>] [--random-runs <run dir> ...]

Input: ssbot.tools.human_session recordings (state.raw.zst: every oracle STATE with room.battles and allies; the
oracle only observes, so a death is a real death and the person walks back in from the Hang_06b bench). One pass
(scan) keeps per frame the hero, the input mask, the battle's wave and the live enemies (compact), every event but
pause_gate, and the full entity list (colliders) for the frames around each hit the hero took; --cache keeps that
pass as a pickle per session.

An attempt is one "Battle Scene" instance (room.battles id; the room reloads after a death) from its first started
frame to the death ("die" event), the clear (completed) or the last frame of that instance (left / session end).
Per attempt: the waves reached and the time of each (game seconds: sum of udt x time scale, so hit stops count as
their scaled length), every mask lost (hp events with delta < 0: the source path, enemy type, attack collider or
projectile, the attacker's attack family from its control FSM (FORUM_SPECS: the last attack-start state within 4 s,
otherwise <P>_IDLE = body contact between attacks), the hero's position, animation and contact state one frame
before, how many enemies were in play and how close their enabled damage colliders were (STATE hero.box, the physics
collider, not the hurt box)), multi-hit chains (Choristor whip, Reed / Minister parry counter: "Multihit"
TakeQuickDamage follow-ups then "Final Hit"; a chain cut by the death or left without its Final Hit is flagged in
chain_cut), the enemy-seconds each type was in play (per-type rates are per enemy-minute: raw hit shares mostly
follow exposure), the hero's start and lowest silk, heals (Bind AddHealth) and Bind starts, kills and the killer (hero
attack, Garmond, Cogfly, a batted Throwing Bell), technique use (dash, dash attack, Clawline, wall cling, glide,
down slash, Cogfly throws, Silkspear hits), the hero's position at each wave start, and key presses per second
(ssbot.tools.key_economy's count: rising edges of input.mask, gameplay keys only).

--random-runs adds the random data policy's Forum runs (AttemptRecords: wave times and hit sources) for comparison.
"""
import argparse
import json
import pickle
import statistics
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

import msgpack
import zstandard

from ssbot.ipc.framing import HEADER, MsgType
from ssbot.knowledge.gauntlet_tables import FORUM_SPECS
from ssbot.tools.forum_pocket import collider_box_distance
from ssbot.tools.key_economy import MENU_KEYS, holds_from_masks
from ssbot.train.encounters import FORUM_WAVES
from ssbot.train.gauntlet import DEAD_REPEAT_F, WAITING_STATES, live_enemies, type_key

FPS = 60.0
BATTLE = "Battle Scene"
CSTATE_FACTS = Path(__file__).resolve().parents[3] / "docs" / "facts" / "1.0.30000" / "cstate_schema.json"

# game names (forum.md §9.1): internal type -> (English, Chinese)
NAMES = {
    "Song Pilgrim 03": ("Choristor", "圣咏使徒"), "Song Pilgrim 01": ("Envoy", "圣咏特使"),
    "Pilgrim 03 Song": ("Choir Bellbearer", "圣咏钟卫"), "Song Reed": ("Reed", "簧片战士"),
    "Song Handmaiden": ("Clawmaiden", "丝偶侍女"), "Song Administrator": ("Minister", "圣咏大臣"),
    "Song Pilgrim Maestro": ("Maestro", "圣咏指挥"), "Song Heavy Sentry": ("Choir Clapper", "圣咏槌手"),
    "Song Automaton Tiny": ("Tiny", "小机械（Maestro 召唤）"),
}
# hazards and projectiles named without their owner: path prefix -> owner type
PROJECTILES = {
    "Throwing Bell": "Pilgrim 03 Song", "Song Reed Pin Projectile": "Song Reed", "Spear": "Song Handmaiden",
    "handmaiden_spear_silk_explosion": "Song Handmaiden", "rune bomb small": "Song Heavy Sentry",
    "rune slam": "Song Heavy Sentry",
}
GARMOND = frozenset(("WildSlash Enemy Damager", "Stomp Damager", "Stomp Splash Damager", "Charge Damager"))
COGFLY = frozenset(("Damager",))
BELL = frozenset(("Enemy Damager",))
# the hero's own attack sources ("hit" src); anything else that is not a helper is reported as "other"
HERO_ATTACKS = frozenset(("Slash", "AltSlash", "UpSlash", "DownSlash", "DownSlash New", "DownSlashAlt", "WallSlash",
                          "DashStab", "DashStabAlt", "DashUpper Slash", "Harpoon Damager", "Harpoon Dash Damager",
                          "Needle Damage", "Extra Damager"))
# animation clips whose start counts as one use (clip prefix -> technique)
CLIP_USES = (("Dash Upper Antic", "dash_attack"), ("Wanderer Dash Attack", "dash_attack"),
             ("Harpoon Antic", "clawline"), ("Umbrella Inflate", "glide"), ("BindCharge", "bind_start"),
             ("v3 Down Slash Antic", "down_slash"), ("DownSlash", "down_slash"), ("Walljump", "wall_jump"))
CS_BITS = ("onGround", "dashing", "airDashing", "wallClinging", "wallSliding", "attacking", "recoiling", "casting")
POCKET_X, POCKET_Y = 14.6, 13.2        # forum.md §10.3: transform x < 14.57 and y >= 13.2 on the left wall
# a multi-hit chain's Final Hit lands 20-41 frames after its last Multihit follow-up in both demo recordings; a pending
# chain with no hp loss within this many frames is closed on its own (chain_cut "missing") instead of absorbing the
# next unrelated hit
CHAIN_GAP_F = 90
SILK_FULL = 9


# ---------------------------------------------------------------------------------------------------- scan

def _stream(path: Path):
    """(msg_type, payload) of a recorder file without holding the whole decompressed stream."""
    with path.open("rb") as f:
        r = zstandard.ZstdDecompressor().stream_reader(f, read_size=1 << 20)
        buf = bytearray()
        while True:
            while len(buf) < 4:
                chunk = r.read(1 << 22)
                if not chunk:
                    return
                buf += chunk
            n = int.from_bytes(buf[:4], "little")
            while len(buf) < 4 + n:
                chunk = r.read(max(1 << 22, 4 + n - len(buf)))
                if not chunk:
                    return
                buf += chunk
            body = bytes(buf[4:4 + n])
            del buf[:4 + n]
            yield body[0], msgpack.unpackb(body[HEADER.size - 4:], raw=False, strict_map_key=False)


def _main_state(e: dict) -> tuple[str | None, float | None]:
    spec = FORUM_SPECS.get(e.get("type_key"))
    fsms = e.get("fsms") or ()
    for name in ((spec.control_fsm,) if spec else ()) + ("Control", "Attack"):
        for x in fsms:
            if x.get("name") == name:
                return x.get("state"), x.get("t")
    return (fsms[0].get("state"), fsms[0].get("t")) if fsms else (None, None)


def scan(session: Path, snap_before: int = 2, snap_after: int = 1) -> dict:
    """One pass over state.raw.zst (see the module doc)."""
    rows, ents_c, allies_c, events, snaps = [], [], [], [], {}
    ring: deque = deque(maxlen=snap_before + 1)
    last_hit = -10 ** 9
    for t, m in _stream(session / "state.raw.zst"):
        if t != MsgType.STATE:
            continue
        f = m["f"]
        g = m.get("game") or {}
        h = m.get("hero") or {}
        inp = m.get("input") or {}
        b = next((x for x in (m.get("room") or {}).get("battles") or () if x.get("name") == BATTLE), None)
        pos = h.get("pos") or [None, None]
        vel = h.get("vel") or [None, None]
        cog = next((a for n, a in zip(h.get("tools") or (), h.get("tool_amounts") or ()) if n == "Cogwork Flier"),
                   None)
        rows.append(dict(
            f=f, udt=m.get("udt"), ts=m.get("ts"), scene=g.get("scene"), gs=g.get("gs"), paused=g.get("paused"),
            x=pos[0], y=pos[1], vx=vel[0], vy=vel[1], facing=h.get("facing"), box=h.get("box"),
            hp=h.get("health"), silk=h.get("silk"), cs=h.get("cstate"), anim=(h.get("anim") or {}).get("clip"),
            inv=h.get("invulnerable"), cog=cog, crest=h.get("crest"), spell=(h.get("spell") or [None])[0],
            mask=inp.get("mask"), move=inp.get("move"),
            b_id=b.get("id") if b else None, b_wave=b.get("wave") if b else None,
            b_started=b.get("started") if b else None, b_completed=b.get("completed") if b else None,
            b_enemies=b.get("enemies") if b else None))
        live = []
        for e in live_enemies(m):
            st, stt = _main_state(e)
            live.append((e.get("iid"), e.get("type_key"), e["pos"][0], e["pos"][1], e.get("hp"), st, stt,
                         e.get("flipX")))
        ents_c.append(live)
        allies_c.append([(a.get("kind"), a.get("name"), (a.get("pos") or [None])[0], (a.get("pos") or [None, None])[1],
                          a.get("state"), a.get("iid")) for a in m.get("allies") or () if a.get("active")])
        ring.append((f, h, m.get("ents") or []))
        hit_here = False
        for ev in m.get("ev") or ():
            k = ev.get("k")
            if k == "pause_gate":
                continue
            d = ev.get("d") or {}
            if k == "fsm":
                d = {kk: d.get(kk) for kk in ("ent", "obj", "fsm", "from", "to", "t_in_prev")}
            events.append((ev.get("f", f), k, d))
            if k in ("damage", "special_damage", "die"):
                hit_here = True
        if hit_here:
            for ff, hh, ee in ring:
                snaps.setdefault(ff, (hh, ee))
            last_hit = f
        elif 0 < f - last_hit <= snap_after:
            snaps.setdefault(f, (h, m.get("ents") or []))
    return dict(rows=rows, ents=ents_c, allies=allies_c, events=events, snaps=snaps)


def load(session: Path, cache: Path | None) -> dict:
    if cache is not None:
        p = cache / f"{session.name}.pkl"
        if p.exists():
            with p.open("rb") as f:
                return pickle.load(f)
    s = scan(session)
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)
        with (cache / f"{session.name}.pkl").open("wb") as f:
            pickle.dump(s, f, protocol=5)
    return s


# ---------------------------------------------------------------------------------------------------- helpers

def source_type(src: str | None) -> tuple[str | None, str | None, str | None]:
    """(enemy type, attack, GameObject) of a damage source path: "Song Pilgrim 03 (2)/Whip Hit 2", "Wave 1/Song
    Reed" (body), "Colliders/Collider ParryStance" (Minister body), "Throwing Bell(Clone)", "rune slam(Clone)/damager",
    "EmptyObjectFromNull/Song Automaton Tiny(Clone)"."""
    if not src:
        return None, None, None
    parts = src.split("/")
    head = type_key(parts[0])
    if head in PROJECTILES:
        return PROJECTILES[head], head, None
    if parts[0] == "Colliders":
        return "Song Administrator", parts[-1], None
    if parts[0].startswith("Wave ") or parts[0] == "EmptyObjectFromNull":
        obj = parts[-1]
        return type_key(obj), "body", obj
    if len(parts) == 1:
        return type_key(parts[0]), "body", parts[0]
    return head, parts[-1], parts[0]


def killer(src: str | None) -> str:
    if src in GARMOND:
        return "garmond"
    if src in COGFLY:
        return "cogfly"
    if src in BELL:
        return "bell"
    if src in HERO_ATTACKS:
        return "hero"
    return "other"


def _cs_index() -> dict[str, int]:
    names = json.loads(CSTATE_FACTS.read_text("utf-8"))["bools"]
    return {n: names.index(n) for n in CS_BITS}


def _flags(cs, idx: dict[str, int]) -> dict[str, bool]:
    if not cs:
        return {n: False for n in idx}
    return {n: bool((cs[i >> 6] >> (i & 63)) & 1) for n, i in idx.items()}


def _contact(fl: dict[str, bool]) -> str:
    if fl["wallClinging"]:
        return "wall_cling"
    if fl["wallSliding"]:
        return "wall_slide"
    return "ground" if fl["onGround"] else "air"


def _ent_dist(e: dict, box) -> float | None:
    """Closest enabled damage collider of a full STATE entity to the hero box."""
    best = None
    for c in e.get("colliders") or ():
        if not c.get("enabled") or not c.get("damage"):
            continue
        dmg = c["damage"]
        if isinstance(dmg, dict) and not (dmg.get("dealt") or dmg.get("eff")):
            continue
        d = collider_box_distance(c, tuple(box))
        best = d if best is None or d < best else best
    return best


def _attack_family(tk: str | None, iid, i: int, ents: list, back: int = 240) -> tuple[str | None, str | None]:
    """(family, state at the hit) of an enemy: the last attack-start state of its control FSM within `back` frames
    before row i, else <P>_IDLE."""
    spec = FORUM_SPECS.get(tk)
    if spec is None or iid is None:
        return None, None
    st_now = None
    for j in range(i, max(-1, i - back), -1):
        for e in ents[j]:
            if e[0] == iid:
                if st_now is None:
                    st_now = e[5]
                if e[5] in spec.attack_starts:
                    return spec.attack_starts[e[5]], st_now
                if e[5] in spec.decision_states and j < i - 6:
                    return spec.idle_family, st_now
                break
    return spec.idle_family, st_now


def _active(tk: str | None, state: str | None) -> bool:
    """In the fight: a control state that is neither a waiting state (gauntlet.WAITING_STATES, applied by
    live_enemies) nor one of the type's dormant states (the Maestro's pooled Tiny sit in "Dead" between summons)."""
    spec = FORUM_SPECS.get(tk)
    return state is not None and not (spec is not None and state in spec.dormant) and state not in WAITING_STATES


def in_play(live: list) -> list:
    return [e for e in live if _active(e[1], e[5])]


def _median(v):
    return round(statistics.median(v), 2) if v else None


# ---------------------------------------------------------------------------------------------------- attempts

def attempts(s: dict) -> list[dict]:
    """Attempts of one scanned session (see the module doc), with everything per attempt."""
    rows, ents, events = s["rows"], s["ents"], s["events"]
    idx = _cs_index()
    fi = {r["f"]: i for i, r in enumerate(rows)}
    # game time per row
    gt, acc = [], 0.0
    for r in rows:
        acc += (r["udt"] or 0.0) * (r["ts"] if r["ts"] is not None else 1.0)
        gt.append(acc)
    spans: list[tuple[int, int, int]] = []    # (battle id, first started row, last row of that id)
    cur, i0 = None, None
    for i, r in enumerate(rows):
        if r["b_id"] is not None and r["b_started"]:
            if r["b_id"] != cur:
                if cur is not None:
                    spans.append((cur, i0, last))
                cur, i0 = r["b_id"], i
            last = i
        elif cur is not None and r["b_id"] not in (None, cur):
            spans.append((cur, i0, last))
            cur = None
    if cur is not None:
        spans.append((cur, i0, last))
    by_f = defaultdict(list)
    for f, k, d in events:
        by_f[f].append((k, d))
    out = []
    for n, (bid, a, z) in enumerate(spans):
        f0 = rows[a]["f"]
        died = next(((rows[j]["f"], d) for j in range(a, z + 1) for k, d in by_f.get(rows[j]["f"], ())
                     if k == "die"), None)
        done = next((j for j in range(a, z + 1) if rows[j]["b_completed"]), None)
        if died is not None:
            z = fi[died[0]]
            outcome = "died"
        elif done is not None:
            outcome = "cleared"
        else:
            outcome = "left"
        f1 = rows[z]["f"]
        out.append(_attempt(n, bid, a, z, outcome, died, rows, ents, s["allies"], s["snaps"], by_f, fi, gt, idx))
        out[-1]["f0"], out[-1]["f1"] = f0, f1
    return out


def _wave_at(waves: list[tuple[int, int]], f: int) -> int:
    w = -1
    for wi, wf in waves:
        if wf <= f:
            w = wi
    return w


def _attempt(n, bid, a, z, outcome, died, rows, ents, allies, snaps, by_f, fi, gt, idx) -> dict:
    f0, f1 = rows[a]["f"], rows[z]["f"]
    waves: list[tuple[int, int]] = []
    for j in range(a, z + 1):
        r = rows[j]
        if r["b_wave"] is not None and (not waves or waves[-1][0] != r["b_wave"]):
            waves.append((r["b_wave"], r["f"]))
    t = lambda f: round(gt[fi[f]] - gt[a], 2)      # noqa: E731 - game seconds since the battle start

    # ---- masks lost (hp events), chains, attribution
    hits, pend = [], []
    for j in range(a, z + 1):
        f = rows[j]["f"]
        for k, d in by_f.get(f, ()):
            if k != "hp" or (d.get("delta") or 0) >= 0:
                continue
            src = d.get("source") or ""
            fsm = d.get("fsm") or ""
            amount = -(d.get("delta") or 0)
            if pend and f - pend[-1][0] > CHAIN_GAP_F:     # its Final Hit never came (blocked, i-frame edge)
                hits.append(_hit(pend[-1][0], "", 0, pend, rows, ents, snaps, fi, idx, waves, t, cut="missing"))
                pend = []
            if "Multihit" in src or "Multihit" in fsm:
                pend.append((f, amount))
                continue
            hits.append(_hit(f, src, amount, pend, rows, ents, snaps, fi, idx, waves, t))
            pend = []
    if pend:    # a chain cut by the death (the die event names the source) or left open at the end
        by_death = died is not None and died[0] - pend[-1][0] <= CHAIN_GAP_F
        src = (died[1].get("source") if by_death else None) or ""
        hits.append(_hit(pend[-1][0], src, 0, pend, rows, ents, snaps, fi, idx, waves, t,
                         cut="death" if by_death else "missing"))

    # ---- heals, bind starts, kills, deaths
    heals, kills, dead_last = [], [], {}
    for j in range(a, z + 1):
        f = rows[j]["f"]
        for k, d in by_f.get(f, ()):
            if k == "hp" and (d.get("delta") or 0) > 0 and d.get("src") == "AddHealth":
                r = rows[j - 1] if j > a else rows[j]
                fl = _flags(r["cs"], idx)
                heals.append({"f": f, "t": t(f), "wave": _wave_at(waves, f), "amount": d["delta"],
                              "hp_after": d.get("h"), "x": round(r["x"], 2), "y": round(r["y"], 2),
                              "contact": _contact(fl), "enemies": len(in_play(ents[j])),
                              "anim": r["anim"]})
            elif k == "hit" and d.get("dead"):
                hp0 = d.get("hp_before")
                ent = d.get("ent")
                if (hp0 is not None and hp0 <= 0) or (ent in dead_last and f - dead_last[ent] < DEAD_REPEAT_F):
                    continue
                dead_last[ent] = f
                kills.append({"f": f, "t": t(f), "wave": _wave_at(waves, f), "type": d.get("type_key"),
                              "src": d.get("src"), "by": killer(d.get("src"))})
    # nail clashes (freeze NailClashEffect): the closest enemy in play and its attack family
    clashes = []
    for j in range(a, z + 1):
        f = rows[j]["f"]
        for k, d in by_f.get(f, ()):
            if k == "freeze" and d.get("phase") == "start" and d.get("type") == "NailClashEffect":
                r = rows[j - 1] if j > a else rows[j]
                live = in_play(ents[j - 1] if j > a else ents[j])
                near = min(live, key=lambda e: (e[2] - r["x"]) ** 2 + (e[3] - r["y"]) ** 2) if live else None
                fam = _attack_family(near[1], near[0], j - 1, ents) if near else (None, None)
                clashes.append({"f": f, "t": t(f), "wave": _wave_at(waves, f), "hero_anim": r["anim"],
                                "type": near[1] if near else None, "family": fam[0], "state": fam[1],
                                "dist_u": round(((near[2] - r["x"]) ** 2 + (near[3] - r["y"]) ** 2) ** 0.5, 2)
                                if near else None,
                                "hit_within_1s": any(0 <= h["f"] - f <= FPS for h in hits)})
    death = None
    if died is not None:
        src = died[1].get("source")
        tk, atk, _ = source_type(src)
        death = {"f": died[0], "t": t(died[0]), "wave": _wave_at(waves, died[0]), "source": src, "type": tk,
                 "attack": atk}

    # ---- technique use, wall time, pocket, Cogfly, keys
    uses: Counter = Counter()
    prev_anim, prev_fl, prev_cog = None, None, None
    cling_f = pocket_f = 0
    garmond_first = None
    fs_, masks = [], []
    enemy_s: Counter = Counter()       # type -> enemy-seconds in play (each instance counts)
    for j in range(a, z + 1):
        r = rows[j]
        if j > a:
            dt = gt[j] - gt[j - 1]
            for e in in_play(ents[j]):
                enemy_s[e[1]] += dt
        fl = _flags(r["cs"], idx)
        an = r["anim"] or ""
        if an != prev_anim:
            for pre, name in CLIP_USES:
                if an.startswith(pre) and not (prev_anim or "").startswith(pre):
                    uses[name] += 1
        if prev_fl is not None:
            if fl["dashing"] and not prev_fl["dashing"]:
                uses["dash"] += 1
            if fl["wallClinging"] and not prev_fl["wallClinging"]:
                uses["wall_cling"] += 1
        if fl["wallClinging"]:
            cling_f += 1
            if r["x"] is not None and r["x"] < POCKET_X and r["y"] >= POCKET_Y:
                pocket_f += 1
        if prev_cog is not None and r["cog"] is not None and r["cog"] < prev_cog:
            uses["cogfly"] += prev_cog - r["cog"]
        prev_anim, prev_fl, prev_cog = an, fl, r["cog"]
        if garmond_first is None:
            for al in allies[j]:
                if al[1] == "Garmond Fighter" and al[4] not in (None, "Dormant", "Init"):
                    garmond_first = r["f"]
        fs_.append(r["f"])
        masks.append(r["mask"] or 0)
        for k, d in by_f.get(r["f"], ()):
            if k == "hit" and d.get("src") in HERO_ATTACKS:
                uses["hits_" + d["src"]] += 1
    holds = holds_from_masks(fs_, masks, f0, f1)
    presses = Counter({k: len(v) for k, v in holds.items()})
    wall_s = (f1 - f0 + 1) / FPS
    game_s = round(gt[z] - gt[a], 2)
    # silk over the attempt (the death frame itself excluded: the game resets it there)
    silk = [rows[j]["silk"] for j in range(a, z if died is not None and z > a else z + 1)
            if rows[j]["silk"] is not None]

    # ---- per wave
    wave_rows = []
    for k_, (wi, wf) in enumerate(waves):
        end_f = waves[k_ + 1][1] if k_ + 1 < len(waves) else f1
        complete = k_ + 1 < len(waves) or outcome == "cleared"
        j = fi[wf]
        r = rows[j - 1] if j > a else rows[j]
        fl = _flags(r["cs"], idx)
        rb = rows[max(a, j - int(FPS))]
        n_in = [len(in_play(ents[jj])) for jj in range(j, fi[end_f] + 1)]
        wave_rows.append({
            "wave": wi, "f": wf, "t": t(wf), "dur_s": round(gt[fi[end_f]] - gt[j], 2), "complete": complete,
            "hits": sum(1 for h in hits if wi == h["wave"]),
            "masks": sum(h["masks"] for h in hits if wi == h["wave"]),
            "heals": sum(1 for h in heals if wi == h["wave"]),
            "kills": [k["type"] for k in kills if k["wave"] == wi],
            "hero_at_start": {"x": round(r["x"], 2), "y": round(r["y"], 2), "contact": _contact(fl),
                              "anim": r["anim"], "hp": r["hp"], "silk": r["silk"]},
            "hero_1s_before": {"x": round(rb["x"], 2), "y": round(rb["y"], 2), "anim": rb["anim"]},
            "enemies_in_play_mean": round(sum(n_in) / len(n_in), 2) if n_in else None,
            "enemies_in_play_max": max(n_in) if n_in else None,
            "keys_per_s": round(sum(v for kk, v in Counter(
                {kk: len(vv) for kk, vv in holds_from_masks(fs_, masks, wf, end_f).items()}).items()
                if kk not in MENU_KEYS) / max((end_f - wf + 1) / FPS, 1e-6), 2)})
    return {
        "n": n, "battle_id": bid, "outcome": outcome, "crest": rows[a]["crest"],
        "start": {"hp": rows[a]["hp"], "silk": rows[a]["silk"]},
        "silk_min": min(silk) if silk else None, "silk_last": silk[-1] if silk else None,
        "enemy_s": {k: round(v, 2) for k, v in enemy_s.most_common()},
        "wave_reached": waves[-1][0] if waves else -1, "game_s": game_s, "wall_s": round(wall_s, 2),
        "waves": wave_rows, "hits": hits, "masks_lost": sum(h["masks"] for h in hits), "heals": heals,
        "kills": kills, "death": death, "clashes": clashes,
        "garmond_t": t(garmond_first) if garmond_first is not None else None,
        "uses": dict(uses), "cling_s": round(cling_f / FPS, 2), "pocket_s": round(pocket_f / FPS, 2),
        "presses": dict(presses.most_common()),
        "keys_per_s": round(sum(v for k, v in presses.items() if k not in MENU_KEYS) / wall_s, 2),
    }


def _hit(f, src, amount, pend, rows, ents, snaps, fi, idx, waves, t, cut: str | None = None) -> dict:
    """One attack instance that cost masks: a plain hit or a multi-hit chain (pend: its follow-up frames; cut: the
    chain ended by the death or without its Final Hit, see CHAIN_GAP_F)."""
    tk, atk, obj = source_type(src)
    f_first = pend[0][0] if pend else f
    j = fi[f_first]
    r = rows[j - 1] if j > 0 else rows[j]          # the hero one frame before the (first) hit
    fl = _flags(r["cs"], idx)
    box = r["box"]
    # attacker: the entity whose collider carries the source's GameObject name (else the closest of the type)
    snap = snaps.get(rows[j - 1]["f"]) or snaps.get(f_first)
    attacker, dists = None, []
    if snap is not None and box:
        for e in snap[1]:
            if e.get("hidden") or e.get("is_dead") or (e.get("hp") or 0) <= 0:
                continue
            if e.get("category") == "enemy" and not _active(e.get("type_key"), _main_state(e)[0]):
                continue
            d = _ent_dist(e, box)
            names = {c.get("name") for c in e.get("colliders") or ()}
            if obj is not None and obj in names and e.get("type_key") == tk:
                attacker = e.get("iid")
            if d is not None:
                dists.append((d, e.get("type_key"), e.get("iid")))
    live = in_play(ents[j - 1] if j > 0 else ents[j])
    if attacker is None and tk is not None and atk not in PROJECTILES:
        cand = [e for e in live if e[1] == tk and r["x"] is not None]
        if cand:
            attacker = min(cand, key=lambda e: (e[2] - r["x"]) ** 2 + (e[3] - r["y"]) ** 2)[0]
    fam, st = _attack_family(tk, attacker, j - 1, ents) if attacker is not None else (None, None)
    if atk in PROJECTILES:
        fam = {"Throwing Bell": "CB_THROW", "Song Reed Pin Projectile": "RE_THROW", "Spear": "CM_SPIN",
               "handmaiden_spear_silk_explosion": "CM_SPIN", "rune bomb small": "CC_CAST",
               "rune slam": "CC_JUMP_CAST"}[atk]
    others = sorted(d for d in dists if d[2] != attacker)
    return {
        "f": f_first, "t": t(f_first), "wave": _wave_at(waves, f_first), "source": src, "type": tk, "attack": atk,
        "family": fam, "attacker_state": st, "masks": amount + sum(m for _, m in pend),
        "chain": len(pend) + 1, "chain_cut": cut,
        "hero": {"x": round(r["x"], 2), "y": round(r["y"], 2), "anim": r["anim"], "contact": _contact(fl),
                 "attacking": fl["attacking"], "dashing": fl["dashing"] or fl["airDashing"],
                 "binding": (r["spell"] or "") in ("Binding", "Bind Air", "Bind Ground", "Bind Burst"),
                 "recoiling": fl["recoiling"], "hp_before": r["hp"], "silk": r["silk"]},
        "enemies_in_play": len(live), "types_in_play": sorted(Counter(e[1] for e in live).items()),
        "within_2u": sum(1 for d in dists if d[0] <= 2.0), "within_4u": sum(1 for d in dists if d[0] <= 4.0),
        "nearest_other_u": round(others[0][0], 2) if others else None,
        "nearest_other_type": others[0][1] if others else None,
    }


# ---------------------------------------------------------------------------------------------------- summary

def anim_kind(an: str | None) -> str:
    """Coarse class of the hero's animation clip at a hit (what the person was doing)."""
    an = an or ""
    if an.startswith(("Slash", "SlashAlt", "UpSlash", "DownSlash", "v3 Down Slash", "Wall Slash", "Dash Upper",
                      "Wanderer Dash Attack", "Harpoon")):
        return "attack_recovery" if "Recovery" in an else "attack"
    if any(p in an for p in ("Recoil", "Downspike Recovery", "DownSpikeBounce", "Slash Land", "Wanderer DashRecoil")):
        return "attack_recovery"
    if an.startswith(("Dash", "Air Dash")):
        return "dash"
    if an.startswith(("Airborne", "Sprint Air", "Umbrella", "Shuttlecock", "Walljump", "Double")):
        return "air_move"
    if an.startswith(("Run", "Idle", "Sprint", "Turn", "Land", "Skid")):
        return "ground_move"
    if an.startswith("Bind"):
        return "bind"
    if an.startswith("Wall"):
        return "wall"
    return "other"


def _pct(v: list[float], q: float):
    """Linearly interpolated percentile (q = 0.5 is the median)."""
    if not v:
        return None
    v = sorted(v)
    x = q * (len(v) - 1)
    lo = int(x)
    hi = min(lo + 1, len(v) - 1)
    return round(v[lo] + (v[hi] - v[lo]) * (x - lo), 2)


def details(atts: list[dict]) -> dict:
    """Kill order and time to kill per wave, pre-wave positions, net masks per completed wave, deaths."""
    first_kill, orders, t_kill, pos, net = (defaultdict(Counter), defaultdict(Counter), defaultdict(list),
                                            defaultdict(list), defaultdict(list))
    for a in atts:
        for w in a["waves"]:
            ks = [k for k in a["kills"] if k["wave"] == w["wave"] and k["type"] != "Song Automaton Tiny"]
            if ks:
                first_kill[w["wave"]][ks[0]["type"]] += 1
            if w["complete"]:
                orders[w["wave"]][" > ".join(NAMES.get(k["type"], (k["type"],))[0] for k in ks)] += 1
                net[w["wave"]].append(w["masks"] - 3 * w["heals"])
            for k in ks:
                t_kill[f'{w["wave"]}/{k["type"]}'].append(k["t"] - w["t"])
            pos[w["wave"]].append(w["hero_1s_before"]["x"])
    deaths = [a for a in atts if a["death"]]
    # death -> next battle start, within one session only (main() tags each attempt with its session)
    gaps = [(b["f0"] - a["death"]["f"]) / FPS for a, b in zip(atts, atts[1:])
            if a["death"] and a.get("session") == b.get("session") and b["f0"] > a["death"]["f"]]
    since_heal = []
    for a in deaths:
        lh = [h["t"] for h in a["heals"] if h["t"] <= a["death"]["t"]]
        since_heal.append(a["death"]["t"] - lh[-1] if lh else None)
    hits = [h for a in atts for h in a["hits"]]
    return {
        "first_kill": {w: dict(c) for w, c in sorted(first_kill.items())},
        "kill_orders": {w: c.most_common(5) for w, c in sorted(orders.items())},
        "t_kill_s": {k: {"n": len(v), "p50": _pct(v, 0.5), "min": round(min(v), 1), "max": round(max(v), 1)}
                     for k, v in sorted(t_kill.items())},
        "pre_wave_x": {w: {"n": len(v), "p10": _pct(v, 0.1), "p50": _pct(v, 0.5), "p90": _pct(v, 0.9)}
                       for w, v in sorted(pos.items())},
        "net_masks_completed_wave": {w: {"n": len(v), "p50": _pct(v, 0.5), "min": min(v), "max": max(v)}
                                     for w, v in sorted(net.items())},
        "hero_anim_at_hit": dict(Counter(anim_kind(h["hero"]["anim"]) for h in hits).most_common()),
        "chain_masks": dict(Counter(h["masks"] for h in hits if h["chain"] > 1)),
        "hp_before_final_hit": dict(Counter(a["hits"][-1]["hero"]["hp_before"] for a in deaths if a["hits"])),
        "hits_last_10s_before_death": dict(sorted(Counter(sum(1 for h in a["hits"] if a["death"]["t"] - 10 <= h["t"])
                                                          for a in deaths).items())),
        "deaths_without_heal": sum(1 for v in since_heal if v is None),
        "deaths_without_heal_full_silk_at_start": sum(1 for a, v in zip(deaths, since_heal)
                                                      if v is None and (a["start"]["silk"] or 0) >= SILK_FULL),
        "deaths_without_heal_full_silk_throughout": sum(1 for a, v in zip(deaths, since_heal)
                                                        if v is None and (a["silk_min"] or 0) >= SILK_FULL),
        "deaths_full_silk": sum(1 for a in deaths if (a["silk_last"] or 0) >= SILK_FULL),
        # the final hit: (hp before, chain, masks); a 2-mask death is a chain or a single 2-mask attack
        "final_hit_at_death": [[*k, v] for k, v in sorted(Counter(
            (a["hits"][-1]["hero"]["hp_before"], a["hits"][-1]["chain"], a["hits"][-1]["masks"],
             a["hits"][-1]["type"], a["hits"][-1]["attack"] if a["hits"][-1]["chain"] == 1 else "chain")
            for a in deaths if a["hits"]).items(), key=lambda kv: (-kv[1], str(kv[0])))],
        "start_hp_silk": {f"{k[0]}/{k[1]}": v for k, v in Counter((a["start"]["hp"], a["start"]["silk"])
                                                                   for a in atts).most_common()},
        "since_last_heal_s_p50": _pct([v for v in since_heal if v is not None], 0.5),
        "death_to_next_start_s_p50": _pct(gaps, 0.5),
        "hits_within_2s_of_previous": sum(1 for a in atts for x, y in zip(a["hits"], a["hits"][1:])
                                          if y["t"] - x["t"] <= 2.0),
    }


def summarise(atts: list[dict]) -> dict:
    """Aggregates over attempts (one session or several)."""
    hits = [h for a in atts for h in a["hits"]]
    exposure = defaultdict(float)          # wave -> game seconds spent in it
    wave_dur = defaultdict(list)
    for a in atts:
        for w in a["waves"]:
            exposure[w["wave"]] += w["dur_s"]
            if w["complete"]:
                wave_dur[w["wave"]].append(w["dur_s"])
    by_wave = {}
    for w in sorted(exposure):
        hw = [h for h in hits if h["wave"] == w]
        by_wave[w] = {"name": FORUM_WAVES[w].name if 0 <= w < len(FORUM_WAVES) else "?",
                      "attempts_reached": sum(1 for a in atts if any(x["wave"] == w for x in a["waves"])),
                      "completed": len(wave_dur[w]), "dur_median_s": _median(wave_dur[w]),
                      "dur_range_s": [min(wave_dur[w]), max(wave_dur[w])] if wave_dur[w] else None,
                      "exposure_s": round(exposure[w], 1), "hits": len(hw), "masks": sum(h["masks"] for h in hw),
                      "hits_per_min": round(60 * len(hw) / exposure[w], 2) if exposure[w] else None,
                      "deaths": sum(1 for a in atts if a["death"] and a["death"]["wave"] == w),
                      "hits_by_type": dict(Counter(h["type"] for h in hw).most_common())}
    by_type = Counter(h["type"] for h in hits)
    masks_type = Counter()
    for h in hits:
        masks_type[h["type"]] += h["masks"]
    # exposure per type: raw hit shares mostly follow how long each type is in play (index 0 is most of the fight
    # time because every attempt starts there), so rates are per enemy-minute in play
    enemy_min = Counter()
    for a in atts:
        for k, v in a["enemy_s"].items():
            enemy_min[k] += v / 60
    death_type = Counter(a["death"]["type"] for a in atts if a["death"])
    tot_enemy_min = sum(enemy_min.values())
    per_type = {k: {"enemy_min": round(m, 1), "share_of_enemy_time": round(m / tot_enemy_min, 3),
                    "hits": by_type.get(k, 0), "masks": masks_type.get(k, 0), "deaths": death_type.get(k, 0),
                    "hits_per_enemy_min": round(by_type.get(k, 0) / m, 2) if m else None,
                    "deaths_per_enemy_hour": round(60 * death_type.get(k, 0) / m, 2) if m else None}
                for k, m in enemy_min.most_common()}
    fam = Counter((h["type"], h["family"], h["attack"]) for h in hits)
    deaths = Counter((a["death"]["type"], a["death"]["attack"]) for a in atts if a["death"])
    dfam = Counter()
    for a in atts:
        if a["death"]:
            last = [h for h in a["hits"] if h["f"] <= a["death"]["f"]]
            if last:
                dfam[(last[-1]["type"], last[-1]["family"])] += 1
    kills_by = Counter(k["by"] for a in atts for k in a["kills"])
    kill_type_by = Counter((k["type"], k["by"]) for a in atts for k in a["kills"])
    uses = Counter()
    for a in atts:
        uses.update(a["uses"])
    tot_game = sum(a["game_s"] for a in atts)
    tot_wall = sum(a["wall_s"] for a in atts)
    keys = Counter()
    for a in atts:
        keys.update(a["presses"])
    contact = Counter(h["hero"]["contact"] for h in hits)
    return {
        "attempts": len(atts), "outcomes": dict(Counter(a["outcome"] for a in atts)),
        "wave_reached": dict(sorted(Counter(a["wave_reached"] for a in atts).items())),
        "fight_game_s": round(tot_game, 1), "fight_wall_s": round(tot_wall, 1),
        "hits": len(hits), "masks": sum(h["masks"] for h in hits),
        "hits_per_min": round(60 * len(hits) / tot_game, 2) if tot_game else None,
        "chains": sum(1 for h in hits if h["chain"] > 1),
        "by_wave": by_wave,
        "hits_by_type": dict(by_type.most_common()), "masks_by_type": dict(masks_type.most_common()),
        "per_type_exposure": per_type,
        "hits_by_family": [[*k, v] for k, v in fam.most_common()],
        "deaths_by_source": [[*k, v] for k, v in deaths.most_common()],
        "deaths_by_family": [[*k, v] for k, v in dfam.most_common()],
        "hero_contact_at_hit": dict(contact.most_common()),
        "hit_while_attacking": sum(1 for h in hits if h["hero"]["attacking"]),
        "hit_while_dashing": sum(1 for h in hits if h["hero"]["dashing"]),
        "hit_while_binding": sum(1 for h in hits if h["hero"]["binding"]),
        "enemies_in_play_at_hit": dict(sorted(Counter(h["enemies_in_play"] for h in hits).items())),
        "other_threat_within_2u_at_hit": sum(1 for h in hits if (h["nearest_other_u"] or 99) <= 2.0),
        "nearest_other_u_median": _median([h["nearest_other_u"] for h in hits if h["nearest_other_u"] is not None]),
        "hit_gap_s_median": _median([b["t"] - a_["t"] for a in atts for a_, b in zip(a["hits"], a["hits"][1:])]),
        "first_hit_s_median": _median([a["hits"][0]["t"] for a in atts if a["hits"]]),
        "heals": sum(len(a["heals"]) for a in atts), "bind_starts": uses.get("bind_start", 0),
        "heal_contact": dict(Counter(h["contact"] for a in atts for h in a["heals"])),
        "clashes": sum(len(a["clashes"]) for a in atts),
        "clashes_by_family": [[*k, v] for k, v in Counter((c["type"], c["family"]) for a in atts
                                                          for c in a["clashes"]).most_common()],
        "clashes_hit_within_1s": sum(1 for a in atts for c in a["clashes"] if c["hit_within_1s"]),
        "kills_by": dict(kills_by.most_common()),
        "kills_by_type": [[*k, v] for k, v in sorted(kill_type_by.items())],
        "uses": dict(uses.most_common()),
        "uses_per_min": {k: round(60 * v / tot_game, 2) for k, v in uses.most_common()} if tot_game else {},
        "cling_s": round(sum(a["cling_s"] for a in atts), 1), "pocket_s": round(sum(a["pocket_s"] for a in atts), 1),
        "keys_per_s": round(sum(v for k, v in keys.items() if k not in MENU_KEYS) / tot_wall, 2) if tot_wall else None,
        "presses": dict(keys.most_common()),
        "details": details(atts),
    }


def random_policy(runs: list[Path], per_wave: bool = True) -> dict:
    """The data policy's Forum AttemptRecords (fo_A, LethalBlock: it never dies, so every wave is played out): wave
    durations (gauntlet.waves) and hit sources by enemy type; per_wave also reads each recording's events.jsonl for
    the "damage" events (one per attack instance that hit, as in the human count) inside each wave's window."""
    durs, hits_type, n, game_s = defaultdict(list), Counter(), 0, 0.0
    windows: dict[str, list[tuple[int, int, int]]] = defaultdict(list)    # recording -> (wave, f_from, f_to)
    for run in runs:
        for p in sorted(run.glob("attempts_i*.jsonl")):
            for line in p.read_text("utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                g = r.get("gauntlet") or {}
                ws = g.get("waves") or []
                if r.get("outcome") != "CLEAR" or len(ws) < 14:
                    continue
                n += 1
                game_s += r.get("ingame_s") or 0.0
                for a_, b in zip(ws, ws[1:]):
                    durs[a_["wave"]].append(b["t"] - a_["t"])
                for src, c in (r.get("hit_sources") or {}).items():
                    hits_type[source_type(src)[0]] += c
                if r.get("recording") and r.get("f_end"):
                    bounds = [w["f"] for w in ws] + [r["f_end"]]
                    for w, lo, hi in zip(ws, bounds, bounds[1:]):
                        windows[r["recording"]].append((w["wave"], lo, hi))
    tot = sum(hits_type.values())
    out = {"runs": [str(r) for r in runs], "complete_gauntlets": n, "game_s": round(game_s, 1),
           "wave_dur_median_s": {w: _median(v) for w, v in sorted(durs.items())},
           "hits_per_min": round(60 * tot / game_s, 2) if game_s else None,
           "hit_share_by_type": {k: round(v / tot, 3) for k, v in hits_type.most_common()} if tot else {}}
    if not per_wave:
        return out
    exp_s, wave_hits, wave_types = defaultdict(float), Counter(), defaultdict(Counter)
    for rec, wins in windows.items():
        p = Path(rec) / "events.jsonl"
        if not p.exists():
            continue
        wins.sort(key=lambda x: x[1])
        for w, lo, hi in wins:
            exp_s[w] += (hi - lo) / FPS
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                if '"kind": "damage"' not in line:
                    continue
                e = json.loads(line)
                f = e.get("frame")
                for w, lo, hi in wins:
                    if lo <= f < hi:
                        wave_hits[w] += 1
                        wave_types[w][source_type((e.get("data") or {}).get("source"))[0]] += 1
                        break
    out["by_wave"] = {w: {"exposure_s": round(exp_s[w], 1), "hits": wave_hits[w],
                          "hits_per_min": round(60 * wave_hits[w] / exp_s[w], 2) if exp_s[w] else None,
                          "hits_by_type": dict(wave_types[w].most_common())} for w in sorted(exp_s)}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sessions", nargs="+", type=Path)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--cache", type=Path)
    ap.add_argument("--random-runs", nargs="*", type=Path, default=[])
    a = ap.parse_args(argv)
    out = {"sessions": {}}
    every = []
    for sess in a.sessions:
        meta = json.loads((sess / "meta.json").read_text("utf-8")) if (sess / "meta.json").exists() else {}
        atts = attempts(load(sess, a.cache))
        for x in atts:
            x["session"] = sess.name
        every += atts
        out["sessions"][sess.name] = {"commands": meta.get("commands"), "summary": summarise(atts),
                                      "attempts": atts}
        sm = out["sessions"][sess.name]["summary"]
        print(f"{sess.name}: {sm['attempts']} attempts {sm['outcomes']} waves reached {sm['wave_reached']} "
              f"hits {sm['hits']} masks {sm['masks']} ({sm['hits_per_min']}/min) heals {sm['heals']} "
              f"keys/s {sm['keys_per_s']}")
    out["all"] = summarise(every)
    if a.random_runs:
        out["random_policy"] = random_policy(a.random_runs)
    if a.json:
        a.json.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
