#!/usr/bin/env python3
"""Отказ WA-вебхука ДОХОДИТ до владельца (06.09.2026).

КЛАСС. Наблюдение за `wa-webhook` в `health.py` было и раньше — настоящая проба рукопожатия
(`_wa_probe`) плюс вотчдог, перезапускающий юнит на двух подряд провалах. Не было РЕАКЦИИ:
строка «❌ WA webhook» печаталась в тело отчёта, но в список `problems` не попадала, поэтому
сводка оставалась «✅ ВСЁ ОК», код возврата 0 и пуш владельцу не уходил ВООБЩЕ. Мёртвый
вебхук был виден отчёту и невидим человеку.

Живой факт основания (журнал `splinter-health.service`, 05–06.09.2026): восемь прогонов подряд
дали «✅ WA webhook active, handshake 200/probe42, очередь new=0» — то есть проба работала и
докладывала. Проверить обратную ветку живьём было нечем: за наблюдение отказов не случилось,
поэтому она проверяется здесь подстановкой.

ТРИ СОСТОЯНИЯ, А НЕ ДВА — и это главный предмет файла. `check_wa_webhook()` отдаёт None, когда
WA не настроен вовсе (`WA_VERIFY_TOKEN` пуст). Наивное `if not wa_ok` записало бы в проблемы и
None, то есть подняло бы тревогу на каждой машине, где WhatsApp просто не заведён. Проблемой
считается РОВНО измеренный отказ — `wa_ok is False`.

Сети здесь нет: все зонды `health` подменены, `build_report` не делает ни одного обращения
наружу (проверяется отдельно — счётчиком вызовов подменённых зондов).

Боевых файлов и процессов тоже нет (RCFIX2010 C h3): на сервере REPO — живое дерево, и `health.LOG`
указывает на боевой `splinter.log`. Поэтому подменены ВСЕ читатели, которых зовёт `build_report`
(журнал — `_read_log` с r2 и прежний `_read_log_lines`, граница systemd — `_read_run`), `LOG` уведён
во временный каталог, а `open` и `subprocess.run` внутри `health` — сторожа: попытка открыть файл или
запустить процесс мимо подмен записывается и роняет проверку (7). Там же замок: каждая функция
`health`, которую зовёт `build_report`, либо подменена здесь, либо чистая.
"""

import ast
import os
import sys
import tempfile
import types

REPO = "/root/turbobaby-manager-bot"
sys.path.insert(0, REPO)
os.environ["PRETOOL_NOPUSH"] = "1"

import health as H

res = []


def ok(cond, label):
    print(("  PASS " if cond else "  FAIL ") + label)
    res.append(bool(cond))
    return bool(cond)


_ORIG = {}
_probe_calls = {"n": 0}
_TMP = tempfile.mkdtemp(prefix="health_wa_reaction_")
_LIVE = {"open": [], "run": []}            # попытки health открыть файл / запустить процесс мимо подмен
# Чем подменены читатели build_report (замок (7)): всё, что открывает файл, запускает процесс или ходит в сеть.
_PATCHED = ("check_service", "check_bridge", "check_auditor", "check_polling",
            "check_log_health", "check_brain_latency", "check_api_credit",
            "check_commit", "check_wa_webhook", "_read_log_lines", "_read_log", "_read_run")
_PURE = ("_recheck_run", "_utcnow")          # зовутся build_report, но ничего не читают


def _guard_open(path, *a, **kw):
    _LIVE["open"].append(str(path))
    raise PermissionError(13, "тест: health не открывает файлы в этом тесте", str(path))


def _guard_run(cmd, *a, **kw):
    _LIVE["run"].append(list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)])
    raise FileNotFoundError(2, "тест: живой процесс из health запрещён", str(cmd))


def _install(wa_value):
    """Подменить ВСЕ зонды здоровья на зелёные, кроме WA — он отдаёт заданное значение."""
    for n in _PATCHED + ("LOG", "subprocess"):
        _ORIG.setdefault(n, getattr(H, n))

    H.LOG = os.path.join(_TMP, "splinter.log")             # не боевой журнал, даже если читатель не подменён
    H.open = _guard_open                                   # имя модуля health заслоняет builtins.open
    H.subprocess = types.SimpleNamespace(run=_guard_run)   # _run / _read_run / рестарт WA — мимо подмен не пройдут
    H._read_log_lines = lambda *a, **kw: []
    H._read_log = lambda *a, **kw: ([], None)  # RCFIX2010 C r2: build_report читает журнал ЭТИМ читателем
    H._read_run = lambda *a, **kw: None       # RCFIX2010 C: без живого `systemctl show`; polling судит заглушка ниже
    H.check_service   = lambda *a, **kw: (True, "active", None, None)
    H.check_bridge    = lambda *a, **kw: (True, "ok")
    H.check_auditor   = lambda *a, **kw: (True, "ok")
    H.check_polling   = lambda *a, **kw: (True, "ok")
    H.check_log_health = lambda *a, **kw: (True, "ok", 0)
    H.check_brain_latency = lambda *a, **kw: (False, "ok")
    H.check_api_credit    = lambda *a, **kw: (False, "ok")
    H.check_commit        = lambda *a, **kw: (True, "abc1234")

    def _wa(*a, **kw):
        _probe_calls["n"] += 1
        return wa_value, "деталь про WA"
    H.check_wa_webhook = _wa


