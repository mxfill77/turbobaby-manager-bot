#!/usr/bin/env python3
"""ХРАПОВИК СЛЕПЫХ ЧИТАТЕЛЕЙ — метод счёта класса «нуль по неразбору» (08.08.2026).

ЗАЧЕМ. Перепись `docs/artifacts/2026-08-08-zero-on-parse-miss-census.md` насчитала ≈368 слепых
веток из 469 — руками, глазами трёх обходов. Число, полученное глазами, не удерживает НИЧЕГО:
завтра появится 369-я, и никто этого не заметит. Поэтому метод счёта закреплён КОДОМ, его текущее
значение — базовой линией в репозитории (`blind_readers_baseline.json`), а гейт краснеет при РОСТЕ
числа. Храповик: назад — сколько угодно, вперёд — нельзя.

ПОЧЕМУ ГЕЙТ, А НЕ ЗАМОК ПРИ ИМПОРТЕ. Замок («читатель обязан вернуть ScanResult») детонировал бы на
сотнях старых мест и не дал бы подняться демону. Гейт судит ДЕЛЬТУ и потому совместим с тем, что
класс закрывается местами, а не разом.

=== МЕТОД (он же — то, что нельзя ослабить незаметно) ===

ЧИТАТЕЛЬ — функция, которая берёт живой текст (`_SOURCE_*`) либо применяет к нему ШАБЛОН
(`_PATTERN_*`). Функция без того и другого читателем не считается вовсе.

СЛЕПОЙ ВЫХОД — `return <ПУСТОЕ>` из ВЕТКИ ПРОМАХА:
    · тело `except`-обработчика                     («не смогли» → пусто)
    · тело `if`, чья проверка есть проверка промаха  (`not X`, `X is None`, `X == None`)
ПУСТОЕ — `[]`, `{}`, `""`, `0`, `0.0`, `False`, `()`, `set()`, `list()`, `dict()` и составные, у
которых пусто ВСЁ содержимое (`{"overdue": []}` — то самое место якоря). Пустое значение слепо
потому, что его же функция отдаёт при ЧЕСТНОМ «ничего не нашлось»: промах и правда неразличимы.

`None` ПУСТЫМ НЕ СЧИТАЕТСЯ, И ЭТО НАМЕРЕННО. `None` там, где успех отдаёт список или число, — это
как раз ОБРАЗЕЦ различения из §5 переписи (`_git_tracked_top_level`, `_queue_items`,
`task_metrics._sum_fields`). Цена решения названа прямо: места вроде `status_truth.claim_started`
(None и при «файла нет», и при «ts битый») перепись считает слепыми, а этот метод — нет. Значит
ЧИСЛО МЕТОДА ЕСТЬ НИЖНЯЯ ГРАНИЦА слепоты, а не её мера. Для храповика этого достаточно: нижняя
граница не может выдумать слепоту, которой нет, а новая слепота названной формы всё равно поднимет
число.

ЧЕГО МЕТОД НЕ ВИДИТ (названо, чтобы не выдавать подмножество за целое):
    · слепоту ПОТОКОМ ДАННЫХ: `items = r.get("items", [])` — промах уходит в переменную, а не в
      `return` (так слепы `auditor.daily_report`, `bridge_deploy._node_harnesses_ok`);
    · `except: pass` / `continue` — промах без возврата;
    · модульный код вне функций;
    · `None`-выходы (см. выше);
    · всё, что вне верхнего уровня репозитория (подкаталоги, `tests/`, `_*.py`-черновики).

=== ЗАМОК ПРОТИВ ПОДЛОГА ===

Храповик обходится не правкой кода, а ОСЛАБЛЕНИЕМ МЕТОДА: сузить список источников, выкинуть `[]`
из пустых, перестать считать `except` веткой промаха, урезать список файлов. Поэтому:
    · метод проверяется `tests/test_blind_readers.py` на ИЗВЕСТНЫХ образцах слепого и зрячего
      читателя — ослабление роняет тест;
    · область обхода проверяется там же полом (сколько файлов и какие именно);
    · базовую линию модуль НЕ ПИШЕТ: `open` здесь только на чтение. Линия правится РУКАМИ, то есть
      видимой строкой в диффе, а не командой «пересчитай»;
    · нечитаемый или неразбираемый файл — ИСКЛЮЧЕНИЕ, а не пропуск. Счётчик слепых читателей,
      молча пропускающий файл, был бы слепым читателем сам (см. `find_blind`).

Запуск руками (read-only): `venv/bin/python3 blind_readers.py`
"""
import ast
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BASELINE_NAME = "blind_readers_baseline.json"

