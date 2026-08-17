# -*- coding: utf-8 -*-
"""ТЕНЬ СУДИТ ЦЕПОЧКУ, А НЕ КАЖДЫЙ ШАГ (16.08.2026, поправка Штаба к контракту третьего исхода).

СЧИТАТЬ, НЕ ПРИМЕНЯТЬ — как и у пошаговой тени (`tests/test_shadow_rule.py`, 46/46, коммит
`9a57117`). Здесь проверяется ЕДИНИЦА: контракт повесил адрес результата на ШАГ, а метрика фазы
считается ЦЕПОЧКАМИ (рамка §8г запрещает плоский счёт записей прямо). Промежуточный служебный шаг
своего продукта не имеет и иметь не должен: суди его по собственному адресу — и цепочка рвётся на
ровном месте.

Правила поправки, каждое — своей секцией:
  * адрес берётся из КОРНЕВОЙ записи, исход один из трёх на всю цепочку;
  * шаг БЕЗ своего адреса цепочку НЕ обрывает — и не «потому что мы так решили», а потому что
    подать в судью ему нечего (устройство `chain_states`);
  * шаг СО СВОИМ адресом судится дополнительно, порядок силы прежний: НЕ ДОКАЗАН > НЕИЗВЕСТНО >
    ДОКАЗАН;
  * прежний пошаговый счёт НЕ УДАЛЁН и пишется в СВОЙ файл — оба видны рядом.

Секции:
(1) чистота: цепочечная часть ничего не решает; имени счёта серии в модуле нет
(2) ЕДИНИЦА: корень судится всегда, шаг без адреса не подаётся судье ВООБЩЕ
(3) порядок силы у цепочки: НЕ ДОКАЗАН шага обрывает, НЕИЗВЕСТНО не даёт зелёного
(4) ЗАМОК B — отрицательный тест: корневой адрес в пустоту → НЕ ДОКАЗАН при живом зелёном
(5) ЗАМОК C — мягче не значит слепо: порча ОДНОГО знака корневого адреса переворачивает вердикт
(6) руки демона: строка цепочки в своём файле, пошаговый журнал не тронут
(7) ЗАМОК A — настоящий вердикт и ход цепи НЕ ИЗМЕНИЛИСЬ (посимвольно, тень вкл/выкл)
(8) цена и границы: ноль лишних обращений, очередь не тронута, файл счёта серии не тронут
(9) память родства: транзитивный корень, петля, потолок; откат SHADOW_RULE=0
"""
import ast
import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile

# Путь ОТ ФАЙЛА ТЕСТА, а не константой: тот же файл гоняется по дереву ДО правки (git worktree).
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["ORCH_TEST_MODE"] = "1"
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["CURATOR"] = "0"
os.environ["PLAN_ADAPT"] = "0"
os.environ["STEP_SELFHEAL"] = "0"
os.environ["CARD_DUTY"] = "0"
os.environ["CHAIN_SERIES"] = "0"          # счёт серии этот сьют не считает и файла его не касается

TMP = tempfile.mkdtemp(prefix="cc_shadowchain_suite_")
os.environ["CC_SHADOW_DIR"] = os.path.join(TMP, "shadow")
STATE_FILE = os.path.join(REPO, "chain_series.json")


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return bool(c)


def sha_file(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return "нет файла"


res = []
import result_judge as RJ                                              # noqa: E402
import result_judge_facts as RF                                        # noqa: E402
import shadow_rule as SH                                               # noqa: E402

STATE_BEFORE = sha_file(STATE_FILE)

print("(1) ЧИСТОТА — цепочечная часть тоже ничего не решает")
src = open(os.path.join(REPO, "shadow_rule.py"), encoding="utf-8").read()
tree = ast.parse(src)
imports = sorted({(n.names[0].name.split(".")[0] if isinstance(n, ast.Import)
                   else (n.module or "").split(".")[0])
                  for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))})
res.append(ok(imports == ["result_judge"],
              "(1) импорт по-прежнему ровно один — `result_judge` (нашли %s)" % imports))
