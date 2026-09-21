# -*- coding: utf-8 -*-
"""ЗЕЛЁНАЯ ГАЛОЧКА ТОЛЬКО НА ИЗМЕРЕННОМ ПРОБЕГЕ (21.09.2026, класс 69v).

ЧТО СТЕРЕЖЁТ (ослабить — покраснеть):
  1. ГЛАВНЫЙ ГОЛДЕН ОТРИЦАТЕЛЬНЫЙ. Подставленный пробег НЕ ДАЁТ ни одной зелёной галочки —
     считается ЧИСЛОМ вхождений «✅» в карточку, а не глазом. Живой вход — ADV 350CC BLACK GOLD
     PHUKET 372 замера 69u: `current_km = 12212` = `max(I/J/K/L)`, и у регистра-МАКСИМУМА остаток
     по построению равен полному интервалу (`rem = last + iv − last`), то есть карточка
     утверждала, что байк проехал с последней замены РОВНО НОЛЬ километров. Настоящий одометр
     того же дня по фотографии приборки — 14919, расхождение 2707 км.
  2. СВОЙ ОДОМЕТР — БАЙТ-В-БАЙТ КАК БЫЛО. Голдены здесь — ЛИТЕРАЛЫ, снятые с версии ДО правки
     (`splinter.py` до 21.09): если правка тронет здоровый путь, покраснеет ровно эта строка.
  3. ГРОМКОЕ ПЕРЕЖИВАЕТ ПОДСТАНОВКУ, НО НАЗЫВАЕТСЯ ГРАНИЦЕЙ. Просрочка на подставленном пробеге
     остаётся просрочкой (подставленный пробег не больше настоящего → настоящий перепробег не
     меньше посчитанного), но текст обязан сказать «не меньше чем», и форма БЕЗ границы в такой
     строке не встречается вовсе.
  4. FAIL-CLOSED ПО УМОЛЧАНИЮ. Источник не назвали — галочки нет. Иначе один забытый вызов вернул
     бы ложное зелёное молча, и это была бы ровно прежняя болезнь.
  5. ОДНО ПРАВИЛО НА ДВУХ СУДЕЙ. Условие «а своим ли одометром мерили» и имя причины живут в
     `park_verdict` (`measured`, `why_unmeasured`); в `_mand_line` своей копии нет — проверяется
     разбором ИСХОДНИКА функции, а не обещанием в докстринге.
  6. ЧИСЛО ПРИХОДИТ В КАРТОЧКУ НАЗВАННЫМ. Живая сборка зовёт `_odo_current_src` (правило), а не
     дверь `_odo_current` (она слово «откуда» выбрасывает) — проверяется прогоном сборки на
     мок-мосте БЕЗ своего одометра.
  7. ТАЙСКИЙ БЛОК БЕЗ КИРИЛЛИЦЫ. Новые строки двуязычны, и русское слово причины в тайскую
     половину не уезжает — ровно это ловит живой аудитор исходящего (`auditor.py`), через который
     проходит каждое сообщение Splinter.

СЕТИ В ТЕСТЕ НЕТ: мост — фикстура, боевых таблиц не касаемся, сообщений не шлём.
"""
import ast
import inspect
import os
import re
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import park_verdict                                                    # noqa: E402
import splinter as S                                                   # noqa: E402

res = []


def ok(cond, label):
    print(("  PASS " if cond else "  FAIL ") + label)
    res.append(bool(cond))
    return bool(cond)


def th_block(card):
    """Тайская половина карточки: от 🇹🇭-строки до 🇷🇺-строки."""
    out, inth = [], False
    for line in card.split("\n"):
        s = line.lstrip()
        if s.startswith("\U0001f1f7\U0001f1fa"):
            inth = False
        if s.startswith("\U0001f1f9\U0001f1ed"):
            inth = True
        if inth:
            out.append(line)
    return "\n".join(out)


BIKE = "ADV 350CC BLACK GOLD PHUKET 372"
# Живой ряд 69u: I=J=12212, K и L пусты; интервалы масла и редуктора — 4000.
MAND_372 = [
    {"kind": "oil", "last": 12212, "interval": 4000},
    {"kind": "gear", "last": 12212, "interval": 4000},
    {"kind": "abs", "last": 0, "interval": 10000},
    {"kind": "airfilter", "last": 0, "interval": 20000},
]

print("\n(1) ОТРИЦАТЕЛЬНЫЙ ГОЛДЕН: подставленный пробег не даёт НИ ОДНОЙ галочки")
sub = S.msg_bike_card(BIKE, "12212", MAND_372, None,
                      cur_km_source=park_verdict.SRC_FALLBACK)
ok(sub.count("✅") == 0,
   "зелёных галочек в карточке: %d (нужно 0)" % sub.count("✅"))
