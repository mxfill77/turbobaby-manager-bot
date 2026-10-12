#!/usr/bin/env python3
"""Второе ядро агента для Telegram (TGCOREA0610, задание Штаба 012b9-7ed.0510; план TGPLAN0510 З2) поверх двери
приёма TGDOOR0510: `wa_agent_svc` собирает `wa_agent.Core(tg_agent.db, tg_queue.db, …)` под флагом канала
WA_AGENT_TG (по умолчанию выключен); читатель getUpdates бота ОДИН (руки WA), нажатия и реплаи «Исправить»
разводятся по префиксу `wa:`/`tg:` и по карточке своей базы.

Всё на подделках: поддельный Bot API, поддельные модели, поддельная дверь WhatsApp (считает вызовы), временные
очереди и базы во временном каталоге (`tempfile.mkdtemp`, префикс `tgcore_`, не удаляются намеренно). Настройки —
словарём в `build(environ=…)`; ни .env, ни окружения процесса набор не читает. Сети нет, модель не зовётся.

Проверки: флаг выключен — строка старта и поведение WA прежние (голден, зелёный и на снимке З1) · флаг включён при
открытой двери WA — ядро TG ни разу не зовёт отправку WA · нажатие tg: базу WA оставляет прежней, нажатие wa: —
базу TG · реплай «Исправить» — ядру своей карточки · номера черновиков двух баз раздельны · у ядра TG выключены
ритм, напоминание, ожидание, уроки, показ, тема → клиенту и реакции · совпавший файл агента канал не собирает.

Поверх (TGCOREC0610, проверка Штаба): падение такта TG — такт WA выполнен, строка одна на серию из 3 и строка
восстановления с числом · сбой сборки канала (ядро, модель, прицеп) — старт WA прежний, канал «не собран», читатель
один · модели TG в main (`models_of`, подделка make_model) не даются уроки, брони и инструменты, строки — «TG: » ·
матрица совпадений файлов TG с любым файлом WA и друг с другом (realpath, samefile) · карточка TG при закрытой двери
без «Отправить», подсказка «Исправить» отправку не обещает; карточка и подсказка WA — голден байт в байт · кнопки
уроков TG — tg:rule/tg:unrule, у WA — прежние wa: · сводка TG — с недоставленными карточками, как у WA."""
import inspect
import json
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import wa_agent as A  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_agent_tg as G  # noqa: E402

QSCHEMA = """CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER NOT NULL,
 channel TEXT NOT NULL DEFAULT 'wa', from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT,
 ts_msg INTEGER, echo INTEGER NOT NULL DEFAULT 0, history INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'new', raw TEXT, wamid TEXT)"""

NUM = "66812345678"
TGNUM = "tg:6879003264"                     # ключ клиента канала TG (wa_webhook.tg_row_event: from_number)
CHAT = G.AGENTS_CHAT
SHOW = "-1004401325262"
T0 = 1_790_000_000
HUMAN = {"id": 501, "is_bot": False, "first_name": "Дарья"}
TOKEN = "123:VYDUMANNYJ"
ALL_ON = {"WA_AGENT_DRAFTS": "1", "WA_AGENT_CARDS": "1", "WA_AGENT_REACT": "1", "WA_SEND": "1"}
TG_ON = dict(ALL_ON, WA_AGENT_TG="1")
GOLDEN_START = ("wa-agent: WA_AGENT_DRAFTS=вкл WA_AGENT_CARDS=вкл WA_AGENT_REACT=вкл WA_AGENT_RELAY=выкл WA_SEND=вкл "
                "WA_AGENT_WATCH=выкл · ключ бота есть · группа показа есть · очередь есть (только чтение) · база показа "
                "есть (только чтение) · читатель getUpdates — только эта служба")


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(float(s), 0.01)


class FakeHttp:
    """Поддельный Bot API: пишет вызовы; getUpdates — из очереди партий, двигает часы."""

    def __init__(self, clock):
        self.calls, self.updates, self.mid, self.clock = [], [], 100, clock

    def __call__(self, method, url, headers=None, data=None, timeout=30):
        name = url.rsplit("/", 1)[-1]
        params = json.loads(data.decode("utf-8")) if data else {}
        self.calls.append((name, params))
        if name == "getUpdates":
            self.clock.t += max(params.get("timeout", 0), 0.5)
            batch = self.updates.pop(0) if self.updates else []
            return 200, json.dumps({"ok": True, "result": batch}).encode()
        if name == "sendMessage":
            self.mid += 1
            return 200, json.dumps({"ok": True, "result": {"message_id": self.mid}}).encode()
        return 200, json.dumps({"ok": True, "result": True}).encode()

    def of(self, name):
        return [p for n, p in self.calls if n == name]


