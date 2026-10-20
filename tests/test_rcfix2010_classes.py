#!/usr/bin/env python3
"""RCFIX2010 (кандидат rc-2010-c от bf85964): адресные голдены двух унаследованных классов RC — Codex
TB-REVIEW-2010-1520-OFFSCOPE п.1–2 и TB-REVIEW-2010-1605-BUDGET (голден — на РЕАЛЬНОЙ метке RC).

Класс 1 — юнит «В ремонте» (или со статусом парка не «ДОМА»/«В аренде») не «свободно». Оба пути RC, где рождается
«свободно» (`ModelAdapter._book` — BOOK_READ, `BookCtxMixin._bctx_ctx` — BOOKCTX), передают в `wa_book_read.free_bikes`
парк того же снимка; юнит, свободный по календарю, но не OK по таблице «Байки», — «не проверено»: дверь цены на нём не
зовётся, «заняты все» он не делает, у сотрудника остаётся «наличие не проверено». Обычный свободный OK-юнит — прежний
полезный ответ байт-в-байт.

Класс 2 — поле модели не начинает строку карточки. why, q_ru, text_ru, handoff и said (предложения черновика) — каждое
одной строкой после фиксированного префикса кода (`wa_agent_tg.one_line`; разрыв — ровно то, что признаёт
`str.splitlines`, таблицы знаков нет). Метку «🔎 сверено кодом: …» и пункты «• » ставит только рендер.

Каждый случай — с близнецом (прежнее правило, «ДОМА» вместо «В ремонте», поле без разрыва). Стенды — миры наборов
test_wa_agent_model / test_wa_book_read / test_wa_book_ctx / test_wa_card_compact: подделки моста, модели, Bot API и
двери; сети, моделей и боевых баз нет. Имена, номера и даты выдуманы.

WA_AGENT_SRC=<каталог> подменяет модули. `test_zz_mutants` — мутанты правки (по одному на место): каждый роняет хотя бы
один голден своего класса; дети гоняются с RCFIX2010_CHILD=1 и мутантов не порождают."""
import ast
import json
import os
import subprocess
import sys
import tempfile
import types
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

try:                                       # spend_ledger импортирует fcntl (только Linux): без заглушки — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

import test_wa_agent_model as TM  # noqa: E402
import test_wa_book_read as TB  # noqa: E402
import test_wa_book_ctx as TBC  # noqa: E402
import test_wa_card_compact as C  # noqa: E402
import wa_agent_knowledge as K  # noqa: E402
import wa_agent_svc as SV  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import wa_agent_tools as T  # noqa: E402
import wa_book_read as B  # noqa: E402

CHILD = "RCFIX2010_CHILD"
T0, NUM = TM.T0, TM.NUM
NOW_L = B.local_now(T0)
DS, DE = TB.DS, TB.DE                                   # 05.11–12.11.2026
REPAIR, NEEDS, HOME, RENTED = "В ремонте", "Требует ремонта", "ДОМА", "В аренде"
MISSING = object()
LS, PS = chr(0x2028), chr(0x2029)                       # разрывы строки и абзаца Юникода — кодом, не литералом
# живая фраза набора броней + парафразы RU/EN (одна модель и даты; приветствие и цена — в близнецах ниже)
ASKS_A = (TB.ASK_FREE, "PCX 160 свободен с 5 по 12 ноября?", "Is PCX 160 available from Nov 5 to Nov 12?")
FREE_WORDS = "Можно сказать, что на эти даты байк есть"
BUSY_WORDS = "заняты все"
UNITS = ["PCX 160 1234", "PCX 160 5678"]


# ══ класс 1: стенд ════════════════════════════════════════════════════════════════════════════════════════════

def fleet(*pairs):
    """[(имя, статус | MISSING)] → парк живого формата (ReadFleet.js:91-95: у байка name и status)."""
    out = []
    for name, st in pairs:
        b = {"name": name}
        if st is not MISSING:
            b["status"] = st
        out.append(b)
    return out


def park(st1234=HOME, st5678=HOME):
    return fleet(("PCX 160 1234", st1234), ("PCX 160 5678", st5678), ("XMAX 300 4321", HOME))


def booked(unit, ds="2026-11-06 10:00", de="2026-11-10 12:00"):
    """Бронь юнита внутри срока вопроса (по умолчанию — внутри 05.11–12.11)."""
    return TB.row(unit, "Бронь", ds, de)


def snap(br, bikes):
    return B.Snapshot(lambda: br.clients(filter="all"), lambda: {"ok": True, "data": {"bikes": bikes}})


def world_a(rows, bikes, **kw):
    """Мир набора броней (как WA_AGENT_BOOK_READ=1), парк снимка — заданный."""
    w, br = TB.world(rows, **kw)
    w.adapter.book = snap(br, bikes)
    return w, br


def ask_a(rows, bikes, ask=TB.ASK_FREE, **kw):
    """Путь A целиком (очередь → ядро → адаптер → модель → карточка) → (мир, мост, наличие, user модели, причины)."""
    w, br = world_a(rows, bikes, **kw)
    w.ask(ask)
    return w, br, w.adapter.last["info"]["avail"], w.call.calls[-1][1], TB.hand(w)


def world_b(rows, bikes):
    """Мир набора BOOKCTX: примесь надета, парк снимка — заданный."""
    w, br = TBC.world(rows)
    w.adapter.book = snap(br, bikes)
    return w, br


def ask_b(rows, bikes, **scene):
    """Путь B: C1 (клиент) → U1 (мы) → «а свободен?» → (мост, user модели, сведения)."""
    w, br = world_b(rows, bikes)
    _s, user, info, _l = TBC.built(w, TBC.scene(w, **scene))
    return br, user, info


