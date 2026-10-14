#!/usr/bin/env python3
"""Подписанный договор → ОДНА карточка с PDF (SIGNEDCARD1410, `wa_agent_attach.AttachCore.make_signed_cards`). Черновик
клиенту НИКОГДА не уходит без нажатия «Отправить».

Всё на подделках: временная очередь схемой wa_webhook, своя временная база агента, Telegram, дверь WhatsApp, реестр
подписей (contract_find) и подписанные PDF (contract_pdf) — подделки; дверь аренды — НАСТОЯЩАЯ дверь сверки модели
(`wa_agent_model.ModelAdapter._tool_doors`, снимок броней — подделка `Book`): ядро берёт её у модели тем же способом, что
сверка; тот же код привязки договора (`wa_agent_tools.call_tool` + `bind_ctx`). Сети нет, модель, мост, Telegram и
WhatsApp не зовутся.

Живой пример (данные синтетические, формат живой): номер 79999966963, байк «NINJA 400СС PHUKET 6334», аренда
2026-10-14..2026-10-17; реестр: стр.34 ОТОЗВАН (signed_at 2026-10-14 17:47), стр.35 ОТОЗВАН (18:37), стр.36 ПОДПИСАН
2026-10-14 19:04 с pdf_id; телефон в контактах аренды — с неразрывными дефисами U+2011.

Кроме случаев (а)–(з) выпуска — поправки критиков (FIX1410): текст подписи без PDF не уходит, PDF с «Дослать PDF» и
документ, отправленный человеком, — «покрыто», тишина ядра до первой карточки, вопрос клиента в черновике подписи, версия
снова открыта после снятого ядром «покрытия», тот же PDF под новой строкой реестра, бюджет и курсор прохода, паузы номера,
бюджет плеч моста в службе, снятие карточек подписи без PDF-ядра.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import base64
import calendar
import contextlib
import hashlib
import os
import sqlite3
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import wa_agent_model as M  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import wa_agent_tools as T  # noqa: E402
import k3_pdf_fixture  # noqa: E402  (скелет PDF сверяется перед дверью — фикстура живого формата)
import test_wa_agent_attach as AT  # noqa: E402  (подделки Telegram и двери WhatsApp, схема очереди)

NUM = "79999966963"
NUM2 = "79161234567"                                        # второй клиент: проход, курсор, бюджет
NBH = chr(0x2011)                                           # неразрывный дефис: так номер копируется из WhatsApp
CONTACTS = "Иван +7 999 996%s69%s63" % (NBH, NBH)
CONTACTS2 = "Пётр +7 916 123%s45%s67" % (NBH, NBH)
BIKE = "NINJA 400СС PHUKET 6334"
BIKE2 = "PCX 160 WHITE PHUKET 5580"
PDF36 = k3_pdf_fixture.classic(b"signed contract row 36")
PDF37 = k3_pdf_fixture.classic(b"signed contract row 37")
PDF40 = k3_pdf_fixture.classic(b"signed contract row 40 PCX 5580")
SHA36, SHA37 = hashlib.sha256(PDF36).hexdigest(), hashlib.sha256(PDF37).hexdigest()
PHUKET = 7 * 3600


def phuket(y, mo, d, h, mi):
    """Время Пхукета → эпоха."""
    return calendar.timegm((y, mo, d, h, mi, 0)) - PHUKET


T_SIGN = phuket(2026, 10, 14, 19, 4)                        # стр.36 подписана
T_START = T_SIGN - 2 * 3600                                 # первый старт с флагом: водораздел T_START − 6 ч
RU_TEXT = X.SIGNED_TEXT["ru"]
EN_TEXT = X.SIGNED_TEXT["en"]


def reg_row(row, status, signed_at, pdf_id="", bike=BIKE, date="2026-10-14", phone="+7 999 996-69-63"):
    """Запись реестра в форме `bridge_client.contract_find` (row, doc_id, …, pdf_id, matched_on)."""
    return {"row": row, "doc_id": "D%d" % row, "client": "Иван", "contract_date": date, "contract_date_raw": date,
            "created_raw": date, "date_src": "contract_date", "status": status, "signed": status == "ПОДПИСАН",
            "signed_at": signed_at, "bike": bike, "phone": phone, "pdf_id": pdf_id, "matched_on": ["phone"]}


def live_rows():
    return [reg_row(34, "ОТОЗВАН", "2026-10-14 17:47", "P34"), reg_row(35, "ОТОЗВАН", "2026-10-14 18:37", "P35"),
            reg_row(36, "ПОДПИСАН", "2026-10-14 19:04", "PDF36")]


def row_num2():
    return reg_row(40, "ПОДПИСАН", "2026-10-14 19:10", "PDF40", bike=BIKE2, phone="+7 916 123-45-67")


class Registry:
    """Подделка двери contract_find: отбор моста — телефон по 9 цифрам, срок по «Дата договора»; outcome
    one / ambiguous / none_signed / none; без фильтра — no_filter (как мост). slow — секунд к часам стенда на вызов
    (больной мост); fail — 9 цифр номера, на котором дверь падает таймаутом."""

    def __init__(self, rows=None):
        self.rows, self.calls = list(live_rows() if rows is None else rows), []
        self.clock, self.slow, self.fail = None, 0, None
        self.deadline = 0                           # столько вызовов подряд: общий бюджет прохода исчерпан (card_deadline)

    def __call__(self, phone="", name="", bike="", date_from="", date_to="", limit=None):
        self.calls.append({"phone": phone, "date_from": date_from, "date_to": date_to})
        if self.deadline:
            self.deadline -= 1
            return {"ok": False, "error": "card_deadline"}
        if self.clock is not None and self.slow:
            self.clock.t += self.slow
        if not (str(phone).strip() or str(name).strip() or str(bike).strip()):
            return {"ok": False, "error": "no_filter"}
        key = T.last9(phone)
        if self.fail and key == self.fail:
            raise TimeoutError("read timed out")
        hit = [r for r in self.rows if key and key in T.contract_phones(r["phone"])
               and (not date_from or r["contract_date"] >= date_from) and (not date_to or r["contract_date"] <= date_to)]
        signed = [r for r in hit if r["signed"]]
        out = "none" if not hit else "none_signed" if not signed else "one" if len(signed) == 1 else "ambiguous"
        return {"ok": True, "outcome": out, "pick": dict(signed[0], pdf_ready=True) if out == "one" else None,
                "reason": None, "items": [dict(r) for r in hit], "undated_items": [],
                "checked": {"rows_scanned": len(self.rows), "matched": len(hit), "signed": len(signed),
                            "returned": len(hit), "truncated": False, "undated": 0, "undated_signed": 0,
                            "date_unparsed": 0, "unread": [], "complete": True}}

    def revoke(self, row):
        for r in self.rows:
            if r["row"] == row:
                r.update(status="ОТОЗВАН", signed=False)

    def phones(self):
        return [T.last9(c["phone"]) for c in self.calls]


class Pdfs:
    """Подделка двери contract_pdf в форме `bridge_client.contract_pdf` (verified ставит клиент)."""

    def __init__(self, files=None):
        self.files = dict({"PDF36": (36, PDF36), "PDF37": (37, PDF37), "PDF40": (40, PDF40)} if files is None else files)
        self.calls = []

    def __call__(self, file_id):
        self.calls.append(file_id)
        if file_id not in self.files:
            return {"ok": False, "error": "not_in_registry"}
        row, data = self.files[file_id]
        return {"ok": True, "id": file_id, "name": "contract_%d.pdf" % row, "mime": "application/pdf",
                "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "content_b64": base64.b64encode(data).decode(), "row": row, "verified": True}


class Book:
    """Снимок броней (`wa_book_read.Snapshot.get`): строки листа «клиенты»."""

    def __init__(self, rows):
        self.rows = rows

    def get(self, now):
        return self.rows, [], 0.0, ""


def book_row(bike=BIKE, status="В аренде", contacts=CONTACTS, booking="B6334"):
    return {"booking_id": booking, "bike": bike, "date_start": "2026-10-14", "date_end": "2026-10-17",
            "status": status, "auto_cancel": "", "contacts": contacts, "price": 1500, "currency": "THB"}


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t


class Model(A.Model):
    """Подделка адаптера модели для `make_drafts`: text=None — модель молчит (черновика нет); text — строка или ответ
    словарём (`{"text", "question", "q_lang"}` — как у адаптера). Двери аренды НЕТ — карточка подписи выключена."""

    def __init__(self, tools_out=None, text=None):
        self.tools_out, self.text, self.calls, self.last = tools_out, text, 0, None

    def draft(self, number, upto_id):
        self.calls += 1
        self.last = {"tools": self.tools_out, "info": {"last_in": None}} if self.tools_out is not None else {"info": {}}
        return self.text


class DoorModel(Model):
    """…с дверями сверки НАСТОЯЩЕГО адаптера (`ModelAdapter._tool_doors`): ядро берёт аренду у модели тем же способом,
    что её сверка; вызовы аренды считаются."""

    def __init__(self, adapter, seen, tools_out=None, text=None):
        Model.__init__(self, tools_out, text)
        self.adapter, self.seen = adapter, seen

    def _tool_doors(self, number, upto_id):
        doors = dict(self.adapter._tool_doors(number, upto_id))
        inner = doors["rental"]

        def rental():
            self.seen.append(number)
            return inner()
        doors["rental"] = rental
        return doors


def res(tool, outcome, facts=(), reason="", window=""):
    return {"tool": tool, "outcome": outcome, "source": "", "ref": "", "at": T_SIGN, "version": "", "window": window,
            "reason": reason, "facts": list(facts)}


NO_CONTRACT = {"state": "done", "results": [res("contract", "empty", reason="подписанного нет")]}


def model_pdf36():
    """Сверка модели приняла тот же договор стр.36 и его PDF (как `ModelAdapter.last["tools"]`)."""
    return {"state": "done", "results": [
        res("rental", "fact", [{"kind": "rental", "booking_id": "B6334", "bike": BIKE, "date_start": "2026-10-14",
                                "date_end": "2026-10-17"}]),
        res("contract", "fact", [{"kind": "contract", "row": 36, "doc_id": "D36", "bike": BIKE,
                                  "signed_at": "2026-10-14 19:04", "pdf_id": "PDF36", "booking_id": "B6334"}],
            window="2026-10-14…2026-10-17"),
        res("contract_pdf", "fact", [{"kind": "pdf", "id": "PDF36", "name": "contract_36.pdf", "size": len(PDF36),
                                      "sha256": SHA36, "row": 36}])]}


class World:
    def __init__(self, signed=True, rows=None, book=None, tools_out=None, text=None, start=T_START, lookback_h=6,
                 tg=None, registry=None, rental=True):
        d = tempfile.mkdtemp(prefix="wa_signed_card_t_")
        self.qpath, self.dbpath, self.mpath = (os.path.join(d, "q.db"), os.path.join(d, "agent.db"),
                                               os.path.join(d, "mirror.db"))
        q = sqlite3.connect(self.qpath)
        q.execute(AT.QSCHEMA)
        q.commit()
        q.close()
        self.clock = Clock(start)
        self.book = Book([book_row()] if book is None else book)
        # настоящий адаптер модели — ради ЕГО двери аренды (`_tool_doors`): та же дверь, что у сверки
        self.adapter = M.ModelAdapter(self.qpath, call=lambda *a: ("", {}), book=self.book, clock=self.clock)
        self.rental_calls = []
        self.model = DoorModel(self.adapter, self.rental_calls, tools_out, text) if rental else Model(tools_out, text)
        self.registry = registry or Registry(rows)
        self.registry.clock = self.clock
        self.pdfs = Pdfs()
        self.tg = tg or AT.FakeTG()
        self.door = AT.FakeDoor()
        self.lines = []
        self.signed, self.lookback_h = signed, lookback_h
        self.core = self.new_core()
        if hasattr(self.tg, "bind"):
            self.tg.bind(self.core)
        self.core.tick(start)                                       # первый старт: курсор на верх очереди

    def new_core(self):
        return X.AttachCore(self.dbpath, self.qpath, self.model, self.tg, self.door, log=self.lines.append,
                            clock=self.clock, attach=True, pdf_fetch=self.pdfs, contract_find=self.registry,
                            signed=self.signed, signed_lookback_h=self.lookback_h)

    def restart(self):
        self.core.db.close()
        self.core = self.new_core()
        if hasattr(self.tg, "bind"):
            self.tg.bind(self.core)
        return self.core

    def put(self, ts, text="Подписал договор", kind="in", msg_type="text", number=NUM):
        echo = 1 if kind == "echo" else 0
        q = sqlite3.connect(self.qpath)
        cur = q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
                        "VALUES(?,?,?,?,?,?,0,NULL)", (ts, number, msg_type, text, ts, echo))
        q.commit()
        q.close()
        return cur.lastrowid

    def tick(self, t):
        self.clock.t = float(t)
        return self.core.tick(t)

    def q(self, sql, args=()):
        db = sqlite3.connect(self.dbpath)
        try:
            return db.execute(sql, args).fetchall()
        finally:
            db.close()

    def x(self, sql, args=()):
        db = sqlite3.connect(self.dbpath)
        try:
            db.execute(sql, args)
            db.commit()
        finally:
            db.close()

    def signed_drafts(self):
        return self.q("SELECT id, state, text, upto_id, ctx FROM drafts WHERE kind=? ORDER BY id", (X.KIND_SIGNED,))

    def attach(self, did):
        rows = self.q("SELECT file_id, name, size, sha256, row, doc_id, signed_at, number, date_from, date_to, opora, "
                      "reason FROM attach WHERE draft_id=?", (did,))
        return rows[0] if rows else None

    def versions(self):
        return self.q("SELECT number, doc_id, signed_at, file_id, sha256, draft_id FROM signed_cards ORDER BY ts, "
                      "draft_id")

    def sign_lines(self):
        return [ln for ln in self.lines if ln.startswith("подпись:")]


def _card(w, t=T_SIGN + 600, text="Подписал договор"):
    """Клиент написал после подписи → такт → карточка подписи. → id черновика."""
    w.put(T_SIGN + 60, text)
    w.tick(t)
    got = w.signed_drafts()
    assert len(got) == 1, (got, w.lines[-8:])
    return got[0][0]


# ── (а) стр.36 подписана, 34/35 отозваны, окно открыто → ровно одна карточка ─────────────────────────────

def test_a_one_card_from_live_registry():
    w = World()
    did = _card(w)
    rows = w.signed_drafts()
    assert rows == [(did, A.PENDING, RU_TEXT, rows[0][3], rows[0][4])], rows
    assert rows[0][3] == w.q("SELECT last_in_id FROM clients WHERE number=?", (NUM,))[0][0], "upto = last_in_id"
    assert rows[0][4] == w.q("SELECT ctx FROM clients WHERE number=?", (NUM,))[0][0], "ctx = clients.ctx"
    a = w.attach(did)
    assert a[:10] == ("PDF36", "contract_36.pdf", len(PDF36), SHA36, 36, "D36", "2026-10-14 19:04", NUM,
                      "2026-10-14", "2026-10-17"), a
    assert a[11] is None and "прочитал КОД" in (a[10] or ""), a
    assert "rental" in (a[10] or ""), "опора называет и аренду, к которой код привязал договор"
    assert a[3] == hashlib.sha256(PDF36).hexdigest(), "attach.sha256 = sha байтов PDF"
    assert w.tg.cards == [did], w.tg.cards                       # карточка ушла в «Агенты»
    assert w.q("SELECT state FROM card_out WHERE draft_id=? AND ver=1", (did,)) == [(A.CARD_DELIVERED,)]
    assert w.versions() == [(NUM, "D36", "2026-10-14 19:04", "PDF36", SHA36, did)], w.versions()
    assert w.pdfs.calls == ["PDF36"], w.pdfs.calls               # PDF читал КОД — ровно один раз
    assert w.rental_calls == [NUM], w.rental_calls               # дверь аренды модели — одна на номер
    # поиск привязан кодом: номер обращения и срок аренды (тот же ключ, что у перечитывания перед отправкой); второго
    # поиска без срока нет
    assert w.registry.calls == [{"phone": NUM, "date_from": "2026-10-14", "date_to": "2026-10-17"}], w.registry.calls
    assert w.door.sends == [] and w.door.media == [], "без нажатия клиенту ничего"
    assert w.core.card_label(did) == X.W_SIGNED_LABEL
    assert w.core.signed_counts() == {"карточка": 1}, w.core.signed_counts()
    said = [ln for ln in w.sign_lines() if "черновик %d" % did in ln]
    assert said and "строка реестра 36" in said[0] and SHA36[:12] in said[0] and "язык RU" in said[0], w.sign_lines()
    for ln in w.lines:                                           # без текстов клиента и без его номера целиком
        assert "Подписал договор" not in ln and NUM not in ln, ln


def test_a_second_tick_and_restart_no_second_card():
    w = World()
    did = _card(w)
    w.tick(T_SIGN + 600 + X.SIGNED_EVERY + 10)                    # второй такт: версия решена — номер ждёт SIGNED_IDLE
    assert [r[0] for r in w.signed_drafts()] == [did]
    assert len(w.registry.calls) == 1 and w.pdfs.calls == ["PDF36"], (w.registry.calls, w.pdfs.calls)
    since = w.q("SELECT value FROM meta WHERE key=?", (X.SIGNED_SINCE,))
    w.restart()                                                  # новый экземпляр ядра на той же базе
    w.tick(T_SIGN + 900 + 2 * X.SIGNED_EVERY)
    assert len(w.registry.calls) == 2, "после рестарта реестр перечитан"
    assert [r[0] for r in w.signed_drafts()] == [did], w.signed_drafts()
    assert w.q("SELECT value FROM meta WHERE key=?", (X.SIGNED_SINCE,)) == since, "рестарт водораздел не сдвигает"
    assert len(w.versions()) == 1 and w.pdfs.calls == ["PDF36"], (w.versions(), w.pdfs.calls)


def test_a_throttle_signed_every():
    w = World()
    _card(w)
    n = len(w.registry.calls)
    w.tick(T_SIGN + 600 + X.SIGNED_EVERY - 1)                     # раньше SIGNED_EVERY — дверей не зовём вовсе
    assert len(w.registry.calls) == n and X.SIGNED_EVERY == 120, (w.registry.calls, X.SIGNED_EVERY)


def test_a_press_sends_text_then_pdf_by_existing_path():
    w = World()
    did = _card(w)
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    assert out["ok"] and out["words"] == "текст: ушёл · PDF: ушёл", out
    assert w.door.sends == [(NUM, RU_TEXT)], w.door.sends
    assert w.door.media == [(NUM, "document", "application/pdf", "contract_36.pdf", SHA36)], w.door.media
    assert w.registry.calls[-1] == {"phone": NUM, "date_from": "2026-10-14", "date_to": "2026-10-17"}, "перечитан"
    assert w.q("SELECT state, wamid FROM pdf_parts WHERE draft_id=?", (did,)) == [(A.SENT, "wamid.P1")]
    # уже отправленный — второй карточки та же версия не даёт
    w.tick(T_SIGN + 700 + 2 * X.SIGNED_EVERY)
    assert [r[0] for r in w.signed_drafts()] == [did]


def test_a_new_inbound_after_card_reopens_version():
    """Новое входящее после карточки — поведение ядра (pending → stale). Финальный разбор: договор клиенту НЕ ушёл —
    версия снова открыта; модель промолчала (живого ответа нет) → ОДНА новая карточка той же версии, строка версии одна
    и указывает на неё, клиенту ничего не уходило; дальше третьей карточки нет."""
    w = World()
    did = _card(w)
    w.put(T_SIGN + 800, "А когда можно забрать?")
    w.tick(T_SIGN + 800 + X.SIGNED_EVERY + 5)
    st = w.q("SELECT state, reason FROM drafts WHERE id=?", (did,))[0]
    assert st[0] == A.STALE and "клиент написал ещё" in st[1], st
    sd = w.signed_drafts()
    assert [r[0] for r in sd][0] == did and len(sd) == 2 and sd[1][1] == A.PENDING, sd
    assert len(w.versions()) == 1 and w.versions()[0][5] == sd[1][0], w.versions()
    assert w.attach(sd[1][0])[3] == SHA36, "новая карточка несёт тот же PDF"
    assert w.door.sends == [] and w.door.media == [], (w.door.sends, w.door.media)
    w.tick(T_SIGN + 800 + 3 * X.SIGNED_EVERY + 10)
    w.tick(T_SIGN + 800 + X.SIGNED_IDLE + 4 * X.SIGNED_EVERY)
    assert len(w.signed_drafts()) == 2, ("третьей карточки нет", w.signed_drafts())


def test_a_after_card_model_answers_new_message_promptly():
    """Карточка подписи — ответ на входящее: прежняя пустая попытка модели (пауза MODEL_RETRY_SEC) не задерживает ответ
    на НОВОЕ сообщение клиента — ядро снимает карточку (stale) и спрашивает модель после обычной тишины."""
    w = World()
    did = _card(w)                                               # модель молчала — пауза повтора ядра стояла бы +300 с
    w.model.text = "Байк сдаётся 17.10 в 10:00"
    w.put(T_SIGN + 630, "А когда вернуть байк?")
    w.tick(T_SIGN + 630 + w.core.quiet + 45)
    rows = w.q("SELECT id, state, kind FROM drafts ORDER BY id")
    assert rows == [(did, A.STALE, X.KIND_SIGNED), (did + 1, A.PENDING, None)], rows


# ── (б) висящий pending без PDF → superseded + карточка подписи ──────────────────────────────────────────

def test_b_pending_without_pdf_superseded():
    reg = Registry(live_rows()[:2])                              # стр.36 ещё не подписана
    w = World(tools_out=NO_CONTRACT, text="Спасибо!", registry=reg)
    w.put(T_SIGN - 300, "Подписываю")
    w.tick(T_SIGN - 100)
    first = w.q("SELECT id, state FROM drafts")
    assert first == [(1, A.PENDING)] and w.signed_drafts() == [], (first, w.lines[-6:])
    assert w.attach(1)[0] is None, "у ответа модели PDF нет"
    reg.rows.append(live_rows()[2])                               # стр.36 подписана
    w.tick(T_SIGN + 600)
    st = w.q("SELECT state, reason FROM drafts WHERE id=1")[0]
    sd = w.signed_drafts()
    assert len(sd) == 1 and sd[0][1] == A.PENDING, sd
    assert st[0] == A.SUPERSEDED and "заменён карточкой подписанного договора" in st[1], st
    assert any(d == 1 and "заменён карточкой подписанного договора" in words for d, words in w.tg.done), w.tg.done
    assert w.tg.cards == [1, sd[0][0]], w.tg.cards
    assert w.q("SELECT state FROM card_out WHERE draft_id=1") == [(A.CARD_DECIDED,)], "карточка снятого закрыта"


def test_b_pending_with_same_pdf_covered_no_card():
    """Ждущий черновик модели уже несёт ЭТОТ PDF (тот же sha256) — версия «покрыта», новой карточки нет."""
    w = World(tools_out=model_pdf36(), text="Договор ниже")
    w.put(T_SIGN + 60)
    w.tick(T_SIGN + 600)
    assert w.signed_drafts() == [] and w.q("SELECT id, state FROM drafts") == [(1, A.PENDING)], w.lines[-6:]
    assert w.versions() == [(NUM, "D36", "2026-10-14 19:04", "PDF36", SHA36, 1)], w.versions()
    assert any("покрыта черновиком 1" in ln for ln in w.sign_lines()), w.sign_lines()
    assert w.core.signed_counts() == {"покрыта": 1}, w.core.signed_counts()


# ── (в) отзыв до нажатия → stale, клиенту ничего ────────────────────────────────────────────────────────

def test_c_revoked_before_press_stale_nothing_sent():
    w = World()
    did = _card(w)
    w.registry.revoke(36)
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    assert out["state"] == A.STALE and not out["ok"], out
    assert out["words"].startswith("устарело: основание PDF не подтверждено реестром"), out
    assert w.door.sends == [] and w.door.media == [] and w.pdfs.calls == ["PDF36"], (w.door.sends, w.pdfs.calls)
    st = w.q("SELECT state, reason FROM drafts WHERE id=?", (did,))[0]
    assert st[0] == A.STALE and "ничего не отправлено" in st[1], st
    w.tick(T_SIGN + 700 + 2 * X.SIGNED_EVERY)
    assert [r[0] for r in w.signed_drafts()] == [did], "отозванная версия второй карточки не даёт"


# ── (г) новая версия (стр.37) → новая карточка, старая не повторяется ───────────────────────────────────

def test_d_new_version_new_card_old_not_repeated():
    w = World()
    d36 = _card(w)
    assert w.core.press(d36, 1, A.ACT_SEND, "Даня", T_SIGN + 700)["ok"]
    w.registry.revoke(36)
    w.registry.rows.append(reg_row(37, "ПОДПИСАН", "2026-10-14 21:30", "PDF37"))
    t = phuket(2026, 10, 14, 21, 40)                              # 10 мин после подписи стр.37
    w.tick(t)
    sd = w.signed_drafts()
    assert [r[0] for r in sd] == [d36, sd[-1][0]] and sd[-1][0] != d36, sd
    d37 = sd[-1][0]
    assert sd[-1][1] == A.PENDING and sd[-1][2] == RU_TEXT, sd
    assert w.attach(d37)[0] == "PDF37" and w.attach(d37)[3] == SHA37 and w.attach(d37)[4] == 37, w.attach(d37)
    w.tick(t + X.SIGNED_EVERY + 1)
    w.restart()
    w.tick(t + 3 * X.SIGNED_EVERY)
    assert [r[0] for r in w.signed_drafts()] == [d36, d37], w.signed_drafts()
    assert [v[1] for v in w.versions()] == ["D36", "D37"], w.versions()
    assert w.pdfs.calls == ["PDF36", "PDF36", "PDF37"], w.pdfs.calls   # PDF36: сверка + отправка; PDF37: сверка


# ── (д) карточки нет ───────────────────────────────────────────────────────────────────────────────────

def _none(w, t=T_SIGN + 600):
    w.tick(t)
    assert w.signed_drafts() == [], (w.signed_drafts(), w.sign_lines())


def test_e_window_closed_no_card_no_doors():
    w = World()
    now = T_SIGN + 600
    w.put(now - (A.FOLLOW_WINDOW - A.FOLLOW_SPARE) - 60)          # последнее входящее старше 24 ч − 30 мин
    _none(w, now)
    assert w.registry.calls == [] and w.rental_calls == [] and w.pdfs.calls == [], "окно закрыто — дверей нет"


def test_e_ambiguous_no_card():
    rows = live_rows()
    rows[1].update(status="ПОДПИСАН", signed=True)                # стр.35 тоже подписана — выбрать нельзя
    w = World(rows=rows)
    w.put(T_SIGN + 60)
    _none(w)
    assert w.pdfs.calls == [] and any("ambiguous" in ln for ln in w.sign_lines()), w.sign_lines()


def test_e_other_bike_no_card():
    rows = live_rows()
    rows[2]["bike"] = "PCX 160 WHITE PHUKET 5580"
    w = World(rows=rows)
    w.put(T_SIGN + 60)
    _none(w)
    assert w.pdfs.calls == [] and any("conflict" in ln for ln in w.sign_lines()), w.sign_lines()


def test_e_bike_homoglyph_same_plate_card():
    """Байк в реестре латиницей («400CC»), в листе броней — кириллицей («400СС»): номер байка 6334 один, `bind_contract`
    его сверил — карточка есть (договор, привязанный кодом, второй раз байк строкой не сличается)."""
    rows = live_rows()
    rows[2]["bike"] = "NINJA 400CC PHUKET 6334"
    assert rows[2]["bike"] != BIKE
    w = World(rows=rows)
    did = _card(w)
    assert w.attach(did)[0] == "PDF36", w.attach(did)


def test_e_out_of_term_no_card_no_second_search():
    """Подписанный договор вне срока аренды — карточки нет; второго поиска без срока (он только НАЗЫВАЕТ договор другой
    аренды, фактом не бывает) проход не делает: реестр спрошен ровно раз, со сроком."""
    rows = live_rows()
    for r in rows:
        r.update(contract_date="2026-10-20", contract_date_raw="2026-10-20")   # дата договора вне аренды 14..17
    w = World(rows=rows)
    w.put(T_SIGN + 60)
    _none(w)
    assert w.pdfs.calls == [], w.pdfs.calls
    assert w.registry.calls == [{"phone": NUM, "date_from": "2026-10-14", "date_to": "2026-10-17"}], w.registry.calls


def test_e_before_watershed_no_card():
    start = T_SIGN + 7 * 3600                                     # первый запуск через 7 ч после подписи (окно 6 ч)
    w = World(start=start)
    since = float(w.q("SELECT value FROM meta WHERE key=?", (X.SIGNED_SINCE,))[0][0])
    assert since == start - 6 * 3600 > T_SIGN, since
    w.put(start + 60)
    _none(w, start + 600)
    assert w.pdfs.calls == [] and any("раньше водораздела" in ln for ln in w.sign_lines()), w.sign_lines()


def test_e_flag_off_no_card_no_doors():
    w = World(signed=False, text=None)
    w.put(T_SIGN + 60)
    _none(w)
    assert not w.core.signed and w.core.make_signed_cards(T_SIGN + 10000) == 0
    assert w.registry.calls == [] and w.rental_calls == [] and w.pdfs.calls == [], "флаг выкл — ни одного вызова двери"
    tables = {r[0] for r in w.q("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "signed_cards" not in tables and w.q("SELECT 1 FROM meta WHERE key=?", (X.SIGNED_SINCE,)) == [], tables
    assert w.core.card_label(1) is None


def test_e_flag_turned_off_after_on_no_doors():
    """Флаг выключили после работы: водораздел и таблица в базе есть, а такт — ни одного вызова двери и карточки нет."""
    w = World()
    assert w.q("SELECT 1 FROM meta WHERE key=?", (X.SIGNED_SINCE,)) == [(1,)]
    w.signed = False
    w.restart()
    w.put(T_SIGN + 60)
    _none(w)
    assert not w.core.signed and w.core.make_signed_cards(T_SIGN + 10000) == 0
    assert w.registry.calls == [] and w.rental_calls == [] and w.pdfs.calls == [], "флаг выкл — ни одного вызова двери"


def test_e_no_rental_door_means_off():
    """У модели нет двери аренды сверки (`_tool_doors`) — карточка подписи выключена, водораздел не пишется."""
    w = World(rental=False)
    w.put(T_SIGN + 60)
    _none(w)
    assert not w.core.signed and w.registry.calls == [], "без двери аренды карточки подписи нет"
    assert w.q("SELECT 1 FROM meta WHERE key=?", (X.SIGNED_SINCE,)) == []


def test_e_no_active_rental_no_contract_call():
    w = World(book=[book_row(status="Бронь")])                    # аренда не активна — факта аренды нет
    w.put(T_SIGN + 60)
    _none(w)
    assert w.rental_calls == [NUM] and w.registry.calls == [], (w.rental_calls, w.registry.calls)


# ── (е) claimed / sending у номера → пропуск ───────────────────────────────────────────────────────────

def test_f_claimed_or_sending_skips():
    reg = Registry(live_rows()[:2])
    w = World(tools_out=NO_CONTRACT, text="Спасибо!", registry=reg)
    w.put(T_SIGN - 300)
    w.tick(T_SIGN - 100)
    assert w.q("SELECT id, state FROM drafts") == [(1, A.PENDING)]
    reg.rows.append(live_rows()[2])
    t = T_SIGN + 600
    for state in (A.CLAIMED, A.SENDING):
        w.x("UPDATE drafts SET state=? WHERE id=1", (state,))
        n = len(reg.calls)
        w.tick(t)
        assert w.signed_drafts() == [] and len(reg.calls) == n and w.pdfs.calls == [], (state, w.sign_lines())
        t += X.SIGNED_EVERY + 1
    w.x("UPDATE drafts SET state=? WHERE id=1", (A.PENDING,))      # снова ждёт — карточка рождается (пропуск был тактом)
    w.tick(t)
    assert len(w.signed_drafts()) == 1 and w.q("SELECT state FROM drafts WHERE id=1") == [(A.SUPERSEDED,)]


# ── (ж) двойник sha256 → карточки нет ───────────────────────────────────────────────────────────────────

def test_g_twin_sha_no_card():
    reg = Registry(live_rows()[:2])                               # такт ответа модели: стр.36 ещё не видна реестру
    w = World(tools_out=model_pdf36(), text="Договор ниже", registry=reg)
    w.put(T_SIGN + 60)
    w.tick(T_SIGN + 300)
    assert w.q("SELECT id, state FROM drafts") == [(1, A.PENDING)] and w.attach(1)[3] == SHA36
    reg.rows.append(live_rows()[2])
    out = w.core.press(1, 1, A.ACT_SEND, "Даня", T_SIGN + 400)    # ответ модели ушёл с этим PDF
    assert out["ok"] and len(w.door.media) == 1, out
    w.tick(T_SIGN + 300 + X.SIGNED_EVERY + 10)
    assert w.signed_drafts() == [], w.signed_drafts()
    assert w.versions() == [(NUM, "D36", "2026-10-14 19:04", "PDF36", SHA36, 1)], w.versions()
    assert any("уже уходил черновиком 1" in ln for ln in w.sign_lines()), w.sign_lines()


# ── (з) извинение после 30 мин и язык RU/EN ────────────────────────────────────────────────────────────

def test_h_apology_after_30_min_ru():
    w = World()
    did = _card(w, t=T_SIGN + X.SIGNED_LATE + 60)
    assert w.signed_drafts()[0][2] == X.SIGNED_SORRY["ru"] + RU_TEXT, w.signed_drafts()
    assert w.signed_drafts()[0][2] == "Извините за задержку с ответом и договором. Направляем ваш подписанный договор."
    assert any("с извинением" in ln for ln in w.sign_lines() if "черновик %d" % did in ln), w.sign_lines()


def test_h_english_and_english_apology():
    w = World()
    _card(w, text="I have signed it")
    assert w.signed_drafts()[0][2] == "Here is your signed rental agreement.", w.signed_drafts()
    w2 = World()
    _card(w2, t=T_SIGN + 40 * 60, text="Signed, thanks")
    assert w2.signed_drafts()[0][2] == ("Sorry for the delay with our reply and the agreement. "
                                        "Here is your signed rental agreement."), w2.signed_drafts()


def test_h_language_skips_inbound_without_letters():
    """Последнее входящее без букв (смайл, фото) языка не говорит — берётся предыдущее с буквами."""
    w = World()
    w.put(T_SIGN + 30, "Договор подписал")
    w.put(T_SIGN + 60, "👍")
    w.tick(T_SIGN + 600)
    assert [r[2] for r in w.signed_drafts()] == [RU_TEXT], w.signed_drafts()
    assert X.signed_lang("👍 12") is None and X.signed_lang("ok") == "en" and X.signed_lang("ок") == "ru"
    assert X.signed_text("th", False) == EN_TEXT


def test_h_no_promises_only_template():
    for lang in ("ru", "en"):
        for late in (False, True):
            txt = X.signed_text(lang, late)
            assert not any(ch.isdigit() for ch in txt), txt     # ни сроков, ни сумм
            assert txt in (RU_TEXT, EN_TEXT, X.SIGNED_SORRY["ru"] + RU_TEXT, X.SIGNED_SORRY["en"] + EN_TEXT), txt


# ── (и) атомарность: запись версии и вставка черновика — одной транзакцией ─────────────────────────────

def test_i_version_and_draft_one_transaction():
    reg = Registry(live_rows()[:2])
    w = World(tools_out=NO_CONTRACT, text="Спасибо!", registry=reg)
    w.put(T_SIGN - 300)
    w.tick(T_SIGN - 100)
    reg.rows.append(live_rows()[2])
    w.x("CREATE TRIGGER boom BEFORE INSERT ON attach WHEN NEW.opora LIKE '%карточка подписанного%' "
        "BEGIN SELECT RAISE(ABORT, 'boom'); END")
    w.tick(T_SIGN + 600)
    assert w.signed_drafts() == [] and w.versions() == [], (w.signed_drafts(), w.versions())
    assert w.q("SELECT id, state FROM drafts") == [(1, A.PENDING)], "снятие ждущего откатилось вместе со вставкой"
    assert w.q("SELECT state FROM card_out WHERE draft_id=1") == [(A.CARD_DELIVERED,)], "карточка снятого не тронута"
    assert any("разбор упал" in ln for ln in w.sign_lines()), w.sign_lines()
    w.x("DROP TRIGGER boom")
    w.tick(T_SIGN + 600 + X.SIGNED_EVERY + 1)
    assert len(w.signed_drafts()) == 1 and len(w.versions()) == 1, (w.signed_drafts(), w.versions())


def test_i_card_queue_in_same_transaction():
    """Очередь карточки черновика подписи и решённая карточка снятого ложатся В ТРАНЗАКЦИИ: после COMMIT база занята
    (первая попытка карточки упала) — черновик всё равно в очереди доставки, а не «ждёт, но невидим до рестарта»."""
    reg = Registry(live_rows()[:2])
    w = World(tools_out=NO_CONTRACT, text="Спасибо!", registry=reg)
    w.put(T_SIGN - 300)
    w.tick(T_SIGN - 100)
    reg.rows.append(live_rows()[2])
    real = w.core._card_new

    def busy(*a):
        raise sqlite3.OperationalError("database is locked")
    w.core._card_new = busy
    w.tick(T_SIGN + 600)
    did = w.signed_drafts()[0][0]
    assert w.q("SELECT state FROM card_out WHERE draft_id=? AND ver=1", (did,)) == [(A.CARD_WAIT,)]
    assert w.q("SELECT state FROM card_out WHERE draft_id=1") == [(A.CARD_DECIDED,)], "карточка снятого решена"
    w.core._card_new = real
    w.tick(T_SIGN + 600 + 400)                                     # очередь ядра доставляет карточку позже
    assert w.q("SELECT state FROM card_out WHERE draft_id=? AND ver=1", (did,)) == [(A.CARD_DELIVERED,)]
    assert did in w.tg.cards and len(w.signed_drafts()) == 1, w.tg.cards


def test_i_held_rechecked_inside_transaction():
    """Двойник появился между проверкой и транзакцией (второй экземпляр службы успел отправить этот PDF) — проверка
    повторяется ВНУТРИ транзакции: карточки нет, следующий проход записывает версию двойником."""
    w = World()
    w.put(T_SIGN + 60)
    real = w.core._signed_lang

    def race(number, upto):                                      # зовётся ДО транзакции — здесь «успевает» второй
        w.core.db.execute("INSERT INTO drafts(id, number, state, ver, text, upto_id, created_at) VALUES(901,?,?,1,"
                          "'Договор ниже',0,?)", (NUM, A.SENT, T_SIGN))
        w.core.db.execute("INSERT INTO attach(draft_id, file_id, name, size, sha256, row, doc_id, ts) VALUES(901,"
                          "'PDF36','c.pdf',?,?,36,'D36',?)", (len(PDF36), SHA36, T_SIGN))
        w.core.db.execute("INSERT INTO pdf_parts(draft_id, state, attempt, wamid) VALUES(901,?,1,'wamid.X')", (A.SENT,))
        w.core._signed_lang = real
        return real(number, upto)
    w.core._signed_lang = race
    w.tick(T_SIGN + 600)
    assert w.signed_drafts() == [] and w.versions() == [], (w.signed_drafts(), w.versions())
    w.tick(T_SIGN + 600 + X.SIGNED_EVERY + 1)
    assert w.versions() == [(NUM, "D36", "2026-10-14 19:04", "PDF36", SHA36, 901)], w.versions()


# ── FIX1410: текст подписи без PDF не уходит ────────────────────────────────────────────────────────────

def test_k_twin_at_press_signed_card_stale_nothing_sent():
    """Пока карточка подписи ждала, этот PDF ушёл другим черновиком («Дослать PDF» на старой карточке) — при нажатии
    двойник снимает PDF; карточка подписи без PDF НЕ шлёт и текст: stale словами, клиенту ничего."""
    w = World()
    did = _card(w)
    w.x("INSERT INTO drafts(id, number, state, ver, text, upto_id, created_at) VALUES(900,?,?,1,'Договор ниже',0,?)",
        (NUM, A.SENT, T_SIGN))
    w.x("INSERT INTO attach(draft_id, file_id, name, size, sha256, row, doc_id, ts) VALUES(900,'PDF36','c.pdf',?,?,36,"
        "'D36',?)", (len(PDF36), SHA36, T_SIGN))
    w.x("INSERT INTO pdf_parts(draft_id, state, attempt, wamid) VALUES(900,?,2,'wamid.OLD')", (A.SENT,))
    calls = len(w.registry.calls)
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    assert out["state"] == A.STALE and not out["ok"], out
    assert out["words"].startswith("устарело: карточка подписанного договора без PDF не уходит"), out
    assert "черновик 900" in out["words"], out
    assert w.door.sends == [] and w.door.media == [], (w.door.sends, w.door.media)
    assert len(w.registry.calls) == calls, "без PDF отправлять нечего — реестр не перечитывается"
    assert w.q("SELECT state FROM drafts WHERE id=?", (did,)) == [(A.STALE,)]


def test_k_signed_card_without_pdf_label_none_and_no_text():
    """PDF со строки attach снят (версия по пояснению без PDF) — метки «📄 Договор подписан» нет, «Отправить» — stale."""
    w = World()
    did = _card(w)
    w.x("UPDATE attach SET file_id=NULL, reason='PDF не приложен — сверка версии по пояснению' WHERE draft_id=?", (did,))
    assert w.core.card_label(did) is None
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    assert out["state"] == A.STALE and w.door.sends == [] and w.door.media == [], (out, w.door.sends)


def test_k_sent_with_pdf_waiting_is_covered():
    """Текст ответа модели ушёл, а PDF — нет (на его карточке живёт «Дослать PDF»): тот же PDF второй карточкой не
    подаётся — версия «покрыта» тем черновиком."""
    reg = Registry(live_rows()[:2])
    w = World(tools_out=model_pdf36(), text="Договор ниже", registry=reg)
    w.put(T_SIGN + 60)
    w.tick(T_SIGN + 300)
    reg.rows.append(live_rows()[2])
    w.door.media_out = "not_sent"
    out = w.core.press(1, 1, A.ACT_SEND, "Даня", T_SIGN + 400)
    assert out["parts"] == {"text": A.SENT, "pdf": A.NOT_SENT}, out
    assert w.core.card_buttons(1), "на карточке ответа модели — «Дослать PDF»"
    w.tick(T_SIGN + 300 + X.SIGNED_EVERY + 10)
    assert w.signed_drafts() == [], w.signed_drafts()
    assert w.versions() == [(NUM, "D36", "2026-10-14 19:04", "PDF36", SHA36, 1)], w.versions()
    assert any("ждёт «Дослать PDF» на карточке черновика 1" in ln for ln in w.sign_lines()), w.sign_lines()


def test_k_document_sent_by_human_from_phone_covers():
    """После подписи человек сам отправил документ с телефона (эхо вида document паузы не ставит) — второго PDF нет."""
    w = World()
    w.put(T_SIGN + 60)
    w.put(T_SIGN + 120, "", kind="echo", msg_type="document")
    w.tick(T_SIGN + 600)
    assert w.q("SELECT paused FROM clients WHERE number=?", (NUM,)) == [(0,)], "документ с телефона паузы не ставит"
    assert w.signed_drafts() == [], w.signed_drafts()
    assert w.versions() == [(NUM, "D36", "2026-10-14 19:04", "PDF36", SHA36, None)], w.versions()
    assert any("ушёл человеком с телефона" in ln for ln in w.sign_lines()), w.sign_lines()
    assert w.core.signed_counts() == {"человек": 1}, w.core.signed_counts()


def test_k_document_before_signing_does_not_cover():
    """Документ с телефона ДО подписи — не подписанный договор: карточка есть."""
    w = World()
    w.put(T_SIGN - 600, "", kind="echo", msg_type="document")
    w.put(T_SIGN + 60)
    w.tick(T_SIGN + 600)
    assert len(w.signed_drafts()) == 1, w.sign_lines()


def test_k_document_from_topic_covers():
    """Документ из темы (relay медиа: `outbox` «тема», вид document) после подписи — карточки нет."""
    w = World()
    w.put(T_SIGN + 60)
    w.x("INSERT INTO outbox(wamid, number, ts, text, via, kind) VALUES('wamid.H1',?,?,'[документ]',?,'document')",
        (NUM, T_SIGN + 200, A.VIA_TOPIC))
    w.tick(T_SIGN + 600)
    assert w.signed_drafts() == [] and any("из темы" in ln for ln in w.sign_lines()), w.sign_lines()


# ── FIX1410: модель отвечает первой, вопрос клиента не теряется ─────────────────────────────────────────

def test_j_quiet_core_answers_first():
    """Пока не вышла тишина ядра (`quiet` после последнего входящего), проход номер не трогает — ни дверей, ни карточки:
    первой на «подписал, …» отвечает модель (её черновик с PDF «покроет» версию)."""
    w = World()
    w.put(T_SIGN + 60)
    w.tick(T_SIGN + 60 + w.core.quiet - 10)
    assert w.signed_drafts() == [] and w.registry.calls == [] and w.rental_calls == [], w.sign_lines()
    w.tick(T_SIGN + 60 + w.core.quiet - 10 + X.SIGNED_EVERY)
    assert len(w.signed_drafts()) == 1, w.sign_lines()


def test_j_question_carried_from_superseded():
    """Снятый ответ модели знал вопрос клиента — черновик подписи несёт его и язык вопроса: карточка показывает, что
    спросил клиент (WACARDQ0410)."""
    reg = Registry(live_rows()[:2])
    ask = "Подписал. Во сколько доставка?"
    w = World(tools_out=NO_CONTRACT, text={"text": "Спасибо!", "question": ask, "q_lang": "ru"}, registry=reg)
    w.put(T_SIGN - 300, ask)
    w.tick(T_SIGN - 100)
    assert w.q("SELECT question FROM drafts WHERE id=1") == [(ask,)]
    reg.rows.append(live_rows()[2])
    w.tick(T_SIGN + 600)
    did = w.signed_drafts()[0][0]
    assert w.q("SELECT question, q_lang FROM drafts WHERE id=?", (did,)) == [(ask, "ru")]
    assert w.core.card_extra(did, 1, RU_TEXT)["question"] == ask
    assert any("вопрос клиента — из него" in ln for ln in w.sign_lines()), w.sign_lines()


def test_j_language_when_nothing_superseded():
    w = World()
    did = _card(w, text="Signed")
    assert w.q("SELECT question, q_lang FROM drafts WHERE id=?", (did,)) == [(None, "en")]


# ── FIX1410: «покрытие», снятое ядром, — версия снова открыта; тот же PDF под новой строкой ──────────────

def test_l_reopen_after_cover_died():
    """Ответ модели с этим PDF «покрыл» версию, клиент написал ещё — ядро сняло его (stale), новый ответ модели без PDF:
    версия снова открыта. Финальный разбор: живой ответ модели ради повтора НЕ снимается — карточка ждёт его решения
    (реестр не дёргается), затем карточка подписи (одна строка версии, черновик — подписи)."""
    w = World(tools_out=model_pdf36(), text="Договор ниже")
    w.put(T_SIGN + 60)
    w.tick(T_SIGN + 600)
    assert w.versions()[0][5] == 1 and w.signed_drafts() == [], w.versions()
    w.model.tools_out, w.model.text = NO_CONTRACT, "Хорошо"
    w.put(T_SIGN + 700, "Ок")
    w.tick(T_SIGN + 800)
    states = dict(w.q("SELECT id, state FROM drafts WHERE id IN (1, 2)"))
    assert states == {1: A.STALE, 2: A.PENDING} and w.signed_drafts() == [], (states, w.sign_lines())
    n = len(w.registry.calls)
    w.tick(T_SIGN + 800 + X.SIGNED_EVERY + 1)
    assert len(w.registry.calls) == n, "повтор ждёт ответа модели — реестр не спрашивается"
    assert w.core.press(2, 1, A.ACT_DECLINE, "Даня", T_SIGN + 1000)["ok"]
    w.model.text = None
    w.tick(T_SIGN + 1000 + 2 * X.SIGNED_EVERY)
    sd = w.signed_drafts()
    assert len(sd) == 1, (sd, w.sign_lines())
    assert w.versions() == [(NUM, "D36", "2026-10-14 19:04", "PDF36", SHA36, sd[0][0])], w.versions()
    assert any("версия снова открыта" in ln for ln in w.sign_lines()), w.sign_lines()


def test_l_declined_cover_stays_decided():
    """«Не нужно» на ответе модели с этим PDF — решение человека: версия остаётся решённой, карточки подписи нет."""
    w = World(tools_out=model_pdf36(), text="Договор ниже")
    w.put(T_SIGN + 60)
    w.tick(T_SIGN + 600)
    assert w.core.press(1, 1, A.ACT_DECLINE, "Даня", T_SIGN + 650)["ok"]
    w.model.tools_out, w.model.text = None, None
    w.put(T_SIGN + 700, "Ок")
    w.tick(T_SIGN + 800)
    w.tick(T_SIGN + 800 + X.SIGNED_IDLE + 1)
    assert w.signed_drafts() == [] and w.versions()[0][5] == 1, (w.signed_drafts(), w.versions())


def test_l_same_pdf_new_registry_key_after_decline():
    """«Не нужно» на карточке подписи, потом тот же файл переоформлен новой строкой реестра — тот же sha256 уже решён:
    второй карточки нет."""
    w = World()
    did = _card(w)
    assert w.core.press(did, 1, A.ACT_DECLINE, "Даня", T_SIGN + 650)["ok"]
    w.registry.revoke(36)
    w.registry.rows.append(reg_row(37, "ПОДПИСАН", "2026-10-14 19:20", "PDF36"))
    w.tick(T_SIGN + 600 + X.SIGNED_IDLE + 10)
    assert [r[0] for r in w.signed_drafts()] == [did], w.signed_drafts()
    assert any("уже решён другой версией реестра" in ln for ln in w.sign_lines()), w.sign_lines()


# ── FIX1410: проход не держит поток службы ───────────────────────────────────────────────────────────────

def _two_clients(**kw):
    rows = live_rows() + [row_num2()]
    w = World(rows=rows, book=[book_row(), book_row(bike=BIKE2, contacts=CONTACTS2, booking="B5580")], **kw)
    w.put(T_SIGN + 60)
    w.put(T_SIGN + 60, number=NUM2)
    return w


def test_m_pass_budget_and_cursor():
    """Больной мост: реестр отвечает 25 с — после первого номера бюджет прохода (SIGNED_PASS_SEC) исчерпан, второй
    номер — следующим проходом и ПЕРВЫМ (курсор), а пауза SIGNED_EVERY считается от конца прохода."""
    w = _two_clients()
    w.registry.slow = 25
    t = T_SIGN + 600
    w.tick(t)
    assert w.registry.phones() == [T.last9(NUM2)], w.registry.phones()      # номера по порядку: NUM2 < NUM
    assert [r[0] for r in w.q("SELECT number FROM drafts WHERE kind=?", (X.KIND_SIGNED,))] == [NUM2]
    assert any("проход прерван — бюджет прохода %d с исчерпан" % X.SIGNED_PASS_SEC in ln for ln in w.lines), w.lines
    w.tick(t + 25 + X.SIGNED_EVERY - 1)                           # от конца прохода ещё не прошло SIGNED_EVERY
    assert len(w.registry.calls) == 1
    w.tick(t + 25 + X.SIGNED_EVERY + 1)
    assert w.registry.phones() == [T.last9(NUM2), T.last9(NUM)], w.registry.phones()
    assert sorted(r[0] for r in w.q("SELECT number FROM drafts WHERE kind=?", (X.KIND_SIGNED,))) == sorted([NUM, NUM2])


def test_m_first_door_timeout_ends_pass():
    """Первый таймаут реестра кончает проход (больной мост не держит поток N раз по 60 с); следующий проход начинается с
    номера после курсора — второй клиент получает карточку, хотя первый всё ещё в сбое."""
    w = _two_clients()
    w.registry.fail = T.last9(NUM2)
    w.tick(T_SIGN + 600)
    assert w.registry.phones() == [T.last9(NUM2)] and w.signed_drafts() == [], w.registry.phones()
    assert any("проход прерван — реестр подписей: timeout" in ln for ln in w.lines), w.lines
    w.tick(T_SIGN + 600 + X.SIGNED_EVERY + 1)
    assert w.registry.phones()[1] == T.last9(NUM), w.registry.phones()
    assert [r[0] for r in w.q("SELECT number FROM drafts WHERE kind=?", (X.KIND_SIGNED,))] == [NUM]


def test_m_pass_max_numbers():
    assert X.SIGNED_PASS_MAX == 10 and X.SIGNED_PASS_SEC == 20 and X.SIGNED_IDLE == 600


def test_m_idle_until_new_inbound():
    """Решённая версия — номер не спрашивается до SIGNED_IDLE; новое входящее клиента — сразу."""
    w = World()
    _card(w)
    t = T_SIGN + 600
    for k in (1, 2, 3):
        w.tick(t + k * (X.SIGNED_EVERY + 1))
    assert len(w.registry.calls) == 1, w.registry.calls
    w.put(t + 500, "ещё вопрос")
    w.tick(t + 500 + X.SIGNED_EVERY)
    # новое входящее сняло карточку (ядро), модель промолчала — версия снова открыта: одна новая карточка
    assert len(w.registry.calls) == 2 and len(w.signed_drafts()) == 2, (w.registry.calls, w.signed_drafts())
    w.tick(t + X.SIGNED_IDLE + 2 * X.SIGNED_EVERY + 600)
    assert len(w.registry.calls) == 3, "IDLE вышел — номер проверен снова"


def test_m_empty_registry_slows_after_two_passes():
    """«Договора нет» — первые SIGNED_EMPTY_FREE проходов с обычным шагом (клиент подписывает прямо сейчас), дальше номер
    ждёт SIGNED_IDLE или нового входящего."""
    reg = Registry(live_rows()[:2])
    w = World(registry=reg)
    w.put(T_SIGN + 60)
    t = T_SIGN + 600
    for k in range(5):
        w.tick(t + k * (X.SIGNED_EVERY + 1))
    assert len(reg.calls) == X.SIGNED_EMPTY_FREE + 1, reg.calls
    reg.rows.append(live_rows()[2])
    w.put(t + 700, "подписал!")
    w.tick(t + 700 + X.SIGNED_EVERY)
    assert len(w.signed_drafts()) == 1, w.sign_lines()


def test_m_pdf_failures_back_off():
    """PDF не читается подряд: первые два сбоя — обычный шаг такта, после третьего — пауза SIGNED_RETRY (реестр и PDF
    не дёргаются каждые 120 с); починилось — карточка."""
    w = World()
    w.pdfs.files.pop("PDF36")
    w.put(T_SIGN + 60)
    t = T_SIGN + 600
    for k in range(3):
        w.tick(t + k * (X.SIGNED_EVERY + 1))
    assert len(w.pdfs.calls) == 3 and w.signed_drafts() == [], w.pdfs.calls
    w.tick(t + 3 * (X.SIGNED_EVERY + 1))
    w.tick(t + 4 * (X.SIGNED_EVERY + 1))
    assert len(w.pdfs.calls) == 3 and len(w.registry.calls) == 3, (w.pdfs.calls, w.registry.calls)
    w.pdfs.files["PDF36"] = (36, PDF36)
    w.tick(t + 2 * (X.SIGNED_EVERY + 1) + X.SIGNED_RETRY[2] + 1)
    assert len(w.signed_drafts()) == 1, w.sign_lines()


# ── карточка Telegram: метка «📄 Договор подписан» (настоящие руки `wa_agent_tg.Tg`) ───────────────────

def test_card_label_real_tg():
    import test_wa_card_compact as C
    http = C.FakeHttp()
    d = tempfile.mkdtemp(prefix="wa_signed_card_tg_")
    mpath = os.path.join(d, "mirror.db")
    m = sqlite3.connect(mpath)
    m.execute("CREATE TABLE topics (number TEXT PRIMARY KEY, thread_id INTEGER, trigger_id INTEGER, stage TEXT, "
              "ts REAL, name TEXT)")
    m.execute("INSERT INTO topics VALUES(?,?,?,?,?,?)", (NUM, 42, 1, "live", T_SIGN, "Иван · +" + NUM))
    m.commit()
    m.close()
    tg = G.Tg("123:SECRET", enabled=True, show_chat="-1004401325262", mirror_db=mpath, http=http,
              clock=lambda: T_SIGN + 600, log=lambda s: None)
    w = World(tg=tg)
    did = _card(w)
    msgs = http.of("sendMessage")
    card = [p for p in msgs if "reply_markup" in p][-1]
    assert card["text"].startswith("%s №%d · версия 1" % (X.W_SIGNED_LABEL, did)), card["text"][:120]
    assert "«Отправить» шлёт ВТОРЫМ сообщением подписанный PDF договора" in card["text"], card["text"]
    assert "прочитал КОД" in card["text"], card["text"]
    kb = [b["callback_data"] for row in card["reply_markup"]["inline_keyboard"] for b in row]
    assert kb[0] == "wa:send:%d:1" % did, kb


def test_other_kinds_label_unchanged():
    w = World(tools_out=NO_CONTRACT, text="Спасибо!", registry=Registry([]))
    w.put(T_SIGN + 60)
    w.tick(T_SIGN + 600)
    assert w.core.card_label(1) is None and w.core.draft_kind(1) is None


# ── служба: флаг, строка старта, дверь аренды модели, бюджет прохода ────────────────────────────────────

class SvcModel(object):
    """Модель службы: `_tool_doors` — как у `ModelAdapter` (дверь аренды той же сверки)."""
    tools = None
    case = None

    def __init__(self):
        self.seen = []

    def _tool_doors(self, number, upto_id):
        self.seen.append(number)
        return {"history": lambda: [], "rental": lambda: {"ok": True, "rows": []}, "rules": lambda: None}


@contextlib.contextmanager
def _nobudget(seconds):
    yield


def _svc_kw(environ, attach=True, model=None):
    return S.signed_of(environ, attach, model if model is not None else SvcModel(), budget=_nobudget)


def test_svc_flag_and_start_line():
    on, kw, words = _svc_kw({S.F_SIGNED: "1", S.F_BOOK: "1"})
    assert on and kw == {"signed": True, "signed_lookback_h": 6, "signed_budget": _nobudget}, kw
    assert words.startswith("вкл — ") and "120 с" in words and "20 с" in words, words
    on, kw, _ = _svc_kw({S.F_SIGNED: "yes", S.F_BOOK: "1", S.F_SIGNED_LOOKBACK: "2"})
    assert on and kw["signed_lookback_h"] == 2
    on, kw, _ = S.signed_of({S.F_SIGNED: "1", S.F_BOOK: "1"}, True, SvcModel())
    assert on and kw["signed_budget"] is S._signed_budget, "по умолчанию — свой бюджет прохода службы"
    _on, kw, words = _svc_kw({S.F_SIGNED: "1", S.F_BOOK: "1", S.F_SIGNED_LOOKBACK: "шесть"})
    assert kw["signed_lookback_h"] == 6 and "битая" in words, words
    off = _svc_kw({})
    assert off[0] is False and off[1] is None and off[2].startswith("выкл — "), off
    assert _svc_kw({}, attach=False) == (False, None, None), "ни флага, ни PDF клиенту — строки нет"
    no_attach = _svc_kw({S.F_SIGNED: "1", S.F_BOOK: "1"}, attach=False)
    assert no_attach[0] is False and "не засчитан" in no_attach[2], no_attach
    no_door = S.signed_of({S.F_SIGNED: "1", S.F_BOOK: "1"}, True, object())
    assert no_door[0] is False and "нет двери аренды" in no_door[2], no_door
    assert (S.F_SIGNED, S.SIGNED_EVERY_SEC, S.SIGNED_LOOKBACK_DEFAULT) == (X.F_SIGNED, X.SIGNED_EVERY,
                                                                          X.SIGNED_LOOKBACK_H)
    assert (S.SIGNED_LOOKBACK_MAX, S.SIGNED_PASS_SEC, S.SIGNED_KIND) == (X.SIGNED_LOOKBACK_MAX_H, X.SIGNED_PASS_SEC,
                                                                        X.KIND_SIGNED)


def test_svc_books_off_means_off():
    """Брони выключены и дела аренды нет — аренда не станет фактом: флаг не засчитан, водораздел не пишется."""
    off = _svc_kw({S.F_SIGNED: "1"})
    assert off[0] is False and off[1] is None and "брони" in off[2] and "водораздел не пишется" in off[2], off
    model = SvcModel()
    model.case = object()                                        # дело аренды есть — аренда берётся из дела
    assert _svc_kw({S.F_SIGNED: "1"}, model=model)[0] is True


def test_svc_lookback_ceiling():
    for raw, want, bad in (("24", 24, False), ("0", 0, False), ("25", 6, True), ("100000", 6, True), ("-1", 6, True)):
        hours, words = S.signed_lookback_of(raw)
        assert hours == want and (("битая" in words) is bad), (raw, hours, words)
    # ядро тоже не ставит водораздел дальше суток назад, что бы ему ни передали
    w = World(lookback_h=100000)
    since = float(w.q("SELECT value FROM meta WHERE key=?", (X.SIGNED_SINCE,))[0][0])
    assert since == T_START - X.SIGNED_LOOKBACK_MAX_H * 3600, since


def test_svc_press_door_respects_shorter_outer_budget():
    """Дверь договоров открывает свой бюджет нажатия (PRESS_BRIDGE_SEC) — КРОМЕ случая, когда уже открыт более короткий
    общий бюджет (проход карточки после подписи): иначе каждый вызов двери продлевал бы проход до 60 с."""
    import bridge_client
    seen = []

    @contextlib.contextmanager
    def spy(sec):
        seen.append(sec)
        yield
    door = S.press_door(lambda: "ok", budget=spy)
    assert door() == "ok" and seen == [S.PRESS_BRIDGE_SEC], seen
    with bridge_client.card_budget(5, label="t"):
        assert door() == "ok"
    assert seen == [S.PRESS_BRIDGE_SEC], "под коротким общим бюджетом свой не открывается"
    with bridge_client.card_budget(S.PRESS_BRIDGE_SEC * 10, label="t"):
        door()
    assert seen == [S.PRESS_BRIDGE_SEC] * 2, "длинный внешний бюджет — свой, короче, открывается"


def test_svc_signed_budget_label():
    import bridge_client
    with S._signed_budget(S.SIGNED_PASS_SEC):
        state = bridge_client.current_card_budget()
        assert state.label == "прохода карточки после подписи", state.label
        assert 0 < state.deadline - time.monotonic() <= S.SIGNED_PASS_SEC + 1
    assert bridge_client.current_card_budget() is None


def test_svc_build_passes_signed_to_core():
    import test_wa_attach_svc as AS

    class Model(AS.Model):
        def _tool_doors(self, number, upto_id):
            return {"rental": lambda: {"ok": True, "rows": []}, "history": lambda: []}
    on = dict(AS.ON, WA_AGENT_SIGNED_CARD="1")
    w = AS.World(on)
    w.model = Model()
    w.lines[:] = []
    w.build(on)
    said = [ln for ln in w.lines if ln.startswith("карточка после подписи (WA_AGENT_SIGNED_CARD): вкл — ")]
    assert said and type(w.core).__name__ == "AttachCore" and w.core.signed, (w.lines, w.core.signed)
    assert w.core.signed_budget is S._signed_budget
    assert sorted(w.core._signed_doors(NUM, 0)) == ["contract", "rental"], "ядро берёт аренду у модели, без истории"
    assert w.core._signed_doors(NUM, 0)["rental"]() == {"ok": True, "rows": []}
    w2 = AS.World(AS.ON)                                          # PDF клиенту вкл, карточка подписи — нет
    assert not w2.core.signed and any(ln.startswith("карточка после подписи (WA_AGENT_SIGNED_CARD): выкл — ")
                                      for ln in w2.lines), w2.lines
    w3 = AS.World(AS.BASE)                                        # ничего не запрошено — строки нет вовсе
    assert not [ln for ln in w3.lines if "WA_AGENT_SIGNED_CARD" in ln], w3.lines


def test_svc_attach_off_closes_signed_cards():
    """Служба поднялась без засчитанного WA_AGENT_ATTACH (прежнее ядро), а в базе ждут карточки подписи — прежнее
    «Отправить» отправило бы шаблон без PDF и без перечитывания: ждущая и отложенная сняты stale, клиенту ничего."""
    import test_wa_attach_svc as AS
    w = AS.World(AS.ON)
    db = sqlite3.connect(w.env["agent_db"])
    db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at, kind) VALUES(?,?,1,?,0,?,?)",
               (AS.NUM, A.PENDING, RU_TEXT, AS.T0, X.KIND_SIGNED))
    db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at, kind, due_at) VALUES(?,?,1,?,0,?,?,?)",
               ("66800000001", A.SCHEDULED, RU_TEXT, AS.T0, X.KIND_SIGNED, AS.T0 + 3600))
    db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at) VALUES(?,?,1,'обычный',0,?)",
               ("66800000002", A.PENDING, AS.T0))
    db.commit()
    db.close()
    w.restart(AS.BASE)
    assert type(w.core) is A.Core
    got = w.q("SELECT number, state, reason FROM drafts ORDER BY id")
    assert [g[1] for g in got] == [A.STALE, A.STALE, A.PENDING], got
    assert got[0][2] == S.W_SIGNED_ORPHAN and got[1][2] == S.W_SIGNED_ORPHAN, got
    assert any("карточек подписи снято stale 2 из 2" in ln for ln in w.lines), w.lines
    w.core.send_due(AS.T0 + 7200)
    assert w.sends == [], w.sends
    w2 = AS.World(AS.ON)                                          # PDF-ядро: карточка подписи живёт как жила
    db = sqlite3.connect(w2.env["agent_db"])
    db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at, kind) VALUES(?,?,1,?,0,?,?)",
               (AS.NUM, A.PENDING, RU_TEXT, AS.T0, X.KIND_SIGNED))
    db.commit()
    db.close()
    w2.restart(AS.ON)
    assert w2.q("SELECT state FROM drafts") == [(A.PENDING,)]


def test_svc_summary_counts():
    w = World()
    _card(w)

    class TgStub:
        polls = {"ok": 0, "fail": 0, "conflict": 0}
    w.core.db.execute("CREATE TABLE IF NOT EXISTS tg_cards (x INTEGER)")
    w.core.db.execute("CREATE TABLE IF NOT EXISTS tg_react_out (outcome TEXT)")
    words = {k: "выкл" for k in S.FLAGS}
    line = S.summary(w.core, TgStub(), words, {})
    assert " · подписей карточка=1" in line, line


# ── финальный разбор: текст подписи только вместе с PDF; повтор версии; бюджет прохода ─────────────────────

def test_f_press_pdf_unread_before_text_nothing_sent():
    """«Отправить» на карточке подписи: PDF при нажатии не прочитан — клиенту НИЧЕГО (ни текста, ни PDF), черновик
    назад в pending, кнопки живы; PDF снова читается — второе нажатие шлёт текст, затем PDF одним чтением."""
    w = World()
    did = _card(w)
    keep = w.pdfs.files.pop("PDF36")
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    assert not out["ok"] and out["state"] == A.PENDING and "ничего не отправлено" in out["words"], out
    assert w.door.sends == [] and w.door.media == [], (w.door.sends, w.door.media)
    assert w.q("SELECT state, decided_by FROM drafts WHERE id=?", (did,)) == [(A.PENDING, None)]
    w.pdfs.files["PDF36"] = keep
    n = len(w.pdfs.calls)
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 760)
    assert out["ok"] and out["words"] == "текст: ушёл · PDF: ушёл", out
    assert w.door.sends == [(NUM, RU_TEXT)] and len(w.door.media) == 1 and w.door.media[0][4] == SHA36, w.door.media
    assert len(w.pdfs.calls) == n + 1, ("PDF прочитан ОДИН раз за нажатие", w.pdfs.calls)


def test_f_press_pdf_changed_before_text_nothing_sent():
    """Файл подменили между карточкой и нажатием (другой sha256): текст подписи не уходит вовсе, черновик ждёт."""
    w = World()
    did = _card(w)
    w.pdfs.files["PDF36"] = (36, PDF37)
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    assert not out["ok"] and out["state"] == A.PENDING and "sha256" in out["words"], out
    assert w.door.sends == [] and w.door.media == [], (w.door.sends, w.door.media)


def test_f_reopen_waits_for_model_answer():
    """Повтор версии не снимает живой ответ модели на новое сообщение клиента: ответ жив, реестр ради повтора не
    дёргается; ответ решён — следующим проходом одна новая карточка той же версии."""
    w = World()
    did = _card(w)
    w.model.text = "Байк сдаётся 17.10 в 10:00"
    w.put(T_SIGN + 630, "А когда вернуть байк?")
    w.tick(T_SIGN + 630 + w.core.quiet + 45)
    rows = w.q("SELECT id, state, kind FROM drafts ORDER BY id")
    assert rows == [(did, A.STALE, X.KIND_SIGNED), (did + 1, A.PENDING, None)], rows
    n = len(w.registry.calls)
    w.tick(T_SIGN + 630 + w.core.quiet + 45 + 2 * X.SIGNED_EVERY)
    assert len(w.registry.calls) == n and w.q("SELECT state FROM drafts WHERE id=?", (did + 1,)) == [(A.PENDING,)]
    assert w.core.press(did + 1, 1, A.ACT_DECLINE, "Даня", T_SIGN + 1200)["ok"]
    w.model.text = None
    w.tick(T_SIGN + 1200 + 2 * X.SIGNED_EVERY)
    sd = w.signed_drafts()
    assert len(sd) == 2 and sd[1][1] == A.PENDING and len(w.versions()) == 1, (sd, w.versions())
    assert w.door.sends == [] and w.door.media == []


def test_f_declined_card_never_reopens():
    """«Не нужно» на карточке подписи — решение человека навсегда: новое входящее версию не открывает."""
    w = World()
    did = _card(w)
    assert w.core.press(did, 1, A.ACT_DECLINE, "Даня", T_SIGN + 650)["ok"]
    w.put(T_SIGN + 700, "ок")
    w.tick(T_SIGN + 700 + X.SIGNED_EVERY + 5)
    w.tick(T_SIGN + 700 + X.SIGNED_IDLE + 3 * X.SIGNED_EVERY)
    assert [r[0] for r in w.signed_drafts()] == [did], w.signed_drafts()


def test_f_budget_short_is_not_door_failure():
    """Общий бюджет прохода исчерпан на реестре (card_deadline): сбоем номеру не засчитывается (паузы не растут),
    следующий проход начинается С этого номера — карточка через один шаг такта."""
    w = World()
    w.registry.deadline = 1
    w.put(T_SIGN + 60, "Подписал договор")
    w.tick(T_SIGN + 600)
    assert w.signed_drafts() == [], w.signed_drafts()
    memo = w.core._signed_memo.get(NUM) or {}
    assert not memo.get("fails") and not memo.get("fail_at"), memo
    assert w.core._signed_resume == NUM, w.core._signed_resume
    w.tick(T_SIGN + 600 + X.SIGNED_EVERY + 1)
    assert len(w.signed_drafts()) == 1, (w.signed_drafts(), w.sign_lines())


def test_f_fresh_inbound_before_insert_no_card():
    """Клиент написал между сканом и вставкой (строка в очереди, скан ещё не разобрал): карточки нет, ничего не легло;
    модель отвечает первой, карточка — потом."""
    w = World()
    w.put(T_SIGN + 60, "Подписал договор")
    real = w.core._signed_lang

    def lang_then_write(number, upto):
        w.put(T_SIGN + 599, "а доставка во сколько?")
        return real(number, upto)
    w.core._signed_lang = lang_then_write
    w.tick(T_SIGN + 600)
    assert w.signed_drafts() == [] and w.versions() == [], (w.signed_drafts(), w.versions())


def test_f_signed_card_has_no_pace():
    """Ритм (WAHUMANPACE0210) карточке подписи не назначается: срока нет — уходит сразу по нажатию."""
    w = World()
    did = _card(w)
    x = w.q("SELECT number FROM drafts WHERE id=?", (did,))[0][0]
    w.x("UPDATE drafts SET state=? WHERE id=?", (A.CLAIMED, did))
    due, why = w.core._pace_due(x, 1, "t", T_SIGN + 700)
    assert due is None and why == X.W_SIGNED_PACE, (due, why)


def test_core_imports_untouched():
    """Подготовка живёт в `wa_agent_attach`: импорты модуля прежние (тот же замок, что `test_wa_agent_attach`)."""
    import ast
    tree = ast.parse(open(os.path.join(ROOT, "wa_agent_attach.py"), encoding="utf-8").read())
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
             for a in (n.names if isinstance(n, ast.Import) else [ast.alias(n.module or "")])}
    assert names == {"base64", "hashlib", "re", "zlib", "wa_agent", "wa_agent_tools"}, names


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
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
