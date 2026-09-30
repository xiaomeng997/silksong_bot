"""The frame marker (ssbot.record.marker; oracle/src/Export/MarkerCode.cs and FrameMarker.cs): the code against the
oracle's vectors, decoding from scaled thumbnails, missing, partial and corrupt markers, the exact alignment report on
synthetic timestamp streams with known offsets, duplicates and skips, and synthetic episodes with the marker drawn,
against which the correlation monitor (ssbot.record.align) is scored."""
import json

import cv2
import numpy as np
import pytest

from ssbot.record import align
from ssbot.record import marker as mk
from ssbot.record.recorder import RecordingReader
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
    # Placement as MarkerCode.Place / DefaultCell: 3 px of a 320 px thumbnail at 16:9, `cell` px in from the corner.
    assert mk.Geometry.place((1280, 720), "tr") == mk.Geometry(1100.0, 12.0, 12.0)
    assert mk.Geometry.place((1920, 1080), "bl") == mk.Geometry(18.0, 990.0, 18.0)
    assert mk.Geometry.place((1366, 768), "tr") == mk.Geometry(1171.0, 13.0, 13.0)
    assert mk.Geometry.place((1600, 900), "br") == mk.Geometry(1375.0, 825.0, 15.0)
    assert mk.Geometry.place((1280, 720), "tl").rect == (12.0, 12.0, 180.0, 60.0)


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
    # The oracle's default cell at 16:9 is the same 3 px of a 320 px thumbnail; full resolution decodes too.
    img = base.copy()
    mk.draw(img, 424242, mk.Geometry.place(client, "tr"))
    assert mk.decode(img, mk.Geometry.place(client, "tr"), (1.0, 1.0)).value == 424242 % mk.MODULUS


def test_missing_partial_and_corrupt_markers():
    w, h, width = 1280, 720, 320
    g = mk.Geometry.place((w, h), "tr")
    base = _client(w, h)

    def decoded(img):
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
    far = np.roll(img, 40, axis=1)                                # 10 thumbnail px off: beyond the search
    assert decoded(far).status == "absent"


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
    assert pr.label_steps[1] > 2900 and rep.format().splitlines()[-1].startswith("FAIL")
    assert (arrays["k"][arrays["counted"] & (arrays["shown"] >= 0)] != 0).sum() == len(stale) + len(early)


def test_exact_report_gate_threshold_and_coverage():
    tr, (lo, hi), _ = _stream(n=2000)
    rep, _ = mk.exact(tr)
    assert rep.ok and rep.primary.share == 1.0 and rep.primary.verdict == "PASS" and rep.alt.verdict == "PASS"
    assert rep.alt.D_ms == pytest.approx(rep.primary.D_ms - FRAME_CLOCK / MS, abs=4.0)
    assert rep.primary.lag_ms["p50"] == pytest.approx((D_TRUE + FRAME_CLOCK + 2 * MS) / MS, abs=1.0)
    assert mk.exact(tr, min_captures=5000)[0].primary.verdict == "INCONCLUSIVE"
    # 0.4 % one frame late passes, 0.6 % fails; a missing marker counts like an offset.
    assert mk.exact(_stream(n=2000, stale=set(range(100, 1700, 200)))[0])[0].ok          # 8 / 1999
    assert not mk.exact(_stream(n=2000, stale=set(range(100, 1900, 150)))[0])[0].ok      # 12 / 1999
    assert not mk.exact(_stream(n=2000, hidden=set(range(100, 1900, 150)))[0])[0].ok
    rep, _ = mk.exact(_stream(n=2000, hidden=set(range(100, 1900, 150)))[0])
    assert rep.primary.hist == {0: rep.primary.decoded} and rep.primary.missing == 12
    # Markers not decoded where STATE says the marker was off are left out, not counted.
    rep, _ = mk.exact(_stream(n=2000, off=set(range(1500, 1560)))[0])
    assert rep.ok and rep.primary.excluded["marker_off"] >= 60 and rep.primary.missing == 0


def test_exact_report_with_a_fixed_D():
    tr, _, _ = _stream(n=2000)
    rep, _ = mk.exact(tr)
    early, _ = mk.exact(tr, D_ms=rep.primary.D_ms - PERIOD / MS)   # labels one frame late: every capture at -1
    assert early.primary.hist == {-1: early.primary.decoded} and early.alt is None and not early.ok
    late, _ = mk.exact(tr, D_ms=rep.primary.D_ms + PERIOD / MS)
    assert late.primary.hist == {1: late.primary.decoded}
    empty = mk.Truth(*(np.zeros(0, np.int64) for _ in range(5)), tr.f, tr.t_eof, tr.drawn)
    assert mk.exact(empty)[0].primary.reason == "no captures"


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
    assert rep.marker_frames == 1190 and rep.decode == {"ok": 1187, "absent": 13}
    assert "frame marker on in 1190 STATE frames" in RecordingReader(ep.path).check().format()


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
    """An aligned episode with the marker: the monitor masks the marker's rect (STATE mk), which changes every frame,
    and PASSes; the marker's own report PASSes, and the CLI writes marker.json."""
    ep = S.make(tmp_path, seconds=20, seed=4, marker="bl")
    rep, *_ = align.align_episode(ep.path)
    assert rep.ok and rep.primary.share == 1.0
    trk = align.oracle_track(RecordingReader(ep.path).states(keys=("q", "cam", "game", "mk")), S.syn.QPC_FREQ)
    assert (trk.fixed[:, 1] == align.FIXED_MARKER).sum() == len(trk.f)
    assert mk.main([str(ep.path), "--json", "--monitor", "--min-captures", "300"]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out.splitlines()[-1] and "monitor vs truth" in out
    saved = json.loads((ep.path / "marker.json").read_text("utf-8"))
    assert saved["ok"] is True and saved["verdicts"] == {"frame": "PASS", "arrival": "PASS"}
    assert saved["monitor"]["false_aligned"] == 0 and saved["primary"]["hist"] == {"0": saved["primary"]["decoded"]}


def test_gate_sample_size_counts_only_captures_judged_against_the_marker():
    # The marker drawn in only 100 frames: 2899 captures are left out as marker_off, so the sample is 100, not 2999.
    rep, _ = mk.exact(_stream(n=3000, off=set(range(1100, 4000)))[0])
    g = rep.primary
    assert g.verdict == "INCONCLUSIVE" and not g.ok
    assert g.decoded + g.missing < 1000 and "judged against the marker" in g.reason


def test_marker_going_off_during_the_run_is_inconclusive_or_noted():
    # Off around 15 % of the captures: the gate did not see the whole recording.
    rep, _ = mk.exact(_stream(n=3000, off=set(range(3550, 4000)))[0])
    assert rep.primary.verdict == "INCONCLUSIVE" and "went off during the run" in rep.primary.reason
    # Off around 5 %: still judged on the rest, with a note.
    rep, _ = mk.exact(_stream(n=3000, off=set(range(3850, 4000)))[0])
    assert rep.primary.verdict == "PASS" and "not judged" in rep.primary.reason


def test_undecodable_marker_next_to_a_dropped_state_counts_against_the_share():
    tr = _stream(n=3000, hidden=set(range(500, 2500, 7)), drop_states=set(range(503, 2503, 7)))[0]
    rep, _ = mk.exact(tr)
    g = rep.primary
    assert g.missing >= 280 and g.excluded["marker_off"] < 10
