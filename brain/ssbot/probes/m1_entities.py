"""M1 entities-fsm check: STATE "ents", "fsm" events, and the fsm.graph / fsmtap.set / ents.stats RPCs.

Needs the training copy running with SsOracle (EntitiesModule installed) and gameplay on screen, ideally with
enemies in view. Sandbox save 1 sits at the Bonetown bench; --walk 4 walks right towards the first enemies.
From brain/:

    uv run python -m ssbot.probes.m1_entities [--load] [--walk SECONDS] [--seconds 10] [--instance 0]

Prints entity counts per category, one full entity, cost_ex["ents"] p50/p99 and the FSM events seen, then one
PASS/FAIL/SKIP line per check. Exit code 1 if any check fails.
"""
import argparse
import json
import statistics
import sys
import threading
import time
from collections import Counter

import msgpack

from ssbot.ipc import ents
from ssbot.ipc.framing import HEADER, MsgType, mask
from ssbot.ipc.oracle_link import OracleLink

MAIN_MENU, PLAYING = 1, 4  # GlobalEnums.GameState
TARGET_P50_US, BUDGET_P99_US = 150, 1000  # package target (ents alone) and C14 p99 budget


class Recorder:
    """Decodes every STATE on the link's reader thread: polling skips frames, and an event lives in one STATE."""

    def __init__(self):
        self._lock = threading.Lock()
        self._states: list[dict] = []
        self.active = False

    def __call__(self, msg_type: int, raw: bytes) -> None:
        if msg_type != MsgType.STATE or not self.active:
            return
        s = msgpack.unpackb(raw[HEADER.size:], raw=False, strict_map_key=False)
        s["_bytes"] = len(raw)
        with self._lock:
            self._states.append(s)

    def take(self) -> list[dict]:
        with self._lock:
            out, self._states = self._states, []
        return out


def record(link: OracleLink, rec: Recorder, seconds: float) -> list[dict]:
    rec.take()
    rec.active = True
    time.sleep(seconds)
    rec.active = False
    return rec.take()


def tap(link: OracleLink, key: str) -> None:
    link.act(link.frame + 2, mask(key), hold_frames=3)


def load_slot_one(link: OracleLink) -> None:
    """Best effort from the title screen: Enter (Start) then Enter (highlighted slot 1)."""
    link.wait_state(lambda s: s["game"]["gs"] == MAIN_MENU, timeout_s=60)
    time.sleep(1.5)
    tap(link, "enter")
    time.sleep(2.0)
    tap(link, "enter")
    link.wait_state(lambda s: s["game"]["gs"] == PLAYING, timeout_s=90)
    time.sleep(2.0)


