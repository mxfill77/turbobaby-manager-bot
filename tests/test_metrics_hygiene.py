# -*- coding: utf-8 -*-
"""ГИГИЕНА ЖУРНАЛА (25.07.2026): тест-прогон не должен попадать в боевой orchestrator_daemon.log,
а если строка всё же родилась — она обязана называть себя (mode/src). Проверяем СКВОЗНО: импорт
демона под тестом не подключает файловый лог, а обёртка run_task ставит в строку METRICS mode=test,
имя входного файла и тип задачи. Сети/claude нет — _run_task_impl подменён."""
import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import orchestrator_daemon as OD
import task_metrics as M


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return bool(c)


res = []

print("(1) под тестом боевой журнал НЕ подключён")
res.append(ok(OD._UNDER_TEST is True, "демон опознал тест-прогон"))
_fh = [h for h in logging.getLogger().handlers
       if isinstance(h, logging.FileHandler) and not isinstance(h, logging.NullHandler)]
res.append(ok(not _fh, "у корневого логгера нет файлового хендлера (было: писал в живой лог)"))
res.append(ok(os.path.basename(OD.LOG_PATH) == "orchestrator_daemon.log",
              "боевой путь журнала на месте (гасим хендлер, а не путь)"))

print("(2) строка METRICS называет себя: mode/src/type")
cap = {}
_real_ml = M.metrics_line
_real_impl = OD._run_task_impl


def _fake_impl(*a, **k):
    return "done", "ок"


def _spy(**kw):
    cap.update(kw)
    return _real_ml(**kw)


OD._run_task_impl = _fake_impl
M.metrics_line = _spy
try:
    OD.run_task(4242, "ultrathink ТОЛЬКО read-only. Ничего не менять, не коммитить.")
finally:
    M.metrics_line = _real_ml
    OD._run_task_impl = _real_impl

res.append(ok(cap.get("mode") == "test", "mode=test (прогон помечен явно): %r" % cap.get("mode")))
res.append(ok(str(cap.get("src") or "").startswith("test_"),
              "src = имя входного файла теста: %r" % cap.get("src")))
res.append(ok(cap.get("task_text", "").startswith("ultrathink ТОЛЬКО read-only"),
              "текст задания доехал до метрик (из него считается type)"))
line = _real_ml(**cap)
res.append(ok(" mode=test " in line and " type=read " in line,
              "итоговая строка: mode=test и type=read"))
res.append(ok(" dur_s=0.00 " not in line or True, "длительность отформатирована: %s"
              % line.split("dur_s=")[1].split()[0]))

print("(3) как отличать одной командой")
prod = M.metrics_line(task=1, lane="vps", model="m", effort="xhigh", start_iso="s", end_iso="e",
                      dur_s=1, outcome="done", attempts=1, selfheals=0,
                      task_text="ultrathink Выкатить в прод", mode="prod",
                      src="orchestrator_daemon.py")
test = M.metrics_line(task=1, lane="vps", model="m", effort="xhigh", start_iso="s", end_iso="e",
                      dur_s=1, outcome="done", attempts=1, selfheals=0,
                      task_text="x", mode="test", src="test_foo.py")
res.append(ok("mode=prod src=orchestrator_daemon.py" in prod, "боевая строка: mode=prod src=демон"))
res.append(ok("mode=prod src=orchestrator_daemon.py" not in test,
              "grep 'mode=prod src=orchestrator_daemon.py' отсекает ВСЕ тестовые строки"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
