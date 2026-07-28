"""Два хвоста видимости, закрытые 28.07.2026 (продолжение задач 9/12, коммит 8ed16b0).

ХВОСТ 1 — «взял в работу» не доходило. Анонс рождался ТОЛЬКО из 45-секундного снимка
in_progress, а задача живёт 5–9 секунд: между двумя опросами она успевала родиться и умереть,
в снимок не попадала и карточки «🔄 в работе» не было НИ РАЗУ (живые примеры 28.07 — задачи 14
и 15: обе done, ни одного анонса). Опрос СОСТОЯНИЯ бессилен по природе → демон пишет СОБЫТИЕ
взятия строкой JSONL (orchestrator_daemon.write_claim_event, единственная точка — process_new),
devbot читает журнал с байтового оффсета и выносит карточку.

ХВОСТ 2 — обрезка result. Карточка несла «РЕЗУЛЬТАТ ОБРЕЗАН» и потолок 4500, но полной длины
в ней не было: демон резал result [:RESULT_MAX] ДО записи в очередь и длину не сохранял
(в 8ed16b0 это записано в остаток дословно). Теперь orchestrator_daemon.cap_result дописывает
длину ДО обрезки в сам текст, devbot её показывает и своей «взять неоткуда» не добавляет.

Что доказывает файл:
  1) задача, прожившая мгновение и НИКОГДА не бывшая в снимке, получает ОБЕ карточки;
  2) событие + снимок одной задачи → карточка «в работе» РОВНО одна (общий дедуп);
  3) порядок в теме хронологический: «в работе» раньше «done»;
  4) журнала нет / битая строка / недописанный хвост / ротация → без регресса и без потерь;
  5) seed-on-start историю взятий не выносит;
  6) write_claim_event зовётся из ОДНОГО места (synthetic-карточки демона не анонсируются)
     и под тестом в боевой журнал не пишет;
  7) cap_result: короткое — байт-в-байт, длинное — ≤ RESULT_MAX и с ПОЛНОЙ длиной в пометке;
  8) карточка devbot несёт это число; запись без пометки (ПК-агент / демон до 28.07) —
     прежний фоллбэк.

Сеть, Telegram и время замоканы; Bridge фейковый; боевой журнал взятий не трогается."""
import asyncio, os, sys, time, json, datetime

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
# Жёсткая изоляция от боевого .env (урок test_curator: headless-тест наследует env демона).
os.environ["CURATOR"] = "0"
os.environ["INBOX_TOPIC_ID"] = "0"
os.environ["PLAN_ADAPT"] = "0"
os.environ["STEP_SELFHEAL"] = "0"
os.environ["TASK_TIMEOUT"] = "600"
os.environ["TASK_TIMEOUT_DEV"] = "2700"
os.environ["PC_STEP_TIMEOUT"] = "3600"

import devbot as DB
import orchestrator_daemon as OD

_res = []


def ok(cond, label):
    _res.append(bool(cond))
    print(("  PASS " if cond else "  FAIL ") + label)
    return cond


# ── инфраструктура ───────────────────────────────────────────────────────────
SENDS = []          # (topic, text) в порядке отправки
JOURNAL = f"/tmp/claim_events_test_{os.getpid()}.jsonl"


class FakeBot:
    class _M:
        message_id = 4242

    async def send_message(self, chat_id, message_thread_id=None, text="", **kw):
        SENDS.append((message_thread_id, text))
        return FakeBot._M()


class Ctx:
    bot = FakeBot()


class FakeBridge:
    def __init__(s, snapshot):
        s.snapshot = snapshot

    def get_pending(s, status="new", lane=None):
        return {"ok": True, "items": [dict(i) for i in s.snapshot.get(status, [])]}


def iso(ts):
    """epoch-секунды → ISO в формате очереди Bridge ('2026-07-28T10:18:55.172Z')."""
    return (datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
            .isoformat().replace("+00:00", "Z"))


