"""КОНТРАКТ ЧИТАТЕЛЯ ЖИВОГО ТЕКСТА + первый переведённый читатель (08.08.2026).

ЖИВОЙ ФАКТ, с которого снят регресс (не выдуманный). Перепись
`docs/artifacts/2026-08-08-zero-on-parse-miss-census.md` §2 канал 16 называет самое дорогое место
класса дословно: `splinter._o3_overdue_scan` при падении `fleet()` возвращал `{"overdue": []}`, а
`devbot._g_overdue` на пустом списке печатал владельцу «🔧 Просрочек ТО нет 👍». Упавший мост и
здоровый парк из 38 байков выглядели для владельца ОДИНАКОВО.

ЧТО ЗАКРЕПЛЕНО:
  · наверх идёт ПАРА «осмотрено / разобрано» и ИСХОД; нуль без знаменателя не отдаётся;
  · «осмотрено > 0, разобрано 0» — ТРЕТИЙ исход (`mismatch`), он произносится вслух;
  · «источник не прочитан» — это НЕ «осмотрено 0»: измерения не было вовсе (`scanned=None`);
  · владельцу на недоступном источнике говорится «ПРОВЕРИТЬ НЕ УДАЛОСЬ», а не «просрочек нет 👍»;
  · сам список просрочек на здоровом парке считается тем же порядком «худшие сверху» (перевод
    контракта читателя расчёт не трогал; ЧТО считать просрочкой, изменено позже и отдельно —
    10.08.2026, три состояния клетки, регресс `tests/test_overdue_cells.py`);
  · доска нарядов на несостоявшемся скане НЕ синкается: иначе «✅ решено» встало бы на каждую
    висящую карточку — просрочки исчезли бы с доски, не перестав существовать.

ЖИВОЙ ФОРМАТ (класс row705→1268): парк-фикстура — ТА ЖЕ, что в `tests/test_o3.py` (живые имена,
`current_km` строкой из листа), ответы моста — той же формы, что отдаёт `bridge_client.fleet()`.
Недоступность источника моделируется ТОЛЬКО здесь, мокнутым мостом: живой мост не трогается,
сети нет, Telegram нет, боевых файлов состояния нет.

Проверки:
 (1) ЧЕТЫРЕ ИСХОДА по паре чисел; «осмотрено 0» ≠ «источник не прочитан»;
 (2) ТРЕТИЙ ИСХОД произносится вслух и несёт оба числа;
 (3) ПРОТИВОРЕЧИЕ в счётчиках → громкий исход, а не ok (fail-closed);
 (4) ПЕРЕВЕДЁННЫЙ ЧИТАТЕЛЬ: пять форм недоступности источника → unreadable/empty/mismatch;
 (5) ЗДОРОВЫЙ ПАРК: исход ok, список просрочек БАЙТ-В-БАЙТ прежний (регресс расчёта);
 (6) ВЛАДЕЛЕЦ: «было» (нуль как здоровье) → «стало» (проверить не удалось + знаменатель);
 (7) ДОСКА НАРЯДОВ: несостоявшийся скан → синк отменён, ни одного обращения к Telegram;
 (8) ЧИСТОТА контракта: у модуля НОЛЬ импортов (ast) — ему нечем ни читать, ни писать, ни звать.
"""
import os, sys, ast, asyncio

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _HERE)
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import scan_result as SR
import splinter as S
import devbot as DB

SC = SR.ScanResult

# --- Парк-фикстура: ТА ЖЕ, что в tests/test_o3.py (живые имена и формат листа) ---------------
# РАЗМЕТКА КЛЕТОК (контракт `fleet_cell`, мост @79 от 10.08.2026): скан зовёт `fleet(cells=True)`,
# и мок обязан повторять живой формат — иначе он моделирует несуществующий мост. 0 в плоском поле
# означал «замену не делали», то есть ПУСТУЮ клетку; ABS у NMAX поднят до значения 5000, чтобы
# парк остался просроченным ПО-НАСТОЯЩЕМУ (предмет этого файла — исход прохода, а не толкование
# клетки; толкование закреплено в tests/test_overdue_cells.py).
_CELL_FIELDS = ("mileage", "oil_last_km", "gear_last_km", "abs_last_km", "airfilter_last_km")


