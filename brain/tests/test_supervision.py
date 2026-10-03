"""Training glue (ssbot.train.supervision) on the trial Bell Beast fixture (tests/data/bellbeast_states.msgpack.zst,
run 20261001_121446 i0_000, episode seed 1): per STATE the supervisor decides, and once a pause is pending the pause
machine's keys replace the policy; against a stand-in game that pauses on the pressed key, the attempt ends as an
emulated quit. Also the Q1 pause-window monitor (ssbot.safety.pause_window) on the fixture's hits."""
import copy

from ssbot.ipc.framing import BIT
from ssbot.safety import game_codes as gc
from ssbot.safety import pause_quit as pq
from ssbot.safety.hits_to_death import SupportEvent, SupportSet
from ssbot.safety.pause_window import PauseWindowMonitor
from ssbot.safety.supervisor import SupervisorConfig
from ssbot.train.supervision import SupervisedControl, entity_support, next_hit_may_kill
from tests import worldstate_fixture as wf

PAUSE = 1 << BIT["pause"]
BB = SupervisorConfig(worst_known_damage=2)          # Bell Beast: every attack is 2 masks


def _control(**kw) -> SupervisedControl:
    kw.setdefault("support", lambda s: entity_support(s, worst_damage=2))
    return SupervisedControl(BB, **kw)


def test_q1_at_two_hp_hands_the_keys_to_the_pause_loop():
    """randomize_start sets 2 HP at frame 56533 (5 before): h 3 -> 1, Q1, and from that STATE on the pause loop's
    keys (Pause only, pressed >= 34 ms / released >= 34 ms) replace the policy. The recording never pauses, so the
    loop keeps pressing and alerts after loop_alert_s."""
    sc = _control()
    out = [(s["f"], sc.step(s)) for s in wf.window(0)]
    before = [r for f, r in out if f < 56533]
    assert before and all(r.mask is None and r.decision.h == 3 and not r.decision.triggers for _, r in out[:13])
    assert all(r.decision.tier == "YELLOW" for r in before)      # stand-in support is unknown: never GREEN
    f0, r0 = next((f, r) for f, r in out if r.mask is not None)
    assert f0 == 56533 and "Q1" in r0.decision.triggers and r0.decision.pause_pending and r0.mask == PAUSE
    assert sc.first_pending_f == 56533
    after = [r for f, r in out if f >= 56533]
    assert all(r.mask in (0, PAUSE) and r.outcome is None for r in after)
    edges = sum(1 for a, b in zip(after, after[1:]) if b.mask == PAUSE and a.mask == 0)
    assert 50 <= edges <= 62                                      # one press every 6 frames over 367 frames
    assert all(not r.decision.allows("ATTACK(side)") and r.decision.allows("DASH") for r in after)
    assert sc.pq.alert and any(k == "loop_alert" for _, k, _ in sc.pq.log)


def _paused(s: dict, age: int) -> dict:
    """The fixture STATE as the paused game would export it, `age` frames after the pause (human session
    20260930_210337: the menu accepts input 8 frames in, PauseAllowed returns 19 frames in)."""
    p = copy.deepcopy(s)
    p["ev"] = []
    p["ts"] = 0.0
    p["game"].update(gs=gc.GS_PAUSED, ui=gc.UI_PAUSED, menu=gc.MENU_PAUSE_MENU if age >= 8 else 6, fading=age < 8,
                     paused=True)
    p["pause"]["blk"] = 100 if age < 8 else 68 if age < 19 else 64
    return p


def test_emulated_quit_against_a_game_that_pauses():
    """Stand-in game: an ACTION applies 2 frames after the STATE it answers; a Pause press while pause.blk == 0
    pauses. The supervisor's Q1 ends the attempt as QUIT_EMULATED (Quit available: no dsq, no preload)."""
    sc = _control()
    states = wf.window(0)
    sent: dict[int, int] = {}
    paused_at, res, prev = None, None, 0
    for i, s in enumerate(states):
        f = s["f"]
        if paused_at is None and sent.get(f, 0) & PAUSE and not sent.get(f - 1, 0) & PAUSE and s["pause"]["blk"] == 0:
            paused_at = i
        st = s if paused_at is None else _paused(states[paused_at], i - paused_at) | {"f": f, "q": s["q"]}
        res = sc.step(st)
        sent[f + 2] = res.mask or 0
        prev = res.mask
        if res.outcome in pq.TERMINAL:
            break
    assert paused_at is not None and states[paused_at]["f"] <= 56533 + 2 + 6
    assert res.outcome == pq.QUIT_EMULATED and sc.pq.quit_state_seen == pq.QUIT_AVAILABLE and prev == 0
    assert res.decision.paused or sc.sup.paused


