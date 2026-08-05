"""ПОЗИЦИЯ ЗАЯВЛЕНИЯ: цитата маркера красной зоны — не заявление (класс 05.08.2026).

ЖИВОЙ КЛАСС. Детект читал маркер В ЛЮБОМ МЕСТЕ строки, поэтому отчёт, в котором маркер лишь
ПРОЦИТИРОВАН (ячейка таблицы, обратные кавычки, проза о самом контуре), демон принимал за
самодекларацию и ЗАМЕНЯЛ ВЕСЬ ОТЧЁТ хвостом той строки. Три боевых случая за 14 суток, дословно
из журнала демона (orchestrator_daemon.log):
  · id=246 04.08 07:46 — «заявка исполнителя (NA_MARKER): ` |»  (весь отчёт → три символа);
  · id=130 31.07 15:14 — «NEEDS_APPROVAL: ` в любой строке ИЛИ одна из 8 фраз `_NA_FALLBACK`
    где угодно в отчёте.» (отчёт О САМОМ ДЕТЕКТЕ съеден детектом);
  · id=29  29.07 05:31 — «NEEDS_APPROVAL: op=…` → демон → devbot (другой источник, шаблон гарда
    не использ…» — хвост начинается с «op=», то есть проверкой ФОРМЫ ХВОСТА этот случай не
    ловится вовсе: решает ПОЗИЦИЯ, а не вид строки.

Правило — зеркало правила исполняющей позиции (5ca761d): заявлением считается маркер, стоящий в
ЗАЯВЛЯЮЩЕЙ позиции — там, где его разбирает сам разборщик, то есть в НАЧАЛЕ строки (хвост этой
строки демон и делает карточкой). Маркер внутри текста = цитата: отчёт доезжает целиком, карточки
нет, владелец видит ⚠️-заметку.

НАСТОЯЩЕЕ ЗАЯВЛЕНИЕ ИСПОЛНИТЕЛЯ ОБРАБАТЫВАЕТСЯ КАК ПРЕЖДЕ — секции (2), (4), (6) держат это
байт-в-байт: карточка op=other, замок происхождения (🗣 / исполнимый класс без кнопки), маркер
гарда, слой фразы, фейл-сейф планировщика.

Сети/Telegram/claude/Bridge нет — всё мокнуто, владельцу ничего не уходит."""
import os, sys, json, tempfile, datetime

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PLAN_ADAPT"] = "0"
os.environ["CURATOR"] = "0"
os.environ["STEP_SELFHEAL"] = "0"
os.environ["CARD_DUTY"] = "0"          # изоляция от боевого .env (дежурный по карточкам)
os.environ["ORCH_TEST_MODE"] = "1"
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["MEM_MIN_MB"] = "0"


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []

import orchestrator_daemon as OD

NA = OD.NA_MARKER
SELF_TOKEN = getattr(OD, "ORIGIN_SELF_TOKEN", "🗣 источник карточки: СЛОВА ИСПОЛНИТЕЛЯ")
TEST_TOKEN = "TESTNAPOSTOKEN"
# ДО правки этих имён в модуле нет — фоллбэк, чтобы красный прогон читался ПОВЕДЕНИЕМ,
# а не падал AttributeError-ом на первой проверке (приём соседнего test_card_origin.py).
QUOTE_NOTE = getattr(OD, "NA_QUOTE_NOTE", None)

# ── дословные боевые отчёты (строки собраны вокруг хвостов из журнала демона) ─────────────────
REPORT_246 = (
    "ДЕЖУРНЫЙ ПО КАРТОЧКАМ — read-only разбор потока. Окно 7 суток 28.07 07:22 - 04.08 07:22 UTC.\n"
    "Карточек владельцу 25: 13 approval-задач очереди, 11 сводных карточек куратора, 1 находка ревизора.\n"
    "\n"
    "| # | правило | признак в тексте карточки |\n"
    "|---|---|---|\n"
    "| 1 | пустой объект | строка «Объект:» пуста |\n"
    "| 2 | источник | штамп 🗣 слова исполнителя |\n"
    f"| 3 | самодекларация | маркер `{NA}` |\n"
    "\n"
    "ВЫВОД: машинно выводимо не менее 16 из 25 (64 проц).\n")
REPORT_130 = (
    "Замок происхождения красной карточки на СЕРВЕРНОЙ полосе. ШАГ 1 (read-only): дыра ПОДТВЕРЖДЕНА.\n"
    f"Детект в run-импл читает stdout модели: маркер `{NA}` в любой строке ИЛИ одна из 8 фраз "
    "`_NA_FALLBACK` где угодно в отчёте.\n"
    "process_new ставит из этой строки approvable-карточку с кнопками мимо гарда.\n")
