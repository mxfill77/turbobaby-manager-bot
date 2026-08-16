"""ТЕРМИНАЛ КАРТОЧКИ ПИШЕТСЯ В ЖУРНАЛ И НА ПОЛОСЕ VPS (16.08.2026, зеркало ПК-коммита cc1c779).

ЗАМЕР ДЫРЫ У СЕБЯ (журнал демона 19.06–16.08, 58 суток; журнал карточек `chain_cards.jsonl`;
журнал гарда `/tmp/cc_pretool_guard.log`; снимок живой очереди 16.08):
  · вход в красное — ПИШЕТСЯ: 4 записи рождения в журнале карточек (с 11.08) + 126 номеров
    строкой `NEEDS_APPROVAL id=` в журнале демона;
  · разрешение   — в журнал карточек НЕ пишется (0); в журнале демона видно лишь КОСВЕННО, по
    тому, что демон взялся исполнять approved (61 номер) — это след ИСПОЛНЕНИЯ, а не ответа;
  · ОТКАЗ        — НЕ ПИШЕТСЯ НИГДЕ: 0 строк в обоих журналах и в журнале демона. devbot,
    который применяет «нет», кладёт вердикт в поле `result` очереди — и тем же движением ЗАТИРАЕТ
    тело карточки;
  · истечение    — ветка hard-cap пишет строку в журнал демона; за 58 суток не срабатывала ни
    разу (0), в журнал карточек не пишет.
Терминальных записей в журнале карточек до этой правки: 0 из 13.

ЧТО ДОБАВЛЕНО (только добавление; гард не тронут ни на строку): у записи журнала появился второй
вид — ТЕРМИНАЛ (`chain_cards.end_entry`: номер · исход одним словом · время · объект операции
ярлыком семьи). Исход берётся из ДОКАЗАТЕЛЬСТВА: approved-статус очереди («разрешено»), вердикт
devbot'а в снимке failed («отказ»), собственный hard-cap («истекло»). Доказательства нет —
пишется честное «закрыто», а не догадка.

Секции:
(0) формат: терминал читается назад, дедуп, словарь исходов закрыт, рождение им НЕ подменяется
(A) ЗАМОК A — поведение прежнее: те же команды → те же классы гарда; тот же набор задач → те же
    карточки, столько же и ПОСИМВОЛЬНО те же, при слое включённом и выключенном
(B) ЗАМОК B — след появляется: все четыре исхода на ТЕСТОВЫХ карточках
(C) ЗАМОК C — отрицательный: карточка без наступившего терминала строки терминала НЕ порождает
(D) ЗАМОК D — ПДн и секреты не текут: тела команд, путей и содержимого конфигов в строке нет
(E) границы: задним числом не пишем · полоса pc не трогается · к мосту ни одного лишнего
    обращения · CARD_END_LOG=0 гасит ветку · боевые пути не тронуты ни байтом

Сети, Telegram, claude и моста нет — всё мокнуто; владельцу ничего не уходит.
"""
import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"
os.environ["PLAN_ADAPT"] = "0"
os.environ["CARD_DUTY"] = "0"
os.environ["CURATOR"] = "0"
os.environ["CHAIN_SERIES"] = "1"
os.environ["CARD_END_LOG"] = "1"
os.environ["ORCH_TEST_MODE"] = "1"
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["MEM_MIN_MB"] = "0"


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return bool(c)


res = []

import chain_cards as CC                                              # noqa: E402
import curator_ops                                                    # noqa: E402
import orchestrator_daemon as OD                                      # noqa: E402
import pretool_guard as PG                                            # noqa: E402

TMP = tempfile.mkdtemp(prefix="card_end_")
JOURNAL = os.path.join(TMP, "chain_cards.jsonl")
os.environ["CC_CARDS_FILE"] = JOURNAL
os.environ["CC_SERIES_FILE"] = os.path.join(TMP, "chain_series.json")


def now_iso(shift=0):
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(seconds=shift)).isoformat()


