"""ИЗОЛЯЦИЯ ПРОБ (класс «проба рождает владельцу боевую карточку», 01.08.2026).

ЧТО ЗА КЛАСС. Пять заходов подряд (117, 135, 140, 142, 143) умерли одинаково: задача, ЧИНИВШАЯ
изоляцию проб, сама рождала владельцу боевую красную карточку из собственной пробы — 142 и 143
дословно одинаковы («ТО масло в Лист1 Байки колонка I, байк 6789, пробег 27000»; такого байка в
парке нет, это фикстура). Дефект блокировал собственный фикс. Требование «работай в тест-режиме»
в тексте ТЗ не помогало, потому что ручкой оно не является.

ТРИ КОРНЯ, каждый закреплён здесь отдельной секцией:
  (1) К владельцу вели ДВА канала с РАЗНЫМИ признаками пробы, и ни один признак не накрывал оба:
      прямой пуш слушал PRETOOL_NOPUSH/_is_test_script, а маркер → демон → карточка с кнопками
      не слушал НИЧЕГО и писался безусловно. Проба, объявленная «правильно», всё равно уходила
      владельцу — вторым каналом.
  (2) Внутри живой headless-задачи демон СНИМАЕТ тест-флаги с окружения ребёнка (намеренно), и у
      пробы не оставалось НИ ОДНОГО способа сказать «я проба»: окружение ей не принадлежит.
  (3) Правило 23.07 «сущность без пометки ТЕСТ → жёсткий блок» искало поле `plate=`, которого у
      живого Bridge нет вовсе (там `number=`), поэтому по байкам не срабатывало НИКОГДА, и
      фикстура уезжала в мягкую ветку — прямиком в карточку владельцу.

ФОРМАТ ЗАПУСКА повторяет боевой (правило «проверка повторяет живой формат»): хук зовётся
ПОДПРОЦЕССОМ через stdin-JSON, а окружение ребёнка строится как у демона — тест-флаги СНЯТЫ.
Анализируемая команда пишется в ЖИВОЙ форме `venv/bin/python3 <файл>` — именно её видит хук в бою,
и именно её распознаёт его детектор интерпретатора (_is_python). Хук команду НЕ исполняет: он
читает СОДЕРЖИМОЕ файла-цели, поэтому подстановка настоящего интерпретатора не только не нужна,
но и увела бы формат от живого. Сети нет: пуш диверсится в мок-счётчик NOTIFY_COUNT_FILE, который
отрабатывает ДО токена и до сети.

Красные маркеры собраны ИЗ КУСКОВ — гард сканирует содержимое запускаемого файла, литерал в
исходнике заблокировал бы сам тест (та же техника, что в tests/test_guard_тест_entity.py).
"""
import os
import sys
import json
import shutil
import tempfile
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
import pretool_guard as G                                            # noqa: E402

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return c


_SFO = "set_fleet_" + "oil"
_CB = "create_" + "booking"
_AT = "add_trans" + "action"
_DE = "delete_" + "event"
T = "ТЕСТ"

LIVE_OIL = "bridge.%s(number='6789', oil_km=27000)" % _SFO           # живой формат поля Bridge
TEST_BOOK = "bridge.%s(bike='6789', name='%s Иван')" % (_CB, T)      # ТЕСТ-сущность write-смока
MONEY = "bridge.%s(amount=500, wallet='main')" % _AT                 # деньги: сущности не несут


def _clean_child_env(**extra):
    """Окружение ребёнка КАК У ДЕМОНА в бою: тест-флаги сняты (child_env.pop у orchestrator_daemon).
    Именно в этом окружении проба и была неотличима от боевой команды."""
    e = dict(os.environ)
    for k in ("PRETOOL_TEST_RUN", "ORCH_TEST_MODE", "PRETOOL_NOPUSH", "PYTEST_CURRENT_TEST"):
        e.pop(k, None)
    e["PYTHONIOENCODING"] = "utf-8"
    e.update(extra)
    return e


