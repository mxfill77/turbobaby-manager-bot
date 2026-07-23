"""Подрезка cc_log по триггеру >40КБ (протокол CLAUDE.md «ГИГИЕНА cc_log»):
бэкап на /tmp → записи старше ТЕКУЩИХ суток → архив (write ПЕРВЫМ + сверка маркера) → подрезка cc_log.
Врезка (⛔-шапка до закрывающей ═-строки) сохраняется. Зона 🟢. Только по name (не сырые id)."""
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
full = r.get("text", "")

bak = "/tmp/cc_log_backup_trim_" + today + ".txt"
with open(bak, "w") as f:
    f.write(full)
print("бэкап:", bak, len(full), "байт")

lines = full.splitlines(keepends=True)
ins = 0
for i, ln in enumerate(lines[:15]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        ins = i + 1
        break
head, body = "".join(lines[:ins]), lines[ins:]

# граница: первая журнальная строка с датой НЕ сегодня → оттуда и до конца в архив
pat = re.compile(r"^(DONE|PLAN|NOTE|WAITING|SKIPPED|BLOCKED)\s+(\d{4}-\d{2}-\d{2})")
cut = None
for i, ln in enumerate(body):
    m = pat.match(ln)
    if m and m.group(2) != today:
        cut = i
        break
if cut is None:
    print("старых записей нет — подрезка не нужна")
    raise SystemExit(0)
keep, move = "".join(body[:cut]), "".join(body[cut:])
print("остаётся:", len(head) + len(keep), "байт; в архив:", len(move), "байт")

ra = c._call("read_doc", name="cc_log_archive")
if not ra.get("ok"):
    print("READ архива FAIL — стоп, cc_log НЕ трогаю:", ra)
    raise SystemExit(1)
arch_old = ra.get("text", "")

marker = move.strip().splitlines()[0][:80]
wa = c.write_doc(text=move.rstrip("\n") + "\n\n" + arch_old, name="cc_log_archive")
print("архив WRITE:", wa.get("ok"))
if not wa.get("ok"):
    print("архив НЕ записан — cc_log НЕ трогаю")
    raise SystemExit(1)

va = c._call("read_doc", name="cc_log_archive")
if not va.get("ok") or marker not in va.get("text", "")[:2000]:
    print("СВЕРКА архива НЕ прошла — cc_log НЕ трогаю. marker:", marker)
    raise SystemExit(1)
print("сверка архива ✅ (маркер найден)")

w = c.write_doc(text=head + keep, name="cc_log")
print("cc_log подрезан:", w.get("ok"), "| new size:", len(head + keep))
