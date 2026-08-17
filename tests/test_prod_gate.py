"""ПРАВО НА ПРОД ТРЕБУЕТ ПОЛНОГО ГЕЙТА (17.08.2026) — четыре замка задания.

ПОВОД, ИЗМЕРЕННЫЙ ПО ЖУРНАЛУ ДЕМОНА, ОТЧЁТАМ ЗАДАЧ И cc_log (15.08–17.08): путь конвертов дал
ПЯТЬ доставок в прод, и право на перезапуск живого сервиса получил СЕЛЕКТИВНЫЙ набор трижды —
конверт 15 (задача 17) по 77 тестам, конверт 31 (задача 32) по 78, конверт 43 (задача 45) по 79,
при полном наборе 216. Дважды исполнитель вспомнил правило сам (конверт 33 → полный 211 и прямая
фраза «для прод-операции не авторизация»; конверт 51 → полный сразу). Одна из трёх селективных
(конверт 31) НАЗВАЛА законную причину — «полный 216 прогонялся заходом коммита, дерево после него
не менялось», — поэтому здесь не запрет, а обязательная явная причина.

ЗАМКИ:
 A. ОБЫЧНЫЕ ЗАХОДЫ НЕ ЗАДЕТЫ — селективный набор работает там, где работал (посимвольно тот же
    вывод гейта, тот же выбор набора, ноль новых строк) + корпус живых ТЗ: обычных заходов,
    признанных доставкой, НОЛЬ.
 B. ОТРИЦАТЕЛЬНЫЙ ТЕСТ — доставка, собранная с селективным набором, права на перезапуск НЕ
    получает: набор поднимается до ПОЛНОГО, и если полный красный — exit 1, перезапуска нет.
 C. ПРИЧИНА ВИДНА — пустая причина права не даёт; названная даёт и уезжает в вывод и в журнал.
 D. ХОД ЦЕПИ ПРЕЖНИЙ — терминал задачи (status, result) посимвольно равен при метке и без неё.

Всё in-process с моками (run_tests / run_selective_tests / _log / _push / _POPEN): ни сети, ни
реальных прогонов тестов, ни пушей, ни моста, ни очереди.
"""
import contextlib
import hashlib
import io
import json
import os
import sys

ROOT = "/root/turbobaby-manager-bot"
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["CURATOR"] = "0"                 # изоляция от боевого .env (принудительно, env демона)
os.environ["PLAN_ADAPT"] = "0"
os.environ["STEP_SELFHEAL"] = "0"
os.environ["CARD_DUTY"] = "0"
os.environ["GATE_SINGLE_SELECTIVE"] = "0"   # предмет теста задаём сами, не боевым конфигом
os.environ.pop("CC_PROD_DELIVERY", None)    # метку ставим только сами
os.environ.pop("GATE_STEP_SELECTIVE", None)

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return c


import gate                                                          # noqa: E402
import prod_gate                                                     # noqa: E402

# ── живые ТЗ прода: конверты доставки, кураторский конверт, обычные заходы ────────────────────
def _tz(rel):
    with open(os.path.join(ROOT, "reports", rel), encoding="utf-8") as f:
        t = f.read().split("## Отчёт")[0]
    return t.split("## ТЗ")[-1].strip()


TZ_D43 = _tz("2026-08-17/task-45.md")        # конверт 43 → селективный 79, право взято молча
TZ_D15 = _tz("2026-08-16/task-17.md")        # конверт 15 → селективный 77, право взято молча
TZ_D33 = _tz("2026-08-15/task-34.md")        # конверт 33 → полный 211, «не авторизация»
TZ_C312 = _tz("2026-08-05/task-312.md")      # кураторский конверт с пунктом рестарта splinter
TZ_SQL = _tz("2026-08-14/task-544.md")       # конверт БЕЗ рестарта (SQL) — не доставка
TZ_PLAIN = _tz("2026-08-16/task-27.md")      # обычный заход


