"""Read-only: WARNING/ERROR из splinter.log за последние 24 часа — паттерны и счётчики."""
import re
from collections import Counter
from datetime import datetime, timedelta

CUTOFF = datetime(2026, 7, 1, 21, 33)  # now - 24h (UTC)
LOG = "/root/turbobaby-manager-bot/splinter.log"

pat = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ \[(\w+)\] ([^:]+): (.*)")
rows = []
with open(LOG, encoding="utf-8", errors="replace") as f:
    for line in f:
        m = pat.match(line)
        if not m:
            continue
        ts, lvl, src, msg = m.groups()
        if lvl not in ("WARNING", "ERROR", "CRITICAL"):
            continue
        t = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        if t < CUTOFF:
            continue
        rows.append((t, lvl, src.strip(), msg.strip()))

print(f"Всего WARNING/ERROR/CRITICAL за 24ч: {len(rows)}")
lvl_c = Counter(r[1] for r in rows)
print("По уровням:", dict(lvl_c))

def norm(msg):
    s = re.sub(r"\d+", "N", msg)
    s = re.sub(r"'[^']*'", "'X'", s)
    s = re.sub(r'"[^"]*"', '"X"', s)
    return s[:150]

groups = Counter((r[1], r[2], norm(r[3])) for r in rows)
print("\n=== ПАТТЕРНЫ (top-20) ===")
for (lvl, src, msg), n in groups.most_common(20):
    print(f"{n:4}x [{lvl}] {src}: {msg}")

print("\n=== ПОСЛЕДНИЕ 10 сырых ===")
for t, lvl, src, msg in rows[-10:]:
    print(f"{t} [{lvl}] {src}: {msg[:170]}")

# распределение по часам для всплесков
hours = Counter(r[0].strftime("%m-%d %H") for r in rows)
print("\n=== по часам ===")
for h in sorted(hours):
    print(h, hours[h])
