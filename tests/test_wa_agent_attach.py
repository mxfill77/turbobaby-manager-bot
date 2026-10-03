#!/usr/bin/env python3
"""«Отправить» с подписанным PDF договора двумя частями (WAPARTSEND0410, Т4б-1). Всё на подделках: временная очередь
схемой wa_webhook, своя временная база, модель (с итогом сверки Т4а), Telegram, дверь и contract_pdf — подделки. Сети
нет, модель, мост, Telegram и WhatsApp не зовутся.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import base64
import hashlib
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

QSCHEMA = """CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER NOT NULL,
 channel TEXT NOT NULL DEFAULT 'wa', from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT,
 ts_msg INTEGER, echo INTEGER NOT NULL DEFAULT 0, history INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'new', raw TEXT, wamid TEXT)"""

NUM = "66812345678"
T0 = 1_790_000_000
PDF = b"%PDF-1.4 signed contract bytes"
SHA = hashlib.sha256(PDF).hexdigest()
TEXT = "Здравствуйте, договор ниже"


class Crash(BaseException):
    """Смерть процесса посреди вызова двери: except Exception её не ловит."""


def res(tool, outcome, facts=(), reason=""):
    return {"tool": tool, "outcome": outcome, "source": "", "ref": "", "at": T0, "version": "", "window": "",
            "reason": reason, "facts": list(facts)}


def tools_ok(**over):
    """Итог сверки Т4а: подписанный договор этой аренды и его PDF приняты."""
    r = {
        "rental": res("rental", "fact", [{"kind": "rental", "booking_id": "B7", "bike": "PCX 160 5580"}]),
        "contract": res("contract", "fact", [{"kind": "contract", "row": 41, "doc_id": "D41", "bike": "PCX 160 5580",
                                              "signed_at": "2026-10-01", "pdf_id": "F41"}]),
        "contract_pdf": res("contract_pdf", "fact", [{"kind": "pdf", "id": "F41", "name": "contract_41.pdf",
                                                      "size": len(PDF), "sha256": SHA, "row": 41}]),
    }
    r.update(over)
    return {"state": "done", "results": [v for v in r.values() if v is not None]}


class FakeModel(A.Model):
    def __init__(self, tools=None, text=TEXT):
        self.calls, self.tools, self.text, self.last = 0, tools, text, None

    def draft(self, number, upto_id):
        self.calls += 1
        self.last = {"tools": self.tools} if self.tools is not None else {"info": {}}
        return "%s %d" % (self.text, self.calls)


class FakeTG(A.Telegram):
    def __init__(self):
        self.cards, self.done, self.asks = [], [], []

    def card(self, draft_id, ver, number, text):
        self.cards.append(draft_id)
        return 1000 + draft_id

    def card_done(self, draft_id, card_id, words):
        self.done.append((draft_id, words))

    def ask_pause(self, number, pause_no, via=None):
        self.asks.append((number, pause_no))


class FakeDoor(A.Door):
    def __init__(self, text="sent", media="sent", crash_media=False, media_reason="ok", window=None):
        self.sends, self.media, self.text_out, self.media_out = [], [], text, media
        self.crash_media, self.media_reason, self.window = crash_media, media_reason, window

    def send_text(self, to, text):
        self.sends.append((to, text))
        return {"outcome": self.text_out, "reason": "ok", "window": self.window,
                "wamid": "wamid.T%d" % len(self.sends) if self.text_out == "sent" else None}

    def send_media(self, to, media):
        data, _why = media["fetch"](10 ** 9)
        self.media.append((to, media["kind"], media["mime"], media["filename"], hashlib.sha256(data).hexdigest()))
        if self.crash_media:
            raise Crash()
        return {"outcome": self.media_out, "reason": self.media_reason, "window": self.window,
                "wamid": "wamid.P%d" % len(self.media) if self.media_out == "sent" else None}


class Fetch:
    def __init__(self, data=PDF, ok=True):
        self.calls, self.data, self.ok = [], data, ok

    def __call__(self, file_id):
        self.calls.append(file_id)
        if not self.ok:
            return {"ok": False, "error": "not_in_registry"}
        return {"ok": True, "id": file_id, "verified": True, "size": len(self.data),
                "sha256": hashlib.sha256(self.data).hexdigest(),
                "content_b64": base64.b64encode(self.data).decode()}


class World:
    def __init__(self, tools="ok", door=None, fetch=None, attach=True, cls=X.AttachCore):
        d = tempfile.mkdtemp(prefix="wa_attach_t_")
        self.qpath, self.dbpath = os.path.join(d, "q.db"), os.path.join(d, "agent.db")
        q = sqlite3.connect(self.qpath)
        q.execute(QSCHEMA)
        q.commit()
        q.close()
        self.model = FakeModel(tools_ok() if tools == "ok" else tools)
        self.tg, self.door, self.fetch = FakeTG(), door or FakeDoor(), fetch or Fetch()
        self.attach, self.cls, self.lines = attach, cls, []
        self.core = self.new_core()
        self.core.tick(T0 - 1000)

    def new_core(self):
        if self.cls is A.Core:
            return A.Core(self.dbpath, self.qpath, self.model, self.tg, self.door, log=self.lines.append)
        return self.cls(self.dbpath, self.qpath, self.model, self.tg, self.door, log=self.lines.append,
                        attach=self.attach, pdf_fetch=self.fetch)

    def put(self, ts, kind="in", number=NUM, wamid=None, word="x"):
        echo, msg_type = (1, "text") if kind == "echo" else (0, "text")
        if kind == "status":
            msg_type, echo = "status", 1
        q = sqlite3.connect(self.qpath)
        cur = q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, "
                        "wamid) VALUES(?,?,?,?,?,?,0,?)", (ts, number, msg_type, word, ts, echo, wamid))
        q.commit()
        q.close()
        return cur.lastrowid

    def draft(self):
        self.put(T0)
        made = self.core.tick(T0 + 100)
        assert made, "черновик не родился"
        return made[0]

    def q(self, sql, args=()):
        db = sqlite3.connect(self.dbpath)
        try:
            return db.execute(sql, args).fetchall()
        finally:
            db.close()

    def part(self, did):
        rows = self.q("SELECT state, attempt, wamid, sha256, reason FROM pdf_parts WHERE draft_id=?", (did,))
        return rows[0] if rows else None


# ── 1. сверка → вложение или причина ──────────────────────────────────────────────────────

def test_attach_of_accepted():
    meta, why = X.attach_of(tools_ok())
    assert why == "" and meta["file_id"] == "F41" and meta["sha256"] == SHA and meta["size"] == len(PDF)
    assert meta["row"] == 41 and meta["doc_id"] == "D41" and "content_b64" not in meta


def test_attach_of_refusals_named():
    cases = {
        "не завершена": {"state": "over", "results": []},
        "не принят сверкой: ambiguous": tools_ok(contract=res("contract", "ambiguous", reason="подписанных несколько")),
        "не принят сверкой: empty": tools_ok(contract=res("contract", "empty", reason="подписанного нет")),
        "аренда не подтверждена": tools_ok(rental=res("rental", "empty", reason="не найдена")),
        "расходится": tools_ok(rental=res("rental", "fact", [{"kind": "rental", "bike": "NMAX 5960"}])),
        "contract_pdf не звали": tools_ok(contract_pdf=None),
        "PDF не принят сверкой: refused": tools_ok(contract_pdf=res("contract_pdf", "refused", reason="not_signed")),
        "не этого договора": tools_ok(contract_pdf=res("contract_pdf", "fact", [{"id": "F99", "size": 5,
                                                                                 "sha256": SHA}])),
        "сверки не было": None,
    }
    for want, out in cases.items():
        meta, why = X.attach_of(out)
        assert meta is None and want in why, (want, why)


def test_draft_stores_metadata_or_reason():
    w = World()
    did = w.draft()
    row = w.q("SELECT file_id, name, size, sha256, row, reason FROM attach WHERE draft_id=?", (did,))[0]
    assert row == ("F41", "contract_41.pdf", len(PDF), SHA, 41, None), row
    w2 = World(tools=tools_ok(rental=res("rental", "ambiguous", reason="аренд 2")))
    d2 = w2.draft()
    row2 = w2.q("SELECT file_id, reason FROM attach WHERE draft_id=?", (d2,))[0]
    assert row2[0] is None and "аренда не подтверждена" in row2[1], row2


# ── 2. «Отправить» — две части ────────────────────────────────────────────────────────────

def test_both_parts_sent():
    w = World()
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["ok"] and out["words"] == "текст: ушёл · PDF: ушёл", out
    assert out["parts"] == {"text": A.SENT, "pdf": A.SENT}
    assert len(w.door.sends) == 1 and w.door.media == [(NUM, "document", "application/pdf", "contract_41.pdf", SHA)]
    assert w.fetch.calls == ["F41"], "байты берутся из contract_pdf при отправке"
    assert w.part(did)[:3] == (A.SENT, 1, "wamid.P1")
    # эхо нашего PDF не ставит паузу (wamid в outbox)
    w.put(T0 + 210, "echo", wamid="wamid.P1")
    w.core.tick(T0 + 220)
    assert w.q("SELECT paused FROM clients WHERE number=?", (NUM,))[0][0] == 0
    assert w.tg.done[-1][1].startswith("текст: ушёл · PDF: ушёл — Даня")


def test_pdf_after_text_order():
    order = []

    class D(FakeDoor):
        def send_text(self, to, text):
            order.append("text")
            return FakeDoor.send_text(self, to, text)

        def send_media(self, to, media):
            order.append("pdf")
            return FakeDoor.send_media(self, to, media)

    w = World(door=D())
    w.core.press(w.draft(), 1, A.ACT_SEND, "Даня", T0 + 200)
    assert order == ["text", "pdf"], order


def test_pdf_sending_before_door():
    seen = []

    class D(FakeDoor):
        def send_media(self, to, media):
            seen.append(w.part(1)[0])
            return FakeDoor.send_media(self, to, media)

    w = World(door=D())
    w.core.press(w.draft(), 1, A.ACT_SEND, "Даня", T0 + 200)
    assert seen == [A.SENDING], seen


def test_text_not_sent_pdf_door_not_called():
    w = World(door=FakeDoor(text="not_sent"))
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert w.door.media == [] and w.fetch.calls == []
    assert w.part(did)[0] == A.NOT_SENT and out["words"].startswith("текст: не ушёл · PDF: не ушёл: текст не ушёл")
    nope = w.core.press(did, 1, X.ACT_PDF, "Даня", T0 + 300)
    assert not nope["ok"] and "дослать нельзя" in nope["words"] and w.door.media == []


def test_text_unsure_pdf_not_sent():
    w = World(door=FakeDoor(text="unknown"))
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert w.door.media == [] and out["words"].startswith("текст: неизвестно · PDF: не ушёл: текст: неизвестно")


def test_pdf_refused_then_resend():
    door = FakeDoor(media="not_sent", media_reason="сервер отказал 400")
    w = World(door=door)
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["words"].startswith("текст: ушёл · PDF: не ушёл: не отправлено: ошибка двери — сервер отказал 400")
    door.media_out = "sent"
    again = w.core.press(did, 1, X.ACT_PDF, "Пым", T0 + 300)
    assert again["ok"] and again["words"] == "текст: ушёл · PDF: ушёл" and len(door.sends) == 1
    assert w.part(did)[:2] == (A.SENT, 2)


def test_sha_mismatch_not_sent():
    w = World(fetch=Fetch(data=b"%PDF-1.4 other bytes"))
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert w.door.media == [] and w.part(did)[0] == A.NOT_SENT
    assert "sha256" in out["words"] and "не равен sha256 сверки" in out["words"], out


def test_fetch_refused_not_sent():
    w = World(fetch=Fetch(ok=False))
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert w.door.media == [] and "not_in_registry" in out["words"]


def test_window_closed():
    w = World(door=FakeDoor(text="not_sent", window="closed"))
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert w.door.media == []
    w2 = World(door=FakeDoor(media="not_sent", window="closed", media_reason="окно закрыто"))
    d2 = w2.draft()
    out = w2.core.press(d2, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["words"].endswith("PDF: не ушёл: " + A.W_CLOSED), out["words"]


# ── 3. «неизвестно» и «Дослать PDF» ───────────────────────────────────────────────────────

def test_unsure_with_delivery_status():
    door = FakeDoor(media="unknown")
    w = World(door=door)
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["words"] == "текст: ушёл · PDF: неизвестно"
    w.put(T0 + 205, "status", wamid="wamid.T1", word="delivered")       # статус ТЕКСТА — не наша часть
    w.put(T0 + 206, "status", wamid="wamid.X9", word="delivered")       # неизвестный wamid после попытки
    got = w.core.press(did, 1, X.ACT_PDF, "Пым", T0 + 300)
    assert got["state"] == A.SENT and "дослать нельзя" in got["words"] and len(door.media) == 1, got
    assert w.part(did)[:3] == (A.SENT, 1, "wamid.X9")


def test_unsure_without_status_needs_permit():
    door = FakeDoor(media="unknown")
    w = World(door=door)
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    w.put(T0 + 205, "status", wamid="wamid.T1", word="delivered")       # только текст
    got = w.core.press(did, 1, X.ACT_PDF, "Пым", T0 + 300)
    assert got.get("need_permit") and "дубл" in got["words"] and len(door.media) == 1, got
    door.media_out = "sent"
    ok = w.core.press(did, 1, X.ACT_PDF_RISK, "Пым", T0 + 310)
    assert ok["ok"] and len(door.media) == 2 and w.part(did)[:2] == (A.SENT, 2)
    assert w.q("SELECT permit FROM pdf_parts WHERE draft_id=?", (did,))[0][0] == 1


def test_status_unreadable_no_resend():
    door = FakeDoor(media="unknown")
    w = World(door=door)
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    w.core.queue_path = os.path.join(os.path.dirname(w.qpath), "нет.db")
    got = w.core.press(did, 1, X.ACT_PDF_RISK, "Пым", T0 + 300)
    assert not got["ok"] and "не прочитаны" in got["words"] and len(door.media) == 1, got


def test_second_press_already_decided():
    door = FakeDoor(media="not_sent")
    w = World(door=door)
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    again = w.core.press(did, 1, A.ACT_SEND, "Пым", T0 + 201)
    assert not again["ok"] and again["words"].startswith("уже решено")
    door.media_out = "sent"
    first = w.core.press(did, 1, X.ACT_PDF, "Пым", T0 + 300)
    second = w.core.press(did, 1, X.ACT_PDF, "Даня", T0 + 301)
    assert first["ok"] and not second["ok"] and second["words"].startswith("уже решено"), second
    assert len(door.media) == 2


def test_stale_attempt_button_already_decided():
    door = FakeDoor(media="not_sent")
    w = World(door=door)
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    w.core.press(did, 1, X.ACT_PDF, "Пым", T0 + 300)              # повтор тоже не ушёл — попытка 2
    assert w.part(did)[:2] == (A.NOT_SENT, 2) and len(door.media) == 2
    old = w.core.press(did, 1, X.ACT_PDF, "Даня", T0 + 301)       # кнопка прежней попытки
    assert not old["ok"] and old["words"].startswith("уже решено") and len(door.media) == 2, old


def test_restart_mid_pdf_unknown():
    w = World(door=FakeDoor(crash_media=True))
    did = w.draft()
    try:
        w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    except Crash:
        pass
    assert w.part(did)[0] == A.SENDING
    w.door = FakeDoor()
    core2 = w.new_core()
    assert w.part(did)[0] == A.UNSURE and "рестарт посреди отправки PDF" in w.part(did)[4]
    core2.tick(T0 + 400)
    assert w.door.media == [] and w.door.sends == [], "рестарт не повторяет ни одну часть"
    assert core2.parts(did)["words"] == "текст: ушёл · PDF: неизвестно"


def test_restart_mid_text_pdf_not_called():
    class D(FakeDoor):
        def send_text(self, to, text):
            raise Crash()

    w = World(door=D())
    did = w.draft()
    try:
        w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    except Crash:
        pass
    w.door = FakeDoor()
    w.new_core()
    assert w.q("SELECT state FROM drafts WHERE id=?", (did,))[0][0] == A.UNSURE
    assert w.part(did)[0] == A.NOT_SENT and w.part(did)[4] == X.W_TEXT_UNSURE
    assert w.door.media == []


def test_new_inbound_at_press():
    w = World()
    did = w.draft()
    w.put(T0 + 150)
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["state"] == A.STALE and w.door.sends == [] and w.door.media == []


# ── 4. «Пересобрать со сверкой», замок «без сверки» ──────────────────────────────────────

def test_no_check_stale():
    w = World(tools=None)
    did = w.draft()
    assert w.q("SELECT COUNT(*) FROM attach")[0][0] == 0
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["state"] == A.STALE and w.door.sends == [] and "без сверки" in out["words"]


def test_rebuild_new_draft():
    w = World()
    did = w.draft()
    out = w.core.press(did, 1, X.ACT_REBUILD, "Даня", T0 + 200)
    assert out["ok"] and out["state"] == A.SUPERSEDED and out["new"] and out["new"] != did, out
    assert w.q("SELECT state FROM drafts WHERE id=?", (did,))[0][0] == A.SUPERSEDED
    assert w.q("SELECT file_id FROM attach WHERE draft_id=?", (out["new"],))[0][0] == "F41"
    again = w.core.press(did, 1, X.ACT_REBUILD, "Пым", T0 + 201)
    assert not again["ok"] and again["words"].startswith("уже решено")
    assert w.model.calls == 2


def test_text_only_when_no_attachment():
    w = World(tools=tools_ok(contract=res("contract", "empty", reason="подписанного нет")))
    did = w.draft()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    assert out["ok"] and out["words"] == A.SENT and w.door.media == [] and w.part(did) is None


# ── 5. журнал ────────────────────────────────────────────────────────────────────────────

def test_journal_no_text_no_number():
    w = World()
    did = w.draft()
    w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    rows = w.q("SELECT part, attempt, who, outcome, wamid, sha256 FROM part_log WHERE draft_id=? ORDER BY id", (did,))
    assert rows == [("text", 1, "Даня", A.SENT, "wamid.T1", None), ("pdf", 1, "Даня", A.SENT, "wamid.P1", SHA)], rows
    blob = "\n".join(w.lines)
    assert NUM not in blob and NUM[-4:] not in blob and TEXT not in blob and "contract_41" not in blob
    assert "часть pdf, попытка 1, Даня → sent, wamid есть, sha256 %s" % SHA[:12] in blob


# ── 6. флаг выкл — 24ad256 ───────────────────────────────────────────────────────────────

def _scenario(cls, attach):
    w = World(cls=cls, attach=attach)
    did = w.draft()
    r1 = w.core.press(did, 1, A.ACT_SEND, "Даня", T0 + 200)
    w.put(T0 + 300)
    w.core.tick(T0 + 500)
    tables = sorted(r[0] for r in w.q("SELECT name FROM sqlite_master WHERE type='table'"))
    drafts = w.q("SELECT id, number, state, ver, text, upto_id, decided_by, reason, wamid, closed_at FROM drafts")
    return r1, drafts, tables, w.tg.done, w.door.sends, w.door.media, w.lines


def test_flag_off_golden():
    base = _scenario(A.Core, False)
    off = _scenario(X.AttachCore, False)
    assert base == off, "флаг выкл обязан повторять Core 24ad256"
    assert "pdf_parts" not in off[2] and "attach" not in off[2] and off[5] == []


def test_make_core_switch():
    d = tempfile.mkdtemp(prefix="wa_attach_mk_")
    q = os.path.join(d, "q.db")
    con = sqlite3.connect(q)
    con.execute(QSCHEMA)
    con.commit()
    con.close()
    args = (os.path.join(d, "a.db"), q, FakeModel(), FakeTG(), FakeDoor())
    assert type(X.make_core({}, *args)) is A.Core
    assert type(X.make_core({X.F_ATTACH: "0"}, *args)) is A.Core
    on = X.make_core({X.F_ATTACH: "1"}, *args, pdf_fetch=Fetch())
    assert isinstance(on, X.AttachCore) and on.attach


def test_core_untouched():
    """wa_agent.py и wa_agent_tools.py не правятся — подготовка живёт отдельным модулем."""
    import ast
    tree = ast.parse(open(os.path.join(ROOT, "wa_agent_attach.py"), encoding="utf-8").read())
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
             for a in (n.names if isinstance(n, ast.Import) else [ast.alias(n.module or "")])}
    assert names == {"base64", "hashlib", "re", "wa_agent"}, names


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
