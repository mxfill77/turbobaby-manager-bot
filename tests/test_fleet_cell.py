# -*- coding: utf-8 -*-
"""РАННЕР КОНТРАКТА КЛЕТКИ ЛИСТ1 — три состояния доезжают до питона, а не схлопываются в ноль.

ЧТО СТЕРЕЖЁТ (ослабить — покраснеть):
  1. ТРИ СОСТОЯНИЯ РАЗЛИЧЕНЫ на всём пути: живой ReadFleet.js → JSON моста → `fleet_cell.read`.
     ЗНАЧЕНИЕ → ok, ПУСТО → empty, НЕ-ЧИСЛО → mismatch. Именно неразличимость этих трёх
     (все три приезжали одним `0`) и есть класс, ради которого написан контракт: перепись
     docs/artifacts/2026-08-08-park-overdue-35-of-38-census.md — 12 просрочек из 35 фантомные.
  2. НАСТОЯЩИЙ НОЛЬ ≠ ПУСТАЯ КЛЕТКА. Это главный голден: раньше они были одним числом.
  3. НЕВОЗМОЖНЫЕ значения (−5000 км, ноль там, где ноль невозможен, слово, дата) ТРАНСПОРТ
     не чинит и не прячет: он говорит, ЧТО лежало. Судить данные — работа того, кто считает
     просрочки, и судить он будет ЗНАЯ, пусто там или нет.
  4. ЧЕТВЁРТЫЙ ИСХОД — `unreadable` — там, где разметки нет вовсе (сегодняшний прод: правка
     моста НЕ выложена). Сказать в этом месте `empty` значило бы воспроизвести исходный дефект
     с другой стороны, поэтому «пусто» и «не спросили» разведены голденом.
  5. СОВМЕСТИМОСТЬ: ни один сегодняшний потребитель разметки не просит и не получает —
     проверяется не обещанием в докстринге, а сканом вызовов на ОБЕИХ сторонах моста.
  6. ЧИСТОТА контракта (инвариант FLEET_CELL_PURE): у модуля нет рук, значит «дочитать» клетку
     в обход моста он не может.

ФИКСТУРА ПИТОНА — НЕ ПЕРЕСКАЗ ФОРМАТА: node-харнесс исполняет РЕАЛЬНЫЙ
/root/turbobaby-bridge-gs/ReadFleet.js и печатает рядом с кейсами сам ответ моста с разметкой;
питон кормит этим ответом `fleet_cell.read`. Формат живёт в одном месте — расходиться нечему
(урок «мок, переставший задевать ветку, хуже отсутствующего»).

Ответ БЕЗ разметки (то, что прод отдаёт сегодня) получаем из того же ответа вычитанием ключа
`cells` — это законно ровно потому, что харнесс отдельным кейсом доказывает побайтное равенство
«ответ без параметра == ответ с параметром минус разметка».
"""
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import fleet_cell                                                          # noqa: E402
from scan_result import (OUTCOME_EMPTY, OUTCOME_MISMATCH,                  # noqa: E402
                         OUTCOME_OK, OUTCOME_UNREADABLE)

GS = "/root/turbobaby-bridge-gs/"
HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.join(HERE, "fleet_cells_harness.js")
PROBE_DIR = "/tmp/tb_fleetcell_probe_0809"

_cache = {}


def _harness():
    """Один прогон node-харнесса на весь файл → {'cases': [...], 'fleet': {...}}."""
    if "res" not in _cache:
        p = subprocess.run(["node", HARNESS], capture_output=True, text=True, timeout=90)
        assert p.stdout.strip(), f"харнесс не напечатал JSON:\nstdout={p.stdout}\nstderr={p.stderr}"
        _cache["res"] = json.loads(p.stdout)
        _cache["code"] = p.returncode
        _cache["err"] = p.stderr
    return _cache["res"]


def _bikes():
    """Байки С РАЗМЕТКОЙ — ровно то, что вернул живой ReadFleet.js."""
    bikes = _harness()["fleet"]["bikes"]
    assert len(bikes) == 3, f"ждали 3 байка фикстуры, пришло {len(bikes)}"
    return bikes


def _plain_bikes():
    """Байки БЕЗ разметки — то, что отдаёт задеплоенный сегодня мост."""
    return [{k: v for k, v in b.items() if k != "cells"} for b in _bikes()]


