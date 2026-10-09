"""Each enemy's own support clipped to its real reach, the certified table (task "support reach", switch
SSBOT_FORUM_RCLIP; the person 2026-10-09: the purple support of a Choristor 0.7 s into its whip wind-up covered where
they stood 11.65 u in front of it, never hit; forum.md §29.11).

Built by tools.support_reach clip-build from the DEV fight caches only (the fresh fights stay held out for the
recall): per (type, Control state, time-in-state bin) and look-ahead k = 0 .. CLIP_KMAX frames, the box its threat
colliders (dealt > 0 and the multi-hit ones exported with dealt 0: the Choristor's whip) stayed in k frames after a
frame in that state, relative to its transform then, x by its facing then (+ = forward); part "all" (every frame,
knockbacks included) and "nohit" (frames whose enemy was not hit from KB_FREE_F frames before to k frames after: no
knockback; the run time uses it while the tracker saw no hit on the enemy for KB_FREE_F frames).

Lookup: the (state, time bin) box where it has CLIP_MIN_ROWS rows within +-K_SLACK frames, else the state's (every
time bin), else its family's (the union of the family's states), else its type's; the +-K_SLACK frames union (the
templates' +-1 bin). Certified 2-fold by fight: r per (type, state, part, look-ahead band) = the most one fold's boxes
exceed the other fold's run-time boxes (a state the build did not measure: its type's largest). The entry family's,
waiting and death states are never clipped (an entry flies in from off-stage).

Files: knowledge/1.0.30000/enemies/forum/reach_clip.npz (git-ignored, ~10 MB; frozen checkouts copy it with the
*_hitboxes.npz) and reach_clip.json (the report: r, the worst held-out cases, the row counts)."""
import json
from pathlib import Path

import numpy as np

CLIP_KMAX = 126          # frames: the planner's horizon (2 s) + the sighting's age + the slack
CLIP_MIN_ROWS = 120      # rows (within +-K_SLACK) a box needs, else the next coarser level
CLIP_BANDS = (3, 6, 9, 12, 15, 18, 24, 30, 36, 48, 60, 72, 96, CLIP_KMAX)   # the held-out margin per look-ahead band
CLIP_FILE = "reach_clip.npz"
TAU_BIN_S = 0.05         # time-in-state bins (s); the last bin holds everything from (NT - 1) x TAU_BIN_S on
NT = 21
PARTS = ("all", "nohit")
KB_FREE_F = 20           # frames: "nohit" (a knockback after a hit lasts 8-15 frames, forum.md §29.11)
K_SLACK = 1


def tau_bin(t_in_state) -> np.ndarray:
    return np.clip(np.floor(np.asarray(t_in_state, np.float64) / TAU_BIN_S + 1e-9), 0, NT - 1).astype(np.int64)


def empty_boxes(*shape) -> np.ndarray:
    B = np.empty((*shape, 4), np.float64)
    B[..., 0] = B[..., 2] = np.inf
    B[..., 1] = B[..., 3] = -np.inf
    return B