def test_focus_counts_only_with_a_foreground_sink():
    s = copy.deepcopy(wf.window(0)[0])
    s["focus"] = False
    assert "Q7" not in _control().step(s).decision.triggers
    r = _control(foreground_sink=True).step(s)
    assert "Q7" in r.decision.triggers and r.decision.pause_pending and r.mask == PAUSE


def test_entity_support_keys_instances_on_iid():
    s = next(x for x in wf.window(0) if x["f"] == 56777)
    ss = entity_support(s, worst_damage=2)
    events = ss.events
    assert not ss.known and not ss.certified
    body = [e for e in events if e.source == "Bone Beast"]
    assert len(body) == 1 and body[0].instance == wf.BOSS_IID and body[0].damage == 2 and not body[0].hazard
    assert len({e.instance for e in events}) == len(events)
    # a hidden root (oracle ents[].hidden: the Bell Beast underground) is a threat with no colliders
    h = {"ents": [{"iid": 7, "type_key": "Bone Beast", "hidden": True, "colliders": []},
                  {"iid": 8, "type_key": "Pickup", "colliders": []},
                  {"iid": 9, "type_key": "Spikes", "colliders": [
                      {"enabled": True,
                       "damage": {"dealt": 1, "eff": 1, "hazard_type": 2, "can_cause_damage": True}}]}]}
    ev = entity_support(h, worst_damage=2).events
    assert [(e.instance, e.damage, e.hazard) for e in ev] == [(7, 2, False), (9, 2, True)]
    assert not entity_support({"ents": []}, worst_damage=2, known=True).certified    # never certified empty


def test_support_is_certified_only_explicitly():
    """Review: a bare sequence (a forecaster dropout returning [], a callable not wired yet) was certified by its type
    and read as UNBOUNDED / GREEN. Only SupportSet / (events, True) certify, and an empty one needs certified_empty."""
    s0 = wf.window(0)[0]
    body = SupportEvent("Bone Beast", 2, instance=wf.BOSS_IID)
    for fn, known in ((lambda s: [], False), (lambda s: (), False), (lambda s: None, False),
                      (lambda s: [body], False), (lambda s: ((), True), False), (lambda s: SupportSet((), True), False),
                      (lambda s: ((body,), True), True), (lambda s: SupportSet((body,), True), True),
                      (lambda s: SupportSet((), True, certified_empty=True), True)):
        assert _control(support=fn).step(s0).decision.support_known is known, fn
    # the review's case: support=lambda s: [] on the fixture; the random start drops the hero to 2 HP at 56533
    sc = _control(support=lambda s: [])
    first = next((s["f"], r) for s in wf.window(0) if (r := sc.step(s)).mask is not None)
    assert first[0] == 56533 and "Q1" in first[1].decision.triggers and first[1].decision.h == 1


def test_pause_window_monitor_on_the_fixture_hits():
    """Hits at 56777 (body) and 61617: the pause gate reopens 0.216-0.249 s after the hit and the i-frames end
    1.18-1.20 s after it, a Q1 window of about 0.95 s (probe P7: 250 ms to about 1.2 s)."""
    rows = []
    for i in (0, 1):
        mon = PauseWindowMonitor()
        for s in wf.window(i):
            mon.update(s)
        rows += [w.row() for w in mon.windows]
        assert not mon.alerts
    assert [r["f_hit"] for r in rows] == [56777, 61617]
    for r in rows:
        assert 0.2 <= r["open_s"] <= 0.25 and 1.17 <= r["iframes_end_s"] <= 1.21 and 0.9 <= r["window_s"] <= 1.0


def test_pause_window_monitor_alerts_on_a_short_window():
    """hero.tm.inv (cross-module decision 5) at the gate opening gives the window's end early: a parry-length 0.15 s
    of i-frames left alerts before the window closes; a pause landing closes it."""
    def st(f, blk, inv, ev=(), paused=False):
        return {"f": f, "q": f * 166_667, "ev": list(ev), "pause": {"blk": blk}, "game": {"paused": paused},
                "hero": {"invulnerable": inv > 0, "tm": {"inv": inv}}}
    mon = PauseWindowMonitor(detect_s=0.05, loop_s=0.10)
    mon.update(st(0, 3, 1.2, [{"k": "damage", "d": {"source": "x"}}]))
    for f in range(1, 15):
        mon.update(st(f, 3, 1.0))
    mon.update(st(15, 0, 0.12))
    assert mon.alerts and "frame 0" in mon.alerts[0]
    mon.update(st(16, 0, 0.10, paused=True))
    assert mon.windows and mon.windows[0].t_pause is not None and mon.open is None
    # a lethal hit LethalBlock swallowed (data mode, trial f45992): the gate never closes, no i-frames: no window
    mon = PauseWindowMonitor()
    mon.update(st(0, 0, 0.0, [{"k": "damage", "d": {"source": "x"}}]))
    mon.update(st(1, 0, 0.0))
    assert mon.windows[0].no_effect and mon.windows[0].window_s == 0.0 and not mon.alerts


