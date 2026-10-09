#!/usr/bin/env python3
"""K3-FIX 09.10.2026 (поручение TB-K3-TARGETED-FIXES-0910) — регрессия находок стенда К3 на кандидате f2f7295:
F3 (оплата не в валюте аренды засчитывалась), F4 (неполный PDF уходил клиенту), F5 (rules при устаревшем снимке — FACT),
N2 (после проигранного захвата карточка говорила «текст: ушёл» и молчала о PDF, поздний ответ перетирал исход старта).
Каждый тест утверждает ПРАВИЛЬНОЕ поведение; на f2f7295 тесты F3/F4/F5/N2 падают, на ремонте проходят.

Всё на подделках (`test_wa_attach_svc.World`, двери и Bot API — подделки): сети нет, модель, мост, Telegram, WhatsApp
не зовутся. PDF — живого формата (`k3_pdf_fixture`, без библиотек)."""
import hashlib
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.append(HERE)

import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import wa_agent_knowledge as K  # noqa: E402
import wa_agent_tools as T  # noqa: E402
import contract_door_snaps as S  # noqa: E402
import k3_pdf_fixture as PF  # noqa: E402
import test_wa_attach_svc as AS  # noqa: E402
import wa_agent_svc as SVC  # noqa: E402

AT = 1_790_000_000.0
NUM_NINA = "66815550004"
NINA_BIKE = "Click 160 5555"


# ═══ F3: деньги — только по совпадению суммы и валюты ═══════════════════════════════════════════════

def _tx(items):
    return {"ok": True, "checked": {"span_from": "2026-09-01", "span_to": "2026-10-03", "rows_scanned": 120,
                                    "truncated": False, "complete": True}, "total": {"THB": 1}, "items": list(items)}


def _item(row, amount, currency="THB", booking="bk-N", category="rental", what="аренда"):
    d = "Click 5555 +%s %s %s" % (amount, currency, what)
    return {"row": row, "date": "2026-09-16", "recorded_at": "2026-09-16T05:00:00.000Z", "amount": amount,
            "currency": currency, "category": category, "bike": NINA_BIKE, "description": d, "raw": d,
            "msg_id": "-100311:5%02d:m%d" % (row, row), "link": "https://t.me/c/311/5%02d" % row, "status": "recorded",
            "booking_id": booking}


def _cash(items, args=None):
    r = T.cash_result(_tx(items), at=AT)
    r["req"] = T.request_key("cash", args or {"bike": NINA_BIKE})
    return r


def _rent_row(booking="bk-N", currency=None):
    row = {"status": "В аренде", "contacts": "+66 81 555 0004", "bike": NINA_BIKE, "booking_id": booking,
           "date_start": "2026-09-15 10:00", "date_end": "2026-09-20 10:00"}
    if currency:
        row["currency"] = currency
    return row


def _rental(booking="bk-N", currency=None):
    r = T.rental_result({"ok": True, "rows": [_rent_row(booking, currency)]}, at=AT)
    r["req"] = T.request_key("rental", {})
    return r


def _contract(booking="bk-N", currency=None):
    """Договор Нины (снимок двери one_complete), привязанный кодом к её аренде (как test_agent_dedup.contract_res)."""
    r = T.contract_result(S.snap("one_complete"), at=AT, number=NUM_NINA, rental=_rental(booking, currency))
    assert r["outcome"] == T.FACT, r
    r["req"] = T.request_key("contract", {"phone": NUM_NINA})
    return r


def _hist(text):
    r = T.history_result([{"who": "клиент", "text": text}], at=AT)
    r["req"] = T.request_key("history", {})
    return r


