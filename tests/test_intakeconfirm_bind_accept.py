# -*- coding: utf-8 -*-
"""INTAKECONFIRM1610, ДЕЛЬТА приёмки: согласие на бронь засчитывается только РЕПЛАЕМ на сообщение ЭТОЙ карточки.

Повод — замечание Codex TB-OWNER-CHECK-1610-0307 (принято К3): в строгом режиме «да» без реплая и «да» реплаем на
ЛЮБОЕ сообщение бота доходят до create_booking; черновик выбирается по чату, статусу и авторизатору, поэтому
случайное «да» в той же теме по другому поводу даёт ложную бронь.

Источник требований — ТОЛЬКО текст дельты (пункты 1–6) и проект `DESIGN_INTAKECONFIRM1610.md` (прежние тексты
строгого режима). Код исправителя (fix15/a) автор приёмки не видел. Механика стенда взята у
`tests/test_intakeconfirm_accept.py`: НАСТОЯЩИЙ обработчик `splinter._handle_intake`, фейковый мост со счётчиком,
`_send` пишет в список. Отличие: карточка строится ЖИВЫМ путём (сообщение «🆕 БРОНЬ…» → фото паспорта → резюме
бота), а заглушка `_send` возвращает объект с `message_id`, как настоящая отправка Telegram, — иначе id резюме
получить нечем.

Что считается «сообщением карточки» (п.1 дельты): сама карточка, фото паспорта, привязанное к ней, и сообщение
бота с резюме «Карточка принята… Ставлю бронь?» по ней. Привязка — по message_id, не по тексту (случай D3).

Случаи (у каждого отрицательного — близнец, где запись проходит: стенд доказанно умеет писать):
  A1 «да» без реплая при ждущей карточке → 0 записей, ОДНО уточнение, называющее модель и даты карточки (без
     имени и телефона клиента), статус awaiting_approval; на том же стенде затем «да» реплаем на карточку → 1;
  A2 близнец на свежем стенде: «да» реплаем на карточку → 1;
  B  «да» реплаем на фото паспорта этой карточки → 1;
  C  «да» реплаем на сообщение бота-резюме ЭТОЙ карточки → 1 (id резюме — из ответа заглушки отправки);
  D  «да» реплаем на сообщение ДРУГОГО бота / старое сообщение этого бота / сообщение бота с текстом резюме, но
     чужим id → 0 и ТО ЖЕ уточнение, что без реплая; близнец на том же стенде — реплай на резюме → 1;
  D4 «да» реплаем на сообщение человека, не относящееся к карточке → 0 (текст ответа не нормируется: дельта его не
     называет, прежний _IC_ASK_REPLY допустим);
  E  карточку сменили (вторая карточка в том же чате): «да» реплаем на карточку/фото/резюме ПЕРВОЙ → 0 и
     уточнение, называющее ВТОРУЮ; близнец — реплаем на карточку/фото/резюме второй → 1 с полями второй;
  F  «нет» без реплая → отказ как прежде (строгий текст), 0 записей; прочие не-YES вердикты не тронуты;
  G  ручка INTAKE_CONFIRM_STRICT=0 → «да» без реплая и реплаем на чужого бота пишут бронь (прежнее поведение);
  K  ручка =1 → то же, что по умолчанию (уточнение);
  S1 константа текста уточнения `_IC_ASK_BIND` заведена в splinter; S2 d["ic_msg_ids"] держит id карточки, фото
     и резюме.

Данные только синтетические (Мария Тест / Пётр Тест, CB 300CC R 9011 / NMAX 155 GREY 7777, телефоны вида
+66 8x 000 1610). Сети, мозга, CRM, файлов тест не касается; дерево берётся от __file__, чужие корни из sys.path
убираются.
"""
import asyncio
import datetime
import itertools
import json
import os
import re
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
APPROVER = "deramor"
CARD_AUTHOR = "intake_op_test"        # автор карточки и фото паспорта: человек, не аппрувер (синтетика)
OTHER_HUMAN = "rogova_darya"
BOT_UNAME = "turbobaby_manager_bot"
BOT_ID = 999
OTHER_BOT = "other_helper_test_bot"
KNOB = "INTAKE_CONFIRM_STRICT"

