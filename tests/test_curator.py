"""КУРАТОР ЦЕЛИ (мета-дирижёр, шаги 1–2/7 родитель 231, 12.07.2026).
Шаг 1: флаг CURATOR из .env (дефолт 0, парсер как STEP_SELFHEAL) + _curator_consult(цель, итог)
через _thinker_exec (--max-turns 1, таймаут 180с): вход = цель ДОСЛОВНО + итог/сводка + секции
«ХВОСТ/ХВОСТЫ/технически готово; функционально…» из result; строгий JSON
{"verdict":"closed"|"followup"|"human","tasks":[…],"human":"…","reason":"…"};
мусор/сбой/таймаут → None (fail-safe). Сети/claude нет — subprocess.run подменён.
Шаг 2: ТОЧКИ ВЫЗОВА — финал done/failed одиночки «тз:»/«задача:» vps-полосы (process_new) и
сводка родителя vps-цепи (_dec_post_summary); closed/сбой → тишина, followup/human → карточка
[куратор …] в 328; дедуп = память процесса + restart-proof скан маркеров очереди; МИМО:
⏱ / «отклонено Филиппом» / конверты / pc-полоса / плановый рестарт-🔁; CURATOR=0 → ноль вызовов.
Проверки: (0) парсер флага; (1) парсер JSON (все вердикты, мусор-обёртка, невалидное → None,
followup без tasks → None, обрезка ТЗ до 400); (2) выжимка хвостов; (3) consult: промпт несёт
цель дословно + сводку + хвосты, кондуктор --max-turns 1 / таймаут 180; (4) фолбэки consult:
исключение / exit!=0 / мусор в ответе → None; (5) триггер одиночки (вкл/выкл, все вердикты,
сбой думателя); (6) МИМО-исключения; (7) дедуп (память + маркер очереди); (8) триггер цепи
(_dec_post_summary, идемпотентность, ⏱/отклонено); (9) осиротевшая карточка куратора;
(10) CURATOR=0 байт-в-байт (шаг 6/7): боевой _curator_consult на месте, спай на самом думателе
_thinker_exec + счётчик enqueue — ноль вызовов думателя, ноль лишних enqueue, финалы дословно."""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
# Изоляция ПРИНУДИТЕЛЬНАЯ (не setdefault): headless-задача наследует env демона, где
# STEP_SELFHEAL=1/PLAN_ADAPT=1 из боевого .env — setdefault их не перебил бы, и failed-финалы
# в проверках дёргали бы думатель самопочинки (урок шага 6/7 родителя 231).
os.environ["STEP_SELFHEAL"] = "0"
os.environ["PLAN_ADAPT"] = "0"
os.environ["CURATOR_SCOPE"] = "0"  # новый флаг (15.07.2026): консультация на всех done/failed

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD


class FakeProc:
    def __init__(s, out, rc=0): s.stdout, s.stderr, s.returncode = out, "", rc


_real_run = OD.subprocess.run
def fake_run(args, **kw):
    if args and args[0] == OD.CLAUDE_BIN and args[-1].startswith(OD.CURATOR_PREAMBLE):
        fake_run.calls += 1
        fake_run.prompts.append(args[-1])
        fake_run.cmds.append(list(args))
        fake_run.kws.append(dict(kw))
        if fake_run.exc:
            raise fake_run.exc
        return FakeProc(fake_run.out, fake_run.rc)
    return FakeProc("ok")
OD.subprocess.run = fake_run


def fresh(out='{"verdict":"closed","tasks":[],"human":"","reason":"дефолт мока"}', rc=0, exc=None):
    fake_run.calls, fake_run.prompts, fake_run.cmds, fake_run.kws = 0, [], [], []
    fake_run.out, fake_run.rc, fake_run.exc = out, rc, exc


# (0) парсер флага CURATOR — как STEP_SELFHEAL: строго "1", остальное = выкл
print("(0) парсер флага CURATOR:")
os.environ.pop("CURATOR", None)
res.append(ok(OD._curator_on() is False, "нет в env → выкл (дефолт 0)"))
os.environ["CURATOR"] = "0"
res.append(ok(OD._curator_on() is False, "CURATOR=0 → выкл"))
os.environ["CURATOR"] = " 1 "
res.append(ok(OD._curator_on() is True, "CURATOR=' 1 ' → вкл (strip как STEP_SELFHEAL)"))
os.environ["CURATOR"] = "true"
res.append(ok(OD._curator_on() is False, "CURATOR=true (мусор) → выкл, не падает"))
os.environ["CURATOR"] = "1"
res.append(ok(OD._curator_on() is True, "CURATOR=1 → вкл"))

