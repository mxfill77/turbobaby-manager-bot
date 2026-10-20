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

Доделка класса 2 (Codex TB-QA-2010C-HEAD-2011): D3 — слова причины без действия в пункте «• » идут после фиксированной
метки кода «причина дословно: » в изоляции LRI…PDI (`wa_agent_tg.act_words`); по эталону UAX#9 этого набора (`uax9`)
метка — первая видимая при доказанном bidi-входе и на 3000 случайных; claims — строка из `_num` одной строкой.

Предел замков класса 2 и D3 — ЛОГИЧЕСКАЯ строка карточки (её логический и видимый по UAX#9 порядок). Мягкий перенос
клиента внутри длинной логической строки не закрыт: метка держит первую видимую строку пункта, а продолжение переноса
начинается словами поля — у пункта «• » и у «💭» (у «💭» класс унаследован, он старше D3). Это остаток R-WRAP,
записанный поимённо замком `test_d5`; простого ремонта в тексте без таблицы знаков у него нет.

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
LRI, RLI, FSI, PDI = map(chr, (0x2066, 0x2067, 0x2068, 0x2069))     # изоляторы UAX#9 — кодом, не литералом
RLO, RLE, LRO, LRE, PDF = map(chr, (0x202E, 0x202B, 0x202D, 0x202A, 0x202C))
RLM, LRM, ALM, NEL = map(chr, (0x200F, 0x200E, 0x061C, 0x85))
HEB = "".join(map(chr, (0x05E9, 0x05DC, 0x05D5, 0x05DD)))      # иврит, класс R (4 буквы)
ITEM_HEAD = "• " + G.W_ACT_WORDS                             # D3: метка источника кода перед словами причины
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
    assert (ITEM_HEAD + LRI + HAND_WORDS + " " + FORGED_ITEM + PDI) in card.splitlines(), card   # D3: метка кода
    real, G.one_line = G.one_line, (lambda s: str(s or ""))
    try:
        card0, _w0 = e2e_card(raw_reply(**ATTACK))
    finally:
        G.one_line = real
    assert FORGED_CHECK in card0.splitlines() and (FORGED_ITEM + PDI) in card0.splitlines(), card0
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
            assert (ITEM_HEAD + LRI + HAND_WORDS + " " + FORGED_ITEM + PDI) in ref.splitlines(), ref
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


def test_c9_bidi_prefix_anchor_every_model_field():
    """Ответ на вопрос о bidi (карта §4) замком: в префиксе кода перед why, переводом, основаниями, цитатой оплаты — и
    (D3, Codex TB-QA-2010C-HEAD-2011, было «остаток») перед словами пункта «• » — есть сильная буква LTR, и в префиксе
    нет ни одного знака, который по UAX#9 мог бы её сдвинуть (только L / WS / ON / CS, без явных знаков X1–X8). Слова
    пункта — в изоляции LRI…PDI. Свойство на любом входе — test_d1/test_d4 эталоном UAX#9; здесь — предусловие."""
    def strong_l(p):
        return any(unicodedata.bidirectional(ch) == "L" for ch in p)
    for p in (G.W_WHY, G.W_TR_Q, G.W_TR_A, "основания (1): ", G.W_PAY_SAID + " «", ITEM_HEAD):
        assert strong_l(p), p
    assert {unicodedata.bidirectional(ch) for ch in ITEM_HEAD} <= {"L", "WS", "ON", "CS"}, ITEM_HEAD
    line = G.card_notes([HAND_WORDS], 1, True).splitlines()
    item = [ln for ln in line if HAND_WORDS in ln][0]
    assert item == ITEM_HEAD + LRI + HAND_WORDS + PDI and strong_l(item[:item.index(LRI)]), item


# ══ D3 и claims (Codex TB-QA-2010C-HEAD-2011): стенд — эталон UAX#9 одной строки ═══════════════════════════════════

_X9 = frozenset(("RLE", "LRE", "RLO", "LRO", "PDF", "BN"))
_ISO = frozenset(("LRI", "RLI", "FSI"))
_NI = frozenset(("B", "S", "WS", "ON", "LRI", "RLI", "FSI", "PDI"))


def _bidi_types(s):
    """Классы UAX#9 знаков строки (unicodedata). Эталон не судит то, чего не реализует: скобки (N0 — Ps/Pe),
    неназначенные знаки и разрывы абзаца — отказ, а не молча неверный ответ."""
    out = []
    for c in s:
        t = unicodedata.bidirectional(c)
        assert t and t != "B" and unicodedata.category(c) not in ("Ps", "Pe"), "эталон не судит %r" % c
        out.append(t)
    return out


def _first_strong(types, a, b):
    """P2: первый L/R/AL на [a, b), минуя знаки от изолятора до его PDI (без пары — до конца)."""
    depth = 0
    for i in range(a, b):
        t = types[i]
        if t in _ISO:
            depth += 1
        elif t == "PDI":
            depth = max(0, depth - 1)
        elif not depth and t in ("L", "R", "AL"):
            return t
    return None


def uax9(s):
    """Строка (один абзац) → (уровень абзаца, [уровень знака], [индексы знаков в визуальном порядке слева направо]).
    UAX#9 (Unicode 15): P2–P3, X1–X10 (стек 125, переполнения), W1–W7, N1–N2, I1–I2, L1, L2. Не реализованы N0
    (скобки — отказ в `_bidi_types`), L3 и L4 (зеркальные глифы порядок знаков не меняют). Снятые X9 знаки в порядок
    не входят."""
    types = _bidi_types(s)
    n = len(types)
    match, open_ = {}, []
    for i, t in enumerate(types):                        # BD9: пара изолятора — PDI того же уровня вложенности
        if t in _ISO:
            open_.append(i)
        elif t == "PDI" and open_:
            match[open_.pop()] = i
    para = 1 if _first_strong(types, 0, n) in ("R", "AL") else 0
    t, lev = list(types), [para] * n
    stack, over_iso, over_emb, valid_iso = [(para, None, False)], 0, 0, 0
    for i, ty in enumerate(types):                       # X1–X8
        if ty in ("RLE", "LRE", "RLO", "LRO", "RLI", "LRI", "FSI"):
            if ty in _ISO:
                lev[i] = stack[-1][0]
                t[i] = stack[-1][1] or ty
                rtl = ty == "RLI" or (ty == "FSI" and _first_strong(types, i + 1, match.get(i, n)) in ("R", "AL"))
            else:
                rtl = ty[0] == "R"
            cur = stack[-1][0]
            new = (cur + 1) | 1 if rtl else (cur + 2) & ~1
            if new <= 125 and not over_iso and not over_emb:
                stack.append((new, {"RLO": "R", "LRO": "L"}.get(ty), ty in _ISO))
                valid_iso += ty in _ISO
            elif ty in _ISO:
                over_iso += 1
            elif not over_iso:
                over_emb += 1
            if ty not in _ISO:
                lev[i] = stack[-1][0]
        elif ty == "PDI":
            if over_iso:
                over_iso -= 1
            elif valid_iso:
                over_emb = 0
                while not stack[-1][2]:
                    stack.pop()
                stack.pop()
                valid_iso -= 1
            lev[i] = stack[-1][0]
            t[i] = stack[-1][1] or ty
        elif ty == "PDF":
            if not over_iso:
                if over_emb:
                    over_emb -= 1
                elif not stack[-1][2] and len(stack) > 1:
                    stack.pop()
            lev[i] = stack[-1][0]
        else:
            lev[i] = stack[-1][0]
            if ty != "BN" and stack[-1][1]:
                t[i] = stack[-1][1]
    xl = list(lev)                                       # явные уровни: прогоны и sos/eos — по ним, не по I1–I2
    kept = [i for i in range(n) if types[i] not in _X9]   # X9
    runs = []
    for i in kept:                                       # X10: прогоны уровня и последовательности BD13
        if runs and xl[runs[-1][-1]] == xl[i]:
            runs[-1].append(i)
        else:
            runs.append([i])
    run_at, closing, pos = {r[0]: r for r in runs}, set(match.values()), {i: k for k, i in enumerate(kept)}
    for r in runs:
        if r[0] in closing:
            continue
        seq = list(r)
        while types[seq[-1]] in _ISO and seq[-1] in match and match[seq[-1]] in run_at:
            seq += run_at[match[seq[-1]]]
        lv = xl[seq[0]]
        k0, k1 = pos[seq[0]], pos[seq[-1]]
        before = xl[kept[k0 - 1]] if k0 else para
        after = para if (types[seq[-1]] in _ISO or k1 + 1 == len(kept)) else xl[kept[k1 + 1]]
        sos, eos = ("R" if max(lv, x) % 2 else "L" for x in (before, after))
        ts = [t[i] for i in seq]
        for k, ty in enumerate(ts):                      # W1
            if ty == "NSM":
                ts[k] = sos if not k else ("ON" if ts[k - 1] in _ISO | {"PDI"} else ts[k - 1])
        strong = sos
        for k, ty in enumerate(ts):                      # W2
            if ty in ("L", "R", "AL"):
                strong = ty
            elif ty == "EN" and strong == "AL":
                ts[k] = "AN"
        ts = ["R" if x == "AL" else x for x in ts]       # W3
        for k in range(1, len(ts) - 1):                  # W4
            if ts[k] == "ES" and ts[k - 1] == ts[k + 1] == "EN":
                ts[k] = "EN"
            elif ts[k] == "CS" and ts[k - 1] == ts[k + 1] and ts[k - 1] in ("EN", "AN"):
                ts[k] = ts[k - 1]
        k = 0
        while k < len(ts):                               # W5
            j = k
            while j < len(ts) and ts[j] == "ET":
                j += 1
            if j > k and ((k and ts[k - 1] == "EN") or (j < len(ts) and ts[j] == "EN")):
                ts[k:j] = ["EN"] * (j - k)
            k = max(j, k + 1)
        ts = ["ON" if x in ("ES", "ET", "CS") else x for x in ts]   # W6
        strong = sos
        for k, ty in enumerate(ts):                      # W7
            if ty in ("L", "R"):
                strong = ty
            elif ty == "EN" and strong == "L":
                ts[k] = "L"
        e = "R" if lv % 2 else "L"
        k = 0
        while k < len(ts):                               # N1, N2
            if ts[k] not in _NI:
                k += 1
                continue
            j = k
            while j < len(ts) and ts[j] in _NI:
                j += 1
            a = sos if not k else ("R" if ts[k - 1] in ("R", "EN", "AN") else ts[k - 1])
            b = eos if j == len(ts) else ("R" if ts[j] in ("R", "EN", "AN") else ts[j])
            ts[k:j] = [a if a == b else e] * (j - k)
            k = j
        for k, i in enumerate(seq):                      # I1, I2
            if xl[i] % 2 == 0:
                lev[i] = xl[i] + (1 if ts[k] == "R" else 2 if ts[k] in ("AN", "EN") else 0)
            else:
                lev[i] = xl[i] + (1 if ts[k] in ("L", "EN", "AN") else 0)
    tail = True                                          # L1: S и хвост из WS/изоляторов (и снятых X9) — уровень абзаца
    for i in range(n - 1, -1, -1):
        if types[i] == "S":
            lev[i], tail = para, True
        elif tail and (types[i] in ("WS", "LRI", "RLI", "FSI", "PDI") or types[i] in _X9):
            lev[i] = para
        else:
            tail = False
    order = list(kept)                                   # L2
    lv = [lev[i] for i in order]
    odd = [x for x in lv if x % 2]
    for level in range(max(lv, default=0), (min(odd) if odd else 1 << 30) - 1, -1):
        k = 0
        while k < len(order):
            if lv[k] < level:
                k += 1
                continue
            j = k
            while j < len(order) and lv[j] >= level:
                j += 1
            order[k:j], lv[k:j] = order[k:j][::-1], lv[k:j][::-1]
            k = j
    return para, lev, order


def shown(s):
    """Видимая строка слева направо: визуальный порядок `uax9` без невидимых знаков формата (Cf)."""
    return "".join(s[i] for i in uax9(s)[2] if unicodedata.category(s[i]) != "Cf")


def item_line(payload):
    """Строка пункта «• » блока «НУЖЕН ЧЕЛОВЕК» для одной причины — живым `card_notes`."""
    lines = G.card_notes([payload], 1, True).splitlines()
    assert lines[0] == G.W_HAND and lines[1].startswith("• "), lines
    return lines[1]


def head_holds(line):
    """Метка кода «• причина дословно: » по UAX#9 — первая видимая: абзац LTR, уровни метки 0, её знаки — первые позиции
    визуального порядка и в логическом порядке."""
    para, lev, order = uax9(line)
    n = len(ITEM_HEAD)
    return para == 0 and line.startswith(ITEM_HEAD) and all(x == 0 for x in lev[:n]) and order[:n] == list(range(n))


def old_act(words):
    """Близнец до правки D3 (кандидат 4b12f1d): слова причины сразу после «• » — голое «• »."""
    return words


def old_num(v):
    """Близнец до правки claims: `_num` кандидата 4b12f1d (строка — как есть)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return "{:,}".format(int(v)).replace(",", " ")
    return str(v)


class patched:
    """with patched(G, имя=замена): — подмена атрибута модуля на время блока, возврат в finally."""

    def __init__(self, mod, **kw):
        self.mod, self.kw, self.old = mod, kw, {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = getattr(self.mod, k)
            setattr(self.mod, k, v)

    def __exit__(self, *exc):
        for k, v in self.old.items():
            setattr(self.mod, k, v)


D3_ATTACKS = {                                   # доказанный bidi-вход (D3) × текст под штамп «🔎 сверено…» и пункт «• »
    "RLM+штамп": RLM + FORGED_CHECK,
    "RLO+пункт задом наперёд": RLO + FORGED_ITEM[::-1],
    "RLI без пары+штамп": RLI + FORGED_CHECK,
    "RLI+иврит+PDI+штамп": RLI + HEB + PDI + " " + FORGED_CHECK,
    "иврит первым+штамп": HEB + " " + FORGED_CHECK,
    "ALM+RLO+штамп": ALM + RLO + FORGED_CHECK,
    "лишний PDI+RLM+штамп": PDI + RLM + FORGED_CHECK,
    "RLE+RLO+PDF вперемешку+пункт": RLE + RLO + PDF + FORGED_ITEM[::-1],
}


# ══ D3 и claims: голдены ══════════════════════════════════════════════════════════════════════════════════════════

def test_d0_uax9_reference_known_answers():
    """Эталон сверен с ручным разбором правил UAX#9 на малых строках (иначе зелёный D3 стоял бы на сломанном эталоне):
    LTR; иврит (абзац RTL, порядок обратный); иврит внутри LTR; RLO…PDF; LTR-изолят в RTL-абзаце (P2 пропускает изолят);
    числа в RTL (W7, I2); лишний PDI; RLM первым; скобки — отказ эталона (N0 не реализован)."""
    assert uax9("abc") == (0, [0, 0, 0], [0, 1, 2])
    assert uax9(HEB) == (1, [1, 1, 1, 1], [3, 2, 1, 0])
    assert uax9("a " + HEB + " b") == (0, [0, 0, 1, 1, 1, 1, 0, 0], [0, 1, 5, 4, 3, 2, 6, 7])
    p, lev, order = uax9("a" + RLO + "bc" + PDF + "d")
    assert (p, [lev[i] for i in order], order) == (0, [0, 1, 1, 0], [0, 3, 2, 5]), (p, lev, order)
    assert uax9(HEB[0] + LRI + "ab" + PDI)[0] == 1 and uax9(HEB[0] + LRI + "ab" + PDI)[2] == [4, 2, 3, 1, 0]
    assert shown(HEB[0] + LRI + "ab" + PDI) == "ab" + HEB[0]
    assert uax9(HEB[0] + " 12")[2] == [2, 3, 1, 0] and shown(HEB[0] + " 12") == "12 " + HEB[0]
    assert uax9(LRI + HEB)[0] == 0 and uax9(PDI + HEB)[0] == 1          # P2: изолят пропущен; лишний PDI — не изолят
    assert uax9(RLM + "ab")[0] == 1 and shown(RLM + "ab") == "ab"
    try:
        uax9("a (b)")
    except AssertionError as e:
        assert "эталон не судит" in str(e), e
    else:
        raise AssertionError("скобки эталон не судит — обязан отказать")


def test_d1_bidi_attacks_label_first_twin_spoofed():
    """D3 (Codex TB-QA-2010C-HEAD-2011 п.1): причина без категории идёт `card_actions` → `card_notes` строкой «• …».
    Доказанный bidi-вход модели (RLM, RLO, RLI, ALM, иврит, лишний PDI, RLE/PDF) + текст под «🔎 сверено кодом» /
    «• язык…» → строка = «• причина дословно: LRI слова PDI», и по эталону UAX#9 метка кода — первая видимая (абзац
    LTR, уровни 0, первые позиции), слова — после неё. Близнец до правки (голое «• »): RLM / иврит / ALM делают абзац
    RTL и уводят «•» к правому краю; RLO показывает «• • язык…», которого в логической строке нет."""
    for name, payload in D3_ATTACKS.items():
        assert K.word_categories(payload) == [], name                    # ветка «слова как есть», не действие
        line = item_line(payload)
        assert line == ITEM_HEAD + LRI + payload + PDI, (name, line)
        assert head_holds(line) and shown(line).startswith(ITEM_HEAD), (name, uax9(line), shown(line))
        with patched(G, act_words=old_act):
            old = item_line(payload)
        assert old == "• " + payload and not old.startswith(ITEM_HEAD), (name, old)
    with patched(G, act_words=old_act):
        rtl = {k: uax9(item_line(D3_ATTACKS[k])) for k in ("RLM+штамп", "иврит первым+штамп", "ALM+RLO+штамп")}
        forged = shown(item_line(D3_ATTACKS["RLO+пункт задом наперёд"]))
    for k, (para, _lev, order) in rtl.items():
        assert para == 1 and order[-1] == 0, (k, para, order)            # «•» — у правого края, левее — слова модели
    assert FORGED_ITEM not in item_line(D3_ATTACKS["RLO+пункт задом наперёд"]) and forged == "• " + FORGED_ITEM, forged
    assert shown(item_line(D3_ATTACKS["RLO+пункт задом наперёд"])) == ITEM_HEAD + FORGED_ITEM   # видно — но после метки


def test_d2_e2e_raw_json_bidi_handoff():
    """Сквозной путь на сыром JSON модели (bidi-знаки экранированы \\uXXXX, как их отдаёт модель): handoff с RLM +
    штампом и с RLO + перевёрнутым пунктом → пункты «• » карточки — ровно действия ядра, причина модели — с меткой,
    эталон UAX#9 ставит метку первой; ни одна ЛОГИЧЕСКАЯ строка карточки не начинается с подделки ни в логическом
    порядке, ни в видимом по UAX#9. Мягкий перенос клиента внутри строки — вне этого замка (остаток R-WRAP, test_d5)."""
    for h in (D3_ATTACKS["RLM+штамп"], HAND_WORDS + " " + D3_ATTACKS["RLO+пункт задом наперёд"]):
        card, w = e2e_card(raw_reply(handoff=[h]))
        acts = G.card_actions(w.core.handoff(1))
        items = lines_on(card, "• ")
        assert items == ["• " + x for x in acts[:G.ACTIONS_MAX]] + (
            ["• ещё %d — в подробностях" % (len(acts) - G.ACTIONS_MAX)] if len(acts) > G.ACTIONS_MAX else []), card
        assert (ITEM_HEAD + LRI + h + PDI) in items, (h, items)
        for ln in card.splitlines():
            assert not ln.startswith(FORGED_CHECK) and not ln.startswith(FORGED_ITEM), ln
            if LRI in ln:
                assert head_holds(ln), (ln, uax9(ln))
            if not any(unicodedata.category(c) in ("Ps", "Pe") or not unicodedata.bidirectional(c) for c in ln):
                assert not shown(ln).startswith(FORGED_CHECK) and not shown(ln).startswith(FORGED_ITEM), ln


