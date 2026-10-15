# -*- coding: utf-8 -*-
"""INTAKECONFIRM1610 (16.10.2026): ответ подтверждающего на карточку брони — строгий режим (ручка по умолчанию).

Проект: DESIGN_INTAKECONFIRM1610.md §2–§4. Дефекты прежней ветки «3) approve / нет / правки» (`splinter._handle_intake`):
  Д1 — согласие искалось ПОДСТРОКОЙ и раньше отказа: «не ставь», «не надо», «нет, когда оплатит», «всегда», «погода»,
       «около» записывали бронь в CRM;
  Д2 — исход «неизвестно» (timeout, обрыв, бюджет…) назывался «❌ Не записалось».

Разделы:
  (A) таблица `intake_confirm.decide`;
  (B) таблица `intake_confirm.outcome` — каждый код NOT_WRITTEN_ERRORS и коды группы W6;
  (C) интеграция через `splinter._handle_intake` по таблицам проекта §3 (P/N и W) — у каждого отрицательного случая
      близнец (тот же стенд, другой ввод, запись проходит: 1 вызов, booked);
  (D) фото паспорта после «неизвестно» (W11) и законная новая карточка (W12);
  (E) свойства: (а) decide≠YES → 0 вызовов create_booking; (б) YES ⇔ слова есть, все из CONSENT_WORDS, вопроса
      нет, рядом только спокойные знаки и знаки согласия — на 40+ фразах-ловушках; (в) в журнал не попадает текст;
  (F) ast-чистота `intake_confirm.py`;
  (G) находки критиков 16.10: знаки сомнения рядом с «да» (I1), ответ не карточке и пересланное (I2), тег своего
      бота (И3), почти-согласие и стикер (И4), ложный окончательный отказ (И5/M1), «нет исправь» (M2), «да» после
      просьбы о правках (И6), ручка без учёта регистра и без нового состояния при откате (M3), без билета запись не
      уходит (M4);
  (G2) привязка к карточке (замечание Codex TB-OWNER-CHECK-1610-0307): «да» засчитывается ТОЛЬКО реплаем на
      сообщение ЭТОЙ карточки (карточка, её фото паспорта, резюме бота «Ставлю бронь?», адресное уточнение по ней);
      без реплая, реплаем на чужого бота / другую карточку / старое резюме — уточнение `_IC_ASK_BIND` без записи.
      Буква «G» в задании К3 уже занята находками критиков — раздел назван G2.

Стенд (с 16.10, привязка): сообщение по умолчанию — РЕПЛАЙ НА ТЕКУЩУЮ КАРТОЧКУ (первый id `d["ic_msg_ids"]`), так
теперь подтверждают; без реплая — явно `reply=NOREPLY`. В черновике `reset()` привязаны карточка (CARD_MID, человек)
и резюме бота (SUMMARY_MID = id `Reply()` по умолчанию). Подделка `_send` возвращает сообщение с id только при
`SEND_IDS["on"]` (иначе `None` — «id не получен», привязкой не считается).

Ручка INTAKE_CONFIRM_STRICT снята (проверка «по умолчанию включено»), один случай — с `=1`. Сеть, мозг и CRM не
трогаются: мост — подделка, `_send` пишет в список. Данные синтетические.
"""
import ast
import asyncio
import logging
import os
import re
import sys
import tempfile
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)                 # корень СВОЕГО дерева — первым (ловушка метода: чужой корень не берём)

for _f in ("RENTAL_CASE", "RENTAL_CASE_PICK", "RENTAL_CASE_APPROVALS", "RENTAL_CASE_DB", "CONTRACT_REF_GEN"):
    os.environ.pop(_f, None)
os.environ.pop("INTAKE_CONFIRM_STRICT", None)       # ручка не задана → строгий режим по умолчанию

# Память Splinter — только во временном каталоге прогона.
_TMP = tempfile.mkdtemp(prefix="intake_confirm_t_")
for _k, _name in (("HINT_DEDUP_STATE", "hint_dedup_state.json"), ("DECIDER_LIVE_STATE", "decider_live_state.json"),
                  ("WORKS_PERSIST_STATE", "works_persist_state.json"), ("MILEAGE_Q_STATE", "mileage_q.json"),
                  ("SVC_TOKENS_STATE", "svc_tokens.json"), ("TOPIC_FEED_DIR", "topic_feed"),
                  ("SPLINTER_ASK_STAFF_STATE", "staff_ask_state.json"), ("SPLINTER_RULES_SNAP", "rules_snap.json"),
                  ("WALLET_CACHE_FILE", "wallet_cache.json"), ("ENQUEUE_DEDUP_FILE", "enqueue_dedup.json")):
    os.environ[_k] = os.path.join(_TMP, _name)

try:
    import fcntl  # noqa: F401  (Linux; на ПК — заглушка только для импорта splinter)
except ImportError:
    _fc = types.ModuleType("fcntl")
    _fc.LOCK_SH, _fc.LOCK_EX, _fc.LOCK_NB, _fc.LOCK_UN = 1, 2, 4, 8
    _fc.flock = lambda *a, **k: None
    _fc.lockf = lambda *a, **k: None
    sys.modules["fcntl"] = _fc

import intake_confirm as IC  # noqa: E402
import splinter as S  # noqa: E402

INTAKE = S.INTAKE_CHAT
BIKE = "CB 300CC R 9011"
CLIENT = "Мария Тест"
APPROVER = "deramor"

# Тексты проекта §2.2/§2.3 — дословно (с префиксом отправки).
P = "🐀 Splinter\n"
T_BOOKED = P + "✅ Бронь записана, строка 33, статус «Бронь»."
# Подсказка привязки (16.10): «да» — только реплаем на карточку (прежнее «Поставить: «да».» без реплая не засчитывается).
T_ASK = P + ("❓ Ответ неоднозначный — бронь не ставлю. Поставить: «да» только ответом (реплаем) на карточку брони. "
             "Отказ: «нет». Исправить: «правки».")
T_EDIT = P + "✏️ Принял, жду исправленную карточку."
T_REJECT = P + "❌ Бронь отклонена — в CRM ничего не записано."
T_PHOTO_UNKNOWN = P + "📎 Паспорт привязан. Исход записи брони неизвестен — проверь CRM; повтор не делаю."


def t_unknown(err):
    return P + ("⚠️ Исход записи брони неизвестен (%s) — проверь CRM; повтор не делаю. "
                "Брони там нет — пришли карточку заново." % err)


def t_not_written(err, message=""):
    tail = (" " + message) if message else ""
    return P + "❌ Не записано: %s.%s\nВ CRM ничего не легло — исправь и пришли карточку заново." % (err, tail)


FIELDS = {"bike": BIKE, "name": CLIENT, "date_start": "15-11-2026", "date_end": "20-11-2026", "deposit": "passport",
          "helmets": 2, "contacts": "+66 80 000 0000", "note": None}

SUMMARY = ("🐀 Splinter · Карточка принята.\n"
           "Клиент: Мария Тест · контакты: +66 80 000 0000\n"
           "Модель: CB 300CC R 9011 · даты 15-11-2026 — 20-11-2026\n"
           "Опыт: —\n"
           "Депозит: паспорт\n"
           "Доставка: — (https://maps.app.goo.gl/test) ⚠️ район не определён — проверить вручную\n"
           "Шлемы: 2 · паспорт-фото: да\n"
           "Паспорт распознал (проверьте): MARIA TEST, TST, до 2030-01-01\n"
           "Наличие: даты не распознаны — проверить наличие вручную\n"
           "\nСтавлю бронь? да / нет / правки")


# ----------------------------------------------------------------------------------------------- стенд
class U:
    def __init__(self, uname, is_bot=False, uid=None):
        self.username = uname
        self.is_bot = is_bot
        self.id = uid


class Reply:
    """Сообщение, на которое отвечают. По умолчанию — сообщение бота (резюме карточки)."""

    def __init__(self, uname="turbobaby_manager_bot", is_bot=True, mid=4999, topic_created=None):
        self.from_user = U(uname, is_bot=is_bot) if uname is not None else None
        self.forum_topic_created = topic_created
        self.message_id = mid


class Sticker:
    def __init__(self, emoji=None):
        if emoji is not None:
            self.emoji = emoji


CARD_MID = 4100          # сообщение самой карточки на стенде (автор — человек); привязано в черновике reset()
SUMMARY_MID = 4999       # резюме бота «Ставлю бронь?» на стенде = id Reply() по умолчанию; привязано в reset()
NOREPLY = object()       # явное «без реплая»
ON_CARD = object()       # по умолчанию: реплай на ТЕКУЩУЮ карточку (так подтверждают с 16.10)


def _card_reply():
    d = S._INTAKE_DRAFTS.get(INTAKE) or {}
    ids = d.get("ic_msg_ids") or []
    return Reply("dasha_mgr", is_bot=False, mid=ids[0]) if ids else None


class Msg:
    def __init__(self, text, uname=APPROVER, photo=False, reply_to_bot=False, reply=ON_CARD, mid=4242, forward=None,
                 sticker=None):
        self.text = text
        self.caption = None
        self.photo = [object()] if photo else None
        self.chat_id = INTAKE
        self.message_thread_id = None
        self.message_id = mid
        self.media_group_id = None
        self.from_user = U(uname)
        if reply is NOREPLY:
            self.reply_to_message = None
        elif reply is not ON_CARD:
            self.reply_to_message = reply
        elif reply_to_bot:
            self.reply_to_message = Reply()
        else:
            self.reply_to_message = _card_reply()
        self.sticker = sticker
        if forward:
            setattr(self, forward, object())      # forward_origin (PTB ≥21) / forward_date / forward_from …


