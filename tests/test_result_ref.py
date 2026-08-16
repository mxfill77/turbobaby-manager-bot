"""АДРЕС РЕЗУЛЬТАТА ШАГА — поле очереди заведено, сведено к КАНОНУ, и оно ИНЕРТНО (16.08.2026).

КАНОН, назначенный Штабом и обязательный ОБЕИМ полосам, — `[result_ref: <вид> <указатель>]`:
ключ латиницей, после вида разделитель ПРОБЕЛ, виды `commit · file · row · brain ·
service_start`. Разделитель именно пробел: указатель вправе нести двоеточие внутри себя
(виндовый путь соседней полосы), и деление по двоеточию порвало бы его пополам — поэтому
указатель с двоеточием стоит в наборе как ОБЯЗАТЕЛЬНЫЙ случай, а не как экзотика.

Пункт 1 контракта третьего исхода (узел мозга `orchestrator_plan`, раздел записан 16.08.2026).
Заход заводит МЕСТО, куда адрес можно положить, и ничего сверх этого: вердикт шага не тронут,
третьего исхода нет, правила «нет адреса — нет зелёного» нет.

ТРИ ЗАМКА, и они тут главное:
  A. СТАРЫЙ ПУТЬ ЖИВ — создание, взятие и закрытие шага БЕЗ адреса идут байт-в-байт как до
     правки. Проверяется ЧИСЛОМ: тело каждого запроса к мосту и каждая сохранённая строка
     очереди сравниваются с прежними посимвольно.
  B. НОВОЕ ПОЛЕ ЖИВЁТ — записанный адрес читается НАЗАД дословно. Именно назад: сверяется не
     возврат `attach`, а то, что вернул ЧИТАЮЩИЙ путь очереди из СОХРАНЁННОЙ строки.
  C. ОТРИЦАТЕЛЬНЫЙ ТЕСТ — адрес, по которому ничего нет, НИЧЕГО не меняет в исходе шага. Два
     слоя: поведение (терминал шага с кривым адресом и без него совпадает посимвольно) и
     устройство (по адресу некому сходить — ни один судящий модуль его не импортирует, а у
     самого решения нет рук).

ФИКСТУРА ОЧЕРЕДИ СНЯТА С ПРОДА (правило 8 свода среды): `SheetQueue` — порт живого
`bridge_prod/BotData.js` (enqueueTask_ / getPending_ / claimTask_ / completeTask_), включая
девять колонок `QUEUE_HEADERS` и урезку `String(p.task_text || '').slice(0, 5000)`. Именно эта
урезка и делает «тело режется под адрес» не теорией.

ЗАПУСК — ЖИВОЙ ФОРМАТ ГЕЙТА: `venv/bin/python3 tests/test_result_ref.py` (gate.py гоняет
каждый тест ровно так, отдельным процессом; ненулевой код возврата = красное).
"""
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
# Изоляция от боевого .env — принудительно (демон делает load_dotenv при импорте и иначе
# затащит боевые флаги в тест).
os.environ["PLAN_ADAPT"] = "0"
os.environ["CURATOR"] = "0"
os.environ["CARD_DUTY"] = "0"
os.environ["STEP_SELFHEAL"] = "0"
os.environ["CURATOR_STATE"] = "0"
os.environ["CHAIN_SERIES"] = "0"
os.environ["DELIVER_CARD"] = "0"
os.environ["ORCH_TEST_MODE"] = "1"
os.environ["MEM_MIN_MB"] = "0"
# КАНАЛ 2 ИЗОЛЯЦИИ ПРОБ (правило CLAUDE.md): четыре имени + каталог маркеров ВСЕГДА, даже если
# тест маркеров не пишет — иначе однажды напишет и попадёт в боевой /tmp/cc_guard_block.
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["PRETOOL_TEST_RUN"] = "1"
os.environ["PRETOOL_BLOCK_DIR"] = "/tmp/cc_guard_block_test"

import ast
import json

import result_ref as RR
import bridge_client as BC

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return c


