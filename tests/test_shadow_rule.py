# -*- coding: utf-8 -*-
"""ТЕНЕВОЙ ПРОГОН ПРАВИЛА ЗЕЛЁНОГО (16.08.2026, пункт 3 контракта третьего исхода).

СЧИТАТЬ, НЕ ПРИМЕНЯТЬ. Правило «нет адреса — нет зелёного» включать сегодня нельзя: адрес не
пишет ни один боевой вызов, и включённое правило сделало бы КАЖДЫЙ шаг незелёным, то есть
остановило бы полосу. Поэтому тень считается РЯДОМ с настоящим вердиктом и не касается его.

Замер захода (16.08.2026, читающий снимок ЖИВОЙ очереди, 11 строк, все семь статусов):
ключ `[result_ref:` в начале строки несут 6 строк, адрес прочитан ДОСЛОВНО у 3 (id 9, 10, 11),
НАСТОЯЩИХ ПОТЕРЬ 0, остальные 3 — ЦИТАТА формы в прозе ТЗ (правило позиции работает как
задумано). На закрытых шагах живой очереди тень разошлась с настоящим у 9 из 10, ВСЕ в сторону
«строже»; на широком корпусе (257 закрытых артефактов) — у 243, теневое зелёное получили 0.

Секции:
(1) чистота модуля: импорт ровно один, ни файлов, ни сети, ни подпроцессов (ast)
(2) правило ОДНОСТОРОННЕЕ: снять зелёное умеет, дать — не умеет ни при каком вердикте судьи
(3) порядок силы у нескольких адресов: НЕ ДОКАЗАН > НЕИЗВЕСТНО > ДОКАЗАН; пусто → неизвестно
(4) ЗАМОК C — отрицательный тест: «зелёный отчёт, адрес назван, по адресу пусто» → НЕ ДОКАЗАН
(5) руки демона: запись рядом с настоящим, поля, три рубежа изоляции каталога
(6) ЗАМОК A — настоящий вердикт НЕ ИЗМЕНИЛСЯ: терминалы done и failed посимвольно равны
(7) ЗАМОК B — ход НЕ ИЗМЕНИЛСЯ: шаг с теневым «неизвестно» идёт дальше ровно как раньше
(8) цена: адреса нет → НОЛЬ обращений к миру
(9) границы: очередь тень не трогает; адрес берётся из ПОЛЯ, а не из отчёта; откат SHADOW_RULE=0
"""
import ast
import datetime
import json
import os
import shutil
import sqlite3
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

TMP = tempfile.mkdtemp(prefix="cc_shadow_suite_")
os.environ["CC_SHADOW_DIR"] = os.path.join(TMP, "shadow")


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return bool(c)


res = []
import result_judge as RJ                                              # noqa: E402
import result_judge_facts as RF                                        # noqa: E402
import shadow_rule as SH                                               # noqa: E402

print("(1) ЧИСТОТА МОДУЛЯ — тень не умеет ни читать мир, ни решать")
src = open(os.path.join(REPO, "shadow_rule.py"), encoding="utf-8").read()
tree = ast.parse(src)
imports = sorted({(n.names[0].name.split(".")[0] if isinstance(n, ast.Import)
                   else (n.module or "").split(".")[0])
                  for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))})
res.append(ok(imports == ["result_judge"],
              "(1) импорт ровно один — `result_judge` (нашли %s)" % imports))
bad = [n.func.id for n in ast.walk(tree)
       if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
       and n.func.id in ("open", "exec", "eval", "compile", "__import__")]
res.append(ok(not bad, "(1) ни open/exec/eval в исполняющей позиции (нашли %s)" % bad))
attrs = [n.func.value.id for n in ast.walk(tree)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
         and isinstance(n.func.value, ast.Name)
         and n.func.value.id in ("os", "sys", "subprocess", "sqlite3", "bridge_client", "bc")]
res.append(ok(not attrs, "(1) ни os/subprocess/sqlite3/моста (нашли %s)" % attrs))
# Слова, которыми в этой системе закрывают задачу и двигают цепь. Их в решении быть не может:
# «тень ничего не решает» обязано держаться устройством, а не докстрингом.
forbidden = [w for w in ("complete_task", "enqueue_task", "set_needs_approval", "claim_task",
                         "chain_series") if w in src]
