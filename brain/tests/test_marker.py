"""The frame marker (ssbot.record.marker; oracle/src/Export/MarkerCode.cs and FrameMarker.cs) and the vision mask
(ssbot.vision.mask): the code against the oracle's vectors, the cell sizes and the mask's rect, decoding at full
resolution (the capture path: several client sizes, crops off, scaled images never misread) and from scaled
thumbnails (older recordings), missing, partial and corrupt markers, the label sources (marker, else timestamp), the
label gate and the exact report on synthetic timestamp streams with known offsets, duplicates and skips, synthetic
episodes with the marker read in the capture path (and in thumbnails, as before), against which the correlation
monitor (ssbot.record.align) is scored, and marker_on."""
import json
from dataclasses import replace

import cv2
import numpy as np
import pytest

from ssbot.ipc.oracle_link import OracleError
from ssbot.record import align
from ssbot.record import marker as mk
from ssbot.record.recorder import RecordingReader
from ssbot.vision import mask as vmask
from tests import align_synth as S

MS = 1_000_000

# Same table as oracle/tests/MarkerCheck/Program.cs: rows top to bottom, 1 = white, border included.
VECTORS = [
    (0, "00000000000000|01000000000000|00000000000010|00000000000000"),
    (1, "00000000000000|01100000000000|00000000110010|00000000000000"),
    (12345, "00000000000000|01100111000000|00001100100010|00000000000000"),
    (65535, "00000000000000|01111111111100|00111111110010|00000000000000"),
    (70000, "00000000000000|01000011101000|00001000101010|00000000000000"),
    (2600000, "00000000000000|01000000100000|00110101000110|00000000000000"),
]


def test_code_matches_the_oracle_vectors():
    for frame, rows in VECTORS:
        assert "|".join("".join(map(str, r)) for r in mk.grid(frame)) == rows
    assert [mk.crc4(v) for v in (0, 1, 2, 0x8000, 0xFFFF, 12345, 4464)] == [0, 3, 6, 3, 3, 1, 5]
    # Placement as MarkerCode.Place / DefaultCell (the same table as MarkerCheck): `cell` px in from the corner.
    assert mk.Geometry.place((1280, 720), "tr") == mk.Geometry(1235.0, 3.0, 3.0)
    assert mk.Geometry.place((1920, 1080), "bl") == mk.Geometry(4.0, 1060.0, 4.0)
    assert mk.Geometry.place((1366, 768), "tr") == mk.Geometry(1321.0, 3.0, 3.0)
    assert mk.Geometry.place((1600, 900), "br") == mk.Geometry(1555.0, 885.0, 3.0)
    assert mk.Geometry.place((2560, 1440), "tr") == mk.Geometry(2485.0, 5.0, 5.0)
    assert mk.Geometry.place((3840, 2160), "tr") == mk.Geometry(3720.0, 8.0, 8.0)
    assert mk.Geometry.place((1280, 720), "tl").rect == (3.0, 3.0, 45.0, 15.0)
    assert mk.Geometry.place((1280, 720), "tr", 12) == mk.Geometry(1100.0, 12.0, 12.0)   # an explicit cell


def test_the_marker_lies_inside_the_vision_mask():
    """The marker is where ssbot.vision.mask expects it, and every marker the full-resolution decoder can find
    (+-SEARCH_PX) lies inside the mask, at every client size and corner."""
    assert (mk.COLS + 2, mk.ROWS + 2) == (vmask.GRID_W, vmask.GRID_H)
    for w, h in ((1280, 720), (1920, 1080), (1366, 768), (2560, 1440), (3840, 2160), (640, 360)):
        for corner in vmask.CORNERS:
            assert mk.Geometry.place((w, h), corner).rect == vmask.marker_rect(w, h, corner)
            x0, y0, x1, y1 = vmask.mask_rect(w, h, corner)
            m0, n0, m1, n1 = vmask.marker_rect(w, h, corner)
            assert x0 <= m0 - mk.SEARCH_PX and m1 + mk.SEARCH_PX <= x1 and y0 <= n0 - mk.SEARCH_PX                 and n1 + mk.SEARCH_PX <= y1, (w, h, corner)


def test_geometry_from_state_and_unwrap():
    state = {"drawn": True, "corner": "tr", "cell": 12, "rect": [1100.0, 12.0, 1268.0, 60.0], "grid": [2, 12]}
    assert mk.Geometry.from_state(state) == mk.Geometry(1100.0, 12.0, 12.0)
    assert mk.Geometry.from_state(None) is None and mk.Geometry.from_state(dict(state, grid=[3, 12])) is None
    assert mk.Geometry.from_state(dict(state, rect=None)) is None
    assert mk.unwrap(70000 % 65536, 70003) == 70000 and mk.unwrap(65535, 65540) == 65535
    assert mk.unwrap(3, 65534) == 65539 and mk.unwrap(100, 100 + 40000) == 100 + 65536


