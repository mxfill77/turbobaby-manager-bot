#!/usr/bin/env python3
"""Исход правки и отправки карточки агента WhatsApp — три слова: подтверждено · отказ · неизвестно (WACARDDONEFIX0210,
независимая проверка 02.10: две воспроизведённые находки по ветке wa-draft-safe-0210 c9470ab).

Правка исхода: True → ok; None по контракту («править нечего») → как раньше; False → повтор не больше EDIT_MAX, итог
gave_up; руки упали (исключение, таймаут) → НЕ ok, повтор в тех же пределах, итог unconfirmed («не подтверждено»).
Отправка карточки: ответ потерян после sendMessage → «неизвестно», не отказ: повтор как раньше, `card_out.lost` и
сводка службы считают отдельно, «возможна вторая карточка»; нажатия по обеим карточкам → одна отправка клиенту.
Прочие вызовы рук (`Core._tg`) исключение глотают в None, как раньше.

Всё на подделках (миры test_wa_draft_safe и test_wa_agent_tg: временные базы; у настоящих рук `Tg` — поддельный HTTP
в живом формате `http_request`: потерянный ответ — (None, b"TimeoutError")). Сети нет.
WA_AGENT_SRC=<каталог> подменяет модули (мутанты)."""
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
import test_wa_draft_safe as DS  # noqa: E402

NUM, T0 = TA.NUM, TA.T0
LOST_WORDS = "возможна вторая карточка, единственность не обещается"


class LossyTG(DS.FlakyTG):
    """Telegram, у которого ответ теряется: edit_raise — сколько правок исхода падают TimeoutError (правка могла
    лечь); lost_send — сколько карточек Telegram ПРИНЯЛ (лежат в группе), а ответ не дошёл (TimeoutError);
    none_done — card_done отвечает None по контракту («править нечего»)."""

    def __init__(self, edit_raise=0, lost_send=0, none_done=False, **kw):
        super().__init__(**kw)
        self.edit_raise, self.lost_send, self.none_done = edit_raise, lost_send, none_done
        self.in_group = []                                       # карточки, которые видят люди группы

    def card(self, draft_id, ver, number, text):
        if self.lost_send > 0:
            self.lost_send -= 1
            self.calls.append((draft_id, ver))
            self.in_group.append((draft_id, ver))                # принято Telegram …
            raise TimeoutError("The read operation timed out")   # … ответ потерян
        mid = super().card(draft_id, ver, number, text)
        if mid is not None:
            self.in_group.append((draft_id, ver))
        return mid

    def card_done(self, draft_id, card_id, words):
        if self.edit_raise > 0:
            self.edit_raise -= 1
            self.edits.append((draft_id, card_id, words))
            raise TimeoutError("The read operation timed out")
        if self.none_done:
            self.edits.append((draft_id, card_id, words))
            return None
        return super().card_done(draft_id, card_id, words)


def cols(w, did, ver=1):
    db = sqlite3.connect(w.dbpath)
    row = db.execute("SELECT lost, edit_unk, edit_tries FROM card_out WHERE draft_id=? AND ver=?", (did, ver)).fetchone()
    db.close()
    return row


def declined(w):
    did = DS.draft_at(w)
    w.core.press(did, 1, A.ACT_DECLINE, "owner", now=T0 + 100)
    return did


# ═══ (а) правка исхода: исключение/таймаут — не ok, повтор, предел, «не подтверждено» ══════════════════════

