#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ЗАМОК АТРИБУЦИИ КРАСНОГО: «наше или чужое» отвечает ПРОГОН, а не догадка (15.08.2026).

ЗАЧЕМ. Полный гейт стоит ~100 с и платился ЗА ЗАХОД ДВАЖДЫ: сперва руками
(`venv/bin/python3 gate.py` перед push — строка дисциплины в APPROVAL_PREAMBLE), потом сам собой,
pre-push хуком (`deploy/hooks/pre-push`), которого git зовёт на КАЖДЫЙ push и обойти нельзя
(`--no-verify` в deny). Оба прогона судили ОДНО И ТО ЖЕ дерево, то есть второй покупал ноль.
Убрали ручной: вердикт даёт тот прогон, который ВЛИЯЕТ.

ЧТО ПРИ ЭТОМ ТЕРЯЛОСЬ И ЧЕМ ВОЗВРАЩЕНО. Ручной прогон умел одно, чего pre-push не умеет: показать
состояние ДО. Заход, увидевший красное только на push, знает лишь «сейчас красно» — и дальше
начиналась ДОГАДКА («наверное, чужое, оно и раньше мигало»). Здесь догадки нет: НАЗВАННЫЕ упавшие
тесты гоняются ещё раз — на дереве ДО наших коммитов (`git worktree` на базовый ref), и вердикт
даёт СРАВНЕНИЕ двух прогонов.

ИСХОДОВ ЧЕТЫРЕ, И ТРЕТИЙ — ЗАМОК ПРОТИВ ЛОЖНОГО ЗЕЛЁНОГО (тот же, что у О3, кассы, scan_result):
  · «наше»               — здесь красный, на базовом дереве зелёный;
  · «чужое»              — красный на ОБОИХ (наша правка его не рождала);
  · «не судимо»          — базовый прогон недоказателен: теста на базе нет · worktree не встал ·
                           таймаут · ПРОГОН КОСНУЛСЯ БОЕВОГО ДЕРЕВА. Это НЕ «чужое»;
  · «не воспроизводится» — здесь ЗЕЛЁНЫЙ: красное было не сейчас, судить нечего.
Код возврата: 1 — есть «наше»; 2 — есть «не судимо»/«не воспроизводится»; 0 — ВСЁ доказано чужим.
Порядок силы взят у прибора доставки: наше > неизвестно > чужое.

ЛОВУШКА МЕТОДА ЗАКРЫТА ДВАЖДЫ, И ЭТО ГЛАВНОЕ ЗДЕСЬ. CLAUDE.md ловил её живьём: «демон кладёт свой
ЗАХАРДКОЖЕННЫЙ REPO первым в sys.path — модуль, которого в проверяемом дереве нет, приехал из
БОЕВОГО корня». В этом репозитории 161 тест из 208 (перепись 15.08.2026) держит боевой корень
литералом и сам кладёт его в `sys.path` — наивный прогон «того же файла» из worktree судил бы
ЖИВОЕ дерево и врал бы уверенно. Поэтому:
  (1) ПИН ИМПОРТА. Дочернему процессу подкладывается `sitecustomize.py`, ставящий в `sys.meta_path`
      finder на БАЗОВОЕ дерево. meta_path спрашивают РАНЬШЕ sys.path, поэтому
      `sys.path.insert(0, боевой корень)` внутри теста пин не обходит.
  (2) АУДИТ ОБРАЩЕНИЙ. Пин чинит импорт, но не чинит чтение по абсолютному пути
      (`open("<боевой>/orchestrator_daemon.py")`, `subprocess.run([PY, "<боевой>/tests/x.py"])`) —
      а ast-стражи репозитория читают исходники именно так. Тот же `sitecustomize` вешает
      `sys.addaudithook` (приём `tests/livewatch.py`) и записывает КАЖДОЕ обращение к боевому
      дереву мимо `venv/`, `.git/`, `reports/`. Обращение было → вердикт этого теста «НЕ СУДИМО»
      с числом обращений: соврать «чужое» о живом дереве нельзя.

ЧЕГО МОДУЛЬ НЕ ДЕЛАЕТ. Не правит рабочее дерево (worktree — свой каталог во временном, снимается
за собой), не пишет в очередь, не шлёт сообщений, гейт целиком НЕ гоняет: только названные тесты.

    venv/bin/python3 gate_blame.py test_foo.py test_bar.py [--base origin/main]
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, "venv", "bin", "python3")
BASE_DEFAULT = "origin/main"
TEST_TIMEOUT = 90          # тот же бюджет, что у gate.run_tests — вердикты двух прогонов сравнимы

