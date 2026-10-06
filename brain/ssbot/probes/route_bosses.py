"""Route bosses (Task route bosses, 2026-10-06): scout a boss arena from a savestate, find the boss's Control FSM and
what wakes it, and make the training savestate in front of the trigger. Training copy, oracle view, sandbox
savestates only; save suppression on throughout. Facts: docs/facts/1.0.30000/route_bosses.md (Chinese).

  scout    load --savestate, settle, report every FSM transition (fsmtap all) while the hero walks --walk for
           --walk-s (until a large-HP entity's FSM leaves its first state, then --watch-s more with no input), the
           HealthManager entities (type_key, hp, pos, fsms) and fsm.graph of every FSM on the largest-HP entity (or
           --obj). Writes OUT/<savestate>_scout.json.
  save     load --savestate, settle, optionally walk --walk to hero x --to-x, settle, savestate.save --out (the
           game-written training savestate), load it back and check the scene and position.
  graph    fsm.graph of --obj (all its FSMs, or --fsm) after loading --savestate and walking as scout does: the static
           graph for behaviour_build --fsm-graph. Writes OUT/<obj>_<fsm>.json.

    cd brain
    ..\\scripts\\uv.cmd run python -m ssbot.probes.route_bosses scout --instance 0 --savestate vs_p6_s3 --walk right
"""
import argparse
import json
import sys
import time
from pathlib import Path

from ssbot.ipc.framing import mask
from ssbot.ipc.oracle_link import OracleError, OracleLink

OUT = Path(r"C:\ssbot\sandbox\route_bosses")
BIG_HP = 100          # an entity with at least this much HP is a boss candidate


def connect(instance: int) -> OracleLink:
    from ssbot.probes.common import load_slot, stand_up
    from ssbot.train.episode import unpause
    link = OracleLink(instance=instance, connect_timeout_s=120)
    s = link.wait_state(lambda s: s.get("game") is not None, timeout_s=60)
    if (s.get("game") or {}).get("paused") and (s.get("game") or {}).get("scene"):
        unpause(link)
    if not (s.get("game") or {}).get("scene") or not s.get("hero"):
        load_slot(link, 1)
        stand_up(link)
    # else a game is loaded (perhaps held in a boss dialogue by an earlier scout): the savestate load takes it from
    # there, as combat_run does between episodes
    if not link.rpc("guards.set", timeout_s=30, save_suppression=True)["save_suppression"]:
        raise SystemExit("save suppression could not be turned on")
    return link


def settle(link: OracleLink, timeout_s: float = 30.0) -> dict:
    """The first STATE after a load from which the hero, accepting input, stays put for 10 frames (any scene)."""
    from ssbot.train.episode import wait_settled
    s = link.wait_state(lambda s: (s.get("game") or {}).get("scene") and s.get("hero")
                        and s["hero"].get("hero_accepting_input"), timeout_s=timeout_s)
    return wait_settled(link, s["game"]["scene"], timeout_s=timeout_s)


