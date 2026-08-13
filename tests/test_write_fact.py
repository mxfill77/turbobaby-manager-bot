"""СИНК ЗЕРКАЛА ПО ПЕРЕЧИТАННОМУ ФАКТУ, А НЕ ПО ФЛАГУ РАСПИСКИ (13.08.2026).

Голдены — ДОСЛОВНЫЕ живые случаи 13.08 (splinter.log):
    05:19:07  written=[] failed=[('abs','receipt_unknown')] odo=37015   → байк 4957
    05:21:41  written=[] failed=[('abs','receipt_unknown')] odo=20747   → байк 4724
Величины ОБЕ стоят в Лист1 (перечитано живым мостом 13.08: кол.K, исход `ok`), а строк зеркала
«обслуживание» нет — их погасил флаг `r.get("ok")`.

Разметка клеток в фикстурах снята с ЖИВОГО моста тем же днём (форма `cellState_`, включая
настоящую пустую клетку `airfilter_last_km`) — правило «фикстура снимается с прода».

Что доказывается:
    (1) ТРИГГЕР      перечитываем после молчания транспорта, НЕ после успеха и НЕ после
                     отказа, вынесенного самим мостом;
    (2) ТРИ ИСХОДА   легло / не легло / НЕИЗВЕСТНО, и «неизвестно» НИКОГДА не считается
                     записанным (замок против ложного зелёного);
    (3) РУКИ         любая дырка в фактах на стороне рук → «неизвестно», а не «легло»;
    (4) СКВОЗНОЕ     на дословных 37015 и 20747 синк ИДЁТ, а при чужой величине — нет;
    (5) ЦЕНА         здоровый путь не платит НИ ОДНОГО лишнего обращения к мосту (счётчик);
    (6) ЧИСТОТА      у решения ровно один импорт и ни одной руки (ast).
"""
import ast
import asyncio
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import fleet_cell
import splinter as S
import write_fact

CHAT = -1002751134848
TOPIC = 308

# ── ДОСЛОВНЫЕ строки парка (снято с живого моста 13.08, `fleet(cells=1)`) ──────────────────
BIKE_4957 = "NMAX 155CC GREEN-B PHUKET 4957"
BIKE_4724 = "XMAX 300CC NEW BLUE-3 PHUKET 4724"

ROW_4957 = {
    "name": BIKE_4957,
    "cells": {
        "abs_last_km": {"state": "value", "num": 37015, "raw": "37015"},
        "airfilter_last_km": {"state": "empty", "raw": ""},
    },
}
ROW_4724 = {
    "name": BIKE_4724,
    "cells": {
        "oil_last_km": {"state": "value", "num": 20316, "raw": "20316"},
        "abs_last_km": {"state": "value", "num": 20747, "raw": "20747"},
        "airfilter_last_km": {"state": "empty", "raw": ""},
    },
}

REFUSAL = {"ok": False, "error": "receipt_unknown", "outcome": "unknown",
           "message": "write-POST «set_fleet_service»: расписка пришла отказом по токену"}


def _cell(row, field):
    return fleet_cell.read(row, field)


def run(c):
    return asyncio.run(c)


def reset():
    S._SVC_WRITE_DEDUP.clear()


class FakeBridge:
    """Мост-фикстура. Считает ВСЕ обращения — на этом стоит проверка цены."""

    def __init__(self, write_result=None, rows=None, fleet_result=None):
        self.write_result = write_result if write_result is not None else {"ok": True}
        self.rows = rows if rows is not None else [ROW_4957, ROW_4724]
        self.fleet_result = fleet_result
        self.oil_calls, self.svc_calls, self.upserts, self.events = [], [], [], []
        self.fleet_calls = 0
        self.closed = False

    def set_fleet_oil(self, number, oil_km, confirmed=False):
        self.oil_calls.append((number, oil_km, confirmed))
        return self.write_result

    def set_fleet_service(self, number, kind, km, confirmed=False):
        self.svc_calls.append((number, kind, km, confirmed))
        return self.write_result

    def service_upsert(self, **kw):
        self.upserts.append(kw)
        return {"ok": True, "next_km": 41015, "status": "ok"}

    def add_event(self, **kw):
        self.events.append(kw)
        return {"ok": True}

    def service_pending_close(self, **kw):
        self.closed = True
        return {"ok": True}

    def find_bike(self, q):
        return {"name": q}

    def fleet(self, cells=False):
        self.fleet_calls += 1
        if self.fleet_result is not None:
            return self.fleet_result
        return {"ok": True, "data": {"bikes": self.rows}}

    @staticmethod
    def cell(bike, field):
        return fleet_cell.read(bike, field)