# ═══════════════════════════════════════════════════════════════════════════════════════
#  ЛИСТ ОЧЕРЕДИ, СНЯТЫЙ С ПРОДА (bridge_prod/BotData.js)
# ═══════════════════════════════════════════════════════════════════════════════════════
QUEUE_HEADERS = ["id", "created", "from", "task_text", "status",
                 "result", "approved_by", "updated", "lane"]
SHEET_CAP = 5000          # enqueueTask_: String(p.task_text || '').slice(0, 5000)
NOW = "2026-08-16T04:57:00.000Z"


class SheetQueue:
    """Девять колонок и та же урезка, что у моста. Хранит СТРОКИ, а не объекты: читающий путь
    обязан собирать ответ из сохранённого, иначе «читать назад» ничего не доказывает."""

    def __init__(self):
        self.rows = []
        self.nid = 0

    # --- enqueueTask_ ---
    def enqueue(self, payload):
        self.nid += 1
        lane = str(payload.get("lane") or "").strip().lower() or "vps"
        self.rows.append([
            self.nid, NOW,
            str(payload.get("from") or "")[:120],
            str(payload.get("task_text") or "")[:SHEET_CAP],
            "new", "", "", NOW, lane,
        ])
        return {"ok": True, "id": self.nid, "lane": lane}

    # --- queueRowObj_ ---
    @staticmethod
    def _obj(values):
        return {h: values[i] for i, h in enumerate(QUEUE_HEADERS)}

    def _find(self, tid):
        for r in self.rows:
            if str(r[0]) == str(tid):
                return r
        return None

    # --- getPending_ ---
    def get_pending(self, status="new", lane="vps"):
        sts = [s.strip() for s in str(status).split(",") if s.strip()]
        items = [self._obj(r) for r in reversed(self.rows)
                 if r[4] in sts and (lane == "all" or (r[8] or "vps") == lane)]
        return {"ok": True, "items": items, "statuses": sts, "lane": lane}

    # --- claimTask_ ---
    def claim(self, tid):
        r = self._find(tid)
        if r is None:
            return {"ok": False, "error": "not_found"}
        if r[4] != "new":
            return {"ok": False, "error": "already_claimed", "status": r[4]}
        r[4] = "in_progress"
        r[7] = NOW
        return {"ok": True, "task": self._obj(r)}

    # --- completeTask_ ---
    def complete(self, tid, status, result=""):
        r = self._find(tid)
        if r is None:
            return {"ok": False, "error": "not_found"}
        if status not in ("done", "failed"):
            return {"ok": False, "error": "bad_status"}
        r[4] = status
        r[5] = str(result or "")[:SHEET_CAP]
        r[7] = NOW
        return {"ok": True}


def wire(client, sheet, calls):
    """Транспорт клиента → лист. Записывает ТЕЛО каждого запроса дословно — им и меряется,
    изменился ли старый путь."""

    def _post(action, **fields):
        calls.append(("POST", action, json.dumps(fields, ensure_ascii=False, sort_keys=True)))
        if action == "enqueue_task":
            return sheet.enqueue(fields)
        if action == "claim_task":
            return sheet.claim(fields.get("id"))
        if action == "complete_task":
            return sheet.complete(fields.get("id"), fields.get("status"), fields.get("result"))
        return {"ok": True}

    def _call(action, **params):
        calls.append(("GET", action, json.dumps(params, ensure_ascii=False, sort_keys=True)))
        if action == "get_pending":
            return sheet.get_pending(params.get("status", "new"), params.get("lane", "vps"))
        return {"ok": True}

    client._post = _post
    client._call = _call
    return client


def fresh():
    sheet, calls = SheetQueue(), []
    return sheet, calls, wire(BC.BridgeClient(), sheet, calls)


# ═══════════════════════════════════════════════════════════════════════════════════════
#  (1) ФОРМА ПОЛЯ: пять видов, пустое значение, кривой адрес не глотается
# ═══════════════════════════════════════════════════════════════════════════════════════
print("\n(1) ФОРМА ПОЛЯ")

