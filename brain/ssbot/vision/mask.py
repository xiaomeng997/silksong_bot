"""The vision mask: the first preprocessing step of every image a vision model sees, in training and in the final run
(DESIGN §3.1.4 C4, §3.2.1).

Training captures and a person's play sessions carry the oracle's frame marker (oracle/src/Export/FrameMarker.cs,
decoded by ssbot.record.marker); the final, vanilla run never does. So that training pixels equal final-run pixels, every
client image, marked or not, has mask_rect() filled with FILL before anything else happens to it (resize, crops,
color conversion, augmentation): the marker's pixels never reach a model, and the masked corner looks the same in
training and in the final run. Apply it to the whole client area at capture resolution, as WGC delivers it (or to
a human session's 1920x1080 video frame), never to a resized image: only before the resize does the rect hide the
same content at every model input size (a downscaled masked image mixes the fill into the pixels along the rect's
edges, the same way with and without the marker; a rect masked after the resize would leave the marker's blur
outside it).

The mask is ONE normalized rect, the same share of the image at every supported client size: SHARE_W = 26/640
(4.06 %) of the width and SHARE_H = 11/360 (3.06 %) of the height, from the corner CORNER (top right), rounded
outward to whole px. Those fractions are whole px at every multiple of 640x360, so the rect is exactly the same share
at the project's sizes: 52 x 22 px at 1280x720 (training windows), 78 x 33 at 1920x1080 (the final run's capture and
the human sessions' video), 104 x 44 at 2560x1440, 156 x 66 at 3840x2160; elsewhere it is within a pixel of that share
(1366x768: 56 x 24). It is 0.12 % of the image. Supported sizes: client height >= MIN_HEIGHT (720) and an aspect of
16:10 or wider; there the rect holds the marker plus the capture path's decoder search (SEARCH_PX on its inner sides)
with room to spare, tests/test_vision_mask.py checks both, and a model input of any size made from such an image
shows the same masked share. Below that height (only the synthetic test clients, e.g. 640x360) or on a narrower
aspect the marker's minimum cell would not fit the share, so the rect grows to the marker plus MARGIN_CELLS cells on
its inner sides; no model input is ever made at such a size.

Geometry (client px, origin top-left, x1 / y1 exclusive), the same as oracle/src/Export/MarkerCode.cs Place and
DefaultCell:
    marker  GRID_W x GRID_H = 14 x 4 cells of `cell` px (2 x 12 code cells and a one-cell black border), `cell` px
            in from both edges of the corner
    cell    cell_px(client height) = max(3, round(height / 270)): 3 px at 720p and 768p, 4 at 1080p, 5 at 1440p,
            8 at 2160p; the marker extends 15 x 5 cells from the corner (45 x 15 px at 720p, 60 x 20 at 1080p)
    mask    mask_rect(): the normalized rect above (the larger of it and the marker plus MARGIN_CELLS cells)

The binding size is 720p: the 3 px cell is 1/240 of the height there (1/270 at 1080p), so the marker plus the search
takes 48 x 18 px of the 52 x 22 px rect (4 px to spare on each inner side); at 1080p 63 x 23 of 78 x 33. Because the
share is the same everywhere, a marker drawn at any supported render size and scaled to another output size (a 720p
render in a 1080p window, DPI scaling) still lies inside that output's mask, though it no longer decodes.

The cell size. The video recorder decodes the marker from the full-resolution capture (ssbot.record.video), which WGC
copies pixel for pixel from the window's client area (the game renders at its window size, and the capture side is
DPI-aware), and FrameMarker draws it with point filtering at integer client px: every cell is a square of one value. A
3 px cell is the smallest with a centre pixel that has a whole pixel of its own cell on each side, so a client crop up
to 1 px off still reads every cell at the expected place, and the decoder's search covers +-SEARCH_PX
(ssbot.record.marker.FullResDecoder); a 2 px cell has no centre, and 1 px off mixes every cell with its neighbour. The
cell cannot be the same share at every size (it is whole px, at least 3); the mask is. If something scales the image
after all (a render resolution other than the window's, DPI virtualization), the marker is no longer where the decoder
expects it: the decode fails and the capture falls back to its timestamp label, flagged; a marker is never read as
another frame (CRC, sync and clarity checks, and a decode far from the capture's timestamp label is rejected:
marker.reject_implausible). Where the oracle reports the marker outside the mask (STATE "mk" rect, mapped into the
image), it is filled too and the image flagged mask_mismatch, not training data (the capture path's guard,
ssbot.record.video; a human session's video, ssbot.tools.human_video).

The corner (CORNER, top right), from the HUD layout (a person's 405 s session of 2026-09-30 sampled every 15 s,
gameplay, menus and dialogue; the M1 probes' recordings): top left holds the HUD (bind orb, silk spool, masks; tools
and the currency counters below them) and, in menus, Modlist's version text; bottom left the boss and NPC name titles
(e.g. "Moss Mother"); bottom right the game version at the title screen and, as in Hollow Knight, the save icon;
dialogue boxes, area titles and prompts sit at the top centre or the centre. Top right showed only the room, mostly
the vignette's dark edge. Full-screen panes (inventory, map) lose a 0.12 % corner. The one thing seen there was an
external overlay (the NVIDIA recording notification, before the game started), which no run may show anyway.
"""
from fractions import Fraction

