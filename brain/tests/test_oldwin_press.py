"""Task oldwin stage N: the slam windows by the reflex's path (ssbot.map2.oldwin_press) - off by default, the reflex's
new options default to the old behaviour, the Press's phase confirmations end it when the game does not follow."""
import types

import numpy as np
import pytest

from ssbot.knowledge import kinematics as km
from ssbot.map2 import clapper as cm
from ssbot.map2 import oldwin_press as op
from ssbot.map2 import reflex as rx


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("SSBOT_FORUM_WINDOWS_PRESS", raising=False)
    assert not op.enabled()
    from ssbot.train import forum_planner_policy as fpp
    assert fpp.ForumPlannerPolicy.wpress is None          # a class default: no instance attribute when off


def test_reflex_new_options_default_to_the_old():
    R = rx.Reflex(rx.Table(), W=None)
    assert R.types is None and R.cl_ready is False
    import inspect
    assert inspect.signature(R.check).parameters["bridge"].default == 0
    assert inspect.signature(rx._closed_ds).parameters["k_lo"].default is None
    assert inspect.signature(rx._closed_cl).parameters["k_lo"].default is None


def test_cl_ready_rejects_an_attack_under_way():
    from ssbot.map2 import search as ms
    W = ms.World()
    S = km.initial_state(W.params, 30.0, 3.015 + W.params.foot, ground=True, facing=1)
    S = np.asarray(S, float).reshape(km.K, -1)[:, 0]
    raw = rx.render(rx.Macro("cl", hop=0, wait=0, k=None), 1)
    assert rx._cl_ready(W, S, raw)
    S2 = S.copy()
    S2[km.ATTACKING] = 0.2
    assert not rx._cl_ready(W, S2, raw)


class _Win:
    def __init__(self, obs):
        self._obs = obs
        self.gk = 0
        self.trk = types.SimpleNamespace(mems=lambda: {}, hazards=lambda K: [])

    def obs(self):
        return self._obs


def _raw(f, clip="Idle", mask=0, acc=True, x=30.0, ev=()):
    return {"f": f, "hero": {"anim": {"clip": clip}, "hero_accepting_input": acc, "pos": [x, 4.5]},
            "act": {"mask": mask}, "dt": 1.0 / 60.0, "ev": list(ev)}


def _wp(obs):
    wp = op.WinPress(_Win(obs), inproc=True)
    return wp


def _o(iid=7, st="Slam Antic", j=10, x=35.0):
    return cm.Obs(iid, st, j / 60.0, x, 4.2, 0.0, 0.0, -1, 230, st, j=j)


def _run(wp, frames, clips, masks=None, ev=None):
    out = {}
    S0 = np.zeros(km.K)
    S0[km.PX] = 30.0
    for f in frames:
        r = _raw(f, clips.get(f, "Idle"), (masks or {}).get(f, 0), acc=not clips.get(f, "Idle").startswith("Harpoon"),
                 ev=(ev or {}).get(f, ()))
        wp.feed(r, f)
        out[f] = wp._decide(f, f, r, S0, np.zeros(1, np.int64), None, None, {}, False, False)
    return out


def test_clawline_never_hooked_ends_the_press():
    """CLAWSTRIKE's live failure (stage L H1): a Clawline eaten (no Harpoon clip) must not be taken as control."""
    wp = _wp([_o()])
    P = 101
    cmds = np.array([0, rx.M_CLAW | km.B_RIGHT, rx.M_CLAW | km.B_RIGHT, rx.M_CLAW | km.B_RIGHT], np.int64)
    alts = {"early": (P + 26, -2.0, np.zeros(40, np.int64), P + 36, 0)}
    wp.press = rx.Press("claw_slam0", 7, None, rx.Macro("cl"), (1, 1), 100, cmds, 160, (140, 142), alts, P + 1, 4.0,
                        0.0, d=1, p_abs=P, strike="down")
    wp.pinfo = {"kind": "now", "lane": None, "contact": None, "hooked": False, "ctrl": None, "dx": None}
    _run(wp, range(99, 106), {}, masks={101: rx.M_CLAW, 102: rx.M_CLAW, 103: rx.M_CLAW})
    assert wp.press is None
    assert any(x.get("why") == "no hook" for x in wp.log)


