# -*- coding: utf-8 -*-
"""INTAKECONFIRM1610 — независимая приёмка выпуска «согласие на бронь + неизвестный исход записи».

Источник требований — ТОЛЬКО проект `DESIGN_INTAKECONFIRM1610.md` (разделы 2.2–2.5, 3, 4); код исправителя автор
приёмки не видел. Всё гоняется через НАСТОЯЩИЙ обработчик `splinter._handle_intake` (не через функцию разбора):
фейковый мост считает вызовы `create_booking`, `_send` пишет в список, проверяются ЧИСЛО вызовов записи, итоговый
статус карточки и ДОСЛОВНЫЙ текст ответа бота.

Дефекты, которые приёмка обязана поймать на нетронутом коде (cbe1322):
  Д1 — согласие ищется ПОДСТРОКОЙ и раньше отказа: «не ставь», «не подтверждаю», «нет, когда оплатит», «погода»,
       «около» ЗАПИСЫВАЮТ бронь в CRM («не надо» — нет: подстроки «да» в нём нет, на базе это молчание);
  Д2 — таймаут/обрыв/незнакомый отказ записи называется «❌ Не записалось», хотя строка могла лечь.

Разделы:
  A — первая таблица раздела 3 (P1–P7, N1–N20); у каждого отрицательного случая — близнец (тот же стенд, другой
      ввод, запись ПРОХОДИТ: 1 вызов, booked), он идёт ПЕРВЫМ — стенд доказанно умеет писать;
  B — вторая таблица раздела 3 (W1–W12): исход записи, повторное «да», фото паспорта, новая карточка;
  C — сквозные свойства (а)–(в): ловушки не пишут никогда, согласие-только пишет ровно раз, текста сообщения в журнале нет;
  D — ручка отката INTAKE_CONFIRM_STRICT: не задана/1 = строгий режим; 0/off/no/нет = прежнее поведение
      БАЙТ-В-БАЙТ (голдены сняты с кода cbe1322 и на нём же зелёные; дефекты Д1/Д2 при ручке 0 записаны как
      прежнее поведение и помечены);
  E — структура: прежний блок ветки 3 текстуально цел (sha256 49 строк cbe1322), модуль intake_confirm чист (ast).

Заметка о N19 («нет правок»): таблица проекта говорит SILENT, а нормативный шаг 3а с EDIT_STEMS=("правк",…)
слово «правок» (беглая «о») НЕ узнаёт, буквальная реализация даст NO → rejected. Поэтому N19 разделён: безопасность
(0 вызовов записи) и соответствие таблице — отдельными тестами.

Данные только синтетические (Мария Тест, CB 300CC R 9011). Сети, мозга, CRM, файлов тест не касается; дерево
берётся от __file__, чужие корни из sys.path убираются.
"""
import ast
import asyncio
import copy
import datetime
import hashlib
import itertools
import json
import logging
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _n(p):
    return os.path.normcase(os.path.abspath(p or os.curdir))


for _foreign in ("/root/turbobaby-manager-bot", "D:/turbobaby-bot"):
    if _n(_foreign) != _n(ROOT):
        sys.path[:] = [p for p in sys.path if _n(p) != _n(_foreign)]
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
for _k in ("RENTAL_CASE_APPROVALS", "RENTAL_CASE", "INTAKE_CONFIRM_STRICT"):
    os.environ.pop(_k, None)

import splinter as S  # noqa: E402

if _n(os.path.dirname(os.path.abspath(S.__file__))) != _n(ROOT):
    raise SystemExit("splinter импортирован не из своего дерева: %s (ждал %s)" % (S.__file__, ROOT))

# ------------------------------------------------------------------------------------------------ константы
INTAKE = S.INTAKE_CHAT
BIKE = "CB 300CC R 9011"
APPROVER = "deramor"
NOT_APPROVER = "pym_thai"
BOT_UNAME = "turbobaby_manager_bot"
KNOB = "INTAKE_CONFIRM_STRICT"

PFX = "\U0001F400 Splinter\n"
T_BOOKED = PFX + "\u2705 Бронь записана, строка 33, статус \u00abБронь\u00bb."
T_DUP = PFX + "\u26a0\ufe0f Уже есть такая бронь (строка 12)."
T_ASK = PFX + ("\u2753 Ответ неоднозначный \u2014 бронь не ставлю. Поставить: \u00abда\u00bb. "
               "Отказ: \u00abнет\u00bb. Исправить: \u00abправки\u00bb.")
T_EDIT = PFX + "\u270f\ufe0f Принял, жду исправленную карточку."
T_REJECT = PFX + "\u274c Бронь отклонена \u2014 в CRM ничего не записано."
T_PHOTO_UNKNOWN = PFX + ("\U0001F4CE Паспорт привязан. Исход записи брони неизвестен \u2014 проверь CRM; "
                         "повтор не делаю.")


def t_unknown(err):
    return PFX + ("\u26a0\ufe0f Исход записи брони неизвестен (%s) \u2014 проверь CRM; повтор не делаю. "
                  "Брони там нет \u2014 пришли карточку заново." % err)


def t_not_written(err, message=""):
    return PFX + ("\u274c Не записано: %s.%s\nВ CRM ничего не легло \u2014 исправь и пришли карточку заново."
                  % (err, (" " + message) if message else ""))


# прежние тексты (ручка 0 = код cbe1322)
L_REJECT = PFX + "\u274c Бронь отклонена."


def l_fail(err, message):
    return PFX + "\u274c Не записалось: %s. %s" % (err, message)


SUMMARY_MARK = "Карточка принята."
SUMMARY_TAIL = "Ставлю бронь? да / нет / правки"