def test_d3_ordinary_reason_reads_and_code_actions_unchanged():
    """Позитивный близнец: обычная причина модели без категории читается целиком после метки (видимая строка — «•
    причина дословно: клиент просит фото байка»); причина кода со своим действием — прежний пункт без метки; слова кода
    без действия (K.ARRIVAL_CLAIM_WORDS, T.CONTRACT_WORDS) — тот же литерал с меткой: ветка источник не различает,
    поэтому метка говорит «дословно», а не «модели»; длинная причина — обрезка по прежнему пределу, «…» в изоляции."""
    line = item_line(HAND_WORDS)
    assert line == "• причина дословно: " + LRI + "клиент просит фото байка" + PDI and head_holds(line), line
    assert shown(line) == "• причина дословно: клиент просит фото байка", shown(line)
    lang = K.REASON_WORDS[K.R_LANGUAGE]
    assert item_line(lang) == "• " + G.CARD_ACTIONS[K.R_LANGUAGE], item_line(lang)
    assert K.word_categories(K.ARRIVAL_CLAIM_WORDS) == [K.R_ARRIVAL_CLAIM] and K.R_ARRIVAL_CLAIM not in G.CARD_ACTIONS
    assert K.word_categories(T.CONTRACT_WORDS) == []
    for code_words in (K.ARRIVAL_CLAIM_WORDS, T.CONTRACT_WORDS):
        assert item_line(code_words) == ITEM_HEAD + LRI + code_words + PDI, item_line(code_words)
    cut = item_line("Ж" * 200)
    assert cut == ITEM_HEAD + LRI + "Ж" * (G.REASON_SHOW_MAX - 1) + "…" + PDI and head_holds(cut), cut
    assert (G.BIDI_LRI, G.BIDI_PDI) == (chr(0x2066), chr(0x2069)) and G.W_ACT_WORDS == "причина дословно: "


