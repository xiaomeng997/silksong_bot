"""The m2_exports probe's checks on synthetic data, in process (no socket, no game): the per-STATE validation accepts a
complete M2 STATE and flags each missing or malformed field of an older one, fight_checks passes a consistent Bell
Beast fight and fails when one claim breaks (each mutation below is a regression the probe must catch), and hp_chain
ties the "hit" events to the exported hp."""
import copy

from ssbot.ipc.framing import BUTTONS
from ssbot.probes import m2_exports as probe
from ssbot.train.episode import CLEAR, STUCK, AttemptRecord

BOSS = probe.BOSS
GATE_L, GATE_R = probe.GATES


class FakeLink:
    def __init__(self):
        self.subscribers = []

    def subscribe_state(self, fn) -> None:
        self.subscribers.append(fn)


def _state(f: int = 100) -> dict:
    n = len(BUTTONS)
    tm = {k: 0 for k in probe.TM_KEYS} | {"inv": 0.0, "recoil": 0.0, "grav": 1.0}
    return {
        "f": f, "fdt": 0.02,
        "act": {"mask": 1, "hf": {"pending": [0] * n, "age": [255] * n, "latched": 1, "desired": 1}},
        "hero": {"alpha": 0.4, "wall": [False, True], "tm": tm, "invulnerable": False,
                 "tags": [{"kind": "Acid", "dmg_left": 2, "t_left": 0.3}],
                 "tools": ["Straight Pin", None], "tool_amounts": [7, None], "tool_max": [12, None]},
    }


def _collector() -> probe.Collector:
    link = FakeLink()
    col = probe.Collector(link)
    assert len(link.subscribers) == 1
    return col


def test_validate_complete_state():
    col = _collector()
    col._on(_state())
    assert col.n["act.hf"] == 1 and col.n["hero"] == 1 and not col.bad
    assert col.n["wall_touch"] == 1 and col.n["tags_active"] == 1


def test_validate_flags_each_field():
    col = _collector()
    old = {"f": 5, "act": {"mask": 0}, "hero": {"tools": ["Straight Pin"], "tool_amounts": [3]}}   # pre-M2 STATE
    col._on(old)
    assert set(col.bad) == {"act.hf", "hero.alpha", "hero.wall", "hero.tm", "hero.tags"}
    assert col.n["tool_max_nil"] == 1
    bad = _state()
    bad["act"]["hf"]["latched"] = 3                          # latched != act.mask
    bad["hero"]["alpha"] = -0.1                              # before the fixed clock: never valid
    bad["hero"]["tm"]["recoil"] = 0.5                        # above RECOIL_DURATION
    bad["hero"]["tool_amounts"] = [13, None]                 # above tool_max
    col = _collector()
    col._on(bad)
    assert set(col.bad) == {"act.hf", "hero.alpha", "hero.tm", "hero.tool_max"}


def test_validate_alpha_and_inv():
    col = _collector()
    s = _state()
    s["hero"]["alpha"], s["fdt"] = None, 0.0                 # timeScale 0 (ScaleTime): fixedDeltaTime 0, alpha nil
    col._on(s)
    s = _state(101)
    s["hero"]["alpha"] = 1.3                                 # a long frame whose fixed steps Unity capped: counted
    col._on(s)
    assert not col.bad and col.n["alpha_high"] == 1
    s = _state(102)
    s["hero"]["alpha"] = None                                # nil while fixedDeltaTime is 0.02: broken
    col._on(s)
    assert set(col.bad) == {"hero.alpha"}
    col = _collector()
    s = _state()
    s["hero"]["tm"]["inv"] = 0.8                             # StartInvulnerable timers after SceneInit cleared the flag
    col._on(s)
    assert set(col.bad) == {"hero.tm"} and "invulnerable is false" in col.example["hero.tm"][1]
    s = _state(101)
    s["hero"]["tm"]["inv"], s["hero"]["invulnerable"] = 0.8, True
    col = _collector()
    col._on(s)
    assert not col.bad


