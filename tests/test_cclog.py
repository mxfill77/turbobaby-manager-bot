"""cclog.py — вставка записи СВЕРХУ, но ПОД врезкой-шапкой (правило гигиены cc_log 25.06):
врезка (шапка + ═-only-линия) остаётся первой, новая запись идёт сразу под ней. Сеть не дёргаем —
проверяем чистую функцию _insert_under_vrezka + _make_entry + разбор типа/аргументов."""
import sys, re
sys.path.insert(0, "/root/turbobaby-manager-bot")
import cclog

res = []
def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l); res.append(bool(c)); return c

VREZKA = "📦 cc_log — шапка журнала\n" + "═" * 60 + "\n\nDONE 2026-07-05 10:00: старое\n"

# (a) есть врезка → запись под ═-линией, шапка остаётся строкой 0
out = cclog._insert_under_vrezka(VREZKA, "DONE 2026-07-05 13:00 UTC (Termux): новое")
lines = out.split("\n")
ok(lines[0].startswith("📦 cc_log"), "шапка врезки осталась первой строкой")
ok(set(lines[1].strip()) == {"═"}, "═-only-линия осталась второй")
i_new = out.index("новое"); i_old = out.index("старое")
ok(0 <= i_new < i_old, "новая запись ВЫШЕ старой, но НИЖЕ врезки")
ok(out.rstrip().endswith("старое"), "старое содержимое сохранено (не потеряно)")

# (b) врезки нет → просто сверху
plain = "DONE вчера: X\n"
out2 = cclog._insert_under_vrezka(plain, "DONE сегодня: Y")
ok(out2.index("сегодня") < out2.index("вчера"), "без врезки — запись просто сверху")

# (c) ═-only матчится по составу, НЕ по длине (короткая ═-линия тоже врезка)
short = "hdr\n" + "═" * 5 + "\n\nтело\n"
out3 = cclog._insert_under_vrezka(short, "NEW")
l3 = out3.split("\n")
ok(l3[0] == "hdr" and set(l3[1].strip()) == {"═"} and out3.index("NEW") < out3.index("тело"),
   "короткая ═-линия распознана как врезка (матч по составу)")

# (d) разбор типа: дефолт DONE, явный тип, регистронезависимо — через main с моком BridgeClient
import types
captured = {}
class _FakeBridge:
    def _call(self, action, **kw):
        return {"ok": True, "text": "hdr\n" + "═" * 60 + "\n\nold\n"}
    def write_doc(self, text, name=None, id=None):
        captured[name] = text
        return {"ok": True}
cclog.BridgeClient = _FakeBridge

captured.clear()
rc = cclog.main(["привет мир"])
# Найти запись в cc_log — должна быть одна строка точного канонического формата
cc_entry = next((l for l in captured.get("cc_log", "").split("\n") if "(Termux):" in l), "")
ok(rc == 0 and bool(re.match(
    r"DONE \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC \(Termux\): привет мир$", cc_entry)),
   "дефолтный DONE: точный формат YYYY-MM-DD HH:MM UTC (Termux): текст — единая строка")

captured.clear()
rc = cclog.main(["blocked", "нет доступа"])
ok(rc == 0 and "BLOCKED " in captured.get("cc_log", ""), "тип регистронезависим (blocked→BLOCKED)")
captured.clear()
rc = cclog.main(["done", "итог", "--pulse", "🟢 всё ок"])
ok(rc == 0 and captured.get("pulse") == "🟢 всё ок", "--pulse перезаписывает pulse той же операцией")

# (e) read_doc не ok → НЕ пишем (защита от затирки)
class _FailRead(_FakeBridge):
    def _call(self, action, **kw):
        return {"ok": False, "error": "timeout"}
cclog.BridgeClient = _FailRead
captured.clear()
rc = cclog.main(["что-то"])
ok(rc == 1 and captured == {}, "read FAIL → write НЕ вызван (защита от затирки)")

# (f) формат _make_entry: H:MM обязательны, единая строка, санитизация переносов
ENTRY_PAT = re.compile(
    r"^(?:DONE|PLAN|NOTE|BLOCKED|WAITING|SKIPPED) \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC \(Termux\): .+$"
)
entry = cclog._make_entry("DONE", "текст")
ok(bool(ENTRY_PAT.match(entry)),
   "_make_entry: формат KIND YYYY-MM-DD HH:MM UTC (Termux): текст")
ok("\n" not in entry,
   "_make_entry: запись без переносов строк (единая строка)")
ok(bool(re.search(r"\d{2}:\d{2} UTC", entry)),
   "_make_entry: H:MM обязательны в записи")

# Санитизация: \n внутри текста → пробел, единая строка
entry_nl = cclog._make_entry("PLAN", "строка1\nстрока2")
ok("\n" not in entry_nl,
   "_make_entry: \\n в тексте коллапсируется → единая строка")