res.append(ok(not forbidden, "(1) слов очереди и счёта серии в модуле нет (нашли %s)" % forbidden))

print("\n(2) ПРАВИЛО ОДНОСТОРОННЕЕ — снять зелёное умеет, ДАТЬ не умеет")
r = SH.shadow("done", [RJ.PROVEN])
res.append(ok(r["shadow"] == "done" and not r["diff"] and r["dir"] == "",
              "(2) done + ДОКАЗАН → зелёное устояло, расхождения нет"))
r = SH.shadow("done", [RJ.UNKNOWN])
res.append(ok(r["shadow"] == RJ.UNKNOWN and r["diff"] and r["dir"] == SH.DIR_STRICTER,
              "(2) done + НЕИЗВЕСТНО → теневое «неизвестно», сторона «строже»"))
r = SH.shadow("done", [RJ.UNPROVEN])
res.append(ok(r["shadow"] == RJ.UNPROVEN and r["diff"] and r["dir"] == SH.DIR_STRICTER,
              "(2) done + НЕ ДОКАЗАН → теневое «не доказан», сторона «строже»"))
# Красное остаётся красным при ЛЮБОМ вердикте судьи: «по адресу лежит продукт» не значит
# «работа сделана» — упавший шаг мог оставить файл и умереть следующей строкой.
give_green = [st for st in (RJ.PROVEN, RJ.UNKNOWN, RJ.UNPROVEN)
              if SH.shadow("failed", [st])["shadow"] != "failed"]
res.append(ok(not give_green,
              "(2) failed + любой вердикт судьи → failed; зелёного тень не даёт НИКОГДА (%s)"
              % give_green))
dirs = {SH.shadow(s, [st])["dir"] for s in ("done", "failed")
        for st in (RJ.PROVEN, RJ.UNKNOWN, RJ.UNPROVEN)}
res.append(ok(dirs <= {SH.DIR_STRICTER, SH.DIR_NONE},
              "(2) сторон расхождения ровно одна — «строже» (нашли %s)" % sorted(dirs)))
res.append(ok(SH.shadow("done", [RJ.UNPROVEN])["shadow"] != SH.shadow("done", [RJ.UNKNOWN])["shadow"],
              "(2) «не доказан» и «неизвестно» НЕ свёрнуты в одно — третий исход цел"))

print("\n(3) ПОРЯДОК СИЛЫ у нескольких адресов")
res.append(ok(SH.shadow("done", [RJ.PROVEN, RJ.UNPROVEN])["shadow"] == RJ.UNPROVEN,
              "(3) доказанное отсутствие ХОТЬ ПО ОДНОМУ адресу сильнее доказанного наличия"))
res.append(ok(SH.shadow("done", [RJ.PROVEN, RJ.UNKNOWN])["shadow"] == RJ.UNKNOWN,
              "(3) незнание сильнее доказанного наличия"))
res.append(ok(SH.shadow("done", [RJ.UNKNOWN, RJ.UNPROVEN])["shadow"] == RJ.UNPROVEN,
              "(3) доказанное отсутствие сильнее незнания"))
res.append(ok(SH.shadow("done", [])["shadow"] == RJ.UNKNOWN,
              "(3) адресов не названо вовсе → неизвестно (пустого зелёного не бывает)"))

print("\n(4) ЗАМОК C — ОТРИЦАТЕЛЬНЫЙ ТЕСТ: отчёт зелёный, адрес назван, по адресу ПУСТО")
# file и commit судятся ЖИВЫМИ фактами (диск и origin/main), row — живой базой захода,
# brain и service_start — фактами, собранными руками: спросить мост в тесте нельзя, а без
# третьей и четвёртой ветки замок проверял бы не все виды адреса.
db = os.path.join(TMP, "проба.db")
con = sqlite3.connect(db)
con.execute("CREATE TABLE шаги (ключ TEXT, чей TEXT)")
con.execute("INSERT INTO шаги VALUES ('есть', 'мы')")
con.commit()
con.close()
EMPTY = [
    ("file", os.path.join(TMP, "НЕТ-ТАКОГО.md"), None),
    ("commit", "0123456789abcdef0123456789abcdef01234567", None),
    ("row", "%s шаги ключ=нету" % db, None),
    ("brain", "cc_log ЭТОЙ-СТРОКИ-ТАМ-НЕТ-2026", {"brain": {"cc_log": {
        "read": True, "text": "журнал без названного", "len": 22, "len_before": 10}}}),
    ("service_start", "splinter 1111111", {"units": {"splinter": {"read": True, "started": 100.0}},
                                           "commits": {"read": True, "shas": ["1111111abcdef"],
                                                       "at": {"1111111abcdef": 200.0}}}),
]
green_leak = []
for kind, ptr, hand in EMPTY:
    facts = hand if hand is not None else RF.gather([(kind, ptr)], brain=False)
    v = RJ.verdict((kind, ptr), facts)
    rec = SH.shadow("done", [v["state"]])
    good = v["state"] == RJ.UNPROVEN and rec["shadow"] == RJ.UNPROVEN and rec["diff"]
    if not good:
        green_leak.append((kind, v["state"], rec["shadow"]))
    res.append(ok(good, "(4) %-14s по адресу пусто → судья «%s», тень «%s» при настоящем done"
                  % (kind, v["state"], rec["shadow"])))
