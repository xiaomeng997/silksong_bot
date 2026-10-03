"""run_episode's outcome around the kill (ssbot.train.episode): in mode "eval" a lethal hit in the same STATE as the
kill, or inside the encounter's post-clear window (the Forum: 4.5 s, until BattleScene has set hang04Battle), is
WOULD_DIE, not CLEAR; in mode "data" it is counted (lethal_after_clear) and the outcome stays CLEAR. Driven by a scripted
link that feeds the tap the way OracleLink's reader thread does."""
from dataclasses import replace

from ssbot.train.encounters import BELL_BEAST, FORUM
from ssbot.train.episode import CLEAR, WOULD_DIE, AttemptRecord, EpisodeConfig, make_tap, run_episode


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

    def act(self, f: int, m: int, hold_frames: int = 0) -> None:
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
    rec, pol = _run(BELL_BEAST, BOSS_EVS, "eval", kill_f=100, lethal_at=None)
    assert rec.outcome == CLEAR and rec.f_end == 160 and not any(f > 100 for f in pol.calls)
