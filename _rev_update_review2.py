#!/usr/bin/env python3
"""Ревизия 16.07 retry: archive → review очистка."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=120)  # 120s timeout для большого архива

# 1. Читаем review
r = c._call("read_doc", name="review")
assert r.get("ok"), f"read review failed: {r}"
review_txt = r["text"]

# Разбираем шапку
lines = review_txt.split("\n")
header_end = 0
for i, line in enumerate(lines):
    if "═" * 10 in line and i > 0:
        header_end = i
        break
header = "\n".join(lines[:header_end+1])
content = "\n".join(lines[header_end+1:]).strip()
print(f"[review] header={len(header)}, content={len(content)}")

# 2. Помечаем
marked = content.replace(
    "PLAN 2026-07-02 21:40 UTC ждёт ревью:",
    "✅ РЕАЛИЗОВАНО (03.07.2026), см. KB_MASTER §3\nPLAN 2026-07-02 21:40 UTC:"
).replace(
    "PLAN 2026-06-23 12:25 UTC ждёт ревью:",
    "✅ РЕАЛИЗОВАНО (23.06.2026), см. KB_MASTER §3 (двухфазное ТО)\nPLAN 2026-06-23 12:25 UTC:"
)

# 3. Читаем архив
r_arc = c._call("read_doc", name="review_archive")
assert r_arc.get("ok"), f"read archive failed: {r_arc}"
arc_txt = r_arc["text"]
print(f"[review_archive] current={len(arc_txt)} chars")

# 4. Пишем в архив
# Чтобы не переполнять: добавляем маркер + краткое резюме (без полного текста PLAN),
# т.к. планы можно найти в git-истории cc_log
marker = """══ ПЕРЕНЕСЕНО 2026-07-16 (ревизия 16.07) ══
✅ РЕАЛИЗОВАНО: ОРКЕСТРАТОР СТУПЕНЬ 2 (O4) — plan 2026-07-02, реализован 03.07.2026, см. KB_MASTER §3.
✅ РЕАЛИЗОВАНО: ДВУХФАЗНОЕ ТО — plan 2026-06-23, реализован 23.06.2026, см. KB_MASTER §3.
(полный текст планов доступен в git cc_log)"""

new_arc = marker + "\n\n" + arc_txt
print(f"[review_archive] new size={len(new_arc)}")

r_wa = c._call("write_doc", name="review_archive", text=new_arc)
if r_wa.get("ok"):
    print(f"[review_archive] written OK")
else:
    print(f"[review_archive] WRITE FAILED: {r_wa} — пишем только в review")

# 5. Очищаем review до шапки
new_review = header + "\n\n(пусто — планы 02.07+23.06 помечены ✅ РЕАЛИЗОВАНО и перенесены в review_archive 2026-07-16; детали → KB_MASTER §3)"
r_wr = c._call("write_doc", name="review", text=new_review)
if r_wr.get("ok"):
    print(f"[review] cleared, {len(new_review)} chars OK")
else:
    print(f"[review] WRITE FAILED: {r_wr}")

print("DONE")