import numpy as np

CORNERS = ("tl", "tr", "bl", "br")
CORNER = "tr"
GRID_W, GRID_H = 14, 4   # marker cells, border included (MarkerCode.GridW / GridH)
SHARE_W = Fraction(26, 640)   # the mask's width, as a share of the client's width
SHARE_H = Fraction(11, 360)   # its height, as a share of the client's height
MIN_HEIGHT = 720         # supported client sizes: at least this tall (and 16:10 or wider)
SEARCH_PX = 3            # the capture path's decoder searches this far around the marker (marker.FullResDecoder)
MARGIN_CELLS = 2         # below the supported sizes: the mask is at least the marker plus this many cells
FILL = 0


def cell_px(height: int) -> int:
    """The marker's cell for a client `height` px tall (MarkerCode.DefaultCell; round, like Math.Round, rounds half
    to even)."""
    return max(3, round(height / 270))


def marker_rect(width: int, height: int, corner: str = CORNER, cell: int | None = None) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the marker, border included, where FrameMarker draws it (MarkerCode.Place); `cell`
    defaults to cell_px(height)."""
    c = cell or cell_px(height)
    x0 = c if corner[1] == "l" else width - c - GRID_W * c
    y0 = c if corner[0] == "t" else height - c - GRID_H * c
    return x0, y0, x0 + GRID_W * c, y0 + GRID_H * c


def mask_size(width: int, height: int) -> tuple[int, int]:
    """(w, h) of the mask in a width x height client: SHARE_W x SHARE_H of it rounded up to whole px; at least the
    marker plus MARGIN_CELLS cells (which only matters below the supported sizes)."""
    c = cell_px(height)
    mw = max(-(-width * SHARE_W.numerator // SHARE_W.denominator), (GRID_W + 1 + MARGIN_CELLS) * c)
    mh = max(-(-height * SHARE_H.numerator // SHARE_H.denominator), (GRID_H + 1 + MARGIN_CELLS) * c)
    return min(width, mw), min(height, mh)


def mask_rect(width: int, height: int, corner: str = CORNER) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the mask in a width x height client: mask_size() px from the corner's two edges."""
    mw, mh = mask_size(width, height)
    x0, x1 = (0, mw) if corner[1] == "l" else (width - mw, width)
    y0, y1 = (0, mh) if corner[0] == "t" else (height - mh, height)
    return x0, y0, x1, y1


def supported(width: int, height: int) -> bool:
    """A client size at which the mask is the normalized rect (the same share as at every other supported size)."""
    return height >= MIN_HEIGHT and width * 10 >= height * 16


def apply(img: np.ndarray, fill: int = FILL) -> np.ndarray:
    """Fill the mask of a full-resolution client image, (h, w) or (h, w, channels), in place (every channel);
    returns it."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = mask_rect(w, h)
    img[y0:y1, x0:x1] = fill
    return img
