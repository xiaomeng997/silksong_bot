"""Task 182 package 1 shadow: the hand-back notice of the slam playbook's link, predicted and logged only (the person 11-12 "做吧",
quote 106; docs/plans/forum_clapper_committed_chain.md 3.1, 5.2, 7.1).

The design has a committed link tell the planner, three frames before it hands back, when and where she will be. For the slam
playbook's link (its catch, then bounce_tail's hammer tail: package 1) the hand-back is the bounce's apex. Nothing reads this yet:
the planner has no node to receive a notice. Per pressed playbook run it records the predicted apex (STATE frame, her x and height)
at the press, at the contact and on every rising tick, the notice (the first tick at most NOTICE_F frames before the latest
predicted apex) and the observed apex with the key owner there, for the episode summary ("slam_notices"), so a live batch shows
how good the prediction is before anything relies on it. SSBOT_FORUM_SLAM_NOTICE (follows SSBOT_FORUM_V2; =0 off).

Constants from 23 real catches of package 0's repeat 50 (its episodes 4, 5, 14, the live hero: s312/b_items/catch_apex_timing.txt):
the apex comes 28 STATE frames after the press (p50; 20-29 when nothing interrupts the rise), about 21 after the contact (the first
DownSpikeBounce frame). The bounce first holds vy 17.4 for a few frames (the STATE reads 17.4 and -10 alternately), then vy falls
1.2 per physics step, with about one STATE in six showing no step (a duplicate). The apex is about 7.0 u above the standing height
(p50; 4.1-8.5). A follow-up's dash or attack can end the rise early: the observed apex keeps the clip and the owner of that frame.

    n = ApexNotice()                       # per episode: n.reset()
    n.observe(f, s, slam_play.run, own)    # every tick after the policy's arbitration (own: this tick's key owner)
    n.rows                                 # one dict per pressed run
"""
from __future__ import annotations

import copy
import math
import os

Y_STAND = 4.568          # her transform y standing on the Forum floor (slam_play.FLOOR_Y)
PRESS_TO_APEX = 28       # STATE frames, press -> apex (p50 of 23 catches)
CONTACT_TO_APEX = 21     # first DownSpikeBounce frame -> apex
APEX_RISE = 7.0          # the apex above the standing height (u, p50)
DECAY = 1.2              # vy lost per physics step in the rise (u/s; gravity 72 u/s^2 at 60 Hz)
GRAV = 72.0
STEP_RATIO = 7.0 / 6.0   # STATE frames per physics step (one duplicate STATE in six)
HOLD_VY = 17.0           # a reading above this is the bounce's hold, not the decaying rise
NOTICE_F = 3             # the notice's lead (design 3.4: asked at B - 3)
CONTACT_WAIT = 20        # no contact this long after the press: the row ends ("no contact")
APEX_WAIT = 60           # no apex this long after the press: the row ends ("no apex")


def _on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip() == "1"


ENABLED = _on("SSBOT_FORUM_SLAM_NOTICE", "1" if _on("SSBOT_FORUM_V2") else "0")


def _hero(s: dict) -> tuple[float, float, float, float, str] | None:
    h = (s or {}).get("hero") or {}
    pos, vel, box = h.get("pos"), h.get("vel") or (0.0, 0.0), h.get("box")
    if not pos or len(pos) < 2:
        return None
    x = 0.5 * (float(box[0]) + float(box[2])) if box and len(box) == 4 else float(pos[0])
    return x, float(pos[1]), float(vel[0]), float(vel[1]), str((h.get("anim") or {}).get("clip") or "")


def rise_frames(vy: float) -> int:
    """STATE frames from a decaying rise reading vy (> 0) to the apex."""
    return max(0, int(math.ceil(vy / DECAY * STEP_RATIO)))


class ApexNotice:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._cur: dict | None = None
        self._seen: set = set()          # (iid, antic entry) of every run a row was opened for: one row per run

    def reset(self) -> None:
        self.rows = []
        self._cur = None
        self._seen = set()

    def _close(self, why: str) -> None:
        if self._cur is not None:
            self._cur["end"] = why
            self._cur["complete"] = True
            self._cur.pop("key", None)
            self.rows.append(self._cur)
        self._cur = None

    def summary(self) -> dict:
        """The episode's rows for the summary, read only (Sol REVIEW397: a row still open when the episode ends - just pressed, or
        noticed and not yet at its apex - is kept, marked incomplete, never given an apex it did not reach). Calling it again
        neither duplicates nor changes anything; reset() starts the next episode empty. opened = completed + incomplete."""
        rows = [dict(r) for r in self.rows]
        if self._cur is not None:
            open_ = copy.deepcopy(self._cur)
            open_.pop("key", None)
            open_["end"] = "incomplete: open when the summary was read (episode end)"
            open_["complete"] = False
            rows.append(open_)
        return {"opened": len(self._seen), "completed": len(self.rows), "incomplete": int(self._cur is not None),
                "rows": rows}

    def _predict(self, cur: dict, f: int, apex_f: int, x: float, y: float, vx: float, tag: str) -> None:
        steps = max(0.0, (apex_f - f) / STEP_RATIO)
        p = [f, apex_f, round(x + vx * steps / 60.0, 3), round(y, 3), tag]
        cur["preds"].append(p)
        if cur["notice"] is None and apex_f - f <= NOTICE_F:
            cur["notice"] = p + [None]          # the owner is filled by observe (this tick's)

    def observe(self, f: int, s: dict, run, owner: str | None) -> None:
        """f: this STATE's frame; s: the STATE; run: slam_play.SlamPlay.run (or None); owner: who sends this tick's mask."""
        hs = _hero(s)
        if hs is None:
            return
        x, y, vx, vy, clip = hs
        cur = self._cur
        if (run is not None and getattr(run, "k_press", None) is not None
                and (run.iid, run.fa) not in self._seen):
            # the press tick of a run (its k_press is set on the tick that sends the press); a row per run, never reopened
            # (the run lives on through its own way out after the row's apex)
            if cur is not None:
                self._close("next run")
            self._seen.add((run.iid, run.fa))
            cur = self._cur = {"key": (run.iid, run.fa), "iid": run.iid, "fa": run.fa, "press_f": f,
                               "k_press": run.k_press, "contact_f": None, "rise_f": None, "preds": [], "notice": None,
                               "apex": None, "end": None}
            self._predict(cur, f, f + PRESS_TO_APEX, x, Y_STAND + APEX_RISE, vx, "press")
        if cur is None:
            return
        if cur["contact_f"] is None:
            if clip.startswith("DownSpikeBounce"):
                cur["contact_f"] = f
                self._predict(cur, f, f + CONTACT_TO_APEX, x, Y_STAND + APEX_RISE, vx, "contact")
            elif f - cur["press_f"] > CONTACT_WAIT:
                self._close("no contact")
                return
        elif cur["rise_f"] is None:
            if 0.0 < vy < HOLD_VY:
                cur["rise_f"] = f
        if cur["rise_f"] is not None and f >= cur["rise_f"]:
            if vy <= 0.0:
                cur["apex"] = [f, round(x, 3), round(y, 3), clip, owner]
                self._close("apex")
                return
            self._predict(cur, f, f + rise_frames(vy), x, y + vy * vy / (2.0 * GRAV), vx, "rise")
        if cur["notice"] is not None and cur["notice"][-1] is None:
            cur["notice"][-1] = owner
        if f - cur["press_f"] > APEX_WAIT:
            self._close("no apex")