ok(sorted(RR.KINDS) == ["brain", "commit", "file", "row", "service_start"],
   "пять видов адреса из контракта, шестого нет")

# Указатель с ДВОЕТОЧИЕМ внутри — обязательный случай канона, а не экзотика: на соседней полосе
# это виндовый путь. Деление по двоеточию порвало бы его пополам; канон делит по ПРОБЕЛУ.
_WIN = r"C:\Users\Filipp\turbobaby\pc_orchestrator.py"

_SAMPLES = [
    ("commit", "a3cf244"),
    ("file", _WIN),
    ("row", "очередь[10]: колонка result"),
    ("brain", "orchestrator_plan §КОНТРАКТ ТРЕТЬЕГО ИСХОДА: пункт 1"),
    ("service_start", "orchestrator-daemon > a3cf244"),
]
_round = 0
for k, p in _SAMPLES:
    line = RR.render(k, p)
    got = RR.parse("тело ТЗ\n" + line)
    if got == {"kind": k, "pointer": p}:
        _round += 1
ok(_round == len(_SAMPLES), f"каждый вид разбирается назад дословно ({_round}/{len(_SAMPLES)})")

ok(RR.render("", "") == "", "ничего не названо → пустая строка (адрес не назван)")
ok(RR.parse("обычное ТЗ без всякого адреса") is None, "текста адреса нет → None, не выдумка")
ok(RR.parse("[result_ref: выдумка что-то]") is None,
   "вид не латиницей адресом не считается (и разбор не падает)")
ok(RR.parse("[result_ref: sheet_cell A1]") is None,
   "неизвестный ЛАТИНСКИЙ вид адресом не считается (разбор идёт дальше, а не падает)")

# ── КАНОН ДОСЛОВНО ────────────────────────────────────────────────────────────────────────
# Канон назначен Штабом 16.08.2026 и обязателен обеим полосам: ключ латиницей, после вида —
# ПРОБЕЛ. Голден стоит на литерале: разойдётся форма — тест скажет это прямо, а не «где-то».
ok(RR.render("commit", "a3cf244") == "[result_ref: commit a3cf244]",
   "маркер записан каноном дословно: [result_ref: <вид> <указатель>]")

ok(RR.parse("тело ТЗ\n" + RR.render("file", _WIN)) == {"kind": "file", "pointer": _WIN},
   "указатель с ДВОЕТОЧИЕМ внутри вернулся ДОСЛОВНО (по двоеточию не делим)")
ok(RR.render("file", _WIN) == "[result_ref: file " + _WIN + "]",
   "виндовый путь стоит в маркере целиком, одним куском")

# ДВЕ ПРЕЖНИЕ ФОРМЫ АДРЕСОМ НЕ СЧИТАЮТСЯ. Совместимость не нужна и это ЗАМЕРЕНО (16.08.2026,
# читающий снимок живой очереди, все семь статусов, lane=all): вызовов, пишущих адрес, — 0;
# строк очереди с адресом — 0 из 6. Понимать по-старому нечего, а две формы означали бы два
# способа сказать одно ровно там, где пункт 3 контракта требует одного.
ok(RR.parse("[адрес результата: commit a3cf244]") is None,
   "прежняя форма ЭТОЙ полосы (7f147a0) адресом не считается: 0 живых строк, понимать нечего")
ok(RR.parse("commit:a3cf244") is None,
   "форма СОСЕДНЕЙ полосы (6cb2a70) «вид:указатель» адресом не считается")
ok(RR.parse("[result_ref: service a3cf244]") is None,
   "вид «service» соседней полосы не из контракта — пятый вид зовётся service_start")
ok(sorted(RR.KINDS)[4] == "service_start",
   "пятый вид назван каноном: service_start")

_raised = 0
for bad in [("выдумка", "x"), ("commit", ""), ("commit", "a\nb"), (None, "x")]:
    try:
        RR.render(*bad)
    except ValueError:
        _raised += 1