def test_edit_timeout_not_ok_retried_then_confirmed():
    lines = []
    w = DS.World(tg=LossyTG(edit_raise=1))
    w.core.log = lines.append
    did = declined(w)
    st = w.out(did)
    assert st[0] == A.CARD_DECIDED and st[8] == A.EDIT_WAIT and st[2] == T0 + 105, st     # не ok: повтор через 5 с
    assert cols(w, did)[1:] == (1, 1) and w.core.card_unknown() == (0, 1), cols(w, did)
    assert any("ответ Telegram неизвестен (попытка 1)" in ln for ln in lines), lines
    w.core.tick(T0 + 104)
    assert len(w.tg.edits) == 1, "повтор раньше паузы"
    w.core.tick(T0 + 105)                                      # вторая правка: Telegram подтвердил
    assert len(w.tg.edits) == 2 and w.out(did)[8] == A.EDIT_OK, (w.tg.edits, w.out(did))
    assert w.core.card_unknown() == (0, 0), "подтверждённая правка числится неизвестной"
    w.core.tick(T0 + 999)
    assert len(w.tg.edits) == 2 and w.door.sends == [], w.tg.edits


def test_edit_timeout_until_max_unconfirmed():
    lines = []
    w = DS.World(tg=LossyTG(edit_raise=100))
    w.core.log = lines.append
    did = declined(w)
    for _ in range(30):
        w.core.tick(w.out(did)[2])
    st = w.out(did)
    assert len(w.tg.edits) == A.EDIT_MAX and st[8] == A.EDIT_UNCONFIRMED, (len(w.tg.edits), st)
    assert st[8] != A.EDIT_OK and st[8] != A.EDIT_GAVE_UP, st
    assert cols(w, did)[1:] == (A.EDIT_MAX, A.EDIT_MAX), cols(w, did)
    assert any("исход не подтверждён за %d попыток" % A.EDIT_MAX in ln for ln in lines), lines
    assert w.core.card_unknown() == (0, 1), w.core.card_unknown()
    words = SV.cards_words(w.core)
    assert "правка исхода не подтверждена 1" in words, words
    assert w.door.sends == [], w.door.sends


def test_edit_unknown_then_refusals_unconfirmed_not_gave_up():
    w = DS.World(tg=LossyTG(edit_raise=1, edit_fail=100))     # первая — таймаут (могла лечь), дальше отказы
    did = declined(w)
    for _ in range(30):
        w.core.tick(w.out(did)[2])
    assert len(w.tg.edits) == A.EDIT_MAX and w.out(did)[8] == A.EDIT_UNCONFIRMED, (len(w.tg.edits), w.out(did))
    assert cols(w, did)[1] == 1, cols(w, did)


# ═══ (б) None по контракту и False — прежнее ═════════════════════════════════════════════════════════════

def test_edit_none_by_contract_as_before():
    w = DS.World(tg=LossyTG(none_done=True))
    did = declined(w)
    assert w.out(did)[8] == A.EDIT_OK and len(w.tg.edits) == 1, (w.out(did), w.tg.edits)
    w.core.tick(T0 + 999)
    assert len(w.tg.edits) == 1 and cols(w, did)[1:] == (0, 0), (w.tg.edits, cols(w, did))
    assert w.core.card_unknown() == (0, 0)
    old = DS.World(tg=TA.FakeTG())                              # старая подделка (card_done → None) — как раньше
    did = declined(old)
    assert old.out(did)[8] == A.EDIT_OK, old.out(did)


def test_edit_refused_still_gave_up_not_unknown():
    w = DS.World(tg=LossyTG(edit_fail=100))
    did = declined(w)
    for _ in range(30):
        w.core.tick(w.out(did)[2])
    assert len(w.tg.edits) == A.EDIT_MAX and w.out(did)[8] == A.EDIT_GAVE_UP, (len(w.tg.edits), w.out(did))
    assert cols(w, did)[1] == 0 and w.core.card_unknown() == (0, 0), cols(w, did)
    assert "неизвестен" not in SV.cards_words(w.core), SV.cards_words(w.core)


def test_real_tg_card_done_contract_kept():
    w = TG.World()
    w.draft()
    assert w.tg.card_done(1, 101, "исход") is True
    w.tg.http = lambda *a, **k: (400, b'{"ok": false, "description": "message to edit not found"}')
    assert w.tg.card_done(1, 101, "исход") is False
    w.tg.http = lambda *a, **k: (None, b"TimeoutError")
    assert w.tg.card_done(1, 101, "исход") is False             # контракт card_done прежний: сеть — False
    assert w.tg.card_done(1, None, "исход") is None


