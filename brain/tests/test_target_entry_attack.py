"""L2 chooses first contact style; existing skills choose the route."""
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from ssbot.combat.tactics import gauntlet as G
from ssbot.combat.tactics.modes import EntryAttack, GoalPrefs, entry_attack_prefs
from ssbot.combat.knife_chain_air_native import NativeManualAirChain
from ssbot.combat.knife_chain_air import load_runner
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_eval import Run
from ssbot.combat.knife_chain_transfer import TransferGoal
from ssbot.core.worldstate import Event, Ev, HitDealt
from tests.test_forum_l2 import l2, world, subj, WinFc, CC
from tests.test_knife_chain_transfer import cast_scene, plan


@pytest.mark.parametrize("family,distance,kind", [
    (G.CC_CAST, 2., "stomp"), (G.CC_CAST, 24., "stomp"),
    (G.CC_SLAM, 3., "stomp"), (G.CC_SLAM, 8.05, "stomp"),
    (G.CC_SLAM, 8.06, "side"), (G.CC_SLAM, 20., "side"),
])
def test_natural_focus_switch_outputs_pinned_style(monkeypatch, family, distance, kind):
    monkeypatch.setattr(G, "TWO_FOCUS", True)
    monkeypatch.setattr(G, "TWO_SPRINTSW", False)
    monkeypatch.setattr(G.two_play, "SPACE", False)
    tac = l2()
    # Outer room14 versus20: real two-focus rule switches off the busy old one.
    old = subj(1, CC, 14., state="Spell Antic" if family == G.CC_CAST else "Slam Antic",
               family=family, committed=True, t_free=3.)
    new = subj(2, CC, 40., family=G.CC_IDLE)
    tac.pb.arena_x = (0., 60.)
    tac.goal = G.Goal(G.RUSH, 1, 14., 1.)
    prefs = GoalPrefs(mode="ENGAGE", stance_x=14., weights={}, hit_w={1: 1., 2: 1.})
    out = tac._decide(world(14. + distance), WinFc([old, new]), prefs)
    assert out.target == 2
    assert out.entry_attack == EntryAttack(2, kind, 1, family, pytest.approx(distance), 10.)
    # Re-pick the SAME destination after moving: never reclassify the old range.
    tac.n = tac.rules.period - 1
    moved = tac._decide(world(45., t=10.1), WinFc([old, new]), prefs)
    assert moved.entry_attack == out.entry_attack


@pytest.mark.parametrize("kind,weights", [("stomp", (0., 0., 0., 3.)), ("side", (3., 0., 0., 0.))])
def test_entry_style_overrides_old_attack_bias_only(kind, weights):
    entry = EntryAttack(8, kind, 7, G.CC_SLAM, 4., 0.)
    prefs = GoalPrefs(mode="RUSH", stance_x=38., weights={}, target=8, entry_attack=entry,
        hit_w={8: 3.}, no_pogo=frozenset({7, 8}), ground_hit=frozenset({7, 8}),
        ground_first=frozenset({8}), no_hit=frozenset({7}), no_dash=frozenset({8}))
    out = entry_attack_prefs(prefs)
    assert out.hit_kw[8] == weights
    assert out.ground_hit == out.no_pogo == (frozenset({7}) if kind=='stomp' else frozenset({7,8}))
    assert out.no_hit == prefs.no_hit and out.no_dash == prefs.no_dash
    assert out.weights == prefs.weights and out.stance_x == prefs.stance_x
    assert entry_attack_prefs(replace(prefs, target=7)).hit_kw == {}


@pytest.mark.parametrize("kind,wrong,right", [("stomp", "Slash", "DownSlashAlt"), ("side", "DownSlash", "SlashAlt")])
def test_only_actual_requested_contact_completes_entry(kind, wrong, right):
    tac = l2()
    entry = EntryAttack(2, kind, 1, G.CC_SLAM, 4., 0.)
    tac.goal = G.Goal(G.RUSH, 2, 40., 1., entry_attack=entry)
    def hit(src):
        return Event(Ev.HIT_DEALT, 0, 10.5, HitDealt(2, CC, 9., 20., attack="Nail", src=src))
    tac._count_hits(world(events=[hit(wrong)]), 10.5)
    assert tac.goal.entry_attack == entry
    tac._count_hits(world(events=[hit(right)]), 10.5)
    assert tac.goal.entry_attack is None


def native():
    n = NativeManualAirChain(runner_factory=load_runner, probe_ref="target-entry")
    n.reset(0, start_frame=999)
    n._clock_known = True
    n._clock = 20.
    return n


