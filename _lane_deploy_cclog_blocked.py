"""BLOCKED в cc_log + пульс: конверт заявки 10 — clasp деплой из headless невозможен."""
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
"BLOCKED " + ts + " UTC: конверт заявки 10 (деплой Bridge lane) — ВЫПОЛНИТЬ ИЗ HEADLESS НЕЛЬЗЯ, "
"два независимых блокера, обходить не стал (обход ask-гейта запрещён).\n"
"1) clasp push/redeploy в ask-блоке .claude/settings.json (строки 129-132) — headless-CC ask пройти "
"не может by design (демон без --dangerously-skip-permissions). «Да» на карточку 10 гейт движка НЕ снимает.\n"
"2) clasp-токен ПРОТУХ: clasp list-deployments → invalid_grant/invalid_rapt (нужен повторный "
"clasp login под info@turbophuket.com, браузерный OAuth) — т.е. даже интерактивный CC сейчас не задеплоит "
"без релогина.\n"
"Сделано до блока: гейт 35/35 зелёный; зеркало сверено (diff BotData.js.bak-lane-20260704 → ровно "
"lane-объём: QUEUE_HEADERS 9 кол., queueLane_, enqueue/get_pending/claim фильтры), node --check чисто. "
"Прод-Bridge НЕ тронут, версия не менялась, тестовую pc-задачу НЕ заводил.\n"
"ЧТО НУЖНО ОТ ФИЛИППА (Termux, tmux cc, по одному): 1) cd /root/turbobaby-bridge-gs  "
"2) clasp login  (браузер, info@turbophuket.com)  3) clasp push  "
"4) clasp redeploy AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw  "
"— либо после clasp login сказать интерактивному CC «деплой Bridge по заявке 10», он пройдёт ask руками "
"Филиппа и сам сделает проверку (ping + enqueue lane=pc тест + get_pending без lane не видит).\n"
"ХВОСТЫ включения полосы pc (без изменений): деплой Bridge (этот блок) → PC_DEV_TOPIC_ID уже в .env "
"(commit 2460065) → ПК-агент lane=pc отдельной задачей.\n"
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

pulse = (ts + " | 🔴 | заявка 10 (деплой Bridge lane) BLOCKED: clasp в ask-гейте headless + токен протух "
         "(invalid_grant); гейт 35/35, зеркало сверено, прод не тронут | нужен Филипп: clasp login → push → "
         "redeploy (команды в логе) | детали→cc_log запись «BLOCKED конверт заявки 10 " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