# ═══════════════ (1) ТРИГГЕР: КОГДА ВООБЩЕ ПЕРЕЧИТЫВАТЬ ═══════════════

def test_trigger_success_never_verifies():
    assert write_fact.needs_verify({"ok": True}) is False, \
        "успех перечитывать нечего — здоровый путь не платит"


def test_trigger_receipt_refusal_verifies():
    assert write_fact.needs_verify(REFUSAL) is True, "дословный отказ расписки → перечитать"
    assert write_fact.needs_verify({"ok": False, "outcome": "unknown"}) is True
    assert write_fact.needs_verify({"ok": False, "error": "receipt_unknown"}) is True


def test_trigger_settled_refusals_do_not_verify():
    """Мост ВЫНЕС отказ сам — исход определён, читать нечего (форма `_claim_task_verified`)."""
    for err in ("not_confirmed", "oil_decreasing", "km_decreasing", "not_found", "ambiguous",
                "write_failed", "bad_oil_km", "bad_kind", "missing_number", "card_deadline",
                "fix_incomplete", "oil_drop_needs_trusted", "audit_failed"):
        assert write_fact.needs_verify({"ok": False, "error": err}) is False, \
            f"{err} — отказ самого моста, перечитывание тут лишнее"


def test_trigger_transport_silence_verifies():
    """Молчание транспорта — тот же неизвестный исход, что и отказ расписки."""
    for err in ("timeout", "request_failed", "невиданный_код", "", None):
        assert write_fact.needs_verify({"ok": False, "error": err}) is True, \
            f"{err!r}: исход не определён — направление сомнения в перечитывание"
    assert write_fact.needs_verify(None) is True, "ответ не словарь → судить не по чему"


# ═══════════════ (2) ТРИ ИСХОДА РЕШЕНИЯ ═══════════════

def test_verdict_landed_on_live_rows():
    """Дословные живые случаи: величина СТОИТ в клетке → легло."""
    f = write_fact.verdict(37015, _cell(ROW_4957, "abs_last_km"))
    assert f.state == write_fact.STATE_LANDED and f.landed is True
    assert "СТОИТ" in f.say() and "37015" in f.say()

    f = write_fact.verdict(20747, _cell(ROW_4724, "abs_last_km"))
    assert f.landed is True, "20747 стоит в кол.K байка 4724 — синк обязан пойти"


def test_verdict_absent_when_other_number():
    """В клетке ДРУГОЕ число: нашей величины там нет → синка нет, и это звучит с обоими числами."""
    f = write_fact.verdict(37016, _cell(ROW_4957, "abs_last_km"))
    assert f.state == write_fact.STATE_ABSENT and f.landed is False
    assert "37016" in f.say() and "37015" in f.say(), f"фраза обязана назвать оба числа: {f.say()}"


def test_verdict_absent_when_cell_empty():
    """Живая пустая клетка (airfilter у обоих байков): величины нет вовсе."""
    f = write_fact.verdict(20747, _cell(ROW_4724, "airfilter_last_km"))
    assert f.state == write_fact.STATE_ABSENT and f.landed is False
    assert "пуст" in f.say()


def test_verdict_unknown_when_cell_not_a_number():
    """Содержимое есть, числом не стало → сравнивать не с чем → НЕИЗВЕСТНО, не «не легло»."""
    row = {"name": BIKE_4957, "cells": {"abs_last_km": {"state": "text", "raw": "—"}}}
    f = write_fact.verdict(37015, _cell(row, "abs_last_km"))
    assert f.state == write_fact.STATE_UNKNOWN and f.landed is False


def test_verdict_unknown_when_no_markup():
    """Старый деплой моста разметки не шлёт → «источник не прочитан», а не «пусто»."""
    f = write_fact.verdict(37015, _cell({"name": BIKE_4957}, "abs_last_km"))
    assert f.state == write_fact.STATE_UNKNOWN and f.landed is False
    assert "НЕ УДАЛОСЬ" in f.say() and "НЕИЗВЕСТЕН" in f.say()


