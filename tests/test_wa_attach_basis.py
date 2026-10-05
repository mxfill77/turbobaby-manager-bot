#!/usr/bin/env python3
"""Основание PDF — опора судьи и живое чтение реестра перед отправкой (T4B3BASIS0510, Т4б-3). Всё на подделках:
временная очередь схемой wa_webhook, своя временная база, модель с итогом сверки Т4а, Telegram, дверь WhatsApp,
contract_pdf и contract_find — подделки. Сети нет, модель, мост, Telegram и WhatsApp не зовутся.

Каждый случай, кроме границы «черновик без PDF», падает на 5c4174f7 по существу: на базе дверь реестра конструктор не
знает, поэтому `World` подставляет её атрибутом — база её не читает, и случай падает на своём утверждении.
WA_AGENT_SRC=<каталог> подменяет модули (прогон «до» и мутантов)."""
import inspect
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import test_wa_agent_attach as AT  # noqa: E402  (подделки двери, Telegram, contract_pdf, contract_find)

NUM, T0, SHA, PDF = AT.NUM, AT.T0, AT.SHA, AT.PDF
WINDOW = "2026-10-01…2026-10-07"
SIGNED = "2026-10-01 10:15:00"
REQ_C = 'contract [["phone", "66812345678"]]'


def res(tool, outcome, facts=(), at=T0 + 50, req=None, window="", reason=""):
    r = {"tool": tool, "outcome": outcome, "source": "", "ref": "", "at": at, "version": "", "window": window,
         "reason": reason, "facts": list(facts)}
    if req:
        r["req"] = req
    return r


def contract_fact():
    return {"kind": "contract", "row": 41, "doc_id": "D41", "bike": "PCX 160 5580", "signed_at": SIGNED,
            "pdf_id": "F41", "booking_id": "B7"}


def tools(at=T0 + 50, extra=()):
    """Сверка Т4а: подписанный договор этой аренды и его PDF приняты; extra — дописанные позже ответы."""
    out = [
        res("rental", "fact", [{"kind": "rental", "booking_id": "B7", "bike": "PCX 160 5580",
                                "date_start": "2026-10-01", "date_end": "2026-10-07"}], at=at),
        res("contract", "fact", [contract_fact()], at=at, req=REQ_C, window=WINDOW),
        res("contract_pdf", "fact", [{"kind": "pdf", "id": "F41", "name": "contract_41.pdf", "size": len(PDF),
                                      "sha256": SHA, "row": 41}], at=at),
    ]
    return {"state": "done", "results": out + list(extra)}


class Model(A.Model):
    """Модель с итогом сверки и последним входящим клиента — как ModelAdapter.last (info.last_in)."""
    def __init__(self, tools_out, last_in=T0):
        self.calls, self.tools_out, self.last_in, self.last = 0, tools_out, last_in, None

    def draft(self, number, upto_id):
        self.calls += 1
        self.last = {"tools": self.tools_out, "info": {"last_in": self.last_in}}
        return "%s %d" % (AT.TEXT, self.calls)


def pick(**over):
    p = {"row": 41, "doc_id": "D41", "pdf_id": "F41", "signed_at": SIGNED, "signed": True}
    p.update(over)
    return p


class Find:
    """Реестр при нажатии: answer — ответ двери целиком, либо исключение crash."""
    def __init__(self, answer=None, crash=None, order=None):
        self.calls, self.answer, self.crash, self.order = [], answer, crash, order

    def __call__(self, **kw):
        self.calls.append(kw)
        if self.order is not None:
            self.order.append("find")
        if self.crash:
            raise self.crash
        if self.answer is not None:
            return self.answer
        return {"ok": True, "outcome": "one", "pick": pick(),
                "checked": {"rows_scanned": 50, "unread": [], "undated_signed": 0, "complete": True}}


class Door(AT.FakeDoor):
    def __init__(self, order=None, **kw):
        AT.FakeDoor.__init__(self, **kw)
        self.order = order

    def send_text(self, to, text):
        if self.order is not None:
            self.order.append("text")
        return AT.FakeDoor.send_text(self, to, text)

    def send_media(self, to, media):
        if self.order is not None:
            self.order.append("pdf")
        return AT.FakeDoor.send_media(self, to, media)


class World:
    def __init__(self, tools_out=None, find=None, door=None, last_in=T0):
        d = tempfile.mkdtemp(prefix="wa_attach_basis_t_")
        self.qpath, self.dbpath = os.path.join(d, "q.db"), os.path.join(d, "agent.db")
        q = sqlite3.connect(self.qpath)
        q.execute(AT.QSCHEMA)
        q.commit()
        q.close()
        self.model = Model(tools() if tools_out is None else tools_out, last_in)
        self.tg, self.door, self.fetch, self.find = AT.FakeTG(), door or Door(), AT.Fetch(), find or Find()
        self.lines = []
        kw = dict(log=self.lines.append, attach=True, pdf_fetch=self.fetch)
        if "contract_find" in inspect.signature(X.AttachCore.__init__).parameters:
            kw["contract_find"] = self.find
        self.core = X.AttachCore(self.dbpath, self.qpath, self.model, self.tg, self.door, **kw)
        self.core.contract_find = self.find              # база 5c4174f7 дверь не знает и не читает
        self.core.tick(T0 - 1000)

    def draft(self):
        q = sqlite3.connect(self.qpath)
        q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
                  "VALUES(?,?,?,?,?,?,0,?)", (T0, NUM, "text", "x", T0, 0, None))
        q.commit()
        q.close()
        made = self.core.tick(T0 + 100)
        assert made, "черновик не родился"
        return made[0]

    def q(self, sql, args=()):
        db = sqlite3.connect(self.dbpath)
        try:
            return db.execute(sql, args).fetchall()
        finally:
            db.close()

    def attach_row(self, did):
        return self.q("SELECT file_id, reason FROM attach WHERE draft_id=?", (did,))[0]

    def state(self, did):
        return self.q("SELECT state, reason FROM drafts WHERE id=?", (did,))[0]

    def nothing_sent(self):
        return self.door.sends == [] and self.door.media == [] and self.fetch.calls == []


