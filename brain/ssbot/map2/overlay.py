"""Map v2 M2: the Clapper model's eye-check layer for the live zone overlay (human_session --overlay --overlay-map2;
forum.md section 93). The person checks by eye, before any live use, that the predicted shapes match what the
Clappers then do (the rule validate-predictions-first).

Every fed game frame goes to the online Tracker (the V4 memory, the history's evidence); every EVERY frames
clapper.predict() runs from the Clappers now with HER PATH HELD STILL (she stays where she is and lands no hit: her
real future is unknown to the overlay, so a hit's Dmg Attack is not in the branches) over HORIZON frames. Drawn at the
overlay's look-ahead k (keys 1-5: now / +6 / +12 / +18 / +36 frames):
  - per Clapper its own outcomes (the joint branches grouped by its choices, their probabilities summed), the top
    TOP each in its own colour: their DAMAGE shapes at +k (the body box, the hammer polygons Slam Collider 1 / 2,
    the lit bombs and the big rune circle), outlines, the union over the timing variants;
  - a label per outcome at the Clapper: its probability, its choices (the move picked, Will Evade, ...) and its
    reveal frame (the earliest frame its first choice shows, + frames from now);
  - its less likely outcomes as one grey outline (their union).
The real colliders stay drawn by the overlay's own red layer (mode range+red / red), so prediction and truth sit side
by side. Nothing here feeds the bot.
"""
from __future__ import annotations

import time

import numpy as np

from ssbot.map2 import clapper as cm

EVERY = 2                    # predict every this many fed game frames
HORIZON = 40                 # frames predicted (the overlay's look-aheads go to +36)
TOP = 4                      # branches drawn in their own colours
# BGR
COLS = ((60, 220, 255), (255, 170, 40), (255, 80, 230), (90, 255, 90))
REST_COL = (170, 170, 170)


class Map2Live:
    """The layer's state inside the overlay process (fed from LiveOverlay._take)."""

    def __init__(self, every: int = EVERY, horizon: int = HORIZON):
        self.K = cm.Know.load()
        self.trk = cm.Tracker()
        self.every, self.T = max(1, every), horizon
        self.n = 0
        self.pred = None
        self.k_pred = 0
        self.stats = {"predicted": 0, "ms": [], "errors": []}

    def reset(self) -> None:
        self.trk = cm.Tracker()
        self.pred = None
        self.n = 0

    def feed(self, s: dict) -> None:
        self.trk.feed(s)
        self.n += 1
        if self.n % self.every:
            return
        obs = self.trk.obs()
        h = s.get("hero") or {}
        if not obs or not h.get("pos"):
            self.pred = None
            return
        x, y = float(h["pos"][0]), float(h["pos"][1])
        box = h.get("box")
        hero = cm.HeroPath.constant(x, y, box=tuple(box[:4]) if box else None, T=self.T)
        t0 = time.perf_counter()
        try:
            self.pred = cm.predict(obs, self.trk.mems(), hero, self.K, T=self.T, max_particles=300,
                                   hazards=self.trk.hazards(self.K))
            self.k_pred = self.trk.k
        except Exception as e:  # noqa: BLE001 - the overlay goes on without this layer's frame
            self.pred = None
            self.stats["errors"].append(repr(e)[:200])
        self.stats["predicted"] += 1
        self.stats["ms"].append((time.perf_counter() - t0) * 1e3)

    def frame(self, k: int) -> dict | None:
        """What to draw at look-ahead k (frames from the prediction's start; the frames fed since are subtracted):
        per Clapper its own outcomes (the joint branches grouped by that Clapper's choices, their probabilities
        summed), the top TOP each in a colour with a label at the Clapper, the rest one grey outline."""
        P = self.pred
        if P is None:
            return None
        since = self.trk.k - self.k_pred
        kk = min(int(k) + since, P.T)
        groups: dict = {}
        for b in P.branches:
            for iid, ch in b.choices.items():
                key = (iid, tuple((c[0], c[1]) for c in ch))
                g = groups.get(key)
                if g is None:
                    groups[key] = g = {"iid": iid, "p": 0.0, "ch": ch, "reveal": None, "shapes": {}}
                g["p"] += b.p
                rv = [c[3] for c in ch if c[3] is not None]
                if rv:
                    g["reveal"] = min(rv) if g["reveal"] is None else min(g["reveal"], min(rv))
                for s_ in b.damage(kk):
                    if s_.iid != iid:
                        continue
                    geo = s_.box if s_.box is not None else s_.circle if s_.circle is not None else \
                        tuple(np.round(s_.poly, 2).ravel())
                    g["shapes"][(s_.name, tuple(np.round(geo, 2)) if s_.box is not None else geo)] = s_
        out = {"k": int(k), "clappers": [], "rest": [], "ms": P.ms, "n": len(P.branches)}
        by_iid: dict = {}
        for g in groups.values():
            by_iid.setdefault(g["iid"], []).append(g)
        for iid, gs in sorted(by_iid.items()):
            gs.sort(key=lambda g: -g["p"])
            t = self.trk.cl.get(iid) or {}
            at = (t.get("x"), (t.get("y") or 0.0) + 1.2) if t.get("x") is not None else None
            rows = []
            for n, g in enumerate(gs):
                if n < TOP:
                    rows.append({"p": g["p"], "label": _label(g["ch"], g["p"], g["reveal"], since), "col": COLS[n],
                                 "shapes": list(g["shapes"].values())})
                else:
                    out["rest"].extend(g["shapes"].values())
            out["clappers"].append({"iid": iid, "at": at, "rows": rows})
        return out


