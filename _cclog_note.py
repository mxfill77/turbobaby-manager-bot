"""Записать NOTE в cc_log (Этап 1 трекинга собран, на ревью). Зелёная зона.
Защита от затирки: пишем ТОЛЬКО если read вернул ok. Препенд сверху (как последние записи)."""
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
"NOTE " + ts + " UTC: Этап 1 трекинга СОБРАН (код+мок-тест, БЕЗ деплоя) — на ревью перед clasp redeploy.\n"
"== ЧТО СОБРАНО (3 файла) ==\n"
"1) BotData.js: TABS+='состояние_байка'; STATE_HEADERS=[bike,status,location,booking_id,client,date_out,date_due,date_back,service_name,last_event_msg_id,updated]; getBotTab_ авто-сеет; STATE_STATUSES=[в аренде/к возврату/дома/офис/ремонт]; функции stateUpsert_/stateGet_/stateList_. upsert по bike (точное имя=КЛЮЧ), merge: переданное перезаписывает, НЕ переданное сохраняется из строки; updated=now; bad_status/no_bike отклоняются.\n"
"2) Bridge.js doPost: case state_set->stateUpsert_ / state_get->stateGet_ / state_list->stateList_ (Object.assign({action},...)); + в список actions.\n"
"3) bridge_client.py: обёртки state_set(**fields)/state_get(bike)/state_list() через _post.\n"
"== ПРОВЕРКИ ==\n"
"node --check BotData.js+Bridge.js OK; py_compile bridge_client.py OK; мок-тест 18/18 PASS (insert->get->merge-update без потери client/booking_id->list без дублей->bad_status отклонён->no_bike->not_found->пустой статус ок); гейт 4.3 = 18 зелёных.\n"
"== БЭКАП ==\n"
"git commit baf3dbe (bridge_client.py, БЕЗ push). .gs локально в /root/turbobaby-bridge-gs (не git-репо; бэкап = clasp version history). НЕ деплоено.\n"
"== СТОП ==\n"
"🔴 clasp redeploy = КРАСНОЕ. ЖДУ «да» Филиппа на деплой Bridge. Предусловие из плана: clasp-токен info@turbophuket.com (был invalid_rapt) — проверить перед redeploy.\n"
"ХВОСТЫ: после deploy — проверка ping + state_list (пустой, ok); затем отдельно state_seed из Лист1 Байки (38 байков, стартовое состояние).\n"
)

new = note + "\n" + old
w = c.write_doc(text=new, name="cc_log")
print("WRITE:", w.get("ok"), "| old_len:", len(old), "new_len:", len(new))