def full(unread=(), undated=0, **over):
    return {"ok": True, "outcome": "one", "pick": pick(**over),
            "checked": {"rows_scanned": 50, "unread": list(unread), "undated_signed": undated, "complete": not unread}}


# ── основание — опора судьи ───────────────────────────────────────────────────────────────

def test_late_refusal_same_request_no_attachment():
    """Тот же запрос contract прочитан позже и отказал — sift снимает прежний факт: вложения нет, уходит только текст."""
    late = res("contract", "refused", at=T0 + 60, req=REQ_C, reason="дверь: timeout")
    w = World(tools(extra=[late]))
    did = w.draft()
    file_id, why = w.attach_row(did)
    assert file_id is None and "опорой судьи" in (why or ""), (file_id, why)
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["ok"] and w.door.media == [] and len(w.door.sends) == 1 and w.find.calls == [], out


def test_read_before_last_inbound_no_attachment():
    """Договор и PDF прочитаны раньше последнего входящего клиента — устарели, вложения нет."""
    w = World(tools(at=T0 - 50))
    did = w.draft()
    file_id, why = w.attach_row(did)
    assert file_id is None and "устарел" in (why or ""), (file_id, why)
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert w.door.media == [] and w.fetch.calls == []


# ── «Отправить»: реестр при нажатии ───────────────────────────────────────────────────────

def _press_refused(answer=None, crash=None, word=""):
    w = World(find=Find(answer=answer, crash=crash))
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["state"] == A.STALE and not out["ok"], out
    assert w.nothing_sent(), (w.door.sends, w.door.media, w.fetch.calls)
    st, why = w.state(did)
    assert st == A.STALE and "ничего не отправлено" in why and word in why, (st, why)
    assert len(w.find.calls) == 1
    return w, did


def test_press_new_version_nothing_sent():
    w, did = _press_refused(full(signed_at="2026-10-03 09:00:00"), word="signed_at")
    made = w.core.tick(T0 + 400)                   # пересборка со сверкой: новый черновик
    assert made and made[0] != did, made


def test_press_revoked_nothing_sent():
    _press_refused({"ok": True, "outcome": "none_signed", "checked": {"unread": [], "undated_signed": 0}},
                   word="отозван")


def test_press_second_signed_nothing_sent():
    _press_refused({"ok": True, "outcome": "ambiguous", "checked": {"unread": [], "undated_signed": 0}},
                   word="второй подписанный")


def test_press_incomplete_answer_nothing_sent():
    _press_refused(full(unread=["лист «Архив»"]), word="не целиком")
    _press_refused({"ok": True, "outcome": "one", "pick": pick(), "checked": {"rows_scanned": 50}},
                   word="не разобран")


def test_press_door_crash_nothing_sent():
    _press_refused(crash=RuntimeError("bridge down"), word="упала")


def test_press_door_refused_nothing_sent():
    _press_refused({"ok": False, "error": "unknown_action"}, word="не прочитан")


def test_same_basis_both_parts_as_before():
    order = []
    w = World(find=Find(order=order), door=Door(order=order))
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["ok"] and out["words"] == "текст: ушёл · PDF: ушёл", out
    assert order == ["find", "text", "pdf"], order
    assert w.find.calls == [{"phone": NUM, "date_from": "2026-10-01", "date_to": "2026-10-07"}], w.find.calls


# ── «Дослать PDF» ─────────────────────────────────────────────────────────────────────────

def test_resend_after_revoke_refused():
    w = World(door=Door(media="not_sent", media_reason="сервер отказал 400"))
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert len(w.door.media) == 1
    w.door.media_out = "sent"
    w.find.answer = {"ok": True, "outcome": "none_signed", "checked": {"unread": [], "undated_signed": 0}}
    got = w.core.press(did, 1, X.ACT_PDF, "Пым", T0 + 300)
    assert not got["ok"] and "отозван" in got["words"] and "PDF не ушёл" in got["words"], got
    assert len(w.door.media) == 1 and w.fetch.calls == ["F41"], (w.door.media, w.fetch.calls)
    assert w.q("SELECT state, attempt FROM pdf_parts WHERE draft_id=?", (did,))[0] == (A.NOT_SENT, 1)


def test_resend_same_basis_goes():
    w = World(door=Door(media="not_sent", media_reason="сервер отказал 400"))
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    w.door.media_out = "sent"
    got = w.core.press(did, 1, X.ACT_PDF, "Пым", T0 + 300)
    assert got["ok"] and got["words"] == "текст: ушёл · PDF: ушёл" and len(w.door.media) == 2, got
    assert len(w.find.calls) == 2, w.find.calls


# ── граница ───────────────────────────────────────────────────────────────────────────────

def test_no_pdf_draft_no_recheck():
    """Черновик без PDF: перечитывания нет, текст уходит как раньше (граница — на базе зелёная по построению)."""
    no = {"state": "done", "results": [res("contract", "empty", reason="подписанного нет")]}
    w = World(no)
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["ok"] and len(w.door.sends) == 1 and w.door.media == [] and w.find.calls == [], out


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