# ═══ (в) отправка: принято, ответ потерян — «неизвестно», вторая карточка, одна отправка клиенту ══════════════

def test_send_accepted_then_timeout_core():
    lines = []
    w = DS.World(tg=LossyTG(lost_send=1))
    w.core.log = lines.append
    did = DS.draft_at(w)
    t = T0 + w.quiet
    st = w.out(did)
    assert st[0] == A.CARD_WAIT and st[2] == t + 5 and st[3] is None, st          # повтор как раньше
    assert cols(w, did)[0] == 1 and w.core.card_unknown() == (1, 0), cols(w, did)
    assert any("ответ Telegram неизвестен (попытка 1) — могла лечь" in ln for ln in lines), lines
    assert not any("не доставлена (попытка 1)" in ln for ln in lines), "неизвестное записано отказом"
    w.core.tick(t + 5)                                         # повтор: вторая карточка
    st = w.out(did)
    assert st[0] == A.CARD_DELIVERED and w.tg.in_group == [(did, 1), (did, 1)], (st, w.tg.in_group)
    words = SV.cards_words(w.core)
    assert "отправка карточки 1 — " + LOST_WORDS in words, words
    one = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 200)        # нажатие на одной карточке
    two = w.core.press(did, 1, A.ACT_SEND, "mike", now=T0 + 201)         # и на другой
    assert one["state"] == A.SENT and not two["ok"] and "уже решено" in two["words"], (one, two)
    assert w.door.sends == [(NUM, "черновик 1")], w.door.sends
    w.core.drafts = False                                      # выключили черновики — «неизвестно» в сводке осталось
    assert LOST_WORDS in SV.cards_words(w.core), SV.cards_words(w.core)


def test_real_tg_send_answer_lost_second_card_one_send():
    w = TG.World()
    real = w.http

    def lossy(method, url, headers=None, data=None, timeout=30):
        status, body = real(method, url, headers, data, timeout)          # Telegram принял: сообщение в группе
        if url.endswith("/sendMessage") and lossy.left > 0:
            lossy.left -= 1
            return None, b"TimeoutError"                                  # ответ потерян — живой формат http_request
        return status, body
    lossy.left = 1
    w.tg.http = lossy
    w.put(T0)
    w.core.tick(T0 + A.QUIET_DEFAULT)
    db = w.core.db
    st = db.execute("SELECT state, message_id, lost FROM card_out WHERE draft_id=1").fetchone()
    assert st == (A.CARD_WAIT, None, 1), st                     # не доставлена по нашим данным — и не «отказ»
    assert w.core.card_unknown() == (1, 0)
    w.core.tick(T0 + A.QUIET_DEFAULT + 5)                       # повтор как раньше
    sent = real.of("sendMessage")
    assert len(sent) == 2 and all("wa:send:1:1" in str(p.get("reply_markup")) for p in sent), sent
    st = db.execute("SELECT state, message_id, lost FROM card_out WHERE draft_id=1").fetchone()
    assert st == (A.CARD_DELIVERED, 102, 1), st
    line = SV.summary(w.core, w.tg, {k: "вкл" for k in SV.FLAGS}, {})
    assert "отправка карточки 1 — " + LOST_WORDS in line, line
    w.feed(w.press("wa:send:1:1", card_id=101))                 # первая карточка: ответ на неё потерялся
    w.feed(w.press("wa:send:1:1", user=TG.HUMAN2, card_id=102))  # вторая
    assert w.door.sends == [(TG.NUM, "черновик модели")], w.door.sends
    answers = [p["text"] for p in real.of("answerCallbackQuery")]
    assert len(answers) == 2 and "уже решено" in answers[1], answers


