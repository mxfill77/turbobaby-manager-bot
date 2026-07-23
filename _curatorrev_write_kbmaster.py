from bridge_client import BridgeClient
KB_MASTER_ID = "1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc"
c = BridgeClient()
with open("/root/turbobaby-manager-bot/_curatorrev_kbmaster_snapshot.txt", encoding="utf-8") as f:
    new_text = f.read()
print("NEW LEN:", len(new_text))
w = c.write_doc(new_text, id=KB_MASTER_ID)
print("WRITE:", w)
r = c._call("read_doc", id=KB_MASTER_ID)
t = r.get("text") or ""
print("READBACK LEN:", len(t), "MATCH:", len(t) == len(new_text))
print("CURATOR MENTIONS:", t.count("КУРАТОР ЦЕЛЕЙ"))
