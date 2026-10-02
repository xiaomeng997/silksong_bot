"""M2 oracle exports probe (cross-module decision 5; field list docs/facts/1.0.30000/state_fields_m2.md): on one
training instance, load the Bell Beast savestate, check the new STATE fields at rest and in the pause menu, then play one
Bell Beast episode (the encounter's intro through ssbot.train.episode.run_episode, a DataPolicy pinned to PRESS, mode
"data" so LethalBlock keeps the hero alive) and check the combat fields. PASS/FAIL per check; exit 0 only if all pass.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.launcher -n 1 --detach      # an instance running the new plugin
    ../scripts/uv.cmd run python -m ssbot.probes.m2_exports [--instance 0] [--seed 3] [--skip-menu] [--skip-fight]

Checks:
  rest   act.hf: 22 pending / age entries, ints, age <= 255, latched == act.mask, latched == desired when nothing is
         pending; hero.alpha in [0, 1); hero.wall two bools; hero.tm has its 15 keys; hero.tags a list; hero.tool_max
         aligned with hero.tools and >= tool_amounts; room.gates lists both "Threaded Bell Gate"s, off before the fight.
  menu   Esc (only while pause.blk == 0) pauses: sel "continue", dim ~0.8, alpha ~1, quit_ok == not (dsq or preload),
         ignore_unpause false once the menu is up, quitting false; Down / Up move sel to "options" / "quit" and back;
         Submit only on a "continue" read back from the oracle unpauses (never on Quit; Esc is the fallback); the section
         stays while the dimmer fades out, then goes nil.
  fight  hero.tm.inv ~1.0 right after a hit and non-increasing to 0 (unless hit again), recoil ~0.2 then 0; the boss
         is exported hidden (colliders []) while underground; its first Charge Emerge exports the body box (the tk2d hole
         fixed in EntityRegistry.SpritesChanged) and no boss hit lands on an empty-collider frame; collider names include
         "PolyCollider" and "LeapCollider"; "hit" events: every nail hit on the boss is dmg 5, the boss hits add up to
         its HP loss, and the killing blow is reported (dead, hp_after <= 0); room.gates: both gates enabled during the
         fight and "Wall" listed off.
"""
import argparse
import sys
import threading
import time
from collections import Counter, defaultdict

from ssbot.ipc.framing import BUTTONS, mask
from ssbot.ipc.oracle_link import OracleLink
from ssbot.probes.common import tap
from ssbot.train.data_policy import DataPolicy
from ssbot.train.encounters import BELL_BEAST
from ssbot.train.episode import CLEAR, AttemptRecord, EpisodeConfig, FightTap, run_episode, wait_settled

BOSS = BELL_BEAST.boss_type
GATES = ("Threaded Bell Gate", "Threaded Bell Gate (1)")
TM_KEYS = {"inv", "recoil", "recoil_steps", "dash_cd", "atk_cd", "atk_t", "tool_cd", "jump_steps", "jumped_steps", "ds",
           "ds_rec", "grav", "qj", "qa", "qt"}
MENU_KEYS = {"sel", "quit_ok", "dim", "alpha", "ignore_unpause", "quitting"}
UNDERGROUND = ("Submerged", "Emerge Antic C", "Emerge Antic L", "Burst Antic")
INVUL_TIME = 1.0          # HeroController.INVUL_TIME (docs/facts/1.0.30000/hero_constants.json)
RECOIL_DURATION = 0.2


def check(ok: bool, what: str) -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {what}", flush=True)
    return ok


class PressPolicy(DataPolicy):
    """The data policy pinned to its PRESS mode (close in and attack), so the probe's fight ends sooner."""

    def act(self, s: dict, tap_) -> int:
        self.mode, self.mode_left = "PRESS", 1_000_000
        return super().act(s, tap_)