def merge_boxes(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """The union of two box arrays [..., 4] (u0 min, u1 max, v0 min, v1 max)."""
    return np.stack([np.minimum(A[..., 0], B[..., 0]), np.maximum(A[..., 1], B[..., 1]),
                     np.minimum(A[..., 2], B[..., 2]), np.maximum(A[..., 3], B[..., 3])], -1)


def slack(B: np.ndarray, N: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Boxes [K + 1, 4] and rows [K + 1] unioned / summed over k - K_SLACK .. k + K_SLACK."""
    out, n = B.copy(), N.astype(np.int64).copy()
    for d in range(1, K_SLACK + 1):
        out[:-d] = merge_boxes(out[:-d], B[d:])
        out[d:] = merge_boxes(out[d:], B[:-d])
        n[:-d] += N[d:]
        n[d:] += N[:-d]
    return out, n


class ClipTable:
    """B [(type, state)] -> [NT + 1, 2 parts, K + 1, 4] boxes (time bin NT: every time bin) and the row counts, with
    the run-time lookup (module docstring)."""

    def __init__(self, B: dict, N: dict, fam_of: dict, kmax: int = CLIP_KMAX):
        self.kmax = kmax
        self.B, self.N, self.fam_of = B, N, fam_of
        self.fam: dict = {}
        self.typ: dict = {}
        for key, b in B.items():
            n = N[key]
            for acc, k2 in ((self.fam, (key[0], fam_of.get(key))), (self.typ, key[0])):
                r = acc.get(k2)
                acc[k2] = [b[NT].copy(), n[NT].copy()] if r is None else [merge_boxes(r[0], b[NT]), r[1] + n[NT]]
        self._cache: dict = {}

    def boxes(self, tk: str, state: str | None, tbin: int, part: int) -> np.ndarray:
        """[kmax + 1, 4] boxes by the lookup rule (no data at a k at any level: +-inf, no clip)."""
        key = (tk, state, int(tbin), int(part))
        r = self._cache.get(key)
        if r is not None:
            return r
        out = np.empty((self.kmax + 1, 4))
        out[:, 0] = out[:, 2] = -np.inf
        out[:, 1] = out[:, 3] = np.inf
        levels = []
        b = self.B.get((tk, state))
        if b is not None:
            n = self.N[(tk, state)]
            levels += [(b[tbin, part], n[tbin, part]), (b[NT, part], n[NT, part])]
        fam = self.fam_of.get((tk, state))
        if fam is not None and (tk, fam) in self.fam:
            f = self.fam[(tk, fam)]
            levels.append((f[0][part], f[1][part]))
        if tk in self.typ:
            t = self.typ[tk]
            levels.append((t[0][part], t[1][part]))
        done = np.zeros(self.kmax + 1, bool)
        for i, (bb, nn) in enumerate(levels):
            bs, ns = slack(bb, nn)
            use = ~done & ((ns >= CLIP_MIN_ROWS) | (i == len(levels) - 1)) & np.isfinite(bs[:, 0])
            out[use] = bs[use]
            done |= use
        self._cache[key] = out
        return out


def unclipped_states() -> frozenset:
    """{(type, state)} never clipped: the entry family's states, the waiting states and the death states."""
    from ssbot.combat.enemy_tables import FORUM_DIR
    from ssbot.core.forum import FORUM_TYPES
    out = set()
    for tk, sp in FORUM_TYPES.items():
        out |= {(tk, s) for s in sp.waiting + sp.death_states}
        p = FORUM_DIR / f"{sp.enemy}.json"
        if p.exists():
            a = json.loads(p.read_text("utf-8"))["attacks"].get(sp.entry_family) or {}
            out |= {(tk, s) for s in a.get("states") or ()}
    return frozenset(out)


def save_clip(path: Path, B: dict, N: dict, fam_of: dict, r: dict, kmax: int = CLIP_KMAX) -> None:
    keys = sorted(B, key=lambda k: (k[0], str(k[1])))
    np.savez_compressed(
        path, keys=np.array([f"{tk}|{st}" for tk, st in keys]),
        fam=np.array([fam_of.get(k) or "" for k in keys]),
        B=np.stack([B[k] for k in keys]).astype(np.float32), N=np.stack([N[k] for k in keys]).astype(np.int32),
        r_keys=np.array(["|".join(map(str, k)) for k in sorted(r, key=str)]),
        r_val=np.array([r[k] for k in sorted(r, key=str)], np.float32), kmax=np.array(kmax))


def load_clip(path: Path) -> tuple[ClipTable, dict]:
    """(ClipTable, {(type, state | "*", time bin | NT, part, band): r}) of a clip-build npz."""
    with np.load(path, allow_pickle=False) as z:
        kmax = int(z["kmax"])
        B, N, fam_of = {}, {}, {}
        Ball, Nall = z["B"].astype(np.float64), z["N"].astype(np.int64)      # read once (each z[...] decompresses)
        for i, (key, fam) in enumerate(zip(z["keys"].tolist(), z["fam"].tolist())):
            tk, st = key.split("|", 1)
            B[(tk, st)] = Ball[i]
            N[(tk, st)] = Nall[i]
            if fam:
                fam_of[(tk, st)] = fam
        r = {}
        for key, v in zip(z["r_keys"].tolist(), z["r_val"].tolist()):
            tk, st, tb, part, band = key.split("|")
            r[(tk, st, int(tb), int(part), int(band))] = float(v)
    return ClipTable(B, N, fam_of, kmax), r


class ReachClip:
    """The run-time clip (multi_forecast, SSBOT_FORUM_RCLIP): per enemy the hero-centre world boxes by look-ahead."""

    def __init__(self, table: ClipTable, r: dict, half: tuple[float, float]):
        self.table = table
        self.half = half
        self.kmax = table.kmax
        self.r = r
        self.skip = unclipped_states()
        self._r: dict = {}

    @classmethod
    def load(cls, path: Path, half: tuple[float, float]) -> "ReachClip | None":
        if not Path(path).exists():
            return None
        t, r = load_clip(path)
        return cls(t, r, half)

    def r_of(self, tk: str, state: str | None, tbin: int, part: int) -> np.ndarray:
        """[kmax + 1] the held-out margin by look-ahead: the (state, time bin)'s (2-fold, per band) where the build
        measured it and the table has that bin's own box, else the state's (its largest over the bins), else the
        type's largest ("*")."""
        key = (tk, state, tbin, part)
        out = self._r.get(key)
        if out is None:
            own = self.table.N.get((tk, state))
            own = own is not None and int(own[tbin, part].sum()) > 0
            out = np.zeros(self.kmax + 1)
            lo = 0
            for band in CLIP_BANDS:
                v = self.r.get((tk, state, tbin, part, band)) if own else None
                if v is None:
                    v = self.r.get((tk, state, NT, part, band))
                out[lo:band + 1] = v if v is not None else self.r.get((tk, "*", NT, part, band), 0.0)
                lo = band + 1
            self._r[key] = out
        return out

    def world(self, tk: str, state: str | None, t_in_state: float, part: int, pos, facing: int,
              age_f: int) -> np.ndarray:
        """[kmax + 1, 4] (x0, y0, x1, y1) hero-centre boxes at look-ahead k = 0 .. kmax from now for an enemy seen
        age_f frames ago at pos (its transform) facing +1 / -1, t_in_state s into that state then: the reach box at
        k + age_f, grown by r and the hero half extents; +-inf where there is none (no clip)."""
        out = np.empty((self.kmax + 1, 4))
        out[:, 0] = out[:, 1] = -np.inf
        out[:, 2] = out[:, 3] = np.inf
        n = self.kmax + 1 - age_f
        if n <= 0 or (tk, state) in self.skip:
            return out
        tb = int(tau_bin(t_in_state))
        b = self.table.boxes(tk, state, tb, part)[age_f:age_f + n]
        rr = self.r_of(tk, state, tb, part)[age_f:age_f + n]
        hx, hy = self.half
        if facing >= 0:
            x0, x1 = pos[0] + b[:, 0], pos[0] + b[:, 1]
        else:
            x0, x1 = pos[0] - b[:, 1], pos[0] - b[:, 0]
        out[:n, 0] = x0 - rr - hx
        out[:n, 2] = x1 + rr + hx
        out[:n, 1] = pos[1] + b[:, 2] - rr - hy
        out[:n, 3] = pos[1] + b[:, 3] + rr + hy
        bad = ~(np.isfinite(b[:, 0]) & np.isfinite(b[:, 1]) & np.isfinite(b[:, 2]) & np.isfinite(b[:, 3]))
        out[:n][bad] = (-np.inf, -np.inf, np.inf, np.inf)
        return out
