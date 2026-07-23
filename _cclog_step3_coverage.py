"""cc_log DONE (шаг 3/5 родитель 26: покрытие тестами устойчивости) + pulse — одной операцией."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()

ENTRY = """DONE 2026-07-02 23:36 UTC ([шаг 3/5 родитель 26], headless): ПОКРЫТИЕ ТЕСТАМИ УСТОЙЧИВОСТИ — ПОЛНОЕ, добавлять нечего (0 правок).
— Групп кнопок в splinter.py ровно 4 (по CallbackQueryHandler в bot.py + аудиту шагов 1–2): info: / svc: / delivery: / o3:. Кейс «протухший q.answer (BadRequest Query is too old) НЕ валит действие» есть у КАЖДОЙ:
  · info: → test_info_button.py кейс (i) — DeadAnswerQuery, карточка всё равно построена (edit прошёл);
  · svc: → test_service_pending.py::test_done_button_stale_answer_still_writes — запись oil+svc прошла, токен снят;
  · delivery: → test_handover_board.py::test_stale_answer_still_hands_over — state_set прошёл, разъём 💵 отправлен;
  · o3: → test_o3.py кейс (15) — pick И rescan оба переживают протухший answer.
— Механизм устойчивости централизован в хелперах _btn_answer/_o3_answer (try/except внутри), все 25+13 кнопочных мест идут через них (шаги 1–2) → по тесту на группу = покрытие механизма.
— Прогон: pytest в venv не установлен → штатный раннер venv/bin/python3 gate.py = 29 тестов зелёные (8.8с). Код/тесты НЕ менялись, деплой/restart не нужны.
— aud: (bot.py:182, сырой q.answer) и devbot-кнопки approve/reject/check/next (devbot.py, сырые) — НЕ из шага 2 (splinter.py-only), теста устойчивости у них НЕТ и добавлять сейчас нельзя: тест честно упадёт на непочиненном коде и заблокирует гейт шага 4. Остаются хвостом.
СТАТУС: функционально подтверждено (гейт зелёный, все 4 кейса в наборе).
ХВОСТЫ: сырые q.answer в bot.py:182 (aud:) и devbot.py — вне родителя 26 (шаги 4–5 = гейт+коммит и рестарт), нужна отдельная задача «фикс + тесты парой»; прежние хвосты без изменений.

"""

PULSE = "2026-07-02 23:36 | 🟢 | шаг 3/5 родителя 26: покрытие тестами устойчивости ПОЛНОЕ (4/4 группы info/svc/delivery/o3, гейт 29 зелёных, 0 правок) | ничего не жду, дальше шаг 4/5 (гейт+коммит) | детали→cc_log запись «шаг 3/5 родитель 26»"

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
