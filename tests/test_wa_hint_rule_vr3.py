#!/usr/bin/env python3
"""Пояснение → правило (NIGHT0710-B2), доработка Д1 (INTEG0710): перенос пробы финального проверяющего, круг 3.

Пять пробелов тестов, найденных независимым проверяющим на дереве adcbb27: его мутанты выжили на наборах ветки
(test_wa_hint_rule, _gaps, _r2, _r3), а код на этих путях верен (вердикт — learn_aux/final_r3/VERDICT.md, мутанты —
learn_aux/final_r3/mut_r3.json). Тело пробы перенесено без изменений; формы, которые ловят пробелы:
  R3M03 — R14: пояснил ВЛАДЕЛЕЦ, «Отправить» нажал сотрудник → только кандидат (личность — нажавший, не автор): P02;
  R3M06 — R03: «правило» по отклонённому и по откатанному → «уже решено», в промпт не идёт: P04, P05;
  R3M07 — WA_AGENT_HINTS снят после версии по пояснению → «Отправить» правила не рождает: P08;
  R3M08 — WA_AGENT_HINTS выключен → решений по пояснению и суточного списка нет: P09;
  R3M09 — журнал решений суточного списка (правило / отклонить / отменить) без текстов пояснений: P13.
Остальные формы (P01, P03, P06, P07, P10–P12, P14–P16) — соседние формы прежних находок (личность по id, двойное
нажатие, админ уроков, бот и чужой чат, A12, цепочка пояснений, путь сверки, нажатие без id, «откатить №1» в ответе
на приглашение, «Не нужно»): каждая обязана дать безопасный исход. Замок набора (zz): модули грузятся ИЗ этого
дерева, попыток соединения за прогон — 0 (сеть подменена: попытка записывается и роняет вызов).
Формат набора дерева: PASS/FAIL/ИТОГ, код 1 при любом FAIL. Всё на подделках набора test_wa_hint_rule (его шапка
подменяет spend_ledger до импорта: fcntl на ПК). Модель не зовётся."""
import os
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

_NET = []


def _no_net(*a, **kw):
    _NET.append(repr(a)[:80])
    raise AssertionError("сеть запрещена")


socket.socket.connect = lambda self, *a, **kw: _no_net(*a, **kw)      # noqa: E731
socket.socket.connect_ex = lambda self, *a, **kw: _no_net(*a, **kw)   # noqa: E731
socket.create_connection = _no_net

import test_wa_hint_rule as H  # noqa: E402
import test_wa_hint_rule_r2 as R2  # noqa: E402

A, G, WM, SV = H.A, H.G, H.WM, H.SV
OWNER, STAFF, NUM, CHAT, T0 = H.OWNER, H.STAFF, H.NUM, H.CHAT, H.T0
HINT2 = "второе пояснение: про депозит — только наличными"


def _active(w):
    return [r for r in w.rules() if r[1] == A.LESSON_ACTIVE]


def _cq(w, data, user, chat=None, msg=0):
    cq = {"id": "cq%d" % (w.uid + 1), "data": data, "message": {"message_id": msg, "chat": {"id": chat or CHAT}}}
    if user is not None:
        cq["from"] = user
    w.upd(callback_query=cq)
    return w.answers()[-1] if w.answers() else ""


# P01 — R14-соседняя: сотрудник нажал «Отправить» первым (кандидат), затем владелец жмёт ещё раз → не повышается
def test_p01_staff_wins_then_owner_press_stays_candidate():
    w = H.started()
    w.explain()
    first = w.send(STAFF)
    assert "кандидат №1" in first, first
    again = w.send(OWNER)
    assert again.startswith("уже решено"), again
    r = w.rules()
    assert len(r) == 1 and r[0][1] == A.LESSON_CANDIDATE and r[0][10] is None, r
    assert w.door.sends == [(NUM, H.NEW)], w.door.sends
    assert "правило:" not in w.prompt()


