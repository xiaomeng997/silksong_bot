"""M1 projection check: oracle-projected colliders vs DebugMod's hitbox display (DESIGN §3.1.3; M1 exit "projection
IoU >= 0.95, vertex error <= 1.5 px"). The image and geometry parts live in ssbot.tools.projection_check.

Needs the training copy (SsOracle with RPCs hitbox.show / projection.sample, oracle/src/Train/ProjectionSample.cs, and
DebugMod) in gameplay, TRAIN profile, windowed and not minimized (Windows Graphics Capture stops for a minimized window;
a covered one is fine). No focus needed and no keys are sent. Put Hornet where terrain (and ideally an enemy or a
hazard) is in view and leave her idle: only polygons that sit still on screen around each capture are compared.
1920x1080 gives bigger polygons, so vertex rounding costs less IoU than at 1280x720, but a 1920x1080 window (client
area plus title bar) only fits on a desktop larger than 1080p; on a 1080p monitor use 1600x900. The client area must
equal the game's Screen size (STATE cam.screen), or every capture is skipped with a warning and the run fails. The
probe measures the window in physical pixels (DPI-aware, like the launcher), so display scaling does not matter; the
warning means the window does not show the whole game image (e.g. it is larger than the desktop): relaunch at a size
that fits.

    cd brain
    ..\\scripts\\uv.cmd run python -m ssbot.probes.m1_projection --shot m1_projection.png
    ..\\scripts\\uv.cmd run python -m ssbot.probes.m1_projection --rounds 10 --json m1_projection.json
    ..\\scripts\\uv.cmd run python -m ssbot.probes.m1_projection --vertex-only   # no DebugMod display, no capture
    ..\\scripts\\uv.cmd run python -m ssbot.probes.m1_projection --off           # switch DebugMod's hitboxes off (TRAIN)

Steps: (a) vertex check: projection.sample returns, for the colliders of one frame, world vertices and Unity's own
Camera.WorldToScreenPoint taken when the main camera renders (the V/P the STATE of that frame carries); projector.py on
that STATE's "cam" must land within 1.5 px (p99). It also compares Unity's end-of-frame projection (DebugMod's pose)
with the shake-corrected STATE camera. Every sample below counts, plus --vertex-samples extra ones.
(b) IoU: a fresh TERRAIN (scene.dump); DebugMod's hitboxes on and its UI panels hidden (unless --keep-ui); then per
round: wait until camera and hero are still, capture --frames frames, take a projection.sample (source debugmod: what
DebugMod draws). Each capture is assigned the newest STATE whose end-of-frame QPC precedes the capture callback (the
same clock); since the frame actually on screen may be a frame or two older, a polygon counts only if it sat still
(0.3 px) from --window frames before that STATE to the sample's frame. projection_check pairs each drawn collider with
the oracle label (TERRAIN solid / hazard by collider id, STATE ents collider by identical outline, hero box), finds
DebugMod's lines by colour near the outlines it reports and reports IoU per polygon. The IoU gate takes the polygons
whose label is the shape DebugMod draws (projection_check.LABEL_EXACT); labels of another shape (the hero box is
Collider2D.bounds, an ents box includes edgeRadius) are reported apart, with their offset and IoU(DebugMod, oracle), so
a label-definition difference does not pass for a projection error. PASS when at least MIN_POLYS such polygon-frames
were compared, their IoU p5 >= 0.95 and the vertex p99 <= 1.5 px; without --vertex-only, a missing DebugMod display or
no compared polygons is a FAIL. Finally DebugMod's ShowHitBoxes and UI panels are put back as they were. They last
only until the game restarts (DebugMod reads its Settings.json once at startup, from LocalLow, before SaveRedirect sends
its saves to the sandbox copy, which is never read back), but until then hitboxes left on draw over every capture:
after a crash run --off (hitbox.show changes DebugMod only in the TRAIN profile) or restart the instance. Non-TRAIN
profiles count ShowHitBoxes != 0 as a violation.

Residual error sources (reported, not corrected): DebugMod rounds each vertex to a whole pixel and strokes circles as
16+ chords; a box's edgeRadius is in the ents outline but not in DebugMod's drawing (outside the gate, see above);
Collider2D.bounds (the hero box) may include Box2D's contact skin (same); the antialiased line's centre
pixels over a bright or similar-coloured background shift the found edge by about half a pixel; the image may show an
older frame than the STATE assigned to it (only still polygons count); DebugMod projects with the camera after the shake
is removed, so during a shake its boxes are off the sprites by the shake (compared in that pose here); the camera may
render to a smaller texture (CameraRenderScaled), where DebugMod misplaces its lines (reported as a warning); TERRAIN
is dumped once per room (moving terrain goes stale and is left out); DebugMod UI panels or other overlays hiding a line
let the flood leak (flagged "leak"). Toggling the display on costs one hitch (DebugMod's FindObjectsOfTypeAll) and
each sample one frame a few ms.
"""
import argparse
import dataclasses
import json
import math
import sys
import threading
import time
from collections import Counter, deque

