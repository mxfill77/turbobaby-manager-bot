"""ВИД `brain` УМЕЕТ ДАВАТЬ ДОКАЗАН, И ЕГО РУКИ НАКОНЕЦ ЗОВЁТ ТЕСТ (17.08.2026).

ПОВОД. Разбор 17.08 (`docs/artifacts/2026-08-17-brain-ref-verdict-vps.md`) нашёл у одного вида
адреса три беды сразу, и держались они на том, что ветку НЕ ЗВАЛ НИ ОДИН ТЕСТ (0 вхождений
`brain_fact` в `tests/`): все проверки кормили судью РУКОТВОРНЫМИ словарями фактов, а руки
оставались непройденными. Поэтому гейт не поймал бы главного — у клиента моста нет метода
`read_doc`, которым руки его звали, и `AttributeError` выходил наружу словами «мост не отвечает».
Этот файл существует затем, чтобы такое больше не могло быть зелёным.

ПОРЯДОК СЕКЦИЙ НЕ КОСМЕТИКА: отрицательный тест стоит ПЕРВЫМ по прямому требованию задания.
Прибор, который на отсутствующей подстроке говорит «доказан», негоден целиком.

 (1) ОТРИЦАТЕЛЬНЫЙ ТЕСТ, ПЕРВЫМ, НА ЖИВОМ УЗЛЕ: адрес называет ключ ЖИВОГО узла и подстроку,
     которой в теле НЕТ → НЕ ДОКАЗАН. Читается настоящий мост настоящей дверью;
 (2) ПОЛОЖИТЕЛЬНЫЙ КОНТРОЛЬ на ТОМ ЖЕ единственном живом чтении → ДОКАЗАН (прибор, красящий всё
     в «не доказан», так же негоден);
 (3) НАСТОЯЩИЕ РУКИ БЕЗ СЕТИ: реальный класс моста, подменён ТОЛЬКО транспорт. Эта секция ловит
     поломку входа КАЖДЫМ прогоном гейта — в том числе там, где моста нет вовсе;
 (4) ПОЛОМКА РУК ≠ МОЛЧАНИЕ МОСТА: у наших бед свои слова, и «мост не отвечает» среди них нет;
 (5) АДРЕС БЕЗ ПОДСТРОКИ → НЕИЗВЕСТНО, а не зелёное;
 (6) СМЕНА ОПРЕДЕЛЕНИЯ ЗАПИСАНА ГОЛДЕНОМ: длина больше не решает (решение Штаба 17.08), и забор
     Честертона назван — вместе с тем, что мы теряем;
 (7) ГРАНИЦЫ И ЦЕНА: к мосту ходим ТОЛЬКО под адрес вида `brain`, бюджет режет, судья по-прежнему
     безрукий.

ЖИВЫЕ СЕКЦИИ В ГЕЙТЕ НЕ СУДЯТСЯ, И ЭТО ЧУЖОЙ ЗАБОР, А НЕ НАША ЛЕНЬ. В репозитории с 17.07.2026
стоит рубеж 3 (класс 193): `bridge_client` при `ORCH_TEST_MODE=1` патчит `requests.Session.send`
и поднимает RuntimeError на ЛЮБОМ нелокальном адресе — «тест дёрнул сеть». Гейт ставит этот флаг
всем тестам, значит живого чтения в гейте не будет НИКОГДА, как ни пиши тест. Забор правильный:
тест, краснеющий от болезни Google (за 75 суток `splinter.log` знает 3863 таймаута моста),
блокировал бы push здоровому дереву. Поэтому секции (1) и (2) идут только под ЗАДОКУМЕНТИРОВАННЫМ
обходом самого рубежа — `BRIDGE_ALLOW_NETWORK=1`, — а в гейте честно говорят «не судим», НЕ
засчитывая себе зелёного. Живая проба заходом сделана руками и дословно записана в артефакт
`docs/artifacts/2026-08-17-brain-ref-provable-vps.md`.

ЧТО СУДИТСЯ ВСЕГДА — секции (3)–(7), и среди них та единственная, которой не хватало: (3) зовёт
НАСТОЯЩИЕ руки на РЕАЛЬНОМ классе моста, подменяя только транспорт, и краснеет от исчезновения
входа без всякой сети. Именно она поймала бы класс 17.08.

ЗАПУСК — ЖИВОЙ ФОРМАТ ГЕЙТА: `venv/bin/python3 tests/test_brain_ref_provable.py`
(gate.py гоняет каждый тест ровно так, отдельным процессом, потолок 90 с; ненулевой код = красное).
"""
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
# КАНАЛ 2 ИЗОЛЯЦИИ ПРОБ (правило CLAUDE.md): четыре имени + каталог маркеров ВСЕГДА.
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["PRETOOL_TEST_RUN"] = "1"
os.environ["ORCH_TEST_MODE"] = "1"
os.environ["PRETOOL_BLOCK_DIR"] = "/tmp/cc_guard_block_test"