def test_verdict_unknown_on_broken_inputs():
    assert write_fact.verdict("не число", _cell(ROW_4957, "abs_last_km")).state \
        == write_fact.STATE_UNKNOWN
    assert write_fact.verdict(37015, None).state == write_fact.STATE_UNKNOWN
    assert write_fact.verdict(37015, "не контракт").state == write_fact.STATE_UNKNOWN


def test_verdict_lock_only_equality_is_landed():
    """ЗАМОК: `landed` истинно РОВНО у одного исхода — доказанного равенства."""
    landed = [s for s in (write_fact.STATE_LANDED, write_fact.STATE_ABSENT,
                          write_fact.STATE_UNKNOWN)
              if write_fact.Fact(s, 1).landed]
    assert landed == [write_fact.STATE_LANDED], f"записанным считается лишнее: {landed}"
    assert write_fact.unknown(37015, "мост молчит").landed is False


def test_verdict_true_is_not_a_number():
    """Логическое числом не считается ни с одной стороны — иначе `True` стало бы километром."""
    row = {"name": BIKE_4957, "cells": {"abs_last_km": {"state": "value", "num": True,
                                                       "raw": "TRUE"}}}
    assert write_fact.verdict(1, _cell(row, "abs_last_km")).landed is False


# ═══════════════ (3) РУКИ: ЛЮБАЯ ДЫРКА В ФАКТАХ → НЕИЗВЕСТНО ═══════════════

def test_hands_landed_on_live_row():
    b = FakeBridge()
    f = S._sp_fact_after_write(b, BIKE_4957, "4957", "abs", 37015)
    assert f.landed is True and b.fleet_calls == 1


def test_hands_unknown_when_bridge_silent():
    f = S._sp_fact_after_write(FakeBridge(fleet_result={"ok": False, "error": "timeout"}),
                               BIKE_4957, "4957", "abs", 37015)
    assert f.state == write_fact.STATE_UNKNOWN and f.landed is False


def test_hands_unknown_when_fleet_raises():
    class Boom(FakeBridge):
        def fleet(self, cells=False):
            raise RuntimeError("мост упал")

    f = S._sp_fact_after_write(Boom(), BIKE_4957, "4957", "abs", 37015)
    assert f.state == write_fact.STATE_UNKNOWN, "падение чтения — не повод счесть записанным"


def test_hands_unknown_when_row_not_found_or_ambiguous():
    f = S._sp_fact_after_write(FakeBridge(rows=[ROW_4724]), BIKE_4957, "4957", "abs", 37015)
    assert f.state == write_fact.STATE_UNKNOWN, "строки парка нет — судить не на чем"

    twins = [dict(ROW_4957), dict(ROW_4957)]
    f = S._sp_fact_after_write(FakeBridge(rows=twins), BIKE_4957, "4957", "abs", 37015)
    assert f.state == write_fact.STATE_UNKNOWN, "номер неоднозначен — судить не на чем"


def test_hands_unknown_for_kind_without_column():
    f = S._sp_fact_after_write(FakeBridge(), BIKE_4957, "4957", "pads", 37015)
    assert f.state == write_fact.STATE_UNKNOWN, "колодки в колонке Лист1 не живут"


def test_hands_unknown_when_plate_not_parsed():
    b = FakeBridge()
    f = S._sp_fact_after_write(b, "байк без номера", "", "abs", 37015)
    assert f.state == write_fact.STATE_UNKNOWN and b.fleet_calls == 0, \
        "номера нет → к мосту не ходим вовсе"


# ═══════════════ (4) СКВОЗНОЕ: ДОСЛОВНЫЕ ЖИВЫЕ СЛУЧАИ 13.08 ═══════════════

def test_end_to_end_4957_mirror_now_syncs():
    """Живой случай 05:19:07: расписки нет, 37015 стоит в Лист1 → строка зеркала едет."""
    reset()
    b = FakeBridge(write_result=REFUSAL, rows=[ROW_4957])
    written, failed = run(S._sp_write_done(None, b, CHAT, TOPIC, BIKE_4957, ["abs"], "37015",
                                           confirmed_by="@Pleummmm"))
    assert len(b.upserts) == 1, f"синк зеркала обязан пойти по факту, upserts={b.upserts}"
    assert b.upserts[0]["last_service_km"] == 37015 and b.upserts[0]["service_type"] == "abs"
    assert written == ["abs"] and failed == [], f"written={written} failed={failed}"


