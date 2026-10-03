"""Pause loop and quit sequence (ssbot.safety.pause_quit) against a simulated game (tests/pause_sim.py): the G1 criteria
of DESIGN §3.7.5 (no unintended unpause, pressing stops within the 230 ms budget, pause within a few frames of the
gate opening, p99.9 <= 6 frames) over randomized trials with persistent false cues, slow menu readers and unmeasured
detectors, then the menu paths under large latency, capture stalls and non-wrapping lists (no wrong Submit), latency
past the configured bound (ALERT, never a wrong Submit), greyed Quit (oracle Options items without a role included),
Patch 4 refusal, Continue + Submit, emulated quits, and one mutation test per protection."""
import random

import pytest

from ssbot.ipc.framing import BIT
from ssbot.safety import game_codes as gc
from ssbot.safety import pause_quit as pq
from ssbot.safety.pause_quit import PauseCues, PauseQuit, PauseQuitConfig, cues_from_state, to_mask
from tests.pause_sim import FRAME_S, PAUSE_ITEMS, PauseSim, SimConfig, run

QUIT_SUBMITS = [("pause", "quit"), ("exit_prompt", "yes")]


def _machine(goal: str = pq.GOAL_QUIT, t0: float = 0.0, sim: SimConfig | None = None, **cfg) -> PauseQuit:
    """A machine whose latency bounds are the sim's maxima (what the real one gets from measured p99.9)."""
    if sim is not None:
        cfg.setdefault("input_latency_max_s", sim.input_lat * FRAME_S + sim.input_jitter_s + 0.02)
        cfg.setdefault("obs_latency_max_s", (sim.obs_lat + sim.stall_max + 1) * FRAME_S + 0.02)
    m = PauseQuit(PauseQuitConfig(**cfg))
    m.start(t0, goal)
    return m


def _open_since(cfg: SimConfig, f: int) -> int:
    """First frame of the open-gate stretch that contains frame f."""
    start = cfg.gate_closed_frames
    for a, b in sorted(cfg.closures + cfg.freezes):
        if b <= f:
            start = max(start, b)
    return start


def _held(m: PauseQuit) -> bool:
    return m.state == "HOLD" or m.done


def _false_cues(r: random.Random, closed: int) -> dict:
    """A vision trial's false cue: a 4-frame flash, a dark baseline, a fade rising like the dimmer that stays, or a
    pause menu misread over the running game with a hit-stop inside it."""
    x = r.random()
    if x < 0.15:
        return {"false_dim_at": r.randint(0, closed + 1)}
    if x < 0.3:
        return {"dark_base": r.uniform(0.03, 0.5)}
    if x < 0.45:
        return {"false_fade_at": r.randint(0, closed + 1), "false_fade_to": r.uniform(0.1, 0.6)}
    if x < 0.6:
        a = r.randint(0, closed + 1)
        fa = r.randint(a, a + 30)
        return {"false_menu": (a, a + r.randint(5, 400)), "freezes": ((fa, fa + r.randint(3, 15)),)}
    return {}


def _vision_reader(r: random.Random) -> dict:
    """A vision trial's detectors: the menu reader 3-18 frames behind the pause (round-2 review: readers slower than
    about 10 frames made the old 0.15 s confirm window unpause), and in 10 % each the dimmer or the motion unmeasured
    (the menu cue alone needs a fast reader to stop within the budget, so those keep the 3-frame reader)."""
    x = r.random()
    if x < 0.1:
        return {"measure_dim": False}
    out = {"menu_reader_frames": r.randint(3, 18)}
    if x < 0.2:
        out["measure_motion"] = False
    return out


def test_loop_randomized_never_unpauses_and_stops_within_budget():
    """10^4 trials (the G1 count): pause gate closed for 0-150 frames plus up to 3 more closures, input latency 1-6
    frames, observation latency 0-6 frames, capture stalls of up to 2 frames in 30 % of trials, frame jitter and 2 %
    long frames with time-based key sampling, oracle or vision cues (menu reader 3-18 frames slow, dimmer or motion
    unmeasured in some), and in 60 % of vision trials a false cue (flash, dark baseline, persistent dimmer-like fade,
    misread pause menu with a hit-stop). G1: no unintended unpause, pressing stops within 230 ms of the pause, pause
    latency from the pausable moment p99.9 <= 6 frames."""
    r = random.Random(7)
    worst_stop, lat_n, lat_over, worst_lat, worst_false = 0.0, 0, 0, 0, 0
    for seed in range(10_000):
        closed = r.randint(0, 150)
        closures, f = [], closed
        for _ in range(r.randint(0, 3)):
            f += r.randint(1, 40)
            n = r.randint(1, 25)
            closures.append((f, f + n))
            f += n
        vision = r.random() < 0.5
        extra = {**_vision_reader(r), **_false_cues(r, closed)} if vision else {}
        cfg = SimConfig(seed=seed, gate_closed_frames=closed, closures=tuple(closures), input_lat=r.randint(1, 6),
                        obs_lat=r.randint(0, 6), stall_p=0.03 if r.random() < 0.3 else 0.0, stall_max=2,
                        vision=vision, initial_highlight=r.choice(PAUSE_ITEMS), **extra)
        sim = PauseSim(cfg)
        m = _machine(pq.GOAL_PAUSE, sim=cfg)
        res = run(m, sim, 1500, until=lambda m, s: _held(m))
        assert m.outcome == pq.PAUSED, (seed, cfg, m.log[-5:])
        log = sim.log
        assert log.esc_unpauses == [], (seed, cfg)
        assert len(log.pauses) == 1, (seed, cfg, log)
        t_p = log.pauses[0]
        stop = max((s - t_p for s in res.press_starts if s >= t_p), default=0.0)
        assert stop <= 0.23, (seed, cfg, stop)
        assert all(d < 0.3 for d in log.pause_edges_while_paused), (seed, log.pause_edges_while_paused)
        worst_stop = max(worst_stop, stop)
        # from the pausable moment (gate open and the first press arrived): one press cycle is 3 + 3 frames at 60 fps
        # (the 34 ms floor), plus one frame of sampling jitter; a false cue adds one confirm window
        latency = sim.paused_f - max(_open_since(cfg, sim.paused_f), int(cfg.input_lat) + 1)
        if m.false_cues == 0:
            lat_n += 1
            lat_over += latency > 6
            worst_lat = max(worst_lat, latency)
        else:
            worst_false = max(worst_false, latency)
    assert worst_stop < 0.2
    assert lat_over <= 0.001 * lat_n and worst_lat <= 7, (lat_over, lat_n, worst_lat)     # G1: p99.9 <= 6 frames
    assert worst_false <= 7 + 30, worst_false   # a false cue costs its hit-stop or, motion unmeasured, 0.4 s


