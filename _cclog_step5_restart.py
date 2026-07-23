"""cc_log DONE (шаг 5/5 родитель 26: restart splinter оранжевым циклом) + pulse — одной операцией."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()

ENTRY = """DONE 2026-07-02 23:39 UTC ([шаг 5/5 родитель 26], headless): RESTART SPLINTER — ОРАНЖЕВЫЙ ЦИКЛ, СТАРТ ЧИСТЫЙ. Родитель 26 закрыт целиком.
— Бэкап: рабочий коммит HEAD 346a154 (main==origin, рабочая копия чистая — только .bak/_*.py-хелперы), откат = git reset на 346a154 + restart (не понадобился).
— Гейт: venv/bin/python3 gate.py → 29 тестов зелёные (9.0с), exit 0.
— systemctl restart splinter → is-active=active; старт-лог 23:37:24 чистый: Memory DB ok, Auditor ✅, темы/закрепы 41+41, Bridge ✅ alive v1.0.0, интервалы ТО прогреты, polling started, scheduler started (7 джобов); ERROR/Traceback после старта = 0.
— Покрытие родителя 26: 0 сырых q.answer-мест в splinter.py — всё покрыто c866185 (info:/svc:/delivery: через _btn_answer) + 749cf46 (o3: через _o3_answer); шаг 3 = аудит, 0 правок.
СТАТУС: технически готово + рестарт функционально подтверждён (active, чистый старт-лог); поведение кнопок в реале — по факту следующего нажатия.
ХВОСТЫ: сырые q.answer в bot.py:182 (aud:) и devbot.py (approve/reject/check/next) — отдельная задача «фикс + тесты парой».

"""

PULSE = "2026-07-02 23:39 | 🟢 | родитель 26 закрыт: шаг 5/5 restart splinter — гейт 29 зелёных, active, старт чистый (0 ошибок после 23:37:24); 0 сырых мест в splinter.py, покрыто c866185+749cf46 | ничего не жду | детали→cc_log запись «шаг 5/5 родитель 26»"

r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("read cc_log FAILED:", r.get("error"))
    raise SystemExit(1)
text = r.get("text", "")
lines = text.split("\n")
sep = None
for i, ln in enumerate(lines):
    s = ln.strip()
    if s and set(s) == {"═"}:
        sep = i
        break
if sep is None:
    print("врезка (═-строка) не найдена — не пишу")
    raise SystemExit(1)
new_text = "\n".join(lines[: sep + 1]) + "\n" + ENTRY + "\n".join(lines[sep + 1 :])
w = c.write_doc(text=new_text, name="cc_log")
print("cc_log write ok:", w.get("ok"), "| len:", len(new_text))

p = c.write_doc(text=PULSE, name="pulse")
print("pulse write ok:", p.get("ok"))
