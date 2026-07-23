import asyncio, sys, os
# Allow network even if ORCH_TEST_MODE is set
os.environ['BRIDGE_ALLOW_NETWORK'] = '1'
sys.path.insert(0, '/root/turbobaby-manager-bot')
os.chdir('/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

def _insert_under_vrezka(content: str, new_entry: str) -> str:
    """Insert new_entry after the last ═-only line (header block closing)."""
    lines = content.split('\n')
    header_end_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and all(c == '═' for c in stripped):
            header_end_idx = i
    if header_end_idx >= 0:
        lines.insert(header_end_idx + 1, '')
        lines.insert(header_end_idx + 1, new_entry)
        return '\n'.join(lines)
    else:
        return new_entry + '\n\n' + content

c = BridgeClient()

# Read cc_log
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print(f"READ FAILED: {r}")
    sys.exit(1)

old = r.get("text", "")
new_entry = "DONE 2026-07-17 UTC (headless): тест 6 — задача принята и исполнена, контур работает"
new = _insert_under_vrezka(old, new_entry)

w = c.write_doc(text=new, name="cc_log")
print(f"cc_log write: {w}")
