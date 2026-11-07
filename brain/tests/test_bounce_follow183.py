"""Task 183 (Sol seq 261): after a real DownSlash bounce off one Clapper's own slam, with the two close, the chain's
follow-up prefers the middle (land between the two real bodies), aims the existing witnessed down-slash over the seam when
no standable gap exists, and takes a legal ordinary left / right landing when the middle is not safe.

Production-shaped fixture: the forum hero model (hero_wanderer_forum, HERO2 kinematics, the oracle hold filter), fitted
Clapper poses (map2.clapper Know) at the w13_331 2983 roots (bounced 335476 at 36.86, the other at 24.1, both facing
right), the hero 9 frames after the 2974 bounce at its recorded x / height / rise. The B2 geometry is a fixture: both
current bodies and the named dangers, every frame, all owners (the production RangeSupport is in the replays). Each tick
runs NativeManualAirChain._transfer_offer -> knife_chain_transfer.propose on the real chain table; the offered key is
applied by the hero model (the in-flight prefix one frame later), so the Run's own route meets the actual landing."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import knife_chain_air_native as N
from ssbot.combat import knife_chain_transfer as T
from ssbot.combat.air_chain import ChainSim
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.combat.knife_chain_air import model_path
from ssbot.combat.knife_chain_commitment import ContactScan, MoveInstance, PathContact
from ssbot.combat.knife_chain_eval import Run, X
from ssbot.combat.knife_chain_format import MASK_NAMES as B
from ssbot.combat.knife_chain_transfer import TransferGoal, TransferPlan
from ssbot.combat.tactics.modes import GoalPrefs
from ssbot.knowledge import kinematics as K
from tests.test_knife_chain_transfer import fit_pose
from tests.test_target_entry_attack import native

ROOT = Path(__file__).resolve().parents[2]
PARAMS = K.hero2(K.HeroParams.load(ROOT / 'knowledge/1.0.30000/kinematics/hero_wanderer_forum.json'))
TERRAIN = K.Terrain2D.from_boxes([(-100., -10., 100., 3.015)])
BOUNCE_F, F0 = 2974, 2983
LR = B['L'] | B['R']


def clapper(iid, x, face=1, state='Idle'):
    e = {'iid': iid, 'type_key': 'Song Heavy Sentry', 'hp': 100, 'pos': [x, 7.45], 'vel': [0., 0.], 'flipX': face > 0,
         'fsms': [{'name': 'Control', 'state': state, 't': .2}],
         'colliders': [{'name': 'Song Heavy Sentry', 'enabled': True, 'verts_world': [0.] * 8}]}
    return fit_pose(e)


def hf(hold):
    bits = lambda a: int((a[0].astype(np.int64) << np.arange(a.shape[1], dtype=np.int64)).sum())
    return {'latched': bits(hold.latched), 'desired': bits(hold.desired),
            'pending': [int(v) for v in hold.pending[0]], 'age': [int(v) for v in hold.age[0]]}


class Bout:
    """One bounce follow-up, closed loop: the chain's offered key reaches the hero model two frames later."""

    def __init__(self, monkeypatch, *, bounced=(8, 36.86, 1), other=(7, 24.1, 1), hero=(37.821, 10.774, 11.4),
                 danger=(), stance_x=31., link='bounce_tail', tail_done=False):
        self.n = n = native()
        self.ents = [clapper(other[0], other[1], other[2]), clapper(bounced[0], bounced[1], bounced[2])]
        self.bounced, self.other = bounced[0], other[0]
        self.f, self.game = F0, 20.
        ta = self.game - (F0 - BOUNCE_F) / 60.
        self.plan = p = TransferPlan(bounced[0], bounced[0], BOUNCE_F, BOUNCE_F, ta, 0, 2, 0, 0, False, BOUNCE_F, 0)
        v = dict(n.runner.chains['rune_transfer'].vars)
        v.update(p.variables())
        v.update(source_tail_admitted=True, source_tail_mask=0, source_tail_checked_through=BOUNCE_F + 11,
                 source_tail_done=tail_done, air_entry=True)
        n.runner.run = Run('rune_transfer', link, v)
        self.goal = TransferGoal(bounced[0], bounced[0], BOUNCE_F, ta, 'BOUNCE', MoveInstance(bounced[0], BOUNCE_F - 52, 'CC_SLAM'))
        n._transfer_goal = self.goal
        n._transfer_ready = True
        n.commitment = {'move': p.move, 'origin': BOUNCE_F, 'ta': ta, 'predicted_bounce': None}
        n._transfer_responsibility[p.move] = (self.goal.responsibility, ta)
        n._context = (None, None, None, np.zeros((0, 6)))
        self.S = K.initial_state(PARAMS, hero[0], hero[1], vy=hero[2], ground=False)
        self.hold = K.HoldState.idle()
        self.prefix = 0
        self.prefs = GoalPrefs(mode='RUSH', stance_x=stance_x, weights={}, target=bounced[0])
        self.scans = []
        bodies = [(*T.body_box(e), e['iid'], 'body') for e in self.ents]
        boxes = bodies + [(*d, 99, 'delayed') for d in danger]
        scans = self.scans

        class Geo:
            def __init__(self, *a):
                pass

            @staticmethod
            def ref(path):
                return f'{path.origin}:{path.through}'

            def _scan(self, path, limit):
                hits = []
                for i, b in enumerate(np.asarray(path.box)[:limit + 1]):
                    for x0, y0, x1, y1, iid, kind in boxes:
                        if b[0] < x1 and b[2] > x0 and b[1] < y1 and b[3] > y0:
                            hits.append(PathContact(path.origin + i, iid, kind))
                return ContactScan(self.ref(path), path.origin, path.origin + limit, tuple(hits), 'fixture: bodies + dangers')

            def scan(self, path, limit=None):
                scans.append(len(path.commands))
                return self._scan(path, len(path.commands) if limit is None else limit)

            def scan_batch(self, paths):
                return [self.scan(p) for p in paths]

            def preflight(self, path):
                return self._scan(path, len(path.commands))

        monkeypatch.setattr(N, 'B2Geometry', Geo)
        monkeypatch.setattr(n, 'queued_prefix', lambda *a: (int(self.prefix), 'fixture: the sent prefix'))
        self.fc = NS(rs=NS(trk=NS(T=self.game, now={bounced[0]: (None, None, NS(fam='CC_SLAM', t0=0.)),
                                                    other[0]: (None, None, None)})))
        self.log = []

    def sim(self):
        return ChainSim(self.S.copy(), np.array([self.prefix], np.int64), self.hold.copy(), PARAMS, TERRAIN, self.f, self.f)

    def state(self, sim):
        box = model_path(sim, self.plan, np.zeros(0, np.int64), self.game).box[0]
        S = self.S
        return {'f': self.f, 'hero': {'pos': [float(S[K.PX]), float(S[K.PY])], 'box': [float(v) for v in box],
                                     'vel': [float(S[K.VX]), float(S[K.VY])], 'health': 7, 'hero_accepting_input': True,
                                     'tm': {'dash_cd': 0.}, 'anim': {'clip': 'Airborne'}},
                'ents': deepcopy(self.ents), 'act': {'hf': hf(self.hold)}}

    def tick(self):
        sim = self.sim()
        s = self.state(sim)
        self.n._actual_state = s
        ground = bool(self.S[K.GROUND] > 0)
        offer = self.n._transfer_offer(s, self.game, sim, self.fc, self.prefs, ground)
        m = 0 if offer is None else int(offer.mask)
        if offer is not None:
            self.n.runner.run = offer.draft.run          # sent: the Run carries on with this link
        self.log.append(dict(f=self.f, offer=offer, mask=m, box=list(s['hero']['box']), ground=ground,
                             link=None if offer is None else offer.draft.run.link))
        step = model_path(sim, self.plan, np.array([m], np.int64), self.game)
        self.S = step.states[:, 1].copy()
        self.hold = hold_filter_jit(np.array([[self.prefix]], np.int64), self.hold)[1]
        self.prefix, self.f, self.game = m, self.f + 1, self.game + 1 / 60.
        return offer

    def run(self, ticks=90):
        for _ in range(ticks):
            self.tick()
            if self.n.runner.run is None:
                break
        return self.log

    def notes(self, event):
        return [e for e in self.n.events if e['event'] == event]


