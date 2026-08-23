# -*- coding: utf-8 -*-
"""test_after_deploy_mirror.py — проверка после деплоя судит прод ЗЕРКАЛОМ (23.08.2026).

ПОВОД (шаг 2 цели 102). `deploy/bridge_after_deploy_check.py` вычислял «новый маршрут» двумя
ЗАХАРДКОЖЕННЫМИ снимками 04.08.2026 — папкой слияния и снимком HEAD. К 23.08 прод уехал
@79 → @83: снимок отстал на четыре версии, и ответ инструмента был не о проде, а о том, каким
прод был три недели назад. Истина о задеплоенной версии — зеркало `bridge_prod/` под паспортом
`MIRROR.json`, и путь к нему считается ОТ КАТАЛОГА ФАЙЛА, а не от «/root/…».

ЧТО ЗАКРЕПЛЕНО ЗДЕСЬ:
  - зеркало читается, и «судить можно» приходит РОВНО ОДНИМ путём: у каждого отказа есть
    близнец «то же без порчи — судим», иначе fail-closed мог бы оказаться «всегда закрыто»;
  - отказ ГРОМКИЙ и НЕНУЛЕВОЙ: ни одна порча зеркала/паспорта не даёт кода 0;
  - вердикт несёт КОД: прежняя редакция возвращала 0 даже строкой «маршрута в проде НЕТ»;
  - маршрут выбирается словарём ОДНОГО рода с обеих сторон (метки `case`), а самообъявление
    моста (`actions: [...]`) сравнивается со списками зеркала — каждое с себе подобным;
  - модуль читается БЕЗ сети и без .env: клиент моста импортируется лениво, внутри пробы;
  - инструмент строго читающий — живое зеркало за прогон не меняется ни на байт.

Сеть, `clasp`, прод @83 и живой каталог сборки здесь не трогаются вовсе: зеркала для случаев
делаются настоящими временными каталогами, паспорт в них согласован с байтами роутера
по-настоящему (sha256 считается фикстурой), иначе положительные случаи зеленели бы по
недосмотру, а не по существу.
"""
import ast
import contextlib
import hashlib
import json
import os
import re
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "deploy"))
os.environ.setdefault("PRETOOL_NOPUSH", "1")

import bridge_after_deploy_check as check          # noqa: E402

SRC = os.path.join(ROOT, "deploy", "bridge_after_deploy_check.py")

# Роутер-фикстура живого вида: метки маршрутизации + ДВА списка самообъявления (GET и POST),
# как в настоящем `Bridge.js`. Мок, переставший задевать ветку, хуже отсутствующего.
ROUTER_JS = """
function doGet(e) {
  switch (action) {
    case 'ping':
    case 'fleet':
      return ok();
    default:
      return json({ ok: false, error: 'unknown_action',
                    actions: ['ping', 'fleet'] });
  }
}
function doPost(e) {
  switch (action) {
    case 'add_event':
    case 'service_undo':
      return ok();
    default:
      return json({ ok: false, error: 'unknown_action',
                    actions: ['add_event', 'service_undo', 'edit_event'] });
  }
}
"""
POST_LIST = ["add_event", "edit_event", "service_undo"]      # отсортированный, как отдаёт разбор
GET_LIST = ["fleet", "ping"]


# ──────────────────────────── вспомогательные ────────────────────────────────

@contextlib.contextmanager
def _mirror(router=ROUTER_JS, meta="auto", raw_meta=None):
    """Настоящее временное зеркало на диске.

    router=None — роутера нет вовсе; meta=None — паспорта нет; meta=dict — накладывается на
    здоровый паспорт (так порча называется одной строкой); raw_meta — паспорт пишется текстом
    как есть (для нечитаемого JSON). Каталог убирается сам контекстом: своего кода удаления
    здесь нет намеренно — цель-переменную гард честно судит красной.
    """
    with tempfile.TemporaryDirectory(prefix="tb_adm_") as d:
        if router is not None:
            with open(os.path.join(d, check.ROUTER), "w", encoding="utf-8") as fh:
                fh.write(router)
        if raw_meta is not None:
            with open(os.path.join(d, check.PASSPORT), "w", encoding="utf-8") as fh:
                fh.write(raw_meta)
        elif meta is not None:
            good = {
                "prod_version": 83,
                "pulled_utc": "2026-08-23 12:20:53 UTC",
                "files_sha256": {
                    check.ROUTER: hashlib.sha256((router or "").encode("utf-8")).hexdigest()},
            }
            if isinstance(meta, dict):
                good.update(meta)
                for k, v in list(good.items()):
                    if v is _DROP:
                        del good[k]
            with open(os.path.join(d, check.PASSPORT), "w", encoding="utf-8") as fh:
                json.dump(good, fh)
        yield d