res.append(ok(not green_leak,
              "(4) ЗАМОК C: ни один вид не оставил зелёного (утечки: %s)" % green_leak))
# Обратная сторона замка: там, где продукт ЕСТЬ, тень зелёное НЕ снимает — иначе правило не
# различало бы ничего и «строже» было бы просто «всегда».
v = RJ.verdict(("file", os.path.join(REPO, "shadow_rule.py")),
               RF.gather([("file", os.path.join(REPO, "shadow_rule.py"))], brain=False))
res.append(ok(v["state"] == RJ.PROVEN and not SH.shadow("done", [v["state"]])["diff"],
              "(4) живой файл по адресу → ДОКАЗАН, зелёное устояло (тень различает)"))

print("\n(5) РУКИ ДЕМОНА — тень пишется РЯДОМ, в названное место")
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
# Обрамление провала читает git и ЧАСЫ — в двух прогонах одного сьюта оно дало бы РАЗНЫЙ текст
# и посимвольное сравнение сравнивало бы среду, а не правку. Стаб одинаков для всех прогонов.
OD.status_truth.fail_result = lambda base, code, **kw: "[правда:%s] %s" % (code, base)
OD.status_truth.log_line = lambda tid, code: "fail id=%s code=%s" % (tid, code)


def shadow_lines():
    p = os.path.join(os.environ["CC_SHADOW_DIR"], OD.SHADOW_FILE_NAME)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def run_one(text, out="сводка: сделано\nFACT: read-only", rc=0, bridge=None):
    """Один шаг через ЖИВОЙ process_new → строка очереди после терминала."""
    fb = bridge or FakeBridge()
    OD.bc = fb
    CLAUDE["out"], CLAUDE["rc"] = out, rc
    tid = fb.enqueue_task("Filipp-328-dev", text)["id"]
    OD._LAST_RUN.clear()
    OD.process_new()
    return fb, fb.rows[tid]


shutil.rmtree(os.environ["CC_SHADOW_DIR"], ignore_errors=True)
fb, row = run_one("сделай нечто\n[result_ref: file shadow_rule.py]")
lines = shadow_lines()
res.append(ok(len(lines) == 1, "(5) на терминал шага записана РОВНО одна строка тени (%d)"
              % len(lines)))
rec = lines[0] if lines else {}
res.append(ok(rec.get("real") == "done" and rec.get("shadow") == "done"
              and rec.get("kind") == "file" and rec.get("pointer") == "shadow_rule.py",
              "(5) в строке названы настоящий исход, теневой, вид и указатель адреса"))
res.append(ok(rec.get("judge_why") and "байт" in str(rec.get("judge_why")),
              "(5) причина СУДЬИ едет дословно рядом (%r)" % str(rec.get("judge_why"))[:40]))
res.append(ok(set(rec) >= {"real", "shadow", "judge", "diff", "dir", "why", "at", "id", "lane",
                           "from", "kind", "pointer", "judge_why"},
              "(5) поля записи на месте (%s)" % sorted(rec)))
res.append(ok(os.path.basename(os.path.join(os.environ["CC_SHADOW_DIR"], OD.SHADOW_FILE_NAME))
              == "shadow-rule.jsonl", "(5) место названо явно: reports/<дата>/shadow-rule.jsonl"))
