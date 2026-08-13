#!/usr/bin/env python3
"""СЛОЙ ОЖИДАНИЙ, первые два — регресс (07.08.2026).

Владелец назвал четыре проверки, и они здесь голденами на ЖИВЫХ форматах:
    зависшая цепочка при СВОБОДНОМ исполнителе  → заметка   (секция 2)
    та же цепочка при ЗАНЯТОМ исполнителе       → молчание  (секция 3)
    остановка оборота демона                    → заметка   (секция 6)
    нормальная работа                           → молчание  (секции 3, 6, 8)

Прочие секции держат границы, без которых эти четыре ничего не стоят:
(1) ГРАНИЦА УСТРОЙСТВОМ: решение доказанно без рук (инвариант ловит ВНЕСЁННОЕ нарушение,
    а не только молчит на чистом файле)
(2) О1 — порог 30 мин при свободном исполнителе
(3) О1 — занятый исполнитель: законная очередь, не поломка
(4) О1 — зеркало гварда последовательности: шаг ждёт сиблинга ЗАКОННО
(5) О1 — порог и откат (0 → ветка мертва ДО чтения фактов)
(6) О2 демон — оборот cycle()
(7) О2 демон — молчание там, где факта нет (пульса нет вовсе / экземпляр моложе порога)
(8) О2 splinter — тик devbot_report, два молчания: «лог растёт» ≠ «лог не растёт»
(9) ФОРМА заметки: без кнопок, без номера, без слова «да»; граница названа в самом тексте
(10) ПРАВИЛО ГОДНОСТИ 4.2: у «демон не даёт оборота» задачи не бывает НИКОГДА
(11) ЗАКРЫТИЕ эпизода объявляется, но только когда источник факта доступен
(12) ЖИВЫЕ ФОРМАТЫ: строка очереди и строка splinter.log сняты с прода дословно
(13) РУКИ: один эпизод — одно сообщение; потолок задач; сбой канала не «съедает» эпизод
(14) ЖИВОЙ ФАКТ: полный прогон на этой машине не сменил ни одного PID и ничего не отправил
"""
import json
import os
import shutil
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
# АДРЕС НАБЛЮДЕНИЯ ЗАФИКСИРОВАН НА ДО-13.08: секция (13) судит РУКИ и утверждает прежний
# договор «нарушение найдено → заметка владельцу немедленно». С 13.08 наблюдение уходит в мозг,
# а владельцу — только тяжёлое, пережившее отсрочку (свой регресс — tests/test_expect_journal.py).
# Форсируем, а не setdefault: headless-тест наследует env демона с боевыми флагами (класс CURATOR).
os.environ["EXPECT_TO_BRAIN"] = "0"
os.environ["ORCH_TEST_MODE"] = "1"
os.environ["PRETOOL_NOPUSH"] = "1"


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return bool(c)


res = []

try:
    import expectations as EX
except Exception as e:                                   # noqa: BLE001
    EX = None
    print("  (модуля expectations нет: %s)" % e)

# ЛОВУШКА МЕТОДА (поймана живьём 06.08): orchestrator_daemon держит REPO ЗАХАРДКОЖЕННЫМ и кладёт
# его ПЕРВЫМ в sys.path прямо при импорте. В прогоне «ДО правки» через git worktree всё, что
# импортируется ПОСЛЕ демона, приезжает из БОЕВОГО дерева — и модуль, которого в проверяемом
# дереве нет, «находится». Мало вернуть своё дерево в начало: ЧУЖОЙ корень надо УБРАТЬ.
_LIVE = "/root/turbobaby-manager-bot"
if os.path.abspath(REPO) != _LIVE:
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _LIVE]
    sys.modules.pop("expectations", None)
    try:
        import expectations as EX                        # noqa: F811
    except Exception:                                    # noqa: BLE001
        EX = None

NOW = 1_754_550_000.0            # фиксированное «сейчас»: тест не зависит от часов машины
MIN = 60.0
CFG = {"new": 30 * MIN, "turn": 10 * MIN, "tick": 10 * MIN, "hold": 60 * MIN}


# ЖИВОЙ ФОРМАТ СТРОКИ ОЧЕРЕДИ — снят с прода 07.08.2026 (get_pending, задача 386), не выдуман:
# {"id":386,"created":"2026-08-07T07:09:50.918Z","from":"Filipp-328-dev","task_text":"…",
#  "status":"in_progress","result":"","approved_by":"","updated":"2026-08-07T07:16:27.951Z",
#  "lane":"vps"}
def row(rid, status, age_min, lane="vps", frm="Filipp-328-dev", text="ultrathink\n\nЗАДАЧА: …",
        free=None):
    """free = ЧИСТОЕ ожидание при свободной полосе (мин). None → «полоса стояла всё это время»."""
    return {"id": rid, "status": status, "lane": lane, "from": frm,
            "since": NOW - age_min * MIN, "text": text,
            "free_wait": (age_min if free is None else free) * MIN}


def facts(rows=None, queue_ok=True, pulse_age=1.0, pulse=True, daemon_alive=True,
          tick_age=1.0, tick=True, log_age=None, splinter_alive=True, claims_age=5.0,
          daemon_age_min=600.0, splinter_age_min=600.0, busy=None):
    """Собрать факты в той же форме, в какой их отдаёт expectations_run.snapshot().

    busy — штамп занятости демона (см. orchestrator_daemon._expect_busy): либо готовый словарь,
    либо кортеж (возраст_штампа_мин, объявленный_таймаут_сек, id_задачи)."""
    d = {"pulse": None, "proc": None, "claims": None}
    if pulse:
        d["pulse"] = {"ts": NOW - pulse_age * MIN, "n": 42, "pid": 111,
                      "started": NOW - daemon_age_min * MIN}
        if busy is not None:
            if isinstance(busy, (tuple, list)) and len(busy) == 3:
                b_age, b_limit, b_task = busy
                d["pulse"]["busy"] = {"since": NOW - b_age * MIN, "limit": b_limit,
                                      "task": b_task, "pid": 111}
            else:
                d["pulse"]["busy"] = busy      # словарь как есть / заведомый мусор — проверка формы
    if daemon_alive:
        d["proc"] = {"pid": 111, "started": NOW - daemon_age_min * MIN}
    if claims_age is not None:
        d["claims"] = NOW - claims_age * MIN
    s = {"tick": (NOW - tick_age * MIN) if tick else None,
         "log": (NOW - (log_age if log_age is not None else tick_age) * MIN) if tick else None,
         "proc": {"pid": 222, "started": NOW - splinter_age_min * MIN} if splinter_alive else None}
    return {"now": NOW, "queue": {"ok": queue_ok, "rows": list(rows or [])},
            "daemon": d, "splinter": s}


