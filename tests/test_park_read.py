# -*- coding: utf-8 -*-
"""ЧИТАТЕЛЬ ПАРКА — секрет не виден вызывающему, исход не врёт нормой.

ЧТО СТЕРЕЖЁТ (ослабить — покраснеть):
  1. ТОЛЬКО ЧТЕНИЕ, И ЭТО ПЕРЕЧЕНЬ, А НЕ ОБЕЩАНИЕ. Все обращения к мосту идут через одну дверь
     `_Gate`; она их записывает и пропускает ровно `ALLOWED_ACTIONS`. Проверяется трижды:
     в списке нет ни одного имени пишущего действия моста; полный прогон зовёт только
     разрешённое; незнакомое действие БРОСАЕТ, а не проходит «на всякий случай».
  2. СЕКРЕТ НЕ ВЫХОДИТ НАРУЖУ НИ ОДНОЙ ВЕТКОЙ — ни успехом, ни отказом. Главный голден здесь
     отрицательный: читателю подаются заведомо неверные креды, он падает, и в тексте отказа
     значения нет. Это не теория: транспортный отказ клиента возвращает `str(e)` requests-
     исключения (`bridge_client.py:532`), а оно несёт URL целиком — то есть без замазывания
     секрет утекал бы в обычном, а не экзотическом случае.
  3. ТРИ СЛОВА ИСХОДА И НИ ОДНОГО ЧЕТВЁРТОГО, причём «в норме» возвращается РОВНО одним путём.
  4. «ПУСТО» ОТЛИЧАЕТСЯ ОТ «НЕ ПРОЧИТАНО» — числом, а не интонацией: у первого причина о
     ЛИСТЕ, у второго о НАС, и чинятся они разным.
  5. НОЛЬ И ОТРИЦАТЕЛЬНОЕ — НЕИЗВЕСТНО, А НЕ ПРОСРОЧКА. Это прямой антифантом переписи
     docs/artifacts/2026-08-08-park-overdue-35-of-38-census.md (12 ложных просрочек из 35).
  6. ВОЗРАСТ ПЕРЕД СОДЕРЖИМЫМ: первый ключ ответа — время снятия, и отдельной строкой сказано,
     что у клеток листа штампа нет вовсе.

СЕТИ В ТЕСТАХ НЕТ. Мост — фикстура; единственный подпроцесс (голден 2) ходит на 127.0.0.1:9,
где соединение отвергается сразу: наружу не уходит ничего, а ветка отказа при этом настоящая.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PRETOOL_NOPUSH"] = "1"

import park_read        # noqa: E402
import park_verdict     # noqa: E402
import scan_result      # noqa: E402

PY = os.path.join(ROOT, "venv", "bin", "python3")

# Заведомо неверные креды для отрицательного голдена. Это НЕ секрет: значения выдуманы здесь.
# Форма выбрана так, чтобы `env_out.specific` их узнавал (длинная цепочка, смешанный алфавит) —
# иначе голден «значение замазано» доказывал бы не то.
FAKE_TOKEN = "zzFAKEtoken1234567890abcdefQQ"
FAKE_URL = "http://127.0.0.1:9/macros/s/zzFAKEdeploy0987654321wwww/exec"


# ── ФИКСТУРА МОСТА ────────────────────────────────────────────────────────────────────────────
def _cell(state, raw, num=None):
    c = {"state": state, "raw": raw}
    if num is not None:
        c["num"] = num
    return c


def _row(name, oil, gear, abs_, air):
    """Строка парка с разметкой клеток. Каждый аргумент — готовая клетка."""
    row = {"name": name}
    for field, cell in zip(park_verdict.REGISTERS, (oil, gear, abs_, air)):
        row[field] = cell.get("num", 0)
        row.setdefault("cells", {})[field] = cell
    return row


VALUE = lambda n: _cell("value", str(n), n)          # noqa: E731
EMPTY = _cell("empty", "")
TEXT = _cell("text", "—")
ZERO = _cell("value", "0", 0)


def _sr(field, cell):
    """Клетка → ScanResult ЖИВЫМ контрактом `fleet_cell.read`, а не пересказом его формы.

    Решение судит исход клетки, и подсунуть ему словарь вместо исхода значило бы проверять
    не ту ветку (мок, переставший задевать ветку, хуже отсутствующего)."""
    import fleet_cell
    return fleet_cell.read({"cells": {field: cell}}, field)


def _park():
    """Пять байков, каждый про свою ветку исхода."""
    return [
        _row("NMAX 155 GREY 5960", VALUE(40000), VALUE(40000), VALUE(38000), VALUE(30000)),
        _row("NMAX 155 BLUE 1111", EMPTY, VALUE(40000), VALUE(38000), VALUE(30000)),
        _row("NMAX 155 RED 2222", TEXT, VALUE(40000), VALUE(38000), VALUE(30000)),
        _row("NMAX 155 BLACK 3333", ZERO, VALUE(40000), VALUE(38000), VALUE(30000)),
        _row("NMAX 155 GREEN 4444", VALUE(10000), VALUE(40000), VALUE(38000), VALUE(30000)),
    ]


_KB = """книга знаний
```SERVICE_INTERVALS
{"oil": {"scooter": 4000, "moto": 5000}, "gear": {"scooter": 4000, "moto": null},
 "abs": 10000, "airfilter": 20000, "scooter_keywords": ["nmax"], "moto_default": 5000}
```
"""


class FakeBridge:
    """Мост-фикстура ЖИВОЙ ФОРМЫ: две двери наружу, сходящиеся в `_durable_request`.

    Форма не украшение. У боевого клиента `fleet` идёт GET'ом через `_call`
    (`bridge_client.py:683`), а `service_list` — POST'ом через `_post`
    (`bridge_client.py:1169`), и пишущие действия все до одного POST'овые. Фикстура с одной
    дверью показывала бы забор полным там, где он закрывает половину: ровно так первая
    редакция и прошла тесты, а живой прогон не досчитался `service_list` в перечне."""

    def __init__(self, rows=None, svc=None, boom=None):
        self.rows = _park() if rows is None else rows
        self.svc = svc if svc is not None else [
            {"bike": b["name"], "current_km": 41000, "updated_at": "2026-09-19T10:00:00Z"}
            for b in (_park() if rows is None else rows)
        ]
        self.boom = boom

    # ── единственный узел, мимо которого наружу не уходит ничего ──
    def _durable_request(self, method, action, params=None, body=None, retry_full=False):
        if self.boom:
            raise RuntimeError(self.boom)
        params = params or {}
        if action == "fleet":
            rows = [dict(r) for r in self.rows]
            if not params.get("cells"):
                for r in rows:
                    r.pop("cells", None)
            return {"ok": True, "data": {"bikes": rows}}
        if action == "service_list":
            return {"ok": True, "items": list(self.svc)}
        if action == "read_doc":
            return {"ok": True, "text": _KB}
        raise AssertionError(f"фикстура не знает действия {action}")

    # ── дверь GET (как `_call` боевого клиента) ──
    def _call(self, action, **params):
        return self._durable_request("GET", action, params={"action": action, **params})

    # ── дверь POST (как `_post`; ею ходят ВСЕ пишущие действия) ──
    def _post(self, action, **fields):
        return self._durable_request("POST", action, body={"action": action, **fields})

    def fleet(self, cells=False):
        return self._call("fleet", cells=1) if cells else self._call("fleet")

    def service_list(self):
        return self._post("service_list")


def _fresh_intervals():
    """Сбросить часовой кэш интервалов, чтобы read_doc в прогоне ДЕЙСТВИТЕЛЬНО звался."""
    import splinter
    splinter._SVC_INTERVALS_CACHE["data"] = None
    splinter._SVC_INTERVALS_CACHE["ts"] = 0


def _run(query="весь парк", cells=True, rows=None, svc=None):
    _fresh_intervals()
    bridge = FakeBridge(rows=rows, svc=svc)
    gate = park_read._Gate(bridge)
    return park_read.read_park(bridge, gate, query, cells=cells), gate


def _reg(bike, kind):
    for r in bike["registers"]:
        if r["kind"] == kind:
            return r
    raise AssertionError(f"регистра {kind} нет в ответе")


def _by_name(out, needle):
    for b in out["bikes"]:
        if needle in b["bike"]:
            return b
    raise AssertionError(f"байка {needle} нет в ответе")


# ── (1) ТОЛЬКО ЧТЕНИЕ ─────────────────────────────────────────────────────────────────────────
def test_allowed_actions_contain_no_write_action():
    """В списке разрешённого нет ни одного имени ПИШУЩЕГО действия моста."""
    writes = {
        "set_fleet_oil", "set_fleet_service", "service_undo", "service_upsert",
        "service_set_pin", "service_delete", "service_pending_upsert",
        "service_pending_close", "add_transaction", "void_last", "edit_event",
        "delete_event", "add_event", "create_booking", "activate_booking",
        "close_booking", "closing_upsert", "write_doc", "enqueue_task", "claim_task",
        "complete_task", "set_needs_approval", "set_caps", "toggle_cap", "balance_set",
    }
    bad = sorted(park_read.ALLOWED_ACTIONS & writes)
    assert not bad, f"пишущее действие попало в разрешённые: {bad}"
    assert park_read.ALLOWED_ACTIONS == frozenset(("fleet", "service_list", "read_doc")), \
        f"список разрешённого изменился: {sorted(park_read.ALLOWED_ACTIONS)}"


def test_full_run_calls_only_read_actions():
    """Полный прогон: перечень вызванных действий ⊆ разрешённых, и он не пуст."""
    out, gate = _run()
    assert gate.called, "дверь не записала ни одного действия — перечень доказывать нечем"
    assert gate.all_read_only(), f"вызвано незнакомое действие: {gate.actions}"
    assert set(gate.actions) <= park_read.ALLOWED_ACTIONS, gate.actions
    assert out["all_read_only"] is True
    assert set(out["actions_called"]) == {"fleet", "service_list", "read_doc"}, \
        f"ожидались все три читающих действия, вызваны: {out['actions_called']}"


def test_gate_refuses_unknown_action():
    """Незнакомое действие БРОСАЕТ, а не проходит: fail-closed."""
    bridge = FakeBridge()
    park_read._Gate(bridge)
    try:
        bridge._call("set_fleet_oil", number="5960", oil_km=1)
    except park_read.Refused as e:
        assert "set_fleet_oil" in str(e)
        assert "не разрешено" in str(e)
    else:
        raise AssertionError("пишущее действие прошло через дверь читателя")


def test_gate_closes_the_POST_door_too():
    """ГЛАВНЫЙ ЗАМОК ЗАБОРА: пишущие действия ходят POST'ом, и он закрыт тем же перехватом.

    Забор на одном `_call` пропустил бы их все, выглядя при этом полным."""
    for action in ("set_fleet_oil", "write_doc", "add_transaction", "complete_task"):
        bridge = FakeBridge()
        gate = park_read._Gate(bridge)
        try:
            bridge._post(action, confirmed=True)
        except park_read.Refused as e:
            assert action in str(e) and "POST" in str(e), e
        else:
            raise AssertionError(f"пишущее действие {action} прошло POST'ом мимо забора")
        assert action in gate.called, "отказанное POST-действие не попало в перечень"


def test_read_only_post_action_is_recorded_in_the_list():
    """`service_list` — POST по устройству; в перечне он обязан БЫТЬ."""
    out, gate = _run()
    assert "service_list" in gate.called, \
        "POST-действие не попало в перечень — забор стоит не на том узле"
    assert "service_list" in out["actions_called"], out["actions_called"]


def test_gate_records_even_the_refused_action():
    """Отказанное действие всё равно попадает в перечень: молча не исчезает ничего."""
    bridge = FakeBridge()
    gate = park_read._Gate(bridge)
    try:
        bridge._call("write_doc", name="master")
    except park_read.Refused:
        pass
    assert "write_doc" in gate.called
    assert gate.all_read_only() is False


# ── (2) СЕКРЕТ НЕ ВЫХОДИТ НАРУЖУ ──────────────────────────────────────────────────────────────
def test_scrub_hides_specific_value():
    """Специфичное значение переменной замазывается — правило берётся у env_out."""
    env = {"BRIDGE_TOKEN": FAKE_TOKEN}
    text = f"сбой при обращении: token={FAKE_TOKEN} конец"
    out = park_read._scrub(text, env)
    assert FAKE_TOKEN not in out, "секрет уцелел в замазанном тексте"
    assert park_read.HIDDEN in out, "замазывание не оставило следа"
    assert "сбой при обращении" in out, "замазывание съело посторонний текст"


def test_scrub_hides_url_carried_by_transport_error():
    """Живой случай: str(requests-исключения) несёт URL целиком."""
    env = {"BRIDGE_URL": FAKE_URL, "BRIDGE_TOKEN": FAKE_TOKEN}
    text = (f"HTTPSConnectionPool: Max retries exceeded with url: {FAKE_URL} "
            f"(Caused by NewConnectionError)")
    out = park_read._scrub(text, env)
    assert FAKE_URL not in out, "URL уцелел в тексте отказа"
    assert "Max retries exceeded" in out, "полезная часть диагноза пропала"


def test_scrub_leaves_short_values_alone():
    """Короткое значение не замазывается: иначе оно съело бы куски чужого текста."""
    env = {"BRIDGE_TOKEN": "ab"}
    out = park_read._scrub("таблица байков", env)
    assert out == "таблица байков", f"короткое значение испортило текст: {out!r}"


def test_no_secret_in_output_of_broken_run_subprocess():
    """ГЛАВНЫЙ ОТРИЦАТЕЛЬНЫЙ ГОЛДЕН: неверные креды → отказ, и секрета в нём НЕТ.

    Наружу из проверки не уходит ничего: 127.0.0.1:9 отвергает соединение сразу."""
    env = dict(os.environ)
    env.update({
        "BRIDGE_URL": FAKE_URL,
        "BRIDGE_TOKEN": FAKE_TOKEN,
        "BRIDGE_RETRY_ATTEMPTS": "1",
        "BRIDGE_WEDGE_LIMIT": "1",
        "PRETOOL_NOPUSH": "1",
    })
    p = subprocess.run([PY, os.path.join(ROOT, "park_read.py"), "весь парк"],
                       capture_output=True, text=True, env=env, timeout=180, cwd=ROOT)
    blob = (p.stdout or "") + (p.stderr or "")
    assert blob.strip(), "читатель не сказал вообще ничего"
    for what, needle in (("ТОКЕН", FAKE_TOKEN), ("URL", FAKE_URL),
                         ("кусок URL", "zzFAKEdeploy0987654321wwww")):
        assert needle not in blob, (
            f"{what} УТЁК в вывод читателя. Где именно (значение вырезано): "
            f"...{blob[max(0, blob.index(needle) - 160):blob.index(needle)]}"
            f"⟪ЗДЕСЬ БЫЛ СЕКРЕТ⟫"
            f"{blob[blob.index(needle) + len(needle):blob.index(needle) + len(needle) + 80]}...")
    # Наружу идёт только ПРИЗНАК: что-то сказано, и это разбираемый JSON.
    assert p.stdout.strip().startswith("{"), f"вывод не машинный: {p.stdout[:200]!r}"
    said = json.loads(p.stdout)
    assert said.get("ok") is False, "сломанный прогон притворился удачным"
    assert said.get("message"), "отказ без причины"


def test_secret_absent_from_healthy_output():
    """Удачный прогон тоже не несёт значений окружения."""
    out, _ = _run()
    blob = json.dumps(out, ensure_ascii=False)
    for name in park_read._SECRET_NAMES:
        v = os.environ.get(name) or ""
        if len(v) >= park_read._MIN_MASKABLE:
            assert v not in blob, f"значение {name} попало в удачный ответ"


def test_env_values_are_not_listed_anywhere():
    """Наружу идёт признак «пусто/непусто», а не значение."""
    env = {"BRIDGE_TOKEN": FAKE_TOKEN, "BRIDGE_URL": FAKE_URL}
    names = park_read._mask_names(env)
    assert len(names) == 2, "по имени замазываются не обе переменные"
    # Сам тест о значениях не заявляет ничего, кроме признака непустоты.
    assert all(bool(v) for v in names)


# ── (3) ТРИ СЛОВА ИСХОДА ──────────────────────────────────────────────────────────────────────
def test_only_three_outcome_words_exist():
    out, _ = _run()
    words = {b["outcome"] for b in out["bikes"]}
    for b in out["bikes"]:
        words |= {r["outcome"] for r in b["registers"]}
    assert words <= set(park_verdict.OUTCOMES), f"появилось четвёртое слово: {words}"


def test_norm_is_reached_by_exactly_one_path():
    """«в норме» — только когда клетка разобрана, интервал есть, пробег есть и вычитание вышло."""
    out, _ = _run()
    good = _by_name(out, "5960")
    assert good["outcome"] == park_verdict.IN_NORM, good
    oil = _reg(good, "oil")
    assert oil["last_km"] == 40000 and oil["interval"] == 4000
    assert oil["due_at_km"] == 44000
    assert oil["remaining_km"] == 3000, oil
    assert oil["overdue_km"] is None


def test_overdue_is_counted_not_guessed():
    out, _ = _run()
    late = _by_name(out, "4444")
    assert late["outcome"] == park_verdict.OVERDUE, late
    oil = _reg(late, "oil")
    assert oil["overdue_km"] == 27000, oil      # 41000 - (10000 + 4000)
    assert oil["remaining_km"] is None


def test_answer_carries_four_registers_and_the_mileage():
    out, _ = _run()
    for b in out["bikes"]:
        kinds = [r["kind"] for r in b["registers"]]
        assert kinds == ["oil", "gear", "abs", "airfilter"], kinds
        assert b["current_km"] == 41000, b


# ── (4) «ПУСТО» ≠ «НЕ ПРОЧИТАНО» ──────────────────────────────────────────────────────────────
def test_empty_cell_is_unknown_because_of_the_sheet():
    out, _ = _run()
    oil = _reg(_by_name(out, "1111"), "oil")
    assert oil["outcome"] == park_verdict.UNKNOWN
    assert oil["why"] == park_verdict.WHY_EMPTY, oil


def test_unread_source_is_unknown_because_of_us():
    """Мост без разметки — это «не прочитано», и НЕ «пусто»."""
    out, _ = _run(cells=False)
    oil = _reg(_by_name(out, "5960"), "oil")
    assert oil["outcome"] == park_verdict.UNKNOWN
    assert oil["why"] == park_verdict.WHY_UNREAD, oil


def test_two_unknowns_are_counted_separately():
    """ЧИСЛОМ: причины НЕИЗВЕСТНОГО лежат в разных корзинах, а не в одной."""
    with_cells, _ = _run(cells=True)
    without, _ = _run(cells=False)

    a = with_cells["summary"]["unknown_registers_by_why"]
    b = without["summary"]["unknown_registers_by_why"]

    assert a.get(park_verdict.WHY_EMPTY) == 1, a
    assert a.get(park_verdict.WHY_UNREAD, 0) == 0, a

    n_bikes = len(without["bikes"])
    assert b.get(park_verdict.WHY_UNREAD) == 4 * n_bikes, b
    assert b.get(park_verdict.WHY_EMPTY, 0) == 0, b


def test_unread_run_has_no_norm_at_all():
    """Непрочитанный источник не даёт «в норме» НИ ОДНОМУ байку — это и есть замок."""
    out, _ = _run(cells=False)
    by = out["summary"]["by_outcome"]
    assert by[park_verdict.IN_NORM] == 0, by
    assert by[park_verdict.OVERDUE] == 0, by
    assert by[park_verdict.UNKNOWN] == len(out["bikes"]), by


# ── (5) НОЛЬ И ОТРИЦАТЕЛЬНОЕ — НЕ ПРОСРОЧКА ───────────────────────────────────────────────────
def test_zero_cell_is_unknown_not_overdue():
    """Антифантом переписи 08.08: ноль значит «замены не было», а не «просрочено на 41 тыс»."""
    out, _ = _run()
    oil = _reg(_by_name(out, "3333"), "oil")
    assert oil["outcome"] == park_verdict.UNKNOWN, oil
    assert oil["why"] == park_verdict.WHY_ZERO, oil
    assert oil["overdue_km"] is None, "ноль превратился в просрочку — вернулся фантом"


def test_negative_cell_is_unknown():
    """Живой случай abs_last_km = −5000 (байк 8969): пробег назад не идёт."""
    cell = _sr("abs_last_km", _cell("value", "-5000", -5000))
    v = park_verdict.register("abs_last_km", cell, 41000, 10000)
    assert v["outcome"] == park_verdict.UNKNOWN and v["why"] == park_verdict.WHY_NEGATIVE, v


def test_not_a_scan_result_is_unread_not_norm():
    """Подали не исход, а сырой словарь → НЕИЗВЕСТНО «не прочитано», а не тихая норма."""
    v = park_verdict.register("oil_last_km", {"state": "value", "num": 40000}, 41000, 4000)
    assert v["outcome"] == park_verdict.UNKNOWN and v["why"] == park_verdict.WHY_UNREAD, v


def test_text_cell_is_unknown_and_named_so():
    out, _ = _run()
    oil = _reg(_by_name(out, "2222"), "oil")
    assert oil["outcome"] == park_verdict.UNKNOWN
    assert oil["why"] == park_verdict.WHY_TEXT, oil


def test_missing_interval_is_unknown_not_norm():
    v = park_verdict.register("gear_last_km", _sr("gear_last_km", VALUE(40000)), 41000, None)
    assert v["outcome"] == park_verdict.UNKNOWN and v["why"] == park_verdict.WHY_NO_INTERVAL, v


def test_missing_mileage_is_unknown_not_norm():
    v = park_verdict.register("oil_last_km", _sr("oil_last_km", VALUE(40000)), "", 4000)
    assert v["outcome"] == park_verdict.UNKNOWN and v["why"] == park_verdict.WHY_NO_ODO, v


def test_register_absent_from_row_is_unread():
    b = park_verdict.bike("X", {}, 41000, {"oil": 4000})
    assert b["outcome"] == park_verdict.UNKNOWN
    assert all(r["why"] == park_verdict.WHY_UNREAD for r in b["registers"]), b


def test_loudest_order_is_overdue_then_unknown_then_norm():
    L = park_verdict.loudest
    assert L([park_verdict.IN_NORM, park_verdict.UNKNOWN]) == park_verdict.UNKNOWN
    assert L([park_verdict.UNKNOWN, park_verdict.OVERDUE]) == park_verdict.OVERDUE
    assert L([park_verdict.IN_NORM]) == park_verdict.IN_NORM
    assert L([]) == park_verdict.UNKNOWN, "пустой набор обязан быть НЕИЗВЕСТНО"


# ── (6) ВОЗРАСТ ПЕРЕД СОДЕРЖИМЫМ ──────────────────────────────────────────────────────────────
def test_age_comes_before_content():
    out, _ = _run()
    keys = list(out.keys())
    assert keys[0] == "snapshot_utc", f"ответ начинается не со времени снятия: {keys[:3]}"
    assert keys.index("snapshot_utc") < keys.index("bikes")
    assert out["snapshot_utc"].endswith("Z") and len(out["snapshot_utc"]) == 20, out["snapshot_utc"]


def test_absence_of_cell_timestamp_is_said_in_words():
    out, _ = _run()
    said = out["registers_have_no_timestamp"]
    assert "штампа" in said and "НЕТ ВОВСЕ" in said, said
    assert "I/J/K/L" in said, "не сказано, о каких именно клетках речь"


def test_own_odometer_stamp_is_named_separately():
    """У своего одометра штамп ЕСТЬ — разница с клетками не должна пропасть."""
    out, _ = _run()
    b = _by_name(out, "5960")
    assert b["odometer_confirmed_utc"] == "2026-09-19T10:00:00Z", b
    assert "штамп ЕСТЬ" in out["odometer_timestamp_note"]


def test_odometer_without_stamp_says_so():
    rows = _park()
    svc = [{"bike": rows[0]["name"], "current_km": 41000}]
    out, _ = _run(rows=rows, svc=svc)
    b = _by_name(out, "5960")
    assert "штампа нет" in b["odometer_confirmed_utc"], b


# ── (7) ОБЛАСТЬ ЗАПРОСА ───────────────────────────────────────────────────────────────────────
def test_whole_park_reads_every_row():
    out, _ = _run("весь парк")
    assert out["whole_park"] is True
    assert out["summary"]["bikes_seen"] == out["rows_in_park"] == 5, out["summary"]


def test_single_bike_is_matched_by_plate():
    out, _ = _run("5960")
    assert out["whole_park"] is False
    assert out["summary"]["bikes_seen"] == 1, out["summary"]
    assert "5960" in out["bikes"][0]["bike"]


def test_dead_bridge_is_unread_not_empty_park():
    """Мост не бросает, а ВОЗВРАЩАЕТ ok:false. «Ноль байков» тут был бы ложью."""
    class Dead(FakeBridge):
        def _durable_request(self, method, action, params=None, body=None, retry_full=False):
            return {"ok": False, "error": "request_failed", "message": "мост молчит"}

    _fresh_intervals()
    bridge = Dead()
    gate = park_read._Gate(bridge)
    try:
        park_read.read_park(bridge, gate, "весь парк")
    except park_read.Unread as e:
        assert "НЕ ПРОЧИТАН" in str(e), e
        assert "ноль байков" in str(e), "не сказано, чем это НЕ является"
    else:
        raise AssertionError("мёртвый мост выдан за пустой парк")


def test_unread_service_list_is_named_not_swallowed():
    """Свой одометр не прочитан — не фатально, но названо вслух."""
    class NoOdo(FakeBridge):
        def _durable_request(self, method, action, params=None, body=None, retry_full=False):
            if action == "service_list":
                return {"ok": False, "error": "timeout"}
            return FakeBridge._durable_request(self, method, action, params, body, retry_full)

    _fresh_intervals()
    bridge = NoOdo()
    gate = park_read._Gate(bridge)
    out = park_read.read_park(bridge, gate, "весь парк")
    assert "НЕ ПРОЧИТАН" in out["service_list_problem"], out["service_list_problem"]
    assert out["summary"]["bikes_seen"] == 5, "парк-то прочитан — знаменатель на месте"


def test_url_path_segment_is_masked_too():
    """Текст отказа несёт ПУТЬ, а не весь URL: замазывание обязано узнать и его."""
    env = {"BRIDGE_URL": FAKE_URL}
    text = "Max retries exceeded with url: /macros/s/zzFAKEdeploy0987654321wwww/exec?action=fleet"
    out = park_read._scrub(text, env)
    assert "zzFAKEdeploy0987654321wwww" not in out, out
    assert "Max retries exceeded" in out


def test_unknown_bike_yields_empty_not_crash():
    out, _ = _run("9999")
    assert out["summary"]["bikes_seen"] == 0
    assert out["rows_in_park"] == 5, "парк всё равно прочитан — знаменатель на месте"


# ── (8) ЧИСТОТА РЕШЕНИЯ ───────────────────────────────────────────────────────────────────────
def test_park_verdict_is_pure():
    import invariants_check as ic
    run = ic.CheckRun("PARK_VERDICT_PURE")
    ic.check_park_verdict_pure({}, run)
    assert not run.findings, f"решение обзавелось руками: {run.findings}"


def test_park_verdict_imports_are_exactly_two_vocabularies():
    import ast
    with open(os.path.join(ROOT, "park_verdict.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods == {"fleet_cell", "scan_result"}, f"импорты решения изменились: {sorted(mods)}"


def test_outcomes_vocabulary_is_taken_ready():
    """Словари берутся ГОТОВЫМИ: регистры — у контракта клетки, исходы чтения — у scan_result."""
    import fleet_cell
    assert park_verdict.REGISTERS is fleet_cell.SERVICE_FIELDS, \
        "список регистров переписан своими словами — два словаря об одном"
    src = open(os.path.join(ROOT, "park_verdict.py"), encoding="utf-8").read()
    for name in ("OUTCOME_UNREADABLE", "OUTCOME_EMPTY", "OUTCOME_OK"):
        assert f"scan_result.{name}" in src, f"исход {name} не взят у scan_result"
    assert '"unreadable"' not in src and '"empty"' not in src, \
        "исход клетки продублирован литералом вместо вокабуляра"


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
    if fails:
        print("\nКРАСНЫХ:", len(fails))
        sys.exit(1)
    print("\nВСЕ ТЕСТЫ park_read ПРОШЛИ (только чтение + секрет не течёт + три слова исхода + "
          "«пусто» ≠ «не прочитано» + возраст перед содержимым)")