def test_gap_first_legal_key_goes_to_the_middle_and_lands_between_the_bodies(monkeypatch):
    bout = Bout(monkeypatch)
    log = bout.run()
    first = log[0]
    assert first['link'] == 'middle' and first['offer'].stage == 'active'
    assert first['mask'] & LR == B['L']                     # the right one bounced her: the middle is on its left
    assert first['offer'].draft.run.lid == 'rune_transfer.middle'
    follow = first['offer'].details['follow']
    assert follow['kind'] == 'middle' and follow['F0'] == F0 + 2 and follow['other'] == 7
    links = [r['link'] for r in log[:-1]]
    assert set(links) == {'middle'}                          # no strike, no other owner until the landing
    landed = bout.notes('transfer_follow_landed')
    assert len(landed) == 1 and not bout.notes('transfer_follow_missed')
    box = landed[0]['box']
    lo, hi = T.body_box(bout.ents[0])[2], T.body_box(bout.ents[1])[0]
    assert lo < box[0] and box[2] < hi                        # really between the two near body edges
    assert log[-1]['ground'] and bout.n.runner.run is None and bout.n.commitment is None
    assert not bout.n._failure_exposures                      # the move completed: no failure exposure
    masks = first['offer'].details['follow_masks']
    assert any(m & B['L'] for m in masks) and masks[-1] & LR == 0                       # released over the gap
    assert first['offer'].details['checked_through'] == follow['land_f']                 # chosen: the whole route scanned
    owned = log[1]['offer'].details
    assert owned['checked_through'] == F0 + 1 + T.FOLLOW_SCAN_F                           # owned: its next frames


