from bridge_client import BridgeClient
KB_MASTER_ID = "1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc"
c = BridgeClient()
r = c._call("read_doc", id=KB_MASTER_ID)
if not r.get("ok"):
    print("READ FAILED:", r)
else:
    t = r.get("text") or ""
    print("LEN:", len(t))
    with open("/root/turbobaby-manager-bot/_curatorrev_kbmaster_snapshot.txt", "w", encoding="utf-8") as f:
        f.write(t)
    print("SNAPSHOT WRITTEN")
