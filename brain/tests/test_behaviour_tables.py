"""Behaviour tables (ssbot.knowledge.behaviour_tables) on a scripted synthetic fight and on a real fixture cut from
the trial combat run, plus the build CLI report and the timeline viewer.

Fixture tests/fixtures/bellbeast_trial_windows.msgpack.zst (82 KB): two windows of the trial recording
C:/ssbot/data/runs/m2/20261001_121446_BellBeast_data/rec/2026-10-01/TRAIN/i0_000 (episode 0), frames 45780-46660
(Charge from Set L, Bell Burst, Leap from Set R; phase P1) and 47820-49120 (the Rage pattern Ptn L, then two P2 Bell
Bursts, the second cut by the window), STATEs trimmed to the fields the scanner reads (f, dt, hero pos / box /
health, ents without anim / vel / fsm times, fsm, damage, damage_blocked and hit events). Regenerate with
`python tests/test_behaviour_tables.py <recording dir>`.
"""
import json
import math
import sys
from pathlib import Path

import msgpack
import numpy as np
import pytest
import zstandard

from ssbot.knowledge import behaviour_tables as bt
from ssbot.knowledge import hitbox_tables as hb

FIXTURE = Path(__file__).parent / "fixtures" / "bellbeast_trial_windows.msgpack.zst"
FIXTURE_WINDOWS = [(45780, 46660), (47820, 49120)]
KNOWLEDGE_NPZ = Path(__file__).resolve().parents[2] / "knowledge" / "1.0.30000" / "enemies" / "BellBeast_hitboxes.npz"
DT = 1.0 / 60.0
DMG = {"dealt": 2, "eff": 2, "hazard_type": 1, "flags": 0, "parry": 4, "parryable": False, "can_cause_damage": True}
HX, HY = hb.HERO_HALF_U

SPEC = bt.BehaviourSpec(
    enemy="Synth", scene="S", boss_type="Test Boss", control_fsm="Control", hp=100, dormant=("Dormant",),
    death_states=("Dead",), attack_starts={"Antic A": "A", "Antic B": "B"},
    decision_states=("Idle", "Choose", "Set L", "Set R"), dir_states={"Set L": 1, "Set R": -1}, directed=("A",),
    phase_marks={}, phases={"P1": "all"}, initial_phase="P1", world_fixed=("Rock",), arena_x=(0.0, 30.0))


# ---- synthetic fight ---------------------------------------------------------------------------------------

def _box(x0, y0, x1, y1):
    return [x0, y0, x1, y0, x1, y1, x0, y1]


def _col(verts, enabled=True, kind="box", cooldown=False):
    return {"kind": kind, "verts_world": list(verts), "enabled": enabled, "layer": 11,
            "damage": dict(DMG, can_cause_damage=not cooldown)}


def _ent(iid, tk, x, y, cols, state=None, src=2, category="hazard", flip=False):
    return {"iid": iid, "type_key": tk, "category": category, "src": src, "pos": [x, y, 0.0], "hp": None,
            "flipX": flip, "fsms": [] if state is None else [{"name": "Control", "state": state}], "colliders": cols}


