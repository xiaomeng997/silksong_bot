"""A person's session video (ssbot.tools.human_video, run by ssbot.tools.human_session): the ffmpeg command (the vision
mask filled before encoding, the marker's corner cropped losslessly), where the oracle's marker lands in the 1920x1080
output for the session's setup (a 1920x1080 render in Unity's fullscreen window on a 3840x2160 desktop, scaled 2x up
and 2x down: exactly the mask's marker) and for others (flagged), the corner decoded on synthetic frames, the labels
(marker, implausible, timestamp fallback, mask_mismatch), and the whole chain through ffmpeg when it is installed."""
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest
import zstandard

from ssbot.ipc.framing import MsgType
from ssbot.record import marker as mk
from ssbot.record import synthetic as syn
from ssbot.record.video import inside
from ssbot.tools import human_session as hs
from ssbot.tools import human_video as hv
from ssbot.vision import mask as vmask
from tests import align_synth as S
from tests.test_marker import MarkerLink

MASK = vmask.mask_rect(1920, 1080)
FULLSCREEN = ((0, 0, 3840, 2160), (3840, 2160))      # the game window's client on the desktop, the desktop


def test_ffmpeg_command():
    """ddagrab of desktop output 0, downloaded and scaled by area to 1920x1080, split: the mask's rect filled black
    before NVENC (video.mkv), the same rect of the unfilled frame as gray FFV1 (corner.mkv)."""
    cmd = hv.ffmpeg_cmd(Path("S"), hv.fills_for([]), MASK)
    assert cmd[:6] == [str(hv.FFMPEG), "-hide_banner", "-loglevel", "info", "-stats", "-y"]
    assert cmd[6:10] == ["-f", "lavfi", "-i", "ddagrab=output_idx=0:framerate=60:draw_mouse=0"]
    assert cmd[10:12] == ["-filter_complex",
                          "[0:v]hwdownload,format=bgra,scale=1920:1080:flags=area,split=2[full][raw];"
                          "[full]drawbox=x=1842:y=0:w=78:h=33:color=black:t=fill,format=nv12[v];"
                          "[raw]crop=78:33:1842:0,format=gray[c]"]
    assert cmd[12:] == ["-map", "[v]", "-c:v", "hevc_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "constqp", "-qp",
                        "18", "-g", "120", str(Path("S") / "video.mkv"),
                        "-map", "[c]", "-c:v", "ffv1", "-level", "3", str(Path("S") / "corner.mkv")]
    # Without the marker: masked all the same, no corner stream; a marker box outside the mask is filled as well.
    plain = hv.ffmpeg_cmd(Path("S"), hv.fills_for([(100, 50, 160, 70)]))
    assert plain[11] == ("[0:v]hwdownload,format=bgra,scale=1920:1080:flags=area,"
                         "drawbox=x=1842:y=0:w=78:h=33:color=black:t=fill,"
                         "drawbox=x=100:y=50:w=60:h=20:color=black:t=fill,format=nv12[v]")
    assert plain[-1] == str(Path("S") / "video.mkv") and "[c]" not in plain


def test_where_the_marker_lands_in_the_output():
    """The session's setup maps render px onto output px one to one (2x up into the fullscreen window, 2x down by
    the graph): the marker is the mask's marker for 1920x1080, inside the mask with a px of blur. Other setups move
    it: a 720p render in the same window still lies inside the mask's share (it no longer decodes); a windowed game,
    an ultrawide desktop or a 360p render put it outside: filled too, and flagged."""
    rect = vmask.marker_rect(1920, 1080)
    assert rect == (1860, 4, 1916, 20)
    box = hv.output_box(rect, (1920, 1080), *FULLSCREEN)
    assert box == (1859, 3, 1917, 21) and inside(box, MASK)
    assert hv.output_box(rect, (1920, 1080), (0, 0, 1920, 1080), (1920, 1080)) == rect   # nothing scales at all
    assert hv.fills_for([box]) == [list(MASK)]
    assert inside(hv.output_box(vmask.marker_rect(1280, 720), (1280, 720), *FULLSCREEN), MASK)
    for render, client, desktop in (((1280, 720), (200, 100, 1280, 720), (3840, 2160)),   # windowed
                                    ((1920, 1080), (0, 0, 3440, 1440), (3440, 1440)),     # pillarboxed, stretched
                                    ((640, 360), (0, 0, 3840, 2160), (3840, 2160))):
        b = hv.output_box(vmask.marker_rect(*render), render, client, desktop)
        assert not inside(b, MASK), (render, client, desktop, b)
        assert hv.fills_for([b])[1] == [max(0, b[0]), max(0, b[1]), min(1920, b[2]), min(1080, b[3])]
    assert hv.output_box([0, 0, 0, 0], (1920, 1080), *FULLSCREEN) is None