def test_next_hit_may_kill_from_state():
    """YELLOW's no-killing-blow rule (§3.7.3) needs next_hit_may_kill: a threat root with 0 < hp <= the hero's largest
    hit (floor 5, Bell Beast's measured nail hit; raised by STATE "hit" events)."""
    boss = {"iid": 1, "type_key": "Bone Beast", "hp": 5, "is_dead": False, "colliders": [
        {"enabled": True, "damage": {"dealt": 2, "eff": 2, "hazard_type": 1, "can_cause_damage": True}}]}
    s = {"ents": [boss]}
    assert next_hit_may_kill(s, 5) and not next_hit_may_kill(s, 4)
    assert not next_hit_may_kill({"ents": [{**boss, "hp": 0}]}, 5)
    assert not next_hit_may_kill({"ents": [{**boss, "is_dead": True}]}, 5)
    assert not next_hit_may_kill({"ents": [{"iid": 2, "type_key": "Pot", "hp": 1, "colliders": []}]}, 5)  # no threat
    assert next_hit_may_kill({"ents": [{"iid": 3, "type_key": "Bone Beast", "hp": 3, "hidden": True}]}, 5)
    # through the glue: 5 HP and unknown support is YELLOW (h 3) with no trigger; the boss in reach of a kill
    # removes every damaging primitive, an explicit planner value wins, and a "hit" event raises the reach
    st = {"f": 1, "q": 166_667, "pause": {"blk": 0}, "ev": [], "ents": [boss],
          "hero": {"health": 5, "max_health": 5, "health_blue": 0,
                   "fractured_mask": {"equipped": False, "amount_left": 0}}}
    d = _control().step(st).decision
    assert d.tier == "YELLOW" and not d.triggers and not d.allows("ATTACK(side)") and d.allows("DASH")
    assert _control().step(st, next_hit_may_kill=False).decision.allows("ATTACK(side)")
    st["ents"] = [{**boss, "hp": 8}]
    sc = _control()
    assert sc.step(st).decision.allows("ATTACK(side)")
    st["ev"] = [{"k": "hit", "d": {"ent": 1, "dmg": 8}}]
    assert not sc.step(st).decision.allows("ATTACK(side)") and sc.hero_hit == 8


def _playing(f: int) -> dict:
    return {"f": f, "q": f * 166_667, "ts": 1.0, "ev": [], "ents": [],
            "game": {"gs": gc.GS_PLAYING, "ui": 4, "menu": 6, "fading": False, "paused": False, "pd_mode": 0,
                     "scene": "Bone_05"},
            "pause": {"blk": 0, "dsq": False, "preload": False},
            "hero": {"health": 5, "max_health": 5, "health_blue": 0,
                     "fractured_mask": {"equipped": False, "amount_left": 0}}}


def test_held_pause_resumes_and_the_next_pending_starts_a_new_loop():
    """Review: without always_quit a goal-PAUSE pause held forever (no API) and the machine was never replaced, so a
    later PAUSE_PENDING never pressed. Stand-in game: an ACTION applies 2 frames after its STATE; a Pause edge while
    playing pauses; an Enter edge on the ready pause menu with Continue highlighted, after the lockout, unpauses."""
    enter = 1 << BIT["enter"]
    sc = _control(always_quit=False)
    sent: dict[int, int] = {}
    paused_at, resumed, outcomes, first_pq = None, False, [], None
    for f in range(400):
        m, prev = sent.get(f, 0), sent.get(f - 1, 0)
        if paused_at is None and m & PAUSE and not prev & PAUSE:
            paused_at = f
        elif paused_at is not None and m & enter and not prev & enter and f - paused_at >= 19:
            paused_at = None
        if paused_at is None:
            st = _playing(f)
        else:
            st = _paused(_playing(paused_at), f - paused_at) | {"f": f, "q": f * 166_667}
            st["menu"] = {"sel": "continue", "quit_ok": True}
        kw = {"frame_age_ms": 60.0} if f in (5, 300) else {}
        r = sc.step(st, **kw)
        sent[f + 2] = r.mask or 0
        outcomes.append(r.outcome)
        if f == 5:
            first_pq = sc.pq
            assert r.decision.pause_pending and not r.decision.quit_requested and first_pq.goal == pq.GOAL_PAUSE
        if sc.held and not resumed:
            assert r.outcome == pq.PAUSED and sc.sup.paused and r.mask == 0
            assert sc.resume()
            resumed = True
        if f == 299:
            assert pq.UNPAUSED in outcomes and sc.pq is None and not sc.sup.paused and not r.decision.pause_pending
        if f == 300:
            assert sc.pq is not None and sc.pq is not first_pq and sc.pq.state == "LOOP" and r.mask == PAUSE
    assert resumed and sc.held and sc.pq is not first_pq     # the second pause is held too: quit() now
    assert sc.quit() and sc.pq.goal == pq.GOAL_QUIT