def test_mirror_left_bounced_goes_right_into_the_middle(monkeypatch):
    # the bounced one on the left (root 24.1, facing left), the other on the right; she is over the bounced body
    bout = Bout(monkeypatch, bounced=(8, 24.1, -1), other=(7, 36.86, -1), hero=(23.2, 10.774, 11.4), stance_x=30.)
    log = bout.run()
    assert log[0]['link'] == 'middle' and log[0]['mask'] & LR == B['R']
    landed = bout.notes('transfer_follow_landed')
    lo, hi = T.body_box(bout.ents[1])[2], T.body_box(bout.ents[0])[0]
    assert len(landed) == 1 and lo < landed[0]['box'][0] and landed[0]['box'][2] < hi
    assert not bout.n._failure_exposures


def test_dangerous_middle_takes_the_legal_ordinary_landing(monkeypatch):
    # a delayed hazard on the floor of the whole gap (a rune's area): no middle row and no left landing is legal
    bout = Bout(monkeypatch, danger=[(26.4, 3.0, 35.5, 5.2)])
    log = bout.run()
    assert bout.notes('transfer_follow_middle_blocked')
    side = bout.notes('transfer_follow_side')[0]['verdicts']
    assert [v['kind'] for v in side] == ['left_landing', 'right_landing']
    assert [v['legal'] for v in side] == [False, True]
    assert log[0]['link'] == 'land' and log[0]['mask'] & LR == B['R']
    assert log[0]['offer'].details['follow']['kind'] == 'right_landing'
    landed = bout.notes('transfer_follow_landed')
    assert len(landed) == 1 and landed[0]['link'] == 'land' and landed[0]['box'][0] > 39.
    assert not bout.n._failure_exposures


def test_owned_side_landing_goes_on_when_the_gap_closes(monkeypatch):
    # a left / right landing needs no gap: the other one walking up to the bounced body mid-route changes nothing
    bout = Bout(monkeypatch, danger=[(26.4, 3.0, 35.5, 5.2)])
    bout.tick()
    assert bout.n.runner.run.link == 'land'
    fit_pose(bout.ents[0], x=33.5)                            # bodies now overlap: no standable gap
    assert not T.standable(T.two_gap(bout.state(bout.sim()), 8), (0., 0., .5, 2.))
    log = bout.run()
    assert {r['link'] for r in log[:-1]} == {'land'} and not bout.notes('transfer_follow_gap_closed')
    landed = bout.notes('transfer_follow_landed')
    assert len(landed) == 1 and landed[0]['link'] == 'land' and not bout.n._failure_exposures


