"""DONE в cc_log (добивка протухающих q.answer вне O3) + пульс ТОЙ ЖЕ операцией. Зелёная зона.
Врезку (старт-блок ⛔) сохраняем: новая запись кладётся ПОД закрывающей ═-only-строкой врезки.
Защита от затирки: пишем ТОЛЬКО если read вернул ok."""
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
"DONE " + ts + " UTC (тз:328, headless): добиты протухающие q.answer ВНЕ O3 — паттерн _o3_answer из 749cf46.\n"
"Общий хелпер _btn_answer (try/except, ack «Query is too old» не валит хендлер, действие кнопки выполняется всегда).\n"
"Заменены ВСЕ сырые q.answer вне O3: handle_info_button (3), handle_service_button (12, вкл. show_alert trust-гейта),\n"
"handle_delivery_button (10). Логика/гейты/trust не тронуты. Уточнение: номера из ТЗ (712 и 3748) съехали —\n"
"3748 уже внутри O3-хендлера (пофикшен 749cf46); реально «вне O3» было ТРИ хендлера, добиты все три.\n"
"Тесты: +3 (протухший ack: инфо-карточка строится / delivery:hand выдаёт / svc:done пишет) — гейт 27 зелёных.\n"
"Коммит c866185, push прошёл (pre-push гейт ✅). Бэкап: splinter.py.bak-ackfix-20260702 + git.\n"
"СТАТУС: технически готово (тесты+гейт); функционально НЕ подтверждено — НУЖЕН restart splinter (сам не делаю,\n"
"режим обкатки ступени 2 — кнопка в 328).\n"
"ХВОСТЫ: сырые q.answer остались в bot.py:182 (on_audit_button, аудит-карточки владельца) и devbot.py (~13 шт,\n"
"апрув-кнопки 328) — низкий риск (нет долгих синков рядом), добить тем же паттерном при случае.\n"
)

lines = old.split("\n")
ins = 0
# врезка: если док начинается со старт-блока — вставка ПОСЛЕ его закрывающей ═-only-строки
eq_lines = [i for i, ln in enumerate(lines[:60]) if ln.strip() and set(ln.strip()) == {"═"}]
if eq_lines:
    ins = eq_lines[-1] + 1 if len(eq_lines) >= 2 else eq_lines[0] + 1
new = "\n".join(lines[:ins] + ([""] if ins else []) + [note] + lines[ins:])

w = c.write_doc(text=new, name="cc_log")
print("CC_LOG WRITE:", w.get("ok"), "| ins_line:", ins, "| old_len:", len(old), "new_len:", len(new))
if not w.get("ok"):
    raise SystemExit(1)

pulse = (ts + " | 🟢 | добивка протухающих q.answer вне O3 (info/svc/delivery → _btn_answer): коммит c866185, "
         "push+гейт 27 ✅ | жду: restart splinter кнопкой в 328 (функц. тест после) | детали→cc_log запись «DONE "
         + ts + " добивка q.answer»")
p = c.write_doc(text=pulse, name="pulse")
print("PULSE WRITE:", p.get("ok"))