# P02 — R14 дословно: пояснил ВЛАДЕЛЕЦ, нажал сотрудник → только кандидат (личность — нажавший, а не автор)
def test_p02_owner_hint_staff_send_candidate_only():
    w = H.started()
    w.explain(user=OWNER)
    w.send(STAFF)
    r = w.rules()
    assert len(r) == 1 and r[0][1] == A.LESSON_CANDIDATE, r
    assert r[0][3] == 504608015 and r[0][12] == 501, r      # автор — владелец, нажал — сотрудник
    assert H.HINT not in w.prompt()


# P03 — двойное «правило» владельцем в суточном списке → одно действующее, второе «уже решено»
def test_p03_owner_rule_twice_one_active():
    w = H.World(hint_hour=21)
    H._add_rule(w, 1, A.LESSON_CANDIDATE, "кандидат-двойной")
    first = w.press("wa:rule:1:0", user=OWNER)
    second = w.press("wa:rule:1:0", user=OWNER)
    assert "действующее правило" in first, first
    assert second.startswith("уже решено"), second
    assert w.core.db.execute("SELECT COUNT(*) FROM lessons WHERE state=?", (A.LESSON_ACTIVE,)).fetchone()[0] == 1
    row = w.core.db.execute("SELECT decided_by_id FROM lessons WHERE id=1").fetchone()
    assert row == (504608015,), row


# P04 — R03: отклонённый кандидат владелец потом «правило» → отказ, в промпт не идёт
def test_p04_rejected_then_rule_refused():
    w = H.World(hint_hour=21)
    H._add_rule(w, 1, A.LESSON_CANDIDATE, "кандидат-отклонённый")
    assert "отклонено" in w.press("wa:lno:1:0", user=OWNER)
    again = w.press("wa:rule:1:0", user=OWNER)
    assert again.startswith("уже решено"), again
    assert w.core.db.execute("SELECT state FROM lessons WHERE id=1").fetchone()[0] == A.LESSON_REJECTED
    assert "кандидат-отклонённый" not in w.prompt()


# P05 — откатанное правило владелец «правило» → отказ (откат необратим кнопкой списка)
def test_p05_rolled_then_rule_refused():
    w = H.World(hint_hour=21)
    H._add_rule(w, 1, A.LESSON_ACTIVE, "правило-откатываемое")
    assert "откатан" in w.press("wa:unrule:1:0", user=OWNER)
    again = w.press("wa:rule:1:0", user=OWNER)
    assert again.startswith("уже решено"), again
    assert w.core.db.execute("SELECT state FROM lessons WHERE id=1").fetchone()[0] == A.LESSON_ROLLED
    assert "правило-откатываемое" not in w.prompt()


# P06 — сотрудник из WA_AGENT_LESSON_ADMINS: «правило»/«отклонить»/«отменить» по пояснению → отказ (право — владелец)
def test_p06_lesson_admin_staff_cannot_decide_hint():
    w = H.World(lessons=True, admins=frozenset({501}), hint_hour=21)
    H._add_rule(w, 1, A.LESSON_CANDIDATE, "кандидат-админа")
    H._add_rule(w, 2, A.LESSON_ACTIVE, "правило-админа")
    assert w.press("wa:rule:1:0", user=STAFF).startswith("отказ:"), w.answers()
    assert w.press("wa:lno:1:0", user=STAFF).startswith("отказ:"), w.answers()
    assert w.press("wa:unrule:2:0", user=STAFF).startswith("отказ:"), w.answers()
    res = w.core.lesson_promote(1, "Дарья (id 501)", 501)
    assert not res["ok"], res
    res = w.core.lesson_rollback(2, "Дарья (id 501)", "501")          # id строкой — то же лицо, тот же отказ
    assert not res["ok"], res
    st = dict(w.core.db.execute("SELECT id, state FROM lessons").fetchall())
    assert st == {1: A.LESSON_CANDIDATE, 2: A.LESSON_ACTIVE}, st