# (1) парсер JSON куратора
print("(1) парсер _parse_curator_json:")
v = OD._parse_curator_json('{"verdict":"closed","tasks":[],"human":"","reason":"цель закрыта"}')
res.append(ok(v == {"verdict": "closed", "tasks": [], "human": "", "reason": "цель закрыта"},
              "closed: чистый JSON"))
v = OD._parse_curator_json(
    'Вот ответ:\n```json\n{"verdict":"followup","tasks":["дописать тест на пустой env",'
    '" прогнать gate.py "],"human":"","reason":"хвост в тестах"}\n```')
res.append(ok(v is not None and v["verdict"] == "followup"
              and v["tasks"] == ["дописать тест на пустой env", "прогнать gate.py"],
              "followup: мусор-обёртка терпится, ТЗ стрипаются, пустые режутся"))
v = OD._parse_curator_json('{"verdict":"HUMAN","tasks":[],"human":"нужно да на clasp","reason":"красная зона"}')
res.append(ok(v is not None and v["verdict"] == "human" and v["human"] == "нужно да на clasp",
              "human: регистр вердикта нормализуется, human-строка на месте"))
long_task = "x" * 900
v = OD._parse_curator_json('{"verdict":"followup","tasks":["' + long_task + '"],"human":"","reason":"r"}')
res.append(ok(v is not None and len(v["tasks"][0]) == OD.CURATOR_TASK_MAX == 400,
              "ТЗ длиннее 400 режется до CURATOR_TASK_MAX"))
res.append(ok(OD._parse_curator_json('{"verdict":"followup","tasks":[],"human":"","reason":"r"}') is None,
              "followup без tasks → None (пустой followup бессмыслен)"))
res.append(ok(OD._parse_curator_json('{"verdict":"followup","tasks":"не список","human":"","reason":"r"}') is None,
              "followup с tasks-не-списком → None"))
res.append(ok(OD._parse_curator_json('{"verdict":"maybe","tasks":[],"human":"","reason":"r"}') is None,
              "verdict вне closed|followup|human → None"))
res.append(ok(OD._parse_curator_json("совсем не JSON") is None, "текст без JSON → None"))
res.append(ok(OD._parse_curator_json('{"verdict":"closed", сломанный json}') is None,
              "битый JSON → None"))
res.append(ok(OD._parse_curator_json("") is None and OD._parse_curator_json(None) is None,
              "пусто/None → None"))
res.append(ok(OD._parse_curator_json('["closed"]') is None, "JSON не-dict → None"))
v = OD._parse_curator_json('{"verdict":"closed","tasks":["косметика"],"human":"","reason":"r"}')
res.append(ok(v is not None and v["tasks"] == ["косметика"],
              "closed с tasks валиден (tasks сохраняются, решает вызывающий код)"))

# (2) выжимка секций хвостов из result
print("(2) выжимка _curator_tails:")
result_text = ("Сделал фикс рендера, гейт 81/81.\n"
               "Детали: правка bot.py строка 10.\n"
               "\n"
               "ХВОСТЫ:\n"
               "- дописать тест на пустой env\n"
               "- подрезать cc_log\n"
               "\n"
               "Статус: технически готово; функционально не подтверждено (нужен живой прогон).\n"
               "\n"
               "прочий текст без триггеров")
t = OD._curator_tails(result_text)
res.append(ok("ХВОСТЫ:" in t and "дописать тест на пустой env" in t and "подрезать cc_log" in t,
              "блок ХВОСТЫ: захвачен целиком (триггер + строки до пустой)"))
res.append(ok("технически готово; функционально не подтверждено" in t,
              "строка «технически готово; функционально…» захвачена"))
res.append(ok("прочий текст без триггеров" not in t and "правка bot.py" not in t,
              "нетриггерные куски НЕ попадают в выжимку"))
res.append(ok(OD._curator_tails("всё сделано, чисто") == "(секций про хвосты в итоге нет)",
              "нет секций → явная заглушка"))
res.append(ok(OD._curator_tails("") == "(секций про хвосты в итоге нет)"
              and OD._curator_tails(None) == "(секций про хвосты в итоге нет)",
              "пусто/None → заглушка, не падает"))
