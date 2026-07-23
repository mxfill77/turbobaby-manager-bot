"""DONE в cc_log (ПОД врезкой) + KB_PULSE той же операцией. Зелёная зона."""
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
with open("/tmp/cc_log_backup_nopush_20260705.txt", "w", encoding="utf-8") as f:
    f.write(old)

lines = old.split("\n")
sep = None
for i, ln in enumerate(lines):
    s = ln.strip()
    if s and set(s) == {"═"}:
        sep = i
        break
if sep is None:
    print("ВРЕЗКА НЕ НАЙДЕНА — НЕ пишу")
    raise SystemExit(1)

ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

entry = (
"DONE " + ts + ": [фикс утечки тестовых красных карточек в личку, тз 328] commit 20762b6, push 477ae4c..20762b6 "
"(гейт 38 зелёных, вкл. новый регресс). Класс с 01.07, свежие 16:59/17:04 (=09:59/10:04 UTC). Причины: "
"(а) pretool_guard пушил 🧪-тестовые карточки в личку (пометка меняла только текст), (б) gate.py не пробрасывал "
"PRETOOL_NOPUSH подпроцессам тестов. Сделано: gate.py — env тестов += PRETOOL_NOPUSH=1 (наследуют все дети) + "
"GATE_TESTS_DIR только для регресса, пуш гейта «ТЕСТЫ КРАСНЫЕ» не тронут; pretool_guard — 🧪-карточка "
"(scratchpad/_test/_dryrun) НЕ пушится вовсе (терминальная карточка+ask остаются, классификация не менялась); "
"notify.py — мут по PRETOOL_NOPUSH=1 + мок-счётчик NOTIFY_COUNT_FILE (дивёрсия вместо отправки, ДО токена/сети); "
"pre-push — переменную НЕ ставим намеренно (пуш гейта жив, тесты покрыты через gate); orchestrator_daemon.py — "
"в headless-преамбулу добавлено «ручные прогоны тестов/фикстур — с префиксом PRETOOL_NOPUSH=1»; "
"tests/test_no_push_leak.py — регресс 14 проверок: полный гейт (gate→фейк-тест→pretool_guard на красной фикстуре) "
"→ ноль исходящих пушей по мок-счётчику + проверка живости счётчика (боевой пуш ловится, ноль не ложный); "
"test_notify_clean снимает тест-env у себя (сеть замокана); CLAUDE.md обновлён (🧪 без пуша, свод 05.07). "
"Бэкапы: *.bak-nopush-20260705 (gate/pretool_guard/notify/orchestrator_daemon/CLAUDE.md), откат = git revert 20762b6. "
"СТАТУС: технически готово (регресс+гейт зелёные); функционально — ждёт живой обкатки (следующий прогон тестов/гейта "
"НЕ должен дать ни одной карточки в личку). Рестарт orchestrator-daemon — отложенно (systemd-run 10s) после этой записи. "
"ХВОСТЫ: правка pretool_guard применяется в живых сессиях сразу (хук зовётся процессом на каждый вызов), "
"а вот интерактивной сессии claude при желании — перезапуск не нужен, hook внешний."
)

new_lines = lines[: sep + 1] + ["", entry] + lines[sep + 1 :]
new = "\n".join(new_lines)
w = c.write_doc(text=new, name="cc_log")
print("cc_log WRITE:", w.get("ok"), "| old:", len(old), "new:", len(new))
if not w.get("ok"):
    raise SystemExit(1)

pulse = (ts + " | 🟢 | утечка тестовых красных карточек в личку закрыта: PRETOOL_NOPUSH=1 принудительно во всех путях "
"тестов/гейта (gate env, 🧪-карточки pretool_guard без пуша, notify мут+мок-счётчик, преамбула headless), регресс "
"test_no_push_leak «полный гейт → 0 пушей», commit 20762b6, push ок, гейт 38 зелёных; рестарт orchestrator-daemon "
"отложен systemd-run 10s | ничего не жду; проверка жизнью — следующий гейт без карточек в личке | "
"детали→cc_log запись DONE " + ts)
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
