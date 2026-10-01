"""Frozen-state unpause check (DESIGN §3.7.5 unpause rules) against stand-in threat tubes."""
from ssbot.safety import unpause_check as uc
from ssbot.safety.invariants import is_commit_zone
from ssbot.safety.unpause_check import FrozenState, UnpauseTiming, check_unpause, resume_decision

HERO = FrozenState(hero_box=(80.0, 3.57, 80.46, 5.82))      # standing hurtbox 0.4554 x 2.2498 (m0 §2.5)


def tube_box(box, t_from: float, t_to: float = 99.0):
    """A tube occupying `box` from t_from to t_to seconds after the unpause."""
    def reaches(b, t0, t1):
        overlap_t = t0 < t_to and t1 > t_from
        return overlap_t and b[0] < box[2] and b[2] > box[0] and b[1] < box[3] and b[3] > box[1]
    return reaches


def test_horizon_is_lockout_latency_margin_and_hide_menu():
    t = UnpauseTiming(input_latency_s=0.05)
    assert abs(t.horizon_s - (0.3 + 0.05 + 0.1 + 0.2)) < 1e-12


def test_a_tube_inside_the_horizon_blocks_the_unpause():
    charge = tube_box((80.3, 3.5, 84.0, 6.0), 0.5)               # the charge arrives 0.5 s in, horizon 0.65 s
    v = check_unpause(HERO, charge)
    assert not v.ok and abs(v.first_reach_s - 0.5) < 1 / 30 + 1e-9
    assert check_unpause(HERO, tube_box((80.3, 3.5, 84.0, 6.0), 0.8)).ok      # after the horizon
    assert check_unpause(HERO, tube_box((90.0, 3.5, 92.0, 6.0), 0.0)).ok      # never near


def test_inflation_and_drift_count():
    near = tube_box((80.55, 3.5, 81.0, 6.0), 0.0)                 # 0.09 u right of the hurtbox
    assert not check_unpause(HERO, near).ok                       # inside the 0.15 u margin
    assert check_unpause(HERO, near, inflate_u=0.05).ok
    far_right = tube_box((82.0, 3.5, 83.0, 6.0), 0.3)
    assert check_unpause(HERO, far_right).ok
    drifting = FrozenState(HERO.hero_box, hero_vel=(4.0, 0.0))    # 4 u/s for up to 0.65 s reaches x 83
    assert not check_unpause(drifting, far_right).ok
    below = tube_box((79.0, -5.0, 82.0, 0.0), 0.0)                # a fall of 30 u/s covers it within the horizon
    airborne = FrozenState((80.0, 10.0, 80.46, 11.77), hero_vel=(0.0, 8.0))
    assert not check_unpause(airborne, below).ok


def test_resume_decision_and_zone():
    assert resume_decision(3, True, True) == uc.RESUME
    assert resume_decision(2, True, True) == uc.QUIT
    assert resume_decision(3, False, False) == uc.STAY_ALERT
    z = uc.unpause_zone("Bone_05")
    assert z.kind == "unpause_lockout" and z.seconds == 0.3 and is_commit_zone(z)