def _render(frame: int, seed: int = 4, cell: int | None = None) -> np.ndarray:
    """A 1920x1080 gray game image with the marker of `frame` (the default cell, 4 px)."""
    img = S.texture(1100, 1940, seed)[:1080, :1920].copy()
    mk.draw(img, frame, mk.Geometry.place((1920, 1080), cell=cell))
    return img


def _through_the_desktop(img: np.ndarray, up=cv2.INTER_LINEAR) -> np.ndarray:
    """Unity's 2x upscale into the 3840x2160 window, then the graph's 2x area downscale."""
    big = cv2.resize(img, (3840, 2160), interpolation=up)
    return cv2.resize(big, (1920, 1080), interpolation=cv2.INTER_AREA)


@pytest.mark.parametrize("up", [cv2.INTER_LINEAR, cv2.INTER_CUBIC, cv2.INTER_NEAREST])
def test_corner_decodes_after_the_desktop_scaling(up):
    """The corner stream's frames (the mask's rect of the output) decode exactly with the capture path's decoder,
    whatever filter the 2x upscale uses; a frame without the marker is absent."""
    frames = [70000 + 3 * i for i in range(6)]
    x0, y0, x1, y1 = MASK
    crops = [_through_the_desktop(_render(f), up)[y0:y1, x0:x1] for f in frames]
    crops.append(_through_the_desktop(S.texture(1100, 1940, 4)[:1080, :1920].copy(), up)[y0:y1, x0:x1])
    values, statuses = hv.decode_corner(crops, MASK)
    assert values.tolist() == [f % mk.MODULUS for f in frames] + [-1]
    assert [mk.DECODE_STATUS[s] for s in statuses] == ["ok"] * 6 + ["absent"]
    # The decoder reads a crop as the same client px: the full frame decodes to the same values.
    full = _through_the_desktop(_render(frames[0]), up)
    assert mk.FullResDecoder().decode(full).value == frames[0] % mk.MODULUS


def _states(frames, *, t0_ns: int, marker=True, place=None) -> hv.States:
    places = [(tuple(float(v) for v in vmask.marker_rect(1920, 1080)), (1920, 1080))]
    if place is not None:
        places.append(place)
    pl = np.zeros(len(frames), np.int64) if marker else np.full(len(frames), -1, np.int64)
    return hv.States(np.asarray(frames, np.int64), t0_ns + np.arange(len(frames)) * 16_666_667,
                     np.full(len(frames), marker), pl, places)


