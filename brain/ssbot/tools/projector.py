"""World -> image projection with the oracle's camera export (DESIGN §3.1.3).

STATE "cam" (and "hud"["cam"]) carries V (worldToCameraMatrix) and P (projectionMatrix) as 16 floats in
COLUMN-MAJOR order, the normalized viewport rect [x, y, w, h] and, for "cam", the screen size [w, h]. When
"src" == 1 they are the matrices captured at Camera.onPreRender, i.e. with the camera shake that is removed again
before end-of-frame.

    clip  = P @ V @ [x, y, z, 1]
    ndc   = clip[:3] / clip[3]
    img_x = (rect.x + (ndc.x + 1) / 2 * rect.w) * screen.w
    img_y = screen.h - (rect.y + (ndc.y + 1) / 2 * rect.h) * screen.h      # top-left origin, like the capture

The normalized rect is used instead of pixelRect because the main camera may render into a scaled RenderTexture
(CameraRenderScaled) that is blitted over the whole screen.
"""
from collections.abc import Sequence

import numpy as np


def mat4(col_major16: Sequence[float]) -> np.ndarray:
    """16 column-major floats (m00, m10, m20, m30, m01, ...) -> 4x4 matrix."""
    a = np.asarray(col_major16, dtype=np.float64)
    if a.shape != (16,):
        raise ValueError(f"expected 16 floats, got shape {a.shape}")
    return a.reshape(4, 4).T


def project(points, V: np.ndarray, P: np.ndarray, rect: Sequence[float], screen: Sequence[float]
            ) -> tuple[np.ndarray, np.ndarray]:
    """points (N, 2|3) world -> (N, 2) image pixels (top-left origin) and a mask of points in front of the camera.

    2-D points get z = 0 (the gameplay plane of the hero and most colliders).
    """
    p = np.atleast_2d(np.asarray(points, dtype=np.float64))
    if p.shape[1] == 2:
        p = np.hstack([p, np.zeros((len(p), 1))])
    h = np.hstack([p, np.ones((len(p), 1))])
    clip = h @ (P @ V).T
    w = clip[:, 3]
    ok = w > 1e-6
    safe_w = np.where(ok, w, 1.0)
    ndc = clip[:, :2] / safe_w[:, None]
    rx, ry, rw, rh = rect
    sw, sh = screen
    x = (rx + (ndc[:, 0] + 1.0) * 0.5 * rw) * sw
    y = sh - (ry + (ndc[:, 1] + 1.0) * 0.5 * rh) * sh
    return np.stack([x, y], axis=1), ok


def project_cam(points, cam: dict, screen: Sequence[float] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """project() with a STATE camera dict ("cam", or "hud"["cam"] plus the screen size from "cam")."""
    return project(points, mat4(cam["V"]), mat4(cam["P"]), cam["rect"], screen if screen is not None else cam["screen"])


def viewport_px(cam: dict, screen: Sequence[float] | None = None) -> tuple[float, float, float, float]:
    """The camera's viewport in image pixels [x0, y0, x1, y1] (letterboxing excluded)."""
    rx, ry, rw, rh = cam["rect"]
    sw, sh = screen if screen is not None else cam["screen"]
    return rx * sw, sh - (ry + rh) * sh, (rx + rw) * sw, sh - ry * sh


def is_identity(col_major16: Sequence[float], tol: float = 1e-6) -> bool:
    return bool(np.allclose(mat4(col_major16), np.eye(4), atol=tol))
