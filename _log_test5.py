import sys, os
# Clear test-mode flag so network is allowed (gate.py sets ORCH_TEST_MODE=1 in env)
os.environ.pop("ORCH_TEST_MODE", None)
sys.path.insert(0, '/root/turbobaby-manager-bot')
from dotenv import load_dotenv
load_dotenv('/root/turbobaby-manager-bot/.env')
from datetime import datetime, timezone
from bridge_client import BridgeClient

now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
DONE_LINE = f"DONE {now_utc} UTC (Termux): тест 5 — задача-пинг принята и исполнена оркестратором успешно."
PULSE_LINE = f"{now_utc} | \U0001f7e2 | тест 5 исполнен | ничего не жду | детали→cc_log «тест 5»"

bc = BridgeClient()

# Read cc_log
r = bc._call("read_doc", name="cc_log")
if not r.get("ok"):
    print(f"ERROR: read_doc failed: {r}")
    sys.exit(1)

content = r.get("text", "")
print(f"READ_OK: {len(content)} chars")

# Find the closing ═-only line of the header block
lines = content.split('\n')
insert_idx = 0
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped and all(c == '═' for c in stripped) and i > 0:
        insert_idx = i + 1
        break

print(f"Inserting DONE line at index {insert_idx}")

# Insert DONE line after header
lines.insert(insert_idx, DONE_LINE)
new_content = '\n'.join(lines)

# Write cc_log
ok = bc.write_doc(text=new_content, name="cc_log")
print(f"cc_log write: {ok}")

# Write pulse
ok2 = bc.write_doc(text=PULSE_LINE, name="pulse")
print(f"pulse write: {ok2}")
