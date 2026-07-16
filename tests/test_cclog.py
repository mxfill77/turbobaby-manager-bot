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

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