res.append(ok(len(OD._curator_tails("ХВОСТ: " + "у" * 5000)) <= 1500, "потолок выжимки 1500"))

# (3) consult: промпт и кондуктор
print("(3) _curator_consult — промпт и кондуктор:")
fresh(out='{"verdict":"followup","tasks":["дожать тест"],"human":"","reason":"есть хвост"}')
goal = "тз: почини рендер карточки байка и добавь тест"
v = OD._curator_consult(goal, result_text)
res.append(ok(v is not None and v["verdict"] == "followup" and v["tasks"] == ["дожать тест"],
              "валидный ответ → dict вердикта"))
p = fake_run.prompts[0]
res.append(ok(goal in p, "цель ДОСЛОВНО в промпте"))
res.append(ok("Сделал фикс рендера, гейт 81/81." in p, "итог/сводка (первая строка result) в промпте"))
res.append(ok("ХВОСТЫ:" in p and "технически готово; функционально не подтверждено" in p,
              "секции хвостов в промпте"))
res.append(ok("прочий текст без триггеров" not in p, "нетриггерный шум result в промпт не тащится"))
cmd = fake_run.cmds[0]
mt = cmd[cmd.index("--max-turns") + 1] if "--max-turns" in cmd else None
res.append(ok(mt == "1", "кондуктор: --max-turns 1 (чистый генератор)"))
res.append(ok(fake_run.kws[0].get("timeout") == OD.CURATOR_TIMEOUT == 180, "таймаут 180с"))
res.append(ok("--model" in cmd and cmd[cmd.index("--model") + 1] == OD.ORCH_MODEL,
              "кондуктор: модель ORCH_MODEL (та же схема, что думатели)"))

# (4) фолбэки consult → None
print("(4) фолбэки _curator_consult:")
fresh(exc=OD.subprocess.TimeoutExpired(cmd="claude", timeout=180))
res.append(ok(OD._curator_consult("цель", "итог") is None, "таймаут думателя → None"))
fresh(exc=OSError("no binary"))
res.append(ok(OD._curator_consult("цель", "итог") is None, "исключение запуска → None"))
fresh(out="", rc=1)
res.append(ok(OD._curator_consult("цель", "итог") is None, "exit!=0 → None"))
fresh(out="я подумал и решил, что всё хорошо")
res.append(ok(OD._curator_consult("цель", "итог") is None, "мусор без JSON → None"))
fresh(out='{"verdict":"followup","tasks":[],"human":"","reason":"r"}')
res.append(ok(OD._curator_consult("цель", "итог") is None, "невалидный вердикт (followup без tasks) → None"))
fresh(out='{"result":"{\\"verdict\\":\\"closed\\",\\"tasks\\":[],\\"human\\":\\"\\",\\"reason\\":\\"ок\\"}"}')
v = OD._curator_consult("цель", "итог")
res.append(ok(v is not None and v["verdict"] == "closed",
              "CLI-конверт --output-format json распаковывается (_thinker_exec)"))
v = OD._curator_consult(None, None)
res.append(ok(v is not None and v["verdict"] == "closed"
              and "(итог пуст)" in fake_run.prompts[-1]
              and "(секций про хвосты в итоге нет)" in fake_run.prompts[-1],
              "None-входы не роняют consult (заглушки итога/хвостов в промпте)"))

# ==== ШАГ 2/7: точки вызова куратора (триггеры / МИМО / дедуп / цепь / сирота) ====
class FakeBridge:
    """Мост-очередь в памяти: get/claim/complete/enqueue. Сети нет."""
    def __init__(s):
        s.rows, s.nid = {}, 200
    def add(s, status, text, frm="Filipp-328", result=""):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": text, "status": status,
                         "result": result, "updated": "2026-07-12T00:00:00+00:00"}
        return s.nid
    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True, "items": [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                                      if r["status"] in sts]}
    def claim_task(s, tid, lane=None):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        if r["status"] != "new": return {"ok": False, "error": "already_claimed", "status": r["status"]}
        r["status"] = "in_progress"
        return {"ok": True, "task": dict(r)}
    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"] = status, result
        return {"ok": True}
    def enqueue_task(s, frm, text, lane=None):
        return {"ok": True, "id": s.add("new", text, frm=frm)}
    def set_needs_approval(s, tid, what):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"] = "needs_approval", what
        return {"ok": True}
    def task_heartbeat(s, tid): return {"ok": True}
    def cards(s, mark="[куратор"):
        return [dict(r) for r in s.rows.values() if str(r["task_text"]).startswith(mark)]


