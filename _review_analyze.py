#!/usr/bin/env python3
"""Анализ review для ротации: показываем все entry-границы."""
import sys, re
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

ARCHIVE_ID = "1K0gPMOyM-ER7nweda8-f9MK3edbepYCniZpQy0HkpAA"

c = BridgeClient(timeout=120)

r = c._call("read_doc", name="review")
if not r.get("ok"):
    print("FAIL:", r); sys.exit(1)
text = r.get("text") or r.get("content") or ""

# Сохраняем снимок
with open("/tmp/review_prerotation.md", "w", encoding="utf-8") as f:
    f.write(text)
print(f"review: {len(text)} байт, снимок в /tmp/review_prerotation.md")

# Шапка: до ═-only-строки включительно
lines = text.split("\n")
hdr_end = None
for i, ln in enumerate(lines):
    if ln and set(ln.strip()) == {"═"}:
        hdr_end = i
        break
if hdr_end is None:
    print("WARN: ═-строка не найдена в шапке")
    hdr_end = 0
header = "\n".join(lines[:hdr_end+1])
body = "\n".join(lines[hdr_end+1:])
print(f"шапка: {len(header)} симв (до строки {hdr_end})")
print(f"тело: {len(body)} симв")

# Находим все начала записей
ENTRY_RE = re.compile(r"^(PLAN|DONE|NOTE|BLOCKED|WAITING|SKIPPED) (\d{4}-\d{2}-\d{2})", re.M)
entries = list(ENTRY_RE.finditer(body))
print(f"\nВсего записей в теле: {len(entries)}")
for i, m in enumerate(entries):
    # Показываем первые 80 символов записи
    snippet = body[m.start():m.start()+80].replace("\n", " ")
    print(f"  [{i}] pos={m.start()} date={m.group(2)} | {snippet[:70]}")

# Читаем архив по id
ra = c._call("read_doc", id=ARCHIVE_ID)
if ra.get("ok"):
    at = ra.get("text") or ra.get("content") or ""
    print(f"\narchive (by id): {len(at)} байт")
    print("archive первые 200:", at[:200])
else:
    print(f"\narchive read FAIL: {ra}")
    at = ""
print(f"\nТОТАЛ сейчас: review={len(text)}  archive={len(at)}  сумма={len(text)+len(at)}")
