"""cc_log DONE (шаг 1/5 родитель 26: аудит сырых q.answer в splinter.py) + KB_PULSE — одной операцией.
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
"DONE " + ts + " UTC (тз:328, headless, шаг 1/5 родитель 26): АУДИТ сырых ack-колбэков в splinter.py — "
"РЕЗУЛЬТАТ: 0 сырых вызовов.\n"
"— grep -n \"q.answer\\|query.answer\\|\\.answer(\" splinter.py → 8 строк, ВСЕ внутри тел двух хелперов: "
"_btn_answer (строки 693–700, докстринг + try await q.answer + warning) и _o3_answer (3704–3711, аналогично). "
"Прямых await q.answer(...) вне этих хелперов НЕТ — фиксы 749cf46/c866185 покрыли splinter.py полностью.\n"
"— Гейт: venv/bin/python3 gate.py → 29 тестов зелёные (9.5с). Правок кода не было (read-only шаг), "
"деплой/restart не требуются.\n"
"СТАТУС: функционально подтверждено (grep-аудит исчерпывающий по паттерну .answer().\n"
"ХВОСТЫ: шаги 2–5 родителя 26 (сырые q.answer в bot.py/devbot.py — как в хвостах DONE C-декомпозера).\n"
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

pulse = (ts + " | 🟢 | шаг 1/5 (родитель 26) done: аудит splinter.py — 0 сырых q.answer, всё через "
         "_btn_answer/_o3_answer; гейт 29 ✅, правок нет | ничего не жду; дальше шаги 2–5 (bot.py/devbot.py) | "
         "детали→cc_log DONE " + ts + " аудит ack splinter.py")
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
