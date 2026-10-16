"""Two-Clapper live episodes (task 1v1 SP7, Forum_W_w13 = fo_cl_w13w: the final wave, two Choir Clappers) per arm, from
run manifests (1v1_live.ps1 / sp7_*.ps1).

Per episode: outcome, the kill time (both dead: the battle's end, attempts row kill_s), the fight time (f_wake to the
kill or the end), the hero's landed hits on the Clappers (all, per Clapper), the HP-loss hits (hits are counted by HP
loss: the bounce's i-frames give `damage` events without HP loss) with their source, the Clapper that dealt them (its
GameObject name in the source, "Song Heavy Sentry (2)", mapped to an iid by the first unambiguous slam / body hit, else
the nearest one in a state that fits), both Clappers' Control states, the hero's x from it (centre to centre, + = in
front of it), whether she stood between the two, the L2 goal / target at the hit (decision log: the focus or the other
one), the playbook's phase; per episode the geometry while both live: the share of time the two stand within 4 u of
each other (stacked), the hero between them, the hero within 8 u of the nearer one, and per Clapper its moves (slam /
cast / jump / jump cast / evade starts).

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.sp7_two --manifest C:/ssbot/sandbox/1v1sp7base_manifest.txt \
        [--arms rnjb] [--json out.json] [--hits]
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ssbot.combat import slam_play as sp
from ssbot.tools.slam_play_live import manifest, pct

MOVE_START = {"Slam Antic": "slam", "Spell Antic": "cast", "Jump Antic": "jump", "Cast Slam Antic": "jump_cast",
              "Evade Scuttle": "evade"}
WALL_L, WALL_R = sp.WALL_L, sp.WALL_R


def _hero_attacks():
    from ssbot.tools.forum_demo import HERO_ATTACKS
    return HERO_ATTACKS


def claps(s: dict) -> list[dict]:
    """The living Clappers of a STATE (the order of the STATE's entity list)."""
    return [e for e in s.get("ents") or () if e.get("type_key") == sp.CLAPPER and not e.get("is_dead")
            and (e.get("hp") or 0) > 0 and e.get("pos")]


def _decisions(run: Path, inst: int) -> dict:
    out = defaultdict(dict)
    p = run / f"decisions_i{inst}.jsonl"
    if not p.exists():
        return out
    for line in p.read_text("utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[int(r.get("ep", -1))][int(r["f"])] = r
    return out


def _name(src: str) -> str | None:
    m = re.match(r"(Song Heavy Sentry(?: \(\d+\))?)/", src or "")
    return m.group(1) if m else None


def _fits(src: str, st: str | None) -> bool:
    if "Slam Collider" in src:
        return st in ("Slam 0", "Slam 1", "Slam Effects?", "Slam 2", "Slam Recover", "Air", "Jump", "Land")
    return True


def episode(arm: str, inst: int, run: Path, row: dict, dec: dict) -> dict:
    from ssbot.record.recorder import RecordingReader
    HA = _hero_attacks()
    f_wake, f_end = int(row["f_wake"]), int(row["f_end"])
    fk = row.get("f_kill") or f_end
    states = list(RecordingReader(row["recording"]).states(f_wake, f_end))
    ep_id = f"{run.name[:15]}{run.name[-2:] if run.name.endswith('_2') else ''}_i{inst}_e{row['episode']}"
    ticks = dec.get(int(row["episode"]), {})
    tick_f = sorted(ticks)
    landed, hp_ev, by_f = [], [], {}
    landed_by = Counter()
    moves = defaultdict(Counter)
    prev_st = {}
    n_both = n_stack = n_between = n_near8 = 0
    first_kill_f = None
    for s in states:
        f = int(s["f"])
        by_f[f] = s
        cs = claps(s)
        if len(cs) < 2 and first_kill_f is None and f > f_wake + 30:
            first_kill_f = f
        for e in cs:
            st = sp.control(e)[0]
            if st in MOVE_START and prev_st.get(e["iid"]) != st:
                moves[e["iid"]][MOVE_START[st]] += 1
            prev_st[e["iid"]] = st
        if len(cs) == 2 and f <= fk and (s.get("hero") or {}).get("box"):
            hx = sp.hero_x(s)
            xa, xb = sorted(float(e["pos"][0]) for e in cs)
            n_both += 1
            n_stack += (xb - xa) < 4.0
            n_between += xa < hx < xb
            n_near8 += min(abs(hx - xa), abs(hx - xb)) <= 8.0
        for ev in s.get("ev") or ():
            k, d = ev.get("k"), ev.get("d") or {}
            if k == "hit" and d.get("type_key") == sp.CLAPPER and d.get("src") in HA:
                dealt = d.get("dealt", d.get("amount"))
                if dealt is None or float(dealt) > 0:
                    landed.append((f, str(d.get("src")), d.get("iid") or d.get("target_iid")))
            elif k == "hp" and (d.get("delta") or 0) < 0:
                hp_ev.append((f, -int(d.get("delta")), str(d.get("source"))))
    # the source names -> iids: a hit whose source fits exactly one living Clapper's state (else the nearest)
    names: dict[str, object] = {}
    hits = []
    for f, amt, src in hp_ev:
        s = by_f.get(f) or by_f.get(f - 1) or {}
        cs = claps(s)
        hx = sp.hero_x(s) if (s.get("hero") or {}).get("box") else None
        nm = _name(src)
        e = None
        if nm is not None and nm in names:
            e = next((c for c in cs if c["iid"] == names[nm]), None)
        if e is None and cs:
            fit = [c for c in cs if _fits(src, sp.control(c)[0])]
            pool = fit or cs
            e = min(pool, key=lambda c: abs(float(c["pos"][0]) - (hx if hx is not None else 0.0)))
            if nm is not None and len(fit) == 1 and nm not in names:
                names[nm] = e["iid"]
        other = next((c for c in cs if e is not None and c["iid"] != e["iid"]), None)
        tk = None
        i = np.searchsorted(tick_f, f, side="right") - 1
        if i >= 0 and f - tick_f[i] <= 6:
            tk = ticks[tick_f[i]]
        tgt = tk.get("tgt") if tk else None
        xs = sorted(float(c["pos"][0]) for c in cs)
        face = (1 if e.get("flipX") else -1) if e is not None else None
        pl = (tk or {}).get("play") or None
        hits.append({
            "f": f, "t": round((f - f_wake) / 60.0, 2), "amount": amt, "src": src.split("/")[-1].replace("(Clone)", ""),
            "src_full": src, "before_kill": f <= fk, "by": None if e is None else e["iid"],
            "st": None if e is None else sp.control(e)[0], "other_st": None if other is None else sp.control(other)[0],
            "x": None if (e is None or hx is None) else round((hx - float(e["pos"][0])) * face, 2),
            "sep": round(xs[1] - xs[0], 2) if len(xs) == 2 else None,
            "between": (len(xs) == 2 and hx is not None and xs[0] < hx < xs[1]),
            "air": not sp.on_ground(s) if s else None,
            "focus": None if (tgt is None or e is None) else ("focus" if tgt == e["iid"] else "other"),
            "goal": (tk or {}).get("goal"), "why": (tk or {}).get("goal_why"),
            "play": None if not pl else f"{pl.get('phase')}@{pl.get('k')}",
            "wall": None if e is None else round(min(float(e["pos"][0]) - WALL_L, WALL_R - float(e["pos"][0])), 2),
        })
    fight_s = round((fk - f_wake) / 60.0, 2)
    return {"ep": ep_id, "arm": arm, "outcome": row.get("outcome"), "kill_s": row.get("kill_s"),
            "ingame_s": row.get("ingame_s"), "fight_s": fight_s,
            "first_kill_s": None if first_kill_f is None else round((first_kill_f - f_wake) / 60.0, 2),
            "landed": sum(1 for f, _, _ in landed if f <= fk),
            "hp_hits_before_kill": sum(1 for h in hits if h["before_kill"]),
            "hp_lost_before_kill": sum(h["amount"] for h in hits if h["before_kill"]),
            "min_hp": row.get("min_hp"), "hits": hits,
            "both_s": round(n_both / 60.0, 2), "stack_share": round(n_stack / max(n_both, 1), 3),
            "between_share": round(n_between / max(n_both, 1), 3), "near8_share": round(n_near8 / max(n_both, 1), 3),
            "moves": {str(k): dict(v) for k, v in moves.items()},
            "slam_play": (row.get("policy") or {}).get("slam_play"),
            "l2": ((row.get("policy") or {}).get("l2") or {}).get("sp7")}


def summarize(E: list[dict]) -> dict:
    kills = [e for e in E if e["kill_s"] is not None]
    H = [h for e in E for h in e["hits"] if h["before_kill"]]
    mv = Counter()
    for e in E:
        for c in e["moves"].values():
            mv.update(c)
    return {
        "episodes": len(E), "outcomes": dict(Counter(e["outcome"] for e in E)), "kills": len(kills),
        "hp_hitless_kills": sum(1 for e in kills if e["hp_hits_before_kill"] == 0),
        "hp_hits_before_kill": len(H),
        "kill_s_p10_50_90": pct([e["kill_s"] for e in kills]),
        "first_kill_s_p50": pct([e["first_kill_s"] for e in E if e["first_kill_s"] is not None], (50,)),
        "landed_per_s_pooled": round(sum(e["landed"] for e in E) / max(sum(e["fight_s"] for e in E), 1e-9), 3),
        "landed_per_s_kills": round(sum(e["landed"] for e in kills) / max(sum(e["fight_s"] for e in kills), 1e-9), 3),
        "hits_by_src": dict(Counter(h["src"] for h in H)),
        "hits_by_state": dict(Counter(f"{h['src']} | {h['st']}" for h in H)),
        "hits_focus": dict(Counter(str(h["focus"]) for h in H)),
        "hits_between": dict(Counter(bool(h["between"]) for h in H)),
        "hits_air": dict(Counter(bool(h["air"]) for h in H)),
        "stack_share": round(float(np.mean([e["stack_share"] for e in E])) if E else 0.0, 3),
        "between_share": round(float(np.mean([e["between_share"] for e in E])) if E else 0.0, 3),
        "near8_share": round(float(np.mean([e["near8_share"] for e in E])) if E else 0.0, 3),
        "moves": dict(mv),
    }


def boot(x: list, y: list, f, n: int = 4000, seed: int = 7) -> list:
    """Bootstrap (episodes resampled) 5 / 50 / 95 % of f(y) - f(x)."""
    rng = random.Random(seed)
    d = [f([rng.choice(y) for _ in y]) - f([rng.choice(x) for _ in x]) for _ in range(n)]
    return [round(float(np.percentile(d, q)), 3) for q in (5, 50, 95)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", action="append", required=True)
    ap.add_argument("--arms", default="")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--hits", action="store_true", help="list every HP-loss hit")
    ap.add_argument("--base", default="", help="the base arm for the bootstrap A/B")
    a = ap.parse_args(argv)
    arms = set(filter(None, a.arms.split(",")))
    E = defaultdict(list)
    for arm, inst, run in manifest(a.manifest, arms):
        dec = _decisions(run, inst)
        p = run / f"attempts_i{inst}.jsonl"
        if not p.exists():
            continue
        for line in p.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("outcome") == "HARNESS_FAIL" or not row.get("recording"):
                E[arm].append({"ep": f"{run.name}_e{row.get('episode')}", "arm": arm, "outcome": "HARNESS_FAIL",
                               "kill_s": None, "fight_s": 0.0, "first_kill_s": None, "landed": 0,
                               "hp_hits_before_kill": 0, "hp_lost_before_kill": 0, "hits": [], "moves": {},
                               "stack_share": 0.0, "between_share": 0.0, "near8_share": 0.0})
                continue
            E[arm].append(episode(arm, inst, run, row, dec))
    out = {arm: summarize(v) for arm, v in E.items()}
    for arm, v in out.items():
        print(arm, json.dumps(v))
        for e in E[arm]:
            print(f"  {e['ep']:28s} {e['outcome']:6s} kill {e['kill_s']} first {e.get('first_kill_s')} landed "
                  f"{e['landed']} fight {e['fight_s']} hp-hits {e['hp_hits_before_kill']} stack {e['stack_share']} "
                  f"between {e['between_share']} moves {e['moves']}")
            if a.hits:
                for h in e["hits"]:
                    print(f"     t {h['t']:6.2f} {h['src']:18s} by {h['st']!s:14s} other {h['other_st']!s:14s} x "
                          f"{h['x']} sep {h['sep']} between {h['between']} air {h['air']} {h['focus']} "
                          f"goal {h['goal']} why {h['why']} play {h['play']} wall {h['wall']}")
    if a.base and a.base in E:
        hl = lambda v: [1 if (x["kill_s"] is not None and x["hp_hits_before_kill"] == 0) else 0 for x in v]  # noqa
        pooled = lambda v: sum(x["landed"] for x in v) / max(sum(x["fight_s"] for x in v), 1e-9)          # noqa
        med = lambda v: float(np.median([x["kill_s"] for x in v])) if v else float("nan")                 # noqa
        for arm in E:
            if arm == a.base:
                continue
            kb = [x for x in E[a.base] if x["kill_s"] is not None]
            ka = [x for x in E[arm] if x["kill_s"] is not None]
            print(f"{arm} - {a.base}: landed/s", boot(E[a.base], E[arm], pooled),
                  "| kill p50", boot(kb, ka, med) if kb and ka else None,
                  "| hitless share", boot(hl(E[a.base]), hl(E[arm]), lambda v: sum(v) / len(v)))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps({"arms": out, "episodes": E}, indent=1, default=str), "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