def test_near_slam_switch_reuses_transfer_with_observed_source_identity():
    n = native()
    s = cast_scene()
    s['ents'][0]['fsms'][0].update(state='Slam Antic', t=.25)
    entry = EntryAttack(8, 'stomp', 7, G.CC_SLAM, 4., 10.)
    prefs = GoalPrefs(mode='RUSH', stance_x=38., weights={}, target=8, entry_attack=entry)
    n.goal_preferences(s, prefs, handoff=True)
    assert n._transfer_ready and n._transfer_goal.target == 8
    assert n._transfer_goal.responsibility == MoveInstance(7, 985, 'CC_SLAM')
    assert n._transfer_goal.cast_ta == 19.75
    assert n._transfer_goal.source_kind == 'SWITCH'
    assert n.runner.run is None and n.commitment is None and not n._receipts


@pytest.mark.parametrize('blocked', ['clock', 'source', 'handoff', 'commitment', 'no_hit'])
def test_intent_cannot_fabricate_an_entry_or_interrupt_a_commitment(blocked):
    n = native()
    s = cast_scene()
    s['ents'][0]['fsms'][0].update(state='Slam Antic', t=.25)
    entry = EntryAttack(8, 'stomp', 7, G.CC_SLAM, 4., 10.)
    prefs = GoalPrefs(mode='RUSH', stance_x=38., weights={}, target=8, entry_attack=entry)
    if blocked == 'clock': n._clock_known = False
    if blocked == 'source': s['ents'][0]['fsms'][0]['state'] = 'Idle'
    if blocked == 'commitment': n.commitment = {'existing': True}
    if blocked == 'no_hit': prefs = replace(prefs, no_hit=frozenset({8}))
    n.goal_preferences(s, prefs, handoff=blocked != 'handoff')
    assert not n._transfer_ready
    if blocked == 'commitment': assert n.commitment == {'existing': True}


def test_side_intent_retains_old_hammer_tail_then_hands_to_ordinary_attacks():
    n = native()
    s = cast_scene()
    source = s['ents'][0]
    source['fsms'][0].update(state='Slam 2', t=0.)
    source['colliders'] = [{'name': 'Song Heavy Sentry', 'enabled': True}]
    n._transfer_goal = TransferGoal(8, 7, 1000, 19., 'BOUNCE', MoveInstance(7, 940, 'CC_SLAM'))
    entry = EntryAttack(8, 'side', 7, G.CC_SLAM, 10., 10.)
    prefs = GoalPrefs(mode='RUSH', stance_x=38., weights={}, target=8, entry_attack=entry)
    n.goal_preferences(s, prefs, handoff=True)
    assert n._transfer_ready  # source Slam 2 has NOT disappeared yet
    n.runner.run = Run('rune_transfer', 'bounce_tail', plan().variables())
    n.commitment = {'move': plan().move}
    source['fsms'][0]['state'] = 'Slam Recover'
    assert n._transfer_offer(s, 20., None, None, prefs, False) is None
    assert n.runner.run is None and n.commitment is None
    assert not n._failure_exposures and not n._transfer_ready


@pytest.mark.parametrize('source_shift,available', [(0., True), (1., False)])
def test_slam_intent_reaches_existing_approach_and_checks_source_instance(monkeypatch, source_shift, available):
    from ssbot.combat import knife_chain_air_native as mod
    from ssbot.knowledge import kinematics as K
    from tests.test_knife_chain_transfer import transfer_motion_scene
    r, state, sim = transfer_motion_scene(K.M_NORMAL)
    r.run = None
    state['ents'][0]['fsms'][0].update(state='Slam Antic', t=.1)
    n = native()
    n._clock = .1
    n.runner = r
    entry = EntryAttack(8, 'stomp', 7, G.CC_SLAM, 4., 10.)
    prefs = GoalPrefs(mode='RUSH', stance_x=48., weights={}, target=8, entry_attack=entry)
    n.goal_preferences(state, prefs, handoff=True)
    n._context = (None, sim, None, None)
    monkeypatch.setattr(n, 'queued_prefix', lambda *a: (int(sim.prefix[0]), 'actual fixture prefix'))
    checked = []
    monkeypatch.setattr(mod.B2Geometry, 'preflight', lambda self, path:
                        checked.append(path) or NS(complete=True, contacts=[]))
    fc = NS(rs=NS(trk=NS(T=.1, now={8: (None, None, None),
              7: (None, None, NS(fam='CC_SLAM', t0=source_shift))})))
    offer = n._transfer_offer(state, .1, sim, fc, prefs, True)
    assert (offer is not None) == available
    assert bool(checked) == available
    if available:
        assert offer.draft.run.chain == 'rune_transfer'
        assert offer.mask == int(sim.prefix[0])
        assert offer.draft.run.v['_entry_source_confirmed']
        assert not n._receipts and n.commitment is None  # no fabricated send


