"""Гигиена cc_log: записи старше 2026-07-04 → cc_log_archive (архив ПЕРВЫМ + сверка),
потом подрезка cc_log (шапка + сегодняшнее). Бэкап-снимок в /tmp до правки."""
import re
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

TODAY = "2026-07-04"
c = BridgeClient()

r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ cc_log FAIL:", r)
    raise SystemExit(1)
full = r.get("text", "")
with open("/tmp/cc_log_bak_pcdev829.txt", "w", encoding="utf-8") as f:
    f.write(full)

lines = full.split("\n")
hdr_end = 0
for i, ln in enumerate(lines[:80]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        hdr_end = i + 1
header = lines[:hdr_end]
body = lines[hdr_end:]

ENTRY = re.compile(r"^(DONE|PLAN|NOTE|WAITING|SKIPPED|BLOCKED|RECON)\s+(\d{4}-\d{2}-\d{2})")
keep, arch, cur_keep = [], [], None
for ln in body:
    m = ENTRY.match(ln)
    if m:
        cur_keep = (m.group(2) == TODAY)
    (keep if (cur_keep or cur_keep is None) else arch).append(ln)

arch_text = "\n".join(arch).strip("\n")
if not arch_text:
    print("нечего архивировать — всё сегодняшнее, cc_log не трогаю")
    raise SystemExit(0)

ra = c._call("read_doc", name="cc_log_archive")
if not ra.get("ok"):
    print("READ cc_log_archive FAIL — НЕ архивирую:", ra)
    raise SystemExit(1)
old_arch = ra.get("text", "")
new_arch = arch_text + "\n\n" + old_arch
wa = c.write_doc(text=new_arch, name="cc_log_archive")
print("WRITE archive:", wa.get("ok"), "| arch_add:", len(arch_text), "| arch_total:", len(new_arch))
if not wa.get("ok"):
    raise SystemExit(1)

rb = c._call("read_doc", name="cc_log_archive")
sample = arch_text[:120]
if not rb.get("ok") or sample not in (rb.get("text") or ""):
    print("СВЕРКА АРХИВА НЕ ПРОШЛА — cc_log НЕ режу")
    raise SystemExit(1)
print("сверка архива: образец найден ✅")

new_cclog = "\n".join(header) + ("\n" if header else "") + "\n".join(keep).strip("\n") + "\n"
wc = c.write_doc(text=new_cclog, name="cc_log")
print("WRITE cc_log:", wc.get("ok"), "| было:", len(full), "| стало:", len(new_cclog))