# ДОСЛОВНАЯ форма карточки живой очереди (тело, которое очередь затрёт вердиктом владельца).
CARD_RESTART = ("NEEDS_APPROVAL: op=other | Нужно твоё «да» на рестарт splinter: фикс лежит в "
                "origin/main и гейт зелёный, но живой процесс держит старый код.")
CARD_OIL = ("NEEDS_APPROVAL: op=other | 🔴 ЖИВАЯ ТАБЛИЦА — запись «ТО масло» set_fleet_oil "
            "в Лист1 Байки: байк 4724, 20747 км.")

print("(0) ФОРМАТ ЖУРНАЛА — у карточки два вида записи, и они не путаются")
J0 = os.path.join(TMP, "форма.jsonl")
CC.note(J0, 700, "2026-08-16T10:00:00", "vps", CC.BORN, ["service:splinter"], CARD_RESTART)
CC.note_end(J0, 700, "2026-08-16T10:31:00", "vps", CC.APPROVED, ["service:splinter"])
j = CC.load(J0)
e = CC.ends(J0)
res.append(ok(set(j["cards"]) == {700} and j["cards"][700]["src"] == CC.BORN,
              "(0) рождение осталось рождением: терминал его НЕ подменил (контракт замера цел)"))
res.append(ok(set(e) == {700} and e[700]["end"] == CC.APPROVED,
              "(0) терминал читается назад по своему номеру: исход «%s»" % e[700]["end"]))
res.append(ok(e[700]["ops"] == ["service:splinter"] and e[700]["at"] == "2026-08-16T10:31:00"
              and e[700]["id"] == 700,
              "(0) строка несёт номер, исход, время и объект операции"))
res.append(ok("head" not in e[700] and set(e[700]) == {"id", "at", "lane", "end", "ops"},
              "(0) поля для свободного текста в терминале НЕТ вовсе: %s" % sorted(e[700])))
CC.note_end(J0, 700, "2026-08-16T11:00:00", "vps", CC.CLOSED, [])
res.append(ok(len(CC.ends(J0)) == 1 and CC.ends(J0)[700]["end"] == CC.APPROVED,
              "(0) у карточки один конец: доказанный исход не перебивается поздним «закрыто»"))
bad = False
try:
    CC.note_end(J0, 701, "2026-08-16T11:00:00", "vps", "как-то так", [])
except ValueError:
    bad = True
res.append(ok(bad and 701 not in (CC.ends(J0) or {}),
              "(0) словарь исходов ЗАКРЫТ: слово вне него не пишется, а бросает"))
res.append(ok(CC.ends(os.path.join(TMP, "нет-такого.jsonl")) is None,
              "(0) журнала нет → None («не прочитан»), а не пустой словарь"))
res.append(ok(set(CC.OUTCOMES) == {"разрешено", "отказ", "истекло", "закрыто"},
              "(0) исходов ЧЕТЫРЕ, и четвёртый — честное незнание: %s" % (CC.OUTCOMES,)))

# ── общая машинерия прогона демона (образец tests/test_card_origin.py) ───────────────────────
GUARD_DIR = os.path.join(TMP, "guard")
os.makedirs(GUARD_DIR, exist_ok=True)
OD.GUARD_BLOCK_DIR = GUARD_DIR
OD.MAX_CLAUDE_PROCS = 0
OD._series_commits = lambda lo, hi: []                 # git в тесте не зовём
OD._series_units_now = lambda: {}
OD._truthful_fail = lambda tid, base, code, **kw: base  # правда статуса читает git — не наш предмет
TEST_TOKEN = "TESTGUARDTOKEN"
if hasattr(OD, "_guard_token_new"):
    OD._guard_token_new = lambda: TEST_TOKEN


