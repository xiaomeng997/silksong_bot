from ssbot.probes import mem_growth as mg


def _s(loads, mono, private, objects, fsm=10):
    return {"loads": loads, "mem": {"gc_total": mono * 2**20, "mono_used": mono * 2**20, "oracle": {"fsm_infos": fsm, "ents": {"included": 1, "flag": True}},
                                    "objects": {"Object": objects}}, "proc": {"private_mb": private}}


def test_flatten_units_and_keys():
    f = mg.flatten(_s(0, 50, 2400, 1000))
    assert f["mono_used"] == 50 and f["private_mb"] == 2400 and f["obj.Object"] == 1000
    assert f["fsm_infos"] == 10 and f["ents.included"] == 1 and "ents.flag" not in f


def test_slopes_per_100_loads():
    samples = [_s(0, 50, 2400, 1000), _s(100, 51, 2405, 1010), _s(200, 52, 2410, 1020)]
    per = mg.slopes(samples)
    assert abs(per["mono_used"] - 1.0) < 1e-9 and abs(per["private_mb"] - 5.0) < 1e-9
    assert abs(per["obj.Object"] - 10.0) < 1e-9 and per["fsm_infos"] == 0.0
    assert mg.slopes(samples[:1]) == {}