def test_f3_usd_rent_row_not_confirmed():
    """K04: строка «оплата аренды» только в USD при аренде в THB (договор привязан) — оплата НЕ подтверждена, причина
    словами («валюта не совпала»); близнец в THB — подтверждена."""
    facts = T.accepted([_rental(), _cash([_item(3, 150, "USD")]), _contract()])
    assert T.pay_confirmed(facts) is False, "USD засчитан оплатой аренды в THB"
    ok, why = T.pay_verdict(facts)
    assert not ok and "валюта не совпала" in why and "USD" in why and "THB" in why, why
    assert T.calc(facts)["sums"] == {"оплата аренды USD": 150}            # суммы по валютам — как были
    twin = T.accepted([_rental(), _cash([_item(3, 4900, "THB")]), _contract()])
    assert T.pay_confirmed(twin) is True and T.pay_verdict(twin) == (True, "")


def test_f3_money_roles_names_currency():
    """Текст «оплата получена» при строке только в USD — причина «оплата не подтверждена сверкой» со словами о валюте."""
    facts = T.accepted([_rental(), _cash([_item(3, 150, "USD")]), _contract()])
    got = T.money_roles("Оплата получена, аренда оплачена полностью.", facts)
    assert [w for w, _ in got] == [T.PAY_WORDS], got
    assert "валюта не совпала" in got[0][1], got


def test_f3_contract_carries_rent_currency():
    """Только договор вторым источником (строки листа среди фактов нет): валюта аренды — та, к которой код привязал
    договор (`rent_currency`); THB — подтверждено (как было), USD-строка — нет."""
    c = _contract()
    assert c["facts"][0].get("rent_currency") == "THB", c["facts"]
    assert T.pay_confirmed(T.accepted([_cash([_item(3, 4900)]), c])) is True
    assert T.pay_confirmed(T.accepted([_cash([_item(3, 4900, "USD")]), _contract()])) is False


def test_f3_currency_unknown_not_confirmed():
    """Валюта аренды неизвестна (договор без rent_currency — прежняя запись — и строки листа нет) — не подтверждаем."""
    c = _contract()
    c["facts"][0].pop("rent_currency", None)
    facts = T.accepted([_cash([_item(3, 4900)]), c])
    ok, why = T.pay_verdict(facts)
    assert not ok and "валюта аренды bk-N неизвестна" in why, why


def test_f3_currency_conflict_not_confirmed():
    """Лист говорит THB, а договор привязан к аренде с другой валютой — валюта аренды не одна, не подтверждаем."""
    c = _contract(currency="USD")
    facts = T.accepted([_rental(), _cash([_item(3, 4900)]), c])
    assert T.rent_currency(facts, "bk-N") is None
    assert T.pay_confirmed(facts) is False


def test_f3_backing_only_rent_currency():
    """Подтверждена THB-строкой 4900; текст подтверждает получение 150 — у аренды 150 есть только в USD → причина
    человеку (сумма и валюта не совпали); 4900 бат — опора есть."""
    facts = T.accepted([_rental(), _cash([_item(3, 4900), _item(4, 150, "USD")]), _hist("оплатил 4900 бат")])
    assert T.pay_confirmed(facts) is True
    assert [w for w, _ in T.money_roles("Оплата 150 получена.", facts)] == [T.PAY_WORDS]
    assert T.money_roles("Оплата 4900 бат получена.", facts) == []


# ═══ F5: rules при устаревшем снимке — НЕИЗВЕСТНО, а не FACT «сейчас» ═══════════════════════════════════

def _node(age, max_stale=1800):
    n = {"name": "business_rules", "read": True, "text": "ПРАВИЛО-ТЕСТ: 03.10.2026-1", "len": 26,
         "taken_at": AT - age, "why": ""}
    if max_stale is not None:
        n["max_stale"] = max_stale
    return n


def test_f5_stale_snapshot_unknown():
    r = T.rules_result(_node(7200), at=AT)
    assert r["outcome"] == T.UNKNOWN and r["facts"] == [], r
    assert "снимок правил устарел" in r["reason"] and "120 мин" in r["reason"] and "30 мин" in r["reason"], r
    assert not [f for f in T.accepted([dict(r, req="rules []")]) if f["kind"] == "rules"]


