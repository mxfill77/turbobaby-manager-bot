"""БУФЕР ОТЛОЖЕННЫХ РАБОТ И СТОРОЖ ПАРТИИ (22.08.2026).

Класс, ради которого написано: во внутреннем обслуживании названная человеком позиция могла
исчезнуть БЕЗ ЕДИНОГО СЛОВА кому бы то ни было. Две дороги потери, обе закрываются здесь:
буфер темы ЗАМЕЩАЛСЯ присваиванием (вторая партия стирала первую молча), а расхождение
«принято N / записано M» никем не считалось вовсе — квитанция рапортовала успех о партии,
половина которой не легла никуда.

Что доказывается:
    (1) СУММА       две партии подряд в одной теме дают СУММУ позиций, а не последнюю;
    (2) ДЕДУП       повтор ТЕХ ЖЕ СЛОВ партию не раздувает, а РАЗНЫЕ работы не схлопываются;
    (3) ВОЗРАСТ     срок годности у каждой позиции свой: старая не утаскивает свежую в протухшие;
    (4) ПОИМЁННО    расхождение принято-записано называет КАЖДУЮ не легшую позицию, и обе
                    половины квитанции говорят об этом одно и то же;
    (5) ОТРИЦАТЕЛЬНЫЙ буфер ВЫГЛЯДИТ выгруженным (забран, ячейки темы больше нет), а позиции
                    не легли — сторож ОБЯЗАН показать отказ, а не промолчать;
    (6) ТРИ ИСХОДА  незнакомый исход считается ПОТЕРЕЙ, а не тихо проглатывается;
    (7) ЗДОРОВЫЙ    сошлось → квитанция БАЙТ-В-БАЙТ прежняя: сторож умеет только ДОБАВИТЬ;
    (8) ЖУРНАЛ      в журнальной строке названы ВСЕ потери, без потолка имён квитанции;
    (9) ЧИСТОТА     у сторожа ноль импортов (ast) — зеркало инварианта WORKS_LEDGER_PURE.

НИ ОДНА ДВЕРЬ ЗАПИСИ В МОСТ ЗДЕСЬ НЕ ЗОВЁТСЯ ВОВСЕ. Тест берёт функции напрямую на фикстурах
в памяти: моста нет ни настоящего, ни фейкового, сети нет, LLM нет. Байк ВЫДУМАН и помечен
«ТЕСТ» — номеров и имён живого парка в фикстурах нет ни одного.
"""
import ast
import os
import sys

# Корень берётся ОТ ФАЙЛА, а не литералом: иначе прогон «до правки» через `git worktree` тянул бы
# модули из БОЕВОГО дерева и зеленел бы на коде, которого в проверяемом дереве нет (ловушка метода).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != "/root/turbobaby-manager-bot"] \
    if ROOT != "/root/turbobaby-manager-bot" else sys.path
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import service_receipt as SR
import splinter as S
import works_ledger as WL

CHAT = -1002751134848
TOPIC = 9001
#: Байк ВЫДУМАННЫЙ и помеченный ТЕСТ: номера и имени живого парка в фикстурах нет ни одного.
BIKE = "ТЕСТ PHANTOM 000CC VOID-0 PHUKET 0000"
BASE = "info:0000:fixture"
ODO = "10000"
LBL = S._SP_KIND_LABEL

#: Две партии в ОДНОЙ теме — тот самый порядок, на котором первая исчезала молча.
BATCH_1 = ["долив тормозной жидкости", "передние тормозные колодки", "цепь"]
BATCH_2 = ["полная замена тормозной жидкости", "прокачка тормозов"]


def _fresh():
    """Чистая тема перед каждой проверкой: ни буфера, ни вердикта, ни накопителя сводки."""
    S._PENDING_WORKS.clear()
    S._SVC_LEDGER.clear()
    getattr(S, "_SVC_SUMMARY", {}).clear()


