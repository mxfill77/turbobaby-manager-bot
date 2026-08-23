"""ПОНИЖЕНИЕ ПРОБЕГА ПРОХОДИТ ТОЛЬКО С НАПИСАННЫМ ПОЯСНЕНИЕМ (23.08.2026, правило владельца).

Предмет — решение `odo_lower`: расхождение ЧИСЛОМ, выбор причины из трёх, приёмка письменного
пояснения. Правило прочитано живьём в узле мозга `business_rules`, раздел «ПОНИЖЕНИЕ ПРОБЕГА
23.08.2026»: «Пустое пояснение и односложное согласие причиной не считаются. Пояснение
СОХРАНЯЕТСЯ вместе с записью и остаётся читаемым потом».

КАЖДЫЙ ОТРИЦАТЕЛЬНЫЙ СЛУЧАЙ ИДЁТ С БЛИЗНЕЦОМ, и без близнеца сьют бессмыслен: «не пропустил»
неотличимо от «не пропускает ничего». Пары:
  пусто           не проходит  ‖  те же причина и числа + слова человека     — проходит;
  «да»            не проходит  ‖  «да, сменили одометр»                      — проходит;
  «ок»/«ใช่»/«👍» не проходит  ‖  то же с дописанной причиной                — проходит;
  шум «аа»        не проходит  ‖  «стёрлось»                                 — проходит;
  чужая причина   не проходит  ‖  причина из списка                          — проходит.

Сеть не трогается вовсе, байки выдуманные, в Лист1 не пишется ничего.
"""
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import odo_lower as L          # noqa: E402

BIKE = "TESTBIKE 000ZZ PHUKET 4242"    # такого байка в парке нет и быть не может
REC, SENT = 41200, 38500               # записано / прислано


# ============================================================================================
#  (1) РАСХОЖДЕНИЕ НАЗЫВАЕТСЯ ЧИСЛОМ — ВСЕМИ ТРЕМЯ
# ============================================================================================
def test_diff_names_all_three_numbers():
    d = L.diff(REC, SENT)
    assert d["known"] and d["lower"], d
    assert (d["recorded"], d["sent"], d["drop"]) == (41200, 38500, 2700), d


def test_ask_prints_recorded_sent_and_drop():
    say = L.ask(BIKE, REC, SENT)
    for n in ("41200", "38500", "2700"):
        assert n in say["ru"], (n, say["ru"])
        assert n in say["th"], (n, say["th"])
    # все три причины названы человеку, а не спрятаны в кнопках
    for key in L.REASON_ORDER:
        assert L.REASONS[key]["ru"] in say["ru"], key
        assert L.REASONS[key]["th"] in say["th"], key


def test_ask_says_agreement_alone_is_not_enough():
    say = L.ask(BIKE, REC, SENT)
    assert "«да»" in say["ru"] and "пояснение" in say["ru"].lower(), say["ru"]


def test_no_lowering_no_ask_twin():
    """БЛИЗНЕЦ границы: пробег вырос или равен — вопроса нет вовсе, путь прежний."""
    assert L.ask(BIKE, 38500, 41200) is None
    assert L.ask(BIKE, 38500, 38500) is None
    assert L.diff(38500, 41200)["lower"] is False


def test_unparsed_numbers_do_not_claim_lowering():
    """Замок против ложного «понижение»: не разобрали число — о расхождении не заявляем."""
    for a, b in ((None, 38500), (41200, None), ("—", 1), (True, 5), ("", "")):
        d = L.diff(a, b)
        assert d["lower"] is False and d["known"] is False, (a, b, d)
        assert L.ask(BIKE, a, b) is None, (a, b)


def test_spaced_numbers_are_read():
    """Живой формат: человек пишет «41 200» и «38,500»."""
    d = L.diff("41 200", "38,500")
    assert (d["recorded"], d["sent"], d["drop"]) == (41200, 38500, 2700), d


# ============================================================================================
#  (2) ОТРИЦАТЕЛЬНЫЕ С БЛИЗНЕЦАМИ: пустое и односложное не проходят, слова проходят
# ============================================================================================
def test_empty_explanation_rejected():
    for text in ("", None, "   ", "\n\t ", "!!!", "…", "🙏"):
        v = L.explanation_verdict(text)
        assert v["state"] == L.EMPTY and v["ok"] is False, (text, v)
        assert v["text"] == "", (text, v)