def kinds(vs):
    return sorted(str(v.get("kind")) for v in (vs or []))


# ═══════════ (1) ГРАНИЦА УСТРОЙСТВОМ: решение доказанно без рук ════════════════════════════
print("\n(1) ГРАНИЦА: слой ожиданий не умеет ни писать, ни отправлять, ни перезапускать")
try:
    import invariants_check as IC
except Exception as e:                                   # noqa: BLE001
    IC = None
    print("  (invariants_check не импортируется: %s)" % e)

if IC is not None and hasattr(IC, "check_expectations_pure"):
    r = IC.CheckRun("EXPECTATIONS_PURE")
    IC.check_expectations_pure(None, r)
    res.append(ok(not r.findings, "(1) боевой expectations.py чист: %s" % (r.findings or "0 флагов")))

    # ГЛАВНОЕ: инвариант обязан ЛОВИТЬ внесённое нарушение, а не только молчать на чистом файле.
    _tmp = tempfile.mkdtemp(prefix="expect_pure_")
    cases = [
        ("импорт рук (os)", "import os\nX = os.getcwd()\n"),
        ("канал (notify)", "import notify\ndef f():\n    return notify.send_feed('x')\n"),
        ("запись (open)", "def f():\n    return open('/tmp/x', 'w')\n"),
        ("мост", "import bridge_client\ndef f():\n    return bridge_client.BridgeClient()\n"),
        ("слово рестарта в коде", "CMD = 'systemctl restart splinter'\n"),
        ("исполнение (eval)", "def f(s):\n    return eval(s)\n"),
    ]
    caught = 0
    for title, src in cases:
        p = os.path.join(_tmp, "m_%d.py" % len(title))
        with open(p, "w", encoding="utf-8") as f:
            f.write(src)
        IC._EXPECT_PATH = p
        rr = IC.CheckRun("EXPECTATIONS_PURE")
        IC.check_expectations_pure(None, rr)
        good = bool(rr.findings)
        caught += 1 if good else 0
        res.append(ok(good, "(1) инвариант ловит: %s" % title))
    # Докстринг ОБЯЗАН уметь назвать то, чего модуль не делает — иначе честное объяснение
    # границы стало бы нарушением границы (то же решение, что у PROD_DRIFT_READONLY).
    p = os.path.join(_tmp, "doc.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write('"""Юнит берём не из вывода systemctl, и restart мы не делаем."""\nX = 1\n')
    IC._EXPECT_PATH = p
    rr = IC.CheckRun("EXPECTATIONS_PURE")
    IC.check_expectations_pure(None, rr)
    res.append(ok(not rr.findings, "(1) докстринг вправе НАЗВАТЬ то, чего модуль не делает"))
    IC._EXPECT_PATH = None
    shutil.rmtree(_tmp, ignore_errors=True)
else:
    res.append(ok(False, "(1) инвариант EXPECTATIONS_PURE зарегистрирован"))

# ═══════════ (2) О1 — ЗАВИСШАЯ ЦЕПОЧКА ПРИ СВОБОДНОМ ИСПОЛНИТЕЛЕ → ЗАМЕТКА ═════════════════
print("\n(2) О1: строка стоит в new дольше порога, исполнитель свободен")
if EX:
    v = EX.verdict(facts(rows=[row(390, "new", 47)]), CFG)
    res.append(ok(kinds(v) == ["o1_new_vps"], "(2) 47 мин при свободном исполнителе → заметка"))
    res.append(ok(len(v) == 1 and v[0]["id"] == 390 and int(v[0]["age"]) == int(47 * MIN),
                  "(2) в вердикте названы номер строки и возраст ожидания"))
    txt = EX.render(v[0]) if v else ""
    res.append(ok("390" in txt and "ждёт в new" in txt and "при СВОБОДНОЙ полосе" in txt,
                  "(2) заметка называет строку, ожидание и условие: %s" % txt[:110]))
    # соседняя строка на полосе pc в О1-vps не попадает (её двигает другой исполнитель)
    v2 = EX.verdict(facts(rows=[row(391, "new", 99, lane="pc", frm="Filipp-pc-dev")]), CFG)
    res.append(ok(v2 == [], "(2) строка полосы pc в О1-vps не попадает"))
else:
    res += [ok(False, "(2) О1 при свободном исполнителе")] * 4

# ═══════════ (3) О1 — ЗАНЯТЫЙ ИСПОЛНИТЕЛЬ: ЗАКОННАЯ ОЧЕРЕДЬ, МОЛЧАНИЕ ══════════════════════
print("\n(3) О1: та же строка при ЗАНЯТОМ исполнителе (полоса одно-воркерная)")
if EX:
    busy = facts(rows=[row(390, "new", 47), row(386, "in_progress", 20)])
    res.append(ok(EX.verdict(busy, CFG) == [],
                  "(3) занят → молчание (это очередь, а не поломка)"))
    # ЗАМЕР, ради которого условие и введено: без него та же картина дала бы 3.43 ложных в сутки
    long_wait = facts(rows=[row(392, "new", 121), row(386, "in_progress", 100)])
    res.append(ok(EX.verdict(long_wait, CFG) == [],
                  "(3) ожидание 121 мин за занятым исполнителем — молчание"))
    res.append(ok(EX.verdict(facts(rows=[row(390, "new", 5)]), CFG) == [],
                  "(3) НОРМАЛЬНАЯ РАБОТА (5 мин, свободен) → молчание"))
    res.append(ok(EX.verdict(facts(rows=[]), CFG) == [], "(3) пустая очередь → молчание"))

    # ГОЛДЕН ЖИВОГО СЛУЧАЯ (реплей 7 суток, задача 330 куратора, 05.08): общий возраст в new
    # 69 минут, из них при СВОБОДНОЙ полосе ровно 15 — остальное она законно стояла за
    # исполнявшимися 327 и 328. Мгновенный снимок ловил её в щель МЕЖДУ задачами и давал
    # ложную заметку (17 таких за неделю). Порог берётся по ЧИСТОМУ ожиданию → молчание.
    gap = facts(rows=[row(330, "new", 69, frm="Filipp-curator", free=15)])
    res.append(ok(EX.verdict(gap, CFG) == [],
                  "(3) ЖИВОЙ 330: 69 мин в new, но лишь 15 при свободной полосе → молчание"))
    # а вот вставшая полоса копит чистое ожидание каждым наблюдением и порог берёт
    stuck = facts(rows=[row(330, "new", 69, frm="Filipp-curator", free=35)])
    res.append(ok(len(EX.verdict(stuck, CFG)) == 1,
                  "(3) та же строка при 35 мин ЧИСТОГО ожидания → заметка"))
else:
    res += [ok(False, "(3) О1 при занятом исполнителе")] * 6

# ═══════════ (4) О1 — ЗЕРКАЛО ГВАРДА ПОСЛЕДОВАТЕЛЬНОСТИ ════════════════════════════════════
print("\n(4) О1: шаг цепочки ждёт сиблинга ЗАКОННО (демон его не берёт намеренно)")
if EX:
    step = row(400, "new", 200, frm="Filipp-328-dec", text="[шаг 3/5 родитель 380] сделай Y")
    sib_na = row(399, "needs_approval", 300, frm="Filipp-328-dec",
                 text="[шаг 2/5 родитель 380] сделай X")
    res.append(ok(EX.verdict(facts(rows=[step, sib_na]), CFG) == [],
                  "(4) сиблинг в needs_approval (ждёт владельца) → молчание, хоть 200 мин"))
    parent = {"id": 380, "status": "needs_approval", "lane": "vps", "from": "Filipp-328-dec",
              "since": NOW - 300 * MIN, "text": "декомпозируй: большое ТЗ"}
    res.append(ok(EX.verdict(facts(rows=[step, parent]), CFG) == [],
                  "(4) открыт сам родитель цепочки → молчание"))
    earlier = row(401, "new", 150, frm="Filipp-328-dec",
                  text="[шаг 2/5 родитель 380] сделай X")
    res.append(ok(kinds(EX.verdict(facts(rows=[step, earlier]), CFG)) == ["o1_new_vps"],
                  "(4) впереди шаг с МЕНЬШИМ номером → о нём и говорим (о старшем молчим)"))
    other = row(402, "new", 200, frm="Filipp-328-dec", text="[шаг 1/2 родитель 999] чужая цепь")
    res.append(ok(len(EX.verdict(facts(rows=[step, sib_na, other]), CFG)) == 1,
                  "(4) чужая цепочка чужим сиблингом не оправдана"))
else:
    res += [ok(False, "(4) гвард последовательности")] * 4

# ═══════════ (5) О1 — ПОРОГ И ОТКАТ ════════════════════════════════════════════════════════
print("\n(5) О1: порог 30 мин и откат нулём")
if EX:
    res.append(ok(EX.verdict(facts(rows=[row(390, "new", 29)]), CFG) == [], "(5) 29 мин → молчит"))
    res.append(ok(len(EX.verdict(facts(rows=[row(390, "new", 31)]), CFG)) == 1, "(5) 31 мин → говорит"))
    res.append(ok(EX.verdict(facts(rows=[row(390, "new", 999, free=0)]), CFG) == [],
                  "(5) факта чистого ожидания нет (0) → молчим, хоть возраст 999 мин"))
    dead = dict(CFG, new=0.0)
    res.append(ok(EX.verdict(facts(rows=[row(390, "new", 999)]), dead) == [],
                  "(5) порог 0 → ветка мертва ДО чтения фактов (откат)"))
    res.append(ok(EX.limit_env("EXPECT_NEW_MIN", 30, {"EXPECT_NEW_MIN": "0"}) == 0.0,
                  "(5) EXPECT_NEW_MIN=0 читается как ноль, а не как дефолт"))
    res.append(ok(EX.limit_env("EXPECT_NEW_MIN", 30, {"EXPECT_NEW_MIN": "мусор"}) == 30 * MIN,
                  "(5) мусор в пороге → дефолт (кривой .env не ломает слой)"))
    res.append(ok(EX.verdict(facts(rows=[row(390, "new", 47)], queue_ok=False), CFG) == [],
                  "(5) снимка очереди нет (мост молчит) → молчим, а не догадываемся"))
else:
    res += [ok(False, "(5) порог/откат")] * 7

# ═══════════ (6) О2 ДЕМОН — ОБОРОТ cycle() ═════════════════════════════════════════════════
print("\n(6) О2: демон произвёл оборот, а не просто существует")
if EX:
    v = EX.verdict(facts(pulse_age=23), CFG)
    res.append(ok(kinds(v) == ["o2_daemon"], "(6) оборота нет 23 мин → заметка"))
    res.append(ok(EX.verdict(facts(pulse_age=1), CFG) == [],
                  "(6) НОРМАЛЬНАЯ РАБОТА (оборот 1 мин назад) → молчание"))
    res.append(ok(EX.verdict(facts(pulse_age=9.5), CFG) == [], "(6) 9.5 мин → ещё молчим"))
    v2 = EX.verdict(facts(pulse_age=40, daemon_alive=False), CFG)
    res.append(ok(len(v2) == 1 and v2[0].get("alive") is False,
                  "(6) пульс протух и процесса нет вовсе → заметка это различает"))
    t = EX.render(v[0]) if v else ""
    res.append(ok("оборот" in t and "cycle()" in t, "(6) заметка называет продукт: %s" % t[:80]))
    dead = dict(CFG, turn=0.0)
    res.append(ok(EX.verdict(facts(pulse_age=999), dead) == [], "(6) порог 0 → ветка мертва"))
else:
    res += [ok(False, "(6) О2 демон")] * 6

# ═══════════ (7) О2 ДЕМОН — МОЛЧАНИЕ ТАМ, ГДЕ ФАКТА НЕТ ════════════════════════════════════
print("\n(7) О2: нет факта → нет вердикта (fail-safe в сторону молчания)")
if EX:
    res.append(ok(EX.verdict(facts(pulse=False), CFG) == [],
                  "(7) пульса нет ВООБЩЕ → молчим: «старый код» и «мёртв» отсюда неотличимы"))
    res.append(ok(EX.verdict(facts(pulse_age=30, daemon_age_min=3), CFG) == [],
                  "(7) экземпляр моложе порога (3 мин) → отчитаться не успел, молчим"))
    res.append(ok(EX.verdict({"now": 0, "queue": {"ok": True, "rows": []}}, CFG) == [],
                  "(7) времени нет → молчим"))
    res.append(ok(EX.verdict("мусор", CFG) == [] and EX.verdict(None, CFG) == [],
                  "(7) мусор вместо фактов → молчим"))
    bad = facts(rows=[{"id": 1, "status": "new", "lane": "vps", "since": "не число"}])
    res.append(ok(EX.verdict(bad, CFG) == [], "(7) кривая строка очереди не роняет вердикт"))
else:
    res += [ok(False, "(7) fail-safe")] * 5

# ═══════════ (8) О2 SPLINTER — ТИК И ДВА РАЗНЫХ МОЛЧАНИЯ ═══════════════════════════════════
print("\n(8) О2: тик devbot_report; «лог растёт» ≠ «лог не растёт»")
if EX:
    v = EX.verdict(facts(tick_age=18, log_age=0.1), CFG)
    res.append(ok(kinds(v) == ["o2_splinter"], "(8) тика нет 18 мин → заметка"))
    res.append(ok(v and v[0].get("growing") is True,
                  "(8) лог растёт, тиков нет → «встал планировщик»"))
    res.append(ok("планировщик" in EX.render(v[0]), "(8) заметка называет этот диагноз"))
    v2 = EX.verdict(facts(tick_age=18, log_age=18), CFG)
    res.append(ok(v2 and v2[0].get("growing") is False and "молчит весь процесс" in EX.render(v2[0]),
                  "(8) лог не растёт вовсе → «молчит весь процесс»"))
    res.append(ok(EX.verdict(facts(tick_age=1), CFG) == [],
                  "(8) НОРМАЛЬНАЯ РАБОТА (тик 1 мин назад) → молчание"))
    res.append(ok(EX.verdict(facts(tick=False), CFG) == [],
                  "(8) тика в хвосте нет вовсе (подняли уровень лога) → молчим, а не хороним"))
    res.append(ok(EX.verdict(facts(tick_age=30, splinter_age_min=2), CFG) == [],
                  "(8) splinter поднялся 2 мин назад → продукта ещё не ждём"))
else:
    res += [ok(False, "(8) О2 splinter")] * 7

# ═══════════ (9) ФОРМА ЗАМЕТКИ ═════════════════════════════════════════════════════════════
print("\n(9) Заметка ленты: без кнопок, без номера карточки, без слова «да»")
if EX:
    all_v = (EX.verdict(facts(rows=[row(390, "new", 47)]), CFG)
             + EX.verdict(facts(pulse_age=23), CFG)
             + EX.verdict(facts(tick_age=18, log_age=0.1), CFG))
    texts = [EX.render(v) for v in all_v]
    res.append(ok(len(texts) == 3, "(9) три класса заметок отрисованы"))
    res.append(ok(all(t.startswith("🔔") for t in texts), "(9) семейство ленты: первый токен 🔔"))
    bad = [t for t in texts if "«да»" in t or "approve" in t.lower() or "NEEDS_APPROVAL" in t]
    res.append(ok(not bad, "(9) ни в одной заметке нет ни кнопки, ни «да»: %s" % (bad or "чисто")))
    res.append(ok(all(t.endswith(EX.TAIL) for t in texts),
                  "(9) каждая заметка кончается границей владельца: «%s»" % EX.TAIL))
    res.append(ok(all("\n" not in t for t in texts), "(9) одна строка на заметку"))
else:
    res += [ok(False, "(9) форма заметки")] * 5

# ═══════════ (10) ПРАВИЛО ГОДНОСТИ 4.2 ═════════════════════════════════════════════════════
print("\n(10) Задача законна, только если её исполнитель доказанно жив")
if EX:
    v = EX.verdict(facts(pulse_age=23), CFG)
    res.append(ok(v and v[0]["can_task"] is False,
                  "(10) «демон не даёт оборота» → задачи НЕ бывает (исполнитель и есть предмет)"))
    res.append(ok(EX.task_text(v[0]) == "" if v else False,
                  "(10) текста задачи для него нет вовсе"))
    # О1: демон даёт оборот И берёт другие строки (журнал претензий моложе начала ожидания)
    good = EX.verdict(facts(rows=[row(390, "new", 47)], pulse_age=1, claims_age=5), CFG)
    res.append(ok(good and good[0]["can_task"] is True,
                  "(10) О1: оборот есть и другие строки берутся → задача законна"))
    stale = EX.verdict(facts(rows=[row(390, "new", 47)], pulse_age=1, claims_age=90), CFG)
    res.append(ok(stale and stale[0]["can_task"] is False,
                  "(10) О1: демон давно ничего не брал → задача ляжет в ту же очередь, не ставим"))
    nopulse = EX.verdict(facts(rows=[row(390, "new", 47)], pulse=False), CFG)
    res.append(ok(nopulse and nopulse[0]["can_task"] is False,
                  "(10) оборот не доказан → права на задачу нет по умолчанию"))
    tt = EX.task_text(good[0]) if good else ""
    res.append(ok("READ-ONLY" in tt and "НЕ перезапускать" in tt and "НЕ править" in tt,
                  "(10) ТЗ задачи несёт границу владельца в себе"))
    res.append(ok("systemctl" not in tt and "systemd-run" not in tt,
                  "(10) в ТЗ нет ни одной команды перезапуска даже цитатой"))
else:
    res += [ok(False, "(10) правило 4.2")] * 7

# ═══════════ (11) ЗАКРЫТИЕ ЭПИЗОДА ═════════════════════════════════════════════════════════
print("\n(11) Закрытие объявляется — но только когда источник факта доступен")
if EX:
    keys = ["o1|390|1", "o2d|1|2", "o2s|3"]
    good = EX.closures(facts(pulse_age=1, tick_age=1), CFG, keys)
    res.append(ok(sorted(good) == sorted(keys), "(11) всё выздоровело → закрываем все три"))
    blind = EX.closures(facts(queue_ok=False, pulse=False, tick=False), CFG, keys)
    res.append(ok(blind == [], "(11) источники молчат → НЕ закрываем (молчание ≠ выздоровление)"))
    still = EX.closures(facts(pulse_age=23, tick_age=1), CFG, ["o2d|%d|%d" % (
        int(NOW - 600 * MIN), int(NOW - 23 * MIN))])
    res.append(ok(still == [], "(11) нарушение продолжается → закрывать нечего"))
    res.append(ok("снова" in EX.render_close("o2d|1|2"), "(11) текст закрытия говорит о возврате"))
else:
    res += [ok(False, "(11) закрытие")] * 4

# ═══════════ (12) ЖИВЫЕ ФОРМАТЫ ════════════════════════════════════════════════════════════
print("\n(12) Разбор снят с прода дословно, а не идеализирован")
if EX:
    # дословная строка очереди (снимок 07.08.2026, задача 386)
    t = EX.parse_iso("2026-08-07T07:09:50.918Z")
    res.append(ok(t is not None and abs(t - 1786086590.918) < 0.01,
                  "(12) ISO очереди с «T», долями и «Z» разобран как UTC: %s" % t))
    res.append(ok(EX.parse_iso("") is None and EX.parse_iso("не дата") is None,
                  "(12) пустое/мусор → None (молчим)"))
    # ГОЛДЕН КЛАССА 17.07: строка БЕЗ зоны обязана дать РОВНО то же число, что с «Z». Разойдись
    # они — машина (Бангкок, UTC+7) сдвинула бы возраст ожидания на семь часов, и порог 30 минут
    # стал бы фикцией в обе стороны.
    naive, zulu = EX.parse_iso("2026-08-07 07:09:50"), EX.parse_iso("2026-08-07T07:09:50Z")
    res.append(ok(naive is not None and naive == zulu,
                  "(12) без зоны читается как UTC, а не как Бангкок: %s == %s" % (naive, zulu)))
    # дословные строки splinter.log (снимок 07.08.2026)
    tail = (
        '2026-08-07 07:11:37,399 [INFO] apscheduler.executors.default: Job "devbot_report '
        '(trigger: interval[0:00:45], next run at: 2026-08-07 07:12:19 UTC)" executed successfully\n'
        '2026-08-07 07:12:19,321 [INFO] apscheduler.executors.default: Running job "devbot_report '
        '(trigger: interval[0:00:45], next run at: 2026-08-07 07:13:04 UTC)" (scheduled at '
        '2026-08-07 07:12:19.311034+00:00)\n'
        '2026-08-07 07:13:00,001 [INFO] splinter: что-то другое, не тик\n'
    )
    tf = EX.tick_facts(tail)
    res.append(ok(tf["tick"] is not None and tf["log"] is not None and tf["log"] > tf["tick"],
                  "(12) тик и «жив ли лог» — РАЗНЫЕ факты из одного хвоста"))
    res.append(ok(EX.tick_facts("")["tick"] is None and EX.tick_facts("мусор")["tick"] is None,
                  "(12) пустой/битый хвост → фактов нет"))
    res.append(ok(EX.tick_facts(tail.replace("devbot_report", "другой_джоб"))["tick"] is None,
                  "(12) чужой джоб тиком не считается"))
else:
    res += [ok(False, "(12) живые форматы")] * 6

# ═══════════ (13) РУКИ: ОДИН ЭПИЗОД — ОДНО СООБЩЕНИЕ ═══════════════════════════════════════
print("\n(13) Руки яруса 2: дедуп эпизода, потолок задач, сбой канала")
try:
    import expectations_run as ER
except Exception as e:                                   # noqa: BLE001
    ER = None
    print("  (модуля expectations_run нет: %s)" % e)

if ER and EX:
    # ── СЧЁТЧИК ЧИСТОГО ОЖИДАНИЯ (сердце О1: копится по одному наблюдению за прогон) ────────
    # ЖДУЩАЯ СТРОКА — ОДНА И ТА ЖЕ: `since` у неё не меняется (это момент попадания в new),
    # меняется только «сейчас». Ключ счётчика ключуется именно since — иначе каждое наблюдение
    # заводило бы новый счётчик и порог не брался бы никогда.
    stt = {}
    waiting = row(390, "new", 5, free=0)
    f_free = facts(rows=[waiting])
    ER.update_waits(stt, f_free, NOW)
    res.append(ok(waiting["free_wait"] == 0.0,
                  "(13) первое наблюдение строки не добавляет ничего (не с чем сравнивать)"))
    # Дальше каждое наблюдение добавляет свой период: после N наблюдений накоплено (N−1)×10 мин.
    for i in range(1, 4):
        ER.update_waits(stt, facts(rows=[waiting]), NOW + i * 600)
    res.append(ok(abs(waiting["free_wait"] - 1800.0) < 1 and
                  EX.verdict(facts(rows=[waiting]), CFG) == [],
                  "(13) 3 интервала = ровно порог (30 мин) → ещё молчим: %.0f с"
                  % waiting["free_wait"]))
    ER.update_waits(stt, facts(rows=[waiting]), NOW + 4 * 600)
    res.append(ok(abs(waiting["free_wait"] - 2400.0) < 1 and
                  len(EX.verdict(facts(rows=[waiting]), CFG)) == 1,
                  "(13) 4 интервала (40 мин) → заметка; вставшая полоса ловится на ~4-м прогоне"))

    stb = {}
    busy_row = row(390, "new", 5, free=0)
    for i in range(6):                        # та же длительность, но полоса ЗАНЯТА
        ER.update_waits(stb, facts(rows=[busy_row, row(386, "in_progress", 60)]), NOW + i * 600)
    res.append(ok(busy_row["free_wait"] == 0.0,
                  "(13) полоса занята → счётчик не растёт вовсе"))

    stc = {}
    late = row(390, "new", 5, free=0)
    ER.update_waits(stc, facts(rows=[late]), NOW)
    ER.update_waits(stc, facts(rows=[late]), NOW + 4 * 3600)   # таймер молчал 4 часа
    res.append(ok(late["free_wait"] == ER.WAIT_STEP_CAP,
                  "(13) таймер молчал 4 ч → засчитан ОДИН период (%.0f с), а не 4 часа выдумки"
                  % ER.WAIT_STEP_CAP))

    std = {"waits": {"390|1": {"free": 999.0, "seen": NOW}}}
    ER.update_waits(std, facts(rows=[row(390, "new", 47)], queue_ok=False), NOW + 600)
    res.append(ok(std["waits"] == {"390|1": {"free": 999.0, "seen": NOW}},
                  "(13) снимка нет → счётчики не тронуты (молчание моста ≠ простой полосы)"))

    tmp = tempfile.mkdtemp(prefix="expect_run_")
    os.environ["CC_EXPECT_DIR"] = tmp
    sent, tasks = [], []
    _snap, _note, _enq, _proof = ER.snapshot, ER.send_note, ER.enqueue_escalation, ER.write_proof
    _upd = ER.update_waits
    try:
        # Счётчик чистого ожидания проверен ВЫШЕ отдельно; здесь предмет — машинерия эпизода
        # (одно сообщение, эскалация, потолок, закрытие), поэтому счётчик не пересчитываем и
        # берём free_wait прямо из фикстуры.
        ER.update_waits = lambda st, f, now: None
        state = {"f": facts(rows=[row(390, "new", 47)], pulse_age=1, claims_age=5)}
        # Подпись повторяет ЖИВУЮ (10.08: снимку передаются состояние и пороги — у моста и ПК
        # факт составной). Заглушка обязана принимать то же, что боевой вызов, иначе она молча
        # разойдётся с кодом и тест начнёт проверять несуществующую форму.
        ER.snapshot = lambda now=None, st=None, cfg=None: state["f"]
        ER.send_note = lambda t: (sent.append(t), True)[1]
        ER.enqueue_escalation = lambda v: (tasks.append(v.get("key")), 700 + len(tasks))[1]
        ER.write_proof = lambda v, f, n: "/dev/null"      # ФС в тесте не трогаем

        out1 = ER.run(now=NOW)
        res.append(ok(len(out1["notes"]) == 1 and len(sent) == 1,
                      "(13) первое обнаружение → РОВНО одна заметка"))
        out2 = ER.run(now=NOW + 60)
        res.append(ok(out2["notes"] == [] and len(sent) == 1,
                      "(13) второй прогон того же эпизода → НИ ОДНОГО повтора"))
        # «нарушение держится» → задача, но ровно одна
        out3 = ER.run(now=NOW + 61 * MIN)
        res.append(ok(len(out3["tasks"]) == 1 and len(tasks) == 1,
                      "(13) держится дольше hold → одна задача-эскалация"))
        out4 = ER.run(now=NOW + 120 * MIN)
        res.append(ok(out4["tasks"] == [] and len(tasks) == 1,
                      "(13) второй задачи по тому же эпизоду не бывает"))
        # закрытие: строка ушла из new
        state["f"] = facts(rows=[], pulse_age=1)
        out5 = ER.run(now=NOW + 130 * MIN)
        res.append(ok(len(out5["closed"]) == 1 and "снова" in sent[-1],
                      "(13) эпизод закрылся → сказано отдельной заметкой"))
        out6 = ER.run(now=NOW + 140 * MIN)
        res.append(ok(out6["closed"] == [], "(13) закрытие объявляется один раз"))

        # СБОЙ КАНАЛА не «съедает» эпизод: не сказали — не пометили
        shutil.rmtree(tmp, ignore_errors=True)
        sent2 = []
        ER.send_note = lambda t: (sent2.append(t), False)[1]
        state["f"] = facts(rows=[row(391, "new", 47)], pulse_age=1)
        ER.run(now=NOW + 200 * MIN)
        ER.send_note = lambda t: (sent.append(t), True)[1]
        out7 = ER.run(now=NOW + 201 * MIN)
        res.append(ok(len(out7["notes"]) == 1,
                      "(13) заметка не ушла → эпизод НЕ помечен, скажем на следующем прогоне"))

        # ПОТОЛОК ЗАДАЧ В СУТКИ (страховка от петли)
        shutil.rmtree(tmp, ignore_errors=True)
        tasks2 = []
        ER.enqueue_escalation = lambda v: (tasks2.append(v.get("key")), 800 + len(tasks2))[1]
        base = NOW + 300 * MIN
        for i in range(5):
            state["f"] = facts(rows=[row(500 + i, "new", 200)], pulse_age=1, claims_age=5)
            ER.run(now=base + i * 61 * MIN)
            ER.run(now=base + i * 61 * MIN + 61 * MIN)
        res.append(ok(len(tasks2) <= ER.TASK_CAP_DAY,
                      "(13) потолок задач в сутки соблюдён: %d ≤ %d" % (len(tasks2), ER.TASK_CAP_DAY)))

        # dry-прогон не трогает ни канал, ни очередь
        shutil.rmtree(tmp, ignore_errors=True)
        n_before, t_before = len(sent), len(tasks2)
        state["f"] = facts(rows=[row(600, "new", 200)], pulse_age=1)
        outd = ER.run(dry=True, now=NOW + 500 * MIN)
        res.append(ok(outd["dry"] and len(sent) == n_before and len(tasks2) == t_before
                      and outd["notes"], "(13) --dry считает, но не отправляет и не ставит"))
    finally:
        ER.snapshot, ER.send_note = _snap, _note
        ER.enqueue_escalation, ER.write_proof = _enq, _proof
        ER.update_waits = _upd
        os.environ.pop("CC_EXPECT_DIR", None)
        shutil.rmtree(tmp, ignore_errors=True)
else:
    res += [ok(False, "(13) руки яруса 2")] * 15

# ═══════════ (14) ЖИВОЙ ФАКТ ═══════════════════════════════════════════════════════════════
print("\n(14) Живой прогон на этой машине: ни один PID не сменился, канал молчит")
if ER and EX:
    try:
        import prod_drift as PD
    except Exception:                                    # noqa: BLE001
        PD = None
    if PD:
        def live_pids():
            out = {}
            for unit, entry in PD.WATCHED:
                p = PD.live(unit, entry)
                if p:
                    out[unit] = p["pid"]
            return out

        before = live_pids()
        sent3 = []
        _note = ER.send_note
        _enq = ER.enqueue_escalation
        _q = ER.queue_facts
        try:
            ER.send_note = lambda t: (sent3.append(t), True)[1]
            ER.enqueue_escalation = lambda v: 0           # очередь в тесте не трогаем
            ER.queue_facts = lambda: {"ok": False, "rows": []}   # и мост тоже
            out = ER.run(dry=True)
            res.append(ok(isinstance(out, dict), "(14) полный прогон отработал: %s" % out))
        except Exception as e:                            # noqa: BLE001
            res.append(ok(False, "(14) полный прогон: %r" % e))
        finally:
            ER.send_note, ER.enqueue_escalation, ER.queue_facts = _note, _enq, _q
        after = live_pids()
        res.append(ok(before == after and bool(before),
                      "(14) PID живых процессов до и после совпали: %s" % (before or "нет процессов")))
        res.append(ok(sent3 == [], "(14) в dry-прогоне канал не тронут ни разу"))
        # снимок фактов на живой машине обязан собираться без исключений
        try:
            f = ER.snapshot()
            good = isinstance(f, dict) and "splinter" in f and "daemon" in f
            res.append(ok(good, "(14) снимок фактов собран: тик=%s пульс=%s"
                          % (f["splinter"]["tick"] is not None, f["daemon"]["pulse"] is not None)))
        except Exception as e:                            # noqa: BLE001
            res.append(ok(False, "(14) снимок фактов: %r" % e))
    else:
        res += [ok(False, "(14) живой прогон")] * 4
else:
    res += [ok(False, "(14) живой прогон")] * 4

# ═══════════ (15) О2 ДЕМОН: ЗАХОД — НЕ ОСТАНОВКА ═══════════════════════════════════════════
print("\n(15) Идущий claude -p внутри cycle() — работа, а не поломка (замер 10.08: 10 ложных из 10)")
if EX:
    # ГОЛДЕНЫ НА ДОСЛОВНЫХ ЛОЖНЫХ ЗАМЕТКАХ. Пары «разрыв пульса, окно исполнения» сняты с журнала
    # таймера и журнала демона 08–10.08.2026; task_timeout дев-ТЗ = 2700с (TASK_TIMEOUT_DEV).
    LIVE_FALSE = [(13.6, 18.0, 398), (14.4, 14.0, 399), (11.1, 26.0, 402), (14.3, 14.0, 405),
                  (14.1, 34.0, 406), (15.4, 15.0, 410), (14.9, 21.0, 417), (14.3, 21.0, 422),
                  (16.1, 20.0, 426), (17.2, 30.0, 430)]
    quiet = 0
    for gap, win, tid in LIVE_FALSE:
        v = EX.verdict(facts(pulse_age=gap, busy=(win, 2700.0, tid)), CFG)
        quiet += 1 if v == [] else 0
    res.append(ok(quiet == len(LIVE_FALSE),
                  "(15) все 10 ЖИВЫХ ложных заметок замера теперь молчат (%d/10)" % quiet))

    # ЗУБЫ ЦЕЛЫ: простой без штампа судится ровно как раньше — это и есть случай, ради которого О2 заведён.
    res.append(ok(kinds(EX.verdict(facts(pulse_age=23), CFG)) == ["o2_daemon"],
                  "(15) демон СТОИТ без штампа занятости → заметка как прежде"))
    # ПОТОЛОК СЛЕПОТЫ НАЗВАН ЧИСЛОМ: объявленный таймаут (45 мин) + хвост оборота (10 мин) = 55.
    res.append(ok(kinds(EX.verdict(facts(pulse_age=50, busy=(50.0, 2700.0, 401)), CFG)) == [],
                  "(15) заход 50 мин при таймауте 45 мин — внутри хвоста оборота → молчим"))
    res.append(ok(kinds(EX.verdict(facts(pulse_age=56, busy=(56.0, 2700.0, 401)), CFG))
                  == ["o2_daemon"],
                  "(15) 56 мин — за потолком (45+10) → молчание кончилось, слепота ограничена"))
    over = EX.verdict(facts(pulse_age=90, busy=(70.0, 600.0, 401)), CFG)
    res.append(ok(kinds(over) == ["o2_daemon"] and over[0].get("busy_task") == 401,
                  "(15) заход ПЕРЕЖИЛ свой объявленный таймаут (70 мин при 10) → нарушение стоит"))
    t = EX.render(over[0]) if over else ""
    res.append(ok("401" in t and "kill" in t,
                  "(15) заметка называет виновника номером: %s" % t.split("\n")[-1][:70]))

    # ШТАМП ПРОШЛОГО ЭКЗЕМПЛЯРА НИЧЕГО НЕ ОПРАВДЫВАЕТ — иначе смерть посреди задачи = «работа» вечно.
    stale = {"since": NOW - 700 * MIN, "limit": 2700.0, "task": 399, "pid": 111}
    res.append(ok(kinds(EX.verdict(facts(pulse_age=23, busy=stale, daemon_age_min=600.0), CFG))
                  == ["o2_daemon"],
                  "(15) штамп ПОСТАВЛЕН ДО старта экземпляра (протух с ним) → заметка остаётся"))
    res.append(ok(kinds(EX.verdict(facts(pulse_age=40, busy=(5.0, 2700.0, 399),
                                         daemon_alive=False), CFG)) == ["o2_daemon"],
                  "(15) живого процесса не видно вовсе → занятость не оправдание"))

    # МУСОР В ШТАМПЕ → ПОТОЛОК, А НЕ БЕСКОНЕЧНОСТЬ (иначе кривое поле глушило бы детектор навсегда).
    huge = {"since": NOW - 300 * MIN, "limit": 10 ** 9, "task": 399, "pid": 111}
    res.append(ok(kinds(EX.verdict(facts(pulse_age=300, busy=huge), CFG)) == ["o2_daemon"],
                  "(15) объявленный таймаут 10^9 с → срезан потолком BUSY_MAX_SEC, заметка есть"))
    for bad in ({"since": "мусор", "limit": 2700}, {"since": 0, "limit": 2700}, {"limit": 2700},
                "не словарь", None):
        v = EX.verdict(facts(pulse_age=23, busy=bad), CFG) if bad is not None else \
            EX.verdict(facts(pulse_age=23), CFG)
        if kinds(v) != ["o2_daemon"]:
            break
    else:
        bad = None
    res.append(ok(bad is None, "(15) мусор вместо штампа → судим как без штампа (fail-safe с зубами)"))
    res.append(ok(EX.verdict(facts(pulse_age=5, busy=(3.0, 2700.0, 399)), CFG) == [],
                  "(15) НОРМАЛЬНАЯ РАБОТА со штампом → молчание (штамп не создаёт нарушений)"))
    dead = dict(CFG, turn=0.0)
    res.append(ok(EX.verdict(facts(pulse_age=999, busy=(999.0, 1.0, 399)), dead) == [],
                  "(15) порог 0 → ветка мертва ДО чтения штампа (откат не сломан)"))
else:
    res += [ok(False, "(15) заход — не остановка")] * 12

# ═══════════ (16) ШТАМП ПИШЕТ ДЕМОН: ФОРМА ФАЙЛА ОДНА У ОБЕИХ СТОРОН ════════════════════════
print("\n(16) Демон штампует занятость и НЕ подменяет ею продукт (ts последнего оборота)")
_busy_tmp = tempfile.mkdtemp(prefix="o2busy_")
os.environ["CC_EXPECT_DIR"] = _busy_tmp
_s16 = len(res)
try:
    import orchestrator_daemon as OD
    _pulse_file = os.path.join(OD._expect_pulse_dir(), "pulse.json")

    def _read_pulse():
        with open(_pulse_file, encoding="utf-8") as f:
            return json.load(f)

    OD._expect_pulse()                                   # оборот состоялся
    p1 = _read_pulse()
    res.append(ok(p1.get("ts", 0) > 0 and "busy" not in p1,
                  "(16) чистый оборот: ts есть, штампа занятости НЕТ"))

    OD._expect_busy(432, 2700)                           # начался заход
    p2 = _read_pulse()
    res.append(ok(p2.get("ts") == p1.get("ts"),
                  "(16) штамп НЕ двигает ts — продукт остаётся последним СОСТОЯВШИМСЯ оборотом"))
    res.append(ok(isinstance(p2.get("busy"), dict) and p2["busy"].get("task") == 432
                  and float(p2["busy"].get("limit")) == 2700.0,
                  "(16) штамп несёт номер задачи и ОБЪЯВЛЕННЫЙ таймаут захода"))
    res.append(ok(p2["busy"].get("since", 0) >= p1.get("ts", 0),
                  "(16) штамп поставлен ПОСЛЕ оборота — время идёт вперёд"))

    OD._expect_busy(433, 180)                            # следом думатель: окно перештамповано
    p3 = _read_pulse()
    res.append(ok(p3["busy"].get("task") == 433 and float(p3["busy"]["limit"]) == 180.0,
                  "(16) следующий claude -p перештамповывает окно СВОИМ таймаутом"))

    OD._expect_pulse()                                   # оборот завершился
    p4 = _read_pulse()
    res.append(ok("busy" not in p4 and p4.get("ts", 0) > p1.get("ts", 0),
                  "(16) состоявшийся оборот СНИМАЕТ штамп сам — отдельной уборки не нужно"))

    # СКВОЗНАЯ СВЯЗКА: файл, написанный демоном, читается решением и молчит на живом заходе.
    OD._expect_busy(434, 2700)                            # дев-ТЗ: 45 мин собственного таймаута
    p5 = _read_pulse()
    live = {"pulse": p5, "proc": {"pid": os.getpid(), "started": p1["ts"] - 600},
            "claims": None}
    now3 = p5["busy"]["since"] + 20 * MIN                  # заход идёт 20 мин, пульсу 20+ мин
    v = EX.verdict({"now": now3, "queue": {"ok": False, "rows": []}, "daemon": live,
                    "splinter": {"tick": None, "log": None, "proc": None}}, CFG) if EX else None
    res.append(ok(v == [], "(16) СКВОЗНОЕ: файл демона → решение яруса 2 → молчание на живом заходе"))
except Exception as e:                                   # noqa: BLE001
    # Тот же файл гоняется по дереву ДО правки: там штампа нет вовсе, и это ЧЕСТНЫЙ красный,
    # а не крушение прогона — иначе «до» не сосчитать (метод git worktree тем же файлом).
    print("  (штамп занятости демону недоступен: %s)" % e)
    res += [ok(False, "(16) штамп занятости демона")] * (7 - (len(res) - _s16))
finally:
    os.environ.pop("CC_EXPECT_DIR", None)
    shutil.rmtree(_busy_tmp, ignore_errors=True)

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
