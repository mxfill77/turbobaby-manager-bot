"""cc_log DONE (добивка ревизии §7: сырые q.answer вне splinter.py) + KB_PULSE — ОДНОЙ операцией.
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
"DONE " + ts + " UTC (headless, Filipp-328-dev): добиты последние сырые q.answer вне splinter.py "
"(хвост ревизии §7) — commit 51c196d, запушен, splinter перезапущен (старт чистый).\n"
"— bot.py:182 on_audit_button (кнопки 👍/✏️/👎 карточки аудита) → splinter._btn_answer: раньше протухший "
"ack (BadRequest «Query is too old») первой строкой валил хендлер — правило НЕ записывалось в memory.\n"
"— devbot.py: локальный _btn_answer (паттерн _o3_answer) + заменены ВСЕ 13 сырых q.answer "
"(approve/reject/check/next/чужой юзер/error-тост). Критично для check/next: там ack шёл ДО действия — "
"протухший колбэк оставлял кнопку «мёртвой». Логика хендлеров/гейты не тронуты.\n"
"— Тесты: tests/test_audit_button.py (4 сценария; bot.py импортирован со стабами Bridge/Claude/Memory/"
"Auditor — живая memory.db не тронута) + tests/test_devbot_buttons.py (5 сценариев). Гейт 33 зелёных.\n"
"— Оранжевый цикл restart: гейт exit 0 → systemctl restart splinter → is-active=active, старт-лог чистый "
"(Bridge alive, polling, scheduler started, ошибок нет). Бэкап = git (откат git revert 51c196d + restart) "
"+ bot.py/devbot.py.bak-btnans-20260703.\n"
"СТАТУС: технически готово; функционально не подтверждено (реальный протухший колбэк в 328/аудите "
"не воспроизводился — покрыто мок-тестами). Теперь сырых q.answer в репо нет нигде.\n"
"ХВОСТЫ: нет.\n"
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

pulse = (ts + " | 🟢 | ревизия §7 добита: протухший q.answer больше не валит кнопки bot.py (аудит 👍/✏️/👎) "
         "и devbot (approve/check/next) — commit 51c196d, гейт 33 зелёных, push ok, splinter перезапущен "
         "чисто | ничего не жду | детали→cc_log DONE " + ts)
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
