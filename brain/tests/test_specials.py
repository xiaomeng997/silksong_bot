"""The special-move table (ssbot.combat.specials; task 1v1 T3, forum.md 48)."""
import numpy as np
import pytest

from ssbot.combat import specials as sp
from ssbot.combat.pogo_slam import FLOOR_Y, HERO_STAND_DY, SlamTimeline
from ssbot.knowledge import kinematics as kin

TAB = sp.SpecialTable.load()
pytestmark = pytest.mark.skipif(not TAB.entries, reason="no specials_CL_SLAM.json")


def _params():
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    return kin.HeroParams.load(CREST_PARAMS["Wanderer"])


def test_move_frame_and_lut():
    assert sp.move_frame("Song Heavy Sentry", "Slam Antic", 0.5) == ("CL_SLAM", 30)
    assert sp.move_frame("Song Heavy Sentry", "Slam 2", 0.0) == ("CL_SLAM", 57)
    assert sp.move_frame("Song Heavy Sentry", "Walk", 0.0) is None
    assert sp.move_frame("Song Reed", "Slam Antic", 0.0) is None
    lut = TAB.lut("CL_SLAM", certs=("both", "bounce"))
    for e in TAB.entries[::397]:
        i = lut.find(np.array([e.k0]), np.array([0.5 * (e.dx0 + e.dx1)]), np.array([0.5 * (e.dy0 + e.dy1)]),
                     np.array([e.vy]))[0]
        f = lut.entries[i]
        assert i >= 0 and f.has(e.k0, 0.5 * (e.dx0 + e.dx1), 0.5 * (e.dy0 + e.dy1))
        assert f.cert == "both" or e.cert == "bounce"      # the best key in the cell: never a worse cert
    assert all(e.k1 <= 77 for e in TAB.entries)


@pytest.mark.parametrize("P", [0, 2])
def test_strike_rows_land_in_their_entry(P):
    params = _params()
    tl = SlamTimeline.load()
    lut = TAB.lut("CL_SLAM", certs=("both", "bounce"))
    cx, cy, face = 31.0, 7.449, 1
    S = kin.initial_state(params, cx + 5.0, FLOOR_Y + HERO_STAND_DY, facing=-1, ground=True)
    prefix = np.zeros(P, np.int64)
    r = sp.strike_rows(params, None, S, lut, 6, cx, cy, face, tl.disp, 36, prefix=prefix if P else None)
    assert len(r.cmd) > 0 and r.tried > 0
    full = np.concatenate([np.zeros((len(r.cmd), P), np.int64), r.cmd], axis=1)
    ro = kin.rollout(S, full, params, None)
    for n, (e, j) in enumerate(zip(r.entry, r.j_press)):
        assert (r.cmd[n, j] & kin.B_ATTACK) and (r.cmd[n, j] & kin.B_DOWN)
        k = 6 + P + j + 1
        x, y = ro.pos[n, P + j + 1]
        dx = (x - (cx + face * tl.disp[k])) * face
        assert e.has(k, dx, y - cy, ro.vel[n, P + j + 1, 1])


def test_overlay_cells():
    from types import SimpleNamespace

    from ssbot.tools.zone_overlay import specials_cells
    tl = SlamTimeline.load()
    cells = specials_cells(SimpleNamespace(), tl, 10, 31.0, 7.449, 1)
    assert cells and {c[0] for c in cells} <= {"both", "bounce"}
    assert all(c[1] < c[2] and c[3] < c[4] for c in cells)
    assert specials_cells(SimpleNamespace(), tl, 200, 31.0, 7.449, 1) == []