class Synth:
    """A scripted boss: Idle (underground, 30 frames) -> one-frame chain Choose -> [Set L|R ->] Antic A|B ->
    A: Antic A 20 (hidden), Dash 30 (box 2 x 2 u moving 0.2 u/frame toward the far side), Recover 10;
    B: Antic B 15 (hidden), Throw 10 (arms the world-fixed Rock for 40 frames and a Shard projectile for 25),
    Recover B 10. Always-on Spikes are ambient; a Saw is armed when the scan starts, disarms after 10 frames and is
    armed again by the first Throw. One hit per Dash (frame 10) followed by 2 i-frame-blocked frames, one Rock hit in
    B's tail; the hero box is put on the source at every contact. hole: the first Dash is exported without
    colliders for its first 5 frames and hits on frame 2. ghost: an extra hit from the boss during a Recover."""

    def __init__(self, hole: bool = False, ghost: bool = False):
        self.f = 1000
        self.out = []
        self.ev = []
        self.ctl = None
        self.entered = None
        self.boss = None
        self.hero = (12.0, 1.04)
        self.box_at = None
        self.rock_left = 0
        self.rock_j = 0
        self.shard_left = 0
        self.shard_x = 0.0
        self.saw_left = 10
        self.saw_rearm = True
        self.hole, self.ghost = hole, ghost
        self.n_a = 0

    def to(self, state):
        tip = None if self.ctl is None else (self.f - self.entered) * DT
        self.ev.append({"k": "fsm", "f": self.f, "d": {"iid": 1, "ent": 1, "obj": "Test Boss", "fsm": "Control",
                                                        "from": self.ctl, "to": state, "t_in_prev": tip,
                                                        "rt_in_prev": tip}})
        self.ctl, self.entered = state, self.f

    def hit(self, source, at):
        self.ev.append({"k": "damage", "f": self.f, "d": {"source": source, "amount": 2, "hazard": "ENEMY"}})
        self.box_at = at

    def blocked(self, source, first_f, last_f):
        self.ev.append({"k": "damage_blocked", "f": self.f, "d": {"source": source, "hazard": "ENEMY",
                                                                   "why": "iframes", "first_f": first_f,
                                                                   "last_f": last_f}})

    def frame(self, dt=DT):
        ents = [_ent(70, "Spikes", 30.5, 0.0, [_col(_box(30, 0, 31, 1))])]
        saw_on = self.saw_left > 0
        ents.append(_ent(80, "Saw", 2.0, 5.0, [_col(_box(1.5, 4.5, 2.5, 5.5), enabled=saw_on)],
                         "Spin" if saw_on else "Dormant"))
        self.saw_left -= 1
        if self.boss is not None:
            ents.append(self.boss)
        if self.rock_left > 0:
            y = 8.0 - 0.1 * self.rock_j
            ents.append(_ent(50, "Rock", 10.0, y, [_col(_box(9.5, y - 0.5, 10.5, y + 0.5))], "Fall"))
            self.rock_left -= 1
            self.rock_j += 1
        else:
            ents.append(_ent(50, "Rock", 10.0, 8.0, [_col(_box(9.5, 7.5, 10.5, 8.5), enabled=False)], "Dormant"))
        if self.shard_left > 0:
            x = self.shard_x
            ents.append(_ent(60, "Shard", x, 1.0, [_col(_box(x - 0.25, 0.75, x + 0.25, 1.25))], "Fly", src=2 | 32))
            self.shard_x += 0.3
            self.shard_left -= 1
        cx, cy = self.box_at or self.hero
        self.out.append({"f": self.f, "dt": dt, "hero": {"pos": [*self.hero, 0.0], "box": [cx - HX, cy - HY, cx + HX,
                                                                                          cy + HY], "health": 5},
                         "ents": ents, "ev": self.ev})
        self.ev = []
        self.box_at = None
        self.f += 1

    def idle(self, n, freeze_at=None):
        self.boss = None
        for j in range(n):
            self.frame(0.0 if j == freeze_at else DT)

    def attack_a(self, side, die=False):
        m = 1 if side == "Set L" else -1
        x0 = 5.0 if m == 1 else 25.0
        hole = self.hole and self.n_a == 0
        self.n_a += 1
        self.idle(20)
        for j in range(30):
            if j == 0:
                self.to("Dash")
            x = x0 + m * 0.2 * j
            cols = [] if hole and j < 5 else [_col(_box(x - 1, 0, x + 1, 2), cooldown=j == 11)]
            self.boss = _ent(1, "Test Boss", x, 1.0, cols, "Dash", src=3, category="enemy", flip=m < 0)
            if die and j == 5:
                self.to("Dead")
                self.hit("Test Boss/Body", (x, 1.0))  # same frame as the kill, after the transition
                self.idle(10)
                return
            if j == 10 or (hole and j == 2):
                self.hit("Boss Scene/Test Boss", (x, 1.0))
            elif j in (11, 12):
                self.box_at = (x, 1.0)
            elif j == 13:
                self.blocked("Boss Scene/Test Boss", self.f - 2, self.f - 1)
            self.frame()
        self.to("Recover")
        for j in range(10):
            self.boss = _ent(1, "Test Boss", self.boss["pos"][0], 1.0, [_col(_box(0, 0, 1, 1), enabled=False)],
                             "Recover", src=3, category="enemy")
            if self.ghost and j == 5:
                self.hit("Test Boss/Body", (0.5, 0.5))
            self.frame()

    def attack_b(self):
        self.idle(15)
        self.to("Throw")
        self.rock_left, self.rock_j = 40, 0
        self.shard_left, self.shard_x = 25, 16.0
        if self.saw_rearm:
            self.saw_left, self.saw_rearm = 5, False
        for _ in range(10):
            self.boss = _ent(1, "Test Boss", 15.0, 1.0, [], "Throw", src=1, category="enemy")
            self.frame()
        self.to("Recover B")
        for _ in range(10):
            self.frame()

    def fight(self, plan):
        self.to("Dormant")
        self.idle(5)
        self.to("Idle")
        for k, (fam, side) in enumerate(plan):
            self.hero = ((3.0, 12.0, 20.0, 28.0)[k % 4], 1.04)
            self.idle(30, freeze_at=7 if k == 0 else None)
            self.to("Choose")
            if side:
                self.to(side)
            self.to("Antic A" if fam == "A" else "Antic B")
            if fam == "A":
                self.attack_a(side, die=k == len(plan) - 1)
            else:
                self.attack_b()
            if self.ctl != "Dead":
                self.to("Idle")
                if fam == "B":
                    for j in range(25):  # the Rock is still falling: hit the hero 10 frames into Idle
                        if j == 10:
                            self.hit("Boss Scene/Rock", (10.0, 8.0 - 0.1 * self.rock_j))
                        self.frame()
        return self.out


PLAN = [("A", "Set L"), ("B", None), ("A", "Set R"), ("B", None), ("A", "Set L"), ("A", "Set R"), ("B", None),
        ("A", "Set L")]


@pytest.fixture(scope="module")
def synth():
    b = bt.BehaviourBuilder(SPEC)
    info = b.scan_states(Synth().fight(PLAN), "synth")
    return b, info


def _support_covers(built: bt.Built, contacts: list, frames=("anchor", "world_all", "self")) -> dict:
    """The planner's query of every contact: the hero collider centres of frames f-1 and f, each at its own frame's
    time (tk = box_dt: -(T_f - T_f-1), 0), against the planner templates (support + hurtbox) of its family (or,
    "self", of its hazard entity placed where it armed); a contact is caught when either frame is flagged.
    {frame: number of contacts not caught}; contacts with a boss source count as caught for "self"."""
    keys = {k for k in built.support if k.count("/") == 2 or k.startswith(f"support/{bt.SELF}/")}
    plan = hb.planner_templates({k: built.support[k] for k in keys})
    q = hb.SupportQuery(plan)
    missed = {f: 0 for f in frames}
    for c in contacts:
        fam = c.inst.family
        assert len(c.box_dt) == len(c.boxes) and c.box_dt[-1] == 0.0
        for frame in frames:
            q.clear()
            if frame == "anchor":
                if c.inst.anchor is not None and f"support/{fam}/anchor" in plan:
                    q.place(f"support/{fam}/anchor", c.t, c.inst.anchor, c.inst.mirror or 1)
                if f"support/{fam}/world" in plan:
                    q.place(f"support/{fam}/world", c.t)
            elif frame == "self":
                if c.arm is None:
                    continue
                q.place(f"support/{bt.SELF}/{c.tk}/self", c.T - c.arm[0], c.arm[1], 1)
            else:
                q.place(f"support/{fam}/world_all", c.t)
            xs = np.array([[(b[0] + b[2]) / 2 for b in c.boxes]])
            ys = np.array([[(b[1] + b[3]) / 2 for b in c.boxes]])
            hit = q.query(xs, ys, np.array(c.box_dt, np.float64))
            missed[frame] += not hit.any()
    return missed


