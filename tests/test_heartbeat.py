"""Мок heartbeat-потока оркестратора (шаг C): пока claude -p блокирующе исполняется, фон-поток
бьёт bc.task_heartbeat; после возврата поток останавливается; ошибки heartbeat глушатся (не валят задачу).
Сеть/subprocess замоканы; HEARTBEAT_SEC ужат до миллисекунд."""
import sys, time, types, threading
sys.path.insert(0, "/root/turbobaby-manager-bot")
import os
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import orchestrator_daemon as D


class FakeBC:
    def __init__(s, raise_hb=False):
        s.hb = 0; s.raise_hb = raise_hb; s.lock = threading.Lock()
    def task_heartbeat(s, tid):
        with s.lock:
            s.hb += 1
        if s.raise_hb:
            raise RuntimeError("bridge down")
        return {"ok": True}


def _fake_proc(rc=0, out="ok", err=""):
    p = types.SimpleNamespace(); p.returncode = rc; p.stdout = out; p.stderr = err
    return p


def _patch_run(sleep_s, proc=None, exc=None):
    def run(*a, **k):
        time.sleep(sleep_s)
        if exc:
            raise exc
        return proc or _fake_proc()
    return run


# C1: heartbeat бьётся в фоне, пока subprocess «работает» (>=1 удар), задача done
def test_heartbeat_fires_during_run():
    D.HEARTBEAT_SEC = 0.02
    fake = FakeBC(); D.bc = fake
    D.subprocess.run = _patch_run(0.2, _fake_proc(0, "готово"))
    status, result = D.run_task(1, "просто почитай логи")
    assert status == "done", (status, result)
    assert fake.hb >= 1, f"heartbeat должен удариться хотя бы раз: {fake.hb}"


# C2: после возврата subprocess поток ОСТАНАВЛИВАЕТСЯ (счётчик не растёт)
def test_heartbeat_stops_after_return():
    D.HEARTBEAT_SEC = 0.02
    fake = FakeBC(); D.bc = fake
    D.subprocess.run = _patch_run(0.15, _fake_proc(0, "ок"))
    D.run_task(2, "task")
    n1 = fake.hb
    time.sleep(0.2)              # если бы поток не остановился — счётчик бы вырос
    assert fake.hb == n1, f"после возврата heartbeat обязан стоять: было {n1}, стало {fake.hb}"


# C3: ошибки heartbeat ГЛУШАТСЯ — задача всё равно завершается done (не падает из-за heartbeat)
def test_heartbeat_errors_swallowed():
    D.HEARTBEAT_SEC = 0.02
    fake = FakeBC(raise_hb=True); D.bc = fake
    D.subprocess.run = _patch_run(0.15, _fake_proc(0, "результат"))
    status, result = D.run_task(3, "task")
    assert status == "done", (status, result)
    assert fake.hb >= 1, "heartbeat пытался бить, но падал — это не должно ронять задачу"


# C4: таймаут claude -p → failed, но heartbeat всё равно корректно остановлен (finally)
def test_heartbeat_stopped_on_timeout():
    D.HEARTBEAT_SEC = 0.02
    fake = FakeBC(); D.bc = fake
    D.subprocess.run = _patch_run(0.1, exc=D.subprocess.TimeoutExpired(cmd="claude", timeout=600))
    status, result = D.run_task(4, "task")
    assert status == "failed" and "таймаут" in result, (status, result)
    n1 = fake.hb
    time.sleep(0.15)
    assert fake.hb == n1, "на таймауте finally обязан остановить heartbeat-поток"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов heartbeat-потока (шаг C)")
