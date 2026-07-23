"""cc_log DONE (шаг 4/7 родитель 33: синк CLAUDE.md) + KB_PULSE — ОДНОЙ операцией (правило CLAUDE.md).
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
"DONE " + ts + " UTC ([шаг 4/7 родитель 33], headless): CLAUDE.md синхронизирован с реальностью O4 — "
"commit e45908b (локально, push = шаг 7).\n"
"— Проверка показала: Q2 (restart оранжевым циклом) и доктрина подтверждений УЖЕ были отражены "
"(7d840e2/ea92795); НЕ хватало дев-контура целиком.\n"
"— Добавлен раздел «ДЕВ-КОНТУР O4 — TurboControl, тема 328»: chat -1003853365891 тема 328, только Филипп; "
"поток префикс→Bridge-очередь→orchestrator_daemon (claude -p)→report_results 45с; префиксы задача: (10 мин, "
"Filipp-328) / тз: (произвольное дев-ТЗ 45 мин, Filipp-328-dev) / декомпозируй: (ступень 2C 2733f17: план "
"2–7 шагов → по одному, guard/halt-on-fail, Filipp-328-dec); NEEDS_APPROVAL+кнопки (approve 30 мин), Q2 "
"restart сам, рубильник systemctl stop orchestrator-daemon, утренняя сводка 08:00.\n"
"— Архитектура: добавлены devbot.py и orchestrator_daemon.py; в разделе гейта 4.3 «Будущий дев-бот» → "
"существующий дев-контур.\n"
"Бэкап: CLAUDE.md.bak-o4sync-20260703 + git. База docs/*.md не менялась → синк Brain не нужен.\n"
"СТАТУС: технически готово (docs-правка, тесты/py_compile не требуются; commit локальный).\n"
"ХВОСТЫ: push этой правки — шаг 7/7 родителя 33.\n"
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

pulse = (ts + " | 🟢 | [шаг 4/7 родитель 33] CLAUDE.md синхронизирован с O4: новый раздел ДЕВ-КОНТУР "
         "(328: задача:/тз:/декомпозируй:, очередь, Q2), devbot+daemon в архитектуре; commit e45908b локально "
         "| ничего не жду; push = шаг 7 | детали→cc_log DONE " + ts + " шаг 4/7")
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
