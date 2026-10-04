"""Key track renderer prototype (DESIGN 2, the formal run's video: a rhythm-game key track rendered afterwards from
the decision logs; M2 plan "key economy"): one lane per key, a note appears at the frame its press was first decided,
falls at a constant speed and meets the judgement line at the frame the game latched the press; its length is the
hold. A changed note jumps to its new frame and leaves a grey ghost of the old one for a moment; a cancelled plan
stays as a grey ghost until its frame has passed the line. Offline, from a run's key plan log (keys_i<N>.jsonl) and,
for the arena strip above the lanes (hero and boss boxes), the episode's recording.

    cd brain
    ../scripts/uv.cmd run python -m ssbot.tools.key_track C:/ssbot/data/runs/m2/<run> --instance 3 --episode 0
        [--start-s 10 --seconds 20] [--out C:/ssbot/sandbox/key_track_sample] [--no-video]

Writes PNG frames (frames/NNNNN.png, one per game frame) and key_track.mp4 (60 fps, ffmpeg libx264) to --out, plus
notes.json (the notes drawn, with their histories).
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from ssbot.train.keyplan import final_press, match_actual

FFMPEG = Path(r"C:\ssbot\tools\ffmpeg\bin\ffmpeg.exe")
LANES = ("left", "right", "up", "down", "jump", "attack", "quickcast", "dash", "bind")
LABELS = {"left": "LEFT", "right": "RIGHT", "up": "UP", "down": "DOWN", "jump": "JUMP", "attack": "ATTACK",
          "quickcast": "SPEAR", "dash": "DASH", "bind": "BIND"}
COLORS = {"left": (86, 156, 214), "right": (86, 156, 214), "up": (197, 134, 192), "down": (197, 134, 192),
          "jump": (78, 201, 176), "attack": (244, 135, 113), "quickcast": (220, 200, 90), "dash": (156, 220, 254),
          "bind": (181, 206, 168)}
GREY = (110, 110, 110)
BG = (18, 18, 22)
W, H = 640, 720
STRIP_H = 120                 # the arena strip above the lanes
LINE_Y = H - 90               # the judgement line
PX_F = 6.0                    # pixels per frame (0.1 s = 36 px): a note decided 1.5 s ahead enters at the top
GHOST_F = 12                  # frames a moved note's old place stays drawn


def note_track(rec: dict, f_lo: int, f_hi: int) -> list[dict]:
    """The notes to draw, each with its planned (press, release) per change, the latched press / release when it was
    executed and when it ends (cancelled)."""
    lat = match_actual(rec)
    out = []
    for i, n in enumerate(rec["notes"]):
        key, born, p0, r0, st, exf, sup, hist = n
        if key not in LANES or st == "h":
            continue
        steps = [(born, p0, r0)]
        cancel = None
        for hf, hp, hr in hist:
            if hp < 0:
                cancel = hf
            else:
                steps.append((hf, hp, hr))
        last_p = final_press(n)
        if last_p < f_lo - 120 or born > f_hi:
            continue
        a = lat.get(i)
        out.append({"key": key, "steps": steps, "cancel": cancel, "status": st, "exec": exf, "sup": bool(sup),
                    "latched": list(a) if a else None})
    return out


def _planned(nt: dict, f: int) -> tuple[int, int] | None:
    cur = None
    for hf, p, r in nt["steps"]:
        if hf <= f:
            cur = (p, r)
    return cur


def render(rec: dict, f_lo: int, f_hi: int, out: Path, states: dict | None = None, video: bool = True) -> dict:
    from PIL import Image, ImageDraw, ImageFont
    notes = note_track(rec, f_lo, f_hi)
    used = [k for k in LANES if any(n["key"] == k for n in notes)]
    lane_w = (W - 40) // max(1, len(used))
    x0 = 20
    lane_x = {k: x0 + i * lane_w for i, k in enumerate(used)}
    fdir = out / "frames"
    if fdir.exists():
        shutil.rmtree(fdir)
    fdir.mkdir(parents=True)
    try:
        font = ImageFont.truetype("consola.ttf", 14)
        small = ImageFont.truetype("consola.ttf", 12)
    except OSError:
        font = small = ImageFont.load_default()
    actual = {k: sorted(tuple(x) for x in v) for k, v in rec["actual"].items()}
    presses_so_far = 0
    changes_so_far = 0
    arena = (60.0, 110.0)
    for k_img, f in enumerate(range(f_lo, f_hi + 1)):
        img = Image.new("RGB", (W, H), BG)
        dr = ImageDraw.Draw(img)
        # lanes
        for k in used:
            x = lane_x[k]
            dr.rectangle([x + 2, STRIP_H + 10, x + lane_w - 2, H - 40], outline=(40, 40, 48))
            dr.text((x + 6, H - 34), LABELS[k], fill=COLORS[k], font=font)
        dr.line([x0, LINE_Y, W - 20, LINE_Y], fill=(230, 230, 230), width=3)
        top = STRIP_H + 10

        def bar(k, p, r, col, outline=None, width=0):
            """The part of a note (press p, release r; r < 0: held at least to -r) still above the line: a held
            key's note shrinks into the line, a released one is gone."""
            x = lane_x[k]
            r_end = r if r >= 0 else -r
            if r_end <= f or p > r_end:
                return
            yb = LINE_Y - (max(p, f) - f) * PX_F
            yt = max(LINE_Y - (r_end - f) * PX_F, top)
            if yb < top:
                return
            if yb - yt < 4:
                yt = yb - 4
            if outline is None:
                dr.rectangle([x + 6, yt, x + lane_w - 6, yb], fill=col)
            else:
                dr.rectangle([x + 6, yt, x + lane_w - 6, yb], outline=outline, width=width)

        for nt in notes:
            k = nt["key"]
            born = nt["steps"][0][0]
            if f < born:
                continue
            col = COLORS[k]
            cancel = nt["cancel"]
            pl = _planned(nt, f)
            if pl is None:
                continue
            if cancel is not None and f >= cancel:
                # a cancelled plan: grey ghost at its last place until that has passed the line
                p, r = _planned(nt, cancel - 1) or pl
                if p >= f - 2:
                    bar(k, p, r, None, outline=GREY, width=2)
                continue
            # a recent change: the old place as a ghost
            for j in range(1, len(nt["steps"])):
                hf = nt["steps"][j][0]
                if hf <= f < hf + GHOST_F:
                    po, ro = nt["steps"][j - 1][1], nt["steps"][j - 1][2]
                    bar(k, po, ro, None, outline=GREY, width=1)
            if nt["exec"] is not None and f >= nt["exec"] and nt["latched"]:
                p, r = nt["latched"]
                r = r if r >= 0 else f + 1
                bar(k, p, r, col)
            else:
                p, r = pl
                bar(k, p, r, tuple(int(c * 0.75) for c in col))
        # the key lights while the game has it down
        for k in used:
            for p, r in actual.get(k, ()):
                if p <= f and (r < 0 or f < r):
                    x = lane_x[k]
                    dr.rectangle([x + 2, LINE_Y - 3, x + lane_w - 2, LINE_Y + 3], fill=COLORS[k])
        # counters
        presses_so_far = sum(1 for v in actual.values() for p, _r in v if f_lo <= p <= f)
        changes_so_far = sum(1 for nt in notes for s in nt["steps"][1:] if f_lo <= s[0] <= f) + \
            sum(1 for nt in notes if nt["cancel"] is not None and f_lo <= nt["cancel"] <= f)
        t = (f - f_lo) / 60.0
        dr.text((20, 8), f"frame {f}   t {t:6.2f} s", fill=(200, 200, 200), font=font)
        dr.text((20, 26), f"presses {presses_so_far}  ({presses_so_far / max(t, 1 / 60):4.1f}/s)   plan changes "
                          f"{changes_so_far}", fill=(200, 200, 200), font=small)
        dr.text((W - 250, 8), "note: first decided -> pressed", fill=(150, 150, 150), font=small)
        dr.text((W - 250, 24), "grey: cancelled / moved plan", fill=GREY, font=small)
        # the arena strip: hero (white) and boss (red) from the recording
        if states is not None:
            s = states.get(f)
            ys = 50
            dr.line([20, STRIP_H - 6, W - 20, STRIP_H - 6], fill=(60, 60, 70), width=1)

            def ax(x):
                return 20 + (x - arena[0]) / (arena[1] - arena[0]) * (W - 40)

            def ay(y):
                return STRIP_H - 6 - y * 4.5 + 2.0 * 4.5

            if s:
                for e in s.get("ents") or ():
                    tk = str(e.get("type_key"))
                    if e.get("hidden") or not (tk == "Bone Beast" or "Bell" in tk):
                        continue
                    pts = [p for c in e.get("colliders") or () if c.get("enabled")
                           for p in np.asarray(c["verts_world"], float).reshape(-1, 2)]
                    if not pts:
                        continue
                    b = np.array(pts)
                    col = (220, 80, 80) if tk == "Bone Beast" else (230, 160, 60)
                    dr.rectangle([ax(b[:, 0].min()), max(ys, ay(b[:, 1].max())), ax(b[:, 0].max()),
                                  max(ys, ay(b[:, 1].min()))], outline=col, width=2)
                h = (s.get("hero") or {}).get("box")
                if h:
                    dr.rectangle([ax(h[0]), max(ys, ay(h[3])), ax(h[2]), ay(h[1])], fill=(235, 235, 235))
        img.save(fdir / f"{k_img:05d}.png", optimize=False, compress_level=1)
    res = {"frames": [f_lo, f_hi], "notes": len(notes), "lanes": used, "png_dir": str(fdir)}
    (out / "notes.json").write_text(json.dumps(notes), "utf-8")
    if video and FFMPEG.exists():
        mp4 = out / "key_track.mp4"
        cmd = [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-framerate", "60", "-i",
               str(fdir / "%05d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(mp4)]
        subprocess.run(cmd, check=True)
        res["video"] = str(mp4)
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--instance", type=int, required=True)
    ap.add_argument("--episode", type=int, default=0, help="the worker's episode number (attempts' 'episode')")
    ap.add_argument("--start-s", type=float, default=0.0, help="seconds after the wake")
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--out", type=Path, default=Path(r"C:\ssbot\sandbox\key_track_sample"))
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--no-arena", action="store_true")
    a = ap.parse_args(argv)
    from ssbot.tools.key_economy import _attempts, _key_records, _record_for
    att = next(x for x in _attempts(a.run) if x.get("instance") == a.instance and x.get("episode") == a.episode)
    rec = _record_for(_key_records(a.run).get(a.instance, []), att)
    if rec is None:
        raise SystemExit("no key plan record for that episode")
    f_lo = int(att["f_wake"] + a.start_s * 60)
    f_hi = int(min(att["f_end"], f_lo + a.seconds * 60 - 1))
    states = None
    if not a.no_arena and att.get("recording") and Path(att["recording"]).exists():
        from ssbot.record.recorder import RecordingReader
        r = RecordingReader(att["recording"])
        states = {s["f"]: s for s in r.states(f_lo, f_hi, keys=("hero", "ents"))}
    a.out.mkdir(parents=True, exist_ok=True)
    res = render(rec, f_lo, f_hi, a.out, states, video=not a.no_video)
    res.update(run=str(a.run), instance=a.instance, episode=a.episode, outcome=att.get("outcome"))
    (a.out / "info.json").write_text(json.dumps(res, indent=1), "utf-8")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