def _quit_cfg(r: random.Random, seed: int, **over) -> SimConfig:
    il = r.randint(1, 8)
    ol = r.randint(0, min(6, 14 - il))
    vision = r.random() < 0.5
    kw = dict(seed=seed, gate_closed_frames=r.randint(0, 60), input_lat=il, obs_lat=ol,
              stall_p=0.03 if r.random() < 0.5 else 0.0, stall_max=1 if il + ol >= 13 else 2, vision=vision,
              initial_highlight=r.choice(PAUSE_ITEMS), prompt_wraps=r.random() < 0.5, quit_frames=20,
              **(_false_cues(r, 30) if vision and r.random() < 0.3 else {}))
    kw.update(over)
    return SimConfig(**kw)


def test_full_quit_randomized_never_submits_a_wrong_item():
    """10^4 full quits: input latency 1-8 frames plus observation latency up to 14 frames in all (the loop's own limit
    is about 17 frames: past that its last press lands after the 0.3 s lockout), capture stalls, prompts that do or
    do not wrap, random initial highlight, oracle or vision cues with false cues: the only Submits are Quit, then
    Yes."""
    r = random.Random(11)
    flips = 0
    for seed in range(10_000):
        cfg = _quit_cfg(r, 10_000 + seed)
        sim = PauseSim(cfg)
        m = _machine(sim=cfg)
        run(m, sim, 3000, until=lambda m, s: m.done)
        assert sim.log.submits == QUIT_SUBMITS, (seed, cfg, sim.log.submits, m.log[-8:])
        assert sim.log.esc_unpauses == [] and sim.log.continue_unpauses == [], (seed, cfg)
        assert m.outcome == pq.QUIT and sim.gs == "MAIN_MENU", (seed, cfg, m.log[-5:])
        flips += m.nav_flips
    assert flips < 100                 # a flip follows only a press a long frame swallowed


def _paused_sim(cfg: SimConfig) -> PauseSim:
    """The game paused on frame 0 and the machine starts once it can see the dimmer up (a navigation-only trial: with
    this much latency the loop's own presses would land after the lockout)."""
    sim = PauseSim(cfg)
    for _ in range(cfg.obs_lat + 16):
        sim.advance()
    return sim


@pytest.mark.parametrize("bounds", ["measured", "default"])
def test_navigation_with_24_frames_of_latency_and_stalls(bounds):
    """2x10^3 menu walks on a paused game with input latency 0-12 frames, observation latency 0-12 frames and capture
    stalls repeating a frame for up to 4 steps: plain quits, and greyed-by-disableSaveQuit menus refreshed through
    Options (wrapping or not) -> Back. With the machine's latency bounds set to the sim's maxima ("measured") every
    walk quits. Left at the 0.1 s defaults ("default"), the input bound alone is not exceeded (the post-tap cut comes
    0.117 s after a release that ends about 0.1 s after the press edge: about 13 frames, round-2 review), but the round
    trip (up to 24 frames plus stalls) passes the configured 0.37 s in some walks: still no wrong Submit and no
    unpause; a walk whose flipped tap then shows the bound broken ends ALERT (14 of 2000). The cases past the input
    bound are test_beyond_the_latency_bound_alerts_and_never_submits_a_wrong_item."""
    r = random.Random(23 if bounds == "measured" else 29)
    alerts = 0
    for seed in range(2000):
        il, ol = r.randint(0, 12), r.randint(0, 12)
        greyed = r.random() < 0.3
        cfg = SimConfig(seed=seed, start_paused=True, input_lat=il, obs_lat=ol, stall_p=0.05, stall_max=4,
                        vision=r.random() < 0.5, initial_highlight=r.choice(PAUSE_ITEMS),
                        prompt_wraps=r.random() < 0.5, options_wraps=r.random() < 0.5, quit_frames=20,
                        quit_greyed=greyed, greyed_cause="dsq", dsq_clears_on_refresh=True)
        sim = _paused_sim(cfg)
        m = _machine(t0=sim.t, sim=cfg if bounds == "measured" else None)
        run(m, sim, 6000, until=lambda m, s: m.done)
        want = ([("pause", "options"), ("options", "back")] if greyed else []) + QUIT_SUBMITS
        assert sim.log.esc_unpauses == [] and sim.log.continue_unpauses == [], (seed, cfg)
        if bounds == "default" and m.outcome == pq.ALERT:
            assert sim.log.submits == want[:len(sim.log.submits)], (seed, cfg, sim.log.submits, m.log[-10:])
            assert any("latency above the configured bound" in d for _, k, d in m.log if k == "fail"), m.log[-4:]
            alerts += 1
            continue
        assert sim.log.submits == want, (seed, cfg, sim.log.submits, m.log[-10:])
        assert m.outcome == pq.QUIT, (seed, cfg, m.log[-6:])
    assert alerts <= 40 and (bounds == "default" or alerts == 0)


def test_reviewer_case_nine_frames_of_latency():
    """Round-1 review: input 4 + observation 5 frames with the highlight on Options made 200 of 200 quits Submit the
    wrong item (62 on Continue). Same case, default bounds."""
    for seed in range(200):
        cfg = SimConfig(seed=seed, gate_closed_frames=20, input_lat=4, obs_lat=5, initial_highlight="options")
        sim = PauseSim(cfg)
        m = _machine()
        run(m, sim, 3000, until=lambda m, s: m.done)
        assert sim.log.submits == QUIT_SUBMITS and m.outcome == pq.QUIT, (seed, m.log[-8:])
        assert sim.log.esc_unpauses == [] and sim.log.continue_unpauses == []