# --- Источники живого текста: вызов, которым текст БЕРУТ -------------------------------------
_SOURCE_BARE = frozenset(("open",))
_SOURCE_DOTTED = frozenset((
    "os.popen", "os.listdir", "os.walk", "os.scandir", "os.readlink",
    "glob.glob", "glob.iglob",
    "json.load", "json.loads",
    "subprocess.run", "subprocess.check_output", "subprocess.Popen",
    "subprocess.call", "subprocess.check_call", "subprocess.getoutput",
    "requests.get", "requests.post",
))
# Метод у чего угодно: `f.read()`, `bridge.fleet()`. Второй блок — как ИМЕННО этот репозиторий
# берёт живой текст у Google-таблиц, мозга и очереди (мост).
_SOURCE_METHODS = frozenset((
    "read", "readlines", "readline", "read_text", "communicate",
    "fleet", "service_list", "clients", "read_doc", "list_brain", "brain_list",
    "get_pending", "get_pending_multi", "state_list", "log_read", "_call", "_post",
))

# --- Шаблоны: чем текст РАЗБИРАЮТ ------------------------------------------------------------
_PATTERN_DOTTED = frozenset((
    "re.search", "re.match", "re.fullmatch", "re.findall", "re.finditer",
    "json.loads", "json.load", "ast.parse", "ast.literal_eval",
))
_PATTERN_METHODS = frozenset((
    "search", "match", "fullmatch", "findall", "finditer", "strptime",
    "group", "groups", "groupdict",
))

# Пустое, собранное вызовом: `list()`, `dict()`, `set()` … Аргументов быть не должно.
_EMPTY_CALLS = frozenset(("list", "dict", "set", "tuple", "str", "int", "float", "bool",
                          "frozenset", "bytes"))


# ============================ РАЗБОР ============================

def _call_names(node):
    """(точечное имя, имя метода) вызова: `os.listdir` → ('os.listdir','listdir'),
    `bridge.fleet` → ('bridge.fleet','fleet'), `open` → ('open','')."""
    f = node.func
    if isinstance(f, ast.Name):
        return f.id, ""
    if isinstance(f, ast.Attribute):
        root = f.value.id if isinstance(f.value, ast.Name) else ""
        return (f"{root}.{f.attr}" if root else ""), f.attr
    return "", ""


def _reader_kinds(fn):
    """Чем функция является: {'источник'} / {'шаблон'} / оба / пустое множество (не читатель)."""
    kinds = set()
    for n in ast.walk(fn):
        if not isinstance(n, ast.Call):
            continue
        dotted, meth = _call_names(n)
        if dotted in _SOURCE_BARE or dotted in _SOURCE_DOTTED or meth in _SOURCE_METHODS:
            kinds.add("источник")
        if dotted in _PATTERN_DOTTED or meth in _PATTERN_METHODS:
            kinds.add("шаблон")
    return kinds


def _is_empty(node):
    """Пустое ли значение возврата. `None` пустым НЕ является (см. шапку)."""
    if isinstance(node, ast.Constant):
        v = node.value
        if v is None or v is True:
            return False
        if isinstance(v, bool):
            return v is False
        if isinstance(v, (int, float)):
            return v == 0
        if isinstance(v, (str, bytes)):
            return len(v) == 0
        return False
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_empty(e) for e in node.elts)          # пустой литерал → all([]) → True
    if isinstance(node, ast.Dict):
        return all(_is_empty(v) for v in node.values if v is not None)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return (node.func.id in _EMPTY_CALLS and not node.args and not node.keywords)
    return False


def _is_miss_test(test):
    """Проверка промаха: `not X`, `X is None`, `X == None` — в любой глубине выражения."""
    for n in ast.walk(test):
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            return True
        if isinstance(n, ast.Compare):
            for op, cmp in zip(n.ops, n.comparators):
                if (isinstance(op, (ast.Is, ast.Eq))
                        and isinstance(cmp, ast.Constant) and cmp.value is None):
                    return True
    return False


def _walk_stmts(stmts, miss, sink):
    """Собрать слепые выходы. `miss` — стоим ли мы в ветке промаха.

    Во вложенные функции НЕ заходим: у чужой функции свой счёт (её `return` — её ответ, а не наш).
    """
    for n in stmts:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(n, ast.Return):
            if miss and n.value is not None and _is_empty(n.value):
                sink.append(n)
            continue
        if isinstance(n, ast.Try):
            _walk_stmts(n.body, miss, sink)
            for h in n.handlers:
                _walk_stmts(h.body, True, sink)              # except — ветка промаха
            _walk_stmts(n.orelse, miss, sink)
            _walk_stmts(n.finalbody, miss, sink)
            continue
        if isinstance(n, ast.If):
            _walk_stmts(n.body, miss or _is_miss_test(n.test), sink)
            _walk_stmts(n.orelse, miss, sink)                # else промахом не является
            continue
        for _, value in ast.iter_fields(n):                  # for/while/with — флаг наследуется
            if isinstance(value, list):
                _walk_stmts([x for x in value if isinstance(x, ast.stmt)], miss, sink)
            elif isinstance(value, ast.stmt):
                _walk_stmts([value], miss, sink)


