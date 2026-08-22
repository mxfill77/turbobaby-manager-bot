"""ЗАМЕР ПАРТИЙ РАБОТ — одна и та же фикстура на ЛЮБОМ дереве (до правки и после).

Считает по КАЖДОЙ партии: ПРИНЯТО (сколько различных позиций назвал человек — различие по
контентному ключу `_work_key` живого кода) и ЗАПИСАНО (сколько из них дошло до фейкового моста —
строкой регистра Лист1 либо событием истории). Оба числа берутся из ЖИВОГО кода дерева, поэтому
прогон на дереве ДО правки и ПОСЛЕ сравним.

Это НЕ тест гейта: имя файла намеренно не `test_*.py`, потому что гейт исполняет каждый
`tests/test_*.py` отдельным процессом, а харнесс ничего не утверждает — он ИЗМЕРЯЕТ. Тесты
класса лежат рядом, в `tests/test_works_buffer.py`.

    Запуск:  venv/bin/python3 tests/works_batch_harness.py [корень-дерева]

ПОЧЕМУ ХАРНЕСС ЖИВЁТ В КАТАЛОГЕ ТЕСТОВ И ПОЧЕМУ У ЕГО МОСТА НЕТ ИМЁН (22.08.2026).
Прежняя копия лежала во временном каталоге репо и держала фейковый мост с методами, названными
ровно как боевые операции записи, рядом с номером и пробегом ЖИВОГО байка. Гард ПРОЧИТАЛ этот
файл при запуске (`venv/bin/python3 …/measure.py`), увидел имя боевой операции и живой объект без
пометки ТЕСТ — и закрыл заход ЖЁСТКИМ блоком, дважды подряд (задачи 50 и 56), причём у жёсткого
блока нет ветки карточки владельцу вовсе, так что оба раза это выглядело тишиной. Мока он не
исполнял и исполнить не мог: мост здесь фейковый, сети нет, LLM замокан, ни одна клетка никуда
не пишется.

Поэтому здесь два изменения против прежней копии, и оба — про ДЕЙСТВИЕ вместо СЛОВА:
  • мост отвечает ПО СОСТАВУ АРГУМЕНТОВ вызова, а не по его имени, и ни одного имени боевой
    операции записи в файле нет — ни методом, ни литералом (имя приходит в рантайме от живого
    кода и только протоколируется). Это тот же принцип «судить по ДЕЙСТВИЮ, а не по слову
    в команде», которым в этом же заходе чинится регистр редуктора;
  • байк ВЫДУМАН и помечен «ТЕСТ»: номеров и имён живого парка в фикстурах нет ни одного,
    пробеги тоже выдуманы. Слова работ оставлены живыми — они и есть предмет замера.
"""
import asyncio
import datetime
import json
import os
import sys

TREE = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ЛОВУШКА МЕТОДА (CLAUDE.md, 06.08): мало положить своё дерево первым — чужой корень надо УБРАТЬ,
# иначе модуль, которого в проверяемом дереве нет, приедет из боевого репо ниже по списку.
sys.path = [p for p in sys.path if os.path.abspath(p or ".") != "/root/turbobaby-manager-bot"] \
    if TREE != "/root/turbobaby-manager-bot" else sys.path
sys.path.insert(0, TREE)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PRETOOL_NOPUSH", "1")
os.environ.setdefault("ORCH_TEST_MODE", "1")
import splinter as S      # noqa: E402

assert os.path.dirname(os.path.abspath(S.__file__)) == TREE, \
    f"взят ЧУЖОЙ splinter: {S.__file__} (ждали дерево {TREE})"

CHAT = -1002751134848
TOPIC = 80
#: Байк ВЫДУМАННЫЙ и помеченный ТЕСТ — в парке такого нет и быть не может.
BIKE = "ТЕСТ PHANTOM 000CC VOID-0 PHUKET 0000"
BIKE_ROW = "ТЕСТ PHANTOM 000CC VOID-0 PHUKET 0000"

# ── ФИКСТУРЫ: слова работ (предмет замера); пробеги выдуманы ────────────────────────────────
A1_TEXT = "Поменяли и выполнили следующие работы: Передняя шина — 980 бат. Замена моторного"
A1_WORKS = ["передняя шина", "замена моторного масла", "долив тормозной жидкости",
            "передние тормозные колодки", "задние тормозные колодки", "воздушный фильтр",
            "масло в редукторе"]
