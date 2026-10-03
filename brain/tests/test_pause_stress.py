"""Pause stress test pieces (ssbot.train.hit_injection, ssbot.tools.pause_stress): the injector waits for its kind of
moment and then asks hurt.special for a hit down to 1 HP, re-arms when the game did not take it, never injects while
the supervisor's pause machine owns the keys, and leaves the wrapped policy's interface intact; the trial summary
reads a synthetic recording (the hit, the closed gate, the pause, the menu keys, the main menu) the way the run's
recordings will be read."""
import random
from concurrent.futures import Future

from ssbot.ipc.framing import BUTTONS
from ssbot.tools import pause_stress as ps
from ssbot.train.hit_injection import HitInjector


class FakeLink:
    def __init__(self, take: bool = True):
        self.calls: list[dict] = []
        self.take = take

    def rpc_async(self, name, **args):
        self.calls.append({"name": name, **args})
        fut = Future()
        hp = args["amount"] + 1                       # the injector asks for HP - 1
        fut.set_result({"frame": 1000 + len(self.calls), "hp_before": hp,
                        "hp_after": hp - args["amount"] if self.take else hp, "take_health_calls": int(self.take)})
        return fut


class Inner:
    def __init__(self):
        self.pause_owned = False
        self.episode_outcome = None
        self.acts = 0

    def reset(self, rng, enc):
        rng.random()

    def act(self, s, tap=None):
        self.acts += 1
        return 7

    def stats(self):
        return {"view": "oracle"}


def _s(f: int, hp: int = 5, hs: int = 1, vy: float = 0.0, clip: str = "Idle", paused: bool = False) -> dict:
    return {"f": f, "game": {"paused": paused}, "hero": {"health": hp, "hero_state": hs, "vel": [0.0, vy],
                                                          "facing": 1, "anim": {"clip": clip}}}


def _injector(kind: str, take: bool = True, fault: str = "hit", offset: int = 0,
              inner=None) -> tuple[HitInjector, FakeLink]:
    inj = HitInjector(inner or Inner(), p_event=0.0, min_s=1.0, boss_type="Bone Beast")
    link = FakeLink(take)
    inj.attach(link)
    inj.reset(random.Random(1), None)
    inj.kind = inj.log["kind"] = kind
    inj.fault = inj.log["fault"] = fault
    inj.offset = inj.log["offset"] = offset
    return inj, link


def test_injector_waits_for_its_moment_then_takes_the_hero_to_one_hp():
    inj, link = _injector("rising")
    assert inj.act(_s(0)) == 7 and inj.pause_owned is False          # the wrapped policy's mask and attributes
    for f in range(1, 59):
        inj.act(_s(f, hs=3, vy=5.0))
    assert not link.calls                                             # min_s: not before the fight is under way
    inj.act(_s(60, hs=3, vy=-4.0))                                    # falling: not this episode's kind
    assert not link.calls
    inj.act(_s(61, hp=4, hs=3, vy=4.0))
    assert link.calls == [{"name": "hurt.special", "kind": "damage", "amount": 3, "hazard": "ENEMY", "side": "left"}]
    for f in range(62, 200):
        inj.act(_s(f, hs=3, vy=4.0))
    st = inj.stats()
    assert len(link.calls) == 1 and st["view"] == "oracle" and st["inject"]["kind"] == "rising"
    assert st["inject"]["replies"][0]["hp_after"] == 1


def test_injector_rearms_when_the_game_does_not_take_the_hit_and_respects_an_owned_pause():
    inj, link = _injector("apex", take=False)
    for f in range(0, 400):
        inj.act(_s(f, hs=3, vy=0.5))
    assert len(link.calls) == 1 + inj.max_retries                     # i-frames: retried, then given up
    inj, link = _injector("apex")
    inj.inner.pause_owned = True
    for f in range(0, 200):
        inj.act(_s(f, hs=3, vy=0.5))
    assert not link.calls                                             # never into a pause under way
    inj.inner.pause_owned = False
    for f in range(200, 210):
        inj.act(_s(f, hp=1, hs=3, vy=0.5))
    assert not link.calls                                             # HP 1: nothing left to take down to 1


def test_bit_table_matches_the_framing_buttons():
    assert ps.KEYS == BUTTONS


