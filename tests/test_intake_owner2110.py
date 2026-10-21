# -*- coding: utf-8 -*-
"""INTAKEOWNER2110 (21.10.2026): приём брони во «Входящих» — ручка INTAKE_PASSPORT_STRICT (Codex
TB-OWNER-2110-SPLINTER-INTAKE-REPAIR п.1–4; норма владельца 21.10: бронь только с распознанным паспортом, ФИО в D —
по паспорту).

Живой случай 21.10 22:28–22:47 Пхукет: «да» владельца реплаем на сводку ушло в мозг (splinter.log 15:47:21Z
«→ мозг: Да»), бронь не встала; карточка «Lazarev Stanislav» привязалась к паспорту Vladislav (последнее фото в буфере
чата); «да» принималось при «⚠️ Паспорт НЕ распознан»; два фото подряд — две строки «паспорта» под одним клиентом.

Случаи (стенд test_intake_confirm: мост, отправка и OCR — подделки; личности синтетические; сети, CRM и модели нет):
  R  маршрут: реплай владельца на сводку ждущей карточки — в приём брони (`intake_reply_to_card` → True, в bot.py
     проверка стоит ДО ветки «владелец → мозг»); посторонний реплай, без реплая, ручка выкл — False; «да» владельца
     реплаем — ровно одна запись с ФИО паспорта;
  I  личность: ФИО паспорта ≠ «Клиент» — записи нет, конфликт словами, «да» его не снимает; паспорт не распознан /
     не прислан — записи нет; дверь `_intake_booking_fields` сама бросает до билета; ручка выкл — прежнее имя;
  B  привязка: два паспорта до карточки — ни один не привязан; второй распознанный паспорт к той же карточке — не
     перезаписывает и не сохраняется; повтор того же события фото — один OCR, одна строка «паспорта»; старая карточка
     после записи второй брони не даёт.
"""
import asyncio
import inspect
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import test_intake_confirm as H  # noqa: E402  — стенд (подделки моста, отправки, OCR; память во временном каталоге)

S = H.S
INTAKE = H.INTAKE
OWNER = "turbophuket"
STAS, VLAD = "LAZAREV STANISLAV", "LAZAREV VLADISLAV"
CARD = "🆕 БРОНЬ\nсинтетическая карточка"


class Claude(H.FakeClaude):
    PARSED = ('{"model": "NMAX 155CC TEST 0001", "client": "Lazarev Stanislav", "date_start": "27-10-2026", '
              '"date_end": "03-11-2026", "date_start_iso": null, "date_end_iso": null, '
              '"contacts": "+66 80 000 0000", "delivery_url": "https://maps.app.goo.gl/test", '
              '"helmets": 1, "deposit_type": "паспорт"}')


OCR_QUEUE, OCR_CALLS, SAVES = [], [], []


async def seq_ocr(photo_msg, chat_id, context, bridge):
    name, fid = OCR_QUEUE.pop(0)
    OCR_CALLS.append(fid)
    rec = {"file_id": fid, "ocr_status": "ok" if name else "failed", "ts": time.time(),
           "fields": {"full_name": name} if name else None}
    S._INTAKE_PASSPORT[chat_id] = rec
    return (bool(name), rec["fields"])


def rec_save(d, rec, bridge):
    SAVES.append((d.get("client"), rec.get("file_id")))


def pp(name, fid="f-1", status="ok"):
    return {"file_id": fid, "ocr_status": status, "ts": time.time(), "fields": {"full_name": name} if name else None}


def owner_yes(bridge, mid=H.SUMMARY_MID):
    asyncio.run(S._handle_intake(H.Msg("да", uname=OWNER, reply=H.Reply(mid=mid)), H.Ctx(), bridge, Claude()))


def photo(bridge, mid):
    asyncio.run(S._handle_intake(H.Msg("", photo=True, mid=mid, reply=H.NOREPLY), H.Ctx(), bridge, Claude()))


def card(bridge, mid=5100):
    asyncio.run(S._handle_intake(H.Msg(CARD, mid=mid, reply=H.NOREPLY), H.Ctx(), bridge, Claude()))


