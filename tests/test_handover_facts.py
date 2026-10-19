# -*- coding: utf-8 -*-
"""HOFACTS1910 (19.10.2026, v2 20.10): карточка выдачи проверяет факты — строка брони по точному ЦЕЛЕВОМУ дню, договор,
залог; день выдачи против брони — ручная карточка; вкладка состояния и «да» — только по той же брони.

Повод: карта цикла 19.10 (этап handover, пробелы 1 и 2; отрезок №3 HOFACTS). Карточка активации брала ПОСЛЕДНЮЮ по
листу строку «Бронь/В аренде» номера (`cand[-1]`), вкладка состояния — самый поздний date_start: будущая бронь другого
клиента того же байка, записанная ниже сегодняшней, выигрывала в обоих местах. В карточке не было ни договора, ни
залога — «да» человека было штампом на каждой выдаче. v2 — правило владельца 19.10 23:3x («Тогда надо переделать
договор и бронь, но если клиент опоздал на день то оплата считается со дня первоначальных договоренностей. Если он за
ранее не перенес.»), Codex TB-NIGHT-1910-2305 (HOFACTS) и TB-REVIEW-1910-2400 (HOFACTS v2), пробелы сверки
wf_2fc46177 у 003f626.

Флаг HANDOVER_FACTS (по умолчанию ВЫКЛ, читается на каждый вызов):
  (A) чистый модуль handover_facts — исходы реестра дают разные строки (таймаут — «неизвестно, а не «договора нет»»,
      хвоста GW_NOT_BRIDGE нет; неоднозначность двери и брони — разными словами; ждущих подписи несколько — перечнем),
      залог — голдены: «7,000»/«7.000»/«7 000» = 7000, дробь и смесь знаков — «не разобран», слова называют источник
      «записан в CRM» и «получение не сверено»; исключение — первой строкой; в словах нет телефона, полного doc_id и
      pdf_id; день против брони — дословно правило владельца; тождество строки; граница импортов — ast;
  (B) настоящие обработчики Splinter (`_handle_servicing` → `_ho_flow`: карточка → сверка той же брони → state_set;
      `_handle_intake` → «да») с мостом-подделкой: целевой день — местный день СООБЩЕНИЯ (фраза до местной полуночи,
      разобранная после неё; UTC-дата сообщения не та), не t0 чтения; брони на этот день нет, а на другой есть —
      ручная карточка без «да», без билета и без смены дат (позже / раньше / несколько — адресный вопрос); перед
      state_set и перед билетом «да» — повторное чтение той же брони (не та — записи нет, честная строка); запись,
      заведённая до флага / восстановленная рестартом, перед «да» сверяется; мост перевёл не ту строку — громко;
      CRM не прочитан — «неизвестно», а не «брони нет»; договор — дорогой `_contract_ref_report` (те же аргументы
      двери);
  (C) флаг ВЫКЛ в отдельном процессе: модулей handover_facts / contract_ref / rental_case_rules в процессе нет, тексты
      карточек и записи — прежние байт-в-байт.

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
UTC = datetime.timezone.utc
P = "🐀 Splinter\n"
NAME_A, NAME_B, NAME_C = "Анна Сегодня", "Пётр Будущий", "Вера Вчера"
PHONE_A, PHONE_B, PHONE_C = "+66 82 555 1111", "+66 89 999 0000", "+66 80 333 4444"
DOC_A = "1HoFaCtS-synthetic-doc-id-0000000000a1b2c3"
PDF_A = "PDF-synthetic-hofacts-0001"
NOT_CHECKED = " — получение не сверено"
DEP_MONEY_7000 = "💰 Залог по брони (записан в CRM): 7 000 ฿" + NOT_CHECKED
DEP_PASSPORT = "💰 Залог по брони (записан в CRM): паспорт" + NOT_CHECKED
DEP_NONE = "💰 Залог по брони: в CRM не указан ⚠️"
DOC_SIGNED = "📄 Договор: подписан · стр. 36 · doc …a1b2c3"
YES_LINE = "Активирую (Бронь→В аренде)? да / нет"
HAND_TAIL = "Сам не активирую и даты не меняю — после переоформления активируй руками (Бронь→В аренде)."


def local_now():
    return datetime.datetime.now(UTC) + TZ


def dt(days, hm="10:00"):
    return "%s %s" % ((local_now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d"), hm)


def day(days):
    return (local_now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d")


def dm(days):
    d = local_now() + datetime.timedelta(days=days)
    return "%02d.%02d" % (d.day, d.month)


def local_midnight_utc(days=0):
    """Местная (TZ+7) полночь дня `days` от сегодня — как UTC-время с зоной (так Telegram даёт msg.date)."""
    d = (local_now() + datetime.timedelta(days=days)).date()
    return datetime.datetime(d.year, d.month, d.day, tzinfo=UTC) - TZ


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


def row_c(**kw):
    """Вчерашняя бронь того же байка (клиент C) — ВЫШЕ всех по листу."""
    base = dict(row=690, status="Бронь", bike=BIKE, name=NAME_C, date_start=dt(-1, "11:00"), date_end=dt(2),
                contacts=PHONE_C, booking_id="bk-c", deposit_raw="5000", debt=0)
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
        self.date = datetime.datetime.now(UTC)
        self.from_user = BotUser()


class Msg(object):
    _next = [930000]

    def __init__(self, text, chat_id=SERV_CHAT, uname="extthiwxer", reply=None, date=None):
        Msg._next[0] += 1
        self.message_id = Msg._next[0]
        self.text = text
        self.caption = None
        self.photo = None
        self.sticker = None
        self.chat_id = chat_id
        self.message_thread_id = (TOPIC if chat_id == SERV_CHAT else None)
        self.media_group_id = None
        self.date = date if date is not None else datetime.datetime.now(UTC)
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
    """Мост: дверь clients (живой формат; `after_read` — правка строк после N-го чтения, `fail_reads` — номера чтений с
    обрывом) + contract_find (ответ | исключение | функция) + красные шаги — журнал."""

    def __init__(self, rows, contract=SIGNED_A, after_read=None, fail_reads=(), act_row=None):
        self.rows = [dict(r) for r in rows]
        self.contract = contract
        self.after_read = dict(after_read or {})
        self.fail_reads = set(fail_reads)
        self.act_row = act_row
        self.reads = 0
        self.finds = []
        self.activated = []
        self.states = []
        self.tickets = 0

    def _call(self, action, **k):
        assert action == "clients", action
        self.reads += 1
        if self.reads in self.fail_reads:
            raise RuntimeError("обрыв чтения clients")
        out = F.clients_reply(self.rows, filter=k.get("filter", "all"))
        fn = self.after_read.get(self.reads)
        if fn is not None:
            fn(self.rows)
        return out

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
                return {"ok": True, "activated": True, "row": self.act_row or r["row"], "bike": bike, "name": name}
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


def do_handover(b, date=None):
    run(S._handle_servicing(Msg("выдаю клиенту, повёз", date=date), Ctx(), b, FakeClaude(HO_PARSE)))


def intake_texts():
    return [s.text for s in SENDS if s.chat_id == INTAKE]


def cards():
    return [s for s in SENDS if s.chat_id == INTAKE and "Активирую" in s.text]


def hand_cards():
    return [s for s in SENDS if s.chat_id == INTAKE and HAND_TAIL in s.text]


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


def cref():
    import contract_ref
    return contract_ref


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
        self.assertEqual(lines["current"], (DOC_SIGNED, None))
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

    def test_a1b_door_ambiguity_and_many_pending_named_apart(self):
        """v2 (e): неоднозначность ДВЕРИ при одном привязанном подписанном — не «подписанных этой брони несколько»
        (как GW_AMBIGUOUS_DOOR у contract_ref); ждущих подписи две — вторая названа, а не потеряна."""
        H = hf()
        door = self._res(fresp([citem(36), citem(38, doc="2HoFaCtS-other-doc-0000ffee99", phone="+66 81 000 0000")]))
        self.assertEqual(door["outcome"], "ambiguous")
        self.assertEqual(H.contract_fact(door),
                         ("📄 Договор: под фильтром байка и срока подписанных несколько (стр. 38, стр. 36; привязанных к "
                          "брони — 1) — какой текущий, решает человек ⚠️", "договоров несколько"))
        two = self._res(fresp([citem(37, status="ОТПРАВЛЕН"), citem(39, status="НОВЫЙ", doc="3HoFaCtS-x-00009f9f")]))
        self.assertEqual(two["outcome"], "pending")
        self.assertEqual(H.contract_fact(two)[0],
                         "📄 Договор: ждёт подписи · стр. 39 НОВЫЙ · doc …009f9f · ещё ждут подписи: стр. 37 ⚠️")

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
        self.assertEqual(H.contract_fact(H.no_term()),
                         ("📄 Договор: в строке брони нет номера байка или срока — реестр не читал ⚠️",
                          "договор не сверен"))
        # исход ДОРОГИ _contract_ref_report: дверь не звана — по сроку (no_term) или сверка не собрана (неизвестно)
        CR = cref()
        self.assertEqual(H.from_report(row_a(), False, None, CR.GEN_NO_TERM)["outcome"], "no_term")
        broke = H.from_report(row_a(), False, None, S.W_CONTRACT_REF_BROKEN % "ImportError")
        self.assertEqual(H.contract_fact(broke),
                         ("📄 Договор: реестр не прочитан (сверка не собрана) — неизвестно, а не «договора нет» ⚠️",
                          "договор неизвестен"))
        self.assertEqual(H.from_report(row_a(), True, SIGNED_A, "слова")["outcome"], "current")
        self.assertEqual(H.from_report(row_a(), True, {"ok": False, "error": "RuntimeError"}, "")["reason"],
                         "реестр не прочитан: RuntimeError")

    def test_a3_deposit_goldens(self):
        """v2 (d): источник назван («записан в CRM»), получение — «не сверено»; разделители тысяч — 7000; спорный
        текст — «не разобран», значение клетки не повторяется."""
        H = hf()
        money = ("7000", "7,000", "7.000", "7 000", "7 000", "7 000", " 7000 ", "07000", 7000, 7000.0,
                 "7000.0", "7000,00", "7,000.00", "7.000,00")
        for raw in money:
            self.assertEqual(H.deposit_fact(raw), (DEP_MONEY_7000, None), repr(raw))
        self.assertEqual(H.deposit_fact("20000.0"), ("💰 Залог по брони (записан в CRM): 20 000 ฿" + NOT_CHECKED, None))
        self.assertEqual(H.deposit_fact("1,000,000"),
                         ("💰 Залог по брони (записан в CRM): 1 000 000 ฿" + NOT_CHECKED, None))
        self.assertEqual(H.deposit_fact("passport"), (DEP_PASSPORT, None))
        self.assertEqual(H.deposit_fact(" Паспорт "), (DEP_PASSPORT, None))
        self.assertEqual(H.deposit_fact(""), (DEP_NONE, "залог не указан"))
        for raw in ("0", "0,000", 0):
            self.assertEqual(H.deposit_fact(raw), ("💰 Залог по брони (записан в CRM): 0 ฿ ⚠️", "залог 0 ฿"), raw)
        self.assertEqual(H.deposit_fact(None, 5000),
                         ("💰 Залог по брони (записан в CRM): 5 000 ฿" + NOT_CHECKED, None), "старый мост без S сырьём")
        self.assertEqual(H.deposit_fact(None, 0), (DEP_NONE, "залог не указан"))
        unparsed = ("💰 Залог по брони: в CRM записан не числом и не «паспорт» — не разобран ⚠️", "залог не разобран")
        for raw in ("7.5", "7,50", "1,000.50", "1.000,5", "7,0000", "7.000,000", "7000 бат", "7000฿", "-7000", "7k",
                    "1,000.000", "1.000.00", 7000.5, True, float("nan"), "наличка у Пыма +66 81 000 0000"):
            self.assertEqual(H.deposit_fact(raw), unparsed, repr(raw))
        ln, _x = H.deposit_fact("наличка у Пыма +66 81 000 0000")
        self.assertNotIn("0000", ln, "рукописная клетка не повторяется")
        for raw in money + ("passport",):
            ln, _x = H.deposit_fact(raw)
            self.assertIn("(записан в CRM)", ln)
            self.assertTrue(ln.endswith(NOT_CHECKED), ln)

    def test_a4_exception_is_first_line(self):
        H = hf()
        ok = H.facts(row_a(), self._res(SIGNED_A))
        self.assertIsNone(ok["head"])
        self.assertEqual(ok["lines"], [DOC_SIGNED, DEP_MONEY_7000])
        both = H.facts(row_a(deposit_raw=""), self._res(fresp([])))
        self.assertEqual(both["head"], "⚠️ Исключение: подписанного договора нет · залог не указан")
        self.assertEqual(both["exceptions"], ["подписанного договора нет", "залог не указан"])
        dep = H.facts(row_a(deposit_raw=""), self._res(SIGNED_A))
        self.assertEqual(dep["head"], "⚠️ Исключение: залог не указан")
        unp = H.facts(row_a(deposit_raw="7,5"), self._res(SIGNED_A))
        self.assertEqual(unp["head"], "⚠️ Исключение: залог не разобран")
        self.assertIsNone(H.facts(row_a(deposit_raw="passport"), self._res(SIGNED_A))["head"],
                          "«получение не сверено» — слова строки, а не исключение на каждой выдаче")

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
        self.assertEqual(imports, {"re", "datetime", "contract_ref"})
        bad = {"open", "exec", "eval", "__import__", "input", "os", "sys", "socket", "sqlite3", "subprocess", "time",
               "splinter", "bridge_client"}
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        self.assertFalse(used & bad, used & bad)
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertFalse(attrs & {"contract_find", "_call", "now", "today", "utcnow", "fromtimestamp", "time"},
                         "двери и часы модулю не нужны: datetime — только разбор дня ISO")

    def test_a7_day_mismatch_owner_rule_words(self):
        """v2 (b): одна бронь на другой день — позже / раньше на N дн. словами правила владельца; несколько — перечень
        для вопроса; на тот же день или без дня — не суд этого модуля."""
        H = hf()
        late = H.day_mismatch([{"row": 700, "start_day": "2026-10-18", "name": NAME_A}], "2026-10-20")
        self.assertEqual((late["kind"], late["days"], late["cand"]["row"]), ("late", 2, 700))
        self.assertEqual(H.mismatch_line(late),
                         "Клиент берёт байк позже брони на 2 дн. (бронь с 18.10): переоформить договор и бронь. Если "
                         "перенос не согласован заранее — оплата с 18.10 (исходная дата).")
        early = H.day_mismatch([{"row": 720, "start_day": "2026-11-02"}], "2026-10-30")
        self.assertEqual((early["kind"], early["days"]), ("early", 3))
        self.assertEqual(H.mismatch_line(early),
                         "Выдача раньше брони на 3 дн. (бронь с 02.11): переоформить договор и бронь на фактические "
                         "даты.")
        many = H.day_mismatch([{"row": 1, "start_day": "2026-10-18"}, {"row": 2, "start_day": "2026-10-25"}],
                              "2026-10-20")
        self.assertEqual(many["kind"], "many")
        self.assertEqual(H.many_line("X 1", "2026-10-20", many["cands"] + [{"row": 3, "start_day": "2026-10-26",
                                                                            "name": "Н"},
                                                                           {"row": 4, "start_day": "2026-10-27"}]),
                         "⚠️ ВЫДАЧА X 1: брони на 20.10 нет, а броней этого байка несколько: строка 1 с 18.10 (?), "
                         "строка 2 с 25.10 (?), строка 3 с 26.10 (Н) и ещё 1 — какая выдаётся? Сам не выбираю, не "
                         "активирую и даты не меняю: договор и бронь переоформить руками.")
        self.assertIsNone(H.day_mismatch([], "2026-10-20"))
        self.assertIsNone(H.day_mismatch([{"row": 1, "start_day": "2026-10-20"}], "2026-10-20"))
        self.assertIsNone(H.day_mismatch([{"row": 1, "start_day": "2026-10-18"}], None))
        self.assertIsNone(H.day_mismatch([{"row": 1, "start_day": None}], "2026-10-20"))
        year = H.day_mismatch([{"row": 1, "start_day": "2026-12-30"}], "2027-01-02")
        self.assertEqual((year["kind"], year["days"]), ("late", 3), "через границу года")

    def test_a8_ident_same_booking(self):
        """v2 (c): тождество строки — строка, booking_id, номер, срок (дни), имя без регистра; статус не входит.
        Запись без тождества (рестарт / до флага) — строка, имя и начало срока как в записи."""
        H = hf()
        a = row_a()
        self.assertEqual(H.ident(a), [700, "bk-a", H.CR.binding_of_crm(a)["plate"], day(0), day(5), "анна сегодня"])
        self.assertEqual(H.ident(row_a(status="В аренде", date_start=dt(0, "12:00"))), H.ident(a),
                         "статус и час начала тождество не меняют")
        for other in (row_a(row=701), row_a(booking_id="bk-x"), row_a(date_end=dt(6)), row_a(name="Анна Другая"),
                      row_a(bike="ADV 350 1234")):
            self.assertNotEqual(H.ident(other), H.ident(a))
        rec = {"row": 700, "name": NAME_A, "date_start": a["date_start"], "ident": H.ident(a)}
        self.assertTrue(H.same_as_card(rec, a))
        self.assertFalse(H.same_as_card(rec, row_a(date_end=dt(6))))
        bare = {"row": 700, "name": NAME_A, "date_start": a["date_start"]}
        self.assertTrue(H.same_as_card(bare, a))
        self.assertFalse(H.same_as_card(bare, row_b()))
        self.assertFalse(H.same_as_card({"row": None, "name": NAME_A, "date_start": a["date_start"]}, a))


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
        self.assertEqual(sorted(S._HANDOVER_ACTIVATIONS[INTAKE]),
                         sorted(["bike", "name", "date_start", "row", "ts", "status", "msg_ids"]),
                         "флаг ВЫКЛ — запись ожидания прежняя (без целевого дня и тождества)")
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
        rec = S._HANDOVER_ACTIVATIONS[INTAKE]
        self.assertEqual((rec["on_day"], rec["ident"]), (day(0), hf().ident(row_a())))
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
        self.assertEqual(c[2:], [DOC_SIGNED, DEP_MONEY_7000, YES_LINE])
        self.assertEqual(b.finds, [{"bike": BIKE, "date_from": day(0), "date_to": day(5), "limit": 100}],
                         "ровно один contract_find — по байку и сроку выбранной строки")

    def test_b3b_contract_read_is_contract_ref_report_path(self):
        """v2 (e): договор читается ДОРОГОЙ `_contract_ref_report` (её вызов со строкой карточки), аргументы двери —
        ровно те, что она шлёт сама для той же строки; у `_ho_contract_read` своего contract_find нет (ast)."""
        self.on()
        b = Bridge([row_a(), row_b()])
        seen = []
        real = S._contract_ref_report

        def spy(bridge, row=None, **kw):
            seen.append((type(bridge).__name__, (row or {}).get("row"), kw))
            return real(bridge, row=row, **kw)
        S._contract_ref_report = spy
        try:
            do_handover(b)
        finally:
            S._contract_ref_report = real
        self.assertEqual(seen, [("_HoFindTap", 700, {})])
        direct = Bridge([row_a()])
        words = S._contract_ref_report(direct, row=row_a())
        self.assertTrue(words.startswith("в реестре есть подписанный договор этой брони"), words)
        self.assertEqual(b.finds, direct.finds, "аргументы двери карточки = аргументы _contract_ref_report")
        with open(S.__file__, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_ho_contract_read"]
        self.assertEqual(len(fn), 1)
        attrs = [n.attr for n in ast.walk(fn[0]) if isinstance(n, ast.Attribute)]
        names = [n.id for n in ast.walk(fn[0]) if isinstance(n, ast.Name)]
        self.assertNotIn("contract_find", attrs, "свой contract_find в обход _contract_ref_report")
        self.assertEqual(names.count("_contract_ref_report"), 1)

    def test_b4_on_missing_contract_and_deposit_named_first_yes_route_same(self):
        """Договора нет, залог не указан → исключение первой строкой (после подписи). Слова «да/нет» и маршрут
        APPROVEFIX прежние: решает человек, «да» реплаем активирует ту же строку."""
        self.on()
        b = Bridge([row_a(deposit_raw=""), row_b()], contract=fresp([]))
        do_handover(b)
        cs = cards()
        lines = cs[0].text.split("\n")
        self.assertEqual(lines[:2], ["🐀 Splinter", "⚠️ Исключение: подписанного договора нет · залог не указан"])
        self.assertIn(DEP_NONE, lines)
        self.assertEqual(lines[-1], YES_LINE)
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
        self.assertIn(DEP_PASSPORT, lines)

    def test_b5b_on_thousand_separator_deposit_in_card(self):
        """v2 (d): «7,000» в клетке S → «7 000 ฿», источник и «получение не сверено» — в карточке, исключения нет."""
        self.on()
        b = Bridge([row_a(deposit_raw="7,000")])
        do_handover(b)
        lines = cards()[0].text.split("\n")
        self.assertEqual(lines[2:], [DOC_SIGNED, DEP_MONEY_7000, YES_LINE])

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

    def test_b8_on_only_future_booking_is_hand_card_early(self):
        """v2 (b): брони на сегодня нет, есть только будущая (через 3 дн.) → ручная карточка «раньше брони»: без «да»,
        без ожидания, билета и записей; даты брони не тронуты; факты её строки (договор, залог) — в карточке."""
        self.on()
        b = Bridge([row_b()])
        do_handover(b)
        self.assertEqual(cards(), [], intake_texts())
        hs = hand_cards()
        self.assertEqual(len(hs), 1, intake_texts())
        self.assertEqual(hs[0].text.split("\n"), [
            "🐀 Splinter",
            "⚠️ ВЫДАЧА %s → %s: брони на %s нет — бронь строка 720 (%s — %s)." % (BIKE, NAME_B, dm(0), dt(3), dt(10)),
            "Выдача раньше брони на 3 дн. (бронь с %s): переоформить договор и бронь на фактические даты." % dm(3),
            "📄 Договор: подписанного и ждущего подписи в реестре нет (строк в сроке: 1) ⚠️",
            DEP_PASSPORT,
            HAND_TAIL])
        self.assertNotIn(INTAKE, S._HANDOVER_ACTIVATIONS, "ручная карточка ожидания «да» не заводит")
        say_yes(b, hs[0])
        self.assertEqual((b.activated, b.tickets), ([], 0))
        self.assertEqual(b.states, [], "точной строки нет — вкладка состояния не пишется")
        self.assertEqual(b.reads, 1, "точной строки нет — второго чтения (сверки вкладки) нет")
        self.assertEqual((b.rows[0]["date_start"], b.rows[0]["date_end"], b.rows[0]["status"]),
                         (dt(3), dt(10), "Бронь"), "даты и статус брони бот не меняет")

    def test_b8b_on_no_booking_at_all_keeps_pick_question(self):
        """Броней номера нет вовсе (только завершённая) → прежний ⚠️ с вопросом pick, ни реестра, ни записи."""
        self.on()
        b = Bridge([row_a(status="Завершена", date_start=dt(-9), date_end=dt(-2))])
        do_handover(b)
        self.assertEqual((cards(), hand_cards()), ([], []), intake_texts())
        warns = [t for t in intake_texts() if "⚠️ ВЫДАЧА" in t]
        self.assertEqual(warns, [P + "⚠️ ВЫДАЧА %s: Брони этого байка на этот день не нашёл — какая бронь выдаётся "
                                     "(дата и имя)? — активируй руками (Бронь→В аренде)." % BIKE])
        self.assertEqual((b.finds, b.states, b.reads), ([], [], 1))

    def test_b9_on_two_bookings_today_is_question(self):
        self.on()
        b = Bridge([row_a(), row_a(row=705, name="Вера Тоже", booking_id="bk-c", contacts="+66 80 111 2222")])
        do_handover(b)
        self.assertEqual(cards(), [])
        warns = [t for t in intake_texts() if "⚠️ ВЫДАЧА" in t]
        self.assertEqual(len(warns), 1, intake_texts())
        self.assertIn("Какая бронь выдаётся:", warns[0])
        self.assertEqual(b.finds, [])
        self.assertEqual(b.states, [], "две брони на день — вкладка состояния не пишется («последней» нет)")
        self.assertEqual(b.reads, 1, "сверки вкладки без точной строки нет")

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
        self.assertEqual([s["client"] for s in b.states], [NAME_A, NAME_A])

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
        читается, маршрут «да» прежний (перед билетом — сверка по строке, имени и началу срока)."""
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
        self.assertEqual(lines[3:], [YES_LINE])
        self.assertEqual(b.finds, [])
        self.assertEqual(b.states, [], "сверка той же брони не собрана — вкладку состояния не пишем")
        self.assertNotIn("ident", S._HANDOVER_ACTIVATIONS[INTAKE])
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

    # ------------------------------------------------------------------------------------- v2 (a): целевой день
    def test_b15_message_before_local_midnight_processed_after_keeps_its_day(self):
        """v2 (a): фраза выдачи в 23:50 местного вчера, разобрана сегодня (хвост после рестарта) → бронь ВЧЕРАШНЕГО
        дня (A), а не сегодняшняя бронь другого клиента (C); тот же день — у вкладки состояния и у «да»."""
        self.on()
        a_y = row_a(date_start=dt(-1, "09:00"), date_end=dt(4))
        c_t = row_c(date_start=dt(0, "11:00"), date_end=dt(6))
        b = Bridge([a_y, c_t])
        stamp = local_midnight_utc(0) - datetime.timedelta(minutes=10)
        self.assertEqual(S._ho_target_day(Msg("x", date=stamp)), day(-1))
        do_handover(b, date=stamp)
        cs = cards()
        self.assertEqual(len(cs), 1, intake_texts())
        self.assertIn("%s → %s, бронь строка 700" % (BIKE, NAME_A), cs[0].text)
        self.assertNotIn(NAME_C, cs[0].text)
        self.assertEqual([(s["client"], s["booking_id"]) for s in b.states], [(NAME_A, "bk-a")])
        self.assertEqual(S._HANDOVER_ACTIVATIONS[INTAKE]["on_day"], day(-1))
        say_yes(b, cs[0])
        self.assertEqual(b.activated, [{"bike": BIKE, "name": NAME_A, "date_start": a_y["date_start"]}])

    def test_b16_local_day_not_utc_date_of_message(self):
        """v2 (a): 06:30 местного = 23:30 UTC прошлого дня: UTC-дата сообщения (`_msg_date`) — вчера, целевой день —
        сегодня; бронь — сегодняшняя (A), не вчерашняя (C). Без зоны msg.date — UTC; без даты — сегодня."""
        self.on()
        stamp = local_midnight_utc(0) + datetime.timedelta(hours=6, minutes=30)
        self.assertEqual(str(stamp.date()), day(-1), "предпосылка: UTC-дата сообщения — вчера")
        self.assertEqual(S._ho_target_day(Msg("x", date=stamp)), day(0))
        self.assertEqual(S._ho_target_day(Msg("x", date=stamp.replace(tzinfo=None))), day(0), "без зоны — UTC")

        class NoDate(object):
            date = None
        self.assertEqual(S._ho_target_day(NoDate()), day(0))
        b = Bridge([row_c(), row_a()])
        do_handover(b, date=stamp)
        cs = cards()
        self.assertEqual(len(cs), 1, intake_texts())
        self.assertIn("бронь строка 700", cs[0].text)
        self.assertEqual([s["client"] for s in b.states], [NAME_A])

    # ----------------------------------------------------------------------------- v2 (b): день против брони
    def test_b17_late_client_hand_card_owner_rule(self):
        """v2 (b): бронь была с позавчера, клиент берёт байк сегодня → ручная карточка «позже брони на 2 дн.»: оплата
        с исходной даты, если перенос не согласован заранее; бот ±N не выбирает, ничего не активирует и не пишет."""
        self.on()
        a_late = row_a(date_start=dt(-2, "09:00"), date_end=dt(3))
        b = Bridge([a_late])
        do_handover(b)
        self.assertEqual(cards(), [], intake_texts())
        hs = hand_cards()
        self.assertEqual(len(hs), 1, intake_texts())
        self.assertEqual(hs[0].text.split("\n"), [
            "🐀 Splinter",
            "⚠️ ВЫДАЧА %s → %s: брони на %s нет — бронь строка 700 (%s — %s)." % (BIKE, NAME_A, dm(0), dt(-2, "09:00"),
                                                                               dt(3)),
            "Клиент берёт байк позже брони на 2 дн. (бронь с %s): переоформить договор и бронь. Если перенос не "
            "согласован заранее — оплата с %s (исходная дата)." % (dm(-2), dm(-2)),
            "📄 Договор: подписан · стр. 36 · doc …a1b2c3",
            DEP_MONEY_7000,
            HAND_TAIL])
        self.assertNotIn("да / нет", hs[0].text)
        self.assertEqual(b.finds, [{"bike": BIKE, "date_from": day(-2), "date_to": day(3), "limit": 100}])
        say_yes(b, hs[0])
        run(S._handle_intake(Msg("да", chat_id=INTAKE, uname=APPROVER), Ctx(), b, None))
        self.assertEqual((b.activated, b.tickets, b.states, b.reads), ([], 0, [], 1))
        self.assertEqual((b.rows[0]["date_start"], b.rows[0]["status"]), (dt(-2, "09:00"), "Бронь"))
        do_handover(b)
        self.assertEqual((len(hand_cards()), len(b.finds)), (1, 1), "повтор фразы — кулдаун, реестр не перечитан")

    def test_b18_several_bookings_other_days_addressed_question(self):
        """v2 (b): броней номера на другие дни две (вчера C, через 3 дн. B) → адресный вопрос с обеими, «последней»
        нет; ни карточки, ни реестра, ни записей."""
        self.on()
        b = Bridge([row_c(), row_b()])
        do_handover(b)
        self.assertEqual(cards(), [], intake_texts())
        self.assertEqual(intake_texts(), [
            P + "⚠️ ВЫДАЧА %s: брони на %s нет, а броней этого байка несколько: строка 690 с %s (%s), строка 720 с %s "
                "(%s) — какая выдаётся? Сам не выбираю, не активирую и даты не меняю: договор и бронь переоформить "
                "руками." % (BIKE, dm(0), dm(-1), NAME_C, dm(3), NAME_B)])
        self.assertEqual((b.finds, b.states, b.activated, b.reads), ([], [], [], 1))
        self.assertNotIn(INTAKE, S._HANDOVER_ACTIVATIONS)

    # ------------------------------------------------------------- v2 (c)/(6): та же бронь перед записью и «да»
    def test_b19_state_recheck_changed_row_no_state_set_honest_line(self):
        """v2 (c): между карточкой и записью вкладки бронь в CRM изменилась (booking_id) → state_set нет, честная
        строка; «да» перед билетом перечитывает и тоже не пишет."""
        self.on()

        def edit(rows):
            rows[0]["booking_id"] = "bk-a-new"
        b = Bridge([row_a(), row_b()], after_read={1: edit})
        do_handover(b)
        cs = cards()
        self.assertEqual(len(cs), 1, intake_texts())
        self.assertEqual(b.states, [])
        self.assertIn(P + "⚠️ ВЫДАЧА %s: перед записью вкладки состояния бронь строка 700 перечитана иначе (другая "
                          "строка, срок или клиент) — вкладку состояния не трогал; сверь карточку с CRM." % BIKE,
                      intake_texts())
        say_yes(b, cs[0])
        self.assertEqual((b.activated, b.tickets), ([], 0))

    def test_b20_state_recheck_unread_no_state_set(self):
        self.on()
        b = Bridge([row_a(), row_b()], fail_reads={2})
        do_handover(b)
        self.assertEqual(len(cards()), 1, intake_texts())
        self.assertEqual(b.states, [])
        self.assertTrue(any("перечитана иначе (CRM не перечитан)" in t for t in intake_texts()), intake_texts())

    def test_b21_crm_unread_is_unknown_not_no_booking(self):
        """v2: дверь clients не прочитана → «CRM не прочитан — бронь неизвестна, а не «брони нет»», а не «брони в CRM
        не нашёл»; ни карточки, ни реестра, ни записи."""
        self.on()
        b = Bridge([row_a()], fail_reads={1})
        do_handover(b)
        self.assertEqual(intake_texts(), [P + "⚠️ ВЫДАЧА %s: CRM не прочитан (read_failed) — бронь неизвестна, а не "
                                              "«брони нет»; активируй руками (Бронь→В аренде)." % BIKE])
        self.assertEqual((b.finds, b.states), ([], []))

    def test_b22_yes_after_crm_edit_refused_no_ticket(self):
        """v2 (6): после карточки срок брони в CRM поменяли → «да» реплаем: ни билета, ни activate_booking, карточка
        снята; второй «да» — «исход уже есть»."""
        self.on()
        b = Bridge([row_a(), row_b()])
        do_handover(b)
        cs = cards()
        self.assertEqual(len(b.states), 1)
        b.rows[0]["date_end"] = dt(7)
        say_yes(b, cs[0])
        self.assertEqual((b.activated, b.tickets), ([], 0))
        self.assertIn(P + "⚠️ Бронь карточки выдачи %s, строка 700 перечитана иначе (другая строка, срок или клиент) — "
                          "не активирую, в CRM ничего не записал. Повтори выдачу — придёт новая карточка." % BIKE,
                      intake_texts())
        self.assertEqual(S._HANDOVER_ACTIVATIONS[INTAKE]["status"], "stale")
        say_yes(b, cs[0])
        self.assertEqual((b.activated, b.tickets), ([], 0))

    def test_b23_record_from_before_flag_revalidated(self):
        """v2 (6): запись ожидания, заведённая при ВЫКЛ (cand[-1] = будущая бронь B), после включения флага перед «да»
        сверяется точным днём: не та бронь — не пишем. Та же запись без тождества (как после рестарта), но верная
        строка — пишем."""
        b = Bridge([row_a(), row_b()])
        do_handover(b)                                   # ВЫКЛ: карточка B (строка 720)
        cs = cards()
        self.assertIn("бронь строка 720", cs[0].text)
        self.on()
        say_yes(b, cs[0])
        self.assertEqual((b.activated, b.tickets), ([], 0), "запись до флага исполнила чужую бронь")
        self.assertTrue(any("строка 720 перечитана иначе" in t for t in intake_texts()), intake_texts())
        reset()
        self.on()
        b2 = Bridge([row_a(), row_b()])
        sent = run(rec_send(None, chat_id=INTAKE, text="карточка до рестарта"))
        a = row_a()
        S._HANDOVER_ACTIVATIONS[INTAKE] = {"bike": BIKE, "name": NAME_A, "date_start": a["date_start"], "row": 700,
                                           "ts": time.time(), "status": "awaiting", "msg_ids": [sent.message_id]}
        say_yes(b2, sent)
        self.assertEqual(b2.activated, [{"bike": BIKE, "name": NAME_A, "date_start": a["date_start"]}])

    def test_b24_bridge_activated_other_row_said_loudly(self):
        """v2 (6): мост перевёл строку 999, а карточка была о строке 700 → громко, без «✅ В аренде»."""
        self.on()
        b = Bridge([row_a(), row_b()], act_row=999)
        do_handover(b)
        say_yes(b, cards()[0])
        self.assertEqual(len(b.activated), 1)
        tail = intake_texts()[-1]
        self.assertEqual(tail, P + "⚠️ В аренде переведена строка 999, а на карточке была строка 700 — проверь CRM "
                                   "руками (повтор не делаю).")
        self.assertFalse(any("✅ В аренде" in t for t in intake_texts()))

    def test_b25_legacy_route_same_recheck(self):
        """Ручка INTAKE_CONFIRM_STRICT=0 (прежние ветки «да»): та же сверка брони перед билетом и та же сверка строки."""
        self.on()
        os.environ["INTAKE_CONFIRM_STRICT"] = "0"
        b = Bridge([row_a(), row_b()])
        do_handover(b)
        b.rows[0]["name"] = "Анна Переписана"
        run(S._handle_intake(Msg("да", chat_id=INTAKE, uname=APPROVER), Ctx(), b, None))
        self.assertEqual((b.activated, b.tickets), ([], 0))
        self.assertTrue(any("перечитана иначе" in t for t in intake_texts()), intake_texts())
        reset()
        self.on()
        os.environ["INTAKE_CONFIRM_STRICT"] = "0"
        b2 = Bridge([row_a(), row_b()], act_row=999)
        do_handover(b2)
        run(S._handle_intake(Msg("да", chat_id=INTAKE, uname=APPROVER), Ctx(), b2, None))
        self.assertEqual(len(b2.activated), 1)
        self.assertEqual(intake_texts()[-1], P + "⚠️ В аренде переведена строка 999, а на карточке была строка 700 — "
                                                 "проверь CRM руками (повтор не делаю).")

    def test_b26_rc_pick_on_day_and_default(self):
        """v2 (a): `_rc_pick(…, on_day)` — день запроса pick и ветки already_active; без on_day — прежний день t0."""
        self.on()
        b = Bridge([row_c(), row_a()])
        self.assertEqual(S._rc_pick(b, BIKE, "handover", on_day=day(-1))["row"]["row"], 690)
        self.assertEqual(S._rc_pick(b, BIKE, "handover", on_day=day(0))["row"]["row"], 700)
        self.assertEqual(S._rc_pick(b, BIKE, "handover")["row"]["row"], 700, "без on_day — день чтения")
        act = Bridge([row_c(status="В аренде"), row_a()])
        pk = S._rc_pick(act, BIKE, "handover", on_day=day(-1))
        self.assertEqual((pk["code"], pk["row"]["row"], pk.get("already_active")), ("found", 690, True),
                         "already_active — по целевому дню, а не по дню t0")
        self.assertEqual(S._rc_pick(act, BIKE, "handover", on_day=day(-3))["code"], "unknown")