# Имени прибора, считающего чистоту цепочки, в модуле тени нет ВОВСЕ: второе определение одного
# понятия рядом с первым и есть класс «две правды об одном».
forbidden = [w for w in ("complete_task", "enqueue_task", "set_needs_approval", "claim_task",
                         "chain_series") if w in src]
res.append(ok(not forbidden, "(1) слов очереди и счёта серии в модуле нет (нашли %s)" % forbidden))
res.append(ok(hasattr(SH, "chain_shadow") and hasattr(SH, "chain_states")
              and hasattr(SH, "shadow"),
              "(1) оба счёта живут рядом: пошаговый `shadow` НЕ удалён, цепочечный добавлен"))

print("\n(2) ЕДИНИЦА — корень судится ВСЕГДА, шаг без адреса не подаётся судье ВООБЩЕ")
res.append(ok(SH.chain_states(RJ.PROVEN, []) == [RJ.PROVEN],
              "(2) корень назвал адрес → его исход и есть исход цепочки"))
res.append(ok(SH.chain_states(None, []) == [RJ.UNKNOWN],
              "(2) корень адреса не назвал → НЕИЗВЕСТНО (зелёное надо заработать)"))
nameless = [{"id": 7, "named": False, "state": RJ.UNPROVEN},
            {"id": 8, "named": False, "state": RJ.UNKNOWN}]
res.append(ok(SH.chain_states(RJ.PROVEN, nameless) == [RJ.PROVEN],
              "(2) шаги БЕЗ своего адреса в судью не попадают вовсе (%s)"
              % SH.chain_states(RJ.PROVEN, nameless)))
r = SH.chain_shadow(True, RJ.PROVEN, nameless)
res.append(ok(r["shadow_green"] and not r["break"] and not r["unresolved"] and r["steps_seen"] == 2
              and r["steps_named"] == 0,
              "(2) ГЛАВНОЕ: два безадресных шага цепочку НЕ оборвали, зелёное устояло"))
res.append(ok(SH.chain_shadow(True, None, [{"id": 1, "named": True, "state": RJ.PROVEN}])["judge"]
              == RJ.UNKNOWN,
              "(2) доказанный ШАГ за молчащий корень не отвечает — цепочка неизвестна"))

print("\n(3) ПОРЯДОК СИЛЫ У ЦЕПОЧКИ — НЕ ДОКАЗАН > НЕИЗВЕСТНО > ДОКАЗАН")
r = SH.chain_shadow(True, RJ.PROVEN, [{"id": 2, "named": True, "state": RJ.UNPROVEN}])
res.append(ok(r["judge"] == RJ.UNPROVEN and r["break"] and not r["unresolved"] and r["diff"]
              and r["dir"] == SH.DIR_STRICTER,
              "(3) шаг со СВОИМ адресом и исходом НЕ ДОКАЗАН обрывает цепочку"))
r = SH.chain_shadow(True, RJ.PROVEN, [{"id": 2, "named": True, "state": RJ.UNKNOWN}])
res.append(ok(r["judge"] == RJ.UNKNOWN and r["unresolved"] and not r["break"],
              "(3) шаг с НЕИЗВЕСТНО зелёного не даёт, но и не обрывает — цепочка не разобрана"))
r = SH.chain_shadow(True, RJ.PROVEN, [{"id": 2, "named": True, "state": RJ.PROVEN}])
res.append(ok(r["shadow_green"] and r["shadow"] == SH.GREEN and not r["diff"],
              "(3) корень доказан и шаг доказан → зелёное устояло"))
r = SH.chain_shadow(False, RJ.PROVEN, [])
res.append(ok(not r["shadow_green"] and not r["diff"] and not r["break"] and not r["unresolved"]
              and r["why"] == SH.WHY_CHAIN_NOT_GREEN,
              "(3) не зелёная и без правила → правило её не касается (снять умеет, дать не умеет)"))
res.append(ok(SH.chain_shadow(True, "мусор из чужого словаря", [])["judge"] == RJ.UNKNOWN,
              "(3) незнакомое слово исхода → НЕИЗВЕСТНО, а не зелёное (fail-closed)"))
