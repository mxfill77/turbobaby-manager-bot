#!/usr/bin/env python3
"""ОДНА ОПЕРАЦИЯ НЕ СПРАШИВАЕТСЯ ДВАЖДЫ (05.08.2026, фикс 3 из 3 «граница гейта»).

ЧТО ДОКАЗЫВАЕМ (голдены — на ДОСЛОВНЫХ формах живого корпуса, 1412 транскриптов):
 (1) ТОЖДЕСТВО ОПЕРАЦИИ — по цели и классу, а НЕ по тексту команды: две разные команды с одной
     картой дают один отпечаток; другой объект/число — другой; объект не назван — отпечатка нет.
 (2) «ИСПОЛНИЛАСЬ» — признак ПОЛОЖИТЕЛЬНЫЙ и измеренный: словарь со stdout/stderr = исполнение,
     строка «Error: …» = отказ. Дословные образцы взяты из транскриптов.
 (3) ЖИВОЙ ХУК: повтор УЖЕ РАЗРЕШЁННОЙ операции-присваивания вопросом больше не становится —
     причём повтор ДРУГИМ ТЕКСТОМ команды.
 (4) ЖИВОЙ ХУК: другая операция (другой объект) спрашивается как прежде — байт-в-байт.
 (5) ПЕРЕХОДЫ (деньги/удаление/процессы) НЕ снимаются НИКОГДА: вопрос остаётся, но карточка
     говорит, что это повтор — иначе владелец подтверждает второй факт, читая текст первого.
 (6) РАЗРЕШЕНИЕ ДОКАЗЫВАЕТСЯ ИСПОЛНЕНИЕМ: отказ движка памяти не касается, вопрос стоит.
 (7) ЗАХОДЫ РАЗДЕЛЕНЫ: чужой заход чужого «да» не наследует.
 (8) ГРАНИЦЫ НЕ ОСЛАБЛЕНЫ: жёсткий блок остаётся deny; гард физически не умеет сказать «allow»;
     сбой памяти (нечитаемый стор) = прежнее поведение.
 (9) ОБЕ СТОРОНЫ ВЫБИРАЮТ ОДИН КАТАЛОГ ПАМЯТИ — иначе фикс мёртв на пробах: гард кладёт связку в
     один файл, лента подтверждает в другом. Секция снимает подмену каталога и ВСЕ ЧЕТЫРЕ имени
     тест-прогона, потому что именно они закрывали эту ветку от проверки.
 (10) «ДА» ЧЕКАНИТСЯ ОПЕРАЦИЕЙ, А НЕ ТЕКСТОМ КОМАНДЫ: исполнение засчитывается разрешением
     ТОЛЬКО если команда СЕЙЧАС — та же самая операция, о которой спрашивали. Иначе зелёный
     прогон той же строки погашал бы вопрос, на который владелец ответил «нет».
 (11) ПРОГОН НЕ КАСАЕТСЯ БОЕВЫХ КАТАЛОГОВ СОСТОЯНИЯ (урок 04.08 со стёртым спулом).

Сети нет: подпроцессам ставим NOTIFY_COUNT_FILE и PRETOOL_NOPUSH=1, каталоги маркеров/ленты/памяти
подменены ВСЕГДА (правило «канал 2 изоляции проб обязан иметь мок у каждого теста»).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# ДЕРЕВО ПОД ПРОВЕРКОЙ. По умолчанию — своё; `TB_TEST_ROOT` наводит тест на ДРУГОЕ дерево (прогон
# «до правки» по worktree на HEAD). Запускать сам файл при этом надо ИЗ PROJECT/tests — иначе
# команда прогона перестаёт быть доверенной и её судит гард (живой случай 05.08, сессия 8c7b2b10).
ROOT = ((sys.argv[1] if len(sys.argv) > 1 else "").strip()
        or (os.environ.get("TB_TEST_ROOT") or "").strip() or os.path.dirname(HERE))
PY = "/root/turbobaby-manager-bot/venv/bin/python3"
GUARD = os.path.join(ROOT, "pretool_guard.py")
FEED = os.path.join(ROOT, "posttool_feed.py")
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PRETOOL_NOPUSH", "1")
os.environ.setdefault("ORCH_TEST_MODE", "1")

try:
    import repeat_ask as RA
except Exception:
    RA = None

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return c


TMP = tempfile.mkdtemp(prefix="repeatask_")
STORE = os.path.join(TMP, "store")
MARKERS = os.path.join(TMP, "markers")
SEEN = os.path.join(TMP, "seen")
for d in (STORE, MARKERS, SEEN):
    os.makedirs(d, exist_ok=True)

# ── СТРАЖ БОЕВЫХ КАТАЛОГОВ (секция 9 сверит) — взводится ДО первого вызова хука ────────────
LIVE_STATE = ("/tmp/cc_repeat_ask", "/tmp/cc_repeat_ask_test", "/tmp/cc_guard_block",
              "/tmp/cc_feed_seen")
sys.path.insert(0, HERE)
import livewatch
LW = livewatch.watch(*LIVE_STATE)
BEFORE = livewatch.snapshot(*LIVE_STATE)


def env(session="run-A"):
    e = dict(os.environ)
    e["CC_REPEAT_DIR"] = STORE
    e["PRETOOL_BLOCK_DIR"] = MARKERS
    e["CC_FEED_SEEN_DIR"] = SEEN
    e["NOTIFY_COUNT_FILE"] = os.path.join(TMP, "notify_count")
    e["PRETOOL_NOPUSH"] = "1"
    e.pop("CC_TASK_ID", None)             # ключ захода берётся из session_id входа хука
    return e


def guard(cmd, session="run-A"):
    """Живой хук PreToolUse → (решение|'defer', причина)."""
    payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": ROOT,
               "session_id": session}
    p = subprocess.run([PY, GUARD], input=json.dumps(payload), capture_output=True,
                       text=True, env=env(session), timeout=90)
    out = (p.stdout or "").strip()
    if not out:
        return "defer", ""
    try:
        d = json.loads(out)["hookSpecificOutput"]
        return d.get("permissionDecision", "?"), d.get("permissionDecisionReason", "")
    except Exception:
        return "?", out


EXEC_RESP = {"stdout": "готово", "stderr": "", "interrupted": False, "isImage": False,
             "noOutputExpected": False}
REFUSED_RESP = "Error: This command requires approval"


def executed(cmd, session="run-A", resp=None):
    """Живой хук PostToolUse: команда ИСПОЛНИЛАСЬ (= владелец разрешил)."""
    payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": ROOT,
               "session_id": session, "tool_response": EXEC_RESP if resp is None else resp}
    subprocess.run([PY, FEED], input=json.dumps(payload), capture_output=True,
                   text=True, env=env(session), timeout=90)


def fixture(name, body):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


# ДОСЛОВНАЯ живая подпись моста (см. _ENTITY_BIKE_RE): number=/kind=/km=. Сущность ТЕСТ-… —
# единственная форма записи в живые таблицы, которую доктрина 23.07 вообще разрешает одобрять
# (живая сущность = жёсткий блок, см. секцию 8). Класс `set_fleet_service` — присваивание:
# «у байка вид ТО gear на пробеге 27000», повтор подтверждает ТО ЖЕ состояние.
SVC = ("import bridge_client\n"
       "bridge_client.set_fleet_service(number='ТЕСТ-6789', kind='gear', km=27000, "
       "confirmed=True)\n")
SVC_OTHER_KIND = SVC.replace("'gear'", "'abs'")
SVC_OTHER_KM = SVC.replace("27000", "31000")
MONEY = ("import bridge_client\n"
         "bridge_client.add_transaction(group='Nalichka', amount=-500)\n")

print("=" * 88)
print("ОДНА ОПЕРАЦИЯ НЕ СПРАШИВАЕТСЯ ДВАЖДЫ")
print("=" * 88)

# ── (1) ТОЖДЕСТВО ОПЕРАЦИИ — ПО ЦЕЛИ И КЛАССУ, НЕ ПО ТЕКСТУ ────────────────────────────────
print("(1) отпечаток = класс + объект + число (карточка), а не текст команды:")
if RA is None:
    ok(False, "модуль памяти захода repeat_ask отсутствует — тождества считать нечем")
else:
    a = RA.fingerprint("set_fleet_service", "вид ТО gear", "пробег 27000")
    b = RA.fingerprint("set_fleet_service", "вид ТО gear", "пробег 27000")
    ok(a and a == b, "та же операция → тот же отпечаток")
    ok(a != RA.fingerprint("set_fleet_service", "вид ТО abs", "пробег 27000"),
       "ДРУГОЙ ОБЪЕКТ → другой отпечаток (владелец спрашивается заново)")
    ok(a != RA.fingerprint("set_fleet_service", "вид ТО gear", "пробег 31000"),
       "ДРУГОЕ ЧИСЛО → другой отпечаток (сверяют «тот ли байк И пробег»)")
    ok(a != RA.fingerprint("add_transaction", "вид ТО gear", "пробег 27000"),
       "ДРУГОЙ КЛАСС → другой отпечаток")
    ok(RA.fingerprint("set_fleet_oil", "", "пробег 27000") == "",
       "объект пуст → тождества НЕТ (пустой отпечаток)")
    ok(RA.fingerprint("set_fleet_oil", "—", "") == "",
       "объект «—» → тождества НЕТ")
    ok(RA.fingerprint("set_fleet_oil", "байк — значение вычисляется (аргумент plate)", "") == "",
       "объект «значение вычисляется» → тождества НЕТ: сравнить можно только названное")
    ok(RA.same_state("set_fleet_oil") and RA.same_state("set_fleet_service"),
       "присваивания в SAME_STATE")
    ok(not any(RA.same_state(h) for h in ("add_transaction", "void_last", "create_booking",
                                          "delete_event", "delete_file", "proc_ctl", "sqlite",
                                          "DOWRITE", "confirmed", "closing_upsert")),
       "переходы (деньги/отмена/создание/удаление/процессы/SQL/DOWRITE) — НЕ в SAME_STATE")
    ok(not RA.same_state("операция_которой_ещё_нет"),
       "FAIL-CLOSED: незнакомый класс вопрос сохраняет")

# ── (2) ПРИЗНАК ИСПОЛНЕНИЯ — ГОЛДЕНЫ НА ДОСЛОВНЫХ ФОРМАХ ТРАНСКРИПТОВ ──────────────────────
print("(2) «исполнилась» — положительный признак, форма измерена по живому корпусу:")
if RA is None:
    ok(False, "модуля памяти нет — признак исполнения проверить нечем")
else:
    ok(RA.executed({"stdout": "total 0", "stderr": "", "interrupted": "False",
                    "isImage": "False", "noOutputExpected": "False"}),
       "ДОСЛОВНО живой словарь исполнения (stdout/stderr/interrupted) → исполнилась")
    ok(not RA.executed("Error: This command requires approval"),
       "ДОСЛОВНО «Error: This command requires approval» → НЕ исполнилась")
    ok(not RA.executed("Error: 🔴 КРАСНОЕ Что: УДАЛЕНИЕ события из истории … жду твоё «да»."),
       "ДОСЛОВНО отказ карточкой гарда → НЕ исполнилась")
    ok(not RA.executed("Error: This Bash command contains multiple operations. The following "
                       "part requires approval: timeout 30 python cowork_log_append.py"),
       "ДОСЛОВНО отказ формы (multiple operations) → НЕ исполнилась")
    ok(not RA.executed({"stdout": "x", "interrupted": True}), "прерванная → НЕ исполнилась")
    ok(not RA.executed(None) and not RA.executed({}) and not RA.executed({"type": "text"}),
       "пусто / чужая форма → НЕ исполнилась (сомнение в сторону вопроса)")

# ── (3) ЖИВОЙ ХУК: ПОВТОР РАЗРЕШЁННОГО ПРИСВАИВАНИЯ ВОПРОСОМ НЕ СТАНОВИТСЯ ─────────────────
print("(3) живой хук: операция, уже разрешённая в этом заходе, второй раз не спрашивается:")
f1 = fixture("svc_a.py", SVC)
f2 = fixture("svc_b.py", "# другой файл, ТА ЖЕ операция\n" + SVC)   # другой ТЕКСТ команды
d1, why1 = guard("%s %s" % (PY, f1), "run-A")
ok(d1 == "ask", "первый раз — вопрос как прежде (решение=%s)" % d1)
ok("вид ТО gear" in why1, "в вопросе назван объект операции")
executed("%s %s" % (PY, f1), "run-A")                                # владелец разрешил → исполнилась
d2, _ = guard("%s %s" % (PY, f2), "run-A")
ok(d2 == "defer", "ПОВТОР той же операции ДРУГИМ ТЕКСТОМ — вопроса нет (решение=%s)" % d2)
d3, _ = guard("%s %s" % (PY, f1), "run-A")
ok(d3 == "defer", "повтор той же командой — тоже без вопроса (решение=%s)" % d3)

# ── (4) ДРУГАЯ ОПЕРАЦИЯ СПРАШИВАЕТСЯ КАК ПРЕЖДЕ ───────────────────────────────────────────
print("(4) другая операция спрашивается как прежде:")
fb = fixture("svc_other_kind.py", SVC_OTHER_KIND)
fk = fixture("svc_other_km.py", SVC_OTHER_KM)
db, whyb = guard("%s %s" % (PY, fb), "run-A")
ok(db == "ask", "ДРУГОЙ ОБЪЕКТ (вид ТО) — вопрос (решение=%s)" % db)
ok("вид ТО abs" in whyb, "и в вопросе назван именно он")
dk, _ = guard("%s %s" % (PY, fk), "run-A")
ok(dk == "ask", "ТОТ ЖЕ объект, ДРУГОЕ ЧИСЛО — вопрос (решение=%s)" % dk)

# ── (5) ПЕРЕХОДЫ НЕ СНИМАЮТСЯ НИКОГДА ─────────────────────────────────────────────────────
print("(5) переход (деньги) — вопрос остаётся, но карточка говорит, что это повтор:")
fm = fixture("money_a.py", MONEY)
dm1, whym1 = guard("%s %s" % (PY, fm), "run-A")
ok(dm1 == "ask", "первая проводка — вопрос (решение=%s)" % dm1)
ok("Повтор операции" not in whym1, "и про повтор в ней ничего не сказано")
executed("%s %s" % (PY, fm), "run-A")
fm2 = fixture("money_b.py", "# другой файл, та же проводка\n" + MONEY)
dm2, whym2 = guard("%s %s" % (PY, fm2), "run-A")
ok(dm2 == "ask", "ВТОРАЯ такая же проводка — вопрос ОСТАЁТСЯ (решение=%s)" % dm2)
ok("Повтор операции" in whym2 and "2-й раз" in whym2,
   "карточка называет повтор: «%s»" % next((s for s in whym2.splitlines()
                                            if "Повтор операции" in s), "—"))
ok("НОВЫЙ факт" in whym2, "и говорит, ЧЕМ повтор опасен (вторая проводка — второй факт)")

# ── (6) РАЗРЕШЕНИЕ ДОКАЗЫВАЕТСЯ ИСПОЛНЕНИЕМ, А НЕ ВОПРОСОМ ────────────────────────────────
print("(6) отказ движка разрешением не считается:")
fr = fixture("svc_refused.py", SVC.replace("'gear'", "'airfilter'"))
dr1, _ = guard("%s %s" % (PY, fr), "run-R")
ok(dr1 == "ask", "первый раз — вопрос")
executed("%s %s" % (PY, fr), "run-R", resp=REFUSED_RESP)             # владелец НЕ разрешил
dr2, _ = guard("%s %s" % (PY, fr), "run-R")
ok(dr2 == "ask", "после ОТКАЗА вопрос стоит как стоял (решение=%s)" % dr2)
executed("%s %s" % (PY, fr), "run-R", resp="Error: 🔴 КРАСНОЕ Что: … — жду твоё «да».")
dr3, _ = guard("%s %s" % (PY, fr), "run-R")
ok(dr3 == "ask", "после отказа карточкой гарда — тоже стоит (решение=%s)" % dr3)

# ── (7) ЗАХОДЫ РАЗДЕЛЕНЫ ──────────────────────────────────────────────────────────────────
print("(7) чужой заход чужого «да» не наследует:")
dz, _ = guard("%s %s" % (PY, f1), "run-B")
ok(dz == "ask", "та же операция в ДРУГОМ заходе — вопрос (решение=%s)" % dz)

# ── (8) ГРАНИЦЫ НЕ ОСЛАБЛЕНЫ ──────────────────────────────────────────────────────────────
print("(8) границы: жёсткое остаётся жёстким, «allow» гард не умеет:")
HARD = "grep -n TOKEN /root/turbobaby-manager-bot/.env"
dh1, _ = guard(HARD, "run-A")
executed(HARD, "run-A")                                  # даже если «исполнилось» — не право
dh2, _ = guard(HARD, "run-A")
ok(dh1 == "deny" and dh2 == "deny", "жёсткий блок секретов: deny и до, и после (%s/%s)"
   % (dh1, dh2))
PROC = "pkill -f splinter"
dp1, _ = guard(PROC, "run-A")
executed(PROC, "run-A")
dp2, _ = guard(PROC, "run-A")
ok(dp1 == "deny" and dp2 == "deny", "жёсткий блок процессов: deny и до, и после (%s/%s)"
   % (dp1, dp2))
LIVE_ENTITY = fixture("svc_live.py", SVC.replace("ТЕСТ-6789", "6789"))
dl1, _ = guard("%s %s" % (PY, LIVE_ENTITY), "run-A")
executed("%s %s" % (PY, LIVE_ENTITY), "run-A")
dl2, _ = guard("%s %s" % (PY, LIVE_ENTITY), "run-A")
ok(dl1 == "deny" and dl2 == "deny",
   "живая сущность в Лист1: deny и до, и после (%s/%s)" % (dl1, dl2))
src = open(GUARD, encoding="utf-8").read()
ok('"allow"' not in src and "'allow'" not in src,
   "в исходнике гарда нет решения «allow» — снять вопрос он может только молчанием (_defer)")
# СБОЙ ПАМЯТИ = ПРЕЖНЕЕ ПОВЕДЕНИЕ. Портим стор захода и ждём вопрос, а не тишину.
broken = os.path.join(STORE, "run-C.json")
with open(broken, "w", encoding="utf-8") as fh:
    fh.write("{не json")
dbr, _ = guard("%s %s" % (PY, f1), "run-C")
ok(dbr == "ask", "нечитаемая память захода → вопрос как прежде (решение=%s)" % dbr)

# ── (9) ОБЕ СТОРОНЫ ВЫБИРАЮТ ОДИН КАТАЛОГ ПАМЯТИ ──────────────────────────────────────────
# ПОЧЕМУ ЭТА СЕКЦИЯ ЕСТЬ. Память захода работает только если СВЯЗКУ пишет и ЧИТАЕТ один файл.
# Гард берёт каталог как isolated() ПОСЛЕ латча set_probe(is_probe(cmd)) — признак зависит ОТ
# КОМАНДЫ; лента брала is_test_run() — признак зависит ТОЛЬКО ОТ ОКРУЖЕНИЯ. В живой сессии любая
# ПРОБА (env-префикс в тексте, _test/_dryrun в имени, запуск из /tmp/tb_scratch) разводила стороны
# по двум файлам, и повтор спрашивался как прежде — то есть фикс был мёртв ровно на той популяции,
# где класс и измерен (оба живых дубля — пробы). Под гейтом ОБА признака истинны, поэтому секции
# 3–7 расхождения не видят вовсе: подменённый CC_REPEAT_DIR и четыре имени тест-прогона закрывают
# именно ту ветку, которая ошибалась («мок, переставший задевать ветку, хуже отсутствующего»).
# Поэтому здесь они СНИМАЮТСЯ — и секция 10 отдельно доказывает, что снятие ничего не записало.
print("(9) каталог памяти захода: гард и лента выбирают ОДИН и тот же:")
FOUR = ("PRETOOL_TEST_RUN", "ORCH_TEST_MODE", "PRETOOL_NOPUSH", "PYTEST_CURRENT_TEST")
DIRCASES = [
    ("КОНТРОЛЬ: боевой скрипт из репо (не проба)", {}, "%s /root/turbobaby-manager-bot/w.py" % PY),
    ("живой случай 05.08: env-префикс в тексте команды", {},
     "PRETOOL_NOPUSH=1 venv/bin/python3 _scratch_litpos_0805/head/tests/test_literal_position.py"),
    ("write-смок с _test в имени", {}, "%s /root/turbobaby-manager-bot/smoke_svc_test.py" % PY),
    ("разведка из /tmp/tb_scratch (правило R17)", {}, "%s /tmp/tb_scratch/x/w.py" % PY),
    ("прогон под гейтом", {"ORCH_TEST_MODE": "1"}, "%s /root/turbobaby-manager-bot/w.py" % PY),
]
if RA is None:
    ok(False, "модуля памяти нет — сравнивать каталоги нечем")
else:
    import pretool_guard as PG
    import posttool_feed as PF
    real_ac, real_ma, real_cf = RA.approved_count, RA.mark_asked, RA.confirm
    grab = {}
    # ЛОВИМ АРГУМЕНТ САМИХ ВЫЗОВОВ, а не пересчитываем признак заново: проверяется то, что
    # стороны РЕАЛЬНО передают в память, поэтому будущая правка любого из двух мест видна тесту.
    RA.approved_count = lambda k, fp, iso=False: grab.__setitem__("чтение гарда", iso) or 0
    RA.mark_asked = lambda k, c, fp, iso=False: grab.__setitem__("пометка гарда", iso)
    RA.confirm = lambda k, c, r, iso=False, fp_now=None: grab.__setitem__("лента", iso) or False
    saved_env = {k: os.environ.get(k) for k in FOUR + ("CC_REPEAT_DIR",)}
    try:
        for label, extra, cmd in DIRCASES:
            for k in FOUR + ("CC_REPEAT_DIR",):
                os.environ.pop(k, None)
            os.environ.update(extra)
            grab.clear()
            payload = {"session_id": "run-D", "tool_name": "Bash",
                       "tool_input": {"command": cmd}, "tool_response": EXEC_RESP}
            PG.set_probe(PG.is_probe(cmd))                  # ровно последовательность main() гарда
            if hasattr(PG, "_repeat_mark"):
                PG._repeat_seen(payload, "set_fleet_service", "вид ТО gear", "пробег 27000")
                PG._repeat_mark(payload, cmd, "set_fleet_service", "вид ТО gear", "пробег 27000")
            else:   # дерево «ДО правки» (прогон по worktree): чтение и пометка были одной функцией
                PG._repeat_seen(payload, cmd, "set_fleet_service", "вид ТО gear", "пробег 27000")
            PF._remember_permission(payload, cmd, EXEC_RESP)
            dirs = {who: RA.store_dir(iso) for who, iso in grab.items()}
            ok(len(set(dirs.values())) == 1 and len(dirs) == 3,
               "%s: %s" % (label, ", ".join("%s=%s" % (w, os.path.basename(d))
                                            for w, d in sorted(dirs.items()))))
    finally:
        RA.approved_count, RA.mark_asked, RA.confirm = real_ac, real_ma, real_cf
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        PG.set_probe(False)
    # ЛАТЧ ВЗВОДИТСЯ РАНЬШЕ, ЧЕМ ЧИТАЕТСЯ. Вся симметрия держится на порядке в main(): сперва
    # set_probe(is_probe(cmd)), потом _repeat_seen. Переставь их местами — гард начнёт выбирать
    # каталог по НЕвзведённому латчу, и расхождение вернётся молча.
    gsrc = open(GUARD, encoding="utf-8").read()
    ok(0 < gsrc.find("set_probe(probe)") < gsrc.find("seen = _repeat_seen("),
       "в main() латч пробы взводится ДО обращения к памяти захода")

# ── (10) «ДА» ЧЕКАНИТСЯ ОПЕРАЦИЕЙ, А НЕ ТЕКСТОМ КОМАНДЫ ───────────────────────────────────
# Связка «команда → операция» живёт в памяти по КЛЮЧУ ТЕКСТА, а текст у скрипта не меняется, пока
# меняется его содержимое — это рабочий цикл репозитория (правлю фикстуру, запускаю, правлю снова).
# Если исполнение засчитывать по одному лишь совпадению текста, то ЗЕЛЁНЫЙ прогон той же строки
# погасит вопрос, на который владелец только что ответил «НЕТ», — и красная операция пройдёт без
# карточки, ни разу не получив «да». Поэтому разрешение засчитывается, только если команда СЕЙЧАС
# даёт ТОТ ЖЕ отпечаток операции, о котором был вопрос.
print("(10) «да» чеканится операцией, а не текстом команды:")
SWAP = SVC.replace("'gear'", "'brakes'")            # свой объект, чтобы не пересечься с секцией 3
fsw = fixture("svc_swap.py", SWAP)
cmd_sw = "%s %s" % (PY, fsw)
dsw1, _ = guard(cmd_sw, "run-S")
ok(dsw1 == "ask", "красное содержимое — вопрос (решение=%s)" % dsw1)
executed(cmd_sw, "run-S", resp=REFUSED_RESP)        # владелец ОТКАЗАЛ
fixture("svc_swap.py", "print('зелёно')\n")         # ТОТ ЖЕ путь и текст команды, другое содержимое
executed(cmd_sw, "run-S")                           # зелёный прогон той же строки — исполнился
fixture("svc_swap.py", SWAP)                        # красное вернулось
dsw2, _ = guard(cmd_sw, "run-S")
ok(dsw2 == "ask",
   "зелёный прогон той же строки НЕ считается «да» за красную операцию (решение=%s)" % dsw2)
# И обратная сторона: настоящее исполнение той же операции засчитывается как прежде (секция 3
# это уже показала; здесь — что проверка содержимого не сломала законный путь в ЭТОМ же заходе).
executed(cmd_sw, "run-S")
dsw3, _ = guard(cmd_sw, "run-S")
ok(dsw3 == "defer", "исполнение ТОЙ ЖЕ операции засчитано, повтор снят (решение=%s)" % dsw3)

# ── (11) БОЕВЫЕ КАТАЛОГИ СОСТОЯНИЯ НЕ ТРОНУТЫ ─────────────────────────────────────────────
print("(11) прогон не касается боевых каталогов состояния:")
AFTER = livewatch.snapshot(*LIVE_STATE)
for p in LIVE_STATE:
    ok(BEFORE[p] == AFTER[p], "не тронут: %s" % p)
ok(not livewatch.diff(BEFORE, AFTER), "расхождений нет: %s" % livewatch.diff(BEFORE, AFTER))
ok(not LW.writes(), "аудит-хук: ноль ЗАПИСЕЙ в боевые каталоги за весь прогон: %s" % LW.report())

shutil.rmtree(TMP, ignore_errors=True)
print("-" * 88)
print("ИТОГ: %d/%d" % (sum(res), len(res)))
if all(res):
    print("Все проверки зелёные.")
sys.exit(0 if all(res) else 1)
