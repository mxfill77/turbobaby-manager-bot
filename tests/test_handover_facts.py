# -*- coding: utf-8 -*-
"""HOFACTS1910 (19.10.2026): карточка выдачи проверяет факты — строка брони по точному дню, договор, залог.

Повод: карта цикла 19.10 (этап handover, пробелы 1 и 2; отрезок №3 HOFACTS). Карточка активации брала ПОСЛЕДНЮЮ по
листу строку «Бронь/В аренде» номера (`cand[-1]`), вкладка состояния — самый поздний date_start: будущая бронь другого
клиента того же байка, записанная ниже сегодняшней, выигрывала в обоих местах. В карточке не было ни договора, ни
залога — «да» человека было штампом на каждой выдаче.

Флаг HANDOVER_FACTS (по умолчанию ВЫКЛ, читается на каждый вызов):
  (A) чистый модуль handover_facts — шесть исходов реестра дают шесть разных строк (таймаут — «неизвестно, а не
      «договора нет»», хвоста GW_NOT_BRIDGE нет), залог 7000 / passport / пусто, исключение — первой строкой, в
      словах нет телефона, полного doc_id и pdf_id; граница импортов — ast;
  (B) настоящие обработчики Splinter (`_handle_servicing` → state_set + `_handover_activation_card` → `_handle_intake`)
      с мостом-подделкой: две «Бронь» одного номера (сегодняшняя выше, будущая ниже) — флаг ВЫКЛ называет будущую
      (закреплённый прежний дефект, текст карточки прежний байт-в-байт, contract_find не зовётся), флаг ВКЛ —
      сегодняшнюю, «да» реплаем → ровно один билет и activate_booking клиента сегодняшней строки, вкладка состояния —
      его же клиент и date_end; договор/залог не найдены → исключение первой строкой, маршрут «да» прежний; брони на
      сегодня нет → ⚠️ с вопросом pick, ни карточки, ни чтения реестра, ни записи; сбой и таймаут двери —
      «неизвестно», карточка не ждёт; сбор фактов сломан — карточка уходит с «факты не собраны»;
  (C) флаг ВЫКЛ в отдельном процессе: модулей handover_facts / contract_ref / rental_case_rules в процессе нет.

Сеть запрещена подменой socket (rental_case_fakes), память Splinter — во временном каталоге прогона (TMP/K4_TTMP).
Хранилище К4 не открывается (RENTAL_CASE_DB не задан). Данные синтетические.
"""
import ast
import asyncio
import datetime
import json
import os
import subprocess
import sys
import tempfile
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (HERE, ROOT):                  # итог: ROOT — первым, tests/ — вторым (чужой корень не берём)
    while _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

FLAGS = ("RENTAL_CASE", "RENTAL_CASE_PICK", "RENTAL_CASE_APPROVALS", "RENTAL_CASE_DB", "CONTRACT_REF_GEN",
         "HANDOVER_FACTS")
for _f in FLAGS:
    os.environ.pop(_f, None)
os.environ.pop("INTAKE_CONFIRM_STRICT", None)       # ручка не задана → строгий режим по умолчанию

TTMP = os.environ.get("K4_TTMP") or tempfile.gettempdir()
STATE_DIR = tempfile.mkdtemp(prefix="hofacts_state_", dir=TTMP)
for _k, _name in (("HINT_DEDUP_STATE", "hint_dedup_state.json"), ("DECIDER_LIVE_STATE", "decider_live_state.json"),
                  ("WORKS_PERSIST_STATE", "works_persist_state.json"), ("MILEAGE_Q_STATE", "mileage_q.json"),
                  ("SVC_TOKENS_STATE", "svc_tokens.json"), ("TOPIC_FEED_DIR", "topic_feed"),
                  ("SPLINTER_ASK_STAFF_STATE", "staff_ask_state.json"), ("SPLINTER_RULES_SNAP", "rules_snap.json"),
                  ("WALLET_CACHE_FILE", "wallet_cache.json"), ("ENQUEUE_DEDUP_FILE", "enqueue_dedup.json"),
                  ("RESTART_HANDOFF_STATE", "restart_handoff.json")):
    os.environ[_k] = os.path.join(STATE_DIR, _name)

