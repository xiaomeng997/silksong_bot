"""B2 input configuration is observed, never repaired during preflight."""
from copy import deepcopy
import json
from types import SimpleNamespace
import pytest
from ssbot.combat.knife_chain_input import capture_input_path, validate_input_path


def stats():
    return {"latency":{"delay_frames":0,"jitter_frames":0,"dist":None},
            "hold":{"min_press_frames":2,"min_release_frames":2},"pending":0}


@pytest.mark.parametrize("section,key,value",[
    ("latency","delay_frames",1),("latency","delay_frames",False),
    ("latency","jitter_frames",1),("latency","jitter_frames",0.),
    ("latency","dist",[]),("latency","dist",[[0,1.]]),
    ("hold","min_press_frames",1),("hold","min_release_frames",3),
    (None,"pending",1),(None,"pending",False),
    (None,"latency",None),(None,"hold",None),
])
def test_unknown_or_different_configuration_is_rejected(section,key,value):
    raw=stats()
    target=raw if section is None else raw[section]
    target[key]=value
    before=deepcopy(raw)
    with pytest.raises(ValueError,match="input.stats"):
        validate_input_path(raw)
    assert raw==before


def test_missing_and_nonmap_are_unknown():
    for raw in (None,[],{}, {"latency":{},"hold":{}}):
        with pytest.raises(ValueError):validate_input_path(raw)


def test_success_is_read_only_exclusive_and_tied_to_supplied_connection(tmp_path):
    calls=[];raw=stats();before=deepcopy(raw)
    def rpc(method,**kwargs):calls.append((method,kwargs));return raw
    link=SimpleNamespace(sock=SimpleNamespace(getpeername=lambda:("127.0.0.1",47018)),frame=123,rpc=rpc)
    path=tmp_path/"receipt.json"
    result=capture_input_path(link,path,instance=1)
    assert json.loads(path.read_text())==result
    assert result["passed"] and result["instance"]==1 and result["peer"]==["127.0.0.1",47018]
    assert calls==[("input.stats",{"timeout_s":10.})] and raw==before
    original=path.read_bytes()
    with pytest.raises(FileExistsError):capture_input_path(link,path,instance=1)
    assert path.read_bytes()==original and len(calls)==1
