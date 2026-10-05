"""Forum plan R2: the multi-enemy forecast (ssbot.combat.multi_forecast and its parts: enemy_tracker, enemy_tables,
projectiles, wave_tracker; ssbot.core.forum). Synthetic tables of one type (a Reed with a stab, a defence and its idle
family) for the walk, the placements and the queries; the static facts against the builder and the encounter; the
structurally absent moves; the vision-legal discipline; the Bell Beast wrap bit for bit on the fixture windows."""
import inspect
import json
import math

import numpy as np
import pytest

from ssbot.combat import enemy_tables as et
from ssbot.combat import multi_forecast as mfm
from ssbot.combat.enemy_tables import EnemyTables, TemplateStore, Tubes, coarsen, type_table
from ssbot.combat.enemy_tracker import EnemyTracker
from ssbot.combat.multi_forecast import MultiForecaster, walk
from ssbot.combat.projectiles import (PhysClock, bell_steps, pin_steps, HazardTracker, BOMB_DX,
                                      BOMB_LEAD_S)
from ssbot.combat.wave_tracker import WaveTracker
from ssbot.core.forum import ABSENT_FAMILIES, FORUM_TYPES, FORUM_WAVES, STRUCTURALLY_ABSENT
from ssbot.core.worldstate import (ORACLE, VISION_EQUIVALENT, DamageBox, E, EnemyKilled, Entity, Ev, Event,
                                   FsmTransition, HitDealt, PhasePost, Stamp, WorldState)
from ssbot.knowledge import hitbox_tables as hb

REED = "Song Reed"
BIN = hb.BIN_S


# ---- synthetic tables -------------------------------------------------------------------------------------------

def _tpl(key: str, boxes, frame: str = "anchor") -> hb.SpaceTimeTemplate:
    """A planner template from [(t0, t1, x0, y0, x1, y1)] boxes (template frame), +-1 bin and the hero hurtbox."""
    acc = hb.TemplateAccumulator(key, frame)
    for t0, t1, x0, y0, x1, y1 in boxes:
        for b in range(int(round(t0 / BIN)), int(round(t1 / BIN)) + 1):
            acc.add(b * BIN, np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64))
    t = acc.finish()
    return t.dilated(rx=hb.HERO_HALF_U[0], ry=hb.HERO_HALF_U[1], t_bins=1, key=key)


def _reed_table(extra_absent: bool = False) -> dict:
    """A behaviour JSON of a Reed: idle "Alert", stab (Stab Pos -> Stab 1 -> Stab Recover), defence (Defend Start ->
    Defend, a multi-hit counter family). extra_absent: an Envoy-like structurally absent start in it too."""
    dwell = {"Alert": (0.2, 0.5), "Stab Pos": (0.1, 0.1), "Stab 1": (0.2, 0.3), "Stab Recover": (0.1, 0.2),
             "Defend Start": (0.1, 0.1), "Defend": (0.5, 1.0)}
    succ = {"Alert": ["Stab Pos", "Defend Start", "Death"], "Stab Pos": ["Stab 1"], "Stab 1": ["Stab Recover"],
            "Stab Recover": ["Alert"], "Defend Start": ["Defend"], "Defend": ["Alert"]}
    edges = [{"from": a, "to": b, "p": 1.0 / len(v)} for a, v in succ.items() for b in v]
    d = {"spec": {"attack_starts": {"Stab Pos": "RE_STAB", "Defend Start": "RE_DEFEND"},
                  "decision_states": ["Alert"]},
         "attacks": {"RE_STAB": {"states": ["Stab Pos", "Stab 1", "Stab Recover"], "start_states": ["Stab Pos"],
                                 "state_entry_s": {"Stab Pos": {"min": 0, "max": 0, "n": 9},
                                                   "Stab 1": {"min": 0.1, "max": 0.1, "n": 9}},
                                 "hitboxes": [{"state": "Stab 1", "source": "Song Reed:box", "dmg": [1]}]},
                     "RE_DEFEND": {"states": ["Defend Start", "Defend"], "start_states": ["Defend Start"],
                                   "state_entry_s": {}, "hitboxes": [{"state": "Defend", "source": "Song Reed:box",
                                                                      "dmg": [1]}]},
                     "RE_IDLE": {"states": ["Alert"], "start_states": ["Alert"], "state_entry_s": {},
                                 "hitboxes": []}},
         "dwell_s": {s: {"min": a, "max": b} for s, (a, b) in dwell.items()},
         "support_transitions": succ, "graph": {"edges": edges}}
    if extra_absent:
        d["spec"]["attack_starts"]["Point Start"] = "MA_POINT"
        d["attacks"]["MA_POINT"] = {"states": ["Point Start"], "start_states": ["Point Start"], "state_entry_s": {},
                                    "hitboxes": []}
        succ["Alert"].append("Point Start")
        d["dwell_s"]["Point Start"] = {"min": 0.1, "max": 0.2}
    return d