class Log:
    """Every fsm / hit event and a sampled view of the HealthManager entities, keyed by frame."""

    def __init__(self, link: OracleLink):
        self.fsm: list[dict] = []
        self.hits: list[dict] = []
        self.ents: dict[int, dict] = {}
        self.samples: list[dict] = []
        self.hero: dict = {}
        self.first_state: dict[tuple, str] = {}
        self.woke: dict | None = None
        self.on = True
        link.subscribe_state(self._on)

    def _on(self, s: dict) -> None:
        if not self.on:
            return
        f = s["f"]
        hx = (s.get("hero") or {}).get("pos") or [None, None]
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if ev.get("k") == "fsm":
                row = {"f": f, "obj": d.get("obj"), "fsm": d.get("fsm"), "from": d.get("from"), "to": d.get("to"),
                       "iid": d.get("iid"), "ent": d.get("ent"), "t_in_prev": d.get("t_in_prev"),
                       "hero": [round(hx[0], 2), round(hx[1], 2)] if hx[0] is not None else None}
                self.fsm.append(row)
            elif ev.get("k") == "hit":
                self.hits.append({"f": f, **{k: d.get(k) for k in ("src", "dst", "amount", "dead", "hp")}})
        for e in s.get("ents") or ():
            if e.get("hp") is None:
                continue
            key = e["iid"]
            cur = {"type_key": e.get("type_key"), "hp": e.get("hp"), "pos": [round(v, 2) for v in e["pos"][:2]],
                   "hidden": e.get("hidden", False), "fsms": {m["name"]: m["state"] for m in e.get("fsms") or ()}}
            old = self.ents.get(key)
            if old is None:
                self.ents[key] = {**cur, "first_f": f, "max_hp": cur["hp"], "states": {}}
                old = self.ents[key]
            old.update({k: cur[k] for k in ("hp", "pos", "hidden")})
            old["max_hp"] = max(old["max_hp"], cur["hp"] or 0)
            for name, st in cur["fsms"].items():
                seen = old["states"].setdefault(name, [])
                if not seen or seen[-1] != st:
                    seen.append(st)
                first = self.first_state.setdefault((key, name), st)
                if (self.woke is None and (old["max_hp"] or 0) >= BIG_HP and st != first):
                    self.woke = {"f": f, "iid": key, "type_key": cur["type_key"], "fsm": name, "from": first,
                                 "to": st, "hero": [round(hx[0], 2), round(hx[1], 2)] if hx[0] is not None else None}
        if f % 30 == 0 and s.get("hero"):
            self.samples.append({"f": f, "hero": [round(v, 2) for v in s["hero"]["pos"][:2]],
                                 "hp": s["hero"].get("health"), "scene": (s.get("game") or {}).get("scene")})


def drive(link: OracleLink, button: int, until, timeout_s: float) -> dict:
    """Hold `button` (continuous control, one ACTION per STATE) until until(s) or the timeout; then release."""
    last = link.frame
    s = link.state
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        s = link.wait_state(newer_than=last, timeout_s=2.0)
        last = s["f"]
        if until(s):
            break
        link.act(last + 2, button, hold_frames=0)
    link.act(link.frame + 2, 0, hold_frames=0)
    return s


def idle(link: OracleLink, seconds: float) -> dict:
    return drive(link, 0, lambda s: False, seconds)


def fsm_summary(rows: list[dict]) -> list[dict]:
    """Per (obj, fsm): the distinct states in order of first entry, the number of transitions."""
    by: dict[tuple, dict] = {}
    for r in rows:
        k = (r["obj"], r["fsm"])
        d = by.setdefault(k, {"obj": r["obj"], "fsm": r["fsm"], "n": 0, "states": [], "first_f": r["f"]})
        d["n"] += 1
        if r["to"] not in d["states"]:
            d["states"].append(r["to"])
    return sorted(by.values(), key=lambda d: -len(d["states"]))


def walk_button(name: str) -> int:
    return {"right": mask("right"), "left": mask("left"), "none": 0}[name]


def scout(link: OracleLink, a) -> dict:
    link.rpc("fsmtap.set", timeout_s=10, all=True)
    log = Log(link)
    try:
        link.rpc("savestate.load", timeout_s=60, name=a.savestate, timeout=50)
        s = settle(link)
        start = {"f": s["f"], "scene": s["game"]["scene"], "hero": s["hero"]["pos"][:2],
                 "health": s["hero"].get("health"), "silk": s["hero"].get("silk")}
        print("settled", json.dumps(start), flush=True)
        t0 = time.monotonic()
        if a.walk != "none":
            for w, secs in ((("right", a.walk_s), ("left", 2 * a.walk_s)) if a.walk == "auto"
                            else ((a.walk, a.walk_s),)):
                drive(link, walk_button(w), lambda s: log.woke is not None
                      or (a.to_x is not None and abs(s["hero"]["pos"][0] - a.to_x) < 0.3), secs)
                if log.woke is not None:
                    break
        print("woke", json.dumps(log.woke), f"after {time.monotonic() - t0:.1f} s", flush=True)
        idle(link, a.watch_s)
    finally:
        log.on = False
        try:
            link.rpc("fsmtap.set", timeout_s=10, all=False)
            link.rpc("input.release", timeout_s=10)
        except (OracleError, TimeoutError):
            pass
    big = sorted(log.ents.items(), key=lambda kv: -(kv[1]["max_hp"] or 0))
    obj = a.obj or (big[0][1]["type_key"] if big else None)
    graphs = {}
    if obj:
        try:
            g = link.rpc("fsm.graph", timeout_s=30, obj=obj)
            graphs = {x.get("fsm"): x for x in (g if isinstance(g, list) else [g])}
        except (OracleError, TimeoutError) as e:
            graphs = {"error": str(e)}
    out = {"savestate": a.savestate, "start": start, "woke": log.woke, "ents": {str(k): v for k, v in big},
           "fsm_summary": fsm_summary(log.fsm), "fsm": log.fsm, "hits": log.hits, "samples": log.samples,
           "graph_obj": obj, "graphs": graphs}
    for k, v in big[:8]:
        print("ent", k, v["type_key"], "hp", v["max_hp"], v["pos"], {n: st[:12] for n, st in v["states"].items()},
              flush=True)
    for d in fsm_summary(log.fsm)[:12]:
        print("fsm", d["obj"], d["fsm"], d["n"], d["states"][:25], flush=True)
    return out


