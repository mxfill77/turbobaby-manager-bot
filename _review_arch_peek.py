#!/usr/bin/env python3
"""Смотрим структуру archive: шапку и первые записи."""
import sys, re
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv; load_dotenv()
from bridge_client import BridgeClient

ARCHIVE_ID = "1K0gPMOyM-ER7nweda8-f9MK3edbepYCniZpQy0HkpAA"
c = BridgeClient(timeout=120)
ra = c._call("read_doc", id=ARCHIVE_ID)
if not ra.get("ok"):
    print("FAIL:", ra); sys.exit(1)
at = ra.get("text") or ra.get("content") or ""
print(f"archive: {len(at)} байт")

lines = at.split("\n")
print(f"строк: {len(lines)}")
print("=== первые 15 строк ===")
for i, ln in enumerate(lines[:15]):
    print(f"  [{i}] {ln[:100]!r}")

# Ищем ═-only строку
hdr_end = None
for i, ln in enumerate(lines[:30]):
    if ln and set(ln.strip()) == {"═"}:
        hdr_end = i
        print(f"\n═-строка найдена на line {i}")
        break
if hdr_end is None:
    print("\n═-строка НЕ найдена в первых 30 строках")

# Первые записи после шапки
ENTRY_RE = re.compile(r"^(PLAN|DONE|NOTE|BLOCKED|WAITING) (\d{4}-\d{2}-\d{2})", re.M)
body_start = "\n".join(lines[hdr_end+1:]) if hdr_end is not None else at
entries = list(ENTRY_RE.finditer(body_start))
print(f"\nВсего записей в archive: {len(entries)}")
print("первые 5:")
for e in entries[:5]:
    print(f"  {body_start[e.start():e.start()+80].split(chr(10))[0]}")
print("последние 3:")
for e in entries[-3:]:
    print(f"  {body_start[e.start():e.start()+80].split(chr(10))[0]}")
