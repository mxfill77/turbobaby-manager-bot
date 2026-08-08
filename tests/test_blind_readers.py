"""ХРАПОВИК СЛЕПЫХ ЧИТАТЕЛЕЙ: метод счёта + замок против подлога (08.08.2026).

ЗАЧЕМ ЭТОТ ФАЙЛ СУЩЕСТВУЕТ. Храповик держит число слепых читателей (класс «нуль по неразбору»,
перепись `docs/artifacts/2026-08-08-zero-on-parse-miss-census.md`) и краснеет при его РОСТЕ.
Обойти храповик правкой кода нельзя — а ОСЛАБЛЕНИЕМ МЕТОДА СЧЁТА можно: выкинуть `[]` из списка
пустых, забыть, что `except` — ветка промаха, сузить список источников или область обхода. Тогда
число упадёт само, гейт позеленеет, и слепота станет невидимой ВТОРОЙ РАЗ — теперь уже с виду
законно.

Поэтому здесь метод проверяется на ИЗВЕСТНЫХ образцах, и образцы подобраны так, что ЛЮБОЕ
ослабление роняет секцию (1) или (6). Секция (5) это доказывает не словами: она ослабляет метод
живьём и показывает, что известный слепой перестаёт находиться.

Образцы сняты с ЖИВОГО кода этого репозитория (формы, а не выдумка):
  слепые  — `health._read_log_lines` (except → []), `_dec_siblings` (`if not r.get("ok")` → []),
            ЯКОРЬ `_o3_overdue_scan` ДО правки (except → {"overdue": []});
  зрячие  — `_queue_items` (None ≠ []), `invariants_check._git_tracked_top_level` (None ≠ set()),
            `task_metrics._sum_fields` (пара «сумма, был ли ключ»), `_o3_overdue_scan` ПОСЛЕ
            правки (ScanResult).

Сети, моста, боевых файлов состояния и записи на диск здесь нет: разбор идёт по строкам-исходникам
в памяти, живое дерево читается только на чтение.

Проверки:
 (1) ИЗВЕСТНЫЕ СЛЕПЫЕ находятся — все формы пустого из ветки промаха;
 (2) ИЗВЕСТНЫЕ ЗРЯЧИЕ не находятся — None-выход, сентинел, пара с флагом, контракт;
 (3) НЕ ЧИТАТЕЛЬ не считается вовсе (нет ни источника, ни шаблона);
 (4) ЯКОРЬ: код парк-скана ДО правки слеп, ПОСЛЕ — нет (было/стало на одном методе);
 (5) ЗАМОК: ослабление метода живьём → известный слепой пропадает (значит (1) держит метод);
 (6) ОБЛАСТЬ обхода: пол по числу файлов и поимённо — сужение области краснит;
 (7) ГРОМКИЙ СБОЙ: неразбираемый файл → ИСКЛЮЧЕНИЕ, а не тихий пустой список; у счётчика нет
     `try`, а у самого модуля — ни `os.environ`, ни записи, ни подпроцесса (нечем ослабить извне);
 (8) ХРАПОВИК: рост → красное, равенство → зелёное, падение → зелёное с заметкой, кривая линия
     и пропавший файл линии → красное (недоказанное зелёным не бывает);
 (9) ЖИВОЕ ДЕРЕВО сходится с базовой линией, и переведённый читатель в слепых больше не числится;
(10) ГЕЙТ реально зовёт храповик (иначе замок стоит на двери, которой нет).
"""
import os, sys, ast, json

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _HERE)

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import blind_readers as BR

# ============================ ОБРАЗЦЫ ============================

