"""КУРАТОР ЦЕЛИ (мета-дирижёр, шаг 1/7 родитель 231, 12.07.2026).
Флаг CURATOR из .env (дефолт 0, парсер как STEP_SELFHEAL) + _curator_consult(цель, итог) через
_thinker_exec (--max-turns 1, таймаут 180с): вход = цель ДОСЛОВНО + итог/сводка + секции
«ХВОСТ/ХВОСТЫ/технически готово; функционально…» из result; строгий JSON
{"verdict":"closed"|"followup"|"human","tasks":[…],"human":"…","reason":"…"};
мусор/сбой/таймаут → None (fail-safe). Сети/claude нет — subprocess.run подменён.
Проверки: (0) парсер флага; (1) парсер JSON (все вердикты, мусор-обёртка, невалидное → None,
followup без tasks → None, обрезка ТЗ до 400); (2) выжимка хвостов; (3) consult: промпт несёт
цель дословно + сводку + хвосты, кондуктор --max-turns 1 / таймаут 180; (4) фолбэки consult:
исключение / exit!=0 / мусор в ответе → None."""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("STEP_SELFHEAL", "0")  # изоляция от боевого .env
os.environ.setdefault("PLAN_ADAPT", "0")

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

os.environ.pop("CURATOR", None)
OD.subprocess.run = _real_run

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