# ─────────────────────────── (1) синтаксис живого моста ───────────────────────────

def test_bridge_js_syntax():
    for f in ("ReadFleet.js", "Bridge.js"):
        p = subprocess.run(["node", "--check", GS + f], capture_output=True, text=True, timeout=30)
        assert p.returncode == 0, f"{f}: {p.stderr}"


# ─────────────────── (2) node-харнесс на РЕАЛЬНОМ коде моста зелёный ───────────────────

def test_harness_green():
    res = _harness()
    failed = [c for c in res["cases"] if not c["pass"]]
    assert not failed, json.dumps(failed, ensure_ascii=False, indent=1)
    assert _cache["code"] == 0, f"харнесс красный: {_cache['err']}"
    names = {c["name"] for c in res["cases"]}
    # РЕГРЕСС, названный в постановке: транспорт добавляет и ничего не заменяет; три состояния
    # различены; невозможные значения доезжают; parseNumber не тронут.
    for need in ("plain.no-cells-key", "plain.identical-to-marked-minus-cells",
                 "marked.has-cells-key", "state.value", "state.empty", "state.text.dash",
                 "state.text.word", "state.empty.spaces", "state.empty.null",
                 "state.empty.undefined", "state.text.date", "three-states.side-by-side",
                 "impossible.negative", "impossible.true-zero", "impossible.zero-as-text",
                 "impossible.zero-vs-empty-differ", "live-text.odometer", "live-text.currency",
                 "live-text.thin-space", "mirror.cellstate-vs-parsenumber",
                 "regress.parsenumber-unchanged", "other-fields.intact", "summary.intact",
                 "dashboard.intact"):
        assert need in names, f"нет кейса {need}: {sorted(names)}"
    # имена кейсов уникальны: два РАЗНЫХ кейса под одним именем прячут провал одного из них
    all_names = [c["name"] for c in res["cases"]]
    assert len(all_names) == len(set(all_names)), \
        f"дубли имён кейсов: {sorted(n for n in all_names if all_names.count(n) > 1)}"


# ─────────────── (3) ТРИ СОСТОЯНИЯ на живой разметке моста (главный предмет) ───────────────

def test_three_states_side_by_side():
    a = _bikes()[0]                       # I=37000, J=пусто, K='-', L='нет данных'
    val = fleet_cell.read(a, "oil_last_km")
    emp = fleet_cell.read(a, "gear_last_km")
    txt = fleet_cell.read(a, "abs_last_km")
    assert val.outcome == OUTCOME_OK and val.payload == 37000, val.say()
    assert emp.outcome == OUTCOME_EMPTY, emp.say()
    assert txt.outcome == OUTCOME_MISMATCH, txt.say()
    assert len({val.outcome, emp.outcome, txt.outcome}) == 3, "три клетки одного байка — три исхода"
    # каждый исход ПРОИЗНОСИТСЯ вслух и со знаменателем (иначе нуль снова остаётся без объяснения)
    assert "разобрано" in val.say() or "осмотрено" in val.say(), val.say()
    assert "осмотрено 0" in emp.say(), emp.say()
    assert "не число" in txt.say() and "-" in txt.say(), txt.say()


def test_text_states_name_what_lies_in_cell():
    a, b = _bikes()[0], _bikes()[1]
    word = fleet_cell.read(a, "airfilter_last_km")
    date = fleet_cell.read(b, "airfilter_last_km")
    assert word.outcome == OUTCOME_MISMATCH and "нет данных" in word.say(), word.say()
    assert date.outcome == OUTCOME_MISMATCH, date.say()
    assert "2026" in date.say(), f"дата в клетке названа сырьём: {date.say()}"


def test_empty_forms_all_read_as_empty():
    b, c = _bikes()[1], _bikes()[2]
    for bike, field, why in ((b, "abs_last_km", "одни пробелы"),
                             (c, "gear_last_km", "null из листа"),
                             (c, "abs_last_km", "undefined из листа")):
        r = fleet_cell.read(bike, field)
        assert r.outcome == OUTCOME_EMPTY, f"{why}: {r.say()}"
        assert r.payload is None, f"{why}: у пустой клетки числа нет вовсе"


# ────────────── (4) НЕВОЗМОЖНЫЕ значения: транспорт не чинит и не прячет ──────────────

