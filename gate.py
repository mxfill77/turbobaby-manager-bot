#!/usr/bin/env python3
"""ТЕСТЫ-ГЕЙТ перед прод-деплоем (пункт 4.3 лестницы фундамента).

Гоняет набор тестов tests/test_*.py (быстрый, ~1.6с, всё мокнуто — нет ложного красного от флапа).
Все зелёные → exit 0 (прод-операция идёт). Хоть один красный → exit 1 (ДЕПЛОЙ БЛОКИРОВАН) +
пуш Филиппу + запись в боевой_лог result=blocked_by_tests.

Использование:
    venv/bin/python3 gate.py                 # прогон гейта (перед clasp redeploy / git push / restart)
    venv/bin/python3 gate.py --for push      # пометить операцию в логе (push/clasp/restart)
    venv/bin/python3 gate.py --final         # ФИНАЛЬНЫЙ прогон: красный алерт в Telegram гарантирован
    venv/bin/python3 gate.py --override "причина"   # ОБХОД — ТОЛЬКО по явному «да» Филиппа

Алерты владельцу (хвост §7, 12.07.2026): «🔴 ТЕСТЫ КРАСНЫЕ» пушится ТОЛЬКО на финальном прогоне.
Внутри headless-задачи (orchestrator_daemon ставит окружению claude -p GATE_ALERT_FINAL_ONLY=1)
промежуточные красные прогоны — штатный red-fix-green цикл: решение гейта/exit 1/боевой_лог не
меняются, но Telegram молчит. Финальность детерминированна: pre-push hook зовёт gate.py --final
(бьёт подавление даже внутри headless — деплой-прогон алертит всегда). FAIL-SAFE: флага контекста
нет / контекст неясен / сбой определения → алертим как раньше.

ЭНФОРСМЕНТ: git push — нативный pre-push hook (deploy/hooks/pre-push) зовёт gate.py автоматически.
clasp redeploy / systemctl restart — по правилу CLAUDE.md (дисциплинарно). Будущий дев-бот/оркестратор
зовёт gate.py в деплой-пути и обойти НЕ может — обход только Филипп («да» → --override).
"""
import os
import sys
import glob
import time
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, "venv", "bin", "python3")
# GATE_TESTS_DIR — ТОЛЬКО для регресса tests/test_no_push_leak.py (подмена набора на фейковый,
# чтобы прогнать полный цикл гейта без рекурсии). Боевой запуск переменную не ставит.
TESTS_DIR = os.environ.get("GATE_TESTS_DIR") or os.path.join(ROOT, "tests")


def _arg(flag):
    a = sys.argv[1:]
    if flag in a:
        i = a.index(flag)
        return a[i + 1] if i + 1 < len(a) else ""
    return None


