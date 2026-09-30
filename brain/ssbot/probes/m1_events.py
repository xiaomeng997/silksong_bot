"""M1 package events-scene-progress: in-game check of EventTap, SceneDumper and ProgressExporter.

Needs the training copy running with this SsOracle build (title screen or in game; slot 1 = the Bonetown bench
save used by P3/P6/P7) and nothing else connected to IPC v1. The game does not need focus.

    cd brain
    uv run python -m ssbot.probes.m1_events [--walk left|right] [--walk-seconds 25]

Steps: connect IPC v1 (expects a full PROGRESS, and a TERRAIN if already in a room) -> load slot 1 if at the
menu (gs edges, scene_enter, TERRAIN, PROGRESS pd_swap) -> leave the bench and wait until Hornet can be hurt
(accepting input, off the bench, nothing blocking pause) -> 'hurt 1 ENEMY' on the debug line server (damage, hp
with caller, freeze start/end, disable_pause edges) -> heal with pdset (hp from the poll) -> 'hurt 1 SPIKES'
(hazard_death, hazard_respawn start and its end from the coroutine's last step >= 0.3 s later, disable_pause on
before the start and off in the end's frame, no scene_enter) and heal again -> pause and unpause (pause_allowed
edges from PreventPause/AllowPause) -> walk (--walk, default left) through a room transition (scene_leave,
scene_enter, TERRAIN for the new room) -> RPC scene.dump and progress.full. Prints PASS/FAIL per check, message
sizes, STATE cost (cost_us and cost_ex per section), the TERRAIN dump's work per frame (room.work_us) and event
counts. Exit code 1 on any FAIL.

Needs a save where one SPIKES hit is not lethal (slot 1 is healed back to its starting health before it).
"""
import argparse
import sys
import threading
import time
from collections import Counter, defaultdict

from ssbot.io.sinks.oracle_inject import OracleClient
from ssbot.ipc.framing import MsgType
from ssbot.ipc.oracle_link import OracleLink
from ssbot.oracle.messages import GATE_BITS, EventLog, ProgressMirror, Terrain, split_frame, unpack
from ssbot.probes.p3_inject import load_slot_one

PLAYING = 4


class Recorder:
    """Everything the oracle sends, decoded on the link's reader thread."""

    def __init__(self, link: OracleLink):
        self.lock = threading.Lock()
        self.events = EventLog()
        self.terrains: list[tuple[float, int, Terrain]] = []
        self.progress: list[tuple[float, int, dict]] = []
        self.mirror = ProgressMirror()
        self.state_sizes: list[int] = []
        self.cost_us: list[int] = []
        self.cost_ex: dict[str, list[int]] = defaultdict(list)
        self.poll_us: list[int] = []
        self.room_work_us: list[int] = []
        self.main_us: list[int] = []  # STATE build + tap poll + TERRAIN dump work, per STATE
        self.last_tap: dict = {}
        link.subscribe_raw(self._on_raw)

    def _on_raw(self, msg_type: int, raw: bytes) -> None:
        _, _, payload = split_frame(raw)
        msg = unpack(payload)
        now = time.monotonic()
        with self.lock:
            if msg_type == MsgType.STATE:
                self.state_sizes.append(len(raw))
                self.cost_us.append(msg.get("cost_us", 0))
                for k, v in (msg.get("cost_ex") or {}).items():
                    self.cost_ex[k].append(v)
                tap = msg.get("tap") or {}
                if tap:
                    self.last_tap = tap
                    self.poll_us.append(tap.get("poll_us", 0))
                room = msg.get("room") or {}
                if room:
                    self.room_work_us.append(room.get("work_us", 0))
                self.main_us.append(msg.get("cost_us", 0) + tap.get("poll_us", 0) + room.get("work_us", 0))
                self.events.add_state(msg)
            elif msg_type == MsgType.TERRAIN:
                self.terrains.append((now, len(raw), Terrain.decode(msg)))
            elif msg_type == MsgType.PROGRESS:
                self.progress.append((now, len(raw), msg))
                self.mirror.apply(msg)

    def wait(self, pred, timeout_s: float, poll_s: float = 0.02):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            with self.lock:
                r = pred()
            if r:
                return r
            time.sleep(poll_s)
        return None