def _rec(f, *, blk=0, paused=False, gs=4, latched=0, ev=(), q=None, ready=None, clip="Airborne") -> dict:
    """ready: the pause menu accepts input (ui PAUSED, not fading, accepting input); default: paused and blk has no
    NOT_ACCEPTING_INPUT bit."""
    ready = paused and not blk & 32 if ready is None else ready
    return {"f": f, "q": q if q is not None else f * 166_667, "ev": list(ev),
            "hero": {"hero_state": 3, "vel": [0.0, -3.0], "anim": {"clip": clip}, "cstate": None},
            "act": {"hf": {"latched": latched}},
            "game": {"paused": paused, "gs": gs, "scene": "Bone_05", "ui": 5 if paused else 0,
                     "fading": not ready, "menu": 7},
            "pause": {"blk": blk if ready or not paused else blk | 32}, "ts": 1.0}


def test_trial_measures_latency_keys_unpauses_and_the_menu():
    P, ENTER, JUMP = ps.BIT["pause"], ps.BIT["enter"], ps.BIT["jump"]
    states = []
    for f in range(90, 400):
        if f < 100:
            states.append(_rec(f, latched=JUMP))
        elif f < 115:
            states.append(_rec(f, blk=3, ev=[{"k": "damage", "d": {"amount": 4}}] if f == 100 else ()))
        elif f < 117:
            states.append(_rec(f, latched=P if f == 116 else 0))
        elif f < 300:
            states.append(_rec(f, blk=64, paused=True, latched=P if f < 119 else ENTER if f in (200, 201) else 0))
        else:
            states.append(_rec(f, paused=True, gs=1))
    row = {"outcome": "QUIT", "reason": "QUIT: Q1", "policy": {
        "first_pending_f": 100, "inject": {"kind": "falling", "offset": 0, "sent": [{"f": 99}],
                                           "replies": [{"frame": 100, "hp_before": 5, "hp_after": 1,
                                                        "take_health_calls": 1}]},
        "real_quit": {"armed": True, "wrong_submits": 0, "unexpected_unpauses": 0}}}
    t = ps.trial(row, states, [])
    assert t["took"] and t["hit_f"] == 100 and t["airborne"] and t["first_pausable"] == 15 and t["paused"] == 17
    assert t["latency"] == 2 and t["pending"] == 0 and t["foreign_key_frames_paused"] == 0
    assert t["pause_key_frames_paused"] == 2 and t["unpauses"] == 0 and t["main_menu"]
    assert t["to_menu_frames"] == 300 - 117 and abs(t["to_menu_s"] - 183 * 0.0166667) < 1e-3
    # a jump latched while paused, and the world running again before the main menu: both counted
    states2 = [dict(s) for s in states]
    for s in states2:
        if 150 <= s["f"] < 152:
            s["act"] = {"hf": {"latched": JUMP}}
        if s["f"] == 160:
            s["game"] = {"paused": False, "gs": 4, "scene": "Bone_05"}
    assert t["foreign_edges_paused"] == 0 and t["last_foreign_edge"] is None
    t2 = ps.trial(row, states2, [])
    assert t2["foreign_key_frames_paused"] == 2 and t2["unpauses"] == 1
    assert t2["foreign_edges_paused"] == 1 and t2["last_foreign_edge"] == 150 - 117
    s = ps.summarize([t, t2])
    assert s["hits_taken"] == 2 and s["unintended_unpauses"] == 1 and s["foreign_keys_while_paused"] == 2
    assert s["latency_frames"]["max"] == 2 and s["main_menu"] == 2


# ---- fault kinds (trigger / menu) and hard moments -------------------------------------------------------------

class FakeSc:
    def __init__(self):
        self.faults: list[tuple[str, str]] = []

    def inject_fault(self, tid="QF", why=""):
        self.faults.append((tid, why))


class InnerSc(Inner):
    def __init__(self):
        super().__init__()
        self.sc = FakeSc()


def _names() -> list[str]:
    from ssbot.knowledge.kinematics import cstate_names
    return cstate_names()


def _cs_words(**flags) -> list[int]:
    from ssbot.tools.cstate import encode
    return encode(flags, _names())