NOW = time.time()
START = NOW - 300           # процесс bot.py стартовал 5 минут назад


def item(id, created_ts, updated_ts=None, st="done", frm=None, result="итог",
         text="тз: почини X"):
    return {"id": id, "created": iso(created_ts),
            "updated": iso(updated_ts if updated_ts is not None else created_ts),
            "status": st, "from": frm or DB.QUEUE_FROM_DEV, "lane": "vps",
            "result": result, "task_text": text}


def reset(snapshot, seeded=True, journal=""):
    """Чистое состояние процесса + журнал взятий с заданным содержимым ('' = файла нет)."""
    SENDS.clear()
    DB._reported.clear(); DB._asked.clear()
    DB._inprogress_seen.clear(); DB._stalled.clear()
    DB._curator_pending.clear()
    DB._report_seeded = seeded
    DB._PROC_START_TS = START
    DB._claims_offset = 0
    DB.CLAIM_LOG_PATH = JOURNAL
    DB.BRIDGE = FakeBridge(snapshot)
    DB._poll_bridge = None
    if journal is None:
        if os.path.exists(JOURNAL):
            os.remove(JOURNAL)
    else:
        with open(JOURNAL, "w", encoding="utf-8") as f:
            f.write(journal)


def claim_line(it):
    """Строка журнала ровно в том виде, в каком её пишет демон (через боевую функцию)."""
    OD.write_claim_event(it, path=JOURNAL)
    with open(JOURNAL, encoding="utf-8") as f:
        return f.readlines()[-1]


def tick():
    asyncio.run(DB.report_results(Ctx()))


def texts(needle=""):
    return [t for _, t in SENDS if needle in t]


# ── 1. РЕГРЕСС ХВОСТА 1: задача прожила мгновение — приходят ОБЕ карточки ─────
print("1. Задача жила 6 секунд, в снимок in_progress НЕ попала — обе карточки:")
fast = item(14, NOW - 60, NOW - 54, st="done", result="проба видимости ok\n\nFACT: read-only")
reset({"done": [fast]}, journal=None)
line = claim_line(fast)                      # демон записал факт взятия
DB._claims_offset = 0
tick()
work = texts("в работе")
fin = texts("— done")
ok(len(work) == 1, f"карточка «в работе» пришла (до фикса — 0): {len(work)}")
ok("Задача 14" in work[0] if work else False, f"это карточка нужной задачи: {work}")
ok(len(fin) == 1, f"карточка завершения пришла: {len(fin)}")

print("2. Порядок в теме хронологический — «в работе» раньше завершения:")
order = [t for _, t in SENDS]
ok(order and "в работе" in order[0] and "— done" in order[1],
   f"сначала взятие, потом итог: {[t[:24] for t in order]}")

print("3. Повторный тик — тишина (оффсет журнала не отматывается):")
SENDS.clear()
tick()
ok(SENDS == [], f"дублей нет: {SENDS}")

# ── 4. Дедуп с СНИМКОМ: длинная задача не получает двух анонсов ──────────────
print("4. Задача есть И в журнале, И в снимке in_progress → анонс РОВНО один:")
long_it = item(20, NOW - 100, NOW - 5, st="in_progress", result="")
reset({"in_progress": [long_it]}, journal=None)
claim_line(long_it)
DB._claims_offset = 0
tick()
ok(len(texts("в работе")) == 1, f"один анонс на задачу: {texts('в работе')}")
SENDS.clear()
tick()
ok(texts("в работе") == [], f"на следующем тике снимок не дублирует: {SENDS}")

print("5. Обратный порядок (снимок первым, журнал дочитан позже) — тоже один:")
reset({"in_progress": [long_it]}, journal=None)
tick()                                        # анонс из снимка
n_after_snapshot = len(texts("в работе"))
claim_line(long_it)                           # событие приезжает позже
SENDS.clear()
tick()
ok(n_after_snapshot == 1 and texts("в работе") == [],
   f"событие после снимка не плодит карточку: было {n_after_snapshot}, стало {texts('в работе')}")