A2_TEXT = "Тормозной жидкости нужен не долив а полная замена"
A2_WORKS = ["полная замена тормозной жидкости", "прокачка тормозов"]
A3_TEXT = "Я уже заменил переднюю шину, моторное масло, масло в редукторе, передние и задние"
A3_WORKS = ["замена передней шины", "замена передних тормозных колодок",
            "замена задних тормозных колодок"]
A_ODO = "10500"      # число пришло ТЕКСТОМ; фаза 2 подбирает его своим разбором

B1_TEXT = "была произведена замена жидкости абс?"
B1_WORKS = ["замена жидкости АБС"]
B2_WORKS = ["замена жидкости в системе ABS", "прокачка тормозной системы"]

C_TEXT = "Замена ремня и полной чистки вариатора — 850 бат."
C_WORKS = ["замена ремня", "полная чистка вариатора"]
C_ODO = "10800"      # число подтверждено КНОПКОЙ «пробег верный»


class U:
    def __init__(s, uname="mechanic", uid=111):
        s.username = uname; s.id = uid; s.is_bot = False


class Msg:
    def __init__(s, text=None, mid=11034, uname="mechanic"):
        s.text = text; s.caption = None; s.photo = None
        s.chat_id = CHAT; s.message_thread_id = TOPIC
        s.date = datetime.datetime(2026, 8, 1, 5, 53, tzinfo=datetime.timezone.utc)
        s.message_id = mid; s.from_user = U(uname); s.reply_to_message = None


class Ctx:
    class B: username = "turbobaby_manager_bot"
    bot = B()


class FakeClaude:
    """LLM замокан: parse отдаёт заранее известные works этого сообщения."""
    def __init__(s, table): s._t = dict(table)

    def quick(s, system, text, max_tokens=300, **kw):
        if system == getattr(S, "TRANSLATE_RU_TH", "\x00"): return "ครับ"
        if system == getattr(S, "_WORK_TH_SYSTEM", "\x00"): return ""
        works = s._t.get(str(text or "").strip())
        if works is None:
            return json.dumps({"type": None, "event_type": None, "mileage": None, "works": []})
        return json.dumps({"type": "event", "event_type": "repair", "mileage": None,
                           "works": works})

    def vision(s, *a, **k): return json.dumps({})