def test_d4_fuzz_bidi_label_invariant():
    """Не один слог LTR, а свойство: 3000 случайных слов причины (seed 2011) из опасных классов UAX#9 — RLO/RLE/LRO/LRE/
    PDF, RLI/LRI/FSI/PDI, RLM/LRM/ALM, иврит (R), арабский (AL), арабские цифры (AN), EN/ES/ET/CS, NSM, BN, WS, S, ON,
    кириллица — у каждого метка кода первая видимая по эталону. Тот же набор на голом «• » уводит «•» с левого края у
    заметной доли — вход действительно опасен. Предел свойства — эталон без N0/L3/L4 (скобок во входе нет)."""
    import random
    rnd = random.Random(2011)
    pool = [RLO, RLE, LRO, LRE, PDF, RLI, LRI, FSI, PDI, RLM, LRM, ALM, HEB[0], HEB[1], chr(0x0628), chr(0x0663), "3",
            "+", "%", ",", chr(0x0301), chr(0x200B), " ", "\t", "•", "🔎", "—", ":", "с", "о", "a"]
    bad_old, seen = 0, 0
    for _ in range(3000):
        payload = "".join(rnd.choice(pool) for _ in range(rnd.randint(1, 24)))
        if K.word_categories(payload.strip()):
            continue
        seen += 1
        line = item_line(payload)
        assert head_holds(line), (ascii(payload), uax9(line))
        with patched(G, act_words=old_act):
            para, _lev, order = uax9(item_line(payload))
        bad_old += para == 1 or order[0] != 0
    assert seen >= 2900 and bad_old >= 300, (seen, bad_old)