ok(_raised == 4, f"кривой адрес бросает ValueError, а не глотается ({_raised}/4)")

ok(RR.as_pair(None) == ("", "")
   and RR.as_pair(("commit", "a3cf244")) == ("commit", "a3cf244")
   and RR.as_pair({"kind": "commit", "pointer": "a3cf244"}) == ("commit", "a3cf244"),
   "адрес принимается парой и словарём (прочитанный переносится одним действием)")

# Тело режется ПОД адрес, а не адрес под тело.
_long = "я" * SHEET_CAP
_att = RR.attach(_long, "commit", "a3cf244")
ok(len(_att) <= SHEET_CAP and RR.parse(_att) == {"kind": "commit", "pointer": "a3cf244"}
   and RR.TRIM_NOTE in _att,
   "длинное ТЗ: адрес уцелел, урезано ТЕЛО, и урезка названа видимой пометкой")

_twice = RR.attach(RR.attach("ТЗ", "commit", "aaa"), "file", "/tmp/x")
ok(_twice.count("[result_ref:") == 1 and RR.parse(_twice)["kind"] == "file",
   "повторная запись заменяет адрес, а не удваивает его")


# ═══════════════════════════════════════════════════════════════════════════════════════
#  (2) ЗАМОК A: СТАРЫЙ ПУТЬ ЖИВ — создание, взятие, закрытие БЕЗ адреса
# ═══════════════════════════════════════════════════════════════════════════════════════
print("\n(2) ЗАМОК A — СТАРЫЙ ПУТЬ ЖИВ (без адреса)")

TEXTS = [
    "тз: почини рендер карточки байка",
    "[шаг 3/5 родитель 42] прогони гейт и закоммить",
    "[конверт одобренной заявки 77] исполнить пункты владельца",
    "[куратор цели 19, шаг 2] проверить живой факт",
    "многострочное ТЗ\nвторая строка\nтретья строка",
    "",
    "я" * SHEET_CAP,
    "хвост похож на адрес, но им не является: [result_ref: sheet_cell A1]",
    "и прежняя форма этой полосы — тоже просто текст: [адрес результата: commit a3cf244]",
]

sheet, calls, bc = fresh()
same_body, same_row = 0, 0
for t in TEXTS:
    calls.clear()
    r = bc.enqueue_task("Filipp-328-dev", t)
    # Тело запроса — РОВНО прежнее: from + task_text, без единого нового ключа и без правки текста.
    body = json.loads(calls[0][2])
    if body == {"from": "Filipp-328-dev", "task_text": t}:
        same_body += 1
    row = sheet._find(r["id"])
    if row[3] == t[:SHEET_CAP]:
        same_row += 1
ok(same_body == len(TEXTS),
   f"создание: тело запроса байт-в-байт прежнее ({same_body}/{len(TEXTS)} текстов, новых ключей 0)")
ok(same_row == len(TEXTS),
   f"создание: сохранённая строка очереди байт-в-байт прежняя ({same_row}/{len(TEXTS)})")
ok(all(RR.parse(r[3]) is None for r in sheet.rows),
   "ни у одной задачи без адреса поле не появилось само собой")

# Взятие и закрытие — этих путей правка не касалась вовсе; проверяем их тем же измерением.
calls.clear()
tid = sheet.rows[0][0]
cl = bc.claim_task(tid)
cl_body = json.loads(calls[0][2])
ok(cl["ok"] and cl_body == {"id": tid}, "взятие: тело запроса прежнее (id и только id)")
ok(cl["task"]["task_text"] == TEXTS[0], "взятие: текст шага доехал дословно")

calls.clear()
bc.complete_task(tid, "done", "сводка: сделано")
co_body = json.loads(calls[0][2])
ok(co_body == {"id": tid, "status": "done", "result": "сводка: сделано"},
   "закрытие: тело запроса прежнее (id/status/result)")
ok(sheet._find(tid)[4] == "done" and sheet._find(tid)[5] == "сводка: сделано",
   "закрытие: строка очереди закрылась как прежде")