PFX = "\U0001F400 Splinter\n"
T_BOOKED = PFX + "\u2705 Бронь записана, строка 33, статус \u00abБронь\u00bb."
# К3 16.10 04:2x (правка литерала, названа в коммите): текст _IC_ASK приведён к правилу привязки — «да» только
# реплаем; прежний литерал «Поставить: «да».» советовал то, что больше не ставит бронь. Проверки записи/статуса те же.
T_ASK = PFX + ("\u2753 Ответ неоднозначный \u2014 бронь не ставлю. Поставить: \u00abда\u00bb только ответом (реплаем) "
               "на карточку брони. Отказ: \u00abнет\u00bb. Исправить: \u00abправки\u00bb.")
T_EDIT = PFX + "\u270f\ufe0f Принял, жду исправленную карточку."
T_REJECT = PFX + "\u274c Бронь отклонена \u2014 в CRM ничего не записано."
L_REJECT = PFX + "\u274c Бронь отклонена."
SUMMARY_MARK = "Карточка принята."

CARD1 = {"model": "CB 300CC R 9011", "client": "Мария Тест", "contacts": "+66 81 000 1610",
         "date_start": "20-10-2026", "date_end": "27-10-2026", "date_start_iso": None, "date_end_iso": None,
         "deposit_type": "паспорт", "helmets": 2, "experience": "есть", "delivery_name": "Раваи (тест)",
         "delivery_url": "https://maps.google.com/?q=test", "term": "7 дней"}
CARD2 = {"model": "NMAX 155 GREY 7777", "client": "Пётр Тест", "contacts": "+66 82 000 1610",
         "date_start": "01-11-2026", "date_end": "05-11-2026", "date_start_iso": None, "date_end_iso": None,
         "deposit_type": "паспорт", "helmets": 1, "experience": "нет", "delivery_name": "Карон (тест)",
         "delivery_url": "https://maps.google.com/?q=test2", "term": "4 дня"}
PARSED = {1: CARD1, 2: CARD2}
CARD_TEXT = {1: "\U0001F195 БРОНЬ\nКлиент: Мария Тест\nМодель: CB 300CC R 9011",
             2: "\U0001F195 БРОНЬ\nКлиент: Пётр Тест\nМодель: NMAX 155 GREY 7777"}
PP_FIELDS = {"full_name": "TEST MARIA", "country": "TST", "expire_date": "2030-01-01"}
# ПДн, которых в уточнении быть не должно (имя клиента, имя из паспорта, телефон) — в нижнем регистре
PII = ("мария", "maria", "пётр", "петр", "000 1610", "0001610")

OK_RESP = {"ok": True, "row": 33, "booking_id": "b-1"}

_PLACEHOLDER = re.compile(r"\{[^{}]*\}|%(?:\([^)]*\))?[-#0 +]*\d*(?:\.\d+)?[sdirf]")


def expected_fields(c):
    return {"bike": c["model"], "name": c["client"], "date_start": c["date_start"], "date_end": c["date_end"],
            "deposit": "passport", "helmets": c["helmets"], "contacts": c["contacts"],
            "note": "опыт: %s | доставка: %s | срок: %s" % (c["experience"], c["delivery_name"], c["term"])}


def date_named(text, ds):
    """Дата карточки названа: дословно из черновика либо в обычных её записях (дд.мм.гггг, дд-мм, дд.мм)."""
    vs = {ds, ds.replace("-", "."), ds.replace("-", "/"), ds[:5], ds[:5].replace("-", ".")}
    return any(v in text for v in vs)


# ------------------------------------------------------------------------------------------------ стенд
SENDS = []                       # dict(chat, text, kw, mid)
_UMID = itertools.count(5000)    # сообщения людей
_BMID = itertools.count(9000)    # сообщения бота (id из «ответа Telegram» заглушки)


class U:
    def __init__(self, username, is_bot=False, uid=None):
        self.username = username
        self.is_bot = is_bot
        self.id = uid if uid is not None else 1000 + len(username or "")
        self.first_name = username


def bot_user():
    return U(BOT_UNAME, is_bot=True, uid=BOT_ID)


