#!/usr/bin/env python3
"""CSTATE1510: ожидание подписи — в БАЗЕ (`contract_expect`), а не в памяти процесса (пункты 5–7 спецификации).

Открывает ожидание ФАКТ: реестр пуст (EMPTY) и в неотвеченных входящих просьба прислать договор (детектор CASEPDF1510) или
сообщение «подписал» (`wa_contract_state.signed_claim`, передаёт служба). Каждая проверка реестра по номеру с открытым
ожиданием пишет checked_at/outcome; timeout и refused не закрывают. Ритм — по базе: первые ASK_EAGER_SEC от открытия —
каждый проход, дальше не чаще SIGNED_IDLE; рестарт ритм не теряет. Закрывает карточка подписи (`card:<id>`, ТА ЖЕ
транзакция `_signed_insert`), решённая версия (`held`) или срок (`expired` + строка журнала). Клиенту ничего не уходит.

Стенд — `tests/test_wa_attach_cstate.World` (стенд подписи `test_wa_signed_card` + параметры ядра службы): реестр живого
формата без подписанной строки (стр.34/35 ОТОЗВАН), потом появляется стр.36 ПОДПИСАН 2026-10-14 19:04. Сети нет; модель,
мост, Telegram и WhatsApp не зовутся.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import test_wa_attach_cstate as CT  # noqa: E402  (стенды выпуска; заглушка spend_ledger — там же)
import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import wa_agent_cstate as C  # noqa: E402
import wa_agent_tools as T  # noqa: E402
import test_wa_signed_card as SC  # noqa: E402

NUM, T_SIGN = SC.NUM, SC.T_SIGN
ASK_RU = "Пришлите, пожалуйста, договор"
DUE = T_SIGN - 700 + A.FOLLOW_WINDOW                              # конец окна 24 ч от входящего T_SIGN − 700


class Registry(SC.Registry):
    """Дверь contract_find живого формата + отказ двери (исключение — REFUSED у `T.call_tool`)."""

    def __init__(self, rows=None):
        SC.Registry.__init__(self, rows)
        self.boom = False

    def __call__(self, **kw):
        if self.boom:
            self.calls.append(dict(kw))
            raise RuntimeError("мост отказал")
        return SC.Registry.__call__(self, **kw)


class FailingDb:
    """Соединение базы агента, у которого падает ОДНА запись внутри транзакции `_signed_insert` (по куску SQL)."""

    def __init__(self, db, marker):
        self._db, self.marker, self.hits = db, marker, 0

    def execute(self, sql, *args):
        if self.marker in sql:
            self.hits += 1
            raise sqlite3.OperationalError("подделка: сбой посреди транзакции карточки")
        return self._db.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._db, name)


def _empty(text, cstate=True, **kw):
    """Реестр без подписанного договора; клиент пишет text в 18:52; первый проход в 18:57 — реестр пуст."""
    reg = Registry(SC.live_rows()[:2])
    w = CT.World(registry=reg, tools_out=SC.NO_CONTRACT, text="Договор пришлём сразу после подписи.", cstate=cstate,
                 **kw)
    w.put(T_SIGN - 700, text)
    w.tick(T_SIGN - 400)
    return w, reg


def _sign(reg):
    reg.rows.append(SC.live_rows()[2])                             # стр.36 подписана 14.10 19:04


# ═══ 5. просьба / «подписал» при пустом реестре → open; реестр FACT → карточка и card:<id> одной транзакцией ═══════════

def test_5_ask_opens_then_card_closes_nothing_sent():
    w, reg = _empty(ASK_RU)
    assert w.expects() == [(NUM, T_SIGN - 400, "ask", 1, DUE, T_SIGN - 400, "empty", "open", None, None)], w.expects()
    assert w.expect_lines() == ["ожидание подписи: открыто — номер %s, просьба прислать договор, реестр пуст; "
                                "проверяется сам до 15.10 18:52 (Пхукет)" % T._tail(T.last9(NUM))], w.expect_lines()
    b = w.block(now=T_SIGN - 300)
    assert "• реестр: проверен 18:57 — подписанного не было (проверка ожидания)" in b, b
    assert "• ожидание подписи: открыто с 18:57 (просьба), реестр проверяется сам до 15.10 18:52" in b, b
    _sign(reg)
    w.tick(T_SIGN + 60)
    sd = w.signed_drafts()
    assert len(sd) == 1 and sd[0][1] == A.PENDING, (sd, w.sign_lines()[-4:])
    did = sd[0][0]
    assert w.expects()[0][5:] == (T_SIGN + 60, "fact", "closed", T_SIGN + 60, "card:%d" % did), w.expects()
    assert "ожидание подписи: закрыто карточкой подписи %d (ждёт нажатия)" % did in w.expect_lines()
    assert w.q("SELECT COUNT(*) FROM outbox") == [(0,)] and w.door.sends == [] and w.door.media == [], "клиенту ничего"
    b = w.block(now=T_SIGN + 120)
    for line in ("• версия: подписан 14.10 19:04 · doc …D36 · карточка подписи",
                 "• реестр: проверен 19:05 — подписанный найден (проверка ожидания)",
                 "• PDF клиенту: ждёт нажатия (черновик с 19:05)",
                 "• просьба прислать договор: 19:05, чистая → карточка",
                 "• ожидание подписи: закрыто 19:05 карточкой (ждёт нажатия)"):
        assert line in b, (line, b)


def test_5_card_and_close_one_transaction():
    """Сбой ВНУТРИ транзакции карточки (после закрытия ожидания) — откат всего: карточки нет, ожидание открыто; следующий
    проход — и карточка, и card:<id> вместе."""
    w, reg = _empty(ASK_RU)
    _sign(reg)
    real = w.core.db
    w.core.db = fail = FailingDb(real, "replaced_id, replaced_why) VALUES")
    try:
        w.tick(T_SIGN + 60)
    finally:
        w.core.db = real
    assert fail.hits == 1, fail.hits
    assert w.signed_drafts() == [] and w.expects()[0][7:] == ("open", None, None), (w.signed_drafts(), w.expects())
    assert w.q("SELECT COUNT(*) FROM signed_cards") == [(0,)] and w.q("SELECT COUNT(*) FROM card_out WHERE "
                                                                         "draft_id>1") == [(0,)]
    w.tick(T_SIGN + 60 + X.SIGNED_EVERY + 1)
    sd = w.signed_drafts()
    assert len(sd) == 1 and w.expects()[0][7:] == ("closed", T_SIGN + 61 + X.SIGNED_EVERY, "card:%d" % sd[0][0]), \
        (sd, w.expects())


def test_5_claim_opens_rhythm_by_base_not_memory():
    """«Подписал» (14.10) при пустом реестре — ожидание открыто; память прохода «договора нет» уходит в паузу SIGNED_IDLE,
    а ожидание первые ASK_EAGER_SEC проверяет реестр каждый проход: подпись в 19:04 — карточка уже в 19:05. Контроль без
    ожидания — до конца паузы реестр не спрашивается."""
    def run(cstate):
        w, reg = _empty("Подписал", cstate=cstate)
        w.tick(T_SIGN - 279)
        w.tick(T_SIGN - 158)                                       # три «договора нет» подряд — пауза до 19:12
        _sign(reg)
        w.tick(T_SIGN + 60)
        return w, reg
    w, reg = run(True)
    e = w.expects()
    assert len(e) == 1 and e[0][2] == "signed_claim" and e[0][1] == T_SIGN - 400, e
    assert len(reg.calls) == 4 and len(w.signed_drafts()) == 1, (reg.calls, w.sign_lines()[-3:])
    assert e[0][7:] == ("closed", T_SIGN + 60, "card:%d" % w.signed_drafts()[0][0]), e
    c, creg = run(False)
    assert len(creg.calls) == 3 and c.signed_drafts() == [] and "contract_expect" not in c.tables(), creg.calls
    # после ASK_EAGER_SEC — не чаще SIGNED_IDLE от прошлой проверки (по базе)
    w2, reg2 = _empty("Подписал")
    core = w2.core
    t = T_SIGN - 400 + X.ASK_EAGER_SEC + 10
    assert core._cstate_due(NUM, T_SIGN - 400 + 30) is True, "в первые ASK_EAGER_SEC — каждый проход"
    w2.x("UPDATE contract_expect SET checked_at=? WHERE number=?", (t - 60, NUM))
    assert core._cstate_due(NUM, t) is False and core._cstate_due(NUM, t - 60 + X.SIGNED_IDLE) is True
    core._signed_memo[NUM] = {"fail_at": t + 10 ** 6}
    assert core._cstate_due(NUM, t - 60 + X.SIGNED_IDLE) is False, "пауза после сбоев двери — ждёт"


def test_5_no_request_no_claim_no_expectation():
    w, reg = _empty("Здравствуйте! Байк на завтра свободен?")
    assert w.expects() == [] and len(reg.calls) == 1, (w.expects(), reg.calls)
    w2, _r = _empty("подпишу завтра")
    assert w2.expects() == []
    w3, _r = _empty("Подписал", claim=False)                       # детектора «подписал» нет — не открывается
    assert w3.expects() == [] and w3.core.claim_of is None


def test_5_claim_with_other_question_opens_thai_question_not():
    """Находка критика: «Подписал, что дальше?» (вопрос о другом через запятую) — сообщение о подписи, ожидание
    открывается; тайский вопрос «เซ็นแล้วหรือยัง» («уже подписали?») и отказ «ไม่เซ็นแล้ว» — нет."""
    w, reg = _empty("Подписал, что дальше?")
    assert [r[2] for r in w.expects()] == ["signed_claim"], (w.expects(), w.lines[-4:])
    for text in ("เซ็นแล้วหรือยัง", "ไม่เซ็นแล้ว"):
        w2, _r = _empty(text)
        assert w2.expects() == [], (text, w2.expects())


def test_5_claim_only_unanswered():
    """«Подписал» открывает ожидание, только пока сообщение НЕ отвечено (id > clients.done_upto — то же чтение очереди,
    что у просьбы): отвеченное «Подписал» и новое приветствие после него — уже не сообщение о подписи."""
    w, reg = _empty("Подписал")
    assert w.core._cstate_claimed(NUM) is True
    did, ver = w.q("SELECT id, ver FROM drafts WHERE number=? AND state=?", (NUM, A.PENDING))[0]
    out = w.core.press(did, ver, A.ACT_SEND, "Даня", T_SIGN - 350)
    assert out["ok"], out
    assert w.q("SELECT done_upto FROM clients WHERE number=?", (NUM,)) == [(1,)], w.q("SELECT * FROM clients")
    assert w.core._cstate_claimed(NUM) is False, "отвеченное «Подписал» ожидание не открывает"
    w.put(T_SIGN - 300, "Здравствуйте!")
    w.tick(T_SIGN - 295)                                           # ядро прочло очередь (тишина не вышла — черновика нет)
    assert w.q("SELECT last_in_id, done_upto FROM clients WHERE number=?", (NUM,)) == [(2, 1)]
    assert w.core._cstate_claimed(NUM) is False
    w.put(T_SIGN - 250, "Подписал ещё раз, проверьте")
    w.tick(T_SIGN - 245)
    assert w.core._cstate_claimed(NUM) is True, "новое неотвеченное — снова сообщение о подписи"


def test_5_timeout_and_refused_do_not_close():
    w, reg = _empty("Подписал")
    reg.fail = T.last9(NUM)
    w.tick(T_SIGN - 279)
    assert w.expects()[0][5:8] == (T_SIGN - 279, T.TIMEOUT, "open"), w.expects()
    reg.fail, reg.boom = None, True
    w.tick(T_SIGN - 158)
    assert w.expects()[0][5:8] == (T_SIGN - 158, T.REFUSED, "open"), w.expects()
    reg.boom = False
    w.tick(T_SIGN - 37)
    assert w.expects()[0][5:8] == (T_SIGN - 37, T.EMPTY, "open"), w.expects()
    b = w.block(now=T_SIGN - 30)
    assert "• реестр: проверен 19:03 — подписанного не было (проверка ожидания)" in b, b
    _sign(reg)
    w.tick(T_SIGN + 84)
    assert w.expects()[0][7] == "closed" and len(w.signed_drafts()) == 1, (w.expects(), w.sign_lines()[-3:])


def test_5_m3_registry_read_writes_outcome_only():
    """M3 (смешанная просьба — PDF к ответу модели) тоже читает реестр по номеру: исход ложится в открытое ожидание;
    нового ожидания этот путь не открывает."""
    w, reg = _empty("Подписал")
    w.put(T_SIGN - 300, "Пришлите договор и во сколько доставка?")
    w.clock.t = T_SIGN - 250
    got = w.core._ask_attach(NUM, 2)
    assert got is not None and got["asked"] == X.ASK_MIXED and got["meta"] is None, got
    assert len(w.expects()) == 1 and w.expects()[0][5:8] == (T_SIGN - 250, T.EMPTY, "open"), w.expects()
    c, creg = _empty("Здравствуйте")                               # ожидания нет — M3 его не открывает
    c.put(T_SIGN - 300, "Пришлите договор и во сколько доставка?")
    c.clock.t = T_SIGN - 250
    assert c.core._ask_attach(NUM, 2) is not None and c.expects() == [] and len(creg.calls) == 2


def test_5_version_held_closes_held():
    """Ожидание открыто, ответ модели на новое сообщение уже несёт этот PDF («покрыта») — новой карточки нет, ожидание
    закрыто `held`."""
    w, reg = _empty("Подписал")
    _sign(reg)
    w.model.tools_out, w.model.text = SC.model_pdf36(), "Договор ниже"
    w.put(T_SIGN + 100, "Ну что там?")
    w.tick(T_SIGN + 300)
    assert w.signed_drafts() == [] and w.attach(2)[0] == "PDF36", (w.signed_drafts(), w.attach(2))
    assert w.expects()[0][7:] == ("closed", T_SIGN + 300, X.EXPECT_HELD), w.expects()
    assert "ожидание подписи: закрыто — версия решена без новой карточки" in w.expect_lines()
    assert "• ожидание подписи: закрыто 19:09 — версия уже решена без новой карточки" in w.block(now=T_SIGN + 400)


def test_5_one_open_per_number():
    w, reg = _empty("Подписал")
    n = w.core._cstate_note(NUM, T.EMPTY, T_SIGN - 100, 1, "pure")
    assert n is None and len(w.expects()) == 1 and w.expects()[0][6] == T.EMPTY, w.expects()
    try:
        w.x("INSERT INTO contract_expect(number, opened_at, why, due_at, state) VALUES(?,?,?,?,?)",
            (NUM, T_SIGN, "ask", DUE, "open"))
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("второе открытое ожидание номера легло")


# ═══ 6. рестарт между открытием и подписью ═════════════════════════════════════════════════════════════════

def test_6_restart_continues_by_base():
    w, reg = _empty("Подписал")
    opened = w.expects()[0][1]
    w.restart()                                                    # ядро пересоздано на тех же файлах
    assert w.core._signed_memo == {} and w.core._cstate_due(NUM, T_SIGN - 300) is True
    a = C.ContractStateAdapter(w.qpath, None, agent_db=w.dbpath, clock=w.clock)   # и адаптер — новый объект
    _s, user, info = a.build(NUM, 10 ** 6, now=T_SIGN - 300)
    assert ("• ожидание подписи: открыто с 18:57 (клиент сообщил о подписи), реестр проверяется сам до "
            "15.10 18:52") in user, user[:900]
    assert info["cstate"]["lines"] >= 3 and opened == T_SIGN - 400
    # память прохода «пауза до нового входящего» не мешает: ритм ожидания — по базе
    w.core._signed_memo[NUM] = {"in": 1, "idle_at": T_SIGN + 10 ** 6, "empty": 9}
    _sign(reg)
    w.tick(T_SIGN + 60)
    sd = w.signed_drafts()
    assert len(sd) == 1 and w.expects()[0][1] == opened, (sd, w.expects())
    assert w.expects()[0][7:] == ("closed", T_SIGN + 60, "card:%d" % sd[0][0]), w.expects()


def test_6_restart_real_adapter_every_turn():
    """Рестарт НАСТОЯЩИХ адаптера и ядра (служба пересобирает оба на тех же файлах): ожидание, открытое прежним процессом,
    модель нового процесса видит в голове КАЖДОГО хода сверки — с прежним opened_at и проверкой реестра; подпись —
    карточка и card:<id> тем же путём, что в п. 5; клиенту ничего."""
    r = CT.Real(rows=SC.live_rows()[:2])                          # реестр без подписанной строки (стр.34/35 ОТОЗВАН)
    r.script = CT.Script(CT.tool("contract"), CT.final("Проверю договор."))
    r.put(T_SIGN - 700, "Подписал")
    r.tick(T_SIGN - 400)
    assert r.q("SELECT opened_at, why, state FROM contract_expect") == [(T_SIGN - 400, "signed_claim", "open")], \
        (r.q("SELECT * FROM contract_expect"), r.lines[-4:])
    r.adapter = r.new_adapter()                                   # новый процесс: адаптер и ядро — новые объекты
    r.restart()
    assert r.core._signed_memo == {} and r.core._cstate_due(NUM, T_SIGN - 100) is True
    r.script = CT.Script(CT.tool("contract"), CT.final("Проверю договор."))
    r.put(T_SIGN - 300, "Хорошо, жду.")
    r.tick(T_SIGN - 100)
    seen = r.script.seen
    assert len(seen) == 2, len(seen)
    for u in seen:
        b = CT.block_of(u)
        assert u.startswith(CT.HEAD_T + CT.HEAD0) and b, u[:300]
        for line in ("• ожидание подписи: открыто с 18:57 (клиент сообщил о подписи), реестр проверяется сам до "
                     "15.10 18:52", "• реестр: проверен 18:57 — подписанного не было (проверка ожидания)",
                     "• версия: в базе нет"):
            assert line in b, (line, b)
        assert "Хорошо, жду" not in b and NUM not in b, b
    assert r.adapter.last["info"]["cstate"]["unread"] == [], r.adapter.last["info"]["cstate"]
    _sign(r.registry)
    r.tick(T_SIGN + 60)
    sd = r.signed_drafts()
    assert len(sd) == 1 and sd[0][1] == A.PENDING, (sd, r.lines[-6:])
    assert r.q("SELECT opened_at, state, closed_by FROM contract_expect") == [
        (T_SIGN - 400, "closed", "card:%d" % sd[0][0])], r.q("SELECT * FROM contract_expect")
    assert r.q("SELECT COUNT(*) FROM outbox") == [(0,)] and r.door.sends == [] and r.door.media == [], "клиенту ничего"


# ═══ 7. срок вышел → expired, в блоке «истекло» ═══════════════════════════════════════════════════════════════

def test_7_expired_and_reopen():
    w, reg = _empty(ASK_RU)
    assert w.expects()[0][4] == DUE
    assert "• ожидание подписи: истекло 18:52 (срок — 24 ч от сообщения клиента)" in w.block(now=DUE + 5), "срок — по времени"
    assert w.core._cstate_due(NUM, DUE) is False
    w.tick(DUE + 10)
    e = w.expects()[0]
    assert e[7:9] == ("expired", DUE + 10) and e[9] is None, e
    said = [ln for ln in w.expect_lines() if "истекло" in ln]
    assert said == ["ожидание подписи: истекло — номер %s, открыто 18:57 (просьба): окно 24 ч кончилось без подписанного "
                    "договора в реестре; клиенту ничего не отправлено" % T._tail(T.last9(NUM))], said
    assert "• ожидание подписи: истекло 18:52 (срок — 24 ч от сообщения клиента)" in w.block(now=DUE + 20)
    assert w.signed_drafts() == [] and w.door.sends == [] and w.q("SELECT COUNT(*) FROM outbox") == [(0,)]
    w.tick(DUE + 10 + X.SIGNED_EVERY + 1)
    assert len([ln for ln in w.expect_lines() if "истекло" in ln]) == 1, "истечение — одной строкой"
    w.put(DUE + 300, "Подписал")                                   # новое окно — новое ожидание
    w.tick(DUE + 600)
    # просьба 18:52 так и не отвечена — она и открывает новое ожидание (просьба сильнее «подписал»)
    assert [r[7] for r in w.expects()] == ["expired", "open"] and w.expects()[1][2] == "ask", w.expects()


def test_7_expired_after_found_line_says_found():
    """Последняя проверка открытого ожидания нашла подписанный, а карточки по нему не было (версия решена, PDF к ответу
    модели) — строка истечения не говорит «без подписанного договора»: слова — по исходу последней проверки."""
    w, reg = _empty("Подписал")
    w.x("UPDATE contract_expect SET outcome=? WHERE number=?", (T.FACT, NUM))
    w.tick(DUE + 10)
    said = [ln for ln in w.expect_lines() if "истекло" in ln]
    assert len(said) == 1 and "подписанный в реестре найден, новой карточки по нему нет" in said[0], said
    assert "без подписанного" not in said[0] and NUM not in said[0], said
    b = w.block(now=DUE + 20)
    assert "• реестр: проверен 14.10 18:57 — подписанный найден (проверка ожидания)" in b, "другой день — с датой"


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