# Девять колонок остались девятью: поле НЕ добавляло колонку в лист.
ok(all(len(r) == 9 for r in sheet.rows),
   "лист очереди по-прежнему несёт РОВНО 9 колонок (десятой не заводили)")


# ═══════════════════════════════════════════════════════════════════════════════════════
#  (3) ЗАМОК B: НОВОЕ ПОЛЕ ЖИВЁТ — записанное читается НАЗАД дословно
# ═══════════════════════════════════════════════════════════════════════════════════════
print("\n(3) ЗАМОК B — АДРЕС ЧИТАЕТСЯ НАЗАД")

sheet, calls, bc = fresh()
ids = {}
for k, p in _SAMPLES:
    r = bc.enqueue_task("Filipp-328-dev", f"тз: работа вида {k}", result_ref=(k, p))
    ids[r["id"]] = (k, p)

# ЧИТАЕМ НАЗАД: не возврат функции, а ответ ЧИТАЮЩЕГО пути очереди, собранный из сохранённых
# строк листа.
back = bc.get_pending("new")
byid = {it["id"]: it for it in back["items"]}
literal = 0
for tid, (k, p) in ids.items():
    got = RR.of_task(byid[tid])
    if got == {"kind": k, "pointer": p}:
        literal += 1
ok(literal == len(ids), f"адрес прочитан назад ДОСЛОВНО из строки очереди ({literal}/{len(ids)})")

# И через второй читающий путь — claim_task (демон читает шаг именно им).
tid0 = sorted(ids)[0]
ok(RR.of_task(bc.claim_task(tid0)["task"]) == {"kind": ids[tid0][0], "pointer": ids[tid0][1]},
   "тот же адрес виден и при взятии шага (claim_task)")

# Тело ТЗ при этом уцелело целиком.
ok(RR.strip_ref(byid[tid0]["task_text"]) == f"тз: работа вида {ids[tid0][0]}",
   "тело ТЗ под адресом не пострадало")

# Адрес переносится в новый шаг одним действием — прочитанный словарь кладётся как есть.
carried = bc.enqueue_task("Filipp-328-dev", "тз: продолжение", result_ref=RR.of_task(byid[tid0]))
ok(RR.parse(sheet._find(carried["id"])[3]) == {"kind": ids[tid0][0], "pointer": ids[tid0][1]},
   "прочитанный адрес переносится в новый шаг без ручной распаковки")

# Длинное ТЗ: адрес обязан пережить урезку МОСТА (slice 5000), а не пропасть молча.
r_long = bc.enqueue_task("Filipp-328-dev", "я" * SHEET_CAP, result_ref=("commit", "a3cf244"))
stored = sheet._find(r_long["id"])[3]
ok(len(stored) <= SHEET_CAP and RR.parse(stored) == {"kind": "commit", "pointer": "a3cf244"},
   "у ТЗ в потолок длиной адрес уцелел ПОСЛЕ урезки моста")

# ТО ЖЕ — для указателя С ДВОЕТОЧИЕМ: обязательный случай канона обязан пережить урезку моста
# целиком, а не «до двоеточия».
r_win = bc.enqueue_task("Filipp-328-dev", "я" * SHEET_CAP, result_ref=("file", _WIN))
stored_win = sheet._find(r_win["id"])[3]
ok(len(stored_win) <= SHEET_CAP and RR.parse(stored_win) == {"kind": "file", "pointer": _WIN},
   "указатель с двоеточием уцелел ДОСЛОВНО после урезки моста")

# И через второй читающий путь, из СОХРАНЁННОЙ строки: канон читается назад всеми пятью видами.
_back2 = bc.get_pending("new,in_progress")     # шаг tid0 выше уже взят — он в in_progress
_by2 = {it["id"]: it for it in _back2["items"]}
_kinds_back = {RR.of_task(_by2[t])["kind"] for t in ids if RR.of_task(_by2[t])}
ok(_kinds_back == set(RR.KINDS),
   f"из очереди прочитаны назад ВСЕ пять видов канона ({len(_kinds_back)}/5)")

