"""Журнал: DONE о выдаче команд ручного деплоя Bridge (read-only задача из 328) + пульс той же операцией."""
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timezone
from bridge_client import BridgeClient

c = BridgeClient()
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

r = c._call("read_doc", name="cc_log")
assert r.get("ok"), f"read cc_log failed: {r}"
text = r.get("text", "")
if "выданы ДОСЛОВНО команды ручного деплоя Bridge" in text:
    print("маркер уже в cc_log — прошлый write долетел, дубль не пишу")
    raise SystemExit(0)
lines = text.split("\n")
sep = None
for i, ln in enumerate(lines):
    s = ln.strip()
    if s and set(s) == {"═"}:
        sep = i
        break
assert sep is not None, "врезка (═-строка) не найдена"

entry = (
    f"DONE {now}: [задача 328, read-only] выданы ДОСЛОВНО команды ручного деплоя Bridge "
    "из записи «конверт 2 деплоя Bridge» (DONE 13:03): cd /root/turbobaby-bridge-gs → clasp login → "
    "clasp push → clasp redeploy AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw. "
    "Ничего не исполнялось (clasp = красное), только чтение cc_log и вывод в 328."
)
new_text = "\n".join(lines[: sep + 1] + [entry, ""] + lines[sep + 1 :])
w = c._post("write_doc", name="cc_log", text=new_text)
print("cc_log write ok:", w.get("ok"))

pulse = (
    f"{now} | 🟢 | выдал в 328 дословные команды ручного деплоя Bridge (clasp login/push/redeploy) из записи "
    "«конверт 2 деплоя Bridge»; ничего не исполнял | жду: владелец прогонит 3 команды из Termux | "
    "детали→cc_log запись «конверт 2 деплоя Bridge» 03.07"
)
p = c._post("write_doc", name="pulse", text=pulse)
print("pulse write ok:", p.get("ok"))