def test_synthetic_segmentation(synth):
    b, info = synth
    assert info["died"] and info["instances"] == 8
    fams = [i.family for i in b.instances]
    assert sorted(fams) == ["A"] * 5 + ["B"] * 3
    a = [i for i in b.instances if i.family == "A"]
    assert [i.dir for i in a] == ["Set L", "Set R", "Set L", "Set R", "Set L"]
    assert [i.mirror for i in a] == [1, -1, 1, -1, 1]
    assert [i.anchor[0] for i in a] == [5.0, 25.0, 5.0, 25.0, 5.0]
    assert all(abs(i.anchor_t - 20 * DT) < 1e-9 for i in a)
    assert [i.end for i in a] == ["rest"] * 4 + ["death"]
    assert all(abs(i.t_end - 60 * DT) < 1e-9 for i in a[:4])
    bb = [i for i in b.instances if i.family == "B"]
    assert all(i.mirror == 1 and i.anchor == (15.0, 1.0) and i.dir is None for i in bb)
    assert all(abs(i.t_end - 35 * DT) < 1e-9 for i in bb)
    assert all(abs(i.t_tail - 54 * DT) < 1e-9 for i in bb)  # the Rock (40 frames from 15) outlives the attack
    assert b.counters == {}  # the always-on Spikes are ambient, nothing unattributed
    assert b.ambient_frames == {"Spikes": len(Synth().fight(PLAN)), "Saw": 10}


def test_synthetic_graph_dwell_and_decisions(synth):
    b, _ = synth
    t = b.tables()
    g = t["graph"]
    assert g["from"]["Idle"]["successors"] == {"Choose": 8}
    assert g["from"]["Choose"]["successors"] == {"Set L": 3, "Set R": 2, "Antic B": 3}
    assert g["from"]["Choose"]["by_phase"]["P1"]["n"] == 8
    p, p_unseen = bt.dirichlet({"Set L": 3, "Set R": 2, "Antic B": 3})
    assert abs(p["Set L"] - 3.5 / 10.0) < 1e-12 and abs(p_unseen - 0.05) < 1e-12
    assert abs(sum(p.values()) + p_unseen - 1.0) < 1e-12
    edge = next(e for e in g["edges"] if e["from"] == "Choose" and e["to"] == "Set L")
    assert edge["p"] == round(3.5 / 10.0, 4) and edge["low_n"]
    assert any(e.get("kill") and e["from"] == "Dash" for e in g["edges"])
    assert g["from"]["Dash"]["successors"] == {"Recover": 4} and g["from"]["Dash"]["worst_case"]
    d = t["dwell_s"]
    assert d["Antic A"]["n"] == 5 and abs(d["Antic A"]["p50"] - 20 * DT) < 1e-4
    assert d["Dash"]["n"] == 4  # the exit into Dead is not a dwell
    assert d["Choose"]["instant"] and not d["Antic A"]["instant"]
    assert d["Antic A"]["max_abs_dwell_minus_state_time"] < 1e-6
    idle = [x.dwell_s for x in b.dwells if x.state == "Idle"]
    assert min(idle) == pytest.approx(29 * DT)  # the frame with dt = 0 (hit-stop) adds no game time
    dec = t["decisions"]["Choose"]
    assert dec["n"] == 8 and dec["probability_only"] and dec["conditioners"] == []
    assert "8 of 8" in dec["untestable"]["hero_x"] and "0 of 8" in dec["untestable"]["dist_visible"]
    assert dec["table"]["all"]["n"] == 8
    assert not t["coverage"]["fsm_edges_extracted"] and t["coverage"]["logged_edges"] == len(g["edges"])


def test_synthetic_templates_follow_the_mirrored_dash(synth):
    b, _ = synth
    tpls = b.templates()
    a = tpls["A/anchor"]
    assert a.n_instances == 5
    j = np.arange(30)
    t = 20 * DT + j * DT
    # Set L and Set R dashes coincide in the anchor frame: the box centre runs along +x' at 0.2 u/frame
    assert a.contains(t, 0.2 * j, 0.0).all()
    assert not a.contains(t, 0.2 * j + 3.0, 0.0).any()
    assert not a.contains(t, -0.2 * j - 3.0, 0.0).any()
    assert tpls["A/Dash/anchor"].contains(j * DT, 0.2 * j, 0.5).all()
    wa = tpls["A/world_all"]  # world frame, both sides: usable before the side is known
    assert wa.frame == "world" and wa.contains(t, 5.0 + 0.2 * j, 1.0).all()
    assert wa.contains(t, 25.0 - 0.2 * j, 1.0).all()
    rock = tpls["B/world"]
    assert rock.frame == "world"
    k = np.arange(40)
    assert rock.contains(15 * DT + k * DT, 10.0, 8.0 - 0.1 * k).all()
    tail = tpls["B/_tail/world"]  # the Rock after B ended (t from the end): 20 frames of the 40
    assert tail.contains(np.arange(1, 20) * DT, 10.0, 8.0 - 0.1 * (np.arange(1, 20) + 20)).all()
    shard = tpls["B/anchor"]
    assert shard.contains(15 * DT + np.arange(25) * DT, 1.0 + 0.3 * np.arange(25), 0.0).all()
    assert "Spikes" not in json.dumps(b.tables()["attacks"])
    # the Saw was ambient only until it disarmed: its re-arming by the first Throw belongs to B
    assert tpls["B/world_all"].contains(15 * DT, 2.0, 5.0)
    assert tpls["_ambient/world"].contains(0.0, 2.0, 5.0) and tpls["_ambient/world"].contains(0.0, 30.5, 0.5)