# ═══════════════ (1) СУММА: две партии подряд дают сумму позиций ═══════════════

def test_two_batches_sum_and_do_not_replace():
    """ГОЛДЕН класса: первая партия обязана дожить до второй. Раньше здесь стояло голое
    присваивание по ключу темы, и работа из первой партии исчезала без строки в журнале."""
    _fresh()
    first = S._pw_add(CHAT, TOPIC, BATCH_1, BIKE, BASE)
    assert first == BATCH_1, first
    second = S._pw_add(CHAT, TOPIC, BATCH_2, BIKE, BASE)
    assert len(second) == len(BATCH_1) + len(BATCH_2), second
    assert second[:len(BATCH_1)] == BATCH_1, "первая партия обязана стоять в буфере целиком"
    for w in BATCH_1 + BATCH_2:
        assert w in second, f"позиция потеряна буфером: {w!r}"
    fresh, stale, bike, base = S._pw_take(CHAT, TOPIC)
    assert fresh == second and stale == [], (fresh, stale)
    assert bike == BIKE and base == BASE, (bike, base)


def test_stems_that_collide_stay_separate_positions():
    """Буфер дедупится ПОВТОРОМ СЛОВ, а не стемом: у «долив тормозной жидкости» и «полная
    замена тормозной жидкости» стем ОДИН, и стем схлопнул бы две названные работы в одну —
    сторож их даже не увидел бы, они не были бы ПРИНЯТЫ."""
    _fresh()
    a, b = "долив тормозной жидкости", "полная замена тормозной жидкости"
    assert S._work_key(a) == S._work_key(b), "фикстура протухла: стемы разошлись, коллизии нет"
    S._pw_add(CHAT, TOPIC, [a], BIKE, BASE)
    got = S._pw_add(CHAT, TOPIC, [b], BIKE, BASE)
    assert got == [a, b], got


# ═══════════════ (2) ДЕДУП: те же слова партию не раздувают ═══════════════

def test_same_words_do_not_inflate_the_batch():
    _fresh()
    S._pw_add(CHAT, TOPIC, BATCH_1, BIKE, BASE)
    same = ["  ДОЛИВ   Тормозной Жидкости ", "цепь"]
    got = S._pw_add(CHAT, TOPIC, same, BIKE, BASE)
    assert got == BATCH_1, got
    assert S._pw_slot(same[0]) == S._pw_slot(BATCH_1[0]), "регистр и пробелы считаться не должны"


def test_empty_names_do_not_become_positions():
    _fresh()
    got = S._pw_add(CHAT, TOPIC, ["", "   ", "цепь"], BIKE, BASE)
    assert got == ["цепь"], got


# ═══════════════ (3) ВОЗРАСТ: у каждой позиции свой ═══════════════

def test_stale_position_does_not_drag_the_fresh_one():
    """Старая позиция протухает ОДНА: иначе свежая работа наследовала бы чужой возраст."""
    _fresh()
    S._pw_add(CHAT, TOPIC, ["цепь"], BIKE, BASE)
    S._pw_add(CHAT, TOPIC, ["вилка"], BIKE, BASE)
    cell = S._PENDING_WORKS[(CHAT, TOPIC)]
    cell["at"][S._pw_slot("цепь")] -= S._PENDING_WORKS_TTL + 60      # состарили ровно одну
    fresh, stale, _, _ = S._pw_take(CHAT, TOPIC)
    assert fresh == ["вилка"], fresh
    assert stale == ["цепь"], stale


# ═══════════════ (4) ПОИМЁННО: расхождение называет каждую потерю ═══════════════

def _positions(landed, lost):
    """Партия для сторожа: `landed` легли событием, `lost` — не легли, причина названа."""
    return ([WL.position(w, WL.AS_EVENT) for w in landed]
            + [WL.position(w, WL.LOST, why="write_failed", detail="bridge_down") for w in lost])