def test_owned_landing_sends_the_keys_it_checked_after_its_row_ran_out(monkeypatch):
    # Sol seq 262 item 1: the right landing's absolute row ends before this tick's first free frame (f 2984: row F0 2985
    # only, f+2 = 2986) while she is still in the air: the recheck holds R to the ground, so R is what goes out
    bout = Bout(monkeypatch, danger=[(26.4, 3.0, 35.5, 5.2)])
    bout.tick()
    run = bout.n.runner.run
    assert run.link == 'land'
    run.v['follow'] = {**run.v['follow'], 'masks': run.v['follow']['masks'][:1], 'land_f': F0 + 1}
    offer = bout.tick()
    assert offer is not None and offer.draft.run.link == 'land' and offer.mask & LR == B['R']
    row = offer.draft.run.v['follow']
    assert row['F0'] == F0 + 3 and row['masks'] and all(m & LR == B['R'] for m in row['masks'])
    log = bout.run()
    assert all(r['mask'] & LR == B['R'] for r in log[:-1])                    # every key sent is the checked one
    assert len(bout.notes('transfer_follow_landed')) == 1 and not bout.n._failure_exposures


def test_owned_routes_follow_a_landing_later_than_planned(monkeypatch):
    # the control: after the first tick she is 1.5 u higher than the planned row assumed (a later real landing); the owned
    # middle / landing keeps re-anchoring the checked row, the keys sent stay the checked ones and she still lands
    for danger, link, key in (((), 'middle', B['L']), ([(26.4, 3.0, 35.5, 5.2)], 'land', B['R'])):
        bout = Bout(monkeypatch, danger=danger)
        first = bout.tick()
        planned = first.details['follow']['land_f']
        bout.S[[K.PY, K.QY, K.SY]] += 1.5
        log = bout.run()
        assert {r['link'] for r in log[:-1]} == {link}
        landed = bout.notes('transfer_follow_landed')
        assert len(landed) == 1 and landed[0]['frame'] > planned                # really later than first planned
        for r in log[:-1]:
            fo = r['offer'].draft.run.v['follow']
            i = r['f'] + 2 - fo['F0']
            assert r['mask'] == (fo['masks'][i] if 0 <= i < len(fo['masks']) else 0)   # sent = the row's key
        assert any(r['mask'] & LR == key for r in log[:-1])
        assert not bout.n._failure_exposures


@pytest.mark.parametrize('mirror', [False, True])
def test_middle_dials_back_when_she_is_past_the_goal(monkeypatch, mirror):
    # Sol seq 262 item 2: she is already over the gap next to the other one's near edge; the right (left) one bounced her.
    # The key toward the bounced-to-other direction finds no landing inside; toward the goal it does.
    if mirror:
        bout = Bout(monkeypatch, bounced=(8, 24.1, -1), other=(7, 36.86, -1), hero=(34.21, 10.774, 11.4), stance_x=30.)
        back = B['L']
    else:
        bout = Bout(monkeypatch, hero=(26.75, 10.774, 11.4))
        back = B['R']
    gap = T.two_gap(bout.state(bout.sim()), 8)
    assert gap.direction != back                                               # the old direction would go away
    offer = bout.tick()
    assert offer is not None and offer.draft.run.link == 'middle' and offer.mask & LR == back
    log = bout.run()
    landed = bout.notes('transfer_follow_landed')
    assert len(landed) == 1 and gap.lo < landed[0]['box'][0] and landed[0]['box'][2] < gap.hi
    assert not bout.n._failure_exposures


def test_no_safe_middle_and_no_legal_landing_keeps_the_existing_air_link(monkeypatch):
    bout = Bout(monkeypatch, danger=[(0., 3.0, 60., 5.2)])
    offer = bout.tick()
    assert bout.notes('transfer_follow_middle_blocked') and bout.notes('transfer_follow_none')
    assert offer is not None and offer.draft.run.link in ('air', 'strike')   # the existing follow-up, unchanged


