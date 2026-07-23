"""cc_log DONE (доводка задачи 43: op=other в approve-исполнителе + правило самомодификации)
+ KB_PULSE — ОДНОЙ операцией. Запись ПОД врезкой (матч ═-only строки), write только если read ok. Зона 🟢."""
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
"DONE " + ts + " UTC (доводка задачи 43 после её самоубийства рестартом, headless): сверка + правило самомодификации.\n"
"— СВЕРКА: задача 43 УСПЕЛА ВСЁ, погиб только отчёт. Коммит 60c1e43 (03:15:02) = полный фикс op=other→конверт "
"в headless-задачу (from=Filipp-328-dev, исключения: шаг декомпозиции→failed, сбой enqueue→честный фоллбэк) "
"+ тест tests/test_orchestrator_other.py (15 проверок). Запушен (ahead=0), рабочая копия чистая. "
"Демон рестартован 03:15:28 (на 26с ПОЗЖЕ коммита) → живой демон УЖЕ крутит код с op=other. "
"Хронология смерти: рестарт демона по ходу задачи убил её же claude-подпроцесс (exit=143 SIGTERM) до отчёта.\n"
"— ДОПИСЫВАТЬ НЕЧЕГО: фикс целиком, тесты есть, гейт зелёный (30 тестов, 9.2с — вкл. 15 новых op=other).\n"
"— КЛАСС-ПРАВИЛО САМОМОДИФИКАЦИИ (commit 1a72ca6, запушен): правка orchestrator_daemon.py из headless-задачи → "
"отчёт cc_log+пульс+сводка ДО рестарта демона; рестарт — САМОЕ ПОСЛЕДНЕЕ действие и ТОЛЬКО отложенно "
"(systemd-run --on-active=10s systemctl restart orchestrator-daemon); прямой restart из тела задачи ЗАПРЕЩЁН. "
"Вписано в CLAUDE.md (раздел ДЕВ-КОНТУР O4) + APPROVAL_PREAMBLE v3.1 в orchestrator_daemon.py. "
"Урок: C-декомпозер выжил (SIGTERM после отчёта), 43 погибла (рестарт до). Бэкапы: *.bak-selfmod-20260703.\n"
"— ФИНАЛ этой задачи тем же способом: после этой записи — deferred restart orchestrator-daemon "
"(демон подхватит преамбулу v3.1).\n"
"СТАТУС: код 43 в проде — функционально НЕ обкатан (нужна живая заявка op=other→approve→конверт→исполнение); "
"правило самомодификации — технически готово (коммит+преамбула), функционально подтвердит следующая правка демона.\n"
"ХВОСТЫ: (а) функциональная обкатка op=other-конверта живой заявкой; (б) прежние хвосты родителя 33 без изменений.\n"
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

pulse = (ts + " | 🟢 | доводка задачи 43: фикс op=other был ПОЛНЫМ (60c1e43 запушен, 15 тестов, демон уже на нём) — "
         "дописал только правило самомодификации (1a72ca6: отчёт ДО рестарта демона, рестарт отложенно systemd-run "
         "--on-active=10s, вписано в CLAUDE.md+преамбулу v3.1); deferred restart демона запланирован | ничего не жду | "
         "детали→cc_log DONE " + ts + " доводка 43")
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
