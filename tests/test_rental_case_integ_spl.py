# -*- coding: utf-8 -*-
"""К4 (TB-FILIPP-K4-CASE-FOUNDATION-0910), DESIGN_K4 §11 шаги 5–7: интеграция Splinter за флагами.

Запуск — в ПОЛНОМ дереве кандидата f2f7295 с модулями К4 (rental_case*.py, tests/rental_case_fakes.py):
    python tests/test_rental_case_integ_spl.py
Сеть запрещена подменой socket.socket (tests/rental_case_fakes.py); мост, Telegram и LLM — подделки; хранилище дела —
временная база в tempfile.mkdtemp(dir=K4_TTMP | tempdir), не удаляется.

Что проверяется:
  * К4-C34: при всех флагах OFF модулей rental_case / rental_case_rules / rental_case_adapters нет в sys.modules —
    сразу после импорта splinter и после прогона прежних путей (отдельный процесс, голдены «флаг OFF» тех же путей);
  * шаг 5 (RENTAL_CASE_PICK): «текущая + будущая бронь» на КАЖДОМ месте — _closing_resolve_booking (возврат и
    выдача), _handover_resolve_activation, _return_resolve_close, _closing_crm_debt, CRM-половина
    _deposit_resolve_booking, state_set на выдаче; unknown → прежний ⚠️ «руками» с конкретным вопросом; голдены
    tests/test_return_close.py:315-350 пересмотрены осознанно — дублем под флагом (исходные ожидания не тронуты);
  * шаг 6 (RENTAL_CASE): дело после create_booking (origin=intake) и на карточке выдачи/приёма (resolve → none →
    open_case(origin=splinter)), без второго дела на повторе; хранилища нет — прежний путь цел;
  * шаг 7 (RENTAL_CASE_APPROVALS): карточки во «Входящих» через хранилище; «да» реплаем одобряющего по id → один
    вызов моста + чтение назад; без реплая / не одобряющий / «нет» / «да, но не …» / после рестарта — не исполняется;
    приоритеты tests/test_handover_activation.py:150-161, tests/test_return_close.py:242-268 и оба TTL-теста
    (tests/test_handover_activation.py:130-134, tests/test_return_close.py:234-238) — дублем под флагом.

Среда набора (рег1 К4, 09.10 — исправление по регрессии):
  * память Splinter — ТОЛЬКО во временном каталоге прогона (STATE_DIR под K4_TTMP | tempdir), явной подменой до импорта
    splinter: без неё при признаке прогона тестов она уходит в /tmp/*_test_<pid> (на ПК — D:/tmp, вне места К4; замер
    reg1 k4-shim: hint_dedup_state_test_30484.json и topic_feed_test_30484/-1002751134848_4242.jsonl этого набора), а без
    признака — в каталог кода рядом с модулем под боевыми именами файлов состояния;
  * fcntl: на сервере кандидата настоящий; на ПК (Windows) его нет, и `import splinter` падал ModuleNotFoundError
    (bridge_client.py:11) до первого теста — основной прогон reg1 k4. Заглушка только для импорта (приём кандидата
    tests/test_spl_human_reply.py:43-49), вызовы считаются и обязаны быть нулём;
  * сеть: тело каждого теста — ноль попыток (счётчик подделки до/после); при импорте допускается только проба IPv6
    urllib3 (`HAS_IPV6 = _has_ipv6("::1")` при импорте requests из bridge_client.py:17), брошенная подделкой: настоящего
    сокета нет (тот же источник, что у находки NF-1 набора integ_wa).
"""
import asyncio
import datetime
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FLAGS = ("RENTAL_CASE", "RENTAL_CASE_PICK", "RENTAL_CASE_APPROVALS", "RENTAL_CASE_DB")
for _f in FLAGS:
    os.environ.pop(_f, None)

# ---------------------------------------------------------------------------------------------------------------------
# Память Splinter — только в каталоге прогона (до импорта splinter: wallet_cache читает путь при импорте). Явная подмена
# сильнее обеих веток умолчания в каждом месте; значения ставятся безусловно — унаследованное окружение их не решает.
# ---------------------------------------------------------------------------------------------------------------------
TTMP = os.environ.get("K4_TTMP") or tempfile.gettempdir()
STATE_DIR = tempfile.mkdtemp(prefix="k4spl_state_", dir=TTMP)
STATE_ENV = (
    ("HINT_DEDUP_STATE", "hint_dedup_state.json"),            # f2f7295:splinter.py:844-858
    ("DECIDER_LIVE_STATE", "decider_live_state.json"),        # f2f7295:splinter.py:1365-1367
    ("WORKS_PERSIST_STATE", "works_persist_state.json"),      # f2f7295:splinter.py:3909-3917
    ("MILEAGE_Q_STATE", "mileage_question_state.json"),       # f2f7295:splinter.py:5009-5017
    ("SVC_TOKENS_STATE", "svc_tokens.json"),                  # f2f7295:splinter.py:6378-6387
    ("TOPIC_FEED_DIR", "topic_feed"),                         # f2f7295:topic_feed.py:59-64
    ("SPLINTER_ASK_STAFF_STATE", "staff_ask_state.json"),     # f2f7295:staff_ask.py:60-62
    ("SPLINTER_RULES_SNAP", "business_rules_snap.json"),      # f2f7295:rules_snap.py:45-47
    ("WALLET_CACHE_FILE", "wallet_cache.json"),               # f2f7295:wallet_cache.py:33 (при импорте модуля)
    ("ENQUEUE_DEDUP_FILE", "enqueue_dedup.json"),             # f2f7295:bridge_client.py:138-150
)
for _k, _name in STATE_ENV:
    os.environ[_k] = os.path.join(STATE_DIR, _name)

import rental_case_fakes as F  # noqa: E402 — сеть запрещена при импорте (К4-C18)

# fcntl: splinter импортирует bridge_client (f2f7295:bridge_client.py:11) и wallet_cache (f2f7295:wallet_cache.py:25).
# На ПК модуля нет — заглушка ТОЛЬКО для импорта; вызовы пишутся в FCNTL_STUB.calls, и каждый тест требует ноль новых:
# пути набора замка файла не берут, иначе зелёное на ПК ничего не говорило бы о Linux-замке.
try:
    import fcntl  # noqa: F401
    FCNTL_STUB = None
except ImportError:
    FCNTL_STUB = types.ModuleType("fcntl")
    FCNTL_STUB.LOCK_SH, FCNTL_STUB.LOCK_EX, FCNTL_STUB.LOCK_NB, FCNTL_STUB.LOCK_UN = 1, 2, 4, 8
    FCNTL_STUB.K4_TEST_STUB = True
    FCNTL_STUB.calls = []

    def _stub_flock(fd, operation):
        FCNTL_STUB.calls.append(("flock", operation))

    def _stub_lockf(fd, cmd, *rest):
        FCNTL_STUB.calls.append(("lockf", cmd))

    FCNTL_STUB.flock = _stub_flock
    FCNTL_STUB.lockf = _stub_lockf
    sys.modules["fcntl"] = FCNTL_STUB

import splinter as S  # noqa: E402

