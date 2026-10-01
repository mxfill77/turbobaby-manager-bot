#!/usr/bin/env python3
"""Автоприветствие WhatsApp Business в службе wa-agent (WAGREETECHO0210, вариант В3 WAAUTOGREET0210).

Эхо с отпечатком текста из настройки службы И не позже 10 с после «первого» входящего (до него 14 суток
тишины в обе стороны) — паузы нет, черновик жив, первый вопрос не закрыт (done_upto не тронут), в истории
агента — строкой «мы · автоприветствие». Всё прочее — пауза, как раньше, и строка исхода в журнале.

Подделки: временная очередь схемой wa_webhook, временная база агента, модель/Telegram/дверь — из
test_wa_agent, модель адаптера — подделка вызова. Сети нет, модели нет. Текст приветствия выдуманный.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import hashlib
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_agent_model as WM  # noqa: E402
import wa_agent_svc as SV  # noqa: E402
import test_wa_agent as T  # noqa: E402

NUM, T0 = T.NUM, T.T0
GREET = ("Здравствуйте! Это автоответ ВЫДУМАННОГО проката: скутеры 125–160, макси 300–400, "
         "доставка по острову. Менеджер ответит в ближайшее время.")
FP = hashlib.sha256(GREET.encode("utf-8")).hexdigest()
OTHER = "Добрый день! Сейчас посмотрю."
Q1, Q2 = "ВОПРОС-ПЕРВЫЙ а большие байки есть?", "ВОПРОС-ВТОРОЙ и на какой срок минимум?"
DAY = 86400


class World(T.World):
    def __init__(self, greet=(FP[:10],), **kw):
        self.greet, self.lines = greet, []
        super().__init__(**kw)

    def new_core(self):
        return A.Core(self.dbpath, self.qpath, self.model, self.tg, self.door, log=self.lines.append,
                      greet=self.greet)

    def say(self, ts, text, kind="in", history=0, wamid=None, msg_type="text"):
        q = sqlite3.connect(self.qpath)
        cur = q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, "
                        "wamid) VALUES(?,?,?,?,?,?,?,?)",
                        (ts, NUM, msg_type, text, ts, 1 if kind == "echo" else 0, history, wamid))
        q.commit()
        q.close()
        return cur.lastrowid

    def client(self):
        db = sqlite3.connect(self.dbpath)
        row = db.execute("SELECT last_in_id, done_upto, paused FROM clients WHERE number=?", (NUM,)).fetchone()
        db.close()
        return row

    def greets(self):
        db = sqlite3.connect(self.dbpath)
        rows = db.execute("SELECT row_id, after FROM autogreet ORDER BY row_id").fetchall()
        db.close()
        return rows

    def said(self, rid):
        return [ln for ln in self.lines if ln.startswith("эхо строки %d:" % rid)]


def first_then_echo(w, delay, text):
    """Первое входящее клиента в T0, эхо через delay с; такт сразу после эха. → (id входящего, id эха)."""
    rin = w.say(T0, Q1)
    rid = w.say(T0 + delay, text, "echo", wamid="wamid.GREET%d" % delay)
    w.core.tick(T0 + delay + 1)
    return rin, rid


def assert_paused(w, rin, rid, why):
    last_in, done, paused = w.client()
    assert paused == 1 and w.tg.asks == [(NUM, 1)], ("нет паузы", w.client(), w.tg.asks)
    assert done == last_in == rin, ("первый вопрос не закрыт эхом человека", w.client())
    assert w.greets() == [], w.greets()
    said = w.said(rid)
    assert len(said) == 1 and "не автоприветствие" in said[0] and said[0].endswith("— пауза") \
        and why in said[0], said
    w.core.tick(T0 + 500)
    assert w.drafts() == [] and w.model.calls == 0, ("черновик на паузе", w.drafts())


# ═══ требования задания ═══════════════════════════════════════════════════════════════════

def test_greet_no_pause_first_question_open():
    """+ приветствие через 3 с — паузы нет, первый вопрос не закрыт: черновик на него родится и уйдёт."""
    w = World()
    rin, rid = first_then_echo(w, 3, GREET)
    last_in, done, paused = w.client()
    assert paused == 0 and w.tg.asks == [], ("автоприветствие поставило паузу", w.client(), w.tg.asks)
    assert last_in == rin and done < rin, ("первый вопрос закрыт автоприветствием", w.client())
    assert w.greets() == [(rid, 3.0)], w.greets()
    said = w.said(rid)
    assert len(said) == 1 and "автоприветствие (отпечаток совпал; 3 с после первого входящего)" in said[0] \
        and "паузы нет" in said[0], said
    w.core.tick(T0 + A.QUIET_DEFAULT)
    d = w.drafts(A.PENDING)
    assert len(d) == 1 and d[0][3] == rin and w.model.calls == 1, ("черновика на первый вопрос нет", w.drafts())
    r = w.core.press(d[0][0], 1, A.ACT_SEND, "owner")
    assert r["ok"] and r["state"] == A.SENT and len(w.door.sends) == 1, ("«Отправить» сняло черновик", r)


def test_ordinary_echo_pauses():
    """+ обычное эхо человека — пауза, как раньше."""
    w = World()
    rin, rid = first_then_echo(w, 40, OTHER)
    assert_paused(w, rin, rid, "отпечаток не совпал; первого входящего за 10 с до эха нет")


def test_greet_text_after_30s_pauses():
    """− текст приветствия через 30 с после первого входящего — пауза."""
    w = World()
    rin, rid = first_then_echo(w, 30, GREET)
    assert_paused(w, rin, rid, "отпечаток совпал; первого входящего за 10 с до эха нет")


def test_other_text_within_10s_pauses():
    """− другой текст за 3 с после первого входящего — пауза; журнал видит «сменили текст приветствия»."""
    w = World()
    rin, rid = first_then_echo(w, 3, OTHER)
    assert_paused(w, rin, rid, "отпечаток не совпал; 3 с после первого входящего")


def test_no_setting_pauses():
    """− настройки нет — приветствие через 3 с ставит паузу, как до правки."""
    w = World(greet=())
    rin, rid = first_then_echo(w, 3, GREET)
    assert_paused(w, rin, rid, "отпечатка приветствия в настройке нет; 3 с после первого входящего")


# ═══ правила признака ══════════════════════════════════════════════════════════════════════

def test_not_first_inbound_pauses():
    """Переписка за 14 суток до входящего (история тоже) — входящее не «первое»: пауза."""
    w = World()
    w.say(T0 - 5 * DAY, "старое", history=1)
    rin, rid = first_then_echo(w, 3, GREET)
    assert_paused(w, rin, rid, "отпечаток совпал; первого входящего за 10 с до эха нет")


def test_silence_over_14_days_is_first():
    """Переписка старше 14 суток — входящее «первое»: паузы нет."""
    w = World()
    w.say(T0 - 15 * DAY, "давнее", "echo", history=1)
    _rin, rid = first_then_echo(w, 3, GREET)
    assert w.client()[2] == 0 and w.greets() == [(rid, 3.0)], (w.client(), w.greets())


def test_receipt_before_keeps_first():
    """Квитанция за 14 суток до входящего — не переписка: входящее остаётся «первым»."""
    w = World()
    w.say(T0 - DAY, "delivered", "echo", msg_type="status")
    _rin, rid = first_then_echo(w, 3, GREET)
    assert w.client()[2] == 0 and w.greets() == [(rid, 3.0)], (w.client(), w.greets())


def test_two_messages_then_greet():
    """Клиент пишет двумя сообщениями подряд, приветствие — через 3 с после первого: паузы нет, оба открыты."""
    w = World()
    w.say(T0, Q1)
    rin2 = w.say(T0 + 1, Q2)
    rid = w.say(T0 + 3, GREET, "echo", wamid="wamid.G")
    w.core.tick(T0 + 4)
    assert w.client() == (rin2, 0, 0) and w.greets() == [(rid, 3.0)], (w.client(), w.greets())


def test_our_echo_is_not_first_inbound():
    """«Первым» бывает только входящее клиента: наше эхо первым и текст приветствия за ним — пауза."""
    w = World()
    r1 = w.say(T0, OTHER, "echo", wamid="wamid.H")
    rid = w.say(T0 + 3, GREET, "echo", wamid="wamid.G")
    w.core.tick(T0 + 4)
    assert w.greets() == [] and w.client()[2] == 1, (w.greets(), w.client())
    assert w.said(r1) and "не автоприветствие" in w.said(rid)[0], w.said(rid)


def test_full_sha256_and_prefix_match():
    for greet in ((FP,), (FP[:10],), ("0" * 10, FP[:16])):
        w = World(greet=greet)
        first_then_echo(w, 3, GREET)
        assert w.client()[2] == 0 and len(w.greets()) == 1, (greet, w.client())


def test_greet_survives_restart():
    """Рестарт после приветствия: признание лежит в базе — черновик на первый вопрос родится."""
    w = World()
    rin, _rid = first_then_echo(w, 3, GREET)
    w.core = w.new_core()
    w.core.tick(T0 + A.QUIET_DEFAULT)
    assert [d[3] for d in w.drafts(A.PENDING)] == [rin], w.drafts()


def test_setting_parse():
    assert A.greet_fps(FP)[0] == (FP,)
    assert A.greet_fps(" %s " % FP[:10].upper())[0] == (FP[:10],)
    assert A.greet_fps("%s,%s" % (FP[:10], "a" * 64))[0] == (FP[:10], "a" * 64)
    for bad in ("", None, FP[:9], "z" * 10, FP + "0", "%s,zz" % FP, ","):
        fps, words = A.greet_fps(bad)
        assert fps == () and "пауз" in words, (bad, fps, words)


def test_svc_reads_setting():
    """Служба берёт отпечаток из WA_AGENT_GREET_SHA256 и пишет его исход строкой; нет — признака нет."""
    for environ, want, word in (({SV.F_GREET: FP[:10]}, (FP[:10],), "отпечаток " + FP[:10]),
                                ({}, (), "настройки нет — любое эхо ставит паузу"),
                                ({SV.F_GREET: "не-отпечаток"}, (), "настройка битая")):
        w = World()
        lines = []
        env = {"queue_db": w.qpath, "agent_db": w.dbpath + ".svc", "mirror_db": "", "tg_token": "",
               "show_chat": ""}
        core, _tg, _f, _words = SV.build(env, environ=environ, clock=lambda: T0, line=lines.append)
        assert core.greet == want, (environ, core.greet)
        said = [ln for ln in lines if ln.startswith("автоприветствие (WA_AGENT_GREET_SHA256): ")]
        assert len(said) == 1 and word in said[0], (environ, lines)


def test_agent_history_line_and_first_question_now():
    """История агента: приветствие — строкой «мы · автоприветствие», текста приветствия нет; первый
    вопрос — в «КЛИЕНТ СЕЙЧАС» и когда приветствие новее черновика, и когда клиент написал после него."""
    w = World()
    rin, _rid = first_then_echo(w, 3, GREET)
    ad = WM.ModelAdapter(w.qpath, lambda s, u: ("", {}), agent_db=w.dbpath, clock=lambda: T0 + 100)
    _s, user, _i = ad.build(NUM, rin, now=T0 + 100)
    hist, now = user.split("КЛИЕНТ СЕЙЧАС")
    assert hist.count("· мы · автоприветствие") == 1 and GREET[:20] not in user, hist[-400:]
    assert Q1 in now, now
    rin2 = w.say(T0 + 20, Q2)
    w.core.tick(T0 + 21)
    _s, user, _i = ad.build(NUM, rin2, now=T0 + 100)
    hist, now = user.split("КЛИЕНТ СЕЙЧАС")
    assert hist.count("· мы · автоприветствие") == 1 and GREET[:20] not in user, hist[-400:]
    assert Q1 in now and Q2 in now, now
    assert hist.index(Q1) < hist.index("автоприветствие") < hist.index(Q2), hist[-400:]
    items, _missing = ad._history(NUM, rin2)
    auto = [it for it in items if it.get("auto")]
    assert len(auto) == 1 and auto[0]["text"] == "автоприветствие" and auto[0]["who"] == "мы", auto
    assert not any(GREET[:20] in (it["text"] or "") for it in items), "текст приветствия в истории агента"


def test_journal_no_text_no_number():
    w = World()
    first_then_echo(w, 3, GREET)
    log = "\n".join(w.lines)
    assert GREET[:20] not in log and Q1 not in log and NUM not in log, log
    assert FP[10:20] not in log, "в журнале больше 10 знаков отпечатка"


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
