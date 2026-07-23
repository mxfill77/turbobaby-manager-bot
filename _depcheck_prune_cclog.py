"""Подрезка cc_log (триггер >40 КБ): записи старше ТЕКУЩИХ суток → архив (name=cc_log_archive).
Порядок жёсткий: бэкап на /tmp → АРХИВ ПИШЕТСЯ ПЕРВЫМ + сверка → только потом подрезка cc_log.
Врезка (шапка до последней ═-only строки в начале) сохраняется. Зона 🟢 (Brain-журналы)."""
import re
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ cc_log FAIL — стоп:", r)
    raise SystemExit(1)
old = r.get("text", "")

with open("/tmp/cc_log_backup_depcheck_20260703.txt", "w") as f:
    f.write(old)
print("BACKUP /tmp/cc_log_backup_depcheck_20260703.txt:", len(old), "chars")

lines = old.split("\n")
hdr_end = 0
for i, ln in enumerate(lines[:80]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        hdr_end = i + 1

entry_re = re.compile(r"^(DONE|PLAN|NOTE|WAITING|BLOCKED|SKIPPED|RECON)\s+(\d{4}-\d{2}-\d{2})")
cut = None  # первая строка записи со старой датой — с неё и до конца всё в архив
for i in range(hdr_end, len(lines)):
    m = entry_re.match(lines[i])
    if m and m.group(2) != today:
        cut = i
        break

if cut is None:
    print("Нечего подрезать: все записи сегодняшние. Стоп без изменений.")
    raise SystemExit(0)

old_part = "\n".join(lines[cut:]).strip("\n")
keep_part = "\n".join(lines[:cut]).rstrip("\n")
print("Split: keep", len(keep_part), "chars | to_archive", len(old_part), "chars")

ra = c._call("read_doc", name="cc_log_archive")
if not ra.get("ok"):
    print("READ архив FAIL — СТОП, cc_log НЕ трогаю:", ra)
    raise SystemExit(1)
arch_old = ra.get("text", "")
arch_new = old_part + "\n\n" + arch_old  # старое из cc_log СВЕРХУ архива (оно новее содержимого архива)

wa = c.write_doc(text=arch_new, name="cc_log_archive")
print("WRITE архив:", wa.get("ok"), "| len:", len(arch_old), "→", len(arch_new))
if not wa.get("ok"):
    print("Архив НЕ записан — cc_log НЕ подрезаю. Стоп.")
    raise SystemExit(1)

# сверка образца: перечитать архив, убедиться что перенесённое там
ra2 = c._call("read_doc", name="cc_log_archive")
sample = old_part[:120]
if not ra2.get("ok") or sample not in ra2.get("text", ""):
    print("СВЕРКА архива ПРОВАЛЕНА — cc_log НЕ подрезаю. Стоп.", ra2.get("ok"))
    raise SystemExit(1)
print("Сверка архива: образец найден, ok")

w = c.write_doc(text=keep_part + "\n", name="cc_log")
print("WRITE cc_log (подрезан):", w.get("ok"), "| len:", len(old), "→", len(keep_part) + 1)