def test_exit_prompt_no_to_yes_is_up_and_a_dead_tap_flips_direction(monkeypatch):
    assert pq._direction(pq.M_EXIT_PROMPT, "no", "yes") == pq.UP          # probe P7, §3.7.5
    assert pq._direction(pq.M_EXIT_PROMPT, "yes", "no") == pq.DOWN
    assert pq._direction(pq.M_PAUSE, "continue", "quit") == pq.UP         # wraps: the short way
    assert pq._direction(pq.M_PAUSE, "options", "quit") == pq.DOWN
    assert pq._direction(pq.M_OPTIONS, "game", "back") == pq.UP           # unknown order: a guess, then a flip
    cfg = SimConfig(gate_closed_frames=10, prompt_wraps=False, initial_highlight="quit")
    sim = PauseSim(cfg)
    m = _machine()
    run(m, sim, 2000, until=lambda m, s: m.done)
    assert m.outcome == pq.QUIT and sim.log.submits == QUIT_SUBMITS and m.nav_flips == 0
    # the old tie-break (Down on a non-wrapping prompt) recovers by flipping once
    monkeypatch.setattr(pq, "_direction", lambda menu, at, target: pq.DOWN)
    for vision in (False, True):
        sim = PauseSim(SimConfig(gate_closed_frames=10, prompt_wraps=False, initial_highlight="quit", vision=vision,
                                 input_lat=6, obs_lat=6))
        m = _machine(sim=sim.cfg)
        run(m, sim, 3000, until=lambda m, s: m.done)
        assert m.outcome == pq.QUIT and sim.log.submits == QUIT_SUBMITS and m.nav_flips == 1, m.log


def test_oracle_options_items_without_a_role_still_reach_back():
    """Round-2 review: the oracle names only Back on Options (sel nil for Game, Audio, ...), so the greyed-by-dsq
    refresh failed 'highlight unreadable on options'. cues_from_state reads such an item as UNLABELLED; the machine
    walks Down (Back is last, wrapping or not) without flipping, waiting a full round trip per tap, and Submits only
    on Back."""
    for wraps in (True, False):
        sim = PauseSim(SimConfig(gate_closed_frames=20, quit_greyed=True, greyed_cause="dsq",
                                 dsq_clears_on_refresh=True, options_wraps=wraps, options_unlabelled=True))
        m = _machine()
        run(m, sim, 4000, until=lambda m, s: m.done)
        assert m.outcome == pq.QUIT and m.nav_flips == 0, (wraps, m.log[-6:])
        assert sim.log.submits == [("pause", "options"), ("options", "back")] + QUIT_SUBMITS
    assert pq._direction(pq.M_OPTIONS, pq.UNLABELLED, "back") == pq.DOWN
    paused = dict(gs=gc.GS_PAUSED, ui=5, menu=gc.MENU_OPTIONS_MENU, fading=False, blk=64)
    assert cues_from_state(_state(1, **paused, extra={"sel": None})).highlight == pq.UNLABELLED
    assert cues_from_state(_state(1, **paused, extra={"sel": "back"})).highlight == "back"
    assert cues_from_state(_state(1, **paused, extra={"sel": "GameButton"})).highlight == "GameButton"   # names pass
    assert cues_from_state(_state(1, **paused)).highlight is None          # no STATE "menu" section: unknown


def test_options_without_wrap_reaches_back_by_flipping():
    sim = PauseSim(SimConfig(gate_closed_frames=20, quit_greyed=True, greyed_cause="dsq", dsq_clears_on_refresh=True,
                             options_wraps=False))
    m = _machine()
    run(m, sim, 3000, until=lambda m, s: m.done)
    assert m.outcome == pq.QUIT and m.nav_flips == 1
    assert sim.log.submits == [("pause", "options"), ("options", "back")] + QUIT_SUBMITS


def test_persistent_false_cues_never_stop_the_loop():
    # the review's case: a constant dark reading never makes a cue; the loop presses for 10 s and alerts at 5 s
    m = _machine(pq.GOAL_PAUSE)
    keys = [m.step(PauseCues(t=i / 60, dim=0.05)) for i in range(600)]
    starts = sum(1 for a, b in zip([frozenset()] + keys, keys) if "pause" in b and "pause" not in a)
    assert starts >= 95 and m.state == "LOOP" and m.alert
    assert any(k == "loop_alert" and 4.9 < t < 5.1 for t, k, _ in m.log)
    # a fade rising like the dimmer every 40 frames: each is a false cue at most once, the loop keeps pressing, and
    # the third raises the alert
    m = _machine(pq.GOAL_PAUSE)
    starts, prev = 0, frozenset()
    for i in range(600):
        k = m.step(PauseCues(t=i / 60, dim=0.053 * (i % 40) if i % 40 < 8 else 0.0, frozen=False))
        starts += "pause" in k and "pause" not in prev
        prev = k
    assert m.false_cues >= 10 and starts >= 60 and m.alert
    assert any(k == "false_cue_alert" for _, k, _ in m.log)
    for over, false_cues in ((dict(false_fade_at=10, false_fade_to=0.4), 1),     # rises like the dimmer, then stays
                             (dict(dark_base=0.5), 0),                           # dark room: a real pause still rises
                             (dict(false_menu=(0, 600), freezes=((60, 70),)), 0),   # misread menu over the game
                             (dict(false_menu=(0, 600), freezes=((60, 70),), dark_base=0.1), 0)):
        sim = PauseSim(SimConfig(gate_closed_frames=150, vision=True, obs_lat=3, input_lat=3, **over))
        m = _machine(pq.GOAL_PAUSE)
        res = run(m, sim, 900, until=lambda m, s: _held(m))
        assert m.outcome == pq.PAUSED and m.false_cues <= false_cues and m.unexpected_unpauses == 0, (over, m.log)
        assert len(sim.log.pauses) == 1 and sim.log.esc_unpauses == [], over
        t_p = sim.log.pauses[0]
        assert max(s - t_p for s in res.press_starts if s >= t_p) <= 0.23
        assert sim.paused_f - 150 <= 7 + 12 * false_cues, (over, sim.paused_f)


