#!/usr/bin/env python3
"""PDF клиенту в СЛУЖБЕ (NIGHT0710-B3v, Б3в): `wa_agent_attach.AttachCore` встроен в `wa_agent_svc.build` под выключателем
WA_AGENT_ATTACH. «Отправить» шлёт текст и подписанный PDF двумя частями, у каждой своё подтверждение провайдера (wamid);
PDF — только того же клиента и той же аренды; исход части, outbox и журнал — одной транзакцией; «неизвестно» вслепую не
повторяется; двойное нажатие — одна отправка; рестарт между частями — без дубля и без потери (исход и кнопка «Дослать PDF»
на карточке); поздние delivered/read хранятся по ТОЧНОЙ части; отозванное основание — PDF не уходит; выключено — прежнее.

Всё на подделках: Bot API (`test_wa_agent_svc.FakeHttp`), модель с итогом сверки Т4а и дверями договоров, дверь провайдера
(`send`/`send_media` вместо 360dialog), временные очередь (живая схема: UNIQUE wamid; или `wa_webhook.WAQueueDB`), база
показа и база агента. Сети нет, модель, мост, Telegram и WhatsApp не зовутся. `wa_agent_attach` этот файл НЕ импортирует
наверху: первый случай проверяет, что выключенная служба его не грузит.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import base64
import hashlib
import importlib
import json
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import test_wa_agent_svc as SV  # noqa: E402  (поддельный Bot API, часы, схема очереди)

NUM, CHAT, SHOW, T0, HUMAN = SV.NUM, SV.CHAT, SV.SHOW, SV.T0, SV.HUMAN
OTHER = "66899999999"
PDF = b"%PDF-1.4 signed contract bytes NIGHT0710"
SHA = hashlib.sha256(PDF).hexdigest()
TEXT = "черновик модели"
SIGNED = "2026-10-01 10:15:00"
WINDOW = "2026-10-01…2026-10-07"
ON = {"WA_AGENT_DRAFTS": "1", "WA_AGENT_CARDS": "1", "WA_SEND": "1", "WA_AGENT_TOOLS": "1",
      "WA_AGENT_BOOK_READ": "1", "WA_AGENT_ATTACH": "1"}
BASE = {k: v for k, v in ON.items() if k != "WA_AGENT_ATTACH"}
UNIQUE = "CREATE UNIQUE INDEX idx_wa_wamid ON wa_inbox(wamid)"     # живой формат очереди (wa_webhook.py:148)
REVOKED = {"ok": True, "outcome": "none_signed", "checked": {"unread": [], "undated_signed": 0}}


class Crash(BaseException):
    """Смерть процесса посреди вызова: except Exception её не ловит."""


def X():
    return importlib.import_module("wa_agent_attach")


def res(tool, outcome, facts=(), window=""):
    return {"tool": tool, "outcome": outcome, "source": "", "ref": "", "at": T0 + 50, "version": "",
            "window": window, "reason": "", "facts": list(facts)}


def tools_out():
    """Итог сверки Т4а: подписанный договор ЭТОЙ аренды и его PDF приняты (форма `ModelAdapter.last["tools"]`)."""
    return {"state": "done", "results": [
        res("rental", "fact", [{"kind": "rental", "booking_id": "B7", "bike": "PCX 160 5580",
                                "date_start": "2026-10-01", "date_end": "2026-10-07"}]),
        res("contract", "fact", [{"kind": "contract", "row": 41, "doc_id": "D41", "bike": "PCX 160 5580",
                                  "signed_at": SIGNED, "pdf_id": "F41", "booking_id": "B7"}], window=WINDOW),
        res("contract_pdf", "fact", [{"kind": "pdf", "id": "F41", "name": "contract_41.pdf", "size": len(PDF),
                                      "sha256": SHA, "row": 41}]),
    ]}


class Fetch:
    """Дверь contract_pdf (форма `bridge_client.contract_pdf`: verified ставит клиент)."""
    def __init__(self):
        self.calls, self.row, self.crash = [], None, None

    def __call__(self, file_id):
        self.calls.append(file_id)
        if self.crash:
            raise self.crash
        out = {"ok": True, "id": file_id, "verified": True, "size": len(PDF), "sha256": SHA,
               "content_b64": base64.b64encode(PDF).decode()}
        if self.row is not None:
            out["row"] = self.row
        return out


class Find:
    """Дверь contract_find: по умолчанию — тот же подписанный договор; answer — ответ целиком."""
    def __init__(self):
        self.calls, self.answer = [], None

    def __call__(self, **kw):
        self.calls.append(kw)
        if self.answer is not None:
            return self.answer
        return {"ok": True, "outcome": "one",
                "pick": {"row": 41, "doc_id": "D41", "pdf_id": "F41", "signed_at": SIGNED, "signed": True},
                "checked": {"rows_scanned": 50, "unread": [], "undated_signed": 0, "complete": True}}


class Model(A.Model):
    """Адаптер модели: `.tools` — двери сверки (как `make_model(tools=True)`), `.last` — итог сверки и last_in."""
    def __init__(self, tools=True):
        self.calls, self.last = 0, None
        self.fetch, self.find = Fetch(), Find()
        self.tools = {"cash": lambda **kw: {"ok": False}, "contract": self.find,
                      "contract_pdf": self.fetch} if tools else None

    def draft(self, number, upto_id):
        self.calls += 1
        self.last = ({"tools": tools_out(), "info": {"last_in": T0 - 200}} if self.tools is not None
                     else {"info": {"last_in": T0 - 200}})
        return TEXT


class World:
    def __init__(self, environ, model=True, webhook=False, text="sent", media="sent"):
        d = tempfile.mkdtemp(prefix="wa_attach_svc_t_")
        self.env = {"queue_db": os.path.join(d, "q.db"), "mirror_db": os.path.join(d, "mirror.db"),
                    "agent_db": os.path.join(d, "agent.db"), "tg_token": SV.TOKEN, "show_chat": SHOW,
                    "log_path": os.path.join(d, "wa_agent.log")}
        if webhook:
            import wa_webhook
            wa_webhook.WAQueueDB(self.env["queue_db"], statuses=True)   # очередь живой схемой вебхука (квитанции вкл)
        else:
            q = sqlite3.connect(self.env["queue_db"])
            q.execute(SV.QSCHEMA)
            q.execute(UNIQUE)
            q.commit()
            q.close()
        m = sqlite3.connect(self.env["mirror_db"])
        m.execute("CREATE TABLE topics (number TEXT PRIMARY KEY, thread_id INTEGER, trigger_id INTEGER, "
                  "stage TEXT, ts REAL, name TEXT)")
        m.execute("INSERT INTO topics VALUES(?,?,?,?,?,?)", (NUM, 42, 1, "live", T0, "Анна · +" + NUM))
        m.execute("CREATE TABLE shown (key TEXT PRIMARY KEY, number TEXT, state TEXT, ts REAL, msg_id INTEGER, "
                  "solo INTEGER)")
        m.commit()
        m.close()
        self.clock = SV.Clock(T0)
        self.http = SV.FakeHttp(self.clock)
        self.model = Model() if model else None
        self.sends, self.media, self.lines = [], [], []
        self.text_out, self.media_out = text, media
        self.uid = 1000
        self.build(environ)

    # подделка провайдера (вместо wa_send → 360dialog): три исхода, wamid только при sent
    def send(self, to, text, db_path=None):
        self.sends.append((to, text))
        if self.text_out == "crash":
            raise Crash()
        return {"outcome": self.text_out, "reason": "ok",
                "wamid": "wamid.T%d" % len(self.sends) if self.text_out == "sent" else None}

    def send_media(self, to, media, db_path=None):
        data, _why = media["fetch"](10 ** 9)
        self.media.append((to, media["kind"], media["mime"], media["filename"], hashlib.sha256(data).hexdigest()))
        if self.media_out == "crash":
            raise Crash()
        return {"outcome": self.media_out, "reason": "ok" if self.media_out == "sent" else "сервер отказал 400",
                "wamid": "wamid.P%d" % len(self.media) if self.media_out == "sent" else None}

    def build(self, environ):
        self.environ = dict(environ)
        self.core, self.tg, self.flags, self.words = S.build(
            self.env, environ=self.environ, model=self.model, http=self.http, send=self.send,
            send_media=self.send_media, clock=self.clock, line=self.lines.append)
        return self

    def restart(self, environ=None):
        """Смерть процесса: соединение закрыто (незакоммиченное откатывается — как у умершего процесса), сборка заново."""
        try:
            self.core.db.close()
        except Exception:                                            # noqa: BLE001
            pass
        return self.build(self.environ if environ is None else environ)

    def put(self, ts, number=NUM):
        q = sqlite3.connect(self.env["queue_db"])
        cur = q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
                        "VALUES(?,?,?,?,?,0,0,NULL)", (ts, number, "text", "x", ts))
        q.commit()
        q.close()
        return cur.lastrowid

    def status(self, wamid, word, ts, number=NUM):
        """Квитанция провайдера так, как её кладёт вебхук: INSERT OR IGNORE — на wamid в wa_inbox живёт ПЕРВЫЙ статус."""
        q = sqlite3.connect(self.env["queue_db"])
        q.execute("INSERT OR IGNORE INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, "
                  "wamid) VALUES(?,?,'status',?,?,1,0,?)", (ts, number, word, ts, wamid))
        q.commit()
        q.close()

    def ready(self):
        """Первый старт, вход клиента, черновик №1 и его карточка (сообщение 101)."""
        self.core.tick(T0 - 1000)
        self.put(T0 - 200)
        made = self.core.tick(T0 + 100)
        assert made == [1], made
        return 1

    def press(self, data, card_id=101):
        self.uid += 1
        return self.tg.handle({"update_id": self.uid, "callback_query": {
            "id": "cq%d" % self.uid, "from": HUMAN, "data": data,
            "message": {"message_id": card_id, "chat": {"id": CHAT}}}})

    def answers(self):
        return [p["text"] for p in self.http.of("answerCallbackQuery")]

    def edits(self, mid=101):
        return [p for p in self.http.of("editMessageText") if p.get("message_id") == mid]

    def q(self, sql, args=()):
        db = sqlite3.connect(self.env["agent_db"])
        try:
            return db.execute(sql, args).fetchall()
        finally:
            db.close()

    def part(self, did=1):
        rows = self.q("SELECT state, attempt, wamid, reason FROM pdf_parts WHERE draft_id=?", (did,))
        return rows[0] if rows else None


def kb_data(edit):
    return [b["callback_data"] for row in (edit.get("reply_markup") or {}).get("inline_keyboard", []) for b in row]


# ═══ выключатель: по умолчанию выключено, прежнее ядро ═══════════════════════════════════════════

def test_00_flag_off_core_no_import():
    """Флаг не запрошен (и 0/пусто/no) — прежний wa_agent.Core, модуль PDF не грузится, строки о флаге нет."""
    for env in (BASE, dict(BASE, WA_AGENT_ATTACH="0"), dict(BASE, WA_AGENT_ATTACH=""),
                dict(BASE, WA_AGENT_ATTACH="no")):
        w = World(env)
        assert type(w.core) is A.Core, (env, type(w.core))
        assert not [ln for ln in w.lines if "WA_AGENT_ATTACH" in ln], w.lines
    assert "wa_agent_attach" not in sys.modules, "выключенная служба загрузила wa_agent_attach"


def _scenario(env):
    w = World(env)
    w.ready()
    w.press("wa:send:1:1")
    w.press("wa:send:1:1")
    w.press("wa:pdf:1:1")
    w.core.tick(T0 + 400)
    drafts = w.q("SELECT id, state, ver, text, wamid, decided_by FROM drafts")
    tables = sorted(r[0] for r in w.q("SELECT name FROM sqlite_master WHERE type='table'"))
    return (type(w.core).__name__, w.sends, w.media, w.answers(), w.http.calls, w.lines, drafts, tables, w.words)


def test_flag_off_golden_send_path():
    """Выключено — путь «Отправить» прежний: одна отправка текста, PDF нет, «уже решено», «Дослать» — неизвестная
    кнопка, таблиц PDF нет; одинаково без флага и с 0/пусто/no."""
    base = _scenario(BASE)
    assert base[0] == "Core" and base[1] == [(NUM, TEXT)] and base[2] == [], base[:3]
    assert base[3][0] == "sent" and base[3][1].startswith("уже решено") and base[3][2] == "неизвестная кнопка", base[3]
    assert "pdf_parts" not in base[7] and "attach" not in base[7] and "part_status" not in base[7], base[7]
    for raw in ("0", "", "no", "off"):
        other = _scenario(dict(BASE, WA_AGENT_ATTACH=raw))
        assert other == base, "WA_AGENT_ATTACH=%r — путь разошёлся с выключенным" % raw
    assert S.FLAGS == (S.F_DRAFTS, S.F_CARDS, S.F_REACT, S.F_RELAY, S.F_SEND, S.F_WATCH)
    assert set(base[8]) == set(S.FLAGS), base[8]                  # слова флагов и строка старта — прежние


def test_flag_one_rule_true_equals_one():
    """Одно правило флага: «true»/«yes»/«on» дают то же ядро, что «1»; служба и модуль PDF судят одинаково."""
    x = X()
    one = World(ON)
    assert isinstance(one.core, x.AttachCore) and one.core.attach, type(one.core)
    for raw in ("true", "TRUE", "yes", "on", " 1 "):
        w = World(dict(ON, WA_AGENT_ATTACH=raw))
        assert type(w.core) is type(one.core), (raw, type(w.core))
    for raw in ("1", "true", "yes", "on", "0", "", "no", "off", "2", "да", None):
        assert x.enabled({x.F_ATTACH: raw}) == G.flag_on(raw), raw


def test_flag_without_check_stays_old_core():
    """Флаг 1 без сверки (WA_AGENT_TOOLS выкл) или без черновиков — прежнее ядро и слова; «Отправить» шлёт текст, не stale."""
    w = World(dict(ON, WA_AGENT_TOOLS="0"))
    w.model.tools = None
    w.build(w.environ)
    assert type(w.core) is A.Core, type(w.core)
    said = [ln for ln in w.lines if ln.startswith("PDF клиенту (WA_AGENT_ATTACH)")]
    assert said and "флаг 1, сверки нет" in said[-1] and "прежнее ядро" in said[-1], said
    w.ready()
    w.press("wa:send:1:1")
    assert w.sends == [(NUM, TEXT)] and w.answers()[0] == "sent", (w.sends, w.answers())
    w2 = World(dict(ON, WA_AGENT_DRAFTS="0"))
    assert type(w2.core) is A.Core and any("черновиков нет" in ln for ln in w2.lines), w2.lines


def test_start_line_words():
    """Строка старта словами: вкл — двери от сверки и бюджет; брони выкл — сказано, что PDF не приложится."""
    w = World(ON)
    said = [ln for ln in w.lines if ln.startswith("PDF клиенту (WA_AGENT_ATTACH): вкл")]
    assert said and "брони вкл" in said[0] and "contract_pdf" in said[0], w.lines
    w2 = World(dict(ON, WA_AGENT_BOOK_READ="0"))
    said2 = [ln for ln in w2.lines if ln.startswith("PDF клиенту (WA_AGENT_ATTACH): вкл")]
    assert said2 and "брони ВЫКЛ" in said2[0] and "уйдёт только текст" in said2[0], w2.lines
    assert set(w.words) == set(S.FLAGS) and S.F_ATTACH not in S.FLAGS, w.words   # FLAGS и сводка — прежние


def test_doors_from_check_under_budget():
    """Двери договоров — те же, что у сверки (`model.tools`), и каждый вызов идёт под общим бюджетом плеч моста."""
    seen = []
    import contextlib

    @contextlib.contextmanager
    def budget(sec):
        seen.append(("in", sec))
        yield
        seen.append(("out", sec))
    real = S._press_budget
    S._press_budget = budget
    try:
        w = World(ON)
    finally:
        S._press_budget = real
    did = w.ready()
    w.press("wa:send:%d:1" % did)
    assert w.model.find.calls and w.model.fetch.calls == ["F41"], (w.model.find.calls, w.model.fetch.calls)
    assert seen == [("in", S.PRESS_BRIDGE_SEC), ("out", S.PRESS_BRIDGE_SEC)] * 2, seen


# ═══ две части — у каждой своё подтверждение ═══════════════════════════════════════════════════

def test_send_two_parts_two_wamids():
    """«Отправить» в службе: текст и PDF двумя частями; у текста wamid.T1, у PDF wamid.P1 — каждое в своей части."""
    w = World(ON)
    w.ready()
    w.press("wa:send:1:1")
    assert w.sends == [(NUM, TEXT)], w.sends
    assert w.media == [(NUM, "document", "application/pdf", "contract_41.pdf", SHA)], w.media
    assert w.answers()[-1] == "текст: ушёл · PDF: ушёл", w.answers()
    assert w.q("SELECT state, wamid FROM drafts WHERE id=1") == [(A.SENT, "wamid.T1")]
    assert w.part()[:3] == (A.SENT, 1, "wamid.P1"), w.part()
    out = dict(w.q("SELECT wamid, COALESCE(kind, 'text') FROM outbox"))
    assert out == {"wamid.T1": "text", "wamid.P1": "document"}, out
    log = w.q("SELECT part, attempt, outcome, wamid FROM part_log WHERE draft_id=1 ORDER BY id")
    assert log == [("text", 1, A.SENT, "wamid.T1"), ("pdf", 1, A.SENT, "wamid.P1")], log
    done = w.edits()[-1]
    assert "текст: ушёл · PDF: ушёл" in done["text"] and not kb_data(done), done


def test_pdf_same_client_same_rental():
    """PDF — тому же клиенту (номер черновика) и по той же аренде: реестр перечитан номером и сроком аренды черновика."""
    w = World(ON)
    w.ready()
    w.press("wa:send:1:1")
    assert {m[0] for m in w.media} == {NUM} and w.sends[0][0] == NUM, (w.sends, w.media)
    assert w.model.find.calls == [{"phone": NUM, "date_from": "2026-10-01", "date_to": "2026-10-07"}], w.model.find.calls
    basis = w.q("SELECT number, doc_id, row, signed_at, date_from, date_to FROM attach WHERE draft_id=1")
    assert basis == [(NUM, "D41", 41, SIGNED, "2026-10-01", "2026-10-07")], basis


def test_pdf_other_registry_row_not_sent():
    """Мост при отправке назвал другую строку реестра для того же файла — договор сменился: PDF не уходит."""
    w = World(ON)
    w.model.fetch.row = 99
    w.ready()
    w.press("wa:send:1:1")
    assert len(w.sends) == 1 and w.media == [], w.media
    assert w.part()[0] == A.NOT_SENT and "строка реестра" in w.part()[3], w.part()


def test_registry_other_contract_nothing_sent():
    """Реестр при нажатии отвечает другим договором (doc_id) — ничего не отправлено, черновик stale."""
    w = World(ON)
    w.model.find.answer = {"ok": True, "outcome": "one",
                           "pick": {"row": 77, "doc_id": "D77", "pdf_id": "F77", "signed_at": SIGNED, "signed": True},
                           "checked": {"rows_scanned": 50, "unread": [], "undated_signed": 0, "complete": True}}
    w.ready()
    w.press("wa:send:1:1")
    assert w.sends == [] and w.media == [] and w.model.fetch.calls == [], (w.sends, w.media)
    assert w.q("SELECT state FROM drafts WHERE id=1") == [(A.STALE,)]


# ═══ отозванное основание ══════════════════════════════════════════════════════════════════════

def test_revoked_at_send_nothing_goes():
    """Отозвано до «Отправить» (реестр: none_signed) — не уходит НИ текст, ни PDF."""
    w = World(ON)
    w.model.find.answer = REVOKED
    w.ready()
    w.press("wa:send:1:1")
    assert w.sends == [] and w.media == [] and w.model.fetch.calls == []
    assert "отозван" in w.answers()[-1], w.answers()


def test_revoked_before_resend_pdf_not_sent():
    """PDF не ушёл, затем договор отозван — «Дослать PDF» отказывает, PDF не уходит, попытка не тратится."""
    w = World(ON, media="not_sent")
    w.ready()
    w.press("wa:send:1:1")
    w.media_out = "sent"
    w.model.find.answer = REVOKED
    w.press("wa:pdf:1:1")
    assert len(w.media) == 1 and "отозван" in w.answers()[-1], (w.media, w.answers())
    assert w.part()[:2] == (A.NOT_SENT, 1), w.part()


# ═══ «неизвестно» вслепую не повторяется ═══════════════════════════════════════════════════════

def test_unknown_not_repeated_blindly():
    """PDF «неизвестно»: «Дослать PDF» без разрешения — двери нет (нужна кнопка риска); «— риск дубля» — ровно одна
    попытка; повтор той же кнопки — «уже решено»."""
    w = World(ON, media="unknown")
    w.ready()
    w.press("wa:send:1:1")
    assert w.part()[:3] == (A.UNSURE, 1, None) and len(w.media) == 1, w.part()
    card = w.edits()[-1]
    assert kb_data(card) == ["wa:pdf:1:1", "wa:pdf_risk:1:1"], card
    w.press("wa:pdf:1:1")
    assert len(w.media) == 1 and "риск дубля" in w.answers()[-1], (w.media, w.answers())
    w.media_out = "sent"
    w.press("wa:pdf_risk:1:1")
    assert len(w.media) == 2 and w.part()[:3] == (A.SENT, 2, "wamid.P2"), (w.media, w.part())
    w.press("wa:pdf_risk:1:1")
    assert len(w.media) == 2 and w.answers()[-1].startswith("уже решено"), w.answers()


def test_restart_mid_pdf_unknown_no_repeat():
    """Рестарт посреди двери PDF (часть sending) — «неизвестно»: ни одна часть не повторяется сама; на карточке исход
    и кнопки PDF."""
    w = World(ON, media="crash")
    w.ready()
    try:
        w.press("wa:send:1:1")
    except Crash:
        pass
    w.media_out = "sent"
    w.restart()
    assert w.part()[0] == A.UNSURE, w.part()
    w.core.tick(T0 + 400)
    assert len(w.sends) == 1 and len(w.media) == 1, (w.sends, w.media)
    card = w.edits()[-1]
    assert "PDF: неизвестно" in card["text"] and kb_data(card) == ["wa:pdf:1:1", "wa:pdf_risk:1:1"], card


def test_resend_door_closed_no_bridge():
    """Дверь WA_SEND выключена — «Дослать PDF» отвечает словами ДО моста и захвата; попытка не тратится."""
    w = World(ON, media="not_sent")
    w.ready()
    w.press("wa:send:1:1")
    finds = len(w.model.find.calls)
    w.environ["WA_SEND"] = "0"
    w.press("wa:pdf:1:1")
    assert "отправка выключена" in w.answers()[-1] and len(w.model.find.calls) == finds, w.answers()
    assert w.part()[:2] == (A.NOT_SENT, 1) and len(w.media) == 1, w.part()


# ═══ двойное нажатие — одна отправка ═══════════════════════════════════════════════════════════

def test_double_press_send_one_send():
    """Два колбэка «Отправить» подряд (одна партия getUpdates) — один текст и один PDF; второму — «уже решено»."""
    w = World(ON)
    w.ready()
    w.http.updates = [[{"update_id": 2001, "callback_query": {"id": "a", "from": HUMAN, "data": "wa:send:1:1",
                                                             "message": {"message_id": 101, "chat": {"id": CHAT}}}},
                       {"update_id": 2002, "callback_query": {"id": "b", "from": HUMAN, "data": "wa:send:1:1",
                                                             "message": {"message_id": 101, "chat": {"id": CHAT}}}}]]
    w.tg.poll()
    assert len(w.sends) == 1 and len(w.media) == 1, (w.sends, w.media)
    assert w.answers()[0] == "текст: ушёл · PDF: ушёл" and w.answers()[1].startswith("уже решено"), w.answers()


def test_double_press_resend_one_pdf():
    """Два «Дослать PDF» одной попытки — одна отправка PDF; кнопка прежней попытки — «уже решено»."""
    w = World(ON, media="not_sent")
    w.ready()
    w.press("wa:send:1:1")
    card = w.edits()[-1]
    assert kb_data(card) == ["wa:pdf:1:1"] and "PDF: не ушёл" in card["text"], card
    w.media_out = "sent"
    w.press("wa:pdf:1:1")
    w.press("wa:pdf:1:1")
    assert len(w.media) == 2 and len(w.sends) == 1, (w.media, w.sends)
    assert w.answers()[-2] == "текст: ушёл · PDF: ушёл" and w.answers()[-1].startswith("уже решено"), w.answers()


def test_resend_button_carries_attempt():
    """Кнопка «Дослать PDF» несёт номер ТЕКУЩЕЙ попытки: после второй неудачи — попытка 2, прежняя кнопка — «уже решено»."""
    w = World(ON, media="not_sent")
    w.ready()
    w.press("wa:send:1:1")
    w.press("wa:pdf:1:1")                                     # попытка 2 тоже не ушла
    assert w.part()[:2] == (A.NOT_SENT, 2) and kb_data(w.edits()[-1]) == ["wa:pdf:1:2"], (w.part(), w.edits()[-1])
    w.media_out = "sent"
    w.press("wa:pdf:1:1")
    assert len(w.media) == 2 and w.answers()[-1].startswith("уже решено"), w.answers()
    w.press("wa:pdf:1:2")
    assert len(w.media) == 3 and w.part()[:2] == (A.SENT, 3), (w.media, w.part())


# ═══ рестарт между частями — без дубля и без потери ═════════════════════════════════════════════

def test_restart_between_parts_no_dup_no_loss():
    """Процесс умер после текста, ДО PDF: старт — PDF «не ушёл: рестарт между частями», исход и «Дослать PDF» на
    карточке первым тактом; текст не повторяется; «Дослать» шлёт PDF один раз; повтор — «уже решено»."""
    w = World(ON)
    w.ready()

    def die(*a, **kw):
        raise Crash()
    w.core._send_pdf = die
    try:
        w.press("wa:send:1:1")
    except Crash:
        pass
    assert w.sends == [(NUM, TEXT)] and w.media == []
    w.restart()
    assert w.part()[0] == A.NOT_SENT and "между частями" in w.part()[3], w.part()
    w.core.tick(T0 + 400)
    card = w.edits()[-1]
    assert "текст: ушёл · PDF: не ушёл: рестарт между частями" in card["text"], card["text"]
    assert kb_data(card) == ["wa:pdf:1:1"], card
    assert len(w.sends) == 1 and w.media == [], "рестарт сам ничего не отправил"
    w.press("wa:pdf:1:1")
    assert len(w.media) == 1 and len(w.sends) == 1 and w.part()[:3] == (A.SENT, 2, "wamid.P1"), (w.media, w.part())
    w.press("wa:pdf:1:1")
    assert len(w.media) == 1 and w.answers()[-1].startswith("уже решено"), w.answers()


def test_restart_before_pdf_door_no_loss():
    """Процесс умер на выборке байт PDF (часть claimed, дверь не звана) — «не ушёл», кнопка, одна досылка."""
    w = World(ON)
    w.ready()
    w.model.fetch.crash = Crash()
    try:
        w.press("wa:send:1:1")
    except Crash:
        pass
    w.model.fetch.crash = None
    w.restart()
    assert w.part()[0] == A.NOT_SENT and w.media == [], w.part()
    w.core.tick(T0 + 400)
    assert kb_data(w.edits()[-1]) == ["wa:pdf:1:1"], w.edits()[-1]
    w.press("wa:pdf:1:1")
    assert len(w.media) == 1 and w.part()[0] == A.SENT, (w.media, w.part())


# ═══ атомарность SENT / outbox / журнал ═══════════════════════════════════════════════════════

def test_atomic_pdf_write_all_or_nothing():
    """Смерть между исходом PDF и строкой outbox — не легло НИЧЕГО: после рестарта часть «неизвестно» (sending до двери),
    outbox и журнал без PDF; дверь PDF звана один раз."""
    w = World(ON)
    w.ready()
    real = w.core._sent_out

    def boom(wamid, number, text, via, now, kind=None):
        if kind == "document":
            raise Crash()
        return real(wamid, number, text, via, now, kind=kind)
    w.core._sent_out = boom
    try:
        w.press("wa:send:1:1")
    except Crash:
        pass
    w.restart()
    st = w.part()[0]
    out = w.q("SELECT COUNT(*) FROM outbox WHERE wamid='wamid.P1'")[0][0]
    log = w.q("SELECT COUNT(*) FROM part_log WHERE part='pdf' AND wamid='wamid.P1'")[0][0]
    assert (st, out, log) in ((A.SENT, 1, 1), (A.UNSURE, 0, 0)), (st, out, log)
    assert (st, out, log) == (A.UNSURE, 0, 0), "до двери sending, после — ничего: должно было откатиться"
    w.core.tick(T0 + 400)
    assert len(w.media) == 1 and len(w.sends) == 1


def test_atomic_text_write_all_or_nothing():
    """Смерть между исходом текста и журналом части — исход текста и outbox откатились: «неизвестно», без повтора;
    PDF не звали (файл без текста не уходит)."""
    w = World(ON)
    w.ready()
    real = w.core._plog

    def boom(draft_id, part, *a, **kw):
        if part == "text":
            raise Crash()
        return real(draft_id, part, *a, **kw)
    w.core._plog = boom
    try:
        w.press("wa:send:1:1")
    except Crash:
        pass
    w.restart()
    assert w.q("SELECT state, wamid FROM drafts WHERE id=1") == [(A.UNSURE, None)], w.q("SELECT state FROM drafts")
    assert w.q("SELECT COUNT(*) FROM outbox")[0][0] == 0
    assert w.part()[0] == A.NOT_SENT and w.media == [], w.part()
    w.core.tick(T0 + 400)
    assert len(w.sends) == 1 and w.media == []


def test_atomic_error_rolls_back_in_process():
    """Исключение посреди записи части (процесс жив) — откат, транзакция не остаётся открытой, outbox без PDF."""
    w = World(ON)
    w.ready()
    real = w.core._plog

    def boom(draft_id, part, *a, **kw):
        if part == "pdf":
            raise RuntimeError("диск")
        return real(draft_id, part, *a, **kw)
    w.core._plog = boom
    w.press("wa:send:1:1")                                    # руки ловят исключение обновления
    assert not w.core.db.in_transaction
    assert w.q("SELECT COUNT(*) FROM outbox WHERE wamid='wamid.P1'")[0][0] == 0
    assert w.part()[0] == A.SENDING and len(w.media) == 1, w.part()


def test_pdf_echo_is_ours_by_part():
    """Эхо PDF любой попытки — наше (по `pdf_parts`/`part_log`), даже без строки outbox: паузы нет."""
    w = World(ON)
    w.ready()
    w.press("wa:send:1:1")
    w.core.db.execute("UPDATE pdf_parts SET wamid='wamid.P77' WHERE draft_id=1")
    assert w.core._our_wamid("wamid.P77") and w.core._our_wamid("wamid.P1")
    assert not w.core._our_wamid("wamid.X9")


# ═══ поздние статусы по точной части ═══════════════════════════════════════════════════════════

def test_late_statuses_saved_by_exact_part():
    """Очередь живой схемой вебхука: sent → delivered → read по wamid PDF и delivered по wamid текста ложатся в
    `part_status` по своей части; wa_inbox держит только первый статус (UNIQUE); чужой wamid не сохраняется."""
    import wa_webhook
    w = World(ON, webhook=True)
    w.ready()
    w.press("wa:send:1:1")
    qdb = wa_webhook.WAQueueDB(w.env["queue_db"], statuses=True)
    for i, (wamid, word) in enumerate((("wamid.P1", "sent"), ("wamid.P1", "delivered"), ("wamid.P1", "read"),
                                       ("wamid.T1", "delivered"), ("wamid.X9", "read"))):
        qdb.enqueue([{"type": "status", "from": NUM, "text": word, "wamid": wamid, "ts": T0 + 300 + i,
                      "echo": True}])
    q = sqlite3.connect(w.env["queue_db"])
    first = q.execute("SELECT text FROM wa_inbox WHERE wamid='wamid.P1'").fetchall()
    q.close()
    assert first == [("sent",)], first                           # в очереди — только первое слово
    w.core.tick(T0 + 600)
    got = w.q("SELECT wamid, status, part, draft_id, attempt FROM part_status ORDER BY wamid, status")
    assert got == [("wamid.P1", "delivered", "pdf", 1, 1), ("wamid.P1", "read", "pdf", 1, 1),
                   ("wamid.P1", "sent", "pdf", 1, 1), ("wamid.T1", "delivered", "text", 1, 1)], got
    parts = w.core.parts(1)
    assert parts["delivery"][0] == "delivered" and parts["text_delivery"][0] == "delivered", parts


def test_late_status_other_recipient_not_attributed():
    """Статус нашего wamid, но с чужим получателем — части не приписывается."""
    import wa_webhook
    w = World(ON, webhook=True)
    w.ready()
    w.press("wa:send:1:1")
    wa_webhook.WAQueueDB(w.env["queue_db"], statuses=True).enqueue([{"type": "status", "from": OTHER, "text": "read",
                                                      "wamid": "wamid.P1", "ts": T0 + 300, "echo": True}])
    w.core.tick(T0 + 600)
    assert w.q("SELECT COUNT(*) FROM part_status")[0][0] == 0
    assert w.core.parts(1)["delivery"][0] == "unknown"


def test_old_webhook_queue_only_first_status_honest():
    """Очередь БЕЗ квитанций вебхука (`wa_status` нет, как в проде до его выкатки): delivered после sent не доходит —
    система честно говорит «принято WhatsApp», а не «доставлен»; сохранён ровно sent по точной части."""
    w = World(ON)
    w.ready()
    w.press("wa:send:1:1")
    w.status("wamid.P1", "sent", T0 + 300)
    w.status("wamid.P1", "delivered", T0 + 301)                 # UNIQUE: проглочено, как в живой очереди
    w.core.tick(T0 + 600)
    assert w.q("SELECT status, part FROM part_status") == [("sent", "pdf")]
    assert w.core.parts(1)["delivery"][0] == "accepted"


def test_saved_status_survives_queue_loss():
    """Сохранённый статус части живёт в базе агента: очередь не прочитана — доставка всё равно названа по хранимому."""
    import wa_webhook
    w = World(ON, webhook=True)
    w.ready()
    w.press("wa:send:1:1")
    wa_webhook.WAQueueDB(w.env["queue_db"], statuses=True).enqueue([{"type": "status", "from": NUM, "text": "read",
                                                      "wamid": "wamid.P1", "ts": T0 + 300, "echo": True}])
    w.core.tick(T0 + 600)
    w.core.queue_path = os.path.join(os.path.dirname(w.env["queue_db"]), "нет.db")
    assert w.core.delivery_check(NUM, "wamid.P1")[0] == "delivered"


def test_webhook_status_table_additive():
    """Вебхук: все статусы wamid — в `wa_status`; wa_inbox и счёт вставок прежние (первый статус, остальные — 0)."""
    import wa_webhook
    d = tempfile.mkdtemp(prefix="wa_status_t_")
    qdb = wa_webhook.WAQueueDB(os.path.join(d, "q.db"), statuses=True)
    counts =[qdb.enqueue([{"type": "status", "from": NUM, "text": w_, "wamid": "wamid.Z1", "ts": T0 + i,
                            "echo": True}]) for i, w_ in enumerate(("sent", "delivered", "read", "read"))]
    assert counts == [1, 0, 0, 0], counts
    con = sqlite3.connect(os.path.join(d, "q.db"))
    try:
        inbox = con.execute("SELECT text FROM wa_inbox WHERE wamid='wamid.Z1'").fetchall()
        st = con.execute("SELECT status, recipient FROM wa_status WHERE wamid='wamid.Z1' ORDER BY status").fetchall()
    finally:
        con.close()
    assert inbox == [("sent",)], inbox
    assert st == [("delivered", NUM), ("read", NUM), ("sent", NUM)], st


# ═══ руки Telegram ═════════════════════════════════════════════════════════════════════════════

def test_tg_pdf_buttons_only_with_attach_core():
    """`wa:pdf` у прежнего ядра — «неизвестная кнопка» (как было); имена кнопок = действия ядра PDF."""
    w = World(BASE)
    w.ready()
    w.press("wa:send:1:1")
    w.press("wa:pdf:1:1")
    w.press("wa:pdf_risk:1:1")
    assert w.answers()[-2:] == ["неизвестная кнопка", "неизвестная кнопка"], w.answers()
    assert not [e for e in w.edits() if e.get("reply_markup")], w.edits()


def test_tg_pdf_action_names():
    """Кнопки рук и действия ядра PDF — одни и те же имена (иначе «Дослать» молча стал бы «неизвестной кнопкой»)."""
    x = X()
    assert tuple(G.PDF_ACTIONS) == (x.ACT_PDF, x.ACT_PDF_RISK)


def test_tg_buttons_survive_edit_retry():
    """Правка исхода, которую Telegram не принял, повторяется — кнопка «Дослать PDF» едет и с повтором."""
    w = World(ON, media="not_sent")
    w.ready()
    real = w.http.__class__.__call__
    fails = [1]

    def http(method, url, headers=None, data=None, timeout=30):
        name = url.rsplit("/", 1)[-1]
        if name == "editMessageText" and fails:
            fails.pop()
            w.http.calls.append((name, json.loads(data.decode("utf-8"))))
            return 400, json.dumps({"ok": False, "error_code": 400, "description": "x"}).encode()
        return real(w.http, method, url, headers=headers, data=data, timeout=timeout)
    w.tg.http = http
    w.press("wa:send:1:1")
    w.clock.t += 600
    w.core.tick(w.clock.t)
    edits = w.edits()
    assert len(edits) >= 2 and all(kb_data(e) == ["wa:pdf:1:1"] for e in edits), edits


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