def test_end_to_end_4724_mirror_now_syncs():
    """Живой случай 05:21:41: то же на 20747."""
    reset()
    b = FakeBridge(write_result=REFUSAL, rows=[ROW_4724])
    written, failed = run(S._sp_write_done(None, b, CHAT, TOPIC, BIKE_4724, ["abs"], "20747",
                                           confirmed_by="@Pleummmm"))
    assert len(b.upserts) == 1 and written == ["abs"] and failed == []


def test_end_to_end_absent_keeps_mirror_silent():
    """Расписки нет И величины в клетке нет → синка НЕТ, и исход назван словом."""
    reset()
    b = FakeBridge(write_result=REFUSAL, rows=[ROW_4957])
    written, failed = run(S._sp_write_done(None, b, CHAT, TOPIC, BIKE_4957, ["abs"], "37999",
                                           confirmed_by="@Pleummmm"))
    assert b.upserts == [], "нашей величины в Лист1 нет — зеркалу ехать не с чем"
    assert written == [] and failed == [("abs", "receipt_unknown/absent")], \
        f"исход обязан звучать: failed={failed}"


def test_end_to_end_unknown_is_not_written():
    """ЗАМОК: перечитать не удалось → НЕ записано, и в отчёте стоит «unknown», а не «absent»."""
    reset()
    b = FakeBridge(write_result=REFUSAL, fleet_result={"ok": False, "error": "timeout"})
    written, failed = run(S._sp_write_done(None, b, CHAT, TOPIC, BIKE_4957, ["abs"], "37015",
                                           confirmed_by="@Pleummmm"))
    assert b.upserts == [] and written == []
    assert failed == [("abs", "receipt_unknown/unknown")], f"failed={failed}"


def test_end_to_end_settled_refusal_unchanged():
    """Отказ, вынесенный мостом: путь БАЙТ-В-БАЙТ прежний — ни чтения, ни синка, код как был."""
    reset()
    b = FakeBridge(write_result={"ok": False, "error": "oil_decreasing"}, rows=[ROW_4724])
    written, failed = run(S._sp_write_done(None, b, CHAT, TOPIC, BIKE_4724, ["oil"], "20316",
                                           confirmed_by="@Pleummmm"))
    assert b.fleet_calls == 0, "на определённом отказе перечитывать нечего"
    assert b.upserts == [] and written == [] and failed == [("oil", "oil_decreasing")]


# ═══════════════ (5) ЦЕНА: ЗДОРОВЫЙ ПУТЬ НЕ ПЛАТИТ НИЧЕГО ═══════════════

def test_price_healthy_path_pays_nothing():
    """Расписка пришла → ноль лишних обращений к больному мосту. Счётчиком, а не обещанием."""
    reset()
    b = FakeBridge(rows=[ROW_4724])
    written, failed = run(S._sp_write_done(None, b, CHAT, TOPIC, BIKE_4724, ["oil", "abs"],
                                           "20747", confirmed_by="@Pleummmm"))
    assert b.fleet_calls == 0, f"здоровый путь сходил к мосту лишний раз: {b.fleet_calls}"
    assert len(b.upserts) == 2 and written == ["oil", "abs"] and failed == []


def test_price_one_reread_per_failed_kind():
    """Перечитывание идёт РОВНО раз на неудачный вид, а не на каждую запись."""
    reset()
    b = FakeBridge(write_result=REFUSAL, rows=[ROW_4724])
    run(S._sp_write_done(None, b, CHAT, TOPIC, BIKE_4724, ["oil", "abs"], "20747",
                         confirmed_by="@Pleummmm"))
    assert b.fleet_calls == 2, f"два неудачных вида — два чтения, поймали {b.fleet_calls}"


# ═══════════════ (6) ЧИСТОТА РЕШЕНИЯ (ast, а не докстринг) ═══════════════

def test_purity_one_import_no_hands():
    with open("/root/turbobaby-manager-bot/write_fact.py", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("open", "exec", "eval", "compile", "__import__"), \
                f"у решения появились руки: {node.func.id} (строка {node.lineno})"
    assert imports == {"scan_result"}, f"импорт обязан быть ровно один: {sorted(imports)}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} проверок: синк зеркала по перечитанному факту")