def test_labels_marker_else_timestamp_and_mask_mismatch():
    """Per video frame: the corner frame with the same pts, its decode, the label (the decoded frame where plausible,
    else the timestamp label with D calibrated on the decoded frames) and mask_mismatch; the summary for meta.json."""
    n = 600
    start = 5_000_000_000
    pts = np.round(np.arange(n) * 1e9 / 60 / 1e6).astype(np.int64) * 1_000_000      # mkv: whole ms
    # Video frame i shows STATE frame 1000 + i, whose end of frame is 40 ms before the capture.
    st = _states(range(1000 - 10, 1000 + n + 10), t0_ns=start - 40_000_000 - 10 * 16_666_667)
    values = (1000 + np.arange(n)) % mk.MODULUS
    statuses = np.zeros(n, np.int64)
    values[[100, 101]], statuses[[100, 101]] = -1, mk.DECODE_STATUS.index("absent")     # fades: timestamp labels
    values[300] = (1000 + 300 + 4321) % mk.MODULUS                                       # a misread: implausible
    keep = np.r_[0:200, 201:n]                                                           # no corner frame for 200
    meta = {"video_start_qpc_ns": start, "video": {"render": [1920, 1080], "fills": [list(MASK)],
                                                   "placements": [{"client": [0, 0, 3840, 2160],
                                                                   "desktop": [3840, 2160]}]}}
    arrays, summary = hv.build(meta, st, pts, pts[keep], values[keep], statuses[keep])
    src = np.asarray(mk.LABEL_SOURCES)[arrays["source"]]
    assert set(np.flatnonzero(src == "timestamp")) == {100, 101, 200, 300} and (src != "none").all()
    assert (arrays["frame"] == 1000 + np.arange(n)).all()                 # the fallbacks land right, too
    assert arrays["corner"][200] == -1 and arrays["corner"][201] == 200 and arrays["mk"][300] == -1
    status = [mk.DECODE_STATUS[s] for s in arrays["status"]]
    assert (status[100], status[200], status[300], status[0]) == ("absent", "off", "implausible", "ok")
    assert (arrays["pts_ns"] == pts).all() and not arrays["mm"].any()
    assert summary["frames"] == n and summary["corner_frames"] == n - 1 and summary["without_corner"] == 1
    assert summary["marker"] == n - 4 and summary["timestamp"] == 4 and summary["marker_share"] == (n - 4) / n
    assert summary["decode"] == {"ok": n - 4, "absent": 2, "off": 1, "implausible": 1}
    assert summary["mask_mismatch"] == 0 and summary["training_safe"] is True
    assert abs(summary["D_ms"] - 40.0) < 17
    # An older plugin's 12 px marker reported for STATE frames 1400..1409: the video frames around them are flagged,
    # and so are the marker pixels left outside the filled rects.
    big = (tuple(float(v) for v in vmask.marker_rect(1920, 1080, cell=18)), (1920, 1080))
    st2 = _states(range(1000 - 10, 1000 + n + 10), t0_ns=start - 40_000_000 - 10 * 16_666_667, place=big)
    st2.place[(st2.f >= 1400) & (st2.f < 1410)] = 1
    arrays, summary = hv.build(meta, st2, pts, pts[keep], values[keep], statuses[keep])
    assert set(np.flatnonzero(arrays["mm"])) == set(range(400 - 3, 410 + 3))
    assert summary["mask_mismatch"] == 16 and summary["marker_pixels_stored"] == 16 and not summary["training_safe"]


def _wire_states(path: Path, frames, q0: int, mk_of) -> None:
    raw = b"".join(syn.wire(MsgType.STATE, i + 1, dict(syn.state(f, q0=q0 - 1000 * syn.QPC_FREQ // 60, hero=False,
                                                                  ents=False), mk=mk_of(f)))
                   for i, f in enumerate(frames))
    with path.open("wb") as fh, zstandard.ZstdCompressor(level=3).stream_writer(fh) as z:
        z.write(raw)


def test_read_states_from_the_raw_stream(tmp_path):
    rect = [float(v) for v in vmask.marker_rect(1920, 1080)]
    _wire_states(tmp_path / "state.raw.zst", range(1000, 1010), 0,
                 lambda f: None if f < 1003 else {"drawn": True, "rect": rect, "screen": [1920, 1080]} if f < 1007
                 else {"drawn": False, "rect": rect})                  # an older plugin: no mk screen
    st = hv.read_states(tmp_path, syn.QPC_FREQ, screen=(1920, 1080))
    assert st.f.tolist() == list(range(1000, 1010)) and st.drawn.tolist() == [False] * 3 + [True] * 4 + [False] * 3
    assert st.place.tolist() == [-1] * 3 + [0] * 7 and st.places == [(tuple(rect), (1920, 1080))]
    assert (np.diff(st.t_eof) > 16_000_000).all()


def test_no_corner_stream_means_timestamp_labels(tmp_path):
    (tmp_path / "meta.json").write_text(json.dumps({"marker": {"on": False, "why": "OracleError: refused"}}),
                                        encoding="utf-8")
    assert hv.labels(tmp_path) == {"source": "timestamp", "why": "OracleError: refused"}
    assert hv.main([str(tmp_path)]) == 1 and not (tmp_path / "labels.npz").exists()