@pytest.mark.parametrize("reader", [9, 12, 15, 18, 24])
def test_slow_menu_reader_never_unpauses(reader):
    """Round-2 review: with the vision menu visible to the reader only N frames after the pause, the 0.15 s confirm
    window declared real pauses false and resumed pressing: N = 12 unpaused 65 of 400 trials, N = 24 400 of 400. The
    dimmer on its pause trajectory over a stopped world now keeps the loop from pressing until the reader confirms."""
    r = random.Random(reader)
    for seed in range(150):
        cfg = SimConfig(seed=seed, gate_closed_frames=r.randint(0, 60), input_lat=r.randint(1, 6),
                        obs_lat=r.randint(0, 6), vision=True, menu_reader_frames=reader,
                        dark_base=r.choice((0.0, 0.0, r.uniform(0.03, 0.5))))
        sim = PauseSim(cfg)
        m = _machine(pq.GOAL_PAUSE, sim=cfg)
        res = run(m, sim, 1500, until=lambda m, s: _held(m))
        assert m.outcome == pq.PAUSED and sim.log.esc_unpauses == [] and m.false_cues == 0, (seed, cfg, m.log[-6:])
        t_p = sim.log.pauses[0]
        assert max((x - t_p for x in res.press_starts if x >= t_p), default=0.0) <= 0.23


def test_misread_menu_needs_independent_evidence():
    """Round-2 review (F2, menu variant): a pause menu misread with motion unmeasured (frozen None), or over a dark
    room (a constant dim 0.75 is no rise above the baseline), never stops the loop; nor does one over a hit-stop
    once the world moves again."""
    for frozen, dim in ((None, None), (None, 0.75), (True, 0.75)):
        m = _machine(pq.GOAL_PAUSE)
        keys = [m.step(PauseCues(t=i / 60, dim=dim, frozen=False)) for i in range(30)]     # gameplay, then the misread
        keys += [m.step(PauseCues(t=i / 60, menu=pq.M_PAUSE, frozen=frozen, dim=dim)) for i in range(30, 630)]
        starts = sum(1 for a, b in zip([frozenset()] + keys, keys) if "pause" in b and "pause" not in a)
        assert starts >= 95 and m.state == "LOOP" and m.false_cues == 0, (frozen, dim, starts, m.log[-4:])
        assert any(k == "loop_alert" for _, k, _ in m.log)
    # over hit-stops (frozen for 9 frames out of every 60, dim not measured): one false cue per hit-stop, rejected
    # two moving frames after it, and the loop keeps pressing in between
    m = _machine(pq.GOAL_PAUSE)
    keys = [m.step(PauseCues(t=i / 60, menu=pq.M_PAUSE, frozen=i % 60 < 9)) for i in range(600)]
    starts = sum(1 for a, b in zip([frozenset()] + keys, keys) if "pause" in b and "pause" not in a)
    assert m.false_cues == 10 and starts >= 60 and m.state == "LOOP" and m.alert
    # the loop's first frame has no history: a menu over a stopped world with the dimmer at its plateau (or not
    # measured) is taken as a pause already in place (a press would unpause it), confirmed after confirm_hold_s and
    # then held or quit; a menu that never becomes ready ends in an alert, never in a press
    for dim in (None, 0.8):
        m = _machine(pq.GOAL_PAUSE)
        keys = [m.step(PauseCues(t=i / 60, menu=pq.M_PAUSE, frozen=True, dim=dim)) for i in range(300)]
        assert not any(keys) and m.outcome == pq.ALERT and any("not ready" in d for _, k, d in m.log if k == "fail")


def test_beyond_the_latency_bound_alerts_and_never_submits_a_wrong_item():
    """Round-2 review: past input_latency_max_s, a late first tap and the flipped counter-tap both acted and the
    Submit landed on a wrong item, Continue included (input 14 / observation 20 frames: 19 of 40 wrong, 2 unpaused;
    20 / 12: 40 of 40, 14 unpaused). After a flip the reading must now hold for two round trips past the last tap; a
    change meanwhile is the bound broken: ALERT."""
    outcomes = {pq.QUIT: 0, pq.ALERT: 0}
    for il, ol in ((14, 20), (16, 12), (16, 20), (20, 12)):
        for seed in range(40):
            cfg = SimConfig(seed=seed, start_paused=True, input_lat=il, obs_lat=ol, vision=seed % 2 == 0,
                            initial_highlight=PAUSE_ITEMS[seed % 3], prompt_wraps=seed % 4 < 2, quit_frames=20)
            sim = _paused_sim(cfg)
            m = _machine(t0=sim.t)
            run(m, sim, 6000, until=lambda m, s: m.done)
            assert sim.log.submits == QUIT_SUBMITS[:len(sim.log.submits)], (il, ol, seed, sim.log.submits)
            assert sim.log.esc_unpauses == [] and sim.log.continue_unpauses == [], (il, ol, seed)
            assert m.outcome in outcomes, (il, ol, seed, m.log[-4:])
            outcomes[m.outcome] += 1
    assert outcomes[pq.ALERT] > 0 and outcomes[pq.QUIT] > 0, outcomes


def _quits_with_mutation(monkeypatch, n: int, **patch) -> tuple[int, int]:
    """(wrong-Submit quits, unpaused quits) of n randomized full quits at up to 14 frames of latency, with the
    machine's bounds at the sim's maxima and the given PauseQuit methods replaced."""
    for name, fn in patch.items():
        monkeypatch.setattr(PauseQuit, name, fn)
    r = random.Random(11)
    wrong = unpaused = 0
    for seed in range(n):
        cfg = _quit_cfg(r, 10_000 + seed)
        sim = PauseSim(cfg)
        m = _machine(sim=cfg)
        run(m, sim, 3000, until=lambda m, s: m.done)
        wrong += sim.log.submits != QUIT_SUBMITS[:len(sim.log.submits)]
        unpaused += bool(sim.log.esc_unpauses or sim.log.continue_unpauses)
    monkeypatch.undo()
    return wrong, unpaused