def test_divergence_names_every_lost_position_in_both_halves():
    v = WL.tally(_positions(BATCH_2, BATCH_1))
    assert v["n"] == 5 and v["m"] == 2, v
    assert v["agree"] is False
    assert len(v["lost"]) == 3, v["lost"]
    for half in ("th", "ru"):
        assert v[half], f"половина {half} молчит о потере"
        assert "5" in v[half] and "2" in v[half], v[half]
        for w in BATCH_1:
            assert w in v[half], f"половина {half} не назвала потерю {w!r}: {v[half]}"
    assert "не легло 3" in v["ru"], v["ru"]


def test_both_halves_carry_the_same_arithmetic():
    """Половины расходиться не смеют: класс 14.08 — тайская молчала о том, что сказала русская."""
    v = WL.tally(_positions(["цепь"], BATCH_1))
    assert v["th"].count(str(v["n"])) and v["ru"].count(str(v["n"]))
    assert len(v["lost"]) == 3 and v["th"] and v["ru"]
    assert v["th"] != v["ru"], "половины обязаны быть на РАЗНЫХ языках, а не копией"


def test_names_overflow_is_counted_not_swallowed():
    """Больше потолка имён — остаток назван ЧИСЛОМ, а не проглочен молчанием."""
    many = [f"работа {i}" for i in range(WL.NAMES_MAX + 3)]
    v = WL.tally(_positions([], many))
    assert v["n"] == len(many) and v["m"] == 0
    assert "и ещё 3" in v["ru"], v["ru"]


# ═══════════════ (5) ОТРИЦАТЕЛЬНЫЙ: выглядит выгруженным, но не легло ═══════════════

def test_buffer_looks_flushed_but_nothing_landed():
    """ОТРИЦАТЕЛЬНЫЙ ТЕСТ. Буфер забран и ячейки темы больше нет — снаружи это ровно тот вид,
    какой бывает у успешной выгрузки. Позиции при этом не легли никуда. Сторож ОБЯЗАН показать
    отказ: без этой проверки «сумма партий» зеленела бы и на молчаливой потере."""
    _fresh()
    S._pw_add(CHAT, TOPIC, BATCH_1, BIKE, BASE)
    S._pw_add(CHAT, TOPIC, BATCH_2, BIKE, BASE)
    fresh, stale, _, _ = S._pw_take(CHAT, TOPIC)
    # ── буфер ВЫГЛЯДИТ выгруженным ──
    assert (CHAT, TOPIC) not in S._PENDING_WORKS, "ячейка темы обязана исчезнуть при заборе"
    assert len(fresh) == 5 and stale == [], (fresh, stale)
    # ── а мир не принял ни одной позиции ──
    v = S._sp_ledger_note(CHAT, TOPIC, [], [], [], [],
                          [(w, "write_failed", "bridge_down") for w in fresh])
    assert v["agree"] is False, "сторож промолчал о партии, не легшей целиком"
    assert v["n"] == 5 and v["m"] == 0, v
    for w in fresh:
        assert w in v["ru"], f"потеря не названа поимённо: {w!r}"
    rec = SR.receipt([], [], ODO, LBL, ledger=S._svc_ledger_take(CHAT, TOPIC))
    assert rec["ledger"]["n"] == 5 and rec["ledger"]["m"] == 0, rec["ledger"]
    for w in fresh:
        assert w in rec["ru"], f"квитанция не назвала потерю {w!r}"
    assert rec["th"].strip() and rec["ru"].strip()


def test_no_bridge_loss_is_named_too():
    """Вторая дорога того же класса: моста нет, писать было НЕКУДА. До 22.08 у неё был только
    лог, а логов из команды не читает никто."""
    _fresh()
    peek = S._pw_add(CHAT, TOPIC, BATCH_1, BIKE, BASE)
    v = S._sp_ledger_note(CHAT, TOPIC, [], [], [], [], [(w, "no_bridge", "") for w in peek])
    assert v["agree"] is False and v["m"] == 0
    assert WL.WHY["no_bridge"][WL.RU] in v["ru"], v["ru"]
    assert WL.WHY["no_bridge"][WL.TH] in v["th"], v["th"]


