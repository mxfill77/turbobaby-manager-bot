"""cc_log DONE (шаг 6/7 родитель 33: гигиена cc_log) + KB_PULSE — ОДНОЙ операцией (правило CLAUDE.md).
Запись ПОД врезкой (матч ═-only строки), write только если read ok. Зона 🟢."""
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

entry = (
"DONE " + ts + " UTC ([шаг 6/7 родитель 33], headless): гигиена cc_log — переносить НЕЧЕГО, подрезка не потребовалась.\n"
"— Бэкап-снимок снят: /tmp/cc_log_backup_trim_2026-07-03.txt (14682 байта).\n"
"— Проверка по протоколу (_s4_cclog_trim.py, только name=): все журнальные строки в cc_log датированы "
"ТЕКУЩИМИ сутками 2026-07-03 (сверено grep по бэкапу — записей 07-02 и старше нет); врезка ⛔ на месте.\n"
"— cc_log уже = «врезка + сегодняшнее», 14.7 КБ < 40 КБ; архив cc_log_archive НЕ трогал (write в архив "
"без переноса не нужен и опасен).\n"
"СТАТУС: функционально подтверждено (grep дат по снимку).\n"
"ХВОСТЫ: шаг 7/7 родителя 33 — гейт + push (там уйдёт и локальный commit e45908b).\n"
)

lines = old.splitlines(keepends=True)
ins = 0
for i, ln in enumerate(lines[:10]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        ins = i + 1
        break
new = "".join(lines[:ins]) + entry + "\n" + "".join(lines[ins:])
w = c.write_doc(text=new, name="cc_log")
print("cc_log WRITE:", w.get("ok"), "| вставка после строки", ins, "| old:", len(old), "new:", len(new))

pulse = (ts + " | 🟢 | [шаг 6/7 родитель 33] гигиена cc_log: бэкап в /tmp снят, все записи сегодняшние — "
         "переносить нечего, cc_log 14.7КБ уже чистый (врезка+сегодня), архив не трогал "
         "| ничего не жду; остался шаг 7/7 (гейт+push) | детали→cc_log DONE " + ts + " шаг 6/7")
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
