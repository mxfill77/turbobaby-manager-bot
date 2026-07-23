"""cc_log PLAN (C-декомпозер) + KB_PULSE — ОДНОЙ операцией (правило CLAUDE.md).
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
"PLAN " + ts + " UTC (тз:328, headless): C-ДЕКОМПОЗЕР по KB_review PLAN 21:40 часть C. "
"«декомпозируй: <крупное ТЗ>» в 328 → очередь from=Filipp-328-dec → демон: claude -p планировщик "
"(read-only, СТРОГО нумерованный список 2–7 шагов) → шаги отдельными задачами «[шаг i/N родитель id]» "
"(from=Filipp-328-dec) → исполнение по одному (FIFO, guard последовательности: пока сиблинг в "
"needs_approval/approved/in_progress — шаги этого родителя не берём, ДРУГИЕ задачи не блокируем; "
"failed шаг → остальные new-сиблинги пропущены) → сводный отчёт по родителю synthetic-задачей в 328. "
"Bridge-очередь НЕ меняется (родитель — по паттерну в task_text). Красный шаг → NEEDS_APPROVAL кнопкой "
"как раньше. Точки врезки: orchestrator_daemon.py (планировщик+fan-out+guard+агрегация), devbot.py "
"(префикс «декомпозируй:»+QUEUE_FROMS+help), tests. Дальше: бэкапы → код → py_compile+тесты+гейт → "
"commit/push → restart splinter+daemon оранжевым циклом.\n"
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

pulse = (ts + " | 🟡 | строю C-декомпозер (KB_review PLAN 21:40 часть C): префикс «декомпозируй:», "
         "планировщик→шаги [шаг i/N родитель id]→по одному→сводка | ничего не жду | "
         "детали→cc_log PLAN " + ts + " C-декомпозер")
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