def test_synthetic_hits_entities_and_cooldown_frames(synth):
    b, _ = synth
    t = b.tables()
    assert t["attacks"]["A"]["hits_taken"] == {"n": 5, "by_source": {"Boss Scene/Test Boss": 4, "Test Boss/Body": 1},
                                               "by_state": {"Dash": 5}}
    assert t["attacks"]["B"]["hits_taken"]["by_state"] == {bt.TAIL: 3}
    rock = t["entities"]["Rock"]
    assert rock["armed"] == 3 and rock["armed_by_family"] == {"B": 3} and rock["armed_at_boss_state"] == {"Throw": 3}
    assert rock["by_state"]["Fall"]["enabled"] == 1.0 and "enabled" not in rock["by_state"]["Dormant"]
    assert rock["world_frame"] and rock["lifetime_s"]["p50"] == pytest.approx(39 * DT, abs=1e-4)
    shard = t["entities"]["Shard"]
    assert shard["end"] == {"left view": 3} and shard["src"] == ["damage_hero", "projectile"]
    assert t["entities"]["Saw"]["armed_by_family"] == {"B": 1}
    assert t["entities"]["Test Boss"]["cooldown_frames"] == 4  # can_cause_damage false, still in the templates
    hb_rows = {(h["state"], h["source"]): h for h in t["attacks"]["A"]["hitboxes"]}
    dash = hb_rows[("Dash", "Test Boss:box")]
    assert dash["n"] == 5 and dash["dmg"] == [2]
    assert dash["t0"] == pytest.approx(19 * DT, abs=1e-4) and dash["t1"] == pytest.approx(50 * DT, abs=1e-4)  # +-1
    assert dash["type"] == ["ENEMY"] and dash["parry"] == ["counter"] and not dash["parryable"]
    assert t["attacks"]["A"]["coverage"] == {"n": 5, "target": 200, "ok": False}
    assert t["attacks"]["A"]["anchor"]["by_dir"]["Set L"]["support"] == {"x": [5.0, 5.0], "y": [1.0, 1.0]}


def test_synthetic_contacts_are_validated_and_covered(synth):
    b, _ = synth
    built = b.build()
    v = built.tables["coverage"]["validation"]
    # 5 dash hits (one on the kill frame), 4 x 2 blocked frames, 3 Rock hits after B ended
    assert v["ok"] and v["contacts"] == 16 and v["damage"] == 8 and v["blocked_frames"] == 8
    assert all(c.exported and not c.hole and c.inst is not None for c in b.contacts)
    assert {c.state for c in b.contacts} == {"Dash", bt.TAIL}
    assert all(d == 0.0 for c in b.contacts for d in c.res.values())
    r = built.tables["attacks"]["A"]["residual_u"]
    assert r["sets"]["anchor"]["n"] == 13 and r["sets"]["anchor"]["max"] == 0.0
    assert _support_covers(built, b.contacts) == {"anchor": 0, "world_all": 0, "self": 0}
    sup = built.support["support/A/anchor"]
    assert sup.t_pad == 1 and sup.contains(19 * DT, 0.0, 0.0, tol_bins=0)  # the +-1 bin is baked in


def test_export_hole_is_flagged_and_left_out_of_statistics():
    b = bt.BehaviourBuilder(SPEC)
    b.scan_states(Synth(hole=True).fight(PLAN), "synth-hole")
    t = b.tables()
    assert t["coverage"]["export_holes"]["frames"] == {"Test Boss": {"Dash": 5}}
    assert t["coverage"]["export_holes"]["instances"] == 1 and t["attacks"]["A"]["export_holes"]["instances"] == 1
    v = t["coverage"]["validation"]
    assert v["ok"] and v["no_exported_collider_explained_by_export_hole"] == {
        "n": 1, "damage": 1, "by_source": {"Boss Scene/Test Boss": 1}}
    assert t["attacks"]["A"]["ttd_s"]["Dash"]["n"] == 4  # the holed instance is left out
    holes = t["attacks"]["A"]["export_holes"]
    assert holes["states"] == {"Dash": 1} and holes["frames"] == 5
    assert holes["ttd_left_out"] == {"start": 1, "Antic A": 1, "Dash": 1}  # every span containing a hole frame
    assert t["entities"]["Test Boss"]["by_state"]["Dash"]["no_colliders"] == 5
    hole_hit = next(c for c in b.contacts if c.hole)
    assert hole_hit.res["anchor"] == 0.0  # the other instances' geometry covers it


def test_self_templates_follow_each_hazard_from_where_it_armed(synth):
    b, _ = synth
    built = b.build()
    rock = built.support["support/ent/Rock/self"]
    assert rock.frame == "anchor" and rock.n_instances == 3
    k = np.arange(40)  # the Rock falls 0.1 u per frame from where it armed, wherever that is
    assert rock.contains(k * DT, 0.0, -0.1 * k, tol_bins=0).all()
    assert not rock.contains(k * DT, 0.0, -0.1 * k + 1.5, tol_bins=0).any()
    ent = built.tables["entities"]["Rock"]
    assert ent["arm_pos"]["support"] == {"n": 3, "x": [10.0, 10.0], "y": [8.0, 8.0]}
    assert ent["arm_pos"]["by_owner_state"]["B / Throw"]["t_since_state_entry_s"] == [0.0, 0.0]
    st = ent["self_template"]
    assert st["npz"] == "support/ent/Rock/self" and st["contacts"] == 3 and st["max"] == 0.0
    shard = built.tables["entities"]["Shard"]["arm_pos"]["support"]
    assert shard["x"] == [16.0, 16.0]
    rock_hits = [c for c in b.contacts if c.tk == "Rock"]
    assert rock_hits and all(c.res["self:Rock"] == 0.0 for c in rock_hits)