import rental_case_fakes as F  # noqa: E402 — сеть запрещена при импорте

try:
    import fcntl  # noqa: F401
except ImportError:
    _fc = types.ModuleType("fcntl")
    _fc.LOCK_SH, _fc.LOCK_EX, _fc.LOCK_NB, _fc.LOCK_UN = 1, 2, 4, 8
    _fc.flock = lambda *a, **k: None
    _fc.lockf = lambda *a, **k: None
    sys.modules["fcntl"] = _fc

import splinter as S  # noqa: E402

NEW_MODS = ("handover_facts", "contract_ref", "rental_case_rules", "rental_case")
MODS_AT_IMPORT = sorted(m for m in NEW_MODS if m in sys.modules)
CHILD_MARK = "HOFACTS_CHILD_OFF "

SERV_CHAT = -1002751134848
TOPIC = 4242
BIKE = "CB 300CC R 9011"
INTAKE = S.INTAKE_CHAT
APPROVER = "deramor"                 # INTAKE_APPROVERS (по нику)
TZ = datetime.timedelta(hours=7)
P = "🐀 Splinter\n"
NAME_A, NAME_B = "Анна Сегодня", "Пётр Будущий"
PHONE_A, PHONE_B = "+66 82 555 1111", "+66 89 999 0000"
DOC_A = "1HoFaCtS-synthetic-doc-id-0000000000a1b2c3"
PDF_A = "PDF-synthetic-hofacts-0001"


def local_now():
    return datetime.datetime.now(datetime.timezone.utc) + TZ


