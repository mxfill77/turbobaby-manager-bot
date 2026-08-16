# -*- coding: utf-8 -*-
"""ПРАВИЛО ЗЕЛЁНОГО ВКЛЮЧЕНО В СЧЁТЕ СЕРИИ — И ТОЛЬКО В СЧЁТЕ (16.08.2026, пункт 3 контракта).

Правило: цепочка чистая, только если по НАЗВАННОМУ ЕЮ АДРЕСУ и правда лежит её продукт. НЕ
ДОКАЗАН и НЕИЗВЕСТНО — обрыв (решение владельца 16.08, узел `orchestrator_plan`). Пункты 1
(`result_ref`, `55d2f1d`) и 2 (`result_judge`, `25ade7b`) завели поле и судью; тень (`9a57117`,
`fda5528`) считала правило рядом, ничего не решая. Здесь тень становится ПРИБОРОМ МЕТРИКИ —
и ровно им: ход цепи не меняется ни на байт.

Секции:
(1) правило ВЫКЛЮЧЕНО → вердикт и серия БАЙТ-В-БАЙТ прежние (ветка мертва до чтения фактов)
(2) правило включено: чистой остаётся только ДОКАЗАННАЯ; молчание ПРИБОРА ≠ «неизвестно» судьи
(3) ЗАМОК B — отрицательный тест: адрес в пустоту в чистые не попадает (и в функции, и живьём)
(4) ЗАМОК C — служебные корни: признак назван, ловит их, в знаменатель и в длину не пускает
(5) счёт С НУЛЯ от момента включения: прошлое не пересчитывается, рекорд не наследуется
(6) ЗАМОК D — прежние числа целы: `rule.before` держит прежний `derived` ДОСЛОВНО + определение
(7) ЗАМОК A — ход цепи прежний: терминалы посимвольно равны при правиле вкл и выкл
(8) руки живьём: чистая · обрыв по правилу · служебный корень; цена и границы
(9) откат RULE_ON_COUNT=0 и сверка: файл судится тем определением, каким считался
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
os.environ["CHAIN_SERIES"] = "1"          # предмет сьюта — сам счёт, он обязан работать
os.environ["RULE_ON_COUNT"] = "1"

TMP = tempfile.mkdtemp(prefix="cc_ruleon_suite_")
os.environ["CC_SHADOW_DIR"] = os.path.join(TMP, "shadow")
os.environ["CC_SERIES_FILE"] = os.path.join(TMP, "series.json")
os.environ["CC_CARDS_FILE"] = os.path.join(TMP, "cards.jsonl")
LIVE_STATE = os.path.join(REPO, "chain_series.json")


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
import chain_series as CS                                              # noqa: E402
import result_judge as RJ                                              # noqa: E402
import shadow_rule as SH                                               # noqa: E402

LIVE_BEFORE = sha_file(LIVE_STATE)


def chain(root, statuses=("done",), created="2026-08-16T20:00:00", kinds=None, rule=None,
          cards=(), refusals=(), commits=(), lane="vps"):
    return {"root": root, "lane": lane, "created": created, "closed_at": created,
            "statuses": list(statuses), "cards": list(cards), "refusals": list(refusals),
            "kinds": dict(kinds or {str(root): "root"}), "rule": dict(rule) if rule else None,
            "weight": {"commits": list(commits), "restarts": 0, "known": True}}


PROVEN = {"green": True, "judge": RJ.PROVEN, "why": SH.WHY_CHAIN_KEEP}
UNPROVEN = {"green": False, "judge": RJ.UNPROVEN, "why": SH.WHY_CHAIN_UNPROVEN}
UNKNOWN = {"green": False, "judge": RJ.UNKNOWN, "why": SH.WHY_CHAIN_UNKNOWN}
SINCE = "2026-08-16T19:00:00Z"

print("\n(1) ПРАВИЛО ВЫКЛЮЧЕНО → ПРЕЖНЕЕ БАЙТ-В-БАЙТ")
for label, rl in (("не доказан", UNPROVEN), ("неизвестно", UNKNOWN), ("доказан", PROVEN)):
    v = CS.chain_verdict(chain(1, rule=rl))
    res.append(ok(not v["break"] and not v["unresolved"] and v["counted"] and not v["service"],
                  "(1) правило выкл: вердикт адреса «%s» счёта не касается (обрыв=%s)"
                  % (label, v["break"])))
svc_off = CS.chain_verdict(chain(1, kinds={"1": "envelope"}))
res.append(ok(svc_off["counted"] and not svc_off["service"],
              "(1) правило выкл: служебный корень судится как прежде (в счёт входит)"))
old = CS.series([CS.chain_verdict(chain(i, rule=UNKNOWN)) for i in range(1, 6)])
res.append(ok(old["current"] == 5 and old["clean"] == 5 and not old["rule_since"]
              and old["service"] == 0 and old["before_rule"] == 0,
              "(1) правило выкл: пять цепочек без доказательства = серия 5 (прежнее определение)"))
res.append(ok("правило зелёного" not in CS.render(old),
              "(1) правило выкл: строка журнала БЕЗ хвоста правила (легаси-формат цел)"))
src = ast.parse(open(os.path.join(REPO, "chain_series.py"), encoding="utf-8").read())
imports = sorted({n.name.split(".")[0] for x in ast.walk(src) if isinstance(x, ast.Import)
                  for n in x.names}
                 | {(x.module or "").split(".")[0] for x in ast.walk(src)
                    if isinstance(x, ast.ImportFrom)})
res.append(ok(imports == ["re"],
              "(1) ЧИСТОТА ЦЕЛА: импорт счёта по-прежнему ровно один — %s (судить адреса ему "
              "нечем, вердикт приходит готовым)" % imports))
names = {x.id for x in ast.walk(src) if isinstance(x, ast.Name)} \
    | {x.attr for x in ast.walk(src) if isinstance(x, ast.Attribute)}
res.append(ok("shadow_rule" not in names and "result_judge" not in names,
              "(1) второго определения нет: ни судьи, ни тени счёт НЕ ЗОВЁТ (имена встречаются "
              "лишь в прозе — указателем, откуда взят вокабуляр)"))

print("\n(2) ПРАВИЛО ВКЛЮЧЕНО: ЧИСТАЯ = ДОКАЗАННАЯ")
v = CS.chain_verdict(chain(1, rule=PROVEN), since=SINCE)
res.append(ok(not v["break"] and not v["unresolved"] and v["counted"],
              "(2) ДОКАЗАН → цепочка чистая"))
v = CS.chain_verdict(chain(1, rule=UNPROVEN), since=SINCE)
res.append(ok(v["break"] and v["cause"] == CS.RULE_CAUSE and RJ.UNPROVEN in v["why"],
              "(2) НЕ ДОКАЗАН → ОБРЫВ, причина названа «%s»" % v["cause"]))
v = CS.chain_verdict(chain(1, rule=UNKNOWN), since=SINCE)
res.append(ok(v["break"] and v["cause"] == CS.RULE_CAUSE and RJ.UNKNOWN in v["why"],
              "(2) НЕИЗВЕСТНО → ОБРЫВ (решение владельца 16.08), а не «не разобрана»"))
v = CS.chain_verdict(chain(1, rule=None), since=SINCE)
res.append(ok(not v["break"] and v["unresolved"] and "прибор" in v["unresolved_why"],
              "(2) МОЛЧАНИЕ ПРИБОРА (вердикта нет вовсе) → не разобрана: факт о нас, не о цепочке"))
v = CS.chain_verdict(chain(1, rule=PROVEN, cards=[{"sort": CS.NOISE, "why": "шумная карточка"}]),
                     since=SINCE)
res.append(ok(v["break"] and v["cause"] == CS.NOISE,
              "(2) ОДНОСТОРОННОСТЬ: доказанный адрес НЕ спасает цепочку, оборванную шумом"))
v = CS.chain_verdict(chain(1, rule=UNPROVEN, refusals=[{"id": 1, "reason": "зависание"}]),
                     since=SINCE)
res.append(ok(v["break"] and v["cause"] == "отказ",
              "(2) порядок причин прежний: отказ называется раньше правила"))
v = CS.chain_verdict(chain(1, rule=UNPROVEN, cards=[{"sort": CS.UNKNOWN, "why": "?"}]),
                     since=SINCE)
res.append(ok(v["break"] and v["cause"] == CS.RULE_CAUSE,
              "(2) факт обрыва по правилу сильнее незнания сорта (обрыв, а не «не разобрана»)"))

print("\n(3) ЗАМОК B — ОТРИЦАТЕЛЬНЫЙ ТЕСТ: АДРЕС В ПУСТОТУ В ЧИСТЫЕ НЕ ПОПАДАЕТ")
st = CS.series([CS.chain_verdict(chain(1, rule=PROVEN), since=SINCE),
                CS.chain_verdict(chain(2, rule=UNPROVEN), since=SINCE),
                CS.chain_verdict(chain(3, rule=PROVEN), since=SINCE)], since=SINCE)
res.append(ok(st["current"] == 1 and st["best"] == 1 and len(st["breaks"]) == 1
              and st["rule_breaks"] == 1 and st["clean"] == 2,
              "(3) адрес в пустоту рвёт серию: идёт %d, лучшая %d, обрывов по правилу %d"
              % (st["current"], st["best"], st["rule_breaks"])))
allunk = CS.series([CS.chain_verdict(chain(i, rule=UNKNOWN), since=SINCE) for i in range(1, 11)],
                   since=SINCE)
res.append(ok(allunk["current"] == 0 and allunk["best"] == 0 and allunk["clean"] == 0
              and len(allunk["breaks"]) == 10,
              "(3) десять недоказанных подряд → серия 0 и чистых 0 (длину незнанием не набить)"))
res.append(ok(allunk["qualified"] == CS.QUAL_NO,
              "(3) зачётности у такой серии нет: %s" % allunk["qualified_why"]))

print("\n(4) ЗАМОК C — СЛУЖЕБНЫЕ КОРНИ ЕДИНИЦЕЙ НЕ ЯВЛЯЮТСЯ")
res.append(ok(sorted(CS.SERVICE_KINDS) == ["adapt_card", "curator_verdict", "envelope",
                                           "owner_card", "pc_card", "summary"],
              "(4) ПРИЗНАК НАЗВАН: вид маркера корневой записи ∈ SERVICE_KINDS = %s"
              % sorted(CS.SERVICE_KINDS)))
res.append(ok(CS.service_root({"root": 5, "kinds": {"5": "envelope"}}) == "envelope"
              and CS.service_root({"root": 5, "kinds": {"5": "root"}}) == ""
              and CS.service_root({"root": 5, "kinds": {"5": "step"}}) == "",
              "(4) корневая запись видена: судится ЕЁ вид"))
res.append(ok(CS.service_root({"root": 900, "kinds": {"901": "envelope", "902": "summary"}})
              == "envelope"
              and CS.service_root({"root": 900, "kinds": {"901": "envelope", "902": "step"}}) == "",
              "(4) корня не видели: все виденные служебные → служебная, есть рабочая → нет"))
res.append(ok(CS.service_root({"root": 5}) == "" and CS.service_root({"root": 5, "kinds": {}}) == "",
              "(4) видов нет вовсе (легаси) → '' : не знаем — не объявляем"))
mix = [CS.chain_verdict(chain(1, rule=PROVEN), since=SINCE),
       CS.chain_verdict(chain(2, kinds={"2": "envelope"}, rule=UNKNOWN), since=SINCE),
       CS.chain_verdict(chain(3, kinds={"3": "summary"}, rule=UNKNOWN), since=SINCE),
       CS.chain_verdict(chain(4, kinds={"4": "curator_verdict"}, rule=UNKNOWN), since=SINCE),
       CS.chain_verdict(chain(5, rule=PROVEN), since=SINCE)]
sm = CS.series(mix, since=SINCE)
res.append(ok(sm["service"] == 3 and sm["chains"] == 2 and sm["current"] == 2
              and len(sm["breaks"]) == 0,
              "(4) ЧИСЛОМ: три служебных корня в знаменатель не вошли (цепочек %d, служебных %d) "
              "и серию не удлинили и не оборвали (идёт %d)"
              % (sm["chains"], sm["service"], sm["current"])))
sm_off = CS.series([CS.chain_verdict(dict(c, rule=UNKNOWN)) for c in
                    [chain(2, kinds={"2": "envelope"}), chain(3, kinds={"3": "summary"})]])
res.append(ok(sm_off["chains"] == 2 and sm_off["service"] == 0,
              "(4) контроль: при выключенном правиле те же служебные считались как раньше"))
res.append(ok("служебных корней 3" in CS.render(sm) and "правило зелёного с" in CS.render(sm),
              "(4) МОЛЧАЛИВОГО ПРОПУСКА НЕТ: числа стоят в строке журнала — %s"
              % CS.render(sm).split("|")[-1].strip()))

print("\n(5) СЧЁТ С НУЛЯ ОТ МОМЕНТА ВКЛЮЧЕНИЯ")
past = CS.chain_verdict(chain(1, created="2026-08-15T10:00:00", rule=UNKNOWN), since=SINCE)
res.append(ok(not past["counted"] and "прошлое не пересчитываем" in past["skip_why"],
              "(5) цепочка старше включения в счёт не входит вовсе (ни чистой, ни обрывом)"))
nodate = CS.chain_verdict(chain(1, created="", rule=PROVEN), since=SINCE)
res.append(ok(not nodate["counted"] and "время неизвестно" in nodate["skip_why"],
              "(5) время рождения неизвестно → под правило не берём (не знаем — не судим)"))
mixed = CS.series([CS.chain_verdict(chain(1, created="2026-08-14T10:00:00", rule=UNKNOWN),
                                    since=SINCE),
                   CS.chain_verdict(chain(2, created="2026-08-15T10:00:00", rule=UNKNOWN),
                                    since=SINCE),
                   CS.chain_verdict(chain(3, rule=PROVEN), since=SINCE)], since=SINCE)
res.append(ok(mixed["before_rule"] == 2 and mixed["current"] == 1 and mixed["chains"] == 1
              and len(mixed["breaks"]) == 0,
              "(5) ЧИСЛОМ: две прежние цепочки названы и пропущены, счёт пошёл с нуля (идёт %d)"
              % mixed["current"]))
res.append(ok("прежних цепочек 2" in CS.render(mixed),
              "(5) прежние названы числом в строке журнала"))

print("\n(6) ЗАМОК D — ПРЕЖНИЕ ЧИСЛА ЦЕЛЫ")
import orchestrator_daemon as OD                                       # noqa: E402

OD._IS_DAEMON = False
BEFORE_DERIVED = {"current": 7, "best": 15, "best_ever": 15, "chains": 46, "clean": 42,
                  "line": "серия цепочек: идёт 7 ... лучшая 15, всего цепочек 46",
                  "last_break": {"root": 512, "cause": "ремонт"}}
state = {"chains": {}, "derived": dict(BEFORE_DERIVED)}
OD._series_derive(state)
before = (state.get("rule") or {}).get("before") or {}
res.append(ok(before == BEFORE_DERIVED,
              "(6) прежний derived сохранён ДОСЛОВНО (best=%s, clean=%s из chains=%s)"
              % (before.get("best"), before.get("clean"), before.get("chains"))))
res.append(ok("прежнее определение" in ((state.get("rule") or {}).get("definition") or ""),
              "(6) рядом лежит ПОМЕТКА, по какому определению они считались"))
res.append(ok(state["derived"]["best_ever"] == 0 and not state["derived"]["last_break"],
              "(6) счёт с нуля: рекорд прежнего определения НЕ унаследован (best_ever=%s)"
              % state["derived"]["best_ever"]))
res.append(ok(state["derived"].get("rule_since") == (state["rule"]["since"] or "")[:19],
              "(6) момент включения записан в состоянии и в строке"))
first_since = state["rule"]["since"]
state["derived"]["best_ever"] = 3
OD._series_derive(state)
res.append(ok(state["rule"]["since"] == first_since and state["rule"]["before"] == BEFORE_DERIVED,
              "(6) включение случается ОДИН раз: момент и прежние числа второй раз не переписаны"))

print("\n(7) ЗАМОК A — ХОД ЦЕПИ ПРЕЖНИЙ (посимвольно, правило вкл и выкл)")


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class FakeBridge:
    """Очередь в памяти + СЧЁТЧИК обращений: счёт не смеет тронуть ни одну строку очереди."""
    def __init__(s):
        s.rows, s.nid, s.calls = {}, 0, []

    def enqueue_task(s, frm, txt, **kw):
        s.calls.append("enqueue_task")
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": txt, "status": "new",
                         "result": "", "created": now_iso(), "updated": now_iso(), "lane": "vps"}
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


def state_now():
    p = os.environ["CC_SERIES_FILE"]
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def reset(bridge=None):
    """Чистый лист: файл счёта, журналы тени и память родства тени."""
    for p in (os.environ["CC_SERIES_FILE"], os.environ["CC_CARDS_FILE"]):
        if os.path.exists(p):
            os.remove(p)
    shutil.rmtree(os.environ["CC_SHADOW_DIR"], ignore_errors=True)
    OD._SHADOW_KIN.clear()
    OD._SHADOW_CHAIN.clear()
    OD._REF_VERDICT.update({"key": None, "v": None})
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


CASES = [("зелёный, адреса нет", "проверь что-нибудь", "сводка: сделано\nFACT: read-only", 0),
         ("зелёный, адрес живой", "нечто\n[result_ref: file chain_series.py]",
          "сводка: сделано\nFACT: read-only", 0),
         ("зелёный, адрес в никуда", "нечто\n[result_ref: file docs/artifacts/НЕТ-0816.md]",
          "сводка: сделано\nFACT: read-only", 0),
         ("шаг цепи без адреса", "[шаг 1/2 родитель 900] часть первая",
          "сводка: сделано\nFACT: read-only", 0),
         ("конверт (служебный корень)", "[конверт одобренной заявки 901] исполни пункты",
          "сводка: сделано\nFACT: read-only", 0),
         ("красный", "нечто", "claude упал", 1)]
snaps = {}
for flag in ("1", "0"):
    os.environ["RULE_ON_COUNT"] = flag
    fb = reset()
    got = []
    for label, text, out, rc in CASES:
        r = run_one(fb, text, out, rc)
        got.append((label, r["status"], r["result"]))
    snaps[flag] = got
os.environ["RULE_ON_COUNT"] = "1"
diff = [a for a, b in zip(snaps["1"], snaps["0"]) if a != b]
res.append(ok(not diff,
              "(7) ЗАМОК A: терминалы ПОСИМВОЛЬНО равны при правиле вкл и выкл (разошлось %d "
              "из %d)" % (len(diff), len(CASES))))
res.append(ok(hashlib.sha256(json.dumps(snaps["1"], ensure_ascii=False).encode()).hexdigest()
              == hashlib.sha256(json.dumps(snaps["0"], ensure_ascii=False).encode()).hexdigest(),
              "(7) sha256 снимка терминалов совпал: %s"
              % hashlib.sha256(json.dumps(snaps["1"],
                                          ensure_ascii=False).encode()).hexdigest()[:12]))
res.append(ok([s[1] for s in snaps["1"]] == ["done"] * 5 + ["failed"],
              "(7) исходы прежние: пять done и один failed (%s)" % [s[1] for s in snaps["1"]]))
res.append(ok(snaps["1"][2][2] == snaps["1"][0][2],
              "(7) цепочка с обрывом ПО ПРАВИЛУ закрыта тем же текстом, что и без адреса"))
res.append(ok(snaps["1"][5][2].startswith("[правда:"),
              "(7) терминал failed прошёл прежнее обрамление правды статуса"))
moves = []
OD._maybe_dec_after = lambda text, status: moves.append((str(text)[:22], status))
for flag in ("1", "0"):
    os.environ["RULE_ON_COUNT"] = flag
    fb = reset()
    moves.clear()
    run_one(fb, "[шаг 1/2 родитель 900] сделай первую часть\n[result_ref: file НЕТ.md]")
    res.append(ok(moves == [("[шаг 1/2 родитель 900]", "done")],
                  "(7) RULE_ON_COUNT=%s → цепь двинута ровно раз и НАСТОЯЩИМ статусом (%s)"
                  % (flag, moves)))
os.environ["RULE_ON_COUNT"] = "1"
OD._maybe_dec_after = lambda text, status: None

print("\n(8) РУКИ ЖИВЬЁМ: ЧИСТАЯ · ОБРЫВ ПО ПРАВИЛУ · СЛУЖЕБНЫЙ КОРЕНЬ")
fb = reset()
run_one(fb, "цель захода\n[result_ref: file chain_series.py]")
d = state_now().get("derived") or {}
res.append(ok(d.get("current") == 1 and d.get("clean") == 1 and not d.get("breaks"),
              "(8) ЖИВЬЁМ: цель с доказанным адресом → серия 1 (%s)" % d.get("line", "")[:60]))
ch = (state_now().get("chains") or {}).get("1") or {}
res.append(ok((ch.get("rule") or {}).get("green") and (ch.get("kinds") or {}).get("1") == "root",
              "(8) в цепочке лежат ФАКТЫ правила: вердикт %s, вид корня %s"
              % ((ch.get("rule") or {}).get("judge"), (ch.get("kinds") or {}).get("1"))))
fb = reset()
run_one(fb, "цель захода\n[result_ref: file docs/artifacts/НЕТ-0816.md]")
d = state_now().get("derived") or {}
res.append(ok(d.get("current") == 0 and d.get("rule_breaks") == 1 and d.get("clean") == 0,
              "(8) ЖИВЬЁМ ЗАМОК B: адрес в пустоту → обрыв по правилу, чистых 0"))
fb = reset()
run_one(fb, "цель захода\n[result_ref: file chain_series.py]")
run_one(fb, "[шаг 1/2 родитель 1] собери факты")
run_one(fb, "[шаг 2/2 родитель 1] запиши вывод")
d = state_now().get("derived") or {}
res.append(ok(d.get("chains") == 1 and d.get("current") == 1,
              "(8) ЕДИНИЦА — ЦЕПОЧКА: корень с адресом и два шага без него = ОДНА чистая (%s)"
              % d.get("current")))
fb = reset()
run_one(fb, "[конверт одобренной заявки 901] исполни пункты")
d = state_now().get("derived") or {}
res.append(ok(d.get("service") == 1 and d.get("chains") == 0 and d.get("current") == 0,
              "(8) ЖИВЬЁМ ЗАМОК C: служебный корень в счёт не вошёл (служебных %s, цепочек %s)"
              % (d.get("service"), d.get("chains"))))
fb = reset()
run_one(fb, "цель\n[result_ref: file chain_series.py]")
run_one(fb, "[конверт одобренной заявки 1] исполни пункты")
d = state_now().get("derived") or {}
res.append(ok(d.get("service") == 0 and d.get("chains") == 1 and d.get("current") == 1,
              "(8) контроль: конверт ВНУТРИ живой цепочки её служебной не делает"))
_real_gather = OD.result_judge_facts.gather
gathers = []
OD.result_judge_facts.gather = lambda refs, **kw: (gathers.append(list(refs)),
                                                   _real_gather(refs, **kw))[1]
fb = reset()
run_one(fb, "цель без адреса вовсе")
res.append(ok(not gathers, "(8) ЦЕНА: адреса нет → фактов не спрашиваем ВООБЩЕ (вызовов %d)"
              % len(gathers)))
fb = reset()
gathers.clear()
run_one(fb, "цель\n[result_ref: file chain_series.py]")
res.append(ok(len(gathers) == 1,
              "(8) ЦЕНА: адрес есть → факты собраны РОВНО раз на двоих (счёт и тень), вызовов %d"
              % len(gathers)))
res.append(ok(all("brain" not in str(g) for g in gathers) and len(gathers) == 1,
              "(8) к мосту за узлом мозга счёт не ходит (brain=False, как у тени)"))
OD.result_judge_facts.gather = _real_gather
fb = reset()
run_one(fb, "цель\n[result_ref: file chain_series.py]")
res.append(ok(fb.calls.count("complete_task") == 1 and "enqueue_task" not in fb.calls[1:],
              "(8) ГРАНИЦА: счёт не поставил ни одной задачи и не тронул строк очереди (%s)"
              % sorted(set(fb.calls))))
res.append(ok(sha_file(LIVE_STATE) == LIVE_BEFORE,
              "(8) БОЕВОЙ chain_series.json не тронут ни на байт (sha256 до и после совпал)"))

print("\n(9) ОТКАТ И СВЕРКА")
os.environ["RULE_ON_COUNT"] = "0"
fb = reset()
run_one(fb, "цель\n[result_ref: file docs/artifacts/НЕТ-0816.md]")
run_one(fb, "вторая цель без адреса")
d_off = state_now().get("derived") or {}
res.append(ok(d_off.get("current") == 2 and not d_off.get("rule_since")
              and not state_now().get("rule"),
              "(9) ОТКАТ RULE_ON_COUNT=0: счёт прежний (идёт %s), маркера правила в файле нет"
              % d_off.get("current")))
os.environ["RULE_ON_COUNT"] = "1"
fb = reset()
run_one(fb, "цель\n[result_ref: file chain_series.py]")
live = state_now()
import chain_series_report as CR                                       # noqa: E402
code, lines = CR.verify(live, {}, unread=(), windows_read=True)
res.append(ok(not any("файл сам себе противоречит" in x for x in lines),
              "(9) СВЕРКА не краснеет на файле, считанном под правилом (файл судится тем "
              "определением, каким считался)"))
res.append(ok(any("правило зелёного в счёте с" in x for x in lines),
              "(9) сверка НАЗЫВАЕТ, что ось правила реплеем не судится"))
res.append(ok(CR._rule_since({}) == "" and CR._rule_since(live) == live["rule"]["since"],
              "(9) маркер сверка берёт ИЗ ФАЙЛА, а не из окружения процесса"))

shutil.rmtree(TMP, ignore_errors=True)
print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
