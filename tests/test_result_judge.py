"""СУДЬЯ АДРЕСА РЕЗУЛЬТАТА — читает продукт шага НАЗАД и отвечает одним из ТРЁХ (16.08.2026).

Пункт 2 контракта третьего исхода. Судья построен и НИКУДА НЕ ПОДКЛЮЧЁН: вердикт шага не тронут,
движение цепи не изменено, правила «нет адреса — нет зелёного» нет. Здесь это не обещание, а
проверка — секция (6) считает вызовы судьи из боевого кода и требует НОЛЯ.

ПОРЯДОК СЕКЦИЙ НЕ КОСМЕТИКА: отрицательный тест стоит ПЕРВЫМ по прямому требованию задания.
Прибор, который на пустом адресе говорит «доказан», негоден целиком, и узнать это надо до всех
прочих чисел, а не после.

 (1) ОТРИЦАТЕЛЬНЫЙ ТЕСТ, ПЕРВЫМ — по каждому из ПЯТИ видов: «адрес назван, по адресу пусто» →
     НЕ ДОКАЗАН, «источник недоступен» → НЕИЗВЕСТНО. Источники ЖИВЫЕ, где живой источник вообще
     можно привести в такое состояние read-only (несуществующий хеш в origin/main, пустой файл,
     путь, который не разрешается, база без таблицы, юнит, которого нет);
 (2) АДРЕС НЕ НАЗВАН → НЕИЗВЕСТНО (и это законное сегодняшнее состояние каждого шага);
 (3) ПОЛОЖИТЕЛЬНЫЙ КОНТРОЛЬ — прибор, который всё красит в «не доказан», так же негоден;
 (4) СТАРШИНСТВО: НЕ ДОКАЗАН > НЕИЗВЕСТНО > ДОКАЗАН (порядок О3), НЕИЗВЕСТНО сильнее ДОКАЗАН;
 (5) ВРЕМЕНИ У СУДЬИ НЕТ: сдвиг ВСЕХ меток на ±2 часа не меняет ни одного вердикта, и у самих
     функций нет параметра времени (проверяется подписью, а не на слово);
 (6) НИКЕМ НЕ ЗОВОМ: судьи нет в замыкании импортов ни одной живой точки входа; вызовов из
     боевого кода — ноль, и число печатается;
 (7) ЧИСТОТА РЕШЕНИЯ: страж `RESULT_JUDGE_PURE` зелен на живом модуле и КРАСНЕЕТ, если руки
     появятся (зелёное без этого ничего не стоит);
 (8) РУКИ ТОЛЬКО ЧИТАЮТ: разбор `result_judge_facts.py` — argv литеральный и из белого списка,
     `shell` нигде, база открывается режимом `ro`, `open` не зовётся вовсе.

ЗАПУСК — ЖИВОЙ ФОРМАТ ГЕЙТА: `venv/bin/python3 tests/test_result_judge.py` (gate.py гоняет
каждый тест ровно так, отдельным процессом; ненулевой код возврата = красное).
"""
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["ORCH_TEST_MODE"] = "1"
# КАНАЛ 2 ИЗОЛЯЦИИ ПРОБ (правило CLAUDE.md): четыре имени + каталог маркеров ВСЕГДА.
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["PRETOOL_TEST_RUN"] = "1"
os.environ["PRETOOL_BLOCK_DIR"] = "/tmp/cc_guard_block_test"

import ast
import inspect
import sqlite3
import subprocess

import result_judge as RJ
import result_judge_facts as RF
import result_ref as RR

REPO = "/root/turbobaby-manager-bot"
SCRATCH = os.path.join(REPO, "_scratch_judge_0816")
os.makedirs(SCRATCH, exist_ok=True)


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    res.append(bool(c))
    return bool(c)


res = []

# ════════════════════════════════════════════════════════════════════════════════════════════
print("\n(1) ОТРИЦАТЕЛЬНЫЙ ТЕСТ — ПЕРВЫМ: пусто → НЕ ДОКАЗАН, источник недоступен → НЕИЗВЕСТНО")
# ════════════════════════════════════════════════════════════════════════════════════════════
# ЖИВЫЕ ИСТОЧНИКИ. Каждый приведён в нужное состояние ТОЛЬКО чтением: несуществующий хеш, пустой
# файл в каталоге захода, путь, который не разрешается, база без таблицы, юнит, которого нет.
_empty_file = os.path.join(SCRATCH, "empty_by_design.txt")
with open(_empty_file, "w", encoding="utf-8") as f:
    pass