PRODUCT = ("rental_case", "rental_case_rules", "rental_case_adapters")
LOADED_AFTER_IMPORT = sorted(m for m in PRODUCT if m in sys.modules)
NET_AT_IMPORT = F.net_log()                               # попытки до первого теста (подделка бросила каждую)
IPV6_PROBE = "socket.socket(<AddressFamily.AF_INET6:"     # проба urllib3 при импорте requests (bridge_client.py:17)
CHILD_MARK = "K4_SPL_CHILD_OFF "


def fcntl_calls():
    return list(FCNTL_STUB.calls) if FCNTL_STUB is not None else []


FCNTL_AT_IMPORT = fcntl_calls()


def state_paths():
    """Куда Splinter и его модули положат память в этом процессе — теми же функциями, что зовёт продукт."""
    return {
        "HINT_DEDUP_STATE": S._hint_state_path(),
        "DECIDER_LIVE_STATE": S._dlive_path(),
        "WORKS_PERSIST_STATE": S._wl_path(),
        "MILEAGE_Q_STATE": S._mileage_q_path(),
        "SVC_TOKENS_STATE": S._svc_tokens_path(),
        "TOPIC_FEED_DIR": S._tfeed.feed_dir(),
        "SPLINTER_ASK_STAFF_STATE": S._sask.state_path(),
        "SPLINTER_RULES_SNAP": S._rsnap.snap_path(),
        "WALLET_CACHE_FILE": S.wallet_cache._CACHE_FILE,
        "ENQUEUE_DEDUP_FILE": S.bridge_client._dedup_file(),
    }


def state_want():
    return dict((k, os.path.join(STATE_DIR, n)) for k, n in STATE_ENV)


class K4SplCase(unittest.TestCase):
    """Тело каждого теста: ноль попыток сети и ноль вызовов fcntl-заглушки (счётчики до и после равны)."""

    def setUp(self):
        self.addCleanup(self._no_net_no_lock, F.net_attempts(), len(fcntl_calls()))

    def _no_net_no_lock(self, net0, lock0):
        self.assertEqual(F.net_attempts(), net0, "сеть в теле теста: %s" % F.net_log()[net0:])
        self.assertEqual(fcntl_calls()[lock0:], [], "замок файла (fcntl-заглушка) в теле теста")

SERV_CHAT = -1002751134848
TOPIC = 4242
BIKE = "CB 300CC R 9011"
INTAKE = S.INTAKE_CHAT
OWNER_ID = 504608015                     # splinter.OWNER_IDS = rental_case_rules.OWNER_IDS = APPROVER_IDS по умолчанию
MANAGER_ID = 777001                      # менеджер из INTAKE_APPROVERS по нику, но не одобряющий по id (В10 UNKNOWN)
TZ = datetime.timedelta(hours=7)


# ---------------------------------------------------------------------------------------------------------------------
# Время и строки двери clients (живой формат: tests/rental_case_fakes.make_row)
# ---------------------------------------------------------------------------------------------------------------------

def local_now():
    return datetime.datetime.now(datetime.timezone.utc) + TZ


