"""cc_log DONE (узкие allow-паттерны deferred-рестарта) + KB_PULSE — ОДНОЙ операцией.
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
"DONE " + ts + " UTC (задача:328, headless): узкие allow-паттерны deferred-рестарта — ПОДГОТОВЛЕНО, "
"ждёт разовый cp из Termux (headless в .claude/ писать не может — гейт движка, это правильно, не обходил).\n"
"— Паттерны (ТОЛЬКО две формы): «systemd-run --on-active=* systemctl restart orchestrator-daemon» и "
"«…restart splinter». Голый/широкий systemd-run в allow ЗАПРЕЩЁН НАВСЕГДА: transient unit исполняет "
"ПРОИЗВОЛЬНУЮ команду вне bash-паттернов allowlist = обход allow/ask/deny (мимо deny rm -rf и ask sqlite3). "
"Задокументировано в CLAUDE.md (РЕЖИМ АВТО-APPROVE, новый буллет Deferred-рестарт) и в докстринге теста.\n"
"— Тест классификации tests/test_settings_deferred_restart.py (в гейте, 17 проверок): узкие формы → allow; "
"8 других форм systemd-run (nginx/stop/rm/bash -c/без --on-active/--unit=/голый) → НЕ allow (дефолт prompt, "
"как раньше); в allow нет systemd-run-правил кроме 2 узких; прежняя классификация не тронута (stop→ask, "
"sqlite3→ask, --no-verify→deny, прямой restart splinter→allow). До применения тест проверяет подготовленный "
"файл + WARN; после — живой settings.json (сверка prepared↔live отключается, ложного красного не будет).\n"
"— ГЕЙТ ЗАПИСИ .claude/ headless: подтверждён (cp-бэкап и Edit settings.json — оба denied) → подготовлен "
"полный файл _sdrun_new_settings.json (= живой settings + ровно 2 строки allow, ask/deny/hooks идентичны — "
"сверено тестом). ПРИМЕНЕНИЕ (Филипп, Termux, одна команда): "
"cp _sdrun_new_settings.json .claude/settings.json\n"
"Гейт 31 зелёный; коммит fd281fc, push прошёл (pre-push гейт ✅). Бэкап: CLAUDE.md.bak-sdrun-20260703, "
"settings.json не менялся (бэкап не понадобился).\n"
"СТАТУС: технически готово (тест+доки+prepared в репо); ФУНКЦИОНАЛЬНО паттерны заработают ПОСЛЕ cp из Termux "
"+ они читаются на старте claude-сессии (демон спавнит новую сессию на задачу — подхват автоматом).\n"
"ХВОСТЫ: 1) Филипп: разовый cp выше, затем закоммитить изменённый .claude/settings.json (tracked) + можно "
"удалить _sdrun_new_settings.json; 2) прежние хвосты без изменений (подхват v3 демоном проверить на следующем "
"«тз:»; clasp redeploy склейки статусов — красное, ждёт «да»; сырые q.answer в bot.py:182 и devbot.py).\n"
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

pulse = (ts + " | 🟡 | deferred-рестарт: 2 узких allow-паттерна подготовлены (тест в гейте 31✅, CLAUDE.md, "
         "commit fd281fc push ✅); headless в .claude/ не пишет (гейт движка, не обходил) | жду от Филиппа разовый "
         "cp из Termux: cp _sdrun_new_settings.json .claude/settings.json | детали→cc_log DONE " + ts + " deferred-рестарт")
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
