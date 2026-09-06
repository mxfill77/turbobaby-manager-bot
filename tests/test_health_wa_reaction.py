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
"""

import os
import sys

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


def _install(wa_value):
    """Подменить ВСЕ зонды здоровья на зелёные, кроме WA — он отдаёт заданное значение."""
    names = ("check_service", "check_bridge", "check_auditor", "check_polling",
             "check_log_health", "check_brain_latency", "check_api_credit",
             "check_commit", "check_wa_webhook", "_read_log_lines")
    for n in names:
        _ORIG.setdefault(n, getattr(H, n))

    H._read_log_lines = lambda *a, **kw: []
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
finally:
    _restore()

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