def walk(link: OracleLink, key: str, seconds: float) -> None:
    """Hold a direction; ACTIONs are renewed every 100 ms (the oracle releases keys after 250 ms of silence)."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        link.act(link.frame + 1, mask(key), hold_frames=12)
        time.sleep(0.1)
    link.act(link.frame + 1, 0)
    time.sleep(0.3)


def pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * q))] if xs else float("nan")


def rounded(v, nd: int = 3):
    if isinstance(v, float):
        return round(v, nd)
    if isinstance(v, list):
        return [rounded(x, nd) for x in v]
    if isinstance(v, dict):
        return {k: rounded(x, nd) for k, x in v.items()}
    return v


def print_entity(e: dict, max_verts: int = 40) -> None:
    """One key per line, compact JSON values, long vertex lists cut."""
    e = rounded(e)
    for c in e["colliders"]:
        if len(c["verts_world"]) > max_verts:
            c["verts_world"] = c["verts_world"][:max_verts] + ["..."]
    for k, v in e.items():
        if k == "colliders":
            print(f"  colliders ({len(v)}):")
            for c in v:
                print("    " + json.dumps(c))
        else:
            print(f"  {k}: {json.dumps(v)}")


def pick_sample(seen: dict[int, dict]) -> dict | None:
    def score(e: dict) -> tuple:
        threats = sum(1 for c in e["colliders"] if c["damage"])
        return (e["hp"] is not None, bool(e["fsms"]), threats, len(e["colliders"]))
    return max(seen.values(), key=score) if seen else None


class Checks:
    def __init__(self):
        self.failed = 0
        self.lines: list[str] = []

    def add(self, name: str, ok: bool | None, detail: str = "") -> None:
        verdict = "SKIP" if ok is None else "PASS" if ok else "FAIL"
        self.failed += ok is False
        self.lines.append(f"  {verdict:4}  {name}{': ' + detail if detail else ''}")


def fsm_consistency(states: list[dict]) -> tuple[int, int, int, int]:
    """(chained, chain_total, agree, agree_total).

    chained: consecutive events of one (iid, fsm) where from == the previous event's to (restarts excluded).
    agree: per-frame ents fsms[].state equal to the last event's "to" for that root FSM at or before the frame.
    """
    last_to: dict[tuple, str] = {}
    chained = chain_total = agree = agree_total = 0
    for s in states:
        for ev in ents.fsm_events(s):
            key = (ev["iid"], ev["fsm"])
            if key in last_to and ev["from"] is not None:
                chain_total += 1
                chained += ev["from"] == last_to[key]
            last_to[key] = ev["to"]
        for e in s.get("ents") or ():
            names = Counter(f["name"] for f in e["fsms"])
            for f in e["fsms"]:
                key = (e["iid"], f["name"])
                if names[f["name"]] == 1 and key in last_to:
                    agree_total += 1
                    agree += f["state"] == last_to[key]
    return chained, chain_total, agree, agree_total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--walk", type=float, default=0.0, help="hold right for this many seconds first")
    ap.add_argument("--load", action="store_true", help="load save slot 1 from the title screen first")
    args = ap.parse_args()
    checks = Checks()

    link = OracleLink(instance=args.instance)
    rpcs = set(link.hello["rpcs"])
    missing = {"fsm.graph", "fsmtap.set", "ents.stats"} - rpcs
    checks.add("RPCs registered", not missing, f"missing {sorted(missing)}" if missing else "")
    s = link.wait_state(timeout_s=5)
    if "ents" not in s:
        print('STATE has no "ents": is Entities.EntitiesModule.Install in Modules.InstallAll?')
        return 1
    if s["game"] is None or s["game"]["gs"] != PLAYING:
        if args.load:
            load_slot_one(link)
        else:
            print("waiting for gameplay (load a save; --load does it from the title screen) ...")
            link.wait_state(lambda s: s["game"]["gs"] == PLAYING, timeout_s=180)
    if args.walk > 0:
        walk(link, "right", args.walk)

    rec = Recorder()
    link.subscribe_raw(rec)
    print(link.rpc("fsmtap.set", all=False, enabled=True))
    print(f"recording {args.seconds:.0f} s in scene {link.state['game']['scene']} ...")
    states = record(link, rec, args.seconds)
    if not states:
        print("no STATE received")
        return 1

    # ---- entities -----------------------------------------------------------------------------------------
    playing = [s for s in states if s["game"] and s["game"]["gs"] == PLAYING]
    with_ents = [s for s in playing if isinstance(s.get("ents"), list)]
    checks.add('"ents" is a list in every gameplay STATE', len(with_ents) == len(playing),
               f"{len(with_ents)}/{len(playing)}")
    seen: dict[int, dict] = {}
    per_frame = []
    schema_errors: list[str] = []
    for st in with_ents:
        per_frame.append(len(st["ents"]))
        for e in st["ents"]:
            seen[e["iid"]] = e
            if len(schema_errors) < 5:
                schema_errors += [f"{e.get('type_key')}: {m}" for m in ents.validate_entity(e)]
    checks.add("entity schema", not schema_errors, "; ".join(schema_errors[:5]))
    cats = ents.count_categories(seen.values())
    print(f"\nentities per frame: mean {statistics.fmean(per_frame) if per_frame else 0:.1f}, max {max(per_frame, default=0)}")
    print(f"distinct entities over {args.seconds:.0f} s by category: {dict(cats)}")
    print("by type_key:", dict(Counter(e["type_key"] for e in seen.values()).most_common(12)))
    for e in sorted(seen.values(), key=lambda e: (e["category"], e["type_key"]))[:25]:
        print("  ", ents.describe(e))
    sample = pick_sample(seen)
    if sample:
        print("\none full entity (last seen; long vertex lists cut):")
        print_entity(sample)
    enemies = cats.get("enemy", 0)
    checks.add("enemies in view", enemies > 0 or None, f"{enemies} distinct" if enemies else "none in view; try --walk 4")

    # ---- cost -------------------------------------------------------------------------------------------
    cost = [st["cost_ex"]["ents"] for st in states if "ents" in (st.get("cost_ex") or {})]
    total = [st["cost_us"] for st in states]
    print(f"\ncost_ex[ents] us: p50 {pct(cost, .5):.0f}  p99 {pct(cost, .99):.0f}  max {max(cost, default=0)}  (n={len(cost)})")
    print(f"STATE build cost_us: p50 {pct(total, .5):.0f}  p99 {pct(total, .99):.0f}  max {max(total, default=0)}")
    sizes = [st["_bytes"] for st in states]
    print(f"STATE size p50 {statistics.median(sizes):.0f} B, max {max(sizes)} B")
    checks.add(f"ents p50 <= {TARGET_P50_US} us", bool(cost) and pct(cost, .5) <= TARGET_P50_US, f"{pct(cost, .5):.0f} us")
    checks.add(f"ents p99 <= {BUDGET_P99_US} us", bool(cost) and pct(cost, .99) <= BUDGET_P99_US, f"{pct(cost, .99):.0f} us")
    checks.add("STATE p50 <= 300 us, p99 <= 1000 us (C14)", pct(total, .5) <= 300 and pct(total, .99) <= 1000,
               f"p50 {pct(total, .5):.0f}, p99 {pct(total, .99):.0f}")

    # ---- fsm events --------------------------------------------------------------------------------------
    events = [ev for st in states for ev in ents.fsm_events(st)]
    frames = [st["f"] for st in states]
    gaps = sum(1 for a, b in zip(frames, frames[1:]) if b != a + 1)
    print(f"\nfsm events: {len(events)} in {args.seconds:.0f} s ({len(events) / args.seconds:.1f}/s); "
          f"STATE frame gaps {gaps}, drop counter {states[-1]['drop']}")
    by_fsm = Counter((ev["obj"], ev["fsm"]) for ev in events)
    for (obj, fsm), n in by_fsm.most_common(10):
        print(f"   {n:4d}  {obj} / {fsm}")
    for ev in events[:12]:
        after = f" (after {ev['t_in_prev']:.2f} s)" if ev["t_in_prev"] is not None else " (start)"
        print(f"   f{ev['f']} {ev['obj']}/{ev['fsm']}: {ev['from']} -> {ev['to']}{after}")
    bad_t = [ev for ev in events if (ev["from"] is None) != (ev["t_in_prev"] is None)
             or (ev["t_in_prev"] is not None and ev["t_in_prev"] < 0)]
    checks.add("fsm event t_in_prev (>= 0, null exactly on starts)", not bad_t, f"{len(bad_t)} bad" if bad_t else "")
    bad_keys = [ev for ev in events if set(ev) - {"f"} != ents.FSM_EVENT_KEYS]
    checks.add("fsm event keys", not bad_keys, f"{len(bad_keys)} malformed" if bad_keys else "")
    has_fsms = any(e["fsms"] for e in seen.values())
    checks.add("fsm events seen", (len(events) > 0) if has_fsms else None,
               f"{len(events)}" if has_fsms else "no entity with FSMs in view")
    chained, chain_total, agree, agree_total = fsm_consistency(states)
    if chain_total:
        # Not exactly 100%: the per-frame cap, or an FSM that is only reported while its root is in view.
        checks.add("event chains (from == previous to)", chained >= 0.95 * chain_total, f"{chained}/{chain_total}")
    if agree_total:
        checks.add("ents fsms[].state == last event's to", agree >= 0.95 * agree_total, f"{agree}/{agree_total}")

    # ---- fsm.graph ----------------------------------------------------------------------------------------
    target = next(((e["iid"], e["fsms"][0]["name"]) for e in [sample] if e and e["fsms"]), None)
    if target is None and events:
        target = (events[0]["iid"], events[0]["fsm"])
    if target:
        try:
            g = link.rpc("fsm.graph", iid=target[0], fsm=target[1])
            names = {st["name"] for st in g["states"]}
            n_tr = sum(len(st["transitions"]) for st in g["states"]) + len(g["global"])
            dangling = {to for st in g["states"] for to in st["transitions"].values()} - names
            print(f"\nfsm.graph {g['obj']}/{g['fsm']} (template {g['template']}): {len(names)} states, {n_tr} transitions, "
                  f"start {g['start']}, active {g['active']}, {len(g['events'])} events")
            for st in g["states"][:8]:
                print(f"   {st['name']}: {st['transitions']}  actions={st['actions'][:6] if st['actions'] else st['actions']}")
            checks.add("fsm.graph", (not g["active"] or g["active"] in names) and not dangling,
                       f"dangling targets {sorted(dangling)}" if dangling else f"{len(names)} states")
        except Exception as ex:  # noqa: BLE001 - report and carry on
            checks.add("fsm.graph", False, repr(ex))
        try:
            all_graphs = link.rpc("fsm.graph", iid=target[0])
            checks.add("fsm.graph without fsm lists all FSMs", isinstance(all_graphs, list) and len(all_graphs) >= 1,
                       f"{len(all_graphs)} FSMs")
        except Exception as ex:  # noqa: BLE001
            checks.add("fsm.graph without fsm lists all FSMs", False, repr(ex))
    else:
        checks.add("fsm.graph", None, "no FSM to query")

    # ---- fsmtap all ---------------------------------------------------------------------------------------
    print("\nfsmtap.set all ->", link.rpc("fsmtap.set", all=True))
    all_states = record(link, rec, 2.0)
    print("fsmtap.set back ->", link.rpc("fsmtap.set", all=False))
    all_events = [ev for st in all_states for ev in ents.fsm_events(st)]
    rate_all, rate_ent = len(all_events) / 2.0, len(events) / args.seconds
    print(f"all-FSM mode: {rate_all:.1f} events/s vs {rate_ent:.1f}/s filtered; "
          f"{len({(ev['iid'], ev['fsm']) for ev in all_events})} distinct FSMs")
    checks.add("fsmtap all mode reports at least as much", rate_all >= rate_ent * 0.5 and (rate_all > 0 or rate_ent == 0),
               f"{rate_all:.1f}/s vs {rate_ent:.1f}/s")

    stats = link.rpc("ents.stats")
    print("\nents.stats:", stats)
    link.close()

    print("\nchecks:")
    print("\n".join(checks.lines))
    print("RESULT:", "FAIL" if checks.failed else "PASS")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    sys.exit(main())
