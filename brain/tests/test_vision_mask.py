"""The vision mask (ssbot.vision.mask): the marker's cell per client height (oracle/src/Export/MarkerCode.cs
DefaultCell), the marker's and the mask's rects in every corner, and apply() filling exactly that rect in place."""
import numpy as np

from ssbot.vision import mask as vmask


def test_cell_sizes():
    assert [vmask.cell_px(h) for h in (360, 720, 768, 900, 1080, 1200, 1440, 2160)] == [3, 3, 3, 3, 4, 4, 5, 8]


def test_marker_and_mask_rects():
    assert vmask.CORNER == "tr"
    # The marker: 14 x 4 cells, `cell` px in from both edges (the same table as oracle/tests/MarkerCheck).
    assert vmask.marker_rect(1280, 720) == (1235, 3, 1277, 15)
    assert vmask.marker_rect(1920, 1080, "bl") == (4, 1060, 60, 1076)
    assert vmask.marker_rect(1280, 720, "tl", 12) == (12, 12, 180, 60)
    # The mask: the marker plus 2 cells on its inner sides, out to the corner's edges: 17 x 7 cells.
    assert vmask.mask_rect(1280, 720) == (1229, 0, 1280, 21)
    assert vmask.mask_rect(1920, 1080) == (1852, 0, 1920, 28)
    assert vmask.mask_rect(1920, 1080, "bl") == (0, 1052, 68, 1080)
    assert vmask.mask_rect(1920, 1080, "br", 18) == (1920 - 17 * 18, 1080 - 7 * 18, 1920, 1080)
    for w, h in ((1280, 720), (1920, 1080), (1366, 768), (2560, 1440), (3840, 2160), (640, 360)):
        c = vmask.cell_px(h)
        for corner in vmask.CORNERS:
            x0, y0, x1, y1 = vmask.mask_rect(w, h, corner)
            m0, n0, m1, n1 = vmask.marker_rect(w, h, corner)
            assert (x1 - x0, y1 - y0) == (17 * c, 7 * c) and (m1 - m0, n1 - n0) == (14 * c, 4 * c)
            margin = vmask.MARGIN_CELLS * c
            # margin on the inner sides; on the edge sides the mask reaches the edge (the marker is `c` px in)
            assert x0 <= max(0, m0 - margin) and min(w, m1 + margin) <= x1
            assert y0 <= max(0, n0 - margin) and min(h, n1 + margin) <= y1
            assert (x0 == 0) == (corner[1] == "l") and (x1 == w) == (corner[1] == "r")
            assert (y0 == 0) == (corner[0] == "t") and (y1 == h) == (corner[0] == "b")
    # A small share of the image: 0.12 % at 720p, 0.09 % at 1080p; clipped on a tiny image.
    assert 51 * 21 / (1280 * 720) < 0.0012 and 68 * 28 / (1920 * 1080) < 0.001
    assert vmask.mask_rect(40, 10) == (0, 0, 40, 10)


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
    assert (gray == 0).sum() == 68 * 28