class _Drop(object):
    pass


_DROP = _Drop()          # маркер «ключа в паспорте нет вовсе», не путать со значением None


@contextlib.contextmanager
def _build(router=ROUTER_JS):
    with tempfile.TemporaryDirectory(prefix="tb_adb_") as d:
        if router is not None:
            with open(os.path.join(d, check.ROUTER), "w", encoding="utf-8") as fh:
                fh.write(router)
        yield d


def _dir_digest(folder):
    """Отпечаток каталога целиком: имена + байты. Ловит и правку, и подмену, и удаление."""
    h = hashlib.sha256()
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        h.update(name.encode("utf-8"))
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


# ─────────────────── (1) зеркало читается: положительный случай ───────────────

def test_healthy_mirror_is_judgeable():
    """Здоровое зеркало — судим: версия ЧИСЛОМ, маршруты разобраны, оба списка объявления."""
    with _mirror() as d:
        f = check.mirror_facts(d)
    assert f["ok"] is True, f["why"]
    assert f["version"] == 83
    assert f["pulled_utc"] == "2026-08-23 12:20:53 UTC"
    assert f["routes"] == ["add_event", "fleet", "ping", "service_undo"]
    assert sorted(f["declared"], key=len) == [GET_LIST, POST_LIST]
    assert f["why"] == "", "у согласного зеркала не бывает причины отказа"


def test_healthy_mirror_names_no_reason():
    """Молчаливого «ну ладно» нет и в обратную сторону: ok=True не несёт причины."""
    with _mirror() as d:
        assert not check.mirror_facts(d)["why"]


# ───────────────────── (2) fail-closed: каждая порча — отказ ──────────────────

def _why(**kw):
    """Прогнать порченое зеркало и вернуть причину отказа (пустая причина запрещена)."""
    with _mirror(**kw) as d:
        f = check.mirror_facts(d)
    assert f["ok"] is False, "порченое зеркало признано годным: %r" % (kw,)
    assert f["why"], "отказ без названной причины — это молчание, а не fail-closed"
    assert f["routes"] == [] and f["version"] is None, "при отказе факты о проде не выдаются"
    return f["why"]


def test_no_mirror_at_all_is_refused():
    with tempfile.TemporaryDirectory(prefix="tb_adm_") as d:
        gone = os.path.join(d, "нет-такого-каталога")
        f = check.mirror_facts(gone)
    assert f["ok"] is False and gone in f["why"]


def test_missing_passport_is_refused():
    assert check.PASSPORT in _why(meta=None)


def test_unreadable_passport_is_refused():
    assert "не читается" in _why(raw_meta="{это не json")


def test_passport_not_an_object_is_refused():
    assert "не объект" in _why(raw_meta="[83]")


def test_passport_without_version_is_refused():
    assert "ЧИСЛОМ" in _why(meta={"prod_version": _DROP})


def test_passport_version_as_string_is_refused():
    """«83» строкой версией не считается — тот же различитель, что у mirror_sync._is_num."""
    assert "ЧИСЛОМ" in _why(meta={"prod_version": "83"})


def test_passport_version_as_bool_is_refused():
    """True — тоже int для питона; зеркало, назвавшее себя булевым, судить прод не вправе."""
    assert "ЧИСЛОМ" in _why(meta={"prod_version": True})


def test_missing_router_is_refused():
    assert check.ROUTER in _why(router=None)