OK_RESP = {"ok": True, "row": 33, "booking_id": "b-1", "bike": BIKE}
EXPECTED_FIELDS = {"bike": BIKE, "name": "Мария Тест", "date_start": "20-10-2026", "date_end": "27-10-2026",
                   "deposit": "passport", "helmets": 2, "contacts": "@maria_test_only",
                   "note": "опыт: есть | доставка: Раваи (тест) | срок: 7 дней"}
NAMES_BOOK = ["issue_write_ticket", "create_booking"]
PARSED_CARD = {"model": BIKE, "client": "Мария Тест", "contacts": "@maria_test_only",
               "date_start": "20-10-2026", "date_end": "27-10-2026", "date_start_iso": None,
               "date_end_iso": None, "deposit_type": "паспорт", "helmets": 2, "experience": "есть",
               "delivery_name": "Раваи (тест)", "delivery_url": "https://maps.google.com/?q=test",
               "term": "7 дней"}
PP_FIELDS = {"full_name": "TEST MARIA", "country": "TST", "expire_date": "2030-01-01"}

R_TIMEOUT = {"ok": False, "error": "timeout", "message": "Timeout >60s"}
R_REQFAIL = {"ok": False, "error": "request_failed", "message": "HTTP 502"}
R_DEADLINE = {"ok": False, "error": "card_deadline", "message": "бюджет карточки исчерпан"}
NOT_WRITTEN_ERRORS = ["bad_json", "no_ticket", "unknown_action", "missing_bike", "missing_name",
                      "bike_not_resolved", "bad_dates", "sheet_not_found", "booking_conflict"]
W6_UNKNOWN = [
    ("receipt_unknown", {"ok": False, "error": "receipt_unknown", "outcome": "unknown",
                         "message": "расписка не доехала"}, "receipt_unknown"),
    ("write_failed", {"ok": False, "error": "write_failed", "message": "запись прервалась"}, "write_failed"),
    ("internal_error", {"ok": False, "error": "internal_error", "message": "сбой моста"}, "internal_error"),
    ("json_parse_error", {"ok": False, "error": "json_parse_error", "message": "не разобран"}, "json_parse_error"),
    ("weird_code", {"ok": False, "error": "weird_code", "message": "что-то новое"}, "weird_code"),
    ("пустой код", {"ok": False, "error": "", "message": ""}, "?"),
    ("кода нет вовсе", {"ok": False}, "?"),
    ("unauthorized", {"ok": False, "error": "unauthorized", "message": "токен"}, "unauthorized"),
    ("outcome=unknown сильнее определённого кода", {"ok": False, "error": "no_ticket", "outcome": "unknown"},
     "no_ticket"),
]

# ------------------------------------------------------------------------------------------------ стенд
SENDS = []            # (chat_id, text, kwargs)
LOGS = []             # (levelno, message)
FINALIZE_CALLS = []   # статус черновика на входе в _intake_finalize
OCR_CALLS = []
SAVE_CALLS = []
_MID = itertools.count(5000)
_DEF = object()


class _Cap(logging.Handler):
    def emit(self, record):
        try:
            LOGS.append((record.levelno, record.getMessage()))
        except Exception:  # noqa: BLE001
            LOGS.append((record.levelno, str(record.msg)))


_root = logging.getLogger()
_root.addHandler(_Cap(level=logging.DEBUG))
_root.setLevel(logging.DEBUG)
S.log.setLevel(logging.DEBUG)


class U:
    def __init__(self, username, is_bot=False):
        self.username = username
        self.is_bot = is_bot
        self.id = 1000 + len(username or "")
        self.first_name = username


class _Reply:
    def __init__(self):
        self.from_user = U(BOT_UNAME, is_bot=True)
        self.text = PFX + SUMMARY_MARK
        self.message_id = 4999


class Msg:
    def __init__(self, text=None, uname=APPROVER, photo=False, reply_to_bot=False, sticker=False):
        self.text = text
        self.caption = None
        self.photo = [object()] if photo else None
        self.sticker = object() if sticker else None
        self.media_group_id = None
        self.chat_id = INTAKE
        self.message_thread_id = None
        self.date = datetime.datetime.now(datetime.timezone.utc)
        self.message_id = next(_MID)
        self.from_user = U(uname)
        self.reply_to_message = _Reply() if reply_to_bot else None


class Ctx:
    class B:
        username = BOT_UNAME
        id = 999
    bot = B()


class FakeClaude:
    def quick(self, system, text, max_tokens=300, **kw):
        return json.dumps(PARSED_CARD, ensure_ascii=False)

    def vision(self, *a, **k):
        return "{}"


class FakeBridge:
    """Мост со счётчиком. Любой иной метод моста — AttributeError (новых чтений/записей выпуск не заводит)."""

    def __init__(self, resp=_DEF, book_exc=None, ticket_exc=None):
        self.calls = []
        self.resp = dict(OK_RESP) if resp is _DEF else resp
        self.book_exc = book_exc
        self.ticket_exc = ticket_exc

    def issue_write_ticket(self):
        self.calls.append(("issue_write_ticket", {}))
        if self.ticket_exc is not None:
            raise self.ticket_exc
        return {"ok": True, "ticket": "t-test-1610"}

    def create_booking(self, **kw):
        self.calls.append(("create_booking", dict(kw)))
        if self.book_exc is not None:
            raise self.book_exc
        return copy.deepcopy(self.resp)

    def names(self):
        return [n for n, _ in self.calls]

    def books(self):
        return sum(1 for n, _ in self.calls if n == "create_booking")

    def booking_kwargs(self):
        return [k for n, k in self.calls if n == "create_booking"]