def _client(w: int, h: int, seed: int = 3) -> np.ndarray:
    tex = S.texture(max(h, 400) + 20, max(w, 400) + 20, seed)
    return tex[:h, :w].copy()


def _thumb(img: np.ndarray, width: int) -> tuple[np.ndarray, tuple[float, float]]:
    h, w = img.shape
    th = max(1, round(width * h / w))
    return cv2.resize(img, (width, th), interpolation=cv2.INTER_AREA), (width / w, th / h)


@pytest.mark.parametrize("client, width", [((1280, 720), 320), ((1920, 1080), 320), ((2560, 1440), 320),
                                           ((1366, 768), 320), ((1280, 720), 400), ((640, 360), 160)])
def test_decodes_from_scaled_thumbnails(client, width):
    """The probe's cell size (3 thumbnail px) at several client sizes and thumbnail widths, in every corner, with the
    client crop a few px off and some noise: every frame decodes exactly."""
    rng = np.random.default_rng(width + client[0])
    w, h = client
    base = _client(w, h)
    cell = int(np.ceil(3 * w / width))
    for corner in mk.CORNERS:
        g = mk.Geometry.place(client, corner, cell)
        for _ in range(6):
            frame = int(rng.integers(0, 5_000_000))
            img = base.copy()
            mk.draw(img, frame, g)
            dx, dy = (int(v) for v in rng.integers(-3, 4, 2))
            img = np.roll(img, (dy, dx), axis=(0, 1))
            img = np.clip(img + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)
            small, scale = _thumb(img, width)
            d = mk.decode(small, g, scale)
            assert d.status == "ok" and mk.unwrap(d.value, frame + 3) == frame, (corner, frame, (dx, dy), d)
    # The oracle's default cell decodes at full resolution, here as in the capture path.
    img = base.copy()
    mk.draw(img, 424242, mk.Geometry.place(client, "tr"))
    assert mk.decode(img, mk.Geometry.place(client, "tr"), (1.0, 1.0)).value == 424242 % mk.MODULUS
    assert mk.FullResDecoder().decode(img).value == 424242 % mk.MODULUS


@pytest.mark.parametrize("full_res", [True, False])
def test_missing_partial_and_corrupt_markers(full_res):
    """The same statuses at full resolution (the capture path, the default cell) and from thumbnails (12 px cells)."""
    w, h, width = 1280, 720, 320
    g = mk.Geometry.place((w, h), "tr", None if full_res else 12)
    base = _client(w, h)

    def decoded(img):
        if full_res:
            return mk.FullResDecoder().decode(img)
        small, scale = _thumb(img, width)
        return mk.decode(small, g, scale)

    assert decoded(base).status == "absent"                       # the marker was off
    assert decoded(np.zeros_like(base)).status == "absent"        # a black screen: no contrast
    img = base.copy()
    mk.draw(img, 12345, g)
    assert decoded(img).value == 12345
    x0, y0, x1, y1 = (int(v) for v in g.rect)
    covered = img.copy()
    covered[y0:y1, x0:x1] = 128                                   # something drawn over it
    assert decoded(covered).status == "absent"

    def cell(gr, gc):
        c = int(g.cell)
        return slice(y0 + gr * c, y0 + (gr + 1) * c), slice(x0 + gc * c, x0 + (gc + 1) * c)

    partial = img.copy()
    partial[cell(1, 5)] = 128                                     # one data cell half-way: not a bit
    assert decoded(partial).status == "unclear"
    flipped = img.copy()
    flipped[cell(2, 7)] = 255 - flipped[cell(2, 7)]               # one data bit wrong: the crc catches it
    assert decoded(flipped).status == "check"
    sync = img.copy()
    sync[cell(1, 1)] = 0                                          # a sync cell wrong: no marker
    assert decoded(sync).status == "absent"
    far = np.roll(img, 40, axis=1)                                # 40 client px off: beyond the search
    assert decoded(far).status == "absent"


@pytest.mark.parametrize("client", [(1280, 720), (1920, 1080), (2560, 1440), (1366, 768), (1600, 900),
                                    (3840, 2160), (640, 360)])
def test_decodes_at_full_resolution(client):
    """The capture path's decoder at several client sizes and their cells (3-8 px): the client crop up to 3 px off
    (the search), some noise, consecutive captures (the last shift is tried first): every frame decodes exactly."""
    rng = np.random.default_rng(client[0])
    w, h = client
    base = _client(w, h)
    g = mk.Geometry.place(client)
    dec = mk.FullResDecoder()
    for _ in range(12):
        frame = int(rng.integers(0, 5_000_000))
        img = base.copy()
        mk.draw(img, frame, g)
        dx, dy = (int(v) for v in rng.integers(-3, 4, 2))
        img = np.roll(img, (dy, dx), axis=(0, 1))
        img = np.clip(img + rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)
        d = dec.decode(img)
        assert d.status == "ok" and mk.unwrap(d.value, frame - 2) == frame, (frame, (dx, dy), d)
    assert dec.decode(np.zeros((h, w), np.uint8)).status == "absent"   # a black screen: no search needed