def test_alerts_reach_the_harness():
    """Review: the pause-window monitor's alerts were not returned. A parry-length i-frame window alerts at the gate
    opening, through Supervised.alerts."""
    sc = _control()
    hero = {"health": 5, "max_health": 5, "health_blue": 0, "invulnerable": True,
            "fractured_mask": {"equipped": False, "amount_left": 0}}

    def st(f, blk, inv, ev=()):
        return {"f": f, "q": f * 166_667, "ev": list(ev), "pause": {"blk": blk}, "ents": [],
                "game": {"paused": False, "scene": "Bone_05"}, "hero": {**hero, "tm": {"inv": inv}}}
    r = sc.step(st(0, 3, 1.2, [{"k": "damage", "d": {"source": "x", "amount": 1}}]))
    assert not r.alerts
    for f in range(1, 15):
        sc.step(st(f, 3, 1.0))
    r = sc.step(st(15, 0, 0.12))
    assert any(a.startswith("pause window: Q1 pause window after the hit at frame 0") for a in r.alerts), r.alerts


def test_pause_window_accounts_for_every_hit():
    """Round-2 review: 29 hits never reached the gate opening and were never checked. A hit superseded by another
    while the gate is shut, a "damage" event that never closed the gate, a hit whose i-frames end with the gate still
    shut (window 0: alert) and a window still open at the end of the attempt (censored)."""
    def st(f, blk, inv, ev=()):
        return {"f": f, "q": f * 166_667, "ev": list(ev), "pause": {"blk": blk}, "game": {"paused": False},
                "hero": {"invulnerable": inv > 0, "tm": {"inv": inv}}}
    hit = [{"k": "damage", "d": {"source": "x"}}]
    mon = PauseWindowMonitor()
    mon.update(st(0, 3, 1.2, hit))
    mon.update(st(1, 3, 1.1))
    mon.update(st(2, 3, 1.2, hit))              # a second hit with the gate shut: the first is superseded
    assert mon.windows[0].superseded and not mon.windows[0].no_effect and not mon.alerts
    mon = PauseWindowMonitor()
    mon.update(st(0, 0, 0.0, hit))
    mon.update(st(1, 0, 0.0, hit))              # the first never closed the gate: it did not land
    assert mon.windows[0].no_effect and not mon.alerts
    mon = PauseWindowMonitor()
    mon.update(st(0, 2, 1.0, hit))              # TIME_SLOWED for the whole i-frames, still PLAYING: no window
    for f in range(1, 70):
        mon.update(st(f, 2, max(0.0, 1.0 - f / 60)))
    w = mon.windows[0]
    assert w.t_open is None and w.window_s == 0.0 and mon.alerts and "frame 0" in mon.alerts[0]
    mon = PauseWindowMonitor()                  # live i0_000 f206760: the episode reload ends it with the gate shut
    mon.update(st(0, 3, 1.0, hit))
    mon.update(st(1, 2, 0.9))
    mon.update(st(2, 66, 0.9))
    assert mon.windows[0].censored and not mon.alerts
    mon = PauseWindowMonitor()
    mon.update(st(0, 3, 1.2, hit))
    assert mon.finish().censored and not mon.alerts and mon.open is None