ok("строка1" in entry_nl and "строка2" in entry_nl,
   "_make_entry: обе части текста сохраняются после коллапса \\n")

entry_crlf = cclog._make_entry("NOTE", "a\r\nb")
ok("\n" not in entry_crlf and "\r" not in entry_crlf,
   "_make_entry: CRLF тоже коллапсируется")

# Все типы дают валидный паттерн
for t in cclog.TYPES:
    e = cclog._make_entry(t, "x")
    ok(bool(ENTRY_PAT.match(e)), f"_make_entry тип {t}: паттерн валиден")

# (g) обратная совместимость: старые записи в old (без H:M или двустрочные) сохраняются без изменений
old_no_time = "DONE 2026-07-01 (Termux):\nстарый текст без времени\n"
out_g = cclog._insert_under_vrezka(
    "hdr\n" + "═" * 60 + "\n\n" + old_no_time,
    "DONE 2026-07-16 14:30 UTC (Termux): новая запись"
)
ok("старый текст без времени" in out_g,
   "обратная совм.: старые записи без H:M сохраняются в old-контенте")
ok(out_g.index("новая запись") < out_g.index("старый текст"),
   "обратная совм.: новое выше старого")


# (h) Класс 1+3: ретрансляция — вложенный headless-entry разворачивается в (headless via Termux)

# _relay_payload: нормальный текст не является ретрансляцией
ok(cclog._relay_payload("обычный текст без KIND-слова") is None,
   "_relay_payload: нормальный текст → None (не ретрансляция)")
ok(cclog._relay_payload("") is None,
   "_relay_payload: пустая строка → None")
ok(cclog._relay_payload("2026-07-16 UTC: что-то") is None,
   "_relay_payload: строка с датой но без KIND → None")

# _relay_payload: текст, начинающийся с KIND-слова — это ретрансляция
ok(cclog._relay_payload("DONE 2026-07-16 (headless): payload текст") == "payload текст",
   "_relay_payload: headless-запись → извлекает payload после «: »")
ok(cclog._relay_payload("PLAN 16.07 UTC (шаг 3/6): класс H сторож Б") == "класс H сторож Б",
   "_relay_payload: шаговая запись → payload после «: »")
ok(cclog._relay_payload("DONE шаг 1/6 (родитель 171): log.info fix-btn") == "log.info fix-btn",
   "_relay_payload: без даты, с шагом → payload после «: »")
ok(cclog._relay_payload("DONE 2026-07-16 UTC: просто текст") == "просто текст",
   "_relay_payload: KIND DATE UTC: text → payload")
ok(cclog._relay_payload("NOTE без_двоеточия") == "без_двоеточия",
   "_relay_payload: нет «: » → всё тело после KIND")
ok(cclog._relay_payload("DONE 2026-07-16 (headless): PLAN 16.07: вложенный план") == "PLAN 16.07: вложенный план",
   "_relay_payload: двойное вложение → payload с первого «: »")

# _make_entry: ретрансляция → (headless via Termux)
from datetime import datetime, timezone as _tz
_fixed_now = datetime(2026, 7, 16, 9, 0, tzinfo=_tz.utc)

entry_relay = cclog._make_entry("DONE", "DONE 2026-07-16 07:44 UTC (headless): реальный payload", now=_fixed_now)
ok("(headless via Termux):" in entry_relay, "_make_entry relay: источник «(headless via Termux)»")
ok("(Termux):" not in entry_relay, "_make_entry relay: НЕ вложенный «(Termux):»")
ok("реальный payload" in entry_relay, "_make_entry relay: реальный payload сохранён")
ok("DONE 2026-07-16 07:44 UTC (headless):" not in entry_relay, "_make_entry relay: внутренний заголовок НЕ дублируется")

entry_relay2 = cclog._make_entry("DONE", "PLAN 16.07 UTC (шаг 3/6 родитель 171): класс H", now=_fixed_now)
ok("(headless via Termux):" in entry_relay2, "_make_entry relay шаговая запись: источник")
ok("класс H" in entry_relay2, "_make_entry relay шаговая: payload сохранён")

# _make_entry: нормальный текст → (Termux) без изменений (регресс)
entry_normal = cclog._make_entry("DONE", "обычный текст 123", now=_fixed_now)
ok("(Termux):" in entry_normal, "_make_entry нормальный: сохраняет «(Termux):»")
ok("(headless via Termux):" not in entry_normal, "_make_entry нормальный: НЕ помечает как relay")

# ENTRY_RE принимает оба формата: (Termux) и (headless via Termux)
ok(bool(cclog.ENTRY_RE.match("DONE 2026-07-16 09:00 UTC (Termux): текст")),
   "ENTRY_RE матчит (Termux):")
ok(bool(cclog.ENTRY_RE.match("DONE 2026-07-16 09:00 UTC (headless via Termux): текст")),
   "ENTRY_RE матчит (headless via Termux):")