def test_clawline_missed_needle_ends_the_press():
    wp = _wp([_o()])
    P = 101
    cmds = np.array([0, rx.M_CLAW | km.B_RIGHT, rx.M_CLAW | km.B_RIGHT, rx.M_CLAW | km.B_RIGHT], np.int64)
    alts = {"early": (P + 26, -2.0, np.zeros(40, np.int64), P + 36, 0)}
    wp.press = rx.Press("claw_slam0", 7, None, rx.Macro("cl"), (1, 1), 100, cmds, 160, (140, 142), alts, P + 1, 4.0,
                        0.0, d=1, p_abs=P, strike="down")
    wp.pinfo = {"kind": "now", "lane": None, "contact": None, "hooked": False, "ctrl": None, "dx": None}
    clips = {f: "Harpoon Antic" for f in range(102, 110)}
    clips.update({f: "Harpoon Throw" for f in range(110, 118)})
    _run(wp, range(99, 122), clips, masks={101: rx.M_CLAW, 102: rx.M_CLAW, 103: rx.M_CLAW})
    assert wp.press is None
    assert any(x.get("why") == "hook missed" for x in wp.log)


def test_down_slash_without_a_swing_ends_the_press():
    wp = _wp([_o()])
    cmds = np.zeros(30, np.int64)
    cmds[8:10] = km.B_ATTACK | km.B_DOWN
    wp.press = rx.Press("hop_slam0", 7, None, rx.Macro("ds", t=9), (1, 1), 100, cmds, 129, (112, 114), {}, 0, 10.0,
                        0.0, d=1, t_abs=108, strike="down")
    wp.pinfo = {"kind": "now", "lane": None, "contact": None, "hooked": False, "ctrl": None, "dx": None}
    _run(wp, range(99, 112), {})
    assert wp.press is None
    assert any(x.get("why") == "no swing" for x in wp.log)


def test_down_slash_contact_plays_to_the_end():
    wp = _wp([_o()])
    cmds = np.zeros(30, np.int64)
    cmds[8:10] = km.B_ATTACK | km.B_DOWN
    wp.press = rx.Press("hop_slam0", 7, None, rx.Macro("ds", t=9), (1, 1), 100, cmds, 129, (112, 114), {}, 0, 10.0,
                        0.0, d=1, t_abs=108, strike="down")
    wp.pinfo = {"kind": "now", "lane": None, "contact": None, "hooked": False, "ctrl": None, "dx": None}
    clips = {f: "DownSlashAlt" for f in range(108, 116)}
    ev = {111: [{"k": "hit", "d": {"ent": 7, "src": "DownSlash"}}]}
    out = _run(wp, range(99, 125), clips, ev=ev)
    assert wp.press is not None and wp.pinfo["contact"] == 111
    assert out[106] == int(cmds[8])                         # the key for f + 2 = 108


def test_commit_needs_the_bridge_keys_sent():
    wp = _wp([_o(j=10)])
    p = rx.Press("hop_slam0", 7, None, rx.Macro("ds", t=9), (1, 1), 105, np.zeros(20, np.int64), 124, (117, 119), {},
                 0, 10.0, 0.0, d=1, t_abs=113, strike="down")
    snap = {"seq": 1, "f": 100, "fo": 100, "g": 0, "bridge": np.array([km.B_RIGHT, km.B_RIGHT, 0], np.int64),
            "obs": [_o(j=10)], "kind": "check"}
    wp.out = snap
    pred = np.tile(np.array([[30.0, 4.5]]), (8, 1))
    wp.pend = [(102, {"kind": "now", "seq": 1, "press": p, "pred": pred, "lane": None, "ms": 5.0})]
    S0 = np.zeros(km.K)
    S0[km.PX], S0[km.PY] = 30.0, 4.5
    sent = {102: km.B_LEFT, 103: km.B_RIGHT}                # the key sent for 102 is not the bridge's
    wp._decide(102, 102, _raw(102), S0, np.zeros(1, np.int64), None, None, sent, False, False)
    assert wp.commit is None and wp.st["commit_keys"] == 1