def test_true_zero_is_not_empty():
    """ГЛАВНЫЙ ГОЛДЕН КЛАССА: «замену сделали на нулевом пробеге» ≠ «замену не делали никогда»."""
    b, a = _bikes()[1], _bikes()[0]
    zero = fleet_cell.read(b, "oil_last_km")       # в клетке настоящий 0
    empty = fleet_cell.read(a, "gear_last_km")     # клетка пуста
    assert zero.outcome == OUTCOME_OK, zero.say()
    assert zero.payload == 0, f"настоящий ноль обязан доехать значением: {zero.say()}"
    assert empty.outcome == OUTCOME_EMPTY, empty.say()
    assert zero.outcome != empty.outcome, "ноль и пусто снова слиплись — класс вернулся"


def test_negative_mileage_arrives_as_value():
    """−5000 км не бывает, но это суждение о ДАННЫХ; транспорт обязан довезти их как есть."""
    r = fleet_cell.read(_bikes()[1], "gear_last_km")
    assert r.outcome == OUTCOME_OK and r.payload == -5000, r.say()


def test_zero_written_as_text_is_value_too():
    r = fleet_cell.read(_bikes()[2], "airfilter_last_km")     # в клетке строка '0'
    assert r.outcome == OUTCOME_OK and r.payload == 0, r.say()


def test_number_mined_from_live_text_says_so():
    """«35200 Km, 05.07.2026» — живой формат колонки одометра (разведка CRM 08.07)."""
    r = fleet_cell.read(_bikes()[1], "mileage")
    assert r.outcome == OUTCOME_OK and r.payload == 35200, r.say()
    assert "35200 Km, 05.07.2026" in r.detail, f"добытое из текста число названо: {r.detail}"
    plain = fleet_cell.read(_bikes()[0], "oil_last_km")        # клетка = ровно 37000
    assert plain.detail == "", f"у простого числа оговорки нет: {plain.detail!r}"


def test_currency_and_thin_space_forms():
    c = _bikes()[2]
    assert fleet_cell.read(c, "mileage").payload == 12345
    assert fleet_cell.read(c, "oil_last_km").payload == 24094


# ────────── (5) ЧЕТВЁРТЫЙ ИСХОД: разметки нет — говорим «не прочитан», а не «пусто» ──────────

def test_no_markup_is_unreadable_not_empty():
    """Сегодняшний прод (правка моста НЕ выложена) обязан давать unreadable по КАЖДОЙ клетке."""
    for bike in _plain_bikes():
        for field in fleet_cell.SERVICE_FIELDS:
            r = fleet_cell.read(bike, field)
            assert r.outcome == OUTCOME_UNREADABLE, f"{bike.get('name')}/{field}: {r.say()}"
            assert r.scanned is None, "«не спросили» — это отсутствие измерения, а не осмотрено 0"
            assert "источник не прочитан" in r.say(), r.say()
            assert "разметку" in r.detail, r.detail


def test_unreadable_and_empty_are_different_answers():
    plain = fleet_cell.read(_plain_bikes()[0], "gear_last_km")
    marked = fleet_cell.read(_bikes()[0], "gear_last_km")      # та же клетка, но с разметкой
    assert plain.outcome == OUTCOME_UNREADABLE and marked.outcome == OUTCOME_EMPTY, \
        f"«не спросили» и «пусто» обязаны различаться: {plain.say()} / {marked.say()}"


# ─────────────────── (6) кривая разметка — громкий исход, а не тихий ноль ───────────────────

