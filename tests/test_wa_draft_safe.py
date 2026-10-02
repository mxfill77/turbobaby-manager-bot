#!/usr/bin/env python3
"""Карточки агента WhatsApp доходят до «Агентов» или честно числятся недоставленными, отложенный ответ не уходит
устаревшим (WADRAFTSAFE0210, находки 2 и 3 внешнего аудита 02.10).

Доставка: у карточки состояние на диске (`card_out`): wait → sending → delivered (message_id, chat_id, время) →
decided; отказ Telegram — повтор с паузой CARD_RETRY; рестарт очередь продолжает; sending на старте → wait.
Повторяются только карточки — дверь клиенту никогда. Ждущие черновики без доставленной карточки — числом в сводке.
Актуальность: новое входящее снимает и ждущий, и отложенный; «Отправить» привязано к последнему сообщению клиента
и версии контекста; устаревшее нажатие отвечает словами и ничего не шлёт.

Всё на подделках: временная очередь схемой wa_webhook, временная база агента, модель/Telegram/дверь — подделки из
test_wa_agent, test_wa_agent_tg и test_wa_pace. Сети нет. WA_AGENT_SRC=<каталог> подменяет модули (мутанты)."""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_agent_svc as SV  # noqa: E402
import test_wa_agent as TA  # noqa: E402
import test_wa_agent_tg as TG  # noqa: E402
import test_wa_pace as TP  # noqa: E402

NUM, T0 = TA.NUM, TA.T0
CHAT = -1003999596406


class FlakyTG(TP.PaceTG):
    """Telegram, который отказывает: fail — сколько первых карточек не доходит; edit_fail — сколько правок
    исхода отказано (card_done → False); crash — смерть процесса посреди sendMessage."""

    def __init__(self, fail=0, edit_fail=0, crash=False):
        super().__init__()
        self.fail, self.edit_fail, self.crash, self.chat = fail, edit_fail, crash, CHAT
        self.calls, self.edits = [], []

    def card(self, draft_id, ver, number, text):
        self.calls.append((draft_id, ver))
        if self.crash:
            raise TA.Crash()
        if self.fail > 0:
            self.fail -= 1
            return None
        self.cards.append(draft_id)
        return 5000 + len(self.calls)

    def card_done(self, draft_id, card_id, words):
        self.edits.append((draft_id, card_id, words))
        if self.edit_fail > 0:
            self.edit_fail -= 1
            return False
        self.done.append((draft_id, words))
        return True


class World(TP.PaceWorld):
    def __init__(self, tg=None, pace=False, **kw):
        super().__init__(pace=pace, **kw)
        self.tg = tg or FlakyTG()
        self.core.tg = self.tg

    def out(self, did, ver=1):
        db = sqlite3.connect(self.dbpath)
        row = db.execute("SELECT state, tries, next_at, message_id, chat_id, delivered_at, decided_at, words, edit "
                         "FROM card_out WHERE draft_id=? AND ver=?", (did, ver)).fetchone()
        db.close()
        return row

    def sql(self, q, args=()):
        db = sqlite3.connect(self.dbpath)
        db.execute(q, args)
        db.commit()
        db.close()

    def card_id(self, did):
        db = sqlite3.connect(self.dbpath)
        row = db.execute("SELECT card_id FROM drafts WHERE id=?", (did,)).fetchone()
        db.close()
        return row[0]

    def ctx(self):
        db = sqlite3.connect(self.dbpath)
        row = db.execute("SELECT ctx FROM clients WHERE number=?", (NUM,)).fetchone()
        db.close()
        return row[0]


def draft_at(w, ts=T0):
    w.put(ts)
    w.core.tick(ts + w.quiet)
    d = w.drafts(A.PENDING)
    assert len(d) == 1, d
    return d[0][0]


# ═══ 1. доставка ═════════════════════════════════════════════════════════════════════════

def test_card_refused_then_retried_with_pause():
    w = World(tg=FlakyTG(fail=2))
    did = draft_at(w)                                          # черновик на T0+60, первая попытка — отказ
    t = T0 + w.quiet
    st = w.out(did)
    assert st[0] == A.CARD_WAIT and st[1] == 1 and st[2] == t + 5 and st[3] is None, st
    assert w.card_id(did) is None and w.core.undelivered() == 1, w.card_id(did)
    w.core.tick(t + 4)
    assert len(w.tg.calls) == 1, "повтор раньше паузы"
    w.core.tick(t + 5)                                         # вторая попытка — отказ, пауза 15
    assert len(w.tg.calls) == 2 and w.out(did)[2] == t + 5 + 15, (w.tg.calls, w.out(did))
    w.core.tick(t + 19)
    assert len(w.tg.calls) == 2, "повтор раньше второй паузы"
    w.core.tick(t + 20)
    st = w.out(did)
    assert st[0] == A.CARD_DELIVERED and st[3] == 5003 and st[4] == CHAT and st[5] == t + 20, st
    assert w.card_id(did) == 5003 and w.core.undelivered() == 0, w.card_id(did)
    w.core.tick(t + 1000)
    assert len(w.tg.calls) == 3, "доставленную карточку шлют снова"
    assert w.door.sends == [], "повтор карточки звал дверь"


