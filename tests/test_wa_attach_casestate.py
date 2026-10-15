#!/usr/bin/env python3
"""CSTATE1510: служба и голдены — проводка флага WA_AGENT_CONTRACT_STATE и чувствительность голдена адаптера.

1. Служба (`wa_agent_svc`): `F_CSTATE` (= `wa_agent_attach.F_CSTATE`, в `FLAGS` не входит); `models_of` добавляет
   `cstate=True` в `make_model` ТОЛЬКО при флаге и WA_AGENT_TOOLS (иначе вызов прежней формы — test_wa_agent_cache:279);
   `make_model(cstate=True)` собирает `ContractStateAdapter` с теми же аргументами; `cstate_of` — не запрошен
   (None, None, None) и ни строки; запрошен без засчитанной карточки подписи — блок у модели гаснет (`cstate_on=False`) и
   строка «не засчитан»; засчитан — ядру `cstate=True` и детектор «подписал»; `tg_model_of` не тронут.
2. Голдены без перепина: `model_story` из tests/test_rental_case_integ_wa.py (прогон адаптера по GOLD_SCRIPTS) с
   подклассом выпуска при ВЫКЛЮЧЕННОМ блоке равен базе посимвольно, при ВКЛЮЧЁННОМ — обязан разойтись (зубы голдена).

Сети нет; модель, мост, Telegram и WhatsApp не зовутся. WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import test_wa_attach_cstate as CT  # noqa: E402  (стенды выпуска; заглушка spend_ledger — там же)
import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import wa_agent_cstate as C  # noqa: E402
import wa_agent_model as M  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_agent_tools as T  # noqa: E402
import wa_contract_state as CS  # noqa: E402
import test_wa_attach_svc as AS  # noqa: E402  (служба на подделках: Bot API, провайдер, очередь, показ)

HEAD = "договор клиента для модели (%s): " % S.F_CSTATE


def _bridge():
    return types.SimpleNamespace(_call=lambda *a, **k: {"ok": False}, fleet=lambda: {"ok": False},
                                 quote_price=lambda *a: {"ok": False}, tx_find=lambda **k: {"ok": False},
                                 contract_find=lambda **k: {"ok": False}, contract_pdf=lambda f: {"ok": False},
                                 clients=lambda **k: {"ok": False})


def _env():
    d = tempfile.mkdtemp(prefix="wa_casestate_")
    return {"queue_db": os.path.join(d, "q.db"), "agent_db": os.path.join(d, "a.db")}


class Model(AS.Model):
    """Модель службы с дверью аренды сверки (карточка подписи засчитывается); `cstate_on` — как у адаптера выпуска."""

    def __init__(self, blocked=True):
        AS.Model.__init__(self)
        if blocked:
            self.cstate_on = True

    def _tool_doors(self, number, upto_id):
        return {"rental": lambda: {"ok": True, "rows": []}, "history": lambda: []}


def _built(environ, blocked=True):
    w = AS.World(environ)
    w.model = Model(blocked)
    w.lines[:] = []
    w.build(environ)
    return w


# ═══ 1. служба ════════════════════════════════════════════════════════════════════════════════════════════

def test_svc_flag_name_one_and_not_in_flags():
    assert S.F_CSTATE == X.F_CSTATE == "WA_AGENT_CONTRACT_STATE"
    assert S.F_CSTATE not in S.FLAGS


def test_svc_cstate_of_three_outcomes():
    m = Model()
    assert S.cstate_of({}, True, m) == (None, None, None) and m.cstate_on is True
    assert S.cstate_of({S.F_CSTATE: "0"}, True, m) == (None, None, None)
    for v in ("1", "true", "YES", " on "):
        on, kw, words = S.cstate_of({S.F_CSTATE: v}, True, m)
        assert on is True and kw == {"cstate": True, "claim_of": CS.signed_claim}, (v, kw)
        assert words.startswith("вкл — ") and "contract_expect" in words and "клиенту ничего без нажатия" in words
    on, kw, words = S.cstate_of({S.F_CSTATE: "1"}, False, m)
    assert (on, kw) == (False, None) and words.startswith("не засчитан — флаг 1, но карточка после подписи"), words
    assert m.cstate_on is False, "блок у модели погашен — её build прежний"
    plain = AS.Model()
    on, kw, words = S.cstate_of({S.F_CSTATE: "1"}, True, plain)
    assert (on, kw) == (False, None) and "адаптер модели без блока договора" in words and not hasattr(plain, "cstate_on")
    assert S.cstate_of({S.F_CSTATE: "1"}, False, None)[0] is False


def test_svc_build_wiring_and_start_lines():
    on = dict(AS.ON, WA_AGENT_SIGNED_CARD="1", WA_AGENT_CONTRACT_STATE="1")
    w = _built(on)
    said = [ln for ln in w.lines if ln.startswith(HEAD)]
    assert len(said) == 1 and said[0].startswith(HEAD + "вкл — "), said
    assert w.core.cstate and w.core.claim_of is CS.signed_claim and w.model.cstate_on is True
    assert "contract_expect" in {r[0] for r in w.q("SELECT name FROM sqlite_master WHERE type='table'")}
    w2 = _built(dict(AS.ON, WA_AGENT_CONTRACT_STATE="1"))          # карточки подписи нет — не засчитан
    said = [ln for ln in w2.lines if ln.startswith(HEAD)]
    assert len(said) == 1 and said[0].startswith(HEAD + "не засчитан"), said
    assert not w2.core.cstate and w2.model.cstate_on is False
    assert "contract_expect" not in {r[0] for r in w2.q("SELECT name FROM sqlite_master WHERE type='table'")}
    w3 = _built(dict(AS.ON, WA_AGENT_SIGNED_CARD="1"))             # флаг не запрошен — ни строки, ни таблицы
    assert not [ln for ln in w3.lines if S.F_CSTATE in ln] and not w3.core.cstate and w3.model.cstate_on is True
    w4 = _built(dict(AS.BASE, WA_AGENT_CONTRACT_STATE="1"))        # PDF клиенту выкл — прежнее ядро
    assert type(w4.core) is A.Core and w4.model.cstate_on is False
    assert [ln for ln in w4.lines if ln.startswith(HEAD)][0].startswith(HEAD + "не засчитан")
    w5 = _built(dict(on, WA_AGENT_CONTRACT_ASK="0"))               # детектор просьбы выкл — ожидание открывает «подписал»
    assert w5.core.cstate and w5.core.ask_of is None and w5.core.claim_of is CS.signed_claim


def test_svc_models_of_call_shape():
    seen = []
    saved = S.make_model
    try:
        S.make_model = lambda env, line=None, **kw: seen.append(dict(kw)) or (None, "")
        S.models_of({}, {"WA_AGENT_DRAFTS": "1"})
        S.models_of({}, {"WA_AGENT_DRAFTS": "1", "WA_AGENT_CONTRACT_STATE": "1"})
        S.models_of({}, {"WA_AGENT_DRAFTS": "1", "WA_AGENT_TOOLS": "1"})
        S.models_of({}, {"WA_AGENT_DRAFTS": "1", "WA_AGENT_TOOLS": "1", "WA_AGENT_CONTRACT_STATE": "1"})
        S.models_of({}, {"WA_AGENT_CONTRACT_STATE": "1", "WA_AGENT_TOOLS": "1"})            # черновиков нет — модели нет
    finally:
        S.make_model = saved
    assert [sorted(k) for k in seen] == [["book", "cache", "lessons"], ["book", "cache", "lessons"],
                                         ["book", "cache", "lessons", "tools"],
                                         ["book", "cache", "cstate", "lessons", "tools"]], seen
    assert seen[3]["cstate"] is True


def test_svc_make_model_class_and_same_args():
    env = _env()
    plain, _ = S.make_model(env, bridge=_bridge(), call=lambda s, u: ("", {}), tools=True, book=True)
    blocked, _ = S.make_model(env, bridge=_bridge(), call=lambda s, u: ("", {}), tools=True, book=True, cstate=True)
    assert type(plain) is M.ModelAdapter and type(blocked) is C.ContractStateAdapter
    assert blocked.cstate_on is True and blocked.cstate_timeout == C.READ_TIMEOUT
    for name in ("queue_db", "agent_db", "archive_db", "manifest", "media_dir", "cache", "hints", "text_lessons",
                 "lessons_db"):
        assert getattr(plain, name) == getattr(blocked, name), name
    assert sorted(plain.tools) == sorted(blocked.tools) == ["cash", "contract", "contract_pdf"]
    assert blocked.book is not None and plain.book is not None
    saved = sys.modules.get("wa_agent_cstate")
    sys.modules["wa_agent_cstate"] = None                          # модуль выпуска не импортируется
    try:
        fell, why = S.make_model(env, bridge=_bridge(), call=lambda s, u: ("", {}), tools=True, cstate=True)
        same, _ = S.make_model(env, bridge=_bridge(), call=lambda s, u: ("", {}), tools=True)
    finally:
        sys.modules["wa_agent_cstate"] = saved
    assert type(fell) is M.ModelAdapter and why == "", "блок не собран — черновики живут на прежнем адаптере"
    assert fell.cstate_fail in ("ImportError", "ModuleNotFoundError") and not hasattr(same, "cstate_fail")
    on, kw, words = S.cstate_of({S.F_CSTATE: "1"}, True, fell)
    assert (on, kw) == (False, None) and "модуль блока договора не собран (%s)" % fell.cstate_fail in words, words
    assert type(same) is M.ModelAdapter, "без флага модуль выпуска не нужен вовсе"


def test_svc_tg_model_untouched():
    seen = []
    saved = S.make_model
    try:
        S.make_model = lambda env, line=None, **kw: seen.append(dict(kw)) or (None, "")
        S.tg_model_of({"tg_queue_db": "q", "tg_agent_db": "a"}, {"WA_AGENT_CONTRACT_STATE": "1", "WA_AGENT_TOOLS": "1"})
    finally:
        S.make_model = saved
    assert seen == [{"cache": None}], seen


def test_svc_full_wiring_real_adapter():
    """Служба на настоящем адаптере выпуска (`make_model(cstate=True)`): ядро получает его обёрнутым `_Probe`, ожидание
    подписи в базе, блок у адаптера включён."""
    w = AS.World(dict(AS.ON, WA_AGENT_SIGNED_CARD="1"))
    model, _ = S.make_model(w.env, bridge=_bridge(), call=lambda s, u: ("", {}), tools=True, book=True, cstate=True)
    w.model = model
    w.lines[:] = []
    w.build(dict(AS.ON, WA_AGENT_SIGNED_CARD="1", WA_AGENT_CONTRACT_STATE="1"))
    assert w.core.cstate and w.core.model._inner is model and model.cstate_on is True
    assert [ln for ln in w.lines if ln.startswith(HEAD)][0].startswith(HEAD + "вкл — ")


# ═══ 2. голден адаптера: выкл — посимвольно база, вкл — обязан разойтись ═══════════════════════════════════════

def test_golden_model_story_off_equal_on_differs():
    import test_rental_case_integ_wa as IW                        # model_story, GOLD_SCRIPTS (флаг дела выкл)
    w = CT.World()                                                # база агента со всеми таблицами выпуска
    w.x("INSERT INTO drafts(id, number, state, ver, text, upto_id, created_at, kind) VALUES(90,?,?,1,'x',1,?,?)",
        (IW.NUMBER, A.SENT, IW.T0, X.KIND_SIGNED))
    w.x("INSERT INTO signed_cards VALUES(?,?,?,?,?,?,?)", (IW.NUMBER, "D-1", "2026-10-01 10:12", "P-1", "c" * 64, 90,
                                                          IW.T0))

    class StubParent(M.ModelAdapter):
        """Родитель на месте `ModelAdapter.build`: голден подменяет build экземпляра лямбдой — она встаёт сюда."""

        def build(self, number, upto_id, now=None, hint=None):
            return self._stub(number, upto_id, now=now, hint=hint)

    class Probe(C.ContractStateAdapter, StubParent):
        def __setattr__(self, name, value):
            object.__setattr__(self, "_stub" if name == "build" else name, value)

    def factory(on):
        def make(*a, **kw):
            p = Probe(*a, agent_db=w.dbpath, **kw)
            p.cstate_on = on
            return p
        return types.SimpleNamespace(ModelAdapter=make)
    assert [k.__name__ for k in Probe.__mro__[:4]] == ["Probe", "ContractStateAdapter", "StubParent", "ModelAdapter"]
    base = IW.model_story(M, T)
    off = IW.model_story(factory(False), T)
    on = IW.model_story(factory(True), T)
    assert off == base, "блок выкл — адаптер выпуска посимвольно равен базе"
    assert on != base, "блок вкл — голден ОБЯЗАН разойтись с базой (зубы)"
    first = on[0]
    assert len(first["seen"]) == 7 and all(u.startswith(CT.HEAD_T + CS.HEAD_START) for u in first["seen"]), \
        first["seen"][0][:300]
    assert all("• версия: подписан 01.10 10:12 · doc …D-1 · карточка подписи" in u for u in first["seen"])
    assert [n["got"] for n in on] == [n["got"] for n in base], "ответы сценариев — те же: блок меняет только запрос"


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:400])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
