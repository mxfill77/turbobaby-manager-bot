"""ЛИМИТ ПОСТАВЩИКА: машинное основание, повтор РОВНО ОДИН РАЗ под вторым слотом (20.09.2026).

ОТРИЦАТЕЛЬНЫЙ ТЕСТ — ЗАМОК ЗАХОДА (п.5 задания): секция (5) собирает состояние «ответ выглядит
как лимит» при ЖИВОМ втором слоте, гоняет ЖИВУЮ `run_task` с мок-`_POPEN` и показывает ЧИСЛОМ,
что заходов стало РОВНО ДВА и второй ушёл под ДРУГОЙ слот. КОНТРФАКТ секции (6): тот же вход со
СНЯТЫМ вторым слотом обязан дать ДРУГОЙ ответ — один заход и исход НЕИЗВЕСТНО.

Ни одного боевого файла, ни одной сети, ни одного значения токена в выводе: слоты — выдуманные
строки фикстуры, `_POPEN` подменён, лента замьючена.
"""
import ast
import json
import os
import sys

os.environ["ORCH_TEST_MODE"] = "1"
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ.setdefault("CHAIN_SERIES", "0")
os.environ.setdefault("SHADOW_RULE", "0")
os.environ.setdefault("CURATOR", "0")
os.environ.setdefault("PLAN_ADAPT", "0")
os.environ.setdefault("CARD_DUTY", "0")
os.environ.setdefault("ASK_DEDUP", "0")
os.environ.setdefault("STEP_SELFHEAL", "0")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import limit_slot as LS                                                    # noqa: E402

res = []


def ok(cond, title):
    res.append((bool(cond), title))
    return bool(cond)


# ── (1) машинное основание: судятся ПОЛЯ, а не английский текст ────────────────────────────────
ok(LS.envelope({"is_error": True, "api_error_status": 429})["verdict"] == LS.LIMIT,
   "(1a) is_error + api_error_status=429 → LIMIT")
ok(LS.envelope({"is_error": True, "api_error_status": "429"})["verdict"] == LS.LIMIT,
   "(1b) статус строкой разбирается так же (конверт не обещает типа)")
ok(LS.envelope({"is_error": False, "api_error_status": 429})["verdict"] == LS.CLEAN,
   "(1c) is_error ложно → CLEAN, даже если статус лимитный")
ok(LS.envelope({"is_error": True, "api_error_status": 404})["verdict"] == LS.UNSURE,
   "(1d) отказ с НЕлимитным статусом → UNSURE, а не LIMIT")
ok(LS.envelope({"is_error": True})["verdict"] == LS.UNSURE,
   "(1e) отказ без статуса → UNSURE (лимит НЕ доказан)")
ok(LS.envelope(None)["verdict"] == LS.CLEAN and LS.envelope("не json")["verdict"] == LS.CLEAN,
   "(1f) конверта нет → CLEAN (путь вызывающего прежний)")
ok(LS.envelope({"is_error": True, "api_error_status": True})["verdict"] == LS.UNSURE,
   "(1g) булево статусом не считается (True ≠ 1)")

# ГЛАВНОЕ ОТЛИЧИЕ ОТ ПРЕЖНЕГО: английский текст лимита БЕЗ машинных полей права не даёт.
_texty = {"result": "API Error: usage limit reached · weekly limit", "is_error": False}
ok(LS.envelope(_texty)["verdict"] == LS.CLEAN,
   "(1h) английский текст про usage limit БЕЗ is_error → CLEAN (текст основанием не является)")

# КОД ВЫХОДА ОСНОВАНИЕМ НЕ СДЕЛАН — его нет даже в сигнатуре.
_sig = ast.parse(open(os.path.join(REPO, "limit_slot.py"), encoding="utf-8").read())
_env_fn = [n for n in _sig.body if isinstance(n, ast.FunctionDef) and n.name == "envelope"][0]
ok([a.arg for a in _env_fn.args.args] == ["parsed"],
   "(1i) у envelope РОВНО один параметр (конверт) — код выхода физически не передаётся")