class FakeModel(A.Model):
    def __init__(self, text):
        self.calls, self.text = [], text

    def draft(self, number, upto_id):
        self.calls.append(number)
        return self.text


class World:
    def __init__(self, environ, tg=False, env_over=None, **kw):
        d = tempfile.mkdtemp(prefix="tgcore_")
        self.dir = d
        self.env = {"queue_db": os.path.join(d, "wa_queue.db"), "mirror_db": os.path.join(d, "mirror.db"),
                    "agent_db": os.path.join(d, "wa_agent.db"), "tg_token": TOKEN, "show_chat": SHOW,
                    "log_path": os.path.join(d, "wa_agent.log"),
                    "tg_queue_db": os.path.join(d, "tg_queue.db"), "tg_agent_db": os.path.join(d, "tg_agent.db")}
        for key in ("queue_db", "tg_queue_db"):
            q = sqlite3.connect(self.env[key])
            q.execute(QSCHEMA)
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
        self.clock = Clock(T0)
        self.http = FakeHttp(self.clock)
        self.model, self.tg_model = FakeModel("черновик модели"), FakeModel("черновик TG")
        self.sends, self.media, self.reacts, self.lines = [], [], [], []
        self.uid = 1000
        self.environ = dict(environ)
        more = {"tg_model": self.tg_model} if tg else {}
        more.update(kw)
        self.env.update(env_over or {})
        self.core, self.tg, self.flags, self.words = S.build(
            self.env, environ=self.environ, model=self.model, http=self.http, send=self.send,
            react_send=self.react_send, clock=self.clock, line=self.lines.append, send_media=self.send_media, **more)

    # дверь WhatsApp: считает каждый вызов — канал TG не смеет её звать ни разу
    def send(self, to, text, db_path=None):
        self.sends.append((to, text))
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.OUT%d" % len(self.sends)}

    def send_media(self, to, media, db_path=None):
        self.media.append((to, media))
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.M%d" % len(self.media)}

    def react_send(self, number, wamid, emoji):
        self.reacts.append((number, wamid, emoji))
        return {"outcome": "sent", "reason": "ok"}

    @property
    def tgc(self):
        return getattr(S, "tg_core_of", lambda tg: None)(self.tg)

    def put(self, key, number, ts):
        q = sqlite3.connect(self.env[key])
        q.execute("INSERT INTO wa_inbox(ts_queued, channel, from_number, msg_type, text, ts_msg, echo, history) "
                  "VALUES(?,?,?,?,?,?,0,0)", (ts, "tg" if key == "tg_queue_db" else "wa", number, "text", "x", ts))
        q.commit()
        q.close()

    def upd(self, **body):
        self.uid += 1
        body["update_id"] = self.uid
        return body

    def press(self, data, card_id=101):
        return self.upd(callback_query={"id": "cq%d" % (self.uid + 1), "from": HUMAN, "data": data,
                                        "message": {"message_id": card_id, "chat": {"id": CHAT}}})

    def reply(self, card_id, text):
        return self.upd(message={"message_id": 9000 + self.uid, "chat": {"id": CHAT}, "from": HUMAN, "text": text,
                                 "reply_to_message": {"message_id": card_id}})

    def serve(self, seconds):
        end = self.clock.t + seconds
        return S.serve(self.core, self.tg, self.words, lambda: self.clock.t >= end, clock=self.clock,
                       sleep=self.clock.sleep, line=self.lines.append)

    def answers(self):
        return [p["text"] for p in self.http.of("answerCallbackQuery")]

    def cards(self, prefix):
        out = []
        for p in self.http.of("sendMessage"):
            kb = (p.get("reply_markup") or {}).get("inline_keyboard") or []
            datas = [b["callback_data"] for row in kb for b in row]
            if datas and datas[0].startswith(prefix + ":"):
                out.append((p, datas))
        return out

    def two_drafts(self):
        """По одному черновику в каждой базе через такт ядер (карточки доставлены)."""
        self.core.tick(T0 - 1000)
        self.tgc.tick(T0 - 1000)                       # первый старт ядра TG: курсор на MAX(id) своей очереди
        self.put("queue_db", NUM, T0 - 200)
        self.put("tg_queue_db", TGNUM, T0 - 200)
        self.core.tick(T0)
        self.tgc.tick(T0)
        return self


