"""ВОЗРАСТ ТИКА РЯДОМ С ЕГО ВРЕМЕНЕМ (14.08.2026, шаг 2 цели 531).

ЖИВОЙ СЛУЧАЙ, на котором стоят голдены (снимок `cowork_log` через мост 14.08.2026 10:32 UTC):
последний тик ревизора — дословная строка
    «NOTE 2026-08-13 13:26 UTC: Orchestrator: ревизор: 1 окон, чисто  »
доска показывала её как «👁 надзор: ревизор 2026-08-13 13:26 — окон 1», и по этой строке тик
возрастом 21 ч 6 мин НЕОТЛИЧИМ от свежего.

Что доказывается:
    (1) ГОЛДЕН     на дословной строке доски возраст стоит РЯДОМ со штампом и назван числом,
                   а при пороге — ещё и словами «⚠️ тик старый»;
    (2) ЧЕТЫРЕ     исхода (свежий · старый · возраст неизвестен · ветка мертва) — и ни один
                   не сворачивается в другой; причины незнания РАЗЛИЧАЮТСЯ;
    (3) ЗАМОК      «возраст неизвестен» не читается ни как свежий, ни как старый: слова
                   «назад» в нём нет вовсе, пометки старости — тоже;
    (4) ПОРОГ      граница ровно на пороге, мусор в `.env` → дефолт (в сторону ГРОМКОГО),
                   ноль → ветка мертва;
    (5) ЧАСЫ ПК    штамп в будущем: до `SKEW_SEC` — дрожание часов, дальше — незнание;
    (6) ОТКАТ      `REVIZOR_TICK_HOURS=0` → строка доски БАЙТ-В-БАЙТ прежняя (дословный голден
                   до правки), и это единственная ручка;
    (7) ЖИВАЯ ДВЕРЬ на дословном боевом журнале через `_revisor_line`; НЕ-ok исходы читателя
                   (пусто · недоступен · не разобрал) не тронуты — возраста в них нет;
    (8) ЧИСТОТА    у решения ровно один импорт, ни рук, ни собственных часов (ast).
"""
import ast
import datetime
import os
import sys

# Корень берётся ОТ ФАЙЛА, а не литералом: иначе прогон «до правки» через `git worktree` тянул бы
# модули из БОЕВОГО дерева и зеленел бы на коде, которого в проверяемом дереве нет (ловушка метода,
# пойманная живьём 07.08). Чужой корень заодно вычищается из пути.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != "/root/turbobaby-manager-bot"] \
    if ROOT != "/root/turbobaby-manager-bot" else sys.path
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import revizor_age as RA
import devbot as DB


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []

# --- ДОСЛОВНЫЕ строки боевого cowork_log (снимок 14.08.2026, хвостовые пробелы сохранены) ---
_L_TICK_NEW = "NOTE 2026-08-13 13:26 UTC: Orchestrator: ревизор: 1 окон, чисто  "
_L_TICK_OLD = ("NOTE 2026-08-13 13:24 UTC: Orchestrator: ревизор: 1 окон с активностью "
               "с прошлого прогона — пакеты собраны  ")
_COWORK_LIVE = "\n".join([_L_TICK_NEW, _L_TICK_OLD]) + "\n"
_STAMP = "2026-08-13 13:26"
_NOW = datetime.datetime(2026, 8, 14, 10, 32)          # момент замера, наивный UTC
# Строка доски ДО правки — дословно, как её видел владелец 14.08:
_BOARD_BEFORE = "👁 надзор: ревизор 2026-08-13 13:26 — окон 1"


def _line(now=_NOW, hours=None):
    return DB._revisor_line(lambda: _COWORK_LIVE, now=now, hours=hours)


# (1) ГОЛДЕН: живой случай ТЗ — 21 час читался как свежий
print("(1) голден на ДОСЛОВНОМ живом случае 14.08 (тик 13.08 13:26, доска в 10:32):")
line = _line(hours=9)
res.append(ok(line == "👁 надзор: ревизор 2026-08-13 13:26 (21 ч 6 мин назад ⚠️ тик старый) "
                      "— окон 1",
              "возраст назван числом РЯДОМ со штампом + громкая пометка"))
res.append(ok(line.startswith("👁 надзор: ревизор 2026-08-13 13:26 ("),
              "приписка стоит ВПЛОТНУЮ к времени, а не в конце строки"))
res.append(ok("— окон 1" in line and "13:24" not in line,
              "тело тика не тронуто: окна на месте, старый тик по-прежнему не показывается"))
res.append(ok(_BOARD_BEFORE != line and _BOARD_BEFORE.replace(" — ", " (") not in line,
              "прежняя строка (без возраста) БОЛЬШЕ не выдаётся при живом пороге"))

