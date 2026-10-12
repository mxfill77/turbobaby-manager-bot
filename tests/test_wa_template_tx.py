#!/usr/bin/env python3
"""INTEG0710 Д5 (Б3г): исход шаблона в `tpl_out` и строка `outbox` — ОДНОЙ транзакцией, как исход части у Б3в.

Сбой между записями — исключение посреди (диск, занятая база) или обрыв процесса — после рестарта не даёт ни второй
отправки шаблона, ни половины («ушёл» в tpl_out без строки outbox: wamid потерян для эха, истории агента и сторожа).
Разовый сбой — ни дубля, ни потери: вторая атомарная попытка кладёт обе записи. Устойчивый сбой — откат, tpl_out ждёт
(sending), рестарт говорит «неизвестно», второго шаблона нет, журнал и карточка называют исход двери.

Каркас (World, TplDoor, FakeHttp) — готовый из набора Б3г `test_wa_template_card`. Сбой базы подсаживается обёрткой
соединения ядра (`FaultDB`): выбранная запись бросает `sqlite3.OperationalError`. Обрыв процесса — `Crash`
(BaseException: его не ловят ни ядро, ни руки Telegram) + закрытие соединения без COMMIT (незакоммиченное уходит, как
при смерти процесса) + новое ядро на той же базе. На дереве до правки (2e586fa) новые проверки красные, проверки
«как раньше» — зелёные. Сети нет: ловушка urlopen ставится каркасом."""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ["PRETOOL_NOPUSH"] = "1"

import test_wa_template_card as B  # noqa: E402  (каркас Б3г; его main() не зовётся)

A = B.A
NUM, T0, TPL_RU = B.NUM, B.T0, B.TPL_RU
W1 = "wamid.TPL1"                                 # wamid, который называет дверь-подделка каркаса (TplDoor)
NOT_APPROVED = {"outcome": "not_sent", "reason": "Meta не одобрила шаблон reply_request (ru): статус pending — не "
                "отправлено", "wamid": None, "approval": "not_approved"}


class Crash(BaseException):
    """Обрыв процесса посреди записи: не Exception — его не ловит ни ядро, ни руки (`Tg.handle` ловит Exception)."""


def _sql(sql):
    return " ".join(str(sql).split()).upper()


def is_outbox(sql):
    return _sql(sql).startswith("INSERT OR IGNORE INTO OUTBOX")


def is_outcome(sql):
    """Запись исхода двери в tpl_out (не захват sending и не старт): SET state, reason, wamid, body."""
    return _sql(sql).startswith("UPDATE TPL_OUT SET STATE=?, REASON=?, WAMID=?, BODY=?")


def is_commit(sql):
    return _sql(sql) == "COMMIT"


def is_begin(sql):
    return _sql(sql).startswith("BEGIN")


class FaultDB:
    """Соединение ядра с подсаженным сбоем: запись под `match` бросает `left` раз (исключение `exc`, по умолчанию
    sqlite3.OperationalError «disk I/O error»); after=True — запись сперва исполняется по-настоящему, потом бросает
    (легло, а ответ базы потерян). Остальное — в настоящее соединение. `log` — исполненное по порядку."""

    def __init__(self, real, match=None, left=0, exc=None, after=False):
        self.real, self.match, self.left, self.exc, self.after = real, match, left, exc, after
        self.log, self.fired = [], 0

    def execute(self, sql, params=()):
        self.log.append(_sql(sql))
        if self.left > 0 and self.match is not None and self.match(sql):
            self.left -= 1
            self.fired += 1
            if self.after:
                self.real.execute(sql, params)
            if self.exc is not None:
                raise self.exc("обрыв процесса (подделка теста)")
            raise sqlite3.OperationalError("disk I/O error (подделка теста)")
        return self.real.execute(sql, params)

    def executescript(self, script):
        return self.real.executescript(script)

    def __getattr__(self, name):
        return getattr(self.real, name)


def armed(match=None, left=0, exc=None, after=False, res=None, text=B.RU):
    """Мир Б3г: черновик при закрытом окне (карточка с «📨»), затем соединение ядра и рук — с подсаженным сбоем."""
    w = B.World(text=text)
    if res is not None:
        w.door.tpl_res = dict(res)
    w.draft()
    f = FaultDB(w.core.db, match, left, exc, after)
    w.core.db = w.tg.db = f
    return w, f