ok(not cclog.ENTRY_RE.match("DONE 2026-07-16 09:00 UTC (headless via Termux):"),
   "ENTRY_RE НЕ матчит (headless via Termux): без payload")

# Сквозной прогон main() с ретрансляцией
cclog.BridgeClient = _FakeBridge   # восстановить мок (после _FailRead в секции (e))
captured.clear()
rc = cclog.main(["DONE 2026-07-16 UTC (headless): сводка задачи 42"])
cc_entry = next((l for l in captured.get("cc_log", "").split("\n") if "(headless via Termux):" in l), "")
ok(rc == 0 and bool(re.match(
    r"DONE \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC \(headless via Termux\): сводка задачи 42$", cc_entry)),
   "main() relay → каноничный (headless via Termux): текст в cc_log, одна строка")

# Ретрансляция НЕ меняет (headless via Termux) entries дважды (идемпотентность)
captured.clear()
cclog.main(["DONE 2026-07-16 09:00 UTC (headless via Termux): уже правильный формат"])
cc_relay2 = next((l for l in captured.get("cc_log", "").split("\n") if "уже правильный формат" in l), "")
ok("(headless via Termux): уже правильный формат" in cc_relay2,
   "relay идемпотентен: (headless via Termux) entry не оборачивается повторно")

# (i) Класс 2: пульс — обязательный H:MM

ok(cclog._ensure_pulse_hhmm("2026-07-16 | 🟢 | статус", now=_fixed_now) == "2026-07-16 09:00 | 🟢 | статус",
   "_ensure_pulse_hhmm: дата без H:MM → инжектирует H:MM")
ok(cclog._ensure_pulse_hhmm("2026-07-16 08:46 UTC | 🟢 | статус") == "2026-07-16 08:46 UTC | 🟢 | статус",
   "_ensure_pulse_hhmm: дата с H:MM → без изменений")
ok(cclog._ensure_pulse_hhmm("🟢 готово") == "🟢 готово",
   "_ensure_pulse_hhmm: без даты → без изменений")
ok(re.search(r"\d{2}:\d{2}", cclog._ensure_pulse_hhmm("2026-07-16 | 🟢 | текст", now=_fixed_now)),
   "_ensure_pulse_hhmm: результат содержит H:MM")

# _ensure_pulse_hhmm не трогает уже корректный пульс
pulse_ok = "2026-07-16 09:00 | 🔴 | ждёт да"
ok(cclog._ensure_pulse_hhmm(pulse_ok, now=_fixed_now) == pulse_ok,
   "_ensure_pulse_hhmm: корректный пульс не меняется (идемпотентен)")

# main() --pulse с датой без H:MM → H:MM добавляется
captured.clear()
cclog.main(["тест пульса", "--pulse", "2026-07-16 | 🟢 | что-то сделал"])
stored_pulse = captured.get("pulse", "")
ok(bool(re.search(r"2026-07-16 \d{2}:\d{2}", stored_pulse)),
   "main() --pulse: H:MM инжектируется в пульс при записи")

# main() --pulse с полным форматом → не изменяется
captured.clear()
cclog.main(["тест пульса 2", "--pulse", "2026-07-16 08:46 | 🟢 | уже правильный"])
ok("2026-07-16 08:46 | 🟢 | уже правильный" == captured.get("pulse", ""),
   "main() --pulse: H:MM уже есть → пульс не меняется")

# (j) Обратная совместимость чтения: старые записи не ломаются

# Старые записи без H:MM в old-контенте (до de95caf/format3) сохраняются
old_legacy = "DONE 2026-07-01 UTC (Termux):\nстарый текст без HH:MM\n"
out_j = cclog._insert_under_vrezka(
    "hdr\n" + "═" * 60 + "\n\n" + old_legacy,
    "DONE 2026-07-16 09:00 UTC (Termux): новая запись"
)
ok("старый текст без HH:MM" in out_j,
   "обратная совм. (j): старые записи без H:MM сохраняются в old-контенте")
ok(out_j.index("новая запись") < out_j.index("старый текст"),
   "обратная совм. (j): новое выше старого")

# Вложенные записи (Termux)/(headless) из прошлого не трогаются при _insert_under_vrezka
old_nested = "DONE 2026-07-15 15:10 UTC (Termux): DONE 2026-07-15 UTC (headless): текст\n"
out_j2 = cclog._insert_under_vrezka(
    "hdr\n" + "═" * 60 + "\n\n" + old_nested,
    "DONE 2026-07-16 09:00 UTC (Termux): свежая запись"
)
ok("DONE 2026-07-15 15:10 UTC (Termux): DONE 2026-07-15 UTC (headless): текст" in out_j2,
   "обратная совм. (j): старые вложенные записи не изменяются в old-контенте")
ok(out_j2.index("свежая запись") < out_j2.index("текст"),
   "обратная совм. (j): новое выше старого вложенного")

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