def test_delivered_card_pressed_once():
    w = World(tg=FlakyTG(fail=1))
    did = draft_at(w)
    w.core.tick(T0 + w.quiet + 5)
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 200)
    assert res["state"] == A.SENT and w.door.sends == [(NUM, "черновик 1")], res
    st = w.out(did)
    assert st[0] == A.CARD_DECIDED and st[7].startswith("sent") and st[8] == A.EDIT_OK, st
    assert w.tg.edits[-1][1] == 5002, w.tg.edits


def test_retry_pause_ceiling():
    w = World(tg=FlakyTG(fail=100))
    did = draft_at(w)
    t = T0 + w.quiet
    for _ in range(12):
        t = w.out(did)[2]
        w.core.tick(t)
    st = w.out(did)
    assert st[1] == 13 and st[2] - t == A.CARD_RETRY[-1], st
    assert w.core.undelivered() == 1 and w.door.sends == [], st


def test_restart_continues_queue():
    w = World(tg=FlakyTG(fail=1))
    did = draft_at(w)
    nxt = w.out(did)[2]
    w.restart()
    assert w.out(did)[0] == A.CARD_WAIT and w.out(did)[2] == nxt, w.out(did)
    w.core.tick(nxt)
    assert w.out(did)[0] == A.CARD_DELIVERED and w.card_id(did) == 5002, w.out(did)
    assert w.door.sends == []


def test_restart_mid_delivery():
    w = World(tg=FlakyTG(crash=True))
    w.put(T0)
    try:
        w.core.tick(T0 + w.quiet)
    except TA.Crash:
        pass                                                   # процесс умер посреди sendMessage
    did = w.drafts(A.PENDING)[0][0]
    assert w.out(did)[0] == A.CARD_SENDING, w.out(did)
    w.tg.crash = False
    lines = []
    w.core.db.close()
    w.core = A.Core(w.dbpath, w.qpath, w.model, w.tg, w.door, quiet=w.quiet, log=lines.append)
    assert w.out(did)[0] == A.CARD_WAIT and any("sending→wait 1" in ln for ln in lines), (w.out(did), lines)
    w.core.tick(T0 + 200)
    assert w.out(did)[0] == A.CARD_DELIVERED and len(w.tg.cards) == 1, (w.out(did), w.tg.cards)
    w.core.tick(T0 + 900)
    assert len(w.tg.cards) == 1 and w.door.sends == [], (w.tg.cards, w.door.sends)


def test_decided_before_delivery_not_sent():
    w = World(tg=FlakyTG(fail=1))
    did = draft_at(w)
    w.put(T0 + 62)                                             # клиент написал ещё до доставки
    w.core.tick(T0 + 63)
    st = w.out(did)
    assert w.drafts()[0][1] == A.STALE and st[0] == A.CARD_DECIDED and st[3] is None and st[8] is None, st
    w.core.tick(T0 + 62 + w.quiet)                             # пересобран — у нового своя карточка
    new = w.drafts(A.PENDING)[0][0]
    assert w.tg.calls == [(did, 1), (new, 1)], w.tg.calls
    assert w.core.undelivered() == 0 and w.tg.edits == [], w.tg.edits


def test_queue_skips_draft_closed_while_waiting():
    w = World(tg=FlakyTG(fail=1))
    did = draft_at(w)
    w.sql("UPDATE drafts SET state=? WHERE id=?", (A.DECLINED, did))   # решён мимо _close (запись снаружи)
    w.sql("UPDATE clients SET done_upto=last_in_id")
    w.core.tick(T0 + 200)
    st = w.out(did)
    assert st[0] == A.CARD_DECIDED and "решён до доставки" in st[7] and len(w.tg.calls) == 1, (st, w.tg.calls)