async def rec_send(context, *, chat_id, text, message_thread_id=None, bilingual=True, **k):
    SENDS.append((chat_id, text, {"bilingual": bilingual, "message_thread_id": message_thread_id}))


async def fake_ocr(photo_msg, chat_id, context, bridge):
    OCR_CALLS.append(chat_id)
    S._INTAKE_PASSPORT[chat_id] = {"file_id": "f-test", "fields": dict(PP_FIELDS), "ocr_status": "ok",
                                   "ts": S._time.time()}
    return (True, dict(PP_FIELDS))


def fake_save(chat_id, draft, bridge):
    SAVE_CALLS.append(chat_id)


_ORIG_FINALIZE = S._intake_finalize


async def spy_finalize(draft, msg, context, bridge):
    FINALIZE_CALLS.append(draft.get("status"))
    return await _ORIG_FINALIZE(draft, msg, context, bridge)


S._send = rec_send
S._intake_passport_ocr = fake_ocr
S._intake_passport_save = fake_save
S._intake_finalize = spy_finalize


def reset():
    SENDS.clear()
    LOGS.clear()
    FINALIZE_CALLS.clear()
    OCR_CALLS.clear()
    SAVE_CALLS.clear()
    S._INTAKE_DRAFTS.clear()
    S._INTAKE_PASSPORT.clear()
    S._HANDOVER_ACTIVATIONS.clear()
    S._RETURN_CLOSES.clear()
    S._RECENT_BOOKINGS.clear()


def make_draft(status="awaiting_approval"):
    d = dict(PARSED_CARD)
    d.update(status=status, ts=S._time.time(), passport_photo=True)
    return d


def status_now():
    d = S._INTAKE_DRAFTS.get(INTAKE)
    return d.get("status") if d else None


def intake_texts():
    return [t for c, t, _ in SENDS if c == INTAKE]


def intake_kws():
    return [k for c, _, k in SENDS if c == INTAKE]


# ------------------------------------------------------------------------------------------------ таблица раздела 3
# (метка, ввод, параметры сообщения, строгий исход, прежний исход при ручке 0 = cbe1322)
S3 = [
    ("P1", "да", {}, "book", "book"),
    ("P2", "Да.", {}, "book", "book"),
    ("P3", "ок", {}, "book", "book"),
    ("P4", "ok", {}, "book", "silent"),
    ("P4", "OK", {}, "book", "silent"),
    ("P5", "ставь", {}, "book", "book"),
    ("P6", "подтверждаю", {}, "book", "book"),
    ("P7", "да \U0001F44D", {}, "book", "book"),
    ("P7", "ДА!!!", {}, "book", "book"),
    ("P7", "да, ставь", {}, "book", "book"),
    ("N1", "\U0001F44D", {}, "ask", "silent"),
    ("N1", "\u2705", {}, "ask", "silent"),
    ("N1", "\U0001F44D\U0001F3FB", {}, "ask", "silent"),
    ("N2", "не ставь", {}, "reject", "book"),             # ДЕФЕКТ Д1 при ручке 0
    # «не надо» подстроки «да» НЕ содержит (н-а-д-о); на cbe1322 — молчание без записи (замер прогоном 16.10),
    # утверждение проекта п.1 «на**да**» неверно; строгий режим отвечает отказом.
    ("N3", "не надо", {}, "reject", "silent"),
    ("N4", "нет", {}, "reject", "reject"),
    ("N5", "отмена", {}, "reject", "reject"),
    ("N6", "не подтверждаю", {}, "reject", "book"),       # ДЕФЕКТ Д1 при ручке 0
    ("N7", "нет, когда оплатит", {}, "reject", "book"),   # ДЕФЕКТ Д1 при ручке 0
    ("N8", "всегда так", {}, "silent", "book"),           # ДЕФЕКТ Д1 при ручке 0
    ("N9", "погода", {}, "silent", "book"),               # ДЕФЕКТ Д1 при ручке 0
    ("N10", "около того", {}, "silent", "book"),          # ДЕФЕКТ Д1 при ручке 0
    ("N11", "да, но поправь дату", {}, "edit", "book"),   # ДЕФЕКТ Д1 при ручке 0
    ("N12", "ок, исправь имя", {}, "edit", "book"),       # ДЕФЕКТ Д1 при ручке 0
    ("N13", None, {"sticker": True}, "silent", "silent"),
    ("N13", None, {}, "silent", "silent"),
    ("N14", "\U0001F602", {}, "silent", "silent"),
    ("N15", "да", {"uname": NOT_APPROVER}, "silent", "silent"),
    ("N16", "да?", {}, "ask", "book"),                    # ДЕФЕКТ Д1 при ручке 0
    ("N16", "ставим?", {}, "ask", "silent"),
    ("N17", "да, я позвоню клиенту", {}, "ask", "book"),  # ДЕФЕКТ Д1 при ручке 0
    ("N17", "да нет", {}, "ask", "book"),                 # ДЕФЕКТ Д1 при ручке 0
    ("N18", "погода", {"reply_to_bot": True}, "ask", "book"),
    ("N19", "нет правок", {}, "silent", "book"),          # ДЕФЕКТ Д1 при ручке 0 («ок» в «правок»)
    ("N20", "нет, исправь дату", {}, "edit", "book"),     # ДЕФЕКТ Д1 при ручке 0 («да» в «дату»)
]

KIND = {
    "book": dict(books=1, status="booked", sends=[T_BOOKED], names=NAMES_BOOK),
    "ask": dict(books=0, status="awaiting_approval", sends=[T_ASK], names=[]),
    "reject": dict(books=0, status="rejected", sends=[T_REJECT], names=[]),
    "silent": dict(books=0, status="awaiting_approval", sends=[], names=[]),
    "edit": dict(books=0, status="awaiting_approval", sends=[T_EDIT], names=[]),
}
LEGACY_KIND = dict(KIND)
LEGACY_KIND["reject"] = dict(books=0, status="rejected", sends=[L_REJECT], names=[])