res.append(ok("не разобрана" in SH.render_chain(SH.chain_shadow(True, None, []))
              and "обрыв" in SH.render_chain(SH.chain_shadow(True, RJ.UNPROVEN, [])),
              "(3) строка журнала называет исход словом, а не флагом"))

print("\n(4) ЗАМОК B — ОТРИЦАТЕЛЬНЫЙ ТЕСТ: корневой адрес в пустоту при ЖИВОМ зелёном")
NOWHERE = [
    ("file", os.path.join(REPO, "docs/artifacts/ЭТОГО-ФАЙЛА-НЕТ-0816.md"), "файла нет"),
    ("commit", "0" * 12, "хеша нет в origin/main"),
    ("row", os.path.join(TMP, "нет.db") + " t k=1", "базы нет"),
    ("brain", "cc_log ЭТОГО-ТАМ-НЕТ-0816", "узел не читается"),
    ("service_start", "нет-такого-юнита-0816.service " + "0" * 12, "юнит не наблюдается"),
]
leaks, seen = [], []
for kind, ptr, label in NOWHERE:
    facts = RF.gather([(kind, ptr)], brain=False)
    v = RJ.verdict((kind, ptr), facts)
    rec = SH.chain_shadow(True, v["state"], [])
    seen.append((kind, v["state"], rec["shadow"]))
    if rec["shadow_green"]:
        leaks.append((kind, label, v["why"]))
res.append(ok(not leaks, "(4) утечек зелёного 0 из %d (%s)" % (len(NOWHERE), leaks)))
res.append(ok(all(s in (RJ.UNPROVEN, RJ.UNKNOWN) for _k, s, _sh in seen),
              "(4) каждый вид дал НЕ ДОКАЗАН либо НЕИЗВЕСТНО: %s"
              % [(k, s) for k, s, _ in seen]))
# Прямой случай задания: адрес НАЗВАН и указывает в пустоту → именно НЕ ДОКАЗАН (не «неизвестно»).
v = RJ.verdict(("file", os.path.join(REPO, "docs/artifacts/НЕТ-0816.md")),
               RF.gather([("file", os.path.join(REPO, "docs/artifacts/НЕТ-0816.md"))],
                         brain=False))
rec = SH.chain_shadow(True, v["state"], [{"id": 5, "named": False, "state": RJ.PROVEN}])
res.append(ok(v["state"] == RJ.UNPROVEN and rec["shadow"] == RJ.UNPROVEN and rec["break"],
              "(4) «зелёный отчёт, корневой адрес в никуда» → НЕ ДОКАЗАН, цепочка оборвана"))

print("\n(5) ЗАМОК C — МЯГЧЕ НЕ ЗНАЧИТ СЛЕПО: один знак переворачивает вердикт цепочки")
live = os.path.join(REPO, "shadow_rule.py")
v_ok = RJ.verdict(("file", live), RF.gather([("file", live)], brain=False))
good = SH.chain_shadow(True, v_ok["state"], [])
spoiled = live[:-1] + "z"                       # РОВНО один знак: …shadow_rule.py → …shadow_rule.pz
v_bad = RJ.verdict(("file", spoiled), RF.gather([("file", spoiled)], brain=False))
bad = SH.chain_shadow(True, v_bad["state"], [])
res.append(ok(good["shadow_green"] and not bad["shadow_green"] and bad["break"],
              "(5) file: живой путь → зелёное устояло; один знак испорчен → обрыв (%s → %s)"
              % (good["shadow"], bad["shadow"])))
# Тот же замок на хеше — на фактах, а не на живом git: замок про РАЗЛИЧЕНИЕ, а не про среду.
SHA = "1a2b3c4d5e6f7a8b"
facts = {"commits": {"read": True, "shas": [SHA + "0" * 24], "at": {SHA + "0" * 24: 100.0}}}
g = SH.chain_shadow(True, RJ.verdict(("commit", SHA), facts)["state"], [])
b = SH.chain_shadow(True, RJ.verdict(("commit", SHA[:-1] + "9"), facts)["state"], [])
res.append(ok(g["shadow_green"] and not b["shadow_green"] and b["break"],
              "(5) commit: хеш из origin/main → зелёное; один знак испорчен → обрыв"))