СЛЕПЫЕ = {
    "except → [] (форма health._read_log_lines)": """
def _read_log_lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.readlines()
    except Exception:
        return []
""",
    "except → {\"overdue\": []} (ЯКОРЬ: парк-скан ДО правки)": """
def _o3_overdue_scan(bridge):
    try:
        bikes = ((bridge.fleet().get("data") or {}).get("bikes")) or []
    except Exception:
        log.exception("fleet упал")
        return {"overdue": []}
    return {"overdue": bikes}
""",
    "if not r.get(\"ok\") → [] (форма _dec_siblings)": """
def _dec_siblings(parent):
    r = bridge.get_pending("new", lane="vps")
    if not r.get("ok"):
        return []
    return r["items"]
""",
    "промах шаблона → \"\"": """
def _tick(text):
    m = re.search(r"NOTE (.+?): ревизор", text)
    if m is None:
        return ""
    return m.group(1)
""",
    "промах шаблона → 0": """
def errors_since(path):
    with open(path) as f:
        lines = f.readlines()
    m = re.search(r"старт", "".join(lines))
    if not m:
        return 0
    return len(lines)
""",
    "except → False": """
def is_fresh(path):
    try:
        with open(path) as f:
            return bool(json.load(f))
    except Exception:
        return False
""",
    "except → set()": """
def known(path):
    try:
        with open(path) as f:
            return set(f.read().split())
    except OSError:
        return set()
""",
    "except → (0, {}) — составное, где пусто ВСЁ": """
def stats(path):
    try:
        with open(path) as f:
            return len(f.read()), {"ok": True}
    except Exception:
        return 0, {}
""",
    "промах в глубине: for → if not m → []": """
def parse_rows(path):
    out = []
    with open(path) as f:
        for line in f:
            m = re.match(r"(\\d+)", line)
            if not m:
                return []
            out.append(m.group(1))
    return out
""",
}

ЗРЯЧИЕ = {
    "None ≠ [] (форма _queue_items)": """
def _queue_items(status):
    try:
        r = bridge.get_pending(status, lane="vps")
    except Exception:
        return None
    if not r.get("ok"):
        return None
    return r.get("items") or []
""",
    "None ≠ set() (форма _git_tracked_top_level)": """
def _git_tracked_top_level(root):
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return set(out.stdout.split())
""",
    "пара «сумма, был ли ключ» (форма task_metrics._sum_fields)": """
def _sum_fields(path, keys):
    with open(path) as f:
        data = json.load(f)
    total, seen = 0, False
    for k in keys:
        if k not in data:
            return 0, False
        total += data[k]
        seen = True
    return total, seen
""",
    "контракт: ScanResult вместо пустого": """
def _o3_overdue_scan(bridge):
    try:
        resp = bridge.fleet()
    except Exception as e:
        return scan_result.ScanResult.unreadable("байков", detail=str(e))
    bikes = (resp.get("data") or {}).get("bikes")
    if not isinstance(bikes, list):
        return scan_result.ScanResult.unreadable("байков", detail="нет списка")
    return scan_result.ScanResult(len(bikes), len(bikes), payload=bikes)
""",
    "промах → исключение (громко)": """
def load(path):
    with open(path) as f:
        data = json.load(f)
    if not data:
        raise ValueError("пусто")
    return data
""",
    "пустое НЕ из ветки промаха (честный нуль успеха)": """
def collect(path):
    with open(path) as f:
        rows = f.readlines()
    out = []
    for r in rows:
        if re.match(r"\\d", r):
            out.append(r)
    return out
""",
    "пустое в ВЕТКЕ УСПЕХА (else), а не промаха": """
def pick(path):
    with open(path) as f:
        text = f.read()
    m = re.search(r"x", text)
    if not m:
        raise ValueError("не нашли")
    else:
        return []
""",
}

НЕ_ЧИТАТЕЛИ = {
    "ни источника, ни шаблона (чистый расчёт)": """
def summarize(rows):
    try:
        return [r["name"] for r in rows]
    except Exception:
        return []
""",
}

# === (1) известные слепые находятся ===========================================================
print("(1) известные слепые находятся:")
for label, src in СЛЕПЫЕ.items():
    got = BR.find_blind(src, "образец.py")
    res.append(ok(len(got) >= 1, f"слепой найден: {label}"))

# === (2) известные зрячие не находятся ========================================================
print("(2) известные зрячие НЕ находятся (метод не кричит на здоровых):")
for label, src in ЗРЯЧИЕ.items():
    got = BR.find_blind(src, "образец.py")
    res.append(ok(not got, f"зрячий чист: {label}" + (f" — но найдено {got}" if got else "")))