class Base(unittest.TestCase):
    def setUp(self):
        os.environ["INTAKE_PASSPORT_STRICT"] = "1"
        H.reset()
        S._INTAKE_DRAFTS.clear()
        S._IDN_SEEN.clear()
        S._IDN_PRE.clear()
        del OCR_QUEUE[:], OCR_CALLS[:], SAVES[:]
        self._ocr, self._save = S._intake_passport_ocr, S._intake_passport_save_rec
        S._intake_passport_ocr, S._intake_passport_save_rec = seq_ocr, rec_save

    def tearDown(self):
        os.environ.pop("INTAKE_PASSPORT_STRICT", None)
        S._intake_passport_ocr, S._intake_passport_save_rec = self._ocr, self._save

    def waiting(self, client="Lazarev Stanislav", passport=None, **kw):
        S._INTAKE_DRAFTS[INTAKE] = H.draft(client=client, passport_ocr=passport, **kw)
        return S._INTAKE_DRAFTS[INTAKE]


class R_Route(Base):
    def test_owner_reply_on_summary_goes_to_intake(self):
        self.waiting(passport=pp(STAS))
        m = H.Msg("да", uname=OWNER, reply=H.Reply(mid=H.SUMMARY_MID))
        m.chat_id = INTAKE
        self.assertTrue(S.intake_reply_to_card(m))

    def test_foreign_reply_no_reply_flag_off_stay_old(self):
        self.waiting(passport=pp(STAS))
        self.assertFalse(S.intake_reply_to_card(H.Msg("да", uname=OWNER, reply=H.Reply(mid=777))))
        self.assertFalse(S.intake_reply_to_card(H.Msg("да", uname=OWNER, reply=H.NOREPLY)))
        os.environ.pop("INTAKE_PASSPORT_STRICT", None)
        self.assertFalse(S.intake_reply_to_card(H.Msg("да", uname=OWNER, reply=H.Reply(mid=H.SUMMARY_MID))))

    def test_bot_checks_card_reply_before_brain(self):
        src = open(os.path.join(os.path.dirname(HERE), "bot.py"), encoding="utf-8").read()
        i = src.index("if splinter.intake_reply_to_card(msg):")
        j = src.index("# Владелец обращается к Splinter напрямую (тег/ответ/ждём ответа) → диалог-мозг")
        self.assertLess(i, j)

    def test_owner_yes_books_once_with_passport_name(self):
        self.waiting(passport=pp(STAS))
        br = H.FakeBridge()
        owner_yes(br)
        self.assertEqual(len(br.booked()), 1, H.texts())
        self.assertEqual(br.booked()[0][1]["name"], STAS)
        self.assertEqual(H.status(), "booked")
        owner_yes(br)                                    # старая карточка / повтор «да» — второй брони нет
        self.assertEqual(len(br.booked()), 1)


class I_Identity(Base):
    def test_conflict_blocks_and_yes_does_not_lift(self):
        self.waiting(passport=pp(VLAD))
        br = H.FakeBridge()
        owner_yes(br)
        owner_yes(br)
        self.assertEqual(br.booked(), [])
        self.assertEqual(br.calls, [], "до билета и сети")
        self.assertTrue(any("не совпадает" in t and VLAD in t for t in H.texts()), H.texts())
        self.assertEqual(H.status(), "awaiting_approval")

    def test_not_recognized_or_missing_blocks(self):
        for passport, photo_flag in ((pp(None, status="failed"), True), (None, False), (pp(STAS), False)):
            H.reset()
            self.waiting(passport=passport, passport_photo=photo_flag)
            br = H.FakeBridge()
            owner_yes(br)
            self.assertEqual(br.booked(), [], (passport, photo_flag))
            self.assertTrue(any("нет распознанного паспорта" in t for t in H.texts()), H.texts())

    def test_door_itself_refuses_and_names_by_passport(self):
        d = self.waiting(passport=pp(VLAD))
        with self.assertRaises(S.IntakeIdentityError):
            S._intake_booking_fields(d)
        d = self.waiting(passport=pp(STAS))
        self.assertEqual(S._intake_booking_fields(d)["name"], STAS)
        d = self.waiting(client="Стас", passport=pp(STAS))           # прозвище — конфликт, а не догадка
        self.assertFalse(S._intake_identity(d)[0])
        d = self.waiting(client="Лазарев Станислав", passport=pp(STAS))   # кириллица карточки — транслитерацией
        self.assertTrue(S._intake_identity(d)[0])
        os.environ.pop("INTAKE_PASSPORT_STRICT", None)
        d = self.waiting(passport=pp(VLAD))
        self.assertEqual(S._intake_booking_fields(d)["name"], "Lazarev Stanislav")   # ручка выкл — прежнее имя
        self.assertNotIn(S.IDN_CONFLICT[:20], S._intake_summary(d, "?", "ok"))