def _run_hook(cmd, env):
    """Прогнать ХУК подпроцессом ровно как движок: stdin-JSON события PreToolUse."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": ROOT})
    p = subprocess.run([sys.executable, os.path.join(ROOT, "pretool_guard.py")],
                       input=payload, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=60)
    return p.stdout or ""


PY = "venv/bin/python3"          # ЖИВАЯ форма вызова, как её видит хук в бою (он её не исполняет)


def _fx(path):
    """Путь фикстуры в команду: прямые слэши. shlex (POSIX-режим, им хук и разбирает команду)
    трактует обратный слэш как экранирование — на Windows-прогоне путь иначе рассыпался бы."""
    return path.replace("\\", "/")


def _decision_of(out):
    try:
        return json.loads(out.strip().splitlines()[-1])["hookSpecificOutput"]["permissionDecision"]
    except Exception:
        return "(нет решения)"


# ─────────────── (1) ЕДИНЫЙ ПРИЗНАК ПРОБЫ: три источника, одна ручка ───────────────
print("(1) единый признак пробы — три источника, и текст пометкой НЕ является:")
_LIVE_ENV = {}
ok(G.is_probe("venv/bin/python3 fx.py", _LIVE_ENV) is False,
   "боевая команда в боевом окружении — не проба")
ok(G.is_probe("venv/bin/python3 fx.py", {"ORCH_TEST_MODE": "1"}) is True,
   "источник 1: тест-флаг в ОКРУЖЕНИИ хука (гейт, тест-подпроцессы)")
ok(G.is_probe("PRETOOL_TEST_RUN=1 venv/bin/python3 fx.py", _LIVE_ENV) is True,
   "источник 2: env-префикс В САМОЙ КОМАНДЕ — единственный доступный пробе внутри живой задачи")
ok(G.is_probe("ORCH_TEST_MODE=1 venv/bin/python3 -c 'x'", _LIVE_ENV) is True,
   "источник 2 работает и для inline `-c`, где файла .py нет вовсе")
ok(G.is_probe("venv/bin/python3 fx_test.py", _LIVE_ENV) is True,
   "источник 3: тест-скрипт по имени (прежняя эвристика)")
ok(G.is_probe("venv/bin/python3 /tmp/tb_scratch/recon.py", _LIVE_ENV) is True,
   "источник 3: каталог разведки R17 /tmp/tb_scratch")
ok(G.is_probe("echo PRETOOL_TEST_RUN=1 — это просто текст", _LIVE_ENV) is False,
   "УПОМИНАНИЕ имени в тексте пометкой НЕ является (иначе пометкой стал бы любой пересказ)")
ok(G.is_probe("venv/bin/python3 fx.py PRETOOL_TEST_RUN=1", _LIVE_ENV) is False,
   "присваивание ПОСЛЕ команды — не env-префикс, пометкой не считается")


# ─────────────── (2) ОБА КАНАЛА СЛУШАЮТ ОДИН И ТОТ ЖЕ ПРИЗНАК ───────────────
print("(2) изоляция накрывает ОБА канала владельца одним признаком:")
G.set_probe(False)
ok(G.isolated({}) is False, "бой: изоляции нет (маркер боевой, пуш идёт)")
ok(G.block_dir({}) == G.GUARD_BLOCK_DIR, "бой: каталог маркеров БОЕВОЙ")
ok(G.marker_name("142", {}) == "142.json", "бой: имя маркера прежнее (демон его увидит)")
G.set_probe(True)
try:
    ok(G.isolated({}) is True, "проба: латч взведён — изоляция включена БЕЗ участия окружения")
    ok(G.block_dir({}) == G.TEST_BLOCK_DIR, "канал 2: каталог маркеров уведён в тест-канал")
    ok(G.marker_name("142", {}).startswith("test-"),
       "канал 2: номер ЖИВОЙ задачи не попадает в имя — монитор демона его не откроет")
    ok(G._push("карточка") is None, "канал 1: пуш подавлен латчем (а не только PRETOOL_NOPUSH)")
    ok(G._edit("карточка", [1, 2]) is None, "канал 1: правка висящей карточки тоже подавлена")
finally:
    G.set_probe(False)

# ЗЕРКАЛЬНАЯ ТЕЧЬ, из-за которой класс жил: признак, гасивший ОДИН канал, оставлял открытым другой.
ok(G.isolated({"ORCH_TEST_MODE": "1"}) is True,
   "регресс течи A: проба с ORCH_TEST_MODE теперь гасит и ПУШ (раньше он читал только NOPUSH)")


# ─────────────── (3) ПРАВИЛО ТЕСТ-СУЩНОСТИ НА ЖИВОМ ФОРМАТЕ ПОЛЕЙ ───────────────
print("(3) сущность без пометки ТЕСТ в живые таблицы не пишется ВОВСЕ:")
ok(G._entity_blocktype(_SFO, LIVE_OIL) == "hard",
   "ДОСЛОВНАЯ фикстура инцидента (number='6789') → жёсткий блок, а НЕ карточка владельцу")
ok(G._extract_first_entity(_SFO, LIVE_OIL) == "6789",
   "живое имя поля Bridge `number=` наконец извлекается (было: только мёртвое `plate=`)")
ok(G._entity_blocktype(_SFO, "bridge.%s(plate='AB-5580', oil_km=1)" % _SFO) == "hard",
   "регресс: старая форма plate= по-прежнему жёсткая")
ok(G._entity_blocktype(_CB, "bridge.%s(client='Jack')" % _CB) == "hard",
   "регресс: живой клиент по полю client= по-прежнему жёсткий")
ok(G._entity_blocktype(_CB, "bridge.%s(bike='6789', name='Jack')" % _CB) == "hard",
   "живые имена полей брони (bike=/name=) — тоже жёстко")
ok(G._entity_blocktype(_CB, TEST_BOOK) is None,
   "ТЕСТ-сущность write-смока остаётся МЯГКОЙ — право владельца сказать «да» не отнято")
ok(G._entity_blocktype(_SFO, "bridge.%s(oil_km=27000)" % _SFO) is None,
   "ГРАНИЦА ужесточения: объекта в команде нет вовсе → судим по ДЕЙСТВИЮ, а не по подстроке")
ok(G._entity_blocktype(_SFO, "print('%s')" % _SFO) is None,
   "ГРАНИЦА: голое УПОМИНАНИЕ имени операции жёстким блоком не становится")
ok(G._entity_blocktype(_AT, MONEY) is None,
   "ГРАНИЦА: деньги НЕ ужесточены — сущности не несут, ложный hard отнял бы право разрешить")
ok(G._entity_blocktype(_DE, "bridge.%s(event_id=1)" % _DE) is None,
   "ГРАНИЦА: удаление события НЕ ужесточено")
ok(G.decision("block", _SFO, "x")["hookSpecificOutput"]["permissionDecision"] == "deny",
   "жёсткий блок остаётся deny — кнопки «да» здесь нет")


# ─────────────── (4) СКВОЗНОЙ ПРОГОН: ПРОБА vs БОЙ в окружении ЖИВОЙ задачи ───────────────
print("(4) сквозной прогон хука в окружении ЖИВОЙ задачи (тест-флаги сняты, как у демона):")
d = tempfile.mkdtemp(prefix="probe_isolation_")
try:
    def scenario(name, cmd, tid):
        mdir = os.path.join(d, name)
        pushes = os.path.join(d, name + ".pushes")
        env = _clean_child_env(CC_TASK_ID=tid, PRETOOL_BLOCK_DIR=mdir,
                               NOTIFY_COUNT_FILE=pushes,
                               PRETOOL_GUARD_LOG=os.path.join(d, name + ".log"),
                               PRETOOL_DEDUP_DIR=os.path.join(d, name + ".dedup"))
        out = _run_hook(cmd, env)
        markers = sorted(os.listdir(mdir)) if os.path.isdir(mdir) else []
        n_push = len(open(pushes, encoding="utf-8").read().splitlines()) if os.path.exists(pushes) else 0
        return out, markers, n_push

    # (а) БОЕВАЯ денежная операция — карточка рождается КАК ПРЕЖДЕ (границу не сломали)
    fx_money = os.path.join(d, "fx_money.py")
    with open(fx_money, "w", encoding="utf-8") as f:
        f.write(MONEY + "\n")
    out, markers, n_push = scenario("live_money", "%s %s" % (PY, _fx(fx_money)), "900001")
    ok(n_push == 1, "БОЙ/деньги: карточка ушла владельцу — 1 попытка пуша (регресс не сломан)")
    ok(markers == ["900001.json"], "БОЙ/деньги: боевой маркер для демона выписан: %s" % (markers,))
    ok(_decision_of(out) == "ask", "БОЙ/деньги: решение ask — владелец решает")

    # (б) ТА ЖЕ денежная операция ПРОБОЙ — владельцу НЕ уходит ни одним каналом
    out, markers, n_push = scenario(
        "probe_money", "PRETOOL_TEST_RUN=1 %s %s" % (PY, _fx(fx_money)), "900002")
    ok(n_push == 0, "ПРОБА/деньги: канал 1 молчит — ноль попыток пуша")
    ok(markers == ["test-900002.json"],
       "ПРОБА/деньги: канал 2 уведён — номер живой задачи не в имени: %s" % (markers,))
    ok(_decision_of(out) == "ask", "ПРОБА/деньги: решение НЕ ослаблено — по-прежнему ask")
    ok("ПЕРЕХВАЧЕНО НА ГРАНИЦЕ" in out, "ПРОБА/деньги: перехват назван прямо")
    ok("кошелёк main" in out and "сумма 500" in out,
       "ПРОБА/деньги: показано ДОСЛОВНО то, что собиралось уйти владельцу (объект и число)")

    # (в) ПРОБА записи в ЖИВЫЕ ТАБЛИЦЫ — дословная фикстура инцидента 142/143
    fx_oil = os.path.join(d, "fx_oil.py")
    with open(fx_oil, "w", encoding="utf-8") as f:
        f.write(LIVE_OIL + "\n")
    out, markers, n_push = scenario(
        "probe_oil", "PRETOOL_TEST_RUN=1 %s %s" % (PY, _fx(fx_oil)), "900143")
    ok(n_push == 0, "ПРОБА/Лист1: канал 1 молчит — ноль попыток пуша")
    ok(all(not m.startswith("900143") for m in markers),
       "ПРОБА/Лист1: боевого маркера живой задачи НЕТ ни по мягкой, ни по ЖЁСТКОЙ ветке: %s" % (markers,))
    ok(_decision_of(out) == "deny", "ПРОБА/Лист1: жёсткий блок остался жёстким (deny)")
    ok("ПЕРЕХВАЧЕНО НА ГРАНИЦЕ" in out, "ПРОБА/Лист1: перехват показан исполнителю")

    # (г) БОЕВАЯ запись в живые таблицы — жёсткий блок, карточки на «да» нет (доктрина 23.07)
    out, markers, n_push = scenario("live_oil", "%s %s" % (PY, _fx(fx_oil)), "900144")
    ok(_decision_of(out) == "deny", "БОЙ/Лист1: сущность без пометки ТЕСТ → deny")
    ok(n_push == 0, "БОЙ/Лист1: карточки на «да» нет — решение владельца вне агента")
    ok(markers == ["900144.json"], "БОЙ/Лист1: маркер blocktype=hard демону выписан: %s" % (markers,))
    if markers:
        with open(os.path.join(d, "live_oil", markers[0]), encoding="utf-8") as f:
            ok(json.load(f).get("blocktype") == "hard", "БОЙ/Лист1: маркер несёт blocktype=hard")

    # (д) БОЕВОЙ write-смок на ТЕСТ-сущности — мягкий путь и карточка ЖИВЫ
    fx_book = os.path.join(d, "fx_book.py")
    with open(fx_book, "w", encoding="utf-8") as f:
        f.write(TEST_BOOK + "\n")
    out, markers, n_push = scenario("live_test_entity", "%s %s" % (PY, _fx(fx_book)), "900005")
    ok(_decision_of(out) == "ask", "БОЙ/ТЕСТ-сущность: мягкий путь цел — ask с правом «да»")
    ok(n_push == 1, "БОЙ/ТЕСТ-сущность: карточка владельцу ушла как прежде")
finally:
    shutil.rmtree(d, ignore_errors=True)


# ─────────── (5) ДЕМОН ЧИСТИТ РОВНО ТЕ ЖЕ ИМЕНА, что гард считает признаком теста ───────────
# Инвариант, а не украшение: списки разъезжались уже дважды. Пока демон снимал с боевого ребёнка
# два имени из четырёх, протёкшее в его окружение PRETOOL_TEST_RUN увело бы маркер ЖИВОЙ задачи в
# тест-каталог — владелец не увидел бы красной карточки вовсе (тихая потеря вместо лишнего вопроса).
print("(5) демон снимает с боевого ребёнка РОВНО те имена, что гард считает тест-признаком:")
import re                                                            # noqa: E402
with open(os.path.join(ROOT, "orchestrator_daemon.py"), encoding="utf-8") as f:
    _od_src = f.read()
_pops = re.findall(r"for _test_flag in \(([^)]*)\)", _od_src)
ok(len(_pops) >= 2, "чистка стоит в ОБЕИХ ветках спавна (исполнитель и думатель): найдено %d" % len(_pops))
for i, _blk in enumerate(_pops, 1):
    _names = set(re.findall(r'"([A-Z_]+)"', _blk))
    ok(_names == set(G._TEST_RUN_ENVS),
       "ветка %d чистит ровно _TEST_RUN_ENVS (лишние/недостающие: %s)"
       % (i, sorted(_names ^ set(G._TEST_RUN_ENVS)) or "нет"))


print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