_real_bc, _real_run_task, _real_rp = OD.bc, OD.run_task, OD._restart_pending
_real_consult = OD._curator_consult
OD._restart_pending = lambda: False

consults = []
def spy_consult(goal, result):
    consults.append((goal, result))
    return spy_consult.verdict
OD._curator_consult = spy_consult


def setup(run_ret, frm="Filipp-328-dev", text="тз: почини рендер карточки байка",
          verdict={"verdict": "closed", "tasks": [], "human": "", "reason": "цель закрыта"}):
    fb = FakeBridge()
    OD.bc = fb
    OD.run_task = lambda tid, t, task_timeout=600, preamble=None: run_ret
    OD._curated.clear(); OD._summarized.clear(); consults.clear()
    spy_consult.verdict = verdict
    return fb, fb.add("new", text, frm=frm)


# (5) триггер одиночки vps-полосы
print("(5) триггер: финал одиночки vps-полосы:")
os.environ["CURATOR"] = "0"
fb, t = setup(("done", "сделано, гейт зелёный"))
OD.process_new()
res.append(ok(consults == [] and fb.cards() == [] and fb.rows[t]["status"] == "done",
              "CURATOR=0 → ноль консультаций, ноль карточек, финал задачи прежний"))
os.environ["CURATOR"] = "1"
fb, t = setup(("done", "сделано, гейт зелёный"))
OD.process_new()
res.append(ok(len(consults) == 1 and consults[0] == ("тз: почини рендер карточки байка",
                                                     "сделано, гейт зелёный"),
              "CURATOR=1, done → РОВНО одна консультация: цель = текст задачи ДОСЛОВНО + итог"))
res.append(ok(fb.cards() == [] and fb.rows[t] == dict(fb.rows[t], status="done",
                                                      result="сделано, гейт зелёный"),
              "verdict=closed → тишина (карточки нет, финал задачи не тронут)"))
fb, t = setup(("done", "сделано, но есть хвост"),
              verdict={"verdict": "followup", "tasks": ["тз: дожать тест на пустой env"],
                       "human": "", "reason": "хвост в тестах"})
OD.process_new()
cards = fb.cards("[куратор задача")
res.append(ok(len(cards) == 1 and cards[0]["task_text"].startswith(f"[куратор задача {t}]")
              and cards[0]["status"] == "done" and cards[0]["from"] == "Filipp-328-dec",
              "followup → карточка [куратор задача N] synthetic-задачей (done, from -dec)"))
res.append(ok("🧭" in cards[0]["result"] and "тз: дожать тест на пустой env" in cards[0]["result"]
              and "хвост в тестах" in cards[0]["result"]
              and "поставлены продолжения" in cards[0]["result"],
              "тело карточки: 🧭 + хвосты списком + причина + отчёт о постановке (шаг 3/7)"))
res.append(ok(fb.rows[t]["status"] == "done" and fb.rows[t]["result"] == "сделано, но есть хвост",
              "финал самой задачи карточкой не тронут"))
fb, t = setup(("failed", "гейт красный, не смог"),
              verdict={"verdict": "human", "tasks": [], "human": "нужно «да» на clasp",
                       "reason": "красная зона"})
OD.process_new()
cards = fb.cards("[куратор задача")
res.append(ok(len(consults) == 1 and len(cards) == 1
              and "требует владельца" in cards[0]["result"]
              and "нужно «да» на clasp" in cards[0]["result"],
              "failed-одиночка тоже терминал; human → карточка «требует владельца»"))
hum = fb.cards("[куратор владельцу цель")
res.append(ok(len(hum) == 1 and hum[0]["status"] == "needs_approval"
              and "нужно «да» на clasp" in hum[0]["result"],
              "…и пункт ушёл в сводную карточку владельцу (needs_approval, шаг 4/7)"))
fb, t = setup(("done", "сделано"), verdict=None)
OD.process_new()
res.append(ok(len(consults) == 1 and fb.cards() == [] and fb.rows[t]["status"] == "done",
              "сбой думателя (None) → тишина, финал цел, цикл не падает (fail-safe)"))
fb, t = setup(("done", "сделано"), frm="Filipp-328", text="задача: проверь логи")
OD.process_new()
res.append(ok(len(consults) == 1, "from=Filipp-328 («задача:») — тоже одиночка, куратор зовётся"))

