"""Menu key guard (ssbot.safety.key_guard) and its use by the pause loop: the scalar filter is the oracle HoldFilter
frame for frame (against ssbot.knowledge.kinematics.hold_filter, itself checked against the C# by
oracle/tests/InputLogicCheck), keys_clear reads in-flight ACTIONs right, and in a simulated key path (planner keys
until PAUSE_PENDING, then the pause machine's keys, ACTIONs applied 2 frames after the STATE they answer, sometimes a
frame late) no game key is ever latched on the pause frame or after it, while without the guard some are (the leak
pause_stress found in 9 of 37 gate / live QUITs, 20261002_123347 ... 152649)."""
import random

import numpy as np

from ssbot.ipc.framing import BIT
from ssbot.knowledge.kinematics import HoldState, hold_filter
from ssbot.safety import key_guard as kg
from ssbot.safety.pause_quit import PauseCues, PauseQuit, PauseQuitConfig

PAUSE = 1 << BIT["pause"]
LEFT, RIGHT, JUMP, ATTACK, DOWN = (1 << BIT[k] for k in ("left", "right", "jump", "attack", "down"))
GAME_KEYS = (LEFT, RIGHT, JUMP, ATTACK, DOWN, 1 << BIT["dash"], 1 << BIT["quickcast"])


def _random_masks(rng: random.Random, n: int) -> list[int]:
    out, m = [], 0
    for _ in range(n):
        if rng.random() < 0.35:
            m = 0
            for k in GAME_KEYS:
                if rng.random() < 0.3:
                    m |= k
            if m & LEFT and m & RIGHT:
                m &= ~(LEFT if rng.random() < 0.5 else RIGHT)
        out.append(m)
    return out


def _hf(f: kg.Filter) -> dict:
    return {"latched": f.latched, "desired": f.desired, "pending": list(f.pending), "age": [min(a, 255) for a in f.age]}


def test_filter_matches_the_kinematics_hold_filter():
    rng = random.Random(3)
    for trial in range(40):
        masks = _random_masks(rng, 300)
        ref, _ = hold_filter(np.array(masks, np.int64), HoldState.idle(1))
        f = kg.Filter()
        got = [f.step(m) for m in masks]
        assert got == [int(x) for x in ref], trial
        # restarting from the exported state (ages capped at 255 as STATE act.hf has them) changes nothing
        g = kg.Filter()
        for m in masks[:150]:
            g.step(m)
        h = kg.Filter.from_hf(_hf(g))
        assert [h.step(m) for m in masks[150:]] == got[150:]


def test_keys_clear_reads_the_in_flight_actions():
    idle = _hf(kg.Filter())
    assert kg.keys_clear(None, [], PAUSE) is None
    assert kg.keys_clear(idle, [0], PAUSE) is True
    assert kg.keys_clear(idle, [RIGHT], PAUSE) is False           # pressed on f + 1: held to f + 3 (2-frame press)
    held = kg.Filter()
    for m in (RIGHT,) * 5:
        held.step(m)
    assert kg.keys_clear(_hf(held), [RIGHT], PAUSE) is True       # long held: released on the press's own frame
    tap = kg.Filter()
    for m in (RIGHT, RIGHT, 0, RIGHT):                            # a re-press the filter defers (2-frame release)
        tap.step(m)
    assert tap.queued(RIGHT) and kg.keys_clear(_hf(tap), [0], PAUSE) is False
    fresh = kg.Filter()
    fresh.step(JUMP)                                              # jump pressed on the observed frame (age 1)
    assert kg.keys_clear(_hf(fresh), [0], PAUSE) is True          # released on f + 2, the press's frame
    assert kg.keys_clear(_hf(fresh), [JUMP], PAUSE) is True
    assert kg.keys_clear(_hf(fresh), [0, JUMP], PAUSE) is False   # pressed again in flight


def test_pause_loop_waits_for_clear_keys_then_presses():
    pq = PauseQuit(PauseQuitConfig(keys_wait_s=0.25))
    pq.start(0.0)
    t = 0.0
    keys = pq.step(PauseCues(t=t, paused=False, gate_open=True, keys_clear=False), t)
    assert keys == frozenset() and pq.presses == 0 and pq.key_waits == 1
    t += 1 / 60
    keys = pq.step(PauseCues(t=t, paused=False, gate_open=True, keys_clear=True), t)
    assert keys == {"pause"} and pq.presses == 1 and pq.key_waits_expired == 0
    pq = PauseQuit(PauseQuitConfig(keys_wait_s=0.1))               # never clear: goes after keys_wait_s, logged
    pq.start(0.0)
    for i in range(10):
        keys = pq.step(PauseCues(t=i / 60, paused=False, gate_open=True, keys_clear=False), i / 60)
        if keys:
            break
    assert keys == {"pause"} and pq.key_waits_expired == 1 and 6 <= i <= 7
    assert any(k == "keys_not_clear" for _, k, _ in pq.log)