# ═══════════════ (1) РЕШЕНИЕ: ЧТО СЧИТАЕТСЯ ПУТЁМ ДОСТАВКИ (на ДОСЛОВНЫХ ТЗ) ═════════════════
print("(1) путь доставки узнаётся у КОНВЕРТА с названным перезапуском:")
ok(prod_gate.is_delivery(TZ_D43), "конверт 43 (доставка коммита 3d63d42) — доставка")
ok(prod_gate.is_delivery(TZ_D15), "конверт 15 (доставка коммита 7f147a0) — доставка")
ok(prod_gate.is_delivery(TZ_D33), "конверт 33 (доставка коммита 0b6ab43) — доставка")
ok(prod_gate.is_delivery(TZ_C312), "кураторский конверт 312 (пункт «рестарт splinter») — доставка")
ok("service:orchestrator-daemon" in (prod_gate.why_delivery(TZ_D43) or ""),
   "причина названа семьёй операции, а не пересказом")
ok(not prod_gate.is_delivery(TZ_SQL), "конверт БЕЗ перезапуска (SQL) доставкой НЕ считается")
ok(not prod_gate.is_delivery(TZ_PLAIN), "обычный заход доставкой НЕ считается")
ok(not prod_gate.is_delivery("рестарт splinter обязателен, перезапусти демон оркестратора"),
   "не-конверт с рестартом в тексте — НЕ доставка (правило конверта)")
ok(not prod_gate.is_delivery("цитата: [конверт одобренной заявки 9] рестарт splinter"),
   "маркер конверта НЕ первым (цитата в прозе) — не доставка (правило позиции)")
ok(prod_gate.is_delivery("[конверт одобренной заявки 9] " + "х" * 5000
                         + " systemctl restart splinter"),
   "длинный конверт: перезапуск найден не только в голове текста")


# ═══════════════════ (2) ЗАМОК B — ОТРИЦАТЕЛЬНЫЙ ТЕСТ: ПРАВА НЕТ ═════════════════════════════
CALLS = []
_real_run_tests, _real_run_sel = gate.run_tests, gate.run_selective_tests
pushes, logs = [], []
gate._push = lambda text: pushes.append(text)
gate._log = lambda result, args_str: logs.append((result, args_str))


def _mock(red_full=False, red_sel=False, n_full=217, n_sel=79):
    def full():
        CALLS.append("full")
        return (["test_fake_red.py"] if red_full else []), n_full, 0.1

    def sel(changed=None):
        CALLS.append("selective")
        return (["test_fake_red.py"] if red_sel else []), n_sel, 0.1, f"селективный ({n_sel} тестов)"
    gate.run_tests, gate.run_selective_tests = full, sel


def run_gate(argv, selective=False, delivery=False, **mock):
    """gate.main() с мокнутыми прогонами. Вернуть (exit_code, stdout, вызванные наборы)."""
    CALLS.clear(); pushes.clear(); logs.clear()
    _mock(**mock)
    saved = {k: os.environ.get(k) for k in ("GATE_STEP_SELECTIVE", "CC_PROD_DELIVERY",
                                            "GATE_ALERT_FINAL_ONLY")}
    old_argv = sys.argv
    sys.argv = ["gate.py"] + argv
    if selective:
        os.environ["GATE_STEP_SELECTIVE"] = "1"
    else:
        os.environ.pop("GATE_STEP_SELECTIVE", None)
    if delivery:
        os.environ[prod_gate.ENV_MARK] = "1"
    else:
        os.environ.pop(prod_gate.ENV_MARK, None)
    os.environ["GATE_ALERT_FINAL_ONLY"] = "1"          # тестовый прогон владельцу не шумит
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = gate.main()
    finally:
        sys.argv = old_argv
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return code, buf.getvalue(), list(CALLS)