def cells(row):
    mk = {}
    for f in _CELL_FIELDS:
        v = row.get(f) or 0
        if isinstance(v, str):              # живая строка одометра «35200 Km, 05.07.2026» — не число
            mk[f] = {"state": "text", "raw": v}
        elif v:
            mk[f] = {"state": "value", "num": v, "raw": str(v)}
        else:
            mk[f] = {"state": "empty", "raw": ""}
    return dict(row, cells=mk)


def fleet_resp(rows, cells_wanted):
    return {"data": {"bikes": [cells(r) if cells_wanted else dict(r) for r in rows]}}


_BIKES = [
    {"name": "NMAX 155CC PHUKET 4255", "status": "ДОМА", "mileage": 3000,
     "oil_last_km": 24000, "gear_last_km": 27000, "abs_last_km": 5000, "airfilter_last_km": 5000},
    {"name": "NINJA 400CC PHUKET 6334", "status": "ДОМА", "mileage": 40000,
     "oil_last_km": 38000, "gear_last_km": 0, "abs_last_km": 25000, "airfilter_last_km": 10000},
    {"name": "PCX 160CC PHUKET 1111", "status": "ДОМА", "mileage": 5000,
     "oil_last_km": 4000, "gear_last_km": 4000, "abs_last_km": 0, "airfilter_last_km": 0},
]


class BR:                                   # здоровый мост, здоровый парк
    def _call(s, a, **k): return {"ok": False}
    def fleet(s, cells=False): return fleet_resp(_BIKES, cells)
    def service_list(s): return {"items": [
        {"bike": "NMAX 155CC PHUKET 4255", "current_km": 30000},
    ]}


class BR_RAISE(BR):                         # мост упал (исключение) — как в проде при таймауте
    def fleet(s, cells=False): raise RuntimeError("Bridge timeout")


class BR_NOTOK(BR):                         # мост ответил ОТКАЗОМ, без исключения
    def fleet(s, cells=False): return {"ok": False, "error": "unauthorized"}


class BR_NOKEY(BR):                         # ответ есть, списка байков в нём нет (сменилась форма)
    def fleet(s, cells=False): return {"ok": True, "data": {}}


class BR_EMPTY(BR):                         # список есть и он пуст
    def fleet(s, cells=False): return {"data": {"bikes": []}}


# ЖИВАЯ форма промаха шаблона, а не выдуманная: колонка одометра в проде держит СТРОКУ
# «35200 Km, 05.07.2026» (класс row705→1268, разведка CRM 23:04 — записан в CLAUDE.md). Через
# `int(str(x).replace(" ","").replace(",",""))` она не проходит → None у КАЖДОГО поля пробега.
_LIVE_ODO_STRING = "35200 Km, 05.07.2026"


class BR_ODO_DEAD(BR):
    """Парк на месте, а ТЕКУЩИЙ ПРОБЕГ не разбирается НИ У ОДНОГО байка — это и есть третий исход.
    Прежний код отдал бы отсюда пустой список просрочек, и владелец прочитал бы «нет 👍»."""
    def fleet(s, cells=False):
        dead = {f"{k}_last_km": _LIVE_ODO_STRING
                for k in ("oil", "gear", "abs", "airfilter")}
        return fleet_resp([dict(b, mileage=_LIVE_ODO_STRING, **dead) for b in _BIKES], cells)
    def service_list(s): return {"items": [
        {"bike": b["name"], "current_km": _LIVE_ODO_STRING} for b in _BIKES
    ]}


# === (1) четыре исхода по паре чисел =========================================================
print("(1) четыре исхода по паре чисел:")
res.append(ok(SC(38, 38).outcome == SR.OUTCOME_OK, "осмотрено 38, разобрано 38 → ok"))
res.append(ok(SC(38, 30).outcome == SR.OUTCOME_OK, "осмотрено 38, разобрано 30 → ok (часть)"))
res.append(ok(SC(0, 0).outcome == SR.OUTCOME_EMPTY, "осмотрено 0 → empty (источник пуст)"))
res.append(ok(SC(38, 0).outcome == SR.OUTCOME_MISMATCH,
              "осмотрено 38, разобрано 0 → mismatch (ТРЕТИЙ исход)"))
