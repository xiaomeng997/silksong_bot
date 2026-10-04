"""combat_run's configuration fingerprint: the SSBOT_* switches (SSBOT_POST_CLEAR_S turns the post-kill tail off,
SSBOT_DEAD_ATK=0 brings back the old post-death forecast) change it, no switches keep the old hash, and `summary`
refuses to pool rows of different fingerprints unless --mixed (post_kill.md, the fixer round's config_fp finding)."""
import json

from ssbot.tools.combat_run import config_fp, env_overrides, main, summary


def test_without_switches_the_fingerprint_is_the_old_hash():
    # the 200-episode run 20261004_065707 (fd18ae6), written before the switches were part of it
    assert config_fp("BellBeast", "planner", "eval", "oracle", "fd18ae6") == "e4a26680c027"
    assert config_fp("BellBeast", "planner", "eval", "oracle", "fd18ae6", {}) == "e4a26680c027"


def test_a_switch_changes_the_fingerprint():
    base = config_fp("BellBeast", "planner", "eval", "oracle", "fd18ae6")
    tail_off = config_fp("BellBeast", "planner", "eval", "oracle", "fd18ae6", {"SSBOT_POST_CLEAR_S": "2.5"})
    old_fc = config_fp("BellBeast", "planner", "eval", "oracle", "fd18ae6", {"SSBOT_DEAD_ATK": "0"})
    assert len({base, tail_off, old_fc}) == 3


def test_env_overrides_takes_only_the_ssbot_switches():
    env = {"PATH": "x", "SSBOT_DEAD_ATK": "0", "SSBOT_POST_CLEAR_S": "2.5", "NUMBA_NUM_THREADS": "4"}
    assert env_overrides(env) == {"SSBOT_DEAD_ATK": "0", "SSBOT_POST_CLEAR_S": "2.5"}
    assert env_overrides({"PATH": "x"}) == {}


def _run(tmp_path, name: str, fp: str, n: int = 2):
    d = tmp_path / name
    d.mkdir()
    rows = [{"unit": "BellBeast", "mode": "eval", "outcome": "CLEAR", "config_fp": fp, "ingame_s": 60.0 + k,
             "wall_s": 70.0, "hits": 0, "would_die": 0, "reason": None} for k in range(n)]
    (d / "attempts_i0.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return d


def test_summary_pools_only_one_fingerprint(tmp_path, capsys):
    a = _run(tmp_path, "a", "e4a26680c027")
    b = _run(tmp_path, "b", "e4a26680c027", n=3)
    c = _run(tmp_path, "c", "0123456789ab")
    out = summary(a, [b], write=False)
    assert out["episodes"] == 5 and out["outcomes"] == {"CLEAR": 5} and out["config_fp"] == {"e4a26680c027": 5}
    out = summary(a, [c], write=False)
    assert "refused" in out and out["config_fp"] == {"e4a26680c027": 2, "0123456789ab": 2} and "outcomes" not in out
    assert main(["summary", str(a), str(c)]) == 1
    assert main(["summary", str(a), str(c), "--mixed"]) == 0
    out = summary(a, [c], write=False, mixed=True)
    assert out["episodes"] == 4 and out["outcomes"] == {"CLEAR": 4}