class Collector:
    """Validates the per-frame fields on the reader thread (so no STATE is kept) and keeps small per-frame rows for
    the combat checks while `recording`."""

    def __init__(self, link: OracleLink):
        self.lock = threading.Lock()
        self.recording = False
        self.control: str | None = None
        self.rows: list[dict] = []
        self.hits: list[tuple[int, dict]] = []
        self.damage: list[tuple[int, dict]] = []
        self.n: Counter = Counter()
        self.bad: Counter = Counter()
        self.example: dict[str, tuple[int, str]] = {}
        link.subscribe_state(self._on)

    def _fail(self, name: str, f: int, detail: str) -> None:
        self.bad[name] += 1
        self.example.setdefault(name, (f, detail))

    def _on(self, s: dict) -> None:
        f = s.get("f", -1)
        with self.lock:
            for ev in s.get("ev") or ():
                k, d = ev.get("k"), ev.get("d") or {}
                if k == "fsm" and d.get("fsm") == "Control" and str(d.get("obj", "")).startswith(BOSS):
                    self.control = d.get("to")
                elif k == "hit" and self.recording:
                    self.hits.append((ev.get("f", f), d))
                elif k == "damage" and self.recording:
                    self.damage.append((ev.get("f", f), d))
            self._validate(s, f)
            if self.recording:
                self.rows.append(self._row(s, f))

    def _validate(self, s: dict, f: int) -> None:
        act = s.get("act") or {}
        hf = act.get("hf")
        self.n["act.hf"] += 1
        if not isinstance(hf, dict):
            self._fail("act.hf", f, f"act.hf = {hf!r}")
        else:
            pend, age = hf.get("pending"), hf.get("age")
            if not (isinstance(pend, list) and isinstance(age, list) and len(pend) == len(age) == len(BUTTONS)):
                self._fail("act.hf", f, f"shape pending {pend!r} age {age!r}")
            elif any(not isinstance(x, int) or x < 0 for x in pend + age) or max(age) > 255:
                self._fail("act.hf", f, f"values pending {pend} age {age}")
            elif hf.get("latched") != act.get("mask"):
                self._fail("act.hf", f, f"latched {hf.get('latched')} != act.mask {act.get('mask')}")
            elif not any(pend) and hf.get("latched") != hf.get("desired"):
                self._fail("act.hf", f, f"nothing pending but latched {hf.get('latched')} != desired {hf.get('desired')}")
        hero = s.get("hero")
        if not hero:
            return
        self.n["hero"] += 1
        a = hero.get("alpha")
        if not (isinstance(a, float) and 0.0 <= a < 1.0):
            self._fail("hero.alpha", f, f"alpha {a!r}")
        w = hero.get("wall")
        if not (isinstance(w, list) and len(w) == 2 and all(isinstance(x, bool) for x in w)):
            self._fail("hero.wall", f, f"wall {w!r}")
        elif any(w):
            self.n["wall_touch"] += 1
        tm = hero.get("tm")
        if not (isinstance(tm, dict) and set(tm) == TM_KEYS and all(v is not None for v in tm.values())):
            self._fail("hero.tm", f, f"tm {tm!r}")
        elif tm["inv"] < 0 or tm["recoil"] < 0 or tm["recoil"] > RECOIL_DURATION + 1e-4:
            self._fail("hero.tm", f, f"inv {tm['inv']} recoil {tm['recoil']}")
        tags = hero.get("tags")
        if not isinstance(tags, list) or any(set(t) != {"kind", "dmg_left", "t_left"} for t in tags):
            self._fail("hero.tags", f, f"tags {tags!r}")
        elif tags:
            self.n["tags_active"] += 1
        if "tools" in hero:
            tools, amounts, tmax = hero.get("tools"), hero.get("tool_amounts"), hero.get("tool_max")
            if tmax is None:
                self.n["tool_max_nil"] += 1
            elif len(tmax) != len(tools) or any((t is None) != (m is None) for t, m in zip(tools, tmax)):
                self._fail("hero.tool_max", f, f"tools {tools} tool_max {tmax}")
            elif any(m is not None and a is not None and m > 0 and a > m for a, m in zip(amounts, tmax)):
                self._fail("hero.tool_max", f, f"amounts {amounts} above tool_max {tmax}")

    def _row(self, s: dict, f: int) -> dict:
        hero = s.get("hero") or {}
        tm = hero.get("tm") or {}
        room = s.get("room") or {}
        g = s.get("game") or {}
        row = {"f": f, "ctl": self.control, "paused": g.get("paused"), "inv": tm.get("inv"), "recoil": tm.get("recoil"),
               "gates": room.get("gates"), "menu": s.get("menu"), "boss": None}
        for e in s.get("ents") or ():
            if e.get("type_key") == BOSS:
                cols = e.get("colliders") or []
                row["boss"] = {"hidden": e.get("hidden"), "ncol": len(cols), "hp": e.get("hp"),
                               "kinds": [c.get("kind") for c in cols], "names": [c.get("name") for c in cols]}
                break
        return row


# ---- phases ------------------------------------------------------------------------------------------------------

def load(link: OracleLink, tap_: FightTap) -> dict:
    link.rpc("savestate.load", timeout_s=40, name=BELL_BEAST.savestate, timeout=30)
    tap_.reset()
    return wait_settled(link, BELL_BEAST.scene)