print("\n(2) ЗАМОК B: доставка + СЕЛЕКТИВНЫЙ набор → права на перезапуск НЕТ:")
v = prod_gate.decide(True, True, None)
ok(v["authorizes"] is False, "решение: селективный набор доставку НЕ авторизует")
ok(v["run"] == "full", "решение: набор поднимается до ПОЛНОГО (право зарабатывается, не отзывается)")
code, out, calls = run_gate([], selective=True, delivery=True)
ok(calls == ["full"], "гейт прогнал ПОЛНЫЙ набор, селективный НЕ гонялся вовсе")
ok(code == 0 and "ПРАВО НА ДОСТАВКУ В ПРОД дано ПОЛНЫМ набором (217 тестов)" in out,
   "право названо в выводе и дано ПОЛНЫМ набором")
ok("СЕЛЕКТИВНЫЙ НАБОР ПРАВА НА ДОСТАВКУ В ПРОД НЕ ДАЁТ" in out,
   "исполнителю сказано, почему набор поднят (правило в коде, а не в голове)")
ok(logs and logs[0][0] == "prod_delivery_full", "запись в журнал: чем дано право")
code, out, calls = run_gate([], selective=True, delivery=True, red_full=True)
ok(code == 1 and calls == ["full"] and "ЗАБЛОКИРОВАН" in out,
   "полный набор красный → exit 1: перезапуска не будет (право не выдано ничем)")
code, out, calls = run_gate([], selective=True, delivery=True, red_sel=True)
ok(code == 0 and calls == ["full"],
   "красный СЕЛЕКТИВНЫЙ набор исхода не решает — его не спрашивают вовсе")
code, out, calls = run_gate(["--for", "restart_splinter"], selective=True, delivery=False)
ok(calls == ["full"] and "ПОЛНЫМ набором" in out,
   "дверь без метки демона: ярлык операции «restart_splinter» сам называет доставку")


# ═══════════════════════ (3) ЗАМОК C — ПРИЧИНА ВИДНА, ПУСТАЯ НЕ ДАЁТ ═════════════════════════
print("\n(3) ЗАМОК C: причина видна; пустая причина права не даёт:")
REASON = "полный 216 зелёный на ЭТОМ дереве, дерево после него не менялось"
code, out, calls = run_gate(["--selective-reason", REASON], selective=True, delivery=True)
ok(calls == ["selective"], "названная причина допускает селективный набор (законный случай 31)")
ok(REASON in out and "по НАЗВАННОЙ причине" in out, "причина стоит В ВЫВОДЕ дословно")
ok(logs and logs[0][0] == "prod_delivery_selective_reason" and REASON in logs[0][1],
   "причина уехала В ЖУРНАЛ дословно")
for junk in ("", "   ", "—", "-", "нет", "n/a", ".", "tbd"):
    code, out, calls = run_gate(["--selective-reason", junk], selective=True, delivery=True)
    ok(calls == ["full"], f"причина-заполнитель {junk!r} права не даёт → полный набор")
code, out, calls = run_gate(["--selective-reason"], selective=True, delivery=True)
ok(calls == ["full"], "флаг без значения права не даёт → полный набор")
ok(prod_gate.reason_named("быстро") is True,
   "КАЧЕСТВО причины не судится — судится наличие (слабую причину видно в отчёте)")
ok(prod_gate.decide(True, False, REASON)["reason"] == "",
   "полный набор причины не требует — она не подмешивается в право")


# ══════════════════ (4) ЗАМОК A — ОБЫЧНЫЕ ЗАХОДЫ НЕ ЗАДЕТЫ (посимвольно) ═════════════════════
print("\n(4) ЗАМОК A: обычные заходы не задеты:")
v = prod_gate.decide(False, True, None)
ok(v["run"] == "selective" and v["say"] == "" and v["authorizes"] is True,
   "решение обычного захода: набор прежний, слова нет")
code_a, out_a, calls_a = run_gate([], selective=True, delivery=False)
ok(calls_a == ["selective"] and code_a == 0, "обычный заход: селективный набор работает, как работал")
ok("ДОСТАВКА В ПРОД" not in out_a and "ПРАВО НА" not in out_a,
   "в выводе обычного захода НИ ОДНОЙ новой строки")
