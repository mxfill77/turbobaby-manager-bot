"""Read-only: найти рамку владельца (30.06) в cc_log и cc_log_archive."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()

for name in ("cc_log", "cc_log_archive"):
    r = c._call("read_doc", name=name)
    text = r.get("text", "")
    print(f"===== {name}: ok={r.get('ok')} len={len(text)} =====")
    lines = text.split("\n")
    # ищем упоминания рамки/чек-листа
    hits = []
    for i, ln in enumerate(lines):
        low = ln.lower()
        if ("рамк" in low) or ("чек-лист владельца" in low) or ("checklist" in low and "владел" in low):
            hits.append(i)
    print("hits:", hits[:40])
    for i in hits[:40]:
        print(f"--- {name}:{i} ---")
        for j in range(max(0, i - 2), min(len(lines), i + 6)):
            print(f"{j:4} | {lines[j][:160]}")
