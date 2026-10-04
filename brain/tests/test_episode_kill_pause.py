"""run_episode's kill path when the supervisor's pause began before the kill (pause stress: a quit trigger 1-3 frames
before a committed blow): the boss dies while the pause machine owns the keys, its quit completes, and the attempt is
CLEAR "quit after the kill", not the AttemptRecord's default HARNESS_FAIL (chunk 20261002_232051 ep 26 and 39)."""
from types import SimpleNamespace

from ssbot.train import episode as ep


class FakeLink:
    def __init__(self):
        self.frame = 1000
        self.acts: list[tuple[int, int, int]] = []

    def _state(self) -> dict:
        return {"f": self.frame, "game": {"scene": "Bone_05", "paused": False},
                "hero": {"hero_accepting_input": True, "pos": [80.0, 3.5]}}

    @property
    def state(self) -> dict:
        return self._state()

    def wait_state(self, cond=None, newer_than=None, timeout_s=2.0) -> dict:
        self.frame += 1
        return self._state()

    def rpc(self, _name, /, timeout_s=10.0, **args):
        return {}

    def act(self, target, mask, hold_frames=0, flags=0):
        self.acts.append((target, mask, flags))


class FakeTap:
    def __init__(self, link: FakeLink, death_at: int):
        self.link, self.death_at = link, death_at
        self.reset()

    def reset(self):
        self.wake_frame = 1000
        self.lethal = []
        self.damage, self.hp, self.control_log = [], [], []

    @property
    def death_frame(self):
        return self.death_at if self.link.frame >= self.death_at else None

    def lethal_frames(self):
        return []


class Policy:
    """Owns the pause from frame `trigger` on (the injected fault), quits at frame `quit_at`."""

    def __init__(self, link: FakeLink, trigger: int, quit_at: int):
        self.link, self.trigger, self.quit_at = link, trigger, quit_at
        self.pause_owned = False
        self.episode_outcome = None
        self.outcome_reason = None
        self.real_quit_active = False

    def reset(self, rng, enc):
        pass

    def act(self, s, tap=None):
        f = s["f"]
        self.pause_owned = f >= self.trigger
        if f >= self.quit_at:
            self.episode_outcome, self.outcome_reason = "QUIT", "QUIT: QF: injected fault (kill)"
        return 0

    def stats(self):
        return {}


def test_a_pause_begun_before_the_kill_ends_clear():
    link = FakeLink()
    enc = SimpleNamespace(scene="Bone_05", savestate="x", boss_type="Bone Beast", timebox_s=240.0,
                          intro=lambda ctx: None)
    tap = FakeTap(link, death_at=1100)
    pol = Policy(link, trigger=1098, quit_at=1160)
    rec = ep.AttemptRecord(unit="BellBeast", stage="TRAIN", profile="TRAIN", build="1.0.30000", code_rev=None,
                           config_fp="x", start_kind="savestate", mode="eval", seed=1)
    cfg = ep.EpisodeConfig(mode="eval", seed=1, hp=None, silk=None, dx=None, facing=None, wait_frames=(0, 0))
    orig = ep.wait_settled
    ep.wait_settled = lambda link, scene, **kw: link.wait_state()
    try:
        ep.run_episode(link, enc, tap, pol, cfg, rec)
    finally:
        ep.wait_settled = orig
    assert rec.outcome == ep.CLEAR and rec.reason.startswith("quit after the kill"), (rec.outcome, rec.reason)


def test_with_the_post_kill_tail_a_quit_after_the_kill_is_a_quit():
    """Encounter.tail_quiet_s (DESIGN §3.9.4): the encounter ends only after the tail's quiet, so the same quit is QUIT."""
    link = FakeLink()
    enc = SimpleNamespace(scene="Bone_05", savestate="x", boss_type="Bone Beast", timebox_s=240.0,
                          intro=lambda ctx: None, tail_quiet_s=2.0, tail_max_s=15.0, tail_armed=())
    tap = FakeTap(link, death_at=1100)
    pol = Policy(link, trigger=1098, quit_at=1160)
    rec = ep.AttemptRecord(unit="BellBeast", stage="TRAIN", profile="TRAIN", build="1.0.30000", code_rev=None,
                           config_fp="x", start_kind="savestate", mode="eval", seed=1)
    cfg = ep.EpisodeConfig(mode="eval", seed=1, hp=None, silk=None, dx=None, facing=None, wait_frames=(0, 0))
    orig = ep.wait_settled
    ep.wait_settled = lambda link, scene, **kw: link.wait_state()
    try:
        ep.run_episode(link, enc, tap, pol, cfg, rec)
    finally:
        ep.wait_settled = orig
    assert rec.outcome == ep.QUIT and rec.reason.startswith("quit after the kill"), (rec.outcome, rec.reason)