# === (3) не читатель не считается =============================================================
print("(3) не-читатель не считается вовсе:")
for label, src in НЕ_ЧИТАТЕЛИ.items():
    got = BR.find_blind(src, "образец.py")
    res.append(ok(not got, f"не читатель — не в счёте: {label}"))

# === (4) якорь: было / стало на одном методе ==================================================
print("(4) ЯКОРЬ — парк-скан ДО и ПОСЛЕ правки одним методом:")
before = BR.find_blind(СЛЕПЫЕ["except → {\"overdue\": []} (ЯКОРЬ: парк-скан ДО правки)"], "splinter.py")
after = BR.find_blind(ЗРЯЧИЕ["контракт: ScanResult вместо пустого"], "splinter.py")
res.append(ok(len(before) == 1 and before[0]["func"] == "_o3_overdue_scan",
              f"ДО правки: слепой, адрес назван — {before}"))
res.append(ok(not after, "ПОСЛЕ правки: не слеп (наверх идёт пара «осмотрено/разобрано»)"))

# === (5) ЗАМОК: ослабление метода роняет обнаружение ==========================================
print("(5) ЗАМОК против подлога — ослабление метода живьём:")
_anchor = СЛЕПЫЕ["except → {\"overdue\": []} (ЯКОРЬ: парк-скан ДО правки)"]
_log_reader = СЛЕПЫЕ["except → [] (форма health._read_log_lines)"]

_saved = (BR._SOURCE_METHODS, BR._SOURCE_BARE, BR._SOURCE_DOTTED,
          BR._PATTERN_METHODS, BR._PATTERN_DOTTED, BR._EMPTY_CALLS)
try:
    BR._SOURCE_METHODS = frozenset()          # «мост источником не считаем»
    res.append(ok(not BR.find_blind(_anchor, "x.py"),
                  "сузили список источников → ЯКОРЬ пропал (значит секция 1 держит этот список)"))
    res.append(ok(len(BR.find_blind(_log_reader, "x.py")) == 1,
                  "…а читатель лога ЖИВ: его держит второй признак (open) — списки перекрываются"))
    BR._SOURCE_BARE = frozenset()             # теперь выкинут и open
    res.append(ok(not BR.find_blind(_log_reader, "x.py"),
                  "выкинули ОБА признака → и он пропал (спрятать читателя = ослабить не одно место)"))
finally:
    (BR._SOURCE_METHODS, BR._SOURCE_BARE, BR._SOURCE_DOTTED,
     BR._PATTERN_METHODS, BR._PATTERN_DOTTED, BR._EMPTY_CALLS) = _saved

_is_empty_saved = BR._is_empty
try:
    BR._is_empty = lambda node: False         # «пустого не бывает»
    res.append(ok(not BR.find_blind(_anchor, "x.py"),
                  "выкинули понятие пустого → пропали ВСЕ (секция 1 краснеет целиком)"))
finally:
    BR._is_empty = _is_empty_saved

_miss_saved = BR._is_miss_test
try:
    BR._is_miss_test = lambda test: False      # «`if not X` промахом не считаем»
    res.append(ok(not BR.find_blind(СЛЕПЫЕ["if not r.get(\"ok\") → [] (форма _dec_siblings)"], "x.py"),
                  "перестали считать `if not X` промахом → форма _dec_siblings пропала"))
    res.append(ok(len(BR.find_blind(_anchor, "x.py")) == 1,
                  "…но except-форма при этом ЖИВА: два признака независимы, ослабить надо оба"))
finally:
    BR._is_miss_test = _miss_saved

res.append(ok(len(BR.find_blind(_anchor, "x.py")) == 1 and len(BR.find_blind(_log_reader, "x.py")) == 1,
              "метод восстановлен после всех ослаблений (тест не оставил его слабым)"))

# === (6) область обхода =======================================================================
print("(6) область обхода — пол по числу и поимённо:")
res.append(ok(all(BR.is_scanned_name(n) for n in
                  ("splinter.py", "devbot.py", "orchestrator_daemon.py", "bot.py", "health.py")),
              "большие модули в области"))
res.append(ok(not BR.is_scanned_name("_scratch_probe.py") and not BR.is_scanned_name("notes.md"),
              "черновики _*.py и не-py вне области"))
