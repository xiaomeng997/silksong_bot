"""Task 179 #308 (live 179-L3 w13_guard179L3 5df8711e): the face hook's entry check covers the whole locked hook AND
its forced bounce. B2Geometry.scan_batch is exactly [scan(p)] (contacts, order, refusals); entry_outs is the N=2
continuation lower bound's short pass at every control point (never weaker than NativeManualAirChain._continuations'
lower bound; no full-exit fallback at entry); _transfer_offer rejects a hook whose bounce has no two clear exits.
Stub RangeSupports as Root's geometry tests use; model rows, not a hit, ride or flight claim."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import knife_chain_face_hook as FH
from ssbot.combat import observed_slam
from ssbot.combat.knife_chain_eval import Run
from ssbot.combat.knife_chain_geometry import B2Geometry, GeometryUnavailable
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.knowledge import kinematics as K
from tests.test_knife_chain_face_hook_step import anchor, scene, step_path, load_runner, replace_plan, MOVE

FT = 1 / 60.


@pytest.fixture(autouse=True)
def plain_support(monkeypatch):
    monkeypatch.setattr(observed_slam, "ENABLED", False)    # stub supports: no exact per-frame RangeSupport rebuild


def moving_rs(body=None, haz=None, unknown=None, canvas=(0., 60.), gate=None, ymin=None):
    """Owner 9 (an attacking family: kind move) occupies hero-centre x in body=(x0, x1, vx) moving at vx u/s (y >= ymin,
    times t >= gate); owner 7's delayed hazards the y band haz=(y0, y1, t0) from t0; unknown occupancy x in unknown."""
    def own(x, y, t):
        x = np.asarray(x, float); t = np.broadcast_to(np.asarray(t, float), x.shape)
        if body is None:
            return np.zeros(x.shape, bool)
        hit = (x >= body[0] + body[2] * t) & (x <= body[1] + body[2] * t)
        if ymin is not None:
            hit &= np.asarray(y, float) >= ymin
        return hit if gate is None else hit & (t >= gate)
    def hazards(x, y, t, ids):
        y = np.asarray(y, float); t = np.broadcast_to(np.asarray(t, float), y.shape)
        if haz is None or 7 not in ids:
            return np.zeros(y.shape, bool)
        return (y >= haz[0]) & (y <= haz[1]) & (t >= haz[2])
    def occ(x, y, t):
        x = np.asarray(x, float)
        out = own(x, y, t) | hazards(x, y, t, {7})
        return out if unknown is None else out | ((x >= unknown[0]) & (x <= unknown[1]))
    return NS(k_shift=0, samples=(0, 400), margin_mode="rule", focus=7,
              trk=NS(now={8: (0, 0, NS(fam=None)), 9: (0, 0, NS(fam="CC_SLAM"))}, orphan_hazards={7: None}),
              haz_raw={}, raw={}, layers={}, bombs=None,
              cv=NS(cell=.1, index=lambda x, y: (x, y, (np.asarray(x) >= canvas[0]) & (np.asarray(x) <= canvas[1]))),
              occupied=occ, occupied_only=lambda x, y, t, ids: own(x, y, t) if 9 in ids else np.zeros(np.asarray(x).shape, bool),
              occupied_hazards=hazards)


def rand_paths(rng, n=40, origin=1000):
    out = []
    for i in range(n):
        L = int(rng.integers(1, 40))
        steps = rng.normal(0., .08, (L, 2))
        dash = rng.random(L) < .1
        steps[dash] = np.clip(steps[dash] * 15., -1.6, 1.6)          # dash-sized steps: multi-row sweeps (< 32 cells)
        c = np.vstack([[rng.uniform(20., 40.), rng.uniform(4., 9.)], np.cumsum(steps, axis=0) + 0.])
        c[1:] += c[0]
        box = np.column_stack([c[:, 0] - .25, c[:, 1] - 1.04, c[:, 0] + .25, c[:, 1] + 1.04])
        flags = np.where(rng.random(L + 1) < .15, K.F_INVULN, 0).astype(np.int64)
        stage = "continuation" if i % 3 == 0 else "transfer_hook_entry"
        o = origin + int(rng.integers(0, 12))
        out.append(NS(origin=o, stage=stage, box=box, flags=flags, check_flags=np.roll(flags, 1),
                      commands=np.zeros(L, np.int64), through=o + L))
    return out


def geo(rs, origin=1000):
    return B2Geometry(NS(rs=rs), origin, MOVE, None)


@pytest.mark.parametrize("seed", range(4))
def test_scan_batch_equals_one_scan_per_path(seed):
    rng = np.random.default_rng(seed)
    rs = moving_rs(body=(28., 31., -3.), haz=(6., 7.5, 10 * FT), unknown=(33., 38.))
    paths = rand_paths(rng)
    batch = geo(rs).scan_batch(paths)
    single = [geo(rs).scan(p) for p in paths]
    assert batch == single                                   # contacts (frame, owner, kind, label), order, coverage
    assert sum(len(s.contacts) for s in single) > 20 and {c.kind for s in single for c in s.contacts} >= {"move", "delayed", "other"}