def test_broken_markup_shapes_are_loud():
    good = _bikes()[0]
    checks = [
        (["не словарь"], fleet_cell.read("не словарь", "oil_last_km")),
        (["разметки нет"], fleet_cell.read({"name": "x"}, "oil_last_km")),
        (["cells не словарь"], fleet_cell.read({"cells": []}, "oil_last_km")),
        (["клетки нет в разметке"], fleet_cell.read({"cells": {"mileage": {}}}, "oil_last_km")),
        (["клетка не словарь"], fleet_cell.read({"cells": {"oil_last_km": 5}}, "oil_last_km")),
        (["состояние незнакомо"],
         fleet_cell.read({"cells": {"oil_last_km": {"state": "нечто"}}}, "oil_last_km")),
    ]
    for why, r in checks:
        assert r.outcome == OUTCOME_UNREADABLE, f"{why}: {r.say()}"
        assert r.detail, f"{why}: молчаливый unreadable бесполезен"
    # мост сказал «значение», а числа не дал / дал логическое: содержимое есть, взять нечего
    for num in (None, "37000", True):
        r = fleet_cell.read({"cells": {"oil_last_km": {"state": "value", "num": num,
                                                       "raw": "37000"}}}, "oil_last_km")
        assert r.outcome == OUTCOME_MISMATCH, f"num={num!r}: {r.say()}"
        assert r.payload is None, f"num={num!r}: числа нет — и payload пуст"
    assert fleet_cell.read(good, "oil_last_km").outcome == OUTCOME_OK, "здоровый путь цел"


def test_subject_names_the_column():
    r = fleet_cell.read(_bikes()[0], "oil_last_km")
    assert "кол.I" in r.say(), f"в фразе названа колонка Лист1: {r.say()}"
    assert fleet_cell.FIELD_COL["oil_last_km"] == "I"
    assert fleet_cell.FIELD_COL["gear_last_km"] == "J"
    assert fleet_cell.FIELD_COL["abs_last_km"] == "K"
    assert fleet_cell.FIELD_COL["airfilter_last_km"] == "L"
    assert fleet_cell.FIELD_COL["mileage"] == "H"
    # пробег H — транспорт тот же, но клеткой ТО он не считается (просрочки по I/J/K/L)
    assert "mileage" not in fleet_cell.SERVICE_FIELDS
    assert set(fleet_cell.SERVICE_FIELDS) <= set(fleet_cell.FIELD_COL)


# ─────────────────── (7) провод в bridge_client: просит только тот, кто спросил ───────────────────

def test_bridge_client_wiring():
    import bridge_client
    seen = []

    class Spy(bridge_client.BridgeClient):
        def __init__(self):                       # без сети и без .env
            pass

        def _call(self, action, **params):
            seen.append((action, params))
            return {"ok": True, "data": {"bikes": []}}

    c = Spy()
    c.fleet()
    c.fleet(cells=False)
    assert seen == [("fleet", {}), ("fleet", {})], \
        f"по умолчанию запрос БАЙТ-В-БАЙТ прежний (ни одного лишнего параметра): {seen}"
    seen.clear()
    c.fleet(cells=True)
    assert seen == [("fleet", {"cells": 1})], f"разметку просит только явный cells=True: {seen}"
    # клетку читает тот же контракт, а не своя копия правила
    bike = _bikes()[0]
    assert bridge_client.BridgeClient.cell(bike, "gear_last_km").outcome == OUTCOME_EMPTY


# ─────────────────── (8) СОВМЕСТИМОСТЬ: сегодняшние потребители не тронуты ───────────────────

# Кто СОЗНАТЕЛЬНО просит разметку. Любой новый потребитель обязан появиться здесь ЯВНО, вместе с
# ответом «что он будет делать с unreadable».
#
#   splinter.py — скан просрочек ТО `_o3_overdue_scan` (10.08.2026, мост @79 выложен).
#     ЧТО ДЕЛАЕТ С `unreadable`: НЕ считает просрочкой и НЕ выдаёт за «не измерено» — кладёт
#     клетку в ТРЕТЬЕ число «не удалось проверить», которое печатается владельцу отдельной
#     строкой (доска, дайджест, сводка /o3board). На мосту без разметки скан честно объявит
#     ноль просрочек и ноль «не измерено» при N непроверенных клеток — регресс
#     `tests/test_overdue_cells.py` §4 держит именно эту ветку.
FLEET_CELLS_CONSUMERS = frozenset({"splinter.py"})