def dt(days, hm="10:00"):
    return "%s %s" % ((local_now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d"), hm)


def day(days):
    return (local_now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")


def dm(days):
    d = local_now() + datetime.timedelta(days=days)
    return "%02d.%02d" % (d.day, d.month)


def row_a(**kw):
    """Сегодняшняя бронь (клиент A) — ВЫШЕ по листу."""
    base = dict(row=700, status="Бронь", bike=BIKE, name=NAME_A, date_start=dt(0, "09:00"), date_end=dt(5),
                contacts=PHONE_A, booking_id="bk-a", deposit_raw="7000", debt=0)
    base.update(kw)
    return F.make_row(**base)


def row_b(**kw):
    """Будущая бронь того же байка (клиент B) — НИЖЕ по листу: прежний cand[-1] и max(date_start) берут её."""
    base = dict(row=720, status="Бронь", bike=BIKE, name=NAME_B, date_start=dt(3), date_end=dt(10),
                contacts=PHONE_B, booking_id="bk-b", deposit_raw="passport", debt=0)
    base.update(kw)
    return F.make_row(**base)


# ----------------------------------------------------------------------------- ответы двери contract_find (живой формат)
def citem(row, status="ПОДПИСАН", doc=DOC_A, phone="+66825551111", bike=BIKE, date=None, signed_at=None, pdf_id=None):
    c = F.make_contract(row=row, doc_id=doc, client=NAME_A, contract_date=date or day(0), bike=bike, phone=phone,
                        signed=(status == "ПОДПИСАН"), status=status,
                        signed_at=(signed_at if signed_at is not None else
                                   ("%s 08:40" % day(0) if status == "ПОДПИСАН" else "")),
                        pdf_id=(pdf_id if pdf_id is not None else (PDF_A if status == "ПОДПИСАН" else "")))
    c["matched_on"] = ["bike"]
    c.pop("nick", None)
    return c


def fresp(items, outcome=None, unread=(), undated_signed=0):
    its = sorted((dict(i) for i in items), key=lambda x: -int(x["row"]))
    signed = [i for i in its if i.get("signed")]
    if outcome is None:
        outcome = ("none" if not its else "none_signed" if not signed else "ambiguous" if len(signed) > 1 else "one")
    return {"ok": True, "outcome": outcome, "pick": (dict(signed[0], pdf_ready=True) if outcome == "one" else None),
            "reason": None, "items": its, "undated_items": [],
            "checked": {"sheet": "Реестр", "rows_scanned": 240, "span_from": day(0), "span_to": day(5),
                        "undated": 0, "undated_signed": undated_signed, "date_unparsed": 0, "unread": list(unread),
                        "complete": not unread, "matched": len(its), "signed": len(signed), "returned": len(its),
                        "truncated": False},
            "filter": {"phone_last9": "", "name": "", "bike": BIKE, "date_from": day(0), "date_to": day(5)}}


SIGNED_A = fresp([citem(36)])


# --------------------------------------------------------------------------------------------- подделки Telegram/моста
class BotUser(object):
    id = 1
    username = "turbobaby_manager_bot"
    is_bot = True


class U(object):
    def __init__(self, uname="extthiwxer"):
        self.username = uname
        self.id = None
        self.is_bot = False


class Sent(object):
    def __init__(self, mid, chat_id, text):
        self.message_id = mid
        self.chat_id = chat_id
        self.text = text
        self.at = time.monotonic()
        self.date = datetime.datetime.now(datetime.timezone.utc)
        self.from_user = BotUser()


class Msg(object):
    _next = [930000]

    def __init__(self, text, chat_id=SERV_CHAT, uname="extthiwxer", reply=None):
        Msg._next[0] += 1
        self.message_id = Msg._next[0]
        self.text = text
        self.caption = None
        self.photo = None
        self.sticker = None
        self.chat_id = chat_id
        self.message_thread_id = (TOPIC if chat_id == SERV_CHAT else None)
        self.media_group_id = None
        self.date = datetime.datetime.now(datetime.timezone.utc)
        self.from_user = U(uname)
        self.reply_to_message = reply


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
    """Мост: дверь clients (живой формат) + contract_find (ответ | исключение | функция) + красные шаги — журнал."""

    def __init__(self, rows, contract=SIGNED_A):
        self.rows = [dict(r) for r in rows]
        self.contract = contract
        self.finds = []
        self.activated = []
        self.states = []
        self.tickets = 0

    def _call(self, action, **k):
        assert action == "clients", action
        return F.clients_reply(self.rows, filter=k.get("filter", "all"))

    def contract_find(self, **k):
        self.finds.append(dict(k))
        c = self.contract
        if isinstance(c, BaseException):
            raise c
        if callable(c):
            return c(**k)
        return c

    def find_bike(self, q):
        return {"name": BIKE, "status": "ДОМА", "oil_last_km": 30500}

    def read_events(self, bike, limit=30):
        return {"ok": False, "error": "нет в подделке"}

    def state_set(self, **k):
        self.states.append(dict(k))
        return {"ok": True}

    def add_event(self, **k):
        return {"ok": True, "saved": True}

    def service_pending_get(self, *a, **k):
        return {"ok": False, "error": "not_found"}

    def service_list(self, *a, **k):
        return {"items": []}

    def closing_upsert(self, **k):
        return {"ok": True, "total_due": 0}

    def issue_write_ticket(self):
        self.tickets += 1
        return {"ok": True, "ticket": "t-hofacts"}

    def activate_booking(self, bike, name, date_start=None):
        self.activated.append({"bike": bike, "name": name, "date_start": date_start})
        for r in self.rows:
            if r["bike"] == bike and r["name"] == name and r["status"] == "Бронь":
                r["status"] = "В аренде"
                return {"ok": True, "activated": True, "row": r["row"], "bike": bike, "name": name}
        return {"ok": False, "error": "booking_not_found", "message": "не найдена"}


SENDS = []
_MID = [940000]


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
BUDGET0 = S._HO_FACTS_BUDGET_S


def reset():
    del SENDS[:]
    for d in (S._HANDOVER_ACTIVATIONS, S._HO_ACT_WARN_TS, S._INTAKE_DRAFTS, S._CARD_LAST, S._PENDING_WORKS):
        d.clear()
    S._RC_STORE = None
    S._HO_FACTS_BUDGET_S = BUDGET0
    for f in FLAGS:
        os.environ.pop(f, None)
    os.environ.pop("INTAKE_CONFIRM_STRICT", None)


def run(coro):
    return asyncio.run(coro)


def do_handover(b):
    run(S._handle_servicing(Msg("выдаю клиенту, повёз"), Ctx(), b, FakeClaude(HO_PARSE)))


def intake_texts():
    return [s.text for s in SENDS if s.chat_id == INTAKE]


def cards():
    return [s for s in SENDS if s.chat_id == INTAKE and "Активирую" in s.text]


def say_yes(b, card):
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname=APPROVER, reply=card), Ctx(), b, None))