def restart(w):
    """Обрыв процесса и новый старт службы: соединение закрыто без COMMIT (незакоммиченное уходит), новое ядро на той
    же базе — `_startup` (sending → unsure)."""
    db = w.core.db.real if isinstance(w.core.db, FaultDB) else w.core.db
    db.close()
    w.new_core()


def outbox(w):
    return w.core.db.execute("SELECT wamid, number, text, via FROM outbox ORDER BY wamid").fetchall()


def whole(w, did=1):
    """Ни половины: tpl_out назвал «ушёл» с wamid ⇔ этот wamid (и только он) в outbox видом «шаблон»; иначе шаблона в
    outbox нет вовсе."""
    row = w.core.db.execute("SELECT state, wamid FROM tpl_out WHERE draft_id=?", (did,)).fetchone()
    got = w.core.db.execute("SELECT wamid FROM outbox WHERE via=?", (A.VIA_TEMPLATE,)).fetchall()
    if row and row[0] == A.SENT:
        return bool(row[1]) and got == [(row[1],)]
    return got == []


def last_answer(w):
    got = w.answers()
    return got[-1] if got else ""


# ═══ одной транзакцией ═══════════════════════════════════════════════════════════════════

def test_outcome_and_outbox_inside_one_transaction():
    """Исход двери в tpl_out и строка outbox — между ОДНИМИ BEGIN IMMEDIATE и COMMIT: внутри нет ни COMMIT, ни
    ROLLBACK, ни нового BEGIN. До правки BEGIN нет вовсе — каждая запись была своей автокоммит-транзакцией."""
    w, f = armed()
    w.press("wa:tpl:1:1")
    log = f.log
    ups = [i for i, s in enumerate(log) if is_outcome(s)]
    ins = [i for i, s in enumerate(log) if is_outbox(s)]
    assert len(ups) == 1 and len(ins) == 1, (ups, ins)
    begins = [i for i in range(ups[0]) if log[i].startswith("BEGIN")]
    assert begins and log[begins[-1]] == "BEGIN IMMEDIATE", ("перед записью исхода нет BEGIN IMMEDIATE", log[-12:])
    ends = [i for i in range(ins[0] + 1, len(log)) if log[i] in ("COMMIT", "ROLLBACK")]
    assert ends and log[ends[0]] == "COMMIT", ("после строки outbox нет COMMIT", log[-12:])
    b, e = begins[-1], ends[0]
    inside = log[b + 1:e]
    assert not [s for s in inside if s.startswith("BEGIN") or s in ("COMMIT", "ROLLBACK")], inside
    assert b < ups[0] < e and b < ins[0] < e, (b, ups, ins, e)


# ═══ сбой между записями ════════════════════════════════════════════════════════════════

def test_fault_once_between_writes_no_dup_no_loss():
    """Разовый сбой строки outbox после записи исхода (в той же транзакции): откат и вторая атомарная попытка — легли
    обе. После рестарта: шаблон ушёл ОДИН раз, wamid в tpl_out и в outbox, эхо шаблона «наше» (паузы нет), второе
    нажатие — «уже ушёл». До правки исход лёг автокоммитом, строка outbox — нет: половина, wamid потерян."""
    w, f = armed(is_outbox, left=1)
    w.press("wa:tpl:1:1")
    assert f.fired == 1, "сбой не подсажен"
    assert outbox(w) == [(W1, NUM, TPL_RU, A.VIA_TEMPLATE)], ("строка outbox не легла", outbox(w), w.tpl_row())
    assert w.tpl_row()[:2] == (A.SENT, W1) and whole(w), w.tpl_row()
    assert last_answer(w) == "шаблон ушёл (reply_request, ru) — ждём ответа клиента", w.answers()
    restart(w)
    assert w.tpl_row()[:2] == (A.SENT, W1) and whole(w), (w.tpl_row(), outbox(w))
    assert w.core._our_wamid(W1), "эхо шаблона после рестарта не узнаётся"
    w.press("wa:tpl:1:1")
    assert len(w.door.tpls) == 1 and "уже ушёл" in last_answer(w), (w.door.tpls, last_answer(w))
    w.put(T0 + 200, "echo", wamid=W1)
    w.core.tick(T0 + 300)
    paused = w.core.db.execute("SELECT paused FROM clients WHERE number=?", (NUM,)).fetchone()[0]
    assert paused == 0 and w.state()[0] == A.PENDING, (paused, w.state())