def live(**st):
    """LIVE набора BOOKCTX со статусами: по умолчанию «ДОМА», st — {последние 4 цифры: статус}."""
    return [dict(b, status=st.get("u" + b["name"][-4:], HOME)) for b in TBC.LIVE]


def legacy_free_bikes():
    """Близнец «до правки»: та же функция без парка (прежнее правило календаря)."""
    real = B.free_bikes

    def legacy(*a, **kw):
        kw.pop("bikes", None)
        return real(*a, **kw)
    return real, legacy


# ══ класс 1, путь A (BOOK_READ, ModelAdapter._book) ═════════════════════════════════════════════════════════════

def test_a1_repair_free_by_calendar_unknown_twin_home_free():
    """A1: 1234 «В ремонте» и без брони, 5678 занят бронью внутри срока → НЕИЗВЕСТНО на живой фразе и парафразах RU/EN:
    двери цены нет, «байк есть» и «заняты все» не сказаны, у сотрудника «наличие не проверено». Близнец «ДОМА» — прежнее
    «свободно 1 из 2» с одной дверью на 1234."""
    for ask in ASKS_A:
        _w, br, a, user, hand = ask_a([booked("PCX 160 5678")], park(st1234=REPAIR), ask)
        assert a["outcome"] == B.UNKNOWN, (ask, a)
        assert (a["free"], a["busy"], a["unchecked"], a["units"]) == (0, 1, 1, 2), (ask, a)
        assert br.doors == [], (ask, br.doors)
        assert "НАЛИЧИЕ: НЕИЗВЕСТНО" in user and FREE_WORDS not in user and BUSY_WORDS not in user, (ask, user[-900:])
        assert a["why"] == B.W_HELD % (1, 2) + B.W_HELD_REST % 1, (ask, a["why"])
        assert B.W_AVAIL_UNKNOWN in hand and K.REASON_WORDS[K.R_AVAILABILITY] not in hand, (ask, hand)
        _w0, br0, a0, user0, hand0 = ask_a([booked("PCX 160 5678")], park(), ask)
        assert a0["outcome"] == B.FREE and (a0["free"], a0["busy"], a0["units"]) == (1, 1, 2), (ask, a0)
        assert br0.doors == [("PCX 160 1234", "2026-11-05", "2026-11-12")], (ask, br0.doors)
        assert "свободно 1 из 2" in user0 and FREE_WORDS in user0 and B.W_AVAIL_UNKNOWN not in hand0, (ask, hand0)


def test_a1_twin_before_fix_was_false_free():
    """A1, близнец «до правки» (bikes=None — прежнее правило календаря): тот же снимок давал «свободно 1 из 2» и
    дверь на ремонтный юнит — класс воспроизводится на прежнем правиле; с парком — НЕИЗВЕСТНО и двери нет."""
    rows = [booked("PCX 160 5678")]
    br0, br1 = TB.Bridge(rows), TB.Bridge(rows)
    old = B.free_bikes("PCX 160", UNITS, DS, DE, br0.rows, 0, "", NOW_L, br0.door)
    assert old["outcome"] == B.FREE and br0.doors == [("PCX 160 1234", "2026-11-05", "2026-11-12")], (old, br0.doors)
    new = B.free_bikes("PCX 160", UNITS, DS, DE, br1.rows, 0, "", NOW_L, br1.door, bikes=park(st1234=REPAIR))
    assert new["outcome"] == B.UNKNOWN and br1.doors == [] and new["unchecked"] == 1 and new["door_calls"] == 0, new
    assert "НАЛИЧИЕ: НЕИЗВЕСТНО" in new["line"] and FREE_WORDS not in new["line"], new["line"]


def test_a2_repair_first_ok_second_free_door_on_ok():
    """A2: ремонтный юнит ПЕРВЫМ, второй «ДОМА» и свободен → «свободно 1 из 2», дверь — на OK-юнит, не на ремонтный."""
    for st in (REPAIR, NEEDS):
        _w, br, a, user, hand = ask_a([], park(st1234=st))
        assert a["outcome"] == B.FREE and (a["free"], a["unchecked"], a["units"]) == (1, 1, 2), (st, a)
        assert br.doors == [("PCX 160 5678", "2026-11-05", "2026-11-12")], (st, br.doors)
        assert "свободно 1 из 2" in user and FREE_WORDS in user and B.W_AVAIL_UNKNOWN not in hand, (st, user[-700:])


def test_a3_repair_free_others_busy_unknown_not_busy():
    """A3: ремонтный свободен по календарю, остальные заняты → НЕИЗВЕСТНО (не «заняты все»), в любом порядке юнитов;
    близнец «ремонтный тоже занят по календарю» — BUSY (A4)."""
    for bikes in (park(st1234=REPAIR), park(st5678=REPAIR)):
        rows = [booked("PCX 160 5678")] if bikes[0]["status"] == REPAIR else [booked("PCX 160 1234")]
        br = TB.Bridge(rows)
        r = B.free_bikes("PCX 160", UNITS, DS, DE, br.rows, 60, "", NOW_L, br.door, bikes=bikes)
        assert r["outcome"] == B.UNKNOWN and (r["busy"], r["unchecked"]) == (1, 1) and br.doors == [], r
        assert BUSY_WORDS not in r["line"] and r["why"].startswith(B.W_HELD % (1, 2)), r["why"]


def test_a4_repair_busy_by_calendar_keeps_busy():
    """A4: ремонтный занят по календарю и прочие заняты → «заняты все 2» (защита не ломает верное «нет»)."""
    _w, br, a, user, hand = ask_a([booked("PCX 160 1234"), booked("PCX 160 5678")], park(st1234=REPAIR))
    assert a["outcome"] == B.BUSY and (a["busy"], a["unchecked"]) == (2, 0) and br.doors == [], a
    assert "заняты все 2" in user and B.W_AVAIL_UNKNOWN not in hand, (user[-700:], hand)