# ── (2) слот берётся из ОКРУЖЕНИЯ запуска, не из текста ────────────────────────────────────────
ENV_A = {LS.VAR_ACTIVE: "значение-первого", "TB_CLAUDE_TOKEN_A": "значение-первого",
         "TB_CLAUDE_TOKEN_B": "значение-второго"}
ENV_B = {LS.VAR_ACTIVE: "значение-второго", "TB_CLAUDE_TOKEN_A": "значение-первого",
         "TB_CLAUDE_TOKEN_B": "значение-второго"}
ok(LS.active_slot(ENV_A) == LS.SLOT_A and LS.active_slot(ENV_B) == LS.SLOT_B,
   "(2a) активный слот определяется равенством значений окружения")
ok(LS.active_slot({LS.VAR_ACTIVE: "чужое", "TB_CLAUDE_TOKEN_A": "a"}) == LS.SLOT_NONE,
   "(2b) не совпал ни с одним → слот НЕ определён")
ok(LS.active_slot({LS.VAR_ACTIVE: "", "TB_CLAUDE_TOKEN_A": ""}) == LS.SLOT_NONE,
   "(2c) пустое значение слотом не является")
ok(LS.other_slot(LS.SLOT_A) == LS.SLOT_B and LS.other_slot(LS.SLOT_B) == LS.SLOT_A,
   "(2d) второй слот — это другой слот")

# ЗАПРЕТ РАЗГЛАШЕНИЯ: ни одно поле вердикта не несёт значения токена.
_p = LS.plan({"is_error": True, "api_error_status": 429}, ENV_A)
_blob = json.dumps(_p, ensure_ascii=False)
ok("значение-первого" not in _blob and "значение-второго" not in _blob,
   "(2e) в вердикте НЕТ ни одного значения токена — только имена слотов и переменных")

# ── (3) план: повтор под другим слотом, ровно один ─────────────────────────────────────────────
ok(_p["action"] == LS.ACT_RETRY and _p["slot"] == LS.SLOT_A and _p["next"] == LS.SLOT_B,
   "(3a) шли под A → повтор под B")
_pb = LS.plan({"is_error": True, "api_error_status": 429}, ENV_B)
ok(_pb["action"] == LS.ACT_RETRY and _pb["next"] == LS.SLOT_A, "(3b) шли под B → повтор под A")
ok(LS.plan({"is_error": True, "api_error_status": 429}, ENV_A, retried=True)["action"]
   == LS.ACT_UNKNOWN, "(3c) повтор уже был → НЕИЗВЕСТНО, а не третий заход")
ok(LS.plan({"is_error": True, "api_error_status": 429},
           {LS.VAR_ACTIVE: "x", "TB_CLAUDE_TOKEN_A": "x", "TB_CLAUDE_TOKEN_B": ""})["action"]
   == LS.ACT_UNKNOWN, "(3d) второй слот пуст → НЕИЗВЕСТНО (повторять не подо что)")
ok(LS.plan({"is_error": True, "api_error_status": 429},
           {LS.VAR_ACTIVE: "чужое"})["action"] == LS.ACT_UNKNOWN,
   "(3e) слот не опознан → НЕИЗВЕСТНО, вслепую не повторяем")
ok(LS.plan({"is_error": False}, ENV_A)["action"] == LS.ACT_NONE,
   "(3f) не лимит → ACT_NONE, путь вызывающего прежний")
ok(LS.plan({"is_error": True, "api_error_status": 500}, ENV_A)["action"] == LS.ACT_NONE,
   "(3g) UNSURE повтора НЕ даёт (направление сомнения — в «не повторять»)")

# ── (4) время сброса ───────────────────────────────────────────────────────────────────────────
ok(LS.reset_at({"resets_at": "2026-09-21T00:00:00Z"}) == "2026-09-21T00:00:00Z",
   "(4a) время сброса читается, если названо")
ok(LS.reset_at({"is_error": True}) == "" and LS.reset_at(None) == "",
   "(4b) не названо → пусто, время не выдумывается")