# ================================================================================== (C) флаг ВЫКЛ — отдельный процесс
class C_OffProcess(unittest.TestCase):
    def test_c1_off_process_has_no_new_modules(self):
        """Флаг ВЫКЛ: модулей ветки флага в процессе нет; карточки и вкладка состояния — прежние байт-в-байт и там, где
        флаг ВКЛ дал бы ручную карточку (поздний клиент), и при фразе до местной полуночи (прежний cand[-1])."""
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
        a_late = row_a(date_start=dt(-2, "09:00"), date_end=dt(3))
        self.assertEqual(got["late_card"], [old_card(a_late)], got)
        self.assertEqual(got["late_states"], [[NAME_A, a_late["date_end"], "bk-a"]], got)
        self.assertEqual(got["night_card"], [old_card(row_c(date_start=dt(0, "11:00"), date_end=dt(6)))], got)
        self.assertEqual(got["night_rec_keys"], sorted(["bike", "name", "date_start", "row", "ts", "status",
                                                        "msg_ids"]), got)


def _child_off():
    """Флаг ВЫКЛ, свой процесс: выдача + «да» — какие модули ветки флага оказались в процессе; поздний клиент и фраза
    до местной полуночи — прежние карточки (cand[-1]) и вкладка состояния (max(date_start))."""
    reset()
    b = Bridge([row_a(), row_b()])
    do_handover(b)
    cs = cards()
    if cs:
        say_yes(b, cs[0])
    out = {"finds": len(b.finds), "card": [c.text for c in cs], "activated": len(b.activated)}
    reset()
    late = Bridge([row_a(date_start=dt(-2, "09:00"), date_end=dt(3))])
    do_handover(late)
    out["late_card"] = [c.text for c in cards()]
    out["late_states"] = [[s["client"], s["date_due"], s["booking_id"]] for s in late.states]
    out["finds"] += len(late.finds)
    reset()
    night = Bridge([row_a(date_start=dt(-1, "09:00"), date_end=dt(4)), row_c(date_start=dt(0, "11:00"),
                                                                             date_end=dt(6))])
    do_handover(night, date=local_midnight_utc(0) - datetime.timedelta(minutes=10))
    out["night_card"] = [c.text for c in cards()]
    out["night_rec_keys"] = sorted(S._HANDOVER_ACTIVATIONS.get(INTAKE) or {})
    out["finds"] += len(night.finds)
    out["mods"] = sorted(m for m in NEW_MODS if m in sys.modules)
    print(CHILD_MARK + json.dumps(out))   # ASCII: кодировка консоли любая
    sys.stdout.flush()


if __name__ == "__main__":
    if sys.argv[1:] == ["--child-off"]:
        _child_off()
        sys.exit(0)
    unittest.main(verbosity=2)
