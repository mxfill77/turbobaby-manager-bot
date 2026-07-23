"""Подрезка cc_log (гигиена, триггер >40КБ + конец сессии): записи старше 2026-07-03 → архив.
Порядок: бэкап /tmp → АРХИВ ПИШЕТСЯ ПЕРВЫМ (prepend, старое сверху) + сверка → подрезка cc_log.
Врезка (шапка до последней ═-only строки в начале) сохраняется. Зелёная зона."""
import re
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

TODAY = "2026-07-03"
MARK = re.compile(r"^(DONE|PLAN|NOTE|WAITING|BLOCKED|SKIPPED)\s+(\d{4}-\d{2}-\d{2})")

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ cc_log FAIL — стоп:", r)
    raise SystemExit(1)
text = r.get("text", "")

with open("/tmp/cc_log_backup_prune_0307.txt", "w", encoding="utf-8") as f:
    f.write(text)
print("BACKUP /tmp/cc_log_backup_prune_0307.txt:", len(text), "chars")

lines = text.split("\n")
hdr_end = 0
for i, ln in enumerate(lines[:80]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        hdr_end = i + 1
header = lines[:hdr_end]
body = lines[hdr_end:]

# режем body на блоки-записи по маркерам PREFIX + дата
blocks, cur = [], []
for ln in body:
    if MARK.match(ln):
        if cur:
            blocks.append(cur)
        cur = [ln]
    else:
        cur.append(ln)
if cur:
    blocks.append(cur)

keep, old = [], []
for b in blocks:
    m = MARK.match(b[0])
    if m and m.group(2) < TODAY:
        old.append(b)
    else:
        keep.append(b)

print("blocks: keep(today/шапочные)=%d old=%d" % (len(keep), len(old)))
if not old:
    print("Нечего архивировать — выходим без записи.")
    raise SystemExit(0)

old_text = "\n".join("\n".join(b) for b in old).strip("\n")

ra = c._call("read_doc", name="cc_log_archive")
if not ra.get("ok"):
    print("READ архива FAIL — НЕ подрезаю:", ra)
    raise SystemExit(1)
arch_old = ra.get("text", "")
arch_new = old_text + "\n\n" + arch_old
wa = c.write_doc(text=arch_new, name="cc_log_archive")
print("WRITE archive:", wa.get("ok"), "| arch_len:", len(arch_old), "→", len(arch_new))
if not wa.get("ok"):
    print("АРХИВ НЕ ЗАПИСАН — cc_log НЕ трогаю.")
    raise SystemExit(1)

# сверка образца: первая строка старейшего блока должна быть в архиве
probe = old[-1][0][:80]
ra2 = c._call("read_doc", name="cc_log_archive")
if not (ra2.get("ok") and probe in ra2.get("text", "")):
    print("СВЕРКА АРХИВА ПРОВАЛЕНА (образец не найден) — cc_log НЕ трогаю. probe:", probe)
    raise SystemExit(1)
print("Сверка архива ok (образец найден):", probe[:60])

new_cc = "\n".join(header) + ("\n" if header else "") + "\n".join("\n".join(b) for b in keep).strip("\n") + "\n"
w = c.write_doc(text=new_cc, name="cc_log")
print("WRITE cc_log:", w.get("ok"), "| len:", len(text), "→", len(new_cc))