# Ловушки свойства (б): у каждой нарушено хотя бы одно условие YES (есть слово вне CONSENT_WORDS, «?», нет слов,
# отказ, правка). Через обработчик: ни одна не зовёт create_booking (свойство (а)).
TRAPS = [
    "когда", "куда", "надо", "всегда", "погода", "около", "срок", "блок", "оставь", "давайте?",
    "подставь", "отставь", "не ставь", "не надо", "не подтверждаю", "не ок", "нет", "отмена", "отклоняю", "стоп",
    "да?", "ок?", "да нет", "нет да", "да, но позже", "ставь завтра", "ок но проверь", "подтверждаю?", "ага",
    "бронируй", "подтвердил", "угу", "\U0001F642", "\U0001F44D", "\u2705", "\U0001F44C", "окно", "дача",
    "ставка", "удача", "доставь", "вставь", "подтверди", "дай", "ok?", "no", "cancel", "yes no", "отправка",
    "не исправляй", "да / нет / правки", "давай не сейчас", "поставь на 15-е", "д\u0061", "\U0001F602", "",
    "да, я позвоню клиенту", "всегда так", "нет, когда оплатит", "около того",
]
# Только слова согласия (+ знаки и эмодзи) — ровно одна запись.
CONSENT_ONLY = [
    "да", "Да.", "ок", "ok", "OK", "Ok!", "окей", "okay", "yes", "Yes!", "давай", "конечно", "ставь", "поставь",
    "ставим", "поставим", "ставлю", "поставлю", "подтверждаю", "подтверждаем", "да \U0001F44D", "ДА!!!",
    "да, ставь", "да да", "ок \U0001F44C", "конечно, ставим", "Подтверждаем.", "да-да", "ок \u2705",
]

LEGACY_BLOCK_SHA256 = "e4818d4c227e301c8fa987d6abde745e968b88f55b3fba31b80b823b8a65fa4e"  # cbe1322 splinter.py:12561-12609
LEGACY_BLOCK_N = 49
LEGACY_BLOCK_FIRST = "        low = text.lower()"
LEGACY_GUARD = '    if d and d.get("status") == "awaiting_approval" and _intake_can_approve(msg):'