res.append(ok(SH.chain_shadow(True, v_ok["state"],
                              [{"id": 3, "named": True, "state": v_bad["state"]}])["break"],
              "(5) порча адреса ШАГА (у которого он свой) тоже обрывает — правило не однобоко"))

print("\n(6) РУКИ ДЕМОНА — цепочка пишется в СВОЙ файл, пошаговый журнал не тронут")
import orchestrator_daemon as OD                                       # noqa: E402


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class FakeBridge:
    """Очередь в памяти + СЧЁТЧИК обращений: тень не смеет тронуть ни одну строку очереди."""
    def __init__(s):
        s.rows, s.nid, s.calls = {}, 0, []

    def enqueue_task(s, frm, txt, **kw):
        s.calls.append("enqueue_task")
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": txt, "status": "new",
                         "result": "", "updated": now_iso(), "lane": "vps"}
        return {"ok": True, "id": s.nid}

    def get_pending(s, status="new", **kw):
        s.calls.append("get_pending")
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True, "items": [dict(r) for r in sorted(s.rows.values(),
                                                              key=lambda x: -x["id"])
                                      if r["status"] in sts]}

    def claim_task(s, tid):
        s.calls.append("claim_task")
        r = s.rows.get(int(tid))
        if not r or r["status"] != "new":
            return {"ok": False, "error": "already_claimed"}
        r["status"] = "in_progress"
        return {"ok": True, "task": dict(r)}

    def complete_task(s, tid, status, result=""):
        s.calls.append("complete_task")
        r = s.rows.get(int(tid))
        r["status"], r["result"] = status, result
        return {"ok": True}

    def set_needs_approval(s, tid, what):
        s.calls.append("set_needs_approval")
        r = s.rows.get(int(tid))
        r["status"], r["result"] = "needs_approval", what
        return {"ok": True}

    def task_heartbeat(s, tid):
        return {"ok": True}

    def issue_write_ticket(s):
        return {"ok": True, "ticket": "t"}

    def consume_write_ticket(s, tk):
        return {"ok": True}

    def log_write(s, **kw):
        return {"ok": True}


class FakePopen:
    def __init__(s, out, rc):
        s.returncode, s._out, s._rc = None, out, rc

    def communicate(s, timeout=None):
        if s.returncode is None:
            s.returncode = s._rc
        return s._out, ""

    def terminate(s):
        s.returncode = -15

    def kill(s):
        s.returncode = -9

    def poll(s):
        return s.returncode


CLAUDE = {"out": "сводка: сделано\nFACT: read-only", "rc": 0}
OD.MAX_CLAUDE_PROCS = 0
OD._POPEN = lambda args, **kw: FakePopen(CLAUDE["out"], CLAUDE["rc"])
OD.subprocess.run = lambda args, **kw: type("P", (), {"stdout": "", "stderr": "",
                                                      "returncode": 0})()
# Обрамление провала читает git и ЧАСЫ — в двух прогонах одного сьюта оно дало бы РАЗНЫЙ текст,
# и посимвольное сравнение сравнивало бы среду, а не правку. Стаб одинаков для всех прогонов.
OD.status_truth.fail_result = lambda base, code, **kw: "[правда:%s] %s" % (code, base)
OD.status_truth.log_line = lambda tid, code: "fail id=%s code=%s" % (tid, code)
_real_dec = OD._maybe_dec_after
OD._maybe_dec_after = lambda text, status: None      # сводки цепи этот сьют не считает


