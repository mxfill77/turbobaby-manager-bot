# -*- coding: utf-8 -*-
"""Метрики задачи: единый формат строки METRICS (наблюдаемость обеих полос) + norm_effort /
extract_tokens / selfheal_count. Чистые функции, без сети/claude — детерминированный юнит.
Стиль/раннер как у tests/test_executor_model.py (standalone: python3 tests/test_metrics_line.py)."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
import task_metrics as M


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []

line = M.metrics_line(task=42, lane="vps", model="claude-fable-5", effort="xhigh",
                      start_iso="2026-07-24T14:00:00+00:00", end_iso="2026-07-24T14:00:37+00:00",
                      dur_s=37.4, outcome="done", attempts=1, selfheals=0,
                      tokens_in=1200, tokens_out=340,
                      task_text="ultrathink Приземлить проверенный гард из origin/main",
                      mode="prod", src="orchestrator_daemon.py")
exp = ("METRICS task=42 lane=vps type=code mode=prod src=orchestrator_daemon.py "
       "model=claude-fable-5 effort=xhigh "
       "start=2026-07-24T14:00:00+00:00 end=2026-07-24T14:00:37+00:00 dur_s=37.40 "
       "outcome=done attempts=1 selfheals=0 tokens_in=1200 tokens_out=340")
res.append(ok(line == exp, "формат строки METRICS дословно (голден)"))
res.append(ok(" type=other mode=na src=na " in M.metrics_line(
                  task=2, lane="vps", model="m", effort="xhigh", start_iso="s", end_iso="e",
                  dur_s=1, outcome="done", attempts=1, selfheals=0),
              "старый вызов без новых полей жив: type=other mode=na src=na"))

res.append(ok(M.metrics_line(task=1, lane="vps", model=None, effort="xhigh", start_iso="s",
              end_iso="e", dur_s=0, outcome="failed", attempts=1, selfheals=0).endswith(
              "tokens_in=na tokens_out=na"), "нет токенов / model None -> na"))

res.append(ok(M.norm_effort("XHIGH") == "xhigh" and M.norm_effort("bogus") == "xhigh"
              and M.norm_effort("") == "xhigh" and M.norm_effort(None) == "xhigh"
              and M.norm_effort("max") == "max",
              "norm_effort: регистр/дефолт xhigh/валид"))

res.append(ok(M.extract_tokens({"usage": {"input_tokens": 12, "output_tokens": 3}}) == (12, 3),
              "extract_tokens: usage.input/output_tokens"))
res.append(ok(M.extract_tokens({"modelUsage": {"claude-fable-5": {"inputTokens": 5, "outputTokens": 7}}}) == (5, 7),
              "extract_tokens: сумма modelUsage[*].inputTokens/outputTokens"))
res.append(ok(M.extract_tokens({"modelUsage": {"claude-sonnet-4-6": {
                  "inputTokens": 2, "cacheReadInputTokens": 29339,
                  "cacheCreationInputTokens": 16329, "outputTokens": 8}}}) == (45670, 8),
              "extract_tokens: ПОЛНЫЙ вход input+cacheRead+cacheCreation (живой формат с кэшем)"))
res.append(ok(M.extract_tokens({"usage": {"input_tokens": 2, "cache_read_input_tokens": 100,
                  "cache_creation_input_tokens": 50, "output_tokens": 9}}) == (152, 9),
              "extract_tokens: usage полный вход с кэшем"))
res.append(ok(M.extract_tokens("x") == (None, None) and M.extract_tokens({}) == (None, None),
              "extract_tokens: не-json / пусто -> (None, None)"))

res.append(ok(M.selfheal_count("обычная") == 0
              and M.selfheal_count("[самопочинка задачи 3, попытка 1]") == 1
              and M.selfheal_count("[самопочинка шага 2, попытка 2]") == 2,
              "selfheal_count по маркеру «[самопочинка … попытка N]»"))

# ---------------------------------------------------------------------------------------------
# (1) ТЕСТ-ПРОГОН ОТЛИЧИМ ОТ БОЕВОГО. Дыра 25.07.2026: копия теста под ЧУЖИМ именем писала в
# боевой журнал строки METRICS, неотличимые от живых задач.
print("(1) under_test: тест-прогон опознаётся, боевой демон — нет")
res.append(ok(M.under_test("/root/x/tests/test_foo.py", {}, ()) is True,
              "имя входного файла test_*.py → тест"))
res.append(ok(M.under_test("/tmp/old_om.py", {"ORCH_TEST_MODE": "1"}, ()) is True,
              "КОПИЯ теста под чужим именем + ORCH_TEST_MODE=1 → тест (та самая дыра)"))
res.append(ok(M.under_test("x.py", {"PYTEST_CURRENT_TEST": "t"}, ()) is True, "pytest в окружении"))
res.append(ok(M.under_test("x.py", {}, ("pytest",)) is True, "pytest в sys.modules"))
res.append(ok(M.under_test("x.py", {"ORCH_DAEMON_TEST": "1"}, ()) is True, "явный ORCH_DAEMON_TEST=1"))
res.append(ok(M.under_test("/root/turbobaby-manager-bot/orchestrator_daemon.py", {}, ()) is False,
              "боевой демон — НЕ тест (иначе журнал замолчит в бою)"))
res.append(ok(M.under_test("orchestrator_daemon.py", {"ORCH_TEST_MODE": "0"}, ()) is False,
              "ORCH_TEST_MODE=0 боевой режим не ломает"))

# (3) ТИП ЗАДАЧИ — на ДОСЛОВНЫХ текстах заданий из боевого журнала (правило репо: голдены детекта
# строятся на реальных фразах владельца, а не на идеализированных формулировках).
print("(3) тип задачи по признакам — живые тексты заданий из журнала")
CASES = [
    ("ultrathink ТОЛЬКО read-only. Ответ ТЕКСТОМ в 328 И краткий итог 3-5 строк в result.", "read"),
    ("ultrathink ТОЛЬКО проверка в изолированном worktree. Живую рабочую копию и демон НЕ трогать.", "read"),
    ("ultrathink Read-only живая проверка гарда + обновление пульса. Код не менять, не коммитить.", "read"),
    ("[куратор цели 377, шаг 1] read-only, ничего не менять/не коммитить. Дай FACT: дословный вывод команд", "read"),
    ("[замер Opus 5 — read-only] Ответь ОДНОЙ строкой: сколько файлов *.py лежит в каталоге tests", "read"),
    ("ultrathink Замер влияния ключевого слова на уровень усилий.", "read"),
    ("ultrathink Проверить метрики живьём и разобрать самообновление демона.", "read"),
    ("ultrathink Приземлить проверенный гард из origin/main.", "code"),
    ("ultrathink Приземлить проверенный фикс из GitHub через merge.", "code"),
    ("[шаг 2/6 родитель 185] поправить карточку приёма", "code"),
    ("ultrathink Класс-фикс гарда: позиционные аргументы скрипта не делают команду красной.", "build"),
    ("ultrathink Одометр ТО, этап 2 — мягкий гейт.", "build"),
    ("ultrathink Выкатить одометр в прод.", "build"),
    ("ultrathink Очистить и достроить метрики.", "build"),
    ("ultrathink Перезапустить демон оркестратора, чтобы вступили новые пороги гейтов (коммит 0bbca3d).", "other"),
]
for _txt, _want in CASES:
    _got, _mk = M.task_type_explain(_txt)
    res.append(ok(_got == _want, "%-5s ← «%s» [признак: %s]" % (_got, _txt[:58], _mk or "нет")))
res.append(ok(M.task_type("") == "other" and M.task_type(None) == "other", "пусто/None → other"))
res.append(ok(M.task_type("ЧИТАТЬ ТОЛЬКО, НИЧЕГО НЕ МЕНЯТЬ") == "read", "регистр не важен"))

# (4) ДЛИТЕЛЬНОСТЬ С ДРОБНОЙ ЧАСТЬЮ — раньше всё короче 1.5 с схлопывалось в dur_s=0
print("(4) длительность: короткие задачи больше не схлопываются в ноль")
_short = M.metrics_line(task=9, lane="vps", model="m", effort="xhigh", start_iso="s", end_iso="e",
                        dur_s=0.834, outcome="done", attempts=1, selfheals=0)
res.append(ok(" dur_s=0.83 " in _short, "0.834 с → dur_s=0.83 (было бы dur_s=0)"))
res.append(ok(" dur_s=176.00 " in M.metrics_line(task=9, lane="vps", model="m", effort="xhigh",
              start_iso="s", end_iso="e", dur_s=176, outcome="done", attempts=1, selfheals=0),
              "целое число секунд → 176.00"))
res.append(ok(" dur_s=0.01 " in M.metrics_line(task=9, lane="vps", model="m", effort="xhigh",
              start_iso="s", end_iso="e", dur_s=0.009, outcome="done", attempts=1, selfheals=0),
              "9 мс → 0.01, а не 0"))
res.append(ok(len(_short.split()) == len(set(x.split("=")[0] for x in _short.split()[1:])) + 1,
              "все ключи строки уникальны (строка остаётся тривиально парсимой)"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