def test_mutations_of_the_menu_protections(monkeypatch):
    """Each protection removed in turn, against the scenario it exists for. The post-tap cut and the change-wait guard
    the same stale frames, so each alone suffices in the randomized quits (removing the cut alone: 0 wrong of 300)
    and only removing both fails; the flip settle is what keeps a broken latency bound from a wrong Submit."""
    assert _quits_with_mutation(monkeypatch, 300) == (0, 0)
    assert _quits_with_mutation(monkeypatch, 300, _tap_cut=lambda self, t: float("-inf")) == (0, 0)
    wrong, _ = _quits_with_mutation(monkeypatch, 300, _tap_cut=lambda self, t: float("-inf"),
                                    _unmoved=lambda self, hl: False)
    assert wrong >= 30, wrong
    monkeypatch.setattr(PauseQuit, "_settling", lambda self, c, hl: False)
    wrong = 0
    for il, ol in ((14, 20), (20, 12)):
        for seed in range(40):
            sim = _paused_sim(SimConfig(seed=seed, start_paused=True, input_lat=il, obs_lat=ol,
                                        initial_highlight=PAUSE_ITEMS[seed % 3], quit_frames=20))
            m = _machine(t0=sim.t)
            run(m, sim, 6000, until=lambda m, s: m.done)
            wrong += sim.log.submits != QUIT_SUBMITS[:len(sim.log.submits)]
    assert wrong >= 10, wrong


def test_mutation_of_the_confirm_rule(monkeypatch):
    """The round-2 rule (a cue not confirmed by the reader within 0.15 s is false) against a 24-frame reader."""
    def timed(self, c):
        if c.paused is not None:
            return "confirm" if c.paused else "reject"
        if c.menu in pq.PAUSE_MENUS and c.frozen is not False:
            return "confirm"
        return "reject" if c.t - self.t_cue > 0.15 else None
    counts = {}
    for name, patch in (("timed", {"_verdict": timed}), ("current", {})):
        for k, fn in patch.items():
            monkeypatch.setattr(PauseQuit, k, fn)
        unpaused = 0
        for seed in range(60):
            cfg = SimConfig(seed=seed, gate_closed_frames=seed % 40, input_lat=3, obs_lat=3, vision=True,
                            menu_reader_frames=24)
            sim = PauseSim(cfg)
            m = _machine(pq.GOAL_PAUSE, sim=cfg)
            run(m, sim, 600, until=lambda m, s: _held(m))
            unpaused += bool(sim.log.esc_unpauses)
        counts[name] = unpaused
        monkeypatch.undo()
    assert counts["timed"] >= 30 and counts["current"] == 0, counts


def test_false_dim_flash_resumes_the_loop():
    sim = PauseSim(SimConfig(gate_closed_frames=90, vision=True, false_dim_at=20, obs_lat=3, input_lat=3))
    m = _machine(pq.GOAL_PAUSE)
    res = run(m, sim, 600, until=lambda m, s: _held(m))
    assert m.false_cues <= 1 and m.outcome == pq.PAUSED
    assert len(sim.log.pauses) == 1 and sim.log.esc_unpauses == []
    t_p = sim.log.pauses[0]
    assert max(s - t_p for s in res.press_starts if s >= t_p) <= 0.23


def test_emulated_quit_ends_once_the_pause_is_confirmed():
    sim = PauseSim(SimConfig(gate_closed_frames=40))
    m = _machine(emulate_quit=True)
    run(m, sim, 400, until=lambda m, s: m.done)
    assert m.outcome == pq.QUIT_EMULATED and m.done
    assert m.quit_state_seen == pq.QUIT_AVAILABLE
    assert sim.log.submits == [] and sim.gs == "PAUSED"


def test_emulated_quit_reports_greyed_refused_and_unknown_apart():
    sim = PauseSim(SimConfig(gate_closed_frames=40, quit_greyed=True))
    m = _machine(emulate_quit=True)
    run(m, sim, 400, until=lambda m, s: m.done)
    assert m.outcome == pq.QUIT_EMULATED_GREYED and m.done
    # oracle: paused with disablePause set (Patch 4 would refuse Yes), or a menu that never becomes readable
    paused = dict(gs=gc.GS_PAUSED, ui=5, menu=17, fading=False)
    for blk, want in ((gc.BLK_PAUSE_LOCKOUT | gc.BLK_DISABLE_PAUSE, pq.REFUSED_EMULATED),
                      (gc.BLK_PAUSE_LOCKOUT, pq.QUIT_EMULATED)):
        m = _machine(emulate_quit=True)
        for f in range(1, 20):
            m.step(cues_from_state(_state(f, blk=blk, **paused)))
        assert m.outcome == want, m.log
    m = _machine(emulate_quit=True)
    for f in range(1, 60):
        m.step(cues_from_state(_state(f, gc.GS_PAUSED, 5, 6, True, 100)))     # stuck fading: never ready
    assert m.outcome == pq.QUIT_EMULATED_UNKNOWN


def test_greyed_by_preload_stays_paused_and_never_touches_quit():
    sim = PauseSim(SimConfig(gate_closed_frames=20, quit_greyed=True, greyed_cause="preload",
                             initial_highlight="quit"))
    m = _machine()
    res = run(m, sim, 400, until=lambda m, s: m.state == "GREYED")
    assert m.outcome == pq.GREYED and m.alert
    assert sim.log.submits == []
    n0 = res.steps
    res = run(m, sim, 300)           # keep stepping: nothing is pressed, the game stays paused
    assert m.state == "GREYED" and sim.gs == "PAUSED" and sim.log.submits == []
    assert not res.press_starts and sim.log.esc_unpauses == [] and n0 > 0
    assert m.resolve_greyed(sim.t, pq.GREYED_STAY) and m.state == "GREYED"