class FakeBridge:
    """Очередь в памяти. calls — ЖУРНАЛ ОБРАЩЕНИЙ: им доказывается, что слой терминала не платит
    мосту ни одного лишнего запроса. na_calls считает set_needs_approval — им проверяется, что
    число выписанных карточек не изменилось."""

    def __init__(s, rows=None):
        s.rows = {int(r["id"]): dict(r) for r in (rows or [])}
        s.nid = max(list(s.rows) + [900])
        s.na_calls, s.calls = 0, []

    def _log(s, name):
        s.calls.append(name)

    def enqueue_task(s, frm, txt, lane=None):
        s._log("enqueue_task")
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": txt, "status": "new",
                         "lane": lane or "vps", "result": "", "created": now_iso(),
                         "updated": now_iso()}
        return {"ok": True, "id": s.nid}

    def get_pending(s, status="new", lane=None):
        s._log("get_pending:" + str(status))
        sts = [x.strip() for x in str(status).split(",")]
        items = [dict(r) for r in sorted(s.rows.values(), key=lambda x: -int(x["id"]))
                 if r["status"] in sts and (lane in (None, "vps", "all")
                                            or r.get("lane") == lane)]
        if lane in (None, "vps"):
            items = [i for i in items if (i.get("lane") or "vps") == "vps"]
        return {"ok": True, "items": items}

    def get_pending_multi(s, statuses, lane=None):
        return s.get_pending(",".join(statuses), lane=lane)

    def claim_task(s, tid, lane=None):
        s._log("claim_task")
        r = s.rows.get(int(tid))
        if not r or r["status"] != "new":
            return {"ok": False, "error": "already_claimed"}
        r["status"], r["updated"] = "in_progress", now_iso()
        return {"ok": True, "task": dict(r)}

    def complete_task(s, tid, status, result=""):
        s._log("complete_task")
        r = s.rows.get(int(tid))
        if not r:
            return {"ok": False, "error": "not_found"}
        r["status"], r["result"], r["updated"] = status, result, now_iso()
        return {"ok": True}

    def set_needs_approval(s, tid, what):
        s._log("set_needs_approval")
        s.na_calls += 1
        r = s.rows.get(int(tid))
        r["status"], r["result"], r["updated"] = "needs_approval", what, now_iso()
        return {"ok": True}

    def task_heartbeat(s, tid):
        return {"ok": True}

    def issue_write_ticket(s):
        return {"ok": True, "ticket": "t-test"}

    def consume_write_ticket(s, tk):
        return {"ok": True}

    def log_write(s, **kw):
        return {"ok": True}


class FakePopen:
    """Мок claude -p: печатает заданный stdout; маркер гарда кладём ВНУТРИ прогона, как хук."""

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


fake = {"out": "", "rc": 0, "on_run": None}
OD._POPEN = lambda *a, **kw: FakePopen(fake["out"], fake["rc"], fake["on_run"])
OD.subprocess.run = lambda *a, **kw: type("P", (), {"stdout": "ok", "stderr": "", "returncode": 0})()


def write_marker(tid, hit, card):
    with open(os.path.join(GUARD_DIR, "%s.json" % tid), "w", encoding="utf-8") as f:
        json.dump({"task_id": str(tid), "hit": hit, "card": card, "token": TEST_TOKEN}, f,
                  ensure_ascii=False)


def reset_layer():
    OD._CARD_OPEN.clear()
    OD._CARD_END_PENDING.clear()
    OD._CARD_ENDED.clear()


def run_new(fb, text, out, marker=None):
    """Поставить задачу и прогнать ОДИН process_new (карточка родится, если гард дал маркер)."""
    fake["out"], fake["rc"] = out, 0
    tid = fb.enqueue_task("Filipp-328-dev", text)["id"]
    fake["on_run"] = (lambda: write_marker(tid, marker[0], marker[1])) if marker else None
    OD.process_new()
    fake["on_run"] = None
    return tid


print("(A) ЗАМОК A — ПОВЕДЕНИЕ ПРЕЖНЕЕ")
# A1. Гард. Правки в нём нет ни на строку — и это проверяется его же решениями на живых формах.
CORPUS = [
    ("systemctl stop splinter", "block", "proc_hard_block"),
    ("rm -f /root/turbobaby-manager-bot/bot.py", "red", "delete_file"),
    ("systemctl restart splinter", "green", ""),
    ("grep -n ПРАВИЛО /root/turbobaby-manager-bot/CLAUDE.md", "green", ""),
]
for cmd, kind_want, hit_want in CORPUS:
    kind, hit, _blob = PG.classify(cmd, REPO)
    res.append(ok(kind == kind_want and hit == hit_want,
                  "(A1) «%s» → класс %s/%s, как и был" % (cmd[:46], kind, hit or "—")))
