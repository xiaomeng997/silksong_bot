"""Forum round R0 offline tools on synthetic STATEs (the gauntlet tables' fixture, tests/test_gauntlet_tables.py):
the per-fight cache, the per-enemy tracker, the held-out support recall end to end (gauntlet build -> per-fold
supports and contacts -> caches -> recall), the per-family margins, the data products and the replay's concurrency."""
import gzip
import json
import math
from pathlib import Path

import numpy as np

from ssbot.knowledge.behaviour_tables import Fight
from ssbot.knowledge.forum_cache import extract_states, load_cache, save_cache
from ssbot.knowledge.forum_products import Chains, FightView, KillFreeze, Quiet, body_collider, source_type
from ssbot.knowledge.forum_support import FoldTables, SubjectRecall, SubjectTracker, margins_from_contacts, \
    read_contacts, replay
from ssbot.knowledge.gauntlet_tables import GauntletBuilder
from tests.test_gauntlet_tables import SPEC, _states

SPECS = {"Foe": SPEC}


def _cache(tmp_path: Path, states=None, name="fight") -> dict:
    c = extract_states(states or _states(), {"id": name})
    p = save_cache(c, tmp_path / f"{name}.npz")
    return load_cache(p)


def test_cache_roundtrip_keeps_entities_colliders_and_events(tmp_path):
    c = _cache(tmp_path)
    assert len(c["f"]) == 120 and c["types"][int(c["e_tk"][0])] == "Foe"
    # two foes every frame, the ball from frame 30 to 70
    assert len(c["e_fi"]) == 2 * 120 + 41
    r = int(np.flatnonzero(c["e_iid"] == 1)[0])
    assert np.allclose(c["e_box"][r], [9.5, 4.5, 11.5, 5.5])   # body and "Hand" child, one union box
    assert {c["names"][int(n)] for n in c["c_name"][c["c_ei"] == r]} == {"Foe", "Hand"}
    assert math.isclose(c["T"][-1], 119 / 60, rel_tol=1e-9)
    kinds = {k for _, k, _ in c["events"]}
    assert {"fsm", "damage", "damage_blocked", "hit"} <= kinds


def test_tracker_segments_like_the_gauntlet_builder(tmp_path):
    c = _cache(tmp_path)
    log: list = []
    tr = SubjectTracker(SPECS, log=log)
    for _ in replay(c, tr, SPECS):
        pass
    by = {}
    for inst in log:
        by.setdefault(inst.iid, []).append((inst.family, inst.end))
    assert by[2] == [("F_IDLE", "chain"), ("F_HIT", "rest"), ("F_IDLE", None)]
    assert by[1] == [("F_IDLE", "death")]
    hit = next(i for i in log if i.family == "F_HIT")
    assert hit.anchor == (20.0, 5.0) and hit.mirror == -1 and hit.f_start == 10 and hit.f_end == 20
    assert tr.subjects[1].dead and tr.subjects[2].ends[-1][0] == "F_HIT"


def _build_extra(tmp_path: Path) -> Path:
    from ssbot.tools.behaviour_build import write_extra
    g = GauntletBuilder(SPECS)
    for k in range(2):           # two fights: fold 0 and fold 1
        g.scan(Fight("states", Path("."), 1, 120, f"run/i0/ep{k}"), _states())
    for b in g.builders.values():
        b.tables()
    extra = tmp_path / "extra"
    write_extra(extra, g, {})
    return extra


