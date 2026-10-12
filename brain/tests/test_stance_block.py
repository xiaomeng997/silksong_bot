"""stance_block: the frames a hit on the Reed would be a tink (task 1v1 T2)."""
import math
from types import SimpleNamespace

import numpy as np

from ssbot.combat import stance_block as sb


def _tr(state, t_entry, pos=(30.0, 7.0), last=None, tk=sb.REED):
    return SimpleNamespace(tk=tk, dead=False, state=state, t_entry=t_entry, pos=pos, iid=1,
                           last_entry=last or {}, table=None, cur=None)


def _fc(T, hero=(31.0, 5.0)):
    ws = SimpleNamespace(hero=SimpleNamespace(pos=SimpleNamespace(v=hero)))
    return SimpleNamespace(t=T, _ws=ws)


def test_defend_blocks_until_its_end():
    t = 10.0 + np.arange(0, 80) / 60.0
    b = sb.blocked(_fc(10.0), _tr("Defend", 9.5), t)
    end = 9.5 + sb.DEF_S + sb.SLACK_S
    assert b[t <= end].all() and not b[t > end].any()


def test_defend_start_blocks_after_its_shortest_dwell():
    t = 10.0 + np.arange(0, 10) / 60.0
    b = sb.blocked(_fc(10.0), _tr("Defend Start", 10.0), t)
    assert not b[0] and b[-1]


def test_alert_may_defend_until_seen_in_range_without_defending():
    tr = _tr("Alert", 9.9)
    fc = _fc(10.0)
    fc.trackers = {1: tr}
    t = 10.0 + np.arange(0, 10) / 60.0
    for k in range(sb.ALERT_SEEN_N):
        fc.t = 10.0 + k / 60.0
        assert sb.blocked(fc, tr, t)[5:].all()      # Will Defend unknown yet
        sb.observe(fc, fc.t, fc._ws)
        sb.observe(fc, fc.t, fc._ws)                # idempotent per frame
    assert sb.blocked(fc, tr, t) is None            # in range that long, no Defend Start: Will Defend 0
    tr.t_entry = 11.0                               # a new Alert: unknown again
    assert sb.blocked(fc, tr, t)[5:].all()


def test_alert_out_of_range_stays_possible():
    tr = _tr("Alert", 9.0)
    fc = _fc(10.0, hero=(45.0, 5.0))
    fc.trackers = {1: tr}
    for k in range(5):
        fc.t = 10.0 + k / 60.0
        sb.observe(fc, fc.t, fc._ws)
        assert sb.blocked(fc, tr, np.array([fc.t + 0.2]))[0]


def test_just_did_defend_and_other_types():
    t = np.array([10.2])
    tr = _tr("Alert", 9.9, last={"Defend Start": 8.0, "Stab Antic": 5.0})
    assert sb.blocked(_fc(10.0), tr, t) is None
    tr = _tr("Alert", 9.9, last={"Defend Start": 5.0, "Stab Antic": 8.0})
    assert sb.blocked(_fc(10.0), tr, t)[0]
    assert sb.blocked(_fc(10.0), _tr("Defend", 9.9, tk="Song Administrator"), t) is None
    assert math.isclose(sb.DEFEND_R, 7.6495)