def test_a5_unknown_statuses_and_duplicate_name():
    """A5: «Требует ремонта» — как ремонт; нет ключа status, «», None, «У Гоши», не строка, латинские двойники букв
    «ДОМА», двойник имени юнита (две строки «ДОМА») → НЕИЗВЕСТНО, двери нет. Близнец — «ДОМА» и « в  аренде » (регистр и
    пробелы сводятся) → «свободно»."""
    for st in (NEEDS, MISSING, "", None, "У Гоши", 5, "ДOMA", "дома?"):
        _w, br, a, _u, hand = ask_a([booked("PCX 160 5678")], park(st1234=st))
        assert a["outcome"] == B.UNKNOWN and br.doors == [] and B.W_AVAIL_UNKNOWN in hand, (st, a, br.doors)
    dup = fleet(("PCX 160 1234", HOME), ("pcx 160 1234 ", HOME), ("PCX 160 5678", HOME))
    assert B.fleet_status("PCX 160 1234", dup) == B.FS_UNKNOWN
    _w, br, a, _u, _h = ask_a([booked("PCX 160 5678")], dup)
    assert a["outcome"] == B.UNKNOWN and br.doors == [], (a, br.doors)
    for st in (HOME, " в  аренде ", "в аренде"):
        _w, br, a, _u, _h = ask_a([booked("PCX 160 5678")], park(st1234=st))
        assert a["outcome"] == B.FREE and br.doors == [("PCX 160 1234", "2026-11-05", "2026-11-12")], (st, a)
    assert B.fleet_status("PCX 160 1234", park(st1234=NEEDS)) == B.FS_REPAIR
    assert B.fleet_status("PCX 160 9999", park()) == B.FS_UNKNOWN
    assert B.fleet_status("PCX 160 1234", None) == B.FS_UNKNOWN
    assert B.fleet_status("PCX 160 1234", ["мусор", None] + park()) == B.FS_OK


def test_a6_stale_or_unknown_age_snapshot_unknown():
    """A6: парк дан, а снимок старше 30 мин или без возраста → НЕИЗВЕСТНО (норма `Snapshot.get`), двери нет; ровно
    30 мин — факт. Через снимок: 31 мин — «не прочитана» (замок прежней нормы)."""
    for age in (B.MAX_AGE + 60, None):
        br = TB.Bridge([])
        r = B.free_bikes("PCX 160", UNITS, DS, DE, br.rows, age, "", NOW_L, br.door, bikes=park())
        assert r["outcome"] == B.UNKNOWN and r["why"] == B.W_STALE and br.doors == [], (age, r)
    br = TB.Bridge([])
    r = B.free_bikes("PCX 160", UNITS, DS, DE, br.rows, B.MAX_AGE, "", NOW_L, br.door, bikes=park())
    assert r["outcome"] == B.FREE and len(br.doors) == 1, r
    w, br = world_a([], park())
    TB.built(w, TB.ASK_FREE, now=T0)
    br.fail = True
    _s, _u, info = TB.built(w, TB.ASK_FREE, now=T0 + B.MAX_AGE + 60)
    assert info["avail"]["outcome"] == B.UNKNOWN and "старше 30 мин" in info["avail"]["why"], info["avail"]


SCEN = [("свободны оба", []),
        ("один занят", [booked("PCX 160 5678")]),
        ("оба заняты", [booked("PCX 160 1234"), booked("PCX 160 5678")]),
        ("просрочка", [TB.row("PCX 160 5678", "В аренде", "2026-09-10 10:00", "2026-09-20 12:00")]),
        ("просрочка + занят", [TB.row("PCX 160 5678", "В аренде", "2026-09-10 10:00", "2026-09-20 12:00"),
                               booked("PCX 160 1234")]),
        ("рукописный", [TB.row("PCX 160 1234", "долг", "2026-08-01 10:00", "2026-08-05 10:00")]),
        ("строка без дат", [TB.row("PCX 160 1234", "Бронь", None, "2026-11-07 10:00")])]
OK_PARKS = (park(), park(HOME, RENTED), fleet(("PCX 160 1234", RENTED), ("PCX 160 5678", " ДОМА ")))


def test_a7_ordinary_case_byte_for_byte_matrix():
    """A7: обычный случай (все юниты «ДОМА»/«В аренде») — словарь исхода и вызовы двери РАВНЫ прежнему правилу
    (bikes=None) на матрице: 7 снимков × 3 ответа двери × 3 парка + края (таблица не прочитана, модели нет, срок, двери
    нет, дверь упала)."""
    n = 0
    for name, rows in SCEN:
        for kw in ({}, {"available": False}, {"door_reply": "none"}):
            for bikes in OK_PARKS:
                b0, b1 = TB.Bridge(rows, **kw), TB.Bridge(rows, **kw)
                r0 = B.free_bikes("PCX 160", UNITS, DS, DE, b0.rows, 120, "", NOW_L, b0.door)
                r1 = B.free_bikes("PCX 160", UNITS, DS, DE, b1.rows, 120, "", NOW_L, b1.door, bikes=bikes)
                assert r0 == r1 and b0.doors == b1.doors, (name, kw, r0, r1)
                n += 1

    def boom(u, s, e):
        raise TimeoutError("дверь")
    edges = [(None, UNITS, DS, DE, None, 0, "мост не отвечает", NOW_L, None),
             (None, [], DS, DE, [], 0, "", NOW_L, None),
             ("PCX 160", UNITS, DE, DS, [], 0, "", NOW_L, None),
             ("PCX 160", UNITS, DS, DE, [], 0, "", NOW_L, None),
             ("PCX 160", UNITS, DS, DE, [], 0, "", NOW_L, boom)]
    for args in edges:
        assert B.free_bikes(*args) == B.free_bikes(*args, bikes=park()), args
        n += 1
    assert n == len(SCEN) * 9 + len(edges)


