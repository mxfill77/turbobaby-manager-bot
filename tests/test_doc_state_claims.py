# -*- coding: utf-8 -*-
"""ЗАМОК СОГЛАСОВАННОСТИ СТОЯЧИХ ДОКУМЕНТОВ (заведено 10.08.2026).

Класс: «документ пережил свою правду и стал источником заданий». Дважды за две недели работу
породил не мир, а текст о мире — и оба раза строку догоняли ПОСТФАКТУМ, уже после того, как
она успела родить задание:

  * `CLAUDE.md` числил остаток О2 открытым и нёс число «12 заметок за трое суток». Класс закрыт
    коммитом `7bcddba`, документа он НЕ ТРОГАЛ; куратор процитировал строку в ТЗ → два захода на
    уже сделанное (цель 440 шаг 1, цель 439 шаг 3). Догнал `bf483e1`.
  * Тот же документ утверждал, что `.js` обезвреженной папки выкладки читают node-харнессы гейта
    и это её единственная живая роль. После `06a477d` харнессы читают `bridge_prod/`. Догнал
    `2e759c7`.

Этот файл — ЗАМОК: заход, закрывающий класс, обязан оставить документ согласованным, и проверяет
это гейт, а не добрая воля. Красный лечится ПРАВКОЙ ДОКУМЕНТА (привязать объявление или увезти
состояние в артефакт), а не правкой теста.

Секции:
  (1) позиция — цитата снятой строки объявлением не является;
  (2) ОБРАТНЫЙ ХОД — ДОСЛОВНЫЕ строки про О2 и про папку выкладки обязаны быть НАЙДЕНЫ;
  (3) привязанная форма обязана проходить — иначе правило нечем удовлетворить;
  (4) ЖИВОЙ ЗАМОК — в стоячих документах ноль объявлений без привязки;
  (5) БИТЬЁ — названный живой факт разрешается (файл есть, коммит есть), иначе привязка
      декоративна: сослаться можно на что угодно, открыть — только на существующее;
  (6) числа НЕ запрещены: документ без чисел бесполезен, лечится их бессрочность.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import doc_state_claims as dsc                                  # noqa: E402

# ── ДОСЛОВНЫЕ строки из дерева `06a477d` — те самые, что родили фантомные задания ──────────────
BEFORE_O2 = (
    "  **ОСТАТКИ: побочная находка, НЕ чинена намеренно** — О2 «демон не даёт оборота» ШУМИТ, потому\n"
    "  что демон исполняет `claude -p` синхронно внутри `cycle()`, а пульс пишется последней строкой:\n"
    "  любой заход дольше 10 мин выглядит остановкой (**12 заметок за трое суток** по журналу таймера);\n"
    "  точки касания `_expect_pulse` в `cycle()` и `expectations._o2_daemon`. Пересечение с\n"
)
BEFORE_GS = (
    "  содержимом — **ноль**. Папка ОСТАВЛЕНА и ничего не удалено: её `.js` читают node-харнессы гейта\n"
    "  (`tests/*_harness.js`) — это её единственная живая роль; копия до захода —\n"
    "  `/root/_bridgegs_predisarm_20260810`. Указатель лежит в самой папке\n"
)


def _findings(text):
    return dsc.findings(text, "проба")


# ── (1) ПОЗИЦИЯ: цитата — не заявление ────────────────────────────────────────────────────────
def test_citation_is_not_a_declaration():
    """Документ обязан иметь право процитировать СНЯТУЮ строку, называя её устаревшей."""
    live = "**ОСТАТКИ:** зеркало ПК-полосы не сделано.\n"
    quoted = "прежняя строка «ОСТАТКИ: побочная находка, НЕ чинена намеренно» УСТАРЕЛА и снята.\n"
    assert _findings(live), "объявление от своего имени обязано судиться"
    assert not _findings(quoted), "цитата снятой строки объявлением не является"


def test_code_span_is_not_a_declaration():
    assert not _findings("форма: `**ОСТАТКИ (на дд.мм.гггг, хеш): …**` — образец, а не заявление.\n")


def test_nested_marker_does_not_cut_the_head():
    """«единственная живая роль» несёт вложенное совпадение — голова не должна обрываться на нём."""
    text = "это её единственная живая роль (на 10.08.2026, `abcdef1`); дальше проза.\n"
    assert not _findings(text), "голова обрезана вложенным маркером — привязка не увидена"


def test_word_tail_is_not_a_marker():
    """«САМОДОСТАТОЧНОСТЬ» несёт «ОСТАТОЧНОСТЬ» внутри слова и объявлением не является."""
    assert not _findings("- **САМОДОСТАТОЧНОСТЬ: строка ДОЛЖНА быть ЗАКОНЧЕННОЙ.**\n")


# ── (2) ОБРАТНЫЙ ХОД: дословные строки дерева ДО фикса ────────────────────────────────────────
def test_reverse_run_names_the_o2_line():
    f = _findings(BEFORE_O2)
    assert len(f) == 1, "строка про остаток О2 обязана быть найдена, найдено: %d" % len(f)
    assert f[0]["вид"] == "остаток"
    assert "дата" in f[0]["чего нет"], "у неё нет даты — именно этим она и пережила свою правду"
    assert "побочная находка" in f[0]["голова"], "находка обязана называть ДОСЛОВНУЮ строку"


def test_reverse_run_names_the_deploy_folder_line():
    f = _findings(BEFORE_GS)
    assert len(f) == 1, "строка про папку выкладки обязана быть найдена, найдено: %d" % len(f)
    assert f[0]["вид"] == "роль"
    assert "дата" in f[0]["чего нет"]
    assert "роль" in f[0]["голова"]


def test_number_alone_did_not_save_the_o2_line():
    """У строки О2 было число «12 заметок за трое суток» — числом привязка не становится."""
    assert dsc.date_of(_findings(BEFORE_O2)[0]["голова"]) is None


# ── (3) ПРИВЯЗАННАЯ ФОРМА ПРОХОДИТ ────────────────────────────────────────────────────────────
def test_anchored_forms_pass():
    ok = [
        "**ОСТАТКИ (на 05.08.2026, `9906598`): зеркало ПК-полосы не сделано** (точки касания: X).\n",
        "**ОСТАТОК КЛАССА НАЗВАН (на 10.08.2026, `bf483e1`):** штамп покрывает только одно место.\n",
        "Живых ролей у папки теперь ноль (на 10.08.2026, `docs/artifacts/x.md`).\n",
    ]
    for t in ok:
        assert not _findings(t), "привязанная форма обязана проходить: %s" % t


def test_date_without_openable_fact_is_not_enough():
    t = "**ОСТАТКИ (на 05.08.2026): зеркало ПК-полосы не сделано** — точка касания в демоне.\n"
    f = _findings(t)
    assert f and f[0]["чего нет"] == ["живой факт (путь или коммит)"]


def test_fact_without_date_is_not_enough():
    t = "**ОСТАТКИ (`9906598`): зеркало ПК-полосы не сделано** — точка касания в демоне.\n"
    f = _findings(t)
    assert f and f[0]["чего нет"] == ["дата"]


def test_symbol_in_backticks_is_not_an_openable_fact():
    """«Точка касания» подсказывает, где искать, но проверить утверждение целиком не даёт."""
    assert dsc.handles_of("ОСТАТКИ (на 05.08.2026): точки касания `_expect_pulse`, `_o2_daemon`") == []


# ── (4) ЖИВОЙ ЗАМОК ───────────────────────────────────────────────────────────────────────────
def test_standing_docs_are_consistent():
    bad = []
    for rel in dsc.STANDING_DOCS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue                       # FAIL-SAFE: документа нет — судить нечего
        with open(path, encoding="utf-8") as fh:
            bad.extend(dsc.explain(f) for f in dsc.findings(fh.read(), rel))
    assert not bad, (
        "утверждение о состоянии без привязки в стоячем документе:\n  " + "\n  ".join(bad) +
        "\nЛЕЧИТСЯ ПРАВКОЙ ДОКУМЕНТА: поставить в голове объявления дату (когда это было верно) "
        "и живой факт, который можно открыть (путь или хеш коммита), — либо увезти состояние в "
        "docs/artifacts/, где ему и место. Правка теста лечением НЕ является.")


# ── (5) БИТЬЁ: живой факт обязан разрешаться ──────────────────────────────────────────────────
def _known_commits():
    """FAIL-SAFE: git недоступен → None, и проверка коммитов пропускается (не краснеем зря)."""
    try:
        out = subprocess.run(["git", "-C", ROOT, "rev-list", "--all"],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return set(out.stdout.split()) if out.returncode == 0 and out.stdout.strip() else None


def _resolves(kind, val, commits):
    if kind == "коммит":
        return True if commits is None else any(s.startswith(val) for s in commits)
    target = val if val.startswith("/") else os.path.join(ROOT, val)
    return os.path.exists(target.split("*")[0].rstrip("/"))


def test_named_live_fact_resolves():
    """Сослаться можно на что угодно — открыть только на существующее."""
    commits = _known_commits()
    bad = []
    for rel in dsc.STANDING_DOCS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for dec in dsc.declarations(text):
            hs = dsc.handles_of(dec["голова"])
            if hs and not any(_resolves(k, v, commits) for k, v in hs):
                bad.append("%s:%d → %s" % (rel, dec["строка"], hs))
    assert not bad, (
        "привязка декоративна — ни один названный факт не открывается: " + "; ".join(bad) +
        " (файла нет на диске / коммита нет в истории этого репозитория)")


# ── (6) ЧИСЛА НЕ ЗАПРЕЩЕНЫ ────────────────────────────────────────────────────────────────────
def test_numbers_outside_declarations_are_free():
    """Документ без чисел бесполезен: лечится бессрочность числа, а не само число."""
    prose = ("ЗАМЕР за 7 суток: 2493 команды, изменились ровно 4 решения, карточек владельцу "
             "3 → 0. Порог 4 ч, потолок 3 эпизода за прогон, дефолт 0.\n")
    assert not _findings(prose), "проза с числами объявлением состояния не является"


def test_measurement_inside_a_declaration_lives_under_its_date():
    t = "**ОСТАТКИ (на 10.08.2026, `bf483e1`): шумит** — 12 заметок за трое суток по журналу.\n"
    assert not _findings(t), "число внутри привязанного объявления судиться не должно"


# ── (7) ОБЛАСТЬ ───────────────────────────────────────────────────────────────────────────────
def test_artifacts_are_out_of_scope():
    """Артефакт датирован именем файла по построению — состоянию место именно там."""
    for rel in dsc.STANDING_DOCS:
        assert not rel.startswith("docs/artifacts/"), rel
        assert not rel.startswith("reports/"), rel


def test_module_stays_pure():
    """Импорт ровно один: решение не должно уметь трогать мир (страж — DOC_STATE_PURE в гейте)."""
    with open(os.path.join(ROOT, "doc_state_claims.py"), encoding="utf-8") as fh:
        src = fh.read()
    imports = [l.strip() for l in src.split("\n")
               if l.startswith("import ") or l.startswith("from ")]
    assert imports == ["import re"], "у чистого решения появились руки: %s" % imports


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("  ✓ %s" % fn.__name__)
    print("OK — %d тестов doc_state_claims" % len(fns))