BODY = (-0.5, -1.0, 0.5, 1.0)


def _templates() -> dict:
    T = {}
    for st, t1 in (("Stab Pos", 0.15), ("Stab Recover", 0.25)):
        T[f"support/RE_STAB/{st}/anchor"] = _tpl(f"support/RE_STAB/{st}/anchor", [(0.0, t1, *BODY)])
    T["support/RE_STAB/Stab 1/anchor"] = _tpl("support/RE_STAB/Stab 1/anchor",
                                              [(0.0, 0.3, *BODY), (0.05, 0.3, 1.0, -0.5, 3.0, 0.5)])
    T["support/RE_STAB/_tail/anchor"] = _tpl("support/RE_STAB/_tail/anchor", [(0.0, 0.05, *BODY)])
    T["support/RE_STAB/anchor"] = _tpl("support/RE_STAB/anchor", [(0.0, 0.7, *BODY), (0.1, 0.4, 1.0, -0.5, 3.0, 0.5)])
    T["support/RE_DEFEND/Defend Start/anchor"] = _tpl("support/RE_DEFEND/Defend Start/anchor", [(0.0, 0.15, *BODY)])
    T["support/RE_DEFEND/Defend/anchor"] = _tpl("support/RE_DEFEND/Defend/anchor", [(0.0, 1.05, -1.0, -1.0, 1.0,
                                                                                         1.0)])
    T["support/RE_IDLE/Alert/anchor"] = _tpl("support/RE_IDLE/Alert/anchor", [(0.0, 0.55, *BODY)])
    return T


def _tables(extra_absent: bool = False) -> EnemyTables:
    tt = type_table(_reed_table(extra_absent), FORUM_TYPES[REED])
    store = EnemyTables._store([_templates()])
    tubes = Tubes({REED: [0.0] + [0.05 * k for k in range(1, 41)]}, {REED: 50.0}, {REED: BODY})
    chains = {"Song Reed/ParrySlash Hit": (2, 2)}
    return EnemyTables({REED: tt}, store, tubes, {}, True, "synthetic", chains)


def _ent(iid, x, y, state=None, tin=0.0, flip=False, box=None, tk=REED, hidden=False, hp=None):
    boxes = [] if box is None else [DamageBox(poly=[(box[0], box[1]), (box[2], box[1]), (box[2], box[3]),
                                                    (box[0], box[3])], active=True)]
    return Entity(id=iid, type_key=E(tk), pos=E((x, y)), vel=E((0.0, 0.0)), pos_transform=(x, y), flip_x=flip,
                  fsm=[("Control", state, tin)] if state else None, dmg_boxes=boxes, hidden=hidden,
                  hp_est=None if hp is None else E(float(hp)),
                  body_polys=[[(x - 0.5, y - 1.0), (x + 0.5, y - 1.0), (x + 0.5, y + 1.0), (x - 0.5, y + 1.0)]])


def _ws(f, t, ents, events=()):
    return WorldState(stamp=Stamp(frame=f, t_game_s=t), entities=list(ents), events=list(events))


def _go(iid, to, f, t):
    return Event(Ev.FSM_TRANSITION, f, t, FsmTransition(enemy_id=iid, type_key=REED, fsm="Control", to_state=to))


def _run(mf, script):
    """script: [(frame, [(state or None)], entity kwargs)]: feeds the WorldStates in order."""
    for f, t, ents, evs in script:
        mf.update(_ws(f, t, ents, evs))


# ---- static facts ----------------------------------------------------------------------------------------------

def test_static_facts_match_the_builder_and_the_encounter():
    from ssbot.knowledge.gauntlet_tables import FORUM_SPECS
    from ssbot.train.encounters import FORUM_WAVES as ENC
    assert set(FORUM_TYPES) == set(FORUM_SPECS)
    for tk, t in FORUM_TYPES.items():
        s = FORUM_SPECS[tk]
        assert (t.enemy, t.control_fsm, t.hp, t.idle_family) == (s.enemy, s.control_fsm, s.hp, s.idle_family)
        assert tuple(t.death_states) == tuple(s.death_states)
        assert tuple(t.waiting) == tuple(s.dormant)
        assert tuple(t.spawns) == tuple(s.spawns) and tuple(t.hazard_rest) == tuple(s.rest_states)
    assert len(FORUM_WAVES) == len(ENC)
    for a, b in zip(FORUM_WAVES, ENC):
        assert (a.index, a.name, a.start_delay_s, a.remaining_to_end) == (b.index, b.name, b.start_delay_s,
                                                                          b.remaining_to_end)
        assert tuple(n for n, _, _ in a.members) == tuple(b.enemies) and a.types == b.types


# ---- the walk ---------------------------------------------------------------------------------------------------