def test_edit_refused_retried():
    w = World(tg=FlakyTG(edit_fail=1))
    did = draft_at(w)
    w.core.press(did, 1, A.ACT_DECLINE, "owner", now=T0 + 100)
    st = w.out(did)
    assert st[0] == A.CARD_DECIDED and st[8] == A.EDIT_WAIT and st[2] == T0 + 105, st
    w.core.tick(T0 + 104)
    assert len(w.tg.edits) == 1, w.tg.edits
    w.core.tick(T0 + 105)
    assert len(w.tg.edits) == 2 and w.out(did)[8] == A.EDIT_OK, (w.tg.edits, w.out(did))
    w.core.tick(T0 + 999)
    assert len(w.tg.edits) == 2 and w.door.sends == [], w.tg.edits


def test_edit_gives_up():
    w = World(tg=FlakyTG(edit_fail=100))
    did = draft_at(w)
    w.core.press(did, 1, A.ACT_DECLINE, "owner", now=T0 + 100)
    for _ in range(30):
        w.core.tick(w.out(did)[2])
    assert len(w.tg.edits) == A.EDIT_MAX and w.out(did)[8] == A.EDIT_GAVE_UP, (len(w.tg.edits), w.out(did))


def test_legacy_pending_taken_into_queue():
    w = World(tg=FlakyTG(fail=100))
    did = draft_at(w)
    w.sql("UPDATE card_out SET state='legacy' WHERE draft_id=?", (did,))
    w.sql("INSERT INTO drafts(number, state, ver, text, upto_id, created_at) VALUES(?,?,1,'x',0,?)",
          ("10000000002", A.PENDING, T0))                     # запись до очереди: карточки нет, строки очереди нет
    old = w.drafts(A.PENDING)[-1][0]
    w.tg.fail = 0
    w.restart()
    assert w.out(old)[0] == A.CARD_WAIT, w.out(old)
    w.core.tick(T0 + 300)
    assert w.out(old)[0] == A.CARD_DELIVERED and w.card_id(old) is not None, w.out(old)


def test_real_tg_send_message_refused_then_delivered():
    w = TG.World()
    real = w.http

    def flaky(method, url, headers=None, data=None, timeout=30):
        if url.endswith("/sendMessage") and flaky.left > 0:
            flaky.left -= 1
            real.calls.append(("sendMessage", {}))
            return 502, b'{"ok": false, "description": "Bad Gateway"}'
        return real(method, url, headers, data, timeout)
    flaky.left = 1
    w.tg.http = flaky
    w.put(T0)
    w.core.tick(T0 + A.QUIET_DEFAULT)
    db = w.core.db
    st = db.execute("SELECT state, message_id FROM card_out WHERE draft_id=1").fetchone()
    assert st == (A.CARD_WAIT, None) and w.core.undelivered() == 1, st
    w.core.tick(T0 + A.QUIET_DEFAULT + 5)
    st = db.execute("SELECT state, message_id, chat_id FROM card_out WHERE draft_id=1").fetchone()
    assert st == (A.CARD_DELIVERED, 101, TG.CHAT), st
    w.feed(w.press("wa:send:1:1"))                            # карточка — сообщение 101: кнопка работает
    assert w.door.sends == [(TG.NUM, "черновик модели")], w.door.sends


def test_real_tg_card_done_contract():
    w = TG.World()
    w.draft()
    assert w.tg.card_done(1, 101, "исход") is True
    w.tg.http = lambda *a, **k: (400, b'{"ok": false, "description": "message to edit not found"}')
    assert w.tg.card_done(1, 101, "исход") is False
    w.tg.http = lambda *a, **k: (None, b"URLError")
    assert w.tg.card_done(1, 101, "исход") is False
    assert w.tg.card_done(1, None, "исход") is None
    off = TG.World(enabled=False)
    assert off.tg.card_done(1, 101, "исход") is None


def test_summary_counts_undelivered():
    w = World(tg=FlakyTG(fail=100))
    draft_at(w)
    words = SV.cards_words(w.core)
    assert "черновиков без доставленной карточки 1" in words and "wait=1" in words, words
    w.core.drafts = False
    assert "черновиков без доставленной карточки 1" in SV.cards_words(w.core), "выключили — число пропало"
    ok = World()
    ok.core.drafts = False
    assert SV.cards_words(ok.core) == "", SV.cards_words(ok.core)


def test_svc_summary_line_carries_count():
    w = TG.World()
    w.tg.http = lambda *a, **k: (502, b"{}")
    w.put(T0)
    w.core.tick(T0 + A.QUIET_DEFAULT)
    words = {k: "вкл" for k in SV.FLAGS}
    line = SV.summary(w.core, w.tg, words, {})
    assert line.endswith("черновиков без доставленной карточки 1"), line