class B_Binding(Base):
    def test_two_passports_before_card_bind_none(self):
        br = H.FakeBridge()
        OCR_QUEUE[:] = [(STAS, "f-s"), (VLAD, "f-v")]
        photo(br, 6001)
        photo(br, 6002)
        card(br)
        d = S._INTAKE_DRAFTS[INTAKE]
        self.assertFalse(d.get("passport_photo"), d)
        self.assertEqual(SAVES, [])
        self.assertTrue(any("до карточки пришло 2 фото" in t for t in H.texts()), H.texts())
        d["status"] = "awaiting_approval"
        owner_yes(br, mid=5100)
        self.assertEqual(br.booked(), [])

    def test_one_passport_before_card_binds_and_saves_once(self):
        br = H.FakeBridge()
        OCR_QUEUE[:] = [(STAS, "f-s")]
        photo(br, 6001)
        card(br)
        d = S._INTAKE_DRAFTS[INTAKE]
        self.assertTrue(d.get("passport_photo"))
        self.assertEqual(d.get("client"), STAS)
        self.assertEqual(SAVES, [(STAS, "f-s")])

    def test_second_passport_after_card_not_rebound_not_saved(self):
        br = H.FakeBridge()
        OCR_QUEUE[:] = [(STAS, "f-s"), (VLAD, "f-v")]
        card(br)
        photo(br, 6001)
        photo(br, 6002)
        d = S._INTAKE_DRAFTS[INTAKE]
        self.assertEqual((d["passport_ocr"] or {}).get("file_id"), "f-s")
        self.assertEqual(SAVES, [(STAS, "f-s")])
        self.assertTrue(any("уже привязан распознанный паспорт" in t for t in H.texts()), H.texts())

    def test_wrong_passport_after_card_not_saved_under_client(self):
        br = H.FakeBridge()
        OCR_QUEUE[:] = [(VLAD, "f-v")]
        card(br)
        photo(br, 6001)
        self.assertEqual(SAVES, [])
        self.assertTrue(any("не совпадает" in t for t in H.texts()), H.texts())

    def test_repeat_event_one_ocr_one_row(self):
        br = H.FakeBridge()
        OCR_QUEUE[:] = [(STAS, "f-s")]
        card(br)
        photo(br, 6001)
        photo(br, 6001)
        self.assertEqual(OCR_CALLS, ["f-s"])
        self.assertEqual(SAVES, [(STAS, "f-s")])


class Z_Source(unittest.TestCase):
    def test_three_write_paths_guarded(self):
        src = inspect.getsource(S)
        # AUTOBOOK2210: четвёртый путь — автобронь; ворота личности у него — `_autobook_check` и сама дверь полей
        self.assertEqual(src.count("bridge.create_booking("), 4)
        self.assertIn("_intake_identity(d)", inspect.getsource(S._autobook_check))
        self.assertIn("_intake_booking_fields(d)", inspect.getsource(S._intake_autobook_write))
        for fn in (S._intake_reply_strict,):
            self.assertIn("_intake_identity(d)", inspect.getsource(fn))
        self.assertIn('written({"error": "identity_not_proven"})', src)


if __name__ == "__main__":
    unittest.main(verbosity=1)
