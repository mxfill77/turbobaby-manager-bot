#!/usr/bin/env python3
"""Ревизия 16.07: KB_review — пометить PLAN-записи «✅ РЕАЛИЗОВАНО», перенести в архив, очистить review."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=60)

# 1. Читаем текущий review
r_review = c._call("read_doc", name="review")
assert r_review.get("ok"), f"read review failed: {r_review}"
review_txt = r_review["text"]

# Шапка review (врезка до первой пустой строки + горизонталь)
header_lines = []
content_lines = []
in_header = True
lines = review_txt.split("\n")
for i, line in enumerate(lines):
    if in_header:
        header_lines.append(line)
        if "═" * 10 in line and i > 0:
            in_header = False
    else:
        content_lines.append(line)

header = "\n".join(header_lines)
content = "\n".join(content_lines).strip()

print(f"[review] header={len(header)} chars, content={len(content)} chars")

# 2. Помечаем PLAN-записи как реализованные
# PLAN 02.07 (O4 ступень 2) и PLAN 23.06 (двухфазное ТО)
marked_content = content.replace(
    "PLAN 2026-07-02 21:40 UTC ждёт ревью:",
    "✅ РЕАЛИЗОВАНО 15.07.2026, см. KB_MASTER §3\nPLAN 2026-07-02 21:40 UTC:"
)
marked_content = marked_content.replace(
    "PLAN 2026-06-23 12:25 UTC ждёт ревью:",
    "✅ РЕАЛИЗОВАНО 23.06.2026, см. KB_MASTER §3 (двухфазное ТО)\nPLAN 2026-06-23 12:25 UTC:"
)
print(f"[review] marked content={len(marked_content)} chars")

# 3. Читаем review_archive
r_arc = c._call("read_doc", name="review_archive")
assert r_arc.get("ok"), f"read review_archive failed: {r_arc}"
archive_txt = r_arc["text"]
print(f"[review_archive] current={len(archive_txt)} chars")

# 4. Пишем в архив: помеченный контент СВЕРХУ (новое выше старого)
new_archive = f"══ ПЕРЕНЕСЕНО 2026-07-16 (ревизия 16.07) ══\n\n{marked_content}\n\n{archive_txt}".strip()
r_write_arc = c._call("write_doc", name="review_archive", text=new_archive)
assert r_write_arc.get("ok"), f"write review_archive failed: {r_write_arc}"
print(f"[review_archive] written {len(new_archive)} chars OK")

# 5. Очищаем review до шапки + пометки
new_review = header + "\n\n(пусто — планы перенесены в review_archive 2026-07-16 по ревизии 16.07; все РЕАЛИЗОВАНЫ, см. KB_MASTER §3)"
r_write_rev = c._call("write_doc", name="review", text=new_review)
assert r_write_rev.get("ok"), f"write review failed: {r_write_rev}"
print(f"[review] cleared, written {len(new_review)} chars OK")

print("DONE: KB_review очищен, архив обновлён")