def test_choice_history_covariates_find_a_forced_repeat_rule():
    """A SendRandomEventV3-like choice: 50/50, but an outcome missed twice in a row is forced. The per-state miss
    counters are kept, the hero's position is not, and the held-out log loss improves."""
    rng = np.random.default_rng(8)
    b = bt.BehaviourBuilder(SPEC)
    for fight in range(40):
        local: list[str] = []
        for i in range(30):
            miss = {o: next((j for j, x in enumerate(reversed(local)) if x == o), None) for o in ("Set L", "Set R")}
            forced = [o for o, m in miss.items() if m is not None and m >= 2]
            to = forced[0] if forced else ("Set L" if rng.random() < 0.5 else "Set R")
            b.transitions.append(bt.Transition(f"f{fight}", i, float(i), "Choose", to, 0.0, float(rng.uniform(0, 30)),
                                               0.0, None, None, None, 50, "P1", None, 0, {}, None, None, fight % 2,
                                               tuple(local)))
            local.append(to)
    d = b.decisions(["Choose"])["Choose"]
    assert set(d["conditioners"]) <= {"miss_Set L", "miss_Set R", "choice_run"} and d["conditioners"]
    assert not d["tests"]["hero_x"]["significant"]
    assert d["heldout"]["logloss_conditioned"] < d["heldout"]["logloss_unconditional"] - 0.05
    forced = [g for g in d["table"].values() if g["n"] >= 30 and max(g["p"].values()) > 0.95]
    assert forced  # the forced cells are found


def test_unexplained_hit_fails_the_build(tmp_path):
    b = bt.BehaviourBuilder(SPEC)
    b.scan_states(Synth(ghost=True).fight(PLAN), "synth-ghost")
    v = b.tables()["coverage"]["validation"]
    assert not v["ok"] and v["unexplained"]["n"] == 4  # a hit while the boss's only collider is disabled
    with pytest.raises(bt.ValidationFailed):
        b.write(tmp_path)
    assert not (tmp_path / "Synth.json").exists()
    js, _, _ = b.write(tmp_path, allow_failed=True)
    assert json.loads(js.read_text("utf-8"))["coverage"]["validation"]["ok"] is False


def test_synthetic_write_and_report(synth, tmp_path):
    from ssbot.tools.behaviour_build import report
    b, _ = synth
    js, npz, tables = b.write(tmp_path)
    data = json.loads(js.read_text("utf-8"))
    assert data["enemy"] == "Synth" and data["attacks"]["A"]["reach_union"]["anchor"]["extent"][2] > 6.0
    assert data["attacks"]["A"]["reach_union"]["world_all"]["npz"] == "support/A/world_all"
    info = data["build_info"]
    assert info["npz_sha256"] == bt._sha256(npz) and set(info["code"]) >= {"sha", "dirty"}
    tpls, extra = hb.load_templates(npz)
    assert {"A/anchor", "B/world", "B/anchor", "support/A/Dash/anchor", "A/world_all", "support/A/anchor",
            "support/ent/Rock/self"} <= set(tpls)
    assert "A/Dash/anchor" not in tpls  # per-state and self templates are stored as support only
    assert extra["A/instances"].shape == (5, len(bt.INSTANCE_COLUMNS))
    assert list(extra["A/state_names"]) == ["Antic A", "Dash", "Recover"]
    assert np.allclose(extra["A/state_t"][:4, 1], 20 * DT)
    w = extra["A/windows"]
    assert w.shape[1] == len(bt.WINDOW_COLUMNS) and set(w[:, 0].astype(int)) == set(range(5))
    path = extra["A/boss_path"]
    assert np.allclose(path[:, 2], path[:, 3])  # mirrored Set L / Set R paths coincide in the anchor frame
    assert "A/paths" not in extra  # fixed anchors (5 / 25 per side): no per-instance paths by default
    text = report(tables)
    assert any(line.split()[:2] == ["A", "5"] for line in text.splitlines()) and "195 missing" in text
    assert "validation ok: 16 contacts" in text


def test_static_fsm_graph_adds_unlogged_edges():
    choose = {"A": "Set L", "B": "Set R", "C": "Antic B", "D": "Antic C"}
    graph = {"states": [{"name": "Choose", "transitions": choose},
                        {"name": "Antic C", "transitions": {"FINISHED": "Idle"}}],
             "global": {"DEATH": "Dead"}}
    b = bt.BehaviourBuilder(SPEC, fsm_graph=graph)
    b.scan_states(Synth().fight(PLAN), "synth")
    t = b.tables()
    g = t["graph"]
    row = next(e for e in g["edges"] if e["from"] == "Choose" and e["to"] == "Antic C")
    assert row["n"] == 0 and row["static_only"] and row["p"] == round(0.5 / (8 + 0.5 * 5), 4)
    assert g["global_targets"] == ["Dead"] and "Antic C" in t["support_transitions"]["Choose"]
    assert "Antic C" in t["support_transitions"] and g["branching"] == ["Choose"]
    assert t["coverage"]["fsm_edges_extracted"] and t["coverage"]["logged_edges"] == len(g["edges"]) - 2


def test_per_instance_paths_on_request():
    b = bt.BehaviourBuilder(SPEC, keep_paths=True)
    b.scan_states(Synth().fight(PLAN[:2]), "synth")
    paths = b.extra_arrays()["A/paths"]
    assert paths.shape == (30 + 10, 4) and set(paths[:, 0]) == {0.0}
    assert np.allclose(paths[:30, 2], 0.2 * np.arange(30), atol=1e-5)  # x' of the dash
    assert np.array_equal(b.extra_arrays()["A/state_f"][0, 1:], b.extra_arrays()["A/state_f"][0, :1] + [20, 50])


def test_timeline_and_snapshot_pictures(synth, tmp_path):
    from ssbot.tools import attack_timeline as at
    b, _ = synth
    _, npz, _ = b.write(tmp_path)
    evs = [(ev["f"], ev["k"], ev["d"]) for s in Synth().fight(PLAN) for ev in s["ev"]]
    segs = at.control_segments(evs, SPEC)
    assert [fam for _, st, fam in segs if st == "Dash"] == ["A"] * 5
    img = at.draw_timeline([{"id": "synth", "f0": 1000, "f1": 1000 + 1200, "segments": segs,
                             "hits": [(f, d["source"]) for f, k, d in evs if k == "damage"]}], SPEC)
    assert img.ndim == 3 and img.shape[0] > 50
    out = tmp_path / "snap.png"
    assert at.main(["snapshots", str(npz), "--out", str(out)]) == 0 and out.stat().st_size > 1000


