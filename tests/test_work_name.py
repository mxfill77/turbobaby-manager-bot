"""В ИСТОРИЮ ОБСЛУЖИВАНИЯ ПИШЕТСЯ НАЗВАННАЯ РАБОТА, А НЕ ЯРЛЫК (14.08.2026).

ЖИВОЙ СЛУЧАЙ, на котором стоят голдены (splinter.log, чат -1002751134848, NMAX RED WHITE 9548):
    14.08 09:05:26  → ТО фаза2 разбор: status=ждёт_факт works=['замена аккумулятора']
                      done=['abs', 'other'] odo=- completed=False
    14.08 11:38:21  → ТО фаза2 запись по числу-да @turbophuket1: written=['abs', 'other']
                      failed=[] odo=36474 исход=written
Механик сделал замену аккумулятора и СКАЗАЛ ЭТО ДОСЛОВНО. В историю ушло «прочие работы».
Соседняя дверь по ТОМУ ЖЕ байку писать дословно умеет и умела (01.08 04:37:36-40:
«замена передних тормозных колодок — 36394 км», «замена ручек руля — 36394 км»).

ЗАМЕР (реплей ЖИВЫМ классификатором по splinter.log 01.06–14.08, 74 суток): записей фазы 2 — 16,
ярлыком в историю ушло 3, и у 2 из 3 механик работу НАЗЫВАЛ словами (14.08 «замена
аккумулятора» → «прочие работы»; 01.08 четыре тормозные работы → «тормозные колодки»).

Что доказывается:
    (1) РЕШЕНИЕ   названа → её слова; не названа → ярлык, БАЙТ-В-БАЙТ прежняя строка;
    (2) ЧУЖИЕ СЛОВА в чужую строку не попадают: вид судит ЖИВОЙ `_service_kind`;
    (3) ДВЕРЬ     сквозь живой `splinter._sp_write_done`: в историю уходит «замена
                  аккумулятора — 36474 км». С 23.08.2026 ключ строки КОНТЕНТНЫЙ, а не по виду
                  (решение владельца «строка на каждую работу») — дедуп доказывается
                  поведением: та же работа другими словами даёт ТУ ЖЕ строку;
    (4) РАСЧЁТ НЕ СЛОМАН: колоночная ветка (кол. I/J/K/L) не изменена ни одним вызовом и НЕ
                  платит ни одного лишнего обращения к мосту (счётчик вызовов, не обещание);
    (5) ОТКАТ     `WORK_NAME=0` → прежний ярлык и слова не читаются вовсе;
    (6) FAIL-SAFE мост молчит · сегмента слов нет · классификатор споткнулся → ярлык;
    (7) ГРАНИЦА   у решения импортов ноль (ast) и ни одного вызова записи.
"""
import ast
import asyncio
import os
import sys

# Корень — ОТ ФАЙЛА (ловушка метода 07.08: чужой боевой корень в sys.path зеленит прогон «до»).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != "/root/turbobaby-manager-bot"] \
    if ROOT != "/root/turbobaby-manager-bot" else sys.path
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["NOTIFY_COUNT_FILE"] = "/tmp/tb_workname_notify_count.txt"
os.environ.pop("WORK_NAME", None)          # дефолт ветки — жива
os.environ["SERVICE_UNDO"] = "0"           # соседний механизм из предмета этого сьюта исключён

import work_name as W
import splinter as S

CHAT = -1002751134848
TOPIC = 79
BIKE = "NMAX 155CC RED WHITE PHUKET 9548"
ODO = 36474
LBL = S._SP_KIND_LABEL
KIND = S._service_kind                      # ЖИВОЙ классификатор, не копия правил

#: ДОСЛОВНО из живого журнала 14.08 09:05:26.
SAID_9548 = ["замена аккумулятора"]
#: ДОСЛОВНО из живого журнала 01.08 08:00 (байк NMAX 155 GREY 5960, четыре работы вида pads).
SAID_5960 = ["замена тормозной жидкости спереди", "замена тормозной жидкости сзади",
             "замена передних тормозных колодок", "замена задних тормозных колодок"]

OK = FAIL = 0


def check(name, cond):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


def note(kind, said, on=True):
    return W.history_note(kind, said, ODO, LBL, KIND, on=on)