try:                                    # настройки моста — тем же способом, что у живых читателей
    from dotenv import load_dotenv
    load_dotenv()
except Exception:                       # noqa: BLE001 — без них живые секции скажут «не судим»
    pass
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import ast                                                              # noqa: E402
import time                                                             # noqa: E402

import requests                                                         # noqa: E402

import bridge_client as BC                                              # noqa: E402
import result_judge as RJ                                               # noqa: E402
import result_judge_facts as RF                                         # noqa: E402

REPO = "/root/turbobaby-manager-bot"
# Живой узел: самый дешёвый из существующих (одна строка статуса). Живая проба 17.08 — 3.05 с.
LIVE_KEY = "pulse"
# Подстрока, которой в теле НЕТ и быть не может: она и есть отрицательный тест.
ABSENT = "ЭТОЙ-СТРОКИ-В-УЗЛЕ-НЕТ-И-НЕ-БУДЕТ-20260817"
# Бюджет ЖИВОГО чтения в тесте — 25 с: ×8 к измеренной цене и ×3.6 под потолком гейта (90 с).
# Боевой бюджет другой (120 с, порог О5 для чтения мозга) — тесту потолок гейта важнее.
LIVE_BUDGET = 25

res = []
skipped = []


def ok(cond, label):
    print(("  PASS " if cond else "  FAIL ") + label)
    res.append(bool(cond))
    return bool(cond)


def skip(label):
    print("  НЕ СУДИМ " + label)
    skipped.append(label)


# ════════════════════════════════════════════════════════════════════════════════════════════
print("(1) ОТРИЦАТЕЛЬНЫЙ ТЕСТ, ПЕРВЫМ: живой узел, подстроки в теле НЕТ → НЕ ДОКАЗАН")
# ════════════════════════════════════════════════════════════════════════════════════════════
LIVE_ON = os.getenv("BRIDGE_ALLOW_NETWORK") == "1"
_ban_installed = getattr(requests.Session.send, "__name__", "") == "_banned"
_facts, _live = {}, {}

if not LIVE_ON:
    # НЕ ПЫТАЕМСЯ и не выдаём чужой запрет за молчание моста: попытка вернула бы «мост не
    # отвечает (RuntimeError)» и обвинила бы невиновного — ровно тот класс, против которого
    # написан весь этот заход.
    skip("сеть в тест-режиме запрещена рубежом 3 (класс 193, ORCH_TEST_MODE=1) — живой узел "
         "здесь не судим; проба заходом сделана под BRIDGE_ALLOW_NETWORK=1 и лежит в артефакте")
    ok(_ban_installed,
       "и запрет НАСТОЯЩИЙ, а не выдуманный поводом промолчать: requests.Session.send = «%s»"
       % getattr(requests.Session.send, "__name__", "?"))
else:
    # ЕДИНСТВЕННОЕ живое чтение на весь файл — через ту же дверь `gather`, которой ходит демон.
    _t0 = time.time()
    _facts = RF.gather([("brain", "%s %s" % (LIVE_KEY, ABSENT))], brain=True, budget=LIVE_BUDGET)
    _live = (_facts.get("brain") or {}).get(LIVE_KEY) or {}
    _dt = time.time() - _t0
    print("  живое чтение узла «%s»: %.2f c, read=%s, знаков=%s, причина=%s"
          % (LIVE_KEY, _dt, _live.get("read"), _live.get("len"), _live.get("why") or "—"))

if LIVE_ON and not _live.get("read"):
    skip("источник недоступен (%s) — о живом узле не судим, но и зелёного не берём"
         % (_live.get("why") or "без причины"))
    ok(not _live.get("broken"),
       "и это НЕ наша поломка: broken=%s (иначе чинить надо код, а не ждать мост)"
       % _live.get("broken"))
elif LIVE_ON:
    v = RJ.verdict(("brain", "%s %s" % (LIVE_KEY, ABSENT)), _facts)
    ok(v["state"] == RJ.UNPROVEN,
       "живой узел прочитан, названного НЕ содержит → %s («%s»)" % (v["state"], v["why"][:70]))
    ok(v["state"] != RJ.PROVEN,
       "ЗАМОК: отрицательный случай НЕ позеленел (это и есть годность прибора)")

