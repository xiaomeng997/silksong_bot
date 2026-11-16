"""Optional batch-scoped display request. Never execute without fresh user authorization.

Does not change a power plan, service, driver, keyboard or mouse. Uses the calling
thread's power request, released at exit. The owning coordinator is checked by
PID plus creation time, not PID alone; a batch stop/end also releases the request.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import time
import psutil

CONTINUOUS = 0x80000000
REQUIRED = CONTINUOUS | 0x00000001 | 0x00000002


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def alive(identity):
    try:
        p = psutil.Process(identity['pid'])
        return abs(p.create_time()-identity['created']) < .01 and 'run_unattended.py' in ' '.join(p.cmdline())
    except psutil.NoSuchProcess:
        return False


def run(analysis, power, me, *, clock=time.monotonic, sleep=time.sleep, owner_alive=alive):
    analysis = Path(analysis)
    auth = read(analysis/'USER_NEW50_AUTHORIZATION.json')
    assert auth.get('batch_id') == analysis.name and auth.get('planned_bouts') == 50
    assert auth.get('kind') == 'explicit_user_chat_unattended_new50'
    assert auth.get('display_awake_for_this_batch') is True, 'fresh explicit display authorization required'
    assert auth.get('user_text') and auth.get('reopen_stopped_batches') is False
    assert not (analysis/'DISPLAY_HOLD_READY.json').exists(), 'one holder per fresh batch'
    assert not (analysis/'COORDINATOR_END.json').exists() and not (analysis/'DISPLAY_HOLD_STOP').exists()
    started = clock()
    held = False
    reason = None
    error = None
    try:
        if not power(REQUIRED):
            raise OSError('SetThreadExecutionState failed')
        held = True
        receipt = dict(at=datetime.now(timezone.utc).isoformat(), pid=me['pid'], created=me['created'],
                       source=auth['source'], batch=analysis.name, active=True, maximum_seconds=7200)
        with (analysis/'DISPLAY_HOLD_READY.json').open('x',encoding='utf-8') as f:
            json.dump(receipt,f)
        while True:
            elapsed = clock()-started
            if (analysis/'DISPLAY_HOLD_STOP').exists():
                reason = 'stop';break
            if (analysis/'COORDINATOR_END.json').exists():
                reason = 'batch ended';break
            launch = analysis/'ROOT_LAUNCH_RECEIPT.json'
            if launch.exists():
                identity = read(launch)
                if identity['source'] != auth['source'] or identity['batch_id'] != analysis.name or not owner_alive(identity):
                    reason = 'own coordinator exited or identity mismatch';break
            elif elapsed >= 120:
                reason = 'coordinator not started in120s';break
            if elapsed >= 7200:
                reason = 'maximum duration';break
            sleep(1)
    except BaseException as exc:
        error = repr(exc)
        raise
    finally:
        released = bool(power(CONTINUOUS)) if held else True
        with (analysis/'DISPLAY_HOLD_CLOSED.json').open('x',encoding='utf-8') as f:
            json.dump(dict(at=datetime.now(timezone.utc).isoformat(),pid=me['pid'],created=me['created'],
                           held=held,released=released,reason=reason,error=error),f)
        if held and not released:
            raise OSError('explicit power-request release failed; thread exit still ends the request')


if __name__ == '__main__':
    import ctypes
    import sys
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    power = kernel.SetThreadExecutionState
    power.argtypes = [ctypes.c_uint32]
    power.restype = ctypes.c_uint32
    me = psutil.Process()
    run(sys.argv[1],power,dict(pid=me.pid,created=me.create_time()))