class Ctx:
    class _B:
        username = "turbobaby_manager_bot"
    bot = _B()


class FakeClaude:
    """Разбор карточки `🆕 БРОНЬ…` — синтетический ответ модели."""
    PARSED = '{"model": "CB 300CC R 9011", "client": "Мария Тест", "date_start": "15-11-2026", ' \
             '"date_end": "20-11-2026", "date_start_iso": null, "date_end_iso": null, ' \
             '"contacts": "+66 80 000 0000", "delivery_url": "https://maps.app.goo.gl/test", ' \
             '"helmets": 2, "deposit_type": "паспорт"}'

    def quick(self, system, text, max_tokens=300, **kw):
        return self.PARSED


class Boom(Exception):
    pass


_TICKET_OK = object()


class FakeBridge:
    """Мост-подделка. create_booking по умолчанию — {"ok": True, "row": 33, …}; `reply` подменяет ответ
    (словарь / None / исключение-экземпляр); `ticket` подменяет ответ issue_write_ticket. Пишет журнал вызовов."""

    def __init__(self, reply="ok", ticket_raises=None, ticket=_TICKET_OK):
        self.calls = []
        self.reply = reply
        self.ticket_raises = ticket_raises
        self.ticket = ticket

    def issue_write_ticket(self):
        self.calls.append(("issue_write_ticket", {}))
        if self.ticket_raises is not None:
            raise self.ticket_raises
        if self.ticket is not _TICKET_OK:
            return self.ticket
        return {"ok": True, "ticket": "t-test"}

    def create_booking(self, **k):
        self.calls.append(("create_booking", dict(k)))
        r = self.reply
        if r == "ok":
            return {"ok": True, "row": 33, "booking_id": "b-1", "bike": k.get("bike")}
        if isinstance(r, BaseException):
            raise r
        return r

    def booked(self):
        return [c for c in self.calls if c[0] == "create_booking"]


SENDS = []
SEND_IDS = {"on": False, "next": 9000}   # on → отправка возвращает сообщение с id (как PTB send_message)


async def rec_send(context, *, chat_id, text, message_thread_id=None, **k):
    SENDS.append((chat_id, text))
    if SEND_IDS["on"]:
        SEND_IDS["next"] += 1
        return types.SimpleNamespace(message_id=SEND_IDS["next"], text=text)
    return None


S._send = rec_send

FINALIZE_CALLS = []
_REAL_FINALIZE = S._intake_finalize


async def spy_finalize(draft, msg, context, bridge):
    FINALIZE_CALLS.append(draft.get("status"))
    return await _REAL_FINALIZE(draft, msg, context, bridge)


S._intake_finalize = spy_finalize

PASSPORT_SAVES = []


async def fake_ocr(photo_msg, chat_id, context, bridge):
    S._INTAKE_PASSPORT[chat_id] = {"file_id": "f-test", "ocr_status": "ok", "ts": time.time(),
                                   "fields": {"full_name": "MARIA TEST", "country": "TST", "expire_date": "2030-01-01"}}
    return (True, S._INTAKE_PASSPORT[chat_id]["fields"])


def fake_passport_save(chat_id, draft, bridge):
    PASSPORT_SAVES.append(draft.get("status"))


S._intake_passport_ocr = fake_ocr
S._intake_passport_save = fake_passport_save