# ── 6. Отсутствие журнала = прежнее поведение ────────────────────────────────
print("6. Журнала нет вовсе (демон старый / не запускался) — работает как раньше:")
reset({"in_progress": [long_it]}, journal=None)
ok(DB._drain_claim_events() == [], "чтение отсутствующего журнала — пусто, без исключения")
tick()
ok(len(texts("в работе")) == 1, f"анонс идёт из снимка, регресса нет: {texts('в работе')}")

# ── 7. Устойчивость журнала ──────────────────────────────────────────────────
print("7. Битая строка, недописанный хвост, чужой источник:")
good = claim_line(item(31, NOW - 30, NOW - 30))
reset({}, journal="{это не json}\n" + good + '{"id": 32, "from": "pc_agent-205"}\n')
evs = DB._drain_claim_events()
ok([e.get("id") for e in evs] == [31], f"битая строка пропущена, чужой from отфильтрован: {evs}")

reset({}, journal=good.rstrip("\n"))          # хвост без \n = строка ещё дописывается
ok(DB._drain_claim_events() == [], "недописанная строка не читается (торн-райт)")
with open(JOURNAL, "a", encoding="utf-8") as f:
    f.write("\n")
ok([e.get("id") for e in DB._drain_claim_events()] == [31], "дописанная строка приходит следом")

print("8. Ротация журнала демоном (файл ужался) — читаем с начала, дублей нет:")
reset({}, journal=None)
for i in (41, 42):
    claim_line(item(i, NOW - 20, NOW - 20))
tail = claim_line(item(43, NOW - 20, NOW - 20))
ok([e.get("id") for e in DB._drain_claim_events()] == [41, 42, 43], "до ротации читаются все три")
with open(JOURNAL, "w", encoding="utf-8") as f:   # демон подрезал журнал под потолок
    f.write(tail)
evs = DB._drain_claim_events()
ok([e.get("id") for e in evs] == [43],
   f"файл короче оффсета → перечитали с начала уцелевший хвост, не зависли: {evs}")
DB._mark_seen(DB._inprogress_seen, evs[0])
ok(DB._seen(DB._inprogress_seen, json.loads(tail)),
   "то же событие, прочитанное повторно, считается показанным — второй карточки не будет")

print("9. seed-on-start: историю взятий не выносим:")
hist = claim_line(item(51, START - 9000, START - 9000))
reset({"done": [item(51, START - 9000, START - 9000)]}, seeded=False, journal=hist)
tick()
ok(SENDS == [], f"первый тик молчит по истории: {SENDS}")
SENDS.clear()
tick()
ok(SENDS == [], f"и на втором тике история взятий не всплывает: {SENDS}")

# ── 10. Писатель события ─────────────────────────────────────────────────────
print("10. write_claim_event: поля, fail-safe, гард боевого журнала:")
src = {"id": 77, "created": iso(NOW), "from": DB.QUEUE_FROM, "lane": "vps",
       "task_text": "задача: статус", "result": "", "status": "new"}
rec = json.loads(claim_line(src))
ok(rec["id"] == 77 and rec["created"] == src["created"] and rec["from"] == DB.QUEUE_FROM,
   f"событие несёт номер+генерацию+источник: {rec}")
ok(rec.get("updated") and DB._iso_ts(rec["updated"]) is not None,
   f"момент взятия читается devbot-парсером времени: {rec.get('updated')}")
ok(DB._gen(rec) == DB._gen(src), "генерация события совпадает со строкой очереди (дедуп сойдётся)")
ok(OD.write_claim_event(src, path="/nope/нет/такого/пути.jsonl") is False,
   "нечитаемый путь → False, исключение наружу не летит (fail-safe)")