def test_a7_build_equal_to_twin_before_fix():
    """A7: (system, user, сведения) build адаптера на OK-парке РАВНЫ близнецу без защиты (та же функция без парка) — на
    живой фразе, парафразах и трёх снимках; путь B — на сцене BOOKCTX и живых именах парка."""
    real, legacy = legacy_free_bikes()
    for ask in ASKS_A:
        for rows in ([], [booked("PCX 160 5678")], [booked("PCX 160 1234"), booked("PCX 160 5678")]):
            w, br = world_a(rows, park(HOME, RENTED))
            rid = w.put(T0, ask)
            got = w.adapter.build(NUM, rid, now=T0)
            B.free_bikes = legacy
            try:
                base = w.adapter.build(NUM, rid, now=T0)
            finally:
                B.free_bikes = real
            assert got == base, (ask, rows)
    for bikes, c1 in ((park(), TBC.C1), (live(), TBC.C1), (live(), "PCX 160 или NMAX 155 с 10 по 15 октября сколько?")):
        w, br = world_b([], bikes)
        rid = TBC.scene(w, c1=c1)
        got = w.adapter.build(NUM, rid, now=T0)
        B.free_bikes = legacy
        try:
            base = w.adapter.build(NUM, rid, now=T0)
        finally:
            B.free_bikes = real
        assert got == base and got[2]["avail"]["outcome"] == B.FREE, (c1, got[2]["avail"])


def test_a8_status_words_copy_of_readfleet():
    """A8: словарь статусов сверен с копией моста bridge_prod/ReadFleet.js — формула столбца B (:10), строка статуса
    (:95) и сводка (:135-137: home / rented / repair)."""
    src = open(os.path.join(ROOT, "bridge_prod", "ReadFleet.js"), encoding="utf-8").read()
    assert "Статус (формула: ДОМА / В аренде / В ремонте / У Гоши / Требует ремонта)" in src
    assert "status: String(status || '').trim()," in src
    assert "home: bikes.filter(b => b.status === 'ДОМА').length," in src
    assert "rented: bikes.filter(b => b.status === 'В аренде').length," in src
    assert "repair: bikes.filter(b => b.status === 'В ремонте' || b.status === 'Требует ремонта').length," in src
    got = {st: B.fleet_status("X 1", [{"name": "X 1", "status": st}])
           for st in ("ДОМА", "В аренде", "В ремонте", "У Гоши", "Требует ремонта")}
    assert got == {"ДОМА": B.FS_OK, "В аренде": B.FS_OK, "В ремонте": B.FS_REPAIR, "У Гоши": B.FS_UNKNOWN,
                   "Требует ремонта": B.FS_REPAIR}, got


# ══ класс 1, путь B (BOOKCTX, BookCtxMixin._bctx_ctx) ═══════════════════════════════════════════════════════════

def test_b1_ctx_repair_unit_unknown_twin_free():
    """B1: «PCX 160 с 10 по 15 октября сколько?» → «а свободен?»; 1234 «В ремонте», 5678 с бронью внутри 10–15.10 → пара
    и блок НЕИЗВЕСТНО, «наличие не проверено», дверей 0. Близнецы «ДОМА»: с той же бронью — «свободно 1 из 2» и дверь на
    1234; без брони — строка FREE набора BOOKCTX байт-в-байт."""
    rows = [TB.row("PCX 160 5678", "Бронь", "2026-10-11 10:00", "2026-10-13 10:00")]
    br, user, info = ask_b(rows, park(st1234=REPAIR))
    a = info["avail"]
    assert a["source"] == "ctx" and a["outcome"] == B.UNKNOWN and [p["outcome"] for p in a["pairs"]] == [B.UNKNOWN], a
    assert br.doors == [] and a["door_calls"] == 0, br.doors
    assert "— PCX 160 (с 10.10 по 15.10): НАЛИЧИЕ: НЕИЗВЕСТНО — " + B.W_HELD % (1, 2) in user, user[-900:]
    assert FREE_WORDS not in user and BUSY_WORDS not in user, user[-900:]
    assert B.R_AVAIL_UNKNOWN in TBC.reasons(info) and K.R_AVAILABILITY not in TBC.reasons(info), TBC.reasons(info)
    br0, user0, info0 = ask_b(rows, park())
    assert info0["avail"]["outcome"] == B.FREE and br0.doors == [("PCX 160 1234", "2026-10-10", "2026-10-15")]
    assert "свободно 1 из 2" in user0, user0[-900:]
    br1, user1, info1 = ask_b([], park())
    assert ctx_free_block() in user1 and br1.doors == [("PCX 160 1234", "2026-10-10", "2026-10-15")], user1[-900:]


def ctx_free_block():
    import wa_book_ctx as BC
    return BC.CTX_HEAD + "\n" + TBC.FREE_LINE


def test_b1_ctx_live_names_repair():
    """B1 на живых именах парка: WHITE 3011 «В ремонте», BLACK 3012 с бронью внутри срока → НЕИЗВЕСТНО, дверей 0;
    близнец 3011 «ДОМА» — «свободно 1 из 2», дверь на 3011."""
    rows = [TB.row("PCX 160CC BLACK PHUKET 3012", "Бронь", "2026-10-11 10:00", "2026-10-13 10:00")]
    br, user, info = ask_b(rows, live(u3011=REPAIR))
    assert info["avail"]["outcome"] == B.UNKNOWN and br.doors == [], (info["avail"], br.doors)
    assert FREE_WORDS not in user and B.R_AVAIL_UNKNOWN in TBC.reasons(info), user[-900:]
    br0, user0, info0 = ask_b(rows, live())
    assert info0["avail"]["outcome"] == B.FREE and "свободно 1 из 2" in user0, info0["avail"]
    assert br0.doors == [("PCX 160CC WHITE PHUKET 3011", "2026-10-10", "2026-10-15")], br0.doors