class Ref:
    """Сообщение, на которое отвечают (reply_to_message)."""

    def __init__(self, message_id, from_user, text=None, photo=False):
        self.message_id = message_id
        self.from_user = from_user
        self.text = text
        self.caption = None
        self.photo = [object()] if photo else None
        self.chat_id = INTAKE
        self.message_thread_id = None
        self.date = datetime.datetime.now(datetime.timezone.utc)


class Sent:
    """Ответ Telegram на отправку: у него есть message_id."""

    def __init__(self, message_id, chat_id, text):
        self.message_id = message_id
        self.chat_id = chat_id
        self.text = text
        self.caption = None
        self.photo = None
        self.from_user = bot_user()
        self.message_thread_id = None
        self.date = datetime.datetime.now(datetime.timezone.utc)


def _record(chat_id, text, kw):
    mid = next(_BMID)
    SENDS.append({"chat": chat_id, "text": text, "kw": kw, "mid": mid})
    return Sent(mid, chat_id, text)


async def rec_send(context, *, chat_id, text, message_thread_id=None, bilingual=True, **k):
    return _record(chat_id, text, {"via": "_send", "bilingual": bilingual, "message_thread_id": message_thread_id})


class Msg:
    def __init__(self, text=None, uname=APPROVER, photo=False, reply_to=None):
        self.text = text
        self.caption = None
        self.photo = [object()] if photo else None
        self.sticker = None
        self.media_group_id = None
        self.chat_id = INTAKE
        self.message_thread_id = None
        self.date = datetime.datetime.now(datetime.timezone.utc)
        self.message_id = next(_UMID)
        self.from_user = U(uname)
        self.reply_to_message = reply_to

    async def reply_text(self, text, **kw):
        return _record(self.chat_id, text, dict(kw, via="reply_text"))


class _Bot:
    username = BOT_UNAME
    id = BOT_ID

    async def send_message(self, chat_id=None, text=None, **kw):
        return _record(chat_id, text, dict(kw, via="bot.send_message"))


class Ctx:
    bot = _Bot()


class FakeClaude:
    def quick(self, system, text, max_tokens=300, **kw):
        return json.dumps(PARSED[2 if "7777" in str(text) else 1], ensure_ascii=False)

    def vision(self, *a, **k):
        return "{}"


class FakeBridge:
    """Мост со счётчиком. Любой иной метод моста — AttributeError (новых чтений/записей дельта не заводит)."""

    def __init__(self):
        self.calls = []

    def issue_write_ticket(self):
        self.calls.append(("issue_write_ticket", {}))
        return {"ok": True, "ticket": "t-test-1610"}

    def create_booking(self, **kw):
        self.calls.append(("create_booking", dict(kw)))
        return dict(OK_RESP, bike=kw.get("bike"))

    def names(self):
        return [n for n, _ in self.calls]

    def books(self):
        return sum(1 for n, _ in self.calls if n == "create_booking")

    def booking_kwargs(self):
        return [k for n, k in self.calls if n == "create_booking"]


async def fake_ocr(photo_msg, chat_id, context, bridge):
    S._INTAKE_PASSPORT[chat_id] = {"file_id": "f-test", "fields": dict(PP_FIELDS), "ocr_status": "ok",
                                   "ts": S._time.time()}
    return (True, dict(PP_FIELDS))


def fake_save(chat_id, draft, bridge):
    return None


S._send = rec_send
S._intake_passport_ocr = fake_ocr
S._intake_passport_save = fake_save


def reset():
    SENDS.clear()
    S._INTAKE_DRAFTS.clear()
    S._INTAKE_PASSPORT.clear()
    S._HANDOVER_ACTIVATIONS.clear()
    S._RETURN_CLOSES.clear()
    S._RECENT_BOOKINGS.clear()


def status_now():
    d = S._INTAKE_DRAFTS.get(INTAKE)
    return d.get("status") if d else None


class Card:
    def __init__(self, n, card_mid, photo_mid, summary_mid, summary_text):
        self.n = n
        self.card_mid = card_mid
        self.photo_mid = photo_mid
        self.summary_mid = summary_mid
        self.summary_text = summary_text


def ref_card(c):
    return Ref(c.card_mid, U(CARD_AUTHOR), CARD_TEXT[c.n])