def test_real_tg_refusal_stays_refusal():
    w = TG.World()
    w.tg.http = lambda *a, **k: (502, b'{"ok": false, "description": "Bad Gateway"}')
    w.put(T0)
    w.core.tick(T0 + A.QUIET_DEFAULT)
    st = w.core.db.execute("SELECT state, lost FROM card_out WHERE draft_id=1").fetchone()
    assert st == (A.CARD_WAIT, 0) and w.core.card_unknown() == (0, 0), st
    line = SV.summary(w.core, w.tg, {k: "вкл" for k in SV.FLAGS}, {})
    assert line.endswith("черновиков без доставленной карточки 1") and "неизвестен" not in line, line


def test_restart_mid_send_counts_unknown():
    w = DS.World(tg=DS.FlakyTG(crash=True))
    w.put(T0)
    try:
        w.core.tick(T0 + w.quiet)
    except TA.Crash:
        pass                                                   # процесс умер посреди sendMessage
    did = w.drafts(A.PENDING)[0][0]
    w.tg.crash = False
    lines = []
    w.core.db.close()
    w.core = A.Core(w.dbpath, w.qpath, w.model, w.tg, w.door, quiet=w.quiet, log=lines.append)
    assert w.out(did)[0] == A.CARD_WAIT and cols(w, did)[0] == 1, (w.out(did), cols(w, did))
    assert any("sending→wait 1 (ответ неизвестен" in ln for ln in lines), lines
    assert w.core.card_unknown() == (1, 0)


def test_old_queue_gets_columns():
    w = DS.World()
    d = os.path.dirname(w.dbpath)
    old = os.path.join(d, "old_agent.db")
    db = sqlite3.connect(old)
    db.execute("CREATE TABLE card_out (draft_id INTEGER NOT NULL, ver INTEGER NOT NULL, state TEXT NOT NULL, "
               "tries INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0, message_id INTEGER, chat_id INTEGER, "
               "delivered_at REAL, decided_at REAL, words TEXT, edit TEXT, edit_tries INTEGER NOT NULL DEFAULT 0, "
               "created_at REAL NOT NULL, PRIMARY KEY (draft_id, ver))")          # очередь c9470ab
    db.commit()
    db.close()
    core = A.Core(old, w.qpath, w.model, LossyTG(lost_send=1), w.door, quiet=w.quiet)
    have = {r[1] for r in core.db.execute("PRAGMA table_info(card_out)")}
    assert {"lost", "edit_unk"} <= have, have
    core.tick(T0 - 1000)
    assert core.card_unknown() == (0, 0)


# ═══ (д) прочие вызовы рук — как раньше ══════════════════════════════════════════════════════════════════

class RaisingTG(DS.FlakyTG):
    def ask_pause(self, number, pause_no, via=None):
        raise TimeoutError("ask_pause")

    def card_wait(self, draft_id, card_id, words, ver):
        raise TimeoutError("card_wait")


def test_other_tg_calls_still_swallow():
    lines = []
    w = DS.World(tg=RaisingTG())
    w.core.log = lines.append
    did = DS.draft_at(w)
    assert w.core._tg("ask_pause", NUM, 1) is None
    w.put(T0 + 70, kind="echo")                                # ответ с телефона: пауза, вопрос паузы падает
    w.core.tick(T0 + 71)
    assert w.paused()[0] == 1 and w.drafts()[0][1] == A.SUPERSEDED, (w.paused(), w.drafts())
    assert any("telegram ask_pause упал: TimeoutError" in ln for ln in lines), lines
    assert w.core.card_unknown() == (0, 0), "чужой вызов рук посчитан «неизвестно» карточки"
    p = DS.World(tg=RaisingTG(), pace=True)
    did = DS.draft_at(p)
    res = p.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 60)          # «уйдёт в ЧЧ:ММ» падает — срок жив
    assert res["state"] == A.SCHEDULED, res


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
