#!/usr/bin/env python3
"""Ревизия 16.07: финальная запись в cc_log + пульс."""
import os, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=90)

utc = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

CCLOG_LINE = f"""DONE {utc}: ревизия мозга 16.07 — триггер ≤21.07 + расхождения штаба.
  Сделано: [1] KB_MASTER +⭐13-15.07 (EXECUTOR_MODEL/селект-гейт/статус-сводка/WA-webhook/guard-инбокс/куратор-SCOPE/доктрина/инцидент-2478) +§4 WA-фронт +§5 роадмап→архив +§6 якорь 30.07; [2] KB_review очищена (PLAN 02.07+23.06 = ✅ РЕАЛИЗОВАНО, review_archive payload-limit — маркер только в review); [3] KB_project_state шапка→АРХИВ-СНИМОК; [4] CLAUDE.md + KB_RULES §9 три правила дисциплины исполнения; [5] registry_manifest.json roadmap_master→archive; [6] registry_check.py 0 расхождений; commit 498d3b2, гейт 104/104.
  Хвосты: ГАРД Б инварианта «одометр растёт» — все пути закрыть отдельной задачей; O3 adoption audit 14.07 (карточка→да→CRM не закрывался) — зафиксировать как хвост О3."""

PULSE_LINE = f"{utc} | 🟢 | ревизия мозга 16.07 завершена: KB_MASTER+review+project_state+CLAUDE.md+KB_RULES+registry, 498d3b2 | ничего не жду | детали→cc_log «ревизия 16.07»"

# Читаем cc_log
r = c._call("read_doc", name="cc_log")
assert r.get("ok"), f"read cc_log failed: {r}"
cc_txt = r["text"]
lines = cc_txt.split("\n")

# Находим шапку (врезка до ═-only строки)
header_end = 0
for i, line in enumerate(lines):
    if line and all(ch == "═" for ch in line) and i > 0:
        header_end = i
        break

header = "\n".join(lines[:header_end+1])
rest = "\n".join(lines[header_end+1:])

new_cc = header + "\n\n" + CCLOG_LINE + "\n" + rest
print(f"cc_log: {len(cc_txt)} → {len(new_cc)} chars")

w = c.write_doc(name="cc_log", text=new_cc)
if not w.get("ok"):
    print(f"cc_log FAILED: {w}")
    sys.exit(1)
print("cc_log updated OK")

# Пишем пульс
wp = c.write_doc(name="pulse", text=PULSE_LINE)
if wp.get("ok"):
    print(f"pulse updated OK")
else:
    print(f"pulse FAILED: {wp}")