def test_walk_hulls_the_entries_and_stops_at_the_horizon():
    tt = _tables().types[REED]
    nodes = walk(tt, "Alert", ("RE_IDLE", "Alert"), False, False, cap=1.0)
    by = {(n.state, n.family, n.kind): (n.lo, n.hi) for n in nodes}
    # the stab may start when Alert ends (0.2 - 0.5 s, one bin of slack each side) and Stab 1 a 0.1 s dwell later;
    # one hull per node: a later stab (after the next Alert) widens it to the cap
    assert by[("Stab Pos", "RE_STAB", "new")] == pytest.approx((0.2 - BIN, 1.0))
    assert by[("Stab 1", "RE_STAB", "new")] == pytest.approx((0.3 - 2 * BIN, 1.0))
    short = {(n.state, n.kind): (n.lo, n.hi) for n in walk(tt, "Alert", ("RE_IDLE", "Alert"), False, False,
                                                            cap=0.5)}
    assert short[("Stab Pos", "new")] == pytest.approx((0.2 - BIN, 0.5))
    assert by[("Alert", "RE_IDLE", "cur")] == (0.0, 0.0)
    assert all(n.lo <= 1.0 for n in nodes)
    # overdue: the current state may end from the next frame to the cap
    od = {(n.state, n.kind): (n.lo, n.hi) for n in walk(tt, "Alert", ("RE_IDLE", "Alert"), False, True, cap=1.0)}
    assert od[("Stab Pos", "new")] == (BIN, 1.0)
    # an instance's own walk (the family walk template) stays inside the instance and its tail
    inst = walk(tt, "Stab Pos", ("RE_STAB", "Stab Pos"), False, False, instance_only=True)
    assert {n.state for n in inst} == {"Stab Pos", "Stab 1", "Stab Recover", "_tail"}


def test_structurally_absent_moves_are_never_walked_or_placed():
    tabs = _tables(extra_absent=True)
    tt = tabs.types[REED]
    # the type table drops nothing of a Reed's (MA_POINT is the Maestro's), but core.forum's table does for the
    # Maestro / Envoy / Bellbearer: check the mechanism on the real specs
    for tk, states in STRUCTURALLY_ABSENT.items():
        d = _reed_table()
        d["spec"]["attack_starts"] = {s: "X_" + s for s in states} | d["spec"]["attack_starts"]
        d["support_transitions"]["Alert"] = list(d["support_transitions"]["Alert"]) + list(states)
        for s in states:
            d["dwell_s"][s] = {"min": 0.1, "max": 0.2}
        t2 = type_table(d, FORUM_TYPES[tk])
        assert not set(states) & set(t2.attack_starts) and not set(states) & set(t2.dwell) - set(t2.dwell) | set()
        assert all(not set(states) & set(v) for v in t2.succ.values())
        for n in walk(t2, "Alert", ("RE_IDLE", "Alert"), False, True, cap=2.0):
            assert n.state not in states
    for tk, fams in ABSENT_FAMILIES.items():
        for f in fams:
            assert not et.wanted_key(f"support/{f}/x/anchor", FORUM_TYPES[tk])
            assert not et.wanted_key(f"support/{f}/anchor", FORUM_TYPES[tk])
    assert "Point Start" in tt.attack_starts          # not absent for a Reed: only the listed types lose it


def test_production_tables_have_no_absent_move():
    tabs = _production()
    for tk, states in STRUCTURALLY_ABSENT.items():
        tt = tabs.types[tk]
        assert not states & set(tt.attack_starts) and all(not states & set(v) for v in tt.succ.values())
    for k in tabs.store.keys + list(tabs.store.coarse_keys):
        p = k.split("/")
        for tk, fams in ABSENT_FAMILIES.items():
            assert not (len(p) > 1 and p[1] in fams), k
        assert not any(len(p) > 2 and p[2] in states for states in STRUCTURALLY_ABSENT.values()), k


_PROD = {}


def _production():
    if "t" not in _PROD:
        if not (et.FORUM_DIR / "Reed_hitboxes.npz").exists():
            pytest.skip("the Forum tables' npz files are not built here (behaviour_build --encounter Forum)")
        _PROD["t"] = EnemyTables.production()
    return _PROD["t"]


# ---- tracker and forecast ----------------------------------------------------------------------------------------

def _script_stab():
    """A Reed idles in Alert at x 20, starts a stab at f 10 (Stab Pos, then Stab 1 at f 16), is hit at f 20 and killed
    at f 24."""
    out = []
    t = 0.0
    for f in range(0, 30):
        t = f * BIN
        evs = []
        st = "Alert" if f < 10 else "Stab Pos" if f < 16 else "Stab 1"
        if f == 0:
            evs.append(_go(7, "Alert", f, t))
        if f == 10:
            evs.append(_go(7, "Stab Pos", f, t))
        if f == 16:
            evs.append(_go(7, "Stab 1", f, t))
        if f == 20:
            evs.append(Event(Ev.HIT_DEALT, f, t, HitDealt(7, REED, 9.0, 46.0, attack="Nail", src="Slash")))
        if f == 24:
            evs.append(Event(Ev.HIT_DEALT, f, t, HitDealt(7, REED, 50.0, -4.0, killing=True)))
            evs.append(Event(Ev.ENEMY_KILLED, f, t, EnemyKilled(7, REED)))
        ents = [] if f > 24 else [_ent(7, 20.0 + (0.05 * (f - 10) if f >= 10 else 0.0), 5.0, st, 0.0, flip=True,
                                       box=(19.5, 4.0, 20.5, 6.0), hp=999)]
        out.append((f, t, ents, evs))
    return out