def test_python_consumers_ask_no_markup():
    """Все вызовы .fleet() в боевом коде — без аргументов (ответ моста прежний)."""
    bad = []
    for name in sorted(os.listdir(ROOT)):
        if not name.endswith(".py") or name.startswith("_"):
            continue
        with open(os.path.join(ROOT, name), encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
        for m in re.finditer(r"\.fleet\(([^)]*)\)", src):
            arg = m.group(1).strip()
            if arg and name not in FLEET_CELLS_CONSUMERS:
                line = src[:m.start()].count("\n") + 1
                bad.append(f"{name}:{line} → .fleet({arg})")
    assert not bad, ("потребитель просит разметку, не назвавшись: " + "; ".join(bad) +
                     " — впиши его в FLEET_CELLS_CONSUMERS вместе с ответом, что он делает с "
                     "исходом unreadable (сегодня мост эту правку НЕ выложил)")


def test_apps_script_consumers_ask_no_markup():
    """Все вызовы getFleetStatus() в папке моста — без аргументов, кроме роутера Bridge.js."""
    allowed = {"Bridge.js": "params.cells", "ReadFleet.js": "withCells"}
    bad = []
    for name in sorted(os.listdir(GS)):
        if not name.endswith(".js"):
            continue                                     # .bak-снимки не судим: они не исполняются
        with open(os.path.join(GS, name), encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
        for m in re.finditer(r"getFleetStatus\(([^)]*)\)", src):
            arg = m.group(1).strip()
            if arg and arg != allowed.get(name):
                line = src[:m.start()].count("\n") + 1
                bad.append(f"{name}:{line} → getFleetStatus({arg})")
    assert not bad, ("потребитель Apps Script получит лишнюю разметку: " + "; ".join(bad))


def test_markup_is_addition_not_replacement():
    """Поля строки парка прежние: разметка ДОБАВЛЕНА рядом, ничего не заменено."""
    a = _bikes()[0]
    assert a["oil_last_km"] == 37000 and a["gear_last_km"] == 0 and a["abs_last_km"] == 0, \
        "числовые поля остались ровно теми же, включая НУЛИ — потребители их и читают"
    assert set(_plain_bikes()[0]) | {"cells"} == set(a), "разметка — единственный новый ключ"


# ─────────────────── (9) чистота контракта — инвариантом, а не докстрингом ───────────────────

def test_invariant_registered_and_green():
    import invariants_check as ic
    names = [n for n, _ in ic.CHECKS]
    assert "FLEET_CELL_PURE" in names, f"страж не зарегистрирован: {names}"
    run = ic.CheckRun("FLEET_CELL_PURE")
    ic.check_fleet_cell_pure(ic._healthy_world(), run)
    assert not run.findings, f"боевой fleet_cell.py обязан быть чист: {run.findings}"


def test_invariant_catches_hands():
    import invariants_check as ic
    os.makedirs(PROBE_DIR, exist_ok=True)
    probe = os.path.join(PROBE_DIR, "fleet_cell.py")
    old = ic._FLEET_CELL_PATH
    try:
        for src, want in (("from scan_result import ScanResult\n", 0),
                          ("import bridge_client\n", 1),                 # сам сходит за клеткой
                          ("from scan_result import ScanResult\nf = open('/x')\n", 1)):
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write(src)
            ic._FLEET_CELL_PATH = probe
            run = ic.CheckRun("FLEET_CELL_PURE")
            ic.check_fleet_cell_pure(ic._healthy_world(), run)
            assert len(run.findings) == want, f"{src!r}: ждали {want}, поймали {run.findings}"
        ic._FLEET_CELL_PATH = os.path.join(PROBE_DIR, "нет-такого.py")
        run = ic.CheckRun("FLEET_CELL_PURE")
        ic.check_fleet_cell_pure(ic._healthy_world(), run)
        assert len(run.findings) == 1, "файла нет → флаг (fail-closed), а не тишина"
    finally:
        ic._FLEET_CELL_PATH = old


def _cleanup():
    shutil.rmtree(PROBE_DIR, ignore_errors=True)


if __name__ == "__main__":
    fails = []
    for _n, _f in sorted(list(globals().items())):
        if _n.startswith("test_") and callable(_f):
            try:
                _f()
                print("OK:", _n)
            except AssertionError as e:
                fails.append((_n, str(e)))
                print("FAIL:", _n, "\n   ", str(e)[:600])
            except Exception as e:      # noqa: BLE001
                fails.append((_n, repr(e)))
                print("ERROR:", _n, "\n   ", repr(e)[:600])
    _cleanup()
    if fails:
        print("\nКРАСНЫХ:", len(fails))
        sys.exit(1)
    print("\nВСЕ ТЕСТЫ fleet_cell ПРОШЛИ (три состояния клетки + невозможные значения + "
          "совместимость потребителей)")