# ═══════════════ (1) РЕШЕНИЕ — В ОБЕ СТОРОНЫ, НА ЖИВОМ СЛУЧАЕ ═══════════════
print("\n(1) решение: работа названа → её слова; не названа → ярлык")

v = note("other", SAID_9548)
check("9548: названа → в историю идут слова механика",
      v["text"] == "замена аккумулятора — 36474 км")
check("9548: названа → named=True, источник назван", v["named"] and v["source"] == "слова механика")
check("9548: ярлыка «прочие работы» в строке НЕТ", "прочие работы" not in v["text"])

v0 = note("other", [])
check("не названа → ярлык (байт-в-байт прежняя строка)", v0["text"] == "прочие работы — 36474 км")
check("не названа → named=False и это видно", (not v0["named"]) and v0["source"] == "ярлык")
check("не названа → причина названа словами", "словами не назвал" in v0["why"])

v1 = note("chain", [])
check("31.07 цепь без слов → «цепь — 36474 км» как прежде", v1["text"] == "цепь — 36474 км")

vp = note("pads", SAID_5960)
check("01.08 pads: идут ВСЕ четыре названные работы того вида",
      all(w in vp["text"] for w in SAID_5960) and vp["named"])
check("01.08 pads: порядок сказанного сохранён",
      vp["text"].index(SAID_5960[0]) < vp["text"].index(SAID_5960[3]))


# ═══════════════ (2) ЧУЖИЕ СЛОВА В ЧУЖУЮ СТРОКУ НЕ ПОПАДАЮТ ═══════════════
print("\n(2) вид судит живой классификатор: слова чужого вида в строку не идут")

MIX = ["замена моторного масла", "замена аккумулятора", "замена масла в редукторе"]
check("живой классификатор: «замена аккумулятора» → other", KIND("замена аккумулятора") == "other")
check("живой классификатор: «замена моторного масла» → oil", KIND("замена моторного масла") == "oil")

vm = note("other", MIX)
check("смешанное сообщение: в строку other идёт ТОЛЬКО аккумулятор",
      vm["text"] == "замена аккумулятора — 36474 км")
check("смешанное: слов про масло в строке other нет", "масл" not in vm["text"])
check("слова вида oil сюда не приходят вовсе — колоночный путь этой ветки не знает",
      W.words_of("oil", MIX, KIND) == ["замена моторного масла"])

check("дубли слов снимаются", W.words_of("other", SAID_9548 * 3, KIND) == SAID_9548)
check("пустые/пробельные слова отбрасываются", W.words_of("other", ["", "   ", None], KIND) == [])
check("слова есть, но НЕ этого вида → ярлык",
      note("chain", SAID_9548)["text"] == "цепь — 36474 км")

long_words = ["замена аккумулятора " + "и подрамника " * 30]
vl = note("other", long_words)
check("длинные слова урезаются под потолок соседней двери", len(vl["text"]) <= W.NOTE_CAP)
check("километры при урезке НЕ теряются", vl["text"].endswith(" — 36474 км"))


# ═══════════════ (3)(4)(5)(6) ЖИВАЯ ДВЕРЬ SPLINTER ═══════════════
print("\n(3)(4) живая дверь _sp_write_done: история, msg_id, колоночный расчёт")

SENDS = []


async def _rec_send(context, *, chat_id=None, text="", message_thread_id=None, **kw):
    SENDS.append(text)


S._send = _rec_send
S._send_retry = _rec_send