def test_f5_control_fresh_snapshot_fact():
    """КОНТРОЛЬ (зелёный и до ремонта): снимок моложе предела — FACT, как было; узел без предела — FACT, как было."""
    for node in (_node(60), _node(7200, max_stale=None)):
        r = T.rules_result(node, at=AT)
        assert r["outcome"] == T.FACT and r["version"] == "26 симв.", r


def test_f5_through_knowledge_and_door():
    """Как в K12: снимок снят `Knowledge`, мост перестал отдавать узел, прошло 2 ч — дверь rules через `call_tool`
    отдаёт НЕИЗВЕСТНО с причиной; модели не уходит устаревшее как свежее."""
    state = {"ok": True}

    def read_doc(name):
        return {"ok": True, "text": "ПРАВИЛО-ТЕСТ"} if state["ok"] else {"ok": False, "error": "stand_read_failed"}
    k = K.Knowledge(read_doc, names=("business_rules",), max_age=600)
    k.refresh(AT)
    state["ok"] = False
    k.refresh(AT + 7200)
    clock = lambda: AT + 7200                                              # noqa: E731
    r = T.call_tool("rules", {}, {"rules": lambda: k.snap.get("business_rules")}, clock=clock)
    assert r["outcome"] == T.UNKNOWN and "снимок правил устарел" in r["reason"], r
    assert "НЕИЗВЕСТНО" in T.render([r]) or "unknown" in T.render([r])


# ═══ F4: скелет PDF — ТЕ ЖЕ байты, что уйдут двери, ДО двери ═══════════════════════════════════════

def _markers_kept(b):
    tail = b[-1024:]
    return b.startswith(b"%PDF-") and b"startxref" in tail and b"%%EOF" in tail


def _swap(b, old, new):
    assert len(old) == len(new) and b.count(old) >= 1, (old, new)
    return b.replace(old, new, 1)


def _bad_pdfs():
    """Отрицательные PDF: маркеры начала/конца СОХРАНЕНЫ, повреждены таблица ссылок и/или дерево страниц."""
    good = PF.classic(b"K3 negative")
    xref_at = int(good.rsplit(b"startxref\n", 1)[1].split(b"\n", 1)[0])
    entry1 = good[xref_at:].split(b"\n")[3]                     # запись объекта 1 (каталог)
    shifted = b"%010d 00000 n " % (int(entry1[:10]) + 3)
    out = {
        "xref: слово «xref» испорчено": _swap(good, b"xref\n0 6", b"xrex\n0 6"),
        "xref: смещение каталога сдвинуто": _swap(good, entry1, shifted),
        "startxref: указывает мимо таблицы": good.replace(b"startxref\n%d\n" % xref_at, b"startxref\n%d\n" % (xref_at - 7)),
        "xref: запись не разбирается": _swap(good, entry1, b"00000x0015 00000 n "),
        "дерево страниц: /Count 0": _swap(good, b"/Count 1", b"/Count 0"),
        "дерево страниц: не /Pages": _swap(good, b"/Type /Pages", b"/Type /Pagez"),
        "дерево страниц: ребёнок вне таблицы": _swap(good, b"/Kids [3 0 R]", b"/Kids [9 0 R]"),
        "каталог: не /Catalog": _swap(good, b"/Type /Catalog", b"/Type /Catalox"),
        "каталог: нет /Pages": _swap(good, b"/Pages 2 0 R", b"/Pagex 2 0 R"),
    }
    xs = PF.xref_stream(b"K3 negative xs")
    comp_at = xs.rfind(b">>\nstream\n") + len(b">>\nstream\n")             # сжатые байты потока ссылок /XRef
    out["поток ссылок: сжатые байты испорчены"] = xs[:comp_at + 2] + bytes(b ^ 0x5A for b in xs[comp_at + 2:comp_at + 12]) \
        + xs[comp_at + 12:]
    out["поток объектов: заголовок смещений испорчен"] = _swap(PF.xref_stream(b"K3 negative os", predictor=False),
                                                              b"/N 4 /First", b"/N 9 /First")
    inc = PF.incremental(b"K3 negative inc")
    prev = int(inc.rsplit(b"/Prev ", 1)[1].split(b" ", 1)[0])
    out["цепочка /Prev: прежняя таблица не найдена"] = inc.replace(b"/Prev %d " % prev, b"/Prev %d " % (prev + 2), 1)
    out["только маркеры"] = b"%PDF-1.4\n" + b"x" * 500 + b"\nstartxref\n0\n%%EOF\n"
    return out