# ════════════════════════════════════════════════════════════════════════════════════════════
print("\n(2) ПОЛОЖИТЕЛЬНЫЙ КОНТРОЛЬ на ТОМ ЖЕ чтении: подстрока из живого тела → ДОКАЗАН")
# ════════════════════════════════════════════════════════════════════════════════════════════
if not _live.get("read"):
    skip("живого чтения не было (%s) — положительный контроль не судим"
         % ("сеть запрещена рубежом 3" if not LIVE_ON else "источник недоступен"))
else:
    _text = str(_live.get("text") or "")
    _present = _text[:24].strip() or _text[:1]
    v = RJ.verdict(("brain", "%s %s" % (LIVE_KEY, _present)), _facts)
    ok(v["state"] == RJ.PROVEN,
       "живой узел содержит названное → %s («%s»)" % (v["state"], v["why"][:70]))
    ok(_present and _present in _text,
       "подстрока взята ИЗ прочитанного тела, а не выдумана: «%s»" % _present[:40])

# ════════════════════════════════════════════════════════════════════════════════════════════
print("\n(3) НАСТОЯЩИЕ РУКИ БЕЗ СЕТИ: реальный класс моста, подменён ТОЛЬКО транспорт")
# ════════════════════════════════════════════════════════════════════════════════════════════
# ИМЕННО ЭТА СЕКЦИЯ поймала бы класс 17.08: вход `_call` резолвится на ЖИВОМ классе, и его
# отсутствие даёт красное здесь же, без всякой сети и без всякого моста.
_seen = []
_real_dr = BC.BridgeClient._durable_request


def _fake_dr(self, method, action, params=None, **kw):
    _seen.append((method, action, dict(params or {})))
    return {"ok": True, "text": "тело узла ЗНАК-17.08", "name": (params or {}).get("name")}


BC.BridgeClient._durable_request = _fake_dr
try:
    f = RF.brain_fact("узел_пробы")
finally:
    BC.BridgeClient._durable_request = _real_dr

ok(f.get("read") is True and f.get("text") == "тело узла ЗНАК-17.08",
   "руки прошли НАСКВОЗЬ до тела узла: read=%s, знаков=%s" % (f.get("read"), f.get("len")))
ok(len(_seen) == 1 and _seen[0][1] == RF.BRAIN_ACTION,
   "спрошено РОВНО одно действие и именно «%s»: %s" % (RF.BRAIN_ACTION,
                                                       [s[1] for s in _seen]))
ok(_seen and _seen[0][2].get("name") == "узел_пробы",
   "ключ узла уехал параметром «name» дословно: %s" % (_seen[0][2].get("name") if _seen else None))
ok(_seen and _seen[0][0] == "GET",
   "чтение идёт GET-ом, как у всех живых читателей: %s" % (_seen[0][0] if _seen else None))
ok(callable(getattr(BC.BridgeClient, RF.BRAIN_ENTRY, None)),
   "вход «%s» ЕСТЬ на живом классе моста (а метода «read_doc» у него нет: %s)"
   % (RF.BRAIN_ENTRY, hasattr(BC.BridgeClient, "read_doc")))

v = RJ.verdict(("brain", "узел_пробы ЗНАК-17.08"), {"brain": {"узел_пробы": f}})
ok(v["state"] == RJ.PROVEN,
   "и вердикт по такому факту — ДОКАЗАН: %s («%s»)" % (v["state"], v["why"][:60]))

# ════════════════════════════════════════════════════════════════════════════════════════════
print("\n(4) ПОЛОМКА РУК ≠ МОЛЧАНИЕ МОСТА: у наших бед свои слова")
# ════════════════════════════════════════════════════════════════════════════════════════════
# (а) вход пропал — ровно то, что было живьём семьдесят дней.
_real_call = BC.BridgeClient._call
del BC.BridgeClient._call
try:
    f_broken = RF.brain_fact("узел_пробы")
finally:
    BC.BridgeClient._call = _real_call

ok(f_broken.get("read") is False and f_broken.get("broken") is True,
   "входа нет → read=False и broken=True (%s)" % f_broken.get("broken"))
ok(RF.BROKEN in str(f_broken.get("why")),
   "причина названа НАШИМИ словами: «%s»" % str(f_broken.get("why"))[:70])
ok("мост не отвечает" not in str(f_broken.get("why")),
   "и мост в ней НЕ обвинён — прежняя ложь («мост не отвечает») больше не звучит")
