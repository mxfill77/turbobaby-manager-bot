#!/usr/bin/env python3
"""Ревизия 08.07: KB_ROADMAP_MASTER — блок «АКТУАЛИЗАЦИЯ 08.07.2026» сверху (после шапки-назначения),
write_doc(name=roadmap_master) + post-write verify. Зона зелёная (живой Brain-док)."""
import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient

SNAP = "/tmp/KB_ROADMAP_snapshot_20260708b.md"
with open(SNAP, encoding="utf-8") as f:
    text = f.read()
orig_len = len(text)

ANCHOR = ("────────────────────────────────────────────────────────\n"
          "АКТУАЛИЗАЦИЯ 07.07.2026 ВЕЧЕР")
BLOCK = """────────────────────────────────────────────────────────
АКТУАЛИЗАЦИЯ 08.07.2026 (РЕВИЗИЯ по вехе: O3 ЗАВЕРШЁН — круг аренды замкнут) — ЧИТАТЬ ПЕРВЫМ
────────────────────────────────────────────────────────
АВТОРИТЕТ ПО ГЛАВНОЙ ОСИ = KB_MASTER Раздел 4 (актуализирован тем же днём). Здесь — сверка backlog.
- ГОРИЗОНТ ОСИ ВЫБРАН И ПРОЙДЕН: владелец выбрал (в) операции O3 — и O3 куски 1–3 ЗАВЕРШЕНЫ ЗА ДЕНЬ,
  КРУГ АРЕНДЫ бронь→выдача→приём В ПРОДЕ: O3-1 кнопка «Бронь» (ПК-репо, живой экзамен PASS) +
  O3-2a/b/c (Booking.js конфликт-чек/даты be09494 + INTAKE + мост userbot→группа) + O3-3a ВЫДАЧА
  (afafac5: handover → карточка 🏍 → activateBooking) + O3-3b ПРИЁМ (554eaad+8935a77: return →
  карточка 📥 → close_booking). Bridge прод за день @65→@69.
- САГА ГЕЙТА ОДОМЕТРА (маятник row705→1268) закрыта за день: инцидент row705 (fail-open пустого Q,
  живая аренда закрыта смоком, восстановлена temp-деплоем) → 5a5092b fail-closed (km_required /
  odo_unverifiable) → over-closed 1268 (живой Q = строка «N Km, дата») → фикс №2 25ef8e0
  bookingParseOdo_ (парсер живого формата). КРУГ ЗАМКНУТ смоком read-only row700/701.
  ДВА УРОКА-КЛАССА в CLAUDE.md: write-смоки только на ТЕСТ-сущностях по отдельным «да»;
  моки колонок листа = живой формат листа.
- O4 фоном: фикс КОРНЯ повторных сирот 138/146 (0501f42, claim-verify) + durable-слой Bridge против
  intermittent 404 (4f892d7). Settings-дрейф clasp ask→allow откачен к git-истине (пойман красным
  гейтом; позже роль-развод permissions de36412: интерактив владельца = allow, headless = строгий).
  Упрощение ПК 2fd1937 (авто-применение кода по диффу). Рамка штаба 08.07 принята владельцем.
- ОТКРЫТЫЕ ХВОСТЫ ДНЯ (полный список KB_MASTER Раздел 7): функциональные первые живые ВЫДАЧА/ПРИЁМ
  на реальном handover/return (+ удалить руками тест-строку CRM 1268); дожим сквозного экзамена 6/6 +
  доработка 2.1 автосбор гео/паспорта; пометка «(повтор)» на клон-карточках; gate-алерты только на
  финальном прогоне; обкатка думателей/adjust/finish — ждёт естественных провалов.
- СЛЕДУЮЩИЙ ГОРИЗОНТ O3 = 3c ДЕПОЗИТ↔БРОНЬ: booking_id в транзакции депозита, возврат депозита
  при закрытии аренды.

"""
n = text.count(ANCHOR)
if n != 1:
    print(f"ANCHOR FAIL: {n} вхождений — СТОП")
    sys.exit(1)
text = text.replace(ANCHOR, BLOCK + ANCHOR)
new_len = len(text)
print(f"len {orig_len} → {new_len} (+{new_len - orig_len})")

c = BridgeClient()
w = c.write_doc(text=text, name="roadmap_master")
if not w.get("ok"):
    print("WRITE FAIL:", w)
    sys.exit(1)
print("write_doc OK")

r = c._call("read_doc", name="roadmap_master")
if not r.get("ok"):
    print("VERIFY READ FAIL:", r)
    sys.exit(1)
back = r.get("text", "")
markers = ["АКТУАЛИЗАЦИЯ 08.07.2026 (РЕВИЗИЯ по вехе: O3 ЗАВЕРШЁН", "bookingParseOdo_",
           "СЛЕДУЮЩИЙ ГОРИЗОНТ O3 = 3c ДЕПОЗИТ↔БРОНЬ"]
missing = [m for m in markers if m not in back]
print(f"post-write verify: len={len(back)} vs {new_len} {'MATCH' if len(back) == new_len else 'MISMATCH'}; "
      f"markers missing={missing or 'нет'}")
if len(back) != new_len or missing:
    sys.exit(1)
print("VERIFIED: KB_ROADMAP_MASTER обновлён и сверен")