def test_fault_always_no_half_no_dup():
    """Устойчивый сбой строки outbox: обе попытки откачены — половины нет (tpl_out ждёт sending без wamid, outbox
    пуст). Второе нажатие до рестарта — «уходит», после рестарта — «исход неизвестен»; второго шаблона нет нигде.
    Ответ на кнопку и карточка называют исход двери и то, что в базу он не записан. До правки: tpl_out «ушёл»,
    outbox пуст, на кнопку ответа нет."""
    w, f = armed(is_outbox, left=99)
    w.press("wa:tpl:1:1")
    assert f.fired == 2, "попыток записи outbox %d (нужно 2: первая и одна повторная)" % f.fired
    row = w.tpl_row()
    assert row[0] == A.SENDING and row[1] is None and outbox(w) == [] and whole(w), (row, outbox(w))
    ans = last_answer(w)
    assert ans.startswith("шаблон ушёл (reply_request, ru)") and "не записано" in ans, ans
    ed = w.http.of("editMessageText")[-1]
    assert "ушёл" in ed["text"] and "не записано" in ed["text"], ed["text"][-200:]
    w.press("wa:tpl:1:1")
    assert len(w.door.tpls) == 1 and "уходит" in last_answer(w), (w.door.tpls, last_answer(w))
    restart(w)
    row = w.tpl_row()
    assert row[0] == A.UNSURE and row[1] is None and outbox(w) == [] and whole(w), (row, outbox(w))
    w.press("wa:tpl:1:1")
    tpl_ans = last_answer(w)
    w.press("wa:send:1:1")
    assert len(w.door.tpls) == 1 and w.door.sends == [], (w.door.tpls, w.door.sends)
    assert "исход неизвестен" in tpl_ans, tpl_ans


def test_crash_between_writes_no_half_no_dup():
    """Обрыв ПРОЦЕССА ровно между записью исхода и строкой outbox: незакоммиченное уходит, старт — sending →
    «неизвестно»; половины нет, второго шаблона нет. До правки исход уже лёг автокоммитом: после старта tpl_out
    «ушёл», а wamid в outbox нет."""
    w, f = armed(is_outbox, left=1, exc=Crash)
    try:
        w.press("wa:tpl:1:1")
    except Crash:
        pass
    else:
        raise AssertionError("обрыв не случился — подсадка не сработала")
    restart(w)
    row = w.tpl_row()
    assert whole(w), "половина после обрыва: tpl_out %r, outbox %r" % (row, outbox(w))
    assert row[0] == A.UNSURE and row[1] is None, row
    assert len(w.door.tpls) == 1, w.door.tpls
    w.press("wa:tpl:1:1")
    assert len(w.door.tpls) == 1 and "исход неизвестен" in last_answer(w), (w.door.tpls, last_answer(w))


def test_commit_fails_once_retried():
    """COMMIT не прошёл один раз (база занята дольше busy-таймаута — класс R21 у Б3в): откат и вторая атомарная
    попытка, легли обе, шаблон один. До правки COMMIT не исполнялся вовсе — записи шли без транзакции."""
    w, f = armed(is_commit, left=1)
    w.press("wa:tpl:1:1")
    assert f.fired == 1, "COMMIT не исполнялся — исход и outbox шли без транзакции"
    assert w.tpl_row()[:2] == (A.SENT, W1) and outbox(w) == [(W1, NUM, TPL_RU, A.VIA_TEMPLATE)], (
        w.tpl_row(), outbox(w))
    ans = last_answer(w)
    assert len(w.door.tpls) == 1 and ans.startswith("шаблон ушёл") and "не записано" not in ans, (w.door.tpls, ans)
    restart(w)
    assert whole(w) and w.core._our_wamid(W1), (w.tpl_row(), outbox(w))