import msgpack
import numpy as np

from ssbot.ipc.framing import HEADER, MsgType
from ssbot.ipc.oracle_link import OracleError, OracleLink
from ssbot.oracle.messages import Terrain, split_frame, unpack
from ssbot.probes.common import in_gameplay
from ssbot.tools import projection_check as pc

results: list[tuple[str, str, str]] = []
MIN_POLYS = 10  # polygon-frames (label = the drawn shape) the IoU gate needs; fewer is a FAIL, not a pass by default


def check(name: str, ok: bool, detail: str = "", warn_only: bool = False) -> bool:
    level = "PASS" if ok else ("WARN" if warn_only else "FAIL")
    results.append((level, name, detail))
    print(f"  [{level}] {name}" + (f": {detail}" if detail else ""))
    return ok


class Recorder:
    """The last `keep` STATEs by frame and the newest TERRAIN, fed from the link's reader thread."""

    def __init__(self, link: OracleLink, keep: int = 1800):
        self.cv = threading.Condition()
        self.states: dict[int, dict] = {}
        self.order: deque[int] = deque()
        self.keep = keep
        self.terrain: Terrain | None = None
        link.subscribe_raw(self._on_raw)

    def _on_raw(self, msg_type: int, raw: bytes) -> None:
        if msg_type == MsgType.STATE:
            s = msgpack.unpackb(raw[HEADER.size:], raw=False, strict_map_key=False)
            with self.cv:
                self.states[s["f"]] = s
                self.order.append(s["f"])
                while len(self.order) > self.keep:
                    self.states.pop(self.order.popleft(), None)
                self.cv.notify_all()
        elif msg_type == MsgType.TERRAIN:
            t = Terrain.decode(unpack(split_frame(raw)[2]))
            with self.cv:
                self.terrain = t
                self.cv.notify_all()

    def wait_frame(self, f: int, timeout_s: float = 2.0) -> dict | None:
        with self.cv:
            self.cv.wait_for(lambda: f in self.states or (self.order and self.order[-1] > f + 120), timeout_s)
            return self.states.get(f)

    def window(self, f0: int, f1: int) -> list[dict] | None:
        """STATEs f0..f1, or None when one of them was not received (dropped)."""
        with self.cv:
            if any(f not in self.states for f in range(f0, f1 + 1)):
                return None
            return [self.states[f] for f in range(f0, f1 + 1)]

    def last(self, n: int) -> list[dict]:
        with self.cv:
            return [self.states[f] for f in list(self.order)[-n:]]

    def q_by_frame(self) -> dict[int, int]:
        with self.cv:
            return {f: s["q"] for f, s in self.states.items()}

    def wait_terrain(self, seq: int, timeout_s: float = 10.0) -> Terrain | None:
        with self.cv:
            self.cv.wait_for(lambda: self.terrain is not None and self.terrain.seq >= seq, timeout_s)
            return self.terrain if self.terrain is not None and self.terrain.seq >= seq else None