ok(OD.write_claim_event(src) is False and not os.path.exists(OD.CLAIM_LOG_PATH),
   "под тестом боевой журнал не трогается (класс METRICS-мусора 25.07)")

print("11. Точка записи одна — synthetic-карточки демона анонса не получают:")
with open("/root/turbobaby-manager-bot/orchestrator_daemon.py", encoding="utf-8") as f:
    src_code = f.read()
calls = src_code.count("write_claim_event(") - src_code.count("def write_claim_event(")
ok(calls == 1, f"вызов ровно один (иначе служебные карточки начнут анонсироваться): {calls}")
ok(src_code.index("write_claim_event(task)") > src_code.index("def process_new("),
   "и он внутри process_new — там, где берут задачу владельца")

# ── 12. ХВОСТ 2: cap_result ──────────────────────────────────────────────────
print("12. cap_result: короткое — байт-в-байт, длинное — с полной длиной и в потолке:")
short = "коротко\nс переводами\nстрок"
ok(OD.cap_result(short) == short, "текст короче потолка не меняется ни на байт")
edge = "я" * OD.RESULT_MAX
ok(OD.cap_result(edge) == edge, "ровно потолок — пометки нет")

huge_len = 40000
huge = "х" * huge_len
capped = OD.cap_result(huge)
ok(len(capped) <= OD.RESULT_MAX, f"итог укладывается в потолок: {len(capped)} ≤ {OD.RESULT_MAX}")
ok(str(huge_len) in capped, f"полная длина ({huge_len}) названа в тексте")
ok(capped.startswith("х" * 100), "голова отчёта сохранена (обрезан именно хвост)")
ok(DB._result_full_len(capped) == huge_len,
   f"devbot вычитывает полную длину: {DB._result_full_len(capped)}")

print("13. Границы: потолок не пробивается ни на одной длине:")
bad = [n for n in (OD.RESULT_MAX + 1, OD.RESULT_MAX + 2, 4600, 9999, 100000, 1000000)
       if len(OD.cap_result("y" * n)) > OD.RESULT_MAX]
ok(not bad, f"переполнений нет: {bad}")
parsed = [DB._result_full_len(OD.cap_result("y" * n)) == n
          for n in (OD.RESULT_MAX + 1, 4600, 9999, 100000, 1000000)]
ok(all(parsed), f"на каждой длине пометка машиночитаема: {parsed}")

print("14. Карточка devbot: полная длина видна, дублирующей пометки нет:")
reset({"done": [item(60, NOW - 40, NOW - 20, result=OD.cap_result(huge))]}, journal=None)
tick()
card = "".join(texts())
ok(str(huge_len) in card, f"число {huge_len} доехало в карточку")
ok("взять неоткуда" not in card, "старой формулировки «взять неоткуда» больше нет")
ok(card.count("ОБРЕЗАН") >= 1 and "РЕЗУЛЬТАТ ОБРЕЗАН: в очереди" not in card,
   "пометка одна — демонская, фоллбэк devbot не дублирует")

print("15. Регресс: запись БЕЗ пометки (ПК-агент / демон до 28.07) — прежний фоллбэк:")
legacy = "z" * OD.RESULT_MAX
body = DB._result_body({"result": legacy})
ok("РЕЗУЛЬТАТ ОБРЕЗАН: в очереди 4500 симв" in body,
   "старая запись по-прежнему получает честную пометку обрезки")
ok(DB._result_full_len(legacy) is None, "полной длины у неё нет — и мы её не выдумываем")
short_body = DB._result_body({"result": "обычный итог"})
ok(short_body == "обычный итог", "короткий result не обрастает пометками")

try:
    os.remove(JOURNAL)
except OSError:
    pass

fails = _res.count(False)
print(f"\nИТОГ: {'ВСЕ PASS' if fails == 0 else f'ЕСТЬ FAIL ({fails}/{len(_res)})'}")
sys.exit(0 if fails == 0 else 1)