def test_held_out_recall_end_to_end(tmp_path):
    extra = _build_extra(tmp_path)
    rows = read_contacts(extra / "contacts.jsonl.gz")
    assert {r["fold"] for r in rows} == {0, 1} and all(r["fight"].startswith("run/i0/ep") for r in rows)
    build = json.loads((extra / "build.json").read_text("utf-8"))
    assert build["walk"]["Foe"]["succ"]["0"]["Idle"] == ["Antic"]
    c = _cache(tmp_path)
    for fold in (0, 1):
        rec = SubjectRecall(FoldTables(extra, 1 - fold, specs=SPECS), lags=(2, 3, 4))
        mine = [r for r in rows if r["fold"] == fold]
        rec.run(c, mine)
        n = sum(v["n"] for (tk, L), v in rec.stats.items() if L)
        assert n == 3 * len([r for r in mine if not r["follow"]]) and n > 0
        assert not rec.misses, rec.misses[:3]
    # a contact the enemy cannot reach is a miss
    far = dict(mine[0], boxes=[[60.0, 4.0, 60.5, 6.0], [60.0, 4.0, 60.5, 6.0]])
    rec = SubjectRecall(FoldTables(extra, 0, specs=SPECS), lags=(2,))
    rec.run(c, [far])
    assert len(rec.misses) == 1


def test_margins_are_calibrated_on_the_other_fold():
    own = {"type": "Foe", "tk": "Foe", "family": "F_HIT", "state": "Antic"}
    rows = [{**own, "fold": 0, "ho": {"state:Antic": 0.2}},
            {**own, "fold": 0, "ho": {"state:Antic": 0.7}},
            {**own, "fold": 1, "ho": {"state:Antic": None}},
            {**own, "fold": 1, "follow": True, "ho": {"state:Antic": 2.0}},
            # a thrown hazard's contact: its self template's residual, not the family's
            {**own, "tk": "Ball", "fold": 0, "state": "_tail", "ho": {"state:_tail": 2.5, "self:Ball": 0.1}}]
    assert margins_from_contacts(rows, fold=0) == {("Foe", "F_HIT"): 0.7, ("ent", "Ball"): 0.1}
    assert margins_from_contacts(rows, fold=1) == {("Foe", "F_HIT"): 3.0}     # beyond the search: its radius
    assert math.isclose(margins_from_contacts(rows, fold=0, q=0.0)[("Foe", "F_HIT")], 0.2)


def test_tracker_records_hazard_armings(tmp_path):
    from ssbot.knowledge.forum_support import thrown
    c = _cache(tmp_path)
    tr = SubjectTracker(SPECS)
    for i, f, T in replay(c, tr, SPECS):
        if f == 45:
            h = thrown(tr, SPEC)
            assert len(h) == 1 and h[0][0] == "Ball" and h[0][2] == (21.0, 4.0)
            assert math.isclose(T - h[0][1], 15 / 60, abs_tol=1e-9)
    assert not thrown(tr, SPEC)        # disarmed after frame 70


def test_margin_dilates_the_fold_templates(tmp_path):
    extra = _build_extra(tmp_path)
    t0 = FoldTables(extra, 0, specs=SPECS)
    t1 = FoldTables(extra, 0, margins={("Foe", "F_HIT"): 0.5}, specs=SPECS)
    k = next(k for k in t0.templates if "/F_HIT/" in k)
    a0 = np.unpackbits(t0.templates[k].bits).sum()
    a1 = np.unpackbits(t1.templates[k].bits).sum()
    assert a1 > a0
    assert t1.templates[k].pad_x >= t0.templates[k].pad_x + 0.5 - 1e-9