REPORT_29 = (
    "Карточка красной зоны: объект берётся из КОМАНДЫ, а не из шаблона — корень задачи 27.\n"
    f"Поток такой: заявка исполнителя `{NA} op=…` → демон → devbot (другой источник, шаблон гарда "
    "не использован).\n"
    "В хуке-страже добавлены _facts и card_due: нет объекта — карточки нет.\n")
QUOTES = [("246 (таблица правил)", REPORT_246),
          ("130 (проза о самом детекте)", REPORT_130),
          ("29 (хвост начинается с op=)", REPORT_29)]

# дословные боевые ЗАЯВЛЕНИЯ (из того же журнала — id=252 и id=56)
DECL_252 = (f"{NA} op=other | Деплой моста НЕ сделан · что: выложить локальный мост (правка "
            "события на месте) в прод-деплой Apps Script · куда: проект «TurboBaby Bridge»")
DECL_56 = (f"{NA} op=other | Реестр мозга — два ручных шага владельца. 1) Drive: перетащить "
           "KB_booking_flow и KB_collect_booking_spec в папку «TurboBaby Brain»")

print("(1) ЖИВЫЕ ЦИТАТЫ: маркер ВНУТРИ строки заявлением не считается")
for name, rep in QUOTES:
    what, kind = OD._detect_na(rep)
    res.append(ok(kind != "marker", f"{name}: kind={kind!r} (не 'marker'), what={str(what)[:40]!r}"))
    res.append(ok(what is None, f"{name}: дескриптора карточки из цитаты не рождается"))

print("(2) НАСТОЯЩЕЕ ЗАЯВЛЕНИЕ — КАК ПРЕЖДЕ (позиция начала строки)")
CASES_DECL = [
    ("боевое 252", DECL_252, "op=other | Деплой моста НЕ сделан"),
    ("боевое 56", DECL_56, "op=other | Реестр мозга — два ручных шага владельца."),
    ("отчёт + строка заявления", "анализ сделан\n" + DECL_252, "op=other | Деплой моста НЕ сделан"),
    ("с отступом", "   " + DECL_56, "op=other | Реестр мозга"),
    ("пунктом списка", "- " + DECL_56, "op=other | Реестр мозга"),
    ("жирным", "**" + DECL_56, "op=other | Реестр мозга"),
    ("исполнимый класс", f"{NA} op=git_push | нужен push в ветку main", "op=git_push |"),
]
for name, text, head in CASES_DECL:
    what, kind = OD._detect_na(text)
    res.append(ok(kind == "marker" and str(what).startswith(head.split(" | ")[0]),
                  f"{name}: kind='marker', хвост {str(what)[:46]!r}"))
res.append(ok(OD._detect_na(f"{NA}   ")[1] == "marker",
              "пустой хвост заявления — прежний фоллбэк-дескриптор, не потеря"))
res.append(ok("не уточнил" in str(OD._detect_na(f"{NA}   ")[0]),
              "пустой хвост: текст фоллбэка прежний"))
res.append(ok(OD._detect_na("обычный отчёт без единого маркера") == (None, None),
              "чистый отчёт — как прежде (None, None)"))

print("(3) ЗАЯВЛЕНИЕ ПОСЛЕ ЦИТАТЫ В ТОМ ЖЕ ОТЧЁТЕ — заявление побеждает")
what, kind = OD._detect_na(REPORT_246 + "\n" + DECL_252)
res.append(ok(kind == "marker" and "Деплой моста" in str(what),
              f"цитата + заявление → карточка по ЗАЯВЛЕНИЮ: {str(what)[:50]!r}"))

print("(4) СЛОЙ ФРАЗЫ И ЧИСТЫЙ ОТЧЁТ НЕ ЗАТРОНУТЫ")
res.append(ok(OD._detect_na("гейт заблокировал: требует подтверждения владельца")[1] == "phrase",
              "фраза без маркера → прежний 'phrase'"))
res.append(ok(OD._detect_na("нет никаких NEEDS_APPROVAL в этой задаче")[1] is None,
              "слово без двоеточия маркером не было и не стало"))

print("(5) ЗАМЕТКА О ЦИТАТЕ: отчёт цел, владелец предупреждён, заметка себя не детектит")
res.append(ok(isinstance(QUOTE_NOTE, str) and len(QUOTE_NOTE) > 80,
              "NA_QUOTE_NOTE существует и не пуст"))
if isinstance(QUOTE_NOTE, str):
    res.append(ok(NA not in QUOTE_NOTE, "в заметке нет литерала маркера (не самодетект)"))
    res.append(ok(not any(p in QUOTE_NOTE.lower() for p in OD._NA_FALLBACK),
                  "в заметке нет ни одной фразы _NA_FALLBACK"))
    res.append(ok(OD._detect_na(QUOTE_NOTE) == (None, None),
                  "детект на самой заметке чист — следующий круг её не поднимет"))

# ── сквозной путь через _run_task_impl (мок claude -p) ────────────────────────────────────────
print("(6) СКВОЗНОЙ ПУТЬ: отчёт с цитатой доезжает ЦЕЛИКОМ")


