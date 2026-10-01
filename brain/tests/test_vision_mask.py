"""The vision mask (ssbot.vision.mask): the marker's cell per client height (oracle/src/Export/MarkerCode.cs
DefaultCell), the marker's rect in every corner, the mask as one normalized rect (the same share of the image at
every supported size, holding the marker plus the decoder's search there), and apply() filling exactly that rect in
place."""
from fractions import Fraction

import numpy as np

from ssbot.vision import mask as vmask

# Supported client sizes: the training windows (1280x720), the final run's capture and the human sessions' video
# (1920x1080), and other common ones, 16:9 and 16:10 and wider.
SIXTEEN_NINE = ((1280, 720), (1920, 1080), (2560, 1440), (3840, 2160))
OTHERS = ((1366, 768), (1600, 900), (1536, 864), (1280, 800), (1440, 900), (1680, 1050), (1920, 1200), (2560, 1600),
          (3440, 1440))


def test_cell_sizes():
    assert [vmask.cell_px(h) for h in (360, 720, 768, 900, 1080, 1200, 1440, 2160)] == [3, 3, 3, 3, 4, 4, 5, 8]


def test_marker_rects():
    assert vmask.CORNER == "tr"
    # The marker: 14 x 4 cells, `cell` px in from both edges (the same table as oracle/tests/MarkerCheck).
    assert vmask.marker_rect(1280, 720) == (1235, 3, 1277, 15)
    assert vmask.marker_rect(1920, 1080, "bl") == (4, 1060, 60, 1076)
    assert vmask.marker_rect(1280, 720, "tl", 12) == (12, 12, 180, 60)


def _share(w: int, h: int, corner: str = vmask.CORNER) -> tuple[Fraction, ...]:
    x0, y0, x1, y1 = vmask.mask_rect(w, h, corner)
    return Fraction(x0, w), Fraction(y0, h), Fraction(x1, w), Fraction(y1, h)


def test_the_mask_is_the_same_share_of_the_image_at_every_supported_size():
    """One normalized rect: exactly the same share at every 16:9 multiple of 640x360 (training 1280x720, final run
    and human sessions 1920x1080), within a pixel of it elsewhere."""
    assert vmask.mask_rect(1280, 720) == (1228, 0, 1280, 22)
    assert vmask.mask_rect(1920, 1080) == (1842, 0, 1920, 33)
    assert vmask.mask_rect(2560, 1440) == (2456, 0, 2560, 44) and vmask.mask_rect(3840, 2160) == (3684, 0, 3840, 66)
    assert vmask.mask_rect(1366, 768) == (1310, 0, 1366, 24)
    for corner in vmask.CORNERS:
        shares = {_share(w, h, corner) for w, h in SIXTEEN_NINE}
        assert len(shares) == 1, (corner, shares)
    assert _share(1920, 1080) == (1 - vmask.SHARE_W, 0, 1, vmask.SHARE_H)
    assert _share(1920, 1080, "bl") == (0, 1 - vmask.SHARE_H, vmask.SHARE_W, 1)
    for w, h in SIXTEEN_NINE + OTHERS:
        assert vmask.supported(w, h)
        mw, mh = vmask.mask_size(w, h)
        assert w * vmask.SHARE_W <= mw < w * vmask.SHARE_W + 1 and h * vmask.SHARE_H <= mh < h * vmask.SHARE_H + 1
    # 0.12 % of the image.
    assert 52 * 22 / (1280 * 720) == 78 * 33 / (1920 * 1080) < 0.00125


def test_the_mask_holds_the_marker_and_the_decoder_search_at_every_supported_size():
    for w, h in SIXTEEN_NINE + OTHERS:
        s = vmask.SEARCH_PX
        for corner in vmask.CORNERS:
            x0, y0, x1, y1 = vmask.mask_rect(w, h, corner)
            m0, n0, m1, n1 = vmask.marker_rect(w, h, corner)
            assert x0 <= m0 - s and m1 + s <= x1 and y0 <= n0 - s and n1 + s <= y1, (w, h, corner)
            # out to the corner's two edges
            assert (x0 == 0) == (corner[1] == "l") and (x1 == w) == (corner[1] == "r")
            assert (y0 == 0) == (corner[0] == "t") and (y1 == h) == (corner[0] == "b")
    # The binding size is 720p: 4 px to spare beyond the search on both inner sides.
    assert vmask.mask_rect(1280, 720)[0] == vmask.marker_rect(1280, 720)[0] - vmask.SEARCH_PX - 4
    assert vmask.mask_rect(1280, 720)[3] == vmask.marker_rect(1280, 720)[3] + vmask.SEARCH_PX + 4


def test_a_marker_scaled_between_supported_sizes_stays_inside_the_mask():
    """A 720p render shown in a 1080p (or 1440p) client, or a 1080p render in a 1440p one: the scaled marker (plus a
    pixel of blur) still lies inside that client's mask."""
    for (rw, rh), (cw, ch) in (((1280, 720), (1920, 1080)), ((1280, 720), (2560, 1440)), ((1920, 1080), (2560, 1440)),
                               ((1920, 1080), (3840, 2160)), ((1280, 720), (3840, 2160))):
        s = cw / rw
        m0, n0, m1, n1 = vmask.marker_rect(rw, rh)
        x0, y0, x1, y1 = vmask.mask_rect(cw, ch)
        assert x0 <= m0 * s - 1 and m1 * s + 1 <= x1 and y0 <= n0 * s - 1 and n1 * s + 1 <= y1, ((rw, rh), (cw, ch))


def test_below_the_supported_sizes_the_mask_grows_to_the_marker():
    """640x360 (synthetic test clients) and a 5:4 client: the marker plus 2 cells, out to the edges."""
    assert not vmask.supported(640, 360) and not vmask.supported(1280, 1024)
    assert vmask.mask_rect(640, 360) == (640 - 17 * 3, 0, 640, 7 * 3)
    assert vmask.mask_rect(1280, 1024) == (1280 - 17 * 4, 0, 1280, 32)    # 4 px cells: 68 px wide
    assert vmask.mask_rect(400, 225, "bl") == (0, 225 - 21, 51, 225)
    assert vmask.mask_rect(40, 10) == (0, 0, 40, 10)                    # clipped on a tiny image


def test_apply_fills_exactly_the_rect_in_place():
    rng = np.random.default_rng(0)
    img = rng.integers(1, 256, (720, 1280, 4), dtype=np.uint8)
    keep = img.copy()
    assert vmask.apply(img) is img
    x0, y0, x1, y1 = vmask.mask_rect(1280, 720)
    assert (img[y0:y1, x0:x1] == vmask.FILL).all()               # every channel
    outside = np.ones((720, 1280), bool)
    outside[y0:y1, x0:x1] = False
    assert np.array_equal(img[outside], keep[outside])
    gray = rng.integers(1, 256, (1080, 1920), dtype=np.uint8)
    vmask.apply(gray)
    assert (gray == 0).sum() == 78 * 33


def test_sizes_where_only_the_marker_floor_fits_are_unsupported():
    mask = vmask
    # 16:10 in some height bands needs the marker plus MARGIN_CELLS cells, not the normalized share.
    for w, h in ((1152, 720), (1600, 1000), (1512, 945)):
        assert not mask.supported(w, h)
    for w, h in ((1280, 720), (1920, 1080), (2560, 1440), (3840, 2160), (1366, 768), (1920, 1200)):
        assert mask.supported(w, h)