def dump(path, skip_offset=False):
    """Все таблицы базы целиком (по порядку строк). skip_offset — без строки meta 'tg_offset': это счётчик
    ЕДИНСТВЕННОГО читателя, он обязан двигаться на любое обновление, и живёт он в базе WA."""
    c = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        out = {}
        for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
            rows = c.execute("SELECT * FROM %s" % name).fetchall()
            if skip_offset and name == "meta":
                rows = [r for r in rows if r[0] != "tg_offset"]
            out[name] = sorted(repr(r) for r in rows)
        return out
    finally:
        c.close()


def draft(path, did=1):
    c = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        return c.execute("SELECT number, state, ver, text FROM drafts WHERE id=?", (did,)).fetchone()
    finally:
        c.close()


# ═══ флаг выключен — WA прежний (голден) ══════════════════════════════════════════════════

def test_flag_off_golden_start_line_and_wa_behaviour():
    for environ in (ALL_ON, dict(ALL_ON, WA_AGENT_TG="0"), dict(ALL_ON, WA_AGENT_TG=""),
                    dict(ALL_ON, WA_AGENT_TG="no")):
        w = World(environ)
        assert w.tgc is None and "WA_AGENT_TG" not in w.words, (environ, w.words)
        assert not os.path.exists(w.env["tg_agent_db"]), "файл агента TG создан при выключенном канале"
        assert S.start_line(w.env, w.words) == GOLDEN_START, S.start_line(w.env, w.words)
        assert not [ln for ln in w.lines if "TG" in ln], w.lines
        assert getattr(w.tg, "peers", {}) == {}, w.tg.peers
        w.core.tick(T0 - 1000)
        w.put("queue_db", NUM, T0 - 200)
        w.http.updates = [[], [], [w.press("wa:send:1:1")], [w.press("wa:send:1:1")]]
        w.serve(60)
        cards = w.cards("wa")
        assert len(cards) == 1 and cards[0][1] == ["wa:send:1:1", "wa:fix:1:1", "wa:no:1:1"], cards
        assert "черновик модели" in cards[0][0]["text"] and "Анна · +" + NUM in cards[0][0]["text"], cards
        assert w.sends == [(NUM, "черновик модели")], w.sends
        assert draft(w.env["agent_db"]) == (NUM, A.SENT, 1, "черновик модели"), draft(w.env["agent_db"])
        assert w.answers()[0] == "sent" and w.answers()[1].startswith("уже решено"), w.answers()
        assert w.tg_model.calls == [] and not [ln for ln in w.lines if ln.startswith("сводка TG")], w.lines
        polls = w.http.of("getUpdates")
        assert polls and all(p["allowed_updates"] == ["callback_query", "message", "message_reaction"]
                             for p in polls), polls[:1]


# ═══ флаг включён: дверь TG закрыта насовсем, WA своей дверью ═════════════════════════════