def lines_of(name):
    p = os.path.join(os.environ["CC_SHADOW_DIR"], name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def step_lines():
    return lines_of(OD.SHADOW_FILE_NAME)


def chain_lines():
    return lines_of(OD.SHADOW_CHAIN_FILE_NAME)


def reset(bridge=None):
    """Чистый лист: журналы тени и ПАМЯТЬ РОДСТВА (она живёт в процессе, не в файле)."""
    shutil.rmtree(os.environ["CC_SHADOW_DIR"], ignore_errors=True)
    OD._SHADOW_KIN.clear()
    OD._SHADOW_CHAIN.clear()
    fb = bridge or FakeBridge()
    OD.bc = fb
    return fb


def run_one(fb, text, out="сводка: сделано\nFACT: read-only", rc=0):
    """Один шаг через ЖИВОЙ process_new → строка очереди после терминала."""
    CLAUDE["out"], CLAUDE["rc"] = out, rc
    tid = fb.enqueue_task("Filipp-328-dev", text)["id"]
    OD._LAST_RUN.clear()
    OD.process_new()
    return fb.rows[tid]


fb = reset()
run_one(fb, "цель захода\n[result_ref: file shadow_rule.py]")
res.append(ok(len(step_lines()) == 1 and len(chain_lines()) == 1,
              "(6) на терминал — РОВНО одна пошаговая строка и РОВНО одна цепочечная (%d/%d)"
              % (len(step_lines()), len(chain_lines()))))
res.append(ok(os.path.basename(os.path.join(os.environ["CC_SHADOW_DIR"],
                                            OD.SHADOW_CHAIN_FILE_NAME)) == "shadow-chain.jsonl"
              and OD.SHADOW_FILE_NAME == "shadow-rule.jsonl",
              "(6) файлы РАЗНЫЕ и названы: shadow-rule.jsonl (шаги) · shadow-chain.jsonl (цепочки)"))
c = chain_lines()[0]
res.append(ok(set(c) >= {"real_green", "shadow_green", "shadow", "judge", "diff", "dir", "why",
                         "break", "unresolved", "root", "id", "terminals", "root_kind",
                         "root_pointer", "root_why", "steps_seen", "steps_named", "lane", "at"},
              "(6) поля цепочечной записи на месте (%s)" % sorted(c)))
res.append(ok(c["root"] == 1 and c["shadow_green"] and c["root_kind"] == "file"
              and c["root_pointer"] == "shadow_rule.py",
              "(6) одиночная задача = цепочка из себя: корень назван, адрес прочитан, зелёное"))

# ЦЕПОЧКА ИЗ КОРНЯ И ДВУХ ШАГОВ: адрес только у корня, у шагов его нет вовсе.
fb = reset()
run_one(fb, "цель цепи\n[result_ref: file shadow_rule.py]")
run_one(fb, "[шаг 1/2 родитель 1] собери факты")
run_one(fb, "[шаг 2/2 родитель 1] запиши вывод")
c = chain_lines()[-1]
res.append(ok(len(chain_lines()) == 3 and c["root"] == 1 and c["terminals"] == 3,
              "(6) три терминала одной цепи → три строки, корень один (%s)"
              % [(x["root"], x["terminals"]) for x in chain_lines()]))
res.append(ok(c["shadow_green"] and c["steps_seen"] == 2 and c["steps_named"] == 0
              and not c["break"],
              "(6) ГЛАВНОЕ ЖИВЬЁМ: шаги без своего адреса цепочку не оборвали"))
# А пошаговый счёт на тех же шагах зелёное СНИМАЕТ — оба видны рядом, и разница именно в этом.
strict = [x for x in step_lines() if x["diff"]]
res.append(ok(len(step_lines()) == 3 and len(strict) == 2
              and all(x["shadow"] == RJ.UNKNOWN for x in strict),
              "(6) пошаговый счёт рядом: те же шаги сняли бы зелёное у 2 из 3 (%s)"
              % [x["shadow"] for x in step_lines()]))

# ШАГ СО СВОИМ АДРЕСОМ В НИКУДА — обрывает цепочку, хотя настоящий вердикт зелёный.
fb = reset()
run_one(fb, "цель цепи\n[result_ref: file shadow_rule.py]")
row = run_one(fb, "[шаг 1/2 родитель 1] нечто\n[result_ref: file docs/artifacts/НЕТ-0816.md]")
c = chain_lines()[-1]
res.append(ok(row["status"] == "done" and c["break"] and c["shadow"] == RJ.UNPROVEN
              and c["steps_named"] == 1,
              "(6) шаг со СВОИМ адресом в никуда обрывает цепочку (настоящий исход при этом done)"))

# ТРАНЗИТИВНЫЙ КОРЕНЬ: конверт одобренной заявки → карточка владельцу → цель.
fb = reset()
run_one(fb, "цель\n[result_ref: file shadow_rule.py]")
run_one(fb, "[куратор владельцу цель 1] пункт владельцу")
run_one(fb, "[конверт одобренной заявки 2] исполни пункты")
c = chain_lines()[-1]
res.append(ok(c["root"] == 1 and c["terminals"] == 3,
              "(6) корень разрешается ТРАНЗИТИВНО: конверт → карточка → цель (root=%s)"
              % c["root"]))

print("\n(7) ЗАМОК A — НАСТОЯЩИЙ ВЕРДИКТ И ХОД НЕ ИЗМЕНИЛИСЬ (посимвольно, тень вкл/выкл)")
CASES = [("зелёный, адреса нет", "проверь что-нибудь", "сводка: сделано\nFACT: read-only", 0),
         ("зелёный, адрес живой", "нечто\n[result_ref: file shadow_rule.py]",
          "сводка: сделано\nFACT: read-only", 0),
         ("зелёный, адрес в никуда", "нечто\n[result_ref: file docs/artifacts/НЕТ.md]",
          "сводка: сделано\nFACT: read-only", 0),
         ("шаг цепи без адреса", "[шаг 1/2 родитель 900] часть первая",
          "сводка: сделано\nFACT: read-only", 0),
         ("красный", "нечто", "claude упал", 1)]
snaps = {}
for flag in ("1", "0"):
    os.environ["SHADOW_RULE"] = flag
    fb = reset()
    got = []
    for label, text, out, rc in CASES:
        r = run_one(fb, text, out, rc)
        got.append((label, r["status"], r["result"]))
    snaps[flag] = got
    res.append(ok(len(chain_lines()) == (len(CASES) if flag == "1" else 0),
                  "(7) SHADOW_RULE=%s → строк цепочечной тени %d" % (flag, len(chain_lines()))))
os.environ["SHADOW_RULE"] = "1"
same = [a for a, b in zip(snaps["1"], snaps["0"]) if a != b]
res.append(ok(not same, "(7) терминалы ПОСИМВОЛЬНО равны при тени вкл и выкл (разошлось %d из %d)"
              % (len(same), len(CASES))))
res.append(ok([s[1] for s in snaps["1"]] == ["done", "done", "done", "done", "failed"],
              "(7) исходы прежние: четыре done и один failed (%s)" % [s[1] for s in snaps["1"]]))
res.append(ok(snaps["1"][2][2] == snaps["1"][0][2],
              "(7) шаг с теневым «не доказан» закрыт тем же текстом, что и шаг без адреса"))
res.append(ok(snaps["1"][4][2].startswith("[правда:"),
              "(7) терминал failed прошёл прежнее обрамление правды статуса"))
# ХОД ЦЕПИ: настоящий статус и ровно один вызов — при тени вкл и выкл.
OD._maybe_dec_after = _real_dec
moves = []
OD._maybe_dec_after = lambda text, status: moves.append((str(text)[:22], status))
for flag in ("1", "0"):
    os.environ["SHADOW_RULE"] = flag
    fb = reset()
    moves.clear()
    run_one(fb, "[шаг 1/2 родитель 900] сделай первую часть")
    res.append(ok(moves == [("[шаг 1/2 родитель 900]", "done")],
                  "(7) SHADOW_RULE=%s → цепь двинута ровно раз и НАСТОЯЩИМ статусом (%s)"
                  % (flag, moves)))
os.environ["SHADOW_RULE"] = "1"

print("\n(8) ЦЕНА И ГРАНИЦЫ")
_real_gather = RF.gather
gathers = []
OD.result_judge_facts.gather = lambda refs, **kw: (gathers.append((list(refs), dict(kw))),
                                                   _real_gather(refs, **kw))[1]
fb = reset()
run_one(fb, "[шаг 1/3 родитель 900] безадресный шаг")
res.append(ok(gathers == [], "(8) адреса нет → фактов не спрашивали НИ РАЗУ, и у цепочки тоже (%s)"
              % gathers))
res.append(ok(len(chain_lines()) == 1 and chain_lines()[0]["judge"] == RJ.UNKNOWN,
              "(8) и при этом строка цепочки написана, с честным «неизвестно»"))
gathers.clear()
fb = reset()
run_one(fb, "нечто\n[result_ref: file shadow_rule.py]")
res.append(ok(len(gathers) == 1 and len(gathers[0][0]) == 1,
              "(8) адрес назван → РОВНО один сбор фактов на ОБА счёта (%d)" % len(gathers)))
# 17.08.2026: было «brain=False — к мосту за узлами не ходим». Запрет снят (решение Штаба): он
# стоял на чужом числе и делал вердикт ДОКАЗАН для вида `brain` физически недостижимым. Мост
# теперь спрашивается ТОЛЬКО под адрес-узел и под общим бюджетом; здесь адрес — файл, значит
# запросов ноль, и это проверяется самим видом адреса, а не флагом.
res.append(ok(gathers and gathers[0][1].get("brain") is True,
              "(8) сбор с brain=True — узел спрашиваем живьём, когда адрес его назвал"))
_ref0 = (gathers[0][0] or [{}])[0] if gathers else {}
_kind0 = _ref0.get("kind") if isinstance(_ref0, dict) else (list(_ref0) + [""])[0]
res.append(ok(_kind0 == "file",
              "(8) адрес здесь не узел (вид «%s») → к мосту не ушло ни одного запроса" % _kind0))
OD.result_judge_facts.gather = _real_gather
res.append(ok(fb.calls.count("complete_task") == 1 and "set_needs_approval" not in fb.calls,
              "(8) очередь тронута РОВНО одним терминалом, тень к ней не ходила (%s)" % fb.calls))
res.append(ok("result" not in OD._shadow_note_chain.__code__.co_varnames,
              "(8) у рук цепочки нет параметра «отчёт» — адрес берётся ИЗ ПОЛЯ"))
fb = reset()
run_one(fb, "нечто без адреса", out="сделано\n[result_ref: file shadow_rule.py]")
c = chain_lines()[0]
res.append(ok(c["root_kind"] == "" and c["judge"] == RJ.UNKNOWN,
              "(8) адрес, названный ОТЧЁТОМ, цепочкой не читается — только поле задачи"))
res.append(ok(sha_file(STATE_FILE) == STATE_BEFORE,
              "(8) chain_series.json не тронут ни на байт (sha256 %s…)" % STATE_BEFORE[:12]))

print("\n(9) ПАМЯТЬ РОДСТВА И ОТКАТ")
OD._SHADOW_KIN.clear()
res.append(ok(OD._shadow_root(10, "обычная задача") == 10,
              "(9) маркера нет → запись сама себе корень"))
res.append(ok(OD._shadow_root(11, "[шаг 1/2 родитель 10] часть") == 10,
              "(9) шаг → корень его родителя"))
res.append(ok(OD._shadow_root(12, "[шаг 2/2 родитель 99] часть") == 99,
              "(9) родителя не видели → он и есть корень (выше подниматься нечем)"))
OD._SHADOW_KIN.clear()
OD._SHADOW_KIN[20] = 21
OD._SHADOW_KIN[21] = 20
res.append(ok(OD._shadow_root(20, "[шаг 1/1 родитель 21] петля") in (20, 21),
              "(9) петля маркеров обрывается на длине цепи, а не зацикливается"))
OD._SHADOW_KIN.clear()
for i in range(OD.SHADOW_KIN_KEEP + 50):
    OD._shadow_root(100000 + i, "задача")
res.append(ok(len(OD._SHADOW_KIN) <= OD.SHADOW_KIN_KEEP,
              "(9) память родства не растёт без потолка (%d ≤ %d)"
              % (len(OD._SHADOW_KIN), OD.SHADOW_KIN_KEEP)))
os.environ["SHADOW_RULE"] = "0"
fb = reset()
r = run_one(fb, "нечто\n[result_ref: file shadow_rule.py]")
res.append(ok(not chain_lines() and not step_lines() and r["status"] == "done",
              "(9) ОТКАТ SHADOW_RULE=0: ни одного файла тени — ветка мертва ДО чтения поля"))
os.environ["SHADOW_RULE"] = "1"
OD._maybe_dec_after = _real_dec

shutil.rmtree(TMP, ignore_errors=True)
print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
