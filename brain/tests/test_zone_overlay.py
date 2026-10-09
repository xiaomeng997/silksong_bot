import numpy as np
import pytest

from ssbot.tools import zone_overlay as zo


def test_merge_states_matches_forum_human_score_pairs():
    from ssbot.tools.forum_human_score import _merge_pair
    a = {"f": 10, "dt": 1 / 120, "udt": 1 / 60, "ts": 0.5, "fs": 1, "ev": [{"k": "x", "f": 10}],
         "input": {"mask": 1}, "hero": {"pos": [1, 2]}}
    b = {"f": 11, "dt": 1 / 120, "udt": 1 / 60, "ts": 0.5, "fs": 0, "ev": [{"k": "y"}], "input": {"mask": 4},
         "hero": {"pos": [3, 4]}}
    m = zo.merge_states([dict(a), dict(b)], 5, 0.5)
    r = _merge_pair(dict(a), dict(b), 5, 0.5)
    for k in ("f", "_f_raw", "dt", "udt", "ts", "fs", "ev", "input", "hero"):
        assert m[k] == r[k], k
    one = zo.merge_states([dict(b)], 7, 1.0)
    assert one["f"] == 7 and one["_f_raw"] == 11 and one["dt"] == b["dt"]


def _block(K, ny, nx, k, r0, r1, c0, c1):
    D = np.zeros((K + 1, ny, nx), bool)
    D[k, r0:r1, c0:c1] = True
    return D


def test_erode_back_shrinks_by_the_reach_per_frame():
    K, ny, nx = 4, 12, 60
    D = _block(K, ny, nx, K, 0, 6, 20, 40)          # 20 cells wide at the last frame, standing rows up
    Z = zo.erode_back(D, ax=2, up=1, dn=1, lat=1)
    widths = [int(Z[k, 0].sum()) for k in range(K + 1)]
    assert widths[K] == 20
    assert widths[K - 1] == 16 and widths[K - 2] == 12 and widths[1] == 8
    assert widths[0] == widths[1]                     # the first frame: not reacted yet
    assert not Z[0, 0, :22].any() and not Z[0, 0, 38:].any()


def test_erode_back_frame_boxes_and_walls():
    K, ny, nx = 3, 8, 30
    D = _block(K, ny, nx, 0, 0, 2, 10, 12)            # a box now only: always doomed now
    D |= _block(K, ny, nx, K, 0, 8, 0, 6)             # a block touching the left wall at the last frame
    Z = zo.erode_back(D, ax=1, up=1, dn=1, lat=1)
    assert Z[0, 0, 10:12].all()
    # the wall side does not erode: the block loses one column per frame on its open side only
    assert Z[K - 1, 0, :5].all() and not Z[K - 1, 0, 5]
    assert Z[1, 0, :4].all() and not Z[1, 0, 4]


def test_damage_colliders_clash_rules():
    box = [0, 0, 1, 0, 1, 1, 0, 1]

    def col(parry, dealt=1, enabled=True, name="c"):
        return {"name": name, "verts_world": box, "enabled": enabled,
                "damage": {"dealt": dealt, "parry": parry}}
    s = {"ents": [{"type_key": "Song Reed", "vel": [1.0, 0.0],
                   "cols": [col(4), col(5), col(4, dealt=0), col(4, enabled=False)]},
                  {"type_key": "Song Heavy Sentry", "cols": [col(5)]}]}
    out = zo.damage_colliders(s)
    assert [c[1] for c in out] == [False, True, False]
    assert out[0][3] == (1.0, 0.0)
    hull = zo.sweep_hull(out[0][0], (60.0, 0.0), frames=6)   # 6 u to the right in 6 frames
    assert hull[:, 0].max() == pytest.approx(7.0) and hull[:, 0].min() == pytest.approx(0.0)


CAM = {"V": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1, 0, -31.94, -9.6, -38.1, 1],
       "P": [2.6463542, 0, 0, 0, 0, 4.7046299, 0, 0, 0, 0, -1.4149377, -1, 0, 0, -24.1493798, 0],
       "rect": [0, 0, 1, 1], "screen": [1920, 1080]}


def test_homography_matches_the_projector():
    from ssbot.tools.projector import project_cam
    g = zo.Grid()
    Hw, Hg = zo.homography(g, CAM, (1920, 1080))
    w = np.array([[20.0, 5.0], [40.0, 12.0], [31.94, 9.6]])
    px, _ = project_cam(w, CAM)
    assert np.allclose(zo._to_px(Hw, w), px, atol=1e-3)
    # grid image pixel (column i, row r: row 0 = the highest hero centre) -> the cell centre's projection
    i, r = 7, 3
    cw = np.array([[g.xs[i], g.ys[g.ny - 1 - r]]])
    assert np.allclose(zo._to_px(Hg, np.array([[i, r]])), project_cam(cw, CAM)[0], atol=1e-3)
    assert np.allclose(px[2], [960, 540], atol=0.5)