def test_verdict_is_taken_exactly_once():
    """Вердикт забирается РОВНО ОДИН РАЗ — иначе он приклеился бы ко второй квитанции темы."""
    _fresh()
    S._sp_ledger_note(CHAT, TOPIC, [], [], [], [], [("цепь", "write_failed", "")])
    assert S._svc_ledger_take(CHAT, TOPIC) is not None
    assert S._svc_ledger_take(CHAT, TOPIC) is None


# ═══════════════ (6) ТРИ ИСХОДА: незнакомый — это потеря ═══════════════

def test_unknown_outcome_counts_as_loss():
    v = WL.tally([WL.position("цепь", "неведомо"), WL.position("вилка", WL.AS_EVENT)])
    assert v["n"] == 2 and v["m"] == 1, v
    assert len(v["lost"]) == 1 and v["lost"][0][0] == "цепь", v["lost"]
    assert WL.WHY["no_outcome"][WL.RU] in v["ru"], v["ru"]


def test_position_without_name_is_still_named():
    v = WL.tally([WL.position("", WL.LOST, why="write_failed")])
    assert WL.NO_NAME[WL.RU] in v["ru"], v["ru"]
    assert WL.NO_NAME[WL.TH] in v["th"], v["th"]


# ═══════════════ (7) ЗДОРОВЫЙ: сошлось → квитанция байт-в-байт прежняя ═══════════════

def test_agreement_keeps_receipt_byte_for_byte():
    """Сторож умеет только ДОБАВИТЬ строку о потере. Отнять он не умеет ничем — и это замок:
    иначе он стал бы вторым путём наружу, и половины поехали бы врозь."""
    v = WL.tally(_positions(["цепь", "вилка"], []))
    assert v["agree"] is True and v["th"] == "" and v["ru"] == "", v
    plain = SR.receipt(["oil"], [], ODO, LBL)
    with_ledger = SR.receipt(["oil"], [], ODO, LBL, ledger=v)
    assert with_ledger == plain, "сошлось — квитанция обязана остаться прежней"
    assert SR.receipt(["oil"], [], ODO, LBL, ledger=None) == plain


def test_empty_batch_is_agreement_not_loss():
    v = WL.tally([])
    assert v["n"] == 0 and v["m"] == 0 and v["agree"] is True, v


# ═══════════════ (8) ЖУРНАЛ: названы ВСЕ потери, без потолка ═══════════════

def test_journal_line_names_all_losses_without_cap():
    many = [f"работа {i}" for i in range(WL.NAMES_MAX + 3)]
    v = WL.tally(_positions([], many))
    body = WL.line(v)
    for w in many:
        assert w in body, f"журнальная строка обрезала потерю {w!r}"
    assert "и ещё" not in body, "у журнала потолка имён нет — обрезка только в квитанции"


def test_journal_line_says_no_losses_when_agreed():
    assert "потерь нет" in WL.line(WL.tally(_positions(["цепь"], [])))


# ═══════════════ (9) ЧИСТОТА: у сторожа ноль импортов ═══════════════

def test_purity_zero_imports_no_hands():
    """Зеркало инварианта WORKS_LEDGER_PURE. Будь у сторожа мост — он спросил бы судьбу записи
    САМ, и «записано» снова зависело бы от того, КАК спросили, а не от ответа листа."""
    with open(os.path.join(ROOT, "works_ledger.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("open", "exec", "eval", "compile", "__import__"), \
                f"у сторожа появились руки: {node.func.id} (строка {node.lineno})"
    assert imports == set(), f"импортов обязано быть ноль: {sorted(imports)}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} проверок: буфер копит партии, сторож называет каждую потерю")