class Checks:
    def __init__(self):
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok, detail: str = "") -> bool:
        ok = bool(ok)
        self.results.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
        return ok


def pct(values, q):
    if not values:
        return 0
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * q))]


def brief(e: dict, keys) -> str:
    return " ".join(f"{k}={e.get(k)}" for k in keys if k in e)


def ready(s: dict) -> bool:
    """Hornet can be hurt: playing, accepting input, off the bench and nothing blocking pause (blk == 0)."""
    p = s["pause"]
    return s["game"]["gs"] == PLAYING and p["hero_input"] and not p["bench"] and p["blk"] == 0


def wait_ready(link: OracleLink, timeout_s: float) -> dict | None:
    try:
        return link.wait_state(ready, timeout_s)
    except TimeoutError:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="M1 events-scene-progress in-game probe")
    ap.add_argument("--walk", choices=("left", "right"), default="left",
                    help="direction to walk from the bench to reach a room transition")
    ap.add_argument("--walk-seconds", type=float, default=25.0, help="give up on the transition after this long")
    args = ap.parse_args(argv)

    link = OracleLink()
    rec = Recorder(link)
    t_connect = time.monotonic()
    c = OracleClient()
    c.own(True)
    ck = Checks()
    print("hello rpcs:", link.hello.get("rpcs"))
    ck.check("rpcs registered", {"scene.dump", "progress.full"} <= set(link.hello.get("rpcs", ())))

    print("\n== connect ==")
    full = rec.wait(lambda: next((p for t, n, p in rec.progress if p["full"]), None), 3)
    ck.check("PROGRESS full on connect", full is not None,
             f"reason={full['reason']} fields={full.get('fields')} tools={len(full.get('tools', {}))}" if full else "none in 3 s")
    s = link.wait_state(timeout_s=5)
    tap = s.get("tap") or {}
    ck.check("all hooks installed", tap.get("hooks_failed") == 0, f"hooks_failed={tap.get('hooks_failed')}")
    in_room = s["game"] is not None and s["game"]["gs"] == PLAYING
    if in_room:
        t = rec.wait(lambda: next((t for _, _, t in rec.terrains if t.reason == "connect"), None), 5)
        ck.check("TERRAIN on connect (in a room)", t is not None, str(t.summary()) if t else "none in 5 s")

    print("\n== load slot 1 (if at the menu) ==")
    f0 = link.frame
    st = c.state()
    if st.get("state") != "PLAYING":
        load_slot_one(c)
        s = link.wait_state(lambda s: s["game"]["gs"] == PLAYING, 60)
        gs = rec.events.of("gs", since_frame=f0)
        ck.check("gs edges during load", any(e["to"] == "PLAYING" for e in gs), " -> ".join(e["to"] for e in gs))
        enter = rec.wait(lambda: next(iter(rec.events.of("scene_enter", since_frame=f0)), None), 10)
        ck.check("scene_enter on load", enter, brief(enter or {}, ("scene_raw", "gate", "gameplay", "seq")))
        t = rec.wait(lambda: next((t for _, _, t in rec.terrains if t.reason == "enter" and t.frame > f0), None), 10)
        ck.check("TERRAIN on load", t, str(t.summary()) if t else "none")
        p = rec.wait(lambda: next((p for _, _, p in rec.progress if p["full"] and p["frame"] > f0), None), 5)
        ck.check("PROGRESS full after PlayerData swap", p, f"reason={p['reason']}" if p else "none")
    else:
        print("  already in game")

    # Wake up / get control, then step off the bench. A hit is only taken once the hero is out of the bench
    # exit (CanTakeDamage is false before), so wait for a STATE that says so.
    link.wait_state(lambda s: s["game"]["gs"] == PLAYING and s["pause"]["hero_input"], 30)
    time.sleep(2.0)
    s = None
    for _ in range(3):
        c.tap("left", 0.3)
        s = wait_ready(link, 4)
        if s:
            break
    ck.check("hero ready (input, off the bench, blk == 0)", s,
             "" if s else f"last pause section {(link.state or {}).get('pause')}")
    time.sleep(0.5)

    print("\n== hurt 1 ENEMY ==")
    s = wait_ready(link, 10) or link.wait_state(timeout_s=2)
    hp0 = s["tap"]["hp"]
    f0 = s["f"]
    reply = c._call("hurt 1 ENEMY")
    print("  hurt ->", reply, "hp before", hp0)
    time.sleep(2.0)
    dmg = rec.events.of("damage", since_frame=f0)
    ck.check("damage event", any(e.get("hazard") == "ENEMY" for e in dmg),
             brief(dmg[0], ("source", "side", "amount", "hazard", "can_take", "invuln")) if dmg else
             "none; blocked: " + "; ".join(brief(e, ("hazard", "why", "n")) for e in rec.events.of("damage_blocked", since_frame=f0)))
    hp = [e for e in rec.events.of("hp", since_frame=f0) if e["delta"] < 0 or e["blue_delta"] < 0]
    ck.check("hp event from TakeHealth", any(e["src"] == "TakeHealth" and e.get("hazard_type") == "ENEMY" for e in hp),
             brief(hp[0], ("h", "hb", "delta", "blue_delta", "src", "hazard_type", "mask_broke", "mask_saved")) if hp else "none")
    if hp:
        print("    caller:", " <- ".join(hp[0].get("caller", ())))
    fr = rec.events.of("freeze", since_frame=f0)
    starts = [e for e in fr if e["phase"] == "start"]
    ends = [e for e in fr if e["phase"] == "end"]
    ck.check("freeze start and end", starts and ends and {e["id"] for e in starts} <= {e["id"] for e in ends},
             "; ".join(brief(e, ("phase", "id", "type", "wait", "ms", "reason")) for e in fr))
    pg = [e for e in rec.events.of("pause_gate", since_frame=f0) if e["gate"] == "disable_pause"]
    ck.check("disable_pause on and off", [e["value"] for e in pg][:2] == [True, False],
             "; ".join(brief(e, ("value", "src", "fsm")) for e in pg))

    print("\n== heal (pdset: a direct write, seen by the poll) ==")
    f0 = link.frame
    c._call(f"pdset health {hp0[0]}")
    heal = rec.wait(lambda: next((e for e in rec.events.of("hp", since_frame=f0) if e["delta"] > 0), None), 2)
    ck.check("hp event from poll", heal and heal["src"] == "poll", brief(heal or {}, ("h", "delta", "src")))

    print("\n== hurt 1 SPIKES (hazard death and respawn) ==")
    s = wait_ready(link, 10)
    ck.check("hero ready for the spikes hit", s, "" if s else f"last pause section {(link.state or {}).get('pause')}")
    s = s or link.wait_state(timeout_s=2)
    f0 = s["f"]
    reply = c._call("hurt 1 SPIKES")
    print("  hurt ->", reply)
    end = rec.wait(lambda: next((e for e in rec.events.of("hazard_respawn", since_frame=f0) if e["phase"] == "end"), None), 15)
    time.sleep(0.5)
    hd = rec.events.of("hazard_death", since_frame=f0)
    ck.check("hazard_death SPIKES", any(e["hazard"] == "SPIKES" for e in hd), "; ".join(brief(e, ("hazard", "h")) for e in hd))
    hp = [e for e in rec.events.of("hp", since_frame=f0) if e["delta"] < 0 or e["blue_delta"] < 0]
    ck.check("hp event from TakeHealth (SPIKES)", any(e["src"] == "TakeHealth" and e.get("hazard_type") == "SPIKES" for e in hp),
             brief(hp[0], ("h", "delta", "src", "hazard_type")) if hp else "none")
    start = next((e for e in rec.events.of("hazard_respawn", since_frame=f0) if e["phase"] == "start"), None)
    ck.check("hazard_respawn start", start, brief(start or {}, ("f", "id", "scene", "from", "marker", "open")))
    span = end["f"] - start["f"] if start and end else None
    # HeroController.HazardRespawn: WaitForSeconds(0.3) plus the respawn animation before its last step.
    ck.check("hazard_respawn end from the coroutine (done, >= 18 frames and >= 0.3 s after the start)",
             start and end and end["id"] == start["id"] and end["reason"] == "done" and span >= 18 and end["ms"] >= 300,
             f"span {span} frames; " + brief(end or {}, ("f", "id", "reason", "ms", "frames", "pos")))
    dp = [e for e in rec.events.of("pause_gate", since_frame=f0) if e["gate"] == "disable_pause"]
    on = next((e for e in dp if e["value"]), None)
    off = next((e for e in dp if not e["value"] and on is not None and e["f"] >= on["f"]), None)
    ck.check("disable_pause on before the start, off in the end's frame",
             on and off and start and end and on["f"] <= start["f"] and off["f"] == end["f"],
             "; ".join(brief(e, ("f", "value", "src")) for e in dp))
    extra = rec.events.of("scene_enter", since_frame=f0)
    ck.check("no scene_enter from the hazard respawn", not extra, "; ".join(brief(e, ("f", "scene_raw", "seq")) for e in extra))
    f1 = link.frame
    c._call(f"pdset health {hp0[0]}")
    rec.wait(lambda: next((e for e in rec.events.of("hp", since_frame=f1) if e["delta"] > 0), None), 2)

    print("\n== pause / unpause ==")
    link.wait_state(lambda s: s["pause"]["blk"] == 0, 10)
    time.sleep(0.3)
    f0 = link.frame
    c.tap("pause", 0.05)
    c.wait_for(lambda s: s.get("menu") == "PAUSE_MENU" and not s.get("menuFading"), 5)
    time.sleep(0.5)
    c.tap("enter", 0.05)  # Continue
    link.wait_state(lambda s: s["game"]["gs"] == PLAYING, 5)
    time.sleep(0.6)
    gs = rec.events.of("gs", since_frame=f0)
    ck.check("gs PLAYING -> PAUSED -> PLAYING", [e["to"] for e in gs][:2] == ["PAUSED", "PLAYING"], " -> ".join(e["to"] for e in gs))
    pa = [e for e in rec.events.of("pause_gate", since_frame=f0) if e["gate"] == "pause_allowed"]
    ck.check("pause_allowed edges from InputHandler", any(e["src"] == "InputHandler.PreventPause" for e in pa)
             and any(e["src"] == "InputHandler.AllowPause" for e in pa),
             "; ".join(brief(e, ("value", "src")) for e in pa))

    print(f"\n== room transition (walk {args.walk}) ==")
    s = link.wait_state(timeout_s=2)
    scene0 = s["game"]["scene_raw"]
    f0 = s["f"]
    n_terrain = len(rec.terrains)
    c.keys(args.walk)
    try:
        enter = rec.wait(lambda: next((e for e in rec.events.of("scene_enter", since_frame=f0) if e["scene_raw"] != scene0), None),
                         args.walk_seconds)
    finally:
        c.keys()
    leave = rec.events.of("scene_leave", since_frame=f0)
    ck.check("scene_leave", leave, brief(leave[0], ("from_raw", "to", "gate")) if leave else "none")
    ck.check("scene_enter (new room)", enter, brief(enter or {}, ("scene_raw", "gate", "gameplay", "seq")))
    gs = [e["to"] for e in rec.events.of("gs", since_frame=f0)]
    ck.check("gs EXITING_LEVEL -> ENTERING_LEVEL -> PLAYING", gs[:3] == ["EXITING_LEVEL", "ENTERING_LEVEL", "PLAYING"], " -> ".join(gs))
    if enter:
        t = rec.wait(lambda: next((t for _, _, t in rec.terrains[n_terrain:] if t.scene_raw == enter["scene_raw"]), None), 5)
        ck.check("TERRAIN for the new room", t and t.solids, str(t.summary()) if t else "none")

    print("\n== RPCs ==")
    n_terrain = len(rec.terrains)
    res = link.rpc("scene.dump", timeout_s=10)
    print("  scene.dump ->", res)
    t = rec.wait(lambda: next((t for _, _, t in rec.terrains[n_terrain:] if t.seq == res["seq"]), None), 3)
    ck.check("scene.dump sends TERRAIN", t and t.reason == "rpc", str(t.summary()) if t else "none")
    n_prog = len(rec.progress)
    res = link.rpc("progress.full", timeout_s=5)
    print("  progress.full ->", res)
    p = rec.wait(lambda: next((p for _, _, p in rec.progress[n_prog:] if p["seq"] == res["seq"]), None), 3)
    ck.check("progress.full sends PROGRESS", p and p["full"] and p["reason"] == "rpc", f"fields={p.get('fields')}" if p else "none")

    time.sleep(1.0)
    link.close()
    c.close()

    print("\n== PROGRESS ==")
    with rec.lock:
        diffs = [(t, n, p) for t, n, p in rec.progress if not p["full"]]
        fulls = [(t, n, p) for t, n, p in rec.progress if p["full"]]
        gaps = [b[0] - a[0] for a, b in zip(rec.progress, rec.progress[1:]) if not b[2]["full"]]
    ck.check("PROGRESS diffs arrive", diffs, f"{len(diffs)} diffs, e.g. {diffs[0][2]['changed'] if diffs else None}")
    ck.check("PROGRESS diffs <= 2 Hz", all(g >= 0.45 for g in gaps), f"min gap {min(gaps) if gaps else None}")
    print(f"  full sizes {[n for _, n, _ in fulls]} B; diff sizes p50 {pct([n for _, n, _ in diffs], .5)} max "
          f"{max((n for _, n, _ in diffs), default=0)} B; mirror fields {len(rec.mirror.fields)}, tools {len(rec.mirror.tools)}, "
          f"crest {rec.mirror.crest}, equipped {rec.mirror.equipped}")

    print("\n== TERRAIN ==")
    for _, n, t in rec.terrains:
        print(f"  #{t.seq} {t.reason:<7} {n:>7} B  {t.summary()}  stats={t.stats}")

    print("\n== STATE ==")
    print(f"  size p50 {pct(rec.state_sizes, .5)} B, max {max(rec.state_sizes)} B, {len(rec.state_sizes)} STATEs")
    print(f"  cost_us p50 {pct(rec.cost_us, .5)}  p99 {pct(rec.cost_us, .99)}  max {max(rec.cost_us)}")
    for k in sorted(rec.cost_ex):
        v = rec.cost_ex[k]
        print(f"  cost_ex[{k:<8}] p50 {pct(v, .5):>4}  p99 {pct(v, .99):>4}  max {max(v):>5} us")
    print(f"  tap.poll_us p50 {pct(rec.poll_us, .5)}  p99 {pct(rec.poll_us, .99)}  max {max(rec.poll_us, default=0)}")
    busy = [v for v in rec.room_work_us if v > 0]
    print(f"  room.work_us (frames with TERRAIN work: {len(busy)}) p50 {pct(busy, .5)}  max {max(busy, default=0)}")
    ck.check("STATE build p50 <= 300 us, p99 <= 1000 us (C14)", pct(rec.cost_us, .5) <= 300 and pct(rec.cost_us, .99) <= 1000)
    ck.check("TERRAIN dump work per frame <= 600 us", max(busy, default=0) <= 600, f"max {max(busy, default=0)} us")
    ck.check("STATE build + tap poll + TERRAIN work p50 <= 300 us, p99 <= 1000 us",
             pct(rec.main_us, .5) <= 300 and pct(rec.main_us, .99) <= 1000,
             f"p50 {pct(rec.main_us, .5)} p99 {pct(rec.main_us, .99)} max {max(rec.main_us, default=0)}")
    gates = rec.last_tap.get("gates", 0)
    print("  last gates:", [g for g, b in GATE_BITS.items() if gates & b])

    print("\n== events ==")
    counts = Counter(e["k"] for e in rec.events.events)
    print("  " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())), f"(lost {rec.events.lost})")

    failed = [r for r in ck.results if not r[1]]
    print(f"\n{len(ck.results) - len(failed)}/{len(ck.results)} checks passed" + (": FAIL " + ", ".join(r[0] for r in failed) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
