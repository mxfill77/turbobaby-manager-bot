# -*- coding: utf-8 -*-
"""ОТМЕНА ЗАПИСИ ТО: память о вытеснении + дверь возврата по ссылке на акт (22.08.2026).

ЧЕГО НЕ БЫЛО. Регистры ТО (Лист1 «Байки»: I масло · J редуктор · K ABS · L фильтр) мост умел
поднимать и не умел понижать: сторож `km_decreasing`/`oil_decreasing` называет себя «Защита от
отката» и смотрит РОВНО в одну сторону. Разбор 22.08 (docs/artifacts/2026-08-22-bridge-lower-registers.md)
намерил: за 82 суток сторож не отверг НИ ОДНОЙ записи, а понижение понадобилось дважды и оба
раза как ОТМЕНА ошибки — 15.07 масло 24997 вместо 24500 и 22.08 кол.J 41641, которую вернули
РУКОЙ. Признака, отличающего отмену от скрутки, у моста не было ни одного: `fix_reason`/`fixed_by`
заполняет сам вызывающий, `trusted` мост проверить не может (и говорит это о себе дословно),
билет токен-замка не связан ни с байком, ни с колонкой, ни с числом.

ПРИЗНАК, КОТОРЫЙ ЗДЕСЬ ПРОВЕРЯЕТСЯ, — НЕ СЛОВА, А ПАМЯТЬ И СЛИЧЕНИЕ:
  · наружу число вниз дверь НЕ ПРИНИМАЕТ ВОВСЕ — только ссылку на акт; прежнее значение мост
    достаёт из своей памяти (строки боевого журнала, написанной им же в момент вытеснения);
  · отмена идёт, только если в клетке ДО СИХ ПОР ровно то число, которое записал акт, И
    возвращается ровно вытесненное им; клетку тронула чужая рука — отказ и зов владельца;
  · только последняя запись по паре «байк × колонка»; отмена отмены запрещена;
  · каждый откат сам ложится в журнал — след РАСТЁТ, а не переписывается;
  · возвращаются ОБЕ базы (живой Лист1 и зеркало «обслуживание»); вторая не вернулась — отказ
    ЦЕЛИКОМ с компенсацией первой, а не частичный успех (живьём по 5960 половинчатый возврат
    рукой оставил расхождение 284 км в ОПАСНУЮ сторону, и само оно не срастётся).

ГДЕ ЖИВЁТ КОД. Править `bridge_prod/` НЕЛЬЗЯ — это ЗЕРКАЛО задеплоенной версии под паспортом
`MIRROR.json`, и замок `tests/test_bridge_prod_mirror.py` краснеет на любой правке (иначе «истина
о проде» тихо станет фантазией). Поэтому стройка лежит в КАТАЛОГЕ СБОРКИ ЗАХОДА `bridge_build/`
поверх базы @79, а node-харнесс исполняет живой код ОТТУДА, добирая из зеркала файлы, которых
сборка не трогала. Выкладки в этом заходе НЕТ.

Красные литералы имён операций собраны конкатенацией — иначе гард краснеет на самом файле теста
(образец: tests/test_record_fix.py).
"""
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys

