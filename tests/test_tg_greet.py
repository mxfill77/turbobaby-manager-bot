#!/usr/bin/env python3
"""Автоприветствие Telegram Business не закрывает первый вопрос клиента (TGGREET1310).

Живой случай 12.10.2026 17:27:24Z: клиент пишет аккаунту в личку, через 0 с Telegram Business шлёт от аккаунта
приветствие-картинку; лента ПК кладёт её исходящим рядом, в очереди TG это эхо строки 2. Ядро TG собиралось с
greet=() — «отпечатка приветствия в настройке нет», эхо читалось ответом человека: done_upto=MAX(done_upto,
last_in_id), вопрос закрыт, черновика и карточки нет (журнал агента 17:30:13). Текста у приветствия нет, отпечатка
быть не может — признак у TG только время: эхо ≤ GREET_SEC после «первого» входящего, перед которым
TG_GREET_SILENCE (7 сут — меньший выбор Telegram Business) ни одной строки. Ручка WA_AGENT_TG_GREET («0» — как было).

Всё на подделках каркаса `test_tg_core` (World, FakeHttp, FakeModel): временные базы, сети нет, модель — подделка."""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import test_tg_core as K  # noqa: E402
import wa_agent as A  # noqa: E402
import wa_agent_svc as S  # noqa: E402

T0 = K.T0
DAY = 86400


def row(w, number, ts, msg_type="text", echo=0):
    q = sqlite3.connect(w.env["tg_queue_db"])
    rid = q.execute("INSERT INTO wa_inbox(ts_queued, channel, from_number, msg_type, text, ts_msg, echo, history) "
                    "VALUES(?,?,?,?,?,?,?,0)", (ts, "tg", number, msg_type, None if msg_type == "image" else "x", ts,
                                                echo)).lastrowid
    q.commit()
    q.close()
    return rid


def tg_state(w):
    db = sqlite3.connect(w.env["tg_agent_db"])
    try:
        cl = db.execute("SELECT last_in_id, done_upto, paused FROM clients WHERE number=?", (K.TGNUM,)).fetchone()
        drafts = db.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
        greeted = [r[0] for r in db.execute("SELECT row_id FROM autogreet ORDER BY row_id")]
    finally:
        db.close()
    return cl, drafts, greeted


def world(environ=None, history=()):
    """Мир с каналом TG: первый старт ядра TG, затем ряды истории (до «первого» входящего)."""
    w = K.World(environ or K.TG_ON, tg=True)
    w.tgc.tick(T0 - 30 * DAY)                    # первый старт: курсор на MAX(id) пустой очереди
    for ts, kind, echo in history:
        row(w, K.TGNUM, ts, kind, echo)
    return w


def live_case(w, gap=0):
    """Живой случай: входящее в T0-200, приветствие-картинка через gap с. → (id входящего, id эха)."""
    rin = row(w, K.TGNUM, T0 - 200)
    recho = row(w, K.TGNUM, T0 - 200 + gap, "image", 1)
    w.tgc.tick(T0)
    return rin, recho


def test_live_case_greeting_keeps_question_open():
    """Живой случай: эхо-картинка через 0 с — автоприветствие, вопрос открыт, черновик и карточка есть."""
    w = world()
    rin, recho = live_case(w)
    cl, drafts, greeted = tg_state(w)
    assert greeted == [recho], greeted
    assert cl[0] == rin and cl[1] < rin and cl[2] == 0, cl          # done_upto не тронут, паузы нет
    assert drafts == 1, drafts
    assert w.tg_model.calls == [K.TGNUM], w.tg_model.calls
    tg_cards = w.cards("tg")
    assert len(tg_cards) == 1 and "TG · " + K.TGNUM in tg_cards[0][0]["text"], tg_cards
    assert any("автоприветствие (признак только по времени; 0 с после первого входящего)" in l for l in w.lines), \
        [l for l in w.lines if "эхо строки" in l]
    assert w.sends == [] and w.media == [], (w.sends, w.media)    # дверь WhatsApp не звана


def test_late_echo_still_closes():
    """Эхо через 11 с (> GREET_SEC) — ответ человека, как было: вопрос закрыт, черновика нет."""
    w = world()
    rin, _ = live_case(w, gap=A.GREET_SEC + 1)
    cl, drafts, greeted = tg_state(w)
    assert greeted == [] and cl[1] == rin and drafts == 0, (cl, drafts, greeted)