res.append(ok(SC.unreadable("байков").outcome == SR.OUTCOME_UNREADABLE,
              "источник не прочитан → unreadable"))
res.append(ok(SC.unreadable("байков").scanned is None and SC(0, 0).scanned == 0,
              "«не прочитан» (scanned=None) и «пусто» (scanned=0) — РАЗНЫЕ состояния, не оба нуль"))
res.append(ok(SC.unreadable("байков").outcome != SC(0, 0).outcome,
              "и исход у них разный — измерения нет vs измерение дало нуль"))
res.append(ok(SC(38, 38).ok and not SC(38, 0).ok and not SC(0, 0).ok
              and not SC.unreadable("б").ok,
              "«.ok» истинно ТОЛЬКО у ok: только там нуль находок значит «находок нет»"))
res.append(ok(SC(38, 30).missed == 8 and SC.unreadable("б").missed is None,
              "«не разобрано» = 8; при непрочитанном источнике — None, а не 0"))

# === (2) третий исход произносится вслух =====================================================
print("(2) третий исход произносится вслух:")
say3 = SC(38, 0, subject="байков").say()
res.append(ok("38" in say3 and "разобрано 0" in say3 and "шаблон разошёлся с источником" in say3,
              f"mismatch несёт ОБА числа и своё имя: «{say3}»"))
res.append(ok("0" in SC(0, 0, subject="байков").say() and "пуст" in SC(0, 0, subject="байков").say(),
              f"empty называет знаменатель: «{SC(0, 0, subject='байков').say()}»"))
res.append(ok("не удалось" in SC.unreadable("байков", detail="fleet() упал").say(),
              f"unreadable говорит «не удалось»: «{SC.unreadable('байков', detail='fleet() упал').say()}»"))
res.append(ok("38" in SC(38, 38, subject="байков").say(),
              "даже успех несёт знаменатель — нуль находок без него не отдаётся"))
res.append(ok("не разобрано 8" in SC(38, 30, subject="байков").say(),
              "частичный разбор называет остаток вслух, а не молчит о нём"))

# === (3) противоречие в счётчиках → громкий исход =============================================
print("(3) противоречие в счётчиках → громкий исход (fail-closed):")
res.append(ok(SC(5, 9).outcome == SR.OUTCOME_MISMATCH and bool(SC(5, 9).contradiction),
              "разобрано больше осмотренного → mismatch, а не ok"))
bad = SC(None, 7)
res.append(ok(bad.outcome == SR.OUTCOME_UNREADABLE and bad.parsed == 0 and bool(bad.contradiction),
              "«источник не прочитан, но разобрано 7» → unreadable, разобрано обнулено"))
res.append(ok(SC(-3, 0).outcome == SR.OUTCOME_UNREADABLE, "отрицательное «осмотрено» → unreadable"))
res.append(ok(SC(5, -1).outcome != SR.OUTCOME_OK, "отрицательное «разобрано» → не ok"))
res.append(ok(SC("38", 0).outcome != SR.OUTCOME_OK, "строка вместо числа → не ok"))
res.append(ok(SC(True, 1).outcome != SR.OUTCOME_OK, "bool вместо числа → не ok (isinstance-ловушка)"))

# === (4) переведённый читатель: формы недоступности источника =================================
print("(4) переведённый читатель — недоступность источника:")
r_raise = S._o3_overdue_scan(BR_RAISE())
res.append(ok(r_raise.outcome == SR.OUTCOME_UNREADABLE and not r_raise.ok,
              "fleet() бросил исключение → unreadable (было: {'overdue': []})"))
res.append(ok("Bridge timeout" in r_raise.say(), f"причина названа: «{r_raise.say()}»"))
r_notok = S._o3_overdue_scan(BR_NOTOK())
res.append(ok(r_notok.outcome == SR.OUTCOME_UNREADABLE and "unauthorized" in r_notok.say(),
              "мост ответил отказом БЕЗ исключения → unreadable (эта форма прежде шла в нуль молча)"))
