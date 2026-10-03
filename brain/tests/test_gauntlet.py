"""Gauntlet tracking (ssbot.train.gauntlet) on synthetic STATEs: the oracle's TypeKey, the BattleScene DecrementEnemy
replay over the Forum's 14 waves (overlapping waves 2, 4 and 9), the battle start from wave 0's spawn, the end from the
kill replay, the battle-end freeze or room.battles, and the gauntlet data policy picking live enemies."""
import random

from ssbot.ipc.framing import mask
from ssbot.train.data_policy import GauntletDataPolicy
from ssbot.train.encounters import FORUM, FORUM_WAVES
from ssbot.train.gauntlet import GauntletTap, WaveSim, type_key


class _Link:
    def __init__(self):
        self.subs = []

    def subscribe_state(self, fn):
        self.subs.append(fn)

    def feed(self, s):
        for fn in self.subs:
            fn(s)


def _ev(k, **d):
    return {"k": k, "d": d}


def test_type_key_matches_the_oracle():
    assert type_key("Song Reed (1)") == "Song Reed"
    assert type_key("Pilgrim 03 Song (1)") == "Pilgrim 03 Song"
    assert type_key("Song Pilgrim 03") == "Song Pilgrim 03"
    assert type_key("Bullet(Clone) (2)") == "Bullet"
    assert type_key("Wave 2 - Call Ally") == "Wave 2 - Call Ally"
    assert type_key("(3)") == "(3)"


def _kill_all(sim: WaveSim, f0: int = 100) -> list[int]:
    """Kill every enemy as soon as it is alive; returns the frames of the kills."""
    f = f0
    kills = []
    while not sim.done:
        f += 10
        sim.kill(f)
        kills.append(f)
    return kills


def test_wave_sim_runs_the_forum_waves_in_order():
    total = sum(len(w.enemies) for w in FORUM_WAVES)
    assert total == 28 and len(FORUM_WAVES) == 14
    sim = WaveSim(FORUM_WAVES)
    sim.start(100)
    kills = _kill_all(sim)
    assert sim.done and sim.end_frame == kills[-1]
    assert [i for i, _ in sim.starts] == list(range(14))
    assert len(kills) == total
    # wave index 2 (2 enemies, remainingEnemyToEnd 2) ends at once: wave 3 starts with it, on the same kill
    f2 = dict(sim.starts)[2] - round(FORUM_WAVES[2].start_delay_s * 60)
    f3 = dict(sim.starts)[3] - round(FORUM_WAVES[3].start_delay_s * 60)
    assert f2 == f3


def test_tap_start_waves_and_end_from_kills():
    link = _Link()
    tap = GauntletTap(link, FORUM)
    f = 1000
    link.feed({"f": f, "ev": [_ev("fsm", obj="Song Reed", fsm="Control", to="Idle")]})
    assert tap.wake_frame == f and tap.wave == 0
    n = 0
    while tap.death_frame is None and n < 40:
        f += 30
        n += 1
        link.feed({"f": f, "ev": [_ev("hit", ent=n, type_key="X", dead=True, src="WildSlash Enemy Damager")]})
    assert n == 28 and tap.death_frame == f and tap.end_source == "kills"
    summ = tap.summary()
    assert summ["wave_reached"] == 13 and summ["kills"]["n"] == 28
    assert summ["kills"]["by_src"] == {"WildSlash Enemy Damager": 28}
    # the same enemy reported dead twice counts once
    link.feed({"f": f + 1, "ev": [_ev("hit", ent=n, type_key="X", dead=True, src="Slash")]})
    assert tap.summary()["kills"]["n"] == 28


def test_tap_prefers_room_battles_and_the_end_freeze():
    link = _Link()
    tap = GauntletTap(link, FORUM)
    b = {"name": "Battle Scene", "id": 5, "wave": 0, "waves": 14, "started": False, "completed": False,
         "enemies": 0, "to_next": 0}
    link.feed({"f": 10, "room": {"battles": [dict(b)]}})
    assert tap.wake_frame is None
    link.feed({"f": 20, "room": {"battles": [dict(b, started=True)]}})
    link.feed({"f": 30, "room": {"battles": [dict(b, started=True, wave=1)]},
               "ev": [_ev("hit", ent=1, type_key="Song Reed", dead=True, src="Slash")]})
    assert tap.wake_frame == 20 and tap.waves == [(0, 20), (1, 30)]
    link.feed({"f": 40, "room": {"battles": [dict(b, completed=True, wave=13)]}})
    assert tap.death_frame == 40 and tap.end_source == "room.battles"
    assert tap.summary()["wave_source"] == "room.battles"

    tap2 = GauntletTap(_Link(), FORUM)
    tap2._on({"f": 5, "ev": [_ev("fsm", obj="Song Pilgrim 01", fsm="Attack", to="Idle")]})
    tap2._on({"f": 9, "ev": [_ev("freeze", phase="start", type="EnemyBattleEndSlow")]})
    assert tap2.death_frame == 9 and tap2.end_source == "freeze"


def test_tap_counts_state_entries_and_allies():
    link = _Link()
    tap = GauntletTap(link, FORUM)
    link.feed({"f": 1, "ev": [_ev("fsm", obj="Song Reed", fsm="Control", to="Idle")]})
    link.feed({"f": 2, "ev": [_ev("fsm", obj="Song Reed (1)", fsm="Control", to="Stab Antic")],
               "allies": [{"name": "Garmond Fighter", "active": True, "state": "Jump In"},
                          {"name": "Shakra Fighter", "active": True, "state": "Dormant"}]})
    assert tap.state_entries["Song Reed/Control/Stab Antic"] == 1
    assert tap.summary()["allies"] == {"Garmond Fighter": {"frames": 1, "first_t": round(1 / 60, 2)}}


def _state(enemies, hx=30.0):
    ents = [{"iid": i, "type_key": tk, "src": 1, "pos": [x, y, 0.0], "hp": 30, "is_dead": False, "fsms": []}
            for i, (tk, x, y) in enumerate(enemies)]
    return {"f": 1, "hero": {"pos": [hx, FORUM.floor_y, 0.0], "facing": 1, "health": 5, "silk": 0, "cstate": []},
            "ents": ents}


def test_gauntlet_policy_presses_toward_a_live_enemy_and_clings_left():
    pol = GauntletDataPolicy()
    pol.reset(random.Random(3), FORUM)
    pol.mode, pol.mode_left = "PRESS", 1000
    s = _state([("Song Reed", 40.0, FORUM.floor_y)])
    moves = [pol.act(s, None) & mask("left", "right") for _ in range(20)]
    assert all(m == mask("right") for m in moves)
    assert pol.stats()["targets"] == {"Song Reed": 20}
    # nobody alive: no chase; CLING walks to the left wall
    pol.mode, pol.mode_left, pol.wall = "CLING", 1000, -1
    moves = [pol.act(_state([]), None) & mask("left", "right") for _ in range(10)]
    assert all(m == mask("left") for m in moves)