def test_cast_transfer_air_entry_uses_attack_adapter_when_destination_starts_slam():
    n = native()
    s = cast_scene()
    s['ents'][1]['fsms'][0].update(state='Slam Antic', t=0.)
    n._transfer_goal = TransferGoal(8, 7, 1000, 20.)
    prefs = GoalPrefs(mode='RUSH', stance_x=38., weights={}, target=8)
    n.goal_preferences(s, prefs, handoff=True)
    assert n._transfer_ready and n._transfer_blade[2] == 'air_contact'
    s['hero']['box'][1] = 3.015
    n.goal_preferences(s, prefs, handoff=True)
    assert not n._transfer_ready  # ground slam still belongs to its own adapter


@pytest.mark.parametrize('family,recovers', [('RUNE_TRANSFER', False), ('CC_SLAM', True)])
def test_approach_clock_is_not_compared_to_new_target_slam_origin(monkeypatch, family, recovers):
    n = native()
    s = cast_scene()
    s['ents'][1]['fsms'][0].update(state='Slam Antic', t=0.)
    n.commitment = {'move': MoveInstance(8, 990, family), 'ta': 19.}
    n._press = n._accepted = n._hit = None
    recovered = []
    monkeypatch.setattr(n, '_observe_application', lambda *a: None)
    monkeypatch.setattr(n, '_observe_hook_start', lambda *a: None)
    monkeypatch.setattr(n, '_recover', lambda reason, f: recovered.append(reason))
    n.observe(s)
    assert bool(recovered) == recovers
    if recovers: assert recovered == ['target started a new slam instance']


def test_real_bounce_uses_hit_targets_slam_tail_not_previous_cast_responsibility():
    n = native()
    s = cast_scene()
    s['ents'][1]['fsms'][0].update(state='Slam 1', t=0.)
    s['hero']['cstate_int'] = [0, 8]
    s['ev'] = [{'k': 'hit', 'f': 1000, 'd': {'ent': 8, 'src': 'DownSlash'}}]
    move = plan().move
    physical = MoveInstance(8, 946, 'CC_SLAM')
    parent = MoveInstance(7, 990, 'CC_CAST')
    n.post_context = {'move': move, 'bounce': 1000, 'hit': 1000, 'ta': 19.}
    n._transfer_responsibility[move] = (parent, 19.)
    n._transfer_target_moves[move] = (physical, 19.1)
    prefs = GoalPrefs(mode='RUSH', stance_x=25., weights={}, target=7)
    assert n.observe_bounce_goal(s, prefs)
    assert n._transfer_goal.responsibility == physical
    assert n._transfer_goal.cast_ta == 19.1
    assert n._transfer_goal.caster == 8
    assert n._transfer_responsibility[move] == (parent, 19.)


@pytest.mark.parametrize('state,binds', [('Slam Antic', True), ('Slam 1', False)])
def test_target_slam_starting_at_actual_bounce_is_bound_or_handed_to_normal_planner(state, binds):
    n = native()
    s = cast_scene()
    s['ents'][1]['fsms'][0].update(state=state, t=0.)
    s['hero']['cstate_int'] = [0, 8]
    s['ev'] = [{'k': 'hit', 'f': 1000, 'd': {'ent': 8, 'src': 'DownSlash'}}]
    move = plan().move
    n.post_context = {'move': move, 'bounce': 1000, 'hit': 1000, 'ta': 19.}
    n._transfer_responsibility[move] = (MoveInstance(7, 990, 'CC_CAST'), 19.)
    prefs = GoalPrefs(mode='RUSH', stance_x=25., weights={}, target=7)
    assert n.observe_bounce_goal(s, prefs) == binds
    if binds:
        assert n._transfer_goal.responsibility == MoveInstance(8, 1000, 'CC_SLAM')
        assert n._transfer_goal.cast_ta == 20.
    else:
        assert n.post_context is None and n.runner.run is None and n._transfer_goal is None


@pytest.mark.parametrize('state', ['Idle', 'Slam Recover'])
def test_finished_target_slam_is_not_reused_as_a_later_bounce_source(state):
    n = native()
    s = cast_scene()
    s['ents'][1]['fsms'][0].update(state=state, t=0.)
    s['hero']['cstate_int'] = [0, 8]
    s['ev'] = [{'k': 'hit', 'f': 1000, 'd': {'ent': 8, 'src': 'DownSlash'}}]
    move = plan().move
    parent = MoveInstance(7, 990, 'CC_CAST')
    n.post_context = {'move': move, 'bounce': 1000, 'hit': 1000, 'ta': 19.}
    n._transfer_responsibility[move] = (parent, 19.)
    n._transfer_target_moves[move] = (MoveInstance(8, 946, 'CC_SLAM'), 19.1)
    prefs = GoalPrefs(mode='RUSH', stance_x=25., weights={}, target=7)
    assert n.observe_bounce_goal(s, prefs)
    assert n._transfer_goal.responsibility == parent
    assert n._transfer_goal.cast_ta == 19.