def test_flag_on_wa_door_open_tg_core_never_calls_wa_send():
    w = World(TG_ON, tg=True)
    tgc = w.tgc
    assert tgc is not None and w.words["WA_AGENT_TG"].startswith("вкл"), w.words
    assert w.words["WA_SEND"] == "вкл" and w.core._door_open() is True             # дверь WA открыта
    w.core.tick(T0 - 1000)
    tgc.tick(T0 - 1000)
    w.put("queue_db", NUM, T0 - 200)
    w.put("tg_queue_db", TGNUM, T0 - 200)
    w.http.updates = [[], [], [w.press("wa:send:1:1")], [w.press("tg:send:1:1")], [w.press("tg:send:1:1")]]
    stats = w.serve(90)
    assert w.tg_model.calls == [TGNUM] and w.model.calls == [NUM], (w.tg_model.calls, w.model.calls)
    tcards = w.cards("tg")
    # TGCOREC0610: дверь TG закрыта — «Отправить» на карточке TG нет (решение владельца 00:59)
    assert len(tcards) == 1 and tcards[0][1] == ["tg:fix:1:1", "tg:no:1:1"], tcards
    assert "TG · " + TGNUM in tcards[0][0]["text"] and G.W_DOOR_CLOSED in tcards[0][0]["text"], tcards
    assert w.sends == [(NUM, "черновик модели")] and w.media == [], (w.sends, w.media)   # TG — ни одного вызова
    assert draft(w.env["tg_agent_db"]) == (TGNUM, A.PENDING, 1, "черновик TG"), draft(w.env["tg_agent_db"])
    ans = w.answers()
    assert ans[0] == "sent" and all("отправка выключена" in a for a in ans[1:]) and len(ans) == 3, ans
    # устройство — после поведения: дверь TG своя и закрыта насовсем
    assert isinstance(tgc.door, S.TgDoor) and tgc.door.is_open() is False and tgc._door_open() is False, tgc.door
    # дверь TG сама — до сети и без wa_send; перенос из темы — тоже не наружу
    res = tgc.door.send_text(TGNUM, "x")
    assert res["outcome"] == "not_sent" and res["wamid"] is None, res
    rel = tgc.relay(77, TGNUM, "x", "Дарья", now=T0 + 100)
    assert rel["outcome"] == "not_sent" and w.sends == [(NUM, "черновик модели")], rel
    # читатель один: опрашивают только руки WA, руки TG не опрашивают никогда
    side = w.tg.peers["tg"]
    n = len(w.http.of("getUpdates"))
    assert side.reader is False and side.poll(timeout=0) == 0 and len(w.http.of("getUpdates")) == n
    assert stats.get("ticks", 0) >= 5 and not stats.get("tick_fail") and not stats.get("tg_tick_fail"), stats
    line = S.tg_start_line(w.env, tgc, w.words["WA_AGENT_TG"])
    assert line.startswith("wa-agent: канал TG (WA_AGENT_TG): вкл") and "tg_agent.db" in line, line
    assert S.start_line(w.env, w.words) == GOLDEN_START, S.start_line(w.env, w.words)   # строка WA прежняя
    assert [ln for ln in w.lines if ln.startswith("сводка TG:")], w.lines


def test_tg_core_parts_off():
    w = World(dict(TG_ON, WA_AGENT_PACE="1", WA_AGENT_FOLLOWUP="1", WA_AGENT_WATCH="1", WA_AGENT_RELAY="1",
                   WA_AGENT_LESSONS="1"), tg=True)
    tgc, side = w.tgc, w.tg.peers["tg"]
    assert w.core.pace and w.core.followup and w.core.lessons and w.core.watch is not None   # у WA включены
    assert not tgc.pace and not tgc.followup and not tgc.lessons and tgc.watch is None, vars(tgc).keys()
    assert not hasattr(tgc.tg, "agent_line") and tgc.show_agent(T0) == 0            # показа нет по устройству
    assert side.show_chat is None and side.mirror_db is None and not side.relay and not side.react and not side.watch
    assert tgc.queue_path == w.env["tg_queue_db"] and side.prefix == "tg" and w.tg.prefix == "wa"
    assert os.path.realpath(w.env["tg_agent_db"]) != os.path.realpath(w.env["agent_db"])


def test_same_agent_or_queue_file_refused():
    for key, other in (("tg_agent_db", "agent_db"), ("tg_queue_db", "queue_db")):
        w = World(ALL_ON)
        env = dict(w.env)
        env[key] = env[other]
        core, words = S.build_tg(env, w.tg, w.flags, model=w.tg_model, http=w.http, clock=w.clock,
                                 line=w.lines.append)
        assert core is None and "совпал" in words and w.tg.peers == {}, (key, words)


# ═══ разбор нажатий и реплаев по префиксу, номера раздельны ══════════════════════════════

def test_tg_press_keeps_wa_base_and_wa_press_keeps_tg_base():
    w = World(TG_ON, tg=True).two_drafts()
    wa1, tg1 = draft(w.env["agent_db"]), draft(w.env["tg_agent_db"])
    assert wa1 == (NUM, A.PENDING, 1, "черновик модели") and tg1 == (TGNUM, A.PENDING, 1, "черновик TG"), (wa1, tg1)
    before = dump(w.env["agent_db"], skip_offset=True)
    w.tg.handle(w.press("tg:no:1:1"))
    assert draft(w.env["tg_agent_db"])[1] == A.DECLINED, draft(w.env["tg_agent_db"])
    assert dump(w.env["agent_db"], skip_offset=True) == before, "нажатие tg: тронуло базу WA"
    assert draft(w.env["agent_db"]) == wa1
    before_tg = dump(w.env["tg_agent_db"])
    w.tg.handle(w.press("wa:no:1:1"))
    assert draft(w.env["agent_db"])[1] == A.DECLINED, draft(w.env["agent_db"])
    assert dump(w.env["tg_agent_db"]) == before_tg, "нажатие wa: тронуло базу TG"
    assert w.answers() == ["не отправляем", "не отправляем"], w.answers()
    # чужой префикс — прежнее «неизвестная кнопка», базы целы
    a, b = dump(w.env["agent_db"], skip_offset=True), dump(w.env["tg_agent_db"])
    w.tg.handle(w.press("xx:no:1:1"))
    assert w.answers()[-1] == "неизвестная кнопка" and dump(w.env["tg_agent_db"]) == b
    assert dump(w.env["agent_db"], skip_offset=True) == a


