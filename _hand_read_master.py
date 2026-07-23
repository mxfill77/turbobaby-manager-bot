"""Read-only: дамп KB_MASTER (по id) в рабочий файл репо для правки HANDOFF."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", id="1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc")
text = r.get("text", "")
print("ok:", r.get("ok"), "| len:", len(text))
with open("/root/turbobaby-manager-bot/_kb_master_work.txt", "w", encoding="utf-8") as f:
    f.write(text)
print("saved _kb_master_work.txt")