def old_card(row):
    """Прежний текст карточки (splinter@947953e:9688-9692) — флаг ВЫКЛ обязан дать его байт-в-байт."""
    dates = (str(row["date_start"]) + " — " + str(row["date_end"])).strip(" —")
    return (P + "🏍 ВЫДАЧА: %s → %s, бронь строка %s (%s).\nАктивирую (Бронь→В аренде)? да / нет"
            % (BIKE, row["name"], row["row"], dates))


def hf():
    import handover_facts
    return handover_facts


# ================================================================================================= (A) чистый модуль
class A_Pure(unittest.TestCase):
    def setUp(self):
        reset()

    def tearDown(self):
        reset()

    def _res(self, found, row=None):
        return hf().versions_of(row or row_a(), found)

    def test_a1_six_registry_outcomes_six_lines(self):
        H = hf()
        res = {
            "current": self._res(SIGNED_A),
            "pending": self._res(fresp([citem(37, status="ОТПРАВЛЕН")])),
            "none": self._res(fresp([])),
            "ambiguous": self._res(fresp([citem(36), citem(38, doc="2HoFaCtS-other-doc-0000ffee99")])),
            "incomplete": self._res(fresp([citem(36)], unread=["Лист2"])),
            "timeout": H.timeout(8),
        }
        self.assertEqual({k: v["outcome"] for k, v in res.items()},
                         dict((k, k) for k in res), "исходы versions() на синтетике")
        lines = dict((k, H.contract_fact(v)) for k, v in res.items())
        self.assertEqual(len(set(ln for ln, _x in lines.values())), 6, lines)
        self.assertEqual(lines["current"], ("📄 Договор: подписан · стр. 36 · doc …a1b2c3", None))
        self.assertEqual(lines["pending"][0], "📄 Договор: ждёт подписи · стр. 37 ОТПРАВЛЕН · doc …a1b2c3 ⚠️")
        self.assertEqual(lines["none"][0],
                         "📄 Договор: подписанного и ждущего подписи в реестре нет (строк в сроке: 0) ⚠️")
        self.assertEqual(lines["ambiguous"][0],
                         "📄 Договор: подписанных несколько (стр. 38, стр. 36) — какой текущий, решает человек ⚠️")
        self.assertTrue(lines["incomplete"][0].startswith(
            "📄 Договор: реестр прочитан не полностью или привязка не сверена (реестр прочитан не целиком"), lines)
        self.assertEqual(lines["timeout"][0],
                         "📄 Договор: реестр не ответил за 8 с — неизвестно, а не «договора нет» ⚠️")
        self.assertEqual({k: x for k, (_ln, x) in lines.items()},
                         {"current": None, "pending": "договор не подписан", "none": "подписанного договора нет",
                          "ambiguous": "договоров несколько", "incomplete": "договор не сверен",
                          "timeout": "договор неизвестен"})
        for k, (ln, _x) in lines.items():
            self.assertNotIn("мост его не пересоберёт", ln, k)          # хвост GW_NOT_BRIDGE не берётся

    def test_a2_unread_and_no_term_are_unknown_not_no_contract(self):
        H = hf()
        door_off = self._res({"ok": False, "error": "unknown_action"})          # мост без двери (до выкладки)
        self.assertEqual(door_off["outcome"], "unknown")
        self.assertEqual(H.contract_fact(door_off),
                         ("📄 Договор: реестр не прочитан (unknown_action) — неизвестно, а не «договора нет» ⚠️",
                          "договор неизвестен"))
        self.assertEqual(H.contract_fact(H.unread("RuntimeError")),
                         ("📄 Договор: реестр не прочитан (RuntimeError) — неизвестно, а не «договора нет» ⚠️",
                          "договор неизвестен"))
        self.assertEqual(H.contract_fact(self._res("не словарь"))[1], "договор неизвестен")
        self.assertEqual(H.contract_fact(None)[1], "договор неизвестен")
        long_why = H.contract_fact(H.unread("x" * 500))[0]
        self.assertLess(len(long_why), 200, "причина двери обрезается")
        self.assertIsNone(H.find_args(row_a(bike="без номера")), "нет номера байка — реестр не читается")
        self.assertIsNone(H.find_args(row_a(date_end=None)), "нет конца срока — реестр не читается")
        self.assertEqual(H.contract_fact(H.no_term()),
                         ("📄 Договор: в строке брони нет номера байка или срока — реестр не читал ⚠️",
                          "договор не сверен"))

    def test_a3_deposit_lines(self):
        H = hf()
        self.assertEqual(H.deposit_fact("7000"), ("💰 Залог по брони: 7 000 ฿", None))
        self.assertEqual(H.deposit_fact("20000.0"), ("💰 Залог по брони: 20 000 ฿", None))
        self.assertEqual(H.deposit_fact("passport"), ("💰 Залог по брони: паспорт", None))
        self.assertEqual(H.deposit_fact(" Паспорт "), ("💰 Залог по брони: паспорт", None))
        self.assertEqual(H.deposit_fact(""), ("💰 Залог по брони: не указан ⚠️", "залог не указан"))
        self.assertEqual(H.deposit_fact("0"), ("💰 Залог по брони: 0 ฿ ⚠️", "залог 0 ฿"))
        self.assertEqual(H.deposit_fact(None, 5000), ("💰 Залог по брони: 5 000 ฿", None), "старый мост без S сырьём")
        self.assertEqual(H.deposit_fact(None, 0), ("💰 Залог по брони: не указан ⚠️", "залог не указан"))
        ln, x = H.deposit_fact("наличка у Пыма +66 81 000 0000")
        self.assertEqual((ln, x), ("💰 Залог по брони: в CRM записан не числом и не «паспорт» — не разобран ⚠️",
                                   "залог не разобран"))
        self.assertNotIn("0000", ln, "рукописная клетка не повторяется")

    def test_a4_exception_is_first_line(self):
        H = hf()
        ok = H.facts(row_a(), self._res(SIGNED_A))
        self.assertIsNone(ok["head"])
        self.assertEqual(ok["lines"], ["📄 Договор: подписан · стр. 36 · doc …a1b2c3", "💰 Залог по брони: 7 000 ฿"])
        both = H.facts(row_a(deposit_raw=""), self._res(fresp([])))
        self.assertEqual(both["head"], "⚠️ Исключение: подписанного договора нет · залог не указан")
        self.assertEqual(both["exceptions"], ["подписанного договора нет", "залог не указан"])
        dep = H.facts(row_a(deposit_raw=""), self._res(SIGNED_A))
        self.assertEqual(dep["head"], "⚠️ Исключение: залог не указан")

    def test_a5_no_pii_no_full_ids_in_words(self):
        H = hf()
        out = H.facts(row_a(), self._res(SIGNED_A))
        text = "\n".join(out["lines"])
        for bad in (DOC_A, PDF_A, "825551111", "82 555", NAME_A, "bk-a"):
            self.assertNotIn(bad, text, bad)
        for res in (self._res(fresp([citem(37, status="ОТПРАВЛЕН")])), self._res(fresp([citem(36)], unread=["L2"]))):
            t = "\n".join(H.facts(row_a(), res)["lines"])
            self.assertNotIn(DOC_A, t)
            self.assertNotIn("825551111", t)

    def test_a6_module_boundary(self):
        path = os.path.join(ROOT, "handover_facts.py")
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        imports = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                imports |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                imports.add((n.module or "").split(".")[0])
        self.assertEqual(imports, {"re", "contract_ref"})
        bad = {"open", "exec", "eval", "__import__", "input", "os", "sys", "socket", "sqlite3", "subprocess", "time",
               "datetime", "splinter", "bridge_client"}
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        self.assertFalse(used & bad, used & bad)
        self.assertFalse([n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr in ("contract_find",
                                                                                                   "_call")])

    def test_a7_find_args_term_of_row(self):
        H = hf()
        self.assertEqual(H.find_args(row_a()), {"bike": BIKE, "date_from": day(0), "date_to": day(5), "limit": 100})


