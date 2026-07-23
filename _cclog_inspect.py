from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient
import re
b = BridgeClient()
cc = b._call("read_doc", name="cc_log").get("text") or ""
# бэкап на диск
import io
path = "/tmp/claude-0/-root-turbobaby-manager-bot/de0bcc53-2bb9-43ea-8f40-d32c5dc0212b/scratchpad/cclog_backup_20260627.txt"
with open(path, "w", encoding="utf-8") as f:
    f.write(cc)
print("BACKUP saved:", path, "chars:", len(cc))
lines = cc.splitlines()
print("total lines:", len(lines))
# ═-only строки (врезка)
ed = [i for i,l in enumerate(lines) if l.strip() and set(l.strip())=={"═"}]
print("═-only line indices:", ed)
# Первые 8 строк (шапка/врезка/верх)
print("--- TOP 8 ---")
for i in range(min(8,len(lines))):
    print(f"{i:4}| {lines[i][:90]}")
# даты записей: строки начинающиеся с маркера + дата
date_re = re.compile(r'^(PLAN|DONE|NOTE|BLOCKED|WAITING|SKIPPED)\s+(\d{4}-\d{2}-\d{2})')
first_2606 = None
for i,l in enumerate(lines):
    m = date_re.match(l)
    if m and m.group(2) <= "2026-06-26":
        first_2606 = i
        break
print("--- первая запись 26.06 или старше: индекс", first_2606)
if first_2606 is not None:
    for j in range(max(0,first_2606-2), min(len(lines), first_2606+2)):
        print(f"{j:4}| {lines[j][:90]}")
# счётчики
import collections
cnt = collections.Counter()
for l in lines:
    m = date_re.match(l)
    if m: cnt[m.group(2)] += 1
print("--- записи по датам:", dict(sorted(cnt.items(), reverse=True)))