def ref_photo(c):
    return Ref(c.photo_mid, U(CARD_AUTHOR), None, photo=True)


def ref_summary(c):
    return Ref(c.summary_mid, bot_user(), c.summary_text)


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

    def stand(self):
        reset()
        return FakeBridge()

    def say(self, b, text=None, **mkw):
        m = Msg(text, **mkw)
        try:
            asyncio.run(S._handle_intake(m, Ctx(), b, FakeClaude()))
        except Exception as e:  # noqa: BLE001
            return e, m
        return None, m

    def build(self, b, n=1):
        """Живой путь карточки: «🆕 БРОНЬ…» (паспорта нет → «не хватает») → фото паспорта → резюме бота."""
        k0 = len(SENDS)
        exc, cm = self.say(b, CARD_TEXT[n], uname=CARD_AUTHOR)
        self.assertIsNone(exc, "стенд: карточка %d — обработчик бросил %r" % (n, exc))
        exc, pm = self.say(b, None, uname=CARD_AUTHOR, photo=True)
        self.assertIsNone(exc, "стенд: фото паспорта %d — обработчик бросил %r" % (n, exc))
        sums = [s for s in SENDS[k0:] if s["chat"] == INTAKE and SUMMARY_MARK in str(s["text"] or "")]
        self.assertTrue(sums, "стенд: резюме карточки %d не отправлено: %r" % (n, SENDS[k0:]))
        self.assertEqual(status_now(), "awaiting_approval", "стенд: карточка %d ждёт ответа" % n)
        self.assertEqual(S._INTAKE_DRAFTS[INTAKE].get("model"), PARSED[n]["model"], "стенд: черновик — карточка %d" % n)
        self.assertEqual(b.books(), 0, "стенд: сборка карточки бронь не пишет")
        s = sums[-1]
        return Card(n, cm.message_id, pm.message_id, s["mid"], s["text"])

    def two_cards(self):
        """Карточка 1 со своим фото и резюме, затем карточка 2 в том же чате — позже окна 5 мин после фото 1
        (буфер паспорта к карточке 2 не привязывается, у неё своё фото и своё резюме)."""
        b = self.stand()
        c1 = self.build(b, 1)
        S._INTAKE_PASSPORT[INTAKE]["ts"] = S._time.time() - 600
        c2 = self.build(b, 2)
        return b, c1, c2

    def new_texts(self, k0):
        return [s["text"] for s in SENDS[k0:] if s["chat"] == INTAKE]

    def check_bilingual(self, ctx):
        bad = [s["text"] for s in SENDS if s["chat"] == INTAKE and s["kw"].get("via") == "_send"
               and s["kw"].get("bilingual") is not False]
        self.assertEqual(bad, [], "%s: отправка обязана быть bilingual=False" % ctx)

    def expect_booked(self, b, k0, books, n, ctx):
        self.assertEqual(b.books(), books, "%s: число вызовов create_booking" % ctx)
        self.assertEqual(b.booking_kwargs()[-1], expected_fields(PARSED[n]), "%s: поля записи брони" % ctx)
        self.assertEqual(status_now(), "booked", "%s: статус карточки" % ctx)
        self.assertEqual(self.new_texts(k0), [T_BOOKED], "%s: ответ бота" % ctx)
        self.check_bilingual(ctx)

    def assert_bind_text(self, text, n, ctx):
        c = PARSED[n]
        self.assertIsInstance(text, str, "%s: текст уточнения" % ctx)
        self.assertTrue(text.startswith(PFX), "%s: префикс Splinter: %r" % (ctx, text))
        self.assertNotIn(text, (T_ASK, T_EDIT, T_REJECT, T_BOOKED, L_REJECT),
                         "%s: это не уточнение привязки, а прежний ответ: %r" % (ctx, text))
        low = text.lower()
        self.assertIn(c["model"].lower(), low, "%s: уточнение называет модель карточки: %r" % (ctx, text))
        for ds in (c["date_start"], c["date_end"]):
            self.assertTrue(date_named(text, ds), "%s: уточнение называет дату %s: %r" % (ctx, ds, text))
        for p in PII:
            self.assertNotIn(p, low, "%s: в уточнении ПДн клиента (%r): %r" % (ctx, p, text))
        rep = getattr(S, "_IC_ASK_REPLY", None)
        if isinstance(rep, str) and not _PLACEHOLDER.search(rep):
            self.assertNotIn(text, (rep, PFX + rep), "%s: это _IC_ASK_REPLY, а не уточнение привязки" % ctx)
        tmpl = getattr(S, "_IC_ASK_BIND", None)
        if isinstance(tmpl, str):
            pos = 0
            for frag in (f.strip() for f in _PLACEHOLDER.split(tmpl)):
                if not frag:
                    continue
                i = text.find(frag, pos)
                self.assertGreaterEqual(i, 0, "%s: текст не из _IC_ASK_BIND (нет куска %r): %r" % (ctx, frag, text))
                pos = i + len(frag)

    def expect_bind(self, b, k0, calls0, n, ctx):
        """Уточнение без записи: ни билета, ни create_booking; карточка ждёт; ровно одно сообщение-уточнение."""
        self.assertEqual(b.books(), sum(1 for x, _ in calls0 if x == "create_booking"),
                         "%s: create_booking не вызывается" % ctx)
        self.assertEqual(b.calls, calls0, "%s: ни билета, ни записи" % ctx)
        self.assertEqual(status_now(), "awaiting_approval", "%s: статус карточки (не booked)" % ctx)
        t = self.new_texts(k0)
        self.assertEqual(len(t), 1, "%s: ровно одно сообщение-уточнение, получено %r" % (ctx, t))
        self.assert_bind_text(t[0], n, ctx)
        self.check_bilingual(ctx)
        return t[0]

    def bind_case(self, b, n, reply_to, ctx):
        calls0 = list(b.calls)
        k0 = len(SENDS)
        exc, _ = self.say(b, "да", reply_to=reply_to)
        self.assertIsNone(exc, "%s: обработчик бросил %r" % (ctx, exc))
        return self.expect_bind(b, k0, calls0, n, ctx)

    def yes_case(self, b, n, reply_to, ctx, books=1):
        k0 = len(SENDS)
        exc, _ = self.say(b, "да", reply_to=reply_to)
        self.assertIsNone(exc, "%s: обработчик бросил %r" % (ctx, exc))
        self.expect_booked(b, k0, books, n, ctx)