def test_chains_count_multi_hit_follow_ups_and_skip_blocked_first_hits():
    class V:
        events = [(100, "damage", {"source": "Song Pilgrim 03/Whip Hit 2", "amount": 1}),
                  (112, "special_damage", {"fsm": "Hero_Hornet(Clone)/Roar and Wound States/Multihit:X", "amount": 1}),
                  (130, "catastrophe", {"src": "Whip Hit 2", "blocked": True, "amount": 1}),
                  (400, "damage", {"source": "Song Pilgrim 03 (2)/Whip Hit 1", "amount": 1}),
                  (400, "catastrophe", {"src": "Whip Hit 1", "blocked": True, "amount": 1}),
                  (700, "damage", {"source": "Wave 8 - Heavy Sentry/Song Heavy Sentry", "amount": 2}),
                  # follow-ups as damage events of the same whip, another Choristor's hit in between ends nothing
                  (1000, "damage", {"source": "Song Pilgrim 03 (3)/Whip Hit 1", "amount": 1}),
                  (1012, "damage", {"source": "Song Pilgrim 03 (3)/Whip Hit 3", "amount": 1}),
                  (1030, "damage", {"source": "Song Pilgrim 03 (3)/Whip Hit 4", "amount": 1})]
    ch = Chains()
    ch.add(V())
    r = ch.result()["by_source"]
    w = r["Song Pilgrim 03/Whip Hit"]          # the whip's colliders 1-6 are one attack
    assert w["n"] == 3 and w["first_hit_blocked"] == 1 and w["multi_hit_chains"] == 2
    assert w["hits_max"] == 3 and w["damage_max"] == 3 and w["hits"] == {3: 2, 1: 1}
    assert r["Song Heavy Sentry/body"]["damage_max"] == 2


def test_source_types_and_body_colliders():
    assert source_type("Colliders/Collider ParryStance") == ("Song Administrator", "Collider ParryStance")
    assert source_type("rune bomb small(Clone)/damager")[0] == "Song Heavy Sentry"
    assert source_type("Song Reed Pin Projectile(Clone)")[0] == "Song Reed"
    assert source_type("Song Pilgrim 03/Song Pilgrim Maestro/Slash Hit 2") == ("Song Pilgrim Maestro", "Slash Hit 2")
    assert body_collider("Song Reed", "Song Reed (1)") and body_collider("Song Pilgrim 03", "Body Damager")
    assert body_collider("Song Administrator", "Collider Fly") and not body_collider("Song Reed", "Stab Hit 1")


def test_products_on_the_synthetic_fight(tmp_path):
    c = _cache(tmp_path)
    c["events"].append((90, "freeze", {"phase": "start", "id": 7, "type": "BigEnemyDeathSlow", "down": 0.04,
                                       "wait": 0.06, "up": 0.04, "speed": 0.0}))
    c["events"].append((100, "freeze", {"phase": "end", "id": 7}))
    v = FightView(c, specs=SPECS)
    assert [i.family for i in v.instances if i.iid == 2] == ["F_IDLE", "F_HIT", "F_IDLE"]
    # the ball armed after Foe (1)'s attack ended belongs to that attack
    hit = next(i for i in v.instances if i.family == "F_HIT")
    assert v.hazards[id(hit)] and v.hazards[id(hit)][0][1] == "Ball(Clone)"
    kf = KillFreeze()
    kf.add(v)
    r = kf.result()
    assert r["by_type"]["Foe"] and r["frames_to_end"]["Foe|BigEnemyDeathSlow"]["max"] == 10
    q = Quiet()
    q.add(v)
    assert q.result()["gaps"] == 0      # a foe is in play every frame


def test_concurrency_counts_enemies_in_play(tmp_path):
    from ssbot.tools.forum_simul import Concurrency, in_play_rows
    states = _states()
    for s in states:
        s["room"] = {"battles": [{"name": "Battle Scene", "wave": 0, "started": True, "completed": False}]}
    c = _cache(tmp_path, states)
    starts = np.searchsorted(c["e_fi"], np.arange(len(c["f"]) + 1))
    conc = Concurrency(SPECS)
    tr = SubjectTracker(SPECS)
    for i, f, T in replay(c, tr, SPECS):
        conc.frame(c, i, in_play_rows(c, i, starts, SPECS), tr, "x")
    r = conc.result()
    assert r["in_play_share"]["2"] == 1.0          # Init counts as in play (not a waiting state); hp stays 10
    w = r["by_wave"]["0"]
    assert w["in_play_max"] == 2 and w["share_ge2"] == 1.0 and w["x_span_median_u"] == 10.0
    assert sum(w["all_idle_mixed_committed"]) == 1.0 and w["all_idle_mixed_committed"][1] > 0   # the attack frames