def test_fix_reply_goes_to_core_of_its_card():
    w = World(TG_ON, tg=True).two_drafts()
    (wcard, _), = w.cards("wa")
    (tcard, _), = w.cards("tg")
    wmid = w.core.db.execute("SELECT card_id FROM drafts WHERE id=1").fetchone()[0]
    tmid = w.tgc.db.execute("SELECT card_id FROM drafts WHERE id=1").fetchone()[0]
    assert wmid != tmid and wmid and tmid, (wmid, tmid)
    w.tg.handle(w.press("tg:fix:1:1"))
    assert "ответьте реплаем" in w.answers()[-1], w.answers()
    before = dump(w.env["agent_db"], skip_offset=True)
    w.tg.handle(w.reply(tmid, "текст человека TG"))
    assert draft(w.env["tg_agent_db"]) == (TGNUM, A.PENDING, 2, "текст человека TG"), draft(w.env["tg_agent_db"])
    assert dump(w.env["agent_db"], skip_offset=True) == before, "реплай на карточку TG тронул базу WA"
    before_tg = dump(w.env["tg_agent_db"])
    w.tg.handle(w.reply(wmid, "текст человека WA"))
    assert draft(w.env["agent_db"]) == (NUM, A.PENDING, 2, "текст человека WA"), draft(w.env["agent_db"])
    assert dump(w.env["tg_agent_db"]) == before_tg, "реплай на карточку WA тронул базу TG"
    v2 = [p for p, d in w.cards("tg") if d[0] == "tg:fix:1:2"]          # без «Отправить» (TGCOREC0610)
    assert len(v2) == 1, w.cards("tg")
    assert w.sends == [] and w.media == [], w.sends


def test_press_owner_and_attach():
    w = World(TG_ON, tg=True)
    side = w.tg.peers["tg"]
    assert w.tg._press_owner({"data": "tg:send:1:1"}) is side
    assert w.tg._press_owner({"data": "wa:send:1:1"}) is w.tg
    assert w.tg._press_owner({"data": "zz:send:1:1"}) is w.tg and w.tg._press_owner({}) is w.tg
    for bad in (G.Tg(TOKEN, prefix="wa", reader=False), G.Tg(TOKEN, prefix="tg", reader=False),
                G.Tg(TOKEN, prefix="xx", reader=True)):
        try:
            w.tg.attach(bad)
        except ValueError:
            continue
        raise AssertionError("attach принял %s/%s" % (bad.prefix, bad.reader))


# ═══ TGCOREC0610: проверка Штаба поверх TGCOREA0610 ═══════════════════════════════════════════════

# голден WA снят на СНИМКЕ C (код до правки) пробой tmp/tgcore_0610/wa_card_probe_c.py base: дверь WA закрыта
GOLDEN_WA_CARD_SHUT = ("📝 Черновик №1 · версия 1 · Анна · +66812345678\n\nчерновик модели\n\n⛔ отправка выключена — "
                       "ответьте клиенту сами\n✏️ ответьте на карточку полным готовым текстом для клиента — он целиком "
                       "станет новой версией\n\n💭 агент не объяснил\n🔎 числа кодом не проверялись\n\n── подробности "
                       "──\nтема: https://t.me/c/4401325262/42")
GOLDEN_WA_KB = {"inline_keyboard": [[{"text": "✅ Отправить", "callback_data": "wa:send:1:1"},
                                     {"text": "✏️ Исправить", "callback_data": "wa:fix:1:1"},
                                     {"text": "✖️ Не нужно", "callback_data": "wa:no:1:1"}]]}
GOLDEN_WA_FIX = "ответьте реплаем на эту карточку своим текстом — будет версия 2, «Отправить» на ней шлёт ваш текст дословно"
TG_SHUT = "канал не собран: "