def test_scaled_images_are_never_misread():
    """Something scaling the client (a render size other than the window's, DPI virtualization) moves and blurs the
    marker: the capture path's decoder then fails (the capture falls back to its timestamp label), it never reads
    another frame."""
    rng = np.random.default_rng(7)
    w, h = 1280, 720
    base = _client(w, h)
    g = mk.Geometry.place((w, h))
    wrong = 0
    for scale in (0.67, 0.75, 0.8, 0.9, 0.95, 1.05, 1.1, 1.25, 1.5):
        for _ in range(4):
            frame = int(rng.integers(0, 5_000_000))
            img = base.copy()
            mk.draw(img, frame, g)
            big = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_LINEAR)
            d = mk.FullResDecoder().decode(big)
            wrong += d.status == "ok" and d.value != frame % mk.MODULUS
    assert wrong == 0


def test_lean_judge_matches_the_general_one():
    """_judge_one (the capture path's steady state) gives what _judge gives for one shift."""
    rng = np.random.default_rng(3)
    g = mk.Geometry(0.0, 0.0, 1.0)
    for i in range(400):
        cells = np.zeros((mk.ROWS + 2, mk.COLS + 2))
        img = np.zeros((mk.ROWS + 2, mk.COLS + 2), np.uint8)
        mk.draw(img, int(rng.integers(0, 70000)), g, black=int(rng.integers(0, 60)), white=int(rng.integers(90, 256)))
        cells[:] = img + rng.normal(0, [1, 8, 25, 40][i % 4], img.shape)
        if i % 7 == 0:
            cells[1, 2 + i % 10] = cells.mean()                   # an unclear data cell
        a = mk._judge(cells[None], np.zeros((1, 2)))
        b = mk._judge_one(cells.ravel(), (0, 0))
        assert (a.status, a.value) == (b.status, b.value) and a.contrast == pytest.approx(b.contrast), i


# ---- the exact report on synthetic timestamp streams ---------------------------------------------------------------

T0 = 5_000_000_000_000
PERIOD = 16_666_667
D_TRUE = 23_300_000
FRAME_CLOCK = 8_000_000