WRAP_WIDTHS = list(range(28, 121, 4))             # колонок видимой строки: узкий телефон … широкий десктоп


def _cols(c):
    """Ширина знака в модели переноса: знак формата Cf (изоляторы, встраивания, метки bidi) — 0, эмодзи — 2, иначе 1."""
    if unicodedata.category(c) == "Cf":
        return 0
    return 2 if ord(c) >= 0x1F000 else 1


def wrap_rows(line, width):
    """МОДЕЛЬ мягкого переноса одной логической строки, не клиент Telegram: жадно, разрыв — после серии пробелов
    (UAX#14 LB18), хвостовые пробелы висят и ширины не занимают, слово шире строки рвётся по ширине → видимые строки
    в логическом порядке (склейка строк равна исходной)."""
    words, cur, sp = [], "", ""
    for c in line:
        if c == " ":
            sp += c
            continue
        if sp:
            words.append((cur, sp))
            cur, sp = "", ""
        cur += c
    words.append((cur, sp))
    rows, row, w = [], "", 0
    for word, spaces in words:
        ww = sum(map(_cols, word))
        if w and w + ww > width:
            rows.append(row)
            row, w = "", 0
        while ww > width:
            cut, acc = 0, 0
            while cut < len(word) and acc + _cols(word[cut]) <= width:
                acc += _cols(word[cut])
                cut += 1
            rows.append(word[:cut])
            word = word[cut:]
            ww = sum(map(_cols, word))
        row, w = row + word + spaces, w + ww + len(spaces)
        if w > width:
            rows.append(row)
            row, w = "", 0
    return rows + [row] if row else rows