def same_view(a: dict, b: dict, tol: float = 1e-5) -> bool:
    """Camera (V, P, shake) and hero position unchanged between two STATEs."""
    ca, cb = a.get("cam"), b.get("cam")
    if ca is None or cb is None:
        return False
    for k in ("V", "P"):
        if np.max(np.abs(np.asarray(ca[k]) - np.asarray(cb[k]))) > tol:
            return False
    if np.max(np.abs(np.asarray(ca.get("shake") or (0, 0)) - np.asarray(cb.get("shake") or (0, 0)))) > tol:
        return False
    ha, hb = a.get("hero"), b.get("hero")
    return ha is not None and hb is not None and np.max(np.abs(np.asarray(ha["pos"]) - np.asarray(hb["pos"]))) <= 1e-4


def wait_still(rec: Recorder, frames: int = 20, timeout_s: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        last = rec.last(frames)
        if len(last) == frames and last[-1]["f"] - last[0]["f"] == frames - 1 and all(same_view(s, last[-1]) for s in last):
            return True
        time.sleep(0.05)
    return False


class Totals:
    def __init__(self) -> None:
        self.vertex_render: list[np.ndarray] = []
        self.vertex_eof: list[np.ndarray] = []
        self.samples = 0
        self.unrendered = 0
        self.frame_mismatch: list[float] = []
        self.src0 = 0
        self.polys: list[pc.PolyResult] = []
        self.counts: Counter = Counter()
        self.unmatched: Counter = Counter()
        self.skipped: Counter = Counter()
        self.coverage: list[float] = []
        self.thickness: list[float] = []
        self.shifts: Counter = Counter()
        self.palettes: list[dict] = []
        self.shake = 0.0
        self.warnings: set[str] = set()

    def add_sample(self, sample: dict, state: dict | None) -> None:
        self.samples += 1
        if not sample["cam"].get("render"):
            self.unrendered += 1
        if state is None or state.get("cam") is None:
            self.warnings.add(f"STATE {sample['frame']} of a sample was not received")
            return
        cam = state["cam"]
        if cam.get("src") != 1:
            self.src0 += 1
        if sample["cam"].get("render"):
            self.frame_mismatch.append(pc.matrices_match(sample["cam"], cam))
        self.vertex_render.append(pc.vertex_errors(sample, cam, "render"))
        self.vertex_eof.append(pc.vertex_errors(sample, cam, "eof"))
        self.shake = max(self.shake, float(np.max(np.abs(cam.get("shake") or (0.0, 0.0)))))
        for info in (sample["cam"], sample["dm_cam"]):
            if info.get("rt") and list(info["target"]) != list(info["screen"]):
                self.warnings.add(f"camera {info['name']} renders to a {info['target'][0]:.0f}x{info['target'][1]:.0f} texture on a "
                                  f"{info['screen'][0]:.0f}x{info['screen'][1]:.0f} screen: DebugMod draws in texture pixels, so its "
                                  "hitboxes are misplaced (IoU invalid); use full render resolution")
        if not sample["cam"].get("is_main"):
            self.warnings.add(f"STATE camera {sample['cam']['name']} is not Camera.main ({sample['dm_cam']['name']}), which DebugMod uses")


def take_sample(link: OracleLink, rec: Recorder, totals: Totals, source: str) -> tuple[dict, dict | None]:
    sample = link.rpc("projection.sample", timeout_s=10, source=source)
    state = rec.wait_frame(sample["frame"])
    totals.add_sample(sample, state)
    return sample, state


def run_round(link: OracleLink, rec: Recorder, totals: Totals, terrain: Terrain, args, qpc_freq: float,
              crop: tuple[int, int, int, int], keep_masks: bool) -> tuple | None:
    """One capture burst and its projection.sample; returns (image, FrameReport) of the last frame compared."""
    from ssbot.probes import shot

    if not wait_still(rec, timeout_s=args.still_s):
        totals.warnings.add("camera or hero never held still for 20 frames; moving polygons are left out")
    caps = shot.grab_frames(args.frames)
    sample, s_state = take_sample(link, rec, totals, "debugmod")
    if not caps:
        totals.counts["round without a captured frame (window minimized?)"] += 1
    if s_state is None or not caps:
        return None
    # Labels are matched in the sample's frame, where DebugMod's outlines and the STATE are exactly simultaneous.
    polys, unmatched, skipped = pc.match_sample(sample, s_state, terrain)
    totals.unmatched.update(unmatched)
    totals.skipped.update(skipped)
    fresh = []
    for p in polys:
        if p.stale > pc.STALE_MAX:
            totals.counts[f"stale label ({p.src})"] += 1
        else:
            fresh.append(p)
    x, y, w, h = crop
    last = None
    for t_ns, full in caps:
        img = full[y:y + h, x:x + w]
        f_img = pc.frame_for_capture(rec.q_by_frame(), t_ns, qpc_freq)
        if f_img is None:
            totals.counts["capture older than every STATE kept"] += 1
            continue
        states = rec.window(f_img - args.window, max(f_img, sample["frame"]))
        if states is None:
            totals.counts["STATE window incomplete"] += 1
            continue
        ref = next(s for s in states if s["f"] == f_img)
        if ref.get("cam") is None:
            continue
        screen = tuple(int(v) for v in ref["cam"]["screen"])
        if (img.shape[1], img.shape[0]) != screen:
            totals.counts["client area != cam.screen"] += 1
            totals.warnings.add(f"client area {img.shape[1]}x{img.shape[0]} != cam.screen {screen[0]}x{screen[1]}: captures "
                                "skipped; the window does not show the game's whole Screen (e.g. a window larger than the "
                                "desktop), relaunch it at a size that fits")
            continue
        keep = []
        for p in fresh:
            ok, _ = pc.stable(p, states, ref)
            if not ok:
                totals.counts["moved around the capture"] += 1
                continue
            world, radius = pc.world_at(p, ref)
            keep.append(dataclasses.replace(p, world=world, radius=radius))
        totals.counts["frames compared"] += 1
        rep = pc.evaluate_frame(img, keep, ref["cam"], sample, tol=args.tol, keep_masks=keep_masks)
        totals.polys.extend(rep.results)
        totals.counts["too small or out of view"] += rep.too_small
        totals.coverage.append(rep.coverage)
        totals.thickness.append(rep.thickness)
        totals.shifts[rep.shift[:2]] += 1
        totals.palettes.append(rep.palette)
        last = (img, rep)
    return last


def fmt_stats(st: dict, unit: str = "") -> str:
    if not st.get("n"):
        return "n=0"
    return (f"n={st['n']} p5={st['p5']:.4g}{unit} p50={st['p50']:.4g}{unit} p99={st['p99']:.4g}{unit} "
            f"min={st['min']:.4g}{unit} max={st['max']:.4g}{unit}")


def save_images(path: str, img: np.ndarray, rep: pc.FrameReport) -> None:
    """<path>: the client-area capture; <path>_overlay.png: oracle polygons (magenta) with IoU below IOU_MIN in red;
    <path>_masks.png: capture region D only green, oracle region O only magenta, both white."""
    import cv2

    base = path.rsplit(".", 1)[0]
    cv2.imwrite(path, img)
    over = img.copy()
    for r in rep.results:
        bad = r.iou < pc.IOU_MIN
        colour = (0, 0, 255) if bad else (255, 0, 255)
        if r.img_radius > 0:
            c = r.img_pts[0] - 0.5
            cv2.circle(over, (round(c[0]), round(c[1])), round(r.img_radius), colour, 1, cv2.LINE_AA)
        else:
            cv2.polylines(over, [np.round(r.img_pts - 0.5).astype(np.int32)], True, colour, 1, cv2.LINE_AA)
        if bad:
            x, y = r.img_pts[0]
            cv2.putText(over, f"{r.iou:.2f}", (round(x) + 3, round(y) - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    cv2.imwrite(base + "_overlay.png", over)
    masks = (img * 0.35).astype(np.uint8)
    for r in rep.results:
        if r.d is None:
            continue
        x0, y0, x1, y1 = r.box
        view = masks[y0:y1, x0:x1]
        view[r.d & ~r.o] = (0, 255, 0)
        view[r.o & ~r.d] = (255, 0, 255)
        view[r.d & r.o] = (255, 255, 255)
    cv2.imwrite(base + "_masks.png", masks)
    print(f"  wrote {path}, {base}_overlay.png, {base}_masks.png")


def report(totals: Totals, vertex_only: bool) -> dict:
    print("\n== vertex check (projector.py on STATE cam vs Unity WorldToScreenPoint) ==")
    vr = pc.summarize(np.concatenate(totals.vertex_render) if totals.vertex_render else [])
    ve = pc.summarize(np.concatenate(totals.vertex_eof) if totals.vertex_eof else [])
    print(f"  {totals.samples} samples, {totals.unrendered} without a render-time projection, STATE cam src 0 in {totals.src0}")
    check("vertex samples taken", vr.get("n", 0) > 0, fmt_stats(vr, " px"))
    if vr.get("n"):
        check(f"vertex error p99 <= {pc.VERTEX_P99_MAX} px (render pose, the STATE V/P)", vr["p99"] <= pc.VERTEX_P99_MAX, fmt_stats(vr, " px"))
    if ve.get("n"):
        check(f"vertex error p99 <= {pc.VERTEX_P99_MAX} px (end-of-frame pose, shake-corrected: DebugMod's)",
              ve["p99"] <= pc.VERTEX_P99_MAX, fmt_stats(ve, " px"), warn_only=True)
    if totals.frame_mismatch:
        worst = max(totals.frame_mismatch)
        check("samples line up with their STATE frame (same V/P)", worst < 1e-4, f"max |dV|,|dP| {worst:.2e}", warn_only=True)
    check("STATE cam V/P from render time (src 1)", totals.src0 == 0, f"src 0 in {totals.src0} of {totals.samples}",
          warn_only=True)
    print(f"  largest camera shake seen: {totals.shake:.4f} u")
    out = {"vertex_render": vr, "vertex_eof": ve, "samples": totals.samples, "shake_max": totals.shake}
    if vertex_only:
        return out

    print("\n== IoU (DebugMod's outlines in the capture vs oracle polygons) ==")
    polys = totals.polys
    # The gate compares the projection only where the label is the shape DebugMod draws; elsewhere IoU also measures
    # the label's own difference (hero bounds skin, edgeRadius, moved TERRAIN), reported below with its offset.
    exact = [r for r in polys if r.offset <= pc.LABEL_EXACT]
    other = [r for r in polys if r.offset > pc.LABEL_EXACT]
    st = pc.summarize(r.iou for r in exact)
    print(f"  compared: {len(polys)} polygon-frames, {len(exact)} of them labelled with the drawn shape; "
          f"left out: {dict(totals.counts)}")
    print(f"  drawn but not labelled by the oracle: {dict(totals.unmatched) or '-'}; skipped: {dict(totals.skipped) or '-'}")
    if totals.coverage:
        print(f"  segmentation: centreline coverage p50 {np.median(totals.coverage):.3f}, line core "
              f"{np.median(totals.thickness):.2f} px, best shift {dict(totals.shifts)}, palette {totals.palettes[-1]}")
        check("segmentation finds DebugMod's lines where it says it drew them (coverage >= 0.8)",
              float(np.median(totals.coverage)) >= 0.8, f"p50 {np.median(totals.coverage):.3f}", warn_only=True)
        check("capture is not offset (best shift (0, 0))", set(totals.shifts) == {(0, 0)}, str(dict(totals.shifts)),
              warn_only=True)
    check(f"at least {MIN_POLYS} polygon-frames compared (label = the drawn shape)", len(exact) >= MIN_POLYS,
          f"{len(exact)} of {len(polys)}")
    if exact:
        check(f"IoU p5 >= {pc.IOU_MIN} (label = the drawn shape)", st["p5"] >= pc.IOU_MIN, fmt_stats(st))
    if other:
        so = pc.summarize(r.iou for r in other)
        check(f"IoU p5 >= {pc.IOU_MIN} where the label is another shape (not gated)", so["p5"] >= pc.IOU_MIN,
              f"{fmt_stats(so)}; offset up to {max(r.offset for r in other):.4g} u, {sorted({r.type for r in other})}",
              warn_only=True)
    if polys:
        print("  by type and source (label offset: world units from the drawn outline; geom: IoU(DebugMod, oracle)):")
        for name, groups in (("", sorted({r.type for r in polys})), ("src ", sorted({r.src for r in polys}))):
            for key in groups:
                rs = [r for r in polys if (r.src if name else r.type) == key]
                print(f"    {name + key:16s} {fmt_stats(pc.summarize(r.iou for r in rs))}; geom p50 "
                      f"{np.median([r.iou_geom for r in rs]):.3f}; offset p50 {np.median([r.offset for r in rs]):.2g} "
                      f"max {max(r.offset for r in rs):.2g} u; {sum(r.offset > pc.LABEL_EXACT for r in rs)} not gated")
        dm = pc.summarize(r.iou_dm for r in polys)
        geom = pc.summarize(r.iou_geom for r in polys)
        print(f"  IoU(capture, DebugMod's vertices) {fmt_stats(dm)}")
        print(f"  IoU(DebugMod's vertices, oracle)  {fmt_stats(geom)}")
        check("capture chain: IoU(capture, DebugMod's vertices) p5 >= 0.95", dm["p5"] >= 0.95, fmt_stats(dm), warn_only=True)
        leaks = sum(r.leak for r in polys)
        check("no flood leaks (gaps in DebugMod's outlines)", leaks == 0, f"{leaks}", warn_only=True)
        colours = [r.colour for r in polys if r.colour is not None]
        if colours:
            print(f"  outline colour agreement p50 {np.median(colours):.3f}")
        print("  worst:")
        for r in sorted(polys, key=lambda r: r.iou)[:10]:
            print(f"    {r.key:>14s} {r.type:16s} {r.src:8s} iou {r.iou:.3f} (dm {r.iou_dm:.3f}, geom {r.iou_geom:.3f}) "
                  f"area {r.area} px, offset {r.offset:.2g} u{'' if r.offset <= pc.LABEL_EXACT else ' (not gated)'}"
                  f"{' LEAK' if r.leak else ''}")
        out.update(iou=st, iou_all=pc.summarize(r.iou for r in polys), iou_not_gated=pc.summarize(r.iou for r in other),
                   iou_dm=dm, iou_geom=geom, leaks=leaks,
                   polys=[{"key": r.key, "type": r.type, "src": r.src, "iou": r.iou, "iou_dm": r.iou_dm, "iou_geom": r.iou_geom,
                           "area": r.area, "colour": r.colour, "leak": r.leak,
                           "offset": r.offset if math.isfinite(r.offset) else None} for r in polys])
    out.update(left_out=dict(totals.counts), unmatched=dict(totals.unmatched), skipped=dict(totals.skipped))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--rounds", type=int, default=5, help="capture + sample rounds (IoU)")
    ap.add_argument("--frames", type=int, default=3, help="frames captured per round")
    ap.add_argument("--window", type=int, default=4, help="frames before the assigned STATE a polygon must sit still")
    ap.add_argument("--vertex-samples", type=int, default=10, help="extra projection.sample calls for the vertex check")
    ap.add_argument("--vertex-only", action="store_true", help="only the vertex check (no DebugMod display, no capture)")
    ap.add_argument("--tol", type=float, default=60.0, help="colour distance (RGB) for DebugMod's line pixels")
    ap.add_argument("--still-s", type=float, default=5.0, help="how long to wait for a still camera and hero per round")
    ap.add_argument("--keep-ui", action="store_true", help="leave DebugMod's UI panels as they are")
    ap.add_argument("--shot", help="save the last compared capture here, plus <name>_overlay.png and <name>_masks.png")
    ap.add_argument("--json", help="write the numbers here")
    ap.add_argument("--off", action="store_true", help="switch DebugMod's hitboxes off and exit")
    args = ap.parse_args()

    link = OracleLink(instance=args.instance)
    rpcs = set(link.hello["rpcs"])
    print("hello:", {k: link.hello[k] for k in ("plugin", "game", "instance")})
    missing = {"projection.sample", "hitbox.show", "scene.dump"} - rpcs
    if missing:
        print(f"FAIL: RPCs missing {sorted(missing)}: is this SsOracle build older than ProjectionSample?")
        return 1
    if args.off:
        try:
            print("hitbox.show off ->", link.rpc("hitbox.show", on=False))
        except OracleError as e:
            print(f"FAIL: {e}\n  hitbox.show changes DebugMod only in the TRAIN profile (profile.set TRAIN), or restart the "
                  "instance: DebugMod then reloads ShowHitBoxes and its panels from LocalLow's Settings.json")
            return 1
        finally:
            link.close()
        return 0

    rec = Recorder(link)
    try:
        link.wait_state(in_gameplay, timeout_s=10)
    except TimeoutError:
        print("FAIL: not in gameplay (load a save and stand Hornet in a room)")
        return 1
    qpc_freq = float(link.hello["qpc_freq"])
    totals = Totals()
    status = None
    vertex_only = args.vertex_only
    if not vertex_only:
        try:
            status = link.rpc("hitbox.show")
        except OracleError as e:
            # Still measure the vertices, but the IoU half of the M1 check did not run: that is no pass.
            check("DebugMod's hitbox display available (the IoU check needs it; --vertex-only skips it)", False, str(e))
            print("  vertex check only")
            vertex_only = True

    last = None
    try:
        if not vertex_only:
            from ssbot.io import game_window
            from ssbot.tools.launcher import set_dpi_aware

            set_dpi_aware()  # client rect in physical pixels, like the WGC frame (else a scaled desktop skips every capture)
            hwnd = game_window.find()
            if not hwnd:
                print("FAIL: game window not found")
                return 1
            crop = game_window.client_in_capture(hwnd)
            print(f"\nDebugMod {status.get('version')}: ShowHitBoxes {status['show']}, panels {status['panels']}")
            dump = link.rpc("scene.dump", timeout_s=20)
            terrain = rec.wait_terrain(dump["seq"])
            if not check("TERRAIN of this room received", terrain is not None, str(terrain.summary() if terrain else dump)):
                return 1
            ui = {} if args.keep_ui else {"ui": False}
            try:
                on = link.rpc("hitbox.show", on=True, timeout_s=10, **ui)
            except OracleError as e:
                check("DebugMod's hitbox display switched on", False,
                      f"{e} (hitbox.show changes DebugMod only in the TRAIN profile)")
                return 1
            if not check("DebugMod's hitbox display running", on["render"] and on["settled"],
                         f"state {on['state']}, {on['colliders']} colliders, line width {on['line_width']}, panels {on['panels']}"):
                return 1
            if any(on["panels"].values()):
                totals.warnings.add(f"DebugMod UI panels visible ({on['panels']}): they may hide lines")
            time.sleep(0.3)  # the panels hide in DebugMod's next Update
            for i in range(args.rounds):
                out = run_round(link, rec, totals, terrain, args, qpc_freq, crop, keep_masks=bool(args.shot))
                last = out or last
                print(f"  round {i + 1}/{args.rounds}: {len(totals.polys)} polygon-frames so far")
        source = "physics" if vertex_only else "auto"
        for _ in range(args.vertex_samples):
            take_sample(link, rec, totals, source)
            time.sleep(0.1)
    finally:
        if status is not None:
            try:
                now = link.rpc("hitbox.show")  # nothing to put back when switching on was refused (not TRAIN)
                if (now["show"], now["panels"]) != (status["show"], status["panels"]):
                    back = link.rpc("hitbox.show", mode=status["show"], panels=status["panels"], timeout_s=10)
                    print(f"\nDebugMod restored: ShowHitBoxes {back['show']}, panels {back['panels']}")
            except Exception as e:  # noqa: BLE001 - the user must hear about this whatever it was
                print(f"\n!! could not restore DebugMod's hitbox display ({e}); run with --off (TRAIN profile) or restart "
                      "the instance, and check its UI panels")

    if last is not None and args.shot:
        print("\n== images ==")
        save_images(args.shot, *last)
    for w in sorted(totals.warnings):
        check(w, False, warn_only=True)
    out = report(totals, vertex_only)
    link.close()
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
        print(f"wrote {args.json}")

    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    print(f"\n{'FAIL' if fails else 'PASS'}: {len(results) - len(fails) - len(warns)} passed, {len(warns)} warnings, {len(fails)} failed")
    for level, name, detail in fails + warns:
        print(f"  {level} {name}: {detail}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