def refusal(g, paths, batch):
    try:
        (g.scan_batch(paths) if batch else [g.scan(p) for p in paths])
    except GeometryUnavailable as exc:
        return str(exc)
    return None


@pytest.mark.parametrize("bad", [(("canvas", 3), ("sweep", 5)), (("sweep", 2), ("canvas", 4)),
                                 (("canvas", 0), ("origin", 1)), (("origin", 2), ("canvas", 6))])
def test_scan_batch_refuses_as_the_first_refusing_scan(bad):
    rng = np.random.default_rng(7)
    paths = rand_paths(rng, n=8)
    for kind, i in bad:
        p = paths[i]
        if kind == "canvas":
            p.box = p.box + np.array([80., 0., 80., 0.])
        elif kind == "sweep":
            p.box = np.vstack([p.box[:1], p.box[:1] + np.array([4., 0., 4., 0.])]); p.commands = np.zeros(1, np.int64)
            p.flags = p.flags[:2]; p.check_flags = p.check_flags[:2]
        else:
            p.origin = 990
    g = geo(moving_rs(body=(28., 31., 0.)))
    assert refusal(g, paths, True) == refusal(geo(moving_rs(body=(28., 31., 0.))), paths, False) is not None


def test_scan_batch_keeps_the_commitment_instance_guard():
    rng = np.random.default_rng(3)
    paths = rand_paths(rng, n=5)
    paths[2].stage = "commitment"
    assert refusal(geo(moving_rs()), paths, True) == refusal(geo(moving_rs()), paths, False) == \
        "h2 guard target no longer maps to the tracked slam instance"


def hook_case(rs, f=1001):
    a = anchor()                                              # P = 1003: the CLAW is sent at f = 1001 for P
    s, sim = scene(f=f)
    g = B2Geometry(NS(rs=rs), f, MOVE, None)
    return a, s, sim, g, step_path(f)


def controls_of(f=1001):
    a, s, sim, g, path = hook_case(moving_rs(), f)
    scan, controls = FH.entry_scan(g, path, {"hook_press": a}, f)
    assert scan.complete and not scan.contacts and controls
    return controls


def exact(a, sim, g, controls, f=1001):
    from ssbot.combat import knife_chain_air_native as mod
    n = mod.NativeManualAirChain(runner_factory=load_runner, probe_ref="hookentry308")
    n.reset(0, start_frame=1000)
    return [n._continuations(p, sim, g, MOVE) for p in FH.entry_bounces(sim, {"hook_press": a}, f, f / 60., controls)]


def test_open_bounce_passes_the_entry_and_the_exact_lower_bound():
    a, s, sim, g, path = hook_case(moving_rs())
    scan, controls = FH.entry_scan(g, path, {"hook_press": a}, 1001)
    failed, n = FH.entry_outs(g, sim, {"hook_press": a}, 1001, controls, 12)
    assert failed is None and n == 2 * len(controls)
    assert all((r.verdict, r.mode) == ("pass", "lower_bound") for r in exact(a, sim, g, controls))


def test_a_body_over_one_landing_after_control_rejects_where_the_lower_bound_fails():
    controls = controls_of()
    F, x, y = controls[0]
    # owner 9 over the left landing's side, above the hold height, from the first control on: the locked hook stays clear
    rs = moving_rs(body=(x - 3., x - .3, 0.), gate=(F - 1001 + 3) * FT, ymin=y - .51 + .3)
    a, s, sim, g, path = hook_case(rs)
    scan, controls = FH.entry_scan(g, path, {"hook_press": a}, 1001)
    assert scan.complete and not scan.contacts
    failed, _ = FH.entry_outs(g, sim, {"hook_press": a}, 1001, controls, 12)
    assert failed is not None and failed["kind"] == "left_landing" and failed["first"].owner_iid == 9
    i = controls.index(failed["control"])
    r = exact(a, sim, g, controls)[i]
    assert (r.verdict, r.mode) != ("pass", "lower_bound")   # the exact rule may only rescue it by a full exit


def test_a_body_falling_onto_the_bounce_rejects_both_landings():
    controls = controls_of()
    F, x, y = controls[0]
    rs = moving_rs(body=(x - 2.5, x + 2.5, 0.), gate=(F - 1001 + 4) * FT, ymin=y - .51 + .3)   # L3: a body over the bounce
    a, s, sim, g, path = hook_case(rs)
    scan, controls = FH.entry_scan(g, path, {"hook_press": a}, 1001)
    assert scan.complete and not scan.contacts
    failed, _ = FH.entry_outs(g, sim, {"hook_press": a}, 1001, controls, 12)
    assert failed is not None and failed["first"].owner_iid == 9
    r = exact(a, sim, g, controls)[controls.index(failed["control"])]
    assert r.verdict != "pass"