def test_tracker_segments_anchors_and_counts_hits_not_the_export():
    tabs = _tables()
    mf = MultiForecaster(tabs, ORACLE, waves=False)
    script = _script_stab()
    _run(mf, script[:21])
    tr = mf.trackers[7]
    assert tr.state == "Stab 1" and tr.cur.family == "RE_STAB" and tr.cur.start == "Stab Pos"
    assert tr.cur.anchor == (20.0, 5.0) and tr.cur.mirror == 1          # flipX True: mirror +1
    assert [e.family for e in tr.ends] == ["RE_IDLE"]
    assert tr.hp_est == 55.0 - 9.0                                       # the hit's amount, never the export's 999
    _run(mf, script[21:26])
    assert tr.dead and tr.death_box == (19.5, 4.0, 20.5, 6.0)
    # vision view: no FSM events, no amount: the phase and the price of the attack
    ve = EnemyTracker(tabs.types[REED], VISION_EQUIVALENT, 7)
    e = _ent(7, 20.0, 5.0, None, box=(19.5, 4.0, 20.5, 6.0), hp=999)
    e.phase = PhasePost(topk=[("Stab Pos", 1.0)], t_in_phase=0.05)
    ve.observe(1.0, [Event(Ev.HIT_DEALT, 60, 1.0, HitDealt(7, REED, None, None, attack="Nail", src="Slash"))], e)
    assert ve.state == "Stab Pos" and ve.t_entry == pytest.approx(0.95) and ve.cur.family == "RE_STAB"
    assert ve.hp_est == 55.0 - 9.0 and ve.hp_sd > 0


def test_forecast_covers_the_attack_drops_the_dead_and_answers_the_interface():
    tabs = _tables()
    mf = MultiForecaster(tabs, ORACLE, waves=False)
    script = _script_stab()
    _run(mf, script[:17])                                  # f 16: Stab 1 entered at its anchor (20, 5)
    f = mf.forecast(0.8)
    tk = np.arange(0, 31) * BIN
    blade = f.occupied(np.full((1, 31), 22.0), np.full((1, 31), 5.0), tk)[0]
    far = f.occupied(np.full((1, 31), 35.0), np.full((1, 31), 5.0), tk)[0]
    assert blade[4:15].all() and not far.any()
    assert f.known and f.n_fine > 0
    # without the Reed: nothing left near it; only its own support: the same
    assert not f.occupied_without(np.full((1, 31), 22.0), np.full((1, 31), 5.0), tk, 7).any()
    assert np.array_equal(f.occupied_only(np.full((1, 31), 22.0), np.full((1, 31), 5.0), tk, {7})[0], blade)
    assert f.committed().occupied(np.full((1, 31), 22.0), np.full((1, 31), 5.0), tk)[0][4:15].all()
    ss = f.support_set(t1=0.2)
    assert ss.known and [(e.source, e.instance, e.hits) for e in ss.events] == [(REED, 7, 1)]
    # within 0.8 s the stab can end and a defence (its counter chains 2 hits for 2 masks) start: one event, 2 hits
    assert [(e.instance, e.hits, e.damage) for e in f.support_set().events] == [(7, 2, 2)]
    assert 0.0 < f.prob(np.full((1, 31), 22.0), np.full((1, 31), 5.0), tk)[0] <= 1.0
    # far away only once the anchor box of a later attack has grown past the calibrated idle growth (top speed)
    assert f.t_min(22.0, 5.0) <= 0.1 and math.isinf(f.t_min(35.0, 5.0, t_max=0.5))
    tg = f.targets(tk)
    assert [t.iid for t in tg] == [7] and tg[0].box.shape == (31, 4)
    _run(mf, script[17:26])                                # killed at f 24: the death box for 3 bins, then nothing
    f2 = mf.forecast(0.8)
    near = f2.occupied(np.full((1, 31), 20.0), np.full((1, 31), 5.0), tk)[0]
    assert near[:2].any() and not near[5:].any()