r_nokey = S._o3_overdue_scan(BR_NOKEY())
res.append(ok(r_nokey.outcome == SR.OUTCOME_UNREADABLE,
              "ответ без списка байков → unreadable, а не «парк пуст»"))
r_empty = S._o3_overdue_scan(BR_EMPTY())
res.append(ok(r_empty.outcome == SR.OUTCOME_EMPTY and r_empty.scanned == 0,
              "список есть и пуст → empty (осмотрено 0, знаменатель назван)"))
r_dead = S._o3_overdue_scan(BR_ODO_DEAD())
res.append(ok(r_dead.outcome == SR.OUTCOME_MISMATCH and r_dead.scanned == 3 and r_dead.parsed == 0,
              f"пробег не разобрался ни у одного из 3 → ТРЕТИЙ исход: {r_dead.say()}"))
res.append(ok(not r_dead.ok and ((r_dead.payload or {}).get("overdue") or []) == [],
              "у третьего исхода находок нет — но это «не искали», и «.ok» об этом говорит"))

# === (5) здоровый парк: расчёт БАЙТ-В-БАЙТ прежний ============================================
print("(5) здоровый парк — исход ok, список просрочек прежний:")
good = S._o3_overdue_scan(BR())
ov = (good.payload or {}).get("overdue") or []
res.append(ok(good.outcome == SR.OUTCOME_OK and good.scanned == 3 and good.parsed == 3,
              f"осмотрено 3, разобрано 3 → ok ({good.say()})"))
res.append(ok(len(ov) == 2, f"2 байка с просрочками (NMAX+NINJA), PCX нет — {len(ov)}"))
res.append(ok(not any("PCX" in o["bike"] for o in ov),
              "PCX: abs/air НЕ ИЗМЕРЕНЫ (клетки пусты) → в просрочки не идёт (класс 10.08.2026)"))
nm = [o for o in ov if "NMAX" in o["bike"]][0]
res.append(ok(nm["current_km"] == 30000, "NMAX текущий = max(colH, service_list) = 30000"))
res.append(ok(ov[0] is nm and nm["items"][0]["kind"] == "abs"
              and nm["items"][0]["last"] == 5000 and nm["items"][0]["over_km"] == 15000,
              "NMAX первый: ABS просрочен ПО ЗНАЧЕНИЮ, порядок «худшие сверху» прежний"))
res.append(ok([it["kind"] for it in nm["items"]] == ["abs", "airfilter", "oil"],
              "NMAX: abs>airfilter>oil по over_km — сортировка прежняя"))
ninja = [o for o in ov if "NINJA" in o["bike"]][0]
res.append(ok([it["kind"] for it in ninja["items"]] == ["airfilter", "abs"]
              and "gear" not in [it["kind"] for it in ninja["items"]],
              "NINJA: airfilter+abs, gear пропущен (interval None) — прежнее поведение"))


class BR_ONE_BAD(BR):
    """Один байк ломает разбор (строка вместо словаря) — остальные обязаны доехать."""
    def fleet(s, cells=False):
        rows = fleet_resp([_BIKES[0], _BIKES[1]], cells)["data"]["bikes"]
        return {"data": {"bikes": [rows[0], "мусор из листа", rows[1]]}}


r_one = S._o3_overdue_scan(BR_ONE_BAD())
res.append(ok(r_one.scanned == 3 and r_one.parsed == 2 and r_one.outcome == SR.OUTCOME_OK,
              f"битая строка: осмотрено 3, разобрано 2 — скан не падает целиком ({r_one.say()})"))
res.append(ok(len((r_one.payload or {}).get("overdue") or []) == 2,
              "просрочки уцелевших байков посчитаны"))

# === (6) владелец: было → стало ===============================================================
print("(6) владелец — «было» (нуль как здоровье) → «стало»:")
BYLO = "🔧 Просрочек ТО нет 👍"
for name, br in (("мост упал", BR_RAISE()), ("мост отказал", BR_NOTOK()),
                 ("нет списка байков", BR_NOKEY()), ("парк пуст", BR_EMPTY()),
                 ("пробег не разобрался", BR_ODO_DEAD())):
    out = DB._g_overdue(br)
    res.append(ok(out != BYLO and "ПРОВЕРИТЬ НЕ УДАЛОСЬ" in out,
                  f"«{name}» → владельцу «проверить не удалось», а не «{BYLO}»"))
