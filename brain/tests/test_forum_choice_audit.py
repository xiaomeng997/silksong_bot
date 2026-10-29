"""Audit transport must preserve raw arrays and reject malformed payloads."""
import json
import numpy as np
import pytest
from ssbot.tools.forum_choice_audit import freeze, thaw, key_names


def test_copied_rank_inputs_survive_later_array_mutation():
    a = np.array([[1.0, np.inf], [np.nan, -0.0]], dtype=np.float64)
    saved = freeze({"keys": (a,), "missing": None})
    a[:] = 19
    wire = json.dumps(saved, allow_nan=False)
    b = thaw(json.loads(wire))["keys"][0]
    assert b[0, 0] == 1 and np.isposinf(b[0, 1]) and np.isnan(b[1, 0])
    assert np.signbit(b[1, 1]) and b.dtype == np.float64
    assert thaw(json.loads(wire))["missing"] is None


def test_malformed_array_is_rejected():
    payload = freeze(np.arange(3, dtype=np.int64))
    payload["shape"] = [4]
    with pytest.raises(ValueError, match="byte count"):
        thaw(payload)
    payload["dtype"] = "O"
    with pytest.raises(ValueError, match="object"):
        thaw(payload)


def test_preference_schema_drift_is_not_silently_mislabeled():
    from types import SimpleNamespace
    loc = dict(v2=True, _audit_noglide=True, gf_=(), wk_=(), nd_=(np.zeros(1),),
               kk_=(), prefs=SimpleNamespace(no_dash=()), npg_=(), rx_=(), sc={})
    with pytest.raises(ValueError, match="preference key schema"):
        key_names(loc, 24)
