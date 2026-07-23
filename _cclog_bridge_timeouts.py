"""DONE в cc_log (разбор таймаутов get_pending) + пульс — ОДНА операция. Зелёная зона (журнал).
Врезку сохраняем: вставка ПОД шапкой (после последней ═-only строки в начале дока)."""
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
"DONE " + ts + " UTC: РАЗБОР таймаутов Bridge get_pending / skip devbot_report (read-only, ТЗ из 328). ИТОГ:\n"
"== ФАКТЫ (splinter.log) ==\n"
"85 строк «Bridge timeout (>60s) for action=get_pending» всего; за 01-02.07 ~30+; skip devbot_report за 01-02.07 = 40 "
"(apscheduler: maximum number of running instances reached (1)). Таймауты идут КЛАСТЕРАМИ (02.07 14:01-14:12 — 9 подряд, "
"по одному в минуту) — окна деградации на стороне Google, не равномерный шум.\n"
"== ГДЕ ТАЙМАУТИТ ==\n"
"bridge_client.py:53 requests.get(..., timeout=60) к Apps Script /exec. Серверный хендлер getPending_ (BotData.js:311) "
"ДЕШЁВЫЙ: одно getRange().getValues() по вкладке очереди, БЕЗ LockService — тормозит не наш код, а хвостовая латентность "
"самого Apps Script /exec (cold start / окна деградации Google). Доля ~0.1-1% вызовов — норма для /exec.\n"
"== ПОЧЕМУ ДУШИТ devbot_report (усилители на нашей стороне) ==\n"
"1) devbot.report_results (каждые 45с) делает ДО 4 ПОСЛЕДОВАТЕЛЬНЫХ get_pending (done/failed/needs_approval/in_progress) "
"— 4 шанса на таймаут за тик; окно деградации = 60-240с на прогон → apscheduler (max_instances=1) скипает следующие тики.\n"
"2) ГЛАВНОЕ: вызовы СИНХРОННЫЕ (requests) прямо в async job — на время таймаута ВСТАЁТ ВЕСЬ event loop PTB: бот не отвечает "
"на кнопки/сообщения до 1-4 минут. Скипы сами по себе безвредны (отчёт опоздает на тик), заморозка бота — реальный вред.\n"
"3) Плюс параллельно ту же очередь опрашивает orchestrator_daemon (poll=60s, timeout=90) — вклад в нагрузку мал, не причина.\n"
"== ВЕКТОР ФИКСА (НЕ делал — read-only) ==\n"
"а) devbot: get_pending через await asyncio.to_thread(...) — снимает заморозку event loop (главный вред);\n"
"б) отдельный BridgeClient(timeout=10-15) для опроса очереди: опрос идемпотентен, при таймауте просто ждём следующий тик 45с "
"(не держать 60с);\n"
"в) склеить 4 вызова в 1: get_pending с несколькими статусами (Bridge: status=CSV или all) — 4x меньше шансов на таймаут; "
"требует правку BotData.js/Bridge.js + clasp redeploy (красное, отдельное «да»).\n"
"Приоритет: а)+б) — только python, зелёное, чинит 90% вреда без деплоя Bridge. Хвост: в) при следующем деплое Bridge.\n"
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

pulse = (ts + " | 🟢 | Разбор таймаутов get_pending готов: Google /exec хвосты + 4 синхронных вызова в event loop "
         "(бот замерзает до 60-240с); вектор фикса a) to_thread б) timeout 15с в) склейка статусов | ничего не жду | "
         "детали→cc_log запись «разбор таймаутов get_pending 02.07»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