def _label(ch: list, p: float, reveal, since: int) -> str:
    parts = []
    for c in ch:
        if c[0] in ("close", "close_ev", "far", "escape"):
            parts.append(str(c[1]))
        elif c[0] == "will_evade":
            parts.append("evade" if c[1] else "no evade")
        elif c[0] == "hit_idle":
            parts.append("hit in Idle")
    rv = "" if reveal is None else f" rev {reveal - since:+d}f"
    return f"{p:.2f} " + (" / ".join(parts) if parts else "as now") + rv


def draw_map2(img: np.ndarray, data: dict, Hw: np.ndarray, H: int) -> None:
    """Draw the layer (zone_overlay.render calls it with its world -> pixel homography)."""
    import cv2
    from ssbot.tools.zone_overlay import _to_px
    th = max(2, int(round(2.0 * H / 1080)))
    fs = 0.5 * H / 1080.0

    def outline(s: cm.Shape, col, w):
        q = np.round(_to_px(Hw, s.polygon(24))).astype(np.int32)
        cv2.polylines(img, [q], True, (0, 0, 0, 255), w + 2, cv2.LINE_AA)
        cv2.polylines(img, [q], True, (*col, 255), w, cv2.LINE_AA)

    for s in data.get("rest") or ():
        outline(s, REST_COL, max(1, th - 1))
    for cl in data.get("clappers") or ():
        for row in cl["rows"]:
            for s in row["shapes"]:
                outline(s, row["col"], th)
        at = cl.get("at")
        if at is None:
            continue
        p = _to_px(Hw, np.array([at]))[0]
        for n, row in enumerate(cl["rows"]):
            org = (int(p[0]) - int(60 * fs * 2), int(p[1]) - int((len(cl["rows"]) - n) * 22 * fs * 2))
            cv2.putText(img, row["label"], org, cv2.FONT_HERSHEY_SIMPLEX, fs, (0, 0, 0, 255), th + 2, cv2.LINE_AA)
            cv2.putText(img, row["label"], org, cv2.FONT_HERSHEY_SIMPLEX, fs, (*row["col"], 255), max(1, th - 1),
                        cv2.LINE_AA)


def legend(data: dict | None) -> list:
    if data is None:
        return [("MAP2 Clapper model (M2): no Clapper / no prediction yet", None)]
    out = [(f"MAP2 Clapper model (M2) at +{data['k']} f: each Clapper's predicted DAMAGE shapes per outcome (its "
            f"colour; her path held still, no hit by her), label at it = probability / choices / reveal (frames from "
            f"now); grey = its less likely outcomes; {data['n']} joint branches, {data['ms']:.1f} ms", None)]
    for cl in data.get("clappers") or ():
        for row in cl["rows"]:
            out.append((f"Clapper {cl['iid'] % 1000}: {row['label']}", row["col"]))
    return out


__all__ = ["Map2Live", "draw_map2", "legend"]