# (2) ЧЕТЫРЕ исхода — и все четыре звучат по-разному
print("(2) четыре исхода:")
v_fresh = RA.verdict(_STAMP, datetime.datetime(2026, 8, 13, 15, 0), 9)
v_stale = RA.verdict(_STAMP, _NOW, 9)
v_unk = RA.verdict("13:26", _NOW, 9)
v_off = RA.verdict(_STAMP, _NOW, 0)
res.append(ok(v_fresh["state"] == RA.STATE_FRESH and v_fresh["said"] == "1 ч 34 мин назад",
              "свежий: возраст измерен, пометки старости нет"))
res.append(ok(v_stale["state"] == RA.STATE_STALE and v_stale["said"].endswith(RA.STALE_MARK),
              "старый: возраст измерен + громкая пометка"))
res.append(ok(v_unk["state"] == RA.STATE_UNKNOWN and v_unk["why"] == RA.WHY_NO_DATE,
              "легаси «чч:мм» без даты → НЕИЗВЕСТНО, а не «сегодня»"))
res.append(ok(v_off["state"] == RA.STATE_OFF and v_off["said"] == "",
              "порог 0 → ветка мертва, приписки нет"))
res.append(ok(len({v_fresh["said"], v_stale["said"], v_unk["said"], v_off["said"]}) == 4,
              "четыре исхода — четыре РАЗНЫЕ фразы"))
res.append(ok(round(v_stale["age_sec"]) == 21 * 3600 + 6 * 60,
              "возраст в секундах — измеренная величина, а не пересказ (21 ч 6 мин)"))
res.append(ok(v_unk["age_sec"] is None and v_off["age_sec"] is None,
              "нечего измерять → возраст None, а не 0 (нуль — это ИЗМЕРЕНИЕ)"))

# (3) ЗАМОК: незнание не читается ни как свежесть, ни как старость; причины различимы
print("(3) замок против ложного зелёного:")
whys = {
    RA.WHY_NO_STAMP: RA.verdict("", _NOW, 9),
    RA.WHY_NO_DATE: RA.verdict("13:26", _NOW, 9),
    RA.WHY_FUTURE: RA.verdict("2026-08-14 12:00", _NOW, 9),
    RA.WHY_NO_NOW: RA.verdict(_STAMP, "вчера", 9),
}
for why, v in whys.items():
    res.append(ok(v["state"] == RA.STATE_UNKNOWN and v["why"] == why and why in v["said"],
                  f"незнание названо своей причиной: «{why}»"))
    res.append(ok("назад" not in v["said"] and RA.STALE_MARK not in v["said"],
                  f"«{why}» не читается ни как свежий, ни как старый"))
res.append(ok(len({v["said"] for v in whys.values()}) == 4,
              "четыре причины незнания НЕ свёрнуты в одну фразу"))
res.append(ok("(возраст неизвестен: время тика не названо)" == RA.mark("", _NOW, 9),
              "тик без штампа на доске тоже называет незнание, а не молчит"))

# (4) ПОРОГ: граница, мусор, ноль
print("(4) порог:")
t0 = datetime.datetime(2026, 8, 14, 0, 0)
res.append(ok(RA.verdict("2026-08-13 15:00", t0, 9)["state"] == RA.STATE_FRESH,
              "ровно порог (9 ч) — ещё НЕ старый (граница не съедает своё же значение)"))
res.append(ok(RA.verdict("2026-08-13 14:59", t0, 9)["state"] == RA.STATE_STALE,
              "минутой раньше порога — уже старый"))
res.append(ok(RA.DEFAULT_HOURS == 9.0,
              "дефолт 9 ч — середина пустого промежутка живого замера (6.05…11.83)"))
for junk in ("", "три", None, float("nan"), [], "-5"):
    st = RA.verdict(_STAMP, _NOW, junk)["state"]
    res.append(ok(st == (RA.STATE_OFF if junk == "-5" else RA.STATE_STALE),
                  f"мусорный порог {junk!r} → дефолт (громкий слой жив); явный минус → мертва"))
res.append(ok(RA.verdict(_STAMP, _NOW, "3")["state"] == RA.STATE_STALE
              and RA.verdict("2026-08-14 06:00", _NOW, "3")["state"] == RA.STATE_STALE
              and RA.verdict("2026-08-14 06:00", _NOW, "9")["state"] == RA.STATE_FRESH,
              "число владельца работает: тик 4.5 ч при 3 ч стар, при 9 ч (штатный ход) свеж"))

# (5) ЧАСЫ ПК: штамп в будущем
print("(5) чужие часы:")
res.append(ok(RA.verdict("2026-08-14 10:35", _NOW, 9)["said"] == "меньше минуты назад",
              "3 мин в будущее = дрожание часов ПК → возраст 0, а не паника"))
res.append(ok(RA.verdict("2026-08-14 10:40", _NOW, 9)["why"] == RA.WHY_FUTURE,
              "8 минут в будущее (дальше SKEW_SEC) → НЕИЗВЕСТНО, вслух"))
res.append(ok(RA.SKEW_SEC == 300, "допуск часов назван числом, а не спрятан"))

# (6) ОТКАТ: одна ручка, строка байт-в-байт прежняя
print("(6) откат REVIZOR_TICK_HOURS=0:")
res.append(ok(_line(hours=0) == _BOARD_BEFORE,
              "порог 0 → строка доски БАЙТ-В-БАЙТ прежняя (дословный голден до правки)"))
