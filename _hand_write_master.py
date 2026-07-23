"""HANDOFF 05.07: записать обновлённый KB_MASTER (§3/§4/§7 + уроки) обратно в Brain по id."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

MASTER_ID = "1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc"
with open("/root/turbobaby-manager-bot/_kb_master_work.txt", encoding="utf-8") as f:
    text = f.read()
assert text.strip(), "empty text — abort"
print("writing len(codepoints):", len(text))

c = BridgeClient()
w = c.write_doc(text=text, id=MASTER_ID)
print("write ok:", w.get("ok"), "| resp:", {k: w.get(k) for k in ("ok", "bytes", "len", "error") if k in w})

# верификация: перечитать и сверить длину code points
r = c._call("read_doc", id=MASTER_ID)
back = r.get("text", "")
print("read-back ok:", r.get("ok"), "| len:", len(back), "| match:", len(back) == len(text))