def _log(result, args_str):
    """Best-effort запись в боевой_лог (не валит гейт, если Bridge недоступен)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
        from bridge_client import BridgeClient
        BridgeClient(timeout=20).log_write(initiator="gate.py", act="prod_deploy",
                                           args=args_str[:480], result=result, critical="тесты-гейт")
    except Exception as e:
        print(f"[gate] лог не записан ({e}) — решение гейта не затронуто")


def _push(text):
    try:
        from notify import notify
        notify(text, force=True)   # боевой алерт гейта («ТЕСТЫ КРАСНЫЕ») — тест-мут его не глушит
    except Exception:
        pass


def _alert_allowed(final):
    """Красный Telegram-алерт разрешён на ЭТОМ прогоне? (хвост §7, 12.07.2026)
    Финальный прогон (--final, его ставит pre-push hook) → всегда да, даже внутри headless.
    Промежуточный прогон ВНУТРИ headless-задачи (демон даёт claude -p окружение
    GATE_ALERT_FINAL_ONLY=1; красный там — штатный red-fix-green цикл) → тихо, без пуша.
    FAIL-SAFE: переменной нет / значение не «1» / любой сбой чтения → True (алертим как раньше)."""
    try:
        if final:
            return True
        return (os.environ.get("GATE_ALERT_FINAL_ONLY") or "").strip() != "1"
    except Exception:
        return True


def run_tests():
    """Прогнать все tests/test_*.py. Вернуть (failed:list, total:int, dt:float)."""
    # PYTHONPATH — чтобы import splinter работал из tests/. PRETOOL_NOPUSH=1 — тесты и ВСЕ их
    # подпроцессы (вкл. pretool_guard-фикстуры) НЕ шлют пуши в личку (утечки 01–05.07): env
    # наследуется детьми, pretool_guard._push и notify.notify его чтут. Пуш самого гейта о красных
    # тестах НЕ затронут (переменная ставится только подпроцессам тестов, не самому гейту).
    env = dict(os.environ, PYTHONPATH=ROOT, PRETOOL_NOPUSH="1", ORCH_TEST_MODE="1")
    tests = sorted(glob.glob(os.path.join(TESTS_DIR, "test_*.py")))
    failed = []
    t0 = time.time()
    for t in tests:
        name = os.path.basename(t)
        try:
            r = subprocess.run([PY, t], cwd=ROOT, env=env,
                               capture_output=True, text=True, timeout=90)
            if r.returncode != 0:
                failed.append(name)
        except subprocess.TimeoutExpired:
            failed.append(name + "(timeout)")
    return failed, len(tests), time.time() - t0


# === УСКОРЕНИЕ ЦЕПЕЙ ч.2 (13.07.2026): СЕЛЕКТИВНЫЙ ГЕЙТ ПРОМЕЖУТОЧНЫХ ШАГОВ ===
# Промежуточный шаг декомпозера (i < N) → только smoke (py_compile) + тесты затронутых
# модулей вместо полного сьюта — быстрее и дешевле. Последний шаг (i == N), одиночки,
# пуши (pre-push hook --final) — полный сьют, финальное качество не ослабляется.
# Активация: orchestrator_daemon.run_task ставит GATE_STEP_SELECTIVE=1 в child_env
# промежуточного шага; gate.py читает его и переключается в selective-режим.
# --final (pre-push hook) всегда бьёт флаг: деплой-прогон всегда полный.
# Fail-safe: не удалось определить затронутое → полный сьют (label «полный (fail-safe…)»).

def _step_selective():
    """True → текущий вызов — промежуточный шаг цепи (GATE_STEP_SELECTIVE=1 в env).
    Только строгое «1»; мусор/0/пусто → False (в сторону полного, не тишины)."""
    return (os.environ.get("GATE_STEP_SELECTIVE") or "").strip() == "1"


def _changed_py_files():
    """Изменённые .py-файлы: uncommitted (staged + unstaged) + последний коммит.
    Возврат: sorted list базовых имён. Ошибка / пустой git → [] (fail-safe полного сьюта)."""
    try:
        found = set()
        for args in (
            ["git", "diff", "--name-only", "HEAD"],              # unstaged изменения
            ["git", "diff", "--name-only", "--cached", "HEAD"],  # staged изменения
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],    # последний коммит
        ):
            p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=15)
            if p.returncode == 0:
                for f in p.stdout.strip().splitlines():
                    f = f.strip()
                    if f.endswith(".py"):
                        found.add(os.path.basename(f))
        return sorted(found)
    except Exception:
        return []


def _affected_test_files(changed_files):
    """Тесты, покрывающие изменённые модули: имя модуля (без .py) ищем в содержимом каждого теста.
    Возврат: sorted list путей. Пустой → [] (вызывающий переключится на полный сьют).
    Нечитаемый тест включаем (fail-safe в сторону полноты)."""
    if not changed_files:
        return []
    all_tests = sorted(glob.glob(os.path.join(TESTS_DIR, "test_*.py")))
    modules = {f[:-3] for f in changed_files if f.endswith(".py")}
    affected = set()
    for test in all_tests:
        try:
            with open(test, encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
            for mod in modules:
                if mod in content:
                    affected.add(test)
                    break
        except Exception:
            affected.add(test)   # нечитаемый файл включаем — не пропускать молча
    return sorted(affected)


def run_selective_tests(changed_files):
    """Smoke (py_compile) + тесты затронутых модулей.
    Возврат: (failed_names:list, n_tests:int, dt:float, label:str).
    Если затронутых тестов не нашли → fail-safe: полный сьют (label несёт «fail-safe»)."""
    env = dict(os.environ, PYTHONPATH=ROOT, PRETOOL_NOPUSH="1", ORCH_TEST_MODE="1")
    t0 = time.time()
    failed = []

    # Smoke: py_compile каждого изменённого .py
    for fname in changed_files:
        path = os.path.join(ROOT, fname)
        if not os.path.isfile(path):
            continue
        r = subprocess.run([PY, "-m", "py_compile", path], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            failed.append(f"py_compile:{fname}")

    # Тесты затронутых модулей
    test_files = _affected_test_files(changed_files)
    if not test_files:
        # Fail-safe: модули не опознаны → полный сьют
        ff, total, _ = run_tests()
        return (failed + ff), total, time.time() - t0, f"полный (fail-safe: {total} тестов)"

    for t in test_files:
        name = os.path.basename(t)
        try:
            r = subprocess.run([PY, t], cwd=ROOT, env=env,
                               capture_output=True, text=True, timeout=90)
            if r.returncode != 0:
                failed.append(name)
        except subprocess.TimeoutExpired:
            failed.append(name + "(timeout)")

    return failed, len(test_files), time.time() - t0, f"селективный ({len(test_files)} тестов)"


def main():
    op = _arg("--for") or "prod"
    override = _arg("--override")
    final = "--final" in sys.argv[1:]   # финальный прогон (pre-push / явный запуск) — алерт обязателен

    if override is not None:
        # ОБХОД — только по явному «да» Филиппа. Claude Code сам этот флаг не ставит.
        msg = f"причина: {override or '(не указана)'}"
        _log("test_override", f"op={op}; обход тестов; {msg}")
        print(f"⚠️ ГЕЙТ ОБОЙДЁН (по «да» Филиппа). op={op}. {msg}. Записано в боевой_лог: test_override.")
        return 0

    # Selective mode: промежуточный шаг цепи (GATE_STEP_SELECTIVE=1) + не финальный прогон →
    # smoke + тесты затронутых модулей. --final (pre-push) всегда полный сьют.
    if _step_selective() and not final:
        changed = _changed_py_files()
        failed, total, dt, label = run_selective_tests(changed)
    else:
        failed, total, dt = run_tests()
        label = "полный"

    if not failed:
        print(f"✅ ГЕЙТ ({label}): {total} тестов зелёные ({dt:.1f}с) — прод-операция «{op}» разрешена.")
        return 0

    # КРАСНЫЙ → блок + лог; пуш владельцу — только на финальном прогоне (см. _alert_allowed)
    flist = ", ".join(failed)
    alert = _alert_allowed(final)
    print(f"❌ ГЕЙТ: КРАСНЫЕ ТЕСТЫ ({len(failed)}/{total}): {flist}")
    print(f"   ДЕПЛОЙ «{op}» ЗАБЛОКИРОВАН ({label}). Обход только по «да» Филиппа: gate.py --override «причина».")
    _log("blocked_by_tests", f"op={op}; гейт {label}; упали: {flist}"
         + ("" if alert else "; промежуточный headless-прогон — Telegram-алерт подавлен"))
    if alert:
        _push(f"🔴 ТЕСТЫ КРАСНЫЕ ({len(failed)}/{total}): {flist}. Деплой «{op}» ЗАБЛОКИРОВАН (тесты-гейт 4.3). "
              f"Обход только твоим «да».")
    else:
        print("   [gate] промежуточный прогон внутри headless-задачи (GATE_ALERT_FINAL_ONLY=1) — "
              "Telegram-алерт подавлен; финальный прогон (pre-push / --final) алертит как обычно.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