# ---- decisions and small statistics ------------------------------------------------------------------------

def test_decision_covariates_keep_only_what_the_choice_depends_on():
    rng = np.random.default_rng(4)
    b = bt.BehaviourBuilder(SPEC)
    hist = ["A", "B"]
    for i in range(600):
        hx = float(rng.uniform(0, 30))
        p_left = 0.85 if hx < 10 else 0.15 if hx >= 20 else 0.5   # depends on where the hero stands only
        to = "Set L" if rng.random() < p_left else "Set R"
        ph = "P1" if i < 300 else "P2"
        prev = hist[int(rng.integers(0, 2))]
        b.transitions.append(bt.Transition("f", i, float(i), "Choose", to, 0.0, hx, 0.0, None, None, None,
                                           int(rng.integers(1, 101)), ph, prev, 1, {prev: 0}))
    d = b.decisions(["Choose"])["Choose"]
    assert d["conditioners"] == ["hero_x"]
    assert d["tests"]["hero_x"]["p"] < 1e-20 and d["tests"]["hero_x"]["significant"]
    for name in ("phase", "boss_hp", "prev"):
        assert not d["tests"][name]["significant"], name
    assert "dist_visible" in d["untestable"] and "side_visible" in d["untestable"]
    tab = d["table"]
    assert set(tab) == {"hero_x=W", "hero_x=C", "hero_x=E", "*"} and tab["*"]["n"] == 600  # "*": unconditional
    assert tab["hero_x=W"]["p"]["Set L"] > 0.75 and tab["hero_x=E"]["p"]["Set L"] < 0.25


def test_small_statistics():
    q = bt.quantiles([1.0, 2.0, 3.0, None, float("nan")])
    assert q["n"] == 3 and q["p50"] == 2.0 and q["min"] == 1.0 and q["max"] == 3.0
    assert bt.quantiles([]) == {"n": 0}
    edges = (0.0, 3.0, 6.0, 10.0, 99.0)
    assert [bt.dist_bin(d, edges) for d in (0.0, 2.9, 3.0, 9.99, 50.0, 500.0, None)] == [0, 0, 1, 2, 3, 3, None]
    assert bt.collider_key("Boss", {"kind": "poly", "verts_world": [0.0] * 14}) == "Boss:poly7"
    assert bt.chi2_sf(3.841458820694124, 1) == pytest.approx(0.05, rel=1e-9)
    assert bt.chi2_sf(5.991464547107979, 2) == pytest.approx(0.05, rel=1e-9)
    assert bt.chi2_sf(0.0, 3) == 1.0 and bt.chi2_sf(200.0, 2) == pytest.approx(math.exp(-100.0), rel=1e-9)
    assert bt.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    y = np.array([0, 1] * 20)
    res = bt.independence_test(y, y.copy())
    assert res["method"] == "chi2" and res["p"] < 1e-6
    small = bt.independence_test(np.array([0, 1, 0, 1, 0, 0]), np.array([0, 1, 0, 1, 1, 0]), n_perm=200)
    assert small["method"].startswith("permutation") and 0.0 < small["p"] <= 1.0


def test_permutation_kernel_matches_reference_and_resolves_small_p():
    rng = np.random.default_rng(6)
    n = 400
    s = rng.integers(0, 3, n)
    x = rng.integers(0, 4, n)
    y = (rng.random(n) < np.where(x == 3, 0.9, 0.2)).astype(np.int64)  # depends on x
    order = np.argsort(s, kind="stable")
    ys, xs, ss = y[order], x[order], s[order]
    starts = np.searchsorted(ss, np.arange(4)).astype(np.int64)
    g = bt.g_stat(y, x, s, 2, 4, 3)[0]
    for g_obs in (g, 0.5 * g, 2.0):
        a = bt._perm_exceed(ys, xs, ss, starts, 2, 4, 3, g_obs, 300, 11)
        b = bt.perm_exceed_ref(ys, xs, ss, starts, 2, 4, 3, g_obs, 300, 11)
        assert a == b
    # a strong dependence with sparse cells: the permutation p reaches below a Holm threshold over 100 tests
    yy = np.array([0] * 60 + [1] * 6)   # exact p = 1 / C(66, 6) ~ 1e-8
    xx = np.array([0] * 60 + [1] * 6)
    res = bt.independence_test(yy, xx, n_perm=500, n_perm_max=20000)
    assert res["method"] == "permutation (20000)" and res["p"] < 0.01 / 100
    # within strata the permutation keeps each stratum's labels: a y that only depends on s is not significant
    s2 = np.repeat([0, 1], 50)
    y2 = np.concatenate([np.zeros(48, np.int64), np.ones(2, np.int64), np.ones(48, np.int64), np.zeros(2, np.int64)])
    x2 = rng.integers(0, 2, 100)
    assert bt.independence_test(y2, x2, s2, n_perm=2000)["p"] > 0.05


def test_match_source_is_exact():
    known = {"BoneBeast DropBell M", "BoneBeast DropBell M2", "Bone Beast", "BoneBeast AtkBell L"}
    assert bt.match_source("BoneBeast DropBell M2", known) == ("BoneBeast DropBell M2", None)
    assert bt.match_source("Boss Scene/BoneBeast DropBell M", known) == ("BoneBeast DropBell M", None)
    assert bt.match_source("Bone Beast/LeapCollider", known) == ("Bone Beast", "LeapCollider")
    assert bt.match_source("Boss Scene/Bone Beast(Clone)", known) == ("Bone Beast", None)
    assert bt.match_source("Boss Scene/BoneBeast AtkBell L2", known) == (None, None)
    assert bt.support_threat({"enabled": True, "damage": dict(DMG, can_cause_damage=False)})
    assert not bt.support_threat({"enabled": True, "damage": dict(DMG, eff=0)})


