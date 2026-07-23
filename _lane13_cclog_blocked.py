"""BLOCKED в cc_log + пульс: конверт заявки 13 — clasp-деплой lane-фикса из headless невозможен."""
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ cc_log FAIL — НЕ пишу:", r)
    raise SystemExit(1)
old = r.get("text", "")
ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

note = (
"BLOCKED " + ts + " UTC: конверт заявки 13 (clasp push+redeploy lane-фикса get_pending) — clasp из "
"headless по-прежнему НЕПРОХОДИМ: ask-гейт .claude/settings.json «да» на карточку НЕ снимает "
"(подтверждено второй раз, как в заявке 10; обходить не стал — запрещено).\n"
"СДЕЛАНО до блока: гейт 35/35 зелёный; фикс применён локально (Bridge.js:75 прокинут params.lane в "
"getPending_), бэкап Bridge.js.bak-lanefix-20260704 на месте, diff = ровно 1 одобренная строка, "
"node --check чисто.\n"
"ЖИВОЙ СЕЛФТЕСТ прода (_lane_pc_selftest.py) прогнан: 7/8 PASS — ping ok (первый 404 = транзиент "
"Apps Script, со 2-й попытки alive), enqueue lane=pc ok (id 16), get_pending без lane pc-задачу НЕ видит "
"✅, claim lane=vps → wrong_lane guard ✅, claim lane=pc ok, complete done, в new пусто. "
"ЕДИНСТВЕННЫЙ FAIL: get_pending lane=pc → сервер вернул lane=vps ids=[] — прод-GET-роутер игнорирует "
"lane, т.е. ФИКС В ПРОД НЕ ЗАДЕПЛОЕН, и это ровно то, что фикс чинит. Тестовая задача 16 подчищена "
"(complete done), очередь чистая, прод-Bridge не менялся.\n"
"ЧТО НУЖНО ОТ ФИЛИППА (Termux, по одному; если clasp login уже делал после заявки 10 — шаг 2 пропустить): "
"1) cd /root/turbobaby-bridge-gs  2) clasp login  (браузер, info@turbophuket.com)  3) clasp push  "
"4) clasp redeploy AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw  "
"5) в 328: «задача: прогони _lane_pc_selftest.py» → жду ALL PASS 8/8. Откат = clasp redeploy прошлой версии.\n"
"ХВОСТЫ: деплой lane-фикса (руки Филиппа, этот блок) → повторный селфтест 8/8 → ПК-агент lane=pc "
"отдельной задачей.\n"
)

lines = old.split("\n")
ins = 0
for i, ln in enumerate(lines[:80]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        ins = i + 1
new = "\n".join(lines[:ins]) + ("\n" if ins else "") + note + "\n" + "\n".join(lines[ins:])
wl = c.write_doc(text=new, name="cc_log")
print("WRITE cc_log:", wl.get("ok"), "| insert_at_line:", ins)

pulse = (ts + " | 🟡 | заявка 13: lane-фикс готов локально (бэкап+гейт 35/35+diff 1 строка), селфтест прода "
         "7/8 — падает ТОЛЬКО get_pending lane=pc (фикс не задеплоен); clasp из headless заблокирован ask-гейтом, "
         "«да» его не снимает | нужен Филипп: clasp push + redeploy из Termux (команды в логе), потом селфтест "
         "8/8 | детали→cc_log запись «BLOCKED конверт заявки 13 " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