# ══ ЖИВЫЕ РУКИ: подменяем только _POPEN, всё остальное боевое ═══════════════════════════════════
import orchestrator_daemon as OD                                           # noqa: E402

LIMIT_JSON = json.dumps({"result": "", "is_error": True, "api_error_status": 429,
                         "resets_at": "2026-09-21T09:00:00Z", "modelUsage": {}})
GOOD_JSON = json.dumps({"result": "готово", "is_error": False,
                        "modelUsage": {"claude-opus-5": {}}})


class FakeProc:
    def __init__(self, out, rc):
        self._out, self.returncode = out, rc

    def communicate(self, timeout=None):
        return self._out, ""

    def kill(self):
        pass


def run_with(env_extra, outs):
    """Прогнать ЖИВУЮ run_task с мок-_POPEN. → (исход, тело, [слоты заходов])."""
    seen = []
    calls = {"n": 0}

    def fake_popen(cmd, cwd=None, stdin=None, stdout=None, stderr=None, text=None, env=None):
        env = env or {}
        seen.append(LS.active_slot(env))
        i = calls["n"]
        calls["n"] += 1
        return FakeProc(outs[i] if i < len(outs) else outs[-1], 1 if "is_error\": true" in
                        (outs[i] if i < len(outs) else outs[-1]).lower() else 0)

    old_popen, old_env = OD._POPEN, dict(os.environ)
    old_feed = OD._feed_limit_note
    notes = []
    try:
        OD._POPEN = fake_popen
        OD._feed_limit_note = lambda tid, lim, reset: notes.append((tid, lim, reset))
        os.environ.update(env_extra)
        status, result = OD.run_task(777, "проверка лимита", task_timeout=5)
    finally:
        OD._POPEN, OD._feed_limit_note = old_popen, old_feed
        os.environ.clear()
        os.environ.update(old_env)
    return status, result, seen, notes


# ── (5) ОТРИЦАТЕЛЬНЫЙ ТЕСТ: лимит при ЖИВОМ втором слоте → РОВНО ОДИН повтор под другим ────────
BOTH = {LS.VAR_ACTIVE: "знач-A", "TB_CLAUDE_TOKEN_A": "знач-A", "TB_CLAUDE_TOKEN_B": "знач-B"}
st5, body5, seen5, notes5 = run_with(BOTH, [LIMIT_JSON, GOOD_JSON])
ok(len(seen5) == 2, "(5a) ЧИСЛО ЗАХОДОВ РОВНО ДВА (было бы 1 без правки): %d" % len(seen5))
ok(seen5 == [LS.SLOT_A, LS.SLOT_B],
   "(5b) первый заход под A, ПОВТОР под B — слоты заходов: %s" % seen5)
ok(st5 == "done" and "готово" in body5,
   "(5c) повтор удался → исход done, тело от ВТОРОГО захода")
ok(not notes5, "(5d) заметки о лимите нет: слот нашёлся, владельцу решать нечего")

# оба слота исчерпаны: лимит ОБА раза → ровно два захода и НЕИЗВЕСТНО
st5b, body5b, seen5b, notes5b = run_with(BOTH, [LIMIT_JSON, LIMIT_JSON])
ok(len(seen5b) == 2, "(5e) второй лимит подряд НЕ рождает третий заход: %d" % len(seen5b))
ok(OD.LIMIT_MARK in body5b and "НЕИЗВЕСТНО" in body5b,
   "(5f) оба слота исчерпаны → тело несёт маркер 🚦 и слово НЕИЗВЕСТНО")
ok("2026-09-21T09:00:00Z" in body5b, "(5g) время сброса названо в теле")
ok(len(notes5b) == 1 and notes5b[0][2] == "2026-09-21T09:00:00Z",
   "(5h) в ленту ушла РОВНО одна заметка с временем сброса")
ok("знач-A" not in body5b and "знач-B" not in body5b,
   "(5i) в теле исхода НЕТ ни одного значения токена")