# (6) МИМО-исключения
print("(6) МИМО куратора:")
fb, t = setup(("done", "исполнено"), text="[конверт одобренной заявки 55] сделай clasp redeploy")
OD.process_new()
res.append(ok(consults == [] and fb.cards() == [], "конверт одобренной заявки → мимо"))
fb, t = setup(("failed", OD.TIMEOUT_MARK + " таймаут задачи 600s — claude -p убит"))
OD.process_new()
res.append(ok(consults == [] and fb.cards() == [], "⏱-диагноз (таймаут/сирота) → мимо"))
fb, t = setup(("done", "🔁 Завершено плановым рестартом демона (самомодификация)"))
OD.process_new()
res.append(ok(consults == [] and fb.cards() == [], "плановый рестарт-🔁 → мимо"))
fb, t = setup(("failed", "отклонено Филиппом (кнопка ❌)"))
OD.process_new()
res.append(ok(consults == [] and fb.cards() == [], "«отклонено Филиппом» → мимо"))
fb, t = setup(("done", "сделано"), frm="Filipp-pc-dev")
OD.process_new()
res.append(ok(consults == [] and fb.cards() == [], "pc-полоса (Filipp-pc-dev) → мимо"))
fb, t = setup(("done", "шаг сделан"), frm="Filipp-328-dec", text="[шаг 1/1 родитель 300] сделай X")
OD.process_new()
res.append(ok(fb.cards("[куратор задача") == [], "шаг декомпозера НЕ одиночка — [куратор задача] нет"))
res.append(ok(len(consults) == 1 and "родитель 300" in consults[0][0],
              "…но финал шага финалит цепь → одна консультация ЦЕПИ (сводка родителя)"))

# (7) дедуп: одна консультация на терминал
print("(7) дедуп:")
fb, _ = setup(("done", "x"))
OD._maybe_curator("задача", 5, "цель", "итог")
OD._maybe_curator("задача", 5, "цель", "итог")
res.append(ok(len(consults) == 1, "повторный вызов того же терминала → консультация одна (память)"))
fb, _ = setup(("done", "x"))
fb.add("done", "[куратор задача 5] вердикт куратора", frm="Filipp-328-dec", result="🧭 старая")
OD._curated.clear()
OD._maybe_curator("задача", 5, "цель", "итог")
res.append(ok(consults == [], "маркер [куратор задача 5] уже в очереди → скан глушит (restart-proof)"))
OD._maybe_curator("родитель", 5, "цель", "итог")
res.append(ok(len(consults) == 1, "тот же id, но другой вид терминала (родитель) — не путается"))

# (8) триггер цепи: _dec_post_summary
print("(8) триггер: сводка родителя цепи:")
def chain(step2_status="done", step2_result="шаг 2 сделан", verdict=None):
    fb, _ = setup(("done", "x"),
                  verdict=verdict or {"verdict": "followup", "tasks": ["тз: дожать хвост цепи"],
                                      "human": "", "reason": "хвост"})
    p = fb.add("done", "декомпозируй: собери фичу Y", frm="Filipp-328-dec",
               result="1. шаг один\n2. шаг два")
    fb.add("done", f"[шаг 1/2 родитель {p}] шаг один", frm="Filipp-328-dec", result="шаг 1 сделан")
    fb.add(step2_status, f"[шаг 2/2 родитель {p}] шаг два", frm="Filipp-328-dec", result=step2_result)
    return fb, p
fb, p = chain()
OD._dec_post_summary(p)
sums = fb.cards("[сводка родитель")
cards = fb.cards("[куратор родитель")
res.append(ok(len(sums) == 1 and sums[0]["status"] == "done", "сводка родителя встала как раньше"))
res.append(ok(len(consults) == 1 and consults[0][0] == "декомпозируй: собери фичу Y"
              and "Сводка декомпозиции" in consults[0][1],
              "консультация ПОСЛЕ сводки: цель = task_text родителя дословно, итог = сводка"))
res.append(ok(len(cards) == 1 and cards[0]["task_text"].startswith(f"[куратор родитель {p}]"),
              "followup → карточка [куратор родитель N]"))
OD._dec_post_summary(p)
res.append(ok(len(consults) == 1 and len(fb.cards("[куратор родитель")) == 1,
              "повторный вызов (рестарт/хвостовой скан) → без дублей консультации/карточки"))