src_pg = open(os.path.join(REPO, "pretool_guard.py"), encoding="utf-8").read()
res.append(ok("card_end" not in src_pg and "note_end" not in src_pg and "chain_cards" not in src_pg,
              "(A1) в гарде нет НИ ОДНОГО имени нового слоя — он о нём не знает вовсе"))

# A2. Демон. Тот же набор задач при слое включённом и выключенном → те же карточки.
NABOR = [("правка логгера, красное в ходе", CARD_RESTART, ("set_fleet_oil", CARD_OIL)),
         ("вторая задача набора", CARD_RESTART, ("proc_ctl", CARD_RESTART)),
         ("третья задача набора", "готово, красного не было", None)]


def прогон(flag):
    os.environ["CARD_END_LOG"] = flag
    reset_layer()
    jp = os.path.join(TMP, "набор-%s.jsonl" % flag)
    os.environ["CC_CARDS_FILE"] = jp
    os.environ["CC_SERIES_FILE"] = os.path.join(TMP, "набор-%s.json" % flag)
    fb = FakeBridge()
    OD.bc = fb
    ids = [run_new(fb, t, out, marker=m) for t, out, m in NABOR]
    cards = [(fb.rows[i]["status"], fb.rows[i]["result"]) for i in ids]
    return fb, cards, jp


fb_on, cards_on, jp_on = прогон("1")
fb_off, cards_off, jp_off = прогон("0")
sha_on = hashlib.sha256(json.dumps(cards_on, ensure_ascii=False).encode()).hexdigest()
sha_off = hashlib.sha256(json.dumps(cards_off, ensure_ascii=False).encode()).hexdigest()
res.append(ok(fb_on.na_calls == fb_off.na_calls == 2,
              "(A2) карточек выписано столько же: %d при слое вкл и %d при выкл"
              % (fb_on.na_calls, fb_off.na_calls)))
res.append(ok(sha_on == sha_off,
              "(A2) статусы и ТЕКСТЫ карточек совпали ПОСИМВОЛЬНО (sha256 %s)" % sha_on[:12]))
res.append(ok([c[0] for c in cards_on] == ["needs_approval", "needs_approval", "done"],
              "(A2) классы исходов задач набора прежние: %s" % [c[0] for c in cards_on]))
res.append(ok(fb_on.calls == fb_off.calls,
              "(A2) обращений к мосту столько же и в том же порядке (%d)" % len(fb_on.calls)))
res.append(ok(CC.ends(jp_off) in (None, {}),
              "(A2) при CARD_END_LOG=0 терминалов не записано ни одного"))

print("(B) ЗАМОК B — СЛЕД ПОЯВЛЯЕТСЯ: все четыре исхода на ТЕСТОВЫХ карточках")
os.environ["CARD_END_LOG"] = "1"
os.environ["CC_CARDS_FILE"] = JOURNAL
os.environ["CC_SERIES_FILE"] = os.path.join(TMP, "chain_series.json")
reset_layer()
ROWS = [
    {"id": 901, "lane": "vps", "from": "Filipp-328-dev", "status": "needs_approval",
     "task_text": "тест-карточка: разрешение", "created": now_iso(600),
     "updated": now_iso(600), "result": CARD_RESTART},
    {"id": 902, "lane": "vps", "from": "Filipp-328-dev", "status": "needs_approval",
     "task_text": "тест-карточка: отказ", "created": now_iso(600),
     "updated": now_iso(600), "result": CARD_OIL},
    {"id": 903, "lane": "vps", "from": "Filipp-328-dev", "status": "needs_approval",
     "task_text": "тест-карточка: истечение", "created": now_iso(200000),
     "updated": now_iso(200000), "result": CARD_RESTART},
    {"id": 904, "lane": "vps", "from": "Filipp-328-dev", "status": "needs_approval",
     "task_text": "тест-карточка: исход недоказуем", "created": now_iso(600),
     "updated": now_iso(600), "result": CARD_OIL},
    {"id": 905, "lane": "vps", "from": "Filipp-328-dev", "status": "needs_approval",
     "task_text": "тест-карточка: ещё висит", "created": now_iso(60),
     "updated": now_iso(60), "result": CARD_RESTART},
]
fb = FakeBridge(ROWS)
OD.bc = fb
OD._na_reminded.clear()
OD.process_na_reminders()        # первый оборот: 903 сгорает по hard-cap, остальные живы
e = CC.ends(JOURNAL) or {}
res.append(ok(e.get(903, {}).get("end") == CC.EXPIRED,
              "(B) истечение: hard-cap 24ч оставил строку «%s»" % e.get(903, {}).get("end")))
