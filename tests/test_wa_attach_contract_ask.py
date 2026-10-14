#!/usr/bin/env python3
"""Детектор явной просьбы прислать СВОЙ договор (CASEPDF1510, M1, `contract_ask`). Это проверка СМЫСЛА на коротких
примерах, а не корпус: детектор — ограничитель первого узкого транспорта, ответ клиенту строит модель.

Живые факты (корпус входящих за 60 дней со словами договор/контракт/contract/agreement/pdf/подпис): 7 уникальных фраз,
ЯВНОЙ просьбы прислать договор — 0. Шесть живых фраз ниже — НЕГАТИВЫ дословно. Позитивы — ПАРАФРАЗЫ: живьём такие
просьбы не встречались.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import contract_ask as C  # noqa: E402

# ── живые фразы корпуса (дословно): ни одна не просьба ─────────────────────────────────────────────────
LIVE_NEGATIVES = (
    "Мы же договорились",
    "А если допустим заключим контракт на год? Можно прям очень хорошую цену будет получить?)",
    "Подписал",
    "Какую сумму в рублях и куда перевести и будет ли договор?",
    "За 10 не договоримся?",
    "Тогда договорились",
)
# ── парафразы (живьём не встречались) — по нескольку на каждый смысл ─────────────────────────────────────
PURE_RU = ("Пришлите, пожалуйста, договор", "Скиньте договор 🙏", "Здравствуйте! Можно копию договора?",
           "Где мой договор?", "Подписал. Отправьте мне подписанный договор, пожалуйста",
           "Договор подписал, пришлите копию", "Пришлите договор ещё раз, пожалуйста")
PURE_EN = ("Please send me my contract", "Can I get my rental agreement?", "Could you send the pdf?",
           "Where is my contract? Thanks", "Hi! I signed it, send me a copy of the agreement please")
MIXED = ("Пришлите договор и во сколько доставка?", "Скиньте договор, и сколько депозит?",
         "Send me the contract and what time is delivery?", "Пришлите адрес и договор")
NOT_ASKED = ("Будет ли договор?", "Что в договоре про депозит?", "Договор подписан, спасибо", "Получил договор, спасибо",
             "Можно договор на год?", "Is there a contract?", "Where do I sign the contract?",
             "Пришлите копию паспорта")
REFUSED = ("Не надо договор", "Отмените договор", "I don't need the contract", "Don't send the agreement, thanks")
# ── ревизия CASEPDF1510 (находки критиков): чужой договор — не просьба СВОЕГО; второй вопрос из «нейтральных» слов —
# содержание; вежливый пинг «…, да?» — нет; «договор аренды» — тот же свой договор (как rental agreement) ──────────────
FOREIGN = ("Пришлите мне его договор", "Скиньте её договор", "Отправьте его договор пожалуйста",
           "Скиньте мне ее подписанный договор", "Пришлите ваш договор", "Send me his contract", "Send me her contract",
           "Could you send your contract?")
SECOND_QUESTION = ("Где договор? Готово?", "Где договор? Уже?", "Where is the contract? Already signed?",
                   "Покажите договор, его подписали?", "Пришлите договор. Вы подписали?", "Send the contract. Have I?")
PURE_PING = ("Пришлите договор, пожалуйста?", "Пришлите договор, да?", "Can I get my contract? Thanks!",
             "Пришлите договор аренды", "Пришлите, пожалуйста, договор аренды")


def test_live_negatives_are_none():
    for text in LIVE_NEGATIVES:
        assert C.verdict(text) is None, (text, C.verdict(text))


def test_pure_ru_en():
    for text in PURE_RU + PURE_EN:
        assert C.verdict(text) == C.PURE, (text, C.verdict(text))


def test_mixed_keeps_other_question():
    for text in MIXED:
        assert C.verdict(text) == C.MIXED, (text, C.verdict(text))


def test_not_a_request_terms_existence_received():
    for text in NOT_ASKED:
        assert C.verdict(text) is None, (text, C.verdict(text))


def test_refusal_and_cancel_are_none():
    for text in REFUSED:
        assert C.verdict(text) is None, (text, C.verdict(text))


def test_many_unanswered_together():
    """Неотвеченные входящие судятся вместе: нейтральное рядом — pure; другой вопрос в ЛЮБОМ из них — mixed; отказ в
    любом — None; просьбы нет нигде — None."""
    assert C.verdict_many(["Здравствуйте", "Подписал", "Пришлите договор, пожалуйста", "🙏"]) == C.PURE
    assert C.verdict_many(["Пришлите договор", "А шлем дадите?"]) == C.MIXED
    assert C.verdict_many(["Пришлите договор", "Не надо, уже нашёл"]) is None
    assert C.verdict_many(["Подписал", "Спасибо"]) is None
    assert C.verdict_many([]) is None and C.verdict_many(None) is None


def test_doubt_is_not_pure():
    """При сомнении НЕ pure: вложение (зовущий передаёт его словом вида), цифры и незнакомые слова — содержание."""
    assert C.verdict_many(["Пришлите договор", "[image]"]) == C.MIXED
    assert C.verdict_many(["Пришлите договор", None]) == C.MIXED
    assert C.verdict("Пришлите договор 5580") == C.MIXED
    assert C.verdict("Отправьте договор на почту") == C.MIXED


def test_verdicts_vocabulary():
    assert (C.PURE, C.MIXED) == ("pure", "mixed") and C.VERDICTS == (C.PURE, C.MIXED)
    for text in PURE_RU + MIXED + NOT_ASKED + LIVE_NEGATIVES:
        assert C.verdict(text) in (C.PURE, C.MIXED, None)


def test_foreign_contract_is_not_pure():
    """Чужой договор («его / её / ваш», his / her / your) — НЕ просьба своего: pure разрешал бы автоотправку ЕЁ договора
    шаблоном «Направляем ваш…» на чужую просьбу. RU и EN согласованы."""
    for text in FOREIGN:
        assert C.verdict(text) != C.PURE, (text, C.verdict(text))


def test_second_question_is_content_ping_is_not():
    """Второй вопрос рядом с просьбой — содержание, даже собранный из «нейтральных» слов (подписан, готово, уже, вы,
    have): mixed, не pure. Вежливый пинг («…, да?», «please?», «Thanks!») и «договор аренды» — pure."""
    for text in SECOND_QUESTION:
        assert C.verdict(text) == C.MIXED, (text, C.verdict(text))
    for text in PURE_PING:
        assert C.verdict(text) == C.PURE, (text, C.verdict(text))
    assert C.verdict_many(["Пришлите договор", "Подписал?"]) == C.MIXED


def test_wrapper_one_import_and_detector_pure():
    """Граница устройством. Обёртка: импорт ровно один — `wa_agent_attach` (вторая реализация не заводится — разойтись
    нечему). Детектор в ядре: функции `_ca_*`/`ask_verdict*` не зовут ни open, ни exec/eval/compile/__import__, не
    трогают ни os/sys/время/базы/сеть, ни self — только `re` и строки."""
    import wa_agent_attach as X
    tree = ast.parse(open(os.path.join(ROOT, "contract_ask.py"), encoding="utf-8").read())
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            names |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            names.add((n.module or "").split(".")[0])
    assert names == {"wa_agent_attach"}, names
    assert C.verdict_many is X.ask_verdict_many and C.verdict is X.ask_verdict, "одна реализация"
    core = ast.parse(open(os.path.join(ROOT, "wa_agent_attach.py"), encoding="utf-8").read())
    fns = [n for n in core.body if isinstance(n, ast.FunctionDef) and (n.name.startswith("_ca_")
                                                                      or n.name.startswith("ask_verdict"))]
    assert {f.name for f in fns} >= {"_ca_norm", "_ca_parse", "ask_verdict", "ask_verdict_many"}, [f.name for f in fns]
    banned = {"open", "exec", "eval", "compile", "__import__", "input", "getattr", "setattr", "globals", "locals",
              "os", "sys", "time", "datetime", "sqlite3", "socket", "subprocess", "self", "T", "A"}
    for f in fns:
        used = {n.id for n in ast.walk(f) if isinstance(n, ast.Name)}
        assert not (used & banned), (f.name, used & banned)


def test_attach_constants_match_detector():
    """Ядро детектор не импортирует (импорты `wa_agent_attach` прежние) — его словарь исходов сверяется здесь."""
    import wa_agent_attach as X
    assert (X.ASK_PURE, X.ASK_MIXED) == (C.PURE, C.MIXED) and X.ASKED == C.VERDICTS


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