def rest_checks(link: OracleLink, col: Collector) -> bool:
    ok = True
    s = link.wait_state(lambda s: (s.get("room") or {}).get("gates") is not None, timeout_s=10.0)
    gates = {g["name"]: g for g in s["room"]["gates"]}
    print("room.gates at rest:", {k: (v["enabled"], [round(x, 2) for x in v["box"]]) for k, v in gates.items()})
    ok &= check(all(n in gates and not gates[n]["enabled"] for n in GATES),
                "room.gates lists both Threaded Bell Gates, off before the fight")
    g0 = gates.get(GATES[0])
    ok &= check(g0 is not None and abs(g0["box"][2] - 69.21) < 0.05,
                f"left gate box {g0 and [round(x, 2) for x in g0['box']]} (TERRAIN dump: x 67.23-69.21)")
    hero = s["hero"]
    print("hero.tm:", hero.get("tm"))
    print("hero.tools / tool_amounts / tool_max:", hero.get("tools"), hero.get("tool_amounts"), hero.get("tool_max"))
    ok &= check(hero.get("tool_max") is not None, "hero.tool_max present in gameplay")
    return ok


def wait_menu(link: OracleLink, pred, timeout_s: float = 3.0) -> dict:
    return link.wait_state(lambda s: s.get("menu") is not None and pred(s["menu"], s), timeout_s=timeout_s)


def menu_checks(link: OracleLink) -> bool:
    ok = True
    link.wait_state(lambda s: (s.get("pause") or {}).get("blk") == 0 and s["hero"]["hero_accepting_input"], timeout_s=10.0)
    s0 = link.state
    tap(link, "pause")
    s = link.wait_state(lambda s: s["game"]["paused"], timeout_s=3.0)
    print("paused at frame", s["f"], "menu:", s.get("menu"))
    ok &= check(s.get("menu") is not None and set(s["menu"]) == MENU_KEYS, f"menu section present with keys {MENU_KEYS}")
    try:
        s = wait_menu(link, lambda m, s: m["alpha"] >= 0.99 and not m["ignore_unpause"] and not s["game"]["fading"]
                      and m["quit_ok"] is not None, timeout_s=3.0)
    except TimeoutError:
        s = link.state
    m = s.get("menu") or {}
    print("menu up:", m)
    ok &= check(m.get("sel") == "continue", f"sel is 'continue' when the menu opens ({m.get('sel')!r})")
    ok &= check(abs((m.get("dim") or 0) - 0.8) < 0.05, f"dim ~0.8 ({m.get('dim')})")
    ok &= check((m.get("alpha") or 0) >= 0.99 and m.get("ignore_unpause") is False, "menu faded in, ignore_unpause false")
    p = s.get("pause") or s0.get("pause") or {}
    want_quit = not (p.get("dsq") or p.get("preload"))
    ok &= check(m.get("quit_ok") is want_quit, f"quit_ok {m.get('quit_ok')} == not (dsq or preload) ({want_quit})")
    ok &= check(m.get("quitting") is False, "quitting false")

    seen = [m.get("sel")]
    expect = ["options", "quit" if want_quit else "continue"]
    for want in expect:
        before = link.state["menu"]["sel"]
        tap(link, "down")
        try:
            s = wait_menu(link, lambda m, s: m["sel"] != before, timeout_s=2.0)
        except TimeoutError:
            s = link.state
        seen.append((s.get("menu") or {}).get("sel"))
        time.sleep(0.15)
    ok &= check(seen[1:] == expect, f"Down moves sel {seen} (expected {['continue'] + expect})")

    for _ in range(4):
        if (link.state.get("menu") or {}).get("sel") == "continue":
            break
        before = link.state["menu"]["sel"]
        tap(link, "up")
        try:
            wait_menu(link, lambda m, s: m["sel"] != before, timeout_s=2.0)
        except TimeoutError:
            pass
        time.sleep(0.15)
    s = link.wait_state(lambda s: True, newer_than=link.frame)   # a fresh STATE after the last tap
    sel = (s.get("menu") or {}).get("sel")
    ok &= check(sel == "continue", f"Up returns sel to 'continue' ({sel!r})")
    if sel == "continue" and s["game"]["paused"]:
        tap(link, "enter")
        how = "Submit on Continue"
    else:
        tap(link, "pause")                  # Cancel unpauses from any item; never Submit on anything else
        how = "Esc (fallback)"
    try:
        s = link.wait_state(lambda s: not s["game"]["paused"], timeout_s=3.0)
        f_un = s["f"]
    except TimeoutError:
        f_un = None
    ok &= check(f_un is not None, f"{how} unpaused")
    if f_un is not None:
        fade = []
        deadline = time.monotonic() + 2.0
        last = f_un - 1
        while time.monotonic() < deadline:
            s = link.wait_state(lambda s: True, newer_than=last, timeout_s=1.0)
            last = s["f"]
            fade.append(None if s.get("menu") is None else round(s["menu"]["dim"], 3))
            if s.get("menu") is None:
                break
        print("dim after the unpause:", fade[:30])
        ok &= check(len(fade) >= 2 and fade[0] is not None and fade[-1] is None,
                    "the section stays while the dimmer fades out, then goes nil")
    return ok