# ===================================================================================== (B) карточка выдачи в Splinter
class B_Card(unittest.TestCase):
    def setUp(self):
        reset()

    def tearDown(self):
        reset()

    def on(self):
        os.environ["HANDOVER_FACTS"] = "1"

    def test_b1_off_two_bookings_names_future_row_old_text(self):
        """Флаг ВЫКЛ: прежний дефект закреплён — карточка называет будущую строку 720, вкладка состояния — её клиента;
        текст карточки — прежний байт-в-байт; реестр не читается."""
        b = Bridge([row_a(), row_b()])
        do_handover(b)
        cs = cards()
        self.assertEqual([c.text for c in cs], [old_card(row_b())], intake_texts())
        self.assertEqual(b.finds, [], "флаг ВЫКЛ — contract_find не зовётся")
        self.assertEqual([(s["client"], s["date_due"], s["booking_id"]) for s in b.states],
                         [(NAME_B, row_b()["date_end"], "bk-b")], "флаг ВЫКЛ — max(date_start), прежний выбор")
        say_yes(b, cs[0])
        self.assertEqual(b.activated, [{"bike": BIKE, "name": NAME_B, "date_start": row_b()["date_start"]}])

    def test_b2_on_two_bookings_names_today_row_yes_activates_it(self):
        """Флаг ВКЛ: карточка — строка 700 (сегодня), «да» реплаем → ровно один билет и activate_booking(A, старт A);
        вкладка состояния — клиент A и date_end строки A."""
        self.on()
        b = Bridge([row_a(), row_b()])
        do_handover(b)
        cs = cards()
        self.assertEqual(len(cs), 1, intake_texts())
        self.assertIn("бронь строка 700", cs[0].text)
        self.assertIn(NAME_A, cs[0].text)
        self.assertNotIn(NAME_B, cs[0].text)
        self.assertNotIn("строка 720", cs[0].text)
        self.assertEqual([(s["client"], s["date_due"], s["booking_id"]) for s in b.states],
                         [(NAME_A, row_a()["date_end"], "bk-a")])
        say_yes(b, cs[0])
        self.assertEqual(b.tickets, 1, "красный шаг — строго под одним билетом 4.2")
        self.assertEqual(b.activated, [{"bike": BIKE, "name": NAME_A, "date_start": row_a()["date_start"]}])
        self.assertTrue(any("✅ В аренде" in t and "строка 700" in t for t in intake_texts()), intake_texts())

    def test_b3_on_facts_ok_no_exception_line(self):
        self.on()
        b = Bridge([row_a(), row_b()])
        do_handover(b)
        c = cards()[0].text.split("\n")
        self.assertEqual(c[0], "🐀 Splinter")
        self.assertTrue(c[1].startswith("🏍 ВЫДАЧА: %s → %s, бронь строка 700" % (BIKE, NAME_A)), c)
        self.assertEqual(c[2:], ["📄 Договор: подписан · стр. 36 · doc …a1b2c3", "💰 Залог по брони: 7 000 ฿",
                                 "Активирую (Бронь→В аренде)? да / нет"])
        self.assertEqual(b.finds, [{"bike": BIKE, "date_from": day(0), "date_to": day(5), "limit": 100}],
                         "ровно один contract_find — по байку и сроку выбранной строки")

    def test_b4_on_missing_contract_and_deposit_named_first_yes_route_same(self):
        """Договора нет, залог не указан → исключение первой строкой (после подписи). Слова «да/нет» и маршрут
        APPROVEFIX прежние: решает человек, «да» реплаем активирует ту же строку."""
        self.on()
        b = Bridge([row_a(deposit_raw=""), row_b()], contract=fresp([]))
        do_handover(b)
        cs = cards()
        lines = cs[0].text.split("\n")
        self.assertEqual(lines[:2], ["🐀 Splinter", "⚠️ Исключение: подписанного договора нет · залог не указан"])
        self.assertIn("💰 Залог по брони: не указан ⚠️", lines)
        self.assertEqual(lines[-1], "Активирую (Бронь→В аренде)? да / нет")
        run(S._handle_intake(Msg("да", chat_id=INTAKE, uname=APPROVER), Ctx(), b, None))      # без реплая
        self.assertEqual(b.activated, [], "без реплая на карточку согласие не засчитывается (APPROVEFIX)")
        say_yes(b, cs[0])
        self.assertEqual(b.activated, [{"bike": BIKE, "name": NAME_A, "date_start": row_a()["date_start"]}])
        self.assertEqual(b.tickets, 1)

    def test_b5_on_pending_contract_passport_deposit(self):
        self.on()
        b = Bridge([row_a(deposit_raw="passport")], contract=fresp([citem(37, status="ОТПРАВЛЕН")]))
        do_handover(b)
        lines = cards()[0].text.split("\n")
        self.assertEqual(lines[1], "⚠️ Исключение: договор не подписан")
        self.assertIn("📄 Договор: ждёт подписи · стр. 37 ОТПРАВЛЕН · doc …a1b2c3 ⚠️", lines)
        self.assertIn("💰 Залог по брони: паспорт", lines)

    def test_b6_on_door_error_is_unknown_card_still_sent(self):
        self.on()
        b = Bridge([row_a()], contract=RuntimeError("обрыв"))
        do_handover(b)
        lines = cards()[0].text.split("\n")
        self.assertEqual(lines[1], "⚠️ Исключение: договор неизвестен")
        self.assertIn("📄 Договор: реестр не прочитан (RuntimeError) — неизвестно, а не «договора нет» ⚠️", lines)
        self.assertEqual(len(b.finds), 1)

    def test_b7_on_timeout_card_not_delayed(self):
        """Реестр молчит дольше потолка → «неизвестно», карточка уходит по потолку, а не по ответу двери."""
        self.on()
        S._HO_FACTS_BUDGET_S = 0.2

        def slow(**k):
            time.sleep(1.5)
            return SIGNED_A
        b = Bridge([row_a()], contract=slow)
        t0 = time.monotonic()
        do_handover(b)
        cs = cards()
        self.assertEqual(len(cs), 1, intake_texts())
        self.assertLess(cs[0].at - t0, 1.2, "карточка ждала ответа двери дольше потолка")
        lines = cs[0].text.split("\n")
        self.assertEqual(lines[1], "⚠️ Исключение: договор неизвестен")
        self.assertIn("📄 Договор: реестр не ответил за 0.2 с — неизвестно, а не «договора нет» ⚠️", lines)
        say_yes(b, cs[0])
        self.assertEqual(len(b.activated), 1, "маршрут «да» прежний и при неизвестном договоре")

    def test_b8_on_no_booking_today_warns_with_pick_question(self):
        """Брони на сегодня нет (только будущая) → ⚠️ с вопросом pick; ни карточки, ни реестра, ни записи."""
        self.on()
        b = Bridge([row_b()])
        do_handover(b)
        self.assertEqual(cards(), [], intake_texts())
        warns = [t for t in intake_texts() if "⚠️ ВЫДАЧА" in t]
        self.assertEqual(len(warns), 1, intake_texts())
        self.assertIn("Брони этого байка на этот день нет — это ранняя выдача брони с %s (%s)?" % (dm(3), NAME_B),
                      warns[0])
        self.assertIn("активируй руками", warns[0])
        self.assertEqual(b.finds, [])
        self.assertNotIn(INTAKE, S._HANDOVER_ACTIVATIONS)
        say_yes(b, None)
        self.assertEqual((b.activated, b.tickets), ([], 0))
        self.assertEqual([(s["client"], s["booking_id"]) for s in b.states], [("", "")],
                         "вкладка состояния — без чужого клиента (бронь не выбрана)")

    def test_b9_on_two_bookings_today_is_question(self):
        self.on()
        b = Bridge([row_a(), row_a(row=705, name="Вера Тоже", booking_id="bk-c", contacts="+66 80 111 2222")])
        do_handover(b)
        self.assertEqual(cards(), [])
        warns = [t for t in intake_texts() if "⚠️ ВЫДАЧА" in t]
        self.assertEqual(len(warns), 1, intake_texts())
        self.assertIn("Какая бронь выдаётся:", warns[0])
        self.assertEqual(b.finds, [])

    def test_b10_on_already_active_today_silent(self):
        self.on()
        b = Bridge([row_a(status="В аренде"), row_b()])
        do_handover(b)
        self.assertEqual(cards(), [])
        self.assertEqual(b.finds, [])
        self.assertEqual([(s["client"], s["booking_id"]) for s in b.states], [(NAME_A, "bk-a")])

    def test_b11_on_repeat_phrase_one_card_one_read(self):
        self.on()
        b = Bridge([row_a(), row_b()])
        do_handover(b)
        do_handover(b)
        self.assertEqual(len(cards()), 1)
        self.assertEqual(len(b.finds), 1, "повтор фразы выдачи реестр не перечитывает")

    def test_b12_on_no_k4_store(self):
        """Выбор строки — готовый pick без хранилища К4: Store не открывается, модуля rental_case в процессе нет."""
        self.on()
        b = Bridge([row_a(), row_b()])
        do_handover(b)
        say_yes(b, cards()[0])
        self.assertIsNone(S._RC_STORE)
        self.assertNotIn("rental_case", sys.modules)

    def test_b14_on_broken_facts_card_not_lost_not_silent(self):
        """Модуль фактов не загрузился → карточка всё равно уходит, первой строкой — «факты не собраны», реестр не
        читается, маршрут «да» прежний."""
        self.on()
        hf()
        saved = sys.modules.get("handover_facts")
        sys.modules["handover_facts"] = None            # import → ModuleNotFoundError (подкласс ImportError)
        try:
            b = Bridge([row_a(), row_b()])
            do_handover(b)
        finally:
            sys.modules["handover_facts"] = saved
        cs = cards()
        self.assertEqual(len(cs), 1, intake_texts())
        lines = cs[0].text.split("\n")
        self.assertEqual(lines[1], "⚠️ Исключение: факты карточки не собраны (ModuleNotFoundError) — договор и залог "
                                   "неизвестны")
        self.assertTrue(lines[2].startswith("🏍 ВЫДАЧА: %s → %s, бронь строка 700" % (BIKE, NAME_A)), lines)
        self.assertEqual(lines[3:], ["Активирую (Бронь→В аренде)? да / нет"])
        self.assertEqual(b.finds, [])
        say_yes(b, cs[0])
        self.assertEqual(b.activated, [{"bike": BIKE, "name": NAME_A, "date_start": row_a()["date_start"]}])

    def test_b13_flag_word_rule(self):
        for v, want in (("1", True), ("true", True), ("ON", True), ("yes", True), ("0", False), ("", False),
                        ("да", False), ("off", False)):
            os.environ["HANDOVER_FACTS"] = v
            self.assertIs(S._handover_facts_on(), want, v)
        os.environ.pop("HANDOVER_FACTS", None)
        self.assertIs(S._handover_facts_on(), False)
        self.assertEqual(S.F_HANDOVER_FACTS, "HANDOVER_FACTS")


