#!/usr/bin/env python3
"""Ревизия 16.07: очистить KB_review (POST write_doc, не GET _call)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=90)

# 1. Читаем review (GET)
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
print(f"header_end={header_end}, total lines={len(lines)}")
print(f"header preview: {header[:100]!r}")

# 2. Формируем новый текст review (шапка + резюме что РЕАЛИЗОВАНО)
new_review = (
    header
    + "\n\n"
    + "✅ РЕАЛИЗОВАНО (ревизия 16.07, 2026-07-16):\n"
    + "— PLAN 2026-07-02 21:40 UTC: ОРКЕСТРАТОР СТУПЕНЬ 2 (O4) — реализован 03.07.2026 → KB_MASTER §3\n"
    + "— PLAN 2026-06-23 12:25 UTC: ДВУХФАЗНОЕ ТО (двухфазное) — реализован 23.06.2026 → KB_MASTER §3\n"
    + "(review_archive: запись >183К — ограничение payload; история в cc_log + KB_MASTER §3)"
)
print(f"new_review={len(new_review)} chars")

# 3. Пишем через POST (c.write_doc — не c._call!)
w = c.write_doc(name="review", text=new_review)
if w.get("ok"):
    print("review cleared OK via POST write_doc")
else:
    print(f"FAILED: {w}")