def test_passport_without_router_sha_is_refused():
    assert "sha256" in _why(meta={"files_sha256": {}})


def test_router_diverged_from_passport_is_refused():
    """Роутер правили руками — зеркало врёт О СЕБЕ, и список маршрутов из него недостоверен."""
    with _mirror() as d:
        with open(os.path.join(d, check.ROUTER), "a", encoding="utf-8") as fh:
            fh.write("\n// чужая правка\n")
        f = check.mirror_facts(d)
    assert f["ok"] is False and "разошёлся с паспортом" in f["why"]


def test_router_without_routes_is_refused():
    """Ноль разобранных маршрутов — не «прод не знает ничего», а «разобрать не удалось»."""
    assert "ни одного маршрута" in _why(router="// пусто, ни одной метки\n")


def test_every_refusal_is_nonzero_in_main():
    """ГЛАВНОЕ: ни одна порча зеркала не даёт кода 0, и сеть при этом не трогается вовсе."""
    cases = [dict(meta=None), dict(raw_meta="{битый"), dict(router=None),
             dict(meta={"prod_version": "83"}), dict(meta={"files_sha256": {}}),
             dict(router="// без меток\n")]
    for kw in cases:
        with _mirror(**kw) as d:
            with patch.object(check, "MIRROR", d), \
                 patch.object(check, "_probe", _never_probe):
                code = check.main([])
        assert code == check.UNVERIFIED, "порча %r ушла наружу кодом %r" % (kw, code)
    assert check.UNVERIFIED != 0, "код отказа обязан быть ненулевым"


def _never_probe(*a, **kw):
    raise AssertionError("проба пошла в сеть при нечитаемом зеркале")


def test_healthy_mirror_reaches_the_probe():
    """Близнец к предыдущему: здоровое зеркало доводит до пробы (fail-closed ≠ «всегда закрыто»)."""
    seen = {}

    def _probe(route, mirror):
        seen["route"], seen["version"] = route, mirror["version"]
        return check.OK

    with _mirror() as d:
        with patch.object(check, "MIRROR", d), patch.object(check, "_probe", _probe):
            code = check.main(["service_undo"])
    assert code == check.OK and seen == {"route": "service_undo", "version": 83}


# ───────────────────────── (3) выбор проверяемого маршрута ────────────────────

def test_route_from_argument_wins():
    r, note = check.pick_route("edit_event", ["ping"], ["ping"])
    assert r == "edit_event" and "аргумент" in note


def test_route_from_argument_even_if_mirror_does_not_know_it():
    """Именно этот случай и есть «проверяю свежий деплой»: зеркала он ещё не касался."""
    r, _ = check.pick_route("service_undo", ["ping"], None, "сборки нет")
    assert r == "service_undo"


def test_single_new_route_is_derived_from_build_minus_mirror():
    r, note = check.pick_route("", ["ping", "fleet"], ["ping", "fleet", "service_undo"])
    assert r == "service_undo" and "сборка минус зеркало" in note


def test_no_new_route_is_refused_not_guessed():
    """Сборка выложена и зеркало сведено — проверять нечего; молча брать чужой маршрут нельзя."""
    r, note = check.pick_route("", ["ping", "fleet"], ["ping", "fleet"])
    assert r is None and "нового маршрута нет" in note


def test_several_new_routes_are_refused_and_named():
    r, note = check.pick_route("", ["ping"], ["ping", "a_one", "b_two"])
    assert r is None and "a_one" in note and "b_two" in note


def test_missing_build_carries_its_own_reason():
    r, note = check.pick_route("", ["ping"], None, "в каталоге сборки нет роутера: X")
    assert r is None and note.endswith("роутера: X")


def test_build_routes_reads_real_folder():
    with _build() as d:
        r, why = check.build_routes(d)
    assert r == ["add_event", "fleet", "ping", "service_undo"] and why == ""


def test_build_without_router_is_none_not_empty():
    """None, а не []: пустой список сделал бы НОВЫМ каждый маршрут зеркала."""
    with _build(router=None) as d:
        r, why = check.build_routes(d)
    assert r is None and why


