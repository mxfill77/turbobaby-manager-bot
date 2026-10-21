# -*- coding: utf-8 -*-
"""AUTOBOOK2210 (22.10.2026): автобронь во «Входящих» — ручка INTAKE_AUTOBOOK поверх INTAKE_PASSPORT_STRICT.

Слово владельца 22.10: «агент будет и должен это делать его обязанности ставить брони самостоятельно»; условие —
паспорт этого клиента распознан и ФИО совпало, байк свободен на даты по двери цены, стоимость согласована; «высокий
сезон … нужна предоплата», «на месяцы с 15 декабря … 100% предоплата» — первый срез такие брони сам не ставит.

Стенд test_intake_confirm (мост, отправка, OCR — подделки; личности синтетические; сети, CRM и модели нет). Даты —
май следующего года (низкий сезон, всегда в будущем); высокий сезон — декабрь следующего года.
"""
import asyncio
import datetime
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import test_intake_confirm as H  # noqa: E402

S = H.S
INTAKE = H.INTAKE
STAS, VLAD = "LAZAREV STANISLAV", "LAZAREV VLADISLAV"
CARD = "🆕 БРОНЬ\nсинтетическая карточка"
Y = datetime.date.today().year + 1


def parsed(ds, de, price="12 600"):
    return json.dumps({"model": "NMAX 155CC TEST 0001", "client": "Lazarev Stanislav", "date_start": ds,
                       "date_end": de, "date_start_iso": ds, "date_end_iso": de, "contacts": "+66 80 000 0000",
                       "delivery_url": "https://maps.app.goo.gl/test", "helmets": 1, "deposit_type": "паспорт",
                       "price_total": price}, ensure_ascii=False)


LOW = ("%d-05-10" % Y, "%d-05-17" % Y)
HIGH = ("%d-12-20" % Y, "%d-12-27" % Y)


class Claude(H.FakeClaude):
    def __init__(self, ds=LOW[0], de=LOW[1], price="12 600"):
        self.PARSED = parsed(ds, de, price)
        self.systems = []

    def quick(self, system, text, max_tokens=300, **kw):
        self.systems.append(system)
        return self.PARSED


class Door(H.FakeBridge):
    def __init__(self, avail=True, season="low", raises=None, **k):
        super().__init__(**k)
        self.avail, self.season, self.raises, self.quotes = avail, season, raises, []

    def quote_price(self, bike, date_start, date_end):
        self.quotes.append((bike, date_start, date_end))
        if self.raises is not None:
            raise self.raises
        return {"ok": True, "available": self.avail, "total": 12600, "day_price": 1800, "days": 7,
                "season": {"label": self.season}}


OCR_QUEUE = []


async def seq_ocr(photo_msg, chat_id, context, bridge):
    name, fid = OCR_QUEUE.pop(0)
    rec = {"file_id": fid, "ocr_status": "ok" if name else "failed", "ts": time.time(),
           "fields": {"full_name": name} if name else None}
    S._INTAKE_PASSPORT[chat_id] = rec
    return (bool(name), rec["fields"])


def run(bridge, claude, passport=STAS):
    """Фото паспорта до карточки, затем карточка — штатный порядок «Входящих»."""
    OCR_QUEUE[:] = [(passport, "f-1")]
    asyncio.run(S._handle_intake(H.Msg("", photo=True, mid=6001, reply=H.NOREPLY), H.Ctx(), bridge, claude))
    asyncio.run(S._handle_intake(H.Msg(CARD, mid=5100, reply=H.NOREPLY), H.Ctx(), bridge, claude))


class Base(unittest.TestCase):
    def setUp(self):
        os.environ["INTAKE_PASSPORT_STRICT"] = "1"
        os.environ["INTAKE_AUTOBOOK"] = "1"
        H.reset()
        S._INTAKE_DRAFTS.clear()
        S._IDN_SEEN.clear()
        S._IDN_PRE.clear()
        self._ocr, self._save = S._intake_passport_ocr, S._intake_passport_save_rec
        S._intake_passport_ocr, S._intake_passport_save_rec = seq_ocr, (lambda d, rec, bridge: None)

    def tearDown(self):
        os.environ.pop("INTAKE_PASSPORT_STRICT", None)
        os.environ.pop("INTAKE_AUTOBOOK", None)
        S._intake_passport_ocr, S._intake_passport_save_rec = self._ocr, self._save

    def d(self):
        return S._INTAKE_DRAFTS[INTAKE]

    def said(self, part):
        return any(part in t for t in H.texts())