# Голден собираем из ЖИВОГО храповика, а не из его сегодняшнего числа: предмет замка — что этот
# заход не добавил обычному прогону НИ ОДНОЙ строки, а не сколько слепых читателей в репо.
_ratchet = "".join(ln + "\n" for ln in gate._run_ratchet()[1])
ok(out_a == _ratchet + "✅ ГЕЙТ (селективный (79 тестов)): 79 тестов зелёные (0.1с) — "
                       "прод-операция «prod» разрешена.\n",
   "вывод обычного селективного прогона ПОСИМВОЛЬНО прежний")
ok(logs == [], "обычный заход не платит ни одной новой записи в журнал")
code_b, out_b, calls_b = run_gate(["--for", "push", "--final"], selective=True, delivery=False)
ok(calls_b == ["full"] and "прод-операция «push» разрешена" in out_b,
   "pre-push (--for push --final) — полный набор, как был")
ok("ПРАВО НА" not in out_b, "push доставкой не считается: ни одной новой строки")
code_c, out_c, calls_c = run_gate([], selective=False, delivery=False)
ok(calls_c == ["full"] and out_c == _ratchet + "✅ ГЕЙТ (полный): 217 тестов зелёные (0.1с) — "
                                               "прод-операция «prod» разрешена.\n",
   "обычный ПОЛНЫЙ прогон посимвольно прежний")

# корпус живых ТЗ: сколько обычных заходов правило признало бы доставкой
import glob                                                          # noqa: E402
corp_plain = corp_deliv = 0
for path in glob.glob(os.path.join(ROOT, "reports", "2026-08-*", "task-*.md")):
    with open(path, encoding="utf-8", errors="ignore") as f:
        body = f.read().split("## Отчёт")[0].split("## ТЗ")[-1].strip()
    if prod_gate.is_convert(body):
        corp_deliv += 1 if prod_gate.is_delivery(body) else 0
    else:
        corp_plain += 1 if prod_gate.is_delivery(body) else 0
ok(corp_plain == 0, f"корпус живых ТЗ: обычных заходов, признанных доставкой — {corp_plain} (ноль)")
ok(corp_deliv >= 10, f"конвертов-доставок в корпусе найдено {corp_deliv} (замер обещал 10)")


# ═════════════ (5) ДЕМОН: МЕТКА ТОЛЬКО ДОСТАВКЕ, ФЛАГ СЕЛЕКТИВНОСТИ НЕ ТРОНУТ ════════════════
print("\n(5) демон: метка доставки и неприкосновенность флага селективности:")
import orchestrator_daemon as OD                                     # noqa: E402

_good_out = json.dumps({"result": "готово", "is_error": False,
                        "modelUsage": {"claude-fable-5": {}}})


class _FakePopen:
    def __init__(s, out="", rc=0):
        s.returncode = None; s._out = out; s._rc = rc

    def communicate(s, timeout=None):
        if s.returncode is None:
            s.returncode = s._rc
        return s._out, ""

    def terminate(s): s.returncode = -15

    def kill(s): s.returncode = -9

    def poll(s): return s.returncode


CAP = {}
OD.MAX_CLAUDE_PROCS = 0


def cap_popen(args, **kw):
    CAP.update({"args": list(args), "env": dict(kw.get("env") or {})})
    return _FakePopen(out=_good_out)


OD._POPEN = cap_popen
OD.subprocess.run = lambda args, **kw: type("P", (), {"stdout": _good_out, "stderr": "",
                                                      "returncode": 0})()


def daemon_env(task_text, preamble=None, single_sel="0", tid=901):
    saved = os.environ.get("GATE_SINGLE_SELECTIVE")
    os.environ["GATE_SINGLE_SELECTIVE"] = single_sel
    try:
        OD.run_task(tid, task_text, task_timeout=60, preamble=preamble)
        return dict(CAP["env"])
    finally:
        if saved is None:
            os.environ.pop("GATE_SINGLE_SELECTIVE", None)
        else:
            os.environ["GATE_SINGLE_SELECTIVE"] = saved


