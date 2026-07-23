"""Запись DONE аудита задачи 46 в cc_log (под врезкой) + пульс — ОДНОЙ операцией."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

ENTRY = """DONE 2026-07-03 06:12 UTC (задача:328 id=47, headless, read-only): АУДИТ ДИСЦИПЛИНЫ ЗАДАЧИ 46 по v3.1 — ЧИСТО, нарушений нет.
— cc_log+пульс одной операцией: DONE 05:44 в cc_log есть; в сводке задачи явное «cc_log DONE + пульс записаны одной операцией (write ok/ok)». Прямая сверка пульса невозможна (перезаписан операцией 05:48 — норма, пульс = перезапись by design); противоречий нет → принято по самоотчёту.
— Отчёт ДО рестарта: рестартов из ТЕЛА задачи 46 НЕ БЫЛО вообще (задача упёрлась в гейт записи .claude/ и честно доложила «нужен cp из Termux», не обходила — 2 отказа движка зафиксированы). Демон рестартован 05:50:31 владельцем из Termux, через 5.5 мин ПОСЛЕ complete (05:45:05) — порядок «отчёт → рестарт» соблюдён. orchestrator_daemon.py задача не правила (fd281fc: CLAUDE.md + prepared settings + тест).
— Честный статус: разделение есть и в cc_log («СТАТУС: технически готово… ФУНКЦИОНАЛЬНО после cp»), и в сводке 328 (🟡 «Подготовлено, ждёт разовый cp»). Плюс по дисциплине: бэкап CLAUDE.md.bak-sdrun-20260703, гейт 31✅, push через pre-push гейт.
Источники: orchestrator_daemon.log (тайминги id=46 05:38→05:45), journalctl (рестарт 05:50:31), Bridge-очередь (result id=46), cc_log DONE 05:44. Хелперы аудита: _audit46_*.py (3 шт, read-only, орфаны под правило 7 дней).
ХВОСТЫ: прежние без изменений (3-е «тз:» для критерия обкатки уже закрыто Q2-разблокировкой? — сверить при следующей задаче; cp-хвост задачи 46 закрыт владельцем 05:48).
"""

PULSE = "2026-07-03 06:12 | 🟢 | аудит дисциплины задачи 46 (id=47): ЧИСТО — отчёт cc_log+пульс одной операцией (по самоотчёту, противоречий нет), рестартов из тела не было (демон рестартовал владелец 05:50 ПОСЛЕ complete 05:45), статус честный (технически/функционально разделён) | ничего не жду | детали→cc_log DONE 06:12 «аудит задачи 46»"

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    raise SystemExit(f"read cc_log FAILED: {r}")
text = r.get("text", "")
lines = text.split("\n")
sep = None
for i, ln in enumerate(lines):
    s = ln.strip()
    if s and set(s) == {"═"}:
        sep = i
        break
if sep is None:
    raise SystemExit("врезка (═-строка) не найдена — не пишу")
new_text = "\n".join(lines[: sep + 1]) + "\n\n" + ENTRY + "\n" + "\n".join(lines[sep + 1 :]).lstrip("\n")
# сверка: пульс не затёрт кривым GET-вызовом (413 отклонён до исполнения, но проверяем)
chk = c._call("read_doc", name="cc_log")
if not chk.get("ok") or "аудит дисциплины задачи 46" in chk.get("text", "").lower():
    raise SystemExit(f"пред-проверка: запись уже есть или read failed — не дублирую: ok={chk.get('ok')}")
w1 = c.write_doc(new_text, name="cc_log")
w2 = c.write_doc(PULSE, name="pulse")
print("cc_log write ok:", w1.get("ok"), "| pulse write ok:", w2.get("ok"))
