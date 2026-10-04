"""run_episode's outcome around the kill (ssbot.train.episode): in mode "eval" a lethal hit in the same STATE as the
kill, or inside the encounter's post-clear window (the Forum: 4.5 s, until BattleScene has set hang04Battle), is
WOULD_DIE, not CLEAR; in mode "data" it is counted (lethal_after_clear) and the outcome stays CLEAR. Driven by a scripted
link that feeds the tap the way OracleLink's reader thread does."""
from dataclasses import replace

import pytest

from ssbot.train.encounters import BELL_BEAST, FORUM
from ssbot.train.episode import (CLEAR, QUIT, STUCK, WOULD_DIE, AttemptRecord, EpisodeConfig, live_threats, make_tap,
                                 run_episode)


class _Link:
    """STATEs in order: wait_state hands out the next one after feeding the subscribers (the tap)."""

    def __init__(self, states: list[dict]):
        self.states = states
        self.i = 0
        self.subs = []
        self.state: dict | None = None
        self.acts: list[tuple[int, int]] = []

    @property
    def frame(self) -> int:
        return self.state["f"] if self.state else 0

    def subscribe_state(self, fn) -> None:
        self.subs.append(fn)

    def wait_state(self, pred=None, newer_than: int | None = None, timeout_s: float = 2.0) -> dict:
        while self.i < len(self.states):
            s = self.states[self.i]
            self.i += 1
            self.state = s
            for fn in self.subs:
                fn(s)
            if (newer_than is None or s["f"] > newer_than) and (pred is None or pred(s)):
                return s
        raise TimeoutError("script exhausted")

    def rpc(self, method: str, **kw):
        return {"seed": kw.get("seed")} if method == "randomize_start" else {}

    def act(self, f: int, m: int, hold_frames: int = 0, flags: int = 0) -> None:   # OracleLink.act (ACTION flags)
        self.acts.append((f, m))


class _Policy:
    def __init__(self):
        self.calls: list[int] = []

    def reset(self, rng, enc) -> None:
        pass

    def act(self, s: dict, tap) -> int:
        self.calls.append(s["f"])
        return 0


def _st(f: int, scene: str, ev=()) -> dict:
    return {"f": f, "game": {"scene": scene, "paused": False},
            "hero": {"pos": [30.0, 4.57, 0.0], "hero_accepting_input": True}, "ev": list(ev)}


def _ev(k: str, **d) -> dict:
    return {"k": k, "d": d}


def _script(enc, kill_f: int, kill_ev: dict, lethal_at: int | None, n: int = 600) -> list[dict]:
    """Settle frames, a wake, a fight, the kill at kill_f, a lethal hit at lethal_at (None: none), frames after."""
    out = [_st(f, enc.scene) for f in range(1, 15)]
    for f in range(15, n):
        ev = []
        if f == 20:
            ev.append(kill_ev["wake"])
        if f == kill_f:
            ev.append(kill_ev["kill"])
        if f == lethal_at:
            ev.append(_ev("would_die", src="Song Heavy Sentry", dmg=2))
        out.append(_st(f, enc.scene, ev))
    return out


def _intro(ctx) -> int:
    while ctx.tap.wake_frame is None:
        ctx.link.wait_state(newer_than=ctx.link.frame)
    return ctx.tap.wake_frame


GAUNTLET_EVS = {"wake": _ev("fsm", obj="Song Pilgrim 01", fsm="Attack", to="Init", **{"from": None}),
                "kill": _ev("freeze", phase="start", type="EnemyBattleEndSlow")}
BOSS_EVS = {"wake": _ev("fsm", obj="Bone Beast", fsm="Control", to="Emerge", **{"from": "Dormant"}),
            "kill": _ev("fsm", obj="Bone Beast", fsm="Control", to="Death Broadcast", **{"from": "Stun"})}


def _run(enc, evs, mode: str, kill_f: int, lethal_at: int | None):
    enc = replace(enc, intro=_intro)
    link = _Link(_script(enc, kill_f, evs, lethal_at))
    tap = make_tap(link, enc)
    pol = _Policy()
    rec = AttemptRecord(unit="t", stage="t", profile="t", build="t", code_rev=None, config_fp="", start_kind="t",
                        mode=mode, seed=1)
    run_episode(link, enc, tap, pol, EpisodeConfig(mode=mode, seed=1, facing=None), rec)
    return rec, pol