v = RJ.verdict(("brain", "узел_пробы ЧТО-УГОДНО"), {"brain": {"узел_пробы": f_broken}})
ok(v["state"] == RJ.UNKNOWN and RF.BROKEN in v["why"],
   "вердикт НЕИЗВЕСТНО, и слова поломки доехали до отчёта: «%s»" % v["why"][:70])

# (б) мост бросил — это уже мир, и слова другие.
def _raise_dr(self, *a, **kw):
    raise TimeoutError("мост молчит")


BC.BridgeClient._durable_request = _raise_dr
try:
    f_dead = RF.brain_fact("узел_пробы")
finally:
    BC.BridgeClient._durable_request = _real_dr
ok(f_dead.get("read") is False and f_dead.get("broken") is False
   and "мост не отвечает" in str(f_dead.get("why")),
   "мост бросил → «%s», broken=%s" % (str(f_dead.get("why"))[:50], f_dead.get("broken")))

# (в) ответ не того вида — снова НАША беда, а не мира.
BC.BridgeClient._durable_request = lambda self, *a, **kw: "внезапно строка"
try:
    f_junk = RF.brain_fact("узел_пробы")
finally:
    BC.BridgeClient._durable_request = _real_dr
ok(f_junk.get("broken") is True and RF.BROKEN in str(f_junk.get("why")),
   "ответ не словарь → broken=True, «%s»" % str(f_junk.get("why"))[:60])

# (г) мост ответил ОТКАЗОМ — источник ответил, и это ни то, ни другое.
BC.BridgeClient._durable_request = lambda self, *a, **kw: {"ok": False, "error": "unknown_name"}
try:
    f_no = RF.brain_fact("нет-такого-ключа")
finally:
    BC.BridgeClient._durable_request = _real_dr
ok(f_no.get("read") is False and f_no.get("broken") is False
   and "unknown_name" in str(f_no.get("why")),
   "ключа нет в манифесте → отказ моста назван дословно: «%s»" % str(f_no.get("why"))[:60])
v = RJ.verdict(("brain", "нет-такого-ключа ЧТО-УГОДНО"), {"brain": {"нет-такого-ключа": f_no}})
ok(v["state"] == RJ.UNKNOWN,
   "и это НЕИЗВЕСТНО, а не «не доказан»: узел не читали, значит и сказать о нём нечего")

# (д) бюджет исчерпан — ответ, а не исключение, и сеть не трогается вовсе.
_t0 = time.time()
f_dl = RF.brain_fact(LIVE_KEY, budget=0.0001)
_dl_dt = time.time() - _t0
ok(f_dl.get("read") is False and "бюджет" in str(f_dl.get("why")) and _dl_dt < 5,
   "исчерпанный бюджет → «%s» за %.3f c (обмен не начат)" % (str(f_dl.get("why"))[:50], _dl_dt))

# ════════════════════════════════════════════════════════════════════════════════════════════
print("\n(5) АДРЕС БЕЗ ПОДСТРОКИ → НЕИЗВЕСТНО, а не зелёное")
# ════════════════════════════════════════════════════════════════════════════════════════════
_p = RJ.plan(("brain", "KB_trainer_log"))
ok(not _p["ok"] and "ключ" in _p["why"],
   "один ключ без подстроки не разбирается вовсе: «%s»" % _p["why"][:70])
# Даже когда узел прочитан ЦЕЛИКОМ, безподстрочный адрес зелёного не даёт: искать нечего.
v = RJ.verdict(("brain", "KB_trainer_log"),
               {"brain": {"KB_trainer_log": {"read": True, "text": "любое тело", "len": 10}}})
ok(v["state"] == RJ.UNKNOWN,
   "узел прочитан, а подстрока не названа → %s («%s»)" % (v["state"], v["why"][:60]))
ok(RJ.plan(("brain", "ключ   "))["ok"] is False,
   "хвост из пробелов подстрокой не считается (иначе «содержит пустоту» было бы зелёным)")

# ════════════════════════════════════════════════════════════════════════════════════════════
print("\n(6) СМЕНА ОПРЕДЕЛЕНИЯ ЗАПИСАНА ГОЛДЕНОМ (решение Штаба 17.08.2026)")
# ════════════════════════════════════════════════════════════════════════════════════════════
# Прежде эти два случая давали НЕ ДОКАЗАН и НЕИЗВЕСТНО. Теперь — ДОКАЗАН. Это ЗАПИСАННАЯ развилка
# владельца, а не расслабленный тест: пусть смена определения краснеет, если её вернут молча.
v = RJ.verdict(("brain", "узел НАЗВАННОЕ"),
               {"brain": {"узел": {"read": True, "text": "НАЗВАННОЕ и ещё", "len": 15,
                                   "len_before": 15}}})
