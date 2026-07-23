"""Read-only: свежесть Brain-доков (pulse, KB_MASTER, cc_log) — id из манифеста + верхние таймстампы контента."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient
import re

c = BridgeClient()

man = c._call("list_brain").get("manifest", {})
ids = {
    "pulse": man.get("pulse"),
    "cc_log": man.get("cc_log"),
    "KB_MASTER": "1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc",
}
print("MANIFEST ids:", ids)

TS = re.compile(r"20\d\d-\d\d-\d\d[ T]\d\d:\d\d")

for key, doc_id in ids.items():
    if key == "KB_MASTER":
        r = c._call("read_doc", id=doc_id)
    else:
        r = c._call("read_doc", name=key)
    txt = r.get("text", "") or ""
    print(f"\n=== {key} | ok={r.get('ok')} | len={len(txt)} ===")
    # первые таймстампы в теле (верх дока = свежайшее для pulse/cc_log)
    found = TS.findall(txt[:4000])
    print("top timestamps:", found[:6])
    # первые 3 непустые строки
    shown = 0
    for ln in txt.split("\n"):
        if ln.strip():
            print(" |", ln[:160])
            shown += 1
            if shown >= 4:
                break
