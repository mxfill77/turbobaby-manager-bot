"""cc_log DONE (проверка целостности memory.db) + KB_PULSE — ОДНОЙ операцией (правило CLAUDE.md).
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
"DONE " + ts + " UTC (задача:328, headless): проверка целостности memory.db — ЦЕЛА, проблем нет.\n"
"— PRAGMA integrity_check = ok; foreign_key_check = 0 нарушений; файл 442 КБ (108 страниц по 4К, freelist 0 — "
"без раздутия).\n"
"— 9 таблиц, строки: conversations 327, info_pin 41, topic_bike 41, o3_card 29, rules 21, entity_notes 4, "
"o3_task 2, corrections 0.\n"
"Read-only (подключение mode=ro, только PRAGMA/COUNT), в базу не писал. Хелпер _integrity_memdb.py.\n"
"ХВОСТЫ: без изменений (clasp redeploy склейки статусов — красное, ждёт «да»; сырые q.answer в bot.py:182 и "
"devbot.py; подхват преамбулы v3 демоном проверить на следующем «тз:»).\n"
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

pulse = (ts + " | 🟢 | memory.db проверена: integrity_check ok, FK 0 нарушений, 9 таблиц/442КБ, read-only | "
         "ничего не жду | детали→cc_log DONE " + ts + " memory.db")
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