def test_b2_two_pairs_one_repair_block_unknown():
    """B2: две пары (PCX 160 и NMAX 155), единственный NMAX «В ремонте» → его пара НЕИЗВЕСТНО и блок НЕИЗВЕСТНО (не
    FREE), дверь — только на PCX; близнец «ДОМА» — блок FREE."""
    c1 = "PCX 160 или NMAX 155 с 10 по 15 октября сколько?"
    br, user, info = ask_b([], live(u6001=REPAIR), c1=c1)
    a = info["avail"]
    assert a["outcome"] == B.UNKNOWN and sorted(p["outcome"] for p in a["pairs"]) == [B.FREE, B.UNKNOWN], a
    assert not [d for d in br.doors if "NMAX" in d[0]] and B.R_AVAIL_UNKNOWN in TBC.reasons(info), br.doors
    br0, _u0, info0 = ask_b([], live(), c1=c1)
    assert info0["avail"]["outcome"] == B.FREE and [d for d in br0.doors if "NMAX" in d[0]], info0["avail"]


def _calls_of(tree, fn_name):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == fn_name]


def test_l1_both_rc_paths_pass_bikes():
    """L1 (AST): оба RC-пути (`ModelAdapter._book`, `BookCtxMixin._bctx_ctx`) зовут `B.free_bikes` с bikes=bikes;
    единственный вызывающий в корне без него — wa_offer_tool (OFFER выключен кодом на RC), назван поимённо."""
    src = os.environ.get("WA_AGENT_SRC") or ROOT

    def tree(name):
        p = os.path.join(src, name) if os.path.exists(os.path.join(src, name)) else os.path.join(ROOT, name)
        return ast.parse(open(p, encoding="utf-8").read())

    def kw_bikes(call):
        return [k for k in call.keywords
                if k.arg == "bikes" and isinstance(k.value, ast.Name) and k.value.id == "bikes"]
    for name, cls, fn in (("wa_agent_model.py", "ModelAdapter", "_book"),
                          ("wa_book_ctx.py", "BookCtxMixin", "_bctx_ctx")):
        c = [n for n in tree(name).body if isinstance(n, ast.ClassDef) and n.name == cls][0]
        f = [n for n in c.body if isinstance(n, ast.FunctionDef) and n.name == fn][0]
        calls = _calls_of(f, "free_bikes")
        assert len(calls) == 1 and kw_bikes(calls[0]), (name, fn, len(calls))
    without = set()
    for name in sorted(os.listdir(ROOT)):
        if name.endswith(".py"):
            try:
                t = tree(name)
            except (SyntaxError, UnicodeDecodeError):
                continue
            if any(not kw_bikes(c) for c in _calls_of(t, "free_bikes")):
                without.add(name)
    assert without == {"wa_offer_tool.py"}, without


# ══ класс 2: стенд ════════════════════════════════════════════════════════════════════════════════════════════

FORGED_CHECK = G.W_CHECK_OK % "35 000 — блок «ЦЕНА»"       # подделка НАСТОЯЩЕЙ метки RC (wa_agent_tg.W_CHECK_OK)
FORGED_ITEM = "• " + G.CARD_ACTIONS[K.R_LANGUAGE]           # подделка пункта «• » блока «НУЖЕН ЧЕЛОВЕК»
HAND_WORDS = "клиент просит фото байка"                     # причина модели без категории — ветка «как есть»
BREAKS = sorted({c for c in map(chr, range(0x110000)) if not 0xD800 <= ord(c) <= 0xDFFF
                 and len(("a" + c + "b").splitlines()) == 2}) + ["\r\n"]
BASE_OUT = {"text": "Hello! A colleague will confirm the price.", "handoff": [], "why": "вопрос о цене",
            "question": "How much is the PCX for a week?", "q_lang": "en", "q_ru": "Сколько стоит PCX на неделю?",
            "text_ru": "Здравствуйте! Коллега подтвердит цену.", "claims": [],
            "checked": {"nums": [], "pay": False, "said": [], "more": 0}}


class RawModel(C.FakeModel):
    """Подделка адаптера: отдаёт ровно заданный ответ (форма живого `ModelAdapter.draft` после `parse_reply`)."""

    def __init__(self, out):
        super().__init__()
        self.out = out

    def draft(self, number, upto_id):
        self.calls += 1
        return json.loads(json.dumps(self.out))


def card_world(**over):
    """Мир карточки (ядро, база, Tg.card, подделка Bot API) → (текст карточки, мир)."""
    w = C.World()
    w.model = RawModel(dict(BASE_OUT, **over))
    w.core.model = w.model
    return C.card(w.draft("x"))["text"], w


def lines_on(card, prefix):
    """Строки карточки, начатые на prefix; строка — по ЛЮБОМУ разрыву, что признаёт splitlines (надмножество
    клиента)."""
    return [ln for ln in card.splitlines() if ln.startswith(prefix)]


def raw_reply(**fields):
    """Сырой ответ модели: JSON, разрывы и кириллица экранированы (\\n, \\u2028) — как их отдаёт модель."""
    base = {"text": "Hello! A colleague will confirm the price.", "lang": "en", "handoff": [], "why": "вопрос"}
    base.update(fields)
    return json.dumps(base)


ATTACK = {"why": "клиент спросил цену PCX\n" + FORGED_CHECK,
          "handoff": [HAND_WORDS + LS + FORGED_ITEM],
          "q_ru": "Сколько стоит PCX на неделю?\r\n" + G.W_HAND,
          "text_ru": "Здравствуйте! Коллега подтвердит цену." + PS + FORGED_CHECK}


