"""The range overlay's all-look-aheads and swept modes (the person 2026-10-10: "can 0 / 6 / 12 / 18 / 36 be shown at
the same time?", the Tinies' dash shows only its stop point): RangeTracker.ladder, same_mask, ZoneEngine.range_layer,
draw_range, the View switches and the live commands."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from ssbot.combat.attack_range import Estimate, Mask, RangeTracker, poly_mask, same_mask
from ssbot.tools import zone_overlay as zo

CAM = {"V": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1, 0, -31.94, -9.6, -38.1, 1],         # test_zone_overlay's camera
       "P": [2.6463542, 0, 0, 0, 0, 4.7046299, 0, 0, 0, 0, -1.4149377, -1, 0, 0, -24.1493798, 0],
       "rect": [0, 0, 1, 1], "screen": [1920, 1080]}


def box(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64)


class Lunge(RangeTracker):
    """A tracker whose estimates are synthetic: enemy 1 lunges +0.5 u per frame to frame 24, then comes back at
    0.4 u per frame (a dive, out and back: at +36 it is at 27.2 u), enemy 2 idles (the same box every k). Counts the
    estimate calls."""

    def __init__(self):
        super().__init__(tables={})
        self.now = {1: ("t", {}, None), 2: ("t", {}, None)}
        self.calls: list = []

    def estimate(self, iid, k):
        self.calls.append((iid, k))
        if iid == 2:
            return Estimate(iid, k, poly_mask([box(40.0, 4.0, 41.0, 6.0)]), None, None, None, (40.5, 5.0))
        d = 0.5 * min(k, 24) - 0.4 * max(k - 24, 0)
        return Estimate(iid, k, poly_mask([box(20.0 + d, 4.0, 21.0 + d, 6.0)]), "dash", None, 0, (20.5, 5.0))


def test_same_mask_ignores_padding():
    a = poly_mask([box(1.0, 1.0, 2.0, 2.0)], pad=1)
    b = poly_mask([box(1.0, 1.0, 2.0, 2.0)], pad=4)
    c = poly_mask([box(1.0, 1.0, 2.05, 2.0)], pad=1)
    e = Mask(np.zeros((0, 0), bool), 0, 0)
    assert same_mask(a, b) and not same_mask(a, c)
    assert same_mask(e, Mask(np.zeros((3, 3), bool), 5, 5)) and not same_mask(a, e)


def test_ladder_estimates_each_lookahead_once_and_sweeps_out_and_back():
    trk = Lunge()
    per, swept = trk.ladder((0, 6, 12, 18, 36), sweep=36)
    assert sorted(per) == [0, 6, 12, 18, 36] and [e.iid for e in per[12]] == [1, 2]
    assert len(trk.calls) == len(set(trk.calls)) == 2 * 37            # 0..36 once each, the ks among them
    for k in (0, 6, 12, 18, 36):
        assert same_mask(per[k][0].raw, trk.estimate(1, k).raw)
    bb = swept[1].bbox()
    assert abs(bb[0] - 20.0) < 0.11 and abs(bb[2] - 33.0) < 0.11      # out to +12 u at frame 24 (and back)
    assert same_mask(swept[2], per[0][1].raw)                         # idle: the box itself
    assert same_mask(swept[1], trk.swept(1, 36))
    trk.calls.clear()
    per, swept = trk.ladder((12,))
    assert swept == {} and trk.calls == [(1, 12), (2, 12)]


def _fake_engine(trk):
    return SimpleNamespace(rng=trk, name=lambda i: f"E{i}", color=lambda i: zo.ENEMY_COLORS[i])


def test_range_layer_marks_repeated_lookaheads_and_the_swept_path():
    res = zo.ZoneEngine.range_layer(_fake_engine(Lunge()), zo.KS, sweep=36, hero=False)
    assert set(res["range"]) == set(zo.KS) and res["range_sweep"] == 36
    # the idle enemy: every k is the k0 region; the lunge: every k is new
    assert all(res["range_same"][k].get(2) == 0 for k in zo.KS[1:]) and not res["range_same"][0]
    assert all(1 not in res["range_same"][k] for k in zo.KS)
    assert all(e[4] == [] for k in zo.KS for e in res["range"][k])     # no hero-centre outlines
    sw = {iid: (polys, lab) for iid, _n, _c, polys, lab in res["range_swept"]}
    assert sw[1][1] == "path 0-36" and len(sw[1][0]) == 1
    none = zo.ZoneEngine.range_layer(SimpleNamespace(rng=None), (0, 12))
    assert none["range"] == {0: [], 12: []} and none["range_swept"] == []


def _px(Hw, xy):
    return tuple(np.round(zo._to_px(Hw, np.array([xy]))[0]).astype(int))


def test_draw_range_all_lookaheads_and_swept():
    g = zo.Grid()
    fr = {"ks": (0,), "support": {}, "cols": [], "hero": None, "cam": CAM,
          **zo.ZoneEngine.range_layer(_fake_engine(Lunge()), zo.KS, sweep=36, hero=False)}
    size = (1920, 1080)
    Hw, _ = zo.homography(g, CAM, size)
    one = zo.render(fr, g, size, zo.View(mode="range", k=0))
    allk = zo.render(fr, g, size, zo.View(mode="range", k=0, all_k=True))
    # +36: the lunge is back at 27.2..28.2 u (out to 32..33 at +24): its outline is drawn only with all k
    x, y = _px(Hw, (27.2, 5.0))
    assert allk[y - 3:y + 4, x - 3:x + 4, 3].max() > 0 and one[y - 3:y + 4, x - 3:x + 4, 3].max() == 0
    # +0 is filled in both
    x0, y0 = _px(Hw, (20.5, 5.0))
    assert one[y0, x0, 3] > 0 and allk[y0, x0, 3] > 0
    # the swept path covers 31.5 u (beyond +18's 29..30, reached around +21 / +28): only with swept
    xs, ys = _px(Hw, (31.5, 5.0))
    assert allk[ys, xs, 3] == 0
    sw = zo.render(fr, g, size, zo.View(mode="range", k=0, all_k=True, swept=True))
    assert sw[ys, xs, 3] > 0
    # the real colliders stay drawn in the range modes
    fr2 = dict(fr, cols=[(box(36.0, 8.0, 37.0, 9.0), False, "x", (0.0, 0.0))])
    xr, yr = _px(Hw, (36.5, 8.5))
    assert zo.render(fr2, g, size, zo.View(mode="range", all_k=True))[yr, xr, 3] > 0


def test_dashed_outline_has_gaps():
    img = np.zeros((100, 300, 4), np.uint8)
    zo._dashed(img, np.array([[10.0, 50.0], [290.0, 50.0], [290.0, 51.0], [10.0, 51.0]]), (255, 255, 255, 255),
               1, 12.0, 7.0)
    row = img[50, 10:290, 3] > 0
    assert row.any() and not row.all()


def test_view_range_lookaheads_and_sweep():
    v = zo.View(mode="range+red", k=12)
    assert v.range_ks() == (12,) and v.range_sweep() is None
    v.swept = True
    assert v.range_sweep() == 12
    v.all_k = True
    assert v.range_ks() == zo.KS and v.range_sweep() == 36
    v.mode = "yellow+red"                       # no range shown: nothing extra computed
    assert v.range_ks() == (12,) and v.range_sweep() is None
    lines = [t for t, _ in zo.legend_lines(None, zo.View(mode="range", all_k=True, swept=True), "cfg")]
    assert any("at once" in t for t in lines) and any(t.startswith("SWEPT path 0-36") for t in lines)


def test_live_commands_toggle_all_k_and_swept():
    me = SimpleNamespace(view=zo.View(mode="range+red"), dirty=False)
    zo.LiveOverlay._apply(me, "all")
    assert me.view.all_k and me.dirty
    zo.LiveOverlay._apply(me, "all off")
    zo.LiveOverlay._apply(me, "swept on")
    assert not me.view.all_k and me.view.swept