def test_build_with_unparsable_router_is_none_not_empty():
    with _build(router="// ни одной метки\n") as d:
        r, why = check.build_routes(d)
    assert r is None and "ни одного маршрута" in why


# ─────────────────────────── (4) вердикт несёт код ────────────────────────────

def test_no_ticket_means_route_is_live():
    code, say = check.verdict("no_ticket")
    assert code == check.OK == 0 and "ЕСТЬ" in say


def test_unknown_action_is_not_success():
    """Прежняя редакция печатала «маршрута НЕТ» и выходила кодом 0 — это и было тихое зелёное."""
    code, say = check.verdict("unknown_action")
    assert code == check.ROUTE_MISSING and code != 0 and "НЕТ" in say


def test_unexpected_answer_is_unverified_not_green():
    for err in (None, "", "boom", "rate_limited", 500):
        code, say = check.verdict(err)
        assert code == check.UNVERIFIED and code != 0, "ответ %r прошёл как успех" % (err,)
        assert "НЕ заявляю" in say


def test_three_outcomes_are_distinct():
    assert len({check.OK, check.ROUTE_MISSING, check.UNVERIFIED}) == 3


# ──────────────── (5) самообъявление моста: каждое с себе подобным ────────────

def test_declared_lists_are_both_taken_without_guessing():
    lists = check.declared_lists(ROUTER_JS)
    assert sorted(lists, key=len) == [GET_LIST, POST_LIST], "ветка угадывается, а не берётся"


def test_live_answer_matching_post_branch_is_clean():
    same, extra, missing = check.compare_declared(POST_LIST, check.declared_lists(ROUTER_JS))
    assert same is True and extra == [] and missing == []


def test_live_answer_matching_short_get_branch_is_clean_too():
    """Какая ветка ответит пробе — свойство ПРОБЫ; короткий список тоже законный ответ."""
    same, _, _ = check.compare_declared(GET_LIST, check.declared_lists(ROUTER_JS))
    assert same is True


def test_divergence_is_named_against_the_closest_list():
    live = ["add_event", "service_undo", "edit_event", "brand_new"]
    same, extra, missing = check.compare_declared(live, check.declared_lists(ROUTER_JS))
    assert same is False and extra == ["brand_new"] and missing == []


def test_mirror_behind_prod_is_named_as_missing():
    live = ["add_event", "service_undo"]          # прод объявляет меньше, чем зеркало
    same, extra, missing = check.compare_declared(live, check.declared_lists(ROUTER_JS))
    assert same is False and extra == [] and missing == ["edit_event"]


def test_mirror_declaring_nothing_is_third_outcome():
    """Сравнивать не с чем — это None, а не True: третий исход, как везде в этом файле."""
    same, extra, missing = check.compare_declared(["ping"], [])
    assert same is None and extra == [] and missing == []


def test_routes_and_declared_are_different_vocabularies():
    """89 меток против 67 имён — не расхождение, а разные словари; фикстура держит ту же форму."""
    routes = set(check.routes_in(ROUTER_JS))
    declared = set().union(*check.declared_lists(ROUTER_JS))
    assert routes != declared and (declared - routes), "фикстура перестала различать словари"


# ─────────────────── (6) снимков 04.08 нет, путь — от файла ───────────────────

def test_no_absolute_snapshot_paths_left():
    """Судим ЛИТЕРАЛ-ПУТЬ, а не слово: упоминание снятых снимков в прозе шапки — не находка.

    Тот же приём, что у `test_bridge_prod_mirror.test_gate_reads_mirror_not_the_folder`:
    флагуется строковая константа, которая ЦЕЛИКОМ есть абсолютный путь.
    """
    tree = ast.parse(open(SRC, encoding="utf-8").read())
    bad = [n.value for n in ast.walk(tree)
           if isinstance(n, ast.Constant) and isinstance(n.value, str)
           and re.match(r"^/root/\S+$", n.value)]
    assert not bad, "в модуле снова захардкожен абсолютный путь: %s" % bad