def test_greyed_by_disable_save_quit_refreshes_through_options_then_quits():
    sim = PauseSim(SimConfig(gate_closed_frames=20, quit_greyed=True, greyed_cause="dsq", dsq_clears_on_refresh=True))
    m = _machine()
    run(m, sim, 1500, until=lambda m, s: m.done)
    assert m.outcome == pq.QUIT
    assert sim.log.submits == [("pause", "options"), ("options", "back")] + QUIT_SUBMITS
    assert sim.log.esc_unpauses == []


def test_greyed_after_refresh_then_unpause_to_evade_uses_continue():
    sim = PauseSim(SimConfig(gate_closed_frames=20, quit_greyed=True, greyed_cause="dsq"))
    m = _machine()
    run(m, sim, 1500, until=lambda m, s: m.state == "GREYED")
    assert sim.log.submits == [("pause", "options"), ("options", "back")]
    assert m.resolve_greyed(sim.t, pq.GREYED_UNPAUSE_EVADE)
    run(m, sim, 600, until=lambda m, s: m.done)
    assert m.outcome == pq.UNPAUSED
    assert sim.log.submits[-1] == ("pause", "continue")
    assert sim.log.esc_unpauses == [] and len(sim.log.continue_unpauses) == 1


def test_patch4_refusal_stays_paused():
    sim = PauseSim(SimConfig(gate_closed_frames=10, refuse_yes=True))
    m = _machine()
    run(m, sim, 3000, until=lambda m, s: m.state == "REFUSED")
    assert m.outcome == pq.REFUSED and m.alert
    # Yes is pressed max_submits times (a lost press is retried) before the prompt staying counts as a refusal
    assert sim.log.submits == [("pause", "quit")] + [("exit_prompt", "yes")] * 3
    res = run(m, sim, 300)
    assert m.state == "REFUSED" and sim.gs == "PAUSED" and not res.press_starts
    assert len(sim.log.submits) == 4 and sim.log.esc_unpauses == []
    assert m.request_unpause(sim.t)             # an explicit decision: No, then Continue
    run(m, sim, 900, until=lambda m, s: m.done)
    assert m.outcome == pq.UNPAUSED
    assert sim.log.submits[4:] == [("exit_prompt", "no"), ("pause", "continue")]
    assert sim.log.esc_unpauses == []


def test_refused_then_quit_again_once_the_flags_clear():
    sim = PauseSim(SimConfig(gate_closed_frames=10, refuse_yes=True, input_lat=4, obs_lat=4))
    m = _machine(sim=sim.cfg)
    run(m, sim, 3000, until=lambda m, s: m.state == "REFUSED")
    sim.cfg.refuse_yes = False                  # disablePause / disableSaveQuit cleared (re-checked by the caller)
    assert m.request_quit(sim.t) and not m.request_quit(sim.t)
    run(m, sim, 1500, until=lambda m, s: m.done)
    assert m.outcome == pq.QUIT and sim.gs == "MAIN_MENU"
    assert set(sim.log.submits) == set(QUIT_SUBMITS) and sim.log.esc_unpauses == []
    # from a held pause (goal PAUSE): the Quit item is read again, then the quit
    sim = PauseSim(SimConfig(gate_closed_frames=10))
    m = _machine(pq.GOAL_PAUSE)
    run(m, sim, 600, until=lambda m, s: m.state == "HOLD")
    run(m, sim, 120)
    assert m.request_quit(sim.t)
    run(m, sim, 1500, until=lambda m, s: m.done)
    assert m.outcome == pq.QUIT and sim.log.submits == QUIT_SUBMITS


def test_held_states_follow_a_quit_that_proceeds_and_the_quit_has_a_deadline():
    """A slow save read as a refusal (vision), or a quit started from elsewhere: the held state follows it to the main
    menu. After Yes, a prompt that vanishes with no quit start ends in an alert, not a wait forever."""
    m = _machine()
    m.state, m.outcome = "REFUSED", pq.REFUSED
    m.step(PauseCues(t=1.0, paused=True, menu=pq.M_EXIT_PROMPT, quitting=True))
    assert m.state == "QUITTING"
    m.step(PauseCues(t=2.0, paused=True, menu=pq.M_MAIN_MENU))
    assert m.outcome == pq.QUIT
    for held in ("HOLD", "GREYED"):
        m = _machine()
        m.state = held
        m.step(PauseCues(t=1.0, menu=pq.M_LOADING, quitting=True))
        assert m.state == "QUITTING", held
    sim = PauseSim(SimConfig(gate_closed_frames=10, refuse_yes=True))
    m = _machine(quit_wait_s=2.0)
    run(m, sim, 3000, until=lambda m, s: m.state == "MENU" and m._plan and m._plan[0].target == "yes"
        and m._phase == "effect")
    for i in range(1, 400):             # the prompt is gone but nothing says the quit started
        m.step(PauseCues(t=sim.t + i / 60, paused=True, frozen=True, menu=pq.M_OTHER))
        if m.done:
            break
    assert m.outcome == pq.ALERT and any("neither" in d for _, k, d in m.log if k == "fail")


def test_save_failed_is_acknowledged_and_retried_a_bounded_number_of_times():
    sim = PauseSim(SimConfig(gate_closed_frames=10, save_fails=1))
    m = _machine()
    run(m, sim, 1500, until=lambda m, s: m.done)
    assert m.outcome == pq.QUIT
    assert sim.log.submits == [("pause", "quit"), ("exit_prompt", "yes"), ("save_failed", "ok"),
                               ("exit_prompt", "yes")]
    sim = PauseSim(SimConfig(gate_closed_frames=10, save_fails=5))
    m = _machine()
    run(m, sim, 1500, until=lambda m, s: m.done)
    assert m.outcome == pq.ALERT and sim.gs == "PAUSED" and sim.log.esc_unpauses == []
    assert [x for x in sim.log.submits if x == ("exit_prompt", "yes")] == [("exit_prompt", "yes")] * 3


