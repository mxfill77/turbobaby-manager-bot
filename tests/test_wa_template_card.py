#!/usr/bin/env python3
"""NIGHT0710-B3g «Шаблон после 24 часов»: ядро и карточка. Окно закрыто → «✅ Отправить» отвечает словами ДО
захвата (черновик ждёт), карточка предлагает «📨 Отправить шаблоном»; нажатие — одна отправка шаблона (sending ДО
двери, wamid в outbox, черновик ждёт); не одобрен у Meta → отказ словами на карточке; клиент ответил → окно открыто,
новый черновик уходит обычной кнопкой. Выключатель WA_AGENT_TEMPLATES выкл — карточка и нажатия прежние.

Всё на подделках: Bot API (FakeHttp), дверь (TplDoor) либо НАСТОЯЩИЙ `wa_send.send_template` с поддельными швами
GET/POST провайдера. Сети нет: `urllib.request.urlopen` подменён ловушкой.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import inspect
import json
import os
import sqlite3
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])
os.environ["PRETOOL_NOPUSH"] = "1"


def _no_net(*a, **kw):
    raise AssertionError("тест обратился к сети")


urllib.request.urlopen = _no_net                 # ни одного живого запроса — ни к Telegram, ни к провайдеру

import wa_agent as A  # noqa: E402
import wa_agent_knowledge as K  # noqa: E402
import wa_agent_svc as SVC  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import wa_send as S  # noqa: E402

QSCHEMA = """CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER NOT NULL,
 channel TEXT NOT NULL DEFAULT 'wa', from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT,
 ts_msg INTEGER, echo INTEGER NOT NULL DEFAULT 0, history INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'new', raw TEXT, wamid TEXT)"""

NUM = "66812345678"
CHAT = G.AGENTS_CHAT
SHOW = "-1004401325262"
T0 = 1_790_000_000
HUMAN = {"id": 501, "is_bot": False, "first_name": "Дарья"}
RU = "Здравствуйте! Байк свободен, приезжайте."
EN = "Hello! The bike is available, come and pick it up."
TH = "สวัสดีครับ รถว่างครับ"
KEY = "real_key_abcdef0123456789"
_TT = getattr(S, "template_text", None)          # на базе (до правки) шаблонов нет — набор стартует и краснеет по делу
TPL_RU = _TT("reply_request", "ru", ["байка"]) if _TT else None
TPL_EN = _TT("reply_request", "en", ["bike"]) if _TT else None
# Ядро до правки новых аргументов не знает: тогда ядро собирается прежней сигнатурой (проверки «выключено = как
# раньше» на базе зелёные, проверки нового поведения — красные).
KW_OK = "templates" in inspect.signature(A.Core.__init__).parameters


class FakeHttp:
    def __init__(self):
        self.calls, self.updates, self.mid = [], [], 100

    def __call__(self, method, url, headers=None, data=None, timeout=30):
        name = url.rsplit("/", 1)[-1]
        params = json.loads(data.decode("utf-8")) if data else {}
        self.calls.append((name, params))
        if name == "sendMessage":
            self.mid += 1
            return 200, json.dumps({"ok": True, "result": {"message_id": self.mid}}).encode()
        if name == "getUpdates":
            batch = self.updates.pop(0) if self.updates else []
            return 200, json.dumps({"ok": True, "result": batch}).encode()
        return 200, json.dumps({"ok": True, "result": True}).encode()

    def of(self, name):
        return [p for n, p in self.calls if n == name]


class FakeModel(A.Model):
    def __init__(self, text=RU):
        self.text = text

    def draft(self, number, upto_id):
        return self.text


class TplDoor(A.Door):
    """Дверь-подделка: окно — заданное, шаблон — заданный исход; во время вызова шаблона читает tpl_out."""

    def __init__(self):
        self.sends, self.tpls, self.wcalls, self.seen = [], [], 0, []
        self.win = {"state": "closed", "age": 30 * 3600}
        self.tpl_res = {"outcome": "sent", "reason": "принято, id сообщения назван", "wamid": "wamid.TPL1",
                        "approval": "approved", "text": TPL_RU}
        self.db_path = None
        self.open = True

    def is_open(self):
        return self.open

    def window(self, number):
        self.wcalls += 1
        return dict(self.win)

    def send_text(self, to, text):
        self.sends.append((to, text))
        if self.win["state"] == "closed":          # как настоящая дверь: окно закрыто — отказ до сети
            return {"outcome": "not_sent", "reason": "окно закрыто (последнее сообщение клиента 30 ч назад, предел "
                    "24 ч) — шаблоны не шлём", "wamid": None, "window": "closed"}
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.OUT%d" % len(self.sends)}

    def send_template(self, to, name, lang, params):
        if self.db_path:
            db = sqlite3.connect(self.db_path)
            self.seen.append(db.execute("SELECT state FROM tpl_out").fetchall())
            db.close()
        self.tpls.append((to, name, lang, list(params)))
        return dict(self.tpl_res)


class World:
    def __init__(self, templates=True, text=RU, door=None, kw_templates=True, lang_of=K.lang_of):
        d = tempfile.mkdtemp(prefix="wa_tpl_card_t_")
        self.qpath, self.dbpath = os.path.join(d, "q.db"), os.path.join(d, "agent.db")
        self.mpath = os.path.join(d, "mirror.db")
        q = sqlite3.connect(self.qpath)
        q.execute(QSCHEMA)
        q.commit()
        q.close()
        m = sqlite3.connect(self.mpath)
        m.execute("CREATE TABLE topics (number TEXT PRIMARY KEY, thread_id INTEGER, trigger_id INTEGER, "
                  "stage TEXT, ts REAL, name TEXT)")
        m.execute("INSERT INTO topics VALUES(?,?,?,?,?,?)", (NUM, 42, 1, "live", T0, "Анна · +" + NUM))
        m.commit()
        m.close()
        self.http, self.lines, self.uid = FakeHttp(), [], 1000
        self.door = door if door is not None else TplDoor()
        if isinstance(self.door, TplDoor):
            self.door.db_path = self.dbpath
        self.templates, self.kw_templates, self.lang_of = templates, kw_templates, lang_of
        self.model = FakeModel(text)
        self.new_core()
        self.core.tick(T0 - 1000)

    def new_core(self):
        self.tg = G.Tg("123:SECRET", enabled=True, show_chat=SHOW, mirror_db=self.mpath, http=self.http,
                       clock=lambda: T0 + 500, log=self.lines.append)
        kw = {"templates": self.templates, "lang_of": self.lang_of} if (self.kw_templates and KW_OK) else {}
        self.core = A.Core(self.dbpath, self.qpath, self.model, self.tg, self.door,
                           clock=lambda: T0 + 500, log=self.lines.append, **kw)
        self.tg.bind(self.core)

    def put(self, ts, kind="in", wamid=None):
        q = sqlite3.connect(self.qpath)
        cur = q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
                        "VALUES(?,?,?,?,?,?,0,?)", (ts, NUM, "text", "x", ts, 1 if kind == "echo" else 0, wamid))
        q.commit()
        q.close()
        return cur.lastrowid

    def draft(self):
        self.put(T0)
        self.core.tick(T0 + A.QUIET_DEFAULT)
        cards = self.http.of("sendMessage")
        assert len(cards) == 1, cards
        return cards[0]

    def upd(self, **body):
        self.uid += 1
        body["update_id"] = self.uid
        return body

    def press(self, data, card_id=101):
        self.http.updates.append([self.upd(callback_query={
            "id": "cq%d" % (self.uid + 1), "from": HUMAN, "data": data,
            "message": {"message_id": card_id, "chat": {"id": CHAT}}})])
        return self.tg.poll()

    def reply(self, card_id, text):
        self.http.updates.append([self.upd(message={"message_id": 900 + self.uid, "from": HUMAN, "chat": {"id": CHAT},
                                                    "text": text, "reply_to_message": {"message_id": card_id}})])
        return self.tg.poll()

    def answers(self):
        return [p["text"] for p in self.http.of("answerCallbackQuery")]

    def state(self, did=1):
        row = self.core.db.execute("SELECT state, ver FROM drafts WHERE id=?", (did,)).fetchone()
        return row

    def tpl_row(self, did=1):
        try:
            return self.core.db.execute("SELECT state, wamid, tries, name, lang FROM tpl_out WHERE draft_id=?",
                                        (did,)).fetchone()
        except sqlite3.Error:
            return None


def buttons(params):
    return [b["callback_data"] for row in params["reply_markup"]["inline_keyboard"] for b in row]


def env_door(send="1", tpl="1"):
    return {"WA_SEND": send, "WA_AGENT_TEMPLATES": tpl, "WA_360_API_KEY": KEY}


def listing(status="approved", category="UTILITY", reason=None):
    items = [{"name": n, "language": lg, "status": status, "category": category, "rejected_reason": reason,
              "id": "x%d" % i} for i, (n, lg) in enumerate((n, lg) for n in sorted(S.TEMPLATE_PARAMS)
                                                         for lg in ("ru", "en"))]
    return json.dumps({"waba_templates": items, "count": len(items), "total": len(items)})


class Get:
    def __init__(self, status, body):
        self.status, self.body, self.calls = status, body, []

    def __call__(self, url, key, timeout):
        self.calls.append(url)
        return self.status, self.body, None


class Post:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, url, payload, key, timeout):
        self.calls.append(payload)
        return self.answers[min(len(self.calls), len(self.answers)) - 1]


def svc_door(qpath, get, post, environ=None):
    """Настоящая дверь службы и настоящий `wa_send.send_template`; швы провайдера — подделки."""
    environ = environ or env_door()
    return SVC.SendDoor(qpath, environ=environ,
                        send_template=lambda to, n, lg, p, env=None: S.send_template(
                            to, n, lg, p, env=env, get=get, transport=post, sleep=lambda s: None))


# ═══ выключатель: всё прежнее ═══════════════════════════════════════════════════════════

def test_flag_off_card_and_press_as_before():
    """WA_AGENT_TEMPLATES выкл: окно закрыто, а карточка — три кнопки, строки шаблона нет, окно ядро не спрашивает;
    «Отправить» идёт прежним путём (дверь отказывает сама), таблицы tpl_out нет."""
    w = World(templates=False)
    p = w.draft()
    assert buttons(p) == ["wa:send:1:1", "wa:fix:1:1", "wa:no:1:1"], buttons(p)
    assert "шаблон" not in p["text"].lower(), p["text"]
    w.press("wa:send:1:1")
    assert len(w.door.sends) == 1 and w.door.wcalls == 0, (w.door.sends, w.door.wcalls)
    assert w.state()[0] == A.NOT_SENT and w.answers() == ["not_sent"], (w.state(), w.answers())
    assert w.core.db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='tpl_out'").fetchone()[0] == 0


def test_flag_off_same_calls_as_old_signature():
    """Флаг выкл и ядро, собранное БЕЗ новых аргументов (прежняя сигнатура), дают ОДИНАКОВЫЕ вызовы Bot API и двери."""
    runs = []
    for kw in (True, False):
        w = World(templates=False, kw_templates=kw)
        w.draft()
        w.press("wa:send:1:1")
        w.press("wa:no:1:1")
        runs.append(([(n, json.dumps(p, sort_keys=True)) for n, p in w.http.calls], list(w.door.sends),
                     w.door.wcalls, w.door.tpls))
    assert runs[0] == runs[1], runs


def test_flag_off_tpl_button_refuses_words():
    w = World(templates=False)
    w.draft()
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [] and w.answers() == [A.TPL_OFF_WORDS], (w.door.tpls, w.answers())
    assert w.state()[0] == A.PENDING


# ═══ флаг вкл, окно открыто ═════════════════════════════════════════════════════════════

def test_open_window_no_template_send_as_before():
    w = World()
    w.door.win = {"state": "open", "age": 3600}
    p = w.draft()
    assert buttons(p) == ["wa:send:1:1", "wa:fix:1:1", "wa:no:1:1"], buttons(p)
    assert "шаблон" not in p["text"].lower()
    w.press("wa:send:1:1")
    assert w.door.sends == [(NUM, RU)] and w.state()[0] == A.SENT and w.answers() == ["sent"], (
        w.door.sends, w.state(), w.answers())
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [], w.door.tpls


def test_unknown_window_old_path():
    """Окно не измерено (проба двери: unknown) — шаблон не предлагается, «Отправить» — прежний путь двери."""
    w = World()
    w.door.win = {"state": "unknown", "age": None}
    p = w.draft()
    assert buttons(p) == ["wa:send:1:1", "wa:fix:1:1", "wa:no:1:1"], buttons(p)
    w.press("wa:send:1:1")
    assert len(w.door.sends) == 1, w.door.sends


# ═══ флаг вкл, окно закрыто ═════════════════════════════════════════════════════════════

def test_closed_card_offers_template():
    """Карточка, родившаяся при закрытом окне: вторым рядом «📨 Отправить шаблоном», строка с текстом шаблона ru."""
    w = World()
    p = w.draft()
    assert buttons(p) == ["wa:send:1:1", "wa:fix:1:1", "wa:no:1:1", "wa:tpl:1:1"], buttons(p)
    assert p["reply_markup"]["inline_keyboard"][1][0]["text"] == G.W_TPL_BUTTON
    assert TPL_RU in p["text"] and "по аренде байка" in p["text"], p["text"]


def test_send_closed_window_before_claim():
    """«✅ Отправить» при закрытом окне: дверь send_text НЕ звана, черновик pending, ответ называет окно словами,
    карточка правится с кнопкой шаблона."""
    w = World()
    w.draft()
    w.press("wa:send:1:1")
    assert w.door.sends == [], w.door.sends
    assert w.state() == (A.PENDING, 1), w.state()
    ans = w.answers()[-1]
    assert "окно 24 ч закрыто" in ans and "30 ч назад" in ans and "Отправить шаблоном" in ans, ans
    ed = w.http.of("editMessageText")[-1]
    assert ed["message_id"] == 101 and "wa:tpl:1:1" in buttons(ed) and "wa:send:1:1" in buttons(ed), ed
    assert "окно 24 ч закрыто" in ed["text"] and "Дарья" in ed["text"], ed["text"]


def test_press_template_one_send_sending_before_door():
    w = World()
    w.draft()
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [(NUM, "reply_request", "ru", ["байка"])], w.door.tpls
    assert w.door.seen == [[("sending",)]], w.door.seen         # sending записан ДО двери
    assert w.tpl_row()[:2] == ("sent", "wamid.TPL1"), w.tpl_row()
    out = w.core.db.execute("SELECT wamid, text, via FROM outbox").fetchall()
    assert out == [("wamid.TPL1", TPL_RU, A.VIA_TEMPLATE)], out
    assert w.state() == (A.PENDING, 1), w.state()                # черновик жив — уйдёт после ответа клиента
    assert "шаблон ушёл" in w.answers()[-1], w.answers()
    ed = w.http.of("editMessageText")[-1]
    assert "ушёл" in ed["text"] and TPL_RU in ed["text"] and "wa:tpl:1:1" not in buttons(ed), ed


def test_second_press_no_second_template():
    w = World()
    w.draft()
    w.press("wa:tpl:1:1")
    w.press("wa:tpl:1:1")
    assert len(w.door.tpls) == 1, w.door.tpls
    assert "уже ушёл" in w.answers()[-1] and "Дарья" in w.answers()[-1], w.answers()
    w.press("wa:send:1:1")                                         # окно всё ещё закрыто — без второго шаблона
    assert w.door.sends == [] and len(w.door.tpls) == 1
    assert "уже ушёл" in w.answers()[-1], w.answers()


def test_claim_holds_when_offer_misses():
    """Второй рубеж: первый (`template_offer`) не увидел ушедший шаблон — захват `tpl_out` второго всё равно не даёт."""
    w = World()
    w.draft()
    w.press("wa:tpl:1:1")
    w.core._tpl_taken = lambda *a: None
    w.press("wa:tpl:1:1")
    assert len(w.door.tpls) == 1, w.door.tpls
    assert "второй раз не шлём" in w.answers()[-1], w.answers()


def test_unknown_outcome_no_repeat():
    w = World()
    w.door.tpl_res = {"outcome": "unknown", "reason": "транспорт молчит", "wamid": None}
    w.draft()
    w.press("wa:tpl:1:1")
    assert w.tpl_row()[0] == A.UNSURE and "не знаю, дошло ли" in w.answers()[-1], (w.tpl_row(), w.answers())
    w.press("wa:tpl:1:1")
    assert len(w.door.tpls) == 1 and "исход неизвестен" in w.answers()[-1], (w.door.tpls, w.answers())


def test_not_approved_words_on_card_buttons_alive():
    """Дверь сказала «не одобрен» — отказ СЛОВАМИ на карточке и в ответе, черновик ждёт, кнопки живы, можно ещё раз."""
    w = World()
    why = "Meta не одобрила шаблон reply_request (ru): статус pending — не отправлено"
    w.door.tpl_res = {"outcome": "not_sent", "reason": why, "wamid": None, "approval": "not_approved"}
    w.draft()
    w.press("wa:tpl:1:1")
    assert w.answers()[-1].startswith("шаблон не отправлен: Meta не одобрила") and "pending" in w.answers()[-1], \
        w.answers()
    assert A.W_CLOSED not in w.answers()[-1]
    ed = w.http.of("editMessageText")[-1]
    assert "статус pending" in ed["text"] and "wa:tpl:1:1" in buttons(ed) and "wa:send:1:1" in buttons(ed), ed
    assert w.state() == (A.PENDING, 1) and w.tpl_row()[0] == A.NOT_SENT
    assert w.core.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
    w.door.tpl_res = {"outcome": "sent", "reason": "принято", "wamid": "wamid.TPL2", "text": TPL_RU}
    w.press("wa:tpl:1:1")                                          # Meta одобрила — тот же черновик, ещё раз
    assert len(w.door.tpls) == 2 and w.tpl_row()[:3] == ("sent", "wamid.TPL2", 2), (w.door.tpls, w.tpl_row())


def test_provider_answer_decides_e2e():
    """Настоящий `wa_send.send_template`: провайдер отдаёт pending → POST не звался, на карточке «статус pending»;
    провайдер отдаёт approved+UTILITY → один POST вида template, черновик ждёт, wamid в outbox."""
    get, post = Get(200, listing("pending")), Post([(200, '{"messages":[{"id":"wamid.REAL1"}]}', None)])
    w = World()
    w.door = svc_door(w.qpath, get, post)
    w.door.window = lambda number: {"state": "closed", "age": 40 * 3600}
    w.new_core()
    w.draft()
    w.press("wa:tpl:1:1")
    assert len(get.calls) == 1 and "/v1/configs/templates" in get.calls[0] and post.calls == [], (get.calls, post.calls)
    assert "статус pending" in w.answers()[-1] and "статус pending" in w.http.of("editMessageText")[-1]["text"]
    get.body = listing("APPROVED")
    w.press("wa:tpl:1:1")
    assert len(post.calls) == 1 and post.calls[0]["type"] == "template", post.calls
    assert post.calls[0]["template"]["name"] == "reply_request" and \
        post.calls[0]["template"]["language"] == {"code": "ru"}, post.calls[0]
    assert w.tpl_row()[:2] == ("sent", "wamid.REAL1") and w.state()[0] == A.PENDING, w.tpl_row()
    out = w.core.db.execute("SELECT text, via FROM outbox WHERE wamid='wamid.REAL1'").fetchone()
    assert out == (TPL_RU, A.VIA_TEMPLATE), out


def test_marketing_and_unread_list_refused_e2e():
    for status, body, want in ((200, listing("approved", "MARKETING"), "MARKETING"),
                               (500, '{"meta":{"developer_message":"boom"}}', "одобрение не проверено")):
        get, post = Get(status, body), Post([(200, '{"messages":[{"id":"w"}]}', None)])
        w = World()
        w.door = svc_door(w.qpath, get, post)
        w.door.window = lambda number: {"state": "closed", "age": 40 * 3600}
        w.new_core()
        w.draft()
        w.press("wa:tpl:1:1")
        assert post.calls == [] and want in w.answers()[-1], (post.calls, w.answers())
        assert w.state()[0] == A.PENDING


# ═══ эхо и ответ клиента ════════════════════════════════════════════════════════════════

def test_echo_of_template_no_pause():
    w = World()
    w.draft()
    w.press("wa:tpl:1:1")
    w.put(T0 + 200, "echo", wamid="wamid.TPL1")
    w.core.tick(T0 + 300)
    paused = w.core.db.execute("SELECT paused FROM clients WHERE number=?", (NUM,)).fetchone()[0]
    assert paused == 0 and w.state()[0] == A.PENDING, (paused, w.state())


def test_client_replies_new_draft_goes_by_normal_button():
    """После шаблона клиент ответил: прежний черновик STALE «клиент написал ещё», окно открыто, новый черновик —
    карточка с тремя кнопками, «✅ Отправить» шлёт текстом."""
    w = World()
    w.draft()
    w.press("wa:tpl:1:1")
    assert len(w.door.tpls) == 1 and w.door.sends == [], (w.door.tpls, w.door.sends)
    w.door.win = {"state": "open", "age": 10}
    rid = w.put(T0 + 1000)
    w.core.tick(T0 + 1001)
    assert w.state(1)[0] == A.STALE, w.state(1)
    reason = w.core.db.execute("SELECT reason FROM drafts WHERE id=1").fetchone()[0]
    assert "клиент написал ещё (строка %d)" % rid in reason, reason
    w.core.tick(T0 + 1000 + A.QUIET_DEFAULT)
    assert w.state(2) == (A.PENDING, 1), w.state(2)
    card = w.http.of("sendMessage")[-1]
    assert buttons(card) == ["wa:send:2:1", "wa:fix:2:1", "wa:no:2:1"], buttons(card)
    w.press("wa:send:2:1", card_id=102)
    assert w.door.sends == [(NUM, RU)] and w.state(2)[0] == A.SENT, (w.door.sends, w.state(2))


# ═══ прочие случаи ══════════════════════════════════════════════════════════════════════

def test_revised_version_after_24h_has_button_old_outdated():
    w = World()
    w.door.win = {"state": "open", "age": 60}
    w.draft()
    w.door.win = {"state": "closed", "age": 25 * 3600}             # карточка провисела сутки
    w.reply(101, "Здравствуйте! Байк ваш, ждём вас.")
    card = w.http.of("sendMessage")[-1]
    assert buttons(card) == ["wa:send:1:2", "wa:fix:1:2", "wa:no:1:2", "wa:tpl:1:2"], buttons(card)
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [] and "устарело" in w.answers()[-1], w.answers()


def test_door_off_no_template_button():
    w = World()
    w.door.open = False
    p = w.draft()
    assert "wa:tpl:1:1" not in buttons(p), buttons(p)
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [] and "отправка выключена" in w.answers()[-1], w.answers()


def test_followup_draft_no_template():
    w = World()
    w.draft()
    w.core.db.execute("UPDATE drafts SET kind=? WHERE id=1", (A.KIND_FOLLOW,))
    assert w.core.template_offer(1, 1) is None
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [], w.door.tpls


def test_language_en_and_other():
    w = World(text=EN)
    p = w.draft()
    assert TPL_EN in p["text"] and "about your bike rental" in p["text"], p["text"]
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [(NUM, "reply_request", "en", ["bike"])], w.door.tpls
    w = World(text=TH)
    p = w.draft()
    assert "wa:tpl:1:1" not in buttons(p) and "шаблона нет" in p["text"] and "не ru и не en" in p["text"], p["text"]
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [] and "не ru и не en" in w.answers()[-1], w.answers()


def test_restart_mid_sending_unsure_no_repeat():
    w = World()
    w.draft()
    w.core.db.execute("INSERT INTO tpl_out(draft_id, number, upto_id, ver, name, lang, state, who, ts) "
                      "VALUES(1,?,1,1,'reply_request','ru','sending','Дарья',?)", (NUM, T0 + 400))
    w.new_core()
    assert w.tpl_row()[0] == A.UNSURE, w.tpl_row()
    assert "исход неизвестен" in w.core.template_offer(1, 1)["why"]
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [], w.door.tpls


def test_one_template_per_client_until_new_inbound():
    """Второй черновик того же клиента на то же входящее шаблона не получает — до нового сообщения клиента."""
    w = World()
    w.draft()
    w.press("wa:tpl:1:1")
    w.core.db.execute("UPDATE drafts SET state='declined' WHERE id=1")
    w.core.db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at) VALUES(?,?,1,?,1,?)",
                      (NUM, A.PENDING, RU, T0 + 600))
    assert "уже ушёл" in w.core.template_offer(2, 1)["why"]


def test_window_probe_failure_is_unknown():
    w = World()

    def boom(number):
        raise RuntimeError("x")
    w.door.window = boom
    p = w.draft()
    assert "wa:tpl:1:1" not in buttons(p)
    w.press("wa:send:1:1")
    assert len(w.door.sends) == 1                                   # прежний путь: окно не измерено


# ═══ служба ═════════════════════════════════════════════════════════════════════════════

def test_svc_flag_and_door():
    assert SVC.F_TEMPLATES == S.TEMPLATES_FLAG == "WA_AGENT_TEMPLATES"
    d = tempfile.mkdtemp(prefix="wa_tpl_svc_t_")
    q = os.path.join(d, "q.db")
    conn = sqlite3.connect(q)
    conn.execute(QSCHEMA)
    now = time.time()
    conn.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, ts_msg) VALUES(?,?,?,?)",
                 (int(now - 30 * 3600), "111", "text", int(now - 30 * 3600)))
    conn.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, ts_msg) VALUES(?,?,?,?)",
                 (int(now - 60), "222", "text", int(now - 60)))
    conn.commit()
    conn.close()
    door = SVC.SendDoor(q, environ=env_door())
    assert door.window("111", now=now)["state"] == "closed" and door.window("222", now=now)["state"] == "open"
    assert door.window("333", now=now)["state"] == "unknown"
    calls = []
    off = SVC.SendDoor(q, environ=env_door(send="0"), send_template=lambda *a, **k: calls.append(a))
    assert off.send_template("111", "reply_request", "ru", ["байка"])["outcome"] == "not_sent" and calls == []
    for flag in ("1", "0"):
        lines = []
        env = {"agent_db": os.path.join(d, "a%s.db" % flag), "queue_db": q, "mirror_db": "", "tg_token": "",
               "show_chat": ""}
        core, _tg, _f, _w = SVC.build(env, environ={"WA_AGENT_TEMPLATES": flag}, line=lines.append)
        assert core.templates is (flag == "1"), core.templates
        assert [ln for ln in lines if ln.startswith("шаблоны (WA_AGENT_TEMPLATES): " + ("вкл" if flag == "1"
                                                                                      else "выкл"))], lines


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