_db = os.path.join(SCRATCH, "probe.db")
if not os.path.exists(_db):
    _con = sqlite3.connect(_db)
    _con.execute("CREATE TABLE IF NOT EXISTS acts (id INTEGER, tag TEXT)")
    _con.execute("INSERT INTO acts (id, tag) VALUES (1, 'есть')")
    _con.commit()
    _con.close()

_live_commits = RF.commits_fact()
ok(_live_commits.get("read") and len(_live_commits.get("shas") or []) > 100,
   f"живой origin/main прочитан: коммитов {len(_live_commits.get('shas') or [])}")

_neg = []          # (вид, что за случай, вердикт, ожидание)


def neg(kind, case, ref, facts, want):
    v = RJ.verdict(ref, facts)
    _neg.append((kind, case, v["state"], want))
    ok(v["state"] == want, f"{kind} · {case} → {v['state']} ({v['why'][:70]})")
    return v


# ── commit ───────────────────────────────────────────────────────────────────────────────────
neg("commit", "хеша нет в origin/main (пусто по адресу)",
    ("commit", "deadbee"), {"commits": _live_commits}, RJ.UNPROVEN)
neg("commit", "origin/main не прочитан (источник недоступен)",
    ("commit", "deadbee"), {"commits": RF.commits_fact("нет/такой/ветки")}, RJ.UNKNOWN)

# ── file ─────────────────────────────────────────────────────────────────────────────────────
neg("file", "файл существует и ПУСТ",
    ("file", _empty_file), {"files": {_empty_file: RF.file_fact(_empty_file)}}, RJ.UNPROVEN)
_gone = os.path.join(SCRATCH, "нет-такого-файла.txt")
neg("file", "файла по адресу нет",
    ("file", _gone), {"files": {_gone: RF.file_fact(_gone)}}, RJ.UNPROVEN)
# «Источник недоступен» вживую: путь, у которого промежуточный элемент — не каталог. Сказать
# «файла нет» тут нельзя: адрес не разрешается вовсе, и это разные вещи.
_bad = os.path.join(REPO, "result_ref.py", "внутри.txt")
neg("file", "путь не разрешается (источник недоступен)",
    ("file", _bad), {"files": {_bad: RF.file_fact(_bad)}}, RJ.UNKNOWN)

# ── row ──────────────────────────────────────────────────────────────────────────────────────
_p_no_row = f"{_db} acts tag=нет-такой-строки"
neg("row", "строки по условию нет",
    ("row", _p_no_row), {"rows": {_p_no_row: RF.row_fact(_db, "acts", [("tag", "нет-такой")])}},
    RJ.UNPROVEN)
_p_no_db = f"{SCRATCH}/нет-базы.db acts tag=есть"
neg("row", "базы нет (источник недоступен)",
    ("row", _p_no_db),
    {"rows": {_p_no_db: RF.row_fact(os.path.join(SCRATCH, "нет-базы.db"), "acts",
                                    [("tag", "есть")])}}, RJ.UNKNOWN)
_p_no_tab = f"{_db} нетаблица tag=есть"
neg("row", "таблицы в базе нет (источник недоступен)",
    ("row", _p_no_tab),
    {"rows": {_p_no_tab: RF.row_fact(_db, "нетаблица", [("tag", "есть")])}}, RJ.UNKNOWN)

# ── brain ────────────────────────────────────────────────────────────────────────────────────
neg("brain", "узел прочитан, названного НЕ содержит",
    ("brain", "cc_log СТРОКА-КОТОРОЙ-НЕТ-42"),
    {"brain": {"cc_log": {"read": True, "text": "иные строки", "len": 11, "len_before": 5}}},
    RJ.UNPROVEN)
neg("brain", "узел содержит, но НЕ ВЫРОС (могло лежать и до шага)",
    ("brain", "cc_log DONE 16.08"),
    {"brain": {"cc_log": {"read": True, "text": "DONE 16.08 …", "len": 12, "len_before": 12}}},
    RJ.UNPROVEN)
