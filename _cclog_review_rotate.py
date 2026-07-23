#!/usr/bin/env python3
"""Запись DONE в cc_log о ротации review."""
import sys, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv; load_dotenv()
from bridge_client import BridgeClient

UTC = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")
ENTRY = f"DONE {UTC} UTC: ротация KB_review — 21 запись (June 20 и старше) перенесена в review_archive (id 1K0gPMOyM). review: 49KB→13.4KB, чтение: 3.5с→2.5с (<5с цели). Архив: 147KB→183KB. Сумма сохранена (197043→197044). Снимки до: /tmp/review_prerotation.md + /tmp/review_archive_prerotation.md."

c = BridgeClient(timeout=120)
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("FAIL read cc_log:", r); sys.exit(1)
text = r.get("text") or r.get("content") or ""

# Врезка: шапка до ═-строки включительно
lines = text.split("\n")
hdr_end = None
for i, ln in enumerate(lines):
    if ln and set(ln.strip()) == {"═"}:
        hdr_end = i; break
if hdr_end is None:
    print("WARN: врезка не найдена, пишем в начало")
    new_text = ENTRY + "\n\n" + text
else:
    header = "\n".join(lines[:hdr_end+1])
    body = "\n".join(lines[hdr_end+1:])
    new_text = header + "\n\n" + ENTRY + "\n" + body

w = c.write_doc(text=new_text, name="cc_log")
if not w.get("ok"):
    print("FAIL write cc_log:", w); sys.exit(1)
print(f"cc_log обновлён: {w}")
