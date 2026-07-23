#!/usr/bin/env python3
"""Ревизия 07.07: подрезка cc_log (правило конца сессии) — всё старше 07.07 в архив.
Порядок: свежий read cc_log → снимок на диск → АРХИВ ПИШЕТСЯ ПЕРВЫМ + сверка → потом подрезка cc_log.
Врезка матчится по ═-only-строке. Пишем ТОЛЬКО если read вернул ok."""
import re, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

TODAY = "2026-07-07"
ENTRY_RE = re.compile(r"^(DONE|PLAN|NOTE|BLOCKED|WAITING|SKIPPED) (\d{4}-\d{2}-\d{2})", re.M)

c = BridgeClient(timeout=300)

r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("cc_log read FAIL:", r); sys.exit(1)
log = r.get("text") or r.get("content") or ""
with open("/tmp/revision0707/cc_log.preprune.md", "w") as f:
    f.write(log)

# врезка: всё до конца первой ═-only строки включительно
lines = log.split("\n")
hdr_end = None
for i, ln in enumerate(lines):
    if ln and set(ln.strip()) == {"═"}:
        hdr_end = i
        break
if hdr_end is None:
    print("врезка (═-строка) не найдена — стоп, ничего не трогаю"); sys.exit(1)
header = "\n".join(lines[: hdr_end + 1])
body = "\n".join(lines[hdr_end + 1:])

# граница: первая запись со старой датой
cut = None
for m in ENTRY_RE.finditer(body):
    if m.group(2) < TODAY:
        cut = m.start()
        break
if cut is None:
    print("старых записей нет — подрезка не нужна"); sys.exit(0)
today_part = body[:cut].rstrip("\n")
old_part = body[cut:].strip("\n")
print(f"cc_log={len(log)}c: сегодня={len(today_part)}c, в архив={len(old_part)}c")

ra = c._call("read_doc", name="cc_log_archive")
if not ra.get("ok"):
    print("archive read FAIL:", ra); sys.exit(1)
arch = ra.get("text") or ra.get("content") or ""
with open("/tmp/revision0707/cc_log_archive.preprune.md", "w") as f:
    f.write(arch)

new_arch = old_part + "\n\n" + arch
wa = c.write_doc(new_arch, name="cc_log_archive")
if not wa.get("ok"):
    print("archive WRITE FAIL:", wa, "— cc_log НЕ трогаю"); sys.exit(1)
ba = c._call("read_doc", name="cc_log_archive")
gota = (ba.get("text") or ba.get("content") or "") if ba.get("ok") else ""
sample = old_part[:120]
if len(gota) != len(new_arch) or not gota.startswith(sample):
    print(f"archive VERIFY FAIL (len {len(gota)} vs {len(new_arch)}, top-sample={gota[:120]!r}) — cc_log НЕ трогаю")
    sys.exit(1)
print(f"архив записан и сверен: {len(arch)} → {len(new_arch)}c, образец сверху совпал")

new_log = header + "\n\n" + today_part + "\n"
wl = c.write_doc(new_log, name="cc_log")
if not wl.get("ok"):
    print("cc_log WRITE FAIL:", wl); sys.exit(1)
bl = c._call("read_doc", name="cc_log")
gotl = (bl.get("text") or bl.get("content") or "") if bl.get("ok") else ""
ok = len(gotl) == len(new_log) and gotl.startswith("📦") and "2026-07-06" not in gotl
print(f"cc_log подрезан: {len(log)} → {len(new_log)}c, verify={'OK' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