def test_a_kill_never_enlarges_the_danger_zone_and_the_what_if_leaves_the_state():
    """forum_planner_plan §4.4 item 6: killed mid-stab, the Reed leaves its death box (3 bins) and no tail; the what-if
    forecast is inside the real one around it, and the real state is untouched."""
    tabs = _tables()
    mf = MultiForecaster(tabs, ORACLE, waves=False)
    script = _script_stab()
    _run(mf, script[:17])                                  # f 16: Stab 1 entered
    tk = np.arange(0, 61) * BIN
    g = np.arange(-4.0, 4.01, 0.25)
    gx, gy = np.meshgrid(20.0 + g, 5.0 + g, indexing="ij")
    X = np.repeat(gx.reshape(-1, 1), len(tk), axis=1)
    Y = np.repeat(gy.reshape(-1, 1), len(tk), axis=1)
    f = mf.forecast(1.1)
    fk = mf.forecast_if_killed([7], 1.1)
    base, kill = f.occupied(X, Y, tk), fk.occupied(X, Y, tk)
    assert kill.any() and not (kill & ~base).any()
    assert not kill[:, 4:].any()                           # the death box only: 3 bins from the kill
    assert {b[1] for b in fk.boxes} == {"death"}
    tr = mf.trackers[7]
    assert not tr.dead and tr.cur.family == "RE_STAB" and tr.cur.t_end is None
    assert np.array_equal(mf.forecast(1.1).occupied(X, Y, tk), base)
    # the recorded kill: no tail of the stab it cut short (the idle instance it finished keeps its tail)
    _run(mf, script[17:26])
    assert mf.trackers[7].dead and [e.family for e in mf.trackers[7].ends] == ["RE_IDLE"]


def test_a_waiting_wave_member_waits_for_its_wave():
    """A Reed parked in Fly In Ready (a waiting state) whose wave is queued for 1 s from now: nothing of it (no walk, no
    collider tube) before the activation, its attacks after it; with the wave unknown it is walked from now."""
    d = _reed_table()
    d["dwell_s"]["Fly In Ready"] = {"min": 0.1, "max": 5.0}
    d["support_transitions"]["Fly In Ready"] = ["Alert"]
    d["graph"]["edges"].append({"from": "Fly In Ready", "to": "Alert", "p": 1.0})
    tt = type_table(d, FORUM_TYPES[REED])
    tabs = EnemyTables({REED: tt}, EnemyTables._store([_templates()]), _tables().tubes, {}, True, "synthetic", {})
    tk = np.arange(0, 121) * BIN
    X, Y = np.full((1, 121), 20.0), np.full((1, 121), 5.0)

    def run(queued: bool):
        mf = MultiForecaster(tabs, ORACLE)
        ent = _ent(7, 20.0, 5.0, "Fly In Ready", box=(19.5, 4.0, 20.5, 6.0))
        _run(mf, [(0, 0.0, [ent], [_go(7, "Fly In Ready", 0, 0.0)]), (1, BIN, [ent], [])])
        mf.t_wake = 0.0
        mf.waves.queued = (2, BIN + 1.0, BIN + 1.0 + 2 * BIN) if queued else (2, BIN, BIN + 2 * BIN)
        return mf.forecast(2.0)

    f = run(True)
    occ = f.occupied(X, Y, tk)[0]
    assert not occ[:57].any() and occ[60:].any()           # (the templates' +-1 bin pad)
    assert not any(b[1] == "collider" for b in f.boxes)
    now = run(False).occupied(X, Y, tk)[0]
    assert now[:30].any()


def _tiny_tables() -> EnemyTables:
    """The synthetic Reed's tables as a pooled type (the Maestro's Tinies: prefix AT)."""
    tiny = "Song Automaton Tiny"
    d = json.loads(json.dumps(_reed_table()).replace("RE_", "AT_"))
    tt = type_table(d, FORUM_TYPES[tiny])
    store = EnemyTables._store([{k.replace("RE_", "AT_"): v for k, v in _templates().items()}])
    tubes = Tubes({tiny: [0.0] + [0.05 * k for k in range(1, 41)]}, {tiny: 50.0}, {tiny: BODY})
    return EnemyTables({tiny: tt}, store, tubes, {}, True, "synthetic", {})


def test_tiny_group_placement_covers_its_members_with_fewer_rows():
    """With >= TINY_GROUP Tinies, the instances the ones within TINY_CLUSTER_U of each other may start are placed once
    per cluster (one anchor box over the members): a superset of the per-Tiny placements, fewer rows."""
    tiny = "Song Automaton Tiny"
    tabs = _tiny_tables()
    xs = {1: 20.0, 2: 21.5, 3: 23.0, 4: 40.0}

    def run(group: int):
        mf = MultiForecaster(tabs, ORACLE, waves=False, tiny_group=group)
        evs = [Event(Ev.FSM_TRANSITION, 0, 0.0, FsmTransition(enemy_id=i, type_key=tiny, fsm="Control",
                                                               to_state="Alert")) for i in xs]
        ents = [_ent(i, x, 5.0, "Alert", tk=tiny) for i, x in xs.items()]
        _run(mf, [(0, 0.0, ents, evs), (1, BIN, ents, [])])
        return mf.forecast(0.8)

    grouped, single = run(mfm.TINY_GROUP), run(0)
    assert grouped.groups and set().union(*grouped.groups.values()) | set(grouped.groups) == {1, 2, 3}
    assert grouped.n_bbox < single.n_bbox
    tk = np.arange(0, 49) * BIN
    rng = np.random.default_rng(3)
    X = np.repeat(rng.uniform(15.0, 45.0, (800, 1)), len(tk), axis=1)
    Y = np.repeat(rng.uniform(2.0, 9.0, (800, 1)), len(tk), axis=1)
    a, b = grouped.occupied(X, Y, tk), single.occupied(X, Y, tk)
    assert b.any() and not (b & ~a).any()