def test_f4_level_named_and_good_pass():
    """Заявленный уровень назван дословно (и чего НЕ проверяет); целые PDF трёх устройств проходят."""
    assert "НЕ проверяется" in X.PDF_LEVEL and "НЕ «PDF исправен»" in X.PDF_LEVEL, X.PDF_LEVEL
    for name, data in (("classic", PF.classic(b"x")), ("xref_stream+PNG", PF.xref_stream(b"x")),
                       ("xref_stream", PF.xref_stream(b"x", predictor=False)), ("incremental", PF.incremental(b"x"))):
        ok, why = X.pdf_shape(data)
        assert ok and why == "", (name, why)


def test_f4_negative_pdfs_stopped():
    """Обязательный отрицательный: маркеры начала/конца на месте, а таблица ссылок и/или дерево страниц повреждены —
    проверка останавливает КАЖДЫЙ, с причиной словами."""
    for name, data in _bad_pdfs().items():
        assert _markers_kept(data), "фикстура «%s» потеряла маркеры — не тот случай" % name
        ok, why = X.pdf_shape(data)
        assert not ok and why, "«%s» прошёл проверку скелета" % name


def test_f4_truncated_stopped():
    """Обрезанный посреди потока (как P3 стенда: 60 % байтов) — нет %%EOF — остановлен."""
    good = PF.classic(b"K3 truncated")
    ok, why = X.pdf_shape(good[:int(len(good) * 0.6)])
    assert not ok and "%%EOF" in why, why
    assert X.pdf_shape(b"%PDF-1.4 signed contract bytes")[0] is False       # прежняя фикстура — не PDF