def test_d5_soft_wrap_scope_named_residual():
    """Замок честности (отзыв проверяющего verify2_d3_attack v2): предел D3 и класса 2 — логическая строка. Вход
    проверяющего сквозным путём от сырого JSON: причины «x» + серия пробелов + штамп «🔎 сверено кодом: …» и «x» + серия
    + пункт «• язык…» (обе в пределе REASON_SHOW_MAX) и why с тем же штампом за сериями пробелов. Логически: пункты с
    меткой кода первой, ни одна строка карточки не начинается с подделки. Видимо (модель `wrap_rows`, ширины 28…120):
    первая видимая строка пункта — метка кода на КАЖДОЙ ширине; но продолжение переноса начинается словами поля, и
    подделка встаёт в начало видимой строки — у пункта и у «💭» (у «💭» — и до D3: класс унаследован). Это остаток
    R-WRAP, записанный поимённо: в простом тексте без таблицы знаков его не закрыть (схлопывание серий пробелов — не
    ремонт: замер круга d3 — адаптивный вход после схлопывания держит подделку у «💭» на 21 ширине из 24); направление —
    контейнер рендера для полей модели, решение К3/Codex. Любой ремонт R-WRAP переписывает этот замок вместе с ним."""
    hand = "x" + " " * (G.REASON_SHOW_MAX - 2 - len(FORGED_CHECK)) + FORGED_CHECK
    hand2 = "x" + " " * (G.REASON_SHOW_MAX - 2 - len(FORGED_ITEM)) + FORGED_ITEM
    why = "клиент спросил цену PCX" + (" " * 120 + FORGED_CHECK) * 3
    assert len(hand) == len(hand2) == G.REASON_SHOW_MAX - 1 and len(why) <= 600, (len(hand), len(hand2), len(why))
    card, _w = e2e_card(raw_reply(handoff=[hand, hand2], why=why))
    assert lines_on(card, "🔎 сверено") == [] and lines_on(card, FORGED_ITEM) == [], card
    items = [ln for ln in card.splitlines() if ln.startswith("• ")]
    assert items == [ITEM_HEAD + LRI + hand + PDI, ITEM_HEAD + LRI + hand2 + PDI], items
    assert all(head_holds(ln) for ln in items), [uax9(ln)[0] for ln in items]
    why_line = lines_on(card, G.W_WHY)
    assert len(why_line) == 1 and why_line[0].count(FORGED_CHECK) == 3, why_line
    forged = {}
    for name, line, head, fake in (("пункт → штамп", items[0], ITEM_HEAD, FORGED_CHECK),
                                   ("пункт → пункт", items[1], ITEM_HEAD, FORGED_ITEM),
                                   ("💭 → штамп", why_line[0], G.W_WHY, FORGED_CHECK)):
        forged[name] = []
        for wd in WRAP_WIDTHS:
            rows = wrap_rows(line, wd)
            assert "".join(rows) == line and rows[0].startswith(head), (name, wd, rows[:2])   # гарантия: первая видимая
            if any(r.startswith(fake[:16]) for r in rows[1:]):
                forged[name].append(wd)
    assert all(forged.values()), forged                    # R-WRAP жив: продолжение переноса — слова поля, не метка


