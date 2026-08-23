"""СРОК ГОДНОСТИ ПОДТВЕРЖДЁННОГО ПРОБЕГА: бот не спрашивает число, которое уже знает (23.08.2026).

Предмет — две двери, которые просили пробег, судя ТОЛЬКО текущее сообщение:
  A  `_handle_servicing`  «принял работы — пришли пробег» (живой адрес `km_this_msg`);
  B  `handle_service_result` «переспрос одометра» фазы 2 (живой адрес `if not odo:`).

КАЖДЫЙ ОТРИЦАТЕЛЬНЫЙ СЛУЧАЙ ИДЁТ С БЛИЗНЕЦОМ: число свежее — не спрашиваем; ТО ЖЕ САМОЕ, но
число протухло — спрашиваем; ТО ЖЕ САМОЕ, но числа нет вовсе — спрашиваем. Без близнеца «не
спрашивает» неотличимо от «сломалось и молчит».

Сеть/Bridge/claude/_send замоканы, байки выдуманные, в Лист1 не пишется ничего (проверяется).
"""
import asyncio
import datetime
import json
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
# Предмет сьюта — свежесть числа, а НЕ замок повторных подсказок: сценарии гоняют один байк с
# одним состоянием подряд, и живой замок законно счёл бы их повторами. Приём тот же, что в
# tests/test_service_pending.py (CURATOR / PLAN_ADAPT / CARD_DUTY).
os.environ["HINTS_DEDUP"] = "0"
os.environ["ODO_FRESH_MIN"] = "60"      # боевой дефолт ЯВНО: сьют не зависит от .env машины

import splinter as S          # noqa: E402
import odo_fresh              # noqa: E402

CHAT = -1009000000001
TOPIC = 4242
BIKE = "TESTBIKE 999CC BLUE PHUKET 0001"
NOW = 1_756_000_000.0         # фиксированное «сейчас»: за живыми часами не гоняемся