def test_idle_enemy_is_its_body_tube_and_the_attacks_it_may_start():
    tabs = _tables()
    mf = MultiForecaster(tabs, ORACLE, waves=False)
    _run(mf, [(0, 0.0, [_ent(7, 20.0, 5.0, "Alert", box=(19.5, 4.0, 20.5, 6.0))], [_go(7, "Alert", 0, 0.0)]),
              (1, BIN, [_ent(7, 20.0, 5.0, "Alert", box=(19.5, 4.0, 20.5, 6.0))], [])])
    f = mf.forecast(0.8)
    assert any(b[1] == "idle" for b in f.boxes)
    parts = f.occupied_parts(np.array([[20.0, 22.0]]), np.array([[5.0, 5.0]]), np.array([0.0, 0.0]))
    assert parts["idle body tube"][0, 0]
    # the stab may start from 0.2 s on: its blade can reach x 22.6 then, not before (but the current-collider tube,
    # the reaction-lag net, grows at the top speed for its first 5 frames)
    tk = np.arange(0, 49) * BIN
    X, Y = np.full((1, 49), 22.6), np.full((1, 49), 5.0)
    blade = f.occupied_parts(X, Y, tk)["forecast"][0]
    assert blade[25:].any() and not blade[:8].any()
    tube = f.occupied_parts(X, Y, tk)["collider tube"][0]
    assert tube[:6].any() and not tube[6:].any()
    # the defence family carries a 2-hit chain in the support set
    assert mfm._chain(tabs.chains, REED, "RE_DEFEND") == (2, 2)


def test_coarse_and_bounding_box_forms_are_supersets():
    t = _templates()["support/RE_STAB/Stab 1/anchor"]
    c = coarsen(t, et.COARSE_F)
    rng = np.random.default_rng(1)
    xs, ys = rng.uniform(-3, 5, 4000), rng.uniform(-3, 3, 4000)
    ts = rng.uniform(-0.05, 0.4, 4000)
    fine = t.contains(ts, xs, ys, tol_bins=0)
    coarse = c.contains(ts, xs, ys, tol_bins=0)
    assert fine.any() and not (fine & ~coarse).any()
    store = TemplateStore({"k": t})
    offs, nt, t0 = store.bbox_table(0)
    rows = store.bb_rows()[offs[0]:offs[0] + nt]
    b = ((ts - t0) / BIN).round().astype(int)
    ok = (b >= 0) & (b < nt)
    r = rows[np.clip(b, 0, nt - 1)]
    inside = ok & (xs >= r[:, 0]) & (xs <= r[:, 2]) & (ys >= r[:, 1]) & (ys <= r[:, 3])
    assert not (fine & ~inside).any()
    # a window placement (the coarse time pyramid) covers every entry in its window
    W = et.WinBatch.from_rows([(0, 0.1, 0.25, 20.0, 5.0, 1)])
    xq, yq = 20.0 + xs[:300, None], 5.0 + ys[:300, None]
    for e in np.arange(0.1, 0.25 + 1e-9, BIN):
        want = t.contains(np.full(300, 0.3) - e, xs[:300], ys[:300], tol_bins=0)
        got = store.query_win(W, xq, yq, np.array([0.3]))[:, 0]
        assert not (want & ~got).any()


def test_family_walk_boxes_cover_the_per_state_walk():
    tabs = _tables()
    mf = MultiForecaster(tabs, ORACLE, waves=False)
    tt = tabs.types[REED]
    fid = mf.family_walk_id(tt, "RE_STAB", "Stab Pos")
    offs, nt, t0 = tabs.store.bbox_table(fid)
    rows = tabs.store.bb_rows()[offs[0]:offs[0] + nt]
    rng = np.random.default_rng(2)
    xs, ys = rng.uniform(-3, 5, 6000), rng.uniform(-3, 3, 6000)
    ts = rng.uniform(0.0, 0.8, 6000)
    hit = np.zeros(len(xs), bool)
    for n in walk(tt, "Stab Pos", ("RE_STAB", "Stab Pos"), False, False, instance_only=True):
        tid = tabs.key_id("RE_STAB", n.state)
        if tid is None:
            continue
        t = tabs.store.tpls[tid]
        for e in np.arange(n.lo, n.hi + 1e-9, BIN):
            hit |= t.contains(ts - e, xs, ys, tol_bins=0)
    b = np.clip(((ts - t0) / BIN).round().astype(int), 0, nt - 1)
    r = rows[b]
    cov = (xs >= r[:, 0]) & (xs <= r[:, 2]) & (ys >= r[:, 1]) & (ys <= r[:, 3])
    assert hit.any() and not (hit & ~cov).any()