# Кривой адрес не уезжает в очередь молча: ValueError ДО сети, задача не создана.
calls.clear()
_before = len(sheet.rows)
try:
    bc.enqueue_task("Filipp-328-dev", "тз: что-то", result_ref=("выдумка", "x"))
    _loud = False
except ValueError:
    _loud = True
ok(_loud and len(sheet.rows) == _before and not calls,
   "кривой адрес → ValueError ДО сети: ни запроса, ни строки в очереди")


# ═══════════════════════════════════════════════════════════════════════════════════════
#  (4) ЗАМОК C: ОТРИЦАТЕЛЬНЫЙ ТЕСТ — адрес в никуда НИЧЕГО не меняет
# ═══════════════════════════════════════════════════════════════════════════════════════
print("\n(4) ЗАМОК C — ПОЛЕ ИНЕРТНО (адрес, по которому ничего нет)")

# Адреса намеренно ведут в пустоту: такого коммита нет в origin/main, такого файла нет на диске.
BOGUS = ("commit", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
BOGUS_FILE = ("file", "/tmp/такого-файла-нет-и-не-будет-16082026")

import orchestrator_daemon as OD


class FakeBridge:
    """Очередь оркестратора в памяти — контракт как у Bridge (BotData.js)."""

    def __init__(self):
        self.rows, self.nid = {}, 100

    def enqueue_task(self, frm, txt, lane=None, dedup_key=None, result_ref=None):
        self.nid += 1
        self.rows[self.nid] = {"id": self.nid, "from": frm, "task_text": txt, "status": "new",
                               "result": "", "updated": NOW}
        return {"ok": True, "id": self.nid}

    def get_pending(self, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        items = [dict(r) for r in sorted(self.rows.values(), key=lambda x: -x["id"])
                 if r["status"] in sts]
        return {"ok": True, "items": items}

    def claim_task(self, tid, lane=None):
        r = self.rows.get(int(tid))
        if not r:
            return {"ok": False, "error": "not_found"}
        if r["status"] != "new":
            return {"ok": False, "error": "already_claimed", "status": r["status"]}
        r["status"], r["updated"] = "in_progress", NOW
        return {"ok": True, "task": dict(r)}

    def complete_task(self, tid, status, result=""):
        r = self.rows.get(int(tid))
        r["status"], r["result"], r["updated"] = status, result, NOW
        return {"ok": True}

    def set_needs_approval(self, tid, what):
        r = self.rows.get(int(tid))
        r["status"], r["result"], r["updated"] = "needs_approval", what, NOW
        return {"ok": True}

    def task_heartbeat(self, tid):
        return {"ok": True}

    def issue_write_ticket(self):
        return {"ok": True, "ticket": "t"}

    def consume_write_ticket(self, tk):
        return {"ok": True}

    def log_write(self, **kw):
        return {"ok": True}


class FakeProc:
    def __init__(self, out, rc=0):
        self.stdout, self.stderr, self.returncode = out, "", rc


class FakePopen:
    def __init__(self, out="", rc=0):
        self.returncode = None
        self._out, self._rc = out, rc

    def communicate(self, timeout=None):
        if self.returncode is None:
            self.returncode = self._rc
        return self._out, ""

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9

    def poll(self):
        return self.returncode


_real_run, _real_POPEN = OD.subprocess.run, OD._POPEN
_real_MAX = OD.MAX_CLAUDE_PROCS
OD.MAX_CLAUDE_PROCS = 0          # отключить proc-gate (живых claude нет)


def fake_run(args, **kw):
    return FakeProc("ok")


def fake_popen(args, **kw):
    return FakePopen(fake_popen.out, fake_popen.rc)


fake_popen.out, fake_popen.rc = "сводка: сделано", 0
OD.subprocess.run = fake_run
OD._POPEN = fake_popen

STEP = "[шаг 2/4 родитель 77] прогнать гейт и закоммитить правку"


def terminal(task_text, out="сводка: сделано", rc=0):
    """Один шаг сквозь ЖИВОЙ путь демона → (статус, результат) из строки очереди."""
    fb = FakeBridge()
    OD.bc = fb
    if hasattr(OD, "_summarized"):
        OD._summarized.clear()
    fake_popen.out, fake_popen.rc = out, rc
    tid = fb.enqueue_task("Filipp-328-dev", task_text)["id"]
    OD.process_new()
    r = fb.rows[tid]
    return r["status"], r["result"]

try:
    for label, out, rc in [("зелёный шаг", "сводка: сделано", 0),
                           ("упавший шаг", "", 1)]:
        plain = terminal(STEP, out, rc)
        with_ref = terminal(RR.attach(STEP, *BOGUS), out, rc)
        with_file = terminal(RR.attach(STEP, *BOGUS_FILE), out, rc)
        # Тот же адрес в никуда, но С ДВОЕТОЧИЕМ в указателе: канон обязан быть инертным и здесь.
        with_win = terminal(RR.attach(STEP, "file", _WIN), out, rc)
        ok(plain[0] == with_ref[0] == with_file[0] == with_win[0],
           f"{label}: статус тот же, что без адреса ({plain[0]})")
        ok(plain[1] == with_ref[1] == with_file[1] == with_win[1],
           f"{label}: результат шага СОВПАЛ посимвольно ({len(plain[1])} симв.)")
finally:
    OD.subprocess.run = _real_run
    OD._POPEN = _real_POPEN
    OD.MAX_CLAUDE_PROCS = _real_MAX

# УСТРОЙСТВО, А НЕ ОБЕЩАНИЕ: по названному адресу СЕГОДНЯ некому сходить.
REPO = "/root/turbobaby-manager-bot"
importers = []
for fname in sorted(os.listdir(REPO)):
    if not fname.endswith(".py") or fname == "result_ref.py":
        continue
    try:
        with open(os.path.join(REPO, fname), encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError):
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name == "result_ref" for a in node.names):
            importers.append(fname)
        elif isinstance(node, ast.ImportFrom) and node.module == "result_ref":
            importers.append(fname)
ok(sorted(set(importers)) == ["bridge_client.py"],
   f"адрес импортирует РОВНО одна дверь записи, и ни один судья: {sorted(set(importers))}")

with open(os.path.join(REPO, "orchestrator_daemon.py"), encoding="utf-8") as f:
    daemon_src = f.read()
ok(daemon_src.count("result_ref") == 0,
   "orchestrator_daemon.py не знает об адресе ни одним словом (вердикт шага не тронут)")

# Страж чистоты: у решения нет рук, чтобы сходить по адресу.
import invariants_check as IC

ok(any(name == "RESULT_REF_PURE" for name, _ in IC.CHECKS),
   "страж RESULT_REF_PURE зарегистрирован в гейте")

_run = IC.CheckRun("RESULT_REF_PURE")
IC.check_result_ref_pure(None, _run)
ok(not _run.findings,
   f"страж зелёный на живом модуле: у решения нет рук ({_run.findings})")

# И тот же страж КРАСНЕЕТ, если руки появятся — иначе зелёное ничего не стоит.
_probe = os.path.join("/root/turbobaby-manager-bot/_scratch_resultref_0816", "_hands_probe.py")
with open(_probe, "w", encoding="utf-8") as f:
    f.write("import subprocess\ndef go():\n    return subprocess.run(['git', 'log'])\n")
_IC_PATH_REAL = IC._RESULT_REF_PATH
IC._RESULT_REF_PATH = _probe
_run2 = IC.CheckRun("RESULT_REF_PURE")
IC.check_result_ref_pure(None, _run2)
IC._RESULT_REF_PATH = _IC_PATH_REAL
ok(len(_run2.findings) >= 1,
   f"страж краснеет на модуле с руками ({len(_run2.findings)} находок) — зелёное доказательно")

print("\n" + "=" * 70)
print(f"ИТОГ: {sum(res)}/{len(res)} PASS")
if not all(res):
    sys.exit(1)