def dt(days, hm="10:00"):
    return "%s %s" % ((local_now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d"), hm)


def dm(days):
    d = local_now() + datetime.timedelta(days=days)
    return "%02d.%02d" % (d.day, d.month)


def row_cur(**kw):
    """Текущая аренда: «В аренде» с −3 по +2 сут."""
    base = dict(row=21, status="В аренде", bike=BIKE, name="Иван Текущий", date_start=dt(-3), date_end=dt(2),
                contacts="+66 81 234 5678", booking_id="bk-cur", deposit_raw="5000", debt=500)
    base.update(kw)
    return F.make_row(**base)


def row_fut(**kw):
    """Будущая бронь того же байка: «Бронь» с +3 по +10 сут."""
    base = dict(row=22, status="Бронь", bike=BIKE, name="Пётр Будущий", date_start=dt(3), date_end=dt(10),
                contacts="+66 89 999 0000", booking_id="bk-fut", deposit_raw="passport", debt=0)
    base.update(kw)
    return F.make_row(**base)


def row_today(**kw):
    """Бронь, выдаваемая сегодня: «Бронь» с сегодня по +5 сут."""
    base = dict(row=23, status="Бронь", bike=BIKE, name="Анна Сегодня", date_start=dt(0, "09:00"), date_end=dt(5),
                contacts="+66 82 555 1111", booking_id="bk-today", deposit_raw="3000", debt=0)
    base.update(kw)
    return F.make_row(**base)


# ---------------------------------------------------------------------------------------------------------------------
# Подделки Telegram / моста / LLM (форма — как в tests/test_handover_activation.py, tests/test_return_close.py)
# ---------------------------------------------------------------------------------------------------------------------

class BotUser(object):
    id = 1
    username = "turbobaby_manager_bot"
    is_bot = True


class U(object):
    def __init__(self, uname="extthiwxer", uid=None):
        self.username = uname
        self.id = uid
        self.is_bot = False


class Sent(object):
    """Ответ send_message: message_id и date (время Telegram) — ими хранилище пишет пост карточки."""

    def __init__(self, mid, chat_id, text):
        self.message_id = mid
        self.chat_id = chat_id
        self.text = text
        self.date = datetime.datetime.now(datetime.timezone.utc)
        self.from_user = BotUser()


class Msg(object):
    _next = [700000]

    def __init__(self, text, chat_id=SERV_CHAT, uname="extthiwxer", uid=None, reply_to=None, at=None):
        Msg._next[0] += 1
        self.message_id = Msg._next[0]
        self.text = text
        self.caption = None
        self.photo = None
        self.chat_id = chat_id
        self.message_thread_id = TOPIC if chat_id == SERV_CHAT else None
        self.date = datetime.datetime.fromtimestamp(time.time() if at is None else at, datetime.timezone.utc)
        self.from_user = U(uname, uid)
        self.reply_to_message = reply_to


class Ctx(object):
    class B(object):
        username = "turbobaby_manager_bot"
    bot = B()


class FakeClaude(object):
    def __init__(self, parsed):
        self._p = parsed

    def quick(self, system, text, max_tokens=300, **kw):
        if system == S.TRANSLATE_RU_TH:
            return "ครับ"
        return json.dumps(self._p)

    def vision(self, *a, **k):
        return "{}"


class Bridge(object):
    """Мост: дверь clients по живому формату + красные шаги, меняющие строки (для чтения назад)."""

    def __init__(self, rows, total_due=1500):
        self.rows = [dict(r) for r in rows]
        self.total_due = total_due
        self.calls = []
        self.tickets = 0
        self.close_mode = "ok"
        self.activate_mode = "ok"

    def red(self, name):
        return [k for n, k in self.calls if n == name]

    def _call(self, action, **k):
        assert action == "clients", action
        return F.clients_reply(self.rows, filter=k.get("filter", "all"))

    def clients(self, filter="active"):
        return F.clients_reply(self.rows, filter=filter)

    def find_bike(self, q):
        return {"name": BIKE, "status": "ДОМА", "oil_last_km": 30500}

    def read_events(self, bike, limit=30):
        return {"ok": False, "error": "нет в подделке"}       # положение байка — не предмет этих проверок

    def state_set(self, **k):
        self.calls.append(("state_set", k))
        return {"ok": True}

    def add_event(self, **k):
        self.calls.append(("add_event", k))
        return {"ok": True, "saved": True}

    def service_pending_get(self, *a, **k):
        return {"ok": False, "error": "not_found"}

    def service_list(self, *a, **k):
        return {"items": []}

    def closing_upsert(self, **k):
        self.calls.append(("closing_upsert", k))
        return {"ok": True, "row": 5, "total_due": self.total_due}

    def issue_write_ticket(self):
        self.tickets += 1
        return {"ok": True, "ticket": "t-k4"}

    def _find(self, bike, name, status):
        for r in self.rows:
            if r["bike"] == bike and r["name"] == name and r["status"] == status:
                return r
        return None

    def activate_booking(self, bike, name, date_start=None):
        self.calls.append(("activate_booking", {"bike": bike, "name": name, "date_start": date_start}))
        r = self._find(bike, name, "Бронь")
        if r is None:
            return {"ok": False, "error": "booking_not_found", "message": "не найдена"}
        r["status"] = "В аренде"
        if self.activate_mode == "raise_after_write":
            raise RuntimeError("обрыв после записи")
        return {"ok": True, "activated": True, "row": r["row"], "bike": bike, "name": name}

    def close_booking(self, bike, name, date_start=None, km_end=None, paid_total=None):
        self.calls.append(("close_booking", {"bike": bike, "name": name, "date_start": date_start, "km_end": km_end,
                                             "paid_total": paid_total}))
        if self.close_mode == "km_required" and km_end in (None, ""):
            return {"ok": False, "error": "km_required", "message": "km_end обязателен"}
        r = self._find(bike, name, "В аренде")
        if r is None:
            return {"ok": False, "error": "not_active", "message": "нет активной"}
        r["status"] = "Завершена"
        return {"ok": True, "closed": True, "row": r["row"], "bike": bike, "name": name}

    def create_booking(self, **k):
        self.calls.append(("create_booking", dict(k)))
        n = 30 + len(self.red("create_booking"))
        bk = "bk-new-%d" % n
        self.rows.append(F.make_row(row=n, status="Бронь", bike=k.get("bike") or "", name=k.get("name") or "—",
                                    date_start=dt(4), date_end=dt(9), contacts=k.get("contacts") or "",
                                    booking_id=bk))
        return {"ok": True, "row": n, "booking_id": bk, "bike": k.get("bike")}


SENDS = []
_MID = [910000]


async def rec_send(context, *, chat_id, text, message_thread_id=None, **k):
    _MID[0] += 1
    s = Sent(_MID[0], chat_id, text)
    SENDS.append(s)
    return s


async def rec_pass(*a, **k):
    return None


async def rec_dl(pm):
    return b"x"


S._send = rec_send
S._send_bike_card = rec_pass
S._after_mileage = rec_pass
S._ask_mileage_confirm = rec_pass
S._ask_service_col = rec_pass
S._download_photo = rec_dl
S.set_topic_bike(SERV_CHAT, TOPIC, BIKE)

HO_PARSE = {"type": "event", "event_type": "handover", "bike": BIKE, "fuel": "", "mileage": "", "works": []}
RET_PARSE = {"type": "event", "event_type": "return", "bike": BIKE, "fuel": "полный", "mileage": "35200", "works": []}


def run(coro):
    return asyncio.run(coro)


def reset():
    del SENDS[:]
    for d in (S._RETURN_CLOSES, S._RET_CLOSE_WARN_TS, S._HANDOVER_ACTIVATIONS, S._HO_ACT_WARN_TS, S._INTAKE_DRAFTS,
              S._CARD_LAST, S._PENDING_WORKS, S._RECENT_BOOKINGS):
        d.clear()
    S._RC_STORE = None
    for f in FLAGS:
        os.environ.pop(f, None)


def set_flags(*names):
    for n in names:
        os.environ[n] = "1"


def intake_texts():
    return [s.text for s in SENDS if s.chat_id == INTAKE]


def cards(word):
    return [s for s in SENDS if s.chat_id == INTAKE and word in s.text]


def do_handover(b):
    run(S._handle_servicing(Msg("выдаю клиенту, повёз"), Ctx(), b, FakeClaude(HO_PARSE)))


def do_return(b, parse=RET_PARSE):
    run(S._handle_servicing(Msg("вернул байк, принял"), Ctx(), b, FakeClaude(parse)))


def intake(b, text, reply_to=None, uname="turbophuket", uid=OWNER_ID, at=None):
    m = Msg(text, chat_id=INTAKE, uname=uname, uid=uid, reply_to=reply_to, at=at)
    run(S._handle_intake(m, Ctx(), b, None))
    return m


def draft(**kw):
    d = {"model": BIKE, "client": "Мария Новая", "date_start": "15-11-2026", "date_end": "20-11-2026",
         "date_start_iso": None, "date_end_iso": None, "contacts": "+66 83 777 2222",
         "delivery_url": "https://maps.app.goo.gl/x", "helmets": 2, "deposit_type": "паспорт",
         "passport_photo": True, "ts": time.time(), "status": "new"}
    d.update(kw)
    return d


# ---------------------------------------------------------------------------------------------------------------------
# Хранилище дела (временная база; файлы не удаляются)
# ---------------------------------------------------------------------------------------------------------------------

def new_store(label):
    import rental_case                         # лениво: модульный голден К4-C34 выше снят до этого импорта
    base = os.environ.get("K4_TTMP") or tempfile.gettempdir()
    d = tempfile.mkdtemp(prefix="k4spl_%s_" % label, dir=base)
    p = os.path.join(d, "rental_case.sqlite")
    rental_case.Store.create(p)
    os.environ["RENTAL_CASE_DB"] = p
    return p


def q(path, sql, args=()):
    """Только чтение базы прогона (mode=ro) — для проверок состояния."""
    con = sqlite3.connect(pathlib.Path(path).as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


def expects(path, kind=None):
    rows = q(path, "SELECT exp_id, kind, action, state, case_id, parent_exp, next_check FROM rc_expect "
                   "ORDER BY created_at, exp_id")
    return [r for r in rows if kind is None or r["kind"] == kind]


def answers(path):
    return q(path, "SELECT exp_id, verdict, decision, execute FROM rc_answer ORDER BY id")


def cases(path):
    return q(path, "SELECT case_id, origin, state, ver FROM rc_case ORDER BY created_at, case_id")


def rentals(path):
    return q(path, "SELECT case_id, booking_id, crm_row_seen FROM rc_rental WHERE current=1 ORDER BY case_id")


# =====================================================================================================================
# К4-C34 и голдены «флаг OFF»
# =====================================================================================================================

def child_off():
    """Отдельный процесс: все флаги OFF → прежние пути Splinter; отчёт о модулях и исходах (голдены OFF)."""
    out = {}
    net0, lock0 = F.net_attempts(), len(fcntl_calls())
    b = Bridge([row_cur(), row_fut()])
    out["closing_resolve"] = list(S._closing_resolve_booking(b, BIKE))
    out["closing_resolve_handover"] = list(S._closing_resolve_booking(b, BIKE, purpose="handover"))
    out["handover_resolve_row"] = (S._handover_resolve_activation(b, BIKE) or {}).get("row")
    out["return_resolve_row"] = (S._return_resolve_close(b, BIKE) or {}).get("row")
    out["crm_debt"] = S._closing_crm_debt(b, BIKE)
    out["deposit"] = S._deposit_resolve_booking(b, BIKE)
    reset()
    b = Bridge([row_today(), row_fut()])
    do_handover(b)
    out["ho_card"] = [s.text for s in cards("Активирую")]
    out["ho_pending_row"] = (S._HANDOVER_ACTIVATIONS.get(INTAKE) or {}).get("row")
    out["ho_state_booking"] = [k.get("booking_id") for k in b.red("state_set")]
    # APPROVEFIX1610: «да» засчитывается только реплаем на карточку выдачи (id сохраняется при отправке)
    _ho_cards = cards("Активирую")
    intake(b, "да", reply_to=_ho_cards[-1] if _ho_cards else None, uname="deramor", uid=None)
    out["ho_activated"] = b.red("activate_booking")
    reset()
    b = Bridge([row_cur(row=600, name="Новый", date_start=dt(-1)), row_cur(row=500, name="Старый", date_start=dt(-9))])
    do_return(b)
    out["ret_card"] = [s.text for s in cards("Завершаю")]
    reset()
    b = Bridge([row_cur()])
    # INTAKECONFIRM1610-привязка: черновик знает сообщение своей карточки (ic_msg_ids), «да» — реплаем на неё
    card = Msg("🆕 БРОНЬ …", chat_id=INTAKE, uname="deramor")
    S._INTAKE_DRAFTS[INTAKE] = draft(status="awaiting_approval", ic_msg_ids=[card.message_id])
    intake(b, "да", reply_to=card, uname="deramor", uid=None)
    out["booked"] = len(b.red("create_booking"))
    out["modules"] = sorted(m for m in PRODUCT if m in sys.modules)
    out["net_import"] = NET_AT_IMPORT
    out["net_paths"] = F.net_log()[net0:]
    out["fcntl_stub"] = FCNTL_STUB is not None
    out["fcntl_calls"] = fcntl_calls()[lock0:]
    out["state_ok"] = state_paths() == state_want()
    return out


class T00FlagsOff(K4SplCase):
    """К4-C34: флаги OFF — модулей дела нет в процессе Splinter; прежнее поведение (голдены OFF)."""

    def test_c34_no_rental_case_modules_after_import(self):
        self.assertEqual(LOADED_AFTER_IMPORT, [], "splinter при OFF импортировал модули дела: %s" % LOADED_AFTER_IMPORT)

    def test_env_state_only_in_run_dir(self):
        """Память Splinter — только в каталоге прогона: ни /tmp (D:/tmp на ПК), ни каталог кода (боевые имена)."""
        self.assertTrue(os.path.isdir(STATE_DIR), STATE_DIR)
        self.assertEqual(os.path.normcase(os.path.abspath(os.path.dirname(STATE_DIR))),
                         os.path.normcase(os.path.abspath(TTMP)))
        self.assertEqual(state_paths(), state_want())

    def test_env_net_at_import_only_blocked_ipv6_probe(self):
        """При импорте — только проба IPv6 urllib3, брошенная подделкой (настоящего сокета нет); иного нет."""
        self.assertEqual([w for w in NET_AT_IMPORT if not w.startswith(IPV6_PROBE)], [], NET_AT_IMPORT)

    def test_env_fcntl_stub_import_only(self):
        """Заглушка fcntl — только там, где модуля нет, и только для импорта: при импорте вызовов ноль."""
        if FCNTL_STUB is None:
            self.assertFalse(getattr(sys.modules.get("fcntl"), "K4_TEST_STUB", False), "настоящий fcntl подменён")
        else:
            self.assertIs(sys.modules.get("fcntl"), FCNTL_STUB)
            self.assertEqual(FCNTL_AT_IMPORT, [], "замок файла при импорте splinter")

    def test_c34_off_paths_in_separate_process(self):
        env = dict(os.environ)
        for f in FLAGS:
            env.pop(f, None)
        p = subprocess.run([sys.executable, os.path.abspath(__file__), "--child-off"], cwd=ROOT, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        text = p.stdout.decode("utf-8", "replace")
        lines = [ln for ln in text.splitlines() if ln.startswith(CHILD_MARK)]
        self.assertEqual(p.returncode, 0, "дочерний процесс упал: %s\n%s" % (
            text[-2000:], p.stderr.decode("utf-8", "replace")[-3000:]))
        self.assertEqual(len(lines), 1, text[-2000:])
        got = json.loads(lines[0][len(CHILD_MARK):])
        self.assertEqual(got["modules"], [], "OFF: модули дела загружены прежними путями: %s" % got["modules"])
        # среда ребёнка: тот же замок, что у родителя (сеть, fcntl, память Splinter — в его каталоге прогона)
        self.assertEqual(got["net_paths"], [], "OFF: сеть на прежних путях")
        self.assertEqual([w for w in got["net_import"] if not w.startswith(IPV6_PROBE)], [], got["net_import"])
        self.assertEqual(got["fcntl_stub"], FCNTL_STUB is not None)
        self.assertEqual(got["fcntl_calls"], [], "OFF: замок файла на прежних путях")
        self.assertTrue(got["state_ok"], "OFF: память Splinter ребёнка вне его каталога прогона")
        # голдены OFF: прежние правила кандидата f2f7295, включая названные К4 дефекты (они уходят только под флагом)
        self.assertEqual(got["closing_resolve"], ["bk-fut", "Пётр Будущий", dt(10)],
                         "OFF: _closing_resolve_booking — свежайшая date_start (прежнее правило)")
        self.assertEqual(got["closing_resolve_handover"], got["closing_resolve"], "OFF: purpose не читается")
        self.assertEqual(got["handover_resolve_row"], 22, "OFF: _handover_resolve_activation — cand[-1]")
        self.assertEqual(got["return_resolve_row"], 21, "OFF: _return_resolve_close — строго «В аренде»")
        self.assertEqual(got["crm_debt"], 0, "OFF: _closing_crm_debt — cand[-1]")
        self.assertIsNone(got["deposit"], "OFF: две строки Бронь/В аренде — без привязки")
        self.assertEqual(len(got["ho_card"]), 1, got)
        self.assertIn("строка 22", got["ho_card"][0], "OFF: карточка выдачи по cand[-1]")
        self.assertEqual(got["ho_pending_row"], 22)
        self.assertEqual(got["ho_state_booking"], ["bk-fut"], "OFF: state выдачи — свежайшая date_start")
        self.assertEqual(len(got["ho_activated"]), 1,
                         "OFF: «да» реплаем на карточку выдачи исполняется (APPROVEFIX1610: без реплая — уточнение)")
        self.assertEqual(len(got["ret_card"]), 1, got)
        self.assertIn("Новый", got["ret_card"][0], "OFF: две «В аренде» — свежайшая date_start (прежний голден)")
        self.assertEqual(got["booked"], 1, "OFF: «да» на карточку брони пишет бронь по-прежнему")


# =====================================================================================================================
# Шаг 5: RENTAL_CASE_PICK — «текущая + будущая бронь» на каждом месте
# =====================================================================================================================

class T05Pick(K4SplCase):
    def setUp(self):
        super(T05Pick, self).setUp()
        reset()
        set_flags("RENTAL_CASE_PICK")

    def tearDown(self):
        reset()

    def test_closing_resolve_return_current_not_future(self):
        b = Bridge([row_cur(), row_fut()])
        self.assertEqual(S._closing_resolve_booking(b, BIKE), ("bk-cur", "Иван Текущий", dt(2)))

    def test_closing_resolve_handover_today_not_future(self):
        b = Bridge([row_today(), row_fut()])
        self.assertEqual(S._closing_resolve_booking(b, BIKE, purpose="handover"),
                         ("bk-today", "Анна Сегодня", dt(5)))
        b = Bridge([row_cur(), row_fut()])
        self.assertEqual(S._closing_resolve_booking(b, BIKE, purpose="handover"), (None, "", ""),
                         "текущая чужая + будущая: брони на сегодня нет — не выбирать будущую")

    def test_closing_resolve_handover_already_active_today(self):
        act = row_today(status="В аренде")
        b = Bridge([act, row_fut()])
        self.assertEqual(S._closing_resolve_booking(b, BIKE, purpose="handover"),
                         ("bk-today", "Анна Сегодня", dt(5)))

    def test_handover_resolve_today_not_future(self):
        b = Bridge([row_today(), row_fut()])
        c = S._handover_resolve_activation(b, BIKE)
        self.assertEqual((c or {}).get("row"), 23, c)
        self.assertEqual(c.get("status"), "бронь")

    def test_handover_resolve_current_and_future_is_question(self):
        b = Bridge([row_cur(), row_fut()])
        c = S._handover_resolve_activation(b, BIKE)
        self.assertTrue(c and c.get("rc_unknown"), c)
        self.assertIn(dm(3), c.get("ask") or "", "вопрос называет дату будущей брони: %r" % c)
        self.assertIn("ранняя выдача", c.get("ask") or "")

    def test_handover_resolve_already_active_silent(self):
        b = Bridge([row_today(status="В аренде"), row_fut()])
        c = S._handover_resolve_activation(b, BIKE)
        self.assertEqual((c or {}).get("status"), "в аренде", c)

    def test_return_resolve_current_not_future(self):
        b = Bridge([row_cur(), row_fut()])
        self.assertEqual((S._return_resolve_close(b, BIKE) or {}).get("row"), 21)

    def test_return_resolve_two_active_is_question(self):
        b = Bridge([row_cur(row=600, name="Новый", date_start=dt(-1)), row_cur(row=500, name="Старый",
                                                                               date_start=dt(-9))])
        c = S._return_resolve_close(b, BIKE)
        self.assertTrue(c and c.get("rc_unknown"), c)
        self.assertEqual(c.get("reason"), "two_active")
        self.assertIn("строка 600", c.get("ask"))
        self.assertIn("строка 500", c.get("ask"))

    def test_closing_crm_debt_current_not_future(self):
        b = Bridge([row_cur(debt=500), row_fut(debt=0)])
        self.assertEqual(S._closing_crm_debt(b, BIKE), 500)
        b = Bridge([row_cur(row=600, debt=100), row_cur(row=500, debt=200, date_start=dt(-9))])
        self.assertIsNone(S._closing_crm_debt(b, BIKE), "две «в аренде» — долг не выбирается")

    def test_deposit_crm_half_current_and_future_is_question(self):
        self.assertIsNone(S._deposit_resolve_booking(Bridge([row_cur(), row_fut()]), BIKE),
                          "касса: текущая + будущая — претендентов два, привязки нет")
        self.assertEqual(S._deposit_resolve_booking(Bridge([row_cur()]), BIKE), {"booking_id": "bk-cur", "row": 21})
        self.assertIsNone(S._deposit_resolve_booking(Bridge([row_fut()]), BIKE),
                          "только будущая бронь: предоплата при CASH_PRE_START_DAYS=UNKNOWN — вопрос, не привязка")

    def test_deposit_intake_window_keeps_priority(self):
        S._RECENT_BOOKINGS["9011"] = {"booking_id": "bk-win", "row": 40, "ts": time.time()}
        self.assertEqual(S._deposit_resolve_booking(Bridge([row_cur(), row_fut()]), BIKE),
                         {"booking_id": "bk-win", "row": 40})

    def test_handover_card_current_and_future_warns_with_question(self):
        b = Bridge([row_cur(), row_fut()])
        do_handover(b)
        warns = [t for t in intake_texts() if "⚠️ ВЫДАЧА" in t]
        self.assertEqual(len(warns), 1, intake_texts())
        self.assertIn(dm(3), warns[0])
        self.assertIn("руками", warns[0])
        self.assertNotIn(INTAKE, S._HANDOVER_ACTIVATIONS, "без однозначной брони ожидание «да» не заводится")
        self.assertEqual([k.get("booking_id") for k in b.red("state_set")], [""],
                         "state выдачи: не будущая бронь")

    def test_handover_card_today_not_future(self):
        b = Bridge([row_today(), row_fut()])
        do_handover(b)
        cs = cards("Активирую")
        self.assertEqual(len(cs), 1, intake_texts())
        self.assertIn("строка 23", cs[0].text)
        self.assertEqual(S._HANDOVER_ACTIVATIONS[INTAKE]["row"], 23)
        self.assertEqual([k.get("booking_id") for k in b.red("state_set")], ["bk-today"])

    def test_return_card_two_active_warns_instead_of_freshest(self):
        """Пересмотр осознанно tests/test_return_close.py:336-348 (test_multi_active_freshest_date_start): под
        флагом две «В аренде» — вопрос, а не свежайшая date_start (DESIGN §3.3, К4-C25). Исходный голден не тронут."""
        b = Bridge([row_cur(row=600, name="Новый", date_start=dt(-1)), row_cur(row=500, name="Старый",
                                                                               date_start=dt(-9))])
        do_return(b)
        self.assertEqual(cards("Завершаю"), [], intake_texts())
        warns = [t for t in intake_texts() if "⚠️ ПРИЁМ" in t]
        self.assertEqual(len(warns), 1, intake_texts())
        self.assertIn("строка 600", warns[0])
        self.assertIn("строка 500", warns[0])
        self.assertNotIn(INTAKE, S._RETURN_CLOSES)

    def test_return_card_golden_5960_live_over_closed(self):
        """tests/test_return_close.py:315-334 под флагом: Завершена row1204 + В аренде row703 → карточка row703."""
        live = row_cur(row=703, name="Иван Тест", date_start=dt(-2))
        closed = row_cur(row=1204, status="Завершена", name="Старый клиент", date_start="2025-03-01 10:00",
                         date_end="2025-03-05 10:00")
        b = Bridge([live, closed])
        do_return(b)
        cs = cards("Завершаю")
        self.assertEqual(len(cs), 1, intake_texts())
        self.assertIn("строка 703", cs[0].text)


# =====================================================================================================================
# Шаг 6: RENTAL_CASE — рождение дела
# =====================================================================================================================

class T06Case(K4SplCase):
    def setUp(self):
        super(T06Case, self).setUp()
        reset()
        set_flags("RENTAL_CASE")

    def tearDown(self):
        reset()

    def test_case_after_create_booking_origin_intake(self):
        p = new_store("bk")
        b = Bridge([row_cur()])
        # INTAKECONFIRM1610-привязка: черновик знает сообщение своей карточки (ic_msg_ids), «да» — реплаем на неё
        card = Msg("🆕 БРОНЬ …", chat_id=INTAKE, uname="deramor")
        S._INTAKE_DRAFTS[INTAKE] = draft(status="awaiting_approval", ic_msg_ids=[card.message_id])
        intake(b, "да", reply_to=card, uname="deramor", uid=None)
        self.assertEqual(len(b.red("create_booking")), 1)
        cs = cases(p)
        self.assertEqual([(c["origin"], c["state"]) for c in cs], [("intake", "open")], cs)
        self.assertEqual([r["booking_id"] for r in rentals(p)], ["bk-new-31"])

    def test_case_on_handover_card_once(self):
        p = new_store("ho")
        b = Bridge([row_today(), row_fut()])
        do_handover(b)
        do_handover(b)
        cs = cases(p)
        self.assertEqual([(c["origin"], c["state"]) for c in cs], [("splinter", "open")], cs)
        self.assertEqual([r["booking_id"] for r in rentals(p)], ["bk-fut"],
                         "без RENTAL_CASE_PICK строка карточки — прежняя (cand[-1]); дело — её")
        self.assertEqual(S._HANDOVER_ACTIVATIONS[INTAKE]["status"], "awaiting", "карточка — прежняя, в памяти")
        self.assertEqual(len(cards("Активирую")), 1)

    def test_case_on_handover_with_pick_is_todays_booking(self):
        set_flags("RENTAL_CASE_PICK")
        p = new_store("hop")
        b = Bridge([row_today(), row_fut()])
        do_handover(b)
        self.assertEqual([r["booking_id"] for r in rentals(p)], ["bk-today"])

    def test_case_on_return_card(self):
        p = new_store("ret")
        b = Bridge([row_cur(), row_fut()])
        do_return(b)
        self.assertEqual([r["booking_id"] for r in rentals(p)], ["bk-cur"])
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["status"], "awaiting")

    def test_store_unavailable_old_path_intact(self):
        b = Bridge([row_today()])
        do_handover(b)
        self.assertEqual(S._HANDOVER_ACTIVATIONS[INTAKE]["status"], "awaiting")
        # APPROVEFIX1610: «да» засчитывается только реплаем на карточку выдачи (id сохраняется при отправке)
        intake(b, "да", reply_to=cards("Активирую")[-1], uname="deramor", uid=None)
        self.assertEqual(len(b.red("activate_booking")), 1, "нет хранилища — шаг 6 молчит, прежний путь цел")

    def test_r2_booking_taken_only_through_resolve(self):
        """К4 круг 2 (C22, I38; judge_C21-C30 cx_c22b): после create_booking booking_id уже у дела A, а перечитанная
        строка по байку, дню и имени ведёт в дело B — resolve отвечает unknown(link_confirmation): карточку брони к делу
        A не вешаем. Контроль: booking_taken, где resolve строки находит то же дело, — карточка к нему."""
        import rental_case
        p = new_store("r2bktaken")
        st = rental_case.Store(p, role="test")
        by = {"kind": "code", "id": None, "name": "k4-r2"}
        now = time.time()

        def src(ref):
            return {"name": "clients (синтетика)", "ref": ref, "method": "door", "read_at": now, "observed_at": now}

        def card(ref):
            out = st.request_approval(None, task_id=None, action="booking", chat=str(INTAKE),
                                      card={"ref": ref, "text": "карточка брони"}, by=by,
                                      idem_key="appr:--:booking:%s:%s" % (INTAKE, ref))
            self.assertEqual(out.get("code"), "ok", out)
            return (out.get("data") or {}).get("exp_id")

        r_b = F.make_row(row=61, status="В аренде", bike=BIKE, name="Иван Якорь", date_start=dt(-2), date_end=dt(3),
                         contacts="+66 81 111 2222", booking_id="", deposit_raw="3000", debt=0)
        r_a = F.make_row(row=62, status="Бронь", bike="PCX 160 4410", name="Пётр Другой", date_start=dt(20),
                         date_end=dt(25), contacts="+66 89 333 4444", booking_id="bk-900", deposit_raw="3000", debt=0)
        self.assertEqual(st.open_case(origin="test", by=by, idem_key="open:test:row:61", rental_row=r_b,
                                      source=src("строка 61")).get("code"), "ok")
        oa = st.open_case(origin="test", by=by, idem_key="open:test:bk:bk-900", rental_row=r_a, source=src("строка 62"))
        self.assertEqual(oa.get("code"), "ok", oa)
        cid_a = oa.get("case_id") or (oa.get("data") or {}).get("case_id")
        r_new = F.make_row(row=62, status="Бронь", bike=BIKE, name="Иван Якорь", date_start=r_b["date_start"],
                           date_end=dt(6), contacts="+66 81 111 2222", booking_id="bk-900", deposit_raw="3000",
                           debt=0)
        res = st.resolve(purpose="handover", rows=[r_b, r_new], moment=now, observed_at=now, row=r_new)
        self.assertEqual((res.get("code"), res.get("reason")), ("unknown", "link_confirmation"), res)
        e1 = card("card-r2-a")
        got = S._rc_case_after_booking(Bridge([r_b, r_new]), {"ok": True, "booking_id": "bk-900", "row": 62}, e1)
        self.assertIsNone(got, "booking_taken при unknown(link_confirmation) — дело не выбрано")
        self.assertEqual([r["case_id"] for r in q(p, "SELECT case_id FROM rc_expect WHERE exp_id=?", (e1,))], [None],
                         "карточка брони повешена на дело мимо resolve")
        e2 = card("card-r2-b")
        got = S._rc_case_after_booking(Bridge([r_b, r_a]), {"ok": True, "booking_id": "bk-900", "row": 62}, e2)
        self.assertEqual(got, cid_a, "booking_taken, resolve нашёл то же дело — карточка к нему (контроль)")
        self.assertEqual([r["case_id"] for r in q(p, "SELECT case_id FROM rc_expect WHERE exp_id=?", (e2,))], [cid_a])

    def test_case_row_ambiguous_on_reread_not_born(self):
        """Мутант шва SS5 (exact_1010): строка карточки при перечитывании найдена не ровно один раз (дверь отдала два
        ряда с одним номером и байком) — дело не рождается по догадке, прежняя карточка цела."""
        p = new_store("amb")
        b = Bridge([row_today(), row_today(name="Дубль Строки", booking_id="bk-dup")])
        do_handover(b)
        self.assertEqual(cases(p), [], "дело родилось по неоднозначно перечитанной строке")
        self.assertEqual(len(cards("Активирую")), 1, "прежняя карточка (в памяти) цела")


# =====================================================================================================================
# Шаг 7: RENTAL_CASE_APPROVALS — ожидания «да» в хранилище
# =====================================================================================================================

class T07Approvals(K4SplCase):
    def setUp(self):
        super(T07Approvals, self).setUp()
        reset()
        set_flags("RENTAL_CASE_APPROVALS")
        self.p = new_store(self._testMethodName[5:25])

    def tearDown(self):
        reset()

    def ho_card(self, b):
        do_handover(b)
        cs = cards("Активирую")
        self.assertEqual(len(cs), 1, intake_texts())
        self.assertIn("РЕПЛАЕМ", cs[-1].text)
        return cs[-1]

    def ret_card(self, b, parse=RET_PARSE):
        do_return(b, parse)
        cs = cards("Завершаю")
        self.assertTrue(cs, intake_texts())
        return cs[-1]

    def bk_card(self, b):
        d = draft(status="awaiting_approval")
        S._INTAKE_DRAFTS[INTAKE] = d
        run(S._intake_finalize(d, Msg("🆕 БРОНЬ …", chat_id=INTAKE, uname="deramor"), Ctx(), b))
        cs = [s for s in SENDS if s.chat_id == INTAKE and "РЕПЛАЕМ" in s.text and "Активирую" not in s.text
              and "Завершаю" not in s.text]
        self.assertTrue(cs, intake_texts())
        return cs[-1]

    def state_of(self, kind, action=None):
        return [e["state"] for e in expects(self.p, kind) if action is None or e["action"] == action]

    def test_activation_reply_yes_executes_once_and_reads_back(self):
        b = Bridge([row_today()])
        card = self.ho_card(b)
        self.assertEqual(S._HANDOVER_ACTIVATIONS, {}, "при флаге ожидание «да» не живёт в памяти процесса")
        self.assertEqual(self.state_of("approval", "activate"), ["waiting"])
        intake(b, "да", reply_to=card)
        self.assertEqual(b.red("activate_booking"), [{"bike": BIKE, "name": "Анна Сегодня",
                                                      "date_start": dt(0, "09:00")}])
        self.assertEqual(b.tickets, 1, "красный шаг — под билетом 4.2")
        self.assertTrue(any("✅ В аренде" in t and "строка 23" in t for t in intake_texts()), intake_texts())
        self.assertEqual(self.state_of("approval", "activate"), ["answered"])
        self.assertEqual(self.state_of("readback"), ["answered"], "чтение назад: landed")
        intake(b, "да", reply_to=card)
        self.assertEqual(len(b.red("activate_booking")), 1, "второе «да» на ту же карточку — справка, моста нет")
        self.assertEqual([a["verdict"] for a in answers(self.p)], ["accepted", "reference_answered"])

    def test_activation_card_not_duplicated(self):
        b = Bridge([row_today()])
        do_handover(b)
        do_handover(b)
        self.assertEqual(len(cards("Активирую")), 1)
        self.assertEqual(len(cases(self.p)), 1)

    def test_yes_without_reply_not_executed(self):
        b = Bridge([row_today()])
        self.ho_card(b)
        intake(b, "да")
        self.assertEqual(b.red("activate_booking"), [], "«да» без реплая при APPROVAL_REPLY_REQUIRED=UNKNOWN")
        self.assertTrue(any("ОТВЕТОМ" in t for t in intake_texts()), intake_texts())
        self.assertEqual([a["verdict"] for a in answers(self.p)], ["reference_no_reply"])
        self.assertEqual(self.state_of("approval", "activate"), ["waiting"])

    def test_non_approver_by_id_not_executed(self):
        b = Bridge([row_today()])
        card = self.ho_card(b)
        intake(b, "да", reply_to=card, uname="deramor", uid=MANAGER_ID)
        self.assertEqual(b.red("activate_booking"), [], "одобряющий — по id (APPROVER_IDS), не по нику")
        self.assertEqual([a["verdict"] for a in answers(self.p)], ["reference_foreign_author"])

    def test_words_no_and_negated_yes(self):
        b = Bridge([row_today()])
        card = self.ho_card(b)
        intake(b, "да, но не активируй до оплаты", reply_to=card)
        self.assertEqual(b.red("activate_booking"), [])
        self.assertTrue(any("Активацию отменил" in t for t in intake_texts()), intake_texts())
        self.assertEqual([(a["verdict"], a["decision"]) for a in answers(self.p)], [("accepted", "no")])

    def test_ttl_activation_late_reply_not_executed(self):
        """Дубль под флагом tests/test_handover_activation.py:130-134 (test_ttl_expired)."""
        b = Bridge([row_today()])
        card = self.ho_card(b)
        intake(b, "да", reply_to=card, at=card.date.timestamp() + 1800 + 60)
        self.assertEqual(b.red("activate_booking"), [], "просроченная карточка активации исполняться не должна")
        self.assertEqual([a["verdict"] for a in answers(self.p)], ["reference_late"])

    def test_ttl_close_late_reply_not_executed(self):
        """Дубль под флагом tests/test_return_close.py:234-238 (test_ttl_expired)."""
        b = Bridge([row_cur()])
        card = self.ret_card(b)
        intake(b, "да", reply_to=card, at=card.date.timestamp() + 1800 + 60)
        self.assertEqual(b.red("close_booking"), [], "просроченная карточка закрытия исполняться не должна")
        self.assertEqual([a["verdict"] for a in answers(self.p)], ["reference_late"])

    def test_close_reply_yes_with_km_and_paid(self):
        b = Bridge([row_cur()])
        card = self.ret_card(b)
        self.assertIn("35200", card.text)
        intake(b, "да", reply_to=card)
        # CLOSETRUTH1910 (CLOSE_TRUTH ВКЛ по умолчанию): итог листа закрытия в K «оплачено» не пишется
        self.assertEqual(b.red("close_booking"), [{"bike": BIKE, "name": "Иван Текущий", "date_start": dt(-3),
                                                   "km_end": "35200", "paid_total": None}])
        self.assertTrue(any("✅ Завершена" in t for t in intake_texts()), intake_texts())
        self.assertEqual(self.state_of("readback"), ["answered"])

    def test_close_km_required_gives_new_card(self):
        b = Bridge([row_cur()])
        b.close_mode = "km_required"
        card = self.ret_card(b, dict(RET_PARSE, mileage=""))
        intake(b, "да", reply_to=card)
        self.assertEqual(len(b.red("close_booking")), 1)
        self.assertTrue(any("нет пробега" in t for t in intake_texts()), intake_texts())
        again = cards("Завершаю")
        self.assertEqual(len(again), 2, "после km_required — новая карточка того же закрытия")
        intake(b, "да 35300", reply_to=again[-1])
        self.assertEqual([c["km_end"] for c in b.red("close_booking")], [None, "35300"])

    def test_priority_booking_card_and_activation_no_reply(self):
        """Дубль под флагом tests/test_handover_activation.py:150-161 (test_intake_draft_priority): без реплая «да»
        не исполняет НИЧЕГО (справка к карточке брони — первой по порядку booking → activate → close)."""
        b = Bridge([row_today()])
        self.ho_card(b)
        self.bk_card(b)
        intake(b, "да")
        self.assertEqual(b.red("create_booking"), [])
        self.assertEqual(b.red("activate_booking"), [])
        ans = answers(self.p)
        self.assertEqual([a["verdict"] for a in ans], ["reference_no_reply"])
        booking_exp = [e["exp_id"] for e in expects(self.p, "approval") if e["action"] == "booking"]
        self.assertEqual([a["exp_id"] for a in ans], booking_exp)

    def test_priority_reply_addresses_activation_not_booking(self):
        b = Bridge([row_today()])
        card = self.ho_card(b)
        self.bk_card(b)
        intake(b, "да", reply_to=card)
        self.assertEqual(len(b.red("activate_booking")), 1, "реплай на карточку активации — активация")
        self.assertEqual(b.red("create_booking"), [], "карточка брони своего «да» не получила")
        self.assertEqual(self.state_of("approval", "booking"), ["waiting"])

    def test_priority_activation_and_close(self):
        """Дубль под флагом tests/test_return_close.py:256-268 (test_activation_priority_over_close)."""
        b = Bridge([row_cur(date_end=dt(0, "12:00")), row_today()])
        close_card = self.ret_card(b)
        act_card = self.ho_card(b)
        intake(b, "да", reply_to=act_card)
        self.assertEqual(len(b.red("activate_booking")), 1)
        self.assertEqual(b.red("close_booking"), [])
        self.assertEqual(self.state_of("approval", "close"), ["waiting"], "карточка приёма ждёт своего «да»")
        intake(b, "да", reply_to=close_card)
        self.assertEqual(len(b.red("close_booking")), 1)

    def test_booking_card_yes_creates_case_and_attaches(self):
        b = Bridge([row_cur()])
        card = self.bk_card(b)
        self.assertEqual(self.state_of("approval", "booking"), ["waiting"])
        intake(b, "да", reply_to=card)
        self.assertEqual(len(b.red("create_booking")), 1)
        self.assertTrue(any("✅ Бронь записана" in t for t in intake_texts()), intake_texts())
        cs = cases(self.p)
        self.assertEqual([c["origin"] for c in cs], ["intake"])
        appr = [e for e in expects(self.p, "approval") if e["action"] == "booking"]
        self.assertEqual([e["case_id"] for e in appr], [cs[0]["case_id"]], "attach_expectation — к делу брони")
        self.assertEqual(self.state_of("readback"), ["answered"])

    def test_booking_card_after_restart_not_executed(self):
        b = Bridge([row_cur()])
        card = self.bk_card(b)
        S._RC_STORE = None                           # рестарт процесса: новый Store, новый boot_id
        intake(b, "да", reply_to=card)
        self.assertEqual(b.red("create_booking"), [], "карточка брони годна только в своём запуске (UNKNOWN TTL)")
        self.assertEqual([a["verdict"] for a in answers(self.p)], ["reference_restart"])
        self.assertTrue(any("прошлого запуска" in t for t in intake_texts()), intake_texts())

    def test_unknown_outcome_read_back_on_next_tick(self):
        """Обрыв после записи моста → mark_written(unknown) → такт следующего сообщения читает назад (pending_checks),
        мост повторно не зовётся (I15)."""
        b = Bridge([row_today()])
        b.activate_mode = "raise_after_write"
        card = self.ho_card(b)
        intake(b, "да", reply_to=card)
        self.assertEqual(len(b.red("activate_booking")), 1)
        self.assertTrue(any("неизвестен" in t for t in intake_texts()), intake_texts())
        self.assertEqual(self.state_of("readback"), ["flight_unknown"])
        intake(b, "привет", uname="deramor", uid=MANAGER_ID)
        self.assertEqual(self.state_of("readback"), ["answered"], "такт: чтение назад нашло «В аренде»")
        self.assertEqual(len(b.red("activate_booking")), 1, "повтора записи нет")

    def test_case_changed_between_yes_and_claim_bridge_not_called(self):
        """Мутант шва SS3 (exact_1010): «да» принято, но до захвата исполнения другая роль продлила аренду дела
        (reconcile_rental → period_changed, версия +1). Настоящий CAS claim_execution (P-M9) обязан дать conflict —
        мост и билет 4.2 не зовутся, человеку — слова о новой карточке, ожидание чтения назад не захвачено."""
        import rental_case
        b = Bridge([row_today()])
        card = self.ho_card(b)
        other = rental_case.Store(self.p, role="test")
        st = S._rc_store()
        real = st.claim_execution
        seen = []

        def bump_then_claim(*a, **k):
            cid = cases(self.p)[0]["case_id"]
            ver0 = cases(self.p)[0]["ver"]
            t = time.time()
            moved = [dict(r, date_end=dt(7)) for r in b.rows]
            rr = other.reconcile_rental(cid, rows=moved, source={"name": "тест", "ref": "row", "method": "door",
                                                                 "read_at": t, "observed_at": t},
                                        by={"kind": "code", "id": None, "name": "t"},
                                        idem_key="recon:test:%s:%s" % (cid, t))
            seen.append((ver0, rr.get("code"), cases(self.p)[0]["ver"]))
            return real(*a, **k)

        st.claim_execution = bump_then_claim
        try:
            intake(b, "да", reply_to=card)
        finally:
            st.claim_execution = real
        self.assertEqual(len(seen), 1, "захват исполнения не вызывался — «да» не дошло до исполнения")
        self.assertEqual(seen[0][1], "ok", "продление не записано: %r" % (seen,))
        self.assertGreater(seen[0][2], seen[0][0], "версия дела не поднялась: %r" % (seen,))
        self.assertEqual(b.red("activate_booking"), [], "версия дела сменилась после карточки — мост звать нельзя")
        self.assertEqual(b.tickets, 0, "билет 4.2 выписан при конфликте версии")
        self.assertTrue(any("дело изменилось после карточки" in t for t in intake_texts()), intake_texts())
        self.assertEqual(self.state_of("readback"), ["superseded"],
                         "подъём версии отзывает план чтения назад в той же транзакции (DESIGN §4.2); захвата нет")

    def test_confirm_link_published_and_decided_by_reply(self):
        """Публикация confirm_link во «Входящие» (шаг 7): вопрос продолжения, рождённый open_case другой роли,
        уходит карточкой на такте; «да» одобряющего реплаем → decide_link(same) — дело перепривязано, второго нет."""
        import rental_case
        t = time.time()
        src = {"name": "тест", "ref": "row", "method": "door", "read_at": t, "observed_at": t}
        other = rental_case.Store(self.p, role="test")
        cur = row_cur()
        nxt = row_cur(row=24, status="Бронь", date_start=dt(2), date_end=dt(6), booking_id="bk-next")
        o1 = other.open_case(origin="test", by={"kind": "code", "id": None, "name": "t"}, idem_key="open:test:bk:bk-cur",
                             rental_row=cur, source=src)
        self.assertEqual(o1.get("code"), "ok", o1)
        o2 = other.open_case(origin="test", by={"kind": "code", "id": None, "name": "t"},
                             idem_key="open:test:bk:bk-next", rental_row=nxt, source=src)
        self.assertEqual((o2.get("code"), str(o2.get("reason")).split(":")[0]), ("unknown", "possible_continuation"),
                         o2)
        b = Bridge([cur, nxt])
        intake(b, "привет", uname="deramor", uid=MANAGER_ID)          # такт: публикация плана confirm_link
        link_cards = cards("🔗 Дело аренды")
        self.assertEqual(len(link_cards), 1, intake_texts())
        self.assertEqual(self.state_of("confirm_link"), ["waiting"])
        intake(b, "да", reply_to=link_cards[0])
        self.assertTrue(any("решение «same» записано" in t for t in intake_texts()), intake_texts())
        self.assertEqual(self.state_of("confirm_link"), ["answered"])
        self.assertEqual(len(cases(self.p)), 1, "продолжение не родило второго дела")
        self.assertEqual([r["booking_id"] for r in rentals(self.p)], ["bk-next"])

    def test_store_unavailable_fail_closed(self):
        os.environ.pop("RENTAL_CASE_DB", None)
        S._RC_STORE = None
        b = Bridge([row_today()])
        do_handover(b)
        self.assertEqual(cards("Активирую"), [])
        self.assertTrue(any("⚠️ ВЫДАЧА" in t and "руками" in t for t in intake_texts()), intake_texts())
        intake(b, "да", uname="deramor", uid=None)
        self.assertEqual(b.red("activate_booking"), [], "флаг включён, хранилища нет — «да» не исполняется")
        self.assertTrue(any("Хранилище дела недоступно" in t for t in intake_texts()), intake_texts())


if __name__ == "__main__":
    if "--child-off" in sys.argv:
        print(CHILD_MARK + json.dumps(child_off(), ensure_ascii=True, sort_keys=True))
        sys.exit(0)
    unittest.main()