# ТРИ РУБЕЖА ИЗОЛЯЦИИ — зеркало `_series_file`: промах любого стоит записи во временный каталог,
# а не мусора в боевых отчётах.
_keep = os.environ.pop("CC_SHADOW_DIR")
res.append(ok(OD._shadow_dir() == OD.SHADOW_TEST_DIR,
              "(5) признак тест-прогона → временный каталог (%s)" % OD._shadow_dir()))
_om = os.environ.pop("ORCH_TEST_MODE")
res.append(ok(not OD._IS_DAEMON and OD._shadow_dir() == OD.SHADOW_TEST_DIR,
              "(5) не демон → временный каталог даже без признака тест-прогона"))
os.environ["ORCH_TEST_MODE"] = _om
os.environ["CC_SHADOW_DIR"] = _keep

print("\n(6) ЗАМОК A — НАСТОЯЩИЙ ВЕРДИКТ НЕ ИЗМЕНИЛСЯ (посимвольно, тень вкл/выкл)")
CASES = [("зелёный, адреса нет", "проверь что-нибудь", "сводка: сделано\nFACT: read-only", 0),
         ("зелёный, адрес живой", "нечто\n[result_ref: file shadow_rule.py]",
          "сводка: сделано\nFACT: read-only", 0),
         ("зелёный, адрес в никуда", "нечто\n[result_ref: file docs/artifacts/НЕТ.md]",
          "сводка: сделано\nFACT: read-only", 0),
         ("красный", "нечто", "claude упал", 1)]
snaps = {}
for flag in ("1", "0"):
    os.environ["SHADOW_RULE"] = flag
    shutil.rmtree(os.environ["CC_SHADOW_DIR"], ignore_errors=True)
    got = []
    for label, text, out, rc in CASES:
        _fb, r = run_one(text, out, rc)
        got.append((label, r["status"], r["result"]))
    snaps[flag] = got
    res.append(ok(len(shadow_lines()) == (4 if flag == "1" else 0),
                  "(6) SHADOW_RULE=%s → строк тени %d" % (flag, len(shadow_lines()))))
os.environ["SHADOW_RULE"] = "1"
same = [a for a, b in zip(snaps["1"], snaps["0"]) if a != b]
res.append(ok(not same, "(6) терминалы ПОСИМВОЛЬНО равны при тени вкл и выкл (разошлось %d из %d)"
              % (len(same), len(CASES))))
res.append(ok([s[1] for s in snaps["1"]] == ["done", "done", "done", "failed"],
              "(6) исходы прежние: три done и один failed (%s)" % [s[1] for s in snaps["1"]]))
res.append(ok(snaps["1"][2][2] == snaps["1"][0][2],
              "(6) шаг с теневым «не доказан» закрыт тем же текстом, что и шаг без адреса"))
res.append(ok(snaps["1"][3][2].startswith("[правда:"),
              "(6) терминал failed прошёл прежнее обрамление правды статуса"))

print("\n(7) ЗАМОК B — ХОД НЕ ИЗМЕНИЛСЯ: шаг с теневым «неизвестно» идёт дальше")
_real_dec = OD._maybe_dec_after
moves = []
OD._maybe_dec_after = lambda text, status: moves.append((str(text)[:22], status))
for flag in ("1", "0"):
    os.environ["SHADOW_RULE"] = flag
    moves.clear()
    _fb, r = run_one("[шаг 1/2 родитель 900] сделай первую часть")
    res.append(ok(moves == [("[шаг 1/2 родитель 900]", "done")],
                  "(7) SHADOW_RULE=%s → цепь двинута ровно раз и НАСТОЯЩИМ статусом (%s)"
                  % (flag, moves)))
os.environ["SHADOW_RULE"] = "1"
moves.clear()
shutil.rmtree(os.environ["CC_SHADOW_DIR"], ignore_errors=True)
_fb, r = run_one("[шаг 1/2 родитель 900] сделай первую часть")
ln = shadow_lines()
res.append(ok(ln and ln[0]["shadow"] == RJ.UNKNOWN and ln[0]["diff"] and r["status"] == "done",
              "(7) тень сказала «неизвестно», а шаг закрыт done и цепь пошла дальше"))
OD._maybe_dec_after = _real_dec

print("\n(8) ЦЕНА — адреса нет, значит мира не касаемся ВООБЩЕ")
_real_gather = RF.gather
gathers = []
OD.result_judge_facts.gather = lambda refs, **kw: (gathers.append((list(refs), dict(kw))),
                                                   _real_gather(refs, **kw))[1]
