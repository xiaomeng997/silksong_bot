"""The observed history an external entry may use (plan 6.21: current visible state + traceable history), as a
read-only view cut at the entry tick: the STATEs and game clock of the ticks the chain runner was stepped on, her
contact / input there, and the masks sent (successful native transport receipts only; missing targets stay unknown)
up to the mask frame in flight (cut + 1). Nothing of any script's internal state (its k_press, control return,
bounce flag, side) is in here; those are derived from these observations by slam_prims_v01's h_* primitives.

    H = HistView(ticks, sent, cut)        # ticks: [(f, s, t_game, ground, accepting)] stepped ticks, in order
"""
from __future__ import annotations

from ssbot.combat import slam_play as SP

SEND = SP.SEND_AHEAD


class HistView:
    def __init__(self, ticks: list, sent: dict, cut: int, lag: int = 0):
        self.cut = cut
        self.lag = lag
        self.rows = [r for r in ticks if r[0] <= cut]
        self.by_f = {r[0]: r for r in self.rows}
        self.sent = {F: m for F, m in sent.items() if F <= cut + 1}
        self.F_sorted = sorted(self.sent)

    # -- per tick --

    def state(self, f: int) -> dict:
        return self.by_f[f][1]

    def t_game(self, f: int) -> float:
        return self.by_f[f][2]

    def ground(self, f: int) -> bool:
        return self.by_f[f][3]

    def accepting(self, f: int) -> bool:
        return self.by_f[f][4]

    # -- the slam --

    @staticmethod
    def _ctl(s: dict, iid):
        e = next((o for o in SP.clappers(s) if o.get("iid") == iid), None)
        return e, SP.control(e)

    def antic(self, iid, antic_state: str, slam_states: tuple) -> dict | None:
        """The target's latest slam: the first stepped tick of its latest antic stretch (the clock origin a stepped
        observer takes: ta = t_game - state time there), its facing then. The slam may be over by now (the way out
        runs on to the landing); the links' checks bound it (k_end, landed)."""
        rows = self.rows
        j = len(rows) - 1
        while j >= 0:
            e, (st, tin) = self._ctl(rows[j][1], iid)
            if e is None:
                return None
            if st == antic_state:
                break
            j -= 1
        if j < 0:
            return None
        while j > 0:
            e, (st, _) = self._ctl(rows[j - 1][1], iid)
            if e is None or st != antic_state:
                break
            j -= 1
        f0, s0, t0 = rows[j][0], rows[j][1], rows[j][2]
        e, (st, tin) = self._ctl(s0, iid)
        return {"iid": iid, "first_tick": f0, "ta": t0 - tin, "fa": int(f0 - round(tin * 60.0)),
                "face": 1 if e.get("flipX") else -1}

    def complete_antic_receipts(self, an: dict | None) -> bool:
        """At most one state-clock frame of entry skew, never a missing send.

        fa is measured from the observed FSM time, not a fabricated earlier
        STATE. Unknown edge predecessors are still rejected by edges().
        """
        return (an is not None and 0 <= an["first_tick"] - an["fa"] <= 1
                and all(F in self.sent for F in range(an["fa"] + 1, self.cut + 2)))

    def k_of_tick(self, f: int, an: dict) -> int:
        return int(round((self.t_game(f) - an["ta"]) * 60.0)) + SEND + self.lag

    def k_of(self, F: int, an: dict) -> int | None:
        f = F - SEND
        return self.k_of_tick(f, an) if f in self.by_f else None

    def ticks_since(self, an: dict):
        return [r for r in self.rows if r[0] >= an["first_tick"]]

    def slam0(self, an: dict):
        """(s0 tick, ks0): the first stepped tick of this slam seeing Slam 0."""
        for f, s, t, g, a in self.ticks_since(an):
            e, (st, tin) = self._ctl(s, an["iid"])
            if st == "Slam 0":
                return f, int(round(((t - tin) - an["ta"]) * 60.0))
        return None

    # -- keys --

    def _range(self, an: dict, after_F=None, before_F=None):
        lo = an["first_tick"] + SEND
        for F in self.F_sorted:
            if F < lo or (after_F is not None and F <= after_F) or (before_F is not None and F >= before_F):
                continue
            yield F

    def edges(self, bits: int, an: dict, after_F=None, before_F=None, without: int = 0):
        prev = None
        prev_F = None
        out = []
        for F in self.F_sorted:
            if F < an["first_tick"] + SEND:
                prev = self.sent[F]
                prev_F = F
                continue
            m = self.sent[F]
            on = (m & bits) == bits and not (m & without)
            was = prev is not None and prev_F == F - 1 and (prev & bits) == bits and not (prev & without)
            if on and prev_F == F - 1 and not was and (after_F is None or F > after_F) and (before_F is None or F < before_F):
                out.append(F)
            prev = m
            prev_F = F
        return out

    def key_edge(self, bits: int, an: dict, after_F=None, without: int = 0, before_F=None):
        e = self.edges(bits, an, after_F=after_F, before_F=before_F, without=without)
        return (e[0],) if e else None

    def first_dir(self, an: dict, after_F, before_F=None, exclude_dir=None):
        for F in self._range(an, after_F=after_F, before_F=before_F):
            m = self.sent[F]
            l_, r_ = bool(m & SP.M_L), bool(m & SP.M_R)
            if l_ != r_:
                d = 1 if r_ else -1
                if exclude_dir is not None and d == exclude_dir:
                    continue
                return F, d
        return None

    def F_of_k(self, k: int, an: dict):
        for F in self._range(an):
            if self.k_of(F, an) == k:
                return F
        return None

    # -- observed events --

    def first_tick(self, an: dict, after_k, cond: str, arg, iid, before_f=None):
        for f, s, t, g, a in self.ticks_since(an):
            if before_f is not None and f >= before_f:
                break
            if after_k is not None and self.k_of_tick(f, an) <= after_k:
                continue
            h = s.get("hero") or {}
            if cond == "vy_gt" and float((h.get("vel") or [0, 0])[1]) > arg:
                return f
            if cond == "s_hit":
                from types import SimpleNamespace
                if SP.SlamPlay._cs_s_hit(s, SimpleNamespace(iid=iid)):
                    return f
            if cond == "ground" and g:
                return f
            if cond == "ctrl" and a and not str((h.get("anim") or {}).get("clip") or "").startswith("Harpoon") \
                    and f + SEND > arg + 12:
                return f
        return None

    def any_tick(self, an: dict, before_f: int, pred) -> bool:
        for f, s, t, g, a in self.ticks_since(an):
            if f >= before_f:
                break
            if pred(s, g, a):
                return True
        return False

    def sent_since(self, fa: int, f: int):
        return [(F, self.sent[F]) for F in self.F_sorted if F <= f + 1 and F >= fa]