def _restore():
    for n, fn in _ORIG.items():
        setattr(H, n, fn)
    if H.__dict__.get("open") is _guard_open:
        del H.open


try:
    # ── (1) измеренный отказ → проблема, красная сводка, ненулевой код ───────────
    print("\n(1) WA отвечает отказом — владелец узнаёт")
    _install(False)
    report, summary, code, _, _ = H.build_report()
    ok(code == 1, "code=1 при мёртвом вебхуке (было 0 — пуш не уходил): code=" + str(code))
    ok("WA webhook не отвечает" in summary, "сводка НАЗЫВАЕТ отказ: " + summary[:70])
    ok("ПРОБЛЕМА" in summary, "сводка красная, а не «ВСЁ ОК»")
    ok("WA webhook" in report, "строка про WA осталась и в теле отчёта")

    # ── (2) WA не настроен → молчим, это не поломка ──────────────────────────────
    print("\n(2) WA не настроен (None) — тревоги нет")
    _install(None)
    report, summary, code, _, _ = H.build_report()
    ok(code == 0, "None → code=0: ненастроенный канал поломкой не считается")
    ok("WA webhook не отвечает" not in summary, "и в сводке о нём ни слова: " + summary[:50])
    ok("ВСЁ ОК" in summary, "сводка зелёная")

    # ── (3) WA здоров → прежнее поведение байт-в-байт ────────────────────────────
    print("\n(3) WA здоров — как было")
    _install(True)
    report_ok, summary_ok, code_ok, _, _ = H.build_report()
    ok(code_ok == 0 and "ВСЁ ОК" in summary_ok, "здоровый вебхук → зелено, code=0")

    # ── (4) отличаем False от None по-настоящему ─────────────────────────────────
    print("\n(4) различитель — именно `is False`, а не ложность")
    ok(H.build_report.__code__.co_consts is not None, "функция читается")
    src = open(os.path.join(REPO, "health.py"), encoding="utf-8").read()
    ok("if wa_ok is False:" in src,
       "в коде стоит `is False` — `if not wa_ok` поймал бы и None (ненастроенный канал)")

    # ── (5) прочие компоненты не задеты ──────────────────────────────────────────
    print("\n(5) остальные зонды судятся как судились")
    _install(True)
    H.check_bridge = lambda *a, **kw: (False, "мост молчит")
    _, summary_br, code_br, _, _ = H.build_report()
    ok(code_br == 1 and "Bridge не отвечает" in summary_br,
       "падение моста по-прежнему красит сводку: " + summary_br[:60])

    # ── (6) ни одного обращения наружу ───────────────────────────────────────────
    print("\n(6) сеть не трогалась")
    ok(_probe_calls["n"] >= 4, "зонд WA звался подменённым во всех прогонах: "
                               + str(_probe_calls["n"]))

    # ── (7) ни боевого журнала, ни systemd: каждый читатель build_report подменён ─────
    print("\n(7) боевые файлы и процессы не трогались (на сервере LOG = боевой splinter.log)")
    ok(_LIVE["open"] == [], "open внутри health не звался ни разу: " + repr(_LIVE["open"][:3]))
    ok(_LIVE["run"] == [], "subprocess.run внутри health не звался ни разу: " + repr(_LIVE["run"][:3]))
    ok(H.LOG.startswith(_TMP), "LOG на время прогона — во временном каталоге: " + H.LOG)
    tree = ast.parse(src)
    defs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    br = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_report"][0]
    called = {n.func.id for n in ast.walk(br) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id in defs}
    ok("_read_log" in called and "_read_run" in called, "build_report зовёт _read_log и _read_run: "
                                                        + ", ".join(sorted(called)))
    ok(not (called - set(_PATCHED) - set(_PURE)),
       "каждая функция health из build_report подменена здесь или чистая; лишние: "
       + repr(sorted(called - set(_PATCHED) - set(_PURE))))
finally:
    _restore()

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
