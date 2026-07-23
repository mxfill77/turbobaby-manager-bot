"""DONE в cc_log (фикс заморозки event loop, ТЗ из 328) + пульс — ОДНА операция. Зелёная зона.
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
"DONE " + ts + " UTC: ФИКС заморозки event loop от синхронных Bridge-вызовов (ТЗ из 328, по разбору "
"«таймауты get_pending 02.07»). Commit 3978a91, push ok, гейт 28 зелёных.\n"
"а) ВСЕ Bridge-вызовы devbot — через asyncio.to_thread: опрос очереди report_results, кнопки "
"approve/reject/check/next (_find_task), «да N»/enqueue, зелёные команды 328, morning_summary. "
"Event loop больше не встаёт на 60-240с — бот отвечает, пока /exec тупит.\n"
"б) Отдельный poll-клиент очереди: BridgeClient(timeout=15) вместо 60с (devbot.POLL_TIMEOUT, "
"ленивый, кэш по BRIDGE). Опрос идемпотентен — таймаут = пропустить тик 45с.\n"
"в) Склейка статусов: bridge_client.get_pending_multi(statuses) — 1 CSV-вызов вместо 4; "
"feature-detect по полю statuses в ответе + авто-фоллбэк по-статусно на старом Bridge (кэшируется, "
"CSV-проба не гоняется каждый тик; при timeout склейки фоллбэком Bridge НЕ добиваем). Серверная "
"часть ГОТОВА в зеркале /root/turbobaby-bridge-gs/BotData.js (getPending_ понимает CSV, "
"бэкап BotData.js.bak-bridgefreeze-20260702, node --check ok) — НЕ задеплоена.\n"
"Тесты: tests/test_devbot_nonblocking.py — 7 шт (N1 loop тикает во время опроса; N2 бот отвечает "
"за ~0.05с при висящем Bridge; N3 poll timeout=15; N4 один CSV-вызов; N5 фоллбэк+кэш; N6 таймаут "
"без добивания; N7 регресс done-рапорта). Старые test_inprogress_report 5/5 зелёные.\n"
"Бэкапы: devbot.py/.bridge_client.py .bak-bridgefreeze-20260702. Откат = git revert 3978a91.\n"
"Статус: ТЕХНИЧЕСКИ готово (гейт+моки); функционально НЕ подтверждено — нужен restart splinter "
"(кнопкой в 328), затем посмотреть в splinter.log что «Bridge timeout (>15s)» не тянет за собой "
"молчание кнопок.\n"
"ХВОСТЫ: 1) restart splinter (ждёт кнопки); 2) clasp push + redeploy Bridge для серверной склейки "
"(КРАСНОЕ, отдельное «да»; до деплоя работает фоллбэк — каждый тик 1 лишняя CSV-проба до первого "
"фоллбэк-детекта, дальше по-статусно); 3) при следующем заходе — вынести за to_thread остальные "
"синхронные Bridge-вызовы вне devbot (splinter/bot.py джобы), если замечу заморозки.\n"
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

pulse = (ts + " | 🟢 | Фикс заморозки event loop готов (to_thread + poll 15с + склейка, commit 3978a91, "
         "гейт 28✅, push ok) | жду: restart splinter кнопкой в 328; хвост: clasp redeploy склейки (красное) | "
         "детали→cc_log запись «фикс заморозки event loop 02.07»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