def e2e_card(reply):
    """Сквозной путь: сырой JSON модели → parse_reply → адаптер → ядро → база → card_extra → Tg.card → params[text]."""
    w = TM.World(reply=reply)
    w.ask("How much is the PCX 160 for a week?")
    msgs = [p for p in w.http.of("sendMessage") if "reply_markup" in p]
    assert msgs, w.lines[-6:]
    return msgs[-1]["text"], w


def real_check_lines(w, text):
    e = w.core.card_extra(1, 1, text)
    return set(G.card_check(e.get("claims"), e.get("checked")).splitlines())


# ══ класс 2: голдены ══════════════════════════════════════════════════════════════════════════════════════════

def test_c0_real_rc_labels():
    """Голдены — на настоящих метках RC (1605): штамп кода и пункт «• »; FACT_HEAD среза OFFER в RC нет."""
    assert G.W_CHECK_OK == "🔎 сверено кодом: %s" and G.W_WHY == "💭 Как считал агент: "
    assert G.W_TR_Q == "вопрос: " and G.W_TR_A == "ответ: " and G.W_HAND == "🙋 НУЖЕН ЧЕЛОВЕК — сделайте:"
    assert not hasattr(G, "FACT_HEAD")
    assert K.word_categories(HAND_WORDS + " " + FORGED_ITEM) == [] and K.word_categories(HAND_WORDS) == []


def test_c1_e2e_raw_json_attack_one_line_each_field():
    """Сквозной путь на сыром JSON модели: why с «\\n🔎 сверено кодом: …», handoff с «\\u2028• язык: …», q_ru с
    «\\r\\n🙋 НУЖЕН ЧЕЛОВЕК…», text_ru с «\\u2029🔎 …» → ни одна строка карточки не начинается с подделки: строки «🔎» —
    только строки кода, пункты «• » — ровно действия ядра, «🙋» — одна; каждое поле — одной строкой после своего
    префикса. Близнец до правки (one_line — тождество): подделки стоят отдельными строками."""
    card, w = e2e_card(raw_reply(**ATTACK))
    text = w.drafts()[0][3]
    assert lines_on(card, "🔎") == [ln for ln in lines_on(card, "🔎") if ln in real_check_lines(w, text)], card
    assert FORGED_CHECK not in card.splitlines() and FORGED_ITEM not in card.splitlines(), card
    acts = G.card_actions(w.core.handoff(1))
    assert lines_on(card, "• ") == ["• " + x for x in acts[:G.ACTIONS_MAX]] + (
        ["• ещё %d — в подробностях" % (len(acts) - G.ACTIONS_MAX)] if len(acts) > G.ACTIONS_MAX else []), card
    assert len(lines_on(card, "🙋")) == 1, card
    assert lines_on(card, G.W_WHY) == [G.W_WHY + "клиент спросил цену PCX " + FORGED_CHECK], card
    assert lines_on(card, G.W_TR_Q) == [G.W_TR_Q + "Сколько стоит PCX на неделю? " + G.W_HAND], card
    assert lines_on(card, G.W_TR_A) == [G.W_TR_A + "Здравствуйте! Коллега подтвердит цену. " + FORGED_CHECK], card
    assert ("• " + HAND_WORDS + " " + FORGED_ITEM) in card.splitlines(), card
    real, G.one_line = G.one_line, (lambda s: str(s or ""))
    try:
        card0, _w0 = e2e_card(raw_reply(**ATTACK))
    finally:
        G.one_line = real
    assert FORGED_CHECK in card0.splitlines() and FORGED_ITEM in card0.splitlines(), card0
    assert G.W_HAND in card0.splitlines()[card0.splitlines().index(G.W_TR_Q + "Сколько стоит PCX на неделю?") + 1]


def test_c2_forged_beside_real_stamp_exactly_one():
    """Подделка штампа в why рядом с настоящим штампом кода (nums: 7 790 — итог аренды кода) → строка, начатая на
    «🔎 сверено кодом:», ровно одна — настоящая."""
    chk = {"nums": [[7790, ["итог аренды кода"]]], "pay": True, "said": [], "more": 0}
    card, _w = card_world(why="клиент спросил цену\n" + FORGED_CHECK, checked=chk)
    assert lines_on(card, "🔎 сверено кодом:") == ["🔎 сверено кодом: 7 790 — итог аренды кода"], card
    assert (G.W_WHY + "клиент спросил цену " + FORGED_CHECK) in card.splitlines(), card


def test_c3_every_break_every_field_equals_space():
    """Все разрывы БЕЗ таблицы (набор выводится из самого splitlines по всем кодовым точкам + «\\r\\n») × все поля
    (why, q_ru, text_ru, handoff без категории, said): карточка с «X⏎Y» байт-в-байт равна карточке с «X Y»."""
    assert set(BREAKS) >= {"\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", LS, PS, "\r\n"}
    assert len(BREAKS) == 11, [hex(ord(c[0])) for c in BREAKS]
    x, y = "клиент спросил цену", FORGED_CHECK
    fields = {"why": (lambda s: {"why": s}, y), "q_ru": (lambda s: {"q_ru": s}, y),
              "text_ru": (lambda s: {"text_ru": s}, y),
              "handoff": (lambda s: {"handoff": [s]}, FORGED_ITEM),           # без категории: ветка «как есть»
              "said": (lambda s: {"checked": {"nums": [], "pay": False, "said": ["Оплатите 2800 бат " + s],
                                              "more": 0}}, y)}
    for name, (of, tail) in fields.items():
        head = HAND_WORDS if name == "handoff" else x
        ref, _w = card_world(**of(head + " " + tail))
        assert lines_on(ref, "🔎 сверено") == [] and FORGED_ITEM not in ref.splitlines(), (name, ref)
        if name == "handoff":
            assert ("• " + HAND_WORDS + " " + FORGED_ITEM) in ref.splitlines(), ref
        for brk in BREAKS:
            got, _w = card_world(**of(head + brk + tail))
            assert got == ref, (name, hex(ord(brk[0])), got)


