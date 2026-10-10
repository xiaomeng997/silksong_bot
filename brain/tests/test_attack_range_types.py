"""The attack-range type registry (combat.are_types), the Choristor kept bit-identical through the generalisation,
and the Clapper's new parts: the decided jump (re-anchored at its decision, pending before it), its hazards (rune bombs
row, rune slam circle) live and in the builder's truth attribution. Offline, synthetic data plus the committed
Choristor table."""
import hashlib
import math

import numpy as np
import pytest

from ssbot.combat import attack_range as ar
from ssbot.combat.are_types import module_of, specs
from ssbot.combat.are_types.clapper import JUMP_GAIN, jump_rule

C = ar.CELL
CLAPPER = "Song Heavy Sentry"


def test_registry_finds_every_type_module():
    sp = specs()
    assert {"Song Pilgrim 03", CLAPPER} <= set(sp)
    assert ar.SPECS["Song Pilgrim 03"] is ar.CHORISTOR
    assert module_of("clapper").SPEC.type_key == CLAPPER
    assert module_of("Song Pilgrim 03").SPEC.short == "Choristor"
    for s in sp.values():                       # every start state belongs to its family; primaries are starts
        for st, fam in s.start.items():
            assert st in s.fam_states[fam]
        for fam, st in s.primary.items():
            assert s.start.get(st) == fam


def _mh(m):
    return hashlib.sha256(np.ascontiguousarray(m.m).tobytes() + f"{m.m.shape}{m.ix0},{m.iy0}".encode()).hexdigest()[:16]


@pytest.mark.skipif(not ar.table_path(ar.CHORISTOR).exists(), reason="the committed Choristor table")
def test_choristor_placements_are_bit_identical():
    """The approved Choristor estimate through the generalised code (hash of 1,260 placements made before it)."""
    tab = ar.load_table()
    h = hashlib.sha256()
    for fam, brs in sorted(tab.spec.branches.items()):
        for br in list(brs) + [None]:
            for b in (0, 5, 17, 40, 80, 150, 400):
                for s in (1, -1):
                    for du in (-6.0, 2.5, 9.0):
                        for now in (None, (20.3, 7.1)):
                            m = tab.place(fam, br, b, (20.0, 7.0), s, du, now=now,
                                          b_now=None if now is None else max(b - 6, 0))
                            h.update(_mh(m).encode())
    assert h.hexdigest() == "841a2be9f4b4fc1f947d20b11ce60420343e2b4c06fb59d5dfc199ac854931f2"


def test_jump_rule_vx_and_hero_fallback():
    s, L = jump_rule(30.0, 7.45, -10.82, 19.41, 4.0)
    assert s == -1 and L == pytest.approx(JUMP_GAIN * 10.82)
    s, L = jump_rule(26.36, 7.45, None, 48.73, 4.0)          # vx unknown: clamp(hero du - 5, 12)
    assert s == 1 and L == pytest.approx(JUMP_GAIN * 12.0)
    s, L = jump_rule(20.0, 7.45, None, 22.0, 4.0)            # hero within 5 u: backward
    assert s == 1 and L == pytest.approx(JUMP_GAIN * -3.0)


def _clapper_table():
    """A synthetic Clapper table: CC_JUMP = 10 antic bins of a 2 x 4 body, then (b_dec 10) a body moving ratio x L;
    CC_CAST = the body for 60 bins; hazards: bombs ring m hurts 21 + 10 m .. 26 + 10 m frames, rune slam 65 .. 72."""
    spec = ar.SPECS[CLAPPER]
    body = np.ones((int(4.0 / C), int(2.0 / C)), bool)
    nb = 40
    origin = np.tile(np.array([[int(-1.0 / C), int(-4.4 / C)]], np.int32), (nb, 1))
    ratio = np.zeros(nb)
    ratio[10:] = np.minimum((np.arange(nb - 10)) / 20.0, 1.0)
    jump = ar.Template(nb=nb, shape=[body] * nb, origin=origin, disp=np.zeros((nb, 2)), ratio=ratio, n=1, b_dec=10)
    cast = ar.Template(nb=60, shape=[body] * 60, origin=np.tile(origin[:1], (60, 1)), disp=np.zeros((60, 2)), n=1)
    meta = {"face_flip1": -1, "walls": [8.0, 47.0], "hazards": {
        "rune bomb small": {"win": [[21 + 10 * m, 26 + 10 * m] for m in range(10)], "dx": 0.0, "dv": -3.8,
                            "x_ok": [[7.5, 47.5]], "trig": {"CC_CAST": [48, 55]}},
        "rune slam": {"win": [[65, 72]], "du": 6.48, "dv": -3.27, "trig": {"CC_JUMP_CAST": [100, 112]}}}}
    return ar.RangeTable(spec=spec, templates={("CC_JUMP", "open"): jump, ("CC_JUMP", "wall"): jump,
                                               ("CC_JUMP_CAST", "open"): jump, ("CC_CAST", "main"): cast}, meta=meta)