def test_e1_num_internal_break_one_line():
    """claims (п.2): строка из `_num` идёт в «🔎 проверка кодом — без опоры: %s» и «🔎 сверено кодом: %s» мимо one_line;
    процент модели «30 U+2028 %» / «30 U+0085 %» (regex `\\s*` берёт любой пробел Юникода) рвал строку карточки. Теперь
    каждый разрыв splitlines — пробел; числа и строки без разрывов — прежние байт-в-байт."""
    for brk in BREAKS:
        assert G._num("30" + brk + "%") == "30 %", hex(ord(brk[0]))
        assert len(G.card_check([["процент", "30" + brk + "%"]]).splitlines()) == 1, hex(ord(brk[0]))
    for v in (40000, 7790.0, "30%", "35 000", "", None, True):
        assert G._num(v) == old_num(v), v
    assert G.card_check([["процент", "30" + LS + "%"]]) == G.W_CHECK_BAD % "процент 30 %"
    chk = {"nums": [["30" + NEL + "%", ["блок «ЦЕНА»"]]], "pay": True, "said": [], "more": 0}
    assert G.card_check([], chk) == G.W_CHECK_OK % "30 % — блок «ЦЕНА»", G.card_check([], chk)
    with patched(G, _num=old_num):
        assert len(G.card_check([["процент", "30" + LS + "%"]]).splitlines()) == 2
        assert G.card_check([], chk).splitlines()[1] == "% — блок «ЦЕНА»"