def test_render_draws_yellow_red_and_hero():
    g = zo.Grid()
    y = np.zeros(g.shape, bool)
    y[0:4, 60:70] = True
    poly = np.array([[30.0, 4.0], [31.0, 4.0], [31.0, 6.0], [30.0, 6.0]])
    fr = {"ks": (0,), "support": {0: {}}, "ycom": {0: y}, "yns": {0: np.zeros(g.shape, bool)},
          "cols": [(poly, False, "x", (0.0, 0.0))], "hero": (25.0, 5.0), "cam": CAM}
    v = zo.View()
    img = zo.render(fr, g, (960, 540), v, legend=zo.legend_lines(None, v, "cfg"))
    assert img.shape == (540, 960, 4) and img[..., 3].max() == 255
    Hw, _ = zo.homography(g, CAM, (960, 540))
    rx, ry = np.round(zo._to_px(Hw, np.array([[30.5, 5.0]]))[0]).astype(int)
    assert img[ry, rx, 3] > 0 and img[ry, rx, 2] > img[ry, rx, 1]      # light red: more red than green
    yx, yy = np.round(zo._to_px(Hw, np.array([[g.xs[65], g.ys[1]]]))[0]).astype(int)
    assert img[yy, yx, 3] > 0 and img[yy, yx, 1] > img[yy, yx, 0]      # light yellow: green over blue
    v.on = False
    assert zo.render(fr, g, (960, 540), v)[..., 3].max() == 0


def test_view_modes():
    v = zo.View()
    assert v.show("yellow") and v.show("red") and not v.show("support")
    seen = []
    for _ in range(len(zo.View.MODES)):
        v.cycle()
        seen.append(v.mode)
    assert seen[-1] == "yellow+red" and "support" in seen and v.show("yellow")


def test_erode_back_open_walls_and_a_solid_ceiling():
    K, ny, nx = 3, 8, 30
    D = _block(K, ny, nx, K, 0, 8, 0, 6)              # the wall test's block, walls open: it erodes at the wall too
    walled = zo.erode_back(D, ax=1, up=1, dn=1, lat=1)
    open_ = zo.erode_back(D, ax=1, up=1, dn=1, lat=1, walls=False)
    assert walled[1, 0, 0] and not open_[1, 0, 0]
    # a ceiling (rows 4.. solid): a block over rows 0..3 at the last frame, no escape upward
    D2 = _block(K, ny, nx, K, 0, 4, 10, 20)
    sky = np.zeros((ny, nx), bool)
    sky[4:] = True
    free = zo.erode_back(D2, ax=1, up=1, dn=1, lat=1)
    capped = zo.erode_back(D2, ax=1, up=1, dn=1, lat=1, solid=sky)
    assert capped[1, 0].sum() >= free[1, 0].sum() and capped[1, 3].sum() > free[1, 3].sum()


def test_parked_entities_and_their_colliders():
    box = [0, 0, 1, 0, 1, 1, 0, 1]
    col = {"name": "c", "verts_world": box, "enabled": True, "damage": {"dealt": 1, "parry": 4}}
    parked = {"iid": 5, "type_key": "Song Reed", "fsms": [{"name": "Control", "state": "Fly In Ready"}],
              "render_aabb": None, "cols": [col]}
    shown = dict(parked, iid=6, render_aabb=[0, 0, 1, 1])
    assert zo.parked(parked) and not zo.parked(shown)
    out = zo.damage_colliders({"ents": [parked, shown]})
    assert len(out) == 1 and out[0][4] == 6


def test_screen_share_of_the_grid_and_the_dome():
    from ssbot.core.forum import dome_y
    from ssbot.tools.zone_share import screen_share
    g = zo.Grid()
    sh = screen_share({"all": np.ones(g.shape, bool), "none": np.zeros(g.shape, bool), "arena": g.inside}, g, CAM)
    assert sh["none"] == 0.0 and 0.3 < sh["all"] <= 1.0
    assert sh["arena"] < sh["all"]                    # the sky above the dome is not part of the arena
    j = int(np.argmin(np.abs(g.xs - 31.5)))           # under the dome's top the whole column is inside
    assert g.inside[:, j].all() and not g.inside[-1, 0]
    assert g.ys[g.inside[:, 0]].max() <= dome_y(float(g.xs[0])) - 1.0