# ═══ 2. актуальность ═════════════════════════════════════════════════════════════════════

def scheduled(w):
    did = draft_at(w)
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 60)
    assert res["state"] == A.SCHEDULED, res
    return did, w.due(did)


def test_new_inbound_withdraws_scheduled_now():
    w = World(pace=True)
    did, due = scheduled(w)
    w.put(T0 + 100)
    w.core.tick(T0 + 101)                                      # скан — до срока
    assert w.drafts()[0][1] == A.STALE, w.drafts()
    assert "клиент написал ещё" in w.tg.done[-1][1] and "черновик пересобирается" in w.tg.done[-1][1], w.tg.done
    w.core.tick(due)
    assert w.door.sends == [], w.door.sends
    w.core.tick(T0 + 100 + w.quiet)
    assert len(w.drafts(A.PENDING)) == 1, "черновик не пересобран"


def test_scheduled_without_news_goes_once():
    w = World(pace=True)
    did, due = scheduled(w)
    w.core.tick(due)
    w.core.tick(due + 60)
    assert w.door.sends == [(NUM, "черновик 1")], w.door.sends


def test_unscanned_inbound_blocks_scheduled():
    w = World(pace=True)
    did, due = scheduled(w)
    w.put(due - 1)                                             # пришло, скан ещё не видел — такт отложенного первым
    w.core.tick(due)
    assert w.door.sends == [] and w.drafts()[0][1] == A.STALE, (w.door.sends, w.drafts())


def test_restart_mid_scheduled():
    w = World(pace=True)
    did, due = scheduled(w)
    w.restart()
    w.put(T0 + 150)
    w.restart()
    w.core.tick(due)
    assert w.door.sends == [] and w.drafts()[0][1] == A.STALE, (w.door.sends, w.drafts())
    other = World(pace=True)
    did2, due2 = scheduled(other)
    other.restart()
    other.core.tick(due2)
    other.restart()
    other.core.tick(due2 + 5)
    assert other.door.sends == [(NUM, "черновик 1")], other.door.sends


def test_phone_reply_withdraws_scheduled_now():
    w = World(pace=True)
    did, due = scheduled(w)
    w.put(T0 + 100, kind="echo")
    w.core.tick(T0 + 101)
    assert w.drafts()[0][1] == A.SUPERSEDED and "ответили с телефона" in w.tg.done[-1][1], w.tg.done
    assert w.paused()[0] == 1, w.paused()
    w.core.tick(due)
    assert w.door.sends == [], w.door.sends


def test_topic_text_withdraws_scheduled_now():
    w = World(pace=True)
    did, due = scheduled(w)
    w.core.relay(900, NUM, "сам отвечу", "owner", now=T0 + 100)
    assert w.drafts()[0][1] == A.SUPERSEDED and "в теме" in w.tg.done[-1][1], (w.drafts(), w.tg.done)
    w.core.tick(due)
    assert w.door.sends == [(NUM, "сам отвечу")], w.door.sends


def test_press_bound_to_last_client_message():
    w = World()
    did = draft_at(w)
    w.sql("UPDATE clients SET last_in_id=last_in_id+7")       # клиент дописал — разобрано мимо снятия черновика
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 100)
    assert not res["ok"] and res["state"] == A.STALE and res["words"].startswith("устарело: клиент написал"), res
    assert w.door.sends == [] and "устарело при нажатии" in w.tg.done[-1][1], (w.door.sends, w.tg.done)
    ok = World()
    did = draft_at(ok)
    assert ok.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 100)["state"] == A.SENT


def test_press_bound_to_context_version():
    w = World()
    did = draft_at(w)
    w.sql("UPDATE clients SET ctx=ctx+1")
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 100)
    assert not res["ok"] and "беседа сменилась" in res["words"] and w.door.sends == [], res
    legacy = World()
    did = draft_at(legacy)
    legacy.sql("UPDATE drafts SET ctx=NULL")                   # черновик старше версии контекста
    legacy.sql("UPDATE clients SET ctx=ctx+1")
    assert legacy.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 100)["state"] == A.SENT


def test_scheduled_bound_to_context_version():
    w = World(pace=True)
    did, due = scheduled(w)
    w.sql("UPDATE clients SET ctx=ctx+1")
    w.core.tick(due)
    assert w.door.sends == [] and w.drafts()[0][1] == A.STALE, (w.door.sends, w.drafts())