def test_evade_entered_again_is_the_double_branch():
    spec = ar.SPECS[CLAPPER]
    for tins, want in (([i * ar.FT for i in range(21)], "single"),
                       ([i * ar.FT for i in range(21)] + [i * ar.FT for i in range(21)], "double")):
        seg = ar.Segmenter(spec)
        insts = []
        for i, tin in enumerate(tins + [0.0]):
            st = "Evade Scuttle" if i < len(tins) else "Idle"
            inst = seg.step(st, i * ar.FT, 30.0, 7.45, -1, 20.0, tin)
            if inst is not None and (not insts or insts[-1] is not inst):
                insts.append(inst)
            if i < 21:
                assert insts[-1].branch is None             # one evade so far: open (the union)
        assert len(insts) == 1 and insts[0].branch == want


def _cl(st, x=30.0, flip=False, iid=3, tin=0.0, vx=0.0):
    return {"type_key": CLAPPER, "iid": iid, "pos": [x, 7.45, 0.0], "flipX": flip, "vel": [vx, 0.0],
            "fsms": [{"name": "Control", "state": st, "t": tin}],
            "cols": [{"name": "Song Heavy Sentry (2)", "enabled": True,
                      "verts_world": [x - 1.0, 3.0, x + 1.0, 3.0, x + 1.0, 7.0, x - 1.0, 7.0]}]}


def test_clapper_jump_is_pending_until_decided_then_placed_at_the_landing():
    tab = _clapper_table()
    trk = ar.RangeTracker(tables={CLAPPER: tab})
    for i in range(5):
        trk.feed({"dt": ar.FT, "hero": {"pos": [15.0, 4.5]}, "ents": [_cl("Jump Antic", tin=i * ar.FT)]})
    e = trk.estimate(3, 36)
    assert e.fam == "CC_JUMP"
    x0, _, x1, _ = e.raw.bbox()
    assert x0 == pytest.approx(29.0, abs=2 * C) and x1 == pytest.approx(31.0, abs=2 * C)    # pending: the body only
    for i in range(6):                                       # bins 5 .. 10: the decision at Jump (vx -10)
        trk.feed({"dt": ar.FT, "hero": {"pos": [15.0, 4.5]},
                  "ents": [_cl("Jump Antic" if i < 5 else "Jump", tin=0.0, vx=-10.0)]})
    inst = trk.now[3][2]
    assert inst.dec is not None and inst.dec["s"] == -1 and inst.dec["L"] == pytest.approx(JUMP_GAIN * 10.0)
    assert inst.branch == "open"                             # lands at 20.84: inside the wall zone limits
    e = trk.estimate(3, 30)                                  # 30 bins after the decision: ratio 1, at the landing
    xl = 30.0 - JUMP_GAIN * 10.0
    x0, _, x1, _ = e.raw.bbox()
    assert 0.5 * (x0 + x1) == pytest.approx(xl, abs=2 * C)