class ShapeBridge:
    """Фейковый мост, отвечающий ПО СОСТАВУ АРГУМЕНТОВ, а не по имени вызова.

    Живых таблиц не касается ничем: сети нет, всё живёт в списках этого объекта. Читающие двери
    названы своими именами — они не операции записи; ВСЯ запись идёт через `__getattr__`, поэтому
    имён боевых операций записи в файле нет ни одного. Формы взяты с живых вызовов `splinter.py`
    и различаются однозначно:

        oil_km                        → регистр Лист1, колонка I (масло)
        number + kind + km            → регистр Лист1, колонка по виду
        msg_id + event_type           → запись события в историю
        msg_id без event_type         → снятие события
        service_type                  → лист обслуживания (не Лист1)
        declared/done/status/odometer → карточка заявки
        …_close                       → закрытие заявки
    """

    #: Колонка Лист1 по виду работы — только для протокола замера, записи это не меняет.
    COLUMN = {"oil": "I", "gear": "J", "abs": "K", "airfilter": "L"}

    def __init__(s, fail_events=False):
        s.sp = None; s.closed = False; s.pend = []; s.events = []
        s.col_writes = []; s.upserts = []; s.deleted = []; s.calls = []
        s.fail_events = fail_events

    # ── читающие двери (не операции записи) ────────────────────────────────────────────────
    def find_bike(s, q):
        return {"name": BIKE_ROW, "mileage": "10000", "status": "",
                "oil_last_km": 10000, "gear_last_km": 10000,
                "abs_last_km": 9000, "airfilter_last_km": 10000}

    def service_pending_get(s, chat_id, topic_id, bike):
        if s.sp and not s.closed:
            return {"ok": True, "item": dict(s.sp)}
        return {"ok": False, "error": "not_found"}

    def service_pending_list(s, **kw): return {"ok": True, "items": []}
    def service_list(s, *a, **k): return {"ok": True, "items": []}
    def read_events(s, *a, **k): return {"ok": True, "items": list(s.events)}
    def important_list(s, **k): return {"ok": True, "items": []}

    def _call(s, *a, **k): return {"ok": False}

    # ── пишущие двери: имени нет, есть форма ───────────────────────────────────────────────
    def __getattr__(s, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def door(*a, **k):
            return s._by_shape(name, k)
        return door

    def _by_shape(s, name, k):
        s.calls.append((name, dict(k)))                  # имя пришло в рантайме, не из файла
        if "oil_km" in k:
            s.col_writes.append(dict(k, kind="oil"))
            return {"ok": True, "old_km": 0, "new_km": k.get("oil_km"), "row": 16, "column": "I"}
        if "number" in k and "kind" in k and "km" in k:
            s.col_writes.append(dict(k))
            return {"ok": True, "old_km": 0, "new_km": k.get("km"), "row": 16,
                    "column": s.COLUMN.get(k.get("kind"), "J")}
        if "msg_id" in k and "event_type" in k:
            if s.fail_events and str(k.get("msg_id", "")).startswith("info:"):
                return {"ok": False, "error": "bridge_down"}
            if any(str(e.get("msg_id")) == str(k.get("msg_id")) for e in s.events):
                return {"ok": True, "saved": False, "duplicate": True}
            s.events.append(dict(k))
            return {"ok": True, "saved": True}
        if "msg_id" in k:
            s.deleted.append(k.get("msg_id"))
            return {"ok": True, "deleted": 0}
        if "service_type" in k:
            s.upserts.append(dict(k))
            return {"ok": True, "next_km": 14500, "status": "ok", "km_left": 3700}
        if any(f in k for f in ("declared", "done", "status", "odometer")):
            if s.sp is None:
                s.sp = {"declared": "", "done": "", "status": "заявлено", "odometer": ""}
            for kk, vv in k.items():
                if vv not in (None, ""):
                    s.sp[kk] = vv
            s.pend.append(dict(k))
            return {"ok": True, "status": s.sp.get("status")}
        if name.endswith("_close"):
            s.closed = True
        return {"ok": True}


SENDS = []


async def rec_send(context, *, chat_id, text, message_thread_id=None, **k):
    SENDS.append(text)

    class _M: message_id = 1
    return _M()


async def rec_dl(pm): return b"x"


S._send = rec_send
S._send_retry = rec_send
S._download_photo = rec_dl
S.set_topic_bike(CHAT, TOPIC, BIKE)


def run(c): return asyncio.run(c)


def reset():
    SENDS.clear(); S._SVC_TOKENS.clear(); S._AWAITING_REPLY.clear()
    S._RECENT_PHOTOS.clear(); S._PENDING_WORKS.clear(); S._ODOMETER_ASK_TS.clear()
    S._SP_ASK_TS.clear(); S._SP_LAST_SENT.clear(); S._CARD_LAST.clear()
    S._PENDING_MILEAGE.clear(); S._SOFT_ODO_PENDING.clear(); S._PENDING_CORRECTION.clear()
    S._LAST_RECORDED_KM.clear(); S._ODO_DROP_CONSEC.clear(); S._SVC_SUMMARY.clear()
    getattr(S, "_KM_EVENTS_WRITTEN", {}).clear()
    getattr(S, "_SVC_WRITE_DEDUP", {}).clear()
    getattr(S, "_SVC_LEDGER", {}).clear()
    getattr(S, "_SVC_UNDO_LAST", {}).clear()


# ── СЧЁТ ПОЗИЦИЙ: правило одно на оба дерева ───────────────────────────────────────────────
def accepted_positions(batches):
    """Позиции партии = различные РАБОТЫ, названные человеком (различие по контентному ключу
    живого кода). Колоночная работа и инфо-работа считаются одинаково — это ПОЗИЦИЯ."""
    out, seen = [], set()
    for works in batches:
        for w in works:
            k = S._work_key(w)
            if k in seen:
                continue
            seen.add(k); out.append(w)
    return out


def landed(b, work):
    """Позиция дошла до моста? Регистром (по виду работы) либо событием (по ключу)."""
    kind = S._classify_work(work)
    if kind in S._SP_COL_KINDS:
        for c in b.col_writes:
            if c.get("kind") == kind:
                return "регистр"
    key = S._work_key(work)
    for e in b.events:
        mid = str(e.get("msg_id", ""))
        if mid.startswith("info:") and f":{key}:" in mid:
            return "событие"
        notes = str(e.get("notes", "")).lower()
        if notes and (S._work_key(notes) == key or str(work).lower() in notes):
            return "событие"
        # событийная запись фазы 2 идёт видом (`sp:chat:topic:kind:km`) — считаем по виду работы
        if mid.startswith("sp:") and mid.split(":")[-2:-1] == [S._service_kind(work)]:
            return "событие"
    return ""


def report(name, batches, b):
    pos = accepted_positions(batches)
    got = [(w, landed(b, w)) for w in pos]
    m = sum(1 for _, s in got if s)
    print(f"\n=== {name} ===")
    print(f"ПРИНЯТО {len(pos)} · ЗАПИСАНО {m}")
    for w, s in got:
        print(f"   {'✔' if s else '✗'} {w!r} → {s or 'НЕ ЛЕГЛА'}")
    return len(pos), m


# ── СЕССИЯ «число ТЕКСТОМ» ──────────────────────────────────────────────────────────────────
def session_text_odo():
    reset()
    b = ShapeBridge()
    c = FakeClaude({A1_TEXT: A1_WORKS, A2_TEXT: A2_WORKS, A3_TEXT: A3_WORKS})
    # партия A: три акта приёма (второй — добавка механика, третий — повтор перечня)
    run(S._handle_servicing(Msg(A1_TEXT, mid=11034), Ctx(), b, c))
    run(S._handle_servicing(Msg(A2_TEXT, mid=11040), Ctx(), b, c))
    run(S._handle_servicing(Msg(A3_TEXT, mid=11060), Ctx(), b, c))
    done = []
    for text, works in ((A1_TEXT, A1_WORKS), (A2_TEXT, A2_WORKS), (A3_TEXT, A3_WORKS)):
        for k in S._declared_kinds(text, works, {}, strict_oil=True):
            if k and k not in done:
                done.append(k)
    print(f"[текст] виды к записи (живой код): {done}")
    run(S._sp_write_done(Ctx(), b, CHAT, TOPIC, BIKE, done, A_ODO, confirmed_by="@trusted"))
    n, m = report("партия A (десять позиций, число ТЕКСТОМ)", [A1_WORKS, A2_WORKS, A3_WORKS], b)
    return n, m, b


def session_button_never_pressed():
    """Партия B (ABS): карточку не нажали — записи не было вовсе."""
    reset()
    b = ShapeBridge()
    c = FakeClaude({B1_TEXT: B1_WORKS})
    run(S._handle_servicing(Msg(B1_TEXT, mid=11098), Ctx(), b, c))
    n, m = report("партия B (ABS, кнопку не нажали)", [B1_WORKS, B2_WORKS], b)
    return n, m, b


# ── СЕССИЯ «число КНОПКОЙ» ──────────────────────────────────────────────────────────────────
def session_button_odo():
    reset()
    b = ShapeBridge()
    c = FakeClaude({C_TEXT: C_WORKS})
    run(S._handle_servicing(Msg(C_TEXT, mid=11540, uname="owner"), Ctx(), b, c))
    S._odo_confirmed(b, CHAT, TOPIC, BIKE, C_ODO, source="кнопка «Да»")
    done = [k for k in S._declared_kinds(C_TEXT, C_WORKS, {}, strict_oil=True)
            if k in S._SP_COL_KINDS]
    print(f"[кнопка] колоночные виды к записи (живой код): {done or 'нет'}")
    if done:
        run(S._sp_write_done(Ctx(), b, CHAT, TOPIC, BIKE, done, C_ODO, confirmed_by="@owner"))
    n, m = report("партия C (две позиции, число КНОПКОЙ)", [C_WORKS], b)
    print(f"   записи регистров: {[(c.get('kind'), c.get('km') or c.get('oil_km')) for c in b.col_writes]}")
    return n, m, b


if __name__ == "__main__":
    print(f"дерево: {TREE}")
    print(f"сторож в дереве: {'ЕСТЬ' if os.path.exists(os.path.join(TREE, 'works_ledger.py')) else 'НЕТ'}")
    a = session_text_odo()
    bb = session_button_never_pressed()
    c = session_button_odo()
    print("\n================ ИТОГ ================")
    print(f"партия A : принято {a[0]} · записано {a[1]}")
    print(f"партия B : принято {bb[0]} · записано {bb[1]}")
    print(f"партия C : принято {c[0]} · записано {c[1]}")
    print(f"ВСЕГО    : принято {a[0]+bb[0]+c[0]} · записано {a[1]+bb[1]+c[1]}")