def test_contacts_file_is_gzip_jsonl(tmp_path):
    extra = _build_extra(tmp_path)
    with gzip.open(extra / "contacts.jsonl.gz", "rt", encoding="utf-8") as fh:
        first = json.loads(fh.readline())
    assert {"type", "fight", "f", "family", "state", "fold", "boxes", "res", "ho"} <= set(first)
    assert (extra / "Foe_support_fold0.npz").exists() and (extra / "Foe_support_fold1.npz").exists()


def test_top_speed_and_current_collider_tube(tmp_path):
    from ssbot.knowledge.forum_support import Subject, top_speeds
    states = _states()
    for s in states:                     # Foe (iid 1) walks 0.1 u per frame; a 5 u jump is a teleport
        for e in s["ents"]:
            if e["iid"] == 1:
                e["pos"] = [10.0 + 0.1 * s["f"] + (5.0 if s["f"] >= 60 else 0.0), 5.0, 0.0]
    c = _cache(tmp_path, states)
    v = top_speeds([c], SPECS)
    assert math.isclose(v["Foe"], 6.0, rel_tol=1e-3)
    rec = SubjectRecall.__new__(SubjectRecall)
    rec.tube_speed, rec.tube_skin = {"Foe": 6.0}, 0.1
    s = Subject(1, "Foe", box=(9.5, 4.5, 10.5, 5.5), seen_T=1.0)
    # within the hero half-width + skin + 6 u/s x 4 frames of the box edge, and beyond it
    assert rec.in_tube(s, [(10.5 + 0.25 + 0.1 + 0.39, 5.0, 4 / 60)], 1.0)
    assert not rec.in_tube(s, [(10.5 + 0.25 + 0.1 + 0.41, 5.0, 4 / 60)], 1.0)
    # a box last seen 2 frames before the origin (a killed enemy left the export) grows from then on
    assert rec.in_tube(s, [(10.5 + 0.25 + 0.1 + 0.59, 5.0, 4 / 60)], 1.0 + 2 / 60)
    assert not rec.in_tube(s, [(10.5, 5.0, 0.0)], 1.6)          # too old: no tube


def test_body_hull_and_hazard_tube(tmp_path):
    from ssbot.knowledge.forum_support import Subject, body_hulls
    c = _cache(tmp_path)
    hull = body_hulls([c], SPECS)["Foe"]          # the root collider "Foe" (1 x 1 at its position), not "Hand"
    assert np.allclose(hull, (-0.5, -0.5, 0.5, 0.5))
    rec = SubjectRecall.__new__(SubjectRecall)
    rec.tube_speed, rec.tube_skin, rec.body_rel = {"Foe": 0.0}, 0.1, {"Foe": hull}
    s = Subject(1, "Foe", pos=(10.0, 5.0), seen_T=1.0)          # no damage box exported: the hull at its position
    assert rec.in_tube(s, [(10.0 + 0.5 + 0.25 + 0.09, 5.0, 0.0)], 1.0)
    tr = SubjectTracker(SPECS)
    tr.T = 1.0
    # a ball last seen 1 frame ago moving at 6 u/s, its collider off (a nail hit): 0.5 x 0.5 box around it
    tr.hazard(99, "Ball", 1.0 - 1 / 60, 21.0, 4.0, True, (20.75, 3.75, 21.25, 4.25), (6.0, 0.0))
    tr.hazard(99, "Ball", 1.0 - 1 / 60, 21.0, 4.0, False, None, (6.0, 0.0))
    reach = 21.25 + 0.25 + 0.1 + 6.0 * (3 / 60)
    assert rec.in_hazard_tube(tr, SPEC, [(reach - 0.01, 4.0, 2 / 60)], 1.0)
    assert not rec.in_hazard_tube(tr, SPEC, [(reach + 40.0 * 3 / 60 + 0.05, 4.0, 2 / 60)], 1.0)
