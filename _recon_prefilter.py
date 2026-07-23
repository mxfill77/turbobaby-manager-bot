"""Stage 1 (read-only): regex prefilter of delivery messages.
Counts candidates matching _RETURN_WORDS ∪ _HANDOVER_WORDS, plus signal breakdown
on TEXT ONLY (no parse yet). Nothing is written anywhere."""
import json

PATH = "/root/turbobaby-manager-bot/_delivery_6m.jsonl"

_RETURN_WORDS = ("верну", "вернул", "вернулся", "возврат", "сдал", "сдаёт", "сдает",
                 "приёмк", "приемк", "забрал", "отдал", "клиент верн")
_HANDOVER_WORDS = ("выда", "повезу клиент", "везу клиент", "доставлю клиент", "доставляю клиент",
                   "отвезу клиент", "клиент забира", "клиент забер", "вручаю", "передаю клиент",
                   "повёз клиент", "повез клиент", "уезжает к клиент", "уходит клиент")

rows = []
with open(PATH, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))

total = len(rows)
ret_hits = ho_hits = both = ret_only = ho_only = 0
cand = []
for r in rows:
    blob = (r.get("text") or "").lower()
    rw = any(w in blob for w in _RETURN_WORDS)
    hw = any(w in blob for w in _HANDOVER_WORDS)
    if rw or hw:
        cand.append((r, rw, hw))
    if rw:
        ret_hits += 1
    if hw:
        ho_hits += 1
    if rw and hw:
        both += 1
    elif rw:
        ret_only += 1
    elif hw:
        ho_only += 1

print(f"total messages         : {total}")
print(f"candidates (R∪H)       : {len(cand)}")
print(f"  return-word hits      : {ret_hits}")
print(f"  handover-word hits    : {ho_hits}")
print(f"  text both R&H         : {both}")
print(f"  text ret-only         : {ret_only}")
print(f"  text ho-only          : {ho_only}")

# which return-words / handover-words dominate (so we understand noise)
from collections import Counter
rc, hc = Counter(), Counter()
for r, rw, hw in cand:
    blob = (r.get("text") or "").lower()
    for w in _RETURN_WORDS:
        if w in blob:
            rc[w] += 1
    for w in _HANDOVER_WORDS:
        if w in blob:
            hc[w] += 1
print("\nreturn-word frequency:", dict(rc.most_common()))
print("handover-word frequency:", dict(hc.most_common()))
print("\n--- sample 'text both' messages (verbatim) ---")
shown = 0
for r, rw, hw in cand:
    if rw and hw and shown < 20:
        print(f"[{r.get('date')}] {r.get('author')}: {r.get('text')!r}")
        shown += 1
