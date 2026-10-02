#!/usr/bin/env python3
"""Уроки людей агента WhatsApp (WAAGENTLESSON0210): «Исправить» с новым текстом пишет КАНДИДАТА урока
(автор, время, источник, было/стало, причина или пусто); перевод в действующие — кнопкой «Сделать
правилом» и только тем, кто в праве (WA_AGENT_LESSON_ADMINS, по умолчанию владелец); действующие идут
в промпт агента блоком с номерами; «Откатить №N» убирает; кандидат в промпт не идёт; выключатель
WA_AGENT_LESSONS по умолчанию выключен. Всё на подделках: временная очередь схемой wa_webhook, временная
база агента и архив, поддельные Bot API, мост, модель и дверь из test_wa_agent_model. Сети нет, модель не
зовётся.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import ast
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_agent_model as WM  # noqa: E402
import wa_agent_svc as SV  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import test_wa_agent_model as TM  # noqa: E402

NUM, CHAT, HUMAN, T0 = TM.NUM, TM.CHAT, TM.HUMAN, TM.T0
OWNER = {"id": 504608015, "is_bot": False, "first_name": "Филипп"}
BOT = {"id": 777, "is_bot": True, "first_name": "Splinter"}
MODEL_TEXT = "Добрый день! Подскажу."            # текст поддельной модели (TM.OK_JSON)
FIX = "Здравствуйте! Шлем даём бесплатно, два на байк."
WHY = "клиенту — на вы, про шлемы всегда «бесплатно»"
HEAD = "УРОКИ ЛЮДЕЙ"
CARD1, CARD2, LESSON_MSG = 101, 102, 103           # sendMessage поддельного Bot API: 101, 102, 103 …


class World:
    """Ядро + руки Telegram + адаптер модели, база уроков — база ядра (как в службе)."""

    def __init__(self, lessons=True, admins=None, feed=True):
        d = tempfile.mkdtemp(prefix="wa_lesson_t_")
        self.qpath, self.dbpath = os.path.join(d, "q.db"), os.path.join(d, "agent.db")
        apath = os.path.join(d, "arch.db")
        q = sqlite3.connect(self.qpath)
        q.execute(TM.QSCHEMA)
        q.commit()
        q.close()
        a = sqlite3.connect(apath)
        a.execute(TM.ASCHEMA)
        a.commit()
        a.close()
        self.call, self.bridge, self.lines = TM.FakeCall(), TM.FakeBridge(), []
        self.adapter = WM.ModelAdapter(self.qpath, self.call, read_doc=self.bridge.read_doc,
                                       fleet=self.bridge.fleet, door=self.bridge.door, archive_db=apath,
                                       clock=lambda: T0, log=self.lines.append,
                                       lessons_db=self.dbpath if feed else "")
        self.http, self.door = TM.FakeHttp(), TM.FakeDoor()
        self.uid = 1000
        self.tg = G.Tg("123:SECRET", enabled=True, http=self.http, clock=lambda: T0 + 500, log=self.lines.append)
        kw = {} if admins is None else {"lesson_admins": admins}
        self.core = A.Core(self.dbpath, self.qpath, self.adapter, self.tg, self.door, clock=lambda: T0 + 500,
                           log=self.lines.append, lessons=lessons, **kw)
        self.tg.bind(self.core)
        self.core.tick(T0 - 1000)

    def ask(self, text="а шлем дадите?", ts=T0):
        q = sqlite3.connect(self.qpath)
        cur = q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history) "
                        "VALUES(?,?,?,?,?,0,0)", (ts, NUM, "text", text, ts))
        q.commit()
        q.close()
        self.core.tick(ts + A.QUIET_DEFAULT)
        return cur.lastrowid

    def upd(self, **body):
        self.uid += 1
        body["update_id"] = self.uid
        self.http.updates.append([body])
        self.tg.poll()

    def press(self, data, user=OWNER, msg=LESSON_MSG):
        self.upd(callback_query={"id": "cq%d" % (self.uid + 1), "from": user, "data": data,
                                 "message": {"message_id": msg, "chat": {"id": CHAT}}})
        return self.answers()[-1]

    def say(self, text, user=HUMAN, reply_to=None):
        m = {"message_id": 900 + self.uid, "from": user, "chat": {"id": CHAT}, "text": text}
        if reply_to:
            m["reply_to_message"] = {"message_id": reply_to}
        self.upd(message=m)

    def fix(self, text=FIX, user=HUMAN):
        self.say(text, user=user, reply_to=CARD1)

    def answers(self):
        return [p["text"] for p in self.http.of("answerCallbackQuery")]

    def replies(self):
        return [p["text"] for p in self.http.of("sendMessage") if "reply_parameters" in p]

    def lessons(self):
        return self.core.db.execute("SELECT id, state, author, author_id, draft_id, ver_from, ver_to, was_text, "
                                    "now_text, reason FROM lessons ORDER BY id").fetchall()

    def prompt(self, upto):
        return self.adapter.build(NUM, upto, now=T0 + 100)[1]


def started(**kw):
    w = World(**kw)
    rid = w.ask()
    assert len(w.http.of("sendMessage")) == 1, w.http.of("sendMessage")
    return w, rid


def buttons(params):
    return [b["callback_data"] for row in (params.get("reply_markup") or {}).get("inline_keyboard", []) for b in row]


def edits_of(w, mid):
    return [p for p in w.http.of("editMessageText") if p["message_id"] == mid]


# ═══ позитивы ════════════════════════════════════════════════════════════════════════════

def test_fix_writes_candidate_with_author():
    w, _rid = started()
    w.fix()
    assert w.lessons() == [(1, A.LESSON_CANDIDATE, "Дарья (id 501)", 501, 1, 1, 2, MODEL_TEXT, FIX, None)], \
        w.lessons()
    row = w.core.db.execute("SELECT ts FROM lessons WHERE id=1").fetchone()
    assert row[0] == T0 + 500, row
    msgs = w.http.of("sendMessage")
    assert len(msgs) == 3, [m["text"][:40] for m in msgs]
    assert "урок №1 записан кандидатом" in msgs[1]["text"], msgs[1]["text"]
    assert FIX in msgs[1]["text"] and buttons(msgs[1]) == ["wa:send:1:2", "wa:fix:1:2", "wa:no:1:2"]
    lesson = msgs[2]
    assert buttons(lesson) == ["wa:rule:1:0"], buttons(lesson)
    for part in ("Урок №1 · кандидат", "было: " + MODEL_TEXT, "стало: " + FIX, "Дарья (id 501)",
                 "черновик №1, версия 1 → 2", "причина: —"):
        assert part in lesson["text"], (part, lesson["text"])
    # «Отправить» на исправленной версии шлёт текст человека дословно — как раньше
    w.press("wa:send:1:2", user=HUMAN, msg=CARD2)
    assert w.door.sends == [(NUM, FIX)], w.door.sends


def test_owner_promotes_lesson_goes_to_prompt():
    w, rid = started()
    w.fix()
    words = w.press("wa:rule:1:0")
    assert "действующее правило" in words and "промпт" in words, words
    assert w.lessons()[0][1] == A.LESSON_ACTIVE, w.lessons()
    ed = edits_of(w, LESSON_MSG)
    assert ed and "✅ действующее правило — Филипп (id 504608015)" in ed[-1]["text"], ed
    assert buttons(ed[-1]) == ["wa:unrule:1:0"], buttons(ed[-1])
    user = w.prompt(rid)
    assert HEAD in user and "№1: было «%s» → стало «%s»" % (MODEL_TEXT, FIX) in user, user[:900]
    # следующий черновик: модель получает блок урока в том же вызове, что историю
    w.ask("и ещё вопрос: доставка в Раваи есть?", ts=T0 + 200)
    system, user2 = w.call.calls[-1]
    assert HEAD in user2 and FIX in user2.split(HEAD)[1].split("ИСТОРИЯ ПЕРЕПИСКИ")[0], user2[:900]
    assert w.adapter.last["info"]["lessons"] == [1], w.adapter.last["info"]


def test_rollback_button_removes_from_prompt():
    w, rid = started()
    w.fix()
    w.press("wa:rule:1:0")
    assert HEAD in w.prompt(rid)
    words = w.press("wa:unrule:1:0")
    assert "откатан" in words, words
    assert w.lessons()[0][1] == A.LESSON_ROLLED, w.lessons()
    assert HEAD not in w.prompt(rid) and FIX not in w.prompt(rid)
    ed = edits_of(w, LESSON_MSG)
    assert "↩️ откатан — Филипп" in ed[-1]["text"] and buttons(ed[-1]) == [], ed[-1]


def test_rollback_by_number_text():
    w, rid = started()
    w.fix()
    w.press("wa:rule:1:0")
    w.say("Откатить №1", user=OWNER)
    assert w.lessons()[0][1] == A.LESSON_ROLLED, w.lessons()
    assert w.replies()[-1].startswith("урок №1 откатан"), w.replies()
    assert HEAD not in w.prompt(rid)
    w.say("откатить 1", user=OWNER)                         # второй раз — «уже решено»
    assert "уже решено" in w.replies()[-1], w.replies()


def test_reason_by_reply_goes_to_prompt():
    w, rid = started()
    w.fix()
    w.say(WHY, reply_to=LESSON_MSG)
    assert w.lessons()[0][9] == WHY, w.lessons()
    assert "причина урока №1 записана" in w.replies()[-1], w.replies()
    ed = edits_of(w, LESSON_MSG)
    assert ed and "причина: " + WHY in ed[-1]["text"] and buttons(ed[-1]) == ["wa:rule:1:0"], ed
    w.press("wa:rule:1:0")
    assert "; причина: " + WHY in w.prompt(rid), w.prompt(rid)[:900]
    w.say("другая причина", reply_to=LESSON_MSG)            # действующий: причину меняет только откат
    assert w.lessons()[0][9] == WHY and w.replies()[-1].startswith("не принято"), (w.lessons(), w.replies())


def test_admins_setting():
    assert A.lesson_admins_of("") == (A.LESSON_OWNER_IDS, "владелец (WA_AGENT_LESSON_ADMINS не задан)")
    assert A.lesson_admins_of(None)[0] == A.LESSON_OWNER_IDS
    assert A.lesson_admins_of("501, 502")[0] == frozenset({501, 502})
    ids, words = A.lesson_admins_of("501,abc")
    assert ids == A.LESSON_OWNER_IDS and "битая" in words, (ids, words)
    w, rid = started(admins=frozenset({501}))
    w.fix()
    assert w.press("wa:rule:1:0", user=OWNER).startswith("отказ"), w.answers()
    assert w.lessons()[0][1] == A.LESSON_CANDIDATE
    assert "действующее правило" in w.press("wa:rule:1:0", user=HUMAN)
    assert w.lessons()[0][1] == A.LESSON_ACTIVE and HEAD in w.prompt(rid)


def test_owner_ids_equal_splinter():
    """Владелец по умолчанию — те же id, что splinter.OWNER_IDS (по тексту, без импорта Splinter)."""
    tree = ast.parse(open(os.path.join(ROOT, "splinter.py"), encoding="utf-8").read())
    got = [ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
           and any(getattr(t, "id", "") == "OWNER_IDS" for t in n.targets)]
    assert got and set(got[-1]) == set(A.LESSON_OWNER_IDS), (got, A.LESSON_OWNER_IDS)


def test_lessons_block_newest_kept():
    assert WM.lessons_block([]) == ""
    rows = [(i, "было %d " % i + "б" * 900, "стало %d" % i, None) for i in range(1, 31)]
    block = WM.lessons_block(rows)
    assert block.startswith(HEAD) and len(block) <= WM.LESSONS_MAX, len(block)
    assert "№30:" in block and "№1:" not in block and "старших уроков не поместилось" in block, block[-300:]
    assert block.index("№29:") < block.index("№30:"), "порядок номеров"


def test_lesson_masked_in_prompt():
    w, rid = started()
    w.fix("Ваш пароль от кабинета Qwerty12345abc, вход по ссылке.")
    w.press("wa:rule:1:0")
    user = w.prompt(rid)
    assert HEAD in user and "Qwerty12345abc" not in user and "[скрыто" in user.split(HEAD)[1], user[:900]


# ═══ негативы ════════════════════════════════════════════════════════════════════════════

def test_non_owner_promote_refused():
    w, rid = started()
    w.fix()
    words = w.press("wa:rule:1:0", user=HUMAN)
    assert words.startswith("отказ:") and "владелец" in words and "урок №1 не тронут" in words, words
    assert w.lessons()[0][1] == A.LESSON_CANDIDATE, w.lessons()
    assert edits_of(w, LESSON_MSG) == [], "сообщение урока тронуто при отказе"
    assert HEAD not in w.prompt(rid)
    assert any("нет права" in ln and "Дарья" in ln for ln in w.lines), w.lines[-5:]


def test_candidate_not_in_prompt():
    w, rid = started()
    w.fix()
    user = w.prompt(rid)
    assert HEAD not in user and FIX not in user, user[:900]
    w.ask("ещё вопрос", ts=T0 + 200)
    assert HEAD not in w.call.calls[-1][1] and w.adapter.last["info"]["lessons"] == []


def test_non_owner_rollback_refused():
    w, rid = started()
    w.fix()
    w.press("wa:rule:1:0")
    w.say("откатить №1", user=HUMAN)
    assert w.replies()[-1].startswith("отказ:"), w.replies()
    assert w.press("wa:unrule:1:0", user=HUMAN).startswith("отказ:"), w.answers()
    assert w.lessons()[0][1] == A.LESSON_ACTIVE and HEAD in w.prompt(rid)


def test_switch_off_as_before():
    w, _rid = started(lessons=False)
    w.fix()
    assert w.lessons() == [], w.lessons()
    msgs = w.http.of("sendMessage")
    assert len(msgs) == 2 and "урок" not in msgs[1]["text"], [m["text"] for m in msgs]
    assert w.core.db.execute("SELECT ver, text FROM drafts WHERE id=1").fetchone() == (2, FIX)
    assert w.press("wa:rule:1:0").startswith(A.LESSON_OFF_WORDS), w.answers()


def test_core_default_off():
    d = tempfile.mkdtemp(prefix="wa_lesson_t_")
    q = sqlite3.connect(os.path.join(d, "q.db"))
    q.execute(TM.QSCHEMA)
    q.commit()
    q.close()
    core = A.Core(os.path.join(d, "a.db"), os.path.join(d, "q.db"), TM.FakeCall(), A.Telegram(), A.Door())
    assert core.lessons is False and core.lesson_admins == A.LESSON_OWNER_IDS


def test_same_text_no_lesson():
    w, _rid = started()
    w.fix(MODEL_TEXT)
    assert w.core.db.execute("SELECT ver FROM drafts WHERE id=1").fetchone()[0] == 2
    assert w.lessons() == [] and "урок" not in w.http.of("sendMessage")[1]["text"]


def test_repeat_update_one_lesson():
    w, _rid = started()
    w.fix()
    w.tg._set_offset(0)                                     # offset потерян — то же обновление ещё раз
    w.uid -= 1
    w.fix()
    assert len(w.lessons()) == 1, w.lessons()
    assert w.replies() and "устарело" in w.replies()[-1], w.replies()


def test_promote_twice_already_decided():
    w, _rid = started()
    w.fix()
    w.press("wa:rule:1:0")
    words = w.press("wa:rule:1:0")
    assert words.startswith("уже решено: урок №1 — действующее правило: Филипп"), words
    w.press("wa:unrule:1:0")
    assert w.press("wa:rule:1:0").startswith("уже решено: урок №1 откатан"), w.answers()


def test_bot_cannot_fix_or_rollback():
    w, _rid = started()
    w.fix()
    w.press("wa:rule:1:0")
    w.say("откатить №1", user=BOT)
    assert w.lessons()[0][1] == A.LESSON_ACTIVE
    assert w.press("wa:unrule:1:0", user=BOT).startswith("отказ: боты"), w.answers()


def test_journal_no_lesson_texts():
    w, _rid = started()
    w.fix()
    w.say(WHY, reply_to=LESSON_MSG)
    w.press("wa:rule:1:0")
    w.press("wa:unrule:1:0")
    joined = "\n".join(w.lines)
    for s in (FIX, MODEL_TEXT, WHY, NUM):
        assert s not in joined, s
    assert "урок 1: кандидат" in joined and "урок 1 → действующий" in joined and "урок 1 → откатан" in joined


def test_svc_switch_and_admins():
    w = World()
    env = {"queue_db": w.qpath, "agent_db": os.path.join(os.path.dirname(w.dbpath), "svc.db"),
           "tg_token": "123:SECRET", "show_chat": "-1004401325262", "mirror_db": ""}
    lines = []
    for environ, on, admins in (({}, False, A.LESSON_OWNER_IDS),
                                ({"WA_AGENT_LESSONS": "1", "WA_AGENT_LESSON_ADMINS": "501"}, True, {501}),
                                ({"WA_AGENT_LESSONS": "мусор", "WA_AGENT_LESSON_ADMINS": "x"}, False,
                                 A.LESSON_OWNER_IDS)):
        core, _tg, _f, _w = SV.build(env, environ=environ, model=TM.FakeCall(), http=TM.FakeHttp(),
                                     line=lines.append)
        assert core.lessons is on and core.lesson_admins == frozenset(admins), (environ, core.lessons,
                                                                               core.lesson_admins)
        core.db.close()
    assert any(ln.startswith("уроки (WA_AGENT_LESSONS): вкл") for ln in lines), lines

    class Bridge:
        def _call(self, *a, **k):
            return {"ok": False}

        def fleet(self):
            return {}

        def quote_price(self, *a):
            return {}
    on, _ = SV.make_model(env, bridge=Bridge(), call=lambda s, u: ("", {}), lessons=True)
    off, _ = SV.make_model(env, bridge=Bridge(), call=lambda s, u: ("", {}))
    assert on.lessons_db == env["agent_db"] and off.lessons_db == "", (on.lessons_db, off.lessons_db)


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
