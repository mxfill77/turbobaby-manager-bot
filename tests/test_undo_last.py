"""ОТМЕНА ПОСЛЕДНЕЙ ЗАПИСИ ОБСЛУЖИВАНИЯ (14.08.2026).

ЖИВОЙ СЛУЧАЙ, на котором стоят голдены (splinter.log, тема 83, XADV 750 GREY 2478):
    11:15:32  → ТО XADV 750 GREY 2478: oil_last(I)=17900 interval=5000
    11:17:51  → ТО фаза2 запись по «да» @turbophuket1: written=['oil'] failed=[] odo=24997
    11:20:39  → мозг: «Не верно, моторное масло на 24500»              (через 2 м 48 с)
    11:21:29  → ТО фаза2 запись по «да» @turbophuket1: written=['oil'] failed=[] odo=24997
Человек сказал дословно «последняя запись неверна» — система записала то же число ВТОРОЙ раз.

Что доказывается:
    (1) ОБЪЕКТ    собирается из РАСПИСКИ моста (дословные ответы из журнала), лишних обращений
                  к мосту нет; нуль в `old_*` объектом НЕ является (нуль по неразбору);
    (2) ЗАМКИ     только последняя · только своя (тема+токен) · окно 3 ч · отмена отмены;
    (3) ДВЕ ПОЛОВИНЫ ответ человеку RU+TH из ОДНОГО вердикта, у каждого исхода обе;
    (4) КАРТОЧКА  названный объект (байк · регистр · строка · было → станет) и ЧЕМ возврат
                  возможен: кол.I — ветка исправления, кол.J/K/L — мост не умеет вовсе;
    (5) СКВОЗНОЕ  живая дверь splinter: квитанция с кнопкой → нажатие → карточка владельцу,
                  и в живую таблицу НЕ уходит ни одного вызова;
    (6) НЕ ИЗОБРАЖАЕМ возможности: объекта нет → кнопки нет вовсе;
    (7) ОТКАТ     `SERVICE_UNDO=0` → ни журнала, ни кнопки, путь записи байт-в-байт прежний;
    (8) ГРАНИЦА   у решения импортов ноль (ast), а в ветке отмены нет ни одного вызова записи.
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
# Сеть в тестах не дёргаем НИКОГДА: мок-счётчик стоит ДО токена и до сети (`notify._test_mode`).
COUNT_FILE = "/tmp/tb_undo_notify_count.txt"
os.environ["NOTIFY_COUNT_FILE"] = COUNT_FILE

import fleet_cell
import undo_last as U
import splinter as S

CHAT = -1002751134848
TOPIC = 83
BIKE_2478 = "XADV 750CC GREY BKK 2478"
BIKE_4957 = "NMAX 155CC GREEN-B PHUKET 4957"
LBL = S._SP_KIND_LABEL

#: ДОСЛОВНАЯ расписка живого журнала (31.07 07:31:50, байк 4957).
R_OIL_4957 = {"action": "set_fleet_oil", "ok": True, "number": "4957",
              "bike_name": BIKE_4957, "row": 16, "old_oil": 30800, "new_oil": 37000,
              "verified": True,
              "full_address": "1ZBCmVvzoFu7X0td7O5T5xSJplK8m8h9wvdESBc0a1EE | Лист1 | I16",
              "_status": 200}
#: Расписка живого случая 15.07 (числа — из двух дословных строк журнала: oil_last(I)=17900 и odo=24997).
R_OIL_2478 = {"action": "set_fleet_oil", "ok": True, "number": "2478", "bike_name": BIKE_2478,
              "row": 22, "old_oil": 17900, "new_oil": 24997, "verified": True,
              "full_address": "1ZBC… | Лист1 | I22", "_status": 200}
#: Расписка планового ТО (форма — `setFleetService_` 461-463 задеплоенного ReadFleet.js).
R_ABS_4957 = {"action": "set_fleet_service", "ok": True, "number": "4957",
              "bike_name": BIKE_4957, "row": 16, "kind": "abs", "column": 11,
              "old_km": 30800, "new_km": 37015, "verified": True,
              "full_address": "1ZBC… | Лист1 | K16"}

FAILS = 0
TOTAL = 0


def ok(name, cond, detail=""):
    global FAILS, TOTAL
    TOTAL += 1
    if cond:
        print(f"  ✅ {name}")
    else:
        FAILS += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def col(kind):
    """Буква колонки — тем же путём, каким её берут руки splinter."""
    import write_fact
    return fleet_cell.FIELD_COL.get(write_fact.field_for(kind), "")


# ═══════════════ (1) ОБЪЕКТ ИЗ РАСПИСКИ ═══════════════

def sec_object():
    print("\n(1) объект берётся из расписки моста")
    p, why = U.position("oil", col("oil"), R_OIL_2478, want_km=24997)
    ok("ГОЛДЕН 2478: позиция названа", p is not None, why)
    ok("ГОЛДЕН 2478: убираем 24997", p and p["new"] == 24997)
    ok("ГОЛДЕН 2478: возвращаем на 17900", p and p["old"] == 17900)
    ok("ГОЛДЕН 2478: регистр кол.I", p and p["column"] == "I")
    ok("ГОЛДЕН 2478: строка 22", p and p["row"] == 22)

    p2, _ = U.position("abs", col("abs"), R_ABS_4957, want_km=37015)
    ok("плановое ТО: кол.K", p2 and p2["column"] == "K", str(p2))
    ok("плановое ТО: 37015 → 30800", p2 and (p2["new"], p2["old"]) == (37015, 30800))

    # нуль по неразбору: пусто · не число · настоящий ноль — мост схлопывает в один 0
    z = dict(R_OIL_4957, old_oil=0)
    p3, why3 = U.position("oil", "I", z, want_km=37000)
    ok("нуль в old_* объектом НЕ является", p3 is None and "нул" in why3, why3)
    p4, why4 = U.position("oil", "I", {"ok": False, "error": "receipt_unknown"}, want_km=37000)
    ok("расписки нет → объекта нет", p4 is None, why4)
    p5, why5 = U.position("oil", "I", dict(R_OIL_4957), want_km=37001)
    ok("расписка о ДРУГОМ числе → не наша запись", p5 is None and "37000" in why5, why5)
    p6, _ = U.position("oil", "I", {"ok": True, "new_oil": 100, "old_oil": 100})
    ok("прежнее = новое → отменять нечего", p6 is None)
    p7, _ = U.position("oil", "I", "не словарь")
    ok("ответ не словарь → объекта нет", p7 is None)


# ═══════════════ (2) ЗАМКИ ═══════════════

def entry(tok=1, ts=1000.0, pos=None, blind=0, asked=False):
    p = pos if pos is not None else [U.position("oil", "I", R_OIL_2478, 24997)[0]]
    e = U.act(tok, ts, CHAT, TOPIC, BIKE_2478, "2478", "@turbophuket1", 24997, p, blind)
    e["asked"] = asked
    return e


def sec_locks():
    print("\n(2) замки: последняя · своя · окно 3 ч · отмена отмены")
    e = entry()
    ok("свежая последняя → карточка",
       U.verdict(e, 1, 1, 1000.0 + 60)["state"] == U.STATE_CARD)
    ok("после неё была ещё запись → не последняя",
       U.verdict(e, 1, 2, 1000.0 + 60)["state"] == U.STATE_NONE)
    ok("журнала нет (рестарт бота) → нечего отменять",
       U.verdict(None, 1, 1, 1000.0)["state"] == U.STATE_NONE)
    ok("чужой токен → нечего отменять",
       U.verdict(e, 7, 7, 1000.0 + 60)["state"] == U.STATE_NONE)
    ok("окно 3 ч живо на 2 ч 59 мин",
       U.verdict(e, 1, 1, 1000.0 + 3 * 3600 - 60)["state"] == U.STATE_CARD)
    ok("старше 3 ч → отказ, и он назван stale",
       U.verdict(e, 1, 1, 1000.0 + 3 * 3600 + 1)["state"] == U.STATE_STALE)
    ok("окно ровно 3 часа числом", U.TTL_DEFAULT == 3 * 3600)
    ok("отмена отмены запрещена",
       U.verdict(entry(asked=True), 1, 1, 1000.0 + 60)["state"] == U.STATE_ASKED)
    ok("позиций нет → карточки не будет (blind)",
       U.verdict(entry(pos=[]), 1, 1, 1000.0 + 60)["state"] == U.STATE_BLIND)
    ok("время не разобрано → в отказ, не в карточку",
       U.verdict(entry(ts="никогда"), 1, 1, 1000.0)["state"] == U.STATE_STALE)


# ═══════════════ (3) ОБЕ ПОЛОВИНЫ ═══════════════

def sec_halves():
    print("\n(3) ответ человеку: обе половины из одного вердикта")
    e = entry()
    cases = [("карточка", U.verdict(e, 1, 1, 1060.0)),
             ("старше окна", U.verdict(e, 1, 1, 1000.0 + 4 * 3600)),
             ("не последняя", U.verdict(e, 1, 2, 1060.0)),
             ("уже отправлено", U.verdict(entry(asked=True), 1, 1, 1060.0)),
             ("объект не назван", U.verdict(entry(pos=[]), 1, 1, 1060.0))]
    for name, v in cases:
        th, ru = U.reply(v, LBL)
        ok(f"{name}: тайская половина не пуста и без кириллицы",
           bool(th.strip()) and not any("а" <= c.lower() <= "я" for c in th), th)
        ok(f"{name}: русская половина не пуста", bool(ru.strip()))
        ok(f"{name}: половины РАЗНЫЕ строки", th != ru)
    th, ru = U.reply(U.verdict(e, 1, 1, 1000.0 + 4 * 3600), LBL)
    ok("отказ по окну НАЗЫВАЕТ объект (чтобы донесли владельцу сами)",
       "24997" in ru and "17900" in ru, ru)
    th_c, ru_c = U.reply(U.verdict(e, 1, 1, 1060.0), LBL)
    ok("карточка: человеку сказано, что таблицу бот не правит",
       "не правл" in ru_c.lower(), ru_c)


# ═══════════════ (4) КАРТОЧКА ВЛАДЕЛЬЦУ ═══════════════

def sec_card():
    print("\n(4) карточка владельцу: названный объект + чем возврат возможен")
    v = U.verdict(entry(), 1, 1, 1060.0)
    c = U.card(v, asked_by="@earth", labels=LBL)
    for what, frag in (("байк", "2478"), ("регистр", "кол.I"), ("строка", "строка 22"),
                       ("какое число убираем", "24997"), ("на что возвращаем", "17900"),
                       ("кто просит", "@earth"), ("живая таблица названа", "ЖИВАЯ ТАБЛИЦА")):
        ok(f"карточка называет {what}", frag in c, c[:200])
    ok("карточка говорит, что бот НЕ писал", "НЕ ПИСАЛ" in c)
    ok("масло: назван путь возврата (ветка исправления)", "исправлен" in c, c)

    v2 = U.verdict(entry(pos=[U.position("abs", "K", R_ABS_4957, 37015)[0]]), 1, 1, 1060.0)
    c2 = U.card(v2, asked_by="@earth", labels=LBL)
    ok("плановое ТО: сказано, что мост понижения НЕ умеет", "НЕ умеет" in c2, c2)
    ok("плановое ТО: назван km_decreasing", "km_decreasing" in c2)
    ok("возможность не изображается: у J/K/L своя формулировка",
       U.how_back("abs") != U.how_back("oil"))

    v3 = U.verdict(entry(blind=2), 1, 1, 1060.0)
    ok("частичный объект назван ЧИСЛОМ (позиции без прежнего значения)",
       "2" in U.card(v3, "@earth", LBL).split("Ещё позиций в этой записи:")[-1][:6],
       U.card(v3, "@earth", LBL))
    ok("нет карточки там, где нет вердикта карточки",
       U.card(U.verdict(entry(), 1, 2, 1060.0), "@earth", LBL) == "")


# ═══════════════ (5)(6)(7) СКВОЗНОЕ НА ЖИВОМ КОДЕ SPLINTER ═══════════════

SENDS = []


async def _rec_send(context, *, chat_id, text, message_thread_id=None, reply_markup=None, **kw):
    SENDS.append((text, reply_markup))


S._send = _rec_send
S._send_retry = _rec_send


class FakeBridge:
    """Мост-фикстура (форма — tests/test_odo_ceiling.py) + ДОСЛОВНЫЕ расписки записи."""

    def __init__(self, oil_answer=None, svc_answer=None, sp=None):
        self.oil_answer = oil_answer if oil_answer is not None else dict(R_OIL_2478)
        self.svc_answer = svc_answer if svc_answer is not None else dict(R_ABS_4957)
        self.sp = sp
        self.closed = False
        self.oil_calls, self.svc_calls, self.upserts, self.events = [], [], [], []

    def service_list(self):
        return {"ok": True, "items": [{"bike": BIKE_2478, "current_km": "24000",
                                       "updated_at": "2026-07-15T11:15:32"}]}

    def set_fleet_oil(self, number, oil_km, confirmed=False):
        self.oil_calls.append((number, oil_km, confirmed))
        return dict(self.oil_answer)

    def set_fleet_service(self, number, kind, km, confirmed=False):
        self.svc_calls.append((number, kind, km, confirmed))
        return dict(self.svc_answer)

    def service_upsert(self, **kw):
        self.upserts.append(kw)
        return {"ok": True, "next_km": 29997, "status": "ok"}

    def add_event(self, **kw):
        self.events.append(kw)
        return {"ok": True}

    def service_pending_get(self, chat_id, topic_id, bike):
        if self.sp and not self.closed:
            return {"ok": True, "item": dict(self.sp)}
        return {"ok": False, "error": "not_found"}

    def service_pending_upsert(self, **kw):
        return {"ok": True}

    def service_pending_close(self, **kw):
        self.closed = True
        return {"ok": True}

    def find_bike(self, q):
        return {"name": q}

    def fleet(self, cells=False):
        return {"ok": True, "data": {"bikes": []}}

    @staticmethod
    def cell(bike, field):
        return fleet_cell.read(bike, field)


class FakeQ:
    def __init__(self, data, uname="earth"):
        self.data = data
        self.from_user = type("U", (), {"username": uname, "id": 7})()
        self.message = type("M", (), {"chat_id": CHAT, "message_thread_id": TOPIC})()
        self.markup_cleared = False

    async def answer(self, *a, **k):
        pass

    async def edit_message_reply_markup(self, **k):
        self.markup_cleared = True

    async def edit_message_text(self, *a, **k):
        pass


def _upd(q):
    return type("Upd", (), {"callback_query": q})()


def run(c):
    return asyncio.run(c)


def reset(flag=None):
    SENDS.clear()
    S._SVC_TOKENS.clear()
    S._SVC_WRITE_DEDUP.clear()
    S._SVC_UNDO.clear()
    S._SVC_UNDO_LAST.clear()
    S._TOPIC_BIKE_OVERRIDE[(CHAT, TOPIC)] = BIKE_2478
    S._TOPIC_NAMES[(CHAT, TOPIC)] = BIKE_2478
    os.environ["ODO_CEILING_KM"] = "0"        # верхняя граница — чужая цель, её не трогаем
    if flag is None:
        os.environ.pop(U.FLAG_ENV, None)
    else:
        os.environ[U.FLAG_ENV] = flag
    try:
        os.remove(COUNT_FILE)
    except OSError:
        pass


def door_button(b, odo="24997", done=("oil",), uname="Pleummmm"):
    tok = S._svc_put({"chat": CHAT, "topic": TOPIC, "bike": BIKE_2478,
                      "done": list(done), "odo": odo, "kind": "sp_done"})
    run(S.handle_service_button(_upd(FakeQ(f"svc:done:{tok}", uname)), context=None, bridge=b))


def undo_kb():
    """Токен кнопки отмены с ПОСЛЕДНЕЙ квитанции, либо None."""
    for text, kb in reversed(SENDS):
        if kb is not None:
            for row in kb.inline_keyboard:
                for btn in row:
                    if btn.callback_data.startswith("svc:undo:"):
                        return int(btn.callback_data.split(":")[2])
    return None


def counted():
    try:
        with open(COUNT_FILE, encoding="utf-8") as f:
            return [ln for ln in f.read().splitlines() if ln.strip()]
    except OSError:
        return []


def sec_live():
    print("\n(5) сквозное: живая дверь → кнопка → карточка владельцу")
    reset()
    b = FakeBridge()
    door_button(b)
    ok("запись прошла (дверь не тронута)", b.oil_calls == [("2478", 24997, True)], str(b.oil_calls))
    tok = undo_kb()
    ok("на квитанции появилась кнопка отмены", tok is not None, str(SENDS))
    ok("подпись кнопки двуязычная", "Запись неверна" in U.BUTTON_LABEL
       and "บันทึกผิด" in U.BUTTON_LABEL)

    writes_before = (len(b.oil_calls), len(b.svc_calls), len(b.events), len(b.upserts))
    q = FakeQ(f"svc:undo:{tok}")
    run(S.handle_service_button(_upd(q), context=None, bridge=b))
    ok("ЖИВАЯ ТАБЛИЦА НЕ ТРОНУТА нажатием",
       (len(b.oil_calls), len(b.svc_calls), len(b.events), len(b.upserts)) == writes_before)
    card = counted()
    ok("карточка ушла владельцу РОВНО одна", len(card) == 1, str(card))
    ok("карточка красная и с байком", card and "ЖИВАЯ ТАБЛИЦА" in card[0] and "2478" in card[0],
       str(card))
    ok("человеку ответили обеими половинами",
       SENDS and "🇹🇭" in SENDS[-1][0] and "🇷🇺" in SENDS[-1][0], str(SENDS[-1:]))
    ok("кнопка с квитанции снята", q.markup_cleared)

    # отмена отмены
    q2 = FakeQ(f"svc:undo:{tok}")
    run(S.handle_service_button(_upd(q2), context=None, bridge=b))
    ok("повтор карточки НЕ шлёт (отмена отмены)", len(counted()) == 1, str(counted()))
    ok("повтору сказано, что уже отправлено", "Уже отправил" in SENDS[-1][0], SENDS[-1][0])

    # новая запись делает прежнюю кнопку не последней
    reset()
    b2 = FakeBridge()
    door_button(b2)
    old_tok = undo_kb()
    b2.oil_answer = dict(R_OIL_2478, old_oil=24997, new_oil=25500)
    SENDS.clear()
    door_button(b2, odo="25500")
    new_tok = undo_kb()
    ok("вторая запись — свой токен", new_tok is not None and new_tok != old_tok)
    run(S.handle_service_button(_upd(FakeQ(f"svc:undo:{old_tok}")), context=None, bridge=b2))
    ok("старая кнопка отвечает «не последняя»", "не последняя" in SENDS[-1][0], SENDS[-1][0])
    ok("карточки по старой кнопке НЕ было", len(counted()) == 0, str(counted()))


def sec_no_object():
    print("\n(6) объекта нет → кнопки нет вовсе")
    reset()
    b = FakeBridge(oil_answer=dict(R_OIL_2478, old_oil=0))
    door_button(b)
    ok("прежнее значение нулём → кнопки нет", undo_kb() is None, str(SENDS))
    ok("запись при этом прошла как прежде", len(b.oil_calls) == 1)

    reset()
    b2 = FakeBridge(oil_answer={"ok": False, "error": "km_decreasing", "old_oil": 30000})
    door_button(b2)
    ok("мост отказал → кнопки нет", undo_kb() is None, str(SENDS))

    # объект назван у ЧАСТИ позиций: кнопка есть, недостающее названо числом
    reset()
    b3 = FakeBridge(svc_answer=dict(R_ABS_4957, old_km=0))
    door_button(b3, done=("oil", "abs"))
    tok = undo_kb()
    ok("часть позиций названа → кнопка есть", tok is not None)
    e = S._SVC_UNDO.get(tok) or {}
    ok("неназванная позиция сосчитана", e.get("blind") == 1, str(e))
    # мок-счётчик режет строку на 200 символах, поэтому тело карточки судим целиком
    body = U.card(U.verdict(e, tok, tok, e.get("ts", 0) + 60), "@earth", LBL)
    ok("карточка называет позиции БЕЗ прежнего значения", "НЕ вошли" in body, body)
    run(S.handle_service_button(_upd(FakeQ(f"svc:undo:{tok}")), context=None, bridge=b3))
    ok("карточка ушла", len(counted()) == 1, str(counted()))


def sec_rollback():
    print("\n(7) откат SERVICE_UNDO=0 — путь байт-в-байт прежний")
    reset(flag="0")
    b = FakeBridge()
    door_button(b)
    ok("кнопки нет", undo_kb() is None, str(SENDS))
    ok("журнал пуст", not S._SVC_UNDO)
    ok("запись прошла как прежде", b.oil_calls == [("2478", 24997, True)])
    ok("квитанция та же (обе половины)", SENDS and "🇹🇭" in SENDS[-1][0] and "🇷🇺" in SENDS[-1][0])
    ok("ручка: пусто → ветка жива", U.enabled("") and U.enabled(None))
    ok("ручка: 0/off/no → мертва",
       not U.enabled("0") and not U.enabled("off") and not U.enabled("нет"))
    reset()


# ═══════════════ (8) ГРАНИЦА УСТРОЙСТВОМ ═══════════════

WRITE_NAMES = ("set_fleet_oil", "set_fleet_service", "add_event", "edit_event", "delete_event",
               "service_upsert", "add_transaction", "closing_upsert")


def sec_purity():
    print("\n(8) граница устройством")
    import invariants_check as IC
    src = open(os.path.join(ROOT, "undo_last.py"), encoding="utf-8").read()
    ok("у решения импортов НОЛЬ", IC._duty_ast_findings(src, allowed=frozenset()) == [])
    ok("страж видит грязь", IC._duty_ast_findings("import requests\n", allowed=frozenset()) != [])
    ok("инвариант зарегистрирован", "UNDO_LAST_PURE" in [n for n, _ in IC.CHECKS])

    tree = ast.parse(open(os.path.join(ROOT, "splinter.py"), encoding="utf-8").read())
    fn = [n for n in ast.walk(tree)
          if isinstance(n, ast.AsyncFunctionDef) and n.name == "_svc_undo_ask"]
    ok("ветка отмены найдена в splinter", len(fn) == 1)
    calls = [n.func.attr for n in ast.walk(fn[0]) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)]
    ok("в ветке отмены НЕТ ни одного вызова записи",
       not [c for c in calls if c in WRITE_NAMES], str(calls))
    ok("ветка отмены зовёт дверь инбокса (карточка ЖДЁТ ответа)", "send_card" in calls, str(calls))


def main():
    print("═══ ОТМЕНА ПОСЛЕДНЕЙ ЗАПИСИ ОБСЛУЖИВАНИЯ ═══")
    sec_object()
    sec_locks()
    sec_halves()
    sec_card()
    sec_live()
    sec_no_object()
    sec_rollback()
    sec_purity()
    try:
        os.remove(COUNT_FILE)                      # свой черновик во временном каталоге
    except OSError:
        pass
    print(f"\nИТОГ: {TOTAL - FAILS}/{TOTAL}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
