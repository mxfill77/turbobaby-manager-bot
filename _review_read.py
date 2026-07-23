#!/usr/bin/env python3
"""Читаем review и review_archive для анализа структуры."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient
import time

c = BridgeClient(timeout=120)

t0 = time.time()
r = c._call("read_doc", name="review")
t1 = time.time()
if not r.get("ok"):
    print("FAIL read review:", r)
    sys.exit(1)
text = r.get("text") or r.get("content") or ""
print(f"review прочитан за {t1-t0:.1f}с, размер={len(text)} байт")
print("=== ПЕРВЫЕ 600 симв ===")
print(text[:600])
print("...")
print("=== ПОСЛЕДНИЕ 300 симв ===")
print(text[-300:])
print(f"\n=== КОНЧАЕТСЯ на #{len(text)} ===")

# Считаем записи: строки начинающиеся с PLAN/DONE/NOTE
import re
entries = re.findall(r"^(PLAN|DONE|NOTE|BLOCKED|WAITING) \d{4}-\d{2}-\d{2}", text, re.M)
print(f"\nВсего записей ({'/'.join(['PLAN','DONE','NOTE'])}...): {len(entries)}")
for e in entries[:20]:
    print("  ", e)
print("...")
for e in entries[-5:]:
    print("  ", e)

# Читаем архив
t2 = time.time()
ra = c._call("read_doc", name="KB_claude_review_archive")
t3 = time.time()
print(f"\nreview_archive прочитан за {t3-t2:.1f}с, ok={ra.get('ok')}")
if ra.get("ok"):
    at = ra.get("text") or ra.get("content") or ""
    print(f"archive размер={len(at)} байт")
    print("=== archive первые 200 ===")
    print(at[:200])
else:
    print("archive ответ:", ra)