class A_Autobook(Base):
    def test_all_conditions_book_once_without_yes(self):
        br, cl = Door(), Claude()
        run(br, cl)
        self.assertEqual(len(br.booked()), 1, H.texts())
        f = br.booked()[0][1]
        self.assertEqual(f["name"], STAS)
        self.assertIn("автобронь: согласовано 12 600 ฿", f["note"])
        self.assertEqual(br.quotes, [("NMAX 155CC TEST 0001", LOW[0], LOW[1])])
        self.assertEqual(self.d()["status"], "booked")
        self.assertTrue(self.said("Бронь записана автоматически"), H.texts())
        self.assertTrue(self.said("ставлю бронь сам"), H.texts())
        self.assertTrue(any("price_total" in s for s in cl.systems))

    def test_flag_off_keeps_yes(self):
        os.environ.pop("INTAKE_AUTOBOOK", None)
        br, cl = Door(), Claude()
        run(br, cl)
        self.assertEqual(br.booked(), [])
        self.assertEqual(br.quotes, [])
        self.assertTrue(self.said("Ставлю бронь? да / нет / правки"))
        self.assertFalse(self.said("Автобронь"))
        self.assertFalse(any("price_total" in s for s in cl.systems))      # прежний промпт байт-в-байт

    def test_refusals_name_the_reason_and_keep_yes(self):
        cases = [(dict(), dict(price=""), STAS, "нет согласованной стоимости", 0),
                 (dict(avail=False), dict(), STAS, "не свободен по двери цены", 1),
                 (dict(), dict(ds=HIGH[0], de=HIGH[1]), STAS, "высокий сезон 15.12–15.03", 0),
                 (dict(season="high"), dict(), STAS, "«высокий сезон»", 1),
                 (dict(), dict(), VLAD, "личность паспортом не установлена", 0),
                 (dict(raises=TimeoutError()), dict(), STAS, "дверь цены не ответила", 1)]
        for door_kw, cl_kw, passport, why, quotes in cases:
            self.setUp()
            br, cl = Door(**door_kw), Claude(**cl_kw)
            run(br, cl, passport)
            self.assertEqual(br.booked(), [], why)
            self.assertEqual(len(br.quotes), quotes, why)
            self.assertTrue(self.said("🤖 Автобронь не ставлю: " + why) or
                            any(why in t and "Автобронь не ставлю" in t for t in H.texts()), (why, H.texts()))
            self.assertEqual(self.d()["status"], "awaiting_approval", why)
            self.tearDown()

    def test_unknown_outcome_no_repeat(self):
        br = Door(reply=H.Boom("обрыв"))
        run(br, Claude())
        self.assertEqual(len(br.booked()), 1)
        self.assertEqual(self.d()["status"], "write_unknown")
        self.assertTrue(self.said("Исход записи брони неизвестен"), H.texts())


class B_Units(unittest.TestCase):
    def test_high_season_and_money(self):
        D = datetime.date
        self.assertTrue(S._ab_high_season(D(Y, 12, 10), D(Y, 12, 16)))
        self.assertTrue(S._ab_high_season(D(Y, 3, 1), D(Y, 3, 10)))
        self.assertFalse(S._ab_high_season(D(Y, 3, 15), D(Y, 3, 22)))
        self.assertFalse(S._ab_high_season(D(Y, 12, 1), D(Y, 12, 15)))
        self.assertEqual(S._ab_money("12 600 ฿"), 12600.0)
        self.assertEqual(S._ab_money("12,600 бат"), 12600.0)
        self.assertIsNone(S._ab_money(""))
        self.assertIsNone(S._ab_money("по договорённости"))
        self.assertIsNotNone(S.INTAKE_SYSTEM_AB)
        self.assertNotIn("price_total", S.INTAKE_SYSTEM)


if __name__ == "__main__":
    unittest.main(verbosity=1)