_saved = os.environ.get("REVIZOR_TICK_HOURS")
try:
    os.environ["REVIZOR_TICK_HOURS"] = "0"
    res.append(ok(DB._revizor_tick_hours() == 0.0 and _line() == _BOARD_BEFORE,
                  "ручка читается из окружения ЛЕНИВО и гасит ветку целиком"))
    os.environ["REVIZOR_TICK_HOURS"] = "3"
    res.append(ok(DB._revizor_tick_hours() == 3.0 and "⚠️ тик старый" in _line(),
                  "число владельца (3 ч) — тем же .env, без правки кода"))
    os.environ["REVIZOR_TICK_HOURS"] = "мусор"
    res.append(ok(DB._revizor_tick_hours() == RA.DEFAULT_HOURS,
                  "мусор в .env → дефолт, а не тихо выключенная пометка"))
    os.environ.pop("REVIZOR_TICK_HOURS")
    res.append(ok(DB._revizor_tick_hours() == RA.DEFAULT_HOURS,
                  "ключа нет вовсе → дефолт решения (одно место истины)"))
finally:
    if _saved is None:
        os.environ.pop("REVIZOR_TICK_HOURS", None)
    else:
        os.environ["REVIZOR_TICK_HOURS"] = _saved

# (7) ЖИВАЯ ДВЕРЬ: НЕ-ok исходы читателя не тронуты
print("(7) живая дверь и НЕ-ok исходы читателя:")
res.append(ok(DB._revisor_line(lambda: "", now=_NOW) ==
              "👁 надзор: ревизор: тиков ещё не было — осмотрено 0 строк журнала — источник пуст",
              "пустой журнал: фраза прежняя, возраста в ней нет"))
for fn, mark_ in ((None, "НЕДОСТУПЕН"), (lambda: "просто строка", "НЕ РАЗОБРАН")):
    l = DB._revisor_line(fn, now=_NOW)
    res.append(ok(mark_ in l and "назад" not in l and "возраст неизвестен" not in l,
                  f"«{mark_}»: возраст не приписывается к тому, чего не прочли"))
res.append(ok("(21 ч 6 мин назад ⚠️ тик старый)" in _line(hours=9)
              and DB._parse_revisor("1 окон, чисто", " 2026-08-13 13:26 UTC: Orchestrator: ",
                                    now=_NOW, hours=9) == _line(hours=9),
              "разбор тика и строка доски дают одно и то же (одна дверь возраста)"))
res.append(ok(DB._parse_revisor("пакеты собраны, деталей нет", now=_NOW, hours=9) ==
              "👁 надзор: ревизор (возраст неизвестен: время тика не названо) — пакеты собраны,"
              " деталей нет",
              "тик без времени: «время неизвестно» не воскресло, но и молчания о возрасте нет"))

# (8) ЧИСТОТА решения (ast): один импорт, ни рук, ни собственных часов
print("(8) чистота решения (ast):")
src = open(os.path.join(ROOT, "revizor_age.py"), encoding="utf-8").read()
tree = ast.parse(src)
imports = set()
for n in ast.walk(tree):
    if isinstance(n, ast.Import):
        imports.update(a.name.split(".")[0] for a in n.names)
    elif isinstance(n, ast.ImportFrom):
        imports.add((n.module or "").split(".")[0])
res.append(ok(imports == {"datetime"}, f"импорт РОВНО ОДИН — datetime (нашлось: {sorted(imports)})"))
banned_calls = {"open", "exec", "eval", "compile", "__import__", "input", "print"}
bad = [n.func.id for n in ast.walk(tree)
       if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in banned_calls]
res.append(ok(not bad, f"ни одной руки в теле решения (нашлось: {bad})"))
own_clock = [a.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
             for a in [n.func] if isinstance(a, ast.Attribute)
             and a.attr in ("now", "utcnow", "today", "fromtimestamp")]
res.append(ok(not own_clock,
              f"своих часов у решения НЕТ — «сейчас» приносят (нашлось: {own_clock})"))

# формат возраста — таблицей, чтобы телефонная строка не разъезжалась
print("  формат возраста:")
for sec, want in ((0, "меньше минуты назад"), (59, "меньше минуты назад"), (60, "1 мин назад"),
                  (3599, "59 мин назад"), (3600, "1 ч назад"), (3660, "1 ч 1 мин назад"),
                  (86399, "23 ч 59 мин назад"), (86400, "1 сут назад"),
                  (90000, "1 сут 1 ч назад"), (4 * 86400 + 3600, "4 сут 1 ч назад")):
    res.append(ok(RA.human_age(sec) == want, f"{sec} с → «{want}»"))

print()
if all(res):
    print(f"OK: {len(res)}/{len(res)} проверок возраста тика на доске")
    sys.exit(0)
print(f"FAIL: {sum(1 for r in res if not r)} из {len(res)} проверок красные")
sys.exit(1)
