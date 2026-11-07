"""Task 183 (Sol seq 261): after a real DownSlash bounce off one Clapper's own slam, with the two close, the chain's
follow-up prefers the middle (land between the two real bodies), aims the existing witnessed down-slash over the seam when
no standable gap exists, and takes a legal ordinary left / right landing when the middle is not safe. Sol seq 265 (the
person: go to the middle whether or not there is room): with no clean middle landing now the seam strike keeps to the
middle every tick; the ordinary landing only when that action's own gate turns it down; an owned landing re-chooses a
clean middle; an owned middle whose gap closes goes on by the seam approach.

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
        # seq 265: block_steps puts a fixture contact on every two-frame current step (the air link's own gate) while
        # whole routes scan as before; boxes stays mutable (a danger can go or come mid-run)
        self.block_steps = False
        bodies = [(*T.body_box(e), e['iid'], 'body') for e in self.ents]
        boxes = self.boxes = bodies + [(*d, 99, 'delayed') for d in danger]
        scans = self.scans
        bout = self

        class Geo:
            def __init__(self, forecast, f, move, instance):
                self.target = move.target_iid

            @staticmethod
            def ref(path):
                return f'{path.origin}:{path.through}'

            def _scan(self, path, limit, external_only=False):
                hits = []
                for i, b in enumerate(np.asarray(path.box)[:limit + 1]):
                    for x0, y0, x1, y1, iid, kind in boxes:
                        if external_only and iid == self.target and kind != 'delayed':
                            continue
                        if b[0] < x1 and b[2] > x0 and b[1] < y1 and b[3] > y0:
                            hits.append(PathContact(path.origin + i, iid, kind))
                return ContactScan(self.ref(path), path.origin, path.origin + limit, tuple(hits), 'fixture: bodies + dangers')

            def scan(self, path, limit=None):
                scans.append(len(path.commands))
                if bout.block_steps and limit is None and len(path.commands) == 2:
                    return ContactScan(self.ref(path), path.origin, path.origin + 2,
                                       (PathContact(path.origin + 2, 99, 'delayed'),), 'fixture: blocked current step')
                return self._scan(path, len(path.commands) if limit is None else limit)

            def scan_batch(self, paths):
                return [self.scan(p) for p in paths]

            def preflight(self, path):
                # as B2Geometry.preflight: other owners and every delayed hazard, not the target's own body
                return self._scan(path, len(path.commands), external_only=True)

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


MIRROR_X = 60.96   # the fixtures' mirror: x -> 60.96 - x (36.86 <-> 24.1, 33.5 <-> 27.46)


def _blocked_bout(monkeypatch, mirror, **kw):
    # a delayed hazard on the floor of the whole gap (a rune's area): no middle landing row is clean, no landing on the
    # middle side; the outer landing (right of the right bounced one; mirrored: left of the left one) is legal
    m = (lambda x: MIRROR_X - x) if mirror else (lambda x: x)
    if mirror:
        bout = Bout(monkeypatch, bounced=(8, m(36.86), -1), other=(7, m(24.1), -1), hero=(m(37.821), 10.774, 11.4),
                    stance_x=30., danger=[(m(35.5), 3.0, m(26.4), 5.2)], **kw)
    else:
        bout = Bout(monkeypatch, danger=[(26.4, 3.0, 35.5, 5.2)], **kw)
    return bout, m


def _landing_bout(monkeypatch, mirror=False, **kw):
    # the blocked middle, and no seam action: the Idle target past its Idle Time has no strike witness possible (Task 179
    # #317's definite end): the legal outer landing goes on the first tick
    bout, _ = _blocked_bout(monkeypatch, mirror, link='air', tail_done=True, **kw)
    bout.ents[1]['fsms'][0]['t'] = 1.2
    return bout


@pytest.mark.parametrize('mirror', [False, True])
def test_blocked_middle_stays_on_the_middle_by_the_inner_seam_strike(monkeypatch, mirror):
    # Sol seq 265 (the person: go to the middle whether or not there is room; without it down-slash and wait): the gap is
    # standable but no middle landing row is clean now. The legal outer landing the old code took at once is not the
    # default any more: the follow-up keeps to the middle by the seam approach over the bounced one's inner side and its
    # witnessed inner down-slash; she never lands in the unsafe gap
    bout, m = _blocked_bout(monkeypatch, mirror, link='air', tail_done=True)
    bout.ents[1]['fsms'][0]['t'] = 0.                                       # Idle from t 0: a strike witness
    sim = bout.sim()
    out = B['L'] if mirror else B['R']
    row = T.landing_row(sim, out)                                           # the outer landing is legal from here
    assert row is not None and not N.B2Geometry(None, F0, bout.plan.move, None).scan(
        model_path(sim, bout.plan, row[0], bout.game)).contacts
    log = bout.run(12)
    assert bout.notes('transfer_follow_middle_blocked') and not bout.notes('transfer_follow_side')
    seam = bout.notes('transfer_follow_seam')
    assert seam[0]['gap_standable'] and seam[0]['middle'] == 'no clean middle landing route now'
    root, sign, aim = seam[0]['inner']
    assert (root, sign) == (m(36.86), 1 if mirror else -1)
    sent = [r for r in log if r['offer'] is not None]
    assert sent and all(r['link'] in ('air', 'strike') for r in sent)      # no landing, middle or outer
    inward = B['R'] if mirror else B['L']
    assert sent[0]['mask'] & LR == inward and not sent[0]['mask'] & B['A']
    strike = next(e['strike'] for e in seam if e['strike'])                 # the witnessed down-slash, first contact inner
    assert (strike['contact_x'] - strike['inner_bound']) * sign >= 0
    assert all((r['contact_x'] - r['bound']) * sign < 0 for e in seam for r in e['outer_rejected'] or ())
    assert not bout.notes('transfer_follow_landed') and not bout.notes('b2_recovery')


@pytest.mark.parametrize('mirror', [False, True])
def test_no_strike_witness_on_the_target_takes_the_legal_ordinary_landing(monkeypatch, mirror):
    # the same blocked middle, but no strike witness is possible on the bounced one (its Idle past its Idle Time: Task 179
    # #317's definite end): no seam action to keep to the middle with, the existing legal outer landing, the reason recorded
    bout = _landing_bout(monkeypatch, mirror)
    offer = bout.tick()
    gone = bout.notes('transfer_follow_seam_unavailable')
    assert len(gone) == 1 and gone[0]['reason'].startswith('no strike witness possible')
    assert not bout.notes('transfer_follow_seam')
    out = B['L'] if mirror else B['R']
    assert offer is not None and offer.draft.run.link == 'land' and offer.mask & LR == out
    assert not bout.notes('transfer_no_witness_handback') and not bout.notes('b2_recovery')
    bout.run()
    landed = bout.notes('transfer_follow_landed')
    assert len(landed) == 1 and landed[0]['link'] == 'land' and not bout.n._failure_exposures


@pytest.mark.parametrize('mirror', [False, True])
def test_seam_step_blocked_takes_the_legal_ordinary_landing(monkeypatch, mirror):
    # the seam action (a strike witness possible) whose current step the external step gate turns down (a fixture contact
    # on every two-frame step) while the whole outer-landing route is clear: only then the landing goes, the reason recorded
    bout, _ = _blocked_bout(monkeypatch, mirror, link='air', tail_done=True)
    bout.ents[1]['fsms'][0]['t'] = 0.
    bout.block_steps = True
    offer = bout.tick()
    assert bout.notes('transfer_follow_seam')                               # the middle was tried first
    blocked = bout.notes('transfer_follow_seam_blocked')
    assert len(blocked) == 1 and blocked[0]['reason'].startswith('external step blocked')
    assert blocked[0]['fallback'] == ('left_landing' if mirror else 'right_landing') and bout.notes('rune_transfer_rejected')
    out = B['L'] if mirror else B['R']
    assert offer is not None and offer.draft.run.link == 'land' and offer.mask & LR == out
    assert not bout.notes('b2_recovery')


def test_blocked_seam_with_no_legal_landing_keeps_the_gates_hand_back(monkeypatch):
    # danger on the whole floor: no middle and no left / right landing; the seam action's step turned down by the gate:
    # the gate's own hand-back stands, failure responsibility kept, the reason recorded
    bout = Bout(monkeypatch, danger=[(0., 3.0, 60., 5.2)], link='air', tail_done=True)
    bout.ents[1]['fsms'][0]['t'] = 0.
    bout.block_steps = True
    assert bout.tick() is None
    blocked = bout.notes('transfer_follow_seam_blocked')
    assert len(blocked) == 1 and blocked[0]['fallback'] is None and blocked[0]['reason'].startswith('external step blocked')
    assert bout.notes('b2_recovery') and len(bout.n._failure_exposures) == 1


def test_seam_does_not_approach_a_target_no_strike_is_possible_on(monkeypatch):
    # an owned middle route whose gap closes while the target scuttles (Evade Scuttle: no fitted still pose, the 0ed5c779
    # w13_331 3725 shape): no seam action toward it; the closed gap's original hand-back stands
    bout = Bout(monkeypatch)
    assert bout.tick().draft.run.link == 'middle'
    fit_pose(bout.ents[0], x=33.5)
    bout.ents[1]['fsms'][0]['state'] = 'Evade Scuttle'
    assert bout.tick() is None
    gone = bout.notes('transfer_follow_seam_unavailable')
    assert gone and gone[-1]['reason'] == 'no strike witness possible: no fitted still pose in Evade Scuttle'
    assert bout.notes('transfer_follow_gap_closed') and bout.notes('b2_recovery') and len(bout.n._failure_exposures) == 1


def test_owned_landing_rechooses_a_clean_middle(monkeypatch):
    # Sol seq 265: an outer landing in progress goes back to the middle once a whole middle landing route is clean (she is
    # over the bounced body's middle: after one tick of the outer key the reversal still clears its near edge)
    bout = _landing_bout(monkeypatch, hero=(37.2, 10.774, 11.4))
    bout.tick()
    assert bout.n.runner.run.link == 'land'
    del bout.boxes[2:]                                                       # the danger on the gap floor is gone
    offer = bout.tick()
    assert offer is not None and offer.draft.run.link == 'middle'
    again = bout.notes('transfer_follow_rechosen')
    assert len(again) == 1 and again[0]['old_kind'] == 'right_landing' and again[0]['new'] == 'middle'
    bout.run()
    landed = bout.notes('transfer_follow_landed')
    lo, hi = T.body_box(bout.ents[0])[2], T.body_box(bout.ents[1])[0]
    assert len(landed) == 1 and landed[0]['link'] == 'middle' and lo < landed[0]['box'][0] and landed[0]['box'][2] < hi
    assert not bout.n._failure_exposures


@pytest.mark.parametrize('mirror', [False, True])
def test_owned_landing_goes_back_to_the_seam_when_it_opens_first(monkeypatch, mirror):
    # Sol seq 266: the gap floor dangerous (no clean middle landing), a strike witness possible (Idle from t 0). On 2983 the
    # seam's two-frame step is turned down (block_steps): the legal outer landing goes (R; mirrored L). On 2984 the step
    # gate passes again, everything else as sent: the owned outer landing no longer locks the seam out; it is released to
    # the air link and the inward key goes (L; mirrored R) through 2986, then the witnessed inner strike row
    bout, m = _blocked_bout(monkeypatch, mirror, link='air', tail_done=True)
    bout.ents[1]['fsms'][0]['t'] = 0.
    bout.block_steps = True
    out, inward = (B['L'], B['R']) if mirror else (B['R'], B['L'])
    first = bout.tick()
    assert first.draft.run.link == 'land' and first.mask & LR == out
    bout.block_steps = False
    sent = [bout.tick() for _ in range(3)]                                  # 2984 .. 2986
    assert all(o is not None and o.draft.run.link == 'air' and o.mask & LR == inward and not o.mask & B['A'] for o in sent)
    assert sent[0].draft.run.v.get('follow') is None
    seam = [e for e in bout.notes('transfer_follow_seam') if e['frame'] == F0 + 1]
    assert seam and seam[0]['released'] == 'land' and not bout.notes('transfer_follow_seam_blocked')[1:]
    log = bout.run(6)
    assert any(r['link'] == 'strike' and r['mask'] & B['D'] for r in log)  # its witnessed inner down-slash
    assert not bout.notes('b2_recovery') and not bout.n._failure_exposures


@pytest.mark.parametrize('mirror', [False, True])
def test_owned_landing_goes_on_while_the_seam_stays_blocked(monkeypatch, mirror):
    # Sol seq 266's counterexample: the seam step stays turned down. The seam is tried first every tick; the owned outer
    # landing, still legal, goes on with its own checked keys (its route kept, never re-chosen), no hand-back
    bout, m = _blocked_bout(monkeypatch, mirror, link='air', tail_done=True)
    bout.ents[1]['fsms'][0]['t'] = 0.
    bout.block_steps = True
    out = B['L'] if mirror else B['R']
    log = bout.run()
    assert {r['link'] for r in log[:-1]} == {'land'} and all(r['mask'] & LR == out for r in log[:-1])
    tried = [e for e in bout.notes('transfer_follow_seam') if e['released'] == 'land']
    blocked = bout.notes('transfer_follow_seam_blocked')
    assert len(tried) >= 3 and len(blocked) == len(tried) + 1                # + the first tick's fresh choice
    assert all(b['fallback'] == ('left_landing' if mirror else 'right_landing') for b in blocked)
    assert not bout.notes('transfer_follow_route_blocked') and len(bout.notes('transfer_follow_side')) == 1
    landed = bout.notes('transfer_follow_landed')
    assert len(landed) == 1 and landed[0]['link'] == 'land' and not bout.n._failure_exposures


def test_owned_landing_no_longer_legal_hands_back(monkeypatch):
    # the owned outer landing invalidated (a danger appears in its way right after it was sent): with the seam step turned
    # down, the gate's own hand-back; with no seam action at all (no strike witness possible), the follow-up's hand-back;
    # failure responsibility kept either way and the reason recorded
    for no_witness in (False, True):
        bout, _ = _blocked_bout(monkeypatch, False, link='air', tail_done=True)
        bout.ents[1]['fsms'][0]['t'] = 1.2 if no_witness else 0.
        bout.block_steps = not no_witness
        assert bout.tick().draft.run.link == 'land'
        bout.block_steps = True
        bout.boxes.append((38.25, 8.0, 38.6, 13.0, 99, 'delayed'))          # in the outer route's next frames
        assert bout.tick() is None
        assert bout.notes('transfer_follow_route_blocked') and bout.notes('b2_recovery')
        assert len(bout.n._failure_exposures) == 1
        reason = bout.notes('b2_recovery')[-1]['reason']
        if no_witness:
            assert reason == 'bounce follow-up: no seam action and the owned outer landing no longer legal'
            assert bout.notes('transfer_follow_seam_unavailable')
        else:
            assert reason == 'rune transfer external step blocked'
            assert bout.notes('transfer_follow_seam_blocked')[-1]['fallback'] is None


def test_owned_middle_whose_gap_closes_goes_on_by_the_seam_approach(monkeypatch):
    # Sol seq 265 (no room: down-slash and wait for room): the other one walks up to the bounced body mid-route; the owned
    # middle route is released to the seam approach on the same Run instead of the old hand-back
    bout = Bout(monkeypatch)
    assert bout.tick().draft.run.link == 'middle'
    fit_pose(bout.ents[0], x=33.5)
    assert not T.standable(T.two_gap(bout.state(bout.sim()), 8), (0., 0., .5, 2.))
    offer = bout.tick()
    assert bout.notes('transfer_follow_gap_closed')
    seam = bout.notes('transfer_follow_seam')
    assert seam and seam[-1]['released'] == 'middle' and not seam[-1]['gap_standable']
    assert offer is not None and offer.draft.run.link in ('air', 'strike') and offer.draft.run.v.get('follow') is None
    assert not bout.notes('b2_recovery') and not bout.n._failure_exposures


def test_owned_side_landing_goes_on_when_the_gap_closes(monkeypatch):
    # a left / right landing needs no gap: the other one walking up to the bounced body mid-route changes nothing
    bout = _landing_bout(monkeypatch)
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
    bout = _landing_bout(monkeypatch)
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
    for make, link, key in ((lambda: Bout(monkeypatch), 'middle', B['L']), (lambda: _landing_bout(monkeypatch), 'land', B['R'])):
        bout = make()
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


def test_no_safe_middle_and_no_legal_landing_keeps_the_seam_approach(monkeypatch):
    # seq 265: the existing air link goes on as before, now aimed at the bounced one's inner side (the middle stays the goal)
    bout = Bout(monkeypatch, danger=[(0., 3.0, 60., 5.2)])
    offer = bout.tick()
    assert bout.notes('transfer_follow_middle_blocked') and bout.notes('transfer_follow_seam')
    assert not bout.notes('transfer_follow_none') and not bout.notes('transfer_follow_side')
    assert offer is not None and offer.draft.run.link in ('air', 'strike')
    assert offer.draft.run.v['side'] == B['L']


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


def _seam_bout(monkeypatch, mirror, hero_x):
    # bodies overlap (gap -0.233), the bounced one in Idle from t 0; she is falling (vy -7) from 9.25
    if mirror:
        bout = Bout(monkeypatch, bounced=(8, 24.1, -1), other=(7, 27.46, -1), hero=(hero_x, 9.25, -7.0), link='air', tail_done=True)
    else:
        bout = Bout(monkeypatch, other=(7, 33.5, 1), hero=(hero_x, 9.25, -7.0), link='air', tail_done=True)
    bout.ents[1]['fsms'][0]['t'] = 0.
    return bout


@pytest.mark.parametrize('mirror', [False, True])
def test_seam_strike_turns_down_a_row_that_first_meets_the_outer_side(monkeypatch, mirror):
    # Sol seq 263: she is over the bounced one's outer (front) side; steering the key inward alone left the same row's
    # early outer contact (2989, x 38.155 with the root at 36.86). Now no row whose first contact is outside the target's
    # root / body centre: she keeps positioning inward, and once her step meets the target body the chain hands back
    bout = _seam_bout(monkeypatch, mirror, 22.31 if mirror else 38.65)
    log = bout.run(12)
    seam = [e for e in bout.notes('transfer_follow_seam')]
    first = seam[0]
    root, sign, aim = first['inner']
    assert (root, sign) == ((24.1, 1) if mirror else (36.86, -1))
    assert first['strike'] is None and first['outer_rejected']
    assert all(r['bound'] == root for r in first['outer_rejected'])           # a still body: its root (centre outside)
    assert all((r['contact_x'] - r['bound']) * sign < 0 for e in seam for r in e['outer_rejected'] or ())
    if not mirror:
        assert any(r['contact_frame'] == 2989 and abs(r['contact_x'] - 38.155) < 1e-3 for r in first['outer_rejected'])
    inward = B['R'] if mirror else B['L']
    sent = [r for r in log if r['offer'] is not None]
    assert sent and all(r['offer'].draft.run.link == 'air' and r['mask'] & LR == inward and not r['mask'] & B['A'] for r in sent)
    assert bout.notes('b2_recovery') and len(bout.n._failure_exposures) == 1   # hand-back, responsibility kept


@pytest.mark.parametrize('mirror', [False, True])
def test_seam_strike_on_the_inner_side_still_goes(monkeypatch, mirror):
    # she is over the bounced one's back (inner side) next to the seam: its witnessed strike row goes, first contact inside
    bout = _seam_bout(monkeypatch, mirror, 24.21 if mirror else 36.75)
    offer = bout.tick()
    note = bout.notes('transfer_follow_seam')[0]
    root, sign, aim = note['inner']
    strike = note['strike']
    assert offer is not None and offer.draft.run.link == 'strike' and note['link'] == 'strike'
    assert strike['contact_frame'] == F0 + 6 and strike['inner_bound'] == root and (strike['contact_x'] - root) * sign >= 0
    assert note['mask'] == offer.mask and note['target_frame'] == F0 + 2 and not note['outer_rejected']


@pytest.mark.parametrize('mirror', [False, True])
def test_seam_bound_of_a_walking_target_is_read_at_the_rows_contact_index(monkeypatch, mirror):
    # Sol seq 264 item 1: the right (bounced) one walks at -8 u/s backing off from her (fitted Walk pose from t 0). The old
    # bound took its current root 36.86, and the D+L row's first contact (2989, x 36.815) passed it. The same row's own
    # WalkSupport roots at that contact index are 35.90..36.22: she is outside every one of them, so the row is turned down,
    # she keeps the original approach and the original step gate hands back (responsibility kept).
    from ssbot.combat import pogo_model as PM
    m = (lambda x: MIRROR_X - x) if mirror else (lambda x: x)
    if mirror:
        bout = Bout(monkeypatch, bounced=(8, m(36.86), -1), other=(7, m(33.5), -1), hero=(m(37.31), 9.25, -7.0),
                    link='air', tail_done=True)
    else:
        bout = Bout(monkeypatch, other=(7, 33.5, 1), hero=(37.31, 9.25, -7.0), link='air', tail_done=True)
    fit_pose(bout.ents[1], state='Walk', t=0.)
    bout.ents[1]['vel'] = [8. if mirror else -8., 0.]
    s = bout.state(bout.sim())
    support = T.walk_body_support(bout.ents[1], 1 + 3 + PM.ACTIVE[1], s['hero'])
    roots = support.x + support.step * np.asarray(support.info['steps'][6], float)       # roll index 6 = frame 2989
    assert np.allclose(sorted(roots), sorted([m(35.90), m(36.22)]))
    log = bout.run(12)
    seam = bout.notes('transfer_follow_seam')
    first = seam[0]
    root, sign, aim = first['inner']
    assert (root, sign) == (m(36.86), 1 if mirror else -1) and first['strike'] is None
    row = next(r for r in first['outer_rejected'] if r['contact_frame'] == F0 + 6 and r['direction'] == sign)
    assert abs(row['contact_x'] - m(36.815)) < 1e-3 and abs(row['bound'] - m(35.90)) < 1e-9
    assert (row['contact_x'] - root) * sign >= 0                     # the old current-root bound let this row through
    assert all((r['contact_x'] - r['bound']) * sign < 0 for e in seam for r in e['outer_rejected'] or ())
    sent = [r for r in log if r['offer'] is not None]
    assert sent and all(r['offer'].draft.run.link == 'air' and not r['mask'] & B['A'] for r in sent)   # no seam strike
    assert bout.notes('b2_recovery') and len(bout.n._failure_exposures) == 1


@pytest.mark.parametrize('mirror', [False, True])
def test_seam_side_follows_the_real_roots_when_facing_bodies_overlap_deeply(monkeypatch, mirror):
    # Sol seq 264 item 2: facing each other and overlapping by 3.042 u, the right one's (root 36.86, facing left) body centre
    # 36.4045 lies LEFT of the left one's (root 36.50, facing right) 36.9555: the centres' order made its outer side the
    # inner one. The roots decide the side; body edges still give the gap and the contact geometry. Only the direction is
    # checked here: no room is claimed, the original gates stay (the step gate hands back on the other body).
    m = (lambda x: MIRROR_X - x) if mirror else (lambda x: x)
    bout = Bout(monkeypatch, bounced=(8, m(36.86), 1 if mirror else -1), other=(7, m(36.50), -1 if mirror else 1),
                hero=(m(36.0), 9.25, -7.0), link='air', tail_done=True)
    bout.ents[1]['fsms'][0]['t'] = 0.
    fit_pose(bout.ents[1])
    tb, ob = T.body_box(bout.ents[1]), T.body_box(bout.ents[0])
    centre, other_centre = .5 * (tb[0] + tb[2]), .5 * (ob[0] + ob[2])
    assert abs(centre - m(36.4045)) < 1e-6 and abs(other_centre - m(36.9555)) < 1e-6
    assert abs(min(tb[2], ob[2]) - max(tb[0], ob[0]) - 3.042) < 1e-6
    seam = T.seam_geometry(bout.state(bout.sim()), bout.goal, 8)
    sign = 1 if mirror else -1                                        # the right one by its root: inner = its left
    assert seam.sign == sign and (centre - other_centre) * sign > 0   # the centres' order says the opposite
    assert abs(seam.bound - m(36.4045)) < 1e-6                        # inner of its root and its body centre
    bout.run(12)
    note = bout.notes('transfer_follow_seam')[0]
    assert note['inner'][:2] == [m(36.86), sign]
    out = [r for r in note['outer_rejected'] if r['direction'] == -sign]
    assert out and all((r['contact_x'] - r['bound']) * sign < 0 and abs(r['bound'] - m(36.4045)) < 1e-6 for r in out)
    assert note['strike'] is None or (note['strike']['contact_x'] - note['strike']['inner_bound']) * sign >= 0
    assert bout.notes('b2_recovery') and len(bout.n._failure_exposures) == 1


def test_seam_side_unknown_when_the_roots_coincide_turns_every_row_down(monkeypatch):
    # roots 0.005 u apart (within ROOT_ORDER_EPS_U): which one is on the left is unknown. No aim, no seam strike row: she is
    # over the target right of both roots (a guessed order would have let a row strike here); the original approach stays
    bout = Bout(monkeypatch, bounced=(8, 36.86, -1), other=(7, 36.865, 1), hero=(37.5, 9.25, -7.0), link='air',
                tail_done=True)
    bout.ents[1]['fsms'][0]['t'] = 0.
    fit_pose(bout.ents[1])
    seam = T.seam_geometry(bout.state(bout.sim()), bout.goal, 8)
    assert seam.sign == 0 and seam.aim is None and seam.bound is None
    log = bout.run(12)
    notes = bout.notes('transfer_follow_seam')
    assert notes[0]['inner'] == [36.86, 0, None] and notes[0]['outer_rejected']
    assert all(r['bound'] is None for e in notes for r in e['outer_rejected'] or ())
    assert all(e['strike'] is None for e in notes)
    sent = [r for r in log if r['offer'] is not None]
    assert sent and all(r['offer'].draft.run.link == 'air' and not r['mask'] & B['A'] for r in sent)


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
    # L2 switched to the other one after the bounce and the two stand apart (seq 265: a gap wider than CLOSE_PAIR_GAP_U):
    # the existing transfer to it
    bout = Bout(monkeypatch, other=(7, 20., 1))
    assert T.two_gap(bout.state(bout.sim()), 8).width > T.CLOSE_PAIR_GAP_U
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


def test_cross_target_after_a_bounce_in_a_close_pair_reads_the_middle(monkeypatch):
    # seq 265 (the 0ed5c779 4156 window replayed: after the chain's own model bounce at 4184 L2 switched to the other one,
    # the two 4.11 u apart, and the old scope sent it to the distant cross continuation): a close pair with a standable
    # gap; a fresh Run for the cross target reads the middle first
    bout = Bout(monkeypatch)
    bout.goal = TransferGoal(7, 8, BOUNCE_F, bout.goal.cast_ta, 'BOUNCE', bout.goal.responsibility)
    bout.n._transfer_goal = bout.goal
    bout.n.runner.run = None                                   # the Run starts on this tick (its close flag read now)
    bout.prefs = GoalPrefs(mode='RUSH', stance_x=31., weights={}, target=7)
    s = bout.state(bout.sim())
    gap = T.two_gap(s, 8)
    assert T.standable(gap, tuple(s['hero']['box'])) and gap.width <= T.CLOSE_PAIR_GAP_U
    assert T.bounce_close(s, bout.goal, s['hero'])
    offer = bout.tick()
    assert bout.notes('transfer_follow_decision') and offer is not None and offer.draft.run.link == 'middle'
    assert offer.draft.run.v['follow_close'] and offer.draft.run.v['iid'] == 7


def test_distant_pair_keeps_the_old_follow_up(monkeypatch):
    # a gap wider than CLOSE_PAIR_GAP_U (the other one at 20.0): not the person's close pair. The middle blocked, no seam
    # strike on an inner side; the legal ordinary landing as before seq 265
    bout = Bout(monkeypatch, other=(7, 20., 1), danger=[(22.3, 3.0, 35.5, 5.2)])
    s = bout.state(bout.sim())
    assert T.two_gap(s, 8).width > T.CLOSE_PAIR_GAP_U and T.seam_geometry(s, bout.goal, 8) is None
    offer = bout.tick()
    gone = bout.notes('transfer_follow_seam_unavailable')
    assert bout.notes('transfer_follow_middle_blocked') and gone and gone[0]['reason'].startswith('not a close pair')
    assert offer is not None and offer.draft.run.link == 'land' and offer.mask & LR == B['R']
    assert offer.draft.run.v['seam_inner'] is None


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