res.append(ok("осмотрено" in DB._g_overdue(BR_ODO_DEAD()),
              "и с числом осмотренного: " + DB._g_overdue(BR_ODO_DEAD()).splitlines()[0]))
res.append(ok("не искали" in DB._g_overdue(BR_RAISE()),
              "владельцу сказано прямо: нуль тут означал бы «не искали»"))
out_good = DB._g_overdue(BR())
res.append(ok("просрочено 2 байков" in out_good and "4255 NMAX 155CC PHUKET" in out_good,
              "здоровый парк: список на месте, байк назван"))
res.append(ok("осмотрено 3 байков" in out_good,
              f"…и со знаменателем: {out_good.splitlines()[0]}"))
# С 10.08.2026 «❗не делалось» из ПРОСРОЧЕК ушло вместе со своим источником: неизмеренная клетка
# больше не выдаётся за просроченную, она называется отдельным числом (tests/test_overdue_cells.py).
res.append(ok("+" in out_good and "❗не делалось" not in out_good
              and "не измерено" in out_good,
              "«+N км» на месте, «не делалось» из просрочек ушло, «не измерено» названо отдельно"))


class BR_CLEAN(BR):
    """Парк здоров и просрочек ПРАВДА нет: это единственный случай, где «нет 👍» законно."""
    def fleet(s, cells=False): return fleet_resp([
        {"name": "PCX 160CC PHUKET 1111", "status": "ДОМА", "mileage": 100,
         "oil_last_km": 90, "gear_last_km": 90, "abs_last_km": 90, "airfilter_last_km": 90}], cells)
    def service_list(s): return {"items": []}


clean = DB._g_overdue(BR_CLEAN())
res.append(ok("просрочек по ЗНАЧЕНИЮ нет" in clean and "осмотрено 1" in clean
              and "просрочено 0" in clean,
              f"настоящий нуль остаётся нулём, но СО ЗНАМЕНАТЕЛЕМ: «{clean}»"))
res.append(ok("не измерено 0 клеток" in clean,
              "и рядом честный нуль второго числа: мерить было что, и всё измерено"))

# === (7) доска нарядов: несостоявшийся скан → синк отменён ====================================
print("(7) доска нарядов — на несостоявшемся скане не синкается:")


class DeadContext:
    """Любое обращение к Telegram здесь = провал теста: отмена обязана случиться ДО постинга."""
    def __getattr__(s, name):
        raise AssertionError(f"board тронул Telegram ({name}) при несостоявшемся скане")


try:
    stats = asyncio.new_event_loop().run_until_complete(
        S._o3_board_sync(DeadContext(), BR_RAISE(), allow_post_header=True))
    res.append(ok(isinstance(stats, dict) and stats.get("scan_failed") is True,
                  "скан не состоялся → синк отменён, стата помечена scan_failed"))
    res.append(ok("не удалось" in str(stats.get("scan_said", "")),
                  f"причина доехала до вызывающего: {stats.get('scan_said')}"))
    res.append(ok(stats.get("gone") == 0 and stats.get("new") == 0,
                  "ни одна карточка не помечена «решено» и ни одна не отправлена"))
except AssertionError as e:
    res.append(ok(False, str(e)))
except Exception as e:
    res.append(ok(False, f"board упал вместо честной отмены: {type(e).__name__}: {e}"))

# === (8) чистота контракта (ast) ==============================================================
print("(8) чистота контракта — у модуля НОЛЬ импортов:")
with open(os.path.join(_HERE, "scan_result.py"), encoding="utf-8") as f:
    _src = f.read()
_tree = ast.parse(_src)
_imports = [n for n in ast.walk(_tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
res.append(ok(not _imports, f"импортов ноль (найдено {len(_imports)}) — читать/писать/звать нечем"))
_calls = {n.func.id for n in ast.walk(_tree)
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
res.append(ok(not ({"open", "exec", "eval", "compile", "__import__"} & _calls),
              f"голых рук нет: {sorted(_calls)}"))

print(f"\nИТОГ: {sum(res)}/{len(res)}")
sys.exit(0 if all(res) else 1)