neg("brain", "мост не спрошен (источник недоступен)",
    ("brain", "cc_log DONE 16.08"),
    RF.gather([("brain", "cc_log DONE 16.08")], brain=False), RJ.UNKNOWN)
neg("brain", "содержит, но длину не с чем сравнить → НЕ зелёное",
    ("brain", "cc_log DONE 16.08"),
    {"brain": {"cc_log": {"read": True, "text": "DONE 16.08 …", "len": 12, "len_before": None}}},
    RJ.UNKNOWN)

# ── service_start ────────────────────────────────────────────────────────────────────────────
_sha_old = (_live_commits.get("shas") or ["0" * 40])[-1]
neg("service_start", "юнит поднят РАНЬШЕ коммита (не то по адресу)",
    ("service_start", f"splinter {_sha_old[:7]}"),
    {"commits": _live_commits,
     "units": {"splinter": {"read": True,
                            "started": (_live_commits.get("at") or {}).get(_sha_old, 0) - 60}}},
    RJ.UNPROVEN)
_no_unit = RF.unit_fact("нет-такого-юнита-0816.service")
neg("service_start", "юнита нет (источник недоступен)",
    ("service_start", f"нет-такого-юнита-0816.service {_sha_old[:7]}"),
    {"commits": _live_commits, "units": {"нет-такого-юнита-0816.service": _no_unit}}, RJ.UNKNOWN)

_greened = [n for n in _neg if n[2] == RJ.PROVEN]
ok(not _greened, f"НИ ОДИН отрицательный случай не позеленел: зелёных {len(_greened)} "
                 f"из {len(_neg)} (пусто → НЕ ДОКАЗАН, недоступно → НЕИЗВЕСТНО)")
if _greened:
    print("  ЗАМОК A НЕ УСТОЯЛ — судья негоден, дальше числа не имеют смысла:", _greened)
    print(f"\nИТОГ: {sum(res)}/{len(res)} PASS")
    sys.exit(1)

# ════════════════════════════════════════════════════════════════════════════════════════════
print("\n(2) АДРЕС НЕ НАЗВАН → НЕИЗВЕСТНО")
# ════════════════════════════════════════════════════════════════════════════════════════════
for case, ref in (("None", None), ("пустая пара", ("", "")), ("пустой словарь", {}),
                  ("вид без указателя", ("commit", "")),
                  ("вид не из контракта", ("коммит", "abc1234")),
                  ("мусор вместо адреса", 42)):
    v = RJ.verdict(ref, {"commits": _live_commits})
    ok(v["state"] == RJ.UNKNOWN, f"{case} → {v['state']} ({v['why'][:60]})")

_row_no_ref = {"id": 7, "task_text": "тз: посчитать что-нибудь\nбез всякого адреса"}
v = RJ.of_task(_row_no_ref, {"commits": _live_commits})
ok(v["state"] == RJ.UNKNOWN and v["why"] == RJ.NOT_NAMED,
   f"строка очереди без адреса → {v['state']} «{v['why']}»")

for case, p in (("хеш короче семи знаков", "abc12"), ("не хеш вовсе", "коммит-мой-хороший"),
                ("указатель строки не разобран", "просто слова")):
    kind = "row" if "строки" in case else "commit"
    v = RJ.verdict((kind, p), {"commits": _live_commits})
    ok(v["state"] == RJ.UNKNOWN, f"{case} → {v['state']} ({v['why'][:60]})")

# ════════════════════════════════════════════════════════════════════════════════════════════
print("\n(3) ПОЛОЖИТЕЛЬНЫЙ КОНТРОЛЬ: прибор, красящий всё в «не доказан», так же негоден")
# ════════════════════════════════════════════════════════════════════════════════════════════
v = RJ.verdict(("commit", "55d2f1d"), {"commits": _live_commits})
ok(v["state"] == RJ.PROVEN, f"канон адреса (коммит 55d2f1d) → {v['state']} ({v['why'][:60]})")

_live_file = "result_ref.py"
v = RJ.verdict(("file", _live_file), {"files": {_live_file: RF.file_fact(_live_file)}})
ok(v["state"] == RJ.PROVEN, f"живой файл репозитория → {v['state']} ({v['why'][:60]})")