def test_unpause_waits_for_the_lockout_and_uses_continue():
    for vision in (False, True):
        sim = PauseSim(SimConfig(gate_closed_frames=5, vision=vision))
        m = _machine(pq.GOAL_PAUSE)
        run(m, sim, 400, until=lambda m, s: m.state == "HOLD")
        assert m.outcome == pq.PAUSED
        assert m.request_unpause(sim.t)
        run(m, sim, 600, until=lambda m, s: m.done)
        assert m.outcome == pq.UNPAUSED
        assert sim.log.continue_unpauses[0] - sim.log.pauses[0] >= 0.3
        assert sim.log.esc_unpauses == [] and sim.log.submits[-1] == ("pause", "continue")
        assert m.unpause_lockout_until is not None


def test_death_stops_the_loop():
    sim = PauseSim(SimConfig(gate_closed_frames=400, death_at=30))
    m = _machine()
    res = run(m, sim, 300, until=lambda m, s: m.done)
    assert m.outcome == pq.DEAD and res.press_starts
    assert sim.f == 30 + sim.cfg.obs_lat              # stopped on the first frame the death was seen
    assert not run(m, sim, 60).press_starts


def test_no_blind_submit_without_a_highlight_reader():
    sim = PauseSim(SimConfig(gate_closed_frames=10, highlight_visible=False))
    m = _machine()
    run(m, sim, 600, until=lambda m, s: m.done)
    assert m.outcome == pq.ALERT and sim.log.submits == [] and sim.gs == "PAUSED"


def test_tap_timing_34_ms_and_two_frames():
    m = _machine()
    keys = [m.step(PauseCues(t=i / 60, paused=False)) for i in range(12)]
    assert ["pause" in k for k in keys] == [True, True, True, False, False, False] * 2   # 2 frames = 33.3 ms < 34
    m = _machine()                                        # 240 fps: the 34 ms floor holds keys longer than 2 frames
    keys = [m.step(PauseCues(t=i / 240, paused=False)) for i in range(18)]
    assert ["pause" in k for k in keys] == [True] * 9 + [False] * 9
    # stale repeated frames do not stretch a tap: timing runs on the emission clock
    m = _machine()
    keys = [m.step(PauseCues(t=0.0, paused=False), now=i / 60) for i in range(6)]
    assert ["pause" in k for k in keys] == [True, True, True, False, False, False]


def test_the_sim_samples_keys_by_time():
    """Mutation check of the sim: 1-frame taps lose presses to long frames; the 34 ms taps almost never do."""
    lost = {}
    for name, kw in (("short", dict(press_frames=1, release_frames=1, press_min_s=0.0, release_min_s=0.0)),
                     ("default", {})):
        sim = PauseSim(SimConfig(gate_closed_frames=10_000, long_frame_p=0.3, seed=3))
        m = _machine(pq.GOAL_PAUSE, **kw)
        run(m, sim, 3000)
        lost[name] = 1 - sim.log.pause_edges / m.presses
    assert lost["short"] > 0.1 and lost["default"] < 0.01, lost


def test_loop_budget_check():
    assert pq.loop_budget_ok(0.050, 0.050)
    assert not pq.loop_budget_ok(0.200, 0.050)


def _state(f: int, gs: int = gc.GS_PLAYING, ui: int = 4, menu: int = 6, fading: bool = False, blk: int = 0,
           dsq: bool = False, preload: bool = False, extra: dict | None = None) -> dict:
    s = {"f": f, "q": f * 166_667, "ts": 0.0 if gs == gc.GS_PAUSED else 1.0,
         "game": {"gs": gs, "ui": ui, "menu": menu, "fading": fading, "paused": gs == gc.GS_PAUSED, "pd_mode": 0},
         "pause": {"blk": blk, "dsq": dsq, "preload": preload}, "ev": []}
    if extra is not None:
        s["menu"] = extra
    return s


def test_oracle_cues_follow_the_measured_pause_sequence():
    # human session 20260930_210337 frames 14919 / 14927 / 14938 / 156108, 156265 and the title
    c = cues_from_state(_state(14919, gc.GS_PAUSED, 5, 6, True, 100))
    assert c.paused and c.frozen and c.menu == pq.M_OTHER and not c.menu_ready and c.quit_state is None
    c = cues_from_state(_state(14927, gc.GS_PAUSED, 5, 17, False, 68))
    assert c.menu == pq.M_PAUSE and c.menu_ready and c.quit_state == pq.QUIT_AVAILABLE and c.highlight is None
    assert c.disable_pause is False and c.unpause_blocked is None
    c = cues_from_state(_state(14938, gc.GS_PAUSED, 5, 17, False, 64, dsq=True))
    assert c.quit_state == pq.QUIT_GREYED and c.quit_cause == "dsq"
    c = cues_from_state(_state(14938, gc.GS_PAUSED, 5, 17, False, 64, preload=True))
    assert c.quit_cause == "preload"
    c = cues_from_state(_state(156016, gc.GS_PAUSED, 5, 10, False, 64))
    assert c.menu == pq.M_EXIT_PROMPT and c.menu_ready and not c.quitting
    c = cues_from_state(_state(156108, gc.GS_PAUSED, 5, 10, False, 100))
    assert c.quitting and not c.menu_ready
    c = cues_from_state({"f": 156265, "q": 1, "game": None, "pause": None})
    assert c.menu == pq.M_LOADING and c.quitting
    c = cues_from_state(_state(160000, gc.GS_MAIN_MENU, 1, 1))
    assert c.menu == pq.M_MAIN_MENU
    c = cues_from_state(_state(5, blk=gc.BLK_MSG_CANVAS))
    assert c.menu == pq.M_OTHER and not c.paused
    s = _state(5)
    s["ev"] = [{"k": "hero_dead", "f": 5, "d": {}}]
    assert cues_from_state(s).dead