res.append(ok(e[903]["ops"] == ["service:splinter"],
              "(B) у истёкшей названа операция карточки: %s" % e[903]["ops"]))
res.append(ok(set(e) == {903}, "(B) живые карточки терминала пока НЕ получили: %s" % sorted(e)))

fb.rows[901]["status"] = "approved"                 # владелец нажал ✅
fb.rows[902]["status"], fb.rows[902]["result"] = "failed", "отклонено Филиппом"   # нажал ❌
fb.rows[904]["status"], fb.rows[904]["result"] = "failed", "закрыта служебно"     # ушла молча
OD.process_na_reminders()        # видим уход трёх карточек — исход пока не назван ни у одной
res.append(ok(set(OD._CARD_END_PENDING) == {901, 902, 904} and 903 in OD._CARD_ENDED,
              "(B) ушедшие ждут исхода до конца оборота (%s), а закрытая демоном на второй круг "
              "не заходит" % sorted(OD._CARD_END_PENDING)))
res.append(ok(set(CC.ends(JOURNAL) or {}) == {903},
              "(B) до доказательств В ЖУРНАЛ НЕ ПИСАЛИ НИ СТРОКИ — догадка не опережает факт"))
OD.process_approved()            # доказательство «да»: статус approved ставит только девбот
OD.process_dec_tails()           # доказательство «нет»: вердикт devbot'а в снимке failed
OD._card_end_flush()             # остальным — честное «закрыто»
e = CC.ends(JOURNAL) or {}
res.append(ok(e.get(901, {}).get("end") == CC.APPROVED,
              "(B) разрешение: «%s» (доказано статусом approved)" % e.get(901, {}).get("end")))
res.append(ok(e.get(902, {}).get("end") == CC.REJECTED,
              "(B) ОТКАЗ: «%s» (доказан вердиктом devbot'а)" % e.get(902, {}).get("end")))
res.append(ok(e.get(904, {}).get("end") == CC.CLOSED,
              "(B) исход недоказуем → честное «%s», а не догадка" % e.get(904, {}).get("end")))
res.append(ok(e[902]["ops"] == ["set_fleet_oil"],
              "(B) объект отказа назван, хотя тело карточки уже затёрто вердиктом: %s"
              % e[902]["ops"]))
res.append(ok(all(e[i]["at"][:2] == "20" and len(e[i]["at"]) == 19 for i in (901, 902, 903, 904)),
              "(B) у каждой строки есть время в одной форме с рождением"))
res.append(ok(not OD._CARD_END_PENDING,
              "(B) ожидание пусто: каждая ушедшая карточка получила ровно одну строку"))

print("(C) ЗАМОК C — карточка без наступившего терминала строки НЕ порождает")
res.append(ok(905 not in (CC.ends(JOURNAL) or {}),
              "(C) висящая карточка 905 терминала не имеет — вопрос владельцу ещё открыт"))
OD.process_na_reminders()
OD.process_dec_tails()
OD._card_end_flush()
res.append(ok(905 not in (CC.ends(JOURNAL) or {}) and 905 in OD._CARD_OPEN,
              "(C) и после ещё одного полного оборота её конца в журнале нет"))