# ================================================================================================ A: без реплая
class A_NoReply(Base):

    def test_A1_da_without_reply_asks_bind_then_reply_books(self):
        """«да» без реплая при ждущей карточке → 0 записей, уточнение по карточке; затем реплай на карточку → 1."""
        self.assertNotIn(KNOB, os.environ)
        b = self.stand()
        c = self.build(b, 1)
        self.bind_case(b, 1, None, "A1 «да» без реплая")
        self.yes_case(b, 1, ref_card(c), "A1 тот же стенд, затем «да» реплаем на карточку")

    def test_A1b_other_consent_words_without_reply(self):
        """Прочие чистые согласия без реплая — то же уточнение (п.2 касается любого YES)."""
        for text in ("Да.", "ок", "ставь", "подтверждаю"):
            with self.subTest(inp=text):
                b = self.stand()
                self.build(b, 1)
                calls0, k0 = list(b.calls), len(SENDS)
                exc, _ = self.say(b, text)
                self.assertIsNone(exc, "%r: обработчик бросил %r" % (text, exc))
                self.expect_bind(b, k0, calls0, 1, "A1b %r без реплая" % text)

    def test_A2_twin_reply_to_card_books(self):
        b = self.stand()
        c = self.build(b, 1)
        self.yes_case(b, 1, ref_card(c), "A2 близнец: «да» реплаем на карточку")


# ================================================================================================ B, C: свои сообщения
class B_C_OwnMessages(Base):

    def test_B_reply_to_passport_photo_books(self):
        b = self.stand()
        c = self.build(b, 1)
        self.yes_case(b, 1, ref_photo(c), "B «да» реплаем на фото паспорта этой карточки")

    def test_C_reply_to_bot_summary_books(self):
        b = self.stand()
        c = self.build(b, 1)
        if c.summary_mid is None:
            self.skipTest("резюме ушло мимо записывающих заглушек — message_id не получить")
        self.yes_case(b, 1, ref_summary(c), "C «да» реплаем на резюме бота по ЭТОЙ карточке")