def fight_checks(col: Collector, rec: AttemptRecord) -> bool:
    ok = True
    rows, hits, damage = col.rows, col.hits, col.damage
    print(f"episode: outcome {rec.outcome} ({rec.reason}), {len(rows)} STATEs, {len(hits)} hit events, "
          f"{len(damage)} hero hits, boss hp end {rec.boss_hp_end}")
    by_f = {r["f"]: r for r in rows}

    # i-frames and recoil after the first hero hit that is followed by 90 frames without another one
    hit_fs = sorted({f for f, _ in damage})
    probe_f = next((f for i, f in enumerate(hit_fs) if i + 1 == len(hit_fs) or hit_fs[i + 1] - f > 90), None)
    if probe_f is None:
        ok &= check(False, "hero.tm.inv after a hit: the hero was never hit")
    else:
        seq = [by_f[f] for f in range(probe_f, probe_f + 90) if f in by_f]
        invs = [r["inv"] for r in seq if r["inv"] is not None]
        peak = max(invs[:10]) if invs else None
        after = invs[invs.index(peak):] if invs else []
        mono = all(b <= a + 1e-6 for a, b in zip(after, after[1:]))
        ok &= check(peak is not None and INVUL_TIME - 0.05 <= peak <= INVUL_TIME + 1e-3 and mono and after[-1] == 0.0,
                    f"hero.tm.inv after the hit at f{probe_f}: peak {peak}, non-increasing {mono}, "
                    f"ends {after[-1] if after else None}")
        rec_s = [r["recoil"] for r in seq if r["recoil"] is not None]
        ok &= check(bool(rec_s) and max(rec_s) > 0.15 and rec_s[-1] == 0.0,
                    f"hero.tm.recoil after the hit: max {max(rec_s) if rec_s else None}, ends {rec_s[-1] if rec_s else None}")

    # hidden while underground
    seen_at = next((r["f"] for r in rows if r["boss"] is not None and not r["boss"]["hidden"]), None)
    under = [r for r in rows if seen_at is not None and r["f"] > seen_at and r["ctl"] in UNDERGROUND and not r["paused"]]
    hidden = [r for r in under if r["boss"] is not None and r["boss"]["hidden"]]
    leaks = [r["f"] for r in rows if r["boss"] is not None and r["boss"]["hidden"] and r["boss"]["ncol"] > 0]
    ok &= check(len(under) > 0 and len(hidden) >= 0.8 * len(under) and not leaks,
                f"boss exported hidden underground: {len(hidden)}/{len(under)} frames, hidden with colliders {leaks[:5]}")

    # first Charge Emerge
    ce = []
    for r in rows:
        if r["ctl"] == "Charge Emerge":
            ce.append(r)
        elif ce:
            break
    empty = [r["f"] for r in ce if r["boss"] is None or r["boss"]["ncol"] == 0]
    has_box = any(r["boss"] and "box" in r["boss"]["kinds"] for r in ce)
    first_box = next((i for i, r in enumerate(ce) if r["boss"] and "box" in r["boss"]["kinds"]), None)
    gap = [r["f"] for r in ce[first_box:] if not (r["boss"] and "box" in r["boss"]["kinds"])] if first_box is not None else []
    empty_fs = set(empty)
    bad_hits = [f for f, d in damage if BOSS in str(d.get("source")) and (f in empty_fs or f - 1 in empty_fs)]
    ok &= check(bool(ce) and has_box and not gap and len(empty) <= 6 and not bad_hits,
                f"first Charge Emerge ({len(ce)} frames): body box from frame index {first_box} on, "
                f"{len(empty)} empty frames {empty[:6]}, boss hits on empty frames {bad_hits}")

    names = Counter(n for r in rows if r["boss"] for n in r["boss"]["names"])
    print("boss collider names:", dict(names))
    ok &= check({"PolyCollider", "LeapCollider", BOSS} <= set(names) and all(isinstance(n, str) and n for n in names),
                "collider names include PolyCollider, LeapCollider and the root's own name")

    # hit events
    boss_hits = [d for _, d in hits if d.get("type_key") == BOSS]
    nail = [d for d in boss_hits if d.get("attack") == "Nail"]
    dmg = Counter(d.get("dmg") for d in nail)
    print("hit events on the boss:", len(boss_hits), "nail dmg:", dict(dmg),
          "attacks:", dict(Counter(d.get("attack") for d in boss_hits)), "src:", dict(Counter(d.get("src") for d in boss_hits)))
    ok &= check(bool(nail) and set(dmg) == {5}, f"every nail hit on the boss is dmg 5 ({dict(dmg)})")
    ok &= check(all(d["dmg"] == d["hp_before"] - d["hp_after"] for _, d in hits), "dmg == hp_before - hp_after")
    hps = [r["boss"]["hp"] for r in rows if r["boss"] and r["boss"]["hp"] is not None]
    if boss_hits and hps:
        first_hp = boss_hits[0]["hp_before"]
        last_hp = boss_hits[-1]["hp_after"]
        ok &= check(sum(d["dmg"] for d in boss_hits) == first_hp - last_hp,
                    f"boss hits add up to its HP loss ({sum(d['dmg'] for d in boss_hits)} vs {first_hp} -> {last_hp})")
    kill = [d for d in boss_hits if d.get("dead")]
    if rec.outcome == CLEAR:
        ok &= check(len(kill) == 1 and kill[0]["hp_after"] <= 0, f"the killing blow is reported ({kill})")
    else:
        ok &= check(False, f"killing blow: the episode did not end in CLEAR ({rec.outcome})")

    # gates during the fight
    fight = [r for r in rows if r["ctl"] not in (None, "Init", "Dormant", "Submerged Init") and r["gates"] is not None]
    closed = [r for r in fight if all(any(g["name"] == n and g["enabled"] for g in r["gates"]) for n in GATES)]
    wall_off = [r for r in fight if any(g["name"] == "Wall" and not g["enabled"] for g in r["gates"])]
    ok &= check(bool(fight) and len(closed) >= 0.95 * len(fight),
                f"room.gates: both gates enabled in {len(closed)}/{len(fight)} fight frames")
    ok &= check(bool(fight) and len(wall_off) >= 0.9 * len(fight), f"room.gates: 'Wall' listed off in {len(wall_off)}/{len(fight)}")
    return ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--timebox", type=float, default=300.0, help="STUCK after this many seconds from the wake")
    ap.add_argument("--skip-menu", action="store_true")
    ap.add_argument("--skip-fight", action="store_true")
    a = ap.parse_args(argv)
    link = OracleLink(instance=a.instance, connect_timeout_s=120)
    ftap = FightTap(link, BELL_BEAST)
    col = Collector(link)
    ok = True
    try:
        load(link, ftap)
        ok &= rest_checks(link, col)
        if not a.skip_menu:
            ok &= menu_checks(link)
        if not a.skip_fight:
            rec = AttemptRecord(unit=BELL_BEAST.name, stage="probe", profile="TRAIN", build="1.0.30000", code_rev=None,
                                config_fp="m2_exports", start_kind="savestate", mode="data", seed=a.seed)
            with col.lock:
                col.recording = True
            rec = run_episode(link, BELL_BEAST, ftap, PressPolicy(),
                              EpisodeConfig(mode="data", seed=a.seed, timebox_s=a.timebox), rec)
            with col.lock:
                col.recording = False
            ok &= fight_checks(col, rec)
        for name in ("act.hf", "hero.alpha", "hero.wall", "hero.tm", "hero.tags", "hero.tool_max"):
            n = col.n["act.hf" if name == "act.hf" else "hero"]
            ok &= check(n > 0 and col.bad[name] == 0,
                        f"{name}: {n - col.bad[name]}/{n} STATEs valid {col.example.get(name, '')}")
        print(f"frames touching a wall: {col.n['wall_touch']}, with an active damage tag: {col.n['tags_active']}, "
              f"tool_max nil: {col.n['tool_max_nil']}")
        print("ents.stats:", link.rpc("ents.stats"))
    finally:
        try:
            link.rpc("input.release", timeout_s=10)
        except Exception:   # noqa: BLE001 - best effort on the way out
            pass
        link.close()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