def test_eval_lethal_in_the_kill_state_is_would_die():
    rec, _ = _run(FORUM, GAUNTLET_EVS, "eval", kill_f=100, lethal_at=100)
    assert rec.outcome == WOULD_DIE and rec.reason == "lethal hit at/after the kill"


def test_eval_lethal_in_the_forum_post_clear_window_is_would_die():
    # 200 frames after the freeze: inside the Forum's 4.5 s window, past the old 60-frame one
    rec, _ = _run(FORUM, GAUNTLET_EVS, "eval", kill_f=100, lethal_at=300)
    assert rec.outcome == WOULD_DIE and rec.f_end == 300


def test_eval_clear_runs_the_whole_window_and_keeps_the_gauntlet_policy_playing():
    rec, pol = _run(FORUM, GAUNTLET_EVS, "eval", kill_f=100, lethal_at=None)
    assert rec.outcome == CLEAR and rec.f_end == 100 + round(FORUM.post_clear_s * 60)
    assert sum(1 for f in pol.calls if f > 100) >= 250        # acted through the window, not zeros
    assert rec.lethal_after_clear == 0


def test_data_mode_counts_a_lethal_hit_after_the_kill_and_stays_clear():
    rec, _ = _run(FORUM, GAUNTLET_EVS, "data", kill_f=100, lethal_at=300)
    assert rec.outcome == CLEAR and rec.would_die == 1 and rec.lethal_after_clear == 1


def test_boss_eval_lethal_after_the_kill_is_would_die():
    rec, pol = _run(BELL_BEAST, BOSS_EVS, "eval", kill_f=100, lethal_at=130)
    assert rec.outcome == WOULD_DIE
    # no damage source after the kill: the tail ends 2 s of game time later (dt missing: 1/60 a frame); a policy
    # without act_after_clear sends zeros meanwhile
    rec, pol = _run(BELL_BEAST, BOSS_EVS, "eval", kill_f=100, lethal_at=None)
    assert rec.outcome == CLEAR and rec.tail_end == "quiet" and 220 <= rec.f_end <= 221
    assert not any(f > 100 for f in pol.calls) and rec.tail_threat_s is None and rec.kill_s == round(80 / 60, 2)


# ---- the post-kill tail (Encounter.tail_quiet_s; DESIGN §3.5.7) -------------------------------------------------------

def _bell(state: str = "Launched Up", on: bool = True, hidden: bool = False, tk: str = "BoneBeast AtkBell L") -> dict:
    return {"iid": 9, "type_key": tk, "src": 2, "hidden": hidden, "fsms": [{"name": "Control", "state": state}],
            "colliders": [{"enabled": on, "damage": {"eff": 2, "can_cause_damage": True}}]}


def _tail_script(live_until: int, kill_f: int = 100, n: int = 1200, slow: int = 0,
                 extra: dict | None = None) -> list[dict]:
    """slow: real frames of the death slow motion after the kill (0.05x game time)."""
    out = []
    for s in _script(BELL_BEAST, kill_f, BOSS_EVS, None, n):
        s["dt"] = (0.05 if kill_f < s["f"] <= kill_f + slow else 1.0) / 60.0
        if kill_f <= s["f"] <= live_until:
            s["ents"] = [_bell()]
        for e in (extra or {}).get(s["f"], ()):
            s["ev"].append(e)
        out.append(s)
    return out


class _Actor(_Policy):
    act_after_clear = True

    def __init__(self, quit_at: int | None = None):
        super().__init__()
        self.quit_at = quit_at
        self.episode_outcome = None
        self.outcome_reason = None

    def act(self, s: dict, tap) -> int:
        if self.quit_at is not None and s["f"] >= self.quit_at:
            self.episode_outcome, self.outcome_reason = "QUIT", "Q1: h 1"
        return super().act(s, tap)


