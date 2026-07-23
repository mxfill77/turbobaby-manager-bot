"""cc_log DONE (шаг 4/5 родитель 26: гейт + коммит + push) + pulse — одной операцией."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()

ENTRY = """DONE 2026-07-02 23:35 UTC ([шаг 4/5 родитель 26], headless): ГЕЙТ ЗЕЛЁНЫЙ, ВСЁ УЖЕ ЗАКОММИЧЕНО И ЗАПУШЕНО (0 новых коммитов).
— Гейт: venv/bin/python3 gate.py → 29 тестов зелёные (8.8с), exit 0, чинить нечего, --override не понадобился.
— Коммитить нечего: работа шагов 1–2 уже в истории — c866185 fix(buttons) (splinter.py: 63 строки, все кнопочные места info:/svc:/delivery: через _btn_answer; тесты устойчивости в test_info_button/test_service_pending/test_handover_board) + добивка к 749cf46 (o3: через _o3_answer). Шаг 3 = 0 правок (только аудит покрытия). git status: рабочая копия чистая (только .bak-копии и _*.py-хелперы, они в коммит не идут).
— git push: pre-push hook сам прогнал гейт (29 зелёных) → «Everything up-to-date», main синхронен с origin/main (HEAD 346a154). Оранжевый цикл соблюдён: бэкап=git, откат=git revert (не нужен).
СТАТУС: функционально подтверждено (гейт exit 0, push прошёл через hook).
ХВОСТЫ: без изменений — сырые q.answer в bot.py:182 (aud:) и devbot.py (approve/reject/check/next) ждут отдельной задачи «фикс + тесты парой»; остался шаг 5/5 (restart splinter).

"""

PULSE = "2026-07-02 23:35 | 🟢 | шаг 4/5 родителя 26: гейт 29 зелёных exit 0, коммитить нечего (fix(buttons) уже в c866185/749cf46), push=up-to-date, main==origin | ничего не жду, дальше шаг 5/5 (restart) | детали→cc_log запись «шаг 4/5 родитель 26»"

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