env = daemon_env(TZ_D43, single_sel="1")
ok(env.get(prod_gate.ENV_MARK) == "1", "задача доставки получает метку CC_PROD_DELIVERY=1")
ok(env.get("GATE_STEP_SELECTIVE") == "1",
   "флаг селективности демона НЕ ТРОНУТ (решение живёт в одном месте — в гейте)")
env = daemon_env(TZ_PLAIN, single_sel="1")
ok(env.get(prod_gate.ENV_MARK) is None, "обычная одиночка метки НЕ получает")
ok(env.get("GATE_STEP_SELECTIVE") == "1", "обычная одиночка: селективный флаг как был")
env = daemon_env("[шаг 2/5 родитель 10] промежуточный шаг", single_sel="0")
ok(env.get("GATE_STEP_SELECTIVE") == "1" and env.get(prod_gate.ENV_MARK) is None,
   "промежуточный шаг цепи: селективный как был, метки нет")
env = daemon_env(TZ_D43, preamble=OD.PLANNER_PREAMBLE, single_sel="1", tid=902)
ok(env.get(prod_gate.ENV_MARK) is None, "планировщик метки не получает (он гейт не гоняет)")
os.environ[prod_gate.ENV_MARK] = "1"                   # унаследованная метка обязана сбрасываться
env = daemon_env(TZ_PLAIN, single_sel="1", tid=903)
os.environ.pop(prod_gate.ENV_MARK, None)
ok(env.get(prod_gate.ENV_MARK) is None,
   "метка НЕ наследуется из окружения демона — задаётся только решением")


# ═════════════════ (6) ЗАМОК D — ХОД ЦЕПИ ПРЕЖНИЙ: ТЕРМИНАЛЫ ПОСИМВОЛЬНО ═════════════════════
print("\n(6) ЗАМОК D: терминалы посимвольно равны при метке и без неё:")
_real_is_delivery = prod_gate.is_delivery
terms = {}
for name, patch in (("с правилом", None), ("без правила", lambda *_a, **_k: False)):
    if patch:
        prod_gate.is_delivery = patch
    try:
        out_rows = []
        for tid, text in ((911, TZ_D43), (912, TZ_D15), (913, TZ_PLAIN),
                          (914, "[шаг 2/5 родитель 10] шаг цепи")):
            saved = os.environ.get("GATE_SINGLE_SELECTIVE")
            os.environ["GATE_SINGLE_SELECTIVE"] = "1"
            try:
                out_rows.append(OD.run_task(tid, text, task_timeout=60))
            finally:
                if saved is None:
                    os.environ.pop("GATE_SINGLE_SELECTIVE", None)
                else:
                    os.environ["GATE_SINGLE_SELECTIVE"] = saved
        terms[name] = out_rows
    finally:
        prod_gate.is_delivery = _real_is_delivery

a, b = terms["с правилом"], terms["без правила"]
ok(a == b, "четыре терминала (status, result) совпали ПОСИМВОЛЬНО")
sha = hashlib.sha256(repr(a).encode("utf-8")).hexdigest()[:12]
ok(sha == hashlib.sha256(repr(b).encode("utf-8")).hexdigest()[:12],
   f"sha256 снимка терминалов совпал: {sha}")
ok(all(st == "done" for st, _r in a), "исход задач не изменился (done)")


# ══════════════════════════ (7) ЗЕРКАЛА ЛИТЕРАЛОВ — РАЗОЙТИСЬ НЕ МОГУТ ═══════════════════════
print("\n(7) зеркала литералов:")
ok(prod_gate.CONVERT_HEAD == OD._CONVERT_MARK,
   f"маркер конверта = зеркало демона ({prod_gate.CONVERT_HEAD!r})")
ok(gate._ENV_MARK_FALLBACK == prod_gate.ENV_MARK, "имя метки в гейте = имя в решении")
ok(gate._REASON_FLAG_FALLBACK == prod_gate.REASON_FLAG, "имя флага причины: одно на двоих")
ok(prod_gate.SERVICE_KEY_PREFIX == "service:"
   and any(k.startswith(prod_gate.SERVICE_KEY_PREFIX)
           for k in [o["key"] for o in
                     __import__("curator_ops").operations("рестарт splinter")]),
   "префикс семьи «service:» = то, что отдаёт живой curator_ops")


