# -*- coding: utf-8 -*-
"""ЗЕРКАЛО ПРОД-МОСТА И ЗАМОК ПАПКИ ВЫКЛАДКИ (заведено 10.08.2026).

Инцидент-класс: содержимого моста не было под версиями НИГДЕ, а единственная локальная копия —
рабочая папка инструмента выкладки `/root/turbobaby-bridge-gs` — расходилась с продом в обе
стороны. Замер 10.08.2026 на свежем отпечатке (прод @79): 13 файлов из 17 совпадали побайтно,
4 отставали; в папке 183 функции против 201 у прода и 88 маршрутов против 93 — заливка отсюда
стёрла бы 18 функций и 5 маршрутов ЖИВОГО моста молча.

Этот файл стережёт три вещи разом:
  (1) зеркало `bridge_prod/` не разошлось со своим паспортом `MIRROR.json` — то есть его не
      правили вместо прода (иначе «истина о проде» тихо станет фантазией);
  (2) зеркало не превратилось в каталог выкладки (в нём нет настроек проекта);
  (3) рабочая папка ОСТАЁТСЯ обезвреженной — настройки проекта из неё убраны, а указатель на
      месте. Вернули настройки на место — тест красный НАМЕРЕННО: папка не должна оставаться
      заряженной незаметно.
"""
import hashlib
import importlib.util
import json
import os
import re
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = os.path.join(ROOT, "bridge_prod")
PASSPORT = os.path.join(MIRROR, "MIRROR.json")
TOOL = os.path.join(ROOT, "deploy", "bridge_prod_diff.py")
GS = "/root/turbobaby-bridge-gs"
POINTER = "ЧИТАЙ_МЕНЯ_ПЕРЕД_ВЫКЛАДКОЙ.md"
SCRIPT_ID = "12iXPDU_wxcyslItPW6X41ODuoVxx2smmlQBfhSwI6Lt42MTrYbv9HhOJ"

_spec = importlib.util.spec_from_file_location("bridge_prod_diff", TOOL)
diff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diff)          # main() под __main__-стражем, импорт ничего не делает