def _fight() -> tuple[probe.Collector, AttemptRecord]:
    """A consistent fight: Dormant, a first Charge Emerge whose box appears at its 5th frame, Charge, Submerged
    (hidden), Leap, one hero hit at f150 with i-frames and recoil, two nail hits killing the boss, Death Broadcast."""
    col = _collector()
    gates_closed = [{"name": GATE_L, "id": 1, "enabled": True, "box": [67.2, 3.0, 69.2, 12.0]},
                    {"name": GATE_R, "id": 2, "enabled": True, "box": [102.0, 3.0, 104.0, 12.0]},
                    {"name": "Wall", "id": 3, "enabled": False, "box": [91.7, 3.0, 100.3, 4.0]}]
    gates_open = [dict(g, enabled=False) for g in gates_closed[:2]]

    def boss(kinds: list[str], names: list[str], hidden: bool = False, hp: int = 10) -> dict:
        return {"iid": -42, "hidden": hidden, "ncol": len(kinds), "hp": hp, "kinds": kinds, "names": names}

    for f in range(0, 360):
        row = {"f": f, "paused": False, "inv": 0.0, "recoil": 0.0, "menu": None, "gates": gates_closed, "boss": None}
        if f < 10:
            row.update(ctl="Dormant", gates=gates_open)
        elif f < 20:
            row.update(ctl="Charge Emerge", boss=boss(["box"], [BOSS]) if f >= 14 else boss([], []))
        elif f < 60:
            row.update(ctl="Charge", boss=boss(["box", "poly"], [BOSS, "PolyCollider"], hp=10 if f < 30 else 5))
        elif f < 100:
            row.update(ctl="Submerged", boss=boss([], [], hidden=True, hp=5))
        elif f < 140:
            row.update(ctl="Leap Out", boss=boss(["poly"], ["LeapCollider"], hp=5))
        elif f < 300:
            row.update(ctl="Idle", boss=boss(["box"], [BOSS], hp=5 if f < 250 else 0))
        else:
            row.update(ctl="Death Broadcast")
        if 150 <= f < 210:
            row["inv"] = round(1.0 - (f - 150) / 60, 6)
        if 150 <= f < 162:
            row["recoil"] = round(0.2 - (f - 150) / 60, 6)
        col.rows.append(row)
    col.damage.append((150, {"source": "Boss Scene/Bone Beast"}))
    hit = {"ent": -42, "type_key": BOSS, "dealt": 5, "attack": "Nail", "src": "Slash", "crit": False}
    col.hits += [(30, dict(hit, dmg=5, hp_before=10, hp_after=5, dead=False)),
                 (250, dict(hit, dmg=5, hp_before=5, hp_after=0, dead=True))]
    rec = AttemptRecord(unit="BellBeast", stage="probe", profile="TRAIN", build="1.0.30000", code_rev=None,
                        config_fp="t", start_kind="savestate", mode="data", seed=0, outcome=CLEAR)
    return col, rec


def test_fight_checks_pass_on_a_consistent_fight(capsys):
    col, rec = _fight()
    assert probe.fight_checks(col, rec)
    assert "FAIL" not in capsys.readouterr().out


def test_fight_checks_catch_each_broken_claim(capsys):
    def broken(edit) -> str:
        col, rec = _fight()
        edit(col, rec)
        assert not probe.fight_checks(col, rec)
        return "\n".join(line for line in capsys.readouterr().out.splitlines() if line.startswith("FAIL"))

    def empty_first_charge(col, rec):            # the pre-fix hole: no body box in the whole first Charge Emerge
        for r in col.rows:
            if r["ctl"] == "Charge Emerge":
                r["boss"] = dict(r["boss"], kinds=[], names=[], ncol=0)
    assert "first Charge Emerge" in broken(empty_first_charge)

    def not_hidden(col, rec):                    # the boss missing while underground (pre-M2 export)
        for r in col.rows:
            if r["ctl"] == "Submerged":
                r["boss"] = None
    assert "hidden underground" in broken(not_hidden)

    def overkill_after_death(col, rec):          # a second "dead" hit on the corpse is not a second killing blow
        col.hits.append((260, dict(col.hits[-1][1], hp_before=0, hp_after=-5)))
    col, rec = _fight()
    overkill_after_death(col, rec)
    probe.fight_checks(col, rec)
    out = capsys.readouterr().out
    assert "PASS  the killing blow" in out and "FAIL  dmg == hp_before - hp_after" not in out

    def odd_nail(col, rec):
        f, d = col.hits[0]
        col.hits[0] = (f, dict(d, dmg=4, hp_after=6))
    assert "every nail hit on the boss is dmg 5" in broken(odd_nail)

    def other_ent(col, rec):
        col.hits[0] = (30, dict(col.hits[0][1], ent=7))
    assert "hit.ent is the boss's ents iid" in broken(other_ent)

    def inv_rises(col, rec):
        for r in col.rows:
            if r["f"] == 180:
                r["inv"] = 0.9
    assert "hero.tm.inv" in broken(inv_rises)

    def gate_open(col, rec):
        for r in col.rows:
            if 100 <= r["f"] < 300:
                r["gates"] = [dict(g, enabled=False) if g["name"] == GATE_R else g for g in r["gates"]]
    assert "both gates enabled" in broken(gate_open)

    def stuck(col, rec):
        rec.outcome = STUCK
    assert "did not end in CLEAR" in broken(stuck)

    def first_hit_dropped(col, rec):             # a hook path that misses the first hit: hp drops with no event
        col.hits.pop(0)
    assert "explained by its hit events" in broken(first_hit_dropped)

    def ents_hp_disagrees(col, rec):             # the export's hp and a self-consistent hit chain disagree
        for r in col.rows:
            if 100 <= r["f"] < 140:
                r["boss"] = dict(r["boss"], hp=6)
    assert "explained by its hit events" in broken(ents_hp_disagrees)

    def hit_before_ents_hp(col, rec):            # hp_before is not the hp the boss had before the frame
        f, d = col.hits[1]
        col.hits[1] = (f, dict(d, hp_before=7, hp_after=2, dmg=5))
    assert "explained by its hit events" in broken(hit_before_ents_hp)

    def corpse_hidden(col, rec):                 # fix #4 regressed: the dead boss exported hidden in Death Broadcast
        for r in col.rows:
            if r["f"] >= 300:
                r["boss"] = {"iid": -42, "hidden": True, "ncol": 0, "hp": 0, "kinds": [], "names": []}
    assert "a dead boss is never exported hidden" in broken(corpse_hidden)

    def hidden_in_death_broadcast(col, rec):     # hp still > 0 but the FSM is in its death state
        for r in col.rows:
            if r["f"] >= 300:
                r["boss"] = {"iid": -42, "hidden": True, "ncol": 0, "hp": 5, "kinds": [], "names": []}
                r["ctl"] = "Death Broadcast"
    out = broken(hidden_in_death_broadcast)
    assert "a dead boss is never exported hidden" in out