# ── (6) КОНТРФАКТ: тот же вход со СНЯТЫМ вторым слотом → ДРУГОЙ ответ ──────────────────────────
ONLY_A = {LS.VAR_ACTIVE: "знач-A", "TB_CLAUDE_TOKEN_A": "знач-A", "TB_CLAUDE_TOKEN_B": ""}
st6, body6, seen6, notes6 = run_with(ONLY_A, [LIMIT_JSON, GOOD_JSON])
ok(len(seen6) == 1, "(6a) КОНТРФАКТ: второго слота нет → заход РОВНО ОДИН: %d" % len(seen6))
ok(st6 != st5 or body6 != body5,
   "(6b) КОНТРФАКТ: ответ ОТЛИЧАЕТСЯ от секции (5) — %r против %r" % (st6, st5))
ok(OD.LIMIT_MARK in body6 and "НЕИЗВЕСТНО" in body6,
   "(6c) КОНТРФАКТ: исход НЕИЗВЕСТНО, а не done")
ok(len(notes6) == 1, "(6d) КОНТРФАКТ: заметка владельцу ушла (ему есть что решать — ждать)")

# ── (7) ГРАНИЦЫ: здоровый и НЕлимитный путь БАЙТ-В-БАЙТ прежние ────────────────────────────────
st7, body7, seen7, notes7 = run_with(BOTH, [GOOD_JSON])
ok(len(seen7) == 1 and st7 == "done" and body7 == "готово",
   "(7a) здоровый заход: один вызов, done, тело дословно — повтора нет")
OTHER_ERR = json.dumps({"result": "boom", "is_error": True, "api_error_status": 500,
                        "modelUsage": {}})
st7b, body7b, seen7b, notes7b = run_with(BOTH, [OTHER_ERR])
ok(len(seen7b) == 1 and st7b == "failed",
   "(7b) НЕлимитный отказ: один вызов, честный failed — повтора нет")
ok(OD.LIMIT_MARK not in body7b, "(7c) НЕлимитный отказ маркером лимита НЕ метится")
ok(not notes7b, "(7d) НЕлимитный отказ владельцу в ленту не идёт")

# ── (8) п.6: пустой ввод перенаправлен у ОБОИХ вызовов claude ──────────────────────────────────
_src = open(os.path.join(REPO, "orchestrator_daemon.py"), encoding="utf-8").read()
_tree = ast.parse(_src)
_calls = [n for n in ast.walk(_tree) if isinstance(n, ast.Call)]


def _is_claude_spawn(node):
    f = node.func
    name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
    if name not in ("run", "_POPEN"):
        return False
    return any(isinstance(k.value, ast.Name) and k.value.id == "child_env"
               for k in node.keywords if k.arg == "env")


_spawns = [n for n in _calls if _is_claude_spawn(n)]
ok(len(_spawns) == 2, "(8a) вызовов claude с child_env ровно два (исполнитель и думатель): %d"
   % len(_spawns))
ok(all(any(k.arg == "stdin" for k in n.keywords) for n in _spawns),
   "(8b) у ОБОИХ вызовов задан stdin (пустой ввод) — нет ожидания три секунды")

# ── (9) чистота решения: импортов НОЛЬ ─────────────────────────────────────────────────────────
_ls_tree = ast.parse(open(os.path.join(REPO, "limit_slot.py"), encoding="utf-8").read())
_imports = [n for n in ast.walk(_ls_tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
ok(not _imports, "(9a) у limit_slot импортов НОЛЬ: %d" % len(_imports))
_names = {getattr(n.func, "id", "") for n in ast.walk(_ls_tree) if isinstance(n, ast.Call)}
ok(not ({"open", "print", "exec", "eval", "__import__"} & _names),
   "(9b) решение не умеет ни печатать, ни открывать — значению токена нет дороги наружу")

# ── итог ───────────────────────────────────────────────────────────────────────────────────────
_bad = [t for good, t in res if not good]
for good, t in res:
    print(("PASS  " if good else "FAIL  ") + t)
print("\n%d/%d" % (len(res) - len(_bad), len(res)))
if _bad:
    print("КРАСНЫЕ:")
    for t in _bad:
        print("  -", t)
    sys.exit(1)
