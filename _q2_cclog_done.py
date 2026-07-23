"""cc_log DONE (Q2 разблокирован) + KB_PULSE — ОДНОЙ операцией (правило CLAUDE.md).
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
"DONE " + ts + " UTC (тз:328, headless): Q2 РАЗБЛОКИРОВАН — restart splinter headless-CC теперь делает САМ "
"оранжевым циклом (критерий обкатки ступени 2 выполнен: 3 «тз:» подряд done без Termux, вкл. прод-фикс 3978a91).\n"
"— orchestrator_daemon.py: преамбула v2→v3 (restart сам: гейт gate.py только exit 0 → restart → проверка чистого "
"старта is-active+splinter.log → отчёт «нужен был restart — сделал, старт чистый»; при failed — откат на прошлый "
"рабочий коммит). КРАСНОЕ (Лист1/CRM/деньги/clasp/sqlite3/delete) БЕЗ изменений — op=other, кнопка остаётся; "
"op=restart_splinter — аварийный фоллбэк (AUTO_OPS/EXECUTORS не тронуты).\n"
"— devbot.py: тексты «тз:»-ответа и help под новый режим; tests/test_orchestrator_stage2.py: ассерты под v3; "
"CLAUDE.md: allow-раздел авто-approve дополнен Q2 (03.07).\n"
"Гейт 28 зелёных; коммит 7d840e2, push прошёл (pre-push гейт ✅). Бэкапы: *.bak-q2unlock-20260703 + git.\n"
"ПРИМЕНЕНИЕ: splinter перезапущен ПО НОВОМУ ЦИКЛУ (гейт ✅ → restart → is-active=active, старт чистый: Bridge alive, "
"Auditor ✅, polling, 7 job) — заодно вживую применён фикс 3978a91 (bridge-freeze, ждал рестарта). "
"orchestrator-daemon: прямой systemctl restart изнутри задачи убил бы её же claude -p (cgroup) → послан мягкий "
"SIGTERM (штатный _stop, в логе «получен сигнал 15»); демон доработает эту задачу, systemd (Restart=always) "
"поднимет его с v3.\n"
"СТАТУС: технически готово; restart-цикл прогнан вживую этой же задачей (функционально ✅ для splinter); "
"подхват v3 демоном подтвердить на СЛЕДУЮЩЕМ «тз:».\n"
"ХВОСТЫ: 1) проверить на следующем «тз:», что демон стартовал с преамбулой v3; 2) прежние хвосты без изменений "
"(clasp redeploy склейки статусов — красное, ждёт «да»; сырые q.answer в bot.py:182 и devbot.py).\n"
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

pulse = (ts + " | 🟢 | Q2 разблокирован: преамбула v3 (restart splinter — CC сам, оранжевый цикл гейт→restart→"
         "чистый старт), commit 7d840e2 push ✅, splinter перезапущен по новому циклу (старт чистый), демону послан "
         "мягкий SIGTERM для подхвата v3 | ничего не жду; подхват v3 проверить на следующем «тз:» | "
         "детали→cc_log DONE " + ts + " Q2")
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