os.environ["CURATOR"] = "0"
fb, p = chain()
OD._dec_post_summary(p)
res.append(ok(len(fb.cards("[сводка родитель")) == 1 and consults == [] and fb.cards() == [],
              "CURATOR=0 → сводка как раньше, куратора нет"))
os.environ["CURATOR"] = "1"
fb, p = chain(step2_status="failed", step2_result=OD.TIMEOUT_MARK + " ПК-театр не отвечает")
OD._dec_post_summary(p)
res.append(ok(consults == [] and fb.cards() == [], "⏱-диагноз в шаге цепи (виден в сводке) → мимо"))
fb, p = chain(step2_status="failed", step2_result="отклонено Филиппом («нет 42»)")
OD._dec_post_summary(p)
res.append(ok(consults == [] and fb.cards() == [], "«отклонено Филиппом» в цепи → мимо"))

# (9) осиротевшая карточка куратора (демон упал между enqueue и complete)
print("(9) осиротевшая карточка:")
fb, _ = setup(("done", "x"))
ran = []
OD.run_task = lambda tid, t, task_timeout=600, preamble=None: (ran.append(int(tid)) or ("done", "x"))
oid = fb.add("new", "[куратор задача 77] вердикт куратора", frm="Filipp-328-dec")
del fb.rows[list(fb.rows)[0]]     # убрать сеттаповскую new-задачу — сирота должна взяться первой
OD.process_new()
res.append(ok(fb.rows[oid]["status"] == "done" and "🧭" in fb.rows[oid]["result"],
              "сирота доводится done-карточкой, НЕ уходит планировщику"))
res.append(ok(ran == [] and not any("[шаг" in str(r["task_text"]) for r in fb.rows.values()),
              "claude не зовётся, fan-out шагов не происходит"))
res.append(ok(bool(OD._CURATOR_CARD_RE.match("[куратор родитель 12] вердикт куратора"))
              and not OD._CURATOR_CARD_RE.match("[куратор нечто 12] х"),
              "маркер-regex: задача|родитель, прочее не матчится"))

# (10) CURATOR=0 байт-в-байт (шаг 6/7): спай consults снят — БОЕВОЙ _curator_consult на месте,
# слежка на уровне ниже: сам думатель (_thinker_exec) + КАЖДЫЙ enqueue моста. Доказательство:
# при CURATOR=0 путь мёртв ДО думателя, новых задач в очереди ноль, финалы — дословно как без куратора.
print("(10) CURATOR=0 байт-в-байт:")
import copy
os.environ["CURATOR"] = "0"
OD._curator_consult = _real_consult
thinker_calls = []
_real_thinker = OD._thinker_exec
OD._thinker_exec = lambda *a, **k: (thinker_calls.append(a), None)[1]
_orig_enqueue = FakeBridge.enqueue_task
enq = []
def _counting_enqueue(s, frm, text, lane=None):
    enq.append(str(text))
    return _orig_enqueue(s, frm, text, lane)
FakeBridge.enqueue_task = _counting_enqueue

fb, t = setup(("done", "сделано, гейт зелёный"))
expected = copy.deepcopy(fb.rows)
expected[t]["status"], expected[t]["result"] = "done", "сделано, гейт зелёный"
OD.process_new()
res.append(ok(fb.rows == expected and enq == [] and thinker_calls == [],
              "одиночка done: финал байт-в-байт, ноль enqueue, думатель не звался"))
enq.clear(); thinker_calls.clear()
fb, t = setup(("failed", "гейт красный: 2 теста"))
expected = copy.deepcopy(fb.rows)
expected[t]["status"], expected[t]["result"] = "failed", "гейт красный: 2 теста"
OD.process_new()
res.append(ok(fb.rows == expected and enq == [] and thinker_calls == [],
              "одиночка failed: финал байт-в-байт, ноль enqueue, думатель не звался"))
enq.clear(); thinker_calls.clear()
fb, p = chain()
OD._dec_post_summary(p)
res.append(ok(len(enq) == 1 and enq[0].startswith("[сводка родитель")
              and thinker_calls == [] and fb.cards() == [],
              "цепь: единственный enqueue — сводка (как без куратора), думатель мёртв"))

OD._thinker_exec = _real_thinker
FakeBridge.enqueue_task = _orig_enqueue

OD.bc = _real_bc
OD.run_task = _real_run_task
OD._restart_pending = _real_rp
OD._curator_consult = _real_consult
OD._curated.clear(); OD._summarized.clear()
os.environ.pop("CURATOR", None)
OD.subprocess.run = _real_run

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
