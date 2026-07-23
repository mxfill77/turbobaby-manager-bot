"""Stage 2-4 (read-only): parse candidates with claude.quick, apply BOTH priority
formulas, count divergences. closing is NOT written; nothing is mutated. CRM/vision
handback branch of _is_return_context is OFFLINE-unavailable (no live bridge, no photos)
→ return_signal here = (event_type=='return') OR _RETURN_WORDS. Noted in report."""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, "/root/turbobaby-manager-bot")
from claude_client import ClaudeClient
from splinter import SERVICING_SYSTEM, _parse_json

PATH = "/root/turbobaby-manager-bot/_delivery_6m.jsonl"
OUT = "/root/turbobaby-manager-bot/_recon_result.json"

_RETURN_WORDS = ("верну", "вернул", "вернулся", "возврат", "сдал", "сдаёт", "сдает",
                 "приёмк", "приемк", "забрал", "отдал", "клиент верн")
_HANDOVER_WORDS = ("выда", "повезу клиент", "везу клиент", "доставлю клиент", "доставляю клиент",
                   "отвезу клиент", "клиент забира", "клиент забер", "вручаю", "передаю клиент",
                   "повёз клиент", "повез клиент", "уезжает к клиент", "уходит клиент")

client = ClaudeClient()

rows = []
with open(PATH, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            rows.append(json.loads(line))

# Stage 1: regex prefilter
cand = []
for r in rows:
    blob = (r.get("text") or "").lower()
    rw = any(w in blob for w in _RETURN_WORDS)
    hw = any(w in blob for w in _HANDOVER_WORDS)
    if rw or hw:
        cand.append({"row": r, "rw": rw, "hw": hw})

print(f"candidates to parse: {len(cand)}", flush=True)

# Stage 2: parse ONLY candidates with claude.quick (same prompt as splinter)
def do_parse(c):
    text = c["row"].get("text") or ""
    raw = client.quick(SERVICING_SYSTEM, text, max_tokens=300)
    c["parsed"] = _parse_json(raw)
    c["et"] = (c["parsed"] or {}).get("event_type")
    return c

with ThreadPoolExecutor(max_workers=8) as ex:
    cand = list(ex.map(do_parse, cand))

print("parse done", flush=True)

# Stage 3-4: signals + two formulas
def signals(c):
    et = c["et"]
    ret_sig = (et == "return") or c["rw"]
    ho_sig = (et == "handover") or c["hw"]
    return ret_sig, ho_sig

both = ret_only = ho_only = none = 0
divergence = []           # old loses closing, new catches (both signals True)
for c in cand:
    ret_sig, ho_sig = signals(c)
    # OLD 1391119: handover wins  -> ho_ctx first, ret only if not ho
    old_ho = ho_sig
    old_ret = (not old_ho) and ret_sig
    old_closing = old_ret
    # NEW 438b286: return wins -> ret_ctx first, ho only if not ret
    new_ret = ret_sig
    new_ho = (not new_ret) and ho_sig
    new_closing = new_ret
    c["old_closing"] = old_closing
    c["new_closing"] = new_closing
    if ret_sig and ho_sig:
        both += 1
    elif ret_sig:
        ret_only += 1
    elif ho_sig:
        ho_only += 1
    else:
        none += 1
    if old_closing != new_closing:
        divergence.append(c)

print("\n===== RESULT =====")
print(f"candidates                 : {len(cand)}")
print(f"  both (ret & ho signals)  : {both}")
print(f"  ret-only                 : {ret_only}")
print(f"  ho-only                  : {ho_only}")
print(f"  none (parse-only noise)  : {none}")
print(f"divergences (old loses closing, new catches): {len(divergence)}")
print(f"  => OLD closing total     : {sum(1 for c in cand if c['old_closing'])}")
print(f"  => NEW closing total     : {sum(1 for c in cand if c['new_closing'])}")

print("\n===== CONFLICT EXAMPLES (both signals True; OLD=no closing, NEW=closing) =====")
for i, c in enumerate(divergence, 1):
    r = c["row"]
    print(f"\n#{i} [{r.get('date')}] author={r.get('author')}")
    print(f"   text   : {r.get('text')!r}")
    print(f"   parsed : type={(c['parsed'] or {}).get('type')} event_type={c['et']} bike={(c['parsed'] or {}).get('bike')}")
    print(f"   regex  : ret_word={c['rw']} ho_word={c['hw']}")

# persist for any follow-up (local file only, no tables touched)
dump = []
for c in cand:
    dump.append({"date": c["row"].get("date"), "author": c["row"].get("author"),
                 "text": c["row"].get("text"), "et": c["et"], "rw": c["rw"], "hw": c["hw"],
                 "old_closing": c["old_closing"], "new_closing": c["new_closing"]})
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(dump, f, ensure_ascii=False, indent=1)
print(f"\nsaved detail -> {OUT}")