def test_entry_exempts_the_target_body_only_inside_its_hooked_window():
    a, s, sim, g, path = hook_case(moving_rs())
    windows = [w for _, w, _ in FH._entry(path, {"hook_press": a}, 1001)]
    assert min(lo for lo, _ in windows) == a["P"] + 17                       # strike.HOOK_BODY_OFF from the press
    inside = (max(lo for lo, _ in windows), min(hi for _, hi in windows))  # every variant's window
    class Geo:      # the target (8) body on every frame of every variant
        def scan_batch(self, paths):
            from ssbot.combat.knife_chain_commitment import ContactScan, PathContact
            return [ContactScan("t", p.origin, p.through, tuple(PathContact(p.origin + k, 8, "body")
                                for k in range(len(p.commands) + 1)), "fixed") for p in paths]
    scan, _ = FH.entry_scan(Geo(), path, {"hook_press": a}, 1001)
    assert scan.contacts and all(c.owner_iid == 8 and c.kind == "body" for c in scan.contacts)
    assert min(c.frame for c in scan.contacts) < a["P"] + 17         # before the earliest hooked-body window
    assert not any(inside[0] <= c.frame <= inside[1] for c in scan.contacts)


def offer_case(monkeypatch, rs, f=1001):
    from ssbot.combat import knife_chain_air_native as mod
    from ssbot.combat.knife_chain_air import AirAnchor
    from ssbot.combat.claw_strike import CsPlan
    a = anchor()
    P = a["P"]
    n = mod.NativeManualAirChain(runner_factory=load_runner, probe_ref="hookentry308")
    n.reset(0, start_frame=1000)
    p = replace_plan(f)
    v = {**dict(load_runner().chains["rune_transfer"].vars), **p.variables(), "cs": CsPlan(P - 1, 0, P, 0), "hook_press": a}
    n.runner.run = Run("rune_transfer", "claw", dict(v))
    draft = load_runner().fork_empty(AirAnchor())
    draft.run = Run("rune_transfer", "claw", dict(v))
    path = step_path(f)
    monkeypatch.setattr(mod.transfer, "propose", lambda *a_, **kw: (draft, p, path, 0))
    monkeypatch.setattr(n, "queued_prefix", lambda *a_: (0, "fixture"))
    n._hook_start = None                                     # the CLAW is not sent yet: the whole hook is committed now
    n.commitment = {"move": MOVE, "origin": P - 2, "ta": p.ta}
    n._context = (None, None, None, None)
    recovered = []
    monkeypatch.setattr(n, "_recover", lambda reason, frame: recovered.append(reason))
    st, sim = scene(f=f)
    notes = []
    real = n._note
    monkeypatch.setattr(n, "_note", lambda ev, **kw: (notes.append((ev, kw)), real(ev, **kw))[1])
    offer = n._transfer_offer(st, f / 60., sim, NS(rs=rs), NS(target=8), False)
    return offer, recovered, dict(notes)


def test_transfer_offer_admits_a_hook_with_an_open_bounce(monkeypatch):
    offer, recovered, notes = offer_case(monkeypatch, moving_rs())
    note = notes["transfer_hook_entry_checked"]
    assert offer is not None and not recovered
    assert note["contacts"] == 0 and note["complete"] and note["bounce_paths"] == 2 * note["controls"] > 0


def test_transfer_offer_rejects_a_hook_whose_bounce_meets_a_falling_body(monkeypatch):
    F, x, y = controls_of()[0]
    offer, recovered, notes = offer_case(monkeypatch, moving_rs(body=(x - 2.5, x + 2.5, 0.), gate=(F - 1001 + 4) * FT,
                                                               ymin=y - .51 + .3))
    note = notes["transfer_hook_entry_checked"]
    assert offer is None and recovered == ["rune transfer external step blocked"]
    assert note["first"]["owner_iid"] == 9 and "forced bounce at control" in note["source"]
    assert notes["rune_transfer_rejected"]["first"]["owner_iid"] == 9


@pytest.mark.parametrize("gap,dash", [(10., True), (4.5, False)])
def test_hook_release_decides_the_air_dash_again_from_the_actual_post_hook_state(gap, dash):
    """Task 179 #308 (live L3 2713: target in Evade Scuttle, can.dash and the tracker's AIRDASHED 0 / DASH_CD 0): the
    pre-hook "no air dash after an aimed hook" is not carried across the lock; the air link's probe decides again (far:
    the coast does not reach above the body, so the one air dash; near: no dash), and B2's dash-lock scan still gates it."""
    from ssbot.combat.claw_strike import CsPlan
    from ssbot.combat.knife_chain_format import MASK_NAMES as B
    from tests.test_knife_chain_face_hook import runner_with, step
    cs = CsPlan(988, 0, 989, 0)                                   # F = 1002: 13 frames after P, actual control
    r = runner_with("claw_lock", cs=cs, hook_seen_f=cs.f_press + 2, hook_hit_f=cs.f_press + 8,
                    air_dash_decided=True, approach_recipe=None)
    made, _ = step(r, 1000, gap=gap)
    run = made[0].run
    assert run.v["hook_done"] and run.link == "air"
    assert bool(run.v["air_dash_decided"]) is dash        # near: the probe does not run (no stale True either)
    assert bool(made[3] & B["DASH"]) is dash and (run.v["approach_recipe"] == "air_dash") is dash
