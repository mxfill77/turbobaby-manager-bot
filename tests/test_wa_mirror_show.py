#!/usr/bin/env python3
"""Ушедшее агентом по «Отправить» — в теме клиента ровно одной строкой, без relay; реакция клиента на наше
API-сообщение цитирует наш текст, а не квитанцию (WAMIRROR0410, 04.10.2026).

Всё на подделках: Bot API, дверь, модель, contract_pdf; временные очередь, база показа, база агента, база
зеркала. Сети нет, модель, мост, Telegram, WhatsApp и 360dialog не зовутся. Временные файлы тест НЕ удаляет.

Случаи: отправлено · повтор и рестарт · неизвестно · отказ · Telegram недоступен · relay включён — без дубля ·
паузы нет и строка не уходит клиенту · реакция на наше и на сообщение с телефона · текст и PDF — по строке.
Мутанты: каждый замок ломается копией модуля (WA_AGENT_SRC=<каталог> ставит копии впереди дерева) — набор
обязан упасть; итог — число упавших случаев на мутант."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import test_wa_agent_svc as SV  # noqa: E402  (кладёт ROOT и WA_AGENT_SRC в путь)

import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import wa_tg_mirror as M  # noqa: E402
import wa_webhook as W  # noqa: E402

NUM, SHOW, T0, HUMAN = SV.NUM, SV.SHOW, SV.T0, SV.HUMAN
ON = dict(SV.ALL_ON)                        # карточки, черновики, реакции, дверь; relay ВЫКЛ
RELAY = dict(SV.ALL_ON, WA_AGENT_RELAY="1")
BOT = {"id": 9, "is_bot": True, "first_name": "wa-bot"}


class FailHttp(SV.FakeHttp):
    """Поддельный Bot API, у которого sendMessage в форум показа падает по списку: None — сети нет, код — отказ."""

    def __call__(self, method, url, headers=None, data=None, timeout=30):
        name = url.rsplit("/", 1)[-1]
        params = json.loads(data.decode("utf-8")) if data else {}
        if name == "sendMessage" and str(params.get("chat_id")) == SHOW and self.show_fail:
            code = self.show_fail.pop(0)
            self.calls.append(("sendMessage!", params))
            return code, (b"" if code is None else json.dumps({"ok": False, "description": "boom"}).encode())
        return SV.FakeHttp.__call__(self, method, url, headers, data, timeout)


class RW(SV.World):
    """World службы + исход двери; sendMessage в форум показа можно уронить (None — сети нет, код — отказ)."""

    def __init__(self, environ, res=None, show_fail=(), **kw):
        self.res = res
        super().__init__(environ, **kw)
        self.http.__class__ = FailHttp                                   # руки держат тот же объект
        self.http.show_fail = list(show_fail)

    def send(self, to, text, db_path=None):
        self.sends.append((to, text))
        if self.res:
            return dict(self.res)
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.OUT%d" % len(self.sends)}

    def lines_in_topic(self):
        return [p for p in self.http.of("sendMessage") if str(p.get("chat_id")) == SHOW]

    def paused(self):
        row = self.core.db.execute("SELECT paused FROM clients WHERE number=?", (NUM,)).fetchone()
        return bool(row and row[0])

    def go(self):
        """Черновик → «Отправить» нажато → служба отработала."""
        self.core.tick(T0 - 1000)
        self.put(T0 - 200)
        self.http.updates = [[], [], [self.press("wa:send:1:1")]]
        self.serve(60)

    def show(self):
        return self.core.db.execute("SELECT skey, part, outcome, state, msg_id, tries, lost FROM agent_show "
                                    "ORDER BY draft_id, part DESC").fetchall()


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# ═══ агент: строка показа ════════════════════════════════════════════════════════════════

@case
def c_sent_one_line_without_relay():
    w = RW(ON)
    w.go()
    assert w.sends == [(NUM, "черновик модели")], w.sends
    lines = w.lines_in_topic()
    assert len(lines) == 1, lines
    t = lines[0]["text"]
    assert lines[0]["message_thread_id"] == 42, lines
    head, body = t.split("\n", 1)
    for want in (" · агент · ", "подтвердил Дарья", "черновик №1, версия 1", "· текст"):
        assert want in head, (want, t)
    assert head[:5].count(":") == 1 and body == "черновик модели", t
    assert A.W_SHOW_UNSURE not in t, t
    rows = w.show()
    assert len(rows) == 1 and rows[0][:4] == ("wamid.OUT1|text", "text", "sent", "shown"), rows
    assert isinstance(rows[0][4], int) and rows[0][5:] == (1, 0), rows


@case
def c_repeat_and_restart_no_second_line():
    w = RW(ON)
    w.go()
    w.serve(400)
    assert w.core.show_agent(w.clock.t + 10 ** 6) == 0
    w.build(ON)                                                           # рестарт службы
    w.serve(400)
    w.core.tick(w.clock.t + 10 ** 6)
    assert len(w.lines_in_topic()) == 1, w.lines_in_topic()
    assert [r[3] for r in w.show()] == ["shown"], w.show()


@case
def c_unknown_line_check_phone():
    w = RW(ON, res={"outcome": "unknown", "reason": "транспорт молчит", "wamid": None})
    w.go()
    lines = w.lines_in_topic()
    assert len(lines) == 1, lines
    assert A.W_SHOW_UNSURE in lines[0]["text"] and lines[0]["text"].endswith("\nчерновик модели"), lines
    assert w.show()[0][0] == "?1|text|1" and w.show()[0][2] == "unsure", w.show()
    w.serve(400)
    assert len(w.lines_in_topic()) == 1, "неизвестно показано дважды"


@case
def c_refused_no_line():
    w = RW(ON, res={"outcome": "not_sent", "reason": "окно закрыто", "wamid": None, "window": "closed"})
    w.go()
    assert w.lines_in_topic() == [] and w.show() == [], (w.lines_in_topic(), w.show())


@case
def c_restart_mid_send_unknown_line():
    w = RW(ON)
    w.core.tick(T0 - 1000)
    w.put(T0 - 200)
    w.serve(200)                                                          # черновик и карточка
    w.core.db.execute("UPDATE drafts SET state=?, decided_by=?, decided_at=? WHERE id=1",
                      (A.SENDING, SV.HUMAN["first_name"] + " (id 501)", w.clock.t))
    w.build(ON)                                                           # рестарт посреди двери
    w.serve(20)
    lines = w.lines_in_topic()
    assert len(lines) == 1 and A.W_SHOW_UNSURE in lines[0]["text"], lines
    assert w.sends == [], w.sends                                         # отправки не было и повтора нет


@case
def c_telegram_down_retry_same_key():
    w = RW(ON, show_fail=[None, 500])
    w.go()
    w.serve(30)
    assert len(w.http.of("sendMessage!")) == 2, "строку не пытались положить дважды при недоступном Telegram"
    lines = w.lines_in_topic()
    assert len(lines) == 1 and lines[0]["text"].endswith("\nчерновик модели"), lines
    row = w.show()[0]
    assert row[0] == "wamid.OUT1|text" and row[3] == "shown" and row[5] == 3 and row[6] == 1, row
    assert len(w.sends) == 1, w.sends                                    # клиенту — одна отправка


@case
def c_no_topic_retry_then_line():
    w = RW(ON)
    import sqlite3
    m = sqlite3.connect(w.env["mirror_db"])
    m.execute("DELETE FROM topics")
    m.commit()
    w.go()
    assert w.lines_in_topic() == [] and w.show()[0][3] == "wait", w.show()
    m.execute("INSERT INTO topics VALUES(?,?,?,?,?,?)", (NUM, 42, 1, "live", T0, "Анна"))
    m.commit()
    m.close()
    w.serve(400)
    assert len(w.lines_in_topic()) == 1 and w.show()[0][3] == "shown", w.show()


@case
def c_relay_on_no_duplicate():
    w = RW(RELAY)
    w.go()
    assert len(w.lines_in_topic()) == 1, w.lines_in_topic()


@case
def c_line_no_pause_not_relayed():
    for env in (ON, RELAY):
        w = RW(env)
        w.go()
        line = w.lines_in_topic()[0]
        assert not w.paused(), "строка показа поставила паузу"
        upd = w.upd(message={"message_id": w.http.mid, "chat": {"id": int(SHOW)}, "from": BOT, "date": T0,
                             "text": line["text"], "message_thread_id": 42, "is_topic_message": True})
        w.http.updates = [[upd]]
        w.serve(20)
        assert w.sends == [(NUM, "черновик модели")], w.sends               # строка клиенту не ушла
        assert not w.paused(), "строка показа поставила паузу"
        n = w.core.db.execute("SELECT COUNT(*) FROM relay").fetchone()[0]
        assert n == 0, "строка показа посчитана текстом из темы"
        assert len(w.lines_in_topic()) == 1, w.lines_in_topic()


@case
def c_old_sends_not_shown():
    w = RW(ON)
    w.core.db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at, decided_by, decided_at, "
                      "wamid, closed_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (NUM, A.SENT, 1, "старое", 1, T0 - 9000, "Даня", T0 - 9000, "wamid.OLD", T0 - 9000))
    w.serve(20)
    assert w.lines_in_topic() == [] and w.show() == [], "ушедшее до правки показано задним числом"


# ═══ PDF второй частью (WAPARTSEND0410) ═══════════════════════════════════════════════════

PDF = b"%PDF-1.4 signed contract bytes"
SHA = hashlib.sha256(PDF).hexdigest()


class TG(A.Telegram):
    def __init__(self, fail=0):
        self.lines, self.fail, self.show_chat = [], fail, SHOW

    def card(self, draft_id, ver, number, text):
        return 1000 + draft_id

    def card_done(self, draft_id, card_id, words):
        return True

    def ask_pause(self, number, pause_no, via=None):
        return None

    def agent_line(self, number, line):
        self.lines.append(line)
        return 5000 + len(self.lines)


class PdfWorld:
    def __init__(self, media="sent"):
        import test_wa_agent_attach as AT
        self.AT = AT
        d = tempfile.mkdtemp(prefix="wa_mirror_show_pdf_")
        self.qpath, self.dbpath = os.path.join(d, "q.db"), os.path.join(d, "agent.db")
        import sqlite3
        q = sqlite3.connect(self.qpath)
        q.execute(AT.QSCHEMA)
        q.commit()
        q.close()
        self.tg, self.door = TG(), AT.FakeDoor(media=media)
        self.core = X.AttachCore(self.dbpath, self.qpath, AT.FakeModel(AT.tools_ok()), self.tg, self.door,
                                 clock=lambda: T0 - 5000, attach=True, pdf_fetch=AT.Fetch(),
                                 contract_find=AT.Find())          # реестр при нажатии — тот же договор (T4B3)
        self.core.tick(T0 - 1000)
        q = sqlite3.connect(self.qpath)
        q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
                  "VALUES(?,?,?,?,?,?,0,?)", (T0, NUM, "text", "x", T0, 0, None))
        q.commit()
        q.close()
        self.did = self.core.tick(T0 + 100)[0]


@case
def c_text_and_pdf_line_each():
    p = PdfWorld()
    out = p.core.press(p.did, 1, A.ACT_SEND, "Даня (id 7)", T0 + 200)
    assert out["parts"] == {"text": A.SENT, "pdf": A.SENT}, out
    assert len(p.tg.lines) == 2, p.tg.lines
    assert "· текст:" in p.tg.lines[0] and "· PDF:" in p.tg.lines[1], p.tg.lines
    assert p.tg.lines[1].endswith("\n📄 contract_41.pdf") and "подтвердил Даня" in p.tg.lines[1], p.tg.lines
    keys = sorted(r[0] for r in p.core.db.execute("SELECT skey FROM agent_show"))
    assert keys == ["wamid.P1|pdf", "wamid.T1|text"], keys
    p.core.tick(T0 + 900)
    assert len(p.tg.lines) == 2, "повтор такта дал вторую строку"


@case
def c_pdf_unknown_line():
    p = PdfWorld(media="unknown")
    p.core.press(p.did, 1, A.ACT_SEND, "Даня (id 7)", T0 + 200)
    assert len(p.tg.lines) == 2, p.tg.lines
    assert A.W_SHOW_UNSURE not in p.tg.lines[0] and A.W_SHOW_UNSURE in p.tg.lines[1], p.tg.lines


# ═══ зеркало: реакция клиента на наше API-сообщение ═══════════════════════════════════════

NOW0 = int(time.time())
CL, OUR = "66800000011", "66900000000"


class MHttp:
    def __init__(self):
        self.tg, self.script = [], {}

    def __call__(self, method, url, headers, data, timeout):
        assert url.startswith(M.TG_BASE + "/"), "чужой хост"
        meth = url.rsplit("/", 1)[1]
        params = json.loads(data.decode("utf-8")) if not headers.get("Content-Type", "").startswith(
            "multipart") else {"multipart": True}
        self.tg.append((meth, params))
        result = {"getMe": {"id": 77, "is_bot": True}, "getChat": {"id": -1001, "is_forum": True},
                  "getChatMember": {"status": "administrator", "can_manage_topics": True}}.get(meth)
        if meth == "createForumTopic":
            result = {"message_thread_id": 701, "name": params["name"]}
        if result is None:
            result = True if meth in ("setMessageReaction", "editForumTopic") else {"message_id": 1000 + len(self.tg)}
        return 200, json.dumps({"ok": True, "result": result}).encode()

    def calls(self, meth, since=0):
        return [p for m, p in self.tg[since:] if m == meth]


def mworld(agent=None):
    """Зеркало на временной очереди схемой wa_webhook; agent — {wamid: (msg_id строки показа | None, текст)}."""
    d = tempfile.mkdtemp(prefix="wa_mirror_show_m_")
    q = W.WAQueueDB(os.path.join(d, "wa_queue.db"))
    env = {"queue_db": q.db_path, "state_db": os.path.join(d, "wa_tg_mirror.db"),
           "media_dir": os.path.join(d, "wa_media"), "d360_key": "k" * 26, "tg_token": "123:fake",
           "tg_chat": "-1001", "show": True, "archive_db": os.path.join(d, "no", "a.db"),
           "archive_media": os.path.join(d, "no", "m"), "archive_manifest": os.path.join(d, "no", "m.jsonl"),
           "agent_db": os.path.join(d, "wa_agent.db")}
    if agent is not None:
        core = A.Core(env["agent_db"], q.db_path, None, A.Telegram(), A.Door(), clock=lambda: NOW0 - 100)
        for wamid, (mid, text) in agent.items():
            core._sent_out(wamid, CL, text, A.VIA_AGENT, NOW0 - 50)
            if mid is not None:
                core.db.execute("INSERT INTO agent_show(skey, wamid, part, draft_id, ver, number, outcome, at, state, "
                                "msg_id, chat_id, shown_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                                (wamid + "|text", wamid, "text", 1, 1, CL, "sent", NOW0 - 50, "shown", mid, -1001,
                                 NOW0 - 49))
        core.db.close()
    clk = SV.Clock(NOW0 + 5)
    http = MHttp()
    m = M.Mirror(env, http=http, clock=clk, sleep=clk.sleep, disk_free=lambda p: 10 ** 12)
    m.tick()
    return q, http, m


def payload(msgs, field="messages", name="", statuses=None):
    val = {"messaging_product": "whatsapp", "metadata": {"display_phone_number": OUR}}
    if field == "smb_message_echoes":
        val["message_echoes"] = msgs
    else:
        val["messages"] = msgs
        val["contacts"] = [{"wa_id": CL, "profile": {"name": name}}] if name else []
    if statuses:
        val["statuses"] = statuses
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": field, "value": val}]}]}


def feed(q, p):
    return q.enqueue_stats(W.normalize_wa_payload(p, OUR))


def text_msg(wid, body, sender=CL, ts=None):
    return {"from": sender, "id": wid, "timestamp": str(ts or NOW0), "type": "text", "text": {"body": body}}


def react_msg(wid, target, emoji, sender=CL, to=None):
    m = {"from": sender, "id": wid, "timestamp": str(NOW0 + 1), "type": "reaction",
         "reaction": {"message_id": target, "emoji": emoji}}
    if to:
        m["to"] = to
    return m


def receipt(wamid):
    return {"id": wamid, "status": "sent", "timestamp": str(NOW0), "recipient_id": CL}


def mtopic(agent=None):
    q, http, m = mworld(agent)
    feed(q, payload([text_msg("wamid.C1", "привет")], name="Анна"))
    m.tick()
    feed(q, payload([], statuses=[receipt("wamid.OUT1")]))
    m.tick()
    return q, http, m


@case
def c_reaction_on_show_line():
    q, http, m = mtopic({"wamid.OUT1": (4242, "Байк готов, привезём к 10")})
    k = len(http.tg)
    feed(q, payload([react_msg("wamid.R1", "wamid.OUT1", "👍")]))
    m.tick()
    sr = http.calls("setMessageReaction", k)
    assert len(sr) == 1 and sr[0]["message_id"] == 4242, sr
    assert not http.calls("sendMessage", k), http.calls("sendMessage", k)


@case
def c_reaction_quotes_our_text_not_receipt():
    q, http, m = mtopic({"wamid.OUT1": (None, "Байк готов, привезём к 10")})
    k = len(http.tg)
    feed(q, payload([react_msg("wamid.R1", "wamid.OUT1", "👍")]))
    m.tick()
    sm = [p["text"] for p in http.calls("sendMessage", k)]
    assert len(sm) == 1 and "реакция 👍 на «Байк готов, привезём к 10»" in sm[0], sm
    assert "«sent»" not in sm[0], sm


@case
def c_reaction_our_unknown_text():
    q, http, m = mtopic(None)                                             # базы агента нет — только квитанция
    k = len(http.tg)
    feed(q, payload([react_msg("wamid.R1", "wamid.OUT1", "👍")]))
    m.tick()
    sm = [p["text"] for p in http.calls("sendMessage", k)]
    assert len(sm) == 1 and sm[0].endswith("реакция 👍 на наше сообщение"), sm
    assert "sent" not in sm[0], sm


@case
def c_reaction_on_phone_message_unchanged():
    q, http, m = mtopic({"wamid.OUT1": (4242, "x")})
    feed(q, payload([text_msg("wamid.E1", "с телефона", sender=OUR) | {"to": CL}], field="smb_message_echoes"))
    m.tick()
    k = len(http.tg)
    feed(q, payload([react_msg("wamid.R2", "wamid.E1", "❤️")]))
    m.tick()
    sr = http.calls("setMessageReaction", k)
    shown = m._target_msg("wamid.E1")
    assert shown is not None and len(sr) == 1 and sr[0]["message_id"] == shown and sr[0]["message_id"] != 4242, sr
    k = len(http.tg)
    feed(q, payload([react_msg("wamid.R3", "wamid.C1", "🦩")]))                # вне набора — строкой, как было
    m.tick()
    sm = [p["text"] for p in http.calls("sendMessage", k)]
    assert len(sm) == 1 and "реакция 🦩 на «привет»" in sm[0], sm


@case
def c_reaction_on_pdf_line():
    q, http, m = mworld(None)
    core =A.Core(m.env["agent_db"], q.db_path, None, A.Telegram(), A.Door(), clock=lambda: NOW0 - 100)
    core._sent_out("wamid.P1", CL, "", A.VIA_AGENT, NOW0 - 50, kind="document")
    core.db.execute("INSERT INTO agent_show(skey, wamid, part, draft_id, ver, number, outcome, at, state, msg_id, "
                    "chat_id, shown_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("wamid.P1|pdf", "wamid.P1", "pdf", 1, 1, CL, "sent", NOW0 - 50, "shown", 4343, -1001, NOW0))
    core.db.close()
    feed(q, payload([text_msg("wamid.C1", "привет")], name="Анна"))
    m.tick()
    k = len(http.tg)
    feed(q, payload([react_msg("wamid.R1", "wamid.P1", "👍")]))
    m.tick()
    sr = http.calls("setMessageReaction", k)
    assert len(sr) == 1 and sr[0]["message_id"] == 4343, sr
    _mid, text, ours = m._agent_target("wamid.P1")
    assert ours and text and "sent" not in text, (text, ours)


# ═══ прогон ═══════════════════════════════════════════════════════════════════════════════

def run_cases(quiet=False):
    failed = []
    for fn in CASES:
        try:
            fn()
            if not quiet:
                print("PASS", fn.__name__)
        except Exception as e:                                           # noqa: BLE001
            failed.append(fn.__name__)
            if not quiet:
                print("FAIL", fn.__name__, type(e).__name__, str(e)[:300])
    return failed


# замок → (файл, было, стало): копия модуля с одной правкой; набор обязан упасть
MUTANTS = [
    ("relay снова решает строку", "wa_agent_tg.py",
     '        if not self.show_chat:\n            self.log("тема: строки показа нет — форум показа не задан")',
     '        if not self.relay:\n            return None\n        if not self.show_chat:\n'
     '            self.log("тема: строки показа нет — форум показа не задан")'),
    ("ключ показа не держит повтор", "wa_agent.py", "INSERT OR IGNORE INTO agent_show", "INSERT OR REPLACE INTO agent_show"),
    ("неизвестно без слов", "wa_agent.py", "        head += \" · \" + W_SHOW_UNSURE\n", "        pass\n"),
    ("неизвестно без строки", "wa_agent.py",
     "\"COALESCE(d.closed_at, d.decided_at, d.created_at) FROM drafts d WHERE d.state IN (?,?) \"",
     "\"COALESCE(d.closed_at, d.decided_at, d.created_at) FROM drafts d WHERE d.state IN (?,?) AND d.state<>'unsure' \""),
    ("отказ даёт строку", "wa_agent.py",
     "\"COALESCE(d.closed_at, d.decided_at, d.created_at) FROM drafts d WHERE d.state IN (?,?) \"",
     "\"COALESCE(d.closed_at, d.decided_at, d.created_at) FROM drafts d WHERE d.state IN (?,?,'not_sent') \""),
    ("Telegram не принял — без повтора", "wa_agent.py", "            if tries >= SHOW_MAX:", "            if True:"),
    ("строка inline, как до правки", "wa_agent.py",
     "            self._sent_out(wamid, number, text, VIA_AGENT, now)\n",
     "            self._sent_out(wamid, number, text, VIA_AGENT, now)\n"
     "            self._tg(\"agent_line\", number, text)\n"),
    ("строка показа уходит клиенту", "wa_agent_tg.py",
     "        if not self._human(msg):\n            self.log(\"тема: сообщение %d — написал не человек",
     "        if False:\n            self.log(\"тема: сообщение %d — написал не человек"),
    ("строка показа ставит паузу", "wa_agent.py", "                shown += 1\n",
     "                shown += 1\n                self._pause(number, None, now, via=\"строка показа\")\n"),
    ("прошлое показывается", "wa_agent.py", "            return float(row[0]) if row else 0.0", "            return 0.0"),
    ("PDF без строки", "wa_agent.py", "name='pdf_parts'\").fetchone():", "name='pdf_parts_x'\").fetchone():"),
    ("квитанция — текст цели", "wa_tg_mirror.py", "        tgt = [x for x in rows if not _is_receipt(x)]",
     "        tgt = rows"),
    ("реакция не на строку показа", "wa_tg_mirror.py", "            mid = a_mid\n", "            mid = None\n"),
    ("текст версии по wamid не читается", "wa_tg_mirror.py",
     "                        text = row[0] or (\"[%s]\" % word if word else None)",
     "                        text = None"),
]


def mutate(i):
    name, fname, old, new = MUTANTS[i]
    src = os.environ.get("WA_AGENT_SRC") or ROOT
    d = tempfile.mkdtemp(prefix="wa_mirror_show_mut%d_" % (i + 1))
    for f in ("wa_agent.py", "wa_agent_tg.py", "wa_tg_mirror.py"):
        shutil.copy(os.path.join(ROOT, f), os.path.join(d, f))
    path = os.path.join(d, fname)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    n = text.count(old)
    if n != 1:
        return d, "правка не легла (%d совпадений)" % n
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace(old, new))
    return d, ""


if __name__ == "__main__":
    if os.environ.get("WA_MIRROR_SHOW_CHILD"):
        print("FAILED " + ",".join(run_cases(quiet=True)))
        sys.exit(0)
    failed = run_cases()
    print("случаи: %d/%d" % (len(CASES) - len(failed), len(CASES)))
    caught = 0
    for i, (name, *_rest) in enumerate(MUTANTS):
        d, bad = mutate(i)
        if bad:
            print("мутант %d «%s»: %s" % (i + 1, name, bad))
            continue
        env = dict(os.environ, WA_AGENT_SRC=d, WA_MIRROR_SHOW_CHILD="1", PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-B", os.path.abspath(__file__)], env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=600)
        got = [x for x in (p.stdout or "").splitlines() if x.startswith("FAILED ")]
        fell = [x for x in got[-1][7:].split(",") if x] if got else ["<нет итога: %s>" % (p.stderr or "")[-200:]]
        caught += bool(fell)
        print("мутант %d «%s»: упало %d из %d — %s" % (i + 1, name, len(fell), len(CASES), ", ".join(fell)))
    print("мутантов %d — поймано %d" % (len(MUTANTS), caught))
    sys.exit(0 if not failed and caught == len(MUTANTS) else 1)
