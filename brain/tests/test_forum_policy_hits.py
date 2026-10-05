"""ForumPlannerPolicy's hit accounting (R4 fixer round): the unpredicted-hit check on stub forecasts, no tables.

A hero box's centre x is its frame number here, and the stub forecast covers the frames in COVER: a hit at frame f is
inside the support iff the frame it is judged at (f, a chain's hook, or the frame before) is in COVER."""
from collections import deque

import numpy as np

from ssbot.train.forum_planner_policy import HOOK_LOOKBACK_F, TICK_WAIT_F, ForumPlannerPolicy

F0 = 1000
MULTIHIT = "Hero_Hornet(Clone)/Roar and Wound States/Multihit:CallMethodProper"
FINAL = "Hero_Hornet(Clone)/Roar and Wound States/Final Hit:DamageHeroDirectly"


class _Cover:
    def __init__(self, frames):
        self.frames = set(frames)

    def occupied(self, x, y, t):
        return np.array([[int(round(float(x[0, 0]))) in self.frames]])


def _policy(cover=()) -> ForumPlannerPolicy:
    p = ForumPlannerPolicy.__new__(ForumPlannerPolicy)
    fc = _Cover(cover)
    p.forecasts = deque(((f, fc, f / 60.0) for f in range(F0 - 200, F0 + 400)), maxlen=600)
    p._boxes = {f: ((f, 0.0, f, 0.0), f / 60.0) for f in range(F0 - 200, F0 + 400)}
    p._hit_src, p._enters, p._obj_state, p._ent_obj = {}, {}, {}, {}
    p._pending_ticks, p.mh_ticks, p.hits_taken, p.follow_ups = [], [], [], []
    p.unpredicted, p.unpredicted_unknown, p.unpred_sources, p._unpred_src = [], [], [], []
    return p


def _taken(p, f, path, sid=None, kind="damage"):
    p._hit_src.setdefault(f, []).append({"path": path, "sid": sid, "kind": kind, "used": False})


def _enter(p, f, ent, obj, to, fsm="Control"):
    p._enters.setdefault((ent, fsm), []).append((f, to))
    p._obj_state[(ent, fsm)] = to
    p._ent_obj[ent] = obj


def test_sources_pair_by_caller_path_and_a_blocked_event_gets_none():
    p = _policy()
    _taken(p, F0, "Song Reed/Stab Hit 1", sid=7)
    raw = {"ev": [{"k": "damage", "d": {"source": "Song Pilgrim 01/Charge Damager"}},     # pogo-blocked
                  {"k": "damage", "d": {"source": "Song Reed/Stab Hit 1"}}]}
    assert p._unpredicted(raw, F0) == 2
    assert p.unpred_sources == [[F0, None], [F0, 7]] and p._unpred_src == [None, 7]


def test_a_tick_inside_the_support_is_judged_at_once():
    p = _policy(cover={F0})
    _taken(p, F0, MULTIHIT, kind="tick")
    assert p._unpredicted({"ev": [{"k": "special_damage", "d": {"fsm": MULTIHIT}}]}, F0) == 0
    assert p.mh_ticks == [[F0, "own"]] and not p._pending_ticks


def test_a_tick_outside_without_a_final_hit_is_counted_after_the_wait():
    p = _policy()
    _taken(p, F0, MULTIHIT, kind="tick")
    assert p._unpredicted({"ev": [{"k": "special_damage", "d": {"fsm": MULTIHIT}}]}, F0) == 0
    assert p._pending_ticks == [F0]
    assert p._unpredicted({"ev": []}, F0 + TICK_WAIT_F - 1) == 0
    assert p._unpredicted({"ev": []}, F0 + TICK_WAIT_F) == 1
    assert p.unpredicted == [F0] and p.unpred_sources == [[F0, None]] and p.mh_ticks == [[F0, "miss"]]
    q = _policy()                                    # the episode ends first: stats() flushes it
    _taken(q, F0, MULTIHIT, kind="tick")
    q._unpredicted({"ev": [{"k": "special_damage", "d": {"fsm": MULTIHIT}}]}, F0)
    assert q._flush_ticks(None) == 1 and q.unpredicted == [F0]


def test_a_tick_goes_with_its_chains_final_hit_judged_at_the_hook():
    hook = F0 - 5
    p = _policy(cover={hook})
    _enter(p, hook, 41, "Song Pilgrim 03", "Whip 2")
    _taken(p, F0, MULTIHIT, kind="tick")
    p._unpredicted({"ev": [{"k": "special_damage", "d": {"fsm": MULTIHIT}}]}, F0)
    assert p._pending_ticks == [F0]
    f1 = F0 + 20
    _taken(p, f1, "Song Pilgrim 03/Whip Hit 2", sid=41)
    raw = {"ev": [{"k": "damage", "d": {"source": "Song Pilgrim 03/Whip Hit 2", "fsm": FINAL}}]}
    assert p._unpredicted(raw, f1) == 0
    assert p.follow_ups == [[f1, "Song Pilgrim 03", hook]] and p.mh_ticks == [[F0, "chain"]]
    assert not p._pending_ticks and not p.unpredicted


def test_the_hook_is_the_source_instances_and_a_nested_path_falls_back_to_the_name():
    p = _policy()
    f = F0
    _enter(p, f - 30, 1, "Song Reed", "ParrySlash")
    _enter(p, f - 10, 2, "Song Reed", "ParrySlash")
    assert p._hook_of(1, "Song Reed/ParrySlash Hit", f) == f - 30          # by instance, not by the shared name
    assert p._hook_of(None, "Wave 1/Song Reed/ParrySlash Hit", f) == f - 10  # no iid: every Reed, the latest
    assert p._hook_of(3, "Wave 1/Song Reed/ParrySlash Hit", f) == f - 10    # an iid with no entry: the name
    assert p._hook_of(1, "Song Reed/ParrySlash Hit", f + HOOK_LOOKBACK_F) is None   # too old
