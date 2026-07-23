"""cc_log DONE (C-декомпозер собран) + KB_PULSE — ОДНОЙ операцией (правило CLAUDE.md).
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
"DONE " + ts + " UTC (тз:328, headless): C-ДЕКОМПОЗЕР СОБРАН (ступень 2 часть C по KB_review PLAN 21:40) — "
"commit 2733f17 (+докс 346a154), push ✅ (pre-push гейт).\n"
"— devbot.py: префиксы «декомпозируй:»/«разбей:»/«decompose:» → from=Filipp-328-dec; QUEUE_FROMS +dec "
"(отчёты шагов/сводки доходят в 328); help.\n"
"— orchestrator_daemon.py: PLANNER_PREAMBLE (read-only планировщик, СТРОГО нумерованный список 2–7 шагов, "
"потолок MAX_STEPS=8); родитель → план → fan-out шагов «[шаг i/N родитель id]»; исполнение по одному "
"(FIFO + guard: пока сиблинг в needs_approval/approved/in_progress — шаги родителя не берём, ЧУЖИЕ задачи "
"не блокируем); halt-on-fail (упал/отклонён шаг → остальные new-сиблинги «пропущен»); сводка по родителю "
"synthetic-задачей (идемпотентно: память+скан существующих; хвост после «нет N» мимо демона добирает "
"process_dec_tails раз в цикл); осиротевшая сводка доводится без повторного планирования; таймаут dec=45 мин. "
"Bridge-очередь НЕ менялась (родство по паттерну task_text, как в плане C). Безопасность D не ослаблена: "
"AUTO_OPS/EXECUTORS не тронуты, красный шаг → кнопка как раньше.\n"
"— tests/test_orchestrator_dec.py (10 блоков, 30 моков: dec-префикс, парсер, fan-out, по-одному+сводка, "
"guard+approve, halt-on-fail, reject мимо демона, orphan-сводка, деградации планировщика, «тз:» не задет); "
"test_orchestrator_stage2 подправлен (QUEUE_FROMS). Гейт 29 зелёных.\n"
"ПРИМЕНЕНИЕ (оранжевый цикл): гейт ✅ → systemctl restart splinter → is-active=active, старт чистый "
"(Bridge alive, 7 job, 0 ERROR после старта) — нужен был restart, сделал; orchestrator-daemon — мягкий "
"SIGTERM (в логе «получен сигнал 15»), доработает эту задачу и systemd поднимет с декомпозером. "
"docs/project_state.md: ступень 2 собрана целиком → Brain synced (delta 0). Бэкапы: *.bak-dec-20260703 + git.\n"
"СТАТУС: технически готово; функциональная обкатка — первый живой «декомпозируй:» из 328.\n"
"ХВОСТЫ: 1) обкатать «декомпозируй:» на безрисковом ТЗ (проверить план→шаги→сводку вживую); 2) подтвердить, "
"что демон перезапустился с новым кодом (строка «ДЕМОН СТАРТ» в orchestrator_daemon.log после этой задачи); "
"3) подрезка cc_log (записи старше суток → архив) — не делал из headless-задачи, снять в интерактивной сессии; "
"4) прежние хвосты: clasp redeploy склейки статусов (красное, ждёт «да»); сырые q.answer в bot.py/devbot.py.\n"
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

pulse = (ts + " | 🟢 | C-декомпозер собран (ступень 2 O4 целиком): «декомпозируй:» → план (2–7 шагов) → шаги "
         "[шаг i/N родитель id] по одному → сводка; commit 2733f17+346a154 push ✅, гейт 29 ✅, splinter "
         "перезапущен (старт чистый), демону мягкий SIGTERM для подхвата | ничего не жду; обкатать первый живой "
         "«декомпозируй:» | детали→cc_log DONE " + ts + " C-декомпозер")
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