def _stream(n: int = 3000, *, stale=(), early=(), dup=(), drop=(), hidden=(), off=(), drop_states=(), seed: int = 0
            ) -> tuple[mk.Truth, tuple[int, int], list[int]]:
    """STATE frames 1000.., one capture per frame at t_eof + D_TRUE + 0..4 ms (the frame clock 8 ms later) showing
    it, except: stale i shows the frame before (offset -1), early i the frame after (+1); dup i is captured once
    more half a period later (the same frame twice, offset 0); drop i is never delivered (the next capture skips a
    frame, offset 0); hidden i has no decodable marker; off: frames drawn without the marker; drop_states: frames
    without a STATE. Returns (truth, valid (lo, hi] of D on the frame clock, the frame each capture shows)."""
    rng = np.random.default_rng(seed)
    frames = np.arange(1000, 1000 + n)
    t_eof = T0 + frames * PERIOD + rng.integers(-1_000_000, 1_000_001, n)
    t, shown, hide = [], [], []
    lo, hi = -2**62, 2**62
    for i, f in enumerate(frames):
        if i in drop:
            continue
        ti = int(t_eof[i]) + D_TRUE + int(rng.integers(0, 4_000_001))
        g = int(f) - 1 if i in stale else int(f) + 1 if i in early else int(f)
        for tc in ([ti, ti + PERIOD // 2] if i in dup else [ti]):
            t.append(tc)
            shown.append(g)
            hide.append(i in hidden or g in off)
            if g == f and i + 1 < n:
                lo, hi = max(lo, tc + FRAME_CLOCK - int(t_eof[i + 1])), min(hi, tc + FRAME_CLOCK - int(t_eof[i]))
    t = np.asarray(t, np.int64)
    shown_a = np.asarray(shown, np.int64)
    hide_a = np.asarray(hide, bool)
    keep = ~np.isin(frames, list(drop_states))
    tr = mk.Truth(seq=np.arange(len(t)), t_arrival=t, t_frame=t + FRAME_CLOCK,
                  value=np.where(hide_a, -1, shown_a % mk.MODULUS), status=np.where(hide_a, 1, 0),
                  f=frames[keep], t_eof=t_eof[keep], drawn=~np.isin(frames[keep], list(off)))
    return tr, (lo, hi), shown


def test_exact_report_counts_offsets_duplicates_and_skips():
    stale = set(range(200, 2800, 250))            # 11 captures one frame late
    early = {333, 1333, 2333}
    dup = {444, 1444, 2444, 2644, 2744}
    drop = {555, 1555, 1655, 1755, 2555, 2655, 2755}
    hidden = {666, 1666, 2666, 2766}
    off = set(range(2980, 3000))                  # the marker off for 20 frames
    tr, (lo, hi), shown = _stream(stale=stale, early=early, dup=dup, drop=drop, hidden=hidden, off=off,
                                  drop_states={1900})
    rep, arrays = mk.exact(tr, min_captures=1000)
    pr = rep.primary
    assert pr.clock == "frame" and lo < pr.D_ms * MS <= hi and rep.alt.clock == "arrival"
    assert pr.hist == {-1: len(stale), 0: pr.decoded - len(stale) - len(early), 1: len(early)}
    assert pr.missing == len(hidden) and pr.missing_by == {"absent": len(hidden)}
    # The captures showing 1899 and 1900 are both labelled 1899, whose next frame has no STATE; so is the last one.
    assert pr.excluded == {"no_label": 0, "state_gap": 3, "marker_off": 20}
    assert pr.counted == len(shown) - 3 and pr.decoded == pr.counted - len(hidden) - 20
    assert pr.share == pytest.approx(pr.zero / (pr.decoded + pr.missing)) and pr.verdict == "FAIL"
    assert pr.first_nonzero[0][3] == -1 and pr.first_nonzero[0][0] == 200
    # Duplicates: every stale capture repeats the frame before it, every early one is repeated by the next, every
    # dup twice. Skips: after every stale capture, before every early one, and every capture never delivered.
    assert rep.duplicates == len(stale) + len(early) + len(dup)
    assert rep.skips == len(stale) + len(early) + len(drop) and rep.backwards == 0
    assert rep.shown_steps == {0: rep.duplicates, 1: rep.shown_steps[1], 2: rep.skips}
    # Never captured (as far as the markers tell): the skipped frames and those hidden or unmarked.
    assert rep.never_captured == rep.skips + len(hidden) + 20
    assert pr.label_steps[1] > 2900 and "timestamp labels alone" in rep.format().splitlines()[-1]
    assert (arrays["k"][arrays["counted"] & (arrays["shown"] >= 0)] != 0).sum() == len(stale) + len(early)
    # The gate: every decoded capture carries its marker label, whatever its timestamp says; the hidden ones fall back.
    g = rep.gate
    assert (g.judged, g.marker, g.missing, g.marker_off) == (pr.decoded + pr.missing, pr.decoded, len(hidden), 20)
    assert g.share == pytest.approx(pr.decoded / (pr.decoded + len(hidden))) and g.verdict == "PASS" and rep.ok
    assert rep.format().splitlines()[-1].startswith("PASS")


def test_exact_report_gate_threshold_and_coverage():
    tr, (lo, hi), _ = _stream(n=2000)
    rep, _ = mk.exact(tr)
    assert rep.ok and rep.primary.share == 1.0 and rep.primary.verdict == "PASS" and rep.alt.verdict == "PASS"
    assert rep.gate.share == 1.0 and rep.gate.verdict == "PASS"
    assert rep.alt.D_ms == pytest.approx(rep.primary.D_ms - FRAME_CLOCK / MS, abs=4.0)
    assert rep.primary.lag_ms["p50"] == pytest.approx((D_TRUE + FRAME_CLOCK + 2 * MS) / MS, abs=1.0)
    small = mk.exact(tr, min_captures=5000)[0]
    assert small.primary.verdict == small.gate.verdict == "INCONCLUSIVE" and not small.ok
    # Timestamp labels: 0.4 % one frame late passes, 0.6 % fails; a missing marker counts like an offset. The gate
    # does not care how late a capture is (its marker labels it), only whether its marker was read.
    late8 = mk.exact(_stream(n=2000, stale=set(range(100, 1700, 200)))[0])[0]     # 8 / 1999
    late12 = mk.exact(_stream(n=2000, stale=set(range(100, 1900, 150)))[0])[0]    # 12 / 1999
    assert late8.primary.ok and not late12.primary.ok and late8.ok and late12.ok
    rep, _ = mk.exact(_stream(n=2000, hidden=set(range(100, 1900, 150)))[0])     # 12 / 1999 missing
    assert not rep.primary.ok and not rep.ok and rep.gate.missing == 12 and rep.gate.verdict == "FAIL"
    assert rep.primary.hist == {0: rep.primary.decoded} and rep.primary.missing == 12
    assert "fall back to their timestamp label" in rep.gate.reason
    assert mk.exact(_stream(n=2000, hidden=set(range(100, 1700, 200)))[0])[0].ok   # 8 / 1999 missing
    # Markers not decoded where STATE says the marker was off are left out, not counted.
    rep, _ = mk.exact(_stream(n=2000, off=set(range(1500, 1560)))[0])
    assert rep.ok and rep.primary.excluded["marker_off"] >= 60 and rep.primary.missing == 0
    assert rep.gate.marker_off >= 60 and rep.gate.missing == 0


def test_exact_report_with_a_fixed_D():
    tr, _, _ = _stream(n=2000)
    rep, _ = mk.exact(tr)
    early, _ = mk.exact(tr, D_ms=rep.primary.D_ms - PERIOD / MS)   # labels one frame late: every capture at -1
    assert early.primary.hist == {-1: early.primary.decoded} and early.alt is None and not early.primary.ok
    assert early.ok                                                 # the marker labels do not depend on D
    late, _ = mk.exact(tr, D_ms=rep.primary.D_ms + PERIOD / MS)
    assert late.primary.hist == {1: late.primary.decoded}
    empty = mk.Truth(*(np.zeros(0, np.int64) for _ in range(5)), tr.f, tr.t_eof, tr.drawn)
    e = mk.exact(empty)[0]
    assert e.primary.reason == e.gate.reason == "no captures" and not e.ok
    none = mk.exact(_stream(n=2000, hidden=set(range(2000)))[0])[0]  # the marker drawn but never read
    assert none.gate.verdict == "FAIL" and "no decoded marker" in none.gate.reason and not none.ok


# ---- labels: the marker where it decoded, else the timestamp ----------------------------------------------------

def test_label_sources_marker_else_timestamp():
    hidden = set(range(100, 1900, 150))
    stale = {50, 1950}
    tr, _, shown = _stream(n=2000, hidden=hidden, stale=stale)
    rep, arrays = mk.exact(tr)
    lb = mk.capture_labels(tr, D_ms=rep.primary.D_ms)
    src = np.asarray(mk.LABEL_SOURCES)[lb.source]
    assert set(np.flatnonzero(src == "timestamp")) == hidden and (src != "none").all()
    # A marker label is the frame the capture shows, also where the timestamp is one frame off.
    ok = src == "marker"
    assert (lb.frame[ok] == np.asarray(shown)[ok]).all() and lb.frame[50] == shown[50]
    # The fallback is the timestamp label (align.match with the calibrated D) and is flagged as such.
    L = arrays["label"]
    assert all(lb.frame[i] == tr.f[L[i]] for i in hidden)
    assert lb.summary() == {"captures": 2000, "marker": 2000 - len(hidden), "timestamp": len(hidden), "none": 0,
                            "marker_share": (2000 - len(hidden)) / 2000, "clock": "frame",
                            "D_ms": round(rep.primary.D_ms, 3)}
    assert rep.labels == lb.summary()
    # D calibrated from the decoded captures when not given: the same labels.
    assert np.array_equal(mk.capture_labels(tr).frame, lb.frame)
    # Nothing decoded and no D: no labels at all; with a D, timestamp labels only.
    blind, _, _ = _stream(n=500, hidden=set(range(500)))
    assert mk.capture_labels(blind).summary()["none"] == 500
    ts = mk.capture_labels(blind, D_ms=(D_TRUE + FRAME_CLOCK) / MS).summary()
    assert ts["timestamp"] == 500 and ts["marker_share"] == 0.0


def test_implausible_markers_fall_back_to_their_timestamp_label():
    """Something drawn over the data cells alone can pass the 4-bit crc as another frame. A decoded marker more than
    max_offset frames from its capture's timestamp label, or outside the session's STATE frame range, is rejected
    ("implausible"): the capture falls back to its timestamp label, and the gate counts it as missing. Captures one
    frame late (offset -1) and up to max_offset off stay marker labels."""
    tr, _, shown = _stream(n=2000, stale={50})
    wrong = {300: 12345, 900: -777, 1500: 4, 1990: 40}   # decoded - shown frame (1990: past the last STATE)
    near = {1200: 3, 1700: -2}                             # within max_offset: a plausible marker
    value = tr.value.copy()
    for i, d in (wrong | near).items():
        value[i] = (shown[i] + d) % mk.MODULUS
    bad = replace(tr, value=value)
    lb = mk.capture_labels(bad)
    src = np.asarray(mk.LABEL_SOURCES)[lb.source]
    assert set(np.flatnonzero(src == "timestamp")) == set(wrong) and src[50] == "marker"
    assert all(lb.frame[i] == shown[i] + d for i, d in near.items())
    clean = mk.reject_implausible(bad)
    assert set(np.flatnonzero(clean.status == mk.IMPLAUSIBLE)) == set(wrong)
    assert (clean.value[list(wrong)] == -1).all()
    assert mk.reject_implausible(tr) is tr                        # nothing to reject: the same truth
    # A fixed D (one frame late labels) moves the window with it: offsets are judged against those labels.
    D = int(round(mk.exact(tr)[0].primary.D_ms * 1e6))
    assert set(np.flatnonzero(mk.reject_implausible(bad, D=D).status == mk.IMPLAUSIBLE)) == set(wrong)
    rep_, _ = mk.exact(bad)
    assert rep_.decode["implausible"] == len(wrong) and rep_.gate.missing_by == {"implausible": len(wrong)}
    assert rep_.gate.missing == len(wrong) and rep_.labels["timestamp"] == len(wrong) and rep_.labels["none"] == 0


# ---- synthetic episodes with the marker drawn ----------------------------------------------------------------------

@pytest.fixture(scope="module")
def marked(tmp_path_factory):
    """Hornet-like figure and labelled HUD; captures 300.. every 61st stale, 500..511 one frame late (a run), three
    markers covered, the marker off for the last 10 frames."""
    stale = set(range(300, 900, 61)) | set(range(500, 512))
    ep = S.make(tmp_path_factory.mktemp("marked"), seconds=20, seed=1, stale=stale, hero="sprite", lead=1.0,
                hud_state=True, marker="tr", hide_marker={100, 101, 700}, marker_off=set(range(2190, 2200)))
    rep, arrays, tr = mk.exact_episode(ep.path, min_captures=300)
    return ep, rep, arrays, tr


def test_episode_truth_is_the_frame_each_capture_shows(marked):
    ep, rep, arrays, tr = marked
    shown = arrays["shown"]
    ok = shown >= 0
    assert (shown[ok] == np.asarray(ep.capture_frame)[ok]).all()
    assert set(np.flatnonzero(~ok)) == {100, 101, 700} | set(range(1190, 1200))
    pr = rep.primary
    lo, hi = ep.valid_D["frame"]
    assert lo < pr.D_ms * MS <= hi and pr.verdict == "FAIL"
    late = len(set(range(300, 900, 61)) | set(range(500, 512)))
    assert pr.hist == {-1: late, 0: pr.decoded - late} and pr.missing == 3
    assert pr.share == pytest.approx((pr.decoded - late) / (pr.decoded + 3))
    assert rep.marker_frames == 1190 and rep.decode == {"ok": 1187, "absent": 13} and rep.decoded_in_capture
    assert rep.gate.verdict == "PASS" and rep.gate.missing == 3 and rep.labels["timestamp"] == 13
    # The thumbnails never show the marker: the masked corner is the fill, in every capture.
    x0, y0, x1, y1 = vmask.mask_rect(*S.SCREEN)
    x0, y0, x1, y1 = -(-x0 // 4), -(-y0 // 4), x1 // 4, y1 // 4             # thumbnail px wholly inside it
    assert all((img[y0:y1, x0:x1] == vmask.FILL).all() for _, img in mk.VideoReader(ep.path).frames())
    check = RecordingReader(ep.path).check()
    assert "frame marker on in 1190 STATE frames" in check.format()
    assert check.labels == {"captures": 1200, "marker": 1187, "timestamp": 13, "share": 1187 / 1200,
                            "decoded_in_capture": True, "decode": {"ok": 1187, "absent": 13}, "masked": True,
                            "mask_mismatch": 0, "training_safe": True}
    assert "masked in the capture path, no marker outside the mask: training data" in check.format()
    assert rep.mask == {"masked": True, "mask_mismatch": 0, "training_safe": True, "states_outside": 0, "outside": []}
    assert "training_safe True" in rep.format()


def test_mask_report_flags_states_with_the_marker_outside_the_mask(marked):
    """After the fact, every marker place a STATE reported is mapped into the video's client size as the guard maps
    it: an older plugin's 12 px marker (in px of a 1280x720 render, shown in the 640x360 client) lies outside the
    mask, so the episode is not training data even where no capture was flagged."""
    ep = marked[0]
    vr = mk.VideoReader(ep.path)
    nominal = {(tuple(map(float, vmask.marker_rect(*S.SCREEN))), S.SCREEN): 1190}
    assert mk.mask_report(vr, nominal)["training_safe"] is True
    old = dict(nominal) | {((1100.0, 12.0, 1268.0, 60.0), (1280, 720)): 7}
    m = mk.mask_report(vr, old)
    assert m["states_outside"] == 7 and m["training_safe"] is False and m["outside"][0][2] == list(S.SCREEN)
    notes = mk.mask_notes(m, 1197)
    assert len(notes) == 1 and notes[0].startswith("NOT training data (mask_mismatch)")
    assert mk.mask_notes(dict(m, masked=False), 1197)[0].startswith("the video is unmasked")


def test_monitor_scored_against_the_truth(marked):
    ep, rep, arrays, tr = marked
    mrep, off, *_ = mk.monitor_against_truth(ep.path, rep, arrays)
    m = rep.monitor
    assert m["verdict"] == "FAIL" and m["truth_verdict"] == "FAIL" and m["false_aligned"] == 0
    late = len(set(range(300, 900, 61)) | set(range(500, 512)))
    assert m["truly_off"] == late and m["off_flagged"] + m["off_unseen"] == late and m["off_flagged"] >= late - 2
    assert m["judged_zero"] > 900 and m["false_misaligned"] == 0 and m["wrong_offset"] == 0
    assert "monitor vs truth" in rep.format() and m["D_ms"] == pytest.approx(m["truth_D_ms"], abs=6.0)


def test_marker_is_masked_for_the_monitor_and_the_cli(tmp_path, capsys):
    """An aligned episode with the marker read in the capture path: the monitor masks the marker's rect (STATE mk)
    and the filled corner, PASSes and reports the label sources; the marker's own report PASSes, and the CLI writes
    marker.json and labels.npz."""
    ep = S.make(tmp_path, seconds=20, seed=4, marker="tr")
    rep, *_ = align.align_episode(ep.path)
    assert rep.ok and rep.primary.share == 1.0 and rep.labels["share"] == 1.0 and "carry a marker label" in rep.format()
    trk = align.oracle_track(RecordingReader(ep.path).states(keys=("q", "cam", "game", "mk")), S.syn.QPC_FREQ)
    assert (trk.fixed[:, 1] == align.FIXED_MARKER).sum() == len(trk.f)
    assert align._vision_mask(mk.VideoReader(ep.path)) == [[589 / 640, 0.0, 1.0, 21 / 360]]
    assert mk.main([str(ep.path), "--json", "--monitor", "--labels", "--min-captures", "300"]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out.splitlines()[-1] and "monitor vs truth" in out
    saved = json.loads((ep.path / "marker.json").read_text("utf-8"))
    assert saved["ok"] is True and saved["verdict"] == "PASS" and saved["verdicts"] == {"frame": "PASS",
                                                                                        "arrival": "PASS"}
    assert saved["monitor"]["false_aligned"] == 0 and saved["primary"]["hist"] == {"0": saved["primary"]["decoded"]}
    lb = np.load(ep.path / "labels.npz")
    assert (lb["source"] == mk.MARKER_LABEL).all() and np.array_equal(lb["frame"], ep.capture_frame)


def test_legacy_recordings_decode_from_the_thumbnails(tmp_path):
    """A recording from before the capture path read the marker (12 px cells in any corner, unmasked thumbnails):
    the truth comes from the thumbnails, as it did."""
    ep = S.make(tmp_path, seconds=12, seed=2, marker="bl", legacy_marker=True, hide_marker={50})
    rep, arrays, tr = mk.exact_episode(ep.path, min_captures=300)
    assert not tr.in_capture and not rep.decoded_in_capture and rep.decode == {"ok": len(ep.capture_t) - 1,
                                                                               "absent": 1}
    ok = arrays["shown"] >= 0
    assert (arrays["shown"][ok] == np.asarray(ep.capture_frame)[ok]).all() and rep.ok
    # The marker is in the unmasked thumbnails: validation data only, never training data.
    assert rep.mask["masked"] is False and rep.mask["training_safe"] is False
    assert any("VALIDATION data only" in n for n in rep.notes)
    assert "VALIDATION data only" in RecordingReader(ep.path).check().format()
    with pytest.raises(ValueError, match="mask's corner"):
        S.make(tmp_path / "x", seconds=1, marker="bl")


def test_gate_sample_size_counts_only_captures_judged_against_the_marker():
    # The marker drawn in only 100 frames: 2899 captures are left out as marker_off, so the sample is 100, not 2999.
    rep, _ = mk.exact(_stream(n=3000, off=set(range(1100, 4000)))[0])
    g = rep.primary
    assert g.verdict == "INCONCLUSIVE" and not g.ok
    assert g.decoded + g.missing < 1000 and "judged against the marker" in g.reason
    assert rep.gate.verdict == "INCONCLUSIVE" and rep.gate.judged < 1000 and not rep.ok


def test_marker_going_off_during_the_run_is_inconclusive_or_noted():
    # Off around 15 % of the captures: the gate did not see the whole recording.
    rep, _ = mk.exact(_stream(n=3000, off=set(range(3550, 4000)))[0])
    assert rep.primary.verdict == "INCONCLUSIVE" and "went off during the run" in rep.primary.reason
    assert rep.gate.verdict == "INCONCLUSIVE" and "went off during the run" in rep.gate.reason
    # Off around 5 %: still judged on the rest, with a note.
    rep, _ = mk.exact(_stream(n=3000, off=set(range(3850, 4000)))[0])
    assert rep.primary.verdict == "PASS" and "not judged" in rep.primary.reason
    assert rep.gate.verdict == "PASS" and "not judged" in rep.gate.reason


def test_undecodable_marker_next_to_a_dropped_state_counts_against_the_share():
    tr = _stream(n=3000, hidden=set(range(500, 2500, 7)), drop_states=set(range(503, 2503, 7)))[0]
    rep, _ = mk.exact(tr)
    g = rep.primary
    assert g.missing >= 280 and g.excluded["marker_off"] < 10


# ---- turning it on ------------------------------------------------------------------------------------------------

class MarkerLink:
    """OracleLink for marker_on: the oracle's default cell is `default` (SsOracle before 2026-09-30: height / 60).
    screen_in: where STATE gives the render size ("mk": mk.screen, "cam": cam.screen only, as before 2026-09-30, or
    None); draws=False: no STATE ever shows the marker drawn; obeys=False: an explicit cell is ignored."""

    def __init__(self, default=vmask.cell_px, refuse: str | None = None, screen=(1280, 720), screen_in="mk",
                 draws=True, obeys=True):
        self.default, self.refuse, self.screen = default, refuse, screen
        self.screen_in, self.draws, self.obeys = screen_in, draws, obeys
        self.calls = []
        self.cell = None

    def rpc(self, name, timeout_s=10.0, **args):
        self.calls.append((name, args))
        if self.refuse and args.get("on"):
            raise OracleError(self.refuse)
        size = args.get("size") if self.obeys else None
        self.cell = (size or self.default(self.screen[1])) if args.get("on") else None
        return {"on": bool(args.get("on")), "corner": "tr", "cell": self.cell}

    def wait_state(self, pred=lambda s: True, timeout_s=10.0, newer_than=None):
        w, h = self.screen
        mk_ = None
        if self.cell:
            mk_ = {"drawn": self.draws, "corner": "tr", "cell": self.cell, "grid": [2, 12],
                   "rect": [float(v) for v in vmask.marker_rect(w, h, "tr", self.cell)]}
            if self.screen_in == "mk":
                mk_["screen"] = [w, h]
        s = {"f": 100, "cam": {"screen": [float(w), float(h)]} if self.screen_in == "cam" else None, "mk": mk_}
        if not pred(s):
            raise TimeoutError("condition not met")
        return s


def test_marker_on_draws_the_masks_marker():
    link = MarkerLink()
    res = mk.marker_on(link)
    assert link.calls == [("frame.marker", {"on": True, "corner": "tr"})] and res["cell"] == 3 and "resent" not in res
    assert res["screen"] == [1280, 720] and res["rect"] == [1235.0, 3.0, 1277.0, 15.0]
    # An older plugin draws its larger default, and gives the render size only in cam: the mask's cell is sent.
    old = MarkerLink(default=lambda h: max(4, round(h / 60)), screen=(1920, 1080), screen_in="cam")
    res = mk.marker_on(old)
    assert old.calls == [("frame.marker", {"on": True, "corner": "tr"}),
                         ("frame.marker", {"on": True, "corner": "tr", "size": 4})] and res["resent"]
    assert mk.marker_off(old) == {"on": False, "corner": "tr", "cell": None}
    with pytest.raises(OracleError, match="ssbot-human"):
        mk.marker_on(MarkerLink(refuse="-ssbot-human: a person's session is recorded without the marker"))
    assert mk.marker_screen({"mk": {"screen": [0, 0]}, "cam": {"screen": [1280.0, 720.0]}}) == (1280, 720)
    assert mk.marker_screen({"mk": {"rect": [1, 2, 3, 4]}, "cam": None}) is None


@pytest.mark.parametrize("why", ["never drawn", "no render size", "cell ignored"])
def test_marker_on_turns_the_marker_off_when_it_fails(why):
    """Once the oracle accepted frame.marker, any failure turns it off again: a session declared unmarked never
    carries a drawn marker (no STATE shows it drawn; no STATE says the render size, so its rect cannot be checked;
    an older plugin that ignores the explicit cell keeps its large marker)."""
    link = {"never drawn": lambda: MarkerLink(draws=False),
            "no render size": lambda: MarkerLink(screen_in=None),
            "cell ignored": lambda: MarkerLink(default=lambda h: max(4, round(h / 60)), obeys=False)}[why]()
    with pytest.raises(TimeoutError):
        mk.marker_on(link)
    assert link.calls[0] == ("frame.marker", {"on": True, "corner": "tr"})
    assert link.calls[-1] == ("frame.marker", {"on": False}) and link.cell is None

    class Interrupted(MarkerLink):
        def wait_state(self, *a, **k):
            raise KeyboardInterrupt

    link = Interrupted()
    with pytest.raises(KeyboardInterrupt):
        mk.marker_on(link)
    assert link.calls[-1] == ("frame.marker", {"on": False})