# ================================================================================== (C) флаг ВЫКЛ — отдельный процесс
class C_OffProcess(unittest.TestCase):
    def test_c1_off_process_has_no_new_modules(self):
        self.assertEqual(MODS_AT_IMPORT, [], "модули ветки флага загружены уже импортом splinter")
        env = dict(os.environ)
        for f in FLAGS:
            env.pop(f, None)
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--child-off"], cwd=ROOT, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        lines = [ln for ln in (r.stdout or "").splitlines() if ln.startswith(CHILD_MARK)]
        self.assertEqual(r.returncode, 0, (r.stdout or "")[-2000:] + (r.stderr or "")[-2000:])
        self.assertEqual(len(lines), 1, r.stdout[-2000:])
        got = json.loads(lines[0][len(CHILD_MARK):])
        self.assertEqual(got["mods"], [], got)
        self.assertEqual(got["finds"], 0, got)
        self.assertEqual(got["card"], [old_card(row_b())], got)
        self.assertEqual(got["activated"], 1, got)


def _child_off():
    """Флаг ВЫКЛ, свой процесс: выдача + «да» — какие модули ветки флага оказались в процессе."""
    reset()
    b = Bridge([row_a(), row_b()])
    do_handover(b)
    cs = cards()
    if cs:
        say_yes(b, cs[0])
    print(CHILD_MARK + json.dumps({"mods": sorted(m for m in NEW_MODS if m in sys.modules), "finds": len(b.finds),
                                   "card": [c.text for c in cs], "activated": len(b.activated)}))   # ASCII: кодировка
    sys.stdout.flush()                                                                                # консоли любая


if __name__ == "__main__":
    if sys.argv[1:] == ["--child-off"]:
        _child_off()
        sys.exit(0)
    unittest.main(verbosity=2)