def test_e2_e2e_percent_with_break_one_check_line():
    """Сквозной путь: черновик модели «Предоплата 30⏎% до вечера.» (⏎ = U+2028 и U+0085) → `K.money_claims` берёт «30⏎%»
    → в низе карточки (от «💭») строка «🔎 проверка кодом — без опоры: процент 30 %» одна, строки «%…» нет. Близнец до
    правки — хвост «%» отдельной строкой. Обычный «30%» — прежняя строка. Ответ клиенту — дословно (остаток R1)."""
    for brk in (LS, NEL):
        text = "Предоплата 30" + brk + "% до вечера."
        assert K.money_claims(text, None) == [("процент", "30" + brk + "%")], K.money_claims(text, None)
        card, _w = e2e_card(raw_reply(text=text))
        bottom = card[card.index("💭"):]
        assert lines_on(bottom, "🔎 проверка") == [G.W_CHECK_BAD % "процент 30 %"], bottom
        assert not [ln for ln in bottom.splitlines() if ln.startswith("%")], bottom
        with patched(G, _num=old_num):
            card0, _w0 = e2e_card(raw_reply(text=text))
        bottom0 = card0[card0.index("💭"):].splitlines()
        assert (G.W_CHECK_BAD % "процент 30") in bottom0 and "%" in bottom0, bottom0
    card, _w = e2e_card(raw_reply(text="Предоплата 30% до вечера."))
    assert lines_on(card[card.index("💭"):], "🔎 проверка") == [G.W_CHECK_BAD % "процент 30%"], card


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
CLASS2D = ["test_c1_e2e_raw_json_attack_one_line_each_field", "test_c3_every_break_every_field_equals_space",
           "test_c9_bidi_prefix_anchor_every_model_field", "test_d1_bidi_attacks_label_first_twin_spoofed",
           "test_d2_e2e_raw_json_bidi_handoff", "test_d3_ordinary_reason_reads_and_code_actions_unchanged",
           "test_d4_fuzz_bidi_label_invariant"]