def _fs(f: int, *, cs=None, lat: int = 0, clip: str = "Idle", boss_hp=None, ev=(), hp: int = 5) -> dict:
    s = _s(f, hp=hp, clip=clip)
    s["hero"]["cstate"] = _cs_words(**(cs or {}))
    s["act"] = {"hf": {"latched": lat}}
    s["ev"] = list(ev)
    if boss_hp is not None:
        s["ents"] = [{"type_key": "Bone Beast", "hp": boss_hp}]
    return s


def test_trigger_fault_fires_at_the_bounce_onset_plus_its_offset_without_a_hit():
    inner = InnerSc()
    inj, link = _injector("bounce", fault="trigger", offset=2, inner=inner)
    for f in range(0, 100):
        inj.act(_fs(f))
    assert not inner.sc.faults
    for f in range(100, 110):
        inj.act(_fs(f, cs={"downSpikeBouncing": True}))
    assert len(inner.sc.faults) == 1 and inner.sc.faults[0][0] == "QF" and not link.calls
    st = inj.stats()["inject"]
    assert st["trigger_f"] == 102 and st["moments"] == [["bounce", 100]] and st["fault"] == "trigger"


def test_kill_trigger_goes_before_a_committed_needle_kill():
    """A Silkspear thrown with the boss at <= 15 HP hits 18-20 frames after the press (run 20261002_190611): the
    trigger goes at press + 19 + offset; a hit fault waits for the kill itself."""
    from types import SimpleNamespace
    inner = InnerSc()
    inj, link = _injector("kill", fault="trigger", offset=-2, inner=inner)
    for f in range(0, 100):
        inj.act(_fs(f, boss_hp=10))
    for f in range(100, 130):
        inj.act(_fs(f, boss_hp=10, lat=1 << 6 if f < 104 else 0))         # quickcast latched from 100
    assert not inner.sc.faults                                            # the planner did not score it
    inner = InnerSc()
    inner.planner_last = SimpleNamespace(attack=(4, 2, [0.0] * 4))         # its first scored hit: a Silkspear
    inj, link = _injector("kill", fault="trigger", offset=-2, inner=inner)
    for f in range(0, 100):
        inj.act(_fs(f, boss_hp=10))
    for f in range(100, 130):
        inj.act(_fs(f, boss_hp=10, lat=1 << 6 if f < 104 else 0))
    assert inj.stats()["inject"]["trigger_f"] == 100 + 19 - 2 and len(inner.sc.faults) == 1
    inj, link = _injector("kill", fault="hit", offset=0, inner=InnerSc())
    for f in range(0, 140):
        kill = [{"k": "hit", "d": {"type_key": "Bone Beast", "hp_after": 0, "dead": True}}] if f == 130 else ()
        inj.act(_fs(f, boss_hp=10, lat=1 << 6 if f == 100 else 0, ev=kill))
    assert len(link.calls) == 1 and inj.log["sent"][0]["f"] == 130


def test_menu_fault_triggers_and_hits_on_one_tick_and_hit_faults_rearm_on_the_next_bounce():
    inner = InnerSc()
    inj, link = _injector("menu", fault="menu", inner=inner)
    for f in range(0, 80):
        inj.act(_fs(f))
    assert not link.calls and not inner.sc.faults                     # no planner key latched yet
    inj.act(_fs(80, lat=1 << 20))
    assert len(link.calls) == 1 and len(inner.sc.faults) == 1 and inj.log["trigger_f"] == 80
    inj, link = _injector("cast", fault="hit", offset=0, take=False)
    for f in range(0, 300):
        inj.act(_fs(f, clip="NeedleThrow AnticG" if f % 50 < 5 else "Idle"))   # a cast every 50 frames
    assert [r["f"] for r in inj.log["sent"]] == [100, 150, 200, 250]   # refused (i-frames): re-armed each cast
    kinds = set()
    for seed in range(400):                                            # bounce faults are triggers only
        inj = HitInjector(InnerSc(), p_event=1.0)
        inj.reset(random.Random(seed), None)
        kinds.add((inj.kind, inj.fault))
    assert ("bounce", "hit") not in kinds and ("bounce", "trigger") in kinds
    assert not any(k == "clash" for k, _ in kinds) and ("cast", "hit") in kinds and ("kill", "trigger") in kinds