def _simulate(seed: int, guard: bool, overdue: bool = True) -> tuple[int, int, int]:
    """One trial: planner keys until PAUSE_PENDING at frame T, then the pause machine; the ACTION answering STATE f
    applies at f + 2 (a late one at f + 3, its edges queued with the next one's); the game pauses on the first frame
    Pause is latched with the gate open. Returns (frames on and after the pause with a game key latched, pause
    frame - T, presses). overdue False: the in-flight list without the ACTIONs that missed their frame."""
    rng = random.Random(seed)
    T = rng.randint(10, 40)
    plan = _random_masks(rng, T + 2)
    filt = kg.Filter()
    sent: dict[int, int] = {}
    late: set[int] = {f for f in range(T + 60) if rng.random() < 0.1}
    pq = PauseQuit(PauseQuitConfig(keys_wait_s=0.25))
    paused_at, bad, target = None, 0, -1
    for f in range(T + 60):
        # the frame: the ACTIONs due now (the one for f unless it is late, plus a late one from f - 1)
        due = [g for g in (f - 1, f) if g in sent and ((g == f and g not in late) or (g == f - 1 and g in late))]
        for g in due[:-1]:
            filt.push(sent[g])
        out = filt.step(sent[due[-1]] if due else filt.desired)
        target = max([target] + due)                      # STATE act.target: the last ACTION applied
        if paused_at is None and out & PAUSE and f > T:
            paused_at = f
        if paused_at is not None and out & ~PAUSE:
            bad += 1
        if paused_at is not None and f > paused_at + 8:
            break
        # the brain answers STATE f (act.hf = the filter now) with the mask for f + 2
        if f < T:
            sent[f + 2] = plan[f]
            continue
        if f == T:
            pq.start(f / 60)
        hf = _hf(filt)
        inflight = [sent[g] for g in range(target + 1, f + 2) if g in sent] if overdue else [sent.get(f + 1, 0)]
        clear = kg.keys_clear(hf, inflight, PAUSE) if guard else None
        keys = pq.step(PauseCues(t=f / 60, paused=paused_at is not None, gate_open=True, keys_clear=clear), f / 60)
        sent[f + 2] = PAUSE if "pause" in keys else 0
    return bad, (paused_at or 0) - T, pq.presses


def test_no_game_key_reaches_the_pause_menu_with_the_guard():
    n = 2000
    with_guard = [_simulate(i, True) for i in range(n)]
    without = [_simulate(i, False) for i in range(n)]
    assert sum(b for b, _, _ in with_guard) == 0
    assert sum(1 for b, _, _ in without if b) > 200             # the leak is real without the guard
    # the overdue ACTIONs matter: in-flight = only the one for f + 1 leaks when an ACTION missed its frame
    assert sum(1 for i in range(n) if _simulate(i, True, overdue=False)[0]) > 20
    lat = sorted(d for _, d, _ in with_guard)
    base = sorted(d for _, d, _ in without)
    assert lat[0] == base[0] == 2 and lat[-1] <= base[-1] + 3   # at most the 2-frame press (+ a late ACTION)


def test_exclusive_mirrors_the_oracle_flag():
    """HoldFilter.Exclusive as InputLogicCheck checks it: the Pause press's latch carries nothing else, even a key
    pressed on the frame before, and a queued game-key press never fires."""
    f = kg.Filter()
    f.step(RIGHT)
    f.step(RIGHT | JUMP)
    f.push(RIGHT)
    f.push(RIGHT | ATTACK)
    f.exclusive(PAUSE)
    seen = [f.step(PAUSE)] + [f.step(PAUSE if i < 2 else 0) for i in range(10)]
    assert seen[0] == PAUSE and all(m & ~PAUSE == 0 for m in seen) and not f.queued(~PAUSE & ((1 << 22) - 1))


def test_action_flags_go_out_as_a_fifth_element_and_follow_the_policy():
    import msgpack

    from ssbot.ipc.framing import ACTION_EXCLUSIVE
    from ssbot.ipc.oracle_link import OracleLink
    from ssbot.train.episode import _act

    sent = []
    link = object.__new__(OracleLink)
    link._send = lambda t, body: sent.append(msgpack.unpackb(body))
    link.act(10, PAUSE)
    link.act(11, PAUSE, flags=ACTION_EXCLUSIVE)
    assert sent == [[10, PAUSE, 0, 0], [11, PAUSE, 0, 0, ACTION_EXCLUSIVE]]   # an old oracle reads the first four

    class Pol:
        action_flags = 0

        def act(self, s, tap=None):
            self.action_flags = ACTION_EXCLUSIVE        # set during the tick: the flags of this tick's mask
            return PAUSE
    _act(link, 20, Pol(), {"f": 20}, None)
    assert sent[-1] == [22, PAUSE, 0, 0, ACTION_EXCLUSIVE]
