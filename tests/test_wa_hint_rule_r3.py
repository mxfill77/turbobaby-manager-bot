#!/usr/bin/env python3
"""Пояснение → правило (NIGHT0710-B2), круг исправления №3: перенос проб дозавершения проверки.

Три пробела тестов, найденные независимым проверяющим на дереве 7adf841 (мутанты выжили, код ветки верен;
вердикт — learn_aux/vm/VERDICT.md, мутанты — learn_aux/vm_mut/vm_probe.json):
  V04  — при WA_AGENT_TOOLS живой путь ModelAdapter.draft → _draft_tools → build: действующее правило обязано
         дойти до запроса модели и на этом пути;
  V05  — выключатель WA_AGENT_HINTS через сборку службы make_model при WA_AGENT_LESSONS=1: правило-пояснение
         в промпт не идёт, пока hints выключен (и идёт, когда включён — проба не слепа);
  X83b — «журнал без текстов» на ветке повтора пояснения после сбоя модели (A12): строка журнала есть,
         текста пояснения в журнале нет.
Плюс замок самой пробы: модули грузятся ИЗ этого дерева, сеть не трогается (попытка соединения записывается
и роняет вызов). Формат набора дерева: PASS/FAIL/ИТОГ, код 1 при любом FAIL. Всё на подделках набора
test_wa_hint_rule (его шапка подменяет spend_ledger до импорта: fcntl на ПК). Модель не зовётся."""
import os
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

_NET_TRIES = []                                                       # попытки соединения за прогон набора


def _no_net(*a, **kw):
    _NET_TRIES.append(repr(a)[:120])
    raise AssertionError("сеть в наборе запрещена: %r" % (a[:2],))


socket.socket.connect = lambda self, *a, **kw: _no_net(*a, **kw)      # noqa: E731
socket.socket.connect_ex = lambda self, *a, **kw: _no_net(*a, **kw)   # noqa: E731
socket.create_connection = _no_net

import test_wa_hint_rule as H  # noqa: E402  (подмена spend_ledger — в шапке набора)
import test_wa_hint_rule_r2 as R2  # noqa: E402

A, SV, WM = H.A, H.SV, H.WM


class _Journal:
    def lines(self):
        return []


def test_rule_reaches_request_on_tools_path():
    """V04. Путь сверки (WA_AGENT_TOOLS: ModelAdapter.draft → _draft_tools → build): действующее правило в запросе."""
    import wa_agent_tools as T
    w = H.World()
    H._add_rule(w, 1, A.LESSON_ACTIVE, "правило-на-пути-сверки")
    seen = []
    saved = T.run
    try:
        T.run = lambda call, system, user, doors, **kw: seen.append(user) or {"state": T.ABORTED,
                                                                               "journal": _Journal()}
        w.adapter.tools = {}
        w.adapter.draft(H.NUM, 1)
    finally:
        T.run = saved
        w.adapter.tools = None
    assert seen, "путь сверки не позван"
    assert "№1: правило: правило-на-пути-сверки" in H.rule_block(seen[0]), H.rule_block(seen[0])[:400]


def test_tools_path_rolled_back_rule_absent():
    """V04, соседняя форма: откатанное правило на пути сверки в запрос не идёт (тот же фильтр active_lessons)."""
    import wa_agent_tools as T
    w = H.World()
    H._add_rule(w, 1, A.LESSON_ROLLED, "откатанное-на-пути-сверки")
    seen = []
    saved = T.run
    try:
        T.run = lambda call, system, user, doors, **kw: seen.append(user) or {"state": T.ABORTED,
                                                                               "journal": _Journal()}
        w.adapter.tools = {}
        w.adapter.draft(H.NUM, 1)
    finally:
        T.run = saved
        w.adapter.tools = None
    assert seen, "путь сверки не позван"
    assert "откатанное-на-пути-сверки" not in seen[0], H.rule_block(seen[0])[:400]


def _svc_env(w):
    return {"queue_db": w.qpath, "agent_db": w.dbpath, "archive_db": w.apath, "tg_token": "", "show_chat": "",
            "mirror_db": ""}


def test_hints_switch_off_through_make_model():
    """V05. Служба (make_model): WA_AGENT_HINTS выкл, WA_AGENT_LESSONS вкл — правило-пояснение в промпт не идёт;
    контроль: тот же путь с hints=True правило несёт (проба не слепа)."""
    w = H.World(hints=False, lessons=True)
    H._add_rule(w, 1, A.LESSON_ACTIVE, "правило-при-выключенном-флаге")
    model, why = SV.make_model(_svc_env(w), line=w.lines.append, bridge=H.LiveBridge(), call=H.HintCall(),
                               lessons=True)
    assert model is not None, why
    user = model.build(H.NUM, 1, now=H.T0 + 100)[1]
    assert "правило-при-выключенном-флаге" not in user, H.rule_block(user)[:400]
    model2, why2 = SV.make_model(_svc_env(w), line=w.lines.append, bridge=H.LiveBridge(), call=H.HintCall(),
                                 lessons=True, hints=True)
    assert model2 is not None, why2
    user2 = model2.build(H.NUM, 1, now=H.T0 + 100)[1]
    assert "№1: правило: правило-при-выключенном-флаге" in H.rule_block(user2), H.rule_block(user2)[:400]


def test_retry_after_model_fail_journal_without_text():
    """X83b. A12 (повтор пояснения после сбоя модели): строка журнала есть, текста пояснения в журнале нет."""
    w = H.started()
    good = R2._failing_redraft(w)
    w.explain()
    w.adapter.call = good
    again = "пояснение ещё раз: про шлемы — бесплатно"
    w.say(again, reply_to=w.invite())
    assert w.sent()[-1]["text"].startswith("пояснение №1 принято"), w.sent()[-1]["text"]
    joined = "\n".join(w.lines)
    assert "повторно после сбоя" in joined, w.lines[-6:]
    assert again not in joined and H.HINT not in joined, [ln for ln in w.lines if "пояснени" in ln][-4:]


def test_zz_modules_from_this_tree_and_no_network():
    """Замок пробы: wa_agent*, набор-основа и подделки взяты ИЗ этого дерева; попыток соединения за прогон — 0.
    Имя с «zz» — чтобы стоять последним (main гоняет случаи по имени)."""
    import wa_agent_tools as T
    root = os.path.normcase(os.path.realpath(ROOT))
    for mod in (A, SV, WM, T, H, R2):
        path = os.path.normcase(os.path.realpath(getattr(mod, "__file__", "") or ""))
        assert path.startswith(root + os.sep), (mod.__name__, path, root)
    assert _NET_TRIES == [], _NET_TRIES


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