OURS = "наше"
FOREIGN = "чужое"
UNJUDGED = "не судимо"
NOT_REPRO = "не воспроизводится"

# Каталоги боевого дерева, обращение к которым уликой НЕ является: интерпретатор и его пакеты
# лежат внутри репозитория (venv/bin/python3), метаданные git читает сам git, reports — артефакты.
AUDIT_SKIP_DIRS = ("venv", ".git", "reports", "node_modules", "__pycache__")

# Подкладка дочернего процесса базового прогона. Держим ТЕКСТОМ, а не файлом в репозитории:
# она обязана лежать во временном каталоге прогона, иначе попадёт в sys.path обычных тестов.
SITECUSTOMIZE_SRC = r'''# -*- coding: utf-8 -*-
"""Подкладка gate_blame (живёт только в дочернем процессе базового прогона).

Ничего не решает: пинует верхнеуровневый импорт на БАЗОВОЕ дерево и считает обращения к БОЕВОМУ.
Вердикт по этим фактам выносит родитель."""
import os
import sys

_BASE = os.environ.get("GATE_BLAME_BASE") or ""
_LIVE = os.environ.get("GATE_BLAME_LIVE") or ""
_LOG = os.environ.get("GATE_BLAME_TOUCH") or ""
_SKIP = os.environ.get("GATE_BLAME_SKIP") or ""

if _BASE:
    import importlib.util

    class _PinToBase:
        """meta_path спрашивают РАНЬШЕ sys.path — поэтому хардкод боевого корня внутри теста
        (`sys.path.insert(0, "/root/...")`, 161 тест из 208) этот пин не обходит."""

        def find_spec(self, name, path=None, target=None):
            if path is not None or "." in name:
                return None
            f = os.path.join(_BASE, name + ".py")
            if os.path.isfile(f):
                return importlib.util.spec_from_file_location(name, f)
            pkg = os.path.join(_BASE, name, "__init__.py")
            if os.path.isfile(pkg):
                return importlib.util.spec_from_file_location(
                    name, pkg, submodule_search_locations=[os.path.join(_BASE, name)])
            return None

    sys.meta_path.insert(0, _PinToBase())

if _LIVE and _LOG:
    _skips = tuple(os.path.join(_LIVE, d) + os.sep for d in _SKIP.split(",") if d)
    _state = {"busy": False, "n": 0}

    def _strings(args):
        out = []
        for a in args:
            if isinstance(a, str):
                out.append(a)
            elif isinstance(a, (list, tuple)):
                out.extend([x for x in a if isinstance(x, str)])
        return out

    def _hook(event, args):
        if _state["busy"] or _state["n"] > 200:
            return
        if event not in ("open", "subprocess.Popen", "os.system", "os.exec"):
            return
        for p in _strings(args):
            if not p.startswith(_LIVE + os.sep) or p == _LOG or p.startswith(_skips):
                continue
            _state["busy"] = True
            try:
                with open(_LOG, "a", encoding="utf-8") as fh:
                    fh.write(event + "|" + p + "\n")
                _state["n"] += 1
            except Exception:
                pass
            finally:
                _state["busy"] = False

    sys.addaudithook(_hook)
'''


# ============================ ЧИСТОЕ РЕШЕНИЕ ============================

def classify(here_rc, here_why, base_rc, base_why, touched):
    """Факты двух прогонов → (исход, причина). Чистая функция: ни файлов, ни сети, ни git.

    Порядок проверок — от «судить нечем» к «судим»: сомнение любого рода НИКОГДА не сваливается
    в «чужое» (это и есть замок: «не судимо» ≠ «наша правка ни при чём»)."""
    if here_rc is None:
        return UNJUDGED, "прогон на текущем дереве не состоялся: %s" % (here_why or "причина не названа")
    if here_rc == 0:
        return NOT_REPRO, "на текущем дереве тест ЗЕЛЁНЫЙ — названное красное не воспроизводится"
    if touched:
        return UNJUDGED, ("базовый прогон %d раз коснулся боевого дерева — он судил не базу"
                          % int(touched))
    if base_rc is None:
        return UNJUDGED, "базовый прогон не состоялся: %s" % (base_why or "причина не названа")
    if base_rc == 0:
        return OURS, "на базовом дереве зелёный, здесь красный — красное родила наша правка"
    return FOREIGN, "красный и на базовом дереве — наша правка его не рождала"