# ---- hazards ----------------------------------------------------------------------------------------------------

def test_bell_steps_reproduce_a_recorded_flight():
    """R0 cache 20261002_223640 i2 ep0, bell -623410 from f 762585: thrown at (31.361, 9.418), (-13.261, 20.0); floor
    at f 762637 (y 3.428, vy 0), Bounce at f 762639 (y 3.528, vy 18.8), then (19.161, 3.88) at f 762640."""
    xs, ys, on, tube = bell_steps(31.361, 9.418, -13.261, 20.0, 60)
    # index = physics steps since the throw (frames without a step repeat the last position: f 762590, 762596, ...)
    logged = {1: (31.096, 9.794), 4: (30.3, 10.778), 13: (27.914, 12.434), 44: (19.692, 3.428), 45: (19.427, 3.528),
              46: (19.161, 3.88)}
    for i, (x, y) in logged.items():
        assert xs[i] == pytest.approx(x, abs=2e-3) and ys[i] == pytest.approx(y, abs=2e-3), i
    assert tube is None and on.all()
    # a nail hit's redirect: 30 u/s away, the collider off through Nail Hit
    xs2, ys2, on2, _ = bell_steps(25.0, 8.0, -5.0, 0.0, 30, redirect=(3, 1))
    assert xs2[4] - xs2[3] == pytest.approx(0.6, abs=1e-9) and not on2[3:9].any() and on2[12]


def test_pin_stops_at_the_wall_and_the_clock_narrows():
    xs, ys, on = pin_steps(17.0, 5.0, -31.0, 0.0, 20, (-1.0, -0.05, 1.0, 0.05))
    k = int(np.argmax(~on))
    assert k > 0 and xs[k - 1] - 1.0 <= 14.01 + 0.62 and (xs[k:] == xs[k - 1]).all()
    c = PhysClock()
    assert c.mid() is None
    c.observe(10.0, 10.0 + 1 / 60, moved=False)               # no step in (10.0, 10.0167]
    m = c.mid()
    assert m is not None and not (10.0 % 0.02 < m <= (10.0 + 1 / 60) % 0.02)


def _bomb(iid, x):
    b = DamageBox(poly=[(x - 2.166, 1.5), (x + 2.166, 1.5), (x + 2.166, 5.836), (x - 2.166, 5.836)], active=False)
    return Entity(id=iid, type_key=E("damager"), pos=E((x, 3.67)), pos_transform=(x, 3.67), dmg_boxes=[b],
                  vel=E((0.0, 0.0), conf=0.0))


def test_bomb_rows_predict_the_later_pairs():
    """R0 cache 20261002_223640 i2 ep0: a row's bombs appeared at 418.597 (x 24.43), 418.747 (+-1), 418.914 (+-2),
    419.064 (+-3), 419.23 (+-4), 419.389 (+5): steps of 9 or 10 frames; each arms 0.335-0.36 s after it appears."""
    hz = HazardTracker(ORACLE)
    t0, x0 = 418.597, 24.43
    hz.update(_ws(0, t0, [_bomb(-5, x0)]))
    rows = [p for p in hz.paths(t0, 1.5) if p.predicted]
    xs = sorted({round(float(p.xs[0]), 2) for p in rows})
    assert round(x0 + BOMB_DX, 2) in xs and round(x0 - BOMB_DX, 2) in xs and round(x0 + 2 * BOMB_DX, 2) in xs
    for k, t_app in ((1, 418.747), (2, 418.914), (3, 419.064), (4, 419.23), (5, 419.389)):
        p = next(p for p in rows if abs(p.xs[0] - (x0 + k * BOMB_DX)) < 1e-6)
        assert p.t_lo <= t_app - t0 + BOMB_LEAD_S[0] and p.t_hi >= t_app - t0 + BOMB_LEAD_S[1]
    # pair 2 seen: the later ones are timed from it; the pairs seen are not predicted any more
    hz.update(_ws(1, 418.747, [_bomb(-8, x0 + BOMB_DX), _bomb(-9, x0 - BOMB_DX)]))
    hz.update(_ws(2, 418.914, [_bomb(-6, x0 + 2 * BOMB_DX), _bomb(-7, x0 - 2 * BOMB_DX)]))
    rows = [p for p in hz.paths(418.914, 1.5) if p.predicted]
    assert not any(abs(p.xs[0] - (x0 + 2 * BOMB_DX)) < 1e-6 for p in rows)
    p3 = next(p for p in rows if abs(p.xs[0] - (x0 + 3 * BOMB_DX)) < 1e-6)
    assert p3.t_lo <= 419.064 - 418.914 + BOMB_LEAD_S[0] and p3.t_hi >= 419.064 - 418.914 + BOMB_LEAD_S[1]
    assert p3.t_lo >= 9 / 60 + BOMB_LEAD_S[0] - 0.04 - 1e-9          # one step from pair 2, not three from the first


