"""Read-only разведка (шаг 1/7 родитель 33): pulse, cc_log (сегодня), KB_MASTER, KB_ROADMAP_v2."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()

print("========== PULSE ==========")
r = c._call("read_doc", name="pulse")
print("ok:", r.get("ok"))
print(r.get("text", "")[:2000])

print("\n========== CC_LOG (первые 250 строк) ==========")
r = c._call("read_doc", name="cc_log")
print("ok:", r.get("ok"), "| len:", len(r.get("text", "")))
lines = r.get("text", "").split("\n")
for i, ln in enumerate(lines[:250]):
    print(f"{i:3} | {ln[:160]}")

print("\n========== KB_MASTER ==========")
r = c._call("read_doc", id="1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc")
print("ok:", r.get("ok"), "| len:", len(r.get("text", "")))
open("/tmp/_kb_master.txt", "w").write(r.get("text", ""))
print("saved to /tmp/_kb_master.txt")

print("\n========== KB_ROADMAP_v2 ==========")
r = c._call("read_doc", name="KB_ROADMAP_v2")
if not r.get("ok"):
    r = c._call("read_doc", name="roadmap")
print("ok:", r.get("ok"), "| len:", len(r.get("text", "")))
open("/tmp/_kb_roadmap.txt", "w").write(r.get("text", ""))
print("saved to /tmp/_kb_roadmap.txt")