def _sha(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _write(folder, name, text):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
        fh.write(text)


# ---------- (1) зеркало и его паспорт ----------

def test_mirror_exists_with_passport():
    """Зеркало заведено, паспорт читается и называет версию прода числом."""
    assert os.path.isdir(MIRROR), "нет зеркала bridge_prod/ — истина о проде опять нигде"
    m = json.load(open(PASSPORT, encoding="utf-8"))
    assert isinstance(m["prod_version"], int) and m["prod_version"] > 0
    assert m["script_id"] == SCRIPT_ID, "зеркало снято с ДРУГОГО проекта Apps Script"
    assert isinstance(m["head_equals_prod"], bool)
    assert m["files_sha256"], "паспорт без хешей ничего не стережёт"


def test_mirror_files_match_passport():
    """Каждый файл зеркала совпадает с паспортом, и состав совпадает в ОБЕ стороны.

    Ловит молчаливую правку зеркала «вместо прода»: подправил .js здесь — гейт красный.
    """
    m = json.load(open(PASSPORT, encoding="utf-8"))["files_sha256"]
    on_disk = {n for n in os.listdir(MIRROR)
               if os.path.isfile(os.path.join(MIRROR, n)) and n not in ("MIRROR.json", "README.md")}
    assert on_disk == set(m), (
        "состав зеркала разошёлся с паспортом: лишние %s, пропали %s"
        % (sorted(on_disk - set(m)), sorted(set(m) - on_disk)))
    bad = [n for n in sorted(m) if _sha(os.path.join(MIRROR, n)) != m[n]]
    assert not bad, "содержимое зеркала правили мимо паспорта: %s" % bad


def test_mirror_is_not_a_deploy_folder():
    """В зеркале НЕТ настроек проекта: оно ничего не заливает по устройству."""
    assert not os.path.exists(os.path.join(MIRROR, ".clasp.json")), \
        "в зеркале появились настройки проекта — оно стало вторым заряженным стволом"


# ---------- (2) чистое сравнение: на чём стоит команда «прод впереди?» ----------

def test_compare_identical_is_clean():
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        _write(a, "Bridge.js", "one")
        _write(b, "Bridge.js", "one")
        res = diff.compare(a, b)
        assert res["same"] == ["Bridge.js"]
        assert diff.is_clean(res)


def test_compare_changed_file_is_named():
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        _write(a, "Bridge.js", "one")
        _write(b, "Bridge.js", "one-плюс-правка")
        res = diff.compare(a, b)
        assert res["changed"] == ["Bridge.js"] and not diff.is_clean(res)


def test_compare_prod_ahead_is_named():
    """У живого моста есть файл, которого нет в зеркале — это и есть «прод впереди»."""
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        _write(a, "Bridge.js", "one")
        _write(b, "Bridge.js", "one")
        _write(b, "Newcomer.js", "чужая работа")
        res = diff.compare(a, b)
        assert res["only_live"] == ["Newcomer.js"] and not diff.is_clean(res)


def test_compare_mirror_only_file_is_named():
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        _write(a, "Bridge.js", "one")
        _write(a, "Gone.js", "у прода такого нет")
        _write(b, "Bridge.js", "one")
        res = diff.compare(a, b)
        assert res["only_mirror"] == ["Gone.js"] and not diff.is_clean(res)


def test_compare_ignores_local_only_files():
    """Паспорт и документация зеркала — местные, у Apps Script таких файлов нет по устройству.

    Голден живого прогона 10.08.2026: пока `README.md` участвовал в сверке, команда объявляла
    «прод впереди» ВСЕГДА — то есть не значила ничего. Ложная тревога, повторяющаяся каждый
    раз, ничем не лучше молчания: её перестают читать.
    """
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        _write(a, "Bridge.js", "one")
        _write(a, "MIRROR.json", "{}")
        _write(a, "README.md", "как пользоваться зеркалом")
        _write(b, "Bridge.js", "one")
        res = diff.compare(a, b)
        assert diff.is_clean(res), "местные файлы зеркала выдают себя за расхождение: %s" % res
        assert res["same"] == ["Bridge.js"]


def test_compare_still_sees_real_js_divergence_next_to_docs():
    """Исключение местных файлов не должно глушить НАСТОЯЩЕЕ расхождение рядом с ними."""
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        _write(a, "README.md", "документация")
        _write(a, "Bridge.js", "one")
        _write(b, "Bridge.js", "one-правка-прода")
        res = diff.compare(a, b)
        assert res["changed"] == ["Bridge.js"] and not diff.is_clean(res)


def test_tool_says_nothing_when_it_cannot_look():
    """Отпечаток не снят → код 2 «не заявляю», а не 0 «всё совпадает» (fail-safe в молчание)."""
    src = open(TOOL, encoding="utf-8").read()
    assert "return 2" in src and "не заявляю" in src
    assert 'open(' not in src.replace('open(os.path.join(MIRROR, META), encoding="utf-8")', '') \
        or '"w"' not in src, "инструмент сверки обязан оставаться читающим"


# ---------- (3) замок рабочей папки ----------

def test_bridge_gs_is_disarmed():
    """Из рабочей папки проект НЕ разрешается: настроек нет, но они и не потеряны.

    Красный тест здесь означает ровно одно: папка снова заряжена. Лечится возвратом имени
    `.clasp.json` → `.clasp.json.DISARMED-<дата>`, а не правкой теста.
    """
    if not os.path.isdir(GS):
        return  # чужая машина (полоса ПК) — судить не о чем
    assert not os.path.exists(os.path.join(GS, ".clasp.json")), (
        "рабочая папка снова заряжена: из неё возможна заливка, которая сотрёт прод "
        "(замер 10.08.2026: папка отставала на 18 функций и 5 маршрутов)")
    saved = [n for n in os.listdir(GS) if n.startswith(".clasp.json.")]
    assert saved, "настройки проекта не переименованы, а ПОТЕРЯНЫ — так не обезвреживают"


def test_bridge_gs_has_pointer():
    """Указатель на месте: пришедший в папку узнаёт, откуда теперь выкладывать."""
    if not os.path.isdir(GS):
        return
    p = os.path.join(GS, POINTER)
    assert os.path.isfile(p), "нет указателя %s — папка молчит о том, что обезврежена" % POINTER
    text = open(p, encoding="utf-8").read()
    for must in ("bridge_prod", "bridge_prod_diff.py", "DISARMED"):
        assert must in text, "указатель не называет главного: %s" % must


# ---------- (4) гейт читает ЗЕРКАЛО, а не обезвреженную папку ----------

def test_gate_reads_mirror_not_the_folder():
    """Ни один тест гейта не открывает .js ИЗ рабочей папки (заведено 10.08.2026).

    Класс: харнессы и .js-тесты исполняли код из `/root/turbobaby-bridge-gs`, а он отстаёт от
    прода (замер того же дня: 4 файла из 17, у Bridge.js нет 4 маршрутов и `edit_event`) — гейт
    зеленел на коде, которого в мосте уже нет. Источник .js теперь один: зеркало `bridge_prod/`.

    Судим ПУТЬ, а не слово: флагуется строковый литерал, который ЦЕЛИКОМ есть путь в папку —
    кавычка, сразу путь, без пробелов внутри (так тест называет и файл `.../Booking.js`, и
    каталог-префикс `.../` — оба живых способа туда сходить). Имя папки в прозе комментария и
    внутри команды-фикстуры (`rm -rf …`, `node --check …`) путём-литералом не является и не
    флагуется: фикстура папку НЕ открывает.

    ЕДИНСТВЕННОЕ исключение — константа ЭТОГО файла, равная корню папки: здесь папка сама
    предмет (замок «обезврежена»), и открывают в ней не код, а настройки проекта. Любой другой
    литерал даже здесь — находка.
    """
    lit = re.compile(r"""['"](/root/turbobaby-bridge-gs[^'"\s]*)['"]""")
    tests_dir = os.path.join(ROOT, "tests")
    bad = []
    for name in sorted(os.listdir(tests_dir)):
        if not (name.endswith(".py") or name.endswith(".js")):
            continue
        with open(os.path.join(tests_dir, name), encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
        for m in lit.finditer(src):
            if name == os.path.basename(__file__) and m.group(1) == GS:
                continue                       # замок папки: её корень, а не путь к коду
            bad.append("%s:%d → %s" % (name, src[:m.start()].count("\n") + 1, m.group(0)))
    assert not bad, (
        "тест гейта открывает .js из обезвреженной папки: " + "; ".join(bad) +
        " — источник один, зеркало bridge_prod/ (лечится путём, а не правкой этого теста)")


def test_harnesses_name_the_mirror():
    """Каждый node-харнесс называет зеркало — проверка не только «нет старого», но и «есть новое»."""
    tests_dir = os.path.join(ROOT, "tests")
    harnesses = [n for n in sorted(os.listdir(tests_dir)) if n.endswith("_harness.js")]
    assert harnesses, "харнессы пропали — проверять нечего, это тоже находка"
    for name in harnesses:
        with open(os.path.join(tests_dir, name), encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
        assert "bridge_prod" in src, "%s не называет зеркало прода" % name


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("  ✓ %s" % fn.__name__)
    print("OK — %d тестов bridge_prod_mirror" % len(fns))