def test_paths_are_derived_from_the_file_itself():
    """Зеркало и сборка ищутся от каталога файла — репозиторий переносим, снимок нет."""
    assert check.ROOT == os.path.dirname(os.path.dirname(os.path.abspath(check.__file__)))
    assert check.MIRROR == os.path.join(check.ROOT, "bridge_prod")
    assert check.BUILD == os.path.join(check.ROOT, "bridge_build")


def test_passport_name_has_one_home():
    """Имя паспорта берётся у зеркала, а не переписывается здесь — две копии разъехались бы."""
    import mirror_sync
    assert check.PASSPORT == mirror_sync.PASSPORT_NAME


def test_bridge_client_is_imported_lazily():
    """Модуль обязан читаться БЕЗ сети и .env: клиент и dotenv — только внутри функций."""
    tree = ast.parse(open(SRC, encoding="utf-8").read())
    top = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            top += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            top.append(node.module or "")
    for forbidden in ("bridge_client", "dotenv"):
        assert forbidden not in top, "%s импортируется на уровне модуля — модуль не прочитать" % forbidden


def test_module_does_nothing_at_import_time():
    """На уровне модуля нет ни вызова main(), ни chdir: импорт не должен ходить в прод."""
    tree = ast.parse(open(SRC, encoding="utf-8").read())
    calls = [n for node in tree.body if isinstance(node, ast.Expr)
             for n in ast.walk(node) if isinstance(n, ast.Call)]
    named = [getattr(n.func, "id", getattr(n.func, "attr", "")) for n in calls]
    assert "main" not in named, "main() снова зовётся при импорте"
    assert "chdir" not in named, "chdir при импорте — тесты и соседи получат чужой cwd"


def test_tool_writes_nothing():
    """Власть инструмента строго читающая: ни записи в файл, ни удаления, ни подпроцесса."""
    src = open(SRC, encoding="utf-8").read()
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            name = getattr(n.func, "id", getattr(n.func, "attr", ""))
            assert name not in ("remove", "unlink", "rmtree", "run", "Popen", "system"), \
                "в читающем инструменте появился %s()" % name
            if name == "open":
                mode = [a.value for a in n.args[1:2] if isinstance(a, ast.Constant)]
                kw = [k.value.value for k in n.keywords
                      if k.arg == "mode" and isinstance(k.value, ast.Constant)]
                for m in mode + kw:
                    assert "w" not in m and "a" not in m, "open(..., %r) — инструмент пишет" % m
    assert "clasp" not in src.replace("clasp` не зовётся", ""), "появилось упоминание clasp-вызова"


# ─────────────────────────── (7) живое зеркало @83 ────────────────────────────

def test_live_mirror_is_judgeable_and_untouched():
    """Инструмент судит НАСТОЯЩЕЕ зеркало и не меняет его ни на байт (sha до и после)."""
    before = _dir_digest(check.MIRROR)
    f = check.mirror_facts()
    after = _dir_digest(check.MIRROR)
    assert after == before, "живое зеркало изменилось за прогон"
    assert f["ok"] is True, f["why"]
    assert isinstance(f["version"], int) and f["version"] >= 83
    assert len(f["routes"]) > 50, "маршруты живого роутера не разобрались: %d" % len(f["routes"])
    assert f["declared"], "живой роутер перестал объявлять действия"


def test_live_no_new_route_refuses_before_network():
    """Сквозной прогон по ЖИВОМУ зеркалу: нового маршрута нет — отказ кодом 2, сети не касаемся.

    Сборка подставлена фикстурой намеренно: живой каталог сборки меняется от захода к заходу,
    и тест не должен краснеть от чужой работы.
    """
    with patch.object(check, "build_routes", lambda *a, **kw: (["ping"], "")), \
         patch.object(check, "_probe", _never_probe):
        code = check.main([])
    assert code == check.UNVERIFIED


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS {name}")
        except Exception as e:
            print(f"  FAIL {name}: {e}")
            import traceback; traceback.print_exc()
            failed.append(name)
    print(f"\n{len(tests) - len(failed)}/{len(tests)} — {'ВСЕ PASS' if not failed else 'FAIL: ' + str(failed)}")
    sys.exit(0 if not failed else 1)