CLASS2N = ["test_e1_num_internal_break_one_line", "test_e2_e2e_percent_with_break_one_check_line"]
ACT_RET = "    return W_ACT_WORDS + BIDI_LRI + words + BIDI_PDI"
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
    ("wa_agent_tg.py", ACT_RET, "    return words", "D3: голое «• » (ни метки, ни изоляции)", CLASS2D),
    ("wa_agent_tg.py", ACT_RET, "    return BIDI_LRI + words + BIDI_PDI", "D3: изоляция без метки источника", CLASS2D),
    ("wa_agent_tg.py", ACT_RET, "    return W_ACT_WORDS + words", "D3: метка без изоляции", CLASS2D),
    ("wa_agent_tg.py", ACT_RET, '    return BIDI_LRI + words + BIDI_PDI + " " + W_ACT_WORDS', "D3: метка после слов",
     CLASS2D),
    ("wa_agent_tg.py", "CARD_ACTIONS.get(cat) or act_words(", "CARD_ACTIONS.get(cat) or (",
     "D3: card_actions мимо обёртки", CLASS2D),
    ("wa_agent_tg.py", "    return one_line(str(v))", "    return str(v)", "claims: _num без one_line", CLASS2N),
]


def test_zz_mutants():
    """Каждый мутант правки (20: класс 1 — 8, класс 2 — 6, D3 — 5, claims — 1) роняет хотя бы один голден своего класса
    (дети — параллельно, WA_AGENT_SRC = каталог мутанта во временном месте, RCFIX2010_CHILD=1)."""
    if os.environ.get(CHILD):
        return
    if os.environ.get("RCFIX2010_MUTANTS") != "1":
        # Мутации — проверка силы самих голденов, а не продукта; 20 детей идут дольше лимита gate.py (90 с на набор).
        # В обычном прогоне/гейте — явный пропуск; квитанция мутантов снимается отдельным запуском с RCFIX2010_MUTANTS=1.
        print("  SKIP мутанты: RCFIX2010_MUTANTS не 1 (квитанция мутантов — отдельным запуском)")
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