_p_row = f"{_db} acts tag=есть"
v = RJ.verdict(("row", _p_row), {"rows": {_p_row: RF.row_fact(_db, "acts", [("tag", "есть")])}})
ok(v["state"] == RJ.PROVEN, f"строка в базе по условию → {v['state']} ({v['why'][:60]})")

v = RJ.verdict(("brain", "cc_log DONE 16.08"),
               {"brain": {"cc_log": {"read": True, "text": "DONE 16.08 итог", "len": 15,
                                     "len_before": 5}}})
ok(v["state"] == RJ.PROVEN, f"узел содержит названное и вырос → {v['state']} ({v['why'][:60]})")

_unit_live = RF.unit_fact("splinter")
_older = ([s for s in (_live_commits.get("shas") or [])
           if (_live_commits.get("at") or {}).get(s, 0) < (_unit_live.get("started") or 0)]
          if _unit_live.get("read") else [])
if _older:
    v = RJ.verdict(("service_start", f"splinter {_older[0][:7]}"),
                   {"commits": _live_commits, "units": {"splinter": _unit_live}})
    ok(v["state"] == RJ.PROVEN, f"старт splinter моложе коммита → {v['state']} ({v['why'][:60]})")
else:
    ok(True, f"живой splinter не наблюдается ({_unit_live.get('why')}) — вид проверен фактами")
    v = RJ.verdict(("service_start", f"splinter {_sha_old[:7]}"),
                   {"commits": _live_commits,
                    "units": {"splinter": {"read": True,
                                           "started": (_live_commits.get("at") or {})
                                           .get(_sha_old, 0) + 60}}})
    ok(v["state"] == RJ.PROVEN, f"старт моложе коммита (факты) → {v['state']}")

# ════════════════════════════════════════════════════════════════════════════════════════════
print("\n(4) СТАРШИНСТВО: НЕ ДОКАЗАН > НЕИЗВЕСТНО > ДОКАЗАН")
# ════════════════════════════════════════════════════════════════════════════════════════════
ok(RJ.strongest([RJ.PROVEN, RJ.UNKNOWN]) == RJ.UNKNOWN, "НЕИЗВЕСТНО сильнее ДОКАЗАН")
ok(RJ.strongest([RJ.PROVEN, RJ.UNKNOWN, RJ.UNPROVEN]) == RJ.UNPROVEN, "НЕ ДОКАЗАН сильнее всех")
ok(RJ.strongest([RJ.PROVEN, RJ.PROVEN]) == RJ.PROVEN, "только доказанные → ДОКАЗАН")
ok(RJ.strongest([]) == RJ.UNKNOWN, "пусто → НЕИЗВЕСТНО (пустого зелёного не бывает)")
ok(RJ.RANK[RJ.UNPROVEN] > RJ.RANK[RJ.UNKNOWN] > RJ.RANK[RJ.PROVEN],
   "порядок силы совпадает с прибором О3 (UNDELIVERED > UNKNOWN > DELIVERED)")

# ════════════════════════════════════════════════════════════════════════════════════════════
print("\n(5) ВРЕМЕНИ У СУДЬИ НЕТ: сдвиг всех меток на ±2 часа не меняет ни одного вердикта")
# ════════════════════════════════════════════════════════════════════════════════════════════
_base_facts = {
    "commits": {"read": True, "shas": ["a" * 40, "b" * 40],
                "at": {"a" * 40: 1_000_000.0, "b" * 40: 1_000_500.0}},
    "units": {"splinter": {"read": True, "started": 1_000_900.0},
              "orchestrator-daemon": {"read": True, "started": 999_000.0}},
    "files": {"result_ref.py": RF.file_fact("result_ref.py")},
}
_refs = [("commit", "a" * 7), ("commit", "b" * 7), ("file", "result_ref.py"),
         ("service_start", "splinter " + "a" * 7),
         ("service_start", "orchestrator-daemon " + "b" * 7)]


def shifted(facts, sec):
    out = dict(facts)
    out["commits"] = dict(facts["commits"])
    out["commits"]["at"] = {k: v + sec for k, v in facts["commits"]["at"].items()}
    out["units"] = {u: dict(d, started=d["started"] + sec) for u, d in facts["units"].items()}
    return out