shutil.rmtree(os.environ["CC_SHADOW_DIR"], ignore_errors=True)
run_one("проверь что-нибудь безобидное")
res.append(ok(gathers == [], "(8) адрес не назван → фактов не спрашивали НИ РАЗУ (%s)" % gathers))
res.append(ok(shadow_lines() and shadow_lines()[0]["judge_why"] == RJ.NOT_NAMED,
              "(8) и при этом строка тени написана, с честной причиной «адрес не назван»"))
gathers.clear()
run_one("нечто\n[result_ref: file shadow_rule.py]")
res.append(ok(len(gathers) == 1 and len(gathers[0][0]) == 1,
              "(8) адрес назван → РОВНО один сбор фактов под РОВНО один адрес (%s)" % gathers))
# 17.08.2026: прежде здесь стояло «brain=False — к мосту за узлами не ходим». Запрет снят
# решением Штаба: он стоял на ЧУЖОМ числе (543 с — верхняя оценка cc_log, а не цена узла; живая
# проба 17.08 — 2 с) и стоил виду `brain` всей работы (3 обрыва живой серии из 3). Цена не
# исчезла, а СУЗИЛАСЬ: к мосту идём ТОЛЬКО когда адрес назвал узел, и под общим бюджетом 120 с.
# Здесь адрес — файл, поэтому мост не спрашивается ВООБЩЕ, и это ниже проверено числом.
res.append(ok(len(gathers) == 1 and gathers[0][1].get("brain") is True,
              "(8) сбор идёт с brain=True — узел спрашиваем живьём, если адрес его назвал "
              "(kwargs=%s)" % (gathers[0][1] if gathers else None)))
_ref0 = (gathers[0][0] or [{}])[0] if gathers else {}
_kind0 = _ref0.get("kind") if isinstance(_ref0, dict) else (list(_ref0) + [""])[0]
res.append(ok(_kind0 == "file",
              "(8) но АДРЕС здесь не узел (вид «%s»), значит к мосту не ушло ни одного запроса"
              % _kind0))
OD.result_judge_facts.gather = _real_gather

print("\n(9) ГРАНИЦЫ")
shutil.rmtree(os.environ["CC_SHADOW_DIR"], ignore_errors=True)
fb, row = run_one("нечто\n[result_ref: file shadow_rule.py]")
res.append(ok(fb.calls.count("complete_task") == 1 and "set_needs_approval" not in fb.calls,
              "(9) очередь тронута РОВНО одним терминалом, тень к ней не ходила (%s)" % fb.calls))
res.append(ok("result" not in OD._shadow_note_terminal.__code__.co_varnames,
              "(9) у рук тени нет параметра «отчёт» — сказать о себе шаг здесь не может ничем"))
# Адрес берётся из ПОЛЯ: тот же отчёт с адресом в тексте РЕЗУЛЬТАТА тени не даёт ничего.
shutil.rmtree(os.environ["CC_SHADOW_DIR"], ignore_errors=True)
run_one("нечто без адреса", out="сделано\n[result_ref: file shadow_rule.py]")
ln = shadow_lines()
res.append(ok(ln and ln[0]["judge_why"] == RJ.NOT_NAMED and ln[0]["kind"] == "",
              "(9) адрес, названный ОТЧЁТОМ, тенью не читается — только поле задачи"))
os.environ["SHADOW_RULE"] = "0"
shutil.rmtree(os.environ["CC_SHADOW_DIR"], ignore_errors=True)
_fb, r = run_one("нечто\n[result_ref: file shadow_rule.py]")
res.append(ok(not os.path.exists(os.path.join(os.environ["CC_SHADOW_DIR"], OD.SHADOW_FILE_NAME))
              and r["status"] == "done",
              "(9) ОТКАТ SHADOW_RULE=0: ни файла, ни строки — ветка мертва ДО чтения поля"))
os.environ["SHADOW_RULE"] = "1"
res.append(ok(OD._shadow_on() and (os.environ.pop("SHADOW_RULE"), OD._shadow_on())[1],
              "(9) по умолчанию тень ВКЛЮЧЕНА — она ничего не решает, платить за неё нечем"))
os.environ["SHADOW_RULE"] = "1"

shutil.rmtree(TMP, ignore_errors=True)
print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