# ------------------------------------------------------------------------------------------------ база тестов
class Base(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        for k in (KNOB, "RENTAL_CASE_APPROVALS", "RENTAL_CASE"):
            os.environ.pop(k, None)
        reset()

    def tearDown(self):
        os.environ.pop(KNOB, None)
        reset()

    def stand(self, status="awaiting_approval", **bkw):
        reset()
        S._INTAKE_DRAFTS[INTAKE] = make_draft(status)
        return FakeBridge(**bkw)

    def say(self, b, text=None, **mkw):
        m = Msg(text, **mkw)
        try:
            asyncio.run(S._handle_intake(m, Ctx(), b, FakeClaude()))
        except Exception as e:  # noqa: BLE001
            return e
        return None

    def expect(self, b, exc, *, books, status, sends, names=None, ctx=""):
        self.assertIsNone(exc, "%s: обработчик бросил %r" % (ctx, exc))
        self.assertEqual(b.books(), books, "%s: число вызовов create_booking" % ctx)
        if names is not None:
            self.assertEqual(b.names(), names, "%s: вызовы моста" % ctx)
        if books:
            self.assertEqual(b.booking_kwargs()[-1], EXPECTED_FIELDS, "%s: поля записи брони" % ctx)
        self.assertEqual(status_now(), status, "%s: статус карточки" % ctx)
        self.assertEqual(intake_texts(), sends, "%s: ответ бота" % ctx)
        bad = [k for k in intake_kws() if k.get("bilingual") is not False]
        self.assertEqual(bad, [], "%s: отправка обязана быть bilingual=False" % ctx)

    def expect_kind(self, b, exc, kind, ctx, table=KIND):
        e = table[kind]
        self.expect(b, exc, books=e["books"], status=e["status"], sends=e["sends"], names=e["names"],
                    ctx="%s [%s]" % (ctx, kind))

    def twin_book(self, ctx, text="да", **mkw):
        b = self.stand()
        exc = self.say(b, text, **mkw)
        self.expect_kind(b, exc, "book", "%s — близнец %r (запись проходит)" % (ctx, text))

    def rows(self, label):
        r = [x for x in S3 if x[0] == label]
        self.assertTrue(r, "нет строк таблицы %s" % label)
        return r

    def run_rows(self, label, legacy=False):
        for _, text, mkw, strict_kind, legacy_kind in self.rows(label):
            kind = legacy_kind if legacy else strict_kind
            with self.subTest(case=label, inp=text, msg=str(mkw)):
                b = self.stand()
                exc = self.say(b, text, **mkw)
                self.expect_kind(b, exc, kind, "%s %r" % (label, text), LEGACY_KIND if legacy else KIND)

    def neg(self, label, twin="да", **twin_kw):
        self.twin_book(label, twin, **twin_kw)
        self.run_rows(label)


# ================================================================================================ A: раздел 3, ответы
class A_Replies(Base):
    """Первая таблица раздела 3: P1–P7 (согласие явное), N1–N20 (отказ/сомнение — записи нет)."""

    def test_P01_da(self):
        b = self.stand()
        exc = self.say(b, "да")
        self.expect_kind(b, exc, "book", "P1 'да'")
        rb = S._RECENT_BOOKINGS.get("9011") or {}
        self.assertEqual((rb.get("booking_id"), rb.get("row")), ("b-1", 33),
                         "P1: прежний блок BOOKED целиком — _RECENT_BOOKINGS по номеру байка")

    def test_P02_Da_dot(self):
        self.run_rows("P2")

    def test_P03_ok_ru(self):
        self.run_rows("P3")

    def test_P04_ok_latin(self):
        self.run_rows("P4")

    def test_P05_stav(self):
        self.run_rows("P5")

    def test_P06_podtverzhdayu(self):
        self.run_rows("P6")

    def test_P07_da_with_marks(self):
        self.run_rows("P7")

    def test_N01_consent_emoji_only_asks(self):
        self.neg("N1", "да \U0001F44D")

    def test_N02_ne_stav(self):
        self.neg("N2", "ставь")

    def test_N03_ne_nado(self):
        self.neg("N3", "да")

    def test_N04_net(self):
        self.neg("N4", "да")

    def test_N05_otmena(self):
        self.neg("N5", "ок")

    def test_N06_ne_podtverzhdayu(self):
        self.neg("N6", "подтверждаю")

    def test_N07_net_kogda_oplatit(self):
        self.neg("N7", "да")

    def test_N08_vsegda_tak(self):
        self.neg("N8", "да")

    def test_N09_pogoda(self):
        self.neg("N9", "да")

    def test_N10_okolo_togo(self):
        self.neg("N10", "ок")

    def test_N11_da_no_popravd(self):
        self.neg("N11", "да")

    def test_N12_ok_ispravd(self):
        self.neg("N12", "ок")

    def test_N13_empty_sticker(self):
        self.neg("N13", "да")

    def test_N14_other_emoji(self):
        self.neg("N14", "да")

    def test_N15_not_approver(self):
        self.neg("N15", "да", uname=APPROVER)

    def test_N16_question(self):
        self.neg("N16", "да")

    def test_N17_consent_plus_words(self):
        self.neg("N17", "да")

    def test_N18_silent_reply_to_bot_asks(self):
        self.neg("N18", "да", reply_to_bot=True)

    def test_N18b_silent_tag_bot_asks(self):
        self.twin_book("N18b", "да")
        b = self.stand()
        exc = self.say(b, "погода @" + BOT_UNAME)
        self.expect_kind(b, exc, "ask", "N18b тег бота")

    def test_N18c_addressed_check_exception_is_not_addressed(self):
        self.twin_book("N18c", "да", reply_to_bot=True)
        orig = S._addressed_bot

        def boom(msg, context):
            raise RuntimeError("проверка адресата упала")
        S._addressed_bot = boom
        try:
            b = self.stand()
            exc = self.say(b, "погода", reply_to_bot=True)
        finally:
            S._addressed_bot = orig
        self.expect_kind(b, exc, "silent", "N18c исключение в _addressed_bot = не адресовано")

    def test_N19_net_pravok_no_write(self):
        """Безопасность N19: «нет правок» не пишет бронь (при любом прочтении — SILENT по таблице или NO по шагу 3а)."""
        self.twin_book("N19", "да")
        b = self.stand()
        exc = self.say(b, "нет правок")
        self.assertIsNone(exc, "N19: обработчик бросил %r" % (exc,))
        self.assertEqual(b.books(), 0, "N19: «нет правок» не должно звать create_booking")
        self.assertEqual(b.names(), [], "N19: вызовы моста")

    def test_N19_net_pravok_table(self):
        """N19 по таблице проекта: SILENT, awaiting_approval, без ответа (см. заметку в шапке о шаге 3а)."""
        self.run_rows("N19")

    def test_N20_net_ispravd_datu(self):
        self.neg("N20", "да")

    def test_EDIT_kept(self):
        """Поведение «правки/исправ» сохраняется: тот же текст, записи нет, карточка ждёт."""
        self.twin_book("EDIT", "да")
        for text in ("правки", "исправь модель"):
            with self.subTest(inp=text):
                b = self.stand()
                exc = self.say(b, text)
                self.expect_kind(b, exc, "edit", "EDIT %r" % text)


# ================================================================================================ B: исход записи
class B_WriteOutcome(Base):
    """Вторая таблица раздела 3: ввод «да», мост отвечает по-разному. Повторное «да» не пишет и не напоминает."""

    def wcase(self, label, *, status, text, books, names=None, **bkw):
        self.twin_book("%s (близнец W1)" % label, "да")
        b = self.stand(**bkw)
        exc = self.say(b, "да")
        self.expect(b, exc, books=books, status=status, sends=[text], names=names, ctx=label)
        before = list(intake_texts())
        exc = self.say(b, "да")
        self.assertIsNone(exc, "%s: повторное «да» — обработчик бросил %r" % (label, exc))
        self.assertEqual(b.books(), books, "%s: повторное «да» не зовёт create_booking" % label)
        self.assertEqual(status_now(), status, "%s: повторное «да» не меняет статус" % label)
        self.assertEqual(intake_texts(), before, "%s: на повторное «да» бот молчит (напоминания нет)" % label)
        return b

    def test_W01_booked(self):
        self.wcase("W1", status="booked", text=T_BOOKED, books=1, names=NAMES_BOOK)

    def test_W02_duplicate(self):
        self.wcase("W2", status="approved", text=T_DUP, books=1,
                   resp={"ok": False, "error": "duplicate", "row": 12})

    def test_W03_timeout_unknown(self):
        self.wcase("W3", status="write_unknown", text=t_unknown("timeout"), books=1, resp=R_TIMEOUT)

    def test_W04_request_failed_unknown(self):
        self.wcase("W4", status="write_unknown", text=t_unknown("request_failed"), books=1, resp=R_REQFAIL)

    def test_W05_card_deadline_unknown(self):
        self.wcase("W5", status="write_unknown", text=t_unknown("card_deadline"), books=1, resp=R_DEADLINE)

    def test_W06_unknown_codes(self):
        for label, resp, err in W6_UNKNOWN:
            with self.subTest(case="W6", code=label):
                self.wcase("W6 %s" % label, status="write_unknown", text=t_unknown(err), books=1, resp=resp)

    def test_W07_exception_after_send(self):
        self.wcase("W7", status="write_unknown", text=t_unknown("RuntimeError"), books=1,
                   book_exc=RuntimeError("обрыв"))

    def test_W08_no_answer(self):
        for label, resp in (("None", None), ("строка", "ok"), ("список", [])):
            with self.subTest(case="W8", resp=label):
                self.wcase("W8 %s" % label, status="write_unknown", text=t_unknown("нет ответа"), books=1,
                           resp=resp)

    def test_W09_not_written_codes(self):
        for code in NOT_WRITTEN_ERRORS:
            with self.subTest(case="W9", code=code):
                self.wcase("W9 %s" % code, status="write_failed", text=t_not_written(code, "проверка теста"),
                           books=1, resp={"ok": False, "error": code, "message": "проверка теста"})
        with self.subTest(case="W9", code="bad_dates без message"):
            self.wcase("W9 bad_dates пусто", status="write_failed", text=t_not_written("bad_dates"), books=1,
                       resp={"ok": False, "error": "bad_dates"})

    def test_W10_ticket_exception_before_send(self):
        self.wcase("W10", status="write_failed",
                   text=t_not_written("exception", "до отправки: RuntimeError: билет недоступен"),
                   books=0, names=["issue_write_ticket"], ticket_exc=RuntimeError("билет недоступен"))

    def test_W11_photo_after_unknown_not_rearmed(self):
        b = self.stand(resp=R_TIMEOUT)
        exc = self.say(b, "да")
        self.expect(b, exc, books=1, status="write_unknown", sends=[t_unknown("timeout")], ctx="W11 шаг W3")
        exc = self.say(b, None, photo=True)
        self.assertIsNone(exc, "W11: фото — обработчик бросил %r" % (exc,))
        self.assertEqual(FINALIZE_CALLS, [], "W11: _intake_finalize НЕ вызывается для write_unknown")
        self.assertEqual(status_now(), "write_unknown", "W11: карточка не взведена фото")
        self.assertEqual(intake_texts(), [t_unknown("timeout"), T_PHOTO_UNKNOWN], "W11: ответ на фото")
        self.assertEqual(len(SAVE_CALLS), 1, "W11: паспорт сохранён (привязан)")
        self.assertTrue(S._INTAKE_DRAFTS[INTAKE].get("passport_photo"), "W11: паспорт привязан к черновику")
        exc = self.say(b, "да")
        self.assertIsNone(exc, "W11: «да» после фото — обработчик бросил %r" % (exc,))
        self.assertEqual(b.books(), 1, "W11: «да» после фото НЕ зовёт create_booking (0 новых)")
        self.assertEqual(status_now(), "write_unknown", "W11: статус после «да»")

    def test_W11_twin_photo_fresh_card(self):
        """Близнец W11: фото к свежей карточке — _intake_finalize вызван, карточка ждёт, «да» пишет."""
        b = self.stand()
        exc = self.say(b, None, photo=True)
        self.assertIsNone(exc, "W11 близнец: обработчик бросил %r" % (exc,))
        self.assertEqual(FINALIZE_CALLS, ["awaiting_approval"], "W11 близнец: _intake_finalize вызван")
        self.assertEqual(status_now(), "awaiting_approval")
        t = intake_texts()
        self.assertEqual(len(t), 1, "W11 близнец: одно резюме карточки: %r" % (t,))
        self.assertIn(SUMMARY_MARK, t[0])
        self.assertTrue(t[0].rstrip().endswith(SUMMARY_TAIL), t[0])
        exc = self.say(b, "да")
        self.assertIsNone(exc)
        self.assertEqual(b.books(), 1, "W11 близнец: «да» после фото пишет бронь")
        self.assertEqual(status_now(), "booked")

    def test_W11_twin_write_failed_rearmed(self):
        """Граница п.2.4/5: для write_failed взведение фото НЕ меняется (там «не записано» — повтор безопасен)."""
        b = self.stand(status="write_failed")
        exc = self.say(b, None, photo=True)
        self.assertIsNone(exc, "write_failed+фото: обработчик бросил %r" % (exc,))
        self.assertEqual(FINALIZE_CALLS, ["write_failed"], "write_failed+фото: _intake_finalize вызван")
        self.assertEqual(status_now(), "awaiting_approval", "write_failed+фото: карточка взведена, как прежде")
        self.assertEqual(b.books(), 0)

    def test_W12_new_card_after_unknown(self):
        b = self.stand(resp=R_TIMEOUT)
        exc = self.say(b, "да")
        self.assertIsNone(exc)
        self.assertEqual(b.books(), 1)
        b.resp = dict(OK_RESP)
        S._INTAKE_PASSPORT[INTAKE] = {"file_id": "f-test", "fields": dict(PP_FIELDS), "ocr_status": "ok",
                                      "ts": S._time.time()}
        n0 = len(intake_texts())
        exc = self.say(b, "\U0001F195 БРОНЬ\nКлиент: Мария Тест\nМодель: " + BIKE)
        self.assertIsNone(exc, "W12: новая карточка — обработчик бросил %r" % (exc,))
        self.assertEqual(status_now(), "awaiting_approval", "W12: новая карточка заменила черновик")
        self.assertEqual(len(intake_texts()), n0 + 1, "W12: резюме новой карточки")
        exc = self.say(b, "да")
        self.assertIsNone(exc)
        self.assertEqual(b.books(), 2, "W12: 1 новый вызов create_booking (законный повтор новой карточкой)")
        self.assertEqual(status_now(), "booked")
        self.assertEqual(intake_texts()[-1], T_BOOKED)

    def test_W_log_side_effects(self):
        """Побочное п.2.3: предупреждения в журнал для UNKNOWN и NOT_WRITTEN."""
        b = self.stand(resp=R_TIMEOUT)
        LOGS.clear()
        self.assertIsNone(self.say(b, "да"))
        warn = [m for lv, m in LOGS if lv == logging.WARNING]
        self.assertTrue(any("исход записи брони НЕИЗВЕСТЕН (timeout" in m for m in warn),
                        "UNKNOWN: нет предупреждения «исход записи брони НЕИЗВЕСТЕН»: %r" % (warn,))
        b = self.stand(resp={"ok": False, "error": "no_ticket", "message": "нет билета"})
        LOGS.clear()
        self.assertIsNone(self.say(b, "да"))
        warn = [m for lv, m in LOGS if lv == logging.WARNING]
        self.assertTrue(any("бронь НЕ записана (no_ticket" in m for m in warn),
                        "NOT_WRITTEN: нет предупреждения «бронь НЕ записана»: %r" % (warn,))


# ================================================================================================ C: свойства
class C_Properties(Base):
    """Сквозные свойства (а)–(в) раздела 3."""

    def test_PROP_a_b_traps_never_write(self):
        self.assertGreaterEqual(len(TRAPS), 40)
        self.twin_book("ловушки", "да")
        for text in TRAPS:
            with self.subTest(inp=text):
                b = self.stand()
                exc = self.say(b, text)
                self.assertIsNone(exc, "%r: обработчик бросил %r" % (text, exc))
                self.assertEqual(b.books(), 0, "%r: не согласие — create_booking 0 раз" % text)
                self.assertEqual(b.names(), [], "%r: ни билета, ни записи" % text)
                self.assertNotIn(status_now(), ("approved", "booked", "write_unknown", "write_failed"),
                                 "%r: статус записи без согласия" % text)

    def test_PROP_b_consent_only_writes_once(self):
        for text in CONSENT_ONLY:
            with self.subTest(inp=text):
                b = self.stand()
                exc = self.say(b, text)
                self.expect_kind(b, exc, "book", "согласие %r" % text)

    def test_PROP_v_no_message_text_in_log(self):
        mark = "зюзельфинк"
        b = self.stand()
        LOGS.clear()
        self.assertIsNone(self.say(b, "да"))
        self.assertTrue(any(BIKE in m for _, m in LOGS),
                        "близнец: захват журнала не видит записи брони — стенд слеп: %r" % (LOGS,))
        cases = [("да, Зюзельфинка позвонит", {}), ("нет, Зюзельфинка против", {}), ("Зюзельфинка, исправь", {}),
                 ("Зюзельфинка", {}), ("Зюзельфинка?", {}), ("Зюзельфинка", {"reply_to_bot": True})]
        for text, mkw in cases:
            with self.subTest(inp=text, msg=str(mkw)):
                b = self.stand()
                LOGS.clear()
                exc = self.say(b, text, **mkw)
                self.assertIsNone(exc, "%r: обработчик бросил %r" % (text, exc))
                leaked = [m for _, m in LOGS if mark in m.lower()]
                self.assertEqual(leaked, [], "%r: текст сообщения попал в журнал" % text)

    def test_PROP_v_verdict_and_author_logged(self):
        b = self.stand()
        LOGS.clear()
        self.assertIsNone(self.say(b, "да, Зюзельфинка позвонит"))
        info = [m for lv, m in LOGS if lv == logging.INFO and "ответ на карточку" in m]
        self.assertTrue(info, "п.2.4.4: в журнал пишется вердикт ответа на карточку: %r" % (LOGS,))
        self.assertTrue(any("@" + APPROVER in m for m in info), "п.2.4.4: и имя автора: %r" % (info,))


# ================================================================================================ D: ручка отката
class D_Knob(Base):
    """INTAKE_CONFIRM_STRICT: не задана/1 — строгий режим; 0/off/no/нет — прежнее поведение cbe1322 байт-в-байт."""

    def test_K1_default_is_strict(self):
        self.assertNotIn(KNOB, os.environ)
        self.twin_book("K1", "ставь")
        b = self.stand()
        exc = self.say(b, "не ставь")
        self.expect_kind(b, exc, "reject", "K1 ручка не задана, 'не ставь'")

    def test_K2_knob_1_is_strict(self):
        os.environ[KNOB] = "1"
        self.twin_book("K2", "ставь")
        b = self.stand()
        exc = self.say(b, "не ставь")
        self.expect_kind(b, exc, "reject", "K2 ручка=1, 'не ставь'")

    def test_K3_knob_0_section3_goldens(self):
        os.environ[KNOB] = "0"
        for label, text, mkw, _strict, legacy_kind in S3:
            with self.subTest(case=label, inp=text, msg=str(mkw)):
                b = self.stand()
                exc = self.say(b, text, **mkw)
                self.expect_kind(b, exc, legacy_kind, "ручка 0 %s %r" % (label, text), LEGACY_KIND)
        for text in ("правки", "исправь модель"):
            with self.subTest(case="EDIT", inp=text):
                b = self.stand()
                exc = self.say(b, text)
                self.expect_kind(b, exc, "edit", "ручка 0 %r" % text, LEGACY_KIND)

    def test_K4_knob_0_write_goldens(self):
        os.environ[KNOB] = "0"
        table = [
            ("W1", {}, "booked", [T_BOOKED], 1),
            ("W2", dict(resp={"ok": False, "error": "duplicate", "row": 12}), "approved", [T_DUP], 1),
            # ДЕФЕКТ Д2 при ручке 0: неизвестный исход назван «Не записалось», статус approved
            ("W3", dict(resp=R_TIMEOUT), "approved", [l_fail("timeout", "Timeout >60s")], 1),
            ("W4", dict(resp=R_REQFAIL), "approved", [l_fail("request_failed", "HTTP 502")], 1),
            ("W5", dict(resp=R_DEADLINE), "approved", [l_fail("card_deadline", "бюджет карточки исчерпан")], 1),
            ("W6 receipt_unknown", dict(resp=W6_UNKNOWN[0][1]), "approved",
             [l_fail("receipt_unknown", "расписка не доехала")], 1),
            ("W6 write_failed", dict(resp=W6_UNKNOWN[1][1]), "approved", [l_fail("write_failed", "запись прервалась")], 1),
            ("W6 пусто", dict(resp={"ok": False, "error": "", "message": ""}), "approved", [l_fail("?", "")], 1),
            ("W7", dict(book_exc=RuntimeError("обрыв")), "approved", [l_fail("exception", "обрыв")], 1),
            ("W9", dict(resp={"ok": False, "error": "no_ticket", "message": "нет билета"}), "approved",
             [l_fail("no_ticket", "нет билета")], 1),
            ("W10", dict(ticket_exc=RuntimeError("билет недоступен")), "approved",
             [l_fail("exception", "билет недоступен")], 0),
        ]
        for label, bkw, status, sends, books in table:
            with self.subTest(case=label):
                b = self.stand(**bkw)
                exc = self.say(b, "да")
                self.expect(b, exc, books=books, status=status, sends=sends, ctx="ручка 0 %s" % label)
        with self.subTest(case="W8"):
            b = self.stand(resp=None)
            exc = self.say(b, "да")
            # ДЕФЕКТ при ручке 0: ответ None роняет обработчик (res.get после try) — прежнее поведение
            self.assertIsInstance(exc, AttributeError, "ручка 0 W8: прежний код падал на None")
            self.assertEqual(b.books(), 1)
            self.assertEqual(status_now(), "approved")
            self.assertEqual(intake_texts(), [])

    def test_K5_knob_0_photo_rearms(self):
        os.environ[KNOB] = "0"
        b = self.stand(resp=R_TIMEOUT)
        self.assertIsNone(self.say(b, "да"))
        self.assertIsNone(self.say(b, None, photo=True))
        self.assertEqual(FINALIZE_CALLS, ["approved"], "ручка 0 W11: _intake_finalize вызван")
        self.assertEqual(status_now(), "awaiting_approval", "ручка 0 W11: карточка взведена")
        self.assertIsNone(self.say(b, "да"))
        self.assertEqual(b.books(), 2, "ручка 0 W11: следующее «да» — второй вызов")
        t = intake_texts()
        self.assertEqual(len(t), 3, t)
        self.assertEqual(t[0], l_fail("timeout", "Timeout >60s"))
        self.assertIn(SUMMARY_MARK, t[1])
        self.assertEqual(t[2], l_fail("timeout", "Timeout >60s"))

    def test_K6_other_off_values(self):
        for v in ("off", "no", "нет"):
            with self.subTest(knob=v):
                os.environ[KNOB] = v
                b = self.stand()
                exc = self.say(b, "не ставь")
                self.expect_kind(b, exc, "book", "ручка=%r 'не ставь' (прежнее, ДЕФЕКТ Д1)" % v, LEGACY_KIND)


# ================================================================================================ E: структура
class E_Structure(Base):

    def test_S1_legacy_block_textually_untouched(self):
        with open(os.path.join(ROOT, "splinter.py"), encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        hits = []
        for i, ln in enumerate(lines):
            if ln == LEGACY_BLOCK_FIRST:
                win = "\n".join(lines[i:i + LEGACY_BLOCK_N]) + "\n"
                if hashlib.sha256(win.encode("utf-8")).hexdigest() == LEGACY_BLOCK_SHA256:
                    hits.append(i)
        self.assertEqual(len(hits), 1, "прежний блок ветки 3 (49 строк cbe1322) не найден дословно ровно один раз")
        back = lines[max(0, hits[0] - 6):hits[0]]
        self.assertIn(LEGACY_GUARD, back, "прежний блок обязан стоять под условием ветки 3")

    def test_S2_intake_confirm_module_pure(self):
        p = os.path.join(ROOT, "intake_confirm.py")
        self.assertTrue(os.path.isfile(p), "модуля intake_confirm.py нет")
        with open(p, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        imports = set()
        for nd in ast.walk(tree):
            if isinstance(nd, ast.Import):
                imports |= {a.name.split(".")[0] for a in nd.names}
            elif isinstance(nd, ast.ImportFrom):
                imports.add((nd.module or "").split(".")[0])
        self.assertEqual(imports, {"re"}, "импорты intake_confirm — ровно {'re'}")
        bad = []
        for nd in ast.walk(tree):
            if isinstance(nd, ast.Call) and isinstance(nd.func, ast.Name) and nd.func.id in (
                    "open", "exec", "eval", "compile", "__import__", "input"):
                bad.append(nd.func.id)
            if isinstance(nd, ast.Name) and nd.id in ("os", "sys"):
                bad.append(nd.id)
        self.assertEqual(bad, [], "intake_confirm не открывает файлы и не трогает os/sys")


if __name__ == "__main__":
    unittest.main(verbosity=2)