@pytest.mark.skipif(not (hv.FFMPEG.is_file() and hv.FFPROBE.is_file()), reason="ffmpeg is not installed")
def test_the_session_chain_through_ffmpeg(tmp_path):
    """The session's filter graph with a synthetic source in place of ddagrab (1920x1080 game images with the marker,
    scaled 2x up to the desktop by ffmpeg first) and FFV1 in place of NVENC: video.mkv's mask holds no marker pixel,
    corner.mkv decodes frame for frame, and labels() writes labels.npz and meta.json "labels"."""
    n, f0 = 24, 5000
    start = 7_000_000_000
    source = (("-f", "rawvideo", "-pix_fmt", "gray", "-s", "1920x1080", "-framerate", "60", "-i", "pipe:0"),
              "format=bgra,scale=3840:2160:flags=bilinear,")
    cmd = hv.ffmpeg_cmd(tmp_path, hv.fills_for([]), MASK, source=source, encoder=("-c:v", "ffv1"))
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    frames = [_render(f0 + i, seed=i % 3) for i in range(n)]
    p.communicate(b"".join(img.tobytes() for img in frames), timeout=120)
    assert p.returncode == 0
    rect = [float(v) for v in vmask.marker_rect(1920, 1080)]
    # STATE frame f ends 40 ms before the video frame that shows it: q0 puts frame f0 there.
    _wire_states(tmp_path / "state.raw.zst", range(f0 - 30, f0 + n + 30),
                 (start - 40_000_000) * syn.QPC_FREQ // 1_000_000_000 - f0 * syn.QPC_FREQ // 60 + 1000 *
                 syn.QPC_FREQ // 60, lambda f: {"drawn": True, "rect": rect, "screen": [1920, 1080]})
    meta = {"hello": syn.hello(), "video_start_qpc_ns": start, "marker": {"on": True, "screen": [1920, 1080]},
            "video": {"out": [1920, 1080], "render": [1920, 1080], "corner": list(MASK), "fills": [list(MASK)],
                      "placements": [{"client": [0, 0, 3840, 2160], "desktop": [3840, 2160]}]}}
    (tmp_path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    summary = hv.labels(tmp_path, progress=lambda *a: None)
    assert summary["frames"] == summary["corner_frames"] == n and summary["marker"] == n
    assert summary["decode"] == {"ok": n} and summary["training_safe"] is True
    lb = np.load(tmp_path / "labels.npz")
    assert lb["frame"].tolist() == list(range(f0, f0 + n)) and (lb["corner"] == np.arange(n)).all()
    assert json.loads((tmp_path / "meta.json").read_text("utf-8"))["labels"] == summary
    # video.mkv: the mask's rect is black in every frame (no marker pixel), the rest is the game image.
    out = subprocess.run([str(hv.FFMPEG), "-nostdin", "-v", "error", "-i", str(tmp_path / "video.mkv"), "-f",
                          "rawvideo", "-pix_fmt", "gray", "-fps_mode", "passthrough", "pipe:1"],
                         capture_output=True, check=True).stdout
    video = np.frombuffer(out, np.uint8).reshape(-1, 1080, 1920)
    x0, y0, x1, y1 = MASK
    assert len(video) == n and (video[:, y0:y1, x0:x1] <= 1).all()
    assert np.abs(video[0, 200:400, 200:400].astype(int) - frames[0][200:400, 200:400]).mean() < 4


def test_human_session_turns_the_marker_on_or_goes_on_without_it(capsys):
    """human_session: the marker on (its cell, rect and render size recorded); refused by an older SsOracle under
    -ssbot-human, or never shown in place: off again, said why, and the session goes on with timestamp labels."""
    on = hs.turn_marker_on(MarkerLink(screen=(1920, 1080)))
    assert on == {"on": True, "why": None, "corner": "tr", "cell": 4, "rect": [1860.0, 4.0, 1916.0, 20.0],
                  "screen": [1920, 1080], "resent": False}
    assert "frame marker on (tr, 4 px cells" in capsys.readouterr().out
    refused = hs.turn_marker_on(MarkerLink(refuse="-ssbot-human: a person's session is recorded without the marker"))
    assert refused["on"] is False and refused["why"].startswith("OracleError: -ssbot-human")
    link = MarkerLink(draws=False)
    assert hs.turn_marker_on(link)["why"].startswith("TimeoutError") and link.calls[-1] == ("frame.marker",
                                                                                            {"on": False})
    assert "timestamp labels only" in capsys.readouterr().out
