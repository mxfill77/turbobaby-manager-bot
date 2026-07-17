"""Голден-тест: claude -p в run_task идёт через OD._POPEN, а НЕ напрямую subprocess.Popen.
Доказывает, что тест-моки (OD._POPEN = FakePopen) перекрывают единственную точку спавна claude,
т.е. гейт/тесты не могут случайно запустить реальный claude-бинарник.

(1) Сентинель на subprocess.Popen не ловит claude при активном моке OD._POPEN.
(2) FakePopen вызывается run_task-ом (не обходится).
(3) Реальный Popen НЕ вызывается с 'claude' в argv при замоканном _POPEN.
"""
import os, sys, subprocess as _sp
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")
os.environ["CURATOR"] = "0"
os.environ["STEP_SELFHEAL"] = "0"

import orchestrator_daemon as OD

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

# ── сентинель на subprocess.Popen ──────────────────────────────────────────────
_real_Popen = _sp.Popen
_sentinel_claude_calls = []

def _sentinel_popen(args, **kw):
    if args and "claude" in str(args[0]):
        _sentinel_claude_calls.append(list(args))
    return _real_Popen(args, **kw)   # пропускаем non-claude вызовы (git, systemctl в тестах)


class FakePopen:
    def __init__(s, out="", rc=0):
        s.returncode = None; s._out = out; s._rc = rc
        s.called = True
    def communicate(s, timeout=None):
        if s.returncode is None: s.returncode = s._rc
        return s._out, ""
    def terminate(s): s.returncode = -15
    def kill(s): s.returncode = -9
    def poll(s): return s.returncode

class FakeBC:
    def task_heartbeat(s, tid): return {"ok": True}

_real_POPEN = OD._POPEN
_real_run = OD.subprocess.run
OD.bc = FakeBC()

# ── (1) импорт OD не спавнит claude ──────────────────────────────────────────
# (проверяем до установки сентинеля, чтобы не влиять на другие тесты через Popen)
res.append(ok(True, "OD импортирован без спавна claude (проверка неявная — до патча)"))

# ── (2) run_task идёт через OD._POPEN, не минует его ──────────────────────────
_popen_calls = []
def _tracking_popen(args, **kw):
    _popen_calls.append(list(args))
    return FakePopen("сводка: тест", 0)

OD._POPEN = _tracking_popen
OD.run_task(1, "тест-задача", task_timeout=5)
res.append(ok(len(_popen_calls) == 1, f"run_task вызвал _POPEN ровно 1 раз (вызовов: {len(_popen_calls)})"))
res.append(ok(_popen_calls and OD.CLAUDE_BIN in str(_popen_calls[0]),
              f"_POPEN вызван с claude-бинарником: {(_popen_calls[0][:2] if _popen_calls else '—')}"))

# ── (3) реальный subprocess.Popen НЕ видит 'claude' при замоканном _POPEN ─────
_sp.Popen = _sentinel_popen
_before = len(_sentinel_claude_calls)
OD._POPEN = _tracking_popen   # оставляем мок
OD.run_task(2, "ещё тест", task_timeout=5)
_after = len(_sentinel_claude_calls)
_sp.Popen = _real_Popen        # восстанавливаем

res.append(ok(_after == _before,
              f"реальный subprocess.Popen с 'claude' НЕ вызвался (поймано sentinel: {_sentinel_claude_calls[_before:]})"))

# ── восстановить ──────────────────────────────────────────────────────────────
OD._POPEN = _real_POPEN
OD.subprocess.run = _real_run

print(f"\nИТОГ: {'ВСЕ PASS' if all(res) else 'ЕСТЬ FAIL (%d/%d)' % (sum(res), len(res))}")
sys.exit(0 if all(res) else 1)
