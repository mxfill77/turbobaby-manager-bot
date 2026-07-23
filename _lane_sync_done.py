"""Синк docs/project_state.md → Brain (KB_project_state) + DONE в cc_log + пульс.
cc_log: вставка ПОД шапкой (после последней ═-only строки); пульс — той же операцией."""
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()

with open("/root/turbobaby-manager-bot/docs/project_state.md", encoding="utf-8") as f:
    ps = f.read()
w = c.write_doc(text=ps, name="project_state")
rb = c._call("read_doc", name="project_state")
drive_len = len(rb.get("text") or "")
print("SYNC project_state:", w.get("ok"), "| git codepoints:", len(ps), "| drive codepoints:", drive_len,
      "| delta:", drive_len - len(ps))

r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ cc_log FAIL — НЕ пишу:", r)
    raise SystemExit(1)
old = r.get("text", "")
ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

note = (
"DONE " + ts + " UTC: вторая полоса lane=pc дев-контура O4 СОБРАНА (headless-задача из 328). "
"Commit 0bb38df, push af6d2d7..0bb38df, гейт 35/35 (был 27 + 8 новых), restart splinter — старт чистый "
"(active, Bridge alive, 0 ошибок после старта).\n"
"а) Bridge (ЗЕРКАЛО /root/turbobaby-bridge-gs/BotData.js, ПРОД НЕ ДЕПЛОЕН — красное, ждёт «да»): "
"QUEUE_HEADERS + колонка lane (9-я); queueLane_ (пусто=vps); enqueue пишет lane (дефолт vps); "
"get_pending: без lane = ТОЛЬКО vps (старый VPS-демон без правок не видит pc-задачи), lane=all = обе "
"полосы, иначе точный матч; claim: опц. guard wrong_lane. node --check чисто. Бэкап "
"BotData.js.bak-lane-20260704.\n"
"б) bridge_client.py: enqueue_task/get_pending/get_pending_multi/claim_task — опц. lane (None → параметр "
"НЕ шлётся, старый Bridge совместим; проверено — лишний параметр /exec игнорит).\n"
"в) devbot.py: тема PC-дев = env PC_DEV_TOPIC_ID (лениво, 0/нет = полоса выключена; bot.py импортирует "
"devbot ДО load_dotenv — потому не константа). В теме: ТОЛЬКО «тз:»/«задача:» от Филиппа (504608015) → "
"enqueue lane=pc, метки Filipp-pc-dev/Filipp-pc; «да N»/«нет N» работают; «декомпозируй:» на pc "
"НЕ поддержан (подсказка); зелёный allowlist остался только в 328. Карточки in_progress/needs_approval/"
"done/failed маршрутизируются по lane/метке (_is_pc_item/_item_topic; до redeploy Bridge — по метке from), "
"кнопки те же (handle_callback тем-агностичен). Опрос очереди lane=all. splinter.is_ignored_thread "
"игнорит тему PC-дев (лениво из env). bot.py не трогал (роутер уже зовёт devbot).\n"
"г) orchestrator_daemon.py НЕ ТРОНУТ — отсечение pc целиком на Bridge-дефолте (get_pending без lane = vps).\n"
"д) Тесты: tests/test_lane_pc.py — 8 шт (клиент lane-параметры ×4, _try_enqueue полосы, handle_command "
"PC-темы вкл. чужой юзер/без env, report_results маршрут+кнопки+фоллбэк по from, is_ignored_thread); "
"мок-сигнатуры добиты в test_devbot_nonblocking/test_devbot_buttons/test_inprogress_report; "
"test_orchestrator_stage2 QUEUE_FROMS-проверка расширена метками pc. Гейт 35/35.\n"
"е) docs/project_state.md — блок «вторая полоса lane=pc собрана, ждёт включения»; Brain synced.\n"
"Бэкапы: devbot/bridge_client/splinter .bak-lane-20260704 + git; откат = git revert 0bb38df + restart.\n"
"Статус: ТЕХНИЧЕСКИ ГОТОВО (тесты на моках, старт чистый); функционально НЕ подтверждено — полоса "
"выключена до включения по шагам.\n"
"ХВОСТЫ (включение полосы pc, по порядку): 1) clasp push + clasp redeploy прод-deploymentId "
"(КРАСНОЕ — NEEDS_APPROVAL выведен, ждёт «да»; проверка после: ping + enqueue lane=pc тестовой + "
"get_pending new БЕЗ lane её НЕ видит, с lane=pc — видит); 2) Филипп создаёт тему «PC-дев» в HQ и даёт "
"id → строка PC_DEV_TOPIC_ID=<id> в .env; 3) systemctl restart splinter; 4) ПК-агент-исполнитель полосы "
"pc (опрос get_pending lane=pc + claim lane=pc) — отдельная задача, на VPS его нет.\n"
)

lines = old.split("\n")
ins = 0
for i, ln in enumerate(lines[:80]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        ins = i + 1
new = "\n".join(lines[:ins]) + ("\n" if ins else "") + note + "\n" + "\n".join(lines[ins:])
wl = c.write_doc(text=new, name="cc_log")
print("WRITE cc_log:", wl.get("ok"), "| old_len:", len(old), "new_len:", len(new), "| insert_at_line:", ins)

pulse = (ts + " | 🟡 | вторая полоса lane=pc собрана: Bridge-зеркало+клиент+devbot(тема PC-дев)+8 тестов, "
         "гейт 35/35, push 0bb38df, restart чистый; полоса выключена | жду «да» на clasp redeploy Bridge, "
         "затем id темы PC-дев в .env | детали→cc_log запись «DONE lane=pc " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
