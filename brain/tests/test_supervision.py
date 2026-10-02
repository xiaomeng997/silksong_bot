"""Training glue (ssbot.train.supervision) on the trial Bell Beast fixture (tests/data/bellbeast_states.msgpack.zst,
run 20261001_121446 i0_000, episode seed 1): per STATE the supervisor decides, and once a pause is pending the pause
machine's keys replace the policy; against a stand-in game that pauses on the pressed key, the attempt ends as an
emulated quit. Also the Q1 pause-window monitor (ssbot.safety.pause_window) on the fixture's hits."""
import copy

from ssbot.ipc.framing import BIT
from ssbot.safety import game_codes as gc
from ssbot.safety import pause_quit as pq
from ssbot.safety.pause_window import PauseWindowMonitor
from ssbot.safety.supervisor import SupervisorConfig
from ssbot.train.supervision import SupervisedControl, entity_support
from tests import worldstate_fixture as wf

PAUSE = 1 << BIT["pause"]
BB = SupervisorConfig(worst_known_damage=2)          # Bell Beast: every attack is 2 masks


def _control(**kw) -> SupervisedControl:
    return SupervisedControl(support=lambda s: entity_support(s, worst_damage=2), cfg=BB, **kw)


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
    events, known = entity_support(s, worst_damage=2)
    assert not known
    body = [e for e in events if e.source == "Bone Beast"]
    assert len(body) == 1 and body[0].instance == wf.BOSS_IID and body[0].damage == 2 and not body[0].hazard
    assert len({e.instance for e in events}) == len(events)
    # a hidden root (oracle ents[].hidden: the Bell Beast underground) is a threat with no colliders
    h = {"ents": [{"iid": 7, "type_key": "Bone Beast", "hidden": True, "colliders": []},
                  {"iid": 8, "type_key": "Pickup", "colliders": []},
                  {"iid": 9, "type_key": "Spikes", "colliders": [
                      {"enabled": True,
                       "damage": {"dealt": 1, "eff": 1, "hazard_type": 2, "can_cause_damage": True}}]}]}
    ev, _ = entity_support(h, worst_damage=2)
    assert [(e.instance, e.damage, e.hazard) for e in ev] == [(7, 2, False), (9, 2, True)]
    # a certified callable result is taken as known
    sc = SupervisedControl(support=lambda s: (), cfg=BB)
    assert sc.step(wf.window(0)[0]).decision.support_known


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