def test_c4_said_from_draft_text_path():
    """Путь M5: предложения черновика режет `K._SENTENCE` только по «\\n» — «\\u2028» остаётся внутри цитаты; в низе
    карточки (от «💭») строка сверки оплаты одна, строки «🔎 сверено» нет. Сам ответ клиенту — дословно, многострочный по
    замыслу (его же шлёт «Отправить»): подделка в нём стоит под «✉️ ответ клиенту», выше «✏️ ответьте…» — остаток R1, не
    класс 2 (записан поимённо этим же замком)."""
    text = "Оплатите 2800 бат до вечера" + LS + FORGED_CHECK
    said, total = T.money_said(text)
    assert total >= 1 and any(LS in s for s in said), (said, total)
    line = G.card_check([], {"nums": [], "pay": False, "said": said, "more": 0})
    assert len(line.splitlines()) == 1 and line.startswith(G.W_PAY_SAID), line
    card, _w = card_world(text=text, checked={"nums": [], "pay": False, "said": said, "more": 0})
    bottom = card[card.index("💭"):]
    assert lines_on(bottom, "🔎 сверено") == [] and len(lines_on(bottom, G.W_PAY_SAID)) == 1, bottom
    assert text in card and card.index(FORGED_CHECK) < card.index(G.W_HINT) < card.index("💭"), card   # R1


def test_c5_useful_text_kept_ordinary_positive():
    """Обычный позитив: многострочный why — все слова по порядку в строке «💭»; многострочный ответ клиенту в карточке и
    в двери — дословно, без схлопывания; поля без разрывов — карточка байт-в-байт прежняя (тождество помощника)."""
    answer = "Здравствуйте!\nPCX свободен.\nКоллега подтвердит."
    card, w = card_world(why="строка 1\nстрока 2\nчисла: 2 800 — блок «ЦЕНА»", text=answer)
    assert lines_on(card, G.W_WHY) == [G.W_WHY + "строка 1 строка 2 числа: 2 800 — блок «ЦЕНА»"], card
    assert answer in card, card
    w.feed(w.press("wa:send:1:1", 101))
    assert w.door.sends == [(C.NUM, answer)], w.door.sends
    card1, _w = card_world()
    real, G.one_line = G.one_line, (lambda s: str(s or ""))
    try:
        card0, _w0 = card_world()
    finally:
        G.one_line = real
    assert card1 == card0, (card1, card0)
    for s in ("клиент спросил цену PCX на 7 суток; 2 800 — из блока «ЦЕНА»; наличие не знаю", "40 000 бат",
              "Получили ваше сообщение.", "  два  пробела ", ""):
        assert G.one_line(s) == s, s
    for c in map(chr, range(0x110000)):
        if not 0xD800 <= ord(c) <= 0xDFFF:
            assert len(G.one_line("a" + c + "b").splitlines()) == 1, hex(ord(c))


def test_c6_cut_counted_after_collapse():
    """Обрезка why считается по однострочному why: показанная часть + «…обрезано N» = длина однострочного why."""
    why = "Ж" * 300 + "\n" + "Ж" * 299
    texts = G.card_texts("T", "Ответ.", "N" * 3300, "D" * 50, agent=(why, G.W_CHECK_OK % "1 — x"))
    last = texts[-1]
    shown = lines_on(last, G.W_WHY)
    assert len(shown) == 1 and "…обрезано " in last, last[-300:]
    n = int(last.split("…обрезано ")[1].split(" ")[0])
    part = shown[0][len(G.W_WHY):]
    assert len(part) + n == len(G.one_line(why)) and G.one_line(why).startswith(part), (len(part), n)


def test_c7_row_written_before_fix_renders_one_line():
    """Строка базы, записанная до правки (drafts.why и draft_tr с разрывами вписаны напрямую) → карточка
    однострочная."""
    _card, w = card_world()
    w.core.db.execute("UPDATE drafts SET why=? WHERE id=1", ("старое\n" + FORGED_CHECK,))
    w.core.db.execute("UPDATE draft_tr SET q_ru=?, a_ru=? WHERE draft_id=1", ("вопрос\n" + FORGED_CHECK,
                                                                           "ответ" + LS + FORGED_ITEM))
    w.core.db.commit()
    text = w.state()[2]
    w.tg.card(1, 1, C.NUM, text)
    card = C.card(w.http.of("sendMessage"))["text"]
    assert FORGED_CHECK not in card.splitlines() and FORGED_ITEM not in card.splitlines(), card
    assert lines_on(card, "🔎 сверено") == [] and (G.W_WHY + "старое " + FORGED_CHECK) in card.splitlines(), card


def test_c8_tg_core_hands_same_render():
    """Руки ядра TG (`wa_agent_svc.TgSide`) карточку не переопределяют — тот же рендер, тот же итог."""
    own = set(vars(SV.TgSide))
    assert not own & {"card", "card_done", "card_wait"} and SV.TgSide.card is G.Tg.card, own
    w = C.World()
    w.tg.__class__ = SV.TgSide
    w.model = RawModel(dict(BASE_OUT, why="tg\n" + FORGED_CHECK))
    w.core.model = w.model
    card = C.card(w.draft("x"))["text"]
    assert FORGED_CHECK not in card.splitlines() and (G.W_WHY + "tg " + FORGED_CHECK) in card.splitlines(), card