class LogCap(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


LOGCAP = LogCap()
S.log.addHandler(LOGCAP)
S.log.setLevel(logging.INFO)


def draft(**kw):
    d = {"model": BIKE, "client": CLIENT, "date_start": "15-11-2026", "date_end": "20-11-2026",
         "date_start_iso": None, "date_end_iso": None, "contacts": "+66 80 000 0000",
         "delivery_url": "https://maps.app.goo.gl/test", "helmets": 2, "deposit_type": "паспорт",
         "passport_photo": True, "ts": time.time(), "status": "awaiting_approval",
         "ic_msg_ids": [CARD_MID, SUMMARY_MID]}
    d.update(kw)
    return d


def reset(**kw):
    del SENDS[:]
    del FINALIZE_CALLS[:]
    del PASSPORT_SAVES[:]
    del LOGCAP.records[:]
    SEND_IDS["on"] = False
    for dct in (S._INTAKE_DRAFTS, S._INTAKE_PASSPORT, S._HANDOVER_ACTIVATIONS, S._RETURN_CLOSES, S._RECENT_BOOKINGS,
                S._IC_PRE_PHOTOS):
        dct.clear()
    S._INTAKE_DRAFTS[INTAKE] = draft(**kw)


def say(bridge, text, **kw):
    asyncio.run(S._handle_intake(Msg(text, **kw), Ctx(), bridge, FakeClaude()))


def status():
    return S._INTAKE_DRAFTS[INTAKE]["status"]


def texts():
    return [t for c, t in SENDS if c == INTAKE]


# ------------------------------------------------------------------------------- таблица проекта §3
# (id, ввод, decide, вызовов create_booking, статус после, ответ (None = отправки нет), близнец, опции)
ROWS = [
    ("P1", "да", IC.YES, 1, "booked", T_BOOKED, None, {}),
    ("P2", "Да.", IC.YES, 1, "booked", T_BOOKED, None, {}),
    ("P3", "ок", IC.YES, 1, "booked", T_BOOKED, None, {}),
    ("P4", "ok", IC.YES, 1, "booked", T_BOOKED, None, {}),
    ("P4b", "OK", IC.YES, 1, "booked", T_BOOKED, None, {}),
    ("P5", "ставь", IC.YES, 1, "booked", T_BOOKED, None, {}),
    ("P6", "подтверждаю", IC.YES, 1, "booked", T_BOOKED, None, {}),
    ("P7a", "да 👍", IC.YES, 1, "booked", T_BOOKED, None, {}),
    ("P7b", "ДА!!!", IC.YES, 1, "booked", T_BOOKED, None, {}),
    ("P7c", "да, ставь", IC.YES, 1, "booked", T_BOOKED, None, {}),
    ("N1a", "👍", IC.ASK, 0, "awaiting_approval", T_ASK, "да 👍", {}),
    ("N1b", "✅", IC.ASK, 0, "awaiting_approval", T_ASK, "да 👍", {}),
    ("N1c", "👍🏻", IC.ASK, 0, "awaiting_approval", T_ASK, "да 👍", {}),
    ("N2", "не ставь", IC.NO, 0, "rejected", T_REJECT, "ставь", {}),
    ("N3", "не надо", IC.NO, 0, "rejected", T_REJECT, "да", {}),
    ("N4", "нет", IC.NO, 0, "rejected", T_REJECT, "да", {}),
    ("N5", "отмена", IC.NO, 0, "rejected", T_REJECT, "ок", {}),
    ("N6", "не подтверждаю", IC.NO, 0, "rejected", T_REJECT, "подтверждаю", {}),
    ("N7", "нет, когда оплатит", IC.NO, 0, "rejected", T_REJECT, "да", {}),
    ("N8", "всегда так", IC.SILENT, 0, "awaiting_approval", None, "да", {}),
    ("N9", "погода", IC.SILENT, 0, "awaiting_approval", None, "да", {}),
    ("N10", "около того", IC.SILENT, 0, "awaiting_approval", None, "ок", {}),
    ("N11", "да, но поправь дату", IC.EDIT, 0, "awaiting_approval", T_EDIT, "да", {}),
    ("N12", "ок, исправь имя", IC.EDIT, 0, "awaiting_approval", T_EDIT, "ок", {}),
    ("N13", None, IC.SILENT, 0, "awaiting_approval", None, "да", {}),
    ("N14", "😂", IC.SILENT, 0, "awaiting_approval", None, "да", {}),
    ("N15", "да", None, 0, "awaiting_approval", None, "да", {"uname": "pym_thai"}),
    ("N16a", "да?", IC.ASK, 0, "awaiting_approval", T_ASK, "да", {}),
    ("N16b", "ставим?", IC.ASK, 0, "awaiting_approval", T_ASK, "ставим", {}),
    ("N17a", "да, я позвоню клиенту", IC.ASK, 0, "awaiting_approval", T_ASK, "да", {}),
    ("N17b", "да нет", IC.ASK, 0, "awaiting_approval", T_ASK, "да", {}),
    ("N18", "погода", IC.SILENT, 0, "awaiting_approval", T_ASK, "да", {"reply_to_bot": True}),
    ("N19", "нет правок", IC.SILENT, 0, "awaiting_approval", None, "да", {}),
    ("N20", "нет, исправь дату", IC.EDIT, 0, "awaiting_approval", T_EDIT, "да", {}),
    # сверх таблицы: SILENT с тегом бота поднимается до ASK; тег + согласие — смешанный ответ (ASK)
    ("X1", "@turbobaby_manager_bot погода", IC.SILENT, 0, "awaiting_approval", T_ASK, "да", {}),
    ("X2", "оставь", IC.SILENT, 0, "awaiting_approval", None, "ставь", {}),
    ("X3", "не ок", IC.NO, 0, "rejected", T_REJECT, "ок", {}),
]

# Ловушки (б): 40+ фраз. YES обязан совпасть со свойством «слова есть, все из CONSENT_WORDS, нет «?»».
TRAPS = ["когда", "куда", "надо", "всегда", "погода", "около", "срок", "блок", "оставь", "давайте?", "подставь",
         "отставь", "не ставь", "не надо", "не подтверждаю", "не ок", "окно", "окончательно", "подтвердил", "ага",
         "бронируй", "да?", "ок?", "ставим?", "да, я позвоню клиенту", "да нет", "нет", "отмена", "отклоняю",
         "неа", "стоп", "нельзя", "ok?", "okay!", "yes please", "да 15", "да, ставь", "Да.", "ДА!!!", "окей 👍",
         "конечно", "давай", "поставлю", "подтверждаем", "дa", "ставь бронь", "погодите", "доставка", "отправка",
         "правки", "нет правок", "без правок", "не исправляй", "👍", "✅", "", "😂", "давайте", "Ok, ok",
         "ДаДа", "да-да", "да,да", "not ok", "no", "nope", "cancel", "stop", "ставлю 👌", "Ставим!", "ок ок ок",
         "конечно, давай", "да—ставь", "отменяй", "отклонено", "не сейчас", "не нужно", "не согласна",
         "без проблем", "поставим", "давай ставь", "погода ок", "докладываю", "подтверждаю?", "15 ноября"]


# Знаки рядом с согласием (находка I1): сомнение и отказ без слов YES не дают; спокойные знаки — дают.
SIGN_TRAPS = ["да 👎", "да ❌", "ок 🚫", "да 🤔", "да❓", "да？", "да⁉", "да ⁈", "да...", "да…", "да :(", "да)",
              "да :)", "«да»", "да ✔️", "👍🏽", "да 👍🏽", "ок ⛔", "да 🙅", "да ❎", "да ✖", "+", "++", "+1", "да +",
              "да 😂", "Да!", "ок, ок"]


def _tokens(t):
    return re.findall(r"[a-zа-я0-9]+", str(t or "").lower().replace("ё", "е"))


# =================================================================================================== (A)
class A_Decide(unittest.TestCase):
    def test_table_verdicts(self):
        for rid, text, want, *_ in ROWS:
            if want is None:
                continue
            with self.subTest(rid=rid, text=text):
                self.assertEqual(IC.decide(text), want)

    def test_extra_verdicts(self):
        # «отправка»: правка ищется НАЧАЛОМ слова, а не подстрокой — «от-правк-а» больше не правка (прочее → SILENT)
        # «не, ставь»: запятая рвёт смежность → «не» прочее + «ставь» согласие → ASK
        # «давайте?»: «давайте» — почти-согласие, вопрос → ASK (молчать на него нельзя)
        cases = {"не исправляй": IC.SILENT, "без правок": IC.SILENT, "правки": IC.EDIT, "отправка": IC.SILENT,
                 "давайте?": IC.ASK, "ok?": IC.ASK, "нет?": IC.ASK, "отклоняю": IC.NO, "stop": IC.NO,
                 "не сейчас": IC.NO, "не согласен": IC.NO, "да, ставь 👍": IC.YES, "ага": IC.ASK,
                 "бронируй": IC.ASK, "подтвердил": IC.ASK, "дa": IC.SILENT, "": IC.SILENT, "   ": IC.SILENT,
                 "👌": IC.ASK, "🆗": IC.ASK, "✔": IC.ASK, "☑": IC.ASK, "👍👍": IC.ASK, "да 15": IC.ASK,
                 "не, ставь": IC.ASK, "Ё-моё": IC.SILENT, "исправь": IC.EDIT, "поправь дату": IC.EDIT,
                 # правило (а) проекта: отрицание + существительное о правке — прочее (молчание, N19)
                 "нет правок, ставь": IC.ASK, "есть пара правок": IC.EDIT, "нет поправок": IC.SILENT,
                 "нет правки": IC.SILENT, "без исправлений": IC.SILENT,
                 # отрицание после слова о правке — сомнение, не отказ (И5/M1)
                 "правок нет": IC.ASK, "правки не нужны": IC.ASK, "исправлять не надо": IC.ASK,
                 "не надо править": IC.ASK, "править не надо": IC.ASK,
                 # «нет» + повелительное «исправь» — отказ + правка = правка (M2)
                 "нет исправь дату": IC.EDIT}
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(IC.decide(text), want)

    def test_not_str_input(self):
        self.assertEqual(IC.decide(None), IC.SILENT)
        self.assertEqual(IC.decide(15), IC.SILENT)

    def test_vocabulary_is_design_verbatim(self):
        self.assertEqual(IC.CONSENT_WORDS, frozenset({"да", "ок", "окей", "ok", "okay", "yes", "давай", "конечно",
                                                      "ставь", "поставь", "ставим", "поставим", "ставлю", "поставлю",
                                                      "подтверждаю", "подтверждаем"}))
        self.assertEqual(IC.REFUSE_WORDS, frozenset({"нет", "неа", "no", "nope", "нельзя", "стоп", "stop", "cancel"}))
        self.assertEqual(IC.REFUSE_STEMS, ("отмен", "отклон"))
        self.assertEqual(IC.NEG_REFUSE_NEXT, frozenset({"надо", "нужно", "сейчас", "согласен", "согласна", "согласны"}))
        self.assertEqual(IC.NEG_REFUSE_STEMS, ("став", "подтвер"))
        self.assertEqual(IC.EDIT_STEMS, ("правк", "исправ", "поправ"))
        self.assertEqual(IC.EDIT_NEGATORS, frozenset({"не", "нет", "без"}))
        # дополнения выпуска (не меняют словарей проекта): «правок» — основа «правк» его не покрывает
        self.assertFalse("правок".startswith(IC.EDIT_STEMS), "ради этого факта и заведено EDIT_EXTRA_STEMS")
        self.assertIn("правок", IC.EDIT_EXTRA_STEMS)
        self.assertFalse(IC.CONSENT_WORDS & IC.NEAR_CONSENT_WORDS, "почти-согласие не пересекается с согласием")
        self.assertFalse(IC.REFUSE_CHAIN_WORDS - IC.REFUSE_WORDS)
        self.assertEqual(IC.CONSENT_EMOJI, ("\U0001F44D", "\U0001F44C", "✅", "✔", "☑", "\U0001F197"))
        self.assertEqual((IC.YES, IC.NO, IC.EDIT, IC.ASK, IC.SILENT), ("yes", "no", "edit", "ask", "silent"))
        self.assertEqual((IC.BOOKED, IC.DUPLICATE, IC.NOT_WRITTEN, IC.UNKNOWN),
                         ("booked", "duplicate", "not_written", "unknown"))


# =================================================================================================== (B)
NOT_WRITTEN_CODES = ("bad_json", "no_ticket", "unknown_action", "missing_bike", "missing_name", "bike_not_resolved",
                     "bad_dates", "sheet_not_found", "booking_conflict")
W6_CODES = ("write_failed", "internal_error", "json_parse_error", "weird_code", "", None, "timeout", "request_failed",
            "card_deadline", "unauthorized")


class B_Outcome(unittest.TestCase):
    def test_set_is_design_verbatim(self):
        self.assertEqual(IC.NOT_WRITTEN_ERRORS, frozenset(NOT_WRITTEN_CODES))

    def test_booked_and_duplicate(self):
        self.assertEqual(IC.outcome({"ok": True, "row": 33}, True), IC.BOOKED)
        self.assertEqual(IC.outcome({"ok": False, "error": "duplicate", "row": 12}, True), IC.DUPLICATE)

    def test_not_sent_is_not_written_whatever_res(self):
        for res in (None, {"ok": True, "row": 1}, {"ok": False, "error": "timeout"}, "x"):
            with self.subTest(res=res):
                self.assertEqual(IC.outcome(res, False), IC.NOT_WRITTEN)

    def test_each_not_written_code(self):
        for code in NOT_WRITTEN_CODES:
            with self.subTest(code=code):
                self.assertEqual(IC.outcome({"ok": False, "error": code, "message": "m"}, True), IC.NOT_WRITTEN)

    def test_w6_and_client_codes_unknown(self):
        for code in W6_CODES:
            with self.subTest(code=code):
                self.assertEqual(IC.outcome({"ok": False, "error": code}, True), IC.UNKNOWN)
        self.assertEqual(IC.outcome({"ok": False}, True), IC.UNKNOWN)

    def test_receipt_unknown_outcome_beats_code(self):
        self.assertEqual(IC.outcome({"ok": False, "error": "receipt_unknown", "outcome": "unknown"}, True), IC.UNKNOWN)
        self.assertEqual(IC.outcome({"ok": False, "error": "no_ticket", "outcome": "unknown"}, True), IC.UNKNOWN)

    def test_not_a_dict_unknown(self):
        for res in (None, "ok", [], 0, ("ok",)):
            with self.subTest(res=res):
                self.assertEqual(IC.outcome(res, True), IC.UNKNOWN)


# =================================================================================================== (C)
class C_Integration(unittest.TestCase):
    def setUp(self):
        os.environ.pop("INTAKE_CONFIRM_STRICT", None)

    def _case(self, text, **opt):
        reset()
        b = FakeBridge()
        say(b, text, **opt)
        return b

    def test_default_knob_is_on(self):
        self.assertNotIn("INTAKE_CONFIRM_STRICT", os.environ)
        self.assertTrue(S._intake_confirm_strict_on())

    def test_knob_values(self):
        try:
            for val, on in (("1", True), (" 1 ", True), ("yes", True), ("0", False), ("", False), ("нет", False),
                            ("no", False), ("off", False), (" 0 ", False),
                            # M3: регистр не важен, «false» — тоже откат
                            ("NO", False), ("Off", False), ("НЕТ", False), ("false", False), ("FALSE", False)):
                os.environ["INTAKE_CONFIRM_STRICT"] = val
                with self.subTest(val=val):
                    self.assertEqual(S._intake_confirm_strict_on(), on)
        finally:
            os.environ.pop("INTAKE_CONFIRM_STRICT", None)

    def test_texts_are_module_constants(self):
        self.assertEqual(P + S._IC_ASK, T_ASK)
        self.assertEqual(P + S._IC_REJECT, T_REJECT)
        self.assertEqual(P + S._IC_PHOTO_UNKNOWN, T_PHOTO_UNKNOWN)
        self.assertEqual(P + S._IC_UNKNOWN.format(err="timeout"), t_unknown("timeout"))
        self.assertEqual(P + S._IC_NOT_WRITTEN.format(err="no_ticket", tail=" нет билета"),
                         t_not_written("no_ticket", "нет билета"))

    def test_table_with_twins(self):
        for rid, text, want, n_calls, st, reply, twin, opt in ROWS:
            with self.subTest(rid=rid, text=text):
                b = self._case(text, **opt)
                self.assertEqual(len(b.booked()), n_calls, b.calls)
                self.assertEqual(status(), st)
                self.assertEqual(texts(), [] if reply is None else [reply])
                if n_calls:
                    self.assertEqual(b.booked(), [("create_booking", FIELDS)])
                    self.assertEqual([c[0] for c in b.calls], ["issue_write_ticket", "create_booking"])
                    self.assertEqual(S._RECENT_BOOKINGS.get("9011", {}).get("booking_id"), "b-1")
                else:
                    self.assertEqual(b.calls, [], "отказ и сомнение мост не трогают вовсе")
            if twin is None:
                continue
            with self.subTest(rid=rid + " близнец", text=twin):
                topt = {k: v for k, v in opt.items() if k == "reply_to_bot"}
                b = self._case(twin, **topt)
                self.assertEqual(len(b.booked()), 1, "стенд умеет писать: близнец «%s»" % twin)
                self.assertEqual(status(), "booked")
                self.assertEqual(texts(), [T_BOOKED])

    def test_strict_knob_explicit_1(self):
        os.environ["INTAKE_CONFIRM_STRICT"] = "1"
        try:
            b = self._case("не ставь")
            self.assertEqual((len(b.booked()), status(), texts()), (0, "rejected", [T_REJECT]))
            b = self._case("да")
            self.assertEqual((len(b.booked()), status(), texts()), (1, "booked", [T_BOOKED]))
        finally:
            os.environ.pop("INTAKE_CONFIRM_STRICT", None)

    def test_reject_then_yes_does_nothing(self):
        reset()
        b = FakeBridge()
        say(b, "нет")
        say(b, "да")
        self.assertEqual((b.calls, status()), ([], "rejected"))
        self.assertEqual(texts(), [T_REJECT])

    # ---- исход записи (W) ---------------------------------------------------------------------------
    def _write(self, reply="ok", ticket_raises=None):
        reset()
        b = FakeBridge(reply=reply, ticket_raises=ticket_raises)
        say(b, "да")
        return b

    def _again_no_new(self, b, st):
        n = len(b.booked())
        say(b, "да")
        self.assertEqual(len(b.booked()), n, "повторное «да» не пишет: статус %s" % st)
        self.assertEqual(status(), st)

    def _twin_w1(self):
        b = self._write(reply="ok")
        self.assertEqual((len(b.booked()), status(), texts()), (1, "booked", [T_BOOKED]))

    def test_w1_booked(self):
        b = self._write(reply="ok")
        self.assertEqual((len(b.booked()), status(), texts()), (1, "booked", [T_BOOKED]))
        self._again_no_new(b, "booked")

    def test_w2_duplicate(self):
        b = self._write(reply={"ok": False, "error": "duplicate", "row": 12})
        self.assertEqual((len(b.booked()), status()), (1, "approved"))
        self.assertEqual(texts(), [P + "⚠️ Уже есть такая бронь (строка 12)."])
        self._again_no_new(b, "approved")
        self._twin_w1()

    def test_w3_w4_w5_client_unknown(self):
        for code, msg in (("timeout", "Timeout >60s"), ("request_failed", "HTTP 502"), ("card_deadline", "бюджет")):
            with self.subTest(code=code):
                b = self._write(reply={"ok": False, "error": code, "message": msg})
                self.assertEqual((len(b.booked()), status()), (1, "write_unknown"))
                self.assertEqual(texts(), [t_unknown(code)])
                self.assertFalse(any("Не записалось" in t or "Не записано" in t for t in texts()),
                                 "неизвестный исход не назван «не записано»")
                self._again_no_new(b, "write_unknown")
                self.assertEqual(len(texts()), 1, "на «да» после неизвестного исхода — молчание, не напоминание")
        self._twin_w1()

    def test_w6_unknown_codes(self):
        cases = [({"ok": False, "error": "receipt_unknown", "outcome": "unknown", "message": "расписка"},
                  "receipt_unknown"),
                 ({"ok": False, "error": "write_failed", "message": "setValue"}, "write_failed"),
                 ({"ok": False, "error": "internal_error"}, "internal_error"),
                 ({"ok": False, "error": "json_parse_error"}, "json_parse_error"),
                 ({"ok": False, "error": "weird_code"}, "weird_code"),
                 ({"ok": False, "error": ""}, "?"),
                 ({"ok": False}, "?")]
        for reply, err in cases:
            with self.subTest(err=err, reply=reply):
                b = self._write(reply=reply)
                self.assertEqual((len(b.booked()), status(), texts()), (1, "write_unknown", [t_unknown(err)]))
                self._again_no_new(b, "write_unknown")
        self._twin_w1()

    def test_w7_exception_after_send(self):
        b = self._write(reply=RuntimeError("обрыв"))
        self.assertEqual((len(b.booked()), status(), texts()), (1, "write_unknown", [t_unknown("RuntimeError")]))
        self._again_no_new(b, "write_unknown")
        self._twin_w1()

    def test_w8_none_reply(self):
        b = self._write(reply=None)
        self.assertEqual((len(b.booked()), status(), texts()), (1, "write_unknown", [t_unknown("нет ответа")]))
        self._again_no_new(b, "write_unknown")
        self._twin_w1()

    def test_w9_not_written_codes(self):
        for code in NOT_WRITTEN_CODES:
            with self.subTest(code=code):
                b = self._write(reply={"ok": False, "error": code, "message": "отказ моста"})
                self.assertEqual((len(b.booked()), status()), (1, "write_failed"))
                self.assertEqual(texts(), [t_not_written(code, "отказ моста")])
                self._again_no_new(b, "write_failed")
        b = self._write(reply={"ok": False, "error": "no_ticket"})
        self.assertEqual(texts(), [t_not_written("no_ticket")], "пустое сообщение моста — без хвоста")
        self._twin_w1()

    def test_w10_ticket_raises_before_send(self):
        b = self._write(ticket_raises=Boom("нет билета"))
        self.assertEqual(b.booked(), [], "create_booking не вызывался ни разу")
        self.assertEqual(status(), "write_failed")
        self.assertEqual(texts(), [t_not_written("exception", "до отправки: Boom: нет билета")])
        self.assertTrue(texts()[0].startswith(P + "❌ Не записано: exception. до отправки: "))
        self._again_no_new(b, "write_failed")
        self._twin_w1()

    def test_fields_raise_before_send(self):
        reset()
        S._INTAKE_DRAFTS[INTAKE]["deposit_type"] = "деньги"
        real = S._deposit_for_model

        def bad(model):
            raise ValueError("сломано")
        S._deposit_for_model = bad
        try:
            b = FakeBridge()
            say(b, "да")
        finally:
            S._deposit_for_model = real
        self.assertEqual((b.calls, status()), ([], "write_failed"))
        self.assertEqual(texts(), [t_not_written("exception", "до отправки: ValueError: сломано")])


# =================================================================================================== (D)
class D_Photo(unittest.TestCase):
    def setUp(self):
        os.environ.pop("INTAKE_CONFIRM_STRICT", None)

    def test_w11_photo_after_unknown_does_not_rearm(self):
        reset()
        b = FakeBridge(reply={"ok": False, "error": "timeout", "message": "Timeout >60s"})
        say(b, "да")
        self.assertEqual(status(), "write_unknown")
        say(b, None, photo=True)
        self.assertEqual(FINALIZE_CALLS, [], "_intake_finalize не вызван")
        self.assertEqual(status(), "write_unknown", "карточка не взведена")
        self.assertEqual(texts(), [t_unknown("timeout"), T_PHOTO_UNKNOWN])
        self.assertEqual(PASSPORT_SAVES, ["write_unknown"], "паспорт привязан и сохранён, как прежде")
        self.assertTrue(S._INTAKE_DRAFTS[INTAKE]["passport_photo"])
        say(b, "да")
        self.assertEqual(len(b.booked()), 1, "0 новых вызовов create_booking")
        self.assertEqual(status(), "write_unknown")

    def test_w11_twin_photo_to_fresh_card(self):
        reset(status="awaiting_approval")
        b = FakeBridge()
        say(b, None, photo=True)
        self.assertEqual(FINALIZE_CALLS, ["awaiting_approval"], "фото к свежей карточке — _intake_finalize вызван")
        self.assertEqual(status(), "awaiting_approval")
        self.assertEqual(texts(), [SUMMARY])
        say(b, "да")
        self.assertEqual((len(b.booked()), status()), (1, "booked"))

    def test_photo_other_statuses_unchanged(self):
        for st in ("booked", "rejected", "write_failed", "approved"):
            with self.subTest(status=st):
                reset(status=st)
                b = FakeBridge()
                say(b, None, photo=True)
                self.assertEqual(len(FINALIZE_CALLS), 1, "для прочих статусов фото взводит карточку, как прежде")
                self.assertEqual(status(), "awaiting_approval")

    def test_w12_new_card_after_unknown(self):
        reset()
        b = FakeBridge(reply={"ok": False, "error": "timeout", "message": "Timeout >60s"})
        say(b, "да")
        self.assertEqual(status(), "write_unknown")
        S._INTAKE_PASSPORT[INTAKE] = {"file_id": "f-test", "ocr_status": "ok", "ts": time.time(),
                                      "fields": {"full_name": "MARIA TEST", "country": "TST",
                                                 "expire_date": "2030-01-01"}}
        say(b, "🆕 БРОНЬ\nсинтетическая карточка")
        self.assertEqual(status(), "awaiting_approval")
        self.assertEqual(texts()[-1], SUMMARY)
        b.reply = "ok"
        say(b, "да")
        self.assertEqual(len(b.booked()), 2, "1 новый вызов — законный новый запрос человека")
        self.assertEqual(status(), "booked")
        self.assertEqual(texts()[-1], T_BOOKED)


# =================================================================================================== (E)
class E_Properties(unittest.TestCase):
    def setUp(self):
        os.environ.pop("INTAKE_CONFIRM_STRICT", None)

    def test_a_no_yes_no_write(self):
        inputs = [(r[1], r[7]) for r in ROWS if r[0] != "N15"] + [(t, {}) for t in TRAPS]
        self.assertGreaterEqual(len(inputs), 80)
        for text, opt in inputs:
            with self.subTest(text=text):
                reset()
                b = FakeBridge()
                say(b, text, **opt)
                want = 1 if IC.decide(text) == IC.YES else 0
                self.assertEqual(len(b.booked()), want)

    def test_b_yes_iff_all_consent_words(self):
        """(б) в редакции выпуска: YES ⇔ слова есть, ВСЕ из CONSENT_WORDS, вопроса нет (ни «?», ни «？❓⁉…»), а
        всё, что не слова, — пробелы и спокойные знаки, знаки согласия и их модификаторы (без «..»)."""
        self.assertGreaterEqual(len(TRAPS), 40)
        ok_chars = set(IC.YES_RESIDUE_OK) | set(IC.CONSENT_EMOJI) | set(IC._EMOJI_MODS)
        phrases = TRAPS + [r[1] for r in ROWS] + SIGN_TRAPS
        for t in phrases:
            with self.subTest(text=t):
                s = str(t or "").lower().replace("ё", "е")
                toks = _tokens(t)
                rest = re.sub(r"[a-zа-я0-9]+", "", s)
                prop = (bool(toks) and all(x in IC.CONSENT_WORDS for x in toks)
                        and not any(q in s for q in IC.QUESTION_MARKS)
                        and set(rest) <= ok_chars and ".." not in rest)
                self.assertEqual(IC.decide(t) == IC.YES, prop)
        for t in ("когда", "куда", "надо", "всегда", "погода", "около", "срок", "блок", "оставь", "давайте?",
                  "подставь", "отставь"):
            with self.subTest(trap=t):
                self.assertNotEqual(IC.decide(t), IC.YES)

    def test_c_message_text_not_in_log(self):
        secret_like = ["да, я позвоню клиенту", "нет, когда оплатит", "около того", "всегда так",
                       "да, но поправь дату", "ок, исправь имя", "не подтверждаю", "погода", "Мария звонила 0801"]
        for text in secret_like:
            with self.subTest(text=text):
                reset()
                b = FakeBridge()
                say(b, text)
                recs = list(LOGCAP.records)
                self.assertTrue(recs, "вердикт записан в журнал")
                for r in recs:
                    self.assertNotIn(text, r)
                    self.assertNotIn(text.lower(), r.lower())
                v = IC.decide(text)
                self.assertIn("  🆕 INTAKE: ответ на карточку → %s (@%s)" % (v, APPROVER), recs)
        reset()
        say(FakeBridge(reply={"ok": False, "error": "timeout", "message": "Timeout >60s"}), "да")
        self.assertIn("  🆕 INTAKE: исход записи брони НЕИЗВЕСТЕН (timeout: Timeout >60s) %s" % BIKE, LOGCAP.records)
        reset()
        say(FakeBridge(reply={"ok": False, "error": "no_ticket", "message": "нет"}), "да")
        self.assertIn("  🆕 INTAKE: бронь НЕ записана (no_ticket: нет) %s" % BIKE, LOGCAP.records)


# =================================================================================================== (F)
class F_Purity(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "intake_confirm.py"), encoding="utf-8") as fh:
            self.tree = ast.parse(fh.read())

    def test_imports_exactly_re(self):
        mods = set()
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Import):
                mods |= {a.name for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                mods.add(n.module or "")
        self.assertEqual(mods, {"re"})

    def test_no_forbidden_calls_or_os_sys(self):
        bad_calls = {n.func.id for n in ast.walk(self.tree)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)} & {"open", "exec", "eval",
                                                                                     "compile", "__import__"}
        self.assertEqual(bad_calls, set())
        names = {n.id for n in ast.walk(self.tree) if isinstance(n, ast.Name)}
        self.assertFalse(names & {"os", "sys", "open", "__import__"}, names & {"os", "sys"})
        attrs = {n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute)}
        self.assertFalse(attrs & {"environ", "getenv", "compile"}, attrs)

    def test_module_is_where_tests_look(self):
        self.assertEqual(os.path.normcase(os.path.dirname(os.path.abspath(IC.__file__))), os.path.normcase(ROOT))
        self.assertEqual(os.path.normcase(os.path.dirname(os.path.abspath(S.__file__))), os.path.normcase(ROOT))

    def test_splinter_strict_door_one_create_booking(self):
        with open(os.path.join(ROOT, "splinter.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        fns = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_intake_reply_strict"]
        self.assertEqual(len(fns), 1)
        calls = [n for n in ast.walk(fns[0]) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "create_booking"]
        self.assertEqual(len(calls), 1, "в строгой двери ровно одно место вызова create_booking")


# =================================================================================================== (G)
T_ASK_REPLY = P + ("❓ Это ответ на другое сообщение — бронь не ставлю. Поставить: «да» только ответом (реплаем) "
                   "на карточку брони.")
T_EDIT_PENDING = P + "✏️ По этой карточке просили правки — бронь не ставлю. Пришли исправленную карточку."
# Адресное уточнение привязки (G2): карточка названа моделью и датами, без имени и телефона клиента.
T_BIND = P + ("❓ Это подтверждение брони CB 300CC R 9011 (15-11-2026 — 20-11-2026)? Ответьте «да» реплаем на "
              "карточку — без реплая бронь не ставлю.")
CARD = "🆕 БРОНЬ\nсинтетическая карточка"


def _passport_ready():
    S._INTAKE_PASSPORT[INTAKE] = {"file_id": "f-test", "ocr_status": "ok", "ts": time.time(),
                                  "fields": {"full_name": "MARIA TEST", "country": "TST", "expire_date": "2030-01-01"}}


class G_CriticFixes(unittest.TestCase):
    """Находки критиков 16.10 (корректность I1/I2/M2–M4, живое поведение И3–И6). Каждый отрицательный случай — с
    близнецом, где запись проходит (стенд умеет писать)."""

    def setUp(self):
        os.environ.pop("INTAKE_CONFIRM_STRICT", None)

    def _one(self, text, **opt):
        reset()
        b = FakeBridge()
        say(b, text, **opt)
        return b

    def _assert_booked(self, b, ctx):
        self.assertEqual(len(b.booked()), 1, ctx)
        self.assertEqual(status(), "booked", ctx)
        self.assertEqual(texts()[-1], T_BOOKED, ctx)

    def _assert_not_written(self, b, st, sends, ctx):
        self.assertEqual(b.calls, [], ctx + ": мост не тронут")
        self.assertEqual(status(), st, ctx)
        self.assertEqual(texts(), sends, ctx)

    # ---- I1: знаки сомнения и отказа рядом с согласием ------------------------------------------------
    def test_i1_doubt_signs_next_to_consent_ask(self):
        self._assert_booked(self._one("да"), "близнец «да»")
        for t in ("да 👎", "да ❌", "ок 🚫", "да 🤔", "да❓", "да？", "да⁉", "да...", "да…", "да :(", "да 🙅"):
            with self.subTest(text=t):
                self._assert_not_written(self._one(t), "awaiting_approval", [T_ASK], t)
        for t in ("👎", "❌", "🤔"):
            with self.subTest(text=t):
                self._assert_not_written(self._one(t), "awaiting_approval", [T_ASK], t)
        for t in ("да)", "да :)", "«да»", "да ✔️", "да 👍🏽"):
            with self.subTest(calm=t):
                self._assert_booked(self._one(t), t)

    # ---- I2: ответ, адресованный не карточке -----------------------------------------------------------
    def test_i2_reply_to_other_human_asks(self):
        self._assert_booked(self._one("да", reply_to_bot=True), "близнец: реплай на резюме бота")
        other = Reply("dasha_mgr", is_bot=False, mid=5001)
        # G2 (привязка, 16.10): согласие реплаем на чужое сообщение — адресное уточнение _IC_ASK_BIND (прежний
        # _IC_ASK_REPLY звал «да» «отдельным сообщением», а без реплая согласие больше не засчитывается);
        # отказ и правка — _IC_ASK_REPLY, как прежде
        for t, want in (("да", T_BIND), ("ок", T_BIND), ("нет", T_ASK_REPLY), ("не ставь", T_ASK_REPLY),
                        ("правки", T_ASK_REPLY)):
            with self.subTest(text=t):
                self._assert_not_written(self._one(t, reply=other), "awaiting_approval", [want], t)
        self._assert_not_written(self._one("погода", reply=other), "awaiting_approval", [], "болтовня реплаем")
        self._assert_not_written(self._one("да", reply=Reply(None, mid=5002)), "awaiting_approval", [T_BIND],
                                 "реплай на сообщение без автора (канал)")
        # служебное «тема создана» реплаем не считается: для отказа это прежний отказ, для согласия — «да» без реплая
        topic = Reply("dasha_mgr", is_bot=False, mid=1, topic_created=object())
        self._assert_not_written(self._one("нет", reply=topic), "rejected", [T_REJECT], "«нет» в теме форума")
        self._assert_not_written(self._one("да", reply=topic), "awaiting_approval", [T_BIND],
                                 "«да» в теме форума без реплая на карточку")
        self.assertIn("  🆕 INTAKE: ответ на карточку → ask (@%s) — согласие без реплая на карточку" % APPROVER,
                      LOGCAP.records)
        self._one("да", reply=other)
        self.assertIn("  🆕 INTAKE: ответ на карточку → ask (@%s) — ответ на другое сообщение" % APPROVER,
                      LOGCAP.records)

    def test_i2_reply_to_card_and_its_photo_books(self):
        # сама карточка
        reset()
        S._INTAKE_DRAFTS.clear()
        _passport_ready()
        b = FakeBridge()
        say(b, CARD, mid=777)
        self.assertEqual(status(), "awaiting_approval")
        self.assertEqual(S._INTAKE_DRAFTS[INTAKE]["ic_msg_ids"], [777])
        say(b, "да", reply=Reply("dasha_mgr", is_bot=False, mid=777))
        self._assert_booked(b, "реплай на карточку")
        # фото паспорта после карточки
        reset()
        S._INTAKE_DRAFTS.clear()
        b = FakeBridge()
        say(b, CARD, mid=777)
        say(b, None, photo=True, mid=778)
        self.assertEqual(S._INTAKE_DRAFTS[INTAKE]["ic_msg_ids"], [777, 778])
        say(b, "да", reply=Reply("dasha_mgr", is_bot=False, mid=778))
        self._assert_booked(b, "реплай на фото паспорта")
        # фото паспорта ДО карточки
        reset()
        S._INTAKE_DRAFTS.clear()
        b = FakeBridge()
        say(b, None, photo=True, mid=770)
        self.assertIn(INTAKE, S._IC_PRE_PHOTOS)
        say(b, CARD, mid=777)
        self.assertEqual(S._INTAKE_DRAFTS[INTAKE]["ic_msg_ids"], [777, 770])
        self.assertNotIn(INTAKE, S._IC_PRE_PHOTOS, "буфер фото до карточки забран карточкой")
        say(b, "да", reply=Reply("dasha_mgr", is_bot=False, mid=770))
        self._assert_booked(b, "реплай на фото до карточки")
        # близнец-отрицание: реплай на постороннее сообщение той же беседы
        reset()
        S._INTAKE_DRAFTS.clear()
        _passport_ready()
        b = FakeBridge()
        say(b, CARD, mid=777)
        self.assertEqual(status(), "awaiting_approval")
        n = len(texts())
        say(b, "да", reply=Reply("dasha_mgr", is_bot=False, mid=779))
        self.assertEqual((b.booked(), status(), texts()[n:]), ([], "awaiting_approval", [T_BIND]))

    def test_i2_forwarded_is_silent(self):
        self._assert_booked(self._one("Да"), "близнец без пересылки")
        for attr in ("forward_origin", "forward_date", "forward_from", "forward_from_chat", "forward_sender_name"):
            for t in ("Да", "нет", "правки"):
                with self.subTest(attr=attr, text=t):
                    self._assert_not_written(self._one(t, forward=attr), "awaiting_approval", [], t)
        self._one("Да", forward="forward_origin")
        self.assertIn("  🆕 INTAKE: ответ на карточку → silent (@%s) — переслано, не ответ подтверждающего"
                      % APPROVER, LOGCAP.records)

    # ---- И3: тег своего бота -----------------------------------------------------------------------------
    def test_i3_own_bot_tag_is_stripped(self):
        for t in ("@turbobaby_manager_bot да", "да @TurboBaby_Manager_Bot", "@turbobaby_manager_bot, ок"):
            with self.subTest(text=t):
                self._assert_booked(self._one(t), t)
        for t in ("@turbobaby_manager_bot", "погода @turbobaby_manager_bot", "@turbobaby_manager_botx да", "@pym да"):
            with self.subTest(text=t):
                self._assert_not_written(self._one(t), "awaiting_approval", [T_ASK], t)

    # ---- И4: почти-согласие и стикер ----------------------------------------------------------------------
    def test_i4_near_consent_asks(self):
        self._assert_booked(self._one("да"), "близнец «да»")
        for t in ("подтверждено", "подтверждена", "дааа", "даа", "окк", "+", "++", "+1", "хорошо", "ага", "угу",
                  "принято", "согласен", "верно", "ладно", "норм", "yep", "sure", "без проблем", "нет проблем",
                  "давайте"):
            with self.subTest(text=t):
                self._assert_not_written(self._one(t), "awaiting_approval", [T_ASK], t)

    def test_i4_sticker_judged_by_its_emoji(self):
        self._assert_not_written(self._one(None, sticker=Sticker("👍")), "awaiting_approval", [T_ASK], "стикер 👍")
        self._assert_not_written(self._one(None, sticker=Sticker("👎")), "awaiting_approval", [T_ASK], "стикер 👎")
        self._assert_not_written(self._one(None, sticker=Sticker("😂")), "awaiting_approval", [], "стикер 😂")
        self._assert_not_written(self._one(None, sticker=Sticker()), "awaiting_approval", [], "стикер без эмодзи")

    # ---- И5/M1: ложный отказ ------------------------------------------------------------------------------
    def test_i5_idioms_do_not_reject(self):
        for t in ("правок нет", "нет проблем", "нет возражений", "нет вопросов", "не надо править", "править не надо",
                  "правки не нужны", "исправлять не надо", "отмена не нужна", "сейчас нет", "не ставь бронь"):
            with self.subTest(text=t):
                reset()
                b = FakeBridge()
                say(b, t)
                self._assert_not_written(b, "awaiting_approval", [T_ASK], t)
                say(b, "да")
                self.assertEqual((len(b.booked()), status()), (1, "booked"), "карточка жива: «да» после «%s»" % t)
        self._assert_not_written(self._one("нет правок"), "awaiting_approval", [], "N19 проекта: молчание")
        for t in ("нет", "не ставь", "нет, когда оплатит", "Не, не надо", "нет нет", "нет не ставь", "Нет.",
                  "нет — клиент передумал", "отменяй"):
            with self.subTest(clear=t):
                self._assert_not_written(self._one(t), "rejected", [T_REJECT], t)

    def test_m2_net_plus_imperative_is_edit(self):
        self._assert_not_written(self._one("нет исправь дату"), "awaiting_approval", [T_EDIT], "M2")

    # ---- И6: «да» после просьбы о правках -----------------------------------------------------------------
    def test_i6_yes_after_edit_request_does_not_book_old_card(self):
        reset()
        b = FakeBridge()
        say(b, "да, но поправь дату")
        say(b, "да")
        self.assertEqual((b.calls, status()), ([], "awaiting_approval"), "старая карточка «да» не ставится")
        self.assertEqual(texts(), [T_EDIT, T_EDIT_PENDING])
        self.assertIn("  🆕 INTAKE: ответ на карточку → ask (@%s) — по карточке просили правки" % APPROVER,
                      LOGCAP.records)
        say(b, "нет")
        self.assertEqual((b.calls, status(), texts()[-1]), ([], "rejected", T_REJECT), "отказ по-прежнему работает")
        # законный путь — исправленная карточка: новый черновик без пометки, «да» пишет
        reset()
        b = FakeBridge()
        say(b, "исправь имя")
        _passport_ready()
        say(b, CARD, mid=780)
        self.assertNotIn("ic_edit_asked", S._INTAKE_DRAFTS[INTAKE])
        say(b, "да")
        self._assert_booked(b, "исправленная карточка")

    # ---- M3: ручка без учёта регистра -------------------------------------------------------------------
    def test_m3_knob_case_insensitive_rolls_back(self):
        try:
            for val in ("NO", "Off", "FALSE", "НЕТ", "false"):
                with self.subTest(knob=val):
                    os.environ["INTAKE_CONFIRM_STRICT"] = val
                    b = self._one("не ставь")
                    self.assertEqual((len(b.booked()), status()), (1, "booked"),
                                     "откат = прежнее поведение (ДЕФЕКТ Д1 при ручке выкл)")
        finally:
            os.environ.pop("INTAKE_CONFIRM_STRICT", None)

    def test_m3_knob_off_no_new_state(self):
        """Откат не заводит новых полей и буферов (байт-в-байт и по состоянию)."""
        os.environ["INTAKE_CONFIRM_STRICT"] = "0"
        try:
            reset()
            S._INTAKE_DRAFTS.clear()
            b = FakeBridge()
            say(b, None, photo=True, mid=770)
            say(b, CARD, mid=777)
            say(b, "правки")
            d = S._INTAKE_DRAFTS[INTAKE]
            self.assertFalse({"ic_msg_ids", "ic_edit_asked"} & set(d), sorted(d))
            self.assertEqual(S._IC_PRE_PHOTOS, {})
        finally:
            os.environ.pop("INTAKE_CONFIRM_STRICT", None)

    # ---- M4: без билета запись не уходит ------------------------------------------------------------------
    def test_m4_no_ticket_no_send(self):
        self._assert_booked(self._one("да"), "близнец: билет выдан")
        for tk, tail in (({"ok": False, "error": "quota"}, " (quota)"), ({}, ""), (None, ""), ({"ok": True}, ""),
                         ({"ok": True, "ticket": ""}, "")):
            with self.subTest(ticket=tk):
                reset()
                b = FakeBridge(ticket=tk)
                say(b, "да")
                self.assertEqual(b.calls, [("issue_write_ticket", {})], "create_booking без билета не зовётся")
                self.assertEqual(status(), "write_failed")
                self.assertEqual(texts(), [t_not_written("no_ticket", "до отправки: билет не выдан" + tail)])
                say(b, "да")
                self.assertEqual(len(b.calls), 1, "повторное «да» — ни билета, ни записи")


# =================================================================================================== (G2)
class FakeClaudeOther(FakeClaude):
    """Вторая (другая) карточка: иная модель и даты — чтобы уточнение называло именно АКТУАЛЬНУЮ карточку."""
    PARSED = '{"model": "NMAX 155 GREY 5960", "client": "Иван Тест", "date_start": "01-12-2026", ' \
             '"date_end": "03-12-2026", "date_start_iso": null, "date_end_iso": null, ' \
             '"contacts": "+66 80 000 0001", "delivery_url": "https://maps.app.goo.gl/test2", ' \
             '"helmets": 1, "deposit_type": "паспорт"}'


T_BIND_OTHER = P + ("❓ Это подтверждение брони NMAX 155 GREY 5960 (01-12-2026 — 03-12-2026)? Ответьте «да» реплаем "
                    "на карточку — без реплая бронь не ставлю.")
CARD_B = "🆕 БРОНЬ\nвторая синтетическая карточка"
CONSENT_ONLY = ["да", "Да.", "ок", "ok", "OK", "ставь", "подтверждаю", "да 👍", "ДА!!!", "да, ставь", "конечно",
                "поставим", "@turbobaby_manager_bot да"]


class _RaisingReply:
    """Реплай на бота, у которого чтение id падает: сомнение → «не эта карточка»."""
    forum_topic_created = None

    def __init__(self):
        self.from_user = U("turbobaby_manager_bot", is_bot=True)

    @property
    def message_id(self):
        raise RuntimeError("id не читается")


class G2_CardBinding(unittest.TestCase):
    """Замечание Codex TB-OWNER-CHECK-1610-0307 (принято К3): в строгом режиме «да» без реплая и «да» реплаем на ЛЮБОЕ
    сообщение бота доходили до create_booking. Теперь согласие засчитывается только реплаем на сообщение ЭТОЙ
    карточки; иначе — адресное уточнение без записи. Отказ, правка, сомнение, молчание — как прежде. У каждого
    отрицательного случая близнец, где запись проходит."""

    def setUp(self):
        os.environ.pop("INTAKE_CONFIRM_STRICT", None)

    def tearDown(self):
        SEND_IDS["on"] = False
        os.environ.pop("INTAKE_CONFIRM_STRICT", None)

    # ---- помощники ------------------------------------------------------------------------------------------
    def _one(self, text, **opt):
        reset()
        b = FakeBridge()
        say(b, text, **opt)
        return b

    def _assert_booked(self, b, ctx, n=1):
        self.assertEqual(len(b.booked()), n, ctx)
        self.assertEqual(status(), "booked", ctx)
        self.assertEqual(texts()[-1], T_BOOKED, ctx)

    def _assert_bind(self, b, ctx, want=T_BIND, st="awaiting_approval"):
        self.assertEqual(b.calls, [], ctx + ": мост не тронут (ни билета, ни записи)")
        self.assertEqual(status(), st, ctx)
        self.assertEqual(texts()[-1:], [want], ctx)

    def _live_card(self, b, mid=777, claude=None, text=CARD, ids=True, fresh=True):
        """Живой путь: карточка → разбор → резюме бота. ids → отправка возвращает сообщение с id (как PTB)."""
        if fresh:
            reset()
            S._INTAKE_DRAFTS.clear()
            _passport_ready()
        SEND_IDS["on"] = ids
        asyncio.run(S._handle_intake(Msg(text, mid=mid, reply=NOREPLY), Ctx(), b, claude or FakeClaude()))
        self.assertEqual(status(), "awaiting_approval")
        return S._INTAKE_DRAFTS[INTAKE]

    # ---- G2.1 «да» без реплая — уточнение, без записи ------------------------------------------------------
    def test_g1_yes_without_reply_asks_bind(self):
        self._assert_booked(self._one("да"), "близнец: «да» реплаем на карточку")
        for t in CONSENT_ONLY:
            with self.subTest(text=t):
                self.assertEqual(IC.decide(S._ic_strip_bot(t, Ctx())), IC.YES, "вход — настоящее согласие")
                b = self._one(t, reply=NOREPLY)
                self._assert_bind(b, t)
                self.assertEqual(texts(), [T_BIND], "одно сообщение — адресное уточнение")
        b = self._one("да", reply=NOREPLY)
        self.assertIn("  🆕 INTAKE: ответ на карточку → ask (@%s) — согласие без реплая на карточку" % APPROVER,
                      LOGCAP.records)
        say(b, "да", reply=NOREPLY)
        self.assertEqual((b.calls, status(), texts()), ([], "awaiting_approval", [T_BIND, T_BIND]),
                         "повторное «да» без реплая — снова уточнение, записи нет")

    def test_g1_bind_text_names_card_without_pii(self):
        self._one("да", reply=NOREPLY)
        t = texts()[0]
        self.assertEqual(t, P + S._IC_ASK_BIND.format(card=S._ic_card_name(S._INTAKE_DRAFTS[INTAKE])))
        self.assertIn(BIKE, t)
        self.assertIn("15-11-2026", t)
        self.assertIn("20-11-2026", t)
        for pii in (CLIENT, "Мария", "+66 80 000 0000", "80 000"):
            self.assertNotIn(pii, t, "в уточнении нет имени и телефона клиента")
        self.assertEqual(S._ic_card_name({}), "—")
        self.assertEqual(S._ic_card_name({"model": BIKE}), BIKE)
        self.assertEqual(S._ic_card_name({"model": BIKE, "date_start": "15-11-2026"}), BIKE + " (15-11-2026)")
        self.assertEqual(S._ic_card_name({"model": " ", "date_end": "20-11-2026"}), "— (20-11-2026)")

    # ---- G2.2 резюме «Ставлю бронь?» — сообщение карточки: id запоминается в месте отправки ------------------
    def test_g2_reply_to_summary_books_live_path(self):
        b = FakeBridge()
        d = self._live_card(b, mid=777)
        summary_mid = SEND_IDS["next"]
        self.assertEqual(texts(), [SUMMARY], "одно резюме карточки")
        self.assertEqual(d["ic_msg_ids"], [777, summary_mid], "резюме бота привязано к карточке")
        say(b, "да", reply=Reply(mid=summary_mid))
        self._assert_booked(b, "реплай «да» на резюме «Ставлю бронь?»")
        # отрицательный близнец: тот же живой путь, реплай на сообщение бота НЕ этой карточки
        b = FakeBridge()
        self._live_card(b, mid=777)
        n = len(texts())
        say(b, "да", reply=Reply(mid=SEND_IDS["next"] + 500))
        self._assert_bind(b, "реплай на постороннее сообщение бота")
        self.assertEqual(len(texts()), n + 1)

    def test_g2_summary_without_id_is_not_binding(self):
        b = FakeBridge()
        d = self._live_card(b, mid=777, ids=False)
        self.assertEqual(d["ic_msg_ids"], [777], "id резюме не получен — привязкой не считается")
        say(b, "да", reply=Reply())                      # реплай на резюме бота, id которого неизвестен
        self._assert_bind(b, "реплай на резюме с неизвестным id")
        say(b, "да", reply=Reply("dasha_mgr", is_bot=False, mid=777))
        self._assert_booked(b, "близнец: реплай на саму карточку")

    def test_g2_photo_rearm_summary_also_binds(self):
        b = FakeBridge()
        d = self._live_card(b, mid=777)
        s1 = SEND_IDS["next"]
        say(b, None, photo=True, mid=778)               # фото паспорта к свежей карточке → резюме заново
        s2 = SEND_IDS["next"]
        self.assertEqual(d["ic_msg_ids"], [777, s1, 778, s2])
        say(b, "да", reply=Reply(mid=s1))
        self._assert_booked(b, "реплай на первое резюме той же карточки")

    # ---- G2.3 реплай на сообщение бота, НЕ входящее в ic_msg_ids ------------------------------------------
    def test_g3_reply_to_foreign_bot_message_asks_bind(self):
        self._assert_booked(self._one("да", reply_to_bot=True), "близнец: реплай на привязанное резюме")
        cases = (("своё старое сообщение бота", Reply(mid=6001)),
                 ("другой бот", Reply("other_helper_bot", is_bot=True, mid=6002)),
                 ("бот, id не читается", _RaisingReply()),
                 ("бот без id", Reply(mid=None)))
        for ctx, r in cases:
            with self.subTest(case=ctx):
                b = self._one("да", reply=r)
                self._assert_bind(b, ctx)
                self.assertNotIn(T_ASK_REPLY, texts(), "не _IC_ASK_REPLY")
        self._one("ок", reply=Reply(mid=6001))
        self.assertIn("  🆕 INTAKE: ответ на карточку → ask (@%s) — согласие реплаем не на эту карточку" % APPROVER,
                      LOGCAP.records)

    # ---- G2.4 сменилась карточка: реплай на сообщения прежней не засчитан --------------------------------------
    def test_g4_card_changed_old_messages_do_not_bind(self):
        b = FakeBridge()
        da = self._live_card(b, mid=777)
        sum_a = SEND_IDS["next"]
        say(b, None, photo=True, mid=778)
        say(b, "да", reply=NOREPLY)                      # уточнение по карточке A — тоже её сообщение
        bind_a = SEND_IDS["next"]
        self.assertIn(bind_a, da["ic_msg_ids"])
        db = self._live_card(b, mid=888, claude=FakeClaudeOther(), text=CARD_B, fresh=False)
        sum_b = SEND_IDS["next"]
        self.assertIsNot(da, db)
        self.assertEqual(db["ic_msg_ids"], [888, sum_b], "у новой карточки — только свои сообщения")
        old = (("карточка A", Reply("dasha_mgr", is_bot=False, mid=777)),
               ("фото паспорта A", Reply("dasha_mgr", is_bot=False, mid=778)),
               ("резюме A", Reply(mid=sum_a)),
               ("уточнение по A", Reply(mid=bind_a)))
        for ctx, r in old:
            with self.subTest(old=ctx):
                n = len(texts())
                say(b, "да", reply=r)
                self.assertEqual(b.booked(), [], ctx + ": реплай на прежнюю карточку не пишет")
                self.assertEqual(status(), "awaiting_approval", ctx)
                self.assertEqual(texts()[n:], [T_BIND_OTHER], ctx + ": уточнение называет АКТУАЛЬНУЮ карточку")
        say(b, "да", reply=Reply("dasha_mgr", is_bot=False, mid=888))
        self.assertEqual([c[1]["bike"] for c in b.booked()], ["NMAX 155 GREY 5960"], "близнец: пишется карточка B")
        self.assertEqual((status(), texts()[-1]), ("booked", T_BOOKED))

    # ---- G2.5 реплай «да» на само уточнение — согласие на названную карточку -----------------------------------
    def test_g5_reply_to_bind_question_books(self):
        b = FakeBridge()
        d = self._live_card(b, mid=777)
        say(b, "да", reply=NOREPLY)
        self._assert_bind(b, "без реплая")
        bind_mid = SEND_IDS["next"]
        self.assertIn(bind_mid, d["ic_msg_ids"], "уточнение называет карточку — его id запомнен")
        say(b, "да", reply=Reply(mid=bind_mid))
        self._assert_booked(b, "реплай на уточнение")

    def test_g5_only_bind_question_is_noted_not_other_asks(self):
        b = FakeBridge()
        d = self._live_card(b, mid=777)
        before = list(d["ic_msg_ids"])
        for t in ("да?", "👍", "погода @turbobaby_manager_bot"):       # _IC_ASK — карточку не называет
            say(b, t, reply=NOREPLY)
        say(b, "нет", reply=Reply("dasha_mgr", is_bot=False, mid=5001))  # _IC_ASK_REPLY
        self.assertEqual(texts()[-4:], [T_ASK, T_ASK, T_ASK, T_ASK_REPLY])
        self.assertEqual(d["ic_msg_ids"], before, "переспросы, не называющие карточку, привязкой не становятся")
        say(b, "да", reply=Reply(mid=SEND_IDS["next"]))                   # реплай на _IC_ASK_REPLY
        self._assert_bind(b, "реплай «да» на неадресный переспрос")

    # ---- G2.6 отказ, правка, сомнение, молчание — как прежде (без реплая = реплаем на карточку) ------------------
    def test_g6_non_yes_unchanged_without_reply(self):
        for rid, text, want, n_calls, st, reply, _twin, opt in ROWS:
            if want in (None, IC.YES) or opt:
                continue
            with self.subTest(rid=rid, text=text):
                got = []
                for r in (ON_CARD, NOREPLY):
                    b = self._one(text, reply=r)
                    got.append((b.calls, status(), texts()))
                self.assertEqual(got[0], got[1], "без реплая — то же, что реплаем на карточку")
                self.assertEqual(got[1], ([], st, [] if reply is None else [reply]))

    def test_g6_no_and_edit_replies_as_before(self):
        other_human = Reply("dasha_mgr", is_bot=False, mid=5001)
        other_bot = Reply(mid=6001)
        self._assert_bind(self._one("нет", reply=other_human), "«нет» реплаем на чужое", want=T_ASK_REPLY)
        self._assert_bind(self._one("правки", reply=other_human), "«правки» реплаем на чужое", want=T_ASK_REPLY)
        self._assert_bind(self._one("нет", reply=other_bot), "«нет» реплаем на бота (как прежде — отказ)",
                          want=T_REJECT, st="rejected")
        self._assert_bind(self._one("правки", reply=other_bot), "«правки» реплаем на бота", want=T_EDIT)
        self._assert_bind(self._one("нет", reply=NOREPLY), "«нет» без реплая", want=T_REJECT, st="rejected")

    def test_g6_edit_pending_still_first(self):
        reset()
        b = FakeBridge()
        say(b, "правки", reply=NOREPLY)
        say(b, "да", reply=NOREPLY)
        self.assertEqual((b.calls, status(), texts()), ([], "awaiting_approval", [T_EDIT, T_EDIT_PENDING]))

    # ---- G2.7 свойство: без привязанного реплая create_booking не зовётся НИКОГДА ----------------------------
    def test_g7_property_no_bound_reply_no_write(self):
        replies = (("без реплая", NOREPLY), ("чужой человек", Reply("dasha_mgr", is_bot=False, mid=5001)),
                   ("свой бот, старое", Reply(mid=6001)), ("другой бот", Reply("x_bot", is_bot=True, mid=6002)),
                   ("тема форума", Reply("dasha_mgr", is_bot=False, mid=1, topic_created=object())),
                   ("id не читается", _RaisingReply()))
        inputs = CONSENT_ONLY + TRAPS + [r[1] for r in ROWS]
        self.assertGreaterEqual(len(inputs), 100)
        n_yes = 0
        for ctx, r in replies:
            for t in inputs:
                with self.subTest(reply=ctx, text=t):
                    b = self._one(t, reply=r)
                    self.assertEqual(b.booked(), [], "%s %r: create_booking без привязки" % (ctx, t))
                    self.assertNotIn(status(), ("approved", "booked", "write_unknown", "write_failed"))
                    n_yes += IC.decide(S._ic_strip_bot(t, Ctx())) == IC.YES
        self.assertGreater(n_yes, 50, "среди входов много настоящих согласий — свойство не пустое")
        # близнец свойства: с привязанным реплаем каждое согласие пишет ровно один раз
        for t in CONSENT_ONLY:
            with self.subTest(bound=t):
                self._assert_booked(self._one(t), t)

    # ---- G2.8 разбор реплая (`_ic_reply_binding`) ----------------------------------------------------------
    def test_g8_binding_unit(self):
        d = {"ic_msg_ids": [777, 9001]}
        m = Msg("да", reply=NOREPLY)
        self.assertEqual(S._ic_reply_binding(m, d), "none")
        for r, want in ((Reply("h", is_bot=False, mid=777), "card"), (Reply(mid=9001), "card"),
                        (Reply(mid=9002), "other"), (Reply("h", is_bot=False, mid=1, topic_created=object()), "none"),
                        (Reply(mid=None), "other"), (_RaisingReply(), "other")):
            with self.subTest(mid=getattr(r, "__dict__", {}).get("message_id")):
                self.assertEqual(S._ic_reply_binding(Msg("да", reply=r), d), want)
        self.assertEqual(S._ic_reply_binding(Msg("да", reply=Reply(mid=777)), {}), "other", "черновик без id")
        self.assertEqual(S._ic_reply_binding(Msg("да", reply=Reply(mid=777)), {"ic_msg_ids": None}), "other")

    # ---- G2.9 откат: ручка 0 — прежнее, id резюме не копятся ------------------------------------------------
    def test_g9_knob_off_unchanged(self):
        os.environ["INTAKE_CONFIRM_STRICT"] = "0"
        try:
            b = FakeBridge()
            reset()
            S._INTAKE_DRAFTS.clear()
            _passport_ready()
            SEND_IDS["on"] = True
            asyncio.run(S._handle_intake(Msg(CARD, mid=777, reply=NOREPLY), Ctx(), b, FakeClaude()))
            self.assertNotIn("ic_msg_ids", S._INTAKE_DRAFTS[INTAKE], "при откате id не копятся")
            say(b, "да", reply=NOREPLY)
            self.assertEqual((len(b.booked()), status()), (1, "booked"), "ручка 0: «да» без реплая — прежняя запись")
        finally:
            os.environ.pop("INTAKE_CONFIRM_STRICT", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
