"""cc_log DONE (шаг 2/5 родитель 26: q.answer→_btn_answer в splinter.py) + KB_PULSE — ОДНОЙ операцией.
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
"DONE " + ts + " UTC ([шаг 2/5 родитель 26], headless): сырые q.answer вне O3 в splinter.py → _btn_answer — "
"УЖЕ СДЕЛАНО ранее коммитом c866185 (добивка 749cf46), предок HEAD; правок в этой задаче НЕ потребовалось.\n"
"— Проверка по ТЗ прогнана заново: grep answer( по splinter.py — сырых `await q.answer(` ровно 2, обе ВНУТРИ "
"хелперов (_btn_answer:698, _o3_answer:3709) = 0 сырых вне хелперов; все 25 кнопочных мест вне O3 идут через "
"_btn_answer (аргументы тоста/show_alert сохранены), 13 мест O3 — через _o3_answer.\n"
"— py_compile splinter.py ✅; git status splinter.py чист (ничего не менял, деплой/restart не нужен).\n"
"СТАТУС: функционально это тот же код, что уже крутится в проде с c866185.\n"
"ХВОСТЫ: без изменений — сырые q.answer в bot.py:182 и devbot.py (вне scope этого шага, splinter.py-only); "
"дальше шаг 3/5 родителя 26.\n"
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

pulse = (ts + " | 🟢 | шаг 2/5 (родитель 26) закрыт: q.answer вне O3 в splinter.py уже на _btn_answer (c866185), "
         "перепроверено — 0 сырых вне хелперов, py_compile ✅, правок не потребовалось | ничего не жду; "
         "дальше шаг 3/5 | детали→cc_log DONE " + ts + " шаг 2/5")
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