def test_clapper_bombs_predicted_before_cast2_then_spawned():
    tab = _clapper_table()
    trk = ar.RangeTracker(tables={CLAPPER: tab})
    trk.feed({"dt": ar.FT, "hero": {"pos": [15.0, 4.5]}, "ents": [_cl("Spell Antic")]})
    assert not trk.estimate(3, 0).haz.m.any()               # the first bomb hurts >= 48 + 21 bins later
    e = trk.estimate(3, 48 + 21)
    assert e.haz.m.any()                                     # predicted ring 0 under the Clapper
    x0, y0, x1, y1 = e.haz.bbox()
    assert 0.5 * (x0 + x1) == pytest.approx(30.0, abs=2 * C) and 0.5 * (y0 + y1) == pytest.approx(3.65, abs=2 * C)
    for i in range(1, 50):
        trk.feed({"dt": ar.FT, "hero": {"pos": [15.0, 4.5]}, "ents": [_cl("Spell Antic" if i < 49 else "Cast 2")]})
    for i in range(31):                                      # Cast 2 seen at bin 49; idle afterwards
        trk.feed({"dt": ar.FT, "hero": {"pos": [15.0, 4.5]}, "ents": [_cl("Cast 2" if i < 20 else "Idle")]})
    e = trk.estimate(3, 0)                                   # 31 frames after Cast 2: ring 1 (31 .. 36) at +-4.2
    assert e.fam is None and e.haz.m.any()
    x0, _, x1, _ = e.haz.bbox()
    assert x0 == pytest.approx(30.0 - 4.2 - 2.166, abs=3 * C) and x1 == pytest.approx(30.0 + 4.2 + 2.166, abs=3 * C)
    assert e.haz.area() == pytest.approx(2 * math.pi * 2.166 ** 2, rel=0.05)


def test_rune_slam_circle_in_front_of_the_landing():
    tab = _clapper_table()
    hz = next(h for h in tab.spec.hazards if h.name == "rune slam")
    assert not tab.hazard_mask(hz, 10.0, 10.0, 25.0, 6.6, -1, 10.0 + 64 * ar.FT).m.any()
    m = tab.hazard_mask(hz, 10.0, 10.0, 25.0, 6.6, -1, 10.0 + 66 * ar.FT)
    x0, y0, x1, y1 = m.bbox()
    assert 0.5 * (x0 + x1) == pytest.approx(25.0 - 6.48, abs=2 * C)
    assert 0.5 * (y0 + y1) == pytest.approx(6.6 - 3.27, abs=2 * C)
    assert m.area() == pytest.approx(math.pi * 7.187 ** 2, rel=0.01)


def test_builder_attributes_hazard_episodes_by_the_spawn_rule():
    """attach_hazards: of two casts, a bomb episode goes to the one whose timing fits on0 + on_step x ring."""
    from ssbot.tools.attack_range_build import attach_hazards
    spec = ar.SPECS[CLAPPER]
    F = 400
    T = np.arange(F) * ar.FT
    st_names = ["Idle", "Spell Antic", "Cast 2"]
    seq = np.array([0] * 10 + [1] * 50 + [2] * 20 + [0] * 40 + [1] * 50 + [2] * 20 + [0] * 210)
    c = {"types": [CLAPPER, "damager"], "states": st_names, "names": ["Song Heavy Sentry (2)", "damager"],
         "f": np.arange(F), "T": T, "hx": np.full(F, 15.0), "hy": np.full(F, 4.5), "events": [],
         "meta": {"id": "synthetic"}}
    # entity rows: the Clapper every frame (row f), one bomb entity hurting at ring 1 of the second cast
    cast2 = [i for i in range(1, F) if seq[i] == 2 and seq[i - 1] != 2]
    on = cast2[1] + 31
    brow = list(range(on, on + 6))
    n_e = F + len(brow)
    c.update(e_fi=np.concatenate([np.arange(F), brow]).astype(np.int32),
             e_iid=np.array([3] * F + [99] * len(brow), np.int64),
             e_tk=np.array([0] * F + [1] * len(brow), np.int16),
             e_x=np.array([30.0] * F + [34.2] * len(brow), np.float32), e_y=np.array([7.45] * F + [3.65] * len(brow),
                                                                                  np.float32),
             e_vx=np.zeros(n_e, np.float32), e_flip=np.zeros(n_e, np.int8),
             e_st=np.concatenate([seq, -np.ones(len(brow), int)]).astype(np.int16),
             e_tin=np.zeros(n_e, np.float32), e_hidden=np.zeros(n_e, np.int8), e_src=np.zeros(n_e, np.int16))
    c.update(c_ei=np.arange(F, n_e, dtype=np.int32), c_name=np.ones(len(brow), np.int16),
             c_box=np.array([[34.2 - 2.166, 3.65 - 2.166, 34.2 + 2.166, 3.65 + 2.166]] * len(brow), np.float32),
             c_dealt=np.ones(len(brow), np.int8), c_eff=np.ones(len(brow), np.int8))
    from ssbot.tools.attack_range_build import tracks_from_cache
    trs = tracks_from_cache(c, CLAPPER, "dev")
    stats = attach_hazards(c, trs, spec, f1=-1)
    assert stats["rune bomb small"] == {"episodes": 1, "attributed": 1}
    ep = trs[0]["hz_eps"][0]
    assert ep["ring"] == 1 and ep["t"] == pytest.approx(T[cast2[1]])
    assert any(nm == "HZ:rune bomb small" for nm, _ in trs[0]["cols"][on])