lines_before = CC._read(JOURNAL)["lines"]
OD.process_na_reminders()
OD.process_approved()
OD.process_dec_tails()
OD._card_end_flush()
res.append(ok(CC._read(JOURNAL)["lines"] == lines_before,
              "(C) пустой оборот не добавил в журнал ни одной строки (дублей терминала нет)"))

print("(D) ЗАМОК D — ПДн И СЕКРЕТЫ НЕ ТЕКУТ")
reset_layer()
JD = os.path.join(TMP, "утечка.jsonl")
os.environ["CC_CARDS_FILE"] = JD
ПРИМАНКА_ПУТЬ = "/root/приманка/ключи.conf"
ПРИМАНКА_КЛЮЧ = "AbCdEf1234567890XyZ"
ПРИМАНКА_ТЕЛО = ("NEEDS_APPROVAL: op=other | рестарт splinter после того, как "
                 "`cat %s` показал строку %s, клиент +66812345678, паспорт AA1234567"
                 % (ПРИМАНКА_ПУТЬ, ПРИМАНКА_КЛЮЧ))
fb = FakeBridge([{"id": 906, "lane": "vps", "from": "Filipp-328-dev", "status": "needs_approval",
                  "task_text": "тест-карточка: приманка", "created": now_iso(600),
                  "updated": now_iso(600), "result": ПРИМАНКА_ТЕЛО}])
OD.bc = fb
OD._na_reminded.clear()
OD.process_na_reminders()
fb.rows[906]["status"], fb.rows[906]["result"] = "failed", "отклонено Филиппом"
OD.process_na_reminders()
OD.process_dec_tails()
OD._card_end_flush()
строка = json.dumps((CC.ends(JD) or {}).get(906, {}), ensure_ascii=False)
res.append(ok((CC.ends(JD) or {}).get(906, {}).get("end") == CC.REJECTED,
              "(D) терминал приманки записан — значит проверяем ЖИВУЮ строку, а не пустоту"))
for имя, кусок in (("путь к конфигу", ПРИМАНКА_ПУТЬ), ("значение ключа", ПРИМАНКА_КЛЮЧ),
                   ("тело команды", "cat "), ("телефон клиента", "+66812345678"),
                   ("номер паспорта", "AA1234567")):
    res.append(ok(кусок not in строка, "(D) в строке терминала нет: %s" % имя))
res.append(ok((CC.ends(JD) or {})[906]["ops"] == ["service:splinter"],
              "(D) объект назван ЯРЛЫКОМ семьи операции, а не текстом: %s"
              % (CC.ends(JD) or {})[906]["ops"]))
res.append(ok(all(o in {op["key"] for op in curator_ops.occurrences(ПРИМАНКА_ТЕЛО)}
                  for o in (CC.ends(JD) or {})[906]["ops"]),
              "(D) ярлыки — из словаря curator_ops, своего вокабуляра у слоя нет"))

print("(E) ГРАНИЦЫ")
# задним числом не пишем: карточку, которой этот процесс не видел живой, терминал не догоняет
reset_layer()
JE = os.path.join(TMP, "прошлое.jsonl")
os.environ["CC_CARDS_FILE"] = JE
fb = FakeBridge([{"id": 800, "lane": "vps", "from": "Filipp-328-dev", "status": "failed",
                  "task_text": "давняя карточка", "created": now_iso(90000),
                  "updated": now_iso(90000), "result": "отклонено Филиппом"}])
OD.bc = fb
OD._na_reminded.clear()
OD.process_na_reminders()
OD.process_dec_tails()
OD._card_end_flush()
res.append(ok(CC.ends(JE) in (None, {}),
              "(E) задним числом журнал не заполняется: чужого прошлого слой не судит"))
# полоса pc: её карточки этот слой не трогает вовсе
reset_layer()
OD._pc_carded.clear()
OD._series_note_pc_cards([{"id": 601, "lane": "pc", "status": "needs_approval",
                           "task_text": "[шаг 2/3 родитель 600] правка",
                           "result": CARD_RESTART}])
res.append(ok(601 in (CC.load(JE) or {"cards": {}})["cards"] and 601 not in (CC.ends(JE) or {}),
              "(E) pc-карточка записана рождением и терминала от нас не получает"))