def save(link: OracleLink, a) -> dict:
    link.rpc("savestate.load", timeout_s=60, name=a.savestate, timeout=50)
    s = settle(link)
    if a.walk != "none" and a.to_x is not None:
        s = drive(link, walk_button(a.walk), lambda s: (s["hero"]["pos"][0] >= a.to_x if a.walk == "right"
                                                        else s["hero"]["pos"][0] <= a.to_x), a.walk_s)
        s = settle(link)
    if a.pdset:
        from ssbot.train.wave_start import DebugLine
        dl = DebugLine(a.instance)
        try:
            for item in a.pdset:
                k, v = item.split("=", 1)
                print("pdset", k, v, dl.pdset(k, v), flush=True)
        finally:
            dl.close()
    before = {"scene": s["game"]["scene"], "hero": s["hero"]["pos"][:2], "health": s["hero"].get("health"),
              "silk": s["hero"].get("silk")}
    r = link.rpc("savestate.save", timeout_s=30, name=a.out)
    link.rpc("savestate.load", timeout_s=60, name=a.out, timeout=50)
    s2 = settle(link)
    after = {"scene": s2["game"]["scene"], "hero": s2["hero"]["pos"][:2], "health": s2["hero"].get("health"),
             "silk": s2["hero"].get("silk")}
    ok = after["scene"] == before["scene"] and abs(after["hero"][0] - before["hero"][0]) < 0.5
    print("saved", a.out, json.dumps(before), "->", json.dumps(after), "ok" if ok else "MISMATCH", flush=True)
    return {"out": a.out, "rpc": r, "before": before, "after": after, "ok": ok}


def graph(link: OracleLink, a) -> dict:
    link.rpc("savestate.load", timeout_s=60, name=a.savestate, timeout=50)
    settle(link)
    if a.walk != "none":
        log = Log(link)
        drive(link, walk_button(a.walk), lambda s: log.woke is not None, a.walk_s)
        log.on = False
        idle(link, 1.0)
    args = {"obj": a.obj}
    if a.fsm:
        args["fsm"] = a.fsm
    g = link.rpc("fsm.graph", timeout_s=30, **args)
    link.rpc("input.release", timeout_s=10)
    return {"obj": a.obj, "graphs": g if isinstance(g, list) else [g]}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=("scout", "save", "graph"))
    p.add_argument("--instance", type=int, default=0)
    p.add_argument("--savestate", required=True)
    p.add_argument("--walk", choices=("right", "left", "auto", "none"), default="none",
                   help="auto (scout): right for --walk-s, then left for twice that, until a boss wakes")
    p.add_argument("--walk-s", type=float, default=8.0)
    p.add_argument("--to-x", type=float, default=None)
    p.add_argument("--watch-s", type=float, default=20.0)
    p.add_argument("--obj", default=None)
    p.add_argument("--fsm", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--pdset", action="append", default=[], help="field=value, before the save (repeatable)")
    a = p.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    link = connect(a.instance)
    try:
        if a.cmd == "scout":
            res = scout(link, a)
            path = OUT / f"{a.savestate}_scout.json"
        elif a.cmd == "save":
            if not a.out:
                raise SystemExit("save needs --out")
            res = save(link, a)
            path = OUT / f"{a.out}_save.json"
        else:
            if not a.obj:
                raise SystemExit("graph needs --obj")
            res = graph(link, a)
            path = OUT / f"{a.obj.replace(' ', '_')}_{a.fsm or 'all'}.json"
        path.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        print("wrote", path, flush=True)
    finally:
        link.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
