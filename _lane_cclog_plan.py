"""PLAN в cc_log (вторая полоса lane=pc дев-контура O4) + пульс — ОДНА операция.
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
"PLAN " + ts + " UTC: вторая полоса lane=pc дев-контура O4 (headless-задача из 328).\n"
"1) Bridge (локальное зеркало /root/turbobaby-bridge-gs, ДЕПЛОЙ = красное, спрошу): очередь получает "
"колонку lane (9-я, дефолт vps); enqueue пишет lane; get_pending фильтрует по lane (без параметра = vps — "
"старый VPS-демон БЕЗ правок не видит pc-задачи; lane=all — без фильтра, для devbot-опроса); claim — "
"опциональный guard wrong_lane.\n"
"2) bridge_client.py: enqueue_task/get_pending/get_pending_multi/claim_task получают опц. lane "
"(не передан → параметр не шлётся, старый Bridge не ломается).\n"
"3) devbot.py: тема PC-дев через env PC_DEV_TOPIC_ID (0/нет = выключено; id Филипп даст после создания "
"темы); в ней ТОЛЬКО «тз:»/«задача:» от Филиппа → enqueue lane=pc (метки Filipp-pc-dev / Filipp-pc) + "
"ответы «да N»/«нет N»; карточки in_progress/needs_approval/done/failed маршрутизируются по lane задачи "
"в тему PC-дев (кнопки те же); опрос очереди — lane=all. splinter.is_ignored_thread игнорит тему PC-дев "
"(лениво из env). bot.py не трогаю (роутер уже зовёт devbot на ignored-темах).\n"
"4) orchestrator_daemon.py НЕ трогаю — отсечение pc-задач целиком на Bridge-дефолте lane=vps.\n"
"5) Тесты маршрутизации lane (tests/test_lane_pc.py) + правка мок-сигнатур в 3 существующих тестах; "
"гейт; push. Бэкапы: git-коммит ДО + .bak devbot/bridge_client/splinter + _bridge_bak-lane-20260704/.\n"
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

pulse = (ts + " | 🟢 | строю вторую полосу lane=pc дев-контура O4: Bridge-очередь lane + тема PC-дев в devbot, "
         "VPS-демон не трогаю | ничего не жду | детали→cc_log запись «PLAN lane=pc " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
