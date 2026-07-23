"""DONE в cc_log + пульс по живому селфтесту полосы pc (04.07.2026).
cc_log: вставка ПОД шапкой (после последней ═-only строки); пульс — той же операцией."""
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
"DONE " + ts + " UTC: живой селфтест полосы pc на прод-Bridge (headless-задача из 328) — 7/8 PASS, "
"найден 1 баг GET-роутера.\n"
"ПРОШЛО: ping alive; enqueue_task lane=pc → id 14, lane=pc записан; get_pending new БЕЗ lane "
"pc-задачу НЕ видит (изоляция VPS-демона работает); claim_task lane=vps → wrong_lane (guard чужой "
"полосы работает); claim lane=pc → ok; complete done; после — new (lane=all) пуст, очередь чистая, "
"тестовая задача закрыта (метка from=selftest-lane-pc не в QUEUE_FROMS → devbot карточек не слал).\n"
"БАГ: get_pending С lane=pc задачу НЕ вернул (ответ lane=vps) — GET-роутер Bridge.js (case "
"'get_pending', ~строка 73) прокидывает в getPending_ ТОЛЬКО status, params.lane ТЕРЯЕТСЯ; в doPost "
"case get_pending НЕТ (обхода POST'ом нет). Следствия: (а) будущий ПК-агент НЕ сможет опрашивать свою "
"полосу; (б) devbot._poll_queue_sync(lane=all) реально видит только vps → карточки done/failed/"
"needs_approval pc-задач в тему PC-дев (829) НЕ придут. Мок-тесты test_lane_pc.py это не ловили "
"(мокают клиент, не прод-роутер).\n"
"ФИКС ПОДГОТОВЛЕН (зеркало, ПРОД НЕ ДЕПЛОЕН): /root/turbobaby-bridge-gs/Bridge.js — "
"getPending_({status: params.status, lane: params.lane}) (одна строка); node --check чисто; бэкап "
"Bridge.js.bak-lanefix-20260704. Деплой = clasp push + clasp redeploy прод-deploymentId — КРАСНОЕ, "
"NEEDS_APPROVAL выведен в 328, ждёт «да».\n"
"Статус: изоляция полосы/enqueue/claim-guard/complete функционально ПОДТВЕРЖДЕНЫ живьём; опрос полосы "
"pc (get_pending lane=pc) НЕ работает до redeploy Bridge.\n"
"ХВОСТЫ: 1) «да» → clasp push + redeploy → повторить селфтест: venv/bin/python3 _lane_pc_selftest.py "
"(ожидание ALL PASS 8/8); 2) дальше по плану включения полосы (ПК-агент-исполнитель).\n"
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

pulse = (ts + " | 🟡 | живой селфтест lane=pc: изоляция vps/enqueue/claim-guard/complete ✅, но GET "
         "get_pending теряет lane (баг Bridge.js GET-роутера) — ПК-агент и devbot-опрос полосы pc слепые; "
         "фикс 1 строка подготовлен в зеркале, node --check чисто | жду «да» на clasp push+redeploy Bridge "
         "| детали→cc_log запись «селфтест lane=pc " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