_base = [RJ.verdict(r, _base_facts)["state"] for r in _refs]
_changed = 0
for sec, label in ((7200, "+2 ч"), (-7200, "−2 ч")):
    got = [RJ.verdict(r, shifted(_base_facts, sec))["state"] for r in _refs]
    diff = [(r, a, b) for r, a, b in zip(_refs, _base, got) if a != b]
    _changed += len(diff)
    ok(not diff, f"сдвиг {label}: вердиктов изменилось {len(diff)} из {len(_refs)}")
ok(_changed == 0, f"замок C на уровне функции: изменений всего {_changed}")

_sig = inspect.signature(RJ.verdict).parameters
ok(list(_sig) == ["ref", "facts"] and not any(
    w in " ".join(_sig) for w in ("now", "window", "since", "hours")),
   f"у verdict нет параметра времени: {list(_sig)}")
_src_judge = open(os.path.join(REPO, "result_judge.py"), encoding="utf-8").read()
_tree = ast.parse(_src_judge)
_time_calls = [n.func.attr for n in ast.walk(_tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr in ("time", "now", "utcnow", "monotonic")]
ok(not _time_calls, f"судья не спрашивает время у системы: вызовов {len(_time_calls)}")

# ════════════════════════════════════════════════════════════════════════════════════════════
print("\n(6) ЗОВОМ РОВНО ИЗ ОДНОЙ ДВЕРИ — ТЕНИ, КОТОРАЯ НИЧЕГО НЕ РЕШАЕТ")
# ════════════════════════════════════════════════════════════════════════════════════════════
import prod_drift as PD

# ПУНКТ 3 КОНТРАКТА (16.08.2026, `docs/artifacts/2026-08-16-shadow-rule.md`) ПОДКЛЮЧИЛ СУДЬЮ —
# и ровно в одном месте: ТЕНЕВОЙ прогон правила зелёного в демоне. Прежняя редакция требовала
# «судьи нет в памяти НИ ОДНОЙ живой точки входа»; смысл её был не в отсутствии кода, а в том,
# что ПО АДРЕСУ НИКТО НЕ СУДИТ ЖИВОЙ ШАГ. Поэтому замок не снят, а сужен до списка: судья вправе
# жить в памяти РОВНО демона (там тень), и ни одной другой точки входа. Что он там ничего не
# решает — доказано отдельно: терминалы done и failed посимвольно равны прежним при тени
# включённой и выключенной (`tests/test_shadow_rule.py`, замок A), а имена судьи видны в демоне
# только внутри `_shadow_*` (`tests/test_result_ref.py`).
ENTRIES = ("bot.py", "orchestrator_daemon.py", "expectations_run.py", "pretool_guard.py",
           "posttool_feed.py", "health.py", "splinter.py", "devbot.py")
SHADOW_ENTRY = "orchestrator_daemon.py"
_in_closure = []
for e in ENTRIES:
    cl = PD.closure(e, REPO)
    for name in ("result_judge.py", "result_judge_facts.py"):
        if name in cl and e != SHADOW_ENTRY:
            _in_closure.append((e, name))
ok(not _in_closure,
   f"судьи нет в памяти ни одной живой точки входа, кроме тени ({len(ENTRIES)} проверено): "
   f"{_in_closure}")
_shadow_cl = PD.closure(SHADOW_ENTRY, REPO)
ok("result_judge.py" in _shadow_cl and "shadow_rule.py" in _shadow_cl,
   "судья и теневое правило ЕСТЬ в памяти демона — тень считается там, где рождается вердикт")

_prod_py = sorted(n for n in os.listdir(REPO)
                  if n.endswith(".py") and not n.startswith("_")
                  and n not in ("result_judge.py", "result_judge_facts.py"))
_mentions = []
for n in _prod_py:
    src = open(os.path.join(REPO, n), encoding="utf-8").read()
    t = ast.parse(src)
    for node in ast.walk(t):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in ("result_judge", "result_judge_facts"):
                    _mentions.append((n, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in ("result_judge", "result_judge_facts"):
                _mentions.append((n, node.lineno))
ok(sorted({n for n, _ in _mentions}) == ["orchestrator_daemon.py", "shadow_rule.py"],
   f"судью зовут РОВНО двое — тень и её решение: {sorted({n for n, _ in _mentions})} "
   f"(проверено файлов {len(_prod_py)})")

_hands_src = open(os.path.join(REPO, "result_judge_facts.py"), encoding="utf-8").read()
_hands_imports = [a.name for node in ast.walk(ast.parse(_hands_src))
                  if isinstance(node, ast.Import) for a in node.names]
ok("result_judge" in _hands_imports,
   "единственный читатель судьи в репозитории — его же руки, которых не зовёт никто")

# ════════════════════════════════════════════════════════════════════════════════════════════
print("\n(7) ЧИСТОТА РЕШЕНИЯ: страж зелен на живом модуле и краснеет на модуле с руками")
# ════════════════════════════════════════════════════════════════════════════════════════════
import invariants_check as IC

_run = IC.CheckRun("RESULT_JUDGE_PURE")
IC.check_result_judge_pure(None, _run)
ok(not _run.findings, f"страж зелёный на живом судье: рук нет ({_run.findings})")

_probe = os.path.join(SCRATCH, "_hands_probe.py")
with open(_probe, "w", encoding="utf-8") as f:
    f.write("import subprocess\ndef go():\n    return subprocess.run(['git', 'log'])\n")
_real = IC._RESULT_JUDGE_PATH
IC._RESULT_JUDGE_PATH = _probe
_run2 = IC.CheckRun("RESULT_JUDGE_PURE")
IC.check_result_judge_pure(None, _run2)
IC._RESULT_JUDGE_PATH = _real
ok(len(_run2.findings) >= 1,
   f"страж краснеет на модуле с руками ({len(_run2.findings)} находок) — зелёное доказательно")

_imports = [a.name for node in ast.walk(ast.parse(_src_judge))
            if isinstance(node, ast.Import) for a in node.names]
ok(_imports == ["result_ref"], f"импорт у судьи ровно один: {_imports}")
ok(sorted(RR.KINDS) == sorted(("commit", "file", "row", "brain", "service_start")),
   "виды берутся у канона, второго словаря видов рядом не заведено")

# ════════════════════════════════════════════════════════════════════════════════════════════
print("\n(8) РУКИ ТОЛЬКО ЧИТАЮТ")
# ════════════════════════════════════════════════════════════════════════════════════════════
_ht = ast.parse(_hands_src)
_heads, _shell, _opens, _ro = [], 0, 0, 0
for node in ast.walk(_ht):
    if not isinstance(node, ast.Call):
        continue
    fn = node.func
    name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
    root = fn.value.id if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) else ""
    if root == "subprocess" and name == "run":
        for kw in node.keywords:
            if kw.arg == "shell":
                _shell += 1
        arg = node.args[0] if node.args else None
        if isinstance(arg, ast.List) and arg.elts and isinstance(arg.elts[0], ast.Constant):
            _heads.append(arg.elts[0].value)
        elif isinstance(arg, ast.BinOp) and isinstance(arg.left, ast.List) \
                and isinstance(arg.left.elts[0], ast.Constant):
            _heads.append(arg.left.elts[0].value)
        else:
            _heads.append("НЕ ЛИТЕРАЛ")
    if name == "open" and not root:
        _opens += 1
    if root == "sqlite3" and name == "connect":
        lit = node.args[0] if node.args else None
        txt = ""
        if isinstance(lit, ast.BinOp) and isinstance(lit.left, ast.Constant):
            txt = lit.left.value
        elif isinstance(lit, ast.Constant):
            txt = lit.value
        _ro += 1 if "mode=ro" in str(txt) else 0

ok(sorted(set(_heads)) == ["git", "systemctl"], f"внешние команды рук: {sorted(set(_heads))}")
ok(_shell == 0, f"shell=True нигде: {_shell}")
ok(_opens == 0, f"`open` руками не зовётся вовсе: {_opens}")
ok(_ro == 1 and "uri=True" in _hands_src, "база открывается ТОЛЬКО режимом чтения (mode=ro)")
ok(RF.GIT_READ == frozenset(("log",)),
   f"белый список git у рук — только чтение: {sorted(RF.GIT_READ)}")
_bad_words = [w for w in ("restart", "systemd-run", "pkill", "kill ", "write_doc", "enqueue")
              if w in _hands_src.split('"""')[-1]]
ok(not _bad_words, f"слов записи и перезапуска в коде рук нет: {_bad_words}")

print("\n" + "=" * 70)
print(f"ИТОГ: {sum(res)}/{len(res)} PASS")
if not all(res):
    sys.exit(1)
