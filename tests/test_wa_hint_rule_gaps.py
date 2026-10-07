#!/usr/bin/env python3
"""Пояснение → правило (NIGHT0710-B2): проверки агента мутантов поверх tests/test_wa_hint_rule.py.

Каждый случай закрывает мутанта, который пережил набор строителя (id мутанта — в докстроке случая; мутанты —
learn_aux/mut/mutants.json). Формат набора дерева: PASS/FAIL/ИТОГ, код 1 при любом FAIL. Всё на подделках набора
test_wa_hint_rule (его шапка подменяет spend_ledger до импорта: fcntl на ПК). Сети нет, модель не зовётся."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import test_wa_hint_rule as H  # noqa: E402  (подмена spend_ledger — в шапке набора)
import wa_agent as A  # noqa: E402
import wa_agent_tg as G  # noqa: E402

OWNER_WHO = "Филипп (id 504608015)"
LIST_AT = H.DAY0 + 21 * 3600 + 5 * 60                               # 21:05 по Пхукету в день T0
MONEY_NEW = "Добрый день! Для брони нужна предоплата 30%, остальное — при получении."


def _add_text_lesson(w, n, state, was, now):
    """Урок правкой текстом (WAAGENTLESSON0210): вид NULL, было/стало."""
    w.core.db.execute("INSERT INTO lessons(state, author, author_id, ts, draft_id, ver_from, ver_to, was_text, "
                      "now_text) VALUES(?,?,?,?,?,?,?,?,?)",
                      (state, "Дарья (id 501)", 501, H.T0, 200 + n, 1, 2, was, now))


def _state(w, lid):
    return w.core.db.execute("SELECT state FROM lessons WHERE id=?", (lid,)).fetchone()[0]


# ═══ номер, сообщение правила, проигравшее нажатие ═══════════════════════════════════════════════

def test_press_result_carries_rule_number():
    """X11: ядро возвращает номер правила полем ответа (не только словами)."""
    w = H.started()
    w.explain()
    res = w.core.press(1, 2, A.ACT_SEND, OWNER_WHO, who_id=504608015)
    assert res.get("rule") == 1 == w.rules()[0][0], (res, w.rules())
    w = H.started()
    w.explain()
    res = w.core.press(1, 2, A.ACT_SEND, "Дарья (id 501)", who_id=501)
    assert res.get("rule") == 1 and w.rules()[0][1] == A.LESSON_CANDIDATE, (res, w.rules())


def test_staff_candidate_gets_no_rule_message():
    """X13: «Отправить» сотрудника — кандидат идёт в суточный список; сообщения правила с кнопками в группе нет."""
    w = H.started()
    w.explain()
    before = len(w.sent())
    w.send(H.STAFF)
    after = w.sent()[before:]
    assert not [p for p in after if "Правило №" in p["text"]], [p["text"][:60] for p in after]
    assert not [b for p in after for b in H.buttons(p) if b.startswith(("wa:rule:", "wa:unrule:", "wa:lno:"))]


def test_losing_press_makes_no_rule():
    """X29: «Не нужно» сотрудника выиграло — «Отправить» владельца на той же версии проиграло захват: правила нет."""
    w = H.started()
    w.explain()
    assert w.press("wa:no:1:2", user=H.STAFF, msg=w.card_of(2)) == "не отправляем", w.answers()
    words = w.send(H.OWNER)
    assert words.startswith("уже решено"), words
    assert w.door.sends == [] and w.count_rules() == 0, (w.door.sends, w.rules())


def test_attach_true_hint_version_locked():
    """X24 → A15 (строитель, круг 2): при WA_AGENT_ATTACH версия по пояснению сверку Т4а не проходит. Пояснение не
    принимается словами; версия по пояснению, сделанная до включения сверки, на «Отправить» идёт под замок «без
    сверки»: клиенту ничего, правила нет. Прежний случай X24 («id нажавшего доходит до ядра на пути attach=True»)
    после этого ненаблюдаем: id нажавшего читает только правило, а правила на этом пути не бывает."""
    import wa_agent_attach as X
    w = H.started(core_cls=X.AttachCore, attach=True)
    w.core.db.execute("INSERT INTO attach(draft_id, reason, ts) VALUES(?,?,?)", (1, "договора нет", H.T0))
    w.explain()
    assert w.core.db.execute("SELECT ver FROM drafts WHERE id=1").fetchone()[0] == 1
    assert w.core.db.execute("SELECT COUNT(*) FROM hints").fetchone()[0] == 0
    assert [p for p in w.sent() if X.W_HINT_NO_CHECK in p["text"]], [p["text"][:80] for p in w.sent()[-3:]]
    w2 = H.started(core_cls=X.AttachCore, attach=True)
    w2.core.db.execute("INSERT INTO attach(draft_id, reason, ts) VALUES(?,?,?)", (1, "договора нет", H.T0))
    w2.core.attach = False                                           # версия 2 по пояснению — до включения сверки
    w2.explain()
    w2.core.attach = True
    assert w2.core.db.execute("SELECT ver FROM drafts WHERE id=1").fetchone()[0] == 2
    words = w2.send(H.OWNER)
    assert words == X.W_NO_CHECK, words
    assert w2.door.sends == [] and w2.count_rules() == 0, (w2.door.sends, w2.rules())
    assert not w2.fell(), w2.fell()


# ═══ выключатель: решение и промпт при выключенном флаге ════════════════════════════════════════

def test_flag_off_hint_rule_not_decided():
    """X58: флаг выключен — кандидат-пояснение не переводится и не отклоняется даже владельцем."""
    w = H.World(hints=False)
    H._add_rule(w, 1, A.LESSON_CANDIDATE, "кандидат при выключенном флаге")
    words = w.press("wa:rule:1:0", user=H.OWNER)
    assert A.HINT_OFF_WORDS in words and _state(w, 1) == A.LESSON_CANDIDATE, (words, _state(w, 1))
    w.press("wa:lno:1:0", user=H.OWNER)
    assert _state(w, 1) == A.LESSON_CANDIDATE, _state(w, 1)


def test_flag_off_hint_rules_not_in_prompt():
    """X66: флаг выключен — действующее правило-пояснение (осталось с прошлого включения) в промпт не идёт."""
    w = H.World(hints=False)
    H._add_rule(w, 1, A.LESSON_ACTIVE, "правило-при-выключенном-флаге")
    user = w.prompt()
    assert "правило-при-выключенном-флаге" not in user and "правило:" not in H.rule_block(user), H.rule_block(user)


# ═══ один движок: уроки правкой WAAGENTLESSON0210 рядом с правилами ════════════════════════════════

def test_text_lessons_off_not_in_prompt():
    """X67: WA_AGENT_LESSONS выкл, WA_AGENT_HINTS вкл (база агента адаптеру дана ради правил) — урок правкой
    в промпт не идёт, правило — идёт."""
    w = H.World(hints=True, lessons=False)
    _add_text_lesson(w, 1, A.LESSON_ACTIVE, "было-урок-один", "стало-урок-один")
    H._add_rule(w, 2, A.LESSON_ACTIVE, "правило-два")
    blk = H.rule_block(w.prompt())
    assert "стало-урок-один" not in blk and "№2: правило: правило-два" in blk, blk


def test_text_lessons_on_reach_prompt():
    """X68: WA_AGENT_LESSONS вкл — урок правкой идёт тем же блоком (рядом с правилом и без флага пояснений)."""
    w = H.World(hints=True, lessons=True)
    _add_text_lesson(w, 1, A.LESSON_ACTIVE, "было-урок-один", "стало-урок-один")
    H._add_rule(w, 2, A.LESSON_ACTIVE, "правило-два")
    blk = H.rule_block(w.prompt())
    assert "№1: было «было-урок-один» → стало «стало-урок-один»" in blk and "№2: правило: правило-два" in blk, blk
    w = H.World(hints=False)
    _add_text_lesson(w, 1, A.LESSON_ACTIVE, "было-урок-один", "стало-урок-один")
    blk = H.rule_block(w.prompt())
    assert "№1: было «было-урок-один» → стало «стало-урок-один»" in blk, blk


def test_rule_reaches_followup_request():
    """X69: действующее правило доходит и до запроса напоминания (build_followup — тот же блок уроков)."""
    w = H.World()
    H._add_rule(w, 1, A.LESSON_ACTIVE, "правило-для-напоминания")
    user = w.adapter.build_followup(H.NUM, 1, now=H.T0 + 100)[1]
    assert "№1: правило: правило-для-напоминания" in H.rule_block(user), user[:900]


# ═══ версия по пояснению: гонка с клиентом, проверки кодом, решённый черновик ═════════════════════

class RacingCall(H.HintCall):
    """Пока модель пишет версию по пояснению, клиент пишет ещё (строка в очередь во время вызова)."""

    def __init__(self, w):
        super().__init__()
        self.w = w

    def __call__(self, system, user):
        if H.ASK_MARK in user and self.w is not None:
            self.w.put("пока агент думал — ещё вопрос", ts=H.T0 + 300)
            self.w = None
        return super().__call__(system, user)


def test_hint_version_dropped_when_client_writes_during_model():
    """X74: клиент написал во время вызова модели — версии по пояснению нет, пояснение fail, карточки v2 нет."""
    w = H.started()
    racing = RacingCall(w)
    racing.calls = w.call.calls
    w.adapter.call = w.call = racing
    w.explain()
    assert w.core.db.execute("SELECT ver FROM drafts WHERE id=1").fetchone() == (1,)
    assert w.core.db.execute("SELECT state FROM hints").fetchall() == [(A.HINT_FAIL,)]
    assert w.card_of(2) is None


class MoneyHintCall(H.HintCall):
    """Версия по пояснению с денежным обещанием — проверка кодом обязана пометить её «нужен человек»."""

    def __call__(self, system, user):
        if H.ASK_MARK in user:
            self.calls.append((system, user))
            return (json.dumps({"text": MONEY_NEW, "lang": "ru", "handoff": [], "why": "вопрос"}, ensure_ascii=False),
                    {"model": "fake", "in": 10, "out": 5})
        return super().__call__(system, user)


def test_hint_version_money_claim_marked_for_human():
    """X96: версия по пояснению написана моделью — пометка «нужен человек» на её карточке как у версии 1."""
    w = H.started()
    money = MoneyHintCall()
    money.calls = w.call.calls
    w.adapter.call = w.call = money
    w.explain()
    card2 = w.card_text(2)
    assert MONEY_NEW in card2 and G.W_SEND_HAND in card2 and G.W_SEND_OPEN not in card2, card2


def test_hint_refused_for_decided_draft():
    """X92: черновик уже ушёл — ответ на приглашение пояснением не становится (ядро сверяет pending)."""
    w = H.started()
    w.press("wa:fix:1:1", user=H.STAFF, msg=w.card_of(1))
    inv = w.invite()
    assert w.send(H.OWNER, ver=1) == "sent", w.answers()
    w.say(H.HINT, reply_to=inv)
    assert w.sent()[-1]["text"].startswith("не принято"), w.sent()[-1]["text"]
    assert w.core.db.execute("SELECT COUNT(*) FROM hints").fetchone()[0] == 0


def test_second_fix_press_one_invite():
    """X102: повторное «Исправить» той же версии — одно приглашение, второй раз — слова."""
    w = H.started()
    a1 = w.press("wa:fix:1:1", user=H.STAFF, msg=w.card_of(1))
    a2 = w.press("wa:fix:1:1", user=H.OWNER, msg=w.card_of(1))
    inv = [p for p in w.sent() if (p.get("reply_markup") or {}).get("force_reply")]
    assert len(inv) == 1 and a1 == a2 == G.W_HINT_ASKED, (len(inv), a1, a2)


def test_rule_write_failure_does_not_block_send():
    """X84 (S21): сбой записи правила — строка журнала, «Отправить» идёт дальше, клиенту ушло."""
    w = H.started()
    w.explain()

    def boom(who_id):
        raise RuntimeError("сбой базы правил")
    w.core.owner = boom
    words = w.send(H.OWNER)
    assert words == "sent", (words, w.lines[-5:])
    assert w.door.sends == [(H.NUM, H.NEW)] and w.count_rules() == 0, (w.door.sends, w.rules())
    assert any("правило по пояснению не записано" in ln for ln in w.lines), w.lines[-5:]
    assert not w.fell(), w.fell()


# ═══ суточный список: доставка, состав, пределы ═══════════════════════════════════════════════════

class FlakyHttp:
    """Bot API: первые `fails` отправок суточного списка — 502; остальное — как у подделки набора."""

    def __init__(self, inner, fails=1):
        self.inner, self.fails, self.failed = inner, fails, 0

    def __call__(self, method, url, headers=None, data=None, timeout=30):
        params = json.loads(data.decode("utf-8")) if data else {}
        if url.rsplit("/", 1)[-1] == "sendMessage" and str(params.get("text", "")).startswith(G.W_LIST_HEAD) \
                and self.fails > 0:
            self.fails -= 1
            self.failed += 1
            return 502, json.dumps({"ok": False, "description": "Bad Gateway"}).encode()
        return self.inner(method, url, headers, data, timeout)


def test_daily_list_retry_after_failed_delivery():
    """X47, X95: Telegram не принял список — замок суток НЕ ставится, повтор не раньше HINT_LIST_RETRY, в те же сутки."""
    w = H.World(hint_hour=21)
    H._add_rule(w, 1, A.LESSON_CANDIDATE, "кандидат один")
    flaky = FlakyHttp(w.http, fails=1)
    w.tg.http = flaky
    w.core.tick(LIST_AT)
    assert flaky.failed == 1 and H._lists(w) == [], (flaky.failed, len(H._lists(w)))
    w.core.tick(LIST_AT + A.HINT_LIST_RETRY - 60)                  # раньше срока повтора — попытки нет
    assert flaky.failed == 1 and H._lists(w) == [], (flaky.failed, len(H._lists(w)))
    w.core.tick(LIST_AT + A.HINT_LIST_RETRY + 60)                  # срок вышел — список ушёл в те же сутки
    assert len(H._lists(w)) == 1 and H.buttons(H._lists(w)[0]) == ["wa:rule:1:0", "wa:lno:1:0"], len(H._lists(w))


def test_daily_list_goes_to_agents_chat():
    """X105: суточный список уходит в чат «Агенты» (тот же адрес, что карточки; решает владелец по id)."""
    w = H.World(hint_hour=21)
    H._add_rule(w, 1, A.LESSON_CANDIDATE, "кандидат один")
    w.core.tick(LIST_AT)
    lst = H._lists(w)
    assert len(lst) == 1 and lst[0]["chat_id"] == w.tg.chat == H.CHAT, [(p.get("chat_id"), w.tg.chat) for p in lst]


def test_daily_list_skips_decided_rows():
    """X49: откатанные и отклонённые до списка в список не идут."""
    w = H.World(hint_hour=21)
    H._add_rule(w, 1, A.LESSON_CANDIDATE, "кандидат живой")
    H._add_rule(w, 2, A.LESSON_ROLLED, "откатанное до списка")
    H._add_rule(w, 3, A.LESSON_REJECTED, "отклонённое до списка")
    w.core.tick(LIST_AT)
    lst = H._lists(w)
    assert len(lst) == 1 and H.buttons(lst[0]) == ["wa:rule:1:0", "wa:lno:1:0"], [H.buttons(p) for p in lst]
    assert "откатанное" not in lst[0]["text"] and "отклонённое" not in lst[0]["text"], lst[0]["text"]


def test_daily_list_row_limit_20():
    """X50: строк в одном списке не больше 20 и при коротких пояснениях (предел строк, а не только знаков)."""
    w = H.World(hint_hour=21)
    for n in range(1, 31):
        H._add_rule(w, n, A.LESSON_CANDIDATE, "к%d" % n)
    w.core.tick(LIST_AT)
    lst = H._lists(w)
    assert len(lst) == 1, len(lst)
    shown = [b for b in H.buttons(lst[0]) if b.startswith("wa:lno:")]
    assert len(shown) == 20 and len(H.buttons(lst[0])) <= 100, (len(shown), len(lst[0]["text"]))
    assert (G.W_LIST_MORE % 10) in lst[0]["text"], lst[0]["text"][-120:]


def test_daily_list_long_hints_cut():
    """X97: длинные пояснения режутся в строке списка — в одно сообщение помещается не одна строка."""
    w = H.World(hint_hour=21)
    for n in range(1, 31):
        H._add_rule(w, n, A.LESSON_CANDIDATE, ("пояснение %d " % n) + "ш" * 2000)
    w.core.tick(LIST_AT)
    lst = H._lists(w)
    shown = len([b for b in H.buttons(lst[0]) if b.startswith("wa:lno:")])
    assert shown >= 10, shown
    assert all(len(row) <= G.HINT_ROW_MAX + 80 for row in lst[0]["text"].split("\n")), \
        max(len(row) for row in lst[0]["text"].split("\n"))


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
