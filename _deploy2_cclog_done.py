"""DONE в cc_log (конверт 2 одобренной заявки деплоя Bridge — read-only сверка прода) + пульс —
ОДНА операция. Зелёная зона. Врезка сохраняется: вставка ПОД шапкой (после ═-only строки)."""
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

note = (
"DONE " + ts + " UTC: [конверт 2 деплоя Bridge] «да» получено, headless сверил ПРОД read-only — "
"деплой ЕЩЁ НЕ выполнен, всё ждёт ручных шагов из Termux.\n"
"Проверка прода (curl GET, зелёное): ping ok (v1.0.0 alive); quote_price → unknown_action "
"(нового экшена на проде НЕТ); get_pending БЕЗ поля statuses (склейка CSV на прод не долетела). "
"Вывод: clasp push/redeploy ещё не сделаны — ожидаемо, clasp login = интерактивный OAuth, headless "
"исполнить не может (красное + ask-гейт), обходов не искал.\n"
"Готовность к ручному деплою ПОДТВЕРЖДЕНА повторно: зеркало /root/turbobaby-bridge-gs содержит "
"QuotePrice.js + роутинг quote_price в Bridge.js (GET/POST/help) + statuses в BotData.js getPending_; "
"node --check чист (QuotePrice/Bridge/BotData); бэкап _bridge_bak-quoteprice-20260703/ на месте "
"(без QuotePrice.js = корректный снимок ДО). Откат = clasp redeploy той же deployment на прошлую версию.\n"
"ХВОСТ (руками из Termux, владелец): cd /root/turbobaby-bridge-gs → clasp login → clasp push → "
"clasp redeploy AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw. "
"После — задача в 328: «проверь деплой Bridge» (ping / quote_price bike=4957 08.07–15.07 → ~2217/317, "
"депозит 3000 / get_pending со statuses). Затем зелёная обёртка quote_price() в bridge_client.py.\n"
)

lines = old.split("\n")
ins = 0
for i, ln in enumerate(lines[:80]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        ins = i + 1
new = "\n".join(lines[:ins]) + ("\n" if ins else "") + note + "\n" + "\n".join(lines[ins:])
w = c.write_doc(text=new, name="cc_log")
print("WRITE cc_log:", w.get("ok"), "| old_len:", len(old), "new_len:", len(new), "| insert_at_line:", ins)

pulse = (ts + " | 🟡 | конверт 2 деплоя Bridge: прод сверен — quote_price/statuses ЕЩЁ НЕ на проде, "
         "готовность зеркала/бэкапа подтверждена | жду: владелец руками из Termux clasp login → push → "
         "redeploy (команды в cc_log), после — задача «проверь деплой Bridge» | детали→cc_log запись "
         "«конверт 2 деплоя Bridge " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