class TickCore:
    """Поддельное ядро для такта: считает такты; fail() истинно — такт падает (как без tg_queue.db)."""

    def __init__(self, fail):
        self.n, self.fail = 0, fail

    def tick(self, now=None):
        self.n += 1
        if self.fail():
            raise sqlite3.OperationalError("no such table: wa_inbox")


def test_tg_tick_fail_one_line_per_series_wa_tick_done():
    bad = {"on": True}
    wa, tg = TickCore(lambda: False), TickCore(lambda: bad["on"])
    lines, stats = [], {}
    two = S.TwoCores(wa, tg, lines.append, stats)
    for i in range(3):
        two.tick(T0 + i)                                   # исключение наружу не идёт — такт WA не задет
    assert wa.n == 3 and tg.n == 3, (wa.n, tg.n)
    assert len(lines) == 1 and lines[0].startswith("TG: такт упал: OperationalError"), lines
    assert stats["tg_tick_fail"] == 3, stats                # счётчик прежний — каждый упавший такт
    bad["on"] = False
    two.tick(T0 + 3)
    assert lines[1:] == ["TG: такт снова идёт — упало тактов подряд: 3"], lines
    two.tick(T0 + 4)
    assert len(lines) == 2 and stats["tg_tick_fail"] == 3, (lines, stats)
    bad["on"] = True
    two.tick(T0 + 5)
    two.tick(T0 + 6)
    assert len([ln for ln in lines if ln.startswith("TG: такт упал")]) == 2 and stats["tg_tick_fail"] == 5, lines
    assert wa.n == 7, wa.n
    # живой цикл: очереди TG нет — серия упавших тактов, одна строка, ядро WA доставляет карточку и шлёт
    w = World(TG_ON, tg=True)
    w.tgc.queue_path = os.path.join(w.dir, "нет_очереди_tg.db")
    w.core.tick(T0 - 1000)
    w.put("queue_db", NUM, T0 - 200)
    w.http.updates = [[], [], [w.press("wa:send:1:1")]]
    stats = w.serve(60)
    fall = [ln for ln in w.lines if ln.startswith("TG: такт упал")]
    assert len(fall) == 1 and stats.get("tg_tick_fail", 0) >= 3 and not stats.get("tick_fail"), (fall, stats)
    assert w.sends == [(NUM, "черновик модели")] and len(w.cards("wa")) == 1, w.sends
    summ = [ln for ln in w.lines if ln.startswith("сводка TG:")]
    assert summ and "тактов TG упало" in summ[0], summ


def _wa_alone(w):
    """WA как при выключенном флаге: строка старта — голден, состояния FLAGS прежние, руки TG не прицеплены."""
    off = World(ALL_ON)
    assert w.tgc is None and getattr(w.tg, "peers", {}) == {}, (w.tgc, w.tg.peers)
    assert S.start_line(w.env, w.words) == GOLDEN_START, S.start_line(w.env, w.words)
    assert {k: w.words[k] for k in S.FLAGS} == {k: off.words[k] for k in S.FLAGS}, w.words
    w.core.tick(T0 - 1000)
    w.put("queue_db", NUM, T0 - 200)
    w.http.updates = [[], [], [w.press("wa:send:1:1")]]
    w.serve(60)
    assert w.sends == [(NUM, "черновик модели")] and w.tg_model.calls == [], (w.sends, w.tg_model.calls)
    assert not [ln for ln in w.lines if ln.startswith("сводка TG")], w.lines


def test_build_fail_channel_not_built_wa_start_unchanged():
    # ядро: каталога файла агента TG нет — sqlite3 не открывает базу
    w = World(TG_ON, tg=True, env_over={"tg_agent_db": os.path.join(tempfile.mkdtemp(prefix="tgcore_"), "нет",
                                                                   "tg_agent.db")})
    assert w.words["WA_AGENT_TG"] == TG_SHUT + "OperationalError", w.words
    assert S.tg_start_line(w.env, None, w.words["WA_AGENT_TG"]) == \
        "wa-agent: канал TG (WA_AGENT_TG): канал не собран: OperationalError"
    _wa_alone(w)
    # модель: сбой сборки модели TG (models_of → tg_fail)
    w = World(TG_ON, tg=True, tg_fail="RuntimeError")
    assert w.words["WA_AGENT_TG"] == TG_SHUT + "RuntimeError", w.words
    _wa_alone(w)
    # прицеп: читатель взял руки TG и упал после — руки отцеплены, читатель снова один
    orig = G.Tg.attach

    def boom(self, side):
        orig(self, side)
        raise KeyError("прицеп")
    G.Tg.attach = boom
    try:
        w = World(TG_ON, tg=True)
    finally:
        G.Tg.attach = orig
    assert w.words["WA_AGENT_TG"] == TG_SHUT + "KeyError", w.words
    _wa_alone(w)