# ---- inputs ------------------------------------------------------------------------------------------------

def test_run_fights_reads_closed_recordings_only(tmp_path):
    run = tmp_path / "20261001_000000_BellBeast_data"
    for name, status in (("i0_000", "closed"), ("i0_001", "recording")):
        d = run / "rec" / "2026-10-01" / "TRAIN" / name
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps({"status": status}), "utf-8")
    rows = [{"instance": 0, "episode": 0, "f_wake": 10, "f_end": 900, "outcome": "CLEAR",
             "recording": "D:/elsewhere/i0_000"},
            {"instance": 0, "episode": 1, "f_wake": 910, "f_end": 1900, "outcome": "CLEAR",
             "recording": str(run / "rec" / "2026-10-01" / "TRAIN" / "i0_001")},
            {"instance": 0, "episode": 2, "f_wake": None, "f_end": 2000, "outcome": "HARNESS_FAIL",
             "recording": "x"}]
    (run / "attempts_i0.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n{\"torn", "utf-8")
    fights, skipped = bt.run_fights(run)
    assert [(f.f0, f.f1, f.path.name) for f in fights] == [(10, 900, "i0_000")]
    assert fights[0].id.endswith("/i0/ep0") and len(skipped) == 3
    assert len(bt.run_fights(run, closed_only=False)[0]) == 2
    evs = [{"frame": f, "kind": k, "data": {"to": str(f)}, "state_frame": f, "q": 0}
           for f, k in ((5, "fsm"), (10, "fsm"), (500, "damage"), (600, "gs"), (900, "fsm"), (950, "fsm"))]
    (fights[0].path / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in evs), "utf-8")
    assert [(f, k) for f, k, _ in bt.fight_events(fights[0])] == [(10, "fsm"), (500, "damage"), (900, "fsm")]
    prov = bt.provenance([{"kind": "rec", "path": str(fights[0].path), "f0": 10, "f1": 900}], None)
    inp = prov["inputs"][str(fights[0].path)]
    assert inp["status"] == "closed" and len(inp["meta_sha256"]) == 64 and inp["fights"] == 1


def test_raw_session_states_streams_a_frame_range(tmp_path):
    from ssbot.ipc.framing import MsgType, encode
    msgs = [encode(MsgType.HELLO, 0, msgpack.packb({"role": "oracle"}))]
    msgs += [encode(MsgType.STATE, f, msgpack.packb({"f": f, "dt": DT, "hero": {"pos": [f, 0]}, "big": "x" * 5000}))
             for f in range(100, 400)]
    (tmp_path / "state.raw.zst").write_bytes(zstandard.ZstdCompressor().compress(b"".join(msgs)))
    got = list(bt.raw_session_states(tmp_path, 150, 160, keys=("hero",)))
    assert [s["f"] for s in got] == list(range(150, 161))
    assert set(got[0]) == {"f", "hero"}
    assert len(list(bt.raw_session_states(tmp_path))) == 300


# ---- real fixture ------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def trial():
    data = msgpack.unpackb(zstandard.ZstdDecompressor().decompress(FIXTURE.read_bytes()), raw=False,
                           strict_map_key=False)
    b = bt.BehaviourBuilder(bt.SPECS["BellBeast"])
    infos = [b.scan_states(states, f"trial/{i}") for i, states in enumerate(data["states"])]
    return b, infos


def test_trial_fixture_instances(trial):
    b, infos = trial
    assert [i["instances"] for i in infos] == [4, 3]
    got = [(i.family, i.phase, i.dir, i.mirror, i.end) for i in b.instances]
    # each window ends a few frames into the next attack (cut: "fight_end"; its anchor is never seen)
    assert sorted(got, key=str) == sorted([
        ("BB_CHARGE", "P1", "Set L", 1, "rest"), ("BB_BURST", "P1", None, 1, "rest"),
        ("BB_LEAP", "P1", "Set R", -1, "rest"), ("BB_LEAP", "P1", "Set L", 1, "fight_end"),
        ("BB_RAGE", "P1", None, 1, "rest"), ("BB_BURST", "P2", None, 1, "rest"),
        ("BB_BURST", "P2", None, 1, "fight_end")], key=str)
    by = {(i.family, i.phase, i.end): i for i in b.instances}
    charge, leap = by[("BB_CHARGE", "P1", "rest")], by[("BB_LEAP", "P1", "rest")]
    assert charge.anchor == pytest.approx((75.03, 5.49), abs=0.01) and charge.anchor_flip is False
    assert leap.anchor == pytest.approx((95.72, 0.99), abs=0.01) and leap.anchor_flip is True
    assert by[("BB_BURST", "P1", "rest")].anchor[0] == pytest.approx(81.26, abs=0.01)
    assert charge.anchor_t == pytest.approx(1.0166, abs=0.02)
    assert [s for s, _, _ in charge.states] == ["Emerge Antic C", "Charge Emerge", "Charge Antic", "Charge",
                                                "Charge End", "Dig In"]
    assert set(b.counters) <= {"contact frames outside the scanned range"}


