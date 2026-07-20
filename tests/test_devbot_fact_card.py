#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""229 (FACT-верификация, недеструктивная видимость, 20.07.2026): devbot помечает 328-карточку
dev-задачи, завершившейся done БЕЗ блока FACT:, префиксом «⚠️ unverified» — ТОЛЬКО в тексте
карточки; сохранённый в Bridge result демон НЕ мутирует (инвариант «финал байт-в-байт»).

Тестируем helper devbot._unverified_card_prefix(st, it) — чистая функция, без сети/бота.
Запуск: venv/bin/python3 tests/test_devbot_fact_card.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("PRETOOL_NOPUSH", "1")

import devbot

_res = []
def ok(cond, msg):
    _res.append(bool(cond)); print(f"  {'PASS' if cond else 'FAIL'} - {msg}")

MARK = "⚠️ unverified (нет блока FACT:)\n"


def it(frm, result):
    return {"id": 1, "from": frm, "result": result}


print("(1) dev-задача done БЕЗ FACT: → пометка:")
ok(devbot._unverified_card_prefix("done", it("Filipp-328-dev", "гейт зелёный, push done")) == MARK,
   "Filipp-328-dev без FACT: → ⚠️ unverified")
ok(devbot._unverified_card_prefix("done", it("Filipp-pc-dev", "готово, коммит abc1234")) == MARK,
   "Filipp-pc-dev без FACT: → ⚠️ unverified")

print("(2) dev-задача done С FACT: → без пометки:")
ok(devbot._unverified_card_prefix("done", it("Filipp-328-dev", "Сводка.\nFACT: commit abc1234 в git log")) == "",
   "есть FACT: → пусто")
ok(devbot._unverified_card_prefix("done", it("Filipp-328-dev", "fact: read-only")) == "",
   "lowercase fact: → пусто")
ok(devbot._unverified_card_prefix("done", it("Filipp-328-dev", "FACT : PID=123, is-active=active")) == "",
   "FACT с пробелом → пусто")

print("(3) не-dev задача done БЕЗ FACT: → без пометки (только dev):")
ok(devbot._unverified_card_prefix("done", it("Filipp-328", "проверил DNS, всё ок")) == "",
   "Filipp-328 (не dev) → пусто")
ok(devbot._unverified_card_prefix("done", it("Filipp-curator", "вердикт closed")) == "",
   "Filipp-curator → пусто")

print("(4) failed БЕЗ FACT: → без пометки (только done):")
ok(devbot._unverified_card_prefix("failed", it("Filipp-328-dev", "claude упал exit=1")) == "",
   "failed dev → пусто (пометка только для done)")

print("(5) граница: FACTUAL / PREFACT не считаются блоком FACT:")
ok(devbot._unverified_card_prefix("done", it("Filipp-328-dev", "FACTUAL review, PREFACT note")) == MARK,
   "FACTUAL/PREFACT ≠ FACT: → пометка (нет настоящего FACT:)")

print("\nИТОГ:", "ВСЕ PASS" if all(_res) else f"ЕСТЬ FAIL ({sum(_res)}/{len(_res)})")
raise SystemExit(0 if all(_res) else 1)