def test_main_models_tg_without_lessons_book_tools():
    calls = []

    def fake(env, line=None, bridge=None, call=None, lessons=False, book=False, cache=None, tools=False):
        calls.append({"env": env, "line": line, "lessons": lessons, "book": book, "cache": cache, "tools": tools})
        if env["queue_db"] == "tgq.db" and fail["on"]:
            raise RuntimeError("модель TG")
        return FakeModel("x"), ""
    fail = {"on": False}
    env = {"queue_db": "waq.db", "agent_db": "waa.db", "archive_db": "arch.db", "archive_manifest": "man.json",
           "archive_media": "media", "tg_queue_db": "tgq.db", "tg_agent_db": "tga.db", "mirror_db": "m.db"}
    environ = dict(TG_ON, WA_AGENT_LESSONS="1", WA_AGENT_BOOK_READ="1", WA_AGENT_TOOLS="1", WA_AGENT_CACHE="1h")
    lines = []
    orig = S.make_model
    S.make_model = fake
    try:
        model, why, tgm, tgwhy, tgfail = S.models_of(env, environ, line=lines.append)
        fail["on"] = True
        res2 = S.models_of(env, environ, line=lines.append)
        res3 = S.models_of(env, dict(ALL_ON, WA_AGENT_LESSONS="1"), line=lines.append)
    finally:
        S.make_model = orig
    wa, tg = calls[0], calls[1]
    assert wa["lessons"] and wa["book"] and wa["tools"] and wa["line"] is None and wa["env"] is env, wa
    assert not tg["lessons"] and not tg["book"] and not tg["tools"], tg       # уроков, броней, инструментов нет
    assert tg["env"]["queue_db"] == "tgq.db" and tg["env"]["agent_db"] == "tga.db", tg["env"]
    assert tg["env"]["archive_db"] == "" and tg["env"]["archive_manifest"] == "" and tg["env"]["archive_media"] == ""
    assert tg["cache"] == wa["cache"], (tg["cache"], wa["cache"])
    tg["line"]("модель: вызов 1")
    assert lines == ["TG: модель: вызов 1"], lines                                # строки модели TG — «TG: »
    assert tgm is not None and tgfail is None and model is not None, (tgm, tgfail)
    assert res2[0] is not None and res2[2] is None and res2[4] == "RuntimeError", res2   # сбой модели TG — не падение
    assert res3[2] is None and res3[4] is None and len(calls) == 5, (res3, len(calls))   # флаг TG выкл — модели TG нет
    src = inspect.getsource(S.main)
    assert "models_of(env, os.environ)" in src and "tg_fail=tg_fail" in src, "main мимо models_of"


def test_clash_matrix_refused():
    w = World(ALL_ON)
    d = w.dir
    base = dict(w.env, archive_db=os.path.join(d, "archive.db"))
    sqlite3.connect(base["archive_db"]).close()
    sqlite3.connect(base["tg_agent_db"]).close()
    cases = [("tg_agent_db", base["tg_queue_db"])]                                   # TG друг с другом
    for tkey in ("tg_agent_db", "tg_queue_db"):
        for wkey in ("agent_db", "queue_db", "mirror_db", "archive_db"):
            cases.append((tkey, base[wkey]))                                         # TG с любым файлом WA
    cases.append(("tg_queue_db", os.path.join(d, ".", "wa_agent.db")))               # иное написание пути
    link = os.path.join(d, "ссылка_на_wa_queue.db")
    try:
        os.link(base["queue_db"], link)                                              # жёсткая ссылка: samefile
        cases.append(("tg_agent_db", link))
    except OSError as e:
        print("жёсткой ссылки нет: %s" % type(e).__name__)
    for key, path in cases:
        env = dict(base)
        env[key] = path
        core, words = S.build_tg(env, w.tg, w.flags, model=w.tg_model, http=w.http, clock=w.clock,
                                 line=w.lines.append)
        assert core is None and "совпал" in words and w.tg.peers == {}, (key, path, words)
    assert len(cases) >= 10, len(cases)
    # через build: совпадение — канал не собран, старт WA прежний
    shared = os.path.join(tempfile.mkdtemp(prefix="tgcore_"), "mirror_shared.db")
    sqlite3.connect(shared).close()
    w2 = World(TG_ON, tg=True, env_over={"mirror_db": shared, "tg_queue_db": shared})
    assert w2.tgc is None and w2.words["WA_AGENT_TG"].startswith(TG_SHUT) and "показа WA" in w2.words["WA_AGENT_TG"]
    assert S.start_line(w2.env, w2.words) == GOLDEN_START and w2.tg.peers == {}
    # контроль: свои файлы — канал собирается
    core, words = S.build_tg(base, w.tg, w.flags, model=w.tg_model, http=w.http, clock=w.clock, line=w.lines.append)
    assert core is not None and words.startswith("вкл"), words


