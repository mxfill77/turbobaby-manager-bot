import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
from datetime import datetime, timezone

UTC = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

LOG_LINE = f"DONE {UTC} UTC: [куратор цели 73, шаг 1] DNS-разведка turbophuket.com — NS: ns0.wixdns.net, ns1.wixdns.net (Wix DNS); A: 185.230.63.171/186/107 (Wix-хостинг); wa.=NXDOMAIN (субдомен свободен). Read-only, правок нет."

PULSE = f"{UTC} UTC | 🟢 | [куратор 73 шаг 1] DNS-разведка turbophuket.com завершена: Wix NS, 3×A, wa.=свободен | ничего не жду | детали→cc_log {UTC[:10]}"

def insert_under_vrezka(content, new_line):
    lines = content.split("\n")
    insert_pos = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and all(c == '═' for c in stripped):
            insert_pos = i + 1
            break
    new_lines = lines[:insert_pos] + [new_line, ""] + lines[insert_pos:]
    return "\n".join(new_lines)

c = BridgeClient()

r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print(f"READ FAIL: {r}", file=sys.stderr)
    sys.exit(1)

old = r.get("text", "")
new = insert_under_vrezka(old, LOG_LINE)
w = c.write_doc(text=new, name="cc_log")
print(f"cc_log: {'OK' if w.get('ok') else 'FAIL ' + str(w)}")

wp = c.write_doc(text=PULSE, name="pulse")
print(f"pulse: {'OK' if wp.get('ok') else 'FAIL ' + str(wp)}")