# P07 — нажатие ботом с id владельца и нажатие владельца из чужого чата → отказ, правила нет, отправки нет
def test_p07_bot_with_owner_id_and_foreign_chat_refused():
    w = H.started()
    w.explain()
    bot_owner = {"id": 504608015, "is_bot": True, "first_name": "Филипп"}
    ans = _cq(w, "wa:send:1:2", bot_owner, msg=w.card_of(2))
    assert ans.startswith("отказ: боты"), ans
    ans = _cq(w, "wa:send:1:2", OWNER, chat=-100777, msg=w.card_of(2))
    assert ans.startswith("отказ: эта кнопка"), ans
    assert w.count_rules() == 0 and w.door.sends == [], (w.rules(), w.door.sends)


# P08 — выключатель снят после того, как версия по пояснению сделана: «Отправить» владельца → правила нет
def test_p08_flag_off_after_hint_version_no_rule():
    w = H.started()
    w.explain()
    w.core.hints = False
    w.send(OWNER)
    assert w.count_rules() == 0, w.rules()
    assert w.door.sends == [(NUM, H.NEW)], w.door.sends


# P09 — выключатель выкл: решения по пояснению (правило/отклонить) не принимаются, действующее в промпт не идёт,
# суточного списка нет; откат (шаг в безопасную сторону) остаётся возможен
def test_p09_flag_off_no_decisions_no_prompt_no_list():
    w = H.World(hint_hour=21)
    H._add_rule(w, 1, A.LESSON_CANDIDATE, "кандидат-при-выкл")
    H._add_rule(w, 2, A.LESSON_ACTIVE, "правило-при-выкл")
    w.core.hints = False
    w.adapter.hints = False
    assert w.press("wa:rule:1:0", user=OWNER).startswith(A.HINT_OFF_WORDS), w.answers()
    assert w.press("wa:lno:1:0", user=OWNER).startswith(A.HINT_OFF_WORDS), w.answers()
    assert "правило-при-выкл" not in w.prompt()
    w.core.tick(H.DAY0 + 21 * 3600 + 5 * 60)
    assert H._lists(w) == [], "список при выключенном флаге"
    st = dict(w.core.db.execute("SELECT id, state FROM lessons").fetchall())
    assert st == {1: A.LESSON_CANDIDATE, 2: A.LESSON_ACTIVE}, st


# P10 — A12-соседняя: модель упала на версии по пояснению, «Отправить» владельца на версии 1 → правила нет
def test_p10_fail_hint_owner_sends_model_version_no_rule():
    w = H.started()
    R2._failing_redraft(w)
    w.explain()
    assert w.core.db.execute("SELECT state FROM hints WHERE id=1").fetchone()[0] == A.HINT_FAIL
    w.send(OWNER, ver=1)
    assert w.count_rules() == 0, w.rules()


# P11 — два пояснения подряд (v1→v2→v3): «Отправить» владельца на v3 → РОВНО одно правило, из второго пояснения
def test_p11_chain_of_hints_one_rule_from_last():
    w = H.started()
    w.explain()
    w.explain(text=HINT2, ver=2)
    assert w.core.db.execute("SELECT ver FROM drafts WHERE id=1").fetchone()[0] == 3
    w.send(OWNER, ver=3)
    r = w.rules()
    assert len(r) == 1 and r[0][1] == A.LESSON_ACTIVE and r[0][8] == HINT2 and r[0][6:8] == (2, 3), r
    blk = H.rule_block(w.prompt())
    assert HINT2 in blk and H.HINT not in blk, blk


# P12 — путь сверки (WA_AGENT_TOOLS): кандидат и отклонённый в запрос не идут (соседняя V04)
def test_p12_tools_path_candidate_and_rejected_absent():
    import wa_agent_tools as T
    w = H.World()
    H._add_rule(w, 1, A.LESSON_CANDIDATE, "кандидат-на-пути-сверки")
    H._add_rule(w, 2, A.LESSON_REJECTED, "отклонённый-на-пути-сверки")
    H._add_rule(w, 3, A.LESSON_ACTIVE, "действующее-на-пути-сверки")
    seen = []
    saved = T.run

    class _J:
        def lines(self):
            return []
    try:
        T.run = lambda call, system, user, doors, **kw: seen.append(user) or {"state": T.ABORTED, "journal": _J()}
        w.adapter.tools = {}
        w.adapter.draft(NUM, 1)
    finally:
        T.run = saved
        w.adapter.tools = None
    assert seen, "путь сверки не позван"
    assert "кандидат-на-пути-сверки" not in seen[0] and "отклонённый-на-пути-сверки" not in seen[0], seen[0][:300]
    assert "№3: правило: действующее-на-пути-сверки" in H.rule_block(seen[0])


