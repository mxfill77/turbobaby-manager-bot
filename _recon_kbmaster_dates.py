"""Read-only: все даты в KB_MASTER — оценка свежести (максимальная дата обновления в теле)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient
import re

c = BridgeClient()
r = c._call("read_doc", id="1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc")
txt = r.get("text", "") or ""
dates = re.findall(r"\b(\d\d)\.(\d\d)\.2026\b|\b2026-(\d\d)-(\d\d)\b", txt)
norm = set()
for d, m, m2, d2 in dates:
    if d:
        norm.add(f"2026-{m}-{d}")
    else:
        norm.add(f"2026-{m2}-{d2}")
print("уникальные даты в KB_MASTER:", sorted(norm))
print("MAX (оценка последнего обновления):", max(norm) if norm else "нет")
# контекст строк с максимальной датой
mx = max(norm) if norm else ""
mx_dd = f"{mx[8:10]}.{mx[5:7]}" if mx else ""
for ln in txt.split("\n"):
    if mx and (mx in ln or (mx_dd and mx_dd + ".2026" in ln)):
        print(" |", ln.strip()[:180])
