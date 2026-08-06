"""ДЕТЕКТОР ДРЕЙФА ПРОДА — живой процесс отстал от origin/main (06.08.2026).

Владелец выбрал вариант «детектор без рестарта»: система замечает разрыв и ГОВОРИТ о нём
заметкой в ленту 829. Автоматики перезапуска нет ни в каком виде.

ГЛАВНОЕ, ЧТО ЗДЕСЬ ДОКАЗЫВАЕТСЯ, — определение отставания. Наивное («процесс стартовал раньше
коммита → он позади») ложно ровно в рабочем цикле этого репозитория: правку кладут на диск,
перезапускают сервис, чтобы проверить, и только потом коммитят. Секция (3) держит эту границу
голденом: там наивное правило ЗАГОВОРИЛО БЫ, а детектор молчит.

Секции:
(1) ГРАНИЦА УСТРОЙСТВОМ: модуль read-only (страж-инвариант), в руках демона нет ни рестарта,
    ни чужой команды; живой прогон сбора фактов зовёт РОВНО читающий git
(2) замыкание = что процесс держит В ПАМЯТИ: хуки (pretool_guard/posttool_feed) в него не
    входят по устройству — они подпроцесс на каждый вызов; docs/tests не код в памяти
(3) W1 (свидетель памяти) — сердце класса: коммит после старта + файл записан ДО старта → МОЛЧИМ
(4) W2 (свидетель содержимого): переписан без коммита в origin/main → молчим
(5) ПОРОГ: минуты — шум, часы — сигнал; DRIFT_HOURS=0 → ветка мертва
(6) /proc: юнит из cgroup, точка входа как ПУТЬ (длинный текст ТЗ с упоминанием имени — не процесс)
(7) разбор git log и снимок фактов
(8) ФОРМА заметки: без кнопок, без номера, без «да»
(9) РУКИ ДЕМОНА: одна заметка на эпизод, сбой канала не «съедает» эпизод, откат инертен
(10) FAIL-SAFE: нет /proc, git молчит, мусор в фактах → пусто (= поведение без детектора)
(11) ЖИВОЙ ФАКТ: ни один PID не сменился после полного прогона детектора
"""
import ast
import os
import subprocess
import sys
import tempfile

# Путь берётся ОТ ФАЙЛА ТЕСТА: тот же файл гоняется по дереву ДО правки (git worktree) — с
# хардкодом он импортировал бы новый код и «красный до» был бы ложью.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"
os.environ["PLAN_ADAPT"] = "0"
os.environ["CARD_DUTY"] = "0"
os.environ["CURATOR"] = "0"
os.environ["ORCH_TEST_MODE"] = "1"


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return bool(c)


res = []

try:
    import prod_drift as PD
except Exception as e:                                   # noqa: BLE001
    PD = None
    print("  (модуля prod_drift нет: %s)" % e)

# ПОРЯДОК ИМПОРТОВ ЗДЕСЬ — ЧАСТЬ МЕТОДА, А НЕ ВКУС. `orchestrator_daemon` держит REPO
# ЗАХАРДКОЖЕННЫМ («/root/turbobaby-manager-bot») и кладёт его ПЕРВЫМ в sys.path прямо при
# импорте. Значит в прогоне «ДО правки» через `git worktree` всё, что импортируется ПОСЛЕ
# демона, приезжает из БОЕВОГО дерева — то есть уже исправленным, и «красный до» получился бы
# ложным (поймано живьём на этом заходе: страж read-only зеленел на дереве без детектора).
# Поэтому свои модули берём ДО демона.
try:
    import invariants_check as IC
except Exception as e:                                   # noqa: BLE001
    IC = None
    print("  (модуля invariants_check нет: %s)" % e)

import orchestrator_daemon as OD                          # noqa: E402

T0 = 1_700_000_000.0
HOUR = 3600.0


def facts(started, files, commits, now, unit="orchestrator-daemon", pid=4242):
    """Факты в том виде, в каком их отдаёт snapshot() — решение проверяется БЕЗ живой машины."""
    return {"now": now, "procs": [{"unit": unit, "pid": pid, "started": started,
                                   "files": dict(files), "commits": list(commits)}]}