def test_commit_landed_answer_lost_retry_idempotent():
    """COMMIT лёг, а ответ базы потерян (исключение ПОСЛЕ записи): повтор безопасен — исход пишется только из
    sending, outbox — INSERT OR IGNORE; в базе ровно одна строка outbox и исход «ушёл», шаблон один, слов о сбое нет."""
    w, f = armed(is_commit, left=1, after=True)
    w.press("wa:tpl:1:1")
    assert f.fired == 1, "COMMIT не исполнялся"
    assert w.tpl_row()[:2] == (A.SENT, W1) and outbox(w) == [(W1, NUM, TPL_RU, A.VIA_TEMPLATE)], (
        w.tpl_row(), outbox(w))
    ans = last_answer(w)
    assert len(w.door.tpls) == 1 and ans.startswith("шаблон ушёл") and "не записано" not in ans, (w.door.tpls, ans)


def test_begin_busy_once_retried():
    """BEGIN IMMEDIATE не открылся один раз (базу держит другой писатель): вторая попытка — обе записи одной
    транзакцией, шаблон один. Записи без транзакции нет и здесь."""
    w, f = armed(is_begin, left=1)
    w.press("wa:tpl:1:1")
    assert f.fired == 1, "BEGIN не исполнялся"
    assert w.tpl_row()[:2] == (A.SENT, W1) and outbox(w) == [(W1, NUM, TPL_RU, A.VIA_TEMPLATE)], (
        w.tpl_row(), outbox(w))
    assert f.log.count("BEGIN IMMEDIATE") == 2 and f.log.count("COMMIT") == 1, f.log[-10:]
    assert len(w.door.tpls) == 1, w.door.tpls


def test_not_sent_outcome_fault_once_kept():
    """Исход «не отправлено» (Meta не одобрила) при разовом сбое записи исхода: вторая попытка его кладёт — можно ещё
    раз, и когда Meta одобрила, шаблон уходит. До правки исход терялся: tpl_out оставался sending, второе нажатие —
    «уходит», после рестарта — «неизвестно» навсегда."""
    w, f = armed(is_outcome, left=1, res=NOT_APPROVED)
    w.press("wa:tpl:1:1")
    assert f.fired == 1, "сбой не подсажен"
    assert w.tpl_row()[0] == A.NOT_SENT and outbox(w) == [], (w.tpl_row(), outbox(w))
    assert last_answer(w).startswith("шаблон не отправлен: Meta не одобрила"), last_answer(w)
    w.door.tpl_res = {"outcome": "sent", "reason": "принято", "wamid": "wamid.TPL2", "text": TPL_RU}
    w.press("wa:tpl:1:1")
    assert len(w.door.tpls) == 2 and w.tpl_row()[:3] == (A.SENT, "wamid.TPL2", 2), (w.door.tpls, w.tpl_row())
    assert outbox(w) == [("wamid.TPL2", NUM, TPL_RU, A.VIA_TEMPLATE)] and whole(w), outbox(w)


def test_journal_names_outcome_when_not_saved():
    """Устойчивый сбой: журнал службы ОДНОЙ строкой называет исход двери и wamid (номера и текста клиента в ней нет) —
    исход не теряется молча. До правки такой строки нет."""
    w, f = armed(is_outbox, left=99)
    w.press("wa:tpl:1:1")
    lines = [ln for ln in w.lines if "НЕ легло" in ln]
    assert len(lines) == 1, w.lines[-6:]
    ln = lines[0]
    assert W1 in ln and "→ sent" in ln and "черновик 1" in ln and "sending" in ln, ln
    assert NUM not in ln and TPL_RU not in ln, ln


# ═══ чужая транзакция ════════════════════════════════════════════════════════════════════

def test_outer_transaction_not_closed_by_core():
    """Транзакция, открытая на соединении НЕ ядром, ядром не закрывается и не откатывается: исход и outbox ложатся в
    неё, решает владелец (его откат снимает и их). Закрыть чужую — значило бы закоммитить или откатить чужие записи."""
    w = B.World()
    w.draft()
    w.core.db.execute("BEGIN IMMEDIATE")
    w.press("wa:tpl:1:1")
    assert w.core.db.in_transaction, "ядро закрыло чужую транзакцию"
    assert w.tpl_row()[:2] == (A.SENT, W1) and outbox(w) == [(W1, NUM, TPL_RU, A.VIA_TEMPLATE)], (
        w.tpl_row(), outbox(w))
    w.core.db.execute("ROLLBACK")
    assert w.tpl_row() is None and outbox(w) == [], "откат владельца не снял записи ядра"


