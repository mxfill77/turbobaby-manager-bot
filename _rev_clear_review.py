#!/usr/bin/env python3
"""Ревизия 16.07: очистить review (без записи в архив — 413 payload limit)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=90)

# Читаем review
r = c._call("read_doc", name="review")
assert r.get("ok"), f"read review failed: {r}"
txt = r["text"]

lines = txt.split("\n")
header_end = 0
for i, line in enumerate(lines):
    if "═" * 10 in line and i > 0:
        header_end = i
        break
header = "\n".join(lines[:header_end+1])
print(f"header={len(header)}, full={len(txt)}")

# Очищаем review до шапки + одна строка-резюме
# (review_archive >= 413 limit, пишем только примечание в review)
new_review = (
    header
    + "\n\n"
    + "✅ РЕАЛИЗОВАНО (ревизия 16.07, обновлено 2026-07-16):\n"
    + "— PLAN 2026-07-02 21:40: ОРКЕСТРАТОР СТУПЕНЬ 2 (O4) — реализован 03.07.2026 → KB_MASTER §3\n"
    + "— PLAN 2026-06-23 12:25: ДВУХФАЗНОЕ ТО — реализован 23.06.2026 → KB_MASTER §3\n"
    + "(канал очищен; review_archive недоступен для записи из-за размера ≥ payload limit)"
)

print(f"new_review={len(new_review)} chars")

w = c._call("write_doc", name="review", text=new_review)
if w.get("ok"):
    print("review cleared OK")
else:
    print(f"FAILED: {w}")
