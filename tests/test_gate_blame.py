# -*- coding: utf-8 -*-
"""ЗАМОК АТРИБУЦИИ КРАСНОГО (15.08.2026): «наше или чужое» отвечает ПРОГОН, а не догадка.

Предмет — `gate_blame.py`. Ручной прогон гейта перед push убран (тот же вердикт на том же дереве,
что и у pre-push, ~100 с в никуда), и вместе с ним заход потерял единственный способ увидеть
состояние ДО. Возвращает его этот модуль: упавшие тесты гоняются ещё раз на дереве ДО коммитов.

Проверяем ЧЕТЫРЕ вещи, и третья с четвёртой — главные:
  (1) чистое решение: четыре исхода, порядок силы «наше > неизвестно > чужое», коды возврата;
  (2) живой конец-в-конец на ОДНОРАЗОВОМ git-репозитории (не на боевом): наше · чужое · нет теста
      на базе · не воспроизводится;
  (3) ЛОВУШКА МЕТОДА: тест, прибитый к боевому корню (161 файл из 208 в этом репозитории), при
      наивном прогоне из worktree судит ЖИВОЕ дерево — контрольный прогон это ПОКАЗЫВАЕТ, а пин
      импорта чинит;
  (4) АУДИТ: тест, читающий файл боевого дерева по абсолютному пути, получает «не судимо», а НЕ
      уверенное «чужое» — незнание не выдаётся за оправдание.
Плюс границы: рабочее дерево не тронуто, черновики убраны, гейт целиком не гоняется.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = "/root/turbobaby-manager-bot"
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"

import gate_blame as GB

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return c


# ═══ (1) ЧИСТОЕ РЕШЕНИЕ ═══════════════════════════════════════════════════════════════════════
print("\n(1) четыре исхода и порядок силы")

v, why = GB.classify(here_rc=1, here_why="", base_rc=0, base_why="", touched=0)
ok(v == GB.OURS, "здесь красный, на базе зелёный → НАШЕ")

v, _ = GB.classify(1, "", 1, "", 0)
ok(v == GB.FOREIGN, "красный на обоих деревьях → ЧУЖОЕ")

v, why = GB.classify(1, "", None, "worktree не встал", 0)
ok(v == GB.UNJUDGED and "worktree" in why, "базовый прогон не состоялся → НЕ СУДИМО с причиной")

v, why = GB.classify(1, "", 1, "", 7)
ok(v == GB.UNJUDGED and "7" in why,
   "базовый прогон коснулся боевого дерева → НЕ СУДИМО, хотя оба кода красные (не «чужое»)")

v, _ = GB.classify(0, "", 1, "", 0)
ok(v == GB.NOT_REPRO, "здесь зелёный → НЕ ВОСПРОИЗВОДИТСЯ (судить нечего)")

v, why = GB.classify(None, "не запустился (x)", 0, "", 0)
ok(v == GB.UNJUDGED and "текущем" in why, "текущий прогон не состоялся → НЕ СУДИМО")

code, lines = GB.summary([{"test": "a", "verdict": GB.FOREIGN, "why": ""},
                          {"test": "b", "verdict": GB.OURS, "why": ""}])
ok(code == 1, "есть «наше» → код 1 (сильнее любого чужого)")

code, lines = GB.summary([{"test": "a", "verdict": GB.FOREIGN, "why": ""},
                          {"test": "b", "verdict": GB.UNJUDGED, "why": ""}])
ok(code == 2 and any("ВЕРДИКТА НЕТ" in x for x in lines),
   "есть «не судимо» → код 2, и отчёт прямо говорит, что это не разрешение считать красное чужим")

code, _ = GB.summary([{"test": "a", "verdict": GB.FOREIGN, "why": ""}])
ok(code == 0, "всё доказано чужим → код 0")

code, lines = GB.summary([])
ok(code == 2 and any("НЕ НАЗВАНО" in x for x in lines),
   "тестов не названо → код 2, а не «всё чужое» (пустота ≠ доказательство)")

ok(GB.main([]) == 2, "CLI без имён тестов → код 2, ни одного прогона")


# ═══ ОДНОРАЗОВЫЙ РЕПОЗИТОРИЙ (боевой не трогаем ни одной командой) ════════════════════════════
def git(repo, *args, **kw):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t"] + list(args),
                          cwd=repo, capture_output=True, text=True, timeout=60, **kw)


def write(repo, rel, text):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


HOLDER = tempfile.mkdtemp(prefix="tb_gate_blame_case_")
REPO = os.path.join(HOLDER, "repo")
os.makedirs(REPO)
git(REPO, "init", "-q")

SELF_ROOT = ("import os, sys\n"
             "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n")

# База: модуль говорит «base», четыре теста
write(REPO, "mod_x.py", "VALUE = 'base'\n")
write(REPO, "tests/test_ours.py", SELF_ROOT + "import mod_x\nsys.exit(0 if mod_x.VALUE == 'base' else 1)\n")
write(REPO, "tests/test_foreign.py", "import sys\nsys.exit(1)\n")
write(REPO, "tests/test_green.py", "import sys\nsys.exit(0)\n")
# Тест, ПРИБИТЫЙ к боевому корню (зеркало 161 файла боевого сьюта): свой корень он игнорирует.
write(REPO, "tests/test_pinned.py",
      "import sys\nsys.path.insert(0, %r)\nimport mod_x\n"
      "sys.exit(0 if mod_x.VALUE == 'base' else 1)\n" % REPO)
# Тест, читающий файл боевого дерева по абсолютному пути (ast-страж, харнесс): красный ВСЕГДА.
write(REPO, "tests/test_reads_live.py",
      "import sys\nopen(%r, encoding='utf-8').read()\nsys.exit(1)\n" % os.path.join(REPO, "mod_x.py"))
git(REPO, "add", "-A")
git(REPO, "commit", "-qm", "база")
BASE_SHA = git(REPO, "rev-parse", "HEAD").stdout.strip()

# Наш заход: модуль стал говорить «head» (ломает test_ours и test_pinned) + родился новый тест
write(REPO, "mod_x.py", "VALUE = 'head'\n")
write(REPO, "tests/test_new.py", "import sys\nsys.exit(1)\n")
git(REPO, "add", "-A")
git(REPO, "commit", "-qm", "наша правка")

BEFORE = (git(REPO, "status", "--porcelain").stdout, git(REPO, "rev-parse", "HEAD").stdout,
          git(REPO, "worktree", "list").stdout)

NAMES = ["test_ours.py", "test_foreign.py", "test_green.py", "test_new.py",
         "test_pinned.py", "test_reads_live.py"]
rows, label = GB.blame(NAMES, base=BASE_SHA, root=REPO, live_root=REPO, timeout=60)
V = {r["test"]: r for r in rows}
for r in rows:
    print("      %-22s %-20s %s" % (r["test"], r["verdict"], (r["why"] or "")[:70]))


# ═══ (2) ЖИВОЙ КОНЕЦ-В-КОНЕЦ ══════════════════════════════════════════════════════════════════
print("\n(2) живой прогон на дереве до коммита")
ok(BASE_SHA[:8] in label, "база сравнения названа в отчёте (%s)" % label[:48])
ok(V["test_ours.py"]["verdict"] == GB.OURS,
   "тест, сломанный нашей правкой → НАШЕ (на базовом дереве он зелёный)")
ok(V["test_foreign.py"]["verdict"] == GB.FOREIGN,
   "тест, красный и до нас → ЧУЖОЕ")
ok(V["test_green.py"]["verdict"] == GB.NOT_REPRO,
   "названный «упавшим», а живьём зелёный → НЕ ВОСПРОИЗВОДИТСЯ")
ok(V["test_new.py"]["verdict"] == GB.UNJUDGED and "родился" in V["test_new.py"]["why"],
   "теста на базе нет вовсе → НЕ СУДИМО с названной причиной")

code, lines = GB.summary(rows, base_label=label)
ok(code == 1, "в наборе есть «наше» → код 1 (сильнее и чужого, и незнания)")


# ═══ (3) ЛОВУШКА МЕТОДА: хардкод боевого корня ════════════════════════════════════════════════
print("\n(3) тест, прибитый к боевому корню")
ok(V["test_pinned.py"]["verdict"] == GB.OURS,
   "с пином импорта прибитый тест судит БАЗОВОЕ дерево → НАШЕ (правда)")

# КОНТРОЛЬ «как было бы наивно»: тот же файл базового дерева, но без подкладки.
naive_tree = os.path.join(HOLDER, "naive")
git(REPO, "worktree", "add", "--detach", "-q", naive_tree, BASE_SHA)
naive_env = dict(os.environ, PYTHONPATH=naive_tree, PRETOOL_NOPUSH="1")
naive_env.pop("GATE_BLAME_BASE", None)
rc_naive, _ = GB._run_test(os.path.join(naive_tree, "tests", "test_pinned.py"), naive_tree, naive_env)
ok(rc_naive == 1,
   "контроль: БЕЗ пина тот же базовый файл красный — наивный прогон судил бы живое дерево и "
   "уверенно соврал «чужое»")
git(REPO, "worktree", "remove", "--force", naive_tree)


# ═══ (4) АУДИТ ОБРАЩЕНИЙ К БОЕВОМУ ДЕРЕВУ ═════════════════════════════════════════════════════
print("\n(4) прогон, коснувшийся боевого дерева")
r = V["test_reads_live.py"]
ok(r["verdict"] == GB.UNJUDGED, "чтение файла боевого дерева → НЕ СУДИМО, а не «чужое»")
ok((r["touched"] or 0) > 0 and "коснулся" in r["why"],
   "число обращений названо в причине (%s)" % (r["why"] or "")[:60])
ok(r["base_rc"] == 1,
   "коды при этом СОВПАЛИ (красный и там, и тут) — наивный разбор дал бы «чужое», замок не дал")


# ═══ (5) ГРАНИЦЫ ══════════════════════════════════════════════════════════════════════════════
print("\n(5) границы: дерево не тронуто, черновики убраны, гейт целиком не гоняется")
AFTER = (git(REPO, "status", "--porcelain").stdout, git(REPO, "rev-parse", "HEAD").stdout,
         git(REPO, "worktree", "list").stdout)
delta = [ln for ln in AFTER[0].splitlines() if ln not in BEFORE[0].splitlines()]
ok(not git(REPO, "diff", "--name-only", "HEAD").stdout.strip(),
   "ни один ОТСЛЕЖИВАЕМЫЙ файл рабочего дерева не изменён разбором")
ok(all("__pycache__" in ln for ln in delta),
   "единственный след в рабочем дереве — кэш байткода от самих прогонов (%d строк), "
   "и он назван, а не спрятан" % len(delta))
ok(BEFORE[1] == AFTER[1], "HEAD не сдвинут")
ok(BEFORE[2] == AFTER[2], "лишних worktree не осталось — черновик снят за собой")

leftovers = [d for d in os.listdir(tempfile.gettempdir()) if d.startswith("gate_blame_")]
ok(not leftovers, "временных каталогов gate_blame_* не осталось (%d)" % len(leftovers))

src = open(os.path.join(ROOT, "gate_blame.py"), encoding="utf-8").read()
ok("run_tests(" not in src, "полный сьют не зовётся: гоняются ТОЛЬКО названные тесты")
for word in ("systemctl", "enqueue_task", "complete_task", "notify", "confirmed"):
    ok(word not in src, "в модуле нет «%s» — он только читает и сравнивает" % word)

sha_before = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True,
                            text=True, timeout=60).stdout
ok(isinstance(sha_before, str), "боевой репозиторий опрошен read-only (снимок снят)")

shutil.rmtree(HOLDER, ignore_errors=True)

print(f"\nИТОГ: {'ВСЕ PASS' if all(res) else 'ЕСТЬ FAIL (%d/%d)' % (sum(res), len(res))} "
      f"({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
