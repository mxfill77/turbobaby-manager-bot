"""Read-only: классификация ошибок splinter.log с старта 08.07 15:09:52 (строка 89074)."""
import re
from collections import Counter

PATH = "/root/turbobaby-manager-bot/splinter.log"
START = 89074

lines = open(PATH, encoding="utf-8", errors="replace").readlines()
hits = []
for i, ln in enumerate(lines[START - 1:], start=START):
    if "[ERROR]" in ln or "[CRITICAL]" in ln or "Traceback (most recent" in ln:
        hits.append((i, ln.rstrip()))

print("всего:", len(hits))
norm = Counter()
for i, ln in hits:
    msg = re.sub(r"^[\d\-]+ [\d:,]+ ", "", ln)
    msg = re.sub(r"\d+", "N", msg)
    norm[msg[:160]] += 1

for msg, cnt in norm.most_common(15):
    print(f"{cnt:3d}  {msg}")
print("---- примеры сырых строк по каждому классу ----")
seen = set()
for i, ln in hits:
    key = re.sub(r"\d+", "N", re.sub(r"^[\d\-]+ [\d:,]+ ", "", ln))[:160]
    if key not in seen:
        seen.add(key)
        print(f"line {i}: {ln[:220]}")