def test_f4_level_limit_named():
    """Предел уровня назван тестом, а не скрыт: порча потока СОДЕРЖИМОГО страницы (скелет цел) уровнем НЕ ловится."""
    good = PF.classic(b"K3 limit")
    broken = _swap(good, b"BT /F1 12 Tf", b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b")
    assert X.pdf_shape(broken) == (True, ""), "уровень стал шире заявленного — обнови PDF_LEVEL"


def _with_pdf(data):
    old = (AS.PDF, AS.SHA)
    AS.PDF, AS.SHA = data, hashlib.sha256(data).hexdigest()
    return old


def test_f4_broken_pdf_not_sent_in_service():
    """Служба: PDF верно привязанного договора с битой таблицей ссылок (маркеры целы, sha256 и длина сошлись с мостом) —
    текст уходит, PDF НЕ уходит (двери нет), часть not_sent с причиной на карточке; такт и «Отправить» повтора не дают."""
    bad = _bad_pdfs()["xref: смещение каталога сдвинуто"]
    old = _with_pdf(bad)
    try:
        w = AS.World(AS.ON)
        w.ready()
        w.press("wa:send:1:1")
        w.core.tick(AS.T0 + 400)
        w.press("wa:send:1:1")
        assert len(w.sends) == 1 and w.media == [], (w.sends, w.media)
        part = w.part()
        assert part[0] == A.NOT_SENT and "скелет PDF не сошёлся" in part[3], part
        assert "PDF: не ушёл: скелет PDF не сошёлся" in w.answers()[0], w.answers()
        log = w.q("SELECT outcome, reason FROM part_log WHERE part='pdf'")
        assert log and log[-1][0] == A.NOT_SENT and "скелет PDF" in log[-1][1], log
    finally:
        AS.PDF, AS.SHA = old


def test_f4_checks_exact_bytes_sent():
    """Проверяются ТЕ ЖЕ байты, что получила дверь: запись аргумента проверки = байты `media["fetch"]` (sha256)."""
    seen = []
    real = X.pdf_shape

    def spy(raw):
        seen.append(hashlib.sha256(bytes(raw)).hexdigest())
        return real(raw)
    X.pdf_shape = spy
    try:
        w = AS.World(AS.ON)
        w.ready()
        w.press("wa:send:1:1")
    finally:
        X.pdf_shape = real
    assert len(w.media) == 1 and seen == [w.media[0][4]] == [AS.SHA], (seen, w.media)


# ═══ N2: проигранный захват — слова по перечитанному, поздний ответ карточку не перетирает ═══════════

class HW(AS.World):
    """Мир с крючками внутри двери провайдера (как test_wa_attach_red.HW): крючок — ДО ответа двери."""

    def __init__(self, *a, **kw):
        self.hooks = {}
        AS.World.__init__(self, *a, **kw)

    def send(self, to, text, db_path=None):
        h = self.hooks.pop("send", None)
        if h:
            h()
        return AS.World.send(self, to, text, db_path)

    def send_media(self, to, media, db_path=None):
        h = self.hooks.pop("media", None)
        if h:
            h()
        return AS.World.send_media(self, to, media, db_path)


def _second(w):
    core, tg, _f, _w = SVC.build(w.env, environ=dict(w.environ), model=w.model, http=w.http, send=w.send,
                                 send_media=w.send_media, clock=w.clock, line=w.lines.append)
    return core, tg


def _poke(w, sql, args=()):
    """Другой процесс на той же базе: своё соединение, своя запись (автокоммит первого — захвата нет)."""
    db = sqlite3.connect(w.env["agent_db"], timeout=5)
    try:
        db.execute(sql, args)
        db.commit()
    finally:
        db.close()


def _card_words(w):
    return [e["text"].rsplit("\n— ", 1)[-1] for e in w.edits() if "\n— " in e["text"]]


def test_n2_second_instance_pdf_not_sent_proven():
    """K20: второй экземпляр стартует посреди двери ТЕКСТА. База: текст unsure, PDF not_sent (доказано — двери не было).
    Ответ нажавшему — по базе: «PDF: не ушёл»; исход старта второго экземпляра на карточке НЕ перекрыт поздним «текст:
    ушёл»; повтора нет."""
    w = HW(AS.ON)
    w.ready()
    box = {}
    w.hooks["send"] = lambda: box.update(b=_second(w))
    w.press("wa:send:1:1")
    ans = w.answers()[-1]
    assert ans != "текст: ушёл" and "PDF: не ушёл" in ans, ans
    assert ans.startswith("текст: исход неизвестен — не повторять"), ans
    w.core.tick(AS.T0 + 400)
    words = _card_words(w)
    assert words and "PDF: не ушёл" in words[-1] and "рестарт службы" in words[-1], words
    assert not [x for x in words if x.startswith("текст: ушёл")], words
    assert len(w.sends) == 1 and w.media == [], (w.sends, w.media)


def test_n2_reread_pdf_sent():
    """Другой процесс уже отправил PDF этой попытки (база: sent, wamid) — захват проигран; слова по базе «PDF: ушёл»,
    не «не ушёл» и не молчание о PDF; двери PDF нет (второй копии нет)."""
    w = HW(AS.ON)
    w.ready()
    w.hooks["send"] = lambda: _poke(w, "UPDATE pdf_parts SET state=?, wamid=?, reason=? WHERE draft_id=1",
                                    (A.SENT, "wamid.OTHER1", "ok"))
    w.press("wa:send:1:1")
    ans = w.answers()[-1]
    assert ans.startswith("текст: ушёл · PDF: ушёл"), ans
    assert "не ушёл" not in ans and w.media == [], (ans, w.media)
    words = _card_words(w)
    # шаг 2 (K3-FIX N1): на карточке у ушедших частей — их wamid по базе
    assert words and words[-1].startswith("текст: ушёл (wamid …wamid.T1) · PDF: ушёл (wamid …d.OTHER1)") \
        and "опоздал" in words[-1], words


def test_n2_reread_pdf_unsure_no_blind_repeat():
    """База: PDF unsure (могло уйти) — слова «исход неизвестен — не повторять, проверить переписку», а не «не ушёл»;
    обычное «Дослать PDF» двери не зовёт (повтора вслепую нет)."""
    w = HW(AS.ON)
    w.ready()
    w.hooks["send"] = lambda: _poke(w, "UPDATE pdf_parts SET state=?, reason=?, sending_at=? WHERE draft_id=1",
                                    (A.UNSURE, "рестарт посреди отправки PDF — могло уйти, не повторяем", AS.T0 + 150))
    w.press("wa:send:1:1")
    ans = w.answers()[-1]
    assert "PDF: исход неизвестен — не повторять, проверить переписку" in ans and "не ушёл" not in ans, ans
    w.press("wa:pdf:1:1")
    assert w.media == [], w.media


def test_n2_late_answer_attempt_grown_card_untouched():
    """Поздний ответ: номер попытки PDF в базе вырос (другой процесс решил попытку 2) — ответ попытки 1 карточку НЕ
    правит (сравнение попытки перед правкой)."""
    w = HW(AS.ON)
    w.ready()
    w.hooks["send"] = lambda: _poke(w, "UPDATE pdf_parts SET state=?, attempt=2, wamid=? WHERE draft_id=1",
                                    (A.SENT, "wamid.NEWER"))
    w.press("wa:send:1:1")
    assert not [x for x in _card_words(w) if x.startswith("текст: ушёл")], _card_words(w)
    assert w.q("SELECT words FROM card_out WHERE draft_id=1") == [(None,)], w.q("SELECT words, state FROM card_out")


def test_n2_late_answer_version_changed_card_untouched():
    """Поздний ответ: версия черновика сменилась посреди двери — исход старой версии на карточку не ложится."""
    w = HW(AS.ON)
    w.ready()
    w.hooks["send"] = lambda: _poke(w, "UPDATE drafts SET ver=2 WHERE id=1")
    w.press("wa:send:1:1")
    assert not _card_words(w), _card_words(w)
    assert "опоздал" in w.answers()[-1] or "PDF" in w.answers()[-1], w.answers()


def test_n2_press_pdf_late_attempt_card_untouched():
    """«Дослать PDF»: посреди двери PDF другой процесс поднял номер попытки (3) — ответ попытки 2 карточку не правит,
    слова по базе."""
    w = HW(AS.ON, media="not_sent")
    w.ready()
    w.press("wa:send:1:1")
    assert w.part()[0] == A.NOT_SENT, w.part()
    before = len(_card_words(w))
    w.media_out = "sent"
    w.hooks["media"] = lambda: _poke(w, "UPDATE pdf_parts SET attempt=3, state=?, reason=? WHERE draft_id=1",
                                     (A.NOT_SENT, "решено другим процессом"))
    w.press("wa:pdf:1:1")
    assert len(_card_words(w)) == before, _card_words(w)[before:]
    assert "опоздал" in w.answers()[-1], w.answers()


def test_n2_control_normal_path_words_unchanged():
    """КОНТРОЛЬ (зелёный и до ремонта): без гонки слова нажавшему прежние («текст: ушёл · PDF: ушёл»); карточка — те же
    слова, с шага 2 (K3-FIX N1) — с wamid ушедших частей."""
    w = AS.World(AS.ON)
    w.ready()
    w.press("wa:send:1:1")
    assert w.answers()[-1] == "текст: ушёл · PDF: ушёл", w.answers()
    assert _card_words(w)[-1].startswith("текст: ушёл (wamid …wamid.T1) · PDF: ушёл (wamid …wamid.P1) — "), \
        _card_words(w)


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:400])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
