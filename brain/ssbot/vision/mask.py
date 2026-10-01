"""The vision mask: the first preprocessing step of every image a vision model sees, in training and in the final run
(DESIGN §3.1.4 C4, §3.2.1).

Training captures carry the oracle's frame marker (oracle/src/Export/FrameMarker.cs, decoded by ssbot.record.marker);
the final, vanilla run never does. So that training pixels equal final-run pixels, every client image, marked or not,
has mask_rect() filled with FILL before anything else happens to it (resize, crops, color conversion, augmentation):
the marker's pixels never reach a model, and the masked corner looks the same in training and in the final run. Apply
it to the whole client area at capture resolution, as WGC delivers it, never to a resized image: only before the
resize does a rect in client px hide the same content at every model input size (a downscaled masked image mixes the
fill into the pixels along the rect's edges, the same way with and without the marker; a rect masked after the resize
would leave the marker's blur outside it).

Geometry (client px, origin top-left, x1 / y1 exclusive), the same as oracle/src/Export/MarkerCode.cs Place and
DefaultCell:
    marker  GRID_W x GRID_H = 14 x 4 cells of `cell` px (2 x 12 code cells and a one-cell black border), `cell` px
            in from both edges of the corner
    cell    cell_px(client height) = max(3, round(height / 270)): 3 px at 720p and 768p, 4 at 1080p, 5 at 1440p,
            8 at 2160p
    mask    the marker plus MARGIN_CELLS cells on its two inner sides, out to the corner's two edges: 17 x 7 cells,
            51 x 21 px at 720p, 68 x 28 at 1080p (0.12 % / 0.09 % of the image)

The cell size. The video recorder decodes the marker from the full-resolution capture (ssbot.record.video), which WGC
copies pixel for pixel from the window's client area (the game renders at its window size, and the capture side is
DPI-aware), and FrameMarker draws it with point filtering at integer client px: every cell is a square of one value.
3 px is the smallest cell with a centre pixel that has a whole pixel of its own cell on each side, so a client crop
up to 1 px off still reads every cell at the expected place, and the decoder's search covers +-3 px
(ssbot.record.marker.FullResDecoder); a 2 px cell has no centre, and 1 px off mixes every cell with its neighbour.
Growing with the height keeps the marker the same share of the image (a cell ~ 1/270 of the height), so the masked
corner is the same share of every model input. If something scales the image after all (a render resolution other
than the window's, DPI virtualization), the marker is no longer where the decoder and the mask expect it: the decode
fails and the capture falls back to its timestamp label, flagged; a marker is never read as another frame (CRC, sync
and clarity checks). The margin (2 cells, at least the decoder's search) keeps every marker the decoder can find
inside the mask.

The corner (CORNER, top right), from the HUD layout (a person's 405 s session of 2026-09-30 sampled every 15 s,
gameplay, menus and dialogue; the M1 probes' recordings): top left holds the HUD (bind orb, silk spool, masks; tools
and the currency counters below them) and, in menus, Modlist's version text; bottom left the boss and NPC name titles
(e.g. "Moss Mother"); bottom right the game version at the title screen and, as in Hollow Knight, the save icon;
dialogue boxes, area titles and prompts sit at the top centre or the centre. Top right showed only the room, mostly
the vignette's dark edge. Full-screen panes (inventory, map) lose a 0.1 % corner. The one thing seen there was an
external overlay (the NVIDIA recording notification, before the game started), which no run may show anyway.
"""
import numpy as np

CORNERS = ("tl", "tr", "bl", "br")
CORNER = "tr"
GRID_W, GRID_H = 14, 4   # marker cells, border included (MarkerCode.GridW / GridH)
MARGIN_CELLS = 2
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


def mask_rect(width: int, height: int, corner: str = CORNER, cell: int | None = None) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the mask: the marker plus MARGIN_CELLS cells on its two inner sides, out to the corner's
    edges, clipped to the image."""
    c = cell or cell_px(height)
    x0, y0, x1, y1 = marker_rect(width, height, corner, c)
    m = MARGIN_CELLS * c
    x0, x1 = (0, x1 + m) if corner[1] == "l" else (x0 - m, width)
    y0, y1 = (0, y1 + m) if corner[0] == "t" else (y0 - m, height)
    return max(0, x0), max(0, y0), min(width, x1), min(height, y1)


def apply(img: np.ndarray, fill: int = FILL) -> np.ndarray:
    """Fill the mask of a full-resolution client image, (h, w) or (h, w, channels), in place (every channel);
    returns it."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = mask_rect(w, h)
    img[y0:y1, x0:x1] = fill
    return img