@pytest.mark.parametrize('family', [G.CC_SLAM, G.CC_JUMP, G.CC_JUMP_CAST])
def test_side_entry_yields_to_the_new_targets_own_attack(monkeypatch, family):
    tac = l2()
    entry = EntryAttack(2, 'side', 1, G.CC_SLAM, 12., 10.)
    tac.goal = G.Goal(G.RUSH, 2, 40., 10., family=G.CC_IDLE, entry_attack=entry)
    monkeypatch.setattr(tac, '_pick', lambda *a: tac.goal)
    target = subj(2, CC, 40., state='Slam Antic', family=family, committed=True)
    out = tac._decide(world(30., t=10.1), WinFc([subj(1, CC, 14.), target]),
                      GoalPrefs(mode='ENGAGE', stance_x=40., weights={}, hit_w={2: 3.}))
    assert out.target == 2 and out.entry_attack is None
    assert out.hit_kw.get(2) != (3., 0., 0., 0.)


@pytest.mark.parametrize('kind', ['stomp', 'side'])
def test_unfulfilled_entry_bias_expires_without_a_hit(monkeypatch, kind):
    tac = l2()
    entry = EntryAttack(2, kind, 1, G.CC_SLAM, 12., 10.)
    tac.goal = G.Goal(G.RUSH, 2, 40., 10., family=G.CC_IDLE, entry_attack=entry)
    monkeypatch.setattr(tac, '_pick', lambda *a: tac.goal)
    out = tac._decide(world(30., t=12.01), WinFc([subj(1, CC, 14.), subj(2, CC, 40., family=G.CC_IDLE)]),
                      GoalPrefs(mode='ENGAGE', stance_x=40., weights={}, hit_w={2: 3.}))
    assert out.target == 2 and out.entry_attack is None


def test_completed_source_tail_cannot_restart_on_the_sources_next_slam():
    import numpy as np
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.knife_chain_transfer import propose
    from ssbot.knowledge import kinematics as K
    from tests.test_knife_chain_transfer import transfer_motion_scene
    r, s, oldsim = transfer_motion_scene(K.M_NORMAL)
    s['hero'].update(pos=[25., 12.], box=[24.75, 10.45, 25.25, 12.53], vel=[8.25, 0.])
    s['ents'][0]['fsms'][0].update(state='Slam Recover', t=0.)
    S = K.initial_state(oldsim.params, 25., 12., vx=8.25, ground=False)
    sim = ChainSim(S, oldsim.prefix, oldsim.hold, oldsim.params, oldsim.terrain, 1000, 1000)
    variables = plan().variables(); variables['side'] = 2; variables['air_entry'] = True
    r.run = Run('rune_transfer', 'bounce_tail', variables)
    goal = TransferGoal(8, 7, 1000, 0., 'BOUNCE', MoveInstance(7, 946, 'CC_SLAM'))
    first = propose(r, s, 0., sim, 8, False, np.zeros((0, 6)), set(), goal)
    assert first is not None and first[0].run.link != 'bounce_tail'
    s['f'] = 1001
    s['ents'][0]['fsms'][0].update(state='Slam 0', t=0.)
    sim2 = ChainSim(S, oldsim.prefix, oldsim.hold, oldsim.params, oldsim.terrain, 1001, 1001)
    again = propose(first[0], s, 1/60., sim2, 8, False, np.zeros((0, 6)), set(), goal)
    assert again is not None and again[0].run.link != 'bounce_tail'


@pytest.mark.parametrize('committed', [False, True])
def test_delayed_switch_binding_cannot_outlive_its_intent_unless_already_committed(committed):
    n = native()
    s = cast_scene()
    s['ents'][0]['fsms'][0].update(state='Slam Antic', t=.25)
    entry = EntryAttack(8, 'stomp', 7, G.CC_SLAM, 4., 10.)
    prefs = GoalPrefs(mode='RUSH', stance_x=38., weights={}, target=8, entry_attack=entry)
    n.goal_preferences(s, prefs, handoff=False)
    assert n._transfer_goal is None
    n.goal_preferences(s, prefs, handoff=True)
    goal = n._transfer_goal
    assert goal is not None and goal.source_kind == 'SWITCH'
    if committed: n.commitment = {'existing': True}
    n.goal_preferences(s, replace(prefs, entry_attack=None), handoff=True)
    if committed:
        assert n._transfer_goal == goal and n.commitment == {'existing': True}
    else:
        assert n._transfer_goal is None and not n._transfer_ready