ok("ещё <b>4000</b> км" not in sub,
   "обещания «ещё 4000 км» в карточке нет вовсе")
ok("Масло — ❓ <b>не измерено</b>: "
   "пробег подставлен · "
   "остаток не больше 4000 км" in sub,
   "масло: «не измерено», причина СВОИМИ СЛОВАМИ, остаток назван ВЕРХНЕЙ границей")
ok(sub.count("<b>не измерено</b>") == 2,
   "«не измерено» ровно у двух видов (масло+редуктор): %d"
   % sub.count("<b>не измерено</b>"))
ok(sub.count("<b>не делалось</b>") == 2,
   "пустые клетки (ABS, фильтр) ведут себя КАК БЫЛО — это не предмет этого захода")

print("\n(2) СВОЙ ОДОМЕТР — БАЙТ-В-БАЙТ КАК ДО ПРАВКИ")
own = S.msg_bike_card(BIKE, "12212", MAND_372, None, cur_km_source=park_verdict.SRC_OWN)
ok("Масло — ✅ ещё <b>4000</b> км "
   "(срок 16212)" in own,
   "масло: прежняя строка «✅ ещё <b>4000</b> км (срок 16212)» цела")
ok(own.count("✅") == 4,
   "галочек на своём одометре: %d — два вида в ДВУХ половинах карточки" % own.count("✅"))
ok("✅ อีก <b>4000</b> กม. (ครบ 16212)" in own,
   "тайская половина здорового пути тоже прежняя")
ok("не измерено" not in own,
   "на своём одометре слова «не измерено» нет вовсе")

print("\n(3) ПРОСРОЧКА: громкое переживает подстановку, но называется НИЖНЕЙ границей")
MAND_OVER = [{"kind": "oil", "last": 36400, "interval": 4000}]
over_own = S.msg_bike_card("NMAX 4685", "40900", MAND_OVER, None,
                           cur_km_source=park_verdict.SRC_OWN)
over_sub = S.msg_bike_card("NMAX 4685", "40900", MAND_OVER, None,
                           cur_km_source=park_verdict.SRC_FALLBACK)
ok("Масло — ⚠️ <b>просрочено "
   "на 500 км</b>" in over_own,
   "свой одометр: прежняя строка «просрочено на 500 км» цела")
ok("<b>просрочено не меньше "
   "чем на 500 км</b>" in over_sub
   and "нижняя граница" in over_sub,
   "подстановка: «просрочено не меньше чем на 500 км» + слова «нижняя граница»")
ok("<b>просрочено на 500 км</b>" not in over_sub,
   "ОТРИЦАТЕЛЬНЫЙ: формы БЕЗ границы на подстановке не встречается вовсе")
ok("500" in over_sub, "число просрочки не смягчено — то же самое 500")
ok(over_sub.count("✅") == 0, "на просрочке галочки нет ни в одной ветке")

print("\n(4) FAIL-CLOSED: источник не назвали — галочки нет")
unnamed = S.msg_bike_card(BIKE, "12212", MAND_372, None)
ok(unnamed.count("✅") == 0,
   "умолчание msg_bike_card даёт %d галочек (нужно 0)" % unnamed.count("✅"))
ok(park_verdict.WHY_ODO_SOURCE_UNNAMED in unnamed,
   "причина названа готовым словом park_verdict, а не новой фразой")
ok(S._mand_line("oil", 12212, 4000, "12212")[1].count("✅") == 0,
   "и у самой `_mand_line` умолчание тоже закрытое")

print("\n(5) ОДНО ПРАВИЛО НА ДВУХ СУДЕЙ — разбором исходника, а не обещанием")
def code_without_docstring(fn):
    """ИСПОЛНЯЕМОЕ тело функции текстом, БЕЗ докстринга: докстринг кодом не является, и запрет
    «своей копии правила» иначе ловил бы собственное объяснение правила."""
    fnode = ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]
    body = fnode.body
    if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    return "\n".join(ast.unparse(n) for n in body)


src_mand = code_without_docstring(S._mand_line)
ok("park_verdict.measured" in src_mand,
   "`_mand_line` спрашивает предикат у park_verdict")
ok("SRC_OWN" not in src_mand and park_verdict.SRC_OWN not in src_mand,
   "и НЕ держит своей копии условия «свой одометр» (докстринг не в счёт)")
ok("park_verdict.why_unmeasured" in src_mand,
   "имя причины тоже берётся готовым, а не пишется здесь")
ok(park_verdict.measured(park_verdict.SRC_OWN) is True
   and park_verdict.measured(park_verdict.SRC_FALLBACK) is False
   and park_verdict.measured(park_verdict.SRC_UNKNOWN) is False
   and park_verdict.measured("") is False and park_verdict.measured(None) is False,
   "`measured` истинен РОВНО у своего одометра (5 входов)")