def iso(minutes_ago, now=NOW):
    """ЖИВОЙ формат строки «обслуживание», снятый read-only пробой 23.08.2026: '…T…Z' с мс."""
    t = datetime.datetime.fromtimestamp(now - minutes_ago * 60, datetime.timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


# ============================================================================================
#  (1) ЧИСТАЯ ФУНКЦИЯ: три исхода + выключено
# ============================================================================================
def test_fresh_number_is_used():
    v = odo_fresh.verdict("41641", iso(4.4), NOW, 60)
    assert v["state"] == odo_fresh.STATE_FRESH and v["use"] is True, v
    assert v["km"] == "41641" and 4.0 <= v["age_min"] <= 5.0, v


def test_stale_number_is_asked():
    v = odo_fresh.verdict("41641", iso(956.2), NOW, 60)
    assert v["state"] == odo_fresh.STATE_STALE and v["use"] is False, v
    assert v["km"] == "41641" and v["age_min"] > 900, v
    assert "переспрашиваем" in v["why"], v


def test_no_number_at_all_is_asked():
    for km in ("", None, "—", 0, "0"):
        v = odo_fresh.verdict(km, iso(1), NOW, 60)
        assert v["state"] == odo_fresh.STATE_UNKNOWN and v["use"] is False, (km, v)
        assert v["age_min"] is None, (km, v)


def test_number_without_time_is_unknown_not_fresh():
    # Легаси-строка без updated_at: число есть, возраста нет → спрашиваем (ложное зелёное запрещено)
    v = odo_fresh.verdict("41641", "", NOW, 60)
    assert v["state"] == odo_fresh.STATE_UNKNOWN and v["use"] is False, v
    assert "возраст неизвестен" in v["why"], v


def test_unparseable_time_is_unknown():
    for bad in ("вчера", "2026-13-45T99:99:99Z", "41641"):
        v = odo_fresh.verdict("41641", bad, NOW, 60)
        assert v["use"] is False and v["state"] == odo_fresh.STATE_UNKNOWN, (bad, v)


def test_future_time_beyond_skew_is_unknown_inside_skew_is_fresh():
    v_far = odo_fresh.verdict("41641", iso(-30), NOW, 60)       # на полчаса в будущем
    assert v_far["use"] is False and "в будущем" in v_far["why"], v_far
    v_near = odo_fresh.verdict("41641", iso(-2), NOW, 60)       # дрожание часов листа (≤5 мин)
    assert v_near["use"] is True and v_near["age_min"] == 0.0, v_near


def test_ttl_zero_disables_the_branch():
    v = odo_fresh.verdict("41641", iso(1), NOW, 0)
    assert v["state"] == odo_fresh.STATE_OFF and v["use"] is False, v


def test_threshold_edges():
    assert odo_fresh.verdict("100", iso(59.9), NOW, 60)["use"] is True
    assert odo_fresh.verdict("100", iso(60.0), NOW, 60)["use"] is True      # ровно на пороге — свежее
    assert odo_fresh.verdict("100", iso(60.2), NOW, 60)["use"] is False     # чуть за — спрашиваем


def test_parse_ttl_handles_env_garbage():
    assert odo_fresh.parse_ttl(None) == odo_fresh.TTL_DEFAULT_MIN
    assert odo_fresh.parse_ttl("") == odo_fresh.TTL_DEFAULT_MIN
    assert odo_fresh.parse_ttl("мусор") == odo_fresh.TTL_DEFAULT_MIN
    assert odo_fresh.parse_ttl("0") == 0.0
    assert odo_fresh.parse_ttl("-5") == 0.0
    assert odo_fresh.parse_ttl("90") == 90.0
    assert odo_fresh.parse_ttl("2,5") == 2.5


def test_rule_is_one_way_use_comes_only_from_fresh():
    """Правило умеет СНЯТЬ вопрос и не умеет его РОДИТЬ: `use=True` — ровно из одного исхода."""
    cases = [("41641", iso(1), 60), ("41641", iso(999), 60), ("", iso(1), 60),
             ("41641", "", 60), ("41641", iso(1), 0), ("41641", "кривое", 60),
             ("41641", iso(-30), 60), (None, None, 60)]
    for km, at, ttl in cases:
        v = odo_fresh.verdict(km, at, NOW, ttl)
        assert (v["use"] is True) == (v["state"] == odo_fresh.STATE_FRESH), (km, at, ttl, v)


def test_live_sheet_format_from_probe():
    """Дословная строка живого листа (read-only проба 23.08.2026, ADV 350 372)."""
    now = datetime.datetime(2026, 8, 22, 7, 40, 14, tzinfo=datetime.timezone.utc).timestamp()
    v = odo_fresh.verdict(12212, "2026-08-22T07:10:14.199Z", now, 60)
    assert v["use"] is True and v["age_min"] == 30.0, v
    # то же время без Z (наивное) читаем как UTC, а не как местное — иначе возраст уехал бы на пояс
    v2 = odo_fresh.verdict(12212, "2026-08-22T07:10:14.199", now, 60)
    assert v2["age_min"] == 30.0, v2
    # живой формат числа: пробелы/запятые терпим
    assert odo_fresh.verdict("12 212", "2026-08-22T07:10:14.199Z", now, 60)["km"] == "12212"


# ============================================================================================
#  (2) ПРАВИЛО ВЫБОРА СТРОКИ — ОДНО НА ДВУХ ЧИТАТЕЛЕЙ
# ============================================================================================
ROWS_TWO = [{"bike": BIKE, "service_type": "oil", "current_km": 41641, "updated_at": iso(200)},
            {"bike": BIKE, "service_type": "gear", "current_km": 41700, "updated_at": iso(5)}]


def test_freshest_row_wins_not_the_biggest():
    km, at = S._odo_own_freshest(ROWS_TWO)
    assert km == "41700" and at == iso(5), (km, at)
    # поправка ВНИЗ обязана побеждать прежнее большее число
    down = [{"current_km": 38982, "updated_at": iso(100)}, {"current_km": 36982, "updated_at": iso(3)}]
    assert S._odo_own_freshest(down)[0] == "36982"


def test_legacy_rows_without_time_keep_max_and_give_no_age():
    km, at = S._odo_own_freshest([{"current_km": 100}, {"current_km": 300}])
    assert km == "300" and at == "", (km, at)
    assert odo_fresh.verdict(km, at, NOW, 60)["use"] is False, "без времени — спрашиваем"


def test_odo_current_unchanged_by_the_refactor():
    """Голдены единого источника правды: тот же выбор, что и до выноса правила."""
    assert S._odo_current(None, BIKE, recs=ROWS_TWO) == "41700"
    assert S._odo_current(None, BIKE, recs=[{"current_km": 0, "updated_at": iso(1)}],
                          fleet_row={"oil_last_km": 5000, "gear_last_km": 7000}) == "7000"
    assert S._odo_current(None, BIKE, recs=[], fleet_row={}) == ""


# ============================================================================================
#  ОБЩИЙ СТЕНД ДВЕРЕЙ
# ============================================================================================
class Msg:
    def __init__(self, text, uname="earthmechanic"):
        self.text = text
        self.caption = None
        self.photo = None
        self.chat_id = CHAT
        self.message_thread_id = TOPIC
        self.date = datetime.datetime(2026, 8, 22, 10, 5, tzinfo=datetime.timezone.utc)
        self.message_id = 777
        self.from_user = type("U", (), {"username": uname})()


class FakeClaude:
    def __init__(self, parsed):
        self._parsed = parsed

    def quick(self, system, text, max_tokens=300, **kw):
        return json.dumps(self._parsed)

    def vision(self, *a, **k):
        return "{}"


class FakeBridge:
    """«то_заявки» + свой одометр «обслуживание» + счётчики боевой записи (её быть не должно)."""

    def __init__(self, rows=None, list_raises=False):
        self.sp = None
        self.closed = False
        self.rows = list(rows or [])
        self.list_raises = list_raises
        self.list_calls = 0
        self.oil_calls = []
        self.svc_calls = []
        self.upserts = []
        self.events = []
        self.sp_upserts = []

    def service_list(self, **kw):
        self.list_calls += 1
        if self.list_raises:
            raise RuntimeError("мост молчит")
        return {"ok": True, "items": list(self.rows)}

    def service_pending_get(self, chat_id, topic_id, bike):
        if self.sp and not self.closed:
            return {"ok": True, "item": dict(self.sp)}
        return {"ok": False, "error": "not_found"}

    def service_pending_upsert(self, **kw):
        self.sp_upserts.append(kw)
        if self.sp is None:
            self.sp = {"declared": "", "done": "", "status": "заявлено", "odometer": ""}
        for k, v in kw.items():
            if v not in (None, ""):
                self.sp[k] = v
        return {"ok": True, "status": self.sp.get("status")}

    def service_pending_close(self, **kw):
        self.closed = True
        return {"ok": True}

    def service_pending_list(self, **kw):
        return {"ok": True, "items": ([self.sp] if (self.sp and not self.closed) else [])}

    def set_fleet_oil(self, number, oil_km, confirmed=False):
        self.oil_calls.append((number, oil_km, confirmed))
        return {"ok": True, "new_oil": oil_km}

    def set_fleet_service(self, number, kind, km, confirmed=False):
        self.svc_calls.append((number, kind, km, confirmed))
        return {"ok": True, "new_km": km}

    def service_upsert(self, **kw):
        self.upserts.append(kw)
        return {"ok": True, "next_km": 44000, "status": "ok"}

    def add_event(self, **kw):
        self.events.append(kw)
        return {"ok": True, "saved": True}

    def read_events(self, *a, **k):
        return {"ok": True, "items": []}

    def find_bike(self, q):
        return {"name": BIKE}


SENDS = []


async def rec_send(context, *, chat_id, text, message_thread_id=None, **kw):
    SENDS.append(text)
    return type("M", (), {"message_id": len(SENDS)})()


async def rec_dl(pm):
    return None


S._send = rec_send
S._download_photo = rec_dl
S._time = type("T", (), {"time": staticmethod(lambda: NOW), "monotonic": staticmethod(lambda: NOW)})()


def reset(ttl="60"):
    os.environ["ODO_FRESH_MIN"] = ttl
    SENDS.clear()
    S._SVC_TOKENS.clear()
    S._AWAITING_REPLY.clear()
    S._RECENT_PHOTOS.clear()
    S._PENDING_WORKS.clear()
    S._ODOMETER_ASK_TS.clear()
    S._SP_ASK_TS.clear()
    S._SP_LAST_SENT.clear()
    S._SVC_WRITE_DEDUP.clear()
    S._SVC_SUMMARY.clear()
    S._TOPIC_BIKE_OVERRIDE[(CHAT, TOPIC)] = BIKE
    S._TOPIC_NAMES[(CHAT, TOPIC)] = BIKE


def run(coro):
    return asyncio.run(coro)


def is_pym_card(s):
    """Кнопка Пыму — это ПОДТВЕРЖДЕНИЕ ЗАПИСИ, а не просьба прислать пробег: число в ней уже
    стоит, и человек сверяет его глазами. Различать обязательно — иначе «не спрашиваем» нельзя
    отличить от «спрашиваем другими словами»: в тексте кнопки живут и «ไมล์», и «пришли правильное
    число» (дословный живой текст `msg_sp_confirm_pym`)."""
    return "Подтвердить запись?" in s or "ยืนยันบันทึก?" in s


def asked_odometer():
    """Сообщения, которые ПРОСЯТ у человека пробег (вопрос), — кнопка Пыму сюда не входит."""
    return [s for s in SENDS
            if not is_pym_card(s) and ("пробег" in s.lower() or "ODO" in s or "ไมล์" in s)]


def pym_button_odo():
    toks = [d for d in S._SVC_TOKENS.values() if d.get("kind") == "sp_done"]
    return toks[-1]["odo"] if toks else None


def rows_at(age_min, km=41641):
    return [{"bike": BIKE, "service_type": "oil", "current_km": km, "updated_at": iso(age_min)}]


# ============================================================================================
#  (3) ДВЕРЬ B — «переспрос одометра» фазы 2. ТРИ СЛУЧАЯ-БЛИЗНЕЦА
# ============================================================================================
def _phase2(bridge):
    return run(S.handle_service_result(Msg("колодки и редуктор заменил"), context=None,
                                       bridge=bridge, claude=FakeClaude({"works": ["замена редуктора"],
                                                                         "mileage": ""}),
                                       text="колодки и редуктор заменил"))


def test_door_b_fresh_number_no_question():
    reset()
    b = FakeBridge(rows=rows_at(4.4))
    b.sp = {"declared": "gear", "done": "", "status": "ждёт_факт", "odometer": ""}
    assert _phase2(b) is True
    assert not asked_odometer(), f"свежее число — переспроса быть не должно: {SENDS}"
    assert len(SENDS) == 1 and is_pym_card(SENDS[0]), f"ровно одно сообщение — кнопка Пыму: {SENDS}"
    assert b.sp["status"] == "ждёт_подтверждения" and str(b.sp["odometer"]) == "41641", b.sp
    assert pym_button_odo() == "41641", S._SVC_TOKENS
    assert not b.oil_calls and not b.svc_calls, "в Лист1 не пишем — гейт Пыма на месте"


def test_door_b_stale_number_asks_twin():
    reset()
    b = FakeBridge(rows=rows_at(956.2))          # то же самое, но число 16-часовой давности
    b.sp = {"declared": "gear", "done": "", "status": "ждёт_факт", "odometer": ""}
    assert _phase2(b) is True
    assert asked_odometer(), f"протухшее число — переспрос обязан уйти: {SENDS}"
    assert b.sp["status"] == "ждёт_факт", b.sp
    assert pym_button_odo() is None, "кнопки Пыму быть не должно"


def test_door_b_no_number_asks_twin():
    reset()
    b = FakeBridge(rows=[])                      # то же самое, но своего числа нет вовсе
    b.sp = {"declared": "gear", "done": "", "status": "ждёт_факт", "odometer": ""}
    assert _phase2(b) is True
    assert asked_odometer(), f"числа нет — переспрос обязан уйти: {SENDS}"
    assert b.sp["status"] == "ждёт_факт", b.sp


def test_door_b_number_without_time_asks():
    reset()
    b = FakeBridge(rows=[{"bike": BIKE, "current_km": 41641}])     # легаси-строка без времени
    b.sp = {"declared": "gear", "done": "", "status": "ждёт_факт", "odometer": ""}
    assert _phase2(b) is True
    assert asked_odometer(), f"возраст неизвестен — спрашиваем: {SENDS}"


def test_door_b_other_bike_number_is_not_taken():
    reset()
    b = FakeBridge(rows=[{"bike": "OTHERBIKE 111CC RED PHUKET 0002", "current_km": 55555,
                          "updated_at": iso(2)}])
    b.sp = {"declared": "gear", "done": "", "status": "ждёт_факт", "odometer": ""}
    assert _phase2(b) is True
    assert asked_odometer(), "чужое число не берём — спрашиваем"


def test_door_b_bridge_silent_asks_failsafe():
    reset()
    b = FakeBridge(list_raises=True)
    b.sp = {"declared": "gear", "done": "", "status": "ждёт_факт", "odometer": ""}
    assert _phase2(b) is True
    assert asked_odometer(), "мост молчит → спрашиваем, как спрашивали"


def test_door_b_number_in_message_costs_nothing():
    """Здоровый путь (число в сообщении) не платит НИ ОДНОГО лишнего чтения моста."""
    reset()
    b = FakeBridge(rows=rows_at(1))
    b.sp = {"declared": "gear", "done": "", "status": "ждёт_факт", "odometer": ""}
    run(S.handle_service_result(Msg("готово, редуктор, 40100"), context=None, bridge=b,
                                claude=FakeClaude({"works": ["редуктор"], "mileage": "40100"}),
                                text="готово, редуктор, 40100"))
    assert b.list_calls == 0, f"своего одометра не спрашивали: {b.list_calls}"
    assert pym_button_odo() == "40100", "число из сообщения сильнее известного"


# ============================================================================================
#  (4) ДВЕРЬ A — «принял работы — пришли пробег». ТРИ СЛУЧАЯ-БЛИЗНЕЦА
# ============================================================================================
def _works_no_km(bridge):
    parsed = {"type": "event", "event_type": "repair", "bike": BIKE,
              "works": ["замена масла в редукторе"], "mileage": ""}
    return run(S._handle_servicing(Msg("поменял масло в редукторе"), context=None, bridge=bridge,
                                   claude=FakeClaude(parsed)))


def test_door_a_fresh_number_no_question():
    reset()
    b = FakeBridge(rows=rows_at(2.2))
    _works_no_km(b)
    assert not asked_odometer(), f"свежее число — «пришли пробег» быть не должно: {SENDS}"
    assert len(SENDS) == 1 and is_pym_card(SENDS[0]), f"ровно одно сообщение — кнопка Пыму: {SENDS}"
    assert b.sp and b.sp["status"] == "ждёт_подтверждения", b.sp
    assert str(b.sp["odometer"]) == "41641", b.sp
    assert pym_button_odo() == "41641", S._SVC_TOKENS
    assert not b.oil_calls and not b.svc_calls, "в Лист1 не пишем"


def test_door_a_stale_number_asks_twin():
    reset()
    b = FakeBridge(rows=rows_at(956.2))
    _works_no_km(b)
    assert asked_odometer(), f"протухшее число — вопрос обязан уйти: {SENDS}"
    assert b.sp and b.sp["status"] == "ждёт_факт", b.sp
    assert pym_button_odo() is None


def test_door_a_no_number_asks_twin():
    reset()
    b = FakeBridge(rows=[])
    _works_no_km(b)
    assert asked_odometer(), f"числа нет — вопрос обязан уйти: {SENDS}"
    assert b.sp and b.sp["status"] == "ждёт_факт", b.sp


def test_door_a_does_not_repeat_the_pym_button():
    """Кнопка уже висит с тем же числом → вторым вопросом её не подпираем."""
    reset()
    b = FakeBridge(rows=rows_at(2.2))
    b.sp = {"declared": "gear", "done": "gear", "status": "ждёт_подтверждения", "odometer": "41641"}
    _works_no_km(b)
    assert pym_button_odo() is None, "второй кнопки Пыму не рождаем"


def test_door_a_bridge_silent_asks_failsafe():
    reset()
    b = FakeBridge(list_raises=True)
    _works_no_km(b)
    assert asked_odometer(), "мост молчит → спрашиваем, как спрашивали"


def test_door_a_healthy_path_does_not_read_odometer():
    """Пробег в сообщении есть → короткий путь не зовётся вовсе (счётчик вызовов решения)."""
    reset()
    b = FakeBridge(rows=rows_at(1))
    calls = {"n": 0}
    orig = S._odo_known_fresh

    def spy(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    S._odo_known_fresh = spy
    try:
        parsed = {"type": "event", "event_type": "repair", "bike": BIKE,
                  "works": ["замена масла в редукторе"], "mileage": "40100"}
        run(S._handle_servicing(Msg("поменял масло в редукторе, 40100"), context=None, bridge=b,
                                claude=FakeClaude(parsed)))
    finally:
        S._odo_known_fresh = orig
    assert calls["n"] == 0, f"на здоровом пути решение о свежести не зовётся: {calls}"


# ============================================================================================
#  (5) ОТКАТ: ODO_FRESH_MIN=0 — обе двери спрашивают, как спрашивали
# ============================================================================================
def test_rollback_door_b_asks_even_with_fresh_number():
    reset(ttl="0")
    b = FakeBridge(rows=rows_at(1.0))
    b.sp = {"declared": "gear", "done": "", "status": "ждёт_факт", "odometer": ""}
    _phase2(b)
    assert asked_odometer(), f"ODO_FRESH_MIN=0 → прежний переспрос: {SENDS}"
    assert b.list_calls == 0, "ветка мертва ДО чтения моста"
    reset()


def test_rollback_door_a_asks_even_with_fresh_number():
    reset(ttl="0")
    b = FakeBridge(rows=rows_at(1.0))
    _works_no_km(b)
    assert asked_odometer(), f"ODO_FRESH_MIN=0 → прежний вопрос: {SENDS}"
    assert b.list_calls == 0, "ветка мертва ДО чтения моста"
    reset()


# ============================================================================================
#  (6) ГРАНИЦЫ: красное не ослаблено, число доезжает до глаз человека
# ============================================================================================
def test_pym_still_sees_the_number_before_any_write():
    reset()
    b = FakeBridge(rows=rows_at(3.0))
    b.sp = {"declared": "gear", "done": "", "status": "ждёт_факт", "odometer": ""}
    _phase2(b)
    assert any("41641" in s for s in SENDS), f"число стоит в тексте кнопки: {SENDS}"
    assert not b.oil_calls and not b.svc_calls, "запись в Лист1 — только по «да» доверенного"


def test_env_knob_name_is_the_documented_one():
    assert odo_fresh.TTL_ENV == "ODO_FRESH_MIN"
    assert odo_fresh.TTL_DEFAULT_MIN == 60.0


def test_purity_guard_is_live_and_has_teeth():
    """Страж чистоты зарегистрирован, на живом модуле молчит — и краснеет на близнеце с миром."""
    import invariants_check as IC
    assert "ODO_FRESH_PURE" in [n for n, _ in IC.CHECKS], "страж в гейте"
    with open("/root/turbobaby-manager-bot/odo_fresh.py", encoding="utf-8") as f:
        live = f.read()
    assert IC._duty_ast_findings(live, allowed=frozenset(("datetime",))) == [], "живой модуль чист"
    twin = ("import datetime\nimport requests\n\n"
            "def verdict(a, b, c, d):\n"
            "    return open('/tmp/x').read()\n")
    assert IC._duty_ast_findings(twin, allowed=frozenset(("datetime",))), \
        "тот же страж на модуле, который умеет в мир, обязан краснеть"


if __name__ == "__main__":
    ok = fail = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ok += 1
            except Exception as e:
                fail += 1
                print(f"FAIL {name}: {e}")
    print(f"{ok}/{ok + fail}")
    sys.exit(1 if fail else 0)