# P13 — журнал без текстов на решениях суточного списка (правило/отклонить/отменить)
def test_p13_journal_without_texts_on_list_decisions():
    w = H.World(hint_hour=21)
    secret1, secret2 = "ТЕКСТ-КАНДИДАТА-ОДИН", "ТЕКСТ-КАНДИДАТА-ДВА"
    H._add_rule(w, 1, A.LESSON_CANDIDATE, secret1)
    H._add_rule(w, 2, A.LESSON_CANDIDATE, secret2)
    w.core.tick(H.DAY0 + 21 * 3600 + 5 * 60)
    w.press("wa:rule:1:0", user=OWNER)
    w.press("wa:lno:2:0", user=OWNER)
    w.press("wa:unrule:1:0", user=OWNER)
    w.press("wa:rule:2:0", user=STAFF)
    joined = "\n".join(w.lines)
    assert secret1 not in joined and secret2 not in joined, [ln for ln in w.lines if "ТЕКСТ" in ln][:3]


# P14 — нажатие без id (from нет) на «правило»/«отменить» в списке → отказ
def test_p14_no_from_id_refused_on_list():
    w = H.World(hint_hour=21)
    H._add_rule(w, 1, A.LESSON_CANDIDATE, "кандидат-без-id")
    H._add_rule(w, 2, A.LESSON_ACTIVE, "правило-без-id")
    assert _cq(w, "wa:rule:1:0", None).startswith("отказ:"), w.answers()
    assert _cq(w, "wa:unrule:2:0", None).startswith("отказ:"), w.answers()
    assert _cq(w, "wa:lno:1:0", {"id": "504608015x", "is_bot": False, "first_name": "Филипп"}).startswith("отказ:")
    st = dict(w.core.db.execute("SELECT id, state FROM lessons").fetchall())
    assert st == {1: A.LESSON_CANDIDATE, 2: A.LESSON_ACTIVE}, st


# P15 — пояснение реплаем на приглашение словами «откатить №1» сотрудником → это команда отката (отказ), пояснения нет
def test_p15_rollback_words_in_hint_reply_not_a_hint_and_refused():
    w = H.started()
    H._add_rule(w, 1, A.LESSON_ACTIVE, "правило-под-откатом")
    w.press("wa:fix:1:1", user=STAFF, msg=w.card_of(1))
    w.say("откатить №1", user=STAFF, reply_to=w.invite())
    assert w.sent()[-1]["text"].startswith("отказ:"), w.sent()[-1]["text"]
    assert w.core.db.execute("SELECT COUNT(*) FROM hints").fetchone()[0] == 0
    assert w.core.db.execute("SELECT state FROM lessons WHERE id=1").fetchone()[0] == A.LESSON_ACTIVE


# P16 — «Не нужно» сотрудником на версии по пояснению, затем «Отправить» владельца → ничего не ушло, правила нет
def test_p16_decline_then_owner_send_no_rule():
    w = H.started()
    w.explain()
    assert w.press("wa:no:1:2", user=STAFF, msg=w.card_of(2)) == "не отправляем", w.answers()
    again = w.send(OWNER)
    assert again.startswith("уже решено"), again
    assert w.door.sends == [] and w.count_rules() == 0, (w.door.sends, w.rules())


def test_zz_no_network_and_tree():
    root = os.path.normcase(os.path.realpath(ROOT))
    for mod in (A, G, WM, SV, H, R2):
        p = os.path.normcase(os.path.realpath(getattr(mod, "__file__", "") or ""))
        assert p.startswith(root + os.sep), (mod.__name__, p)
    assert _NET == [], _NET


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