os.environ["PRETOOL_NOPUSH"] = "1"
os.environ.setdefault("ORCH_TEST_MODE", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
MIRROR = os.path.join(ROOT, "bridge_prod")
BUILD = os.path.join(ROOT, "bridge_build")
HARNESS = os.path.join(HERE, "undo_door_harness.js")

sys.path.insert(0, ROOT)
# Различитель «версия названа числом» берём У МАШИНЫ СВЕДЕНИЯ, а не пишем свой: второго
# способа сказать одно и то же не заводим (mirror_sync чист — импортов у него ноль).
from mirror_sync import _is_num                                        # noqa: E402

# имена операций собираем из кусков: файл теста читает гард, а целые литералы делают его красным
A_OIL = "set_fleet_" + "oil"
A_SVC = "set_fleet_" + "service"
A_UNDO = "service_" + "undo"

# Стражи писателей, которые заход НЕ ослаблял ни на строку. Число вхождений в сборке обязано
# совпасть с зеркалом: пропало — значит забор сняли.
GUARDS = ("oil_decreasing", "km_decreasing", "oil_drop_needs_trusted", "audit_failed",
          "not_confirmed", "verify_failed", "OIL_FIX_TRUSTED_DROP", "rolled_back",
          "bad_kind", "bad_oil_km", "bad_km", "missing_number", "ambiguous")

_cache = {}


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _run_harness():
    if "res" not in _cache:
        p = subprocess.run(["node", HARNESS], capture_output=True, text=True, timeout=120)
        assert p.stdout.strip(), "харнесс не напечатал JSON:\nstdout=%s\nstderr=%s" % (p.stdout, p.stderr)
        _cache["res"] = json.loads(p.stdout)
        _cache["code"] = p.returncode
    return _cache["res"]


# ─────────────────────────── (1) харнесс на живом коде ───────────────────────────

def test_harness_all_green():
    """Каждая проверка харнесса зелёная; иначе — поимённо, что упало."""
    res = _run_harness()
    bad = [c for c in res["cases"] if not c["pass"]]
    assert not bad, "провалы харнесса отмены:\n" + "\n".join(
        "  %s | %s" % (c["name"], c["detail"][:300]) for c in bad)
    assert _cache["code"] == 0, "харнесс вернул ненулевой код при зелёных проверках"
    assert len(res["cases"]) >= 100, "проверок стало подозрительно мало: %d" % len(res["cases"])


def test_five_named_negatives_are_present():
    """ПЯТЬ названных заданием отрицательных случаев есть, и каждый — про ОТКАЗ двери.

    Отрицательный тест, который зеленеет сам по себе, не стоит ничего: рядом с каждым живёт
    БЛИЗНЕЦ (тот же сценарий без порчи проходит), поэтому отказ доказанно вызван именно ею.
    """
    res = _run_harness()
    names = [c["name"] for c in res["cases"]]
    need = {
        "скрутка под видом отмены": "НЕГ.скрутка.",
        "клетку между делом изменил третий": "НЕГ.третий.",
        "отмена не последней записи": "НЕГ.непоследняя.",
        "отмена отмены": "НЕГ.отмена-отмены.",
        "вторая база недоступна на середине": "НЕГ.вторая-база.",
    }
    for human, prefix in need.items():
        assert any(n.startswith(prefix) for n in names), "нет отрицательного случая «%s»" % human
    assert res["negatives"] >= 20, "отрицательных проверок всего %d" % res["negatives"]
    for twin in ("undo.третий.близнец-проходит", "undo.последняя-проходит",
                 "undo.первая-отмена-ok", "undo.после-починки-проходит",
                 "undo.след-отмены.близнец-проходит"):
        assert twin in names, "у отрицательного случая пропал близнец: %s" % twin


# ─────────────── (2) зеркало несёт дверь, потому что её несёт ПРОД ───────────────

def test_mirror_carries_the_deployed_door():
    """У ЗАДЕПЛОЕННОЙ версии дверь отмены ЕСТЬ — значит она обязана быть и в зеркале.

    ИСТОРИЯ ПРЕМИСЫ (важно, иначе тест снова протухнет молча). До 23.08.2026 здесь стояло
    обратное утверждение — «у прода двери нет вовсе, это и есть замер „до правки“». Оно было
    верным ровно до выкладки: владелец выложил сборку захода 23.08.2026 06:40 UTC как @83, и
    премиса умерла вместе с @79. Тот же класс, что описан в CLAUDE.md («утверждение о состоянии
    не живёт без способа его проверить»), только пойманный не документом, а гейтом — тест
    покраснел, как и должен был. Разбор: docs/artifacts/2026-08-23-bridge-mirror-sync.md.

    ЗАЧЕМ ЭТОТ ТЕСТ ТЕПЕРЬ — он и есть противомина. Зеркало @79 не знало двери, а прод её уже
    обслуживал: следующая сборка, взяв базой такое зеркало, стёрла бы дверь МОЛЧА. Пропади
    ServiceUndo.js или зов памяти из зеркала снова — здесь красное.

    Чего этот тест НЕ доказывает: что зеркало не правили руками вместо сборки. Это отдельный
    замок и он не ослаблен — tests/test_bridge_prod_mirror.py::test_mirror_files_match_passport
    сверяет каждый байт зеркала с паспортом MIRROR.json.
    """
    assert os.path.exists(os.path.join(MIRROR, "ServiceUndo.js")), \
        "в зеркале нет модуля отмены, а прод его обслуживает — зеркало отстало от прода"
    fleet = _read(os.path.join(MIRROR, "ReadFleet.js"))
    bridge = _read(os.path.join(MIRROR, "Bridge.js"))
    assert fleet.count("undoRemember_(") == 2, \
        "в зеркале память о вытеснении стоит не у обоих писателей: %d" % fleet.count("undoRemember_(")
    assert "serviceUndo_(body)" in bridge and ("case '%s':" % A_UNDO) in bridge, \
        "в зеркале нет маршрута отмены, хотя прод его знает"
    # аудит-след исправления масла — прежний, фейл-клоузд, ОДИН зов: выкладка его не размножила
    assert fleet.count("logWrite_(") == 1, \
        "аудит-след исправления в зеркале задет: зовов %d" % fleet.count("logWrite_(")


def test_mirror_fingerprint_knows_the_door():
    """Отпечаток, который мост печатает на неизвестное действие, в зеркале ТОТ ЖЕ, что у прода.

    По этому списку сверяют, что реально задеплоено (CLAUDE.md, «отпечаток прода обязателен
    перед push»). Живой замер 23.08.2026: прод отдал 67 действий, среди них дверь отмены;
    зеркало @79 несло 66 и о двери молчало. Число здесь не хардкодим — сверяем СОСТАВ зеркала
    со сборкой, а живую сверку с мостом делает deploy/bridge_prod_diff.py (ему нужна сеть,
    в гейте её нет).
    """
    mir = _read(os.path.join(MIRROR, "Bridge.js"))
    bld = _read(os.path.join(BUILD, "Bridge.js"))
    def post_list(src):
        blocks = [b.split("]")[0] for b in src.split("actions: [")[1:]]
        post = [b for b in blocks if ("'%s'" % A_OIL) in b]
        assert post, "в отпечатке не нашёлся список действий POST"
        return sorted(re.findall(r"'([^']+)'", post[0]))
    m, b = post_list(mir), post_list(bld)
    assert A_UNDO in m, "отпечаток зеркала молчит о двери отмены, а прод о ней говорит"
    assert m == b, "отпечаток зеркала разошёлся со сборкой: %s" % (set(m) ^ set(b))


def test_build_remembers_every_register_write():
    """В сборке память о вытеснении стоит у ОБОИХ писателей регистра, а не у одного."""
    fleet = _read(os.path.join(BUILD, "ReadFleet.js"))
    assert fleet.count("undoRemember_(") == 2, \
        "память о вытеснении стоит не у обоих писателей: %d" % fleet.count("undoRemember_(")
    # прежний, фейл-клоузд аудит-след исправления не тронут: как был один зов, так и остался
    assert fleet.count("logWrite_(") == 1, "аудит-след исправления задет"
    body_oil = fleet.split("function setFleetOil_")[1].split("function setFleetService_")[0]
    body_svc = fleet.split("function setFleetService_")[1]
    assert "undoRemember_(" in body_oil, "масло не помнит вытеснения"
    assert "undoRemember_(" in body_svc, "J/K/L не помнят вытеснения"


# ─────────────── (3) граница устройством: числа снаружи дверь не читает ───────────────

def test_door_reads_only_the_act_reference():
    """`serviceUndo_` берёт из тела запроса РОВНО три поля: ссылку, автора, подтверждение.

    Это и есть признак против скрутки, выраженный устройством: числа снаружи двери прочитать
    НЕЧЕМ, поэтому произвольное значение в клетку попасть не может физически.
    """
    src = _read(os.path.join(BUILD, "ServiceUndo.js"))
    door = src.split("function serviceUndo_(")[1]
    fields = set(re.findall(r"\bp\.([A-Za-z_][A-Za-z0-9_]*)", door))
    assert fields == {"act", "by", "confirmed"}, \
        "дверь читает из тела запроса лишнее: %s" % sorted(fields)


def test_door_touches_only_fleet_and_its_own_mirror():
    """Дверь пишет в Лист1 парка и в своё зеркало — и больше никуда; ничего не удаляет."""
    src = _read(os.path.join(BUILD, "ServiceUndo.js"))
    for foreign in ("SHEETS.MANAGER", "SHEETS.SALARY", "SHEETS.PRICES"):
        assert foreign not in src, "дверь отмены полезла в чужую таблицу: %s" % foreign
    for killer in ("deleteRow", "deleteRows", "deleteSheet", "clear("):
        assert killer not in src, "у двери отмены появилось удаление: %s" % killer
    # ровно две записи в клетку: возврат и компенсация. Третьей быть не должно.
    assert src.count(".setValue(") == 2, \
        "записей в клетку в двери стало %d — назови каждую" % src.count(".setValue(")


def test_route_and_lock_are_wired_in_build():
    """Маршрут заведён, замок агент-записи его накрывает, отпечаток прода о нём скажет."""
    bridge = _read(os.path.join(BUILD, "Bridge.js"))
    assert ("case '%s':" % A_UNDO) in bridge, "маршрута отмены нет"
    assert "serviceUndo_(body)" in bridge, "маршрут не зовёт дверь"
    for neighbour in (A_OIL, A_SVC):                 # соседние двери записи на месте
        assert ("case '%s':" % neighbour) in bridge, "пропал маршрут %s" % neighbour
    lock = bridge.split("var REDZONE_LOCK = {")[1].split("};")[0]
    assert ("%s: 1" % A_UNDO) in lock, "отмена не под токен-замком агент-записей"
    # Отпечаток прода — список `actions` в ответе на НЕсуществующее действие; по нему сверяют,
    # что реально задеплоено (CLAUDE.md, «отпечаток прода обязателен перед push»). Списков в
    # файле два (GET и POST); нам нужен ТОТ, где живут двери записи регистра.
    blocks = [b.split("]")[0] for b in bridge.split("actions: [")[1:]]
    post = [b for b in blocks if ("'%s'" % A_OIL) in b]
    assert post, "в отпечатке не нашёлся список действий POST"
    assert ("'%s'" % A_UNDO) in post[0], \
        "отпечаток прода промолчит о новой двери — а по нему сверяют, что задеплоено"


# ─────────────── (4) прежние стражи писателей не ослаблены ───────────────

def test_writers_guards_survive_byte_for_byte():
    """Каждый страж писателей встречается в сборке столько же раз, сколько в зеркале."""
    mir = _read(os.path.join(MIRROR, "ReadFleet.js"))
    bld = _read(os.path.join(BUILD, "ReadFleet.js"))
    bad = [(g, mir.count(g), bld.count(g)) for g in GUARDS if mir.count(g) != bld.count(g)]
    assert not bad, "стражи писателей изменились: %s" % bad
    # новых записей в живую таблицу у писателей не появилось
    assert mir.count(".setValue(") == bld.count(".setValue("), \
        "у писателей стало другое число записей в клетку: %d → %d" % (
            mir.count(".setValue("), bld.count(".setValue("))


def test_diff_from_mirror_removes_no_guard_line():
    """Ни одна СНЯТАЯ строка не несёт стража: сборка добавляет, а не вырезает."""
    for name in ("ReadFleet.js", "Bridge.js"):
        mir = _read(os.path.join(MIRROR, name)).splitlines()
        bld = _read(os.path.join(BUILD, name)).splitlines()
        removed = [l for l in difflib.unified_diff(mir, bld, lineterm="", n=0)
                   if l.startswith("-") and not l.startswith("---")]
        for line in removed:
            for g in GUARDS:
                assert g not in line, "%s: снята строка со стражем %s → %s" % (name, g, line[:120])


# ─────────────── (5) каталог сборки: паспорт, база, не заряженный ствол ───────────────

def test_build_passport_matches_the_mirror_base():
    """У каталога сборки ТРИ состояния, и в каждом сверяется своё.

    (а) НЕ ВЫЛОЖЕН — база сборки обязана быть тем самым продом @N, что лежит в зеркале.
        Съехала — пересобирать поверх свежего прода. Это прежний замок, он не тронут.

    (б) ВЫЛОЖЕН (в паспорте есть `delivered_as_version`), и зеркало описывает ТУ ЖЕ версию —
        сверяется утверждение СИЛЬНЕЕ: содержимое сборки обязано совпасть с зеркалом побайтно,
        то есть «мы выложили ровно то, что построили, и зеркало это подтверждает».

    Почему понадобилось (б), 23.08.2026: сборку выложили как @83, зеркало свели к проду — и
    база @79 законно разошлась с зеркалом @83. Прежняя ветка требовала «пересобрать», но
    пересобирать нечего: дельта уже в проде. Состояние «выложено» автор просто не моделировал
    («Выкладки в этом заходе НЕТ» — шапка этого файла).

    (в) ВЫЛОЖЕН, а прод С ТЕХ ПОР УЕХАЛ ДАЛЬШЕ — заведено 06.09.2026. Живой случай: сборка
        выложена как @83 (23.08), 02.09 ЧУЖОЙ заход выложил @84 (маршрут `list_brain_folder`),
        и после сведения зеркала ветка (б) закричала «в проде НЕ то, что построено» — хотя в
        проде именно то, просто СВЕРХУ легла чужая работа. Это ложное красное, и оно стоило
        дорого: pre-push отбивал ЛЮБУЮ отправку с сервера, пока расхождение не сведено.
        Сверять выкладку с ТЕКУЩИМ зеркалом здесь нельзя ПО УСТРОЙСТВУ: состояния @83 в
        репозитории больше нет, оно ушло в историю git (зеркало @83 нёс коммит `1583609`).
        Поэтому судится то, что проверяемо, — и это и есть ЗУБЫ замка.

    ЗУБЫ (сильнее прежних, и они на БАЙТАХ, а не на числах паспорта): выложенная сборка с тех
    пор НЕ МЕНЯЛАСЬ — каждый её `.js` побайтно равен своему же `build_sha256`, и паспорт знает
    ровно те файлы, что лежат в каталоге. Начал строить здесь новое — обязан снять
    `delivered_as_version` и объявить свежую базу, иначе ветка (а) потребует «база == зеркало».

    Направление сомнения — в красное: зеркало МЛАДШЕ выкладки (прод откатили или зеркало
    отстало) → красное всегда; версия названа не числом → тоже красное (тот же различитель
    `mirror_sync._is_num`, которым живёт машина сведения: строка «83» версией не является).
    """
    meta = json.load(open(os.path.join(BUILD, "BUILD.json"), encoding="utf-8"))
    mirror = json.load(open(os.path.join(MIRROR, "MIRROR.json"), encoding="utf-8"))
    assert meta["script_id"] == mirror["script_id"]
    assert set(meta["changed"]) == {"Bridge.js", "ReadFleet.js"}
    assert meta["added"] == ["ServiceUndo.js"]

    delivered = meta.get("delivered_as_version")
    if delivered is None:
        assert meta["base_prod_version"] == mirror["prod_version"]
        for name, sha in meta["base_sha256"].items():
            assert mirror["files_sha256"].get(name) == sha, \
                "база сборки разошлась с зеркалом по %s — собери заново поверх свежего прода" % name
        return

    prod = mirror["prod_version"]
    assert _is_num(delivered) and _is_num(prod), (
        "версия названа не числом (сборка @%r, зеркало @%r) — судить не на чем"
        % (delivered, prod))
    assert prod >= delivered, (
        "сборка выложена как @%s, а зеркало описывает @%s — зеркало ОТСТАЛО от прода "
        "(или прод откатили): сведи зеркало к проду" % (delivered, prod))

    # Выложенная сборка не меняется. Проверяется по БАЙТАМ файлов, а не по числам паспорта:
    # правка в каталоге выкладки после выкладки — это либо стройка нового без снятого
    # `delivered_as_version`, либо тихая подмена того, о чём паспорт утверждает «выложено».
    js = sorted(n for n in os.listdir(BUILD) if n.endswith(".js"))
    assert set(js) == set(meta["build_sha256"]), (
        "каталог сборки и его паспорт называют разные файлы: %s"
        % sorted(set(js) ^ set(meta["build_sha256"])))
    for name in js:
        with open(os.path.join(BUILD, name), "rb") as fh:
            got = hashlib.sha256(fh.read()).hexdigest()
        assert got == meta["build_sha256"][name], (
            "сборка изменилась после выкладки по %s: либо здесь строят новое, не сняв "
            "delivered_as_version (объяви свежую базу поверх зеркала @%s), либо паспорт "
            "врёт о выложенном" % (name, prod))

    if prod == delivered:                                    # (б) зеркало описывает ТУ выкладку
        for name, sha in meta["build_sha256"].items():
            assert mirror["files_sha256"].get(name) == sha, (
                "выложенная сборка разошлась с зеркалом по %s: в проде НЕ то, что построено "
                "(либо сборку правили после выкладки, либо зеркало сведено не к тому проду)"
                % name)
        return

    # (в) прод ушёл дальше выкладки. Утверждение «в проде ровно наша дельта» стало ИСТОРИЕЙ и
    # текущим зеркалом не проверяется — сказано прямо, чтобы зелёное здесь не читалось как
    # «выкладка сверена». Что сверено: сборка не тронута с тех пор (выше, по байтам).
    assert prod > delivered


def test_build_is_not_a_deploy_folder():
    """В каталоге сборки НЕТ настроек проекта: заряженного ствола в репозитории не заводим."""
    assert not os.path.exists(os.path.join(BUILD, ".clasp.json")), \
        "в каталоге сборки появились настройки проекта — из него стало возможно залить прод"


def test_built_js_is_syntactically_valid():
    """Каждый файл сборки проходит node --check: выкладывать неразбираемое нельзя."""
    for name in sorted(n for n in os.listdir(BUILD) if n.endswith(".js")):
        p = subprocess.run(["node", "--check", os.path.join(BUILD, name)],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, "%s не разбирается: %s" % (name, (p.stderr or p.stdout)[:300])


def test_fixtures_use_invented_bikes_only():
    """Байки фикстур ВЫДУМАНЫ: живых номеров парка в харнессе нет ни одного.

    Заход прямо запрещал трогать 5960 (приёмочный случай следующего захода), а на живых номерах
    легко получить голден, который завтра станет неверным вместе с парком.
    """
    src = _read(HARNESS)
    plates = set(re.findall(r"'ТЕСТ[^']*?(\d{4,})'", src))
    assert plates, "в харнессе не осталось выдуманных байков — проверять нечего"
    for p in plates:
        assert p.startswith("90"), "номер %s не похож на выдуманный" % p
    # Судим КОД, а не прозу: имя живого случая в комментарии данными не является и в мок-лист
    # не попадает (то же правило позиции, что у замка папки выкладки).
    code = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    code = "\n".join(re.sub(r"//.*$", "", ln) for ln in code.splitlines())
    assert "5960" not in code, "живой байк 5960 попал в код харнесса — заход запрещал его трогать"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("  ✓ %s" % fn.__name__)
    r = _run_harness()
    print("OK — %d тестов; харнесс: %d проверок, отрицательных %d"
          % (len(fns), len(r["cases"]), r["negatives"]))