def test_trial_of_a_trigger_fault_counts_game_keys_on_menu_frames():
    """Trigger at 200 on the bounce onset's frame (+0): special. The pause lands at 202 with the planner's right still
    latched on it (counted, also as the pause frame's keys), and an Up before the menu accepts input counts; Up /
    Enter after it does not."""
    P, R, UPK, ENTER = ps.BIT["pause"], ps.BIT["right"], ps.BIT["up"], ps.BIT["enter"]
    states = []
    for f in range(180, 400):
        if f < 202:
            s = _rec(f, latched=R)
        elif f < 300:
            lat = (P | R) if f == 202 else P if f < 205 else UPK if f in (206, 230) else ENTER if f == 240 else 0
            s = _rec(f, paused=True, blk=64, latched=lat, ready=f >= 210)
        else:
            s = _rec(f, paused=True, gs=1)
        s["hero"]["cstate"] = _cs_words(downSpikeBouncing=f >= 200)
        states.append(s)
    row = {"outcome": "QUIT", "reason": "QUIT: QF", "policy": {
        "first_pending_f": 200, "inject": {"kind": "bounce", "fault": "trigger", "offset": 0, "trigger_f": 200,
                                           "sent": [{"f": 200}], "replies": []},
        "real_quit": {"armed": True, "wrong_submits": 0, "unexpected_unpauses": 0, "key_waits": 0}}}
    t = ps.trial(row, states, _names())
    assert t["injected"] and t["fault_f"] == 200 and t["special"] == {"bounce": 0}
    assert t["press"] == 2 and t["paused"] == 2 and t["first_pausable"] == 0 and t["latency"] == 2
    assert t["pause_frame_keys"] == R and t["foreign_key_frames_paused"] == 2      # 202 (right), 206 (up, not ready)
    assert t["foreign_keys"] == {"right": 1, "up": 1}
    s = ps.summarize([t])
    assert s["special_share"] == 1.0 and s["pause_frame_with_game_keys"] == 1 and s["faults"] == {"trigger": 1}
    # the same pause without an injection (a gate QUIT): only with natural, from its first PAUSE_PENDING
    plain = {"outcome": "QUIT", "reason": "QUIT: Q6", "policy": {"first_pending_f": 200, "real_quit": None}}
    assert ps.trial(plain, states, _names()) is None
    tn = ps.trial(plain, states, _names(), natural=True)
    assert tn["kind"] == "natural" and tn["fault_f"] == 200 and tn["pause_frame_keys"] == R


def test_trial_of_a_menu_fault_counts_the_hit_next_to_the_first_press():
    P = ps.BIT["pause"]
    states = []
    for f in range(180, 400):
        dmg = [{"k": "damage", "d": {"amount": 4}}] if f == 201 else ()
        if f < 201:
            states.append(_rec(f))
        elif f < 202:
            states.append(_rec(f, ev=dmg, blk=1))                                         # the hit's disablePause
        elif f < 217:
            states.append(_rec(f, blk=1, latched=P if f in (202, 203, 204) else 0))      # the press dropped
        elif f < 300:
            states.append(_rec(f, paused=f >= 219, blk=64 if f >= 219 else 0, latched=P if f in (219, 220) else 0))
        else:
            states.append(_rec(f, paused=True, gs=1))
    row = {"outcome": "QUIT", "reason": "QUIT: QF", "policy": {
        "first_pending_f": 200, "inject": {"kind": "menu", "fault": "menu", "offset": 0, "trigger_f": 200,
                                           "sent": [{"f": 200}],
                                           "replies": [{"frame": 201, "hp_before": 5, "hp_after": 1,
                                                        "take_health_calls": 1}]},
        "real_quit": {"armed": True, "wrong_submits": 0, "unexpected_unpauses": 0}}}
    t = ps.trial(row, states, [])
    assert t["fault_f"] == 201 and t["special"] == {"menu": -1} and t["press"] == 1
    assert t["first_pausable"] == 16 and t["paused"] == 18 and t["latency"] == 2
    s = ps.summarize([t])
    assert s["special_share"] == 1.0 and s["special_share_without_menu"] == 0.0