def test_empty_explanation_twin_with_words_accepted():
    """БЛИЗНЕЦ: те же причина и числа, но пояснение написано — проходит."""
    v = L.explanation_verdict("одометр стёрся, поставили новый с нуля")
    assert v["state"] == L.ACCEPTED and v["ok"] is True, v
    assert v["text"] == "одометр стёрся, поставили новый с нуля", v


def test_bare_agreement_rejected():
    """Односложное согласие причиной не считается — правило владельца дословно."""
    for text in ("да", "Да", "ДА.", "ок", "окей", "верно", "правильно", "точно",
                 "yes", "ok", "OK!", "sure", "ใช่", "ถูกต้อง", "ครับ", "👍 да", "да!!!"):
        v = L.explanation_verdict(text)
        assert v["state"] == L.AGREEMENT and v["ok"] is False, (text, v)


def test_bare_agreement_twin_with_reason_accepted():
    """БЛИЗНЕЦ: то же слово согласия, но за ним идёт причина — это уже пояснение."""
    for text in ("да, сменили одометр", "ок поставили новую приборку",
                 "верно — прошлый раз записали лишний ноль", "ใช่ เปลี่ยนมาตรวัดใหม่"):
        v = L.explanation_verdict(text)
        assert v["state"] == L.ACCEPTED and v["ok"] is True, (text, v)


def test_agreement_is_judged_by_words_not_substring():
    """Слово согласия ВНУТРИ предложения ничего не отменяет — правило позиции."""
    v = L.explanation_verdict("механик подтвердил, что приборку заменили")
    assert v["state"] == L.ACCEPTED, v


def test_noise_rejected_and_twin_short_word_accepted():
    for text in ("аа", "??", "1", "--", "a"):
        v = L.explanation_verdict(text)
        assert v["ok"] is False, (text, v)
        assert v["state"] in (L.TOO_SHORT, L.EMPTY), (text, v)
    # БЛИЗНЕЦ: настоящее короткое слово порог проходит
    assert L.explanation_verdict("стёрлось")["state"] == L.ACCEPTED
    assert L.explanation_verdict("сброс")["state"] == L.ACCEPTED


def test_every_refusal_says_what_to_do():
    """ПРАВИЛО 2: отказ обязан говорить, ЧТО ДЕЛАТЬ. Глухих отказов тут нет ни одного."""
    for text in ("", "да", "ок", "аа", "??", "ใช่"):
        v = L.explanation_verdict(text)
        assert v["ok"] is False, text
        assert v["say_ru"] and v["say_th"], (text, v)
        assert any(w in v["say_ru"].lower() for w in ("напиши", "пиши", "пояснение", "причин")), v
        assert v["say_ru"].strip().endswith((".", "!")), v


def test_accepted_comes_by_exactly_one_path():
    """ЗАМОК против ложного зелёного: `ok` истинно РОВНО при state==ACCEPTED и наоборот."""
    probes = ["", "  ", "да", "ok", "ใช่", "аа", "1", "стёрлось", "сменили одометр",
              "прошлый раз записали лишний ноль", "👍", "нет", "не знаю"]
    for text in probes:
        v = L.explanation_verdict(text)
        assert v["ok"] == (v["state"] == L.ACCEPTED), (text, v)
        if v["ok"]:
            assert v["text"], (text, v)
        else:
            assert v["text"] == "" and v["say_ru"] and v["say_th"], (text, v)


def test_explanation_is_cut_under_ceiling_not_lost():
    long = "сменили одометр " * 60
    v = L.explanation_verdict(long)
    assert v["state"] == L.ACCEPTED and len(v["text"]) == L.EXPLANATION_MAX, len(v["text"])


# ============================================================================================
#  (3) ПРИЧИНА: список ЗАКРЫТЫЙ, замена одометра — событие
# ============================================================================================
def test_three_reasons_and_no_more():
    assert set(L.REASONS) == {L.WRONG_NUMBER, L.OLD_WRONG, L.ODO_REPLACED}
    assert L.REASON_ORDER == (L.WRONG_NUMBER, L.OLD_WRONG, L.ODO_REPLACED)
    for key in L.REASON_ORDER:
        assert L.reason_ok(key), key


def test_foreign_reason_rejected_with_twin():
    for key in ("", None, "просто так", "yes", "wrong_numberX", "odo"):
        assert L.reason_ok(key) is False, key
        p = L.plan(key, "сменили одометр")
        assert p["ok"] is False and p["state"] == "no_reason", (key, p)
        assert p["say_ru"] and p["say_th"], (key, p)
    # БЛИЗНЕЦ: та же строка пояснения с причиной ИЗ СПИСКА — проходит
    assert L.plan(L.ODO_REPLACED, "сменили одометр")["ok"] is True