ok(park_verdict.why_unmeasured(park_verdict.SRC_OWN) == ""
   and park_verdict.why_unmeasured(park_verdict.SRC_FALLBACK) == park_verdict.WHY_ODO_SUBSTITUTED
   and park_verdict.why_unmeasured(park_verdict.SRC_UNKNOWN) == park_verdict.WHY_ODO_SOURCE_UNNAMED,
   "`why_unmeasured` отдаёт слова ИЗ `WHYS` и молчит у измеренного")
ok(all(park_verdict.why_unmeasured(s) in ("",) + park_verdict.WHYS for s in park_verdict.SOURCES),
   "четвёртого слова причины не заведено")
_pv_imports = set()
for _n in ast.walk(ast.parse(inspect.getsource(park_verdict))):
    if isinstance(_n, ast.Import):
        _pv_imports.update(a.name.split(".")[0] for a in _n.names)
    elif isinstance(_n, ast.ImportFrom):
        _pv_imports.add((_n.module or "").split(".")[0])
ok(_pv_imports == {"fleet_cell", "scan_result"},
   "судья по-прежнему импортирует РОВНО два вокабуляра и ничего о карточке не знает: %s"
   % sorted(_pv_imports))


print("\n(6) ЖИВАЯ СБОРКА БЕРЁТ ЧИСЛО НАЗВАННЫМ (прогон, а не греп)")


class BRnoOdo:
    """Мост-фикстура: своего одометра у байка НЕТ вовсе — ровно 29 байков парка из 38."""

    def _call(self, a, **k):
        return {"ok": False}

    def read_doc(self, *a, **k):
        return {"ok": False}

    def find_bike(self, b):
        return {"name": BIKE, "status": "дома", "oil_last_km": 12212, "gear_last_km": 12212,
                "abs_last_km": 0, "airfilter_last_km": 0, "mileage": 0}

    def service_list(self):
        return {"items": []}

    def read_events(self, b, limit=6):
        return {"items": []}

    def service_pending_get(self, c, t, b):
        return {"ok": False, "error": "not_found"}

    def service_pending_list(self, *a, **k):
        return {"ok": False, "error": "not_found"}


card_live = S._build_bike_card_body(BRnoOdo(), -1, 1, BIKE)
ok(card_live.count("✅") == 0,
   "сборка на мосте БЕЗ своего одометра: %d галочек (нужно 0)" % card_live.count("✅"))
ok("не измерено" in card_live
   and park_verdict.WHY_ODO_SUBSTITUTED in card_live,
   "и причина в живой сборке — именно «пробег подставлен»")
src_body = inspect.getsource(S._build_bike_card_body)
ok("_odo_current_src(" in src_body and "cur_km_source=cur_km_source" in src_body,
   "сборка зовёт ПРАВИЛО и пробрасывает слово дальше")

print("\n(7) ТАЙСКАЯ ПОЛОВИНА БЕЗ КИРИЛЛИЦЫ (то же ловит живой аудитор исходящего)")
for name, card in (("подстановка", sub), ("свой одометр", own),
                   ("просрочка-граница", over_sub), ("источник не назван", unnamed),
                   ("живая сборка", card_live)):
    blk = th_block(card)
    ok(blk != "" and not re.search(r"[А-яЁё]", blk),
       "в 🇹🇭-блоке нет кириллицы (%s)" % name)

print("\n(8) РЕГРЕСС СУДЬИ: `register` на тех же входах отвечает как отвечал")
import fleet_cell                                                      # noqa: E402
ROW = {"cells": {"oil_last_km": {"state": fleet_cell.STATE_VALUE, "raw": "12212", "num": 12212}}}
cell = fleet_cell.read(ROW, "oil_last_km")
r_sub = park_verdict.register("oil_last_km", cell, 12212, 4000, park_verdict.SRC_FALLBACK)
r_own = park_verdict.register("oil_last_km", cell, 12212, 4000, park_verdict.SRC_OWN)
r_over = park_verdict.register("oil_last_km", cell, 20000, 4000, park_verdict.SRC_FALLBACK)
ok(r_sub["outcome"] == park_verdict.UNKNOWN
   and r_sub["why"] == park_verdict.WHY_ODO_SUBSTITUTED
   and r_sub["remaining_km_upper_bound"] == 4000,
   "подстановка → НЕИЗВЕСТНО «пробег подставлен», верхняя граница 4000")
ok(r_own["outcome"] == park_verdict.IN_NORM and r_own["remaining_km"] == 4000,
   "свой одометр → в норме, остаток 4000")
ok(r_over["outcome"] == park_verdict.OVERDUE and r_over["overdue_km"] == 3788
   and r_over["overdue_km_is_lower_bound"] is True,
   "просрочка на подстановке → просрочено 3788, объявлено нижней границей")

print("\nИТОГ:", "ВСЕ PASS" if all(res)
      else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