def commit(sha, ct, files, subject="правка"):
    return {"sha": sha, "ct": ct, "files": list(files), "subject": subject}


def naive(f):
    """НАИВНОЕ правило, которое мы отвергли: «коммит доехал после старта → процесс позади».
    Держим его в тесте живым, чтобы голден (3) доказывал РАЗНИЦУ, а не просто молчание."""
    out = []
    for p in f.get("procs") or []:
        for c in p.get("commits") or []:
            if c["ct"] > p["started"] and any(x in (p.get("files") or {}) for x in c["files"]):
                out.append(c["sha"])
    return out


# ═══════════ (1) ГРАНИЦА УСТРОЙСТВОМ: перезапустить он не может, а не «не станет» ═══════════
print("\n(1) граница устройством — детектор ничего не запускает и не пишет")
try:
    run = IC.CheckRun("PROD_DRIFT_READONLY")
    IC.check_prod_drift_readonly(None, run)
    _guard_clean, _guard_reg = (len(run.findings) == 0,
                                any(n == "PROD_DRIFT_READONLY" for n, _f in IC.CHECKS))
except Exception as e:                                   # noqa: BLE001
    _guard_clean = _guard_reg = False
    print("  (стража read-only нет: %r)" % e)
res.append(ok(_guard_clean, "(1) живой prod_drift.py проходит страж read-only (0 нарушений)"))
res.append(ok(_guard_reg, "(1) страж зарегистрирован в наборе инвариантов (попадёт в гейт)"))