def test_oracle_menu_section_is_read_when_present():
    """STATE "menu" (cross-module decision 5): sel, quit_ok, dim, alpha, ignore_unpause, quitting override the derived
    values; null / missing fields keep the fallbacks."""
    extra = {"sel": "quit", "quit_ok": False, "dim": 0.8, "alpha": 1.0, "ignore_unpause": True, "quitting": False}
    c = cues_from_state(_state(14927, gc.GS_PAUSED, 5, 17, False, 64, extra=extra))
    assert (c.highlight, c.quit_state, c.dim, c.menu_alpha, c.unpause_blocked) == ("quit", pq.QUIT_GREYED, 0.8, 1.0,
                                                                                   True)
    c = cues_from_state(_state(156108, gc.GS_PAUSED, 5, 10, False, 100, extra={"sel": "yes", "quitting": False}))
    assert not c.quitting and c.highlight == "yes"     # PreventPause alone (SAVE_FAILED retry) is not a quit start
    c = cues_from_state(_state(156016, gc.GS_PAUSED, 5, 10, False, 64, extra={"sel": "no", "quitting": True}))
    assert c.quitting
    c = cues_from_state(_state(14927, gc.GS_PAUSED, 5, 17, False, 64, extra={"sel": None, "quit_ok": None}, dsq=True))
    assert c.highlight is None and c.quit_state == pq.QUIT_GREYED


def test_availability():
    assert pq.availability_from_state(_state(1)) == pq.Availability(True, True)
    a = pq.availability_from_state(_state(1, blk=gc.BLK_DISABLE_PAUSE | gc.BLK_TIME_SLOWED))
    assert not a.pause and "DISABLE_PAUSE" in a.reason
    assert pq.availability_from_state(_state(1, dsq=True)) == pq.Availability(True, False, "disableSaveQuit")
    assert not pq.availability("GAMEPLAY", 1.0, unpause_lockout_until=1.2, p_pause=1.0, p_quit=1.0).pause
    assert not pq.availability("GAMEPLAY", 1.0, p_pause=None).pause
    assert pq.availability("GAMEPLAY", 1.0, p_pause=0.995, p_quit=0.9) == pq.Availability(True, False,
                                                                                           "quit map P(quit) 0.9")
    assert pq.availability("GAMEPLAY", 1.0, p_pause=1.0, p_quit=1.0).quit
    assert not pq.availability("CUTSCENE", 1.0, p_pause=1.0, p_quit=1.0).pause


def test_oracle_mode_end_to_end_with_masks():
    """A minimal oracle stand-in that reacts to ACTION masks: gate closed for 30 frames, then the pause; STATE goes
    through cues_from_state and the machine's keys through to_mask with the real button table."""
    m = _machine(emulate_quit=True)
    paused_f = None
    prev_mask = 0
    for f in range(200):
        if paused_f is None:
            s = _state(f, blk=gc.BLK_DISABLE_PAUSE if f < 30 else 0)
        else:
            age = f - paused_f
            s = _state(f, gc.GS_PAUSED, 5, 17 if age >= 8 else 6, age < 8, 100 if age < 8 else 68 if age < 19 else 64)
        mask = to_mask(m.step(cues_from_state(s)), BIT)
        assert mask & ~(1 << BIT["pause"]) == 0
        if paused_f is None and f >= 30 and mask & (1 << BIT["pause"]) and not prev_mask & (1 << BIT["pause"]):
            paused_f = f + 1
        prev_mask = mask
        if m.done:
            break
    assert m.outcome == pq.QUIT_EMULATED and m.quit_state_seen == pq.QUIT_AVAILABLE


def _oracle_hit_quit(gate_cue: bool, open_at: int = 15, lead: int = 2, frames: int = 120,
                     wrong_until: int | None = None) -> tuple[int | None, list[int]]:
    """An oracle stand-in for a quit raised on an enemy hit's frame 0: STATE f is answered by keys the game applies at
    f + lead (the harness's 2-frame lead), the gate is closed until open_at (probe P7: 15 frames after an enemy hit),
    and a Pause edge (pressed now, not on the frame before) on an open frame pauses. gate_cue False: the STATE has no
    pause.blk (the cue unknown, the blind cadence). wrong_until: the STATE says closed until then although the gate is
    open from open_at (a wrong cue). Returns the pause frame and the frames whose applied mask held Pause."""
    m = _machine(emulate_quit=True)
    applied: dict[int, int] = {}
    paused_f, prev, held = None, 0, []
    P = 1 << BIT["pause"]
    for f in range(frames):
        mask = applied.get(f, 0)
        if mask & P:
            held.append(f)
        if paused_f is None and f >= open_at and mask & P and not prev & P:
            paused_f = f
        prev = mask
        if paused_f is not None:
            break
        closed = f < (open_at if wrong_until is None else wrong_until)
        s = _state(f, blk=gc.BLK_DISABLE_PAUSE | gc.BLK_TIME_SLOWED if closed else 0)
        if not gate_cue:
            del s["pause"]["blk"]
        k = to_mask(m.step(cues_from_state(s)), BIT)
        assert k & ~P == 0
        applied[f + lead] = k
    return paused_f, held


def test_oracle_gate_cue_puts_the_first_press_on_the_first_open_frame():
    """(a) of the quit-timeline round: a quit raised inside an enemy hit's 250 ms unpausable window. Blind (no gate
    cue), the 34 ms cadence (3 frames down, 3 up at 60 fps) makes edges at +2, +8, +14; the gate opens at +15 with
    the key still held, so the pause lands at +20. With the oracle's pause.blk the loop holds its press until the
    gate is seen open and the pause lands at the opening plus the lead, whatever the opening frame."""
    assert _oracle_hit_quit(False)[0] == 20
    for open_at in range(3, 30):
        blind, _ = _oracle_hit_quit(False, open_at)
        aware, held = _oracle_hit_quit(True, open_at)
        assert aware == open_at + 2, (open_at, aware)
        assert blind - open_at <= 5 and aware <= blind + 2, (open_at, blind, aware)
        assert all(f >= open_at + 2 for f in held)         # no press wasted into the closed gate
    # a cue that wrongly says closed: after gate_trust_s (1 s) the blind cadence resumes and the pause still lands
    paused, held = _oracle_hit_quit(True, open_at=15, wrong_until=600, frames=200)
    assert paused is not None and 60 <= paused <= 60 + 2 + 6 and min(held) >= 60