class FakeBridge:
    """Мост-фикстура. `calls` — ВСЕ обращения по порядку: «лишних обращений ноль» доказывается
    сравнением списка, а не комментарием."""

    def __init__(self, note_text=None, sp_ok=True):
        self.note_text = note_text
        self.sp_ok = sp_ok
        self.calls, self.events, self.upserts = [], [], []
        self.oil_calls, self.svc_calls = [], []

    def set_fleet_oil(self, number, oil_km, confirmed=False):
        self.calls.append("set_fleet_oil")
        self.oil_calls.append((number, oil_km, confirmed))
        return {"ok": True, "number": number, "old_oil": 30800, "new_oil": oil_km}

    def set_fleet_service(self, number, kind, km, confirmed=False):
        self.calls.append("set_fleet_service")
        self.svc_calls.append((number, kind, km, confirmed))
        return {"ok": True, "number": number, "old_km": 30800, "new_km": km}

    def service_upsert(self, **kw):
        self.calls.append("service_upsert")
        self.upserts.append(kw)
        return {"ok": True}

    def add_event(self, **kw):
        self.calls.append("add_event")
        self.events.append(kw)
        return {"ok": True}

    def service_pending_get(self, chat_id, topic_id, bike):
        self.calls.append("service_pending_get")
        if not self.sp_ok:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "item": {"bike": bike, "note": self.note_text or ""}}

    def service_pending_close(self, **kw):
        self.calls.append("service_pending_close")
        return {"ok": True}

    def service_list(self):
        self.calls.append("service_list")
        return {"ok": True, "items": []}

    def find_bike(self, q):
        self.calls.append("find_bike")
        return {"name": BIKE}

    def fleet(self, cells=False):
        self.calls.append("fleet")
        return {"ok": True, "data": {"bikes": []}}


_WORDS_READS = []          # сколько раз дверь ходила к заявке ЗА СЛОВАМИ


def run_done(bridge, done, works=None):
    """Прогон живой двери фазы 2. Чтения ЗА СЛОВАМИ считаются точечно — спаем на
    `_sp_words_said`, а не по числу `service_pending_get`: с 23.08 у той же двери есть ВТОРОЕ,
    законное чтение — дверь вердикта спрашивает, есть ли что закрывать, ПЕРЕД тем как писать
    (иначе слепой close дописывал строку-эхо). Считать оба обращения одним счётчиком значило бы
    мерить не свой предмет: слова читаются ровно так же лениво, как читались."""
    _WORDS_READS.clear()
    _real = S._sp_words_said

    def _spy(*a, **kw):
        _WORDS_READS.append(1)
        return _real(*a, **kw)
    S._sp_words_said = _spy
    try:
        return asyncio.run(
            S._sp_write_done(None, bridge, CHAT, TOPIC, BIKE, done, str(ODO),
                             confirmed_by="@turbophuket1", ceiling_ok=True, works=works))
    finally:
        S._sp_words_said = _real


NOTE_9548 = S._sp_note_set_works("", SAID_9548)
check("фикстура: сегмент WORKS собран живым кодом splinter", "замена аккумулятора" in NOTE_9548)

b = FakeBridge(note_text=NOTE_9548)
written, failed = run_done(b, ["other"])
ev = b.events[0] if b.events else {}
check("дверь: запись состоялась", written == ["other"] and not failed)
check("дверь: в историю ушли СЛОВА механика",
      ev.get("notes") == "замена аккумулятора — 36474 км")
# ГОЛДЕН ПЕРЕВЁРНУТ 23.08.2026 ПО РЕШЕНИЮ ВЛАДЕЛЬЦА, а не потому что «покраснел». Прежде здесь
# стояло `msg_id == sp:{chat}:{topic}:{вид}:{км}` — ОДИН ключ на весь вид, и шапка `work_name`
# называла это забором идемпотентности. Забор НЕ СНЯТ, он ПЕРЕЕХАЛ на КОНТЕНТНЫЙ ключ работы
# (`info:{plate}:{_work_key}:{км}` — идиома соседней двери `_write_info_works`): ключ стал
# СТРОЖЕ (пять работ дают пять строк, а не одну склеенную), а СВОЙСТВО, ради которого забор
# стоял, доказывается прямо ниже — не формой ключа, а поведением.
check("дверь: ключ строки КОНТЕНТНЫЙ — строка на РАБОТУ, а не на вид",
      str(ev.get("msg_id", "")).startswith("info:9548:"))
_da = FakeBridge(note_text=S._sp_note_set_works("", ["замена тормозных колодок"]))
run_done(_da, ["pads"])
_db = FakeBridge(note_text=S._sp_note_set_works("", ["поменял колодки"]))
run_done(_db, ["pads"])
check("дверь: ДЕДУП ЦЕЛ — та же работа ДРУГИМИ словами даёт ТОТ ЖЕ ключ",
      _da.events[0]["msg_id"] == _db.events[0]["msg_id"])
check("дверь: а РАЗНЫЕ работы — РАЗНЫЕ ключи (склейки в одну строку больше нет)",
      _da.events[0]["msg_id"] != ev.get("msg_id"))
