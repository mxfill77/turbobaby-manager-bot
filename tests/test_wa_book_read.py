#!/usr/bin/env python3
"""Брони агента WhatsApp только на чтение (WABOOKTOOLS0210): «свободен ли байк на даты» и «когда кончается аренда».
Каждый исход — плюсом и минусом; правило занятости — копия QuotePrice.js:227–246. Всё на подделках: поддельный мост
(clients, fleet, дверь цены — счёт вызовов), временные очередь и база агента из test_wa_agent_model. Сети нет,
модели нет. Клиенты, имена, номера и даты — выдуманные.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import ast
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import test_wa_agent_model as TM  # noqa: E402
import wa_agent_knowledge as K  # noqa: E402
import wa_agent_model as WM  # noqa: E402
import wa_agent_svc as SV  # noqa: E402
import wa_book_read as B  # noqa: E402
import wa_history  # noqa: E402

T0 = TM.T0                                    # 2026-09-21 21:13 по Пхукету
NUM = TM.NUM                                  # выдуманный номер WhatsApp 10000000009
CONTACT = "Tel.1: +1 (000) 000-0009, inst @x-client"        # тот же номер в столбце «контакты»
SECRET_NAME, SECRET_DEP, SECRET_DEBT, SECRET_NOTE = "ИМЯ-КЛИЕНТА-СЕКРЕТ", 98761, 54329, "ПРИМЕЧАНИЕ-СЕКРЕТ"
ASK_FREE = "Есть ли свободный PCX 160 с 5 по 12 ноября?"
ASK_END = "Когда мне сдавать байк?"
DS, DE = datetime.date(2026, 11, 5), datetime.date(2026, 11, 12)


def row(bike, status, ds, de, b="OFF", contacts="", name=SECRET_NAME):
    return {"row": 2, "status": status, "auto_cancel": b, "bike": bike, "name": name, "date_start": ds,
            "date_end": de, "deposit": SECRET_DEP, "debt": SECRET_DEBT, "note": SECRET_NOTE, "contacts": contacts}


class Bridge(TM.FakeBridge):
    """Мост: узлы, парк и дверь цены из test_wa_agent_model + дверь clients (filter=all) со счётом вызовов.
    К строкам теста всегда добавлена строка чужой модели (XMAX, «Завершена»)."""

    def __init__(self, rows=(), available=True, door_reply=None):
        super().__init__()
        other = row("XMAX 300 4321", "Завершена", "2026-08-01 10:00", "2026-08-05 10:00", name="ДРУГОЙ")
        self.rows, self.available, self.door_reply = list(rows) + [other], available, door_reply
        self.client_calls, self.fail = [], False

    def quote_price(self, unit, ds, de):
        return self.door(unit, ds, de)

    def _call(self, action, **params):
        return self.read_doc(params.get("name"))

    def clients(self, filter="active"):
        self.client_calls.append(filter)
        if self.fail:
            return {"ok": False, "error": "timeout"}
        return {"ok": True, "data": {"clients": list(self.rows), "summary": {"count": len(self.rows)}}}

    def door(self, unit, ds, de):
        self.doors.append((unit, ds, de))
        if self.door_reply is not None:
            return self.door_reply if self.door_reply != "none" else None
        return {"ok": True, "days": 7, "day_price": 400, "total": 2800, "deposit": 3000, "season": {"label": "P3"},
                "model": "PCX 160", "available": self.available, "conflicts": 0 if self.available else 1}


def world(rows=(), **kw):
    """Мир test_wa_agent_model со снимком броней на поддельном мосту (как WA_AGENT_BOOK_READ=1)."""
    w = TM.World()
    br = Bridge(rows, **kw)
    w.bridge = br
    w.adapter.knowledge = K.Knowledge(br.read_doc)
    w.adapter.fleet, w.adapter.door = br.fleet, br.door
    w.adapter.book = B.Snapshot(lambda: br.clients(filter="all"), br.fleet)
    return w, br


def built(w, text, now=T0):
    rid = w.put(now, text)
    return w.adapter.build(TM.NUM, rid, now=now)


def hand(w):
    raw = w.drafts()[-1][4]
    return json.loads(raw) if raw else []


# ═══ свободен ли байк ═════════════════════════════════════════════════════════════════════

def test_avail_free_one_door_count_only():
    """+ free: свободный юнит есть, ОДНА дверь цены на него сказала available → «свободно 1 из 2», без строк броней."""
    w, br = world([row("PCX 160 1234", "В аренде", "2026-11-01 10:00", "2026-11-06 12:00"),
                   row("PCX 160 5678", "Завершена", "2026-11-05 10:00", "2026-11-10 12:00")])
    w.ask(ASK_FREE)
    assert br.client_calls == ["all"] and br.doors == [("PCX 160 5678", "2026-11-05", "2026-11-12")], br.doors
    user = w.call.calls[0][1]
    assert "НАЛИЧИЕ (таблица броней, снимок 0 мин назад" in user and "свободно 1 из 2" in user, user[-900:]
    for secret in (SECRET_NAME, str(SECRET_DEP), str(SECRET_DEBT), SECRET_NOTE, "2026-11-06 12:00", "inst"):
        assert secret not in user, secret
    assert w.adapter.last["info"]["avail"]["outcome"] == B.FREE
    assert hand(w) == [], hand(w)                                  # факт есть — «агент не видит» снят
    assert w.call.calls[0][0] == WM.SYSTEM_PROMPT_BOOK


def test_avail_busy_all_units_read():
    """+ busy: прочитаны все юниты модели, оба заняты (Бронь при B=ON — тоже занята) → «заняты все 2», двери нет."""
    w, br = world([row("PCX 160 1234", "Бронь", "2026-11-12 09:00", "2026-11-20 12:00", b="ON"),
                   row("PCX 160 5678", "в аренде ", "2026-10-30 10:00", "2026-11-05 09:00")])
    w.ask(ASK_FREE)
    a = w.adapter.last["info"]["avail"]
    assert a["outcome"] == B.BUSY and a["busy"] == 2 and br.doors == [], (a, br.doors)
    assert "заняты все 2" in w.call.calls[0][1]


def test_avail_door_disagrees_unknown():
    """− снимок говорит «свободен», дверь цены — нет → «не знаю», причина «нужен человек»; «Отправить» доходит до двери — решил человек (WACARDUI0510)."""
    w, br = world([row("PCX 160 1234", "Бронь", "2026-11-01 10:00", "2026-11-06 12:00")], available=False)
    w.ask(ASK_FREE)
    a = w.adapter.last["info"]["avail"]
    assert a["outcome"] == B.UNKNOWN and "разошлись" in a["why"] and len(br.doors) == 1, a
    assert "НАЛИЧИЕ: НЕИЗВЕСТНО" in w.call.calls[0][1]
    assert B.W_AVAIL_UNKNOWN in hand(w), hand(w)
    w.press("wa:send:1:1", 101)
    assert w.door.sends == [(TM.NUM, w.drafts()[0][3])], w.door.sends


def test_avail_door_silent_unknown():
    """− дверь цены не ответила (None) → «свободен» не сверен → «не знаю»."""
    w, br = world([], door_reply="none")
    w.ask(ASK_FREE)
    assert w.adapter.last["info"]["avail"]["outcome"] == B.UNKNOWN and len(br.doors) == 1


def test_avail_clients_door_fails_unknown():
    """− дверь clients не ответила → «не знаю», дверь цены не звана; + следующий вопрос после починки — факт."""
    w, br = world([])
    br.fail = True
    w.ask(ASK_FREE)
    a = w.adapter.last["info"]["avail"]
    assert a["outcome"] == B.UNKNOWN and "не прочитана" in a["why"] and br.doors == [], a
    br.fail = False
    _s, user, info = built(w, ASK_FREE, now=T0 + 60)
    assert info["avail"]["outcome"] == B.FREE and br.client_calls == ["all", "all"], br.client_calls


def test_avail_empty_sheet_is_not_all_free():
    """− дверь clients ok, но строк 0 → «не прочитан», а не «всё свободно»."""
    w, br = world([])
    br.rows = []
    _s, _u, info = built(w, ASK_FREE)
    assert info["avail"]["outcome"] == B.UNKNOWN and br.doors == [], info["avail"]
    assert B.rows_of({"ok": True, "data": {"clients": []}}) is None
    assert B.rows_of({"ok": True, "clients": [{"status": "Бронь"}]}) == [{"status": "Бронь"}]


def test_snapshot_ttl_10_min():
    """+ снимок в памяти 10 мин: два вопроса за 9 мин — один чтение clients; через 10 мин — второе."""
    w, br = world([])
    built(w, ASK_FREE, now=T0)
    built(w, ASK_FREE, now=T0 + 540)
    assert br.client_calls == ["all"] and br.fleets == 1, (br.client_calls, br.fleets)
    _s, user, _i = built(w, ASK_FREE, now=T0 + 600)
    assert br.client_calls == ["all", "all"], br.client_calls
    assert B.TTL == 600 and B.MAX_AGE == 1800


def test_snapshot_older_30_min_unknown():
    """Мост лёг после чтения: + снимку 20 мин — факт с возрастом «20 мин»; − снимку 31 мин — «не знаю»."""
    w, br = world([])
    built(w, ASK_FREE, now=T0)
    br.fail = True
    _s, user, info = built(w, ASK_FREE, now=T0 + 1200)
    assert info["avail"]["outcome"] == B.FREE and "снимок 20 мин назад" in user, user[-700:]
    _s, user, info = built(w, ASK_FREE, now=T0 + 1860)
    assert info["avail"]["outcome"] == B.UNKNOWN and "старше 30 мин" in info["avail"]["why"], info["avail"]
    assert br.client_calls == ["all", "all", "all"]                 # неудачное чтение снимок не освежило


def test_avail_model_not_in_fleet_unknown():
    """− модели нет в парке → «не знаю», дверь цены не звана; причина «нужен человек»."""
    w, br = world([])
    w.ask("Есть ли свободная Vespa 150 с 5 по 12 ноября?")
    a = w.adapter.last["info"]["avail"]
    assert a["outcome"] == B.UNKNOWN and a["why"] == "модель не названа точно или её нет в парке" and br.doors == [], a
    assert B.W_AVAIL_UNKNOWN in hand(w)


def test_live_fleet_name_format():
    """Имена живого парка вида «PCX 160CC WHITE PHUKET 3011» (как FLEET_NAMES test_suggest): + модель находится по
    словам клиента, юниты — все цвета, и адаптер даёт факт; − чужая модель не цепляется (XADV ≠ ADV, Forza нет)."""
    live = [{"name": n} for n in ("PCX 160CC WHITE PHUKET 3011", "PCX 160CC BLACK PHUKET 3012",
                                  "ADV 350CC BLACK PHUKET 5849", "XADV 750CC GREY PHUKET 4290",
                                  "MT-03 BLUE PHUKET 7788", "CB 300CC R 9011")]
    assert B.find_model(ASK_FREE, live) == "PCX 160CC"
    assert WM.units_of("PCX 160CC", live) == ["PCX 160CC WHITE PHUKET 3011", "PCX 160CC BLACK PHUKET 3012"]
    assert B.find_model("is XADV 750 free 5-12 Nov?", live) == "XADV 750CC"
    assert B.find_model("ADV 350 available?", live) == "ADV 350CC"
    assert B.find_model("MT-03 есть?", live) == "MT-03" and B.find_model("CB 300R свободен?", live) == "CB 300CC"
    assert B.find_model("Есть ли свободный Forza 350?", live) is None
    assert B.model_key("PCX 160 1234") == "PCX 160"
    w, br = world([])
    w.adapter.book = B.Snapshot(lambda: br.clients(filter="all"), lambda: {"ok": True, "data": {"bikes": live}})
    _s, user, info = built(w, ASK_FREE)
    assert info["avail"]["outcome"] == B.FREE and info["avail"]["units"] == 2, info["avail"]
    assert br.doors == [("PCX 160CC WHITE PHUKET 3011", "2026-11-05", "2026-11-12")], br.doors


def test_avail_overdue_unit_unchecked():
    """Просроченная активная аренда: − юнит «не проверено», и при втором занятом — «не знаю», а не «занят»;
    + при втором свободном — «свободно 1 из 2», не проверено 1."""
    overdue = row("PCX 160 5678", "В аренде", "2026-09-10 10:00", "2026-09-20 12:00")
    w, br = world([overdue, row("PCX 160 1234", "Бронь", "2026-11-04 10:00", "2026-11-09 12:00")])
    _s, _u, info = built(w, ASK_FREE)
    a = info["avail"]
    assert a["outcome"] == B.UNKNOWN and a["unchecked"] == 1 and a["busy"] == 1 and br.doors == [], a
    w2, br2 = world([overdue])
    _s, user, info = built(w2, ASK_FREE)
    a = info["avail"]
    assert a["outcome"] == B.FREE and a["free"] == 1 and a["unchecked"] == 1, a
    assert br2.doors == [("PCX 160 1234", "2026-11-05", "2026-11-12")], br2.doors


def test_avail_manual_status_unchecked():
    """− рукописный статус («долг») — юнит «не проверено», а не «свободен»."""
    st, why = B.unit_state("PCX 160 5678", [row("PCX 160 5678", "долг", "2026-08-01 10:00", "2026-08-05 10:00")],
                           DS, DE, B.local_now(T0))
    assert st == B.UNIT_UNCHECKED and why == "рукописный статус", (st, why)
    st, _ = B.unit_state("PCX 160 5678", [row("PCX 160 5678", "Завершена", "2026-11-05 10:00", "2026-11-09 10:00")],
                         DS, DE, B.local_now(T0))
    assert st == B.UNIT_FREE, st


def test_busy_rule_copy_of_quote_price():
    """Правило двери цены: Бронь — занята при любом B; «В аренде» при B=ON — свободна; пересечение дней
    включительно; имя — quoteNorm_ (регистр, кириллическая «с»); строка без дат — «не проверено»."""
    now = B.local_now(T0)

    def st(r):
        return B.unit_state("PCX 160 5678", [r], DS, DE, now)[0]
    assert st(row("PCX 160 5678", "Бронь", "2026-11-12 18:00", "2026-11-14 10:00", b="ON")) == B.UNIT_BUSY
    assert st(row("PCX 160 5678", "В аренде", "2026-11-01 10:00", "2026-11-05 08:00", b="ON")) == B.UNIT_FREE
    assert st(row("PCX 160 5678", "В аренде", "2026-11-01 10:00", "2026-11-05 08:00")) == B.UNIT_BUSY
    assert st(row("PCX 160 5678", "Бронь", "2026-11-13 09:00", "2026-11-15 10:00")) == B.UNIT_FREE
    assert st(row("PCX 160 5678", "Бронь", "2026-11-01 09:00", "2026-11-04 23:00")) == B.UNIT_FREE
    assert st(row("pсx 160 5678 ", "Бронь", "2026-11-06 09:00", "2026-11-07 10:00")) == B.UNIT_BUSY   # «с» кириллицей
    assert st(row("PCX 160 5678", "Бронь", None, "2026-11-07 10:00")) == B.UNIT_UNCHECKED
    assert st(row("PCX 160 1234", "Бронь", "2026-11-06 09:00", "2026-11-07 10:00")) == B.UNIT_FREE   # чужой юнит
    assert B.day_of("05.11.2026 , 14:00") == DS and B.day_of("2026-11-12 17:30") == DE and B.day_of("x") is None


def test_avail_without_dates_no_table():
    """− «свободен ли» без двух дат — таблица и дверь не званы, причина «агент не видит» остаётся, как раньше."""
    w, br = world([])
    w.ask("Есть ли свободный PCX 160?")
    assert br.client_calls == [] and br.doors == [] and br.fleets == 0, (br.client_calls, br.doors)
    assert K.REASON_WORDS[K.R_AVAILABILITY] in hand(w), hand(w)
    assert "без двух дат" in w.adapter.last["info"]["book_words"]


def test_booking_intent_reason():
    """+ «забронируйте» — факт наличия есть, но бронь делает человек: причина; «Отправить» доходит до двери — решил человек (WACARDUI0510)."""
    w, br = world([])
    w.ask("Забронируйте PCX 160 с 5 по 12 ноября")
    assert w.adapter.last["info"]["avail"]["outcome"] == B.FREE
    h = hand(w)
    assert B.W_BOOKING in h and K.REASON_WORDS[K.R_AVAILABILITY] not in h, h
    w.press("wa:send:1:1", 101)
    assert w.door.sends == [(TM.NUM, w.drafts()[0][3])], w.door.sends


# ═══ когда кончается аренда ═══════════════════════════════════════════════════════════════

def test_rental_one_active_end():
    """+ одна активная аренда по номеру → модель, дата и время конца; имя, залог, долг и контакты — нет."""
    w, br = world([row("PCX 160 5678", "В аренде", "2026-09-18 10:00", "2026-09-25 17:30", contacts=CONTACT)])
    w.ask(ASK_END)
    r = w.adapter.last["info"]["rental"]
    assert r["outcome"] == B.FOUND and len(r["rentals"]) == 1, r
    user = w.call.calls[0][1]
    assert "АРЕНДА КЛИЕНТА (таблица броней по номеру WhatsApp, снимок 0 мин назад; аренд: 1): PCX 160 — " \
           "конец 25.09.2026 17:30 (Пхукет)" in user, user[-700:]
    for secret in (SECRET_NAME, str(SECRET_DEP), str(SECRET_DEBT), SECRET_NOTE, "@x-client", "5678"):
        assert secret not in user, secret
    assert set(r["rentals"][0]) == {"model", "end", "expired"}
    assert hand(w) == [] and br.doors == [], hand(w)


def test_rental_expired_words_no_date():
    """− срок прошёл → «по таблице срок истёк — уточню у менеджера», даты фактом нет, причина «нужен человек»."""
    w, br = world([row("PCX 160 5678", "В аренде", "2026-09-10 10:00", "2026-09-21 20:00", contacts=CONTACT)])
    w.ask(ASK_END)
    r = w.adapter.last["info"]["rental"]
    assert r["outcome"] == B.FOUND and r["expired"] == 1, r
    user = w.call.calls[0][1]
    assert "PCX 160 — по таблице срок истёк" in user and B.EXPIRED_WORDS in user, user[-700:]
    assert "21.09.2026 20:00" not in user and "2026-09-21 20:00" not in user
    assert B.W_RENTAL_EXPIRED in hand(w), hand(w)


def test_rental_several_by_dates():
    """+ несколько активных → все, по датам конца (раньше — первым)."""
    w, br = world([row("XMAX 300 4321", "В аренде", "2026-09-15 10:00", "2026-10-05 12:00", contacts=CONTACT),
                   row("PCX 160 1234", "В аренде", "2026-09-20 10:00", "2026-09-28 09:00", contacts=CONTACT)])
    _s, user, info = built(w, "When do I need to return the bike?")
    r = info["rental"]
    assert [x["model"] for x in r["rentals"]] == ["PCX 160", "XMAX 300"], r["rentals"]
    assert user.index("конец 28.09.2026 09:00") < user.index("конец 05.10.2026 12:00"), user[-700:]
    assert "аренд: 2" in user


def test_rental_not_found_is_unknown_not_none():
    """− номер не найден → «не знаю», а не «аренды нет»; причина «нужен человек»."""
    w, br = world([row("PCX 160 5678", "В аренде", "2026-09-18 10:00", "2026-09-25 17:30",
                       contacts="Tel.1: +7 912 345-67-89")])
    w.ask(ASK_END)
    r = w.adapter.last["info"]["rental"]
    assert r["outcome"] == B.UNKNOWN and "не «аренды нет»" in r["why"], r
    user = w.call.calls[0][1]
    assert "АРЕНДА КЛИЕНТА: НЕИЗВЕСТНО" in user and "НЕ говори «у вас нет аренды»" in user, user[-600:]
    assert B.W_RENTAL_UNKNOWN in hand(w), hand(w)


def test_rental_inactive_rows_ignored():
    """− по номеру есть только «Завершена», «Бронь» и «В аренде» при B=ON → активной нет → «не знаю»."""
    rows = [row("PCX 160 5678", "Завершена", "2026-08-01 10:00", "2026-08-05 10:00", contacts=CONTACT),
            row("PCX 160 1234", "Бронь", "2026-11-01 10:00", "2026-11-05 10:00", contacts=CONTACT),
            row("XMAX 300 4321", "В аренде", "2026-09-18 10:00", "2026-09-25 10:00", b="ON", contacts=CONTACT)]
    got = B.rental_end(NUM, rows, 0, "", B.local_now(T0), WM.model_of_name)
    assert got["outcome"] == B.UNKNOWN and got["rentals"] == [], got
    rows[2]["auto_cancel"] = "OFF"
    assert B.rental_end(NUM, rows, 0, "", B.local_now(T0), WM.model_of_name)["outcome"] == B.FOUND


def test_rental_last_9_digits():
    """Последние 9 цифр: + местный формат и сплошной номер рядом с другим; − отличие в последней цифре."""
    now = B.local_now(T0)

    def find(contacts, number="66812345678"):
        r = [row("PCX 160 5678", "В аренде", "2026-09-18 10:00", "2026-09-25 17:30", contacts=contacts)]
        return B.rental_end(number, r, 0, "", now, WM.model_of_name)["outcome"]
    assert find("Tel.1: 081-234-5678") == B.FOUND
    assert find("tel 66812345678 / 79001112233") == B.FOUND
    assert find("+66 81 234 5679") == B.UNKNOWN
    assert find("@insta66812345678x") == B.FOUND                    # цифры столбца, а не формат
    assert find("Tel.1: 081-234-5678", number="5678") == B.UNKNOWN  # номер короче 9 цифр
    assert B.phone_keys("Tel.1: +7 912 345-67-89, Tel.2: 0812345678") == {"123456789", "812345678"}


def test_rental_end_without_time_unknown():
    """− конец без времени → «дата и время конца не прочитаны» → «не знаю»."""
    rows = [row("PCX 160 5678", "В аренде", "2026-09-18 10:00", "2026-09-25", contacts=CONTACT)]
    got = B.rental_end(NUM, rows, 0, "", B.local_now(T0), WM.model_of_name)
    assert got["outcome"] == B.UNKNOWN and "не прочитаны" in got["why"], got
    assert B.moment_of("2026-09-25 17:30") == datetime.datetime(2026, 9, 25, 17, 30)


def test_rental_snapshot_unread_unknown():
    """− таблица не прочитана → «не знаю», причина; дверь цены не звана."""
    w, br = world([row("PCX 160 5678", "В аренде", "2026-09-18 10:00", "2026-09-25 17:30", contacts=CONTACT)])
    br.fail = True
    w.ask(ASK_END)
    assert w.adapter.last["info"]["rental"]["outcome"] == B.UNKNOWN and B.W_RENTAL_UNKNOWN in hand(w)


# ═══ вопросы, выключатель, журнал, импорты ═════════════════════════════════════════════

def test_rental_question_goldens():
    """Голдены детекта — выдуманные (живых фраз в этом заходе нет): 6 RU + 6 EN позитивов, 8 негативов."""
    pos = ["Когда мне сдавать байк?", "Когда заканчивается аренда?", "До какого числа у меня скутер?",
           "Во сколько нужно вернуть байк?", "Подскажите срок аренды моей", "когда кончается моя аренда",
           "When do I need to return the bike?", "When does my rental end?", "Until when do I have the scooter?",
           "my rental expires when?", "When should I bring it back?", "what time is the bike due back, when?"]
    neg = ["Сколько стоит аренда PCX на неделю?", "Когда можно забрать байк?", "Когда будет доставка?",
           "Когда заканчивается акция?", "Когда вернут депозит?", "When can I pick up the bike?",
           "How much is the rent?", "Привет! Есть ли свободный PCX 160 с 5 по 12 ноября?"]
    assert [p for p in pos if not B.rental_end_ask(p)] == [], [p for p in pos if not B.rental_end_ask(p)]
    assert [n for n in neg if B.rental_end_ask(n)] == [], [n for n in neg if B.rental_end_ask(n)]


def test_avail_question_goldens():
    pos = ["Есть ли свободный PCX 160 с 5 по 12 ноября?", "PCX 160 на 5-12 ноября есть?",
           "Is PCX 160 available from Nov 5 to Nov 12?", "Do you have PCX 160 for 10.12 - 20.12?",
           "Хочу забронировать XMAX 300 с 1 по 8 декабря", "any free nmax?"]
    neg = ["Сколько стоит PCX 160 с 5 по 12 ноября?", "Когда мне сдавать байк?", "Спасибо!",
           "How much is PCX 160 from Nov 5 to Nov 12?"]
    assert [p for p in pos if not B.avail_ask(p)] == [] and [n for n in neg if B.avail_ask(n)] == []
    assert B.book_intent("Забронируйте PCX") and B.book_intent("I want to book it") and not B.book_intent(ASK_FREE)


def test_no_question_no_table_prompt_as_before():
    """− о бронях не спрашивают → таблица не читается, промпт пользователя — байт-в-байт как без снимка."""
    w, br = world([])
    rid = w.put(T0, "Доставка в Патонг есть?")
    s1, u1, _ = w.adapter.build(NUM, rid, now=T0)
    book, w.adapter.book = w.adapter.book, None
    s0, u0, _ = w.adapter.build(NUM, rid, now=T0)
    assert u1 == u0 and br.client_calls == [], br.client_calls
    assert s0 == WM.SYSTEM_PROMPT and s1 == WM.SYSTEM_PROMPT_BOOK and s0 != s1
    assert "«НАЛИЧИЕ»" in s1 and "«АРЕНДА КЛИЕНТА»" in s1 and "НАЛИЧИЕ" not in s0
    assert "Наличие и брони ты не видишь" in s0 and "Наличие и брони ты не видишь" not in s1


def test_svc_switch_and_filter_all():
    """Выключатель WA_AGENT_BOOK_READ: − нет — снимка нет и строка «выкл»; + 1 — снимок на clients(filter=all)."""
    w = TM.World()
    br = Bridge([])
    env = {"queue_db": w.qpath, "agent_db": w.dbpath, "mirror_db": "", "tg_token": "", "show_chat": ""}
    off, _ = SV.make_model(env, bridge=br, call=lambda s, u: ("", {}))
    on, _ = SV.make_model(env, bridge=br, call=lambda s, u: ("", {}), book=True)
    assert off.book is None and isinstance(on.book, B.Snapshot), (off.book, on.book)
    on.book.get(T0)
    assert br.client_calls == ["all"] and br.fleets == 1, br.client_calls
    for flag, word in ((None, "выкл"), ("1", "вкл"), ("да", "выкл")):
        lines = []
        SV.build(dict(env, agent_db=w.dbpath + str(flag)), environ={} if flag is None else {SV.F_BOOK: flag},
                 line=lines.append)
        said = [ln for ln in lines if ln.startswith("брони (WA_AGENT_BOOK_READ): ")]
        assert len(said) == 1 and said[0].split(": ", 1)[1].startswith(word), (flag, said)


def test_main_passes_switch():
    """Служба: main передаёт WA_AGENT_BOOK_READ в make_model (+ «1» — вкл, − нет — выкл). Руки main подменены."""
    class Stop(Exception):
        pass

    def build(*a, **k):
        raise Stop()
    w, seen = TM.World(), []
    env = {"queue_db": w.qpath, "agent_db": w.dbpath, "mirror_db": "", "tg_token": "", "show_chat": "",
           "log_path": w.dbpath + ".log"}
    saved = (SV.env_of, SV.make_model, SV.build, dict(os.environ))
    try:
        SV.env_of, SV.build = (lambda: env), build
        SV.make_model = lambda e, line=None, bridge=None, call=None, lessons=False, book=False, cache=None: \
            seen.append(book) or (None, "")
        for flag in ("1", None):
            os.environ["WA_AGENT_DRAFTS"] = "1"
            os.environ.pop(SV.F_BOOK, None)
            if flag:
                os.environ[SV.F_BOOK] = flag
            try:
                SV.main()
            except Stop:
                pass
    finally:
        SV.env_of, SV.make_model, SV.build = saved[:3]
        os.environ.clear()
        os.environ.update(saved[3])
    assert seen == [True, False], seen


def test_journal_numbers_only():
    """Журнал: исходы и числа; ни номера, ни имени, ни модели, ни дат клиента."""
    w, br = world([row("PCX 160 5678", "В аренде", "2026-09-18 10:00", "2026-09-25 17:30", contacts=CONTACT)])
    w.ask("Когда кончается моя аренда? И есть ли свободный PCX 160 с 5 по 12 ноября?")
    said = [ln for ln in w.lines if ln.startswith("брони:")]
    assert len(said) == 1 and "наличие free" in said[0] and "аренда found (найдено 1" in said[0], said
    for s in (NUM, SECRET_NAME, "PCX", "25.09", "2026-09-25"):
        assert not any(s in ln for ln in w.lines), s


def test_phuket_offset_and_local_now():
    assert B.PHUKET_OFFSET == wa_history.PHUKET_OFFSET
    assert B.local_now(T0) == datetime.datetime(2026, 9, 21, 21, 13, 20), B.local_now(T0)


def test_no_network_imports():
    src = open(os.path.join(os.environ.get("WA_AGENT_SRC") or ROOT, "wa_book_read.py"), encoding="utf-8").read()
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names <= {"datetime", "re", "wa_agent_knowledge"}, names


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:200])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