_scan = BR.scan_repo(_HERE)
_files = set(_scan["files"])
_МОДУЛИ = {"splinter.py", "devbot.py", "orchestrator_daemon.py", "bot.py", "health.py",
           "pretool_guard.py", "gate.py", "bridge_client.py", "expectations.py", "prod_drift.py",
           "card_duty.py", "status_truth.py", "scan_result.py", "blind_readers.py"}
res.append(ok(_МОДУЛИ <= _files, f"поимённо на месте (не хватает: {sorted(_МОДУЛИ - _files)})"))
res.append(ok(len(_files) >= 35, f"пол области: файлов в обходе {len(_files)} (>= 35)"))

# === (7) громкий сбой + нечем ослабить извне ==================================================
print("(7) громкий сбой и отсутствие ручек ослабления:")
try:
    BR.find_blind("def f(:\n    pass\n", "битый.py")
    res.append(ok(False, "неразбираемый файл прошёл МОЛЧА — счётчик слеп сам"))
except SyntaxError:
    res.append(ok(True, "неразбираемый файл → SyntaxError, а не тихий пустой список"))
except Exception as e:
    res.append(ok(False, f"неожиданное исключение: {type(e).__name__}"))

with open(os.path.join(_HERE, "blind_readers.py"), encoding="utf-8") as f:
    _br_src = f.read()
