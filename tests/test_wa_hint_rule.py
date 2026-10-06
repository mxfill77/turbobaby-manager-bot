#!/usr/bin/env python3
"""Пояснение → правило агента WhatsApp (NIGHT0710-B2, выключатель WA_AGENT_HINTS, по умолчанию выключен).

«Исправить» при флаге зовёт ПОЯСНЕНИЕ (приглашение force_reply), такт делает версию по нему моделью; «Отправить» на
такой версии: нажал владелец (по id из события Telegram, строго LESSON_OWNER_IDS) — действующее правило с номером,
автором, временем, источником и откатом; нажал сотрудник — кандидат. Правка текстом правила не рождает. Двойное
нажатие — одно правило. Откат — правила нет в следующем запросе модели. Правило доходит до запроса модели на живом
пути службы (make_model → build → Tg.handle → Core.tick → ModelAdapter.draft → self.call). Суточный список владельцу —
одно сообщение, решает только владелец. Флаг выключен — путь «Исправить»/«Отправить» байт-в-байт прежний (голден).

Всё на подделках: временные очередь (схема wa_webhook), база агента и архив, поддельные Bot API, мост, модель и дверь
из test_wa_agent_model. Сети нет, модель не зовётся. spend_ledger подменяется до импорта (fcntl на ПК — образец
tests/test_agent_facts.py:25-29). WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import hashlib
import inspect
import json
import logging
import os
import sqlite3
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

import wa_agent as A  # noqa: E402
import wa_agent_model as WM  # noqa: E402
import wa_agent_svc as SV  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import test_wa_agent_model as TM  # noqa: E402

NUM, CHAT, T0 = TM.NUM, TM.CHAT, TM.T0
STAFF = TM.HUMAN                                                  # {"id": 501, "first_name": "Дарья"}
OWNER = {"id": 504608015, "is_bot": False, "first_name": "Филипп"}
OWNER_RENAMED = {"id": 504608015, "is_bot": False, "first_name": "Kot"}
OWNER_BIZ = {"id": 6879003264, "is_bot": False, "first_name": "TurboPhuket"}
FAKE_OWNER = {"id": 777001, "is_bot": False, "first_name": "Филипп", "last_name": "(id 504608015)"}
STAFF_NAMED = {"id": 501, "is_bot": False, "first_name": "Филипп"}
BOT = {"id": 777, "is_bot": True, "first_name": "Splinter"}
MODEL_TEXT = "Добрый день! Подскажу."
NEW = "Здравствуйте! Шлем даём бесплатно — по два на байк."      # версия модели по пояснению
HINT = "про шлемы всегда говорим «бесплатно», два на байк, и на вы"
FIX = "Здравствуйте! Шлемы бесплатно."                            # правка полным текстом
HEAD, HIST, ASK_MARK = "УРОКИ ЛЮДЕЙ", "ИСТОРИЯ ПЕРЕПИСКИ", "ПОЯСНЕНИЕ СОТРУДНИКА"
OLD_FIX_WORDS = ("ответьте реплаем на эту карточку своим текстом — будет версия 2, «Отправить» на ней шлёт ваш "
                 "текст дословно")
# Голден флага «выкл»: тот же сценарий на базе a26587da (снят прогоном этого набора на базовом дереве)
GOLDEN_OFF = "ac792a92df7a13d0"


class HintCall:
    """Поддельная модель: запрос с блоком пояснения → NEW, иначе → MODEL_TEXT; пишет (system, user)."""

    def __init__(self):
        self.calls = []

    def __call__(self, system, user):
        self.calls.append((system, user))
        text = NEW if ASK_MARK in user else MODEL_TEXT
        return (json.dumps({"text": text, "lang": "ru", "handoff": [], "why": "вопрос"}, ensure_ascii=False),
                {"model": "fake", "in": 10, "out": 5})


class World:
    """Ядро + руки Telegram + адаптер модели; база правил — база ядра (как в службе). hints=False — прежняя форма
    конструкторов (без новых ключей): набор работает и на базовом дереве."""

    def __init__(self, hints=True, lessons=False, admins=None, hint_hour=24, core_cls=None, **core_kw):
        d = tempfile.mkdtemp(prefix="wa_hint_t_")
        self.dir = d
        self.qpath, self.dbpath, self.apath = (os.path.join(d, n) for n in ("q.db", "agent.db", "arch.db"))
        for path, schema in ((self.qpath, TM.QSCHEMA), (self.apath, TM.ASCHEMA)):
            c = sqlite3.connect(path)
            c.execute(schema)
            c.commit()
            c.close()
        self.call, self.bridge, self.lines = HintCall(), TM.FakeBridge(), []
        self.t = [T0 + 500]
        clock = (lambda: self.t[0])
        akw = {"hints": True, "text_lessons": lessons} if hints else {}
        self.adapter = WM.ModelAdapter(self.qpath, self.call, read_doc=self.bridge.read_doc, fleet=self.bridge.fleet,
                                       door=self.bridge.door, archive_db=self.apath, clock=lambda: T0,
                                       log=self.lines.append, lessons_db=self.dbpath, **akw)
        self.http, self.door = TM.FakeHttp(), TM.FakeDoor()
        self.uid = 1000
        self.tg = G.Tg("123:SECRET", enabled=True, http=self.http, clock=clock, log=self.lines.append)
        ckw = dict(core_kw)
        if admins is not None:
            ckw["lesson_admins"] = admins
        if hints:
            ckw.update(hints=True, hint_hour=hint_hour)
        self.core = (core_cls or A.Core)(self.dbpath, self.qpath, self.adapter, self.tg, self.door, clock=clock,
                                         log=self.lines.append, lessons=lessons, **ckw)
        self.tg.bind(self.core)
        self.core.tick(T0 - 1000)

    def put(self, text="а шлем дадите?", ts=T0):
        q = sqlite3.connect(self.qpath)
        cur = q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history) "
                        "VALUES(?,?,?,?,?,0,0)", (ts, NUM, "text", text, ts))
        q.commit()
        q.close()
        return cur.lastrowid

    def ask(self, text="а шлем дадите?", ts=T0):
        rid = self.put(text, ts)
        self.core.tick(ts + A.QUIET_DEFAULT)
        return rid

    def upd(self, **body):
        self.uid += 1
        body["update_id"] = self.uid
        self.http.updates.append([body])
        self.tg.poll()

    def press(self, data, user=OWNER, msg=None):
        cq = {"id": "cq%d" % (self.uid + 1), "data": data, "message": {"message_id": msg or 0, "chat": {"id": CHAT}}}
        if user is not None:
            cq["from"] = user
        self.upd(callback_query=cq)
        return self.answers()[-1]

    def say(self, text, user=STAFF, reply_to=None, **extra):
        m = {"message_id": 900 + self.uid, "from": user, "chat": {"id": CHAT}}
        if text is not None:
            m["text"] = text
        m.update(extra)
        if reply_to:
            m["reply_to_message"] = {"message_id": reply_to}
        self.upd(message=m)

    def answers(self):
        return [p["text"] for p in self.http.of("answerCallbackQuery")]

    def sent(self):
        return self.http.of("sendMessage")

    def card_of(self, ver, did=1):
        row = self.core.db.execute("SELECT card_id FROM tg_cards WHERE draft_id=? AND ver=? ORDER BY card_id DESC",
                                   (did, ver)).fetchone()
        return row[0] if row else None

    def card_text(self, ver, did=1):
        row = self.core.db.execute("SELECT body FROM tg_cards WHERE draft_id=? AND ver=? ORDER BY card_id DESC",
                                   (did, ver)).fetchone()
        return row[0] if row else ""

    def invite(self, ver=1, did=1):
        row = self.core.db.execute("SELECT msg_id FROM tg_hint_prompts WHERE draft_id=? AND ver=?",
                                   (did, ver)).fetchone()
        return row[0] if row else None

    def explain(self, text=HINT, user=STAFF, ver=1, did=1, tick=True):
        self.press("wa:fix:%d:%d" % (did, ver), user=user, msg=self.card_of(ver, did))
        self.say(text, user=user, reply_to=self.invite(ver, did))
        if tick:
            self.core.tick(self.t[0])

    def send(self, user=OWNER, ver=2, did=1):
        return self.press("wa:send:%d:%d" % (did, ver), user=user, msg=self.card_of(ver, did))

    def rules(self):
        return self.core.db.execute(
            "SELECT id, state, author, author_id, ts, draft_id, ver_from, ver_to, hint, decided_by, decided_by_id, "
            "decided_at, sent_by_id FROM lessons WHERE kind='hint' ORDER BY id").fetchall()

    def count_rules(self):
        return self.core.db.execute("SELECT COUNT(*) FROM lessons WHERE kind='hint'").fetchone()[0]

    def prompt(self):
        return self.adapter.build(NUM, 1, now=T0 + 100)[1]

    def fell(self):
        return [ln for ln in self.lines if "упало" in ln or "упал:" in ln]


def started(**kw):
    w = World(**kw)
    w.ask()
    assert len(w.sent()) == 1, [m["text"][:40] for m in w.sent()]
    return w


def buttons(params):
    return [b["callback_data"] for row in (params.get("reply_markup") or {}).get("inline_keyboard", []) for b in row]


def rule_block(user):
    """Блок уроков/правил между «УРОКИ ЛЮДЕЙ» и «ИСТОРИЯ ПЕРЕПИСКИ» ('' — блока нет)."""
    if HEAD not in user:
        return ""
    return user.split(HEAD, 1)[1].split(HIST, 1)[0]


# ═══ 1. «Отправить» владельца → одно действующее правило с номером, автором и временем ═══════════

def test_owner_send_makes_one_active_rule():
    w = started()
    words = w.press("wa:fix:1:1", user=STAFF, msg=w.card_of(1))
    assert words == G.W_HINT_ASKED, words
    inv = [p for p in w.sent() if (p.get("reply_markup") or {}).get("force_reply")]
    assert len(inv) == 1 and inv[0]["reply_parameters"]["message_id"] == w.card_of(1), inv
    assert "черновику №1, версия 1" in inv[0]["text"], inv[0]["text"]
    calls = len(w.call.calls)
    w.say(HINT, reply_to=w.invite())
    assert len(w.call.calls) == calls, "модель зовётся такт, а не приём сообщения"
    assert "пояснение №1 принято — агент делает версию 2" in w.sent()[-1]["text"], w.sent()[-1]["text"]
    w.core.tick(w.t[0])
    assert len(w.call.calls) == calls + 1 and ASK_MARK in w.call.calls[-1][1] and HINT in w.call.calls[-1][1]
    assert w.core.db.execute("SELECT ver, text FROM drafts WHERE id=1").fetchone() == (2, NEW)
    card2 = w.card_text(2)
    assert "версия 2 по пояснению №1 (Дарья (id 501))" in card2 and HINT in card2 and NEW in card2, card2
    assert buttons(w.sent()[-1]) == ["wa:send:1:2", "wa:fix:1:2", "wa:no:1:2"], buttons(w.sent()[-1])
    words = w.send(OWNER)
    assert w.door.sends == [(NUM, NEW)], w.door.sends
    assert "правило №1 — действует" in words, words
    assert w.rules() == [(1, A.LESSON_ACTIVE, "Дарья (id 501)", 501, T0 + 500, 1, 1, 2, HINT,
                          "Филипп (id 504608015)", 504608015, T0 + 500, 504608015)], w.rules()
    msg = w.sent()[-1]
    assert buttons(msg) == ["wa:unrule:1:0"], buttons(msg)
    for part in ("Правило №1 · действующее правило", "пояснение: " + HINT, "автор пояснения: Дарья (id 501)",
                 "черновик №1, версия 1 → 2"):
        assert part in msg["text"], (part, msg["text"])
    assert not w.fell(), w.fell()


# ═══ 2. «Отправить» сотрудника → только кандидат (и при списке WA_AGENT_LESSON_ADMINS со своим id) ══

def test_staff_send_makes_candidate_only():
    w = started(lessons=True, admins=frozenset({501}))
    w.explain()
    words = w.send(STAFF)
    assert w.door.sends == [(NUM, NEW)], w.door.sends
    assert "кандидат №1" in words, words
    r = w.rules()
    assert len(r) == 1 and r[0][1] == A.LESSON_CANDIDATE and r[0][9] is None and r[0][10] is None, r
    assert r[0][12] == 501, r
    assert HINT not in w.prompt() and "правило:" not in w.prompt()
    w.ask("и ещё: доставка в Раваи?", ts=T0 + 200)
    assert HINT not in w.call.calls[-1][1] and w.adapter.last["info"]["lessons"] == [], w.adapter.last["info"]
    assert w.press("wa:rule:1:0", user=STAFF).startswith("отказ:"), w.answers()
    assert w.rules()[0][1] == A.LESSON_CANDIDATE


# ═══ 3. Правка текстом без пояснения → правила нет ═══════════════════════════════════════════════

def test_text_fix_makes_no_rule():
    w = started(lessons=True)
    w.say(FIX, reply_to=w.card_of(1))                              # правка полным текстом → версия 2
    assert w.core.db.execute("SELECT ver, text FROM drafts WHERE id=1").fetchone() == (2, FIX)
    assert "по пояснению" not in w.card_text(2)
    assert w.send(OWNER) == "sent", w.answers()
    assert w.door.sends == [(NUM, FIX)] and w.count_rules() == 0, w.rules()
    assert [r[1] for r in w.core.db.execute("SELECT id, state FROM lessons")] == [A.LESSON_CANDIDATE]
    assert HEAD not in w.prompt()


def test_text_fix_after_hint_version_makes_no_rule():
    """Пояснение дало версию 2, затем правка текстом — версия 3: «Отправить» владельца на ней правила не рождает."""
    w = started()
    w.explain()
    w.say(FIX, reply_to=w.card_of(2))
    assert w.core.db.execute("SELECT ver, text FROM drafts WHERE id=1").fetchone() == (3, FIX)
    assert w.send(OWNER, ver=3) == "sent", w.answers()
    assert w.door.sends == [(NUM, FIX)] and w.count_rules() == 0, w.rules()


def test_model_version_makes_no_rule():
    w = started()
    assert w.send(OWNER, ver=1) == "sent" and w.count_rules() == 0


# ═══ 4. Двойное нажатие → одно правило ═══════════════════════════════════════════════════════════

def test_double_press_one_rule():
    w = started()
    w.explain()
    w.send(OWNER)
    w.tg._set_offset(0)                                           # offset потерян — то же обновление ещё раз
    w.uid -= 1
    again = w.send(OWNER)
    assert again.startswith("уже решено"), again
    other = w.send(STAFF)                                         # второе нажатие другим обновлением
    assert other.startswith("уже решено"), other
    core2 = A.Core(w.dbpath, w.qpath, w.adapter, w.tg, w.door, clock=lambda: T0 + 600, log=w.lines.append,
                   hints=True, hint_hour=24)                       # второе ядро на той же базе
    res = core2.press(1, 2, A.ACT_SEND, "Филипп (id 504608015)", who_id=504608015)
    assert not res["ok"], res
    assert w.count_rules() == 1 and w.door.sends == [(NUM, NEW)], (w.rules(), w.door.sends)
    # прямой повтор записи правила той же версии — тот же номер, строки одна
    assert w.core._lesson_on_send(1, 2, "Филипп (id 504608015)", 504608015, T0 + 700) == (1, A.LESSON_ACTIVE)
    assert w.count_rules() == 1, w.rules()
    assert not w.fell(), w.fell()


def test_decline_makes_no_rule():
    """«Не нужно» на версии по пояснению — ни отправки, ни правила, ни кандидата."""
    w = started()
    w.explain()
    assert w.press("wa:no:1:2", user=OWNER, msg=w.card_of(2)) == "не отправляем", w.answers()
    assert w.door.sends == [] and w.count_rules() == 0, w.rules()


def test_pace_rule_born_at_press_once():
    """Ритм (WAHUMANPACE0210): «Отправить» до срока — отправка на срок, правило рождается при нажатии; срок настал —
    уходит, второго правила нет (send_due правил не рождает)."""
    w = started(pace=True, rand=lambda: 0.5)
    w.t[0] = T0 + 100
    w.explain()
    words = w.send(OWNER)
    assert words.startswith("уйдёт в") and "правило №1" in words, words
    assert w.door.sends == [] and w.count_rules() == 1, (w.door.sends, w.rules())
    w.core.tick(T0 + 1000)
    assert w.door.sends == [(NUM, NEW)] and w.count_rules() == 1, (w.door.sends, w.rules())


def test_followup_not_explained():
    """Напоминание по пояснению не переписывается (запрос модели у него свой): «Исправить» отвечает прежними словами,
    приглашения нет; пояснение ядру — отказ словами."""
    w = started()
    w.core.db.execute("UPDATE drafts SET kind=? WHERE id=1", (A.KIND_FOLLOW,))
    assert w.press("wa:fix:1:1", user=STAFF, msg=w.card_of(1)) == OLD_FIX_WORDS, w.answers()
    assert w.invite() is None
    res = w.core.hint(1, 1, HINT, "Дарья (id 501)", 501)
    assert not res["ok"] and "напоминание" in res["words"], res


def test_withdrawn_press_makes_no_rule():
    """Нажатие снято (клиент написал ещё, очередь не разобрана) — ничего не ушло и правила нет."""
    w = started()
    w.explain()
    w.put("ещё вопрос", ts=T0 + 300)
    words = w.send(OWNER)
    assert words.startswith("не отправлено: клиент написал ещё"), words
    assert w.door.sends == [] and w.count_rules() == 0, w.rules()


# ═══ 5. Откат → правила нет в следующем запросе модели; откат — только владелец ═════════════════

def test_rollback_removes_rule_from_next_request():
    w = started(lessons=True, admins=frozenset({501}))
    w.explain()
    w.send(OWNER)
    w.ask("и ещё: доставка в Раваи?", ts=T0 + 200)
    blk = rule_block(w.call.calls[-1][1])
    assert "№1: правило: " + HINT in blk, w.call.calls[-1][1][:1500]
    assert w.adapter.last["info"]["lessons"] == [1], w.adapter.last["info"]
    assert w.press("wa:unrule:1:0", user=STAFF).startswith("отказ:"), w.answers()
    w.say("откатить №1", user=STAFF)
    assert w.sent()[-1]["text"].startswith("отказ:"), w.sent()[-1]["text"]
    assert w.rules()[0][1] == A.LESSON_ACTIVE
    words = w.press("wa:unrule:1:0", user=OWNER)
    assert "откатан" in words, words
    row = w.core.db.execute("SELECT state, rolled_by_id FROM lessons WHERE id=1").fetchone()
    assert row == (A.LESSON_ROLLED, 504608015), row
    w.ask("а залог?", ts=T0 + 400)
    user = w.call.calls[-1][1]
    assert HINT not in user and HEAD not in user and w.adapter.last["info"]["lessons"] == [], user[:900]


# ═══ 6. Личность — по id, а не по имени ═════════════════════════════════════════════════════════

def _who_sends(user):
    w = started()
    w.explain()
    w.send(user)
    return w.rules()


def test_identity_by_id_not_name():
    assert _who_sends(FAKE_OWNER)[0][1] == A.LESSON_CANDIDATE, "чужой id с именем владельца — только кандидат"
    assert _who_sends(STAFF_NAMED)[0][1] == A.LESSON_CANDIDATE, "сотрудник «Филипп» — только кандидат"
    assert _who_sends(OWNER_RENAMED)[0][1] == A.LESSON_ACTIVE, "владелец с другим именем — правило"
    assert _who_sends(OWNER_BIZ)[0][1] == A.LESSON_ACTIVE, "второй аккаунт владельца — правило"
    assert _who_sends(None)[0][1] == A.LESSON_CANDIDATE, "нажатие без from — не правило"
    w = World()
    assert w.core.owner(504608015) and w.core.owner("5466425480") and not w.core.owner(501)
    assert not w.core.owner(None) and not w.core.owner("Филипп (id 504608015)")


# ═══ 7. Правило доходит до запроса модели на живом пути службы ═══════════════════════════════════

class LiveBridge(TM.FakeBridge):
    def _call(self, action, name=None, **kw):
        return self.read_doc(name)

    def quote_price(self, *a, **k):
        return self.door(*a)


def _live(environ_extra=None, hints=True):
    d = tempfile.mkdtemp(prefix="wa_hint_live_")
    env = {"queue_db": os.path.join(d, "q.db"), "agent_db": os.path.join(d, "agent.db"), "tg_token": "123:SECRET",
           "show_chat": "", "mirror_db": "", "archive_db": os.path.join(d, "arch.db")}
    for path, schema in ((env["queue_db"], TM.QSCHEMA), (env["archive_db"], TM.ASCHEMA)):
        c = sqlite3.connect(path)
        c.execute(schema)
        c.commit()
        c.close()
    lines, sends, call, http = [], [], HintCall(), TM.FakeHttp()
    model, why = SV.make_model(env, line=lines.append, bridge=LiveBridge(), call=call, **({"hints": True} if hints
                                                                                            else {}))
    assert model is not None, why
    environ = {"WA_AGENT_DRAFTS": "1", "WA_AGENT_CARDS": "1", "WA_SEND": "1", "WA_AGENT_HINTS": "1"}
    environ.update(environ_extra or {})

    def send(to, text, db_path=None):
        sends.append((to, text))
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.OUT%d" % len(sends)}
    core, tg, _flags, _words = SV.build(env, environ=environ, model=model, http=http, send=send,
                                        clock=lambda: T0 + 500, line=lines.append)
    return types.SimpleNamespace(env=env, lines=lines, sends=sends, call=call, http=http, model=model, core=core,
                                 tg=tg, uid=[0])


def _live_put(L, text, ts):
    q = sqlite3.connect(L.env["queue_db"])
    q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history) "
              "VALUES(?,?,?,?,?,0,0)", (ts, NUM, "text", text, ts))
    q.commit()
    q.close()


def _live_upd(L, **body):
    L.uid[0] += 1
    body["update_id"] = L.uid[0]
    L.tg.handle(body)


def _live_card(L, ver):
    row = L.core.db.execute("SELECT card_id FROM tg_cards WHERE draft_id=1 AND ver=?", (ver,)).fetchone()
    return row[0] if row else 0


def test_live_path_rule_reaches_model_request():
    L = _live()
    L.core.tick(T0 - 1000)
    _live_put(L, "а шлем дадите?", T0)
    L.core.tick(T0 + 75)
    _live_upd(L, callback_query={"id": "c1", "from": STAFF, "data": "wa:fix:1:1",
                                 "message": {"message_id": _live_card(L, 1), "chat": {"id": CHAT}}})
    inv = L.core.db.execute("SELECT msg_id FROM tg_hint_prompts").fetchone()
    assert inv, [p.get("text", "")[:60] for p in L.http.of("sendMessage")]
    _live_upd(L, message={"message_id": 900, "from": STAFF, "chat": {"id": CHAT}, "text": HINT,
                          "reply_to_message": {"message_id": inv[0]}})
    L.core.tick(T0 + 100)
    assert _live_card(L, 2), "версии по пояснению нет: " + "; ".join(L.lines[-6:])
    _live_upd(L, callback_query={"id": "c2", "from": OWNER, "data": "wa:send:1:2",
                                 "message": {"message_id": _live_card(L, 2), "chat": {"id": CHAT}}})
    assert L.sends == [(NUM, NEW)], (L.sends, L.lines[-6:])
    _live_put(L, "и ещё: доставка в Раваи?", T0 + 200)
    L.core.tick(T0 + 300)
    user = L.call.calls[-1][1]
    assert "№1: правило: " + HINT in rule_block(user), user[:1500]
    assert L.model.last["info"]["lessons"] == [1], L.model.last["info"]
    assert not [ln for ln in L.lines if "упало" in ln], [ln for ln in L.lines if "упало" in ln]


def test_main_passes_hints_switch():
    """Служба: main передаёт WA_AGENT_HINTS в make_model (вкл — ключ hints, выкл — вызов прежней формы)."""
    class Stop(Exception):
        pass

    def build(*a, **k):
        raise Stop()
    w, seen = World(hints=False), []
    env = {"queue_db": w.qpath, "agent_db": w.dbpath, "mirror_db": "", "tg_token": "", "show_chat": "",
           "log_path": w.dbpath + ".log"}
    saved = (SV.env_of, SV.make_model, SV.build, dict(os.environ))
    try:
        SV.env_of, SV.build = (lambda: env), build
        SV.make_model = lambda e, **kw: seen.append(kw) or (None, "")
        for flag in ("1", None):
            os.environ["WA_AGENT_DRAFTS"] = "1"
            os.environ.pop("WA_AGENT_HINTS", None)
            if flag:
                os.environ["WA_AGENT_HINTS"] = flag
            try:
                SV.main()
            except Stop:
                pass
    finally:
        SV.env_of, SV.make_model, SV.build = saved[:3]
        os.environ.clear()
        os.environ.update(saved[3])
        for h in list(logging.getLogger().handlers):
            logging.getLogger().removeHandler(h)
            h.close()
    assert len(seen) == 2 and seen[0].get("hints") is True and "hints" not in seen[1], seen


def test_svc_switch_line_and_core():
    w = World(hints=False)
    env = {"queue_db": w.qpath, "agent_db": os.path.join(w.dir, "svc.db"), "tg_token": "123:SECRET",
           "show_chat": "", "mirror_db": ""}
    lines = []
    for environ, on in (({}, False), ({"WA_AGENT_HINTS": "1"}, True), ({"WA_AGENT_HINTS": "мусор"}, False)):
        core, _tg, _f, _w = SV.build(env, environ=environ, model=TM.FakeCall(), http=TM.FakeHttp(), line=lines.append)
        assert core.hints is on, (environ, core.hints)
        core.db.close()
    assert any(ln.startswith("пояснения (WA_AGENT_HINTS): вкл") for ln in lines), lines
    assert any(ln.startswith("пояснения (WA_AGENT_HINTS): выкл") for ln in lines), lines


# ═══ 8. Суточный список владельцу ═══════════════════════════════════════════════════════════════

DAY0 = T0 - (T0 + A.PHUKET_OFFSET) % 86400                         # полночь по Пхукету в день T0


def _add_rule(w, n, state, hint, author="Дарья (id 501)"):
    w.core.db.execute("INSERT INTO lessons(state, author, author_id, ts, draft_id, ver_from, ver_to, was_text, "
                      "now_text, kind, hint) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (state, author, 501, T0, 100 + n, 1, 2, "было", "стало", A.KIND_HINT, hint))


def _lists(w):
    return [p for p in w.sent() if p["text"].startswith(G.W_LIST_HEAD)]


def test_daily_list_one_message_owner_decides():
    w = World(hint_hour=21)
    _add_rule(w, 1, A.LESSON_CANDIDATE, "кандидат один: шлем бесплатно")
    _add_rule(w, 2, A.LESSON_CANDIDATE, "кандидат два: депозит наличными")
    _add_rule(w, 3, A.LESSON_ACTIVE, "правило три: на вы")
    w.core.tick(DAY0 + 20 * 3600 + 59 * 60)
    assert _lists(w) == [], "до 21:00 списка нет"
    w.core.tick(DAY0 + 21 * 3600 + 5 * 60)
    lst = _lists(w)
    assert len(lst) == 1, len(lst)
    assert buttons(lst[0]) == ["wa:rule:1:0", "wa:lno:1:0", "wa:rule:2:0", "wa:lno:2:0", "wa:unrule:3:0"], \
        buttons(lst[0])
    for part in ("№1 · кандидат", "№2 · кандидат", "№3 · действующее правило", "«кандидат один: шлем бесплатно»"):
        assert part in lst[0]["text"], (part, lst[0]["text"])
    _add_rule(w, 4, A.LESSON_CANDIDATE, "кандидат четыре")      # родился после списка — в те же сутки не идёт
    w.core.tick(DAY0 + 21 * 3600 + 10 * 60)
    core2 = A.Core(w.dbpath, w.qpath, w.adapter, w.tg, w.door, clock=lambda: T0 + 500, log=w.lines.append,
                   hints=True, hint_hour=21)                       # рестарт: замок в meta
    core2.tick(DAY0 + 21 * 3600 + 15 * 60)
    assert len(_lists(w)) == 1, "второй список в те же сутки"
    w.core.tick(DAY0 + 86400 + 20 * 3600)
    assert len(_lists(w)) == 1, "завтра до часа списка — списка нет"
    w.core.tick(DAY0 + 86400 + 21 * 3600 + 6 * 60)
    assert len(_lists(w)) == 2 and buttons(_lists(w)[-1]) == ["wa:rule:4:0", "wa:lno:4:0"], buttons(_lists(w)[-1])
    w.core.tick(DAY0 + 2 * 86400 + 21 * 3600 + 6 * 60)
    assert len(_lists(w)) == 2, "послезавтра без новых — списка нет"
    # решения: только владелец по id
    assert w.press("wa:rule:1:0", user=STAFF).startswith("отказ:"), w.answers()
    assert w.press("wa:lno:1:0", user=FAKE_OWNER).startswith("отказ:"), w.answers()
    assert w.core.db.execute("SELECT state FROM lessons WHERE id=1").fetchone()[0] == A.LESSON_CANDIDATE
    assert "отклонено" in w.press("wa:lno:2:0", user=OWNER), w.answers()
    assert "действующее правило" in w.press("wa:rule:1:0", user=OWNER), w.answers()
    states = dict(w.core.db.execute("SELECT id, state FROM lessons").fetchall())
    assert states[1] == A.LESSON_ACTIVE and states[2] == A.LESSON_REJECTED, states
    row = w.core.db.execute("SELECT decided_by_id FROM lessons WHERE id=1").fetchone()
    assert row == (504608015,), row
    blk = rule_block(w.prompt())
    assert "кандидат один" in blk and "кандидат два" not in blk and "правило три" in blk, blk
    edits = [p for p in w.http.of("editMessageText") if p["message_id"] == 101]
    assert edits and "№2 · отклонено" in edits[-1]["text"] and "№1 · действующее правило" in edits[-1]["text"], edits
    assert buttons(edits[-1]) == ["wa:unrule:1:0", "wa:unrule:3:0"], buttons(edits[-1])
    assert w.press("wa:unrule:3:0", user=STAFF).startswith("отказ:")
    assert "откатан" in w.press("wa:unrule:3:0", user=OWNER)
    assert "правило три" not in rule_block(w.prompt())


def test_daily_list_limits():
    w = World(hint_hour=21)
    for n in range(1, 31):
        _add_rule(w, n, A.LESSON_CANDIDATE, ("пояснение %d " % n) + "ш" * 2000)
    w.core.tick(DAY0 + 21 * 3600 + 5 * 60)
    lst = _lists(w)
    assert len(lst) == 1, len(lst)
    shown = len([b for b in buttons(lst[0]) if b.startswith("wa:lno:")])
    assert 1 <= shown <= 20 and len(buttons(lst[0])) <= 100 and len(lst[0]["text"]) <= G.TG_TEXT_MAX, \
        (shown, len(lst[0]["text"]))
    assert (G.W_LIST_MORE % (30 - shown)) in lst[0]["text"], lst[0]["text"][-200:]
    left = w.core.db.execute("SELECT COUNT(*) FROM lessons WHERE listed_at IS NULL").fetchone()[0]
    assert left == 30 - shown, (left, shown)


# ═══ дополнительно ═══════════════════════════════════════════════════════════════════════════════

def test_voice_reply_no_hint():
    w = started()
    w.press("wa:fix:1:1", user=STAFF, msg=w.card_of(1))
    calls = len(w.call.calls)
    w.say(None, reply_to=w.invite(), voice={"file_id": "v1", "duration": 3})
    assert w.sent()[-1]["text"] == G.W_HINT_TEXT_ONLY, w.sent()[-1]["text"]
    w.say("   ", reply_to=w.invite())
    w.say(HINT, user=BOT, reply_to=w.invite())
    w.core.tick(w.t[0])
    assert w.core.db.execute("SELECT COUNT(*) FROM hints").fetchone()[0] == 0
    assert len(w.call.calls) == calls and w.core.db.execute("SELECT ver FROM drafts WHERE id=1").fetchone() == (1,)


def test_second_hint_same_version_refused():
    w = started()
    w.explain(tick=False)
    w.say("и ещё одно пояснение", reply_to=w.invite())
    assert "уже есть" in w.sent()[-1]["text"], w.sent()[-1]["text"]
    w.tg._set_offset(0)                                           # повтор того же обновления
    w.uid -= 1
    w.say("и ещё одно пояснение", reply_to=w.invite())
    assert w.core.db.execute("SELECT COUNT(*) FROM hints").fetchone()[0] == 1
    w.core.tick(w.t[0])
    assert len([c for c in w.call.calls if ASK_MARK in c[1]]) == 1


def test_attach_core_passes_who_id():
    import wa_agent_attach as X
    assert "who_id" in inspect.signature(X.AttachCore.press).parameters
    w = started(core_cls=X.AttachCore)
    w.explain()
    w.send(OWNER)
    assert w.rules() and w.rules()[0][1] == A.LESSON_ACTIVE and w.door.sends == [(NUM, NEW)], (w.rules(), w.lines[-5:])
    assert not w.fell(), w.fell()


def test_flag_off_cards_and_press_as_before():
    """Флаг выключен: «Исправить» только отвечает прежними словами, приглашения нет, карточки без «💬», правка
    текстом и «Отправить» как раньше; правил и пояснений нет. Голден — тот же сценарий на базе a26587da."""
    w = World(hints=False)
    w.ask()
    assert w.press("wa:fix:1:1", user=STAFF, msg=w.card_of(1)) == OLD_FIX_WORDS, w.answers()
    assert not [p for p in w.sent() if (p.get("reply_markup") or {}).get("force_reply")]
    w.say(FIX, reply_to=w.card_of(1))
    assert w.press("wa:send:1:2", user=OWNER, msg=w.card_of(2)) == "sent", w.answers()
    w.ask("а залог?", ts=T0 + 300)
    for p in w.sent():
        assert "💬" not in p["text"] and "пояснени" not in p["text"], p["text"]
    assert w.door.sends == [(NUM, FIX)]
    calls = [(n, p) for n, p in w.http.calls if n != "getUpdates"]
    drafts = w.core.db.execute("SELECT * FROM drafts ORDER BY id").fetchall()
    lessons = w.core.db.execute("SELECT id, state, author, ver_from, ver_to FROM lessons").fetchall()
    users = [u for _s, u in w.call.calls]
    blob = json.dumps([calls, drafts, lessons, users], ensure_ascii=False, sort_keys=True, default=str)
    got = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    assert got == GOLDEN_OFF, "голден флага выкл разошёлся с базой: %s" % got


def test_prompt_limits_and_mask():
    rows = [(i, "было", "стало", None, A.KIND_HINT, ("правило %d " % i) + "п" * 2000) for i in range(1, 41)]
    block = WM.lessons_block(rows)
    assert block.startswith(HEAD) and len(block) <= WM.LESSONS_MAX, len(block)
    assert "№40: правило: правило 40" in block and "№1:" not in block and "не поместилось" in block, block[-200:]
    assert all(len(x) <= WM.LESSON_ITEM_MAX + 40 for x in block.split("\n")[1:]), "строка правила длиннее предела"
    assert WM.lessons_block([(7, "a", "b", None)]).endswith("№7: было «a» → стало «b»")
    w = started()
    w.explain("пароль от кабинета Qwerty12345abc — не пиши")
    w.send(OWNER)
    user = w.prompt()
    assert "Qwerty12345abc" not in user and "[скрыто" in rule_block(user), rule_block(user)
    assert "Qwerty12345abc" not in w.call.calls[-1][1], "пояснение в запросе версии — тоже под маской"


def test_journal_without_texts():
    w = started()
    w.explain()
    w.send(OWNER)
    w.press("wa:unrule:1:0", user=OWNER)
    joined = "\n".join(w.lines)
    for s in (HINT, NEW, MODEL_TEXT, NUM):
        assert s not in joined, s
    for s in ("пояснение 1 к версии 1", "версия 2 по пояснению 1", "правило 1: действующее по пояснению 1"):
        assert s in joined, (s, w.lines[-10:])


def test_core_default_off():
    d = tempfile.mkdtemp(prefix="wa_hint_t_")
    q = sqlite3.connect(os.path.join(d, "q.db"))
    q.execute(TM.QSCHEMA)
    q.commit()
    q.close()
    core = A.Core(os.path.join(d, "a.db"), os.path.join(d, "q.db"), TM.FakeCall(), A.Telegram(), A.Door())
    assert core.hints is False
    assert core.hint(1, 1, HINT, "x", 501)["words"] == A.HINT_OFF_WORDS


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