class FakePopen:
    def __init__(s, out="", rc=0, on_run=None):
        s.returncode, s._out, s._rc, s._on_run = None, out, rc, on_run

    def communicate(s, timeout=None):
        if s._on_run:
            s._on_run()
        if s.returncode is None:
            s.returncode = s._rc
        return s._out, ""

    def terminate(s):
        s.returncode = -15

    def kill(s):
        s.returncode = -9

    def poll(s):
        return s.returncode


class FakeBc:
    def task_heartbeat(s, tid):
        return {"ok": True}


TMPDIR = tempfile.mkdtemp(prefix="na_position_")
OD.GUARD_BLOCK_DIR = TMPDIR
OD.bc = FakeBc()
OD.MAX_CLAUDE_PROCS = 0
OD.subprocess.run = lambda *a, **kw: type("P", (), {"stdout": "ok", "stderr": "", "returncode": 0})()
if hasattr(OD, "_guard_token_new"):
    OD._guard_token_new = lambda: TEST_TOKEN
fake = {"out": "", "rc": 0, "on_run": None}
OD._POPEN = lambda *a, **kw: FakePopen(fake["out"], fake["rc"], fake["on_run"])


def run(out, rc=0, tid=901, text="дев-задача про разбор карточек", on_run=None):
    fake["out"], fake["rc"], fake["on_run"] = json.dumps({"result": out}), rc, on_run
    st, r = OD._run_task_impl(tid, text, task_timeout=30)
    fake["on_run"] = None
    return st, r


st, r = run(REPORT_246)
res.append(ok(st == "done", f"цитата в отчёте: исход честный (status={st!r}, а не needs_approval)"))
for probe in ("ДЕЖУРНЫЙ ПО КАРТОЧКАМ", "| 1 | пустой объект", "машинно выводимо не менее 16 из 25"):
    res.append(ok(probe in r, f"отчёт доехал целиком: {probe[:38]!r} на месте"))
res.append(ok(len(r) > 400, f"длина отчёта {len(r)} симв. (было 3 символа хвоста)"))
if isinstance(QUOTE_NOTE, str):
    res.append(ok(QUOTE_NOTE.strip()[:20] in r, "⚠️-заметка о цитате приклеена к отчёту"))

st, r = run(REPORT_130, tid=902)
res.append(ok(st == "done" and "дыра ПОДТВЕРЖДЕНА" in r, "отчёт 130 (о самом детекте) доехал целиком"))
st, r = run(REPORT_29, tid=903)
res.append(ok(st == "done" and "_facts и card_due" in r, "отчёт 29 (хвост op=…) доехал целиком"))

print("(7) ГРАНИЦЫ НЕ ОСЛАБЛЕНЫ: заявление, замок происхождения, маркер гарда")
st, r = run("отчёт о работе\n" + DECL_252, tid=904)
res.append(ok(st == "needs_approval", f"настоящее заявление op=other → карточка как прежде ({st!r})"))
res.append(ok(r.startswith("op=other | Деплой моста"), "дескриптор карточки прежнего формата"))
res.append(ok(SELF_TOKEN in r, "штамп происхождения 🗣 на месте (замок не тронут)"))

st, r = run(f"{NA} op=git_push | нужен push в ветку main", tid=905)
res.append(ok(st == "needs_approval" and "op=git_push" in r,
              "заявка исполнимого класса доходит до замка происхождения как прежде"))

def _marker():
    with open(os.path.join(TMPDIR, "906.json"), "w", encoding="utf-8") as f:
        json.dump({"task_id": "906", "hit": "set_fleet_oil", "token": TEST_TOKEN,
                   "card": "🔴 КРАСНОЕ\nЧто: запись ТО масла\nОбъект: байк 5580\nЧисло: 35200"}, f,
                  ensure_ascii=False)

st, r = run(REPORT_246, tid=906, on_run=_marker)
res.append(ok(st == "needs_approval" and "set_fleet_oil" in r,
              "маркер ГАРДА бьёт цитату в отчёте: карточка родилась (реальный блок не потерян)"))

print("(8) ФЕЙЛ-СЕЙФ ПЛАНИРОВЩИКА (урок 166) не ослаблен")
res.append(ok(OD._detect_needs_approval(f"строка\n{NA} op=other | задеплой прод") is not None,
              "план-фейл-сейф: настоящее заявление в выводе планировщика видно как прежде"))
res.append(ok(OD._detect_needs_approval(REPORT_130) is not None,
              "план-фейл-сейф: цитата тоже НЕ проходит молча (там плана нет — честный отказ)"))
res.append(ok(OD._detect_needs_approval("обычный план\n1. шаг\n2. шаг") is None,
              "чистый вывод планировщика — как прежде"))

bad = len([x for x in res if not x])
print(f"\nИТОГО: {len(res) - bad}/{len(res)} PASS, провалов {bad}")
sys.exit(1 if bad else 0)