# ═══════════════════════════════ (8) ЧИСТОТА: ast-СТРАЖ В ГЕЙТЕ ══════════════════════════════
print("\n(8) чистота решения (PROD_GATE_PURE):")
import invariants_check as IC                                        # noqa: E402


class _Run:
    def __init__(s):
        s.flags = []

    def flag(s, where, why):
        s.flags.append((where, why))


def run_guard(path=None):
    saved = IC._PROD_GATE_PATH
    IC._PROD_GATE_PATH = path
    try:
        run = _Run()
        IC.check_prod_gate_pure(None, run)
        return list(run.flags)
    finally:
        IC._PROD_GATE_PATH = saved


ok(run_guard() == [], "боевой prod_gate.py — чист (импортов ровно два, рук нет)")
# Фикстура — во ВРЕМЕННЫЙ каталог (образец `tests/test_deliver_card.py`): тест живёт в гейте
# постоянно, привязывать его к каталогу одного захода нельзя.
dirty = "/tmp/cc_prod_gate_hands_fixture.py"
with open(dirty, "w", encoding="utf-8") as f:
    f.write("import subprocess\n\n\ndef go():\n    subprocess.run(['systemctl', 'restart', 'x'])\n")
ok(run_guard(dirty) != [], "нечистая копия (subprocess) — ФЛАГ")
ok(run_guard("/tmp/cc_prod_gate_missing_fixture.py") != [],
   "файла нет → ФЛАГ (нечитаемое правило доверия не имеет)")
src = open(os.path.join(ROOT, "prod_gate.py"), encoding="utf-8").read()
ok("subprocess" not in src and "systemctl" not in src and "os.remove" not in src,
   "в решении нет ни подпроцессов, ни команд перезапуска, ни удаления")


# ══════════════════ (9) ДЕГРАДАЦИЯ: МОДУЛЯ РЕШЕНИЯ НЕТ → ДОСТАВКА ИДЁТ ПОЛНЫМ ════════════════
print("\n(9) деградация без модуля решения:")
_saved_pg = gate.prod_gate
gate.prod_gate = None
try:
    code, out, calls = run_gate([], selective=True, delivery=True)
    ok(calls == ["full"] and "не прочитан" in out,
       "модуля нет + метка есть → ПОЛНЫЙ набор (деградация в сторону прода)")
    code, out, calls = run_gate([], selective=True, delivery=False)
    ok(calls == ["selective"] and "ДОСТАВКА" not in out,
       "модуля нет + метки нет → обычный заход идёт селективным, как шёл")
finally:
    gate.prod_gate = _saved_pg
ok(gate.prod_gate is not None, "модуль решения возвращён на место")


# ═══════════════════════════ (10) ГРАНИЦЫ: ЧТО НЕ ОСЛАБЛЕНО ══════════════════════════════════
print("\n(10) границы:")
code, out, calls = run_gate(["--override", "ложное красное"], selective=True, delivery=True)
ok(code == 0 and calls == [] and "ГЕЙТ ОБОЙДЁН" in out,
   "обход владельца (--override) НЕ ослаблен и не изменён")
ok(logs and logs[0][0] == "test_override", "обход по-прежнему виден в журнале как test_override")
ok(prod_gate.op_is_delivery("push") is False and prod_gate.op_is_delivery("prod") is False,
   "push и prod доставкой не считаются (иначе задело бы почти все живые прогоны)")
ok(prod_gate.op_is_delivery("restart_splinter") and prod_gate.op_is_delivery("доставка"),
   "ярлыки restart/доставка узнаются")
ok(prod_gate.is_delivery(None) is False and prod_gate.decide(None, None, None)["run"] == "full",
   "мусор на входе: не доставка / полный набор — без исключений")
gate.run_tests, gate.run_selective_tests = _real_run_tests, _real_run_sel

print(f"\n=== ИТОГ: {sum(res)}/{len(res)} ===")
sys.exit(0 if all(res) else 1)