def test_injected_fault_pauses_and_the_first_press_waits_for_the_planner_keys():
    """The pause stress test's trigger fault (inject_fault -> QF): PAUSE_PENDING with a quit goal on the next step,
    at full health. The menu key guard: with a planner key pressed in flight (the ACTION for f + 1) the first step
    sends no Pause; once the key path shows it released in time, the press goes out (safety.key_guard)."""
    right = 1 << BIT["right"]
    sc = _control()
    states = wf.window(0)[:12]
    for s in states:
        s["act"] = {"target": s["f"], "hf": {"latched": right, "desired": right, "pending": [0] * 22,
                                              "age": [9] * 22}}
    r = sc.step(states[0])
    assert r.mask is None and not r.decision.pause_pending
    sc.inject_fault("QF", "test")
    r = sc.step(states[1], inflight=[right | (1 << BIT["jump"])])  # jump pressed on f + 1: held to f + 3
    assert r.decision.pause_pending and r.decision.quit_requested and "QF" in r.decision.triggers
    assert r.mask == 0 and sc.pq.key_waits == 1
    s = states[2]
    s["act"]["hf"].update(latched=right | (1 << BIT["jump"]), desired=right | (1 << BIT["jump"]),
                          age=[9] * 22)                            # by now held long enough to release with the press
    r = sc.step(s, inflight=[0])
    assert r.mask == PAUSE and sc.pq.presses == 1


def _paused_vision(s: dict, age: int) -> dict:
    """_paused with the menu section the oracle exports while paused (dim and canvas alpha rising 0.083 a frame from
    the pause frame: live run 20261003_022259 i0 ep9)."""
    p = _paused(s, age)
    a = min(1.0, 0.0833 * (age + 1))
    p["menu"] = {"sel": "continue", "quit_ok": True, "dim": min(0.8, a), "alpha": a, "ignore_unpause": age < 9,
                 "quitting": False}
    return p


def test_vision_mode_decides_on_the_delayed_view_and_pauses_on_vision_cues():
    """vision=True (stage C, task V review): the supervisor reads the delayed WorldState (HUD health), not the current
    STATE, so the Q1 at the 2-HP frame 56533 fires k frames later; the pause machine gets the vision cues of the
    delayed STATE (no paused flag, no gate) and against the stand-in game the attempt still ends as an emulated quit."""
    from ssbot.backends.degraded import DegradedOracleBackend
    from ssbot.backends.observability import ObservabilityFilter
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.core.bosses import BELL_BEAST
    deg = DegradedOracleBackend(OracleBackend(bosses=[BELL_BEAST], clock=None),
                                ObservabilityFilter(bosses=[BELL_BEAST]))
    k = deg.reset(5)
    sc = _control(vision=True)
    states = wf.window(0)
    raw: dict[int, dict] = {}
    sent: dict[int, int] = {}
    paused_at, res, pending_f = None, None, None
    for i, s in enumerate(states):
        f = s["f"]
        if paused_at is None and sent.get(f, 0) & PAUSE and not sent.get(f - 1, 0) & PAUSE and s["pause"]["blk"] == 0:
            paused_at = i
        st = s if paused_at is None else _paused_vision(states[paused_at], i - paused_at) | {"f": f, "q": s["q"]}
        raw[f] = st
        ws = deg.feed(st)
        if ws is None:
            continue
        res = sc.step(st, obs=raw[ws.stamp.frame], ws=ws)
        if res.decision.pause_pending and pending_f is None:
            pending_f = f
        sent[f + 2] = res.mask or 0
        if res.outcome in pq.TERMINAL:
            break
    assert pending_f == 56533 + k and sc.first_pending_f == 56533 + k
    assert paused_at is not None and res.outcome == pq.QUIT_EMULATED and sc.pq.quit_state_seen == pq.QUIT_AVAILABLE
    assert not any(x[1] == "cue" and "paused=True" in x[2] for x in sc.pq.log)     # never the oracle's flag


def test_vision_next_hit_may_kill_from_the_counted_hp():
    """Vision: the view's counted HP (hp_est) less 3 sigma against the largest priced hit (15), not ents[].hp."""
    from ssbot.core.worldstate import E, Entity, Kind, WorldState
    from ssbot.train.supervision import VISION_HERO_HIT, next_hit_may_kill_world
    ws = WorldState()
    ws.entities = [Entity(id=1, kind=Kind.BOSS, hp_est=E(17.0, sigma=1.0, conf=0.8))]
    assert VISION_HERO_HIT == 15 and next_hit_may_kill_world(ws, 15) and not next_hit_may_kill_world(ws, 15, z=0.0)
    ws.entities = [Entity(id=1, kind=Kind.BOSS, hp_est=E(40.0, sigma=1.0, conf=0.8))]
    assert not next_hit_may_kill_world(ws, 15)
    ws.entities = [Entity(id=1, kind=Kind.BOSS, hp_est=E(0.0, conf=0.9))]          # counted dead
    assert not next_hit_may_kill_world(ws, 15)