# ---- waves -------------------------------------------------------------------------------------------------------

def test_wave_tracker_follows_battle_scene_rules():
    from ssbot.train.gauntlet import Wave, WaveSim
    waves = tuple(Wave(w.index, w.name, w.start_delay_s, w.remaining_to_end, tuple(n for n, _, _ in w.members))
                  for w in FORUM_WAVES)
    sim = WaveSim(waves)
    wt = WaveTracker()
    wt.start(0.0)
    sim.start(0)
    kills = [120, 150, 180, 300, 330, 420, 600, 660, 800]
    f = 0
    for f in range(0, 1000):
        t = f / 60.0
        sim.advance(f)
        evs = []
        if f in kills and wt.wave >= 0:
            evs.append(Event(Ev.ENEMY_KILLED, f, t, EnemyKilled(1000 + f, FORUM_WAVES[wt.wave].types[0])))
            sim.kill(f)
        ents = []
        if wt.queued is not None:
            w, lo, hi = wt.queued
            if t >= lo:
                ents = [Entity(id=50 + w, type_key=E(FORUM_WAVES[w].types[0]), fsm=[("Control", "Fight", 0.0)])]
        wt.update(_ws(f, t, ents, evs))
    got = [w for w, _ in wt.starts]
    want = [w for w, _ in sim.starts]
    assert got == want[:len(got)] and len(got) >= 3


# ---- vision-legal discipline and the single-boss wrap -------------------------------------------------------------

def test_run_time_modules_read_no_oracle_only_truth():
    """hp from the hits the view saw (never Entity.hp_est), no room.battles, no parry bits, the tracker branches by
    view (the forecast does not)."""
    import ast
    from ssbot.combat import enemy_tracker, projectiles, wave_tracker
    for mod in (enemy_tracker, mfm, wave_tracker, projectiles, et):
        tree = ast.parse(inspect.getsource(mod))
        attrs = {(n.attr, ast.unparse(n.value)) for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        consts = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        # the exported HP of an entity (hp_est on anything but the tracker itself), the battle export, parry bits
        assert not {a for a, v in attrs if a == "hp_est" and v not in ("self", "tr", "ve")}, mod.__name__
        assert not {a for a, _ in attrs if a in ("battles", "room", "parry")}, mod.__name__
        assert not consts & {"battles", "parry", "room"}, mod.__name__
    assert "self.view" in inspect.getsource(EnemyTracker.observe)
    assert "ORACLE" not in inspect.getsource(mfm._Builder.subject)


def test_vision_view_forecast_runs_on_a_stripped_world_state():
    tabs = _tables()
    mf = MultiForecaster(tabs, VISION_EQUIVALENT, waves=False)
    for f, t, ents, evs in _script_stab()[:17]:
        for e in ents:
            e.phase = PhasePost(topk=[(e.fsm[0][1], 1.0)], t_in_phase=0.0)
        ws = _ws(f, t, ents, evs).view(VISION_EQUIVALENT)
        mf.update(ws)
    tr = mf.trackers[7]
    assert tr.state == "Stab 1" and tr.cur.family == "RE_STAB"
    f = mf.forecast(0.8)
    tk = np.arange(0, 31) * BIN
    assert f.occupied(np.full((1, 31), 22.0), np.full((1, 31), 5.0), tk)[0][4:15].any()


def test_bell_beast_wrapped_is_bit_identical_on_the_fixture_windows():
    from ssbot.backends.oracle_backend import OracleBackend
    from ssbot.combat.boss_model import BossModel
    from ssbot.combat.forecast import Forecaster, load_planner_templates
    from ssbot.core.bosses import BELL_BEAST
    from tests import worldstate_fixture as fx
    model = BossModel.load()
    tpl = load_planner_templates(model, 0.0)
    rng = np.random.default_rng(3)
    for win in (0, 1):
        a = Forecaster(model, ORACLE, templates=tpl)
        b = MultiForecaster(boss=Forecaster(model, ORACLE, templates=tpl))
        ba, bb = OracleBackend(bosses=[BELL_BEAST]), OracleBackend(bosses=[BELL_BEAST])
        for s in fx.window(win):
            wa, wb = ba.feed(s), bb.feed(s)
            a.update(wa)
            b.update(wb)
            A, B = a.forecast(2.0), b.forecast(2.0)
            assert [(p.key, p.t_ref, p.anchor) for p in A.placements] == [(p.key, p.t_ref, p.anchor)
                                                                          for p in B.placements]
            X = 80.0 + rng.uniform(-15, 15, (16, 13))
            Y = rng.uniform(2, 10, (16, 13))
            tk = np.arange(13) * 0.05
            assert np.array_equal(A.occupied(X, Y, tk), B.occupied(X, Y, tk))
            assert np.array_equal(A.prob(X, Y, tk), B.prob(X, Y, tk))
            assert A.support_set(wa) == B.support_set(wb)
            assert B.fc is b.boss and B.known == A.known