def summary(rows, base_label=""):
    """Строки разбора → (код возврата, [строки отчёта]). Чистая функция.

    Код: 1 — есть «наше»; 2 — есть «не судимо»/«не воспроизводится»; 0 — ВСЁ доказано чужим.
    Пустой список тестов — тоже 2: судить не о чем, а «0» читалось бы как «всё чужое»."""
    lines = []
    if base_label:
        lines.append("база сравнения: %s" % base_label)
    counts = {OURS: 0, FOREIGN: 0, UNJUDGED: 0, NOT_REPRO: 0}
    for r in rows:
        v = r.get("verdict") or UNJUDGED
        counts[v] = counts.get(v, 0) + 1
        lines.append("  %-22s %-20s %s" % (r.get("test") or "(без имени)", v, r.get("why") or ""))
    if not rows:
        lines.append("ТЕСТОВ НЕ НАЗВАНО — судить не о чем (это НЕ «всё чужое»).")
        return 2, lines
    lines.append("итог: наше %d · чужое %d · не судимо %d · не воспроизводится %d"
                 % (counts[OURS], counts[FOREIGN], counts[UNJUDGED], counts[NOT_REPRO]))
    if counts[OURS]:
        lines.append("❌ КРАСНОЕ НАШЕ — чинить эту правку, а не искать виноватого.")
        return 1, lines
    if counts[UNJUDGED] or counts[NOT_REPRO]:
        lines.append("⚠️ ВЕРДИКТА НЕТ: часть тестов не судима — это не разрешение считать красное чужим.")
        return 2, lines
    lines.append("✅ ВСЁ КРАСНОЕ ЧУЖОЕ — доказано прогоном на дереве до наших коммитов.")
    return 0, lines


# ============================ РУКИ ============================

def _flags_env():
    """Флаги окружения тест-прогона — ОДИН источник с гейтом (PRETOOL_NOPUSH, ORCH_TEST_MODE)."""
    try:
        import gate
        return dict(gate._child_env())
    except Exception:
        return dict(os.environ, PRETOOL_NOPUSH="1", ORCH_TEST_MODE="1")


def resolve_base(ref, root=ROOT):
    """ref → (sha, None) | (None, причина). Промах несёт ПРИЧИНУ: пустоты вместо ответа тут нет."""
    try:
        p = subprocess.run(["git", "rev-parse", "--verify", "%s^{commit}" % ref],
                           cwd=root, capture_output=True, text=True, timeout=20)
    except Exception as e:
        return None, "git не отозвался на rev-parse (%s)" % e
    if p.returncode != 0:
        return None, "ref «%s» не разрешается: %s" % (ref, ((p.stderr or "").strip() or "молча")[:120])
    sha = (p.stdout or "").strip()
    if not sha:
        return None, "git промолчал на rev-parse «%s»" % ref
    return sha, None


def _run_test(path, cwd, env, timeout=TEST_TIMEOUT, py=None):
    """Один тест → (rc, хвост вывода) | (None, причина). Возврата-пустышки нет ни в одной ветке."""
    try:
        p = subprocess.run([py or PY, path], cwd=cwd, env=env,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "не уложился в %d с" % timeout
    except Exception as e:
        return None, "не запустился (%s)" % e
    tail = ((p.stdout or "") + "\n" + (p.stderr or "")).strip().splitlines()
    return p.returncode, (tail[-1][:160] if tail else "(нет вывода)")


def _add_worktree(root, sha):
    """Базовое дерево отдельным каталогом → (путь, None) | (None, причина). Рабочее НЕ трогается."""
    holder = tempfile.mkdtemp(prefix="gate_blame_")
    tree = os.path.join(holder, "tree")
    try:
        p = subprocess.run(["git", "worktree", "add", "--detach", tree, sha],
                           cwd=root, capture_output=True, text=True, timeout=180)
    except Exception as e:
        shutil.rmtree(holder, ignore_errors=True)
        return None, "git worktree не отозвался (%s)" % e
    if p.returncode != 0:
        shutil.rmtree(holder, ignore_errors=True)
        return None, "git worktree add упал: %s" % ((p.stderr or "").strip() or "молча")[:160]
    return tree, None


def _drop_worktree(root, tree):
    """Уборка СВОЕГО черновика во временном каталоге: сначала git, затем каталог целиком."""
    try:
        subprocess.run(["git", "worktree", "remove", "--force", tree],
                       cwd=root, capture_output=True, text=True, timeout=60)
    except Exception:
        pass
    shutil.rmtree(os.path.dirname(tree), ignore_errors=True)
    try:
        subprocess.run(["git", "worktree", "prune"], cwd=root,
                       capture_output=True, text=True, timeout=60)
    except Exception:
        pass


def _pin_dir(holder):
    """Каталог с подкладкой (пин импорта + аудит обращений) для дочернего процесса."""
    d = os.path.join(holder, "pin")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "sitecustomize.py"), "w", encoding="utf-8") as fh:
        fh.write(SITECUSTOMIZE_SRC)
    return d


