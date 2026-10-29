"""Raw evidence must fail closed before any model-coverage claim."""
import pytest

from ssbot.tools.forum_knife_claw_audit import body_box, require_frames


def state(f, dt=1 / 60, fs=1):
    return {"f": f, "dt": dt, "udt": 1 / 60, "fs": fs, "act": {"mask": 0}}


def test_zero_scaled_time_is_preserved_and_gap_is_rejected():
    frames = [state(4), state(5, dt=0, fs=0), state(6)]
    assert require_frames(frames, 4, 6)[5]["dt"] == 0
    with pytest.raises(ValueError, match="gap"):
        require_frames([frames[0], frames[2]], 4, 6)


def test_duplicate_frame_is_not_silently_overwritten():
    with pytest.raises(ValueError, match="duplicate"):
        require_frames([state(4), state(4)], 4, 4)


@pytest.mark.parametrize("field,value", [("dt", None), ("udt", float("nan")), ("fs", 0.5)])
def test_unknown_timing_is_not_invented(field, value):
    row = state(4)
    row[field] = value
    with pytest.raises(ValueError):
        require_frames([row], 4, 4)


def test_target_identity_and_root_body_exclude_range_trigger():
    root = {"kind": "box", "name": "Song Heavy Sentry", "layer": 11, "enabled": True,
            "damage": {"dealt": 0}, "verts_world": [2, 3, 4, 3, 4, 6, 2, 6]}
    trigger = dict(root, name="Slam Range", layer=13, verts_world=[-10, 0, 10, 0, 10, 20, -10, 20])
    row = {"ents": [{"iid": 7, "colliders": [root, trigger]},
                    {"iid": 8, "colliders": [dict(root, verts_world=[50, 3, 60, 3, 60, 6, 50, 6])]}]}
    assert body_box(row, 7).tolist() == [2, 3, 4, 6]
    with pytest.raises(ValueError, match="missing"):
        body_box(row, 9)
    row["ents"][0]["colliders"].append(dict(root))
    with pytest.raises(ValueError, match="one root"):
        body_box(row, 7)
