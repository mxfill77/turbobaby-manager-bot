"""BLOCKED в cc_log (конверт одобренной заявки 1: деплой Bridge) + пульс — ОДНА операция. Зелёная зона.
Врезка сохраняется: вставка ПОД шапкой (после последней ═-only строки в начале дока)."""
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
"BLOCKED " + ts + " UTC: деплой Bridge (конверт одобренной заявки 1, кнопка «да» нажата) — headless "
"исполнить НЕ может, нужны руки владельца в Termux.\n"
"Что успел (вся зелёная подготовка прогнана заново, к деплою ГОТОВО):\n"
"а) зеркало /root/turbobaby-bridge-gs проверено: QuotePrice.js на месте, роутинг quote_price в "
"Bridge.js (doGet+doPost+help), склейка статусов CSV в BotData.js (getPending_, поле statuses) — "
"оба изменения деплой-дельты в наличии;\n"
"б) бэкап зеркала ДО правок подтверждён: _bridge_bak-quoteprice-20260703/ (без QuotePrice.js — "
"корректный снимок);\n"
"в) node --check чисто по всем трём файлам; гейт venv/bin/python3 gate.py = 33 теста зелёные;\n"
"г) clasp show-authorized-user отвечает «logged in» — но это кэш .clasprc, живой вызов упрётся в "
"invalid_rapt (как в прошлой сессии).\n"
"ПОЧЕМУ блок (два независимых стопора, кнопка «да» их НЕ снимает):\n"
"1) clasp login = интерактивный OAuth (браузер/код) — из headless невыполним в принципе;\n"
"2) clasp push из headless упёрся в ask-гейт движка Claude Code (clasp в ask-списке settings; "
"headless ответить на ask не может, одобрение заявки гейт не обходит — это правильно, обходных "
"путей не искал).\n"
"ЧТО ДЕЛАТЬ ВЛАДЕЛЬЦУ (3 команды руками из Termux, по одной):\n"
"  cd /root/turbobaby-bridge-gs\n"
"  clasp login   (откроет URL — авторизоваться под info@turbophuket.com)\n"
"  clasp push\n"
"  clasp redeploy AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw\n"
"Проверка после (могу прогнать сам зелёной задачей «задача: проверь деплой Bridge»): ping=alive; "
"quote_price bike=4957 08.07-15.07 → ~2217/317, депозит 3000; get_pending CSV → поле statuses "
"(devbot перестанет фоллбэчить). Откат = clasp redeploy той же deployment на прошлую версию.\n"
"Статус честно: технически готово (зеркало+гейт+бэкап), функционально НЕ подтверждено — прод не "
"обновлён, curl-тесты на живом Bridge не прогнаны.\n"
"ХВОСТЫ: 1) владелец: 3 команды выше; 2) после деплоя: проверочная задача (ping/quote_price/"
"get_pending CSV); 3) обёртка quote_price() в bridge_client.py — зелёной задачей после деплоя.\n"
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

pulse = (ts + " | 🔴 | деплой Bridge одобрен кнопкой, но headless исполнить clasp НЕ может "
         "(clasp login = интерактивный OAuth + ask-гейт движка) | жду: 3 команды руками из Termux — "
         "cd /root/turbobaby-bridge-gs → clasp login → clasp push → clasp redeploy AKfycbxNC9gCM7-"
         "a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw | детали→cc_log запись "
         "«BLOCKED деплой Bridge " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