# Руки демона: в теле _maybe_prod_drift не должно быть ни исполнителей, ни systemd-слов.
hand, banned, calls = None, [], set()
try:
    tree = ast.parse(open(os.path.join(REPO, "orchestrator_daemon.py"), encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_maybe_prod_drift":
            hand = node
    if hand is not None:
        body = ast.dump(hand)
        banned = [w for w in ("systemctl", "EXECUTORS", "restart_splinter", "systemd-run", "pkill")
                  if w in body]
        calls = {n.func.attr for n in ast.walk(hand)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
except Exception as e:                                   # noqa: BLE001
    print("  (разбор рук не удался: %r)" % e)
res.append(ok(hand is not None, "(1) руки детектора живут в демоне (_maybe_prod_drift)"))
res.append(ok(hand is not None and not banned,
              "(1) в руках нет ни исполнителя, ни слова рестарта: %s" % (banned or "чисто")))
res.append(ok(hand is not None and "run" not in calls and "Popen" not in calls,
              "(1) руки не запускают подпроцессов вовсе"))

# Живой прогон сбора фактов: какие внешние команды он вообще зовёт?
if PD:
    seen_cmds = []
    real_run = PD.subprocess.run

    class _Rec:
        returncode, stdout, stderr = 0, "", ""

    def _spy(argv, **kw):
        seen_cmds.append(list(argv))
        return _Rec()

    PD.subprocess.run = _spy
    try:
        PD.snapshot(now=T0)
    except Exception:
        pass
    PD.subprocess.run = real_run
    heads = {c[0] for c in seen_cmds if c}
    subs = {c[1] for c in seen_cmds if len(c) > 1}
    res.append(ok(heads <= {"git"} and bool(seen_cmds),
                  "(1) внешние команды живого сбора фактов: %s — и ничего кроме" % sorted(heads)))
    res.append(ok(subs <= set(PD.GIT_READ),
                  "(1) подкоманды git только читающие: %s" % sorted(subs)))
    res.append(ok(PD._git(["push", "origin", "main"]) is None,
                  "(1) пишущая подкоманда git не исполняется ВООБЩЕ (словарь GIT_READ)"))
else:
    res += [ok(False, "(1) живой сбор фактов зовёт git"), ok(False, "(1) подкоманда читающая"),
            ok(False, "(1) пишущий git не исполняется")]


# ═══════════ (2) ЗАМЫКАНИЕ = ЧТО ПРОЦЕСС ДЕРЖИТ В ПАМЯТИ ═══════════
print("\n(2) замыкание импортов — только код, который живёт в памяти процесса")
if PD:
    cl_d = PD.closure("orchestrator_daemon.py", REPO)
    cl_s = PD.closure("bot.py", REPO)
    res.append(ok({"orchestrator_daemon.py", "card_duty.py", "bridge_client.py"} <= cl_d,
                  "(2) замыкание демона держит его модули (%d файлов)" % len(cl_d)))
    res.append(ok("prod_drift.py" in cl_d,
                  "(2) детектор видит САМ СЕБЯ в памяти демона (свой дрейф тоже назовёт)"))
    res.append(ok({"splinter.py", "devbot.py", "bot.py"} <= cl_s,
                  "(2) замыкание splinter держит его модули (%d файлов)" % len(cl_s)))
    # ГРАНИЦА КЛАССА, выписанная в CLAUDE.md словами дважды: хуки — подпроцесс на каждый вызов,
    # они перечитываются с диска и дрейфовать не могут. Здесь это следует из устройства.
    res.append(ok("pretool_guard.py" not in cl_d and "pretool_guard.py" not in cl_s,
                  "(2) pretool_guard (хук) НЕ в замыкании — он не живёт в памяти процессов"))
    res.append(ok("posttool_feed.py" not in cl_d and "posttool_feed.py" not in cl_s,
                  "(2) posttool_feed (хук) НЕ в замыкании — та же граница класса"))
    res.append(ok(not any(f.startswith("docs/") or f.startswith("tests/") for f in cl_d | cl_s),
                  "(2) docs/ и tests/ в замыкание не входят — это не код в памяти"))
    d = tempfile.mkdtemp()
    open(os.path.join(d, "entry.py"), "w").write("import helper\nimport os\n")
    open(os.path.join(d, "helper.py"), "w").write("import deep\n")
    open(os.path.join(d, "deep.py"), "w").write("x = 1\n")
    open(os.path.join(d, "hook.py"), "w").write("y = 2\n")
    open(os.path.join(d, "broken.py"), "w").write("def f(:\n")
    res.append(ok(PD.closure("entry.py", d) == {"entry.py", "helper.py", "deep.py"},
                  "(2) обход транзитивный, чужие/неимпортированные файлы не попадают"))
    open(os.path.join(d, "entry.py"), "w").write("import broken\n")
    res.append(ok(PD.closure("entry.py", d) == {"entry.py", "broken.py"},
                  "(2) несобирающийся модуль не роняет замыкание (fail-safe)"))
    res.append(ok(PD.closure("нет-такого.py", d) == set(),
                  "(2) точки входа нет → пустое замыкание, а не исключение"))
else:
    res += [ok(False, "(2) замыкание демона"), ok(False, "(2) самонаблюдение"),
            ok(False, "(2) замыкание splinter"), ok(False, "(2) хук вне замыкания"),
            ok(False, "(2) лента вне замыкания"), ok(False, "(2) docs вне замыкания"),
            ok(False, "(2) транзитивность"), ok(False, "(2) битый модуль"), ok(False, "(2) нет входа")]


# ═══════════ (3) W1 — СВИДЕТЕЛЬ ПАМЯТИ (сердце класса) ═══════════
print("\n(3) отставание — по факту в памяти, а не по возрасту процесса")
if PD:
    # ГОЛДЕН РАБОЧЕГО ЦИКЛА: правку положили на диск (T0+100), перезапустили сервис (T0+500),
    # и только потом закоммитили (T0+600). Процесс держит НОВЫЙ код. Наивное правило заговорит.
    f_cycle = facts(started=T0 + 500, files={"orchestrator_daemon.py": T0 + 100},
                    commits=[commit("aaa1111", T0 + 600, ["orchestrator_daemon.py"])],
                    now=T0 + 600 + 10 * HOUR)
    res.append(ok(naive(f_cycle) == ["aaa1111"],
                  "(3) наивное правило «коммит моложе старта» ЗДЕСЬ ЗАГОВОРИЛО БЫ (контроль)"))
    res.append(ok(PD.verdict(f_cycle, 4) == [],
                  "(3) детектор МОЛЧИТ: файл записан ДО старта — процесс держит новый код"))
    # Настоящий дрейф: файл переписан ПОСЛЕ старта и изменение доехало коммитом.
    f_drift = facts(started=T0, files={"orchestrator_daemon.py": T0 + 100},
                    commits=[commit("bbb2222", T0 + 200, ["orchestrator_daemon.py"])],
                    now=T0 + 200 + 6 * HOUR)
    v = PD.verdict(f_drift, 4)
    res.append(ok(len(v) == 1 and v[0]["sha"] == "bbb2222",
                  "(3) файл переписан ПОСЛЕ старта + коммит доехал → заметка"))
    res.append(ok(len(v) == 1 and abs(v[0]["age"] - 6 * HOUR) < 1,
                  "(3) возраст разрыва считается от КОММИТА, а не от старта процесса"))
    res.append(ok(len(v) == 1 and v[0]["files"] == ["orchestrator_daemon.py"],
                  "(3) заметка называет ИМЕННО отставшие файлы"))
    # Синхронный прод: ничего не переписано после старта.
    f_sync = facts(started=T0 + 1000, files={"orchestrator_daemon.py": T0 + 100},
                   commits=[commit("ccc3333", T0 + 200, ["orchestrator_daemon.py"])],
                   now=T0 + 1000 + 50 * HOUR)
    res.append(ok(PD.verdict(f_sync, 4) == [], "(3) синхронный прод молчит (нечего сказать)"))
    # Первым неподхваченным считается САМЫЙ РАННИЙ коммит, а не последний.
    f_two = facts(started=T0, files={"a.py": T0 + 10, "b.py": T0 + 10},
                  commits=[commit("late999", T0 + 900, ["a.py"]), commit("early11", T0 + 100, ["b.py"])],
                  now=T0 + 100 + 9 * HOUR)
    v2 = PD.verdict(f_two, 4)
    res.append(ok(len(v2) == 1 and v2[0]["sha"] == "early11" and v2[0]["files"] == ["a.py", "b.py"],
                  "(3) разрыв меряется от ПЕРВОГО неподхваченного коммита, файлы собраны все"))
else:
    res += [ok(False, "(3) контроль наивного правила"), ok(False, "(3) молчим на рабочем цикле"),
            ok(False, "(3) настоящий дрейф"), ok(False, "(3) возраст от коммита"),
            ok(False, "(3) файлы названы"), ok(False, "(3) синхронный молчит"),
            ok(False, "(3) первый коммит")]


# ═══════════ (4) W2 — СВИДЕТЕЛЬ СОДЕРЖИМОГО ═══════════
print("\n(4) переписан ≠ изменён: без коммита в origin/main разрыва нет")
if PD:
    f_touch = facts(started=T0, files={"orchestrator_daemon.py": T0 + 100}, commits=[],
                    now=T0 + 50 * HOUR)
    res.append(ok(PD.verdict(f_touch, 4) == [],
                  "(4) mtime сдвинут (touch/checkout), коммита нет → молчим"))
    f_other = facts(started=T0, files={"orchestrator_daemon.py": T0 + 100},
                    commits=[commit("ddd4444", T0 + 200, ["docs/knowledge_base.md", "CLAUDE.md"])],
                    now=T0 + 50 * HOUR)
    res.append(ok(PD.verdict(f_other, 4) == [],
                  "(4) коммит тронул docs/CLAUDE.md — кода в памяти он не менял, молчим"))
    f_old = facts(started=T0 + 1000, files={"orchestrator_daemon.py": T0 + 2000},
                  commits=[commit("eee5555", T0 + 500, ["orchestrator_daemon.py"])],
                  now=T0 + 50 * HOUR)
    res.append(ok(PD.verdict(f_old, 4) == [],
                  "(4) коммит доехал ДО старта → процесс его уже держит, молчим"))
else:
    res += [ok(False, "(4) touch"), ok(False, "(4) docs"), ok(False, "(4) коммит до старта")]


# ═══════════ (5) ПОРОГ ═══════════
print("\n(5) порог: минуты — шум, часы — сигнал")
if PD:
    def aged(sec):
        return facts(started=T0, files={"orchestrator_daemon.py": T0 + 10},
                     commits=[commit("fff6666", T0 + 20, ["orchestrator_daemon.py"])],
                     now=T0 + 20 + sec)
    res.append(ok(PD.verdict(aged(3 * 60), 4) == [], "(5) разрыв 3 минуты — шум, молчим"))
    res.append(ok(PD.verdict(aged(2 * HOUR), 4) == [], "(5) разрыв 2 часа < порога — молчим"))
    res.append(ok(len(PD.verdict(aged(5 * HOUR), 4)) == 1, "(5) разрыв 5 часов > порога — говорим"))
    res.append(ok(len(PD.verdict(aged(90 * 60), 1)) == 1, "(5) порог настраиваемый (1 ч → говорим)"))
    res.append(ok(PD.verdict(aged(50 * HOUR), 0) == [],
                  "(5) ОТКАТ: порог 0 → вердикт пуст даже при разрыве в двое суток"))
    res.append(ok(PD.verdict(aged(50 * HOUR), -1) == [] and PD.verdict(aged(50 * HOUR), "x") == [],
                  "(5) мусорный порог не «включает» детектор (fail-safe)"))
    res.append(ok(PD.hours_env({"DRIFT_HOURS": "0"}) == 0
                  and PD.hours_env({"DRIFT_HOURS": "2.5"}) == 2.5
                  and PD.hours_env({}) == PD.DEFAULT_HOURS
                  and PD.hours_env({"DRIFT_HOURS": "мусор"}) == PD.DEFAULT_HOURS,
                  "(5) парсер порога: 0 значим (откат), мусор → дефолт %s ч" % PD.DEFAULT_HOURS))
    res.append(ok(PD.DEFAULT_HOURS == 4.0,
                  "(5) дефолт 4 ч — из замера (эпизоды 7 суток: разрыв 2 ч 30 м … 6 ч 09 м пуст)"))
else:
    res += [ok(False, "(5) 3 минуты"), ok(False, "(5) 2 часа"), ok(False, "(5) 5 часов"),
            ok(False, "(5) настраиваемый"), ok(False, "(5) откат"), ok(False, "(5) мусор"),
            ok(False, "(5) парсер"), ok(False, "(5) дефолт")]


# ═══════════ (6) /proc: КТО ЖИВОЙ И КОГДА ОН ПРОЧИТАЛ КОД ═══════════
print("\n(6) живой процесс — из /proc, а не из вывода команды управления")
if PD:
    proc = tempfile.mkdtemp()
    repo = tempfile.mkdtemp()
    open(os.path.join(repo, "orchestrator_daemon.py"), "w").write("x = 1\n")
    with open(os.path.join(proc, "stat"), "w") as f:
        f.write("cpu 1 2 3\nbtime 1699990000\n")
    hz = os.sysconf("SC_CLK_TCK")

    def mkproc(pid, cgroup, argv, ticks):
        d = os.path.join(proc, str(pid))
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "cgroup"), "w").write(cgroup)
        open(os.path.join(d, "cmdline"), "w").write("\x00".join(argv) + "\x00")
        # поле 22 = starttime; имя команды в скобках намеренно со скобкой и пробелом
        open(os.path.join(d, "stat"), "w").write(
            "%d (python3 (t)) S %s %d 0 0\n" % (pid, " ".join(["0"] * 18), ticks))

    mkproc(111, "0::/system.slice/orchestrator-daemon.service\n",
           [os.path.join(repo, "venv/bin/python3"), os.path.join(repo, "orchestrator_daemon.py")],
           500 * hz)
    got = PD.live("orchestrator-daemon", "orchestrator_daemon.py", proc=proc, repo=repo)
    res.append(ok(got and got["pid"] == 111, "(6) процесс юнита найден по cgroup + пути входа"))
    res.append(ok(got and abs(got["started"] - (1699990000 + 500)) < 1.5,
                  "(6) старт = btime + тики поля 22 (имя команды со скобками разобрано)"))
    # ЛОЖНЫЙ КАНДИДАТ: у claude-подпроцесса ТА ЖЕ cgroup, а имя файла лишь УПОМЯНУТО в тексте ТЗ.
    mkproc(222, "0::/system.slice/orchestrator-daemon.service\n",
           ["/usr/bin/claude", "-p", "ТЗ: поправь orchestrator_daemon.py и не сломай гейт"],
           900 * hz)
    got2 = PD.live("orchestrator-daemon", "orchestrator_daemon.py", proc=proc, repo=repo)
    res.append(ok(got2 and got2["pid"] == 111,
                  "(6) упоминание имени в длинном аргументе процессом НЕ считается"))
    mkproc(333, "0::/system.slice/splinter.service\n",
           [os.path.join(repo, "orchestrator_daemon.py")], 100 * hz)
    res.append(ok(PD.live("splinter", "bot.py", proc=proc, repo=repo) is None,
                  "(6) чужая точка входа в юните → процесса нет (не путаем сервисы)"))
    res.append(ok(PD.live("orchestrator-daemon", "orchestrator_daemon.py",
                          proc=os.path.join(proc, "нет"), repo=repo) is None,
                  "(6) нет /proc → None, а не исключение"))
else:
    res += [ok(False, "(6) поиск процесса"), ok(False, "(6) старт"), ok(False, "(6) ложный кандидат"),
            ok(False, "(6) чужая точка входа"), ok(False, "(6) нет /proc")]


# ═══════════ (7) РАЗБОР git log И СНИМОК ФАКТОВ ═══════════
print("\n(7) разбор истории origin/main")
if PD:
    sample = ("\x1eabc1234def\x1f1700000200\x1fправка демона\nprod_drift.py\norchestrator_daemon.py\n"
              "\x1e9876543210f\x1f1700000100\x1fправка доков\ndocs/x.md\n")
    real_git = PD._git
    PD._git = lambda args, cwd=None: sample
    cs = PD.commits_since(T0, REPO)
    PD._git = real_git
    res.append(ok(len(cs) == 2 and cs[0]["sha"] == "abc1234" and cs[0]["ct"] == 1700000200,
                  "(7) запись разобрана: короткий sha, время коммита, тема"))
    res.append(ok(cs[0]["files"] == ["prod_drift.py", "orchestrator_daemon.py"],
                  "(7) список изменённых файлов прочитан"))
    PD._git = lambda args, cwd=None: None
    res.append(ok(PD.commits_since(T0, REPO) == [],
                  "(7) git молчит (нет ref origin/main) → пусто, а не исключение"))
    PD._git = real_git
    snap = PD.snapshot(now=T0, proc=os.path.join(tempfile.mkdtemp(), "нет"), repo=REPO)
    res.append(ok(snap["procs"] == [] and snap["now"] == T0,
                  "(7) снимок без живых процессов пуст и не падает"))
else:
    res += [ok(False, "(7) разбор записи"), ok(False, "(7) файлы"), ok(False, "(7) git молчит"),
            ok(False, "(7) пустой снимок")]


# ═══════════ (8) ФОРМА ЗАМЕТКИ ═══════════
print("\n(8) форма: заметка, а не карточка")
if PD:
    note = PD.verdict(facts(started=T0, files={"a.py": T0 + 10, "b.py": T0 + 10, "c.py": T0 + 10,
                                               "d.py": T0 + 10},
                            commits=[commit("abc1234", T0 + 20, ["a.py", "b.py", "c.py", "d.py"],
                                            "очень длинная тема коммита, которая не влезет в строку целиком")],
                            now=T0 + 20 + 9 * HOUR), 4)[0]
    text = PD.render(note, "VPS")
    print("      " + text)
    res.append(ok("✅" not in text and "❌" not in text and "да " not in text.lower(),
                  "(8) ни кнопок, ни слова «да» — отвечать не на что"))
    res.append(ok("NEEDS_APPROVAL" not in text and "op=" not in text,
                  "(8) не карточка: ни маркера, ни op-кода"))
    res.append(ok("9 ч 0 мин" in text and "abc1234" in text,
                  "(8) названы возраст разрыва и первый неподхваченный коммит"))
    res.append(ok("(+1)" in text and "a.py" in text,
                  "(8) длинный список файлов ужат числом, а не обрезан молча"))
    res.append(ok(len(text) < 400, "(8) строка помещается в сообщение (%d символов)" % len(text)))
    res.append(ok("рестарт" in text.lower(),
                  "(8) заметка прямо говорит, что рестарта не будет — ожиданий не создаёт"))
    res.append(ok(PD.human_age(60) == "1 мин" and PD.human_age(2 * HOUR + 300) == "2 ч 5 мин"
                  and PD.human_age(30 * HOUR) == "1 сут 6 ч", "(8) возраст читается с телефона"))
else:
    res += [ok(False, "(8) без кнопок"), ok(False, "(8) не карточка"), ok(False, "(8) возраст"),
            ok(False, "(8) список файлов"), ok(False, "(8) длина"), ok(False, "(8) про рестарт"),
            ok(False, "(8) человеческий возраст")]


# ═══════════ (9) РУКИ ДЕМОНА ═══════════
print("\n(9) руки демона: одна заметка на эпизод, откат инертен")
state = tempfile.mkdtemp()
os.environ["CC_DRIFT_DIR"] = state
sent = []
calls = {"snapshot": 0}
if PD and hasattr(OD, "_maybe_prod_drift"):
    import notify as NF
    real_send, real_snap = NF.send_feed, PD.snapshot
    drift_facts = facts(started=T0, files={"orchestrator_daemon.py": T0 + 10},
                        commits=[commit("abc1234", T0 + 20, ["orchestrator_daemon.py"])],
                        now=T0 + 20 + 9 * HOUR)

    def fake_snap(now=None, **kw):
        calls["snapshot"] += 1
        return drift_facts

    NF.send_feed = lambda t: (sent.append(t), True)[1]
    PD.snapshot = fake_snap
    os.environ["DRIFT_HOURS"] = "4"
    OD._drift_next = 0.0
    said1 = OD._maybe_prod_drift(now=T0 + 20 + 9 * HOUR)
    OD._drift_next = 0.0
    said2 = OD._maybe_prod_drift(now=T0 + 20 + 10 * HOUR)
    res.append(ok(len(said1) == 1 and len(sent) == 1, "(9) отставание > порога → РОВНО одна заметка"))
    res.append(ok(said2 == [] and len(sent) == 1,
                  "(9) тот же эпизод второй раз не повторяется (дедуп по коммиту и старту)"))
    # рестарт процесса → новый эпизод (ключ другой), молчание не «залипает»
    drift_facts["procs"][0]["started"] = T0 + 5
    OD._drift_next = 0.0
    said3 = OD._maybe_prod_drift(now=T0 + 20 + 11 * HOUR)
    res.append(ok(len(said3) == 1 and len(sent) == 2,
                  "(9) другой экземпляр процесса = другой эпизод → заметка снова возможна"))
    # сбой канала: эпизод НЕ помечается — скажем на следующем замере
    NF.send_feed = lambda t: False
    drift_facts["procs"][0]["started"] = T0 + 9
    OD._drift_next = 0.0
    said4 = OD._maybe_prod_drift(now=T0 + 20 + 12 * HOUR)
    NF.send_feed = lambda t: (sent.append(t), True)[1]
    OD._drift_next = 0.0
    said5 = OD._maybe_prod_drift(now=T0 + 20 + 13 * HOUR)
    res.append(ok(said4 == [] and len(said5) == 1,
                  "(9) заметка не ушла → эпизод не «съеден», сказали на следующем замере"))
    # троттлинг: между замерами фактов не собираем
    before = calls["snapshot"]
    OD._maybe_prod_drift(now=T0 + 20 + 13 * HOUR + 5)
    res.append(ok(calls["snapshot"] == before, "(9) троттлинг: лишний цикл фактов не собирает"))
    # ОТКАТ: DRIFT_HOURS=0 → ни одного сбора фактов, ни одной заметки
    os.environ["DRIFT_HOURS"] = "0"
    OD._drift_next = 0.0
    before = calls["snapshot"]
    said6 = OD._maybe_prod_drift(now=T0 + 20 + 20 * HOUR)
    res.append(ok(said6 == [] and calls["snapshot"] == before,
                  "(9) DRIFT_HOURS=0 → ветка мертва: ни фактов, ни заметки, ни git"))
    os.environ["DRIFT_HOURS"] = "4"
    # сбой сбора фактов не роняет цикл демона
    PD.snapshot = lambda now=None, **kw: (_ for _ in ()).throw(RuntimeError("мост /proc упал"))
    OD._drift_next = 0.0
    res.append(ok(OD._maybe_prod_drift(now=T0 + 30 * HOUR) == [],
                  "(9) сбой сбора фактов → пусто, цикл демона жив"))
    PD.snapshot, NF.send_feed = real_snap, real_send
    os.environ.pop("DRIFT_HOURS", None)
    res.append(ok("_maybe_prod_drift" in OD.cycle.__code__.co_names,
                  "(9) детектор действительно зовётся из cycle() демона"))
else:
    res += [ok(False, "(9) одна заметка"), ok(False, "(9) дедуп"), ok(False, "(9) новый эпизод"),
            ok(False, "(9) сбой канала"), ok(False, "(9) троттлинг"), ok(False, "(9) откат"),
            ok(False, "(9) сбой фактов"), ok(False, "(9) вызов из cycle")]


# ═══════════ (10) FAIL-SAFE ═══════════
print("\n(10) fail-safe: любое сомнение → молчание (= поведение без детектора)")
if PD:
    res.append(ok(PD.verdict(None, 4) == [] and PD.verdict({}, 4) == []
                  and PD.verdict({"procs": None}, 4) == [], "(10) мусорные факты → пусто"))
    res.append(ok(PD.verdict(facts(0, {"a.py": T0}, [commit("x", T0, ["a.py"])], T0 + 99 * HOUR), 4) == [],
                  "(10) старт процесса неизвестен → молчим (сравнивать не с чем)"))
    res.append(ok(PD.verdict({"now": T0, "procs": [{"unit": "u", "started": T0 - 99 * HOUR}]}, 4) == [],
                  "(10) фактов о файлах нет → молчим"))
    res.append(ok(PD.started_at(999999999, proc=tempfile.mkdtemp()) is None,
                  "(10) нет /proc/<pid>/stat → None"))
else:
    res += [ok(False, "(10) мусор"), ok(False, "(10) нет старта"), ok(False, "(10) нет файлов"),
            ok(False, "(10) нет stat")]


# ═══════════ (11) ЖИВОЙ ФАКТ: НИ ОДИН ПРОЦЕСС НЕ ПЕРЕЗАПУЩЕН ═══════════
print("\n(11) живой факт: детектор прогнан по настоящей машине — PID не сменились")
if PD:
    def live_pids():
        out = {}
        for unit, entry in PD.WATCHED:
            p = PD.live(unit, entry)
            if p:
                out[unit] = p["pid"]
        return out

    before = live_pids()
    try:
        import notify as NF2
        _rs = NF2.send_feed
        NF2.send_feed = lambda t: True            # канал заглушен: тест ничего не отправляет
        OD._drift_next = 0.0
        os.environ["DRIFT_HOURS"] = "0.0001"      # порог почти нулевой: ветка отрабатывает целиком
        OD._maybe_prod_drift()
        os.environ.pop("DRIFT_HOURS", None)
        NF2.send_feed = _rs
    except Exception as e:                        # noqa: BLE001
        print("      (полный прогон не удался: %r)" % e)
    after = live_pids()
    res.append(ok(before == after and bool(before),
                  "(11) PID живых процессов до и после прогона совпали: %s" % (before or "процессов нет")))
else:
    res.append(ok(False, "(11) живой прогон"))

os.environ.pop("CC_DRIFT_DIR", None)

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