# МОЛЧАНИЕ МОСТА — НЕ «ВСЕ КАРТОЧКИ ЗАКРЫЛИСЬ». Снимок не прочитан → слоя не касаемся вовсе.
reset_layer()
JO = os.path.join(TMP, "мост-молчит.jsonl")
os.environ["CC_CARDS_FILE"] = JO
fb = FakeBridge([dict(ROWS[0], id=921), dict(ROWS[1], id=922)])
OD.bc = fb
OD._na_reminded.clear()
OD.process_na_reminders()
res.append(ok(set(OD._CARD_OPEN) == {921, 922}, "(E) обе карточки взяты на заметку живыми"))
fb.get_pending = lambda status="new", lane=None: {"ok": False, "error": "timeout"}
OD.process_na_reminders()
OD.process_dec_tails()
OD._card_end_flush()
res.append(ok(not OD._CARD_END_PENDING and CC.ends(JO) in (None, {}),
              "(E) мост молчит → ни одного терминала: слепота не читается как «все ответили»"))
src_od = open(os.path.join(REPO, "orchestrator_daemon.py"), encoding="utf-8").read()
res.append(ok("_card_end_watch(r.get(\"items\", []))" in src_od,
              "(E) слой кормится ТЕМ ЖЕ снимком needs_approval, который демон берёт и без него"))
res.append(ok("_card_end_rejects(r.get(\"items\", []))" in src_od,
              "(E) отказ читается из снимка failed, уже взятого process_dec_tails"))
# лишних обращений к мосту — ноль (тот же сценарий при слое вкл и выкл)
def сценарий(flag):
    os.environ["CARD_END_LOG"] = flag
    os.environ["CC_CARDS_FILE"] = os.path.join(TMP, "мост-%s.jsonl" % flag)
    reset_layer()
    OD._na_reminded.clear()
    b = FakeBridge([dict(ROWS[0], id=911), dict(ROWS[3], id=914)])
    OD.bc = b
    OD.process_na_reminders()
    b.rows[911]["status"] = "approved"
    b.rows[914]["status"], b.rows[914]["result"] = "failed", "отклонено Филиппом"
    OD.process_na_reminders()
    OD.process_approved()
    OD.process_dec_tails()
    OD._card_end_flush()
    return b.calls


calls_on, calls_off = сценарий("1"), сценарий("0")
res.append(ok(calls_on == calls_off,
              "(E) обращений к мосту при слое вкл и выкл поровну и те же: %d" % len(calls_on)))
os.environ["CARD_END_LOG"] = "1"
res.append(ok(OD._card_end_on() and not (os.environ.update({"CARD_END_LOG": "0"})
                                         or OD._card_end_on()),
              "(E) ОТКАТ: CARD_END_LOG=0 гасит ветку ДО чтения снимков"))
os.environ["CARD_END_LOG"] = "1"
# изоляция боевых путей
prod_j = os.path.join(REPO, "chain_cards.jsonl")
sha_prod = hashlib.sha256(open(prod_j, "rb").read()).hexdigest() if os.path.exists(prod_j) else "—"
os.environ.pop("CC_CARDS_FILE", None)
res.append(ok(OD._cards_file() != OD.CHAIN_CARDS_FILE,
              "(E) забыли подставить путь — изоляция сьюта держит (тест-файл, не боевой)"))
os.environ["CC_CARDS_FILE"] = JOURNAL
sha_prod2 = hashlib.sha256(open(prod_j, "rb").read()).hexdigest() if os.path.exists(prod_j) else "—"
res.append(ok(sha_prod == sha_prod2,
              "(E) боевой журнал карточек за прогон не изменился ни на байт"))
res.append(ok(open(os.path.join(REPO, "chain_cards.py"), encoding="utf-8")
              .read().count("\nimport ") == 2,
              "(E) формат журнала остался без новых зависимостей (json + os)"))

shutil.rmtree(TMP, ignore_errors=True)
for k in ("CC_CARDS_FILE", "CC_SERIES_FILE"):
    os.environ.pop(k, None)
print("\nИТОГ: %d/%d" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