def _functions(tree):
    """(узел, полное имя) всех функций дерева, включая методы и вложенные."""
    out = []

    def rec(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                out.append((child, name))
                rec(child, name + ".")
            elif isinstance(child, ast.ClassDef):
                rec(child, f"{prefix}{child.name}.")
            else:
                rec(child, prefix)

    rec(tree, "")
    return out


def find_blind(src, filename="<src>"):
    """Слепые читатели одного исходника → [{file, line, func, kinds, why}].

    SyntaxError НЕ ловится намеренно: счётчик, молча возвращающий пустой список на неразобранном
    файле, есть ровно тот класс, который он считает."""
    tree = ast.parse(src)
    found = []
    for fn, name in _functions(tree):
        kinds = _reader_kinds(fn)
        if not kinds:
            continue
        sink = []
        _walk_stmts(fn.body, False, sink)
        for r in sink:
            found.append({
                "file": filename, "line": r.lineno, "func": name,
                "kinds": " + ".join(sorted(kinds)),
                "why": "пустое наверх из ветки промаха",
            })
    return found


# ============================ ОБХОД ДЕРЕВА ============================

def is_scanned_name(name):
    """Область обхода: верхний уровень репозитория, `*.py`, кроме черновиков `_*.py`.

    `tests/` и подкаталоги вне области намеренно: тест — не читатель живого источника, его
    «нуль» никому не докладывается. Сужение этого правила ловится полом области в тесте."""
    base = os.path.basename(name)
    return base.endswith(".py") and not base.startswith("_")


def scan_repo(root=ROOT):
    """Полный обход → {files:[имена], per_file:{имя:N}, total:N, findings:[…]}.

    Нечитаемый/неразбираемый файл роняет обход исключением (см. `find_blind`)."""
    names = sorted(n for n in os.listdir(root) if is_scanned_name(n)
                   and os.path.isfile(os.path.join(root, n)))
    per_file, findings = {}, []
    for n in names:
        with open(os.path.join(root, n), encoding="utf-8") as f:
            src = f.read()
        got = find_blind(src, n)
        per_file[n] = len(got)
        findings.extend(got)
    return {"files": names, "per_file": per_file, "total": len(findings), "findings": findings}


# ============================ ХРАПОВИК ============================

def load_baseline(path=None):
    """Базовая линия из репозитория. Только чтение — модуль её НЕ пишет (см. шапку)."""
    with open(path or os.path.join(ROOT, BASELINE_NAME), encoding="utf-8") as f:
        return json.load(f)


def compare(scan, baseline):
    """(ok, [строки отчёта]). Красное — ТОЛЬКО рост общего числа. Падение — зелёное с заметкой:
    храповик держит потолок, а не заставляет чинить сегодня."""
    base_total = baseline.get("total")
    live = scan["total"]
    lines = []
    if not isinstance(base_total, int):
        return False, [f"храповик: базовая линия без числа total ({base_total!r}) — не доверяем"]
    base_files = baseline.get("per_file") or {}
    grew = sorted(((n, c, base_files.get(n, 0)) for n, c in scan["per_file"].items()
                   if c > base_files.get(n, 0)), key=lambda x: x[2] - x[1])
    if live > base_total:
        lines.append(f"❌ ХРАПОВИК СЛЕПЫХ ЧИТАТЕЛЕЙ: было {base_total}, стало {live} "
                     f"(+{live - base_total}). Новый читатель отдаёт наверх пустое по промаху.")
        for n, c, b in grew[:8]:
            lines.append(f"   выросло: {n} {b} → {c}")
        lines.append("   Лечится КОНТРАКТОМ (scan_result.ScanResult), а не правкой базовой линии: "
                     "наверх идёт пара «осмотрено/разобрано» и исход.")
        return False, lines
    if live < base_total:
        lines.append(f"✅ храповик: слепых читателей {live} при линии {base_total} "
                     f"(−{base_total - live}) — линию можно опустить до {live}.")
    else:
        lines.append(f"✅ храповик: слепых читателей {live} — базовая линия держится.")
    for n, c, b in grew[:5]:                 # общее не выросло, но файл вырос — говорим вслух
        lines.append(f"   заметка: {n} {b} → {c} (общее число не выросло)")
    return True, lines


def ratchet(root=ROOT, baseline_path=None):
    """Одна ручка для гейта: (ok, [строки]). Любой сбой — КРАСНОЕ (недоказанное не зелёное)."""
    try:
        return compare(scan_repo(root), load_baseline(baseline_path))
    except Exception as e:
        return False, [f"❌ ХРАПОВИК СЛЕПЫХ ЧИТАТЕЛЕЙ не отработал ({type(e).__name__}: {e}) — "
                       f"считаем красным: недоказанное зелёным не бывает."]


def main():
    scan = scan_repo()
    print(f"слепых читателей: {scan['total']} (файлов в обходе: {len(scan['files'])})")
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    if only:                       # `blind_readers.py splinter.py` — поимённо, адресами
        for f in scan["findings"]:
            if f["file"] in only:
                print(f"  {f['file']}:{f['line']}  {f['func']}  [{f['kinds']}]  {f['why']}")
        return 0
    for n, c in sorted(scan["per_file"].items(), key=lambda x: -x[1]):
        if c:
            print(f"  {c:4d}  {n}")
    try:
        ok, lines = compare(scan, load_baseline())
    except Exception as e:
        print(f"базовая линия не прочитана: {e}")
        return 1
    for ln in lines:
        print(ln)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