def test_hp_chain_same_frame_overkill_and_gaps():
    rows = [{"f": f, "boss": {"hp": 10 if f < 5 else -3}} for f in range(10)]
    hits = [(5, {"hp_before": 7, "hp_after": -3, "dmg": 10}),     # nested tag hit reported first (inner)
            (5, {"hp_before": 10, "hp_after": 7, "dmg": 3})]      # then the outer call's own part
    out = probe.hp_chain(rows, hits)
    assert out["problems"] == [] and out["checked"] == 1 and out["dmg"] == 13 and (out["hp0"], out["hp_end"]) == (10, -3)
    # the boss leaves "ents" on the killing frame: the events alone carry the chain to the end
    rows = [{"f": f, "boss": {"hp": 10} if f < 5 else None} for f in range(10)]
    out = probe.hp_chain(rows, [(5, {"hp_before": 10, "hp_after": -5, "dmg": 15})])
    assert out["problems"] == [] and out["hp_end"] == -5 and out["dmg"] == out["hp0"] - out["hp_end"]
    # a dropped STATE (frame 5 missing, its event lost with it) is a gap, not a problem
    rows = [{"f": f, "boss": {"hp": 10 if f < 5 else 5}} for f in range(10) if f != 5]
    out = probe.hp_chain(rows, [])
    assert out["problems"] == [] and out["gaps"] == 1
    # without the gap the same hp change is a problem
    rows = [{"f": f, "boss": {"hp": 10 if f < 5 else 5}} for f in range(10)]
    assert probe.hp_chain(rows, [])["problems"] == ["f5: ents hp 5, the hits so far leave 10"]
    # a savestate load brings a fresh boss (another iid, full hp): a new chain; hits on another ent are ignored
    rows = [{"f": f, "boss": {"iid": 1, "hp": 10 if f < 3 else 5}} for f in range(5)] +            [{"f": f, "boss": {"iid": 2, "hp": 10 if f < 8 else 0}} for f in range(5, 10)]
    hits = [(3, {"ent": 1, "hp_before": 10, "hp_after": 5, "dmg": 5}), (8, {"ent": 2, "hp_before": 10, "hp_after": 0,
            "dmg": 10}), (8, {"ent": 99, "hp_before": 40, "hp_after": 30, "dmg": 10})]
    out = probe.hp_chain(rows, hits)
    assert out["problems"] == [] and (out["hp0"], out["hp_end"], out["dmg"]) == (10, 0, 10)


def test_fight_checks_need_hits_and_names(capsys):
    col, rec = _fight()
    col.hits.clear()
    col.damage.clear()
    for r in col.rows:
        if r["boss"]:
            r["boss"] = copy.deepcopy(r["boss"]) | {"names": [None] * len(r["boss"]["names"])}
    assert not probe.fight_checks(col, rec)
    out = capsys.readouterr().out
    assert "FAIL  hero.tm.inv after a hit: the hero was never hit" in out
    assert "FAIL  collider names" in out and "FAIL  every nail hit" in out