def test_no_gap_aims_the_witnessed_downslash_over_the_seam_then_a_real_bounce_with_a_gap_goes_middle(monkeypatch):
    # the other one stands against the bounced body (bodies overlap): no standable ground between them
    bout = Bout(monkeypatch, other=(7, 33.5, 1))
    gap = T.two_gap(bout.state(bout.sim()), 8)
    assert gap.width < 0 and not T.standable(gap, (0., 0., .5, 2.))
    offer = bout.tick()
    seam = bout.notes('transfer_follow_seam')
    assert seam and offer is not None and offer.draft.run.link in ('air', 'strike')
    aim = T.seam_aim(bout.state(bout.sim()), bout.goal, 8)
    other_edge = T.body_box(bout.ents[0])[2]
    assert abs(aim - (other_edge + .25 + T.MIDDLE_PAD_U + T.SEAM_TOL_U)) < 1e-9   # its inner side, clear of the other body
    assert T.body_box(bout.ents[1])[0] + T.SEAM_INSET_U <= aim               # and over the bounced body
    assert offer.draft.run.v['side'] == B['L']                                # toward that seam
    assert not bout.notes('transfer_follow_middle') and not bout.notes('transfer_follow_side')
    # the next real bounce reads the gap again: the other one has walked back to 24.1, so the follow-up goes middle
    again = Bout(monkeypatch)
    assert again.tick().draft.run.link == 'middle'


def test_an_air_run_without_a_witness_still_takes_an_open_gap(monkeypatch):
    # seq 262: an air Run over its target whose Idle is past its Idle Time has no strike witness (the #317 hand-back);
    # the gap is standable, so the follow-up takes the middle this tick instead of handing back
    bout = Bout(monkeypatch, link='air', tail_done=True)
    bout.ents[1]['fsms'][0]['t'] = 1.2
    offer = bout.tick()
    assert offer is not None and offer.draft.run.link == 'middle'
    assert not bout.notes('transfer_no_witness_handback') and not bout.notes('b2_recovery')
    # no standable gap: the hand-back stands as before
    bout = Bout(monkeypatch, other=(7, 33.5, 1), link='air', tail_done=True)
    bout.ents[1]['fsms'][0]['t'] = 1.2
    assert bout.tick() is None
    assert bout.notes('transfer_no_witness_handback') and bout.notes('b2_recovery')


def test_tail_and_sent_strike_keep_their_ownership(monkeypatch):
    bout = Bout(monkeypatch)
    n = bout.n
    goal = bout.goal
    draft = NS(run=NS(link='bounce_tail', v={'iid': 8, 'source_tail_done': False}))
    assert not n._follow_due(goal, draft, n.runner.run, True, False, False)              # hammer tail still on
    draft = NS(run=NS(link='air', v={'iid': 8, 'source_tail_done': False}))
    assert not n._follow_due(goal, draft, n.runner.run, True, False, False)              # tail not yet declared over
    draft = NS(run=NS(link='air', v={'iid': 8, 'source_tail_done': True}))
    assert n._follow_due(goal, draft, n.runner.run, True, False, False)                  # first post-tail tick
    struck = NS(link='strike')
    assert not n._follow_due(goal, draft, struck, True, False, False)                    # a sent strike row finishes
    assert not n._follow_due(goal, draft, NS(link='claw_lock'), True, False, False)      # a hook too
    assert not n._follow_due(goal, draft, n.runner.run, True, True, False)               # grounded
    assert not n._follow_due(goal, draft, n.runner.run, True, False, True)               # approach only


def test_scope_is_a_bounce_in_a_chain_a_clapper_slam_started():
    slam = MoveInstance(8, 2922, 'CC_SLAM')
    assert T.follow_scope(TransferGoal(8, 8, 2974, 0., 'BOUNCE', slam), 8)
    assert T.follow_scope(TransferGoal(8, 8, 2974, 0., 'BOUNCE', slam), 8, close=False)  # its own target: any distance
    # seq 262: L2's cross-Clapper continuation to the other one, and a later bounce of the same chain off the other one
    # (the slam's responsibility kept), are in scope only when the two were close at the bounce (no standable gap)
    assert T.follow_scope(TransferGoal(7, 8, 2974, 0., 'BOUNCE', slam), 7, close=True)
    assert not T.follow_scope(TransferGoal(7, 8, 2974, 0., 'BOUNCE', slam), 7, close=False)
    assert T.follow_scope(TransferGoal(7, 7, 3012, 0., 'BOUNCE', slam), 7)              # the chain's later bounce
    assert not T.follow_scope(TransferGoal(7, 8, 2974, 0., 'BOUNCE', slam), 8, close=True)   # not this Run's target
    assert not T.follow_scope(TransferGoal(8, 8, 2974, 0., 'BOUNCE', MoveInstance(8, 2922, 'CC_CAST')), 8)
    assert not T.follow_scope(TransferGoal(8, 8, 2974, 0., 'SWITCH', slam), 8)
    assert not T.follow_scope(None, 8)