def _base_env(base_tree, pin, touch_log, live_root):
    """env базового прогона: боевой корень из PYTHONPATH УБРАН, а не задвинут (ловушка метода)."""
    env = _flags_env()
    env["PYTHONPATH"] = os.pathsep.join([pin, base_tree, os.path.join(base_tree, "tests")])
    env["GATE_BLAME_BASE"] = base_tree
    env["GATE_BLAME_LIVE"] = live_root
    env["GATE_BLAME_TOUCH"] = touch_log
    env["GATE_BLAME_SKIP"] = ",".join(AUDIT_SKIP_DIRS)
    return env


def _touch_count(path):
    """Сколько раз базовый прогон коснулся боевого дерева. Журнал пишет подкладка и ТОЛЬКО по
    факту обращения, поэтому «файла нет» = ноль обращений, а не незнание; нечитаемый журнал —
    именно незнание (None), и оно станет «не судимо»."""
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                return len([ln for ln in fh.read().splitlines() if ln.strip()])
        except Exception:
            return None
    return 0


def blame(tests, base=BASE_DEFAULT, root=ROOT, live_root=None, py=None, timeout=TEST_TIMEOUT):
    """Разбор названных тестов → (rows, base_label). Каждый тест гоняется ДВАЖДЫ: здесь и на базе."""
    live_root = live_root or root
    names = [os.path.basename(t) for t in tests if str(t).strip()]
    env_here = _flags_env()
    sha, why = resolve_base(base, root=root)
    base_label = "%s (%s)" % (base, (sha or "НЕ РАЗРЕШЁН: %s" % why)[:60])

    tree, tree_why = (None, why)
    holder = pin = None
    if sha:
        tree, tree_why = _add_worktree(root, sha)
        if tree:
            holder = os.path.dirname(tree)
            pin = _pin_dir(holder)

    rows = []
    try:
        for name in names:
            here_rc, here_why = _run_test(os.path.join(root, "tests", name), root, env_here,
                                          timeout=timeout, py=py)
            base_rc, base_why, touched = None, tree_why, 0
            if tree:
                path = os.path.join(tree, "tests", name)
                if not os.path.isfile(path):
                    base_why = "теста нет на базовом дереве — он родился этим заходом"
                else:
                    log = os.path.join(holder, "touch-%s.log" % name)
                    env_base = _base_env(tree, pin, log, live_root)
                    base_rc, base_why = _run_test(path, tree, env_base, timeout=timeout, py=py)
                    touched = _touch_count(log)
                    if touched is None:
                        base_rc, base_why, touched = None, "журнал обращений нечитаем", 0
            verdict, reason = classify(here_rc, here_why, base_rc, base_why, touched)
            rows.append({"test": name, "here_rc": here_rc, "base_rc": base_rc,
                         "touched": touched, "verdict": verdict, "why": reason})
    finally:
        if tree:
            _drop_worktree(root, tree)
        elif holder:
            shutil.rmtree(holder, ignore_errors=True)
    return rows, base_label


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    base = BASE_DEFAULT
    if "--base" in argv:
        i = argv.index("--base")
        base = argv[i + 1] if i + 1 < len(argv) else BASE_DEFAULT
        del argv[i:i + 2]
    tests = [a for a in argv if not a.startswith("-")]
    if not tests:
        print(__doc__.strip().splitlines()[-1].strip())
        print("ТЕСТОВ НЕ НАЗВАНО — судить не о чем (это НЕ «всё чужое»).")
        return 2
    rows, label = blame(tests, base=base)
    code, lines = summary(rows, base_label=label)
    for ln in lines:
        print(ln)
    return code


if __name__ == "__main__":
    sys.exit(main())
