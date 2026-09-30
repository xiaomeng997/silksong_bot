"""Offline checks of the oracle camera convention (column-major V/P, normalized rect, top-left image origin)."""
import math

import numpy as np
import pytest

from ssbot.tools import projector


def unity_view(cx: float, cy: float, cz: float) -> np.ndarray:
    """Camera.worldToCameraMatrix for an unrotated camera at (cx, cy, cz): inverse TRS with z negated."""
    return np.array([[1, 0, 0, -cx], [0, 1, 0, -cy], [0, 0, -1, cz], [0, 0, 0, 1]], dtype=np.float64)


def unity_perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    """Matrix4x4.Perspective (OpenGL convention, what Camera.projectionMatrix returns)."""
    f = 1.0 / math.tan(math.radians(fov_deg) / 2)
    return np.array([
        [f / aspect, 0, 0, 0],
        [0, f, 0, 0],
        [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)],
        [0, 0, -1, 0],
    ])


def unity_ortho(half_h: float, aspect: float, near: float, far: float) -> np.ndarray:
    half_w = half_h * aspect
    return np.array([
        [1 / half_w, 0, 0, 0],
        [0, 1 / half_h, 0, 0],
        [0, 0, -2 / (far - near), -(far + near) / (far - near)],
        [0, 0, 0, 1],
    ])


def col_major(m: np.ndarray) -> list[float]:
    return list(m.flatten(order="F"))


def cam_dict(V, P, rect=(0.0, 0.0, 1.0, 1.0), screen=(1920, 1080)) -> dict:
    return {"V": col_major(V), "P": col_major(P), "rect": list(rect), "screen": list(screen)}


def test_mat4_is_column_major():
    m = np.arange(16, dtype=np.float64).reshape(4, 4)
    assert np.array_equal(projector.mat4(col_major(m)), m)
    with pytest.raises(ValueError):
        projector.mat4([0.0] * 15)


def test_perspective_center_and_top_edge():
    fov, d = 38.0, 38.1
    cam = cam_dict(unity_view(10, 20, -d), unity_perspective(fov, 16 / 9, 0.3, 1000))
    top = d * math.tan(math.radians(fov) / 2)
    px, ok = projector.project_cam([[10, 20, 0], [10, 20 + top, 0], [10, 20 - top, 0]], cam)
    assert ok.all()
    assert px[0] == pytest.approx([960, 540])
    assert px[1] == pytest.approx([960, 0], abs=1e-6)      # world up = image up (y grows downwards)
    assert px[2] == pytest.approx([960, 1080], abs=1e-6)


def test_letterboxed_rect_maps_into_the_viewport():
    # ForceCameraAspect clamps the aspect and letterboxes: rect y 0.05, height 0.9.
    rect = (0.0, 0.05, 1.0, 0.9)
    cam = cam_dict(unity_view(0, 0, -10), unity_perspective(40, 1920 / (1080 * 0.9), 0.3, 100), rect=rect)
    top = 10 * math.tan(math.radians(40) / 2)
    px, _ = projector.project_cam([[0, top, 0], [0, -top, 0]], cam)
    x0, y0, x1, y1 = projector.viewport_px(cam)
    assert (x0, x1) == pytest.approx((0, 1920))
    assert px[0][1] == pytest.approx(y0) and y0 == pytest.approx(54)
    assert px[1][1] == pytest.approx(y1) and y1 == pytest.approx(1026)


def test_ortho_hud_camera_and_2d_points():
    cam = cam_dict(unity_view(0, 0, -30), unity_ortho(8.4375, 16 / 9, 0.3, 100))
    px, ok = projector.project_cam([[-15.0, 8.4375], [0.0, 0.0]], cam)   # 2-D points get z = 0
    assert ok.all()
    assert px[0] == pytest.approx([0, 0])                 # top-left corner of the screen
    assert px[1] == pytest.approx([960, 540])


def test_points_behind_a_perspective_camera_are_flagged():
    cam = cam_dict(unity_view(0, 0, 0), unity_perspective(60, 16 / 9, 0.3, 100))
    _, ok = projector.project_cam([[0, 0, 5], [0, 0, -5]], cam)
    assert ok.tolist() == [True, False]


def test_identity_detection():
    assert projector.is_identity(col_major(np.eye(4)))
    assert not projector.is_identity(col_major(unity_view(1, 2, -3)))