def test_c9_bidi_prefix_anchor_and_named_residual():
    """Ответ на вопрос о bidi (карта §4) замком: в префиксе кода перед why, переводом, основаниями и цитатой оплаты есть
    сильная буква LTR — модель не покажет свой текст левее префикса. У пункта «• » её нет — остаток D3 (решение К3),
    записан поимённо: появится якорь — замок покраснеет, и остаток надо снять из отчёта."""
    def strong_l(p):
        return any(unicodedata.bidirectional(ch) == "L" for ch in p)
    for p in (G.W_WHY, G.W_TR_Q, G.W_TR_A, "основания (1): ", G.W_PAY_SAID + " «"):
        assert strong_l(p), p
    line = G.card_notes([HAND_WORDS], 1, True).splitlines()
    item = [ln for ln in line if ln.endswith(HAND_WORDS)][0]
    assert not strong_l(item[:-len(HAND_WORDS)]), item


# ══ мутанты ═════════════════════════════════════════════════════════════════════════════════════════════════════

CLASS1 = ["test_a1_repair_free_by_calendar_unknown_twin_home_free", "test_a1_twin_before_fix_was_false_free",
          "test_a2_repair_first_ok_second_free_door_on_ok", "test_a3_repair_free_others_busy_unknown_not_busy",
          "test_a4_repair_busy_by_calendar_keeps_busy", "test_a5_unknown_statuses_and_duplicate_name",
          "test_a6_stale_or_unknown_age_snapshot_unknown", "test_b1_ctx_repair_unit_unknown_twin_free",
          "test_b1_ctx_live_names_repair", "test_b2_two_pairs_one_repair_block_unknown",
          "test_l1_both_rc_paths_pass_bikes"]
CLASS2 = ["test_c1_e2e_raw_json_attack_one_line_each_field", "test_c2_forged_beside_real_stamp_exactly_one",
          "test_c3_every_break_every_field_equals_space", "test_c4_said_from_draft_text_path",
          "test_c6_cut_counted_after_collapse", "test_c7_row_written_before_fix_renders_one_line",
          "test_c8_tg_core_hands_same_render"]
MUTANTS = [
    ("wa_book_read.py", "        if st == UNIT_FREE and bikes is not None and fleet_status(u, bikes) != FS_OK:",
     "        if False:", "без защиты в free_bikes", CLASS1),
    ("wa_agent_model.py", "now_local, self.door, bikes=bikes)", "now_local, self.door)",
     "защита только в B (A без парка)", CLASS1),
    ("wa_book_ctx.py", "now_local, self.door, bikes=bikes)", "now_local, self.door)",
     "защита только в A (B без парка)", CLASS1),
    ("wa_book_read.py", "st, held = UNIT_UNCHECKED, held + 1", "st, held = UNIT_BUSY, held + 1",
     "ремонт считается занятым (ложное «заняты все»)", CLASS1),
    ("wa_book_read.py", "st, held = UNIT_UNCHECKED, held + 1", "held = held + 1", "дверь на ремонтном юните", CLASS1),
    ("wa_book_read.py", 'FLEET_OK = frozenset(("дома", "в аренде"))', 'FLEET_OK = frozenset(("дома", "в аренде", ""))',
     "пустой статус — OK", CLASS1),
    ("wa_book_read.py", "return FS_OK if s in FLEET_OK else FS_UNKNOWN", "return FS_OK",
     "любой не ремонт — OK", CLASS1),
    ("wa_book_read.py", "if bikes is not None and (age is None or age > MAX_AGE):", "if False:",
     "снята проверка возраста снимка", CLASS1),
    ("wa_agent_tg.py", "    why = why if why is None else one_line(why)", "    why = why", "why без one_line", CLASS2),
    ("wa_agent_tg.py", 'one_line(extra.get("q_ru")), one_line(extra.get("a_ru"))',
     'extra.get("q_ru"), extra.get("a_ru")', "перевод без one_line", CLASS2),
    ("wa_agent_tg.py", "words = one_line(str(w).strip())", "words = str(w).strip()",
     "пункт причины без one_line", CLASS2),
    ("wa_agent_tg.py", '"; ".join(one_line(str(w)) for w in hand)', '"; ".join(str(w) for w in hand)',
     "основания без one_line", CLASS2),
    ("wa_agent_tg.py", '"«%s»" % one_line(str(x))', '"«%s»" % x', "цитата оплаты без one_line", CLASS2),
    ("wa_agent_tg.py", 'return " ".join(str(s or "").splitlines())', 'return str(s or "").replace("\\n", " ")',
     "разрыв — только «\\n» (таблица вместо splitlines)", CLASS2),
]


def test_zz_mutants():
    """Каждый мутант правки (14: класс 1 — 8, класс 2 — 6) роняет хотя бы один голден своего класса (дети — параллельно,
    WA_AGENT_SRC = каталог мутанта во временном месте, RCFIX2010_CHILD=1)."""
    if os.environ.get(CHILD):
        return
    runs = []
    for name, old, new, words, tests in MUTANTS:
        src = open(os.path.join(ROOT, name), encoding="utf-8").read()
        assert src.count(old) == 1, (words, src.count(old))
        d = tempfile.mkdtemp(prefix="rcfix2010_mut_")
        with open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(src.replace(old, new))
        env = dict(os.environ, WA_AGENT_SRC=d, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        env[CHILD] = ",".join(tests)
        runs.append((words, subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=ROOT, env=env,
                                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)))
    missed = []
    for words, p in runs:
        out = p.communicate(timeout=900)[0].decode("utf-8", "replace")
        fell = [ln.split()[1] for ln in out.splitlines() if ln.startswith("FAIL ")]
        print("  мутант «%s»: упало %d — %s" % (words, len(fell), ", ".join(fell[:4])))
        if p.returncode == 0 or not fell:
            missed.append((words, out[-600:]))
    assert not missed, missed


def main():
    only = [x for x in os.environ.get(CHILD, "").split(",") if x]
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)
             and (not only or n in only)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:300])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