def test_tg_card_without_send_wa_card_golden():
    w = World(dict(TG_ON, WA_SEND="0"), tg=True).two_drafts()
    (wcard, wdatas), = w.cards("wa")
    (tcard, tdatas), = w.cards("tg")
    assert wcard["text"] == GOLDEN_WA_CARD_SHUT and wcard["reply_markup"] == GOLDEN_WA_KB, wcard   # WA байт в байт
    assert tdatas == ["tg:fix:1:1", "tg:no:1:1"] and "Отправить" not in json.dumps(tcard["reply_markup"],
                                                                                     ensure_ascii=False), tcard
    assert G.W_DOOR_CLOSED in tcard["text"] and "TG · " + TGNUM in tcard["text"], tcard["text"]
    w.tg.handle(w.press("wa:fix:1:1"))
    assert w.answers()[-1] == GOLDEN_WA_FIX, w.answers()
    w.tg.handle(w.press("tg:fix:1:1"))
    hint = w.answers()[-1]
    assert hint.startswith("ответьте реплаем на эту карточку своим текстом — будет версия 2") and \
        "Отправить" not in hint and "шлёт" not in hint and "ответьте клиенту сами" in hint, hint
    # кнопка вернётся с открытой дверью TG — та же проба двери, что у нажатия
    side = w.tg.peers["tg"]
    w.tgc.door.is_open = lambda: True
    assert side._send_shown() is True
    mid = side.card(1, 1, TGNUM, "черновик TG")
    p = w.http.of("sendMessage")[-1]
    assert mid and [b["callback_data"] for b in p["reply_markup"]["inline_keyboard"][0]][0] == "tg:send:1:1", p
    # при открытой двери WA — карточка WA та же клавиатура (голден прежней формы)
    w3 = World(TG_ON, tg=True).two_drafts()
    assert w3.cards("wa")[0][0]["reply_markup"] == GOLDEN_WA_KB and \
        w3.cards("tg")[0][1] == ["tg:fix:1:1", "tg:no:1:1"], (w3.cards("wa"), w3.cards("tg"))


def test_lesson_buttons_with_hands_prefix():
    w = World(TG_ON, tg=True).two_drafts()
    side = w.tg.peers["tg"]
    for hands, p in ((w.tg, "wa"), (side, "tg")):
        assert hands._lesson_kb(7, A.LESSON_CANDIDATE) == {"inline_keyboard": [[{
            "text": "📚 Сделать правилом", "callback_data": p + ":rule:7:0"}]]}, p
        assert hands._lesson_kb(7, A.LESSON_ACTIVE) == {"inline_keyboard": [[{
            "text": "↩️ Откатить №7", "callback_data": p + ":unrule:7:0"}]]}, p
        assert hands._lesson_kb(7, "rolled_back") is None
    # нажатие tg:rule — рукам TG, база WA прежняя
    before = dump(w.env["agent_db"], skip_offset=True)
    assert w.tg._press_owner({"data": "tg:rule:1:0"}) is side
    w.tg.handle(w.press("tg:rule:1:0"))
    assert dump(w.env["agent_db"], skip_offset=True) == before, "урок tg: тронул базу WA"


def test_tg_summary_names_undelivered_cards():
    w = World(TG_ON, tg=True).two_drafts()
    tline = S.tg_summary(w.tgc, {"tg_tick_fail": 2})
    wline = S.summary(w.core, w.tg, w.words, {})
    assert tline.startswith("сводка TG: ") and "тактов TG упало 2" in tline, tline
    assert "черновиков без доставленной карточки %d" % w.tgc.undelivered() in tline, tline
    assert S.cards_words(w.tgc) and tline.endswith(S.cards_words(w.tgc)), tline
    assert "черновиков без доставленной карточки" in wline, wline              # как у WA


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL %s %s: %s" % (name, type(e).__name__, str(e)[:300]))
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
