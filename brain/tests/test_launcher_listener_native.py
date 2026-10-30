"""Windows PID_LISTENER membership and fail-closed native-table parsing.

Live controls use only owned ephemeral sockets, never a game/Oracle socket.
"""
import ctypes
import os
import socket
import struct
import sys
from types import SimpleNamespace
import pytest
from ssbot.tools import launcher as L


def packet(*rows):
    return struct.pack("=I",len(rows))+b"".join(struct.pack("=6I",*row) for row in rows)


def row(pid=123,port=47017,state=0):
    addr=int.from_bytes(socket.inet_aton("127.0.0.1"),sys.byteorder)
    return (state,addr,socket.htons(port),0,0,pid)


class FakeApi:
    def __init__(self,payload,*,size_rc=122,data_rc=0,returned_size=None,grow=0):
        self.payload=payload;self.size_rc=size_rc;self.data_rc=data_rc;self.returned_size=returned_size
        self.grow=grow;self.calls=[]
    def __call__(self,buf,size,order,family,kind,reserved):
        self.calls.append((buf is None,order,family,kind,reserved))
        assert family==socket.AF_INET and kind==3 and reserved==0 and order is False
        n=ctypes.cast(size,ctypes.POINTER(ctypes.c_uint32))
        if buf is None:n[0]=len(self.payload);return self.size_rc
        if self.grow:n[0]+=self.grow;return 122
        ctypes.memmove(buf,self.payload,min(len(buf),len(self.payload)))
        n[0]=len(self.payload) if self.returned_size is None else self.returned_size
        return self.data_rc


def query(monkeypatch,api):
    monkeypatch.setattr(L,"_get_tcp_table_api",lambda:api)
    return L._windows_listener_rows()


def test_native_listener_table_membership_retains_zero_raw_state(monkeypatch):
    api=FakeApi(packet(row(),row(999,47018,2)))
    rows=query(monkeypatch,api)
    assert rows==[{"pid":123,"ip":"127.0.0.1","port":47017,"raw_state":0},
                  {"pid":999,"ip":"127.0.0.1","port":47018,"raw_state":2}]
    assert len(api.calls)==2 and ctypes.sizeof(L._TcpOwnerPidRow)==24
    monkeypatch.setattr(L,"_listener_rows",L._windows_listener_rows)
    monkeypatch.setattr(socket,"create_connection",lambda *a,**k:pytest.fail("active Oracle probe"))
    assert L.port_listening(47017,123) and not L.port_listening(47017,999)
    assert not L.port_listening(47019,123)
    report=L.listener_snapshot(47017,123)
    assert report["matches_expected"] and report["listeners"][0]["raw_state"]==0
    assert "raw_status" not in report["listeners"][0] and report["transport_probe"]=="none"
    if sys.platform=="win32":
        assert report["provider"]=="GetExtendedTcpTable" and report["table_class_id"]==3
        assert report["table_class"]=="TCP_TABLE_OWNER_PID_LISTENER"


@pytest.mark.parametrize("payload,returned_size",[
    (b"",None),                         # absent count header
    (struct.pack("=I",1),None),          # count says a missing complete row
    (struct.pack("=I",2)+packet(row())[4:]+b"x"*12,None), # second row truncated
    (packet(row()),3),                  # returned size below header
    (packet(row()),999),                # returned size above allocated buffer
    (struct.pack("=I",0xffffffff),None), # malicious count cannot run beyond the buffer
])
def test_incomplete_or_invalid_table_fails_closed(monkeypatch,payload,returned_size):
    api=FakeApi(payload,returned_size=returned_size)
    monkeypatch.setattr(L,"_get_tcp_table_api",lambda:api)
    monkeypatch.setattr(L,"_listener_rows",L._windows_listener_rows)
    assert not L.port_listening(47017,123)
    report=L.listener_snapshot(47017,123)
    assert report["query_error"] and not report["matches_expected"] and not report["listeners"]


@pytest.mark.parametrize("size_rc,data_rc",[(5,0),(87,0),(122,5),(122,87)])
def test_native_api_failure_does_not_fall_back_to_psutil_none(monkeypatch,size_rc,data_rc):
    api=FakeApi(packet(row()),size_rc=size_rc,data_rc=data_rc)
    monkeypatch.setattr(L,"_get_tcp_table_api",lambda:api)
    monkeypatch.setattr(L,"_listener_rows",L._windows_listener_rows)
    monkeypatch.setattr(L,"_psutil_listener_rows",lambda:pytest.fail("native error must fail closed"))
    assert not L.port_listening(47017,123)
    report=L.listener_snapshot(47017,123)
    assert report["query_error"] and not report["matches_expected"]


def test_insufficient_buffer_has_at_most_three_fill_attempts(monkeypatch):
    api=FakeApi(packet(),grow=24)
    with pytest.raises(OSError,match="3 attempts"):query(monkeypatch,api)
    assert len(api.calls)==4  # one size query, then no more than three fill retries


def test_buffer_growth_retry_then_complete_success(monkeypatch):
    payload=packet(row());calls=[]
    def api(buf,size,order,family,kind,reserved):
        n=ctypes.cast(size,ctypes.POINTER(ctypes.c_uint32));calls.append(buf is None)
        if len(calls)==1:n[0]=4;return 122
        if len(calls)==2:n[0]=len(payload);return 122
        ctypes.memmove(buf,payload,len(payload));n[0]=len(payload);return 0
    assert query(monkeypatch,api)[0]["pid"]==123 and len(calls)==3


def test_oversized_buffer_is_refused_before_allocation(monkeypatch):
    def api(buf,size,*a):
        assert buf is None
        ctypes.cast(size,ctypes.POINTER(ctypes.c_uint32))[0]=L._TCP_TABLE_BUFFER_LIMIT+1
        return 122
    with pytest.raises(OSError,match="buffer size"):query(monkeypatch,api)


def test_psutil_backend_still_requires_explicit_listen(monkeypatch):
    import psutil
    c=SimpleNamespace(pid=123,status=psutil.CONN_NONE,laddr=SimpleNamespace(ip="127.0.0.1",port=47017))
    monkeypatch.setattr(psutil,"net_connections",lambda **kw:[c])
    assert L._psutil_listener_rows()==[]


@pytest.mark.skipif(sys.platform!="win32",reason="native Windows table control")
def test_native_api_signature_and_owned_live_positive_negative_controls():
    api=L._get_tcp_table_api()
    assert api.argtypes==[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint32),ctypes.c_int32,
                          ctypes.c_uint32,ctypes.c_int32,ctypes.c_uint32]
    assert api.restype==ctypes.c_uint32
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as live, socket.socket(socket.AF_INET,socket.SOCK_STREAM) as bound:
        live.bind(("127.0.0.1",0));live.listen();port=live.getsockname()[1]
        bound.bind(("127.0.0.1",0));not_listening=bound.getsockname()[1]
        assert live.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN)==1
        assert bound.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN)==0
        assert L.port_listening(port,os.getpid())
        assert not L.port_listening(port,os.getpid()+1)
        assert not L.port_listening(not_listening,os.getpid())
        report=L.listener_snapshot(port,os.getpid())
        assert report["matches_expected"] and report["table_class_id"]==3
        assert report["provider"]=="GetExtendedTcpTable" and report["query_error"] is None
        assert "raw_state" in report["listeners"][0]
    assert not L.port_listening(port,os.getpid())
