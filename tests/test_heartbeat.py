"""Мок heartbeat-потока оркестратора (шаг C): пока claude -p блокирующе исполняется, фон-поток
бьёт bc.task_heartbeat; после возврата поток останавливается; ошибки heartbeat глушатся (не валят задачу).
Сеть/subprocess замоканы; HEARTBEAT_SEC ужат до миллисекунд."""
import sys, time, threading, json
sys.path.insert(0, "/root/turbobaby-manager-bot")
import os
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")  # изоляция от боевого .env (адаптация плана, кусок 2)
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (куратор целей, родитель 231; принудительно — env демона)
import orchestrator_daemon as D

_DONE_JSON = json.dumps({"result": "готово", "is_error": False,
                         "modelUsage": {"claude-fable-5": {}}})

class FakeBC:
    def __init__(s, raise_hb=False):
        s.hb = 0; s.raise_hb = raise_hb; s.lock = threading.Lock()
    def task_heartbeat(s, tid):
        with s.lock:
            s.hb += 1
        if s.raise_hb:
            raise RuntimeError("bridge down")
        return {"ok": True}


class _FakePopen:
    def __init__(s, sleep_s=0, out=None, rc=0, raise_timeout=False):
        s.returncode = None; s._sleep = sleep_s
        s._out = out if out is not None else _DONE_JSON
        s._rc = rc; s._raise_timeout = raise_timeout; s._calls = 0
    def communicate(s, timeout=None):
        s._calls += 1
        if s._calls == 1 and s._raise_timeout:
            time.sleep(s._sleep)
            raise D.subprocess.TimeoutExpired(cmd="claude", timeout=600)
        if s.returncode is None: s.returncode = s._rc
        time.sleep(s._sleep)
        return s._out, ""
    def terminate(s): s.returncode = -15
    def kill(s): s.returncode = -9; s._raise_timeout = False
    def poll(s): return s.returncode


def _patch_popen(sleep_s, out=None, rc=0, raise_timeout=False):
    def popen(args, **kw):
        return _FakePopen(sleep_s, out=out, rc=rc, raise_timeout=raise_timeout)
    return popen


_real_POPEN = D._POPEN


# C1: heartbeat бьётся в фоне, пока subprocess «работает» (>=1 удар), задача done
def test_heartbeat_fires_during_run():
    D.HEARTBEAT_SEC = 0.02
    fake = FakeBC(); D.bc = fake
    D._POPEN = _patch_popen(0.2)
    status, result = D.run_task(1, "просто почитай логи")
    assert status == "done", (status, result)
    assert fake.hb >= 1, f"heartbeat должен удариться хотя бы раз: {fake.hb}"


# C2: после возврата subprocess поток ОСТАНАВЛИВАЕТСЯ (счётчик не растёт)
def test_heartbeat_stops_after_return():
    D.HEARTBEAT_SEC = 0.02
    fake = FakeBC(); D.bc = fake
    D._POPEN = _patch_popen(0.15)
    D.run_task(2, "task")
    n1 = fake.hb
    time.sleep(0.2)              # если бы поток не остановился — счётчик бы вырос
    assert fake.hb == n1, f"после возврата heartbeat обязан стоять: было {n1}, стало {fake.hb}"


# C3: ошибки heartbeat ГЛУШАТСЯ — задача всё равно завершается done (не падает из-за heartbeat)
def test_heartbeat_errors_swallowed():
    D.HEARTBEAT_SEC = 0.02
    fake = FakeBC(raise_hb=True); D.bc = fake
    D._POPEN = _patch_popen(0.15)
    status, result = D.run_task(3, "task")
    assert status == "done", (status, result)
    assert fake.hb >= 1, "heartbeat пытался бить, но падал — это не должно ронять задачу"


# C4: таймаут claude -p → failed, но heartbeat всё равно корректно остановлен (finally)
def test_heartbeat_stopped_on_timeout():
    D.HEARTBEAT_SEC = 0.02
    fake = FakeBC(); D.bc = fake
    D._POPEN = _patch_popen(0.1, raise_timeout=True)
    status, result = D.run_task(4, "task")
    assert status == "failed" and "таймаут" in result, (status, result)
    n1 = fake.hb
    time.sleep(0.15)
    assert fake.hb == n1, "на таймауте finally обязан остановить heartbeat-поток"


D._POPEN = _real_POPEN

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов heartbeat-потока (шаг C)")