def test_odometer_replacement_is_an_event_not_a_fix():
    """Правило владельца: замена одометра — событие, отдельная строка истории байка."""
    assert L.writes_history(L.ODO_REPLACED) is True
    assert L.writes_history(L.WRONG_NUMBER) is False
    assert L.writes_history(L.OLD_WRONG) is False
    assert L.plan(L.ODO_REPLACED, "поставили новую приборку")["writes_history"] is True
    assert L.plan(L.WRONG_NUMBER, "промахнулся цифрой")["writes_history"] is False


# ============================================================================================
#  (4) ПОЯСНЕНИЕ СОХРАНЯЕТСЯ И ОСТАЁТСЯ ЧИТАЕМЫМ
# ============================================================================================
def test_record_line_keeps_human_words_verbatim():
    line = L.record_line(L.ODO_REPLACED, "приборка сгорела, новая с нуля", "@earth")
    assert "приборка сгорела, новая с нуля" in line, line
    assert L.REASONS[L.ODO_REPLACED]["ru"] in line, line     # ярлык предваряет, а не заменяет
    assert "@earth" in line, line


def test_plan_line_carries_words_into_the_record():
    p = L.plan(L.OLD_WRONG, "в прошлый раз записали лишний ноль", "@pleummmm")
    assert p["ok"] and p["explanation"] == "в прошлый раз записали лишний ноль", p
    assert "в прошлый раз записали лишний ноль" in p["line"], p["line"]


def test_receipt_shows_numbers_and_the_words():
    r = L.receipt(BIKE, REC, SENT, L.ODO_REPLACED, "приборку заменили", "@earth")
    for n in ("41200", "38500", "2700"):
        assert n in r["ru"], (n, r["ru"])
    assert "приборку заменили" in r["ru"], r["ru"]
    assert "приборку заменили" in r["th"], r["th"]
    assert L.REASONS[L.ODO_REPLACED]["ru"] in r["ru"], r["ru"]


def test_plan_refusal_never_carries_words_forward():
    """Не принято — значит ничего не сохраняем: полуфабрикат хуже отсутствия."""
    p = L.plan(L.WRONG_NUMBER, "да")
    assert p["ok"] is False and p["explanation"] == "" and p["line"] == "", p


# ============================================================================================
#  (5) ЗАМОК ЗЕРКАЛА: словарь согласия шире боевого `splinter._CONFIRM_YES`
# ============================================================================================
def test_agreement_vocabulary_covers_live_confirm_words():
    """Две реализации одного смысла разойтись не должны — по крайней мере не в опасную сторону."""
    import splinter as S
    for word in S._CONFIRM_YES:
        assert L.is_agreement(word), (
            f"боевое слово согласия «{word}» решение понижения согласием НЕ считает — "
            f"оно прошло бы как пояснение")


# ============================================================================================
#  (6) ГРАНИЦА: решение НИЧЕГО не пишет и никуда не ходит
# ============================================================================================
def test_module_imports_exactly_one_and_touches_nothing():
    import ast
    src = open("/root/turbobaby-manager-bot/odo_lower.py", encoding="utf-8").read()
    tree = ast.parse(src)
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods == {"re"}, mods
    for forbidden in ("open(", "requests", "subprocess", "urllib", "bridge", "os."):
        assert forbidden not in src, forbidden


def test_purity_guard_is_registered_and_red_on_a_twin():
    """Страж чистоты в гейте, на живом модуле молчит — и краснеет на близнеце с миром."""
    import invariants_check as IC
    assert "ODO_LOWER_PURE" in [n for n, _ in IC.CHECKS], "страж в гейте"
    live = open("/root/turbobaby-manager-bot/odo_lower.py", encoding="utf-8").read()
    assert IC._duty_ast_findings(live, allowed=frozenset(("re",))) == [], "живой модуль чист"
    twin = ("import re\nimport requests\n\n"
            "def plan(a, b):\n"
            "    return open('/tmp/x').read()\n")
    assert IC._duty_ast_findings(twin, allowed=frozenset(("re",))), \
        "тот же страж на модуле, который умеет в мир, обязан краснеть"


if __name__ == "__main__":
    ok = fail = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ok += 1
            except Exception as e:
                fail += 1
                print(f"FAIL {name}: {e}")
    print(f"{ok}/{ok + fail}")
    sys.exit(1 if fail else 0)