def test_state_gate_draws_the_state_now_at_k0_and_what_can_still_come():
    """A bin whose union holds the body (instances still in Air) and a big slam (instances already landed): k = 0 in
    Air draws the body only, k > 0 from Air both, k > 0 from Slam Recover not the slam it has left."""
    body = np.ones((80, 40), bool)
    slam = np.ones((40, 200), bool)
    nb = 10
    sst = [{"Air": (body, -20, 0), "Slam 2": (slam, 0, 0)} for _ in range(nb)]
    full = np.ones((80, 220), bool)
    tp = ar.Template(nb=nb, shape=[full] * nb, origin=np.tile(np.array([[-20, 0]], np.int32), (nb, 1)),
                     disp=np.zeros((nb, 2)), n=2, sst=sst, order={"Air": 0, "Slam 2": 1, "Slam Recover": 2, "<end>": 3})
    tab = ar.RangeTable(spec=ar.SPECS[CLAPPER], templates={("CC_SLAM", "main"): tp}, meta={"walls": [0.0, 99.0]})
    a0 = tab.place("CC_SLAM", "main", 5, (30.0, 7.0), 1, now=(30.0, 7.0), b_now=5, st_now="Air")
    assert a0.area() == pytest.approx(body.sum() * C * C, rel=0.01)
    a6 = tab.place("CC_SLAM", "main", 6, (30.0, 7.0), 1, now=(30.0, 7.0), b_now=5, st_now="Air")
    assert a6.area() > slam.sum() * C * C
    r6 = tab.place("CC_SLAM", "main", 6, (30.0, 7.0), 1, now=(30.0, 7.0), b_now=5, st_now="Slam Recover")
    assert r6.area() == pytest.approx(full.sum() * C * C, rel=0.01)       # nothing at or after it: the whole union
    assert tab.place("CC_SLAM", "main", 6, (30.0, 7.0), 1, now=(30.0, 7.0), b_now=5).area() == r6.area()


def test_family_templates_take_the_own_colliders_only():
    """The hazards attached to a track (HZ:<name>, circles) are the hazards' truth, never part of a family template
    (build uses frame_polys(hz=False)); poly_of draws them as the AABB's inscribed circle."""
    from ssbot.tools.attack_range_build import frame_polys
    tr = {"flip": np.zeros(1, np.int8),
          "cols": [[("Slam Collider 1", np.array([1.0, 3.0, 4.0, 5.0])),
                    ("HZ:rune bomb small", np.array([10.0, 1.5, 14.332, 5.832]))]]}
    own = frame_polys(tr, 0, {}, hz=False)
    haz = frame_polys(tr, 0, {}, hz=True)
    assert len(own) == 1 and len(haz) == 1 and len(frame_polys(tr, 0, {})) == 2
    assert ar.poly_mask(haz).area() == pytest.approx(math.pi * 2.166 ** 2, rel=0.02)