# ================================================================================================ D: чужие сообщения
class D_ForeignReplies(Base):

    def test_D_reply_to_foreign_bot_message_asks_same_bind(self):
        variants = [
            ("D0 без реплая (эталон уточнения)", None),
            ("D1 сообщение другого бота", lambda c: Ref(7001, U(OTHER_BOT, is_bot=True), "\U0001F916 погода на завтра")),
            ("D2 старое сообщение этого бота", lambda c: Ref(4999, bot_user(), PFX + "\u2705 В аренде, строка 7.")),
            ("D3 сообщение бота с текстом резюме, но чужим id", lambda c: Ref(4998, bot_user(), c.summary_text)),
        ]
        texts = {}
        for label, mk in variants:
            with self.subTest(case=label):
                b = self.stand()
                c = self.build(b, 1)
                texts[label] = self.bind_case(b, 1, mk(c) if mk else None, label)
                self.yes_case(b, 1, ref_summary(c), "%s — близнец на том же стенде: реплай на резюме" % label)
        with self.subTest(case="D одно и то же уточнение"):
            if len(texts) >= 2:
                self.assertEqual(len(set(texts.values())), 1, "п.3: то же уточнение, что без реплая: %r" % texts)

    def test_D4_reply_to_human_not_card_no_write(self):
        b = self.stand()
        c = self.build(b, 1)
        calls0, k0 = list(b.calls), len(SENDS)
        exc, _ = self.say(b, "да", reply_to=Ref(6001, U(OTHER_HUMAN), "клиент подтвердит вечером"))
        self.assertIsNone(exc, "D4: обработчик бросил %r" % (exc,))
        self.assertEqual(b.calls, calls0, "D4: «да» реплаем на чужое сообщение человека — ни билета, ни записи")
        self.assertEqual(status_now(), "awaiting_approval", "D4: карточка ждёт")
        t = self.new_texts(k0)
        self.assertEqual(len(t), 1, "D4: одно ответное сообщение: %r" % (t,))
        self.assertNotEqual(t[0], T_BOOKED)
        self.assertTrue(t[0].startswith(PFX), t[0])
        self.yes_case(b, 1, ref_card(c), "D4 — близнец на том же стенде: реплай на карточку")


# ================================================================================================ E: смена карточки
class E_CardReplaced(Base):

    def test_E_reply_to_first_card_after_replace_asks_bind(self):
        texts = {}
        for label, mk in (("E1 реплай на карточку 1", ref_card), ("E2 реплай на фото паспорта карточки 1", ref_photo),
                          ("E3 реплай на резюме карточки 1", ref_summary)):
            with self.subTest(case=label):
                b, c1, c2 = self.two_cards()
                texts[label] = self.bind_case(b, 2, mk(c1), label + " (ждёт карточка 2)")
        with self.subTest(case="E0 эталон: «да» без реплая при карточке 2"):
            b, c1, c2 = self.two_cards()
            texts["E0"] = self.bind_case(b, 2, None, "E0 без реплая")
        with self.subTest(case="E одно и то же уточнение"):
            if len(texts) >= 2:
                self.assertEqual(len(set(texts.values())), 1, "п.4: то же уточнение: %r" % texts)

    def test_E_twin_reply_to_second_card_books(self):
        for label, mk in (("E1' реплай на карточку 2", ref_card), ("E2' реплай на фото паспорта карточки 2", ref_photo),
                          ("E3' реплай на резюме карточки 2", ref_summary)):
            with self.subTest(case=label):
                b, c1, c2 = self.two_cards()
                self.yes_case(b, 2, mk(c2), label)


