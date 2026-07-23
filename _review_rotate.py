#!/usr/bin/env python3
"""Ротация review-дока: записи [2]-[22] (June 20 и старше) → review_archive.
Порядок: снимок → archive ПЕРВЫМ (verify) → review (verify) → отчёт.
При любом сбое — СТОП, review не трогаем."""
import sys, re, time
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv; load_dotenv()
from bridge_client import BridgeClient

# Граница разбивки: сохраняем записи [0] и [1] (July 2, June 23 — 2 самые свежие)
# body[0:13523] = entry[0] + entry[1]; body[13523:] = entry[2..22] (June 20 и старше)
CUT_POS = 13523
ARCHIVE_ID = "1K0gPMOyM-ER7nweda8-f9MK3edbepYCniZpQy0HkpAA"
BACKUP_PATH = "/tmp/review_prerotation.md"
ARCHIVE_BACKUP = "/tmp/review_archive_prerotation.md"

c = BridgeClient(timeout=300)
print("=== Ротация review → review_archive ===")

# --- 1. Читаем review ---
t0 = time.time()
r = c._call("read_doc", name="review")
t_read = time.time() - t0
if not r.get("ok"):
    print(f"FAIL читать review: {r}"); sys.exit(1)
text = r.get("text") or r.get("content") or ""
print(f"review прочитан за {t_read:.1f}с: {len(text)} байт")

# Снимок на диск (бэкап)
with open(BACKUP_PATH, "w", encoding="utf-8") as f:
    f.write(text)
print(f"снимок: {BACKUP_PATH}")

# Парсим шапку (до ═-строки включительно)
lines = text.split("\n")
hdr_end = None
for i, ln in enumerate(lines):
    if ln and set(ln.strip()) == {"═"}:
        hdr_end = i; break
if hdr_end is None:
    print("FAIL: ═-строка не найдена — стоп"); sys.exit(1)
header = "\n".join(lines[:hdr_end + 1])
body = "\n".join(lines[hdr_end + 1:])
print(f"шапка: {len(header)} симв, тело: {len(body)} симв")

# Проверяем, что позиции записей совпадают с ожидаемыми
ENTRY_RE = re.compile(r"^(PLAN|DONE|NOTE|BLOCKED|WAITING) (\d{4}-\d{2}-\d{2})", re.M)
entries = list(ENTRY_RE.finditer(body))
print(f"всего записей в теле: {len(entries)}")
if len(entries) < 3:
    print(f"записей слишком мало ({len(entries)}) — ротация не нужна"); sys.exit(0)

# Проверяем позицию разреза
cut_entry = None
for e in entries:
    if e.start() >= CUT_POS:
        cut_entry = e; break
if cut_entry is None:
    print(f"FAIL: запись на позиции ≥{CUT_POS} не найдена — стоп"); sys.exit(1)
actual_cut = cut_entry.start()
print(f"разрез на pos={actual_cut} (ожидали ≈{CUT_POS}): '{body[actual_cut:actual_cut+50]}'")

# Части
kept_body = body[:actual_cut]
moved_body = body[actual_cut:]
kept_entries = len(list(ENTRY_RE.finditer(kept_body)))
moved_entries_count = len(list(ENTRY_RE.finditer(moved_body)))
print(f"оставляем: {kept_entries} записей, {len(kept_body)} симв")
print(f"переносим в архив: {moved_entries_count} записей, {len(moved_body)} симв")

# --- 2. Читаем архив ---
ra = c._call("read_doc", id=ARCHIVE_ID)
if not ra.get("ok"):
    print(f"FAIL читать archive: {ra}"); sys.exit(1)
arch_text = ra.get("text") or ra.get("content") or ""
print(f"archive прочитан: {len(arch_text)} байт")
with open(ARCHIVE_BACKUP, "w", encoding="utf-8") as f:
    f.write(arch_text)
print(f"archive снимок: {ARCHIVE_BACKUP}")

# Контрольная сумма до
total_before = len(text) + len(arch_text)
print(f"\nКонтроль ДО: review={len(text)} + archive={len(arch_text)} = {total_before}")

# --- 3. Строим новый архив: moved_body + "\n\n" + existing_archive ---
moved_stripped = moved_body.strip("\n")
new_arch = moved_stripped + "\n\n" + arch_text
print(f"новый архив: {len(arch_text)} → {len(new_arch)} (+{len(new_arch)-len(arch_text)})")

# --- 4. Пишем АРХИВ ПЕРВЫМ + verify ---
print("\n→ ПИШЕМ archive...")
wa = c.write_doc(text=new_arch, id=ARCHIVE_ID)
if not wa.get("ok"):
    print(f"FAIL write archive: {wa}"); sys.exit(1)
print(f"  write ok: {wa}")

# Сверка: читаем архив обратно
va = c._call("read_doc", id=ARCHIVE_ID)
if not va.get("ok"):
    print(f"FAIL verify archive read: {va}"); sys.exit(1)
got_arch = va.get("text") or va.get("content") or ""
sample_top = moved_stripped[:100]
if len(got_arch) != len(new_arch):
    print(f"FAIL archive len mismatch: ожидали {len(new_arch)}, получили {len(got_arch)} — review НЕ ТРОГАЕМ")
    sys.exit(1)
if sample_top not in got_arch[:len(sample_top) + 20]:
    print(f"FAIL archive sample mismatch — review НЕ ТРОГАЕМ")
    sys.exit(1)
print(f"  archive verify: len={len(got_arch)} ✅ образец совпал ✅")

# --- 5. Строим новый review: header + "\n" + kept_body ---
new_review = header + "\n" + kept_body
print(f"\nновый review: {len(text)} → {len(new_review)} симв ({len(new_review)/1024:.1f}KB)")

# Проверяем, что шапка цела и свежие записи на месте
if "📦 KB_review" not in new_review:
    print("FAIL: шапка потеряна — стоп"); sys.exit(1)
kept_check = list(ENTRY_RE.finditer(new_review.split("\n", 3)[-1] if "\n" in new_review else new_review))
print(f"  записей в новом review: {len(kept_check)}")

# --- 6. Пишем новый review + verify ---
print("\n→ ПИШЕМ review...")
wr = c.write_doc(text=new_review, name="review")
if not wr.get("ok"):
    print(f"FAIL write review: {wr}"); sys.exit(1)
print(f"  write ok: {wr}")

# Сверка: читаем review обратно + замеряем время
t2 = time.time()
vr = c._call("read_doc", name="review")
t_read2 = time.time() - t2
if not vr.get("ok"):
    print(f"FAIL verify review read: {vr}"); sys.exit(1)
got_rev = vr.get("text") or vr.get("content") or ""
if len(got_rev) != len(new_review):
    print(f"FAIL review len: ожидали {len(new_review)}, получили {len(got_rev)}")
    sys.exit(1)
print(f"  review verify: len={len(got_rev)} ✅ чтение за {t_read2:.1f}с")

# --- 7. Итоговая сверка ---
total_after = len(got_rev) + len(got_arch)
print(f"\n=== ИТОГ ===")
print(f"review:  {len(text):>7} → {len(got_rev):>7} байт ({len(got_rev)/1024:.1f}KB)")
print(f"archive: {len(arch_text):>7} → {len(got_arch):>7} байт")
print(f"СУММА:   {total_before:>7} → {total_after:>7} (разница {total_after-total_before:+d})")
print(f"чтение review: до={t_read:.1f}с → после={t_read2:.1f}с")
print("✅ Ротация завершена успешно")