def test_cross_clapper_continuation_to_a_distant_one_is_unchanged(monkeypatch):
    # L2 switched to the other one after the bounce and the two stand apart (standable gap): the existing transfer to it
    bout = Bout(monkeypatch)
    bout.goal = TransferGoal(7, 8, BOUNCE_F, bout.goal.cast_ta, 'BOUNCE', bout.goal.responsibility)
    bout.n._transfer_goal = bout.goal
    run = bout.n.runner.run
    run.v.update(iid=7)
    bout.prefs = GoalPrefs(mode='RUSH', stance_x=31., weights={}, target=7)
    s = bout.state(bout.sim())
    assert not T.bounce_close(s, bout.goal, s['hero'])
    offer = bout.tick()
    assert offer is not None and offer.draft.run.link not in T.FOLLOW_LINKS
    assert not bout.notes('transfer_follow_decision') and not offer.draft.run.v.get('follow_close')


def test_seam_aim_is_the_target_inner_side_clear_of_the_other_body(monkeypatch):
    # bodies overlap: the bounced right one [35.52, 39.11], the other [32.16, 35.75]; her half width 0.25
    bout = Bout(monkeypatch, other=(7, 33.5, 1))
    s = bout.state(bout.sim())
    assert T.bounce_close(s, bout.goal, s['hero'])
    right, left = T.body_box(bout.ents[1]), T.body_box(bout.ents[0])
    aim = T.seam_aim(s, bout.goal, 8)                                          # target the bounced (right) one
    assert abs(aim - (left[2] + .25 + T.MIDDLE_PAD_U + T.SEAM_TOL_U)) < 1e-9 and right[0] < aim < right[2]
    cross = TransferGoal(7, 8, BOUNCE_F, bout.goal.cast_ta, 'BOUNCE', bout.goal.responsibility)
    assert T.seam_aim(s, cross, 7) is None                                     # cross target: only when close at start
    aim = T.seam_aim(s, cross, 7, close=True)                                  # L2 switched to the left one
    assert abs(aim - (right[0] - .25 - T.MIDDLE_PAD_U - T.SEAM_TOL_U)) < 1e-9 and left[0] < aim < left[2]


def test_owned_middle_landing_outside_the_gap_recovers_with_its_responsibility(monkeypatch):
    bout = Bout(monkeypatch)
    bout.tick()
    run = bout.n.runner.run
    assert run.link == 'middle'
    # she is put on the ground beyond the other body (outside the gap): not the middle's completion
    bout.S = K.initial_state(PARAMS, 20., 4.568, ground=True)
    sim = bout.sim()
    s = bout.state(sim)
    bout.n._actual_state = s
    assert bout.n._transfer_offer(s, bout.game, sim, bout.fc, bout.prefs, True) is None
    assert bout.notes('transfer_follow_missed') and not bout.notes('transfer_follow_landed')
    assert len(bout.n._failure_exposures) == 1                # failure responsibility kept (the source slam)
    assert bout.n._failure_exposures[0].move == bout.goal.responsibility
    assert bout.n.runner.run is None


def test_follow_keys_read_the_absolute_row(monkeypatch):
    from ssbot.combat.knife_chain_air import AirAnchor
    bout = Bout(monkeypatch)
    v = dict(bout.n.runner.run.v)
    v['follow'] = {'F0': 100, 'masks': [B['L'] | B['DASH'], B['L'], 0]}
    keys = []
    for link in ('middle', 'land'):
        for F in (99, 100, 101, 102, 103):
            d = bout.n.runner.fork_empty(AirAnchor())
            d.run = Run('rune_transfer', link, dict(v))
            keys.append(d.eval_link(X(d, d.run, NS(f=F - 2, F=F, k=10, target_valid=True, ground=False))))
    assert keys == [0, B['L'] | B['DASH'], B['L'], 0, 0] * 2