# ================================================================================================ F: прочие вердикты
class F_NotYes(Base):

    def test_F_net_without_reply_rejects(self):
        b = self.stand()
        c = self.build(b, 1)
        self.yes_case(b, 1, ref_card(c), "F близнец: «да» реплаем на карточку")
        for label, mk in (("«нет» без реплая", None), ("«нет» реплаем на карточку", ref_card)):
            with self.subTest(case=label):
                b = self.stand()
                c = self.build(b, 1)
                calls0, k0 = list(b.calls), len(SENDS)
                exc, _ = self.say(b, "нет", reply_to=(mk(c) if mk else None))
                self.assertIsNone(exc, "%s: обработчик бросил %r" % (label, exc))
                self.assertEqual(b.calls, calls0, "%s: ни билета, ни записи" % label)
                self.assertEqual(status_now(), "rejected", "%s: статус" % label)
                self.assertEqual(self.new_texts(k0), [T_REJECT], "%s: ответ — отказ как прежде" % label)
                self.check_bilingual(label)

    def test_F2_other_verdicts_unchanged(self):
        """EDIT, SILENT, ASK и отказ словом — как в строгом режиме до дельты (п.5–6), привязка к ним не требуется."""
        cases = [
            ("правки без реплая", "правки", None, "awaiting_approval", [T_EDIT]),
            ("погода без реплая (молчание)", "погода", None, "awaiting_approval", []),
            ("«да?» без реплая (ASK, не уточнение привязки)", "да?", None, "awaiting_approval", [T_ASK]),
            ("погода реплаем на резюме (SILENT → ASK)", "погода", ref_summary, "awaiting_approval", [T_ASK]),
            ("отмена без реплая", "отмена", None, "rejected", [T_REJECT]),
        ]
        for label, text, mk, st, sends in cases:
            with self.subTest(case=label):
                b = self.stand()
                c = self.build(b, 1)
                calls0, k0 = list(b.calls), len(SENDS)
                exc, _ = self.say(b, text, reply_to=(mk(c) if mk else None))
                self.assertIsNone(exc, "%s: обработчик бросил %r" % (label, exc))
                self.assertEqual(b.calls, calls0, "%s: ни билета, ни записи" % label)
                self.assertEqual(status_now(), st, "%s: статус" % label)
                self.assertEqual(self.new_texts(k0), sends, "%s: ответ бота" % label)


# ================================================================================================ G, K: ручка
class G_Knob(Base):

    def test_G_knob_0_legacy_books_without_binding(self):
        """INTAKE_CONFIRM_STRICT=0 → прежнее поведение: «да» без реплая и реплаем на чужого бота пишут бронь."""
        os.environ[KNOB] = "0"
        for label, mk in (("ручка 0: «да» без реплая", None),
                          ("ручка 0: «да» реплаем на другого бота",
                           lambda c: Ref(7001, U(OTHER_BOT, is_bot=True), "\U0001F916 погода на завтра"))):
            with self.subTest(case=label):
                b = self.stand()
                c = self.build(b, 1)
                self.yes_case(b, 1, mk(c) if mk else None, label)

    def test_K_knob_1_is_strict_bind(self):
        os.environ[KNOB] = "1"
        b = self.stand()
        c = self.build(b, 1)
        self.bind_case(b, 1, None, "K ручка=1: «да» без реплая")
        self.yes_case(b, 1, ref_card(c), "K близнец на том же стенде: реплай на карточку")


# ================================================================================================ S: структура
class S_Structure(Base):

    def test_S1_bind_text_constant_exists(self):
        self.assertTrue(hasattr(S, "_IC_ASK_BIND"), "текст уточнения привязки — константа splinter._IC_ASK_BIND")
        v = getattr(S, "_IC_ASK_BIND", None)
        self.assertTrue(isinstance(v, str) or callable(v), "_IC_ASK_BIND — строка-шаблон или функция: %r" % (v,))

    def test_S2_ic_msg_ids_hold_card_photo_summary(self):
        b = self.stand()
        c = self.build(b, 1)
        ids = S._INTAKE_DRAFTS[INTAKE].get("ic_msg_ids")
        self.assertIsNotNone(ids, "черновик держит d['ic_msg_ids']")
        got = set(str(x) for x in ids)
        want = {str(c.card_mid), str(c.photo_mid), str(c.summary_mid)}
        self.assertTrue(want <= got, "ic_msg_ids ⊇ {карточка, фото, резюме}: ждал %r, есть %r" % (want, got))


if __name__ == "__main__":
    unittest.main(verbosity=2)