_br_tree = ast.parse(_br_src)
_fns = {n.name: n for n in ast.walk(_br_tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
for _name in ("find_blind", "scan_repo", "load_baseline", "compare"):
    _has_try = any(isinstance(x, ast.Try) for x in ast.walk(_fns[_name]))
    res.append(ok(not _has_try, f"{_name}: ни одного try — промах не может быть проглочен"))
_attrs = {f"{n.value.id}.{n.attr}" for n in ast.walk(_br_tree)
          if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
res.append(ok("os.environ" not in _attrs and "os.getenv" not in _attrs,
              "метод не читает окружение — переменной его не ослабить"))
_bad_calls = {n.func.id for n in ast.walk(_br_tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)} & {"exec", "eval", "compile", "__import__"}
res.append(ok(not _bad_calls, f"ни exec/eval/compile: {_bad_calls or 'чисто'}"))
_writes = []
for n in ast.walk(_br_tree):
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open":
        mode = n.args[1].value if len(n.args) > 1 and isinstance(n.args[1], ast.Constant) else "r"
        for kw in n.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = kw.value.value
        if not str(mode).startswith("r"):
            _writes.append(mode)
res.append(ok(not _writes, f"open только на чтение: базовую линию модуль НЕ пишет ({_writes or 'ок'})"))
_imports = sorted({n.names[0].name.split(".")[0] for n in ast.walk(_br_tree) if isinstance(n, ast.Import)}
                  | {(n.module or "").split(".")[0] for n in ast.walk(_br_tree) if isinstance(n, ast.ImportFrom)})
res.append(ok(set(_imports) <= {"ast", "json", "os", "sys"}, f"импорты узкие: {_imports}"))

# === (8) храповик ============================================================================
print("(8) храповик — рост красный, падение зелёное, кривая линия красная:")
_base = {"total": 10, "per_file": {"a.py": 6, "b.py": 4}}
_grew = {"total": 12, "per_file": {"a.py": 8, "b.py": 4}, "files": ["a.py", "b.py"], "findings": []}
_same = {"total": 10, "per_file": {"a.py": 6, "b.py": 4}, "files": ["a.py", "b.py"], "findings": []}
_fell = {"total": 8, "per_file": {"a.py": 4, "b.py": 4}, "files": ["a.py", "b.py"], "findings": []}
_moved = {"total": 10, "per_file": {"a.py": 8, "b.py": 2}, "files": ["a.py", "b.py"], "findings": []}
ok_g, lines_g = BR.compare(_grew, _base)
res.append(ok(not ok_g, "рост числа → КРАСНОЕ"))
res.append(ok(any("a.py" in l and "6 → 8" in l for l in lines_g),
              f"…и назван файл, где выросло: {[l for l in lines_g if 'a.py' in l]}"))
res.append(ok(any("контракт" in l.lower() or "ScanResult" in l for l in lines_g),
              "…и сказано, чем лечить (контрактом, а не правкой линии)"))
ok_s, _ = BR.compare(_same, _base)
res.append(ok(ok_s, "равенство → зелёное"))
ok_f, lines_f = BR.compare(_fell, _base)
res.append(ok(ok_f and any("опустить" in l for l in lines_f),
              f"падение → зелёное с заметкой «линию можно опустить»: {lines_f[0]}"))
ok_m, lines_m = BR.compare(_moved, _base)
res.append(ok(ok_m and any("заметка" in l for l in lines_m),
              "общее не выросло, но файл вырос → зелёное И сказано вслух"))
ok_b, _ = BR.compare(_same, {"per_file": {}})
res.append(ok(not ok_b, "базовая линия без числа total → КРАСНОЕ (не доверяем)"))
ok_r, lines_r = BR.ratchet(_HERE, os.path.join(_HERE, "нет-такого-файла.json"))
res.append(ok(not ok_r and "не отработал" in " ".join(lines_r),
              "файла линии нет → храповик КРАСНЫЙ, а не тихо зелёный"))

# === (9) живое дерево ========================================================================
print("(9) живое дерево сходится с базовой линией:")
_baseline = BR.load_baseline()
res.append(ok(_scan["total"] == _baseline["total"],
              f"слепых читателей {_scan['total']} = базовая линия {_baseline['total']}"))
res.append(ok(sum(_baseline["per_file"].values()) == _baseline["total"],
              "линия внутренне согласована: сумма по файлам = total"))
res.append(ok(all(_scan["per_file"].get(n, 0) == c for n, c in _baseline["per_file"].items()),
              "раскладка по файлам совпадает с живым деревом"))
_o3 = [f for f in _scan["findings"] if f["func"] == "_o3_overdue_scan"]
res.append(ok(not _o3, f"переведённый читатель в слепых НЕ числится ({_o3})"))
res.append(ok(_baseline["per_file"].get("splinter.py") == 14,
              "splinter: 15 → 14 (ровно один переведён, остальные не тронуты)"))
# Живой корпус против линии на единицу ниже = ровно то, что случится, когда появится 75-й слепой
# читатель. Проверяем НА НАСТОЯЩЕМ дереве, а не только на синтетике секции (8): нового слепого
# читателя для этого заводить не нужно (и нельзя — заходу запрещено что-либо удалять за собой).
_ok_grow, _lines_grow = BR.compare(_scan, {"total": _baseline["total"] - 1,
                                           "per_file": _baseline["per_file"]})
res.append(ok(not _ok_grow and any("ХРАПОВИК" in l for l in _lines_grow),
              f"на ЖИВОМ дереве рост на 1 → красное: {_lines_grow[0][:80]}…"))

# === (10) гейт зовёт храповик =================================================================
print("(10) гейт реально зовёт храповик:")
import gate
_g_ok, _g_lines = gate._run_ratchet()
res.append(ok(_g_ok, f"гейт: храповик зелёный — {_g_lines[0] if _g_lines else '(молча)'}"))
with open(os.path.join(_HERE, "gate.py"), encoding="utf-8") as f:
    _gate_tree = ast.parse(f.read())
_main = [n for n in ast.walk(_gate_tree)
         if isinstance(n, ast.FunctionDef) and n.name == "main"][0]
_called = {n.func.id for n in ast.walk(_main) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
res.append(ok("_run_ratchet" in _called,
              "main() гейта зовёт _run_ratchet — шаг не выкинут (иначе замок на двери, которой нет)"))
_top = [st for st in _main.body
        if "_run_ratchet" in {n.func.id for n in ast.walk(st)
                              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}]
res.append(ok(bool(_top) and not any(isinstance(st, ast.If) for st in _top),
              "храповик — оператор ВЕРХНЕГО уровня main(), не внутри ветки режима: "
              "гоняется и в селективном гейте, и в полном"))

print(f"\nИТОГ: {sum(res)}/{len(res)}")
sys.exit(0 if all(res) else 1)
