"""ВЕРХНЯЯ ГРАНИЦА ПРОБЕГА ПРИ ЗАПИСИ ОБСЛУЖИВАНИЯ (14.08.2026).

ЖИВОЙ СЛУЧАЙ — ДОСЛОВНО из splinter.log 14.08.2026, байк NMAX RED WHITE 9548:
    09:06:03  ТО фаза2 разбор: status=ждёт_факт works=[] done=['abs', 'other'] odo=367474
              completed=False text='367474'
    09:06:06  ТО фаза2 → подтверждение Пыму: NMAX RED WHITE 9548 done=['abs', 'other']
              odo=367474 (tok=1)
Текущий пробег того же байка — 36474 (живой факт того же дня: инвариант OIL_VS_CURRENT_ODO
называет «NMAX 155CC RED WHITE PHUKET 9548 … Bot Data current_km=36474»). Легло верное число
только потому, что владелец ответил СООБЩЕНИЕМ: дверь числа берёт его из текста, а дверь кнопки
взяла бы 367474 из токена. Обе двери судятся здесь ОДНИМ И ТЕМ ЖЕ живым случаем.

Что доказывается:
    (1) ЗАМОК В ОБЕ СТОРОНЫ  обычный прирост проходит МОЛЧА, десятикратный — переспрашивается;
    (2) ОБЕ ДВЕРИ            кнопка Пыма и голое число доверенного ведут себя ОДИНАКОВО
                             (в этом и был дефект: 14.08 они разошлись);
    (3) ПОРОГ                выведен замером, а не на глаз: 16750 проходит, 39103 нет;
    (4) ЧЕТЫРЕ ИСХОДА        pass / ask / unknown / off, и «неизвестно» не читается как «мимо»;
    (5) ФАЙЛ-СЕЙФ            текущий пробег не прочитан или мост упал → пишем КАК ПРЕЖДЕ;
    (6) ОТКАТ                ODO_CEILING_KM=0 → обе двери байт-в-байт как до 14.08;
    (7) ГРАНИЦЫ              убывание не тронуто, trust не ослаблен, confirmed=True на месте;
    (8) ЧИСТОТА              у решения НОЛЬ импортов и ни одной руки (ast).
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

import fleet_cell
import odo_ceiling as OC
import service_receipt as SR
import splinter as S

CHAT = -1002751134848
TOPIC = 308

#: Дословный живой случай 14.08.2026 09:06.
BIKE_9548 = "NMAX 155CC RED WHITE PHUKET 9548"
LIVE_WRONG = "367474"      # что назвал текст и что уехало в карточку Пыму
LIVE_CUR = 36474           # текущий пробег байка на тот момент
LIVE_DONE = ["abs", "other"]

FAILS = []


def ok(name, cond, detail=""):
    if cond:
        print(f"  ✅ {name}")
    else:
        FAILS.append(f"{name}: {detail}")
        print(f"  ❌ {name} — {detail}")


# ═══════════════ (1)(3)(4) РЕШЕНИЕ: замок в обе стороны и порог ═══════════════

def sec_verdict():
    print("\n(1)(3)(4) решение: замок в обе стороны, порог, четыре исхода")
    L = OC.LIMIT_DEFAULT

    # живой случай — переспрос
    v = OC.verdict(LIVE_WRONG, LIVE_CUR, L)
    ok("живой 367474 против 36474 → ask", v["state"] == OC.STATE_ASK, v)
    ok("разрыв назван числом", v["gap"] == 331000, v)

    # обычные приросты — молча (значения из замера, см. шапку odo_ceiling)
    for cur, new, d in ((36394, 36474, 80), (24094, 40844, 16750), (39374, 39374, 0),
                        (12835, 16167, 3332), (30225, 37823, 7598)):
        v = OC.verdict(new, cur, L)
        ok(f"обычный прирост {d} проходит молча", v["state"] == OC.STATE_PASS, v)

    # аномалии корпуса — все переспрашиваются
    for cur, new, d in ((12212, 51315, 39103), (17254, 57186, 39932), (39374, 84789, 45415),
                        (6429, 64289, 57860), (40844, 201445, 160601), (24302, 253708, 229406)):
        v = OC.verdict(new, cur, L)
        ok(f"аномалия {d} переспрашивается", v["state"] == OC.STATE_ASK, v)

    # граница ровно на пороге: > порога, не >=
    ok("ровно порог проходит", OC.verdict(30000 + 1000, 1000, L)["state"] == OC.STATE_PASS)
    ok("порог+1 переспрашивает", OC.verdict(30000 + 1001, 1000, L)["state"] == OC.STATE_ASK)

    # порог устойчив: любое значение из пустого промежутка даёт тот же исход
    for L2 in (16751, 20000, 25000, 30000, 39102):
        a = OC.verdict(LIVE_WRONG, LIVE_CUR, L2)["state"]
        b = OC.verdict(40844, 24094, L2)["state"]      # 16750, самый большой настоящий
        ok(f"порог {L2}: аномалия ask, настоящий pass",
           a == OC.STATE_ASK and b == OC.STATE_PASS, (a, b))

    # четвёртый и третий исходы
    ok("выключено → off", OC.verdict(LIVE_WRONG, LIVE_CUR, 0)["state"] == OC.STATE_OFF)
    ok("текущий не прочитан → unknown", OC.verdict(LIVE_WRONG, "", L)["state"] == OC.STATE_UNKNOWN)
    ok("текущий None → unknown", OC.verdict(LIVE_WRONG, None, L)["state"] == OC.STATE_UNKNOWN)
    ok("unknown НЕ равен pass (исход назван отдельно)", OC.STATE_UNKNOWN != OC.STATE_PASS)

    # убывание — чужая дверь
    ok("убывание не наша дверь", OC.verdict(3000, 36474, L)["state"] == OC.STATE_PASS)
    ok("нечитаемое число не подменяет bad_odometer",
       OC.verdict("abc", 36474, L)["state"] == OC.STATE_PASS)

    # живой формат ячейки
    ok("живой формат '36 474'", OC.km("36 474") == 36474)
    ok("живой формат '36,474'", OC.km("36,474") == 36474)

    # ручка
    ok("ручка пустая → дефолт", OC.parse_limit("") == OC.LIMIT_DEFAULT)
    ok("ручка мусор → дефолт", OC.parse_limit("тридцать") == OC.LIMIT_DEFAULT)
    ok("ручка 0 → мертва", OC.parse_limit("0") == 0)
    ok("ручка отрицательная → мертва", OC.parse_limit("-5") == 0)
    ok("ручка число → оно", OC.parse_limit("12345") == 12345)

    # обе половины вопроса несут ОБА числа
    v = OC.verdict(LIVE_WRONG, LIVE_CUR, L)
    th, ru = OC.question_th(BIKE_9548, v), OC.question_ru(BIKE_9548, v)
    for half, nm in ((th, "тайская"), (ru, "русская")):
        ok(f"{nm} половина называет оба числа",
           "367474" in half and "36474" in half, half)


# ═══════════════ СКВОЗНОЕ: обе живые двери ═══════════════

SENDS = []


async def _rec_send(context, *, chat_id, text, message_thread_id=None, **kw):
    SENDS.append(text)


async def _rec_send_retry(context, *, chat_id, text, message_thread_id=None, **kw):
    SENDS.append(text)


S._send = _rec_send
S._send_retry = _rec_send_retry


def run(c):
    return asyncio.run(c)


def reset(limit="30000"):
    SENDS.clear()
    S._SVC_TOKENS.clear()
    S._SVC_WRITE_DEDUP.clear()
    S._SP_ASK_TS.clear()
    S._TOPIC_BIKE_OVERRIDE[(CHAT, TOPIC)] = BIKE_9548
    S._TOPIC_NAMES[(CHAT, TOPIC)] = BIKE_9548
    if limit is None:
        os.environ.pop(OC.LIMIT_ENV, None)
    else:
        os.environ[OC.LIMIT_ENV] = limit


class FakeBridge:
    """Мост-фикстура (форма — из tests/test_service_receipt.py) + `service_list`: именно из него
    `_odo_current` берёт ТЕКУЩИЙ пробег, то есть M, которое судит верхняя граница."""

    def __init__(self, cur_km=LIVE_CUR, sp=None, list_raises=False):
        self.cur_km = cur_km
        self.sp = sp
        self.list_raises = list_raises
        self.closed = False
        self.oil_calls, self.svc_calls, self.upserts, self.events = [], [], [], []

    def service_list(self):
        if self.list_raises:
            raise RuntimeError("мост молчит")
        if self.cur_km is None:
            return {"ok": True, "items": []}
        return {"ok": True, "items": [{"bike": BIKE_9548, "current_km": str(self.cur_km),
                                       "updated_at": "2026-08-01T04:48:35"}]}

    def set_fleet_oil(self, number, oil_km, confirmed=False):
        self.oil_calls.append((number, oil_km, confirmed))
        return {"ok": True}

    def set_fleet_service(self, number, kind, km, confirmed=False):
        self.svc_calls.append((number, kind, km, confirmed))
        return {"ok": True}

    def service_upsert(self, **kw):
        self.upserts.append(kw)
        return {"ok": True, "next_km": 41015, "status": "ok"}

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
    def __init__(self, data, uname):
        self.data = data
        self.from_user = type("U", (), {"username": uname})()

    async def answer(self, *a, **k):
        pass

    async def edit_message_reply_markup(self, **k):
        pass

    async def edit_message_text(self, *a, **k):
        pass


def _upd(q):
    return type("Upd", (), {"callback_query": q})()


class Msg:
    def __init__(self, text, uname="Pleummmm"):
        self.text = text
        self.caption = None
        self.photo = None
        self.chat_id = CHAT
        self.message_thread_id = TOPIC
        self.message_id = 11274
        self.from_user = type("U", (), {"username": uname})()


def _wrote(b):
    return bool(b.oil_calls or b.svc_calls)


def _asked(sends):
    return any("Одометр" in t and "Точно?" in t for t in sends)


SP_WAIT = {"declared": "abs", "done": "abs", "status": "ждёт_подтверждения", "odometer": ""}


def door_button(b, odo, done=None, uname="Pleummmm"):
    tok = S._svc_put({"chat": CHAT, "topic": TOPIC, "bike": BIKE_9548,
                      "done": done or LIVE_DONE, "odo": odo, "kind": "sp_done"})
    run(S.handle_service_button(_upd(FakeQ(f"svc:done:{tok}", uname)), context=None, bridge=b))


def door_number(b, odo, uname="Pleummmm"):
    return run(S.handle_service_result(Msg(odo, uname), context=None, bridge=b,
                                       claude=None, text=odo))


# ═══════════════ (2) ОБЕ ДВЕРИ на дословном живом случае ═══════════════

def sec_doors():
    print("\n(2) обе двери: живой случай 367474 при текущем 36474")

    # ДВЕРЬ 1 — кнопка Пыма. До 14.08 записала бы 367474.
    reset()
    b = FakeBridge()
    door_button(b, LIVE_WRONG)
    ok("дверь кнопки: 367474 НЕ записан", not _wrote(b), (b.oil_calls, b.svc_calls))
    ok("дверь кнопки: переспрос отправлен", _asked(SENDS), SENDS)
    ok("дверь кнопки: квитанции «записано» нет",
       not any("บันทึกแล้ว" in t for t in SENDS), SENDS)

    # ДВЕРЬ 2 — голое число доверенного. 14.08 она случайно спасла ситуацию.
    reset()
    b = FakeBridge(sp=dict(SP_WAIT))
    handled = door_number(b, LIVE_WRONG)
    ok("дверь числа: перехвачено", handled is True)
    ok("дверь числа: 367474 НЕ записан", not _wrote(b), (b.oil_calls, b.svc_calls))
    ok("дверь числа: переспрос отправлен", _asked(SENDS), SENDS)

    # ОБЕ ДВЕРИ ВЕДУТ СЕБЯ ОДИНАКОВО — это и есть предмет цели.
    reset()
    b1 = FakeBridge()
    door_button(b1, LIVE_WRONG)
    s1 = list(SENDS)
    reset()
    b2 = FakeBridge(sp=dict(SP_WAIT))
    door_number(b2, LIVE_WRONG)
    s2 = list(SENDS)
    ok("двери совпали: ни одна не записала", not _wrote(b1) and not _wrote(b2))
    ok("двери совпали: обе переспросили", _asked(s1) and _asked(s2))

    # ВЕРНОЕ число той же пары проходит молча — цена не заплачена зря.
    reset()
    b = FakeBridge()
    door_button(b, "36474")
    ok("верное 36474 проходит кнопкой молча", _wrote(b), (b.oil_calls, b.svc_calls))
    ok("верное 36474: переспроса нет", not _asked(SENDS), SENDS)

    reset()
    b = FakeBridge(sp=dict(SP_WAIT))
    door_number(b, "36474")
    ok("верное 36474 проходит числом молча", _wrote(b), (b.oil_calls, b.svc_calls))
    ok("верное 36474 числом: переспроса нет", not _asked(SENDS), SENDS)


# ═══════════════ (2) КНОПКА ПОДТВЕРЖДЕНИЯ границы ═══════════════

def sec_confirm_button():
    print("\n(2) кнопка «да, число верное» — единственное место снятия границы")

    reset()
    b = FakeBridge()
    door_button(b, LIVE_WRONG)
    tok = max(S._SVC_TOKENS)
    d = S._SVC_TOKENS[tok]
    ok("токен переспроса заведён", d.get("kind") == "codo", d)
    ok("токен помнит оба числа", d.get("odo") == LIVE_WRONG and d.get("cur") == str(LIVE_CUR), d)

    # механик подтвердить НЕ может — trust не ослаблен
    SENDS.clear()
    run(S.handle_service_button(_upd(FakeQ(f"svc:codo:{tok}", "extthiwxer")),
                                context=None, bridge=b))
    ok("механик не снимает границу", not _wrote(b), (b.oil_calls, b.svc_calls))
    ok("токен жив — Пым нажмёт позже", tok in S._SVC_TOKENS)

    # доверенный подтверждает → пишется РОВНО то число
    SENDS.clear()
    run(S.handle_service_button(_upd(FakeQ(f"svc:codo:{tok}", "Pleummmm")),
                                context=None, bridge=b))
    ok("доверенный снял границу — запись прошла", _wrote(b), (b.oil_calls, b.svc_calls))
    wrote_km = [c[1] for c in b.oil_calls] + [c[2] for c in b.svc_calls]
    ok("записано именно подтверждённое число", all(k == 367474 for k in wrote_km), wrote_km)
    ok("confirmed=True не ослаблен",
       all(c[2] is True for c in b.oil_calls) and all(c[3] is True for c in b.svc_calls))
    ok("после подтверждения пришла квитанция",
       any("Записано" in t or "не записано" in t for t in SENDS), SENDS)


# ═══════════════ (5) FAIL-SAFE и (6) ОТКАТ ═══════════════

def sec_failsafe_and_rollback():
    print("\n(5) fail-safe в сторону записи · (6) откат")

    # текущий пробег не прочитан → пишем как прежде (симметрия с нижней границей)
    reset()
    b = FakeBridge(cur_km=None)
    door_button(b, LIVE_WRONG)
    ok("M не прочитан → пишем как прежде", _wrote(b), (b.oil_calls, b.svc_calls))
    ok("M не прочитан → переспроса нет", not _asked(SENDS), SENDS)

    # мост упал → пишем как прежде
    reset()
    b = FakeBridge(list_raises=True)
    door_button(b, LIVE_WRONG)
    ok("мост упал → пишем как прежде", _wrote(b), (b.oil_calls, b.svc_calls))

    # ОТКАТ: ручка 0 — ветка мертва, обе двери байт-в-байт как до 14.08
    reset(limit="0")
    b = FakeBridge()
    door_button(b, LIVE_WRONG)
    ok("откат кнопкой: 367474 записан, как до 14.08", _wrote(b), (b.oil_calls, b.svc_calls))
    ok("откат кнопкой: переспроса нет", not _asked(SENDS), SENDS)

    reset(limit="0")
    b = FakeBridge(sp=dict(SP_WAIT))
    door_number(b, LIVE_WRONG)
    ok("откат числом: 367474 записан, как до 14.08", _wrote(b), (b.oil_calls, b.svc_calls))

    # ручка не задана вовсе → дефолт, граница РАБОТАЕТ
    reset(limit=None)
    b = FakeBridge()
    door_button(b, LIVE_WRONG)
    ok("ручки нет → дефолт, граница работает", not _wrote(b), (b.oil_calls, b.svc_calls))


# ═══════════════ (7) ГРАНИЦЫ ═══════════════

def sec_borders():
    print("\n(7) границы: чего правка НЕ трогает")

    # убывание — чужие сторожа, верхняя граница молчит
    reset()
    b = FakeBridge(cur_km=36474)
    door_button(b, "3000")
    ok("убывание верхней границей не тронуто", _wrote(b), (b.oil_calls, b.svc_calls))
    ok("убывание: переспроса верхней границы нет", not _asked(SENDS), SENDS)

    # нечитаемое число — прежний определённый отказ bad_odometer, а не вопрос
    reset()
    b = FakeBridge()
    door_button(b, "не число")
    ok("нечитаемое число: записи нет", not _wrote(b))
    ok("нечитаемое число: это НЕ переспрос границы", not _asked(SENDS), SENDS)

    # trust на основной двери не ослаблен
    reset()
    b = FakeBridge()
    door_button(b, "36474", uname="extthiwxer")
    ok("механик по-прежнему не пишет", not _wrote(b), (b.oil_calls, b.svc_calls))

    # ярлык отказа — определённый, а не «неизвестно»
    import write_fact
    ok("odo_ceiling в SETTLED_ERRORS", OC.ERR in write_fact.SETTLED_ERRORS)
    ok("отказ границы не читается как «неизвестно»",
       not write_fact.needs_verify({"ok": False, "error": OC.ERR}))

    # квитанция не рождается на переспросе (вопрос ≠ отказ)
    reset()
    b = FakeBridge()
    door_button(b, LIVE_WRONG)
    ok("на переспросе квитанции нет вовсе",
       not any(("Записано" in t) or ("ничего не записано" in t) for t in SENDS), SENDS)


# ═══════════════ (8) ЧИСТОТА ═══════════════

def sec_purity():
    print("\n(8) чистота решения: ноль импортов, ни одной руки")
    src = open(os.path.join(ROOT, "odo_ceiling.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    ok("импортов РОВНО НОЛЬ", not imports, [ast.dump(n)[:60] for n in imports])

    banned = {"open", "exec", "eval", "compile", "__import__", "input"}
    hits = [n.func.id for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in banned]
    ok("ни одной руки (open/exec/eval)", not hits, hits)

    # Судит НЕ моя самодельная эвристика по именам атрибутов (`dict.get` и `str.replace` —
    # законны), а ТОТ ЖЕ разбор, которым живёт боевой страж: у решения не должно быть рук.
    import invariants_check as IC
    findings = IC._duty_ast_findings(src, allowed=frozenset())
    ok("боевой разбор не нашёл рук", not findings, findings)

    names = dict(IC.CHECKS)
    ok("страж ODO_CEILING_PURE зарегистрирован", "ODO_CEILING_PURE" in names)

    # страж зелёный на боевом файле — и КРАСНЕЕТ, если руки появятся (иначе он декоративен)
    run_obj = IC.CheckRun("ODO_CEILING_PURE")
    names["ODO_CEILING_PURE"](None, run_obj)
    ok("страж зелёный на боевом odo_ceiling.py", not run_obj.findings, run_obj.findings)
    dirty = IC._duty_ast_findings("import requests\ndef f():\n    return requests.get('x')\n",
                                  allowed=frozenset())
    ok("страж краснеет на модуле с руками", bool(dirty), dirty)


def main():
    print("═══ ВЕРХНЯЯ ГРАНИЦА ПРОБЕГА ПРИ ЗАПИСИ ТО ═══")
    sec_verdict()
    sec_doors()
    sec_confirm_button()
    sec_failsafe_and_rollback()
    sec_borders()
    sec_purity()
    total = len(FAILS)
    print("\n" + "═" * 60)
    if total:
        print(f"❌ ПРОВАЛОВ: {total}")
        for f in FAILS:
            print("   ·", f)
        sys.exit(1)
    print("✅ ВСЕ ПРОВЕРКИ ЗЕЛЁНЫЕ")


if __name__ == "__main__":
    main()