ok(v["state"] == RJ.PROVEN,
   "узел содержит названное и НЕ ВЫРОС → %s (прежде было «не доказан»)" % v["state"])
ok("длина прежняя" in v["why"],
   "и длина названа СПРАВКОЙ, а не приговором: «%s»" % v["why"][:70])
v = RJ.verdict(("brain", "узел НАЗВАННОЕ"),
               {"brain": {"узел": {"read": True, "text": "НАЗВАННОЕ и ещё", "len": 15,
                                   "len_before": None}}})
ok(v["state"] == RJ.PROVEN,
   "прежней длины нет вовсе → %s (прежде было «неизвестно», и так молчал КАЖДЫЙ узел)" % v["state"])

# ЗАБОР ЧЕСТЕРТОНА: премиса, на которой он снят, проверяется, а не берётся на слово.
_producers = []
for n in sorted(os.listdir(REPO)):
    if not n.endswith(".py") or n.startswith("_"):
        continue
    src = open(os.path.join(REPO, n), encoding="utf-8").read()
    if "len_before" in src and n not in ("result_judge.py", "result_judge_facts.py"):
        _producers.append(n)
ok(not _producers,
   "прежнюю длину узла по-прежнему НЕ ПИШЕТ НИКТО — производителей %d %s (на этом и стоит "
   "решение: забор отделял «неизвестно» от всего, а не работу от совпадения)"
   % (len(_producers), _producers))
print("  ЦЕНА НАЗВАНА: защиту «подстрока могла лежать там и ДО шага» мы ТЕРЯЕМ. Взамен —")
print("  дисциплина адреса: подстрока обязана быть тем, чего до шага быть не могло.")

# ════════════════════════════════════════════════════════════════════════════════════════════
print("\n(7) ГРАНИЦЫ И ЦЕНА")
# ════════════════════════════════════════════════════════════════════════════════════════════
_calls = []
_real_bf = RF.brain_fact
RF.brain_fact = lambda *a, **kw: (_calls.append(a), _real_bf(*a, **kw))[1]
try:
    RF.gather([("file", "result_judge.py"), ("commit", "ed02f17")], brain=True)
    ok(not _calls, "адрес не назвал узла → к мосту не идём НИ РАЗУ (вызовов %d)" % len(_calls))
    RF.gather([("brain", "узел_пробы что-то")], brain=False)
    ok(not _calls, "brain=False по-прежнему держит мост закрытым (вызовов %d)" % len(_calls))
finally:
    RF.brain_fact = _real_bf

_od = open(os.path.join(REPO, "orchestrator_daemon.py"), encoding="utf-8").read()
ok("gather([ref], brain=True)" in _od and "gather([ref], brain=False)" not in _od,
   "демон спрашивает узлы живьём: в `_shadow_verdict` стоит brain=True")

_judge_src = open(os.path.join(REPO, "result_judge.py"), encoding="utf-8").read()
_imports = [a.name for node in ast.walk(ast.parse(_judge_src))
            if isinstance(node, ast.Import) for a in node.names]
ok(_imports == ["result_ref"],
   "судья остался БЕЗРУКИМ: импорт ровно один — %s" % _imports)

import invariants_check as IC                                           # noqa: E402
_run = IC.CheckRun("RESULT_JUDGE_PURE")
IC.check_result_judge_pure(None, _run)
ok(not _run.findings, "страж чистоты судьи зелёный после правки (%s)" % _run.findings)

_hands_src = open(os.path.join(REPO, "result_judge_facts.py"), encoding="utf-8").read()
ok("def read_doc" not in _hands_src and ".read_doc(" not in _hands_src,
   "несуществующий метод из рук ушёл: зовём действие «%s» через вход «%s»"
   % (RF.BRAIN_ACTION, RF.BRAIN_ENTRY))
ok(RF.BRAIN_BUDGET_DEFAULT == 120,
   "боевой бюджет одного чтения — %s с (порог О5 для чтения мозга)" % RF.BRAIN_BUDGET_DEFAULT)

print("\nИТОГ: %d/%d PASS, не судимо секций: %d %s"
      % (sum(res), len(res), len(skipped), skipped if skipped else ""))
sys.exit(0 if all(res) else 1)
