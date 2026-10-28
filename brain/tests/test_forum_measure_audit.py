from ssbot.tools.forum_measure_audit import audit_window


def states():
    return [{"f": f, "dt": .1, "hero": {"health": 7 if f < 12 else 5, "health_blue": 0},
             "ev": [{"f": 12, "q": 12, "k": "hp", "d": {"delta": -2, "blue_delta": 0}},
                    {"f": 12, "q": 13, "k": "would_die", "d": {}}] if f == 12 else []}
            for f in range(9, 13)]


def test_tail_lethal_and_losses_do_not_rewrite_the_earlier_primary_endpoint():
    measured = {"end_f": 11, "end_reason": "targets_dead", "T": .2, "complete": True,
                "target_ids": [], "tail_end_f": 12, "tail_end_reason": "episode_would_die"}
    result = audit_window(states(), measured, {"f_wake": 10, "unit": "Forum_W_w7", "outcome": "WOULD_DIE"})
    assert result["complete"] and result["success"] and result["K_star"] == .2
    assert result["metrics"]["L"] == 0 and result["tail"]["metrics"]["L"] == 2
    assert len(result["tail"]["lethal_events"]) == 1
    assert result["episode_outcome"] == "WOULD_DIE"


def test_lethal_primary_is_a_failure_and_unobserved_tail_is_incomplete():
    measured = {"end_f": 11, "end_reason": "lethal", "T": .2, "complete": True,
                "target_ids": [], "tail_end_f": 11, "tail_end_reason": "lethal"}
    attempt = {"f_wake": 10, "unit": "Forum_W_w13", "outcome": "WOULD_DIE"}
    result = audit_window(states(), measured, attempt)
    assert result["complete"] and not result["success"] and result["K_star"] == 120
    assert result["tail"] is None
    measured.update(end_reason="targets_dead", tail_end_reason="episode_harness_fail")
    assert not audit_window(states(), measured, attempt)["complete"]
