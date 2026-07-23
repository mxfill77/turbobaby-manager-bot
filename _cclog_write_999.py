import sys
import os
sys.path.insert(0, '/root/turbobaby-manager-bot')
os.chdir('/root/turbobaby-manager-bot')
# Allow network even in ORCH_TEST_MODE (this is a real headless task, not a test)
os.environ["BRIDGE_ALLOW_NETWORK"] = "1"

from dotenv import load_dotenv
load_dotenv('/root/turbobaby-manager-bot/.env')

from bridge_client import BridgeClient
from cclog import _insert_under_vrezka

client = BridgeClient()

# Step 1: read cc_log
r = client._call("read_doc", name="cc_log")
if not r.get("ok"):
    print(f"ERROR reading cc_log: {r}", file=sys.stderr)
    sys.exit(1)

old = r.get("text", "")
print(f"Read cc_log OK, length={len(old)}")

# Step 2: insert the line below the header block
new_line = "DONE 2026-07-17 02:12 UTC: [конверт 999] задача-заготовка — тело «сделать нечто» / «X» — плейсхолдеры, не исполнено (нет конкретного действия)"
new_content = _insert_under_vrezka(old, new_line)
print(f"New content length={len(new_content)}")

# Step 3: write cc_log
w = client.write_doc(text=new_content, name="cc_log")
if not w.get("ok"):
    print(f"ERROR writing cc_log: {w}", file=sys.stderr)
    sys.exit(1)
print(f"Write cc_log OK: {w}")

# Step 4: write pulse
pulse = "2026-07-17 02:12 | 🟢 | [конверт 999] заготовка без реального содержания — done без действия | ничего не жду | детали→cc_log 2026-07-17 конверт 999"
wp = client.write_doc(text=pulse, name="pulse")
if not wp.get("ok"):
    print(f"ERROR writing pulse: {wp}", file=sys.stderr)
    sys.exit(1)
print(f"Write pulse OK: {wp}")
print("All done.")