def _run_tail(states: list[dict], pol=None, enc=BELL_BEAST, mode: str = "eval"):
    enc = replace(enc, intro=_intro)
    link = _Link(states)
    tap = make_tap(link, enc)
    pol = pol or _Actor()
    rec = AttemptRecord(unit="t", stage="t", profile="t", build="t", code_rev=None, config_fp="", start_kind="t",
                        mode=mode, seed=1)
    run_episode(link, enc, tap, pol, EpisodeConfig(mode=mode, seed=1, facing=None), rec)
    return rec, pol


def test_tail_lasts_until_two_quiet_seconds_after_the_last_live_source_and_the_policy_plays_on():
    rec, pol = _run_tail(_tail_script(live_until=400))
    assert rec.outcome == CLEAR and rec.tail_end == "quiet"
    assert 520 <= rec.f_end <= 521                                     # 2 s after frame 400
    assert rec.tail_threat_s == pytest.approx(300 / 60) and rec.tail_threats == {"BoneBeast AtkBell L": 301}
    assert all(f in pol.calls for f in range(101, 500))                # acted every frame of the tail
    assert rec.f_kill == 100 and rec.kill_s == round(80 / 60, 2)


def test_tail_counts_game_time_so_the_slow_motion_stretches_it():
    rec, _ = _run_tail(_tail_script(live_until=100, slow=100))
    # 100 slow frames are 5 game frames: 115 more at 1x
    assert rec.outcome == CLEAR and rec.tail_end == "quiet" and 314 <= rec.f_end <= 316


def test_a_hit_in_the_tail_is_counted_and_a_quit_in_it_is_a_quit():
    hit = {200: [_ev("damage", source="Boss Scene/BoneBeast AtkBell L", amount=2),
                 _ev("hp", delta=-2, h=3)]}
    rec, _ = _run_tail(_tail_script(live_until=300, extra=hit))
    assert rec.outcome == CLEAR and rec.tail_hits == 1 and rec.tail_hp_lost == 2 and rec.hits == 1
    rec, _ = _run_tail(_tail_script(live_until=300, extra=hit), pol=_Actor(quit_at=210))
    assert rec.outcome == QUIT and rec.reason.startswith("quit after the kill") and rec.f_end == 210


def test_a_lethal_hit_in_the_tail_is_would_die():
    rec, _ = _run_tail(_tail_script(live_until=600, extra={500: [_ev("would_die", src="AtkBell", dmg=2)]}))
    assert rec.outcome == WOULD_DIE and rec.f_end == 500


def test_a_tail_that_never_goes_quiet_is_stuck():
    rec, _ = _run_tail(_tail_script(live_until=5000, n=5000))
    assert rec.outcome == STUCK and "post-kill tail" in rec.reason
    assert rec.f_end == pytest.approx(100 + BELL_BEAST.tail_max_s * 60, abs=2)


def test_the_fixed_window_without_a_tail():
    rec, _ = _run_tail(_tail_script(live_until=400), enc=replace(BELL_BEAST, tail_quiet_s=None))
    assert rec.outcome == CLEAR and rec.f_end == 160 and rec.tail_end is None


def test_live_threats():
    armed = BELL_BEAST.tail_armed
    assert live_threats([_bell()], armed) == ["BoneBeast AtkBell L"]
    assert live_threats([_bell(on=False, state="Dormant")], armed) == []
    assert live_threats([_bell(hidden=True)], armed) == []
    # a drop bell in its Antic hurts later; one the boss's death cancelled never does
    assert live_threats([_bell(on=False, state="Antic", tk="BoneBeast DropBell M2")], armed) == ["BoneBeast DropBell M2"]
    assert live_threats([_bell(on=False, state="Cancel", tk="BoneBeast DropBell M2")], armed) == []
    off = _bell()
    off["colliders"][0]["damage"]["can_cause_damage"] = False
    assert live_threats([off], armed) == []
    # eff -1: a multi-wounder source whose amount lives in its FSM (EntityExporter) is live like any other
    multi = _bell(tk="Clapper Rune")
    multi["colliders"][0]["damage"]["eff"] = -1
    assert live_threats([multi], armed) == ["Clapper Rune"]
    zero = _bell()
    zero["colliders"][0]["damage"]["eff"] = 0
    assert live_threats([zero], armed) == []