# ═══ как раньше ══════════════════════════════════════════════════════════════════════════

def test_as_before_sent_end_state():
    """Без сбоя — ровно прежнее: одна отправка, sending ДО двери, tpl_out «ушёл» с wamid и текстом, одна строка outbox,
    ответ и правка карточки прежними словами, в журнале прежняя строка исхода и ни одной строки об откате."""
    w, f = armed()
    w.press("wa:tpl:1:1")
    assert w.door.tpls == [(NUM, "reply_request", "ru", ["байка"])] and w.door.seen == [[("sending",)]], (
        w.door.tpls, w.door.seen)
    assert w.tpl_row() == (A.SENT, W1, 1, "reply_request", "ru"), w.tpl_row()
    assert w.core.db.execute("SELECT body FROM tpl_out WHERE draft_id=1").fetchone()[0] == TPL_RU
    assert outbox(w) == [(W1, NUM, TPL_RU, A.VIA_TEMPLATE)], outbox(w)
    assert w.answers() == ["шаблон ушёл (reply_request, ru) — ждём ответа клиента"], w.answers()
    ed = w.http.of("editMessageText")[-1]
    assert "📨 шаблон reply_request (ru) ушёл: Дарья (id 501), " in ed["text"] and TPL_RU in ed["text"], (
        ed["text"][-300:])
    assert "не записано" not in ed["text"], ed["text"][-200:]
    assert [ln for ln in w.lines if ln.startswith("черновик 1: шаблон reply_request (ru) → sent")], w.lines[-4:]
    assert not [ln for ln in w.lines if "не легл" in ln.lower()], w.lines[-6:]
    assert w.state() == (A.PENDING, 1), w.state()


def test_as_before_not_sent_and_unknown():
    """Без сбоя: «не отправлено» и «неизвестно» — прежние состояния, outbox пуст, слова прежние."""
    w, f = armed(res=NOT_APPROVED)
    w.press("wa:tpl:1:1")
    assert w.tpl_row()[0] == A.NOT_SENT and outbox(w) == [], (w.tpl_row(), outbox(w))
    ans = last_answer(w)
    assert ans.startswith("шаблон не отправлен: Meta не одобрила") and "не записано" not in ans, ans
    w, f = armed(res={"outcome": "unknown", "reason": "транспорт молчит", "wamid": None})
    w.press("wa:tpl:1:1")
    assert w.tpl_row()[0] == A.UNSURE and outbox(w) == [], (w.tpl_row(), outbox(w))
    assert last_answer(w) == "шаблон: " + A.W_UNSURE, last_answer(w)


def test_as_before_flag_off_and_text_send_no_new_transaction():
    """Д5 касается ТОЛЬКО записи исхода шаблона: WA_AGENT_TEMPLATES выкл — кнопка отказывает словами, BEGIN не
    исполняется; обычная «✅ Отправить» при открытом окне — прежний путь без новой транзакции."""
    w = B.World(templates=False)
    w.draft()
    f = FaultDB(w.core.db)
    w.core.db = w.tg.db = f
    w.press("wa:tpl:1:1")
    assert w.answers() == [A.TPL_OFF_WORDS] and w.door.tpls == [], (w.answers(), w.door.tpls)
    w2 = B.World()
    w2.door.win = {"state": "open", "age": 3600}
    w2.draft()
    f2 = FaultDB(w2.core.db)
    w2.core.db = w2.tg.db = f2
    w2.press("wa:send:1:1")
    assert w2.door.sends == [(NUM, B.RU)] and w2.state()[0] == A.SENT, (w2.door.sends, w2.state())
    tx = [s for s in f.log + f2.log if s.startswith("BEGIN") or s in ("COMMIT", "ROLLBACK")]
    assert tx == [], tx


def main():
    tests = [(n, fn) for n, fn in sorted(globals().items()) if n.startswith("test_") and callable(fn)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:500])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