def test_context_version_moves_on_each_event():
    w = World()
    w.put(T0)
    w.core.tick(T0 + 1)
    a = w.ctx()
    w.put(T0 + 2)
    w.core.tick(T0 + 3)
    b = w.ctx()
    w.put(T0 + 4, kind="echo")
    w.core.tick(T0 + 5)
    c = w.ctx()
    w.core.resume(NUM, 1, "owner", now=T0 + 6)
    d = w.ctx()
    w.core.human_wrote(NUM, T0 + 7)
    e = w.ctx()
    assert [a, b, c, d, e] == [1, 2, 3, 4, 5], [a, b, c, d, e]
    w.put(T0 + 8, kind="status")                               # квитанция — не событие беседы
    w.core.tick(T0 + 9)
    assert w.ctx() == 5, w.ctx()


def test_double_press_one_send():
    w = World()
    did = draft_at(w)
    one = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 100)
    two = w.core.press(did, 1, A.ACT_SEND, "mike", now=T0 + 101)
    assert one["state"] == A.SENT and not two["ok"] and two["words"].startswith("уже решено"), (one, two)
    assert len(w.door.sends) == 1
    p = World(pace=True)
    did = draft_at(p)
    p.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 60)
    two = p.core.press(did, 1, A.ACT_SEND, "mike", now=T0 + 61)
    assert not two["ok"] and "уже решено" in two["words"], two
    p.core.tick(p.due(did))
    assert len(p.door.sends) == 1, p.door.sends


def test_revise_old_press_dead_new_card_queued():
    w = World(tg=FlakyTG())
    did = draft_at(w)
    w.tg.fail = 1                                              # карточка версии 2 сначала не доходит
    assert w.core.revise(did, "текст человека", "owner", now=T0 + 90, ver=1)
    assert w.out(did, 1)[0] == A.CARD_DECIDED and "устарело" in w.out(did, 1)[7], w.out(did, 1)
    assert w.out(did, 2)[0] == A.CARD_WAIT and w.card_id(did) is None and w.core.undelivered() == 1
    old = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 91)
    assert not old["ok"] and old["words"].startswith("устарело") and w.door.sends == [], old
    w.core.tick(T0 + 95)
    assert w.out(did, 2)[0] == A.CARD_DELIVERED and w.card_id(did) == w.out(did, 2)[3], w.out(did, 2)
    res = w.core.press(did, 2, A.ACT_SEND, "owner", now=T0 + 96)
    assert res["state"] == A.SENT and w.door.sends == [(NUM, "текст человека")], res


def test_pause_no_draft_and_no_send():
    w = World()
    did = draft_at(w)
    w.put(T0 + 70, kind="echo")
    w.core.tick(T0 + 71)
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 72)
    assert not res["ok"] and w.door.sends == [] and w.paused()[0] == 1, res
    w.put(T0 + 80)
    w.core.tick(T0 + 300)
    assert w.drafts(A.PENDING) == [], "на паузе родился черновик"


def test_queue_unreadable_on_press():
    w = World()
    did = draft_at(w)
    real = w.core._fresh

    def broken(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    w.core._fresh = broken
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 100)
    assert not res["ok"] and "очередь не прочитана" in res["words"] and w.door.sends == [], res
    assert w.drafts()[0][1] == A.PENDING, w.drafts()
    w.core._fresh = real
    assert w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 101)["state"] == A.SENT


def test_queue_unreadable_in_send_due():
    w = World(pace=True)
    did, due = scheduled(w)
    real = w.core._fresh

    def broken(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    w.core._fresh = broken
    w.core.send_due(due)
    assert w.door.sends == [] and w.drafts()[0][1] == A.SCHEDULED, w.drafts()
    w.core._fresh = real
    w.core.tick(due + 5)
    assert w.door.sends == [(NUM, "черновик 1")], w.door.sends


# ═══ 4. выключатели по умолчанию ═════════════════════════════════════════════════════════

def test_drafts_off_no_cards_no_calls():
    w = World()
    w.core.drafts = False
    w.put(T0)
    w.core.tick(T0 + 300)
    assert w.tg.calls == [] and w.core.card_counts() == {} and SV.cards_words(w.core) == "", w.tg.calls


def test_journal_no_client_text_or_number():
    lines = []
    w = World(tg=FlakyTG(fail=1, edit_fail=1), pace=True, model=TA.FakeModel(text="секрет"))
    w.core.log = lines.append
    did = draft_at(w)
    w.core.tick(T0 + 200)
    w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 201)
    w.put(T0 + 210)
    w.core.tick(T0 + 211)
    w.core.tick(T0 + 999)
    assert lines and not any(NUM in ln or "секрет" in ln for ln in lines), lines


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
