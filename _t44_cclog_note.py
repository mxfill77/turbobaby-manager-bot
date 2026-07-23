"""cc_log NOTE (deferred restart демона заблокирован permission-гейтом) + KB_PULSE — ОДНОЙ операцией. Зона 🟢."""
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL — НЕ пишу:", r)
    raise SystemExit(1)
old = r.get("text", "")
ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

entry = (
"NOTE " + ts + " UTC (доводка 43, хвост): deferred restart демона НЕ прошёл — команда "
"systemd-run --on-active=10s systemctl restart orchestrator-daemon упёрлась в permission-гейт "
"(systemd-run нет в allowlist, headless без «да»). Обходить гейт не стал; прямой restart запрещён "
"новым правилом самомодификации. ПОСЛЕДСТВИЯ МИНИМАЛЬНЫ: живой демон УЖЕ крутит код op=other "
"(60c1e43), не подхвачена ТОЛЬКО преамбула v3.1 (текст правила в промпте будущих задач). "
"ФИЛИППУ (одно из): (а) руками systemctl restart orchestrator-daemon (вне headless-задачи — безопасно); "
"(б) добавить в allow .claude/settings.json команду systemd-run --on-active=* systemctl restart "
"orchestrator-daemon — тогда правило самомодификации заработает end-to-end (сам allow не расширял — "
"решение о новых разрешениях за владельцем).\n"
)

lines = old.splitlines(keepends=True)
ins = 0
for i, ln in enumerate(lines[:10]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        ins = i + 1
        break
new = "".join(lines[:ins]) + entry + "\n" + "".join(lines[ins:])
w = c.write_doc(text=new, name="cc_log")
print("cc_log WRITE:", w.get("ok"), "| вставка после строки", ins, "| old:", len(old), "new:", len(new))

pulse = (ts + " | 🟡 | доводка 43 done: фикс op=other был полным (60c1e43, демон на нём), правило самомодификации "
         "вписано (1a72ca6, CLAUDE.md+преамбула v3.1) — но deferred restart демона заблокирован permission-гейтом "
         "(systemd-run не в allowlist) | жду от Филиппа: руками systemctl restart orchestrator-daemon ИЛИ добавить "
         "systemd-run в allow | детали→cc_log NOTE " + ts)
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