check("дверь: пробег в строке события прежний", ev.get("mileage") == str(ODO))
check("дверь: адрес события прежний",
      ev.get("event_type") == "repair" and ev.get("group") == f"обслуживание / тема {TOPIC}")

b2 = FakeBridge(note_text=NOTE_9548)
written2, _ = run_done(b2, ["other"], works=SAID_9548)
check("слова переданы дверью 2 → за словами к заявке НЕ ходим",
      not _WORDS_READS and b2.events[0]["notes"].startswith("замена аккумулятора"))

# --- (4) расчёт не сломан: колоночная ветка ---
bcol = FakeBridge(note_text=NOTE_9548)
wcol, fcol = run_done(bcol, ["oil", "gear", "abs", "airfilter"])
check("колоночные виды записаны все четыре", wcol == ["oil", "gear", "abs", "airfilter"] and not fcol)
check("кол.I: set_fleet_oil с confirmed=True и тем же числом",
      bcol.oil_calls == [("9548", ODO, True)])
check("кол.J/K/L: set_fleet_service по ВИДУ и тем же числом",
      [(k, km, c) for _n, k, km, c in bcol.svc_calls] ==
      [("gear", ODO, True), ("abs", ODO, True), ("airfilter", ODO, True)])
check("регистры считаются по ярлыку: service_upsert(service_type=вид)",
      [u["service_type"] for u in bcol.upserts] == ["oil", "gear", "abs", "airfilter"])
check("колоночный путь не пишет строк истории", bcol.events == [])
check("колоночный путь НЕ платит ни одного обращения за словами", not _WORDS_READS)

# --- (5) откат ---
os.environ["WORK_NAME"] = "0"
boff = FakeBridge(note_text=NOTE_9548)
run_done(boff, ["other"])
check("откат WORK_NAME=0: прежний ярлык байт-в-байт",
      boff.events[0]["notes"] == "прочие работы — 36474 км")
check("откат: слова не читаются вовсе (за словами к заявке не ходим)", not _WORDS_READS)
os.environ.pop("WORK_NAME", None)

# --- (6) fail-safe ---
print("\n(6) fail-safe: любая дырка в фактах → ярлык, а не пустая строка")
bfs = FakeBridge(sp_ok=False)
run_done(bfs, ["other"])
check("мост молчит о заявке → ярлык", bfs.events[0]["notes"] == "прочие работы — 36474 км")

bfs2 = FakeBridge(note_text="escalated | что-то без сегмента работ")
run_done(bfs2, ["other"])
check("сегмента WORKS нет → ярлык", bfs2.events[0]["notes"] == "прочие работы — 36474 км")


def boom(_w):
    raise RuntimeError("классификатор споткнулся")


check("классификатор бросил → слово молчит, идёт ярлык",
      W.history_note("other", SAID_9548, ODO, LBL, boom)["text"] == "прочие работы — 36474 км")
check("словаря ярлыков нет → вид называет сам себя",
      W.history_note("other", [], ODO, {}, KIND)["text"] == "other — 36474 км")
check("километров нет → строка всё равно называет работу",
      W.history_note("other", SAID_9548, "", LBL, KIND)["text"] == "замена аккумулятора")


# ═══════════════ (7) ГРАНИЦА УСТРОЙСТВОМ ═══════════════
print("\n(7) граница: у решения импортов ноль и ни одного вызова записи")

SRC = open(os.path.join(ROOT, "work_name.py"), encoding="utf-8").read()
TREE = ast.parse(SRC)
imports = [n for n in ast.walk(TREE) if isinstance(n, (ast.Import, ast.ImportFrom))]
check("импортов ровно ноль — спросить мир нечем", imports == [])
banned = {"open", "exec", "eval", "compile", "__import__", "print", "input"}
bad = [n.func.id for n in ast.walk(TREE)
       if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in banned]
check("ни одного вызова записи/исполнения/печати", bad == [])
check("страж чистоты зарегистрирован в гейте",
      "WORK_NAME_PURE" in open(os.path.join(ROOT, "invariants_check.py"), encoding="utf-8").read())

print(f"\nИТОГ: {OK} PASS, {FAIL} FAIL")
if FAIL:
    sys.exit(1)
