"""Pause loop and quit sequence (ssbot.safety.pause_quit) against a simulated game (tests/pause_sim.py): the G1 criteria
of DESIGN §3.7.5 (no unintended unpause, pressing stops within the 230 ms budget, pause within a few frames of the
gate opening) over randomized trials, then the menu paths: quit, greyed Quit, Patch 4 refusal, Continue + Submit."""
import random

from ssbot.ipc.framing import BIT
from ssbot.safety import game_codes as gc
from ssbot.safety import pause_quit as pq
from ssbot.safety.pause_quit import PauseCues, PauseQuit, PauseQuitConfig, cues_from_state, to_mask
from tests.pause_sim import PAUSE_ITEMS, PauseSim, SimConfig, run


def _machine(goal: str = pq.GOAL_QUIT, **cfg) -> PauseQuit:
    m = PauseQuit(PauseQuitConfig(**cfg))
    m.start(0.0, goal)
    return m


def _random_cfg(r: random.Random, seed: int, **over) -> SimConfig:
    closed = r.randint(0, 150)
    closures = []
    f = closed
    for _ in range(r.randint(0, 3)):
        f += r.randint(1, 40)
        n = r.randint(1, 25)
        closures.append((f, f + n))
        f += n
    vision = r.random() < 0.5
    kw = dict(seed=seed, gate_closed_frames=closed, closures=tuple(closures), input_lat=r.randint(1, 3),
              obs_lat=r.randint(0, 3), vision=vision, initial_highlight=r.choice(PAUSE_ITEMS),
              false_dim_at=r.randint(0, closed) if vision and r.random() < 0.2 else None)
    kw.update(over)
    return SimConfig(**kw)


def _open_since(cfg: SimConfig, f: int) -> int:
    """First frame of the open-gate stretch that contains frame f."""
    start = cfg.gate_closed_frames
    for a, b in cfg.closures:
        if b <= f:
            start = max(start, b)
    return start


def _held(m: PauseQuit) -> bool:
    return m.state == "HOLD" or m.done


def test_loop_randomized_never_unpauses_and_stops_within_budget():
    """10^4 trials (the G1 count): pause gate closed for 0-150 frames plus up to 3 more closures, input latency 1-3
    frames, observation latency 0-3 frames, frame jitter and 2 % long frames, oracle or vision cues (with false dimmer
    flashes in some vision trials)."""
    r = random.Random(7)
    worst_stop, worst_latency = 0.0, 0
    for seed in range(10_000):
        cfg = _random_cfg(r, seed)
        sim = PauseSim(cfg)
        m = _machine(pq.GOAL_PAUSE)
        res = run(m, sim, 900, until=lambda m, s: _held(m))
        assert m.outcome == pq.PAUSED, (seed, cfg, m.log[-5:])
        log = sim.log
        assert log.esc_unpauses == [], (seed, cfg)
        assert len(log.pauses) == 1, (seed, cfg, log)
        t_p = log.pauses[0]
        late = [s - t_p for s in res.press_starts if s >= t_p]
        stop = max(late, default=0.0)
        assert stop <= 0.23, (seed, cfg, late)
        assert all(d < 0.3 for d in log.pause_edges_while_paused), (seed, log.pause_edges_while_paused)
        # G1: pause within 6 frames of the gate opening (steady state <= 3: one press lands every 4 frames; the
        # first press is held longer when the first observations repeat a frame, the 30 ms floor). A false dimmer
        # cue costs at most one confirm window (0.15 s, 9 frames) of not pressing.
        latency = sim.paused_f - _open_since(cfg, sim.paused_f)
        assert latency <= (6 if m.false_cues == 0 else 6 + 10), (seed, cfg, latency)
        worst_stop, worst_latency = max(worst_stop, stop), max(worst_latency, latency)
    assert worst_stop < 0.1


def test_full_quit_randomized_reads_the_highlight_before_every_submit():
    r = random.Random(11)
    for seed in range(1000):
        cfg = _random_cfg(r, 10_000 + seed)
        sim = PauseSim(cfg)
        m = _machine()
        run(m, sim, 1500, until=lambda m, s: m.done)
        assert m.outcome == pq.QUIT, (seed, cfg, m.log[-5:])
        assert sim.log.submits == [("pause", "quit"), ("exit_prompt", "yes")], (seed, sim.log.submits)
        assert sim.log.esc_unpauses == [] and sim.log.continue_unpauses == []
        assert sim.gs == "MAIN_MENU"
        submits = [d for _, k, d in m.log if k == "submit"]
        assert submits == ["pause:quit", "exit_prompt:yes"]


def test_emulated_quit_ends_once_the_pause_is_confirmed():
    sim = PauseSim(SimConfig(gate_closed_frames=40))
    m = _machine(emulate_quit=True)
    run(m, sim, 400, until=lambda m, s: m.done)
    assert m.outcome == pq.QUIT_EMULATED
    assert m.quit_state_seen == pq.QUIT_AVAILABLE
    assert sim.log.submits == [] and sim.gs == "PAUSED"


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
    assert sim.log.submits == [("pause", "options"), ("options", "back"), ("pause", "quit"), ("exit_prompt", "yes")]
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
    run(m, sim, 1500, until=lambda m, s: m.state == "REFUSED")
    assert m.outcome == pq.REFUSED and m.alert
    assert sim.log.submits == [("pause", "quit"), ("exit_prompt", "yes")]
    res = run(m, sim, 300)
    assert m.state == "REFUSED" and sim.gs == "PAUSED" and not res.press_starts
    assert len(sim.log.submits) == 2 and sim.log.esc_unpauses == []
    assert m.request_unpause(sim.t)             # an explicit decision: No, then Continue
    run(m, sim, 900, until=lambda m, s: m.done)
    assert m.outcome == pq.UNPAUSED
    assert sim.log.submits[2:] == [("exit_prompt", "no"), ("pause", "continue")]
    assert sim.log.esc_unpauses == []


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


def test_false_dim_cue_resumes_the_loop():
    sim = PauseSim(SimConfig(gate_closed_frames=90, vision=True, false_dim_at=20, obs_lat=3, input_lat=3))
    m = _machine(pq.GOAL_PAUSE)
    res = run(m, sim, 600, until=lambda m, s: _held(m))
    assert m.false_cues == 1 and m.outcome == pq.PAUSED
    assert len(sim.log.pauses) == 1 and sim.log.esc_unpauses == []
    t_p = sim.log.pauses[0]
    assert max(s - t_p for s in res.press_starts if s >= t_p) <= 0.23


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


def test_tap_timing_two_frames_down_two_up_and_time_floor():
    m = _machine()
    keys = [m.step(PauseCues(t=i / 60, paused=False)) for i in range(12)]
    assert ["pause" in k for k in keys] == [True, True, False, False] * 3
    m = _machine()                                        # 240 fps: the 30 ms floor holds keys longer than 2 frames
    keys = [m.step(PauseCues(t=i / 240, paused=False)) for i in range(16)]
    assert ["pause" in k for k in keys] == [True] * 8 + [False] * 8


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
    c = cues_from_state(_state(14927, gc.GS_PAUSED, 5, 17, False, 64, extra={"sel": "quit", "quit_ok": False,
                                                                              "dim": 0.8}))
    assert c.highlight == "quit" and c.quit_state == pq.QUIT_GREYED and c.dim == 0.8
    c = cues_from_state(_state(5, blk=gc.BLK_MSG_CANVAS))
    assert c.menu == pq.M_OTHER and not c.paused
    s = _state(5)
    s["ev"] = [{"k": "hero_dead", "f": 5, "d": {}}]
    assert cues_from_state(s).dead


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