def test_not_first_within_silence_closes():
    """Переписка 3 сут назад — входящее не «первое»: эхо через 0 с закрывает вопрос, как было."""
    w = world(history=[(T0 - 3 * DAY, "text", 0)])
    rin, _ = live_case(w)
    cl, drafts, greeted = tg_state(w)
    assert greeted == [] and cl[1] == rin and drafts == 0, (cl, drafts, greeted)


def test_silence_is_seven_days_for_tg():
    """Переписка 8 сут назад (> 7 сут Telegram Business, < 14 сут WA) — у TG «первое»: приветствие узнано."""
    w = world(history=[(T0 - 8 * DAY, "text", 0)])
    _, recho = live_case(w)
    cl, drafts, greeted = tg_state(w)
    assert greeted == [recho] and drafts == 1, (cl, drafts, greeted)
    assert w.tgc.greet_silence == S.TG_GREET_SILENCE == 7 * DAY
    assert w.core.greet_silence == A.GREET_SILENCE == 14 * DAY      # ядро WhatsApp — прежние 14 сут


def test_knob_off_is_old_behaviour():
    """WA_AGENT_TG_GREET=0 — как до правки: эхо закрывает, слова старта называют выключение."""
    w = world(dict(K.TG_ON, WA_AGENT_TG_GREET="0"))
    rin, _ = live_case(w)
    cl, drafts, greeted = tg_state(w)
    assert greeted == [] and cl[1] == rin and drafts == 0, (cl, drafts, greeted)
    assert w.tgc.greet == ()
    assert "приветствие TG: выкл" in w.words[S.F_TG], w.words[S.F_TG]
    assert any("отпечатка приветствия в настройке нет" in l for l in w.lines)


def test_start_words_name_the_rule():
    w = world()
    assert w.tgc.greet == (A.GREET_ANY,)
    assert "приветствие TG: эхо ≤ 10 с после первого входящего (до него 7 сут тишины)" in w.words[S.F_TG], \
        w.words[S.F_TG]


def test_whatsapp_untouched():
    """WhatsApp: «*» в настройке отпечатка — битая настройка (признака нет), а не «любой текст»; greet_hit по
    отпечаткам — прежний; ядро WA собрано с прежними отпечатками и тишиной."""
    fps, words = A.greet_fps("*")
    assert fps == () and "битая" in words, (fps, words)
    fp = "ab" * 32
    assert not A.greet_hit("", (fp,)) and not A.greet_hit(None, (fp,)) and not A.greet_hit("x", ())
    assert A.greet_hit("", (A.GREET_ANY,)) and A.greet_hit(None, (A.GREET_ANY,))
    w = world()
    assert w.core.greet == () and A.GREET_ANY not in w.core.greet


def test_wa_media_echo_still_closes():
    """Ядро WhatsApp без настройки: эхо-картинка через 0 с после первого входящего закрывает вопрос, как было."""
    w = world()
    w.core.tick(T0 - 30 * DAY)
    q = sqlite3.connect(w.env["queue_db"])
    q.execute("INSERT INTO wa_inbox(ts_queued, channel, from_number, msg_type, text, ts_msg, echo, history) "
              "VALUES(?,?,?,?,?,?,0,0)", (T0 - 200, "wa", K.NUM, "text", "x", T0 - 200))
    q.execute("INSERT INTO wa_inbox(ts_queued, channel, from_number, msg_type, text, ts_msg, echo, history) "
              "VALUES(?,?,?,?,?,?,1,0)", (T0 - 200, "wa", K.NUM, "image", None, T0 - 200))
    q.commit()
    q.close()
    w.core.tick(T0)
    db = sqlite3.connect(w.env["agent_db"])
    cl = db.execute("SELECT last_in_id, done_upto FROM clients WHERE number=?", (K.NUM,)).fetchone()
    greeted = db.execute("SELECT COUNT(*) FROM autogreet").fetchone()[0]
    db.close()
    assert greeted == 0 and cl[1] == cl[0], (cl, greeted)


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            n += 1
            print("ok", name)
    print("PASS %d/%d" % (n, n))