def test_trial_fixture_hits_entities_and_templates(trial):
    b, _ = trial
    t = b.tables()
    atk = t["attacks"]
    assert atk["BB_CHARGE"]["hits_taken"]["by_state"] == {"Charge End": 2}
    assert atk["BB_LEAP"]["hits_taken"]["by_source"] == {"Bone Beast/LeapCollider": 1}
    # the P2 burst's DropBell M2 hits the hero while the next burst is already current: attributed to its owner
    burst_hits = atk["BB_BURST"]["hits_taken"]["by_source"]
    assert burst_hits == {"Boss Scene/BoneBeast AtkBell R": 2, "BoneBeast DropBell M2": 1}
    assert atk["BB_RAGE"]["hits_taken"]["by_source"] == {"Boss Scene/Bone Beast": 1, "BoneBeast DropBell R2": 1}
    ents = t["entities"]
    assert ents["BoneBeast AtkBell L"]["armed_at_boss_state"] == {"Burst Out": 2}  # 2nd P2 burst fires after f1
    assert ents["BoneBeast AtkBell L"]["category"] == "hazard"
    assert ents["BoneBeast DropBell M2"]["armed_by_family"] == {"BB_RAGE": 1, "BB_BURST": 1}
    assert "enabled" not in ents["BoneBeast DropBell M"]["by_state"]["Antic"]
    assert ents["BoneBeast DropBell M"]["by_state"]["Air"]["enabled"] == 1.0
    assert ents["Bone Beast"]["by_state"]["Charge"]["enabled poly7"] > 0.9
    d = t["dwell_s"]
    assert d["Emerge Antic C"]["p50"] == pytest.approx(1.0166, abs=0.02)
    assert d["Charge"]["p50"] == pytest.approx(0.8833, abs=0.02)
    assert d["Submerged"]["max_abs_dwell_minus_state_time"] < 1e-3
    assert t["phases"]["P2"]["boss_hp_at_entry"]["n"] == 1
    tpls = b.templates()
    ext = tpls["BB_CHARGE/anchor"].extent()
    assert ext[0] > -6.5 and 20.0 < ext[2] < 28.5 and ext[1] > -4.2 and ext[3] < 1.7  # the charge crosses the arena
    lx = tpls["BB_LEAP/anchor"].extent()
    assert lx[2] > 20.0 and lx[0] > -6.5  # a Set R leap faces +x in the anchor frame
    assert tpls["BB_RAGE/world"].frame == "world" and tpls["BB_BURST/world"].n_instances == 1
    wx = tpls["BB_LEAP/world_all"].extent()
    assert wx[0] < 75.0 and wx[2] > 95.0  # both sides of the arena in world coordinates
    boxes = {h["source"] for h in atk["BB_BURST"]["hitboxes"]}
    assert {"Bone Beast:box", "BoneBeast AtkBell L:circle", "BoneBeast DropBell M2:circle"} <= boxes


def test_trial_fixture_every_contact_is_covered_by_its_support(trial):
    b, _ = trial
    built = b.build()
    v = built.tables["coverage"]["validation"]
    assert v["ok"] and v["damage"] >= 8 and v["blocked_frames"] > 50
    cs = [c for c in b.contacts if c.inst is not None and c.boxes]
    assert len(cs) == v["contacts"] - v["no_hero_box"]
    assert _support_covers(built, cs) == {"anchor": 0, "world_all": 0, "self": 0}
    for fam, a in built.tables["attacks"].items():
        r = a["residual_u"]
        assert r["sets"]["anchor"]["beyond_r_fail"] == 0, fam
        assert r["radius"][f"{fam}/anchor"]["u"] >= r["sets"]["anchor"]["max"]
    # the two windows are two "recordings": each window's contacts are also measured against the other's occupancy
    ho = v["heldout"]
    assert ho["world_all"]["n"] > 0 and ho["world_all"]["within_radius"] <= ho["world_all"]["n"]


def test_committed_knowledge_covers_every_fixture_contact(trial):
    """The committed BellBeast_hitboxes.npz (built from all closed recordings, the trial run included) covers every
    hit and blocked contact of the fixture with its support templates plus the hero hurtbox."""
    b, _ = trial
    support, _ = hb.load_templates(KNOWLEDGE_NPZ, prefix=hb.SUPPORT)
    keep = {k: v for k, v in support.items() if k.count("/") == 2 or k.startswith(f"support/{bt.SELF}/")}
    built = bt.Built({}, {}, keep, {})
    cs = [c for c in b.contacts if c.inst is not None and c.boxes]
    assert len(cs) > 60
    assert _support_covers(built, cs) == {"anchor": 0, "world_all": 0, "self": 0}
    meta = json.loads(KNOWLEDGE_NPZ.with_name("BellBeast.json").read_text("utf-8"))
    assert meta["build_info"]["npz_sha256"] == bt._sha256(KNOWLEDGE_NPZ)
    assert meta["coverage"]["validation"]["ok"]


# ---- fixture maker -----------------------------------------------------------------------------------------

def _trim_state(s: dict) -> dict:
    r3 = lambda v: [round(float(x), 3) for x in v]  # noqa: E731
    ents = []
    for e in s.get("ents") or ():
        out = {k: e.get(k) for k in ("iid", "type_key", "category", "src", "hp", "flipX")}
        if e.get("hidden"):
            out["hidden"] = True
        out["pos"] = r3(e["pos"][:2])
        out["fsms"] = [{"name": f["name"], "state": f["state"]} for f in e.get("fsms") or ()]
        out["colliders"] = [{"kind": c["kind"], "verts_world": r3(c["verts_world"]), "enabled": c["enabled"],
                             "damage": c.get("damage"), **({"r": round(float(c["r"]), 3)} if "r" in c else {}),
                             **({"name": c["name"]} if c.get("name") else {})}
                            for c in e.get("colliders") or ()]
        ents.append(out)
    ev = [{k: v for k, v in e.items() if k != "q"} for e in s.get("ev") or ()
          if e.get("k") in ("fsm", "damage", "damage_blocked", "hit")]
    h = s["hero"]
    return {"f": s["f"], "dt": round(float(s["dt"]), 6), "ents": ents, "ev": ev,
            "hero": {"pos": r3(h["pos"][:2]), "box": r3(h["box"]), "health": h["health"]}}


def make_fixture(recording: Path, out: Path = FIXTURE) -> int:
    from ssbot.record.recorder import RecordingReader
    r = RecordingReader(recording)
    states = [[_trim_state(s) for s in r.states(a, b, keys=("dt", "hero", "ents", "ev"))] for a, b in FIXTURE_WINDOWS]
    raw = msgpack.packb({"source": str(recording), "windows": FIXTURE_WINDOWS, "states": states},
                        use_single_float=True)
    out.write_bytes(zstandard.ZstdCompressor(level=19).compress(raw))
    return out.stat().st_size


if __name__ == "__main__":
    print(make_fixture(Path(sys.argv[1])))
