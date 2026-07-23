#!/usr/bin/env python3
"""Дельта-ревизия мозга 12.07: KB_MASTER §3–4 (клиентский трек ночи 11–12.07 + PENDING)
+ синк docs/knowledge_base.md → Drive. Бэкап KB_MASTER = /tmp/kb_master_1207.txt."""
from bridge_client import BridgeClient

KB_MASTER_ID = "1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc"

with open("/tmp/kb_master_1207.txt", encoding="utf-8") as f:
    text = f.read()

ANCHOR3 = ("NEXT клиентского (осознанно отложен владельцем) = Фаза 3 "
           "(скормить прошлые диалоги с правилами) + вылизывание общения.")
BLOCK3 = """
- ⭐ 11–12.07 — ПРАЙС-БОТ В ПРОДЕ, ПОДТВЕРЖДЁН ЖИВЬЁМ (клиентский трек ночи; журнал = cowork_log):
  • price_sheet-СЕТКА по 12 моделям парка (c6d8a30): запрос «каталог/цены в целом» → полная сетка цен одним ответом.
  • ФОРМАТ ответа: карточка-на-байк + строка «низкий сезон до 31.10» (aae1ed2).
  • ДЕТЕКТ ШИРОКИЙ И ДЕТЕРМИНИРОВАННЫЙ (1ed85df): «каталог/цены-в-целом» → сетка; конкретная модель →
    точечный quote. КОРЕНЬ бага: модель-гард глушил сетку по ВСЕМУ окну диалога (модель, упомянутая
    ранее в диалоге, навсегда выключала сетку) — урок «LLM-детект юнитами не закрывается» в knowledge_base.
  • reconcile НА ПК авто-применяет out-of-band коммиты детей (6d8a3b1) — код, приехавший не из своей
    сессии, доезжает до живого демона сам (хвост развязки (2) из §4 частично закрыт этим механизмом).
  PENDING ПРАЙС-БОТА (двое, не блокеры прода):
  (а) XMAX в сетке «от 9900» = кап НОВОГО, а в капах есть СТАРЫЙ XMAX 8900. Read-only чек Лист1
      12.07 (fleet, 38 байков): XMAX в парке 10, из них 3 СТАРЫХ без «NEW» в имени — №17 BLUE 5773
      (2019), №6 GREEN 4248 (2020), №1 GREY 4246 (2019) → сетка «от 9900» ЗАВЫШАЕТ честный минимум
      (= 8900, кап старого). Нужна правка сетки («от 8900» либо две строки old/new) — решение
      владельца; код 12.07 не тронут.
  (б) финальный клиентский тест формата сетки с @samhold + ответ агенту @cryptopeppa —
      подтвердить живьём и закрыть."""

ANCHOR4 = ("канал Dispatch/Cowork). O3-площадка (ступень 1 в TEST_MODE) допиливается по ходу; "
           "боевой выкат отложен (Раздел 7).")
ADD4 = (" ⭐11–12.07: ПРАЙС-БОТ В ПРОДЕ, подтверждён живьём (сетка price_sheet 12 моделей c6d8a30 + "
        "формат карточка-на-байк aae1ed2 + детерминированный детект каталог↔модель 1ed85df + "
        "reconcile out-of-band коммитов 6d8a3b1 — детали в Разделе 3, КЛИЕНТСКИЙ ⭐11–12.07). "
        "PENDING: XMAX «от 9900» завышает минимум — в парке 3 старых XMAX под кап 8900 "
        "(чек Лист1 12.07), нужна правка сетки; финальный клиент-тест @samhold/@cryptopeppa.")

assert text.count(ANCHOR3) == 1, "anchor3 not unique"
assert text.count(ANCHOR4) == 1, "anchor4 not unique"
new = text.replace(ANCHOR3, ANCHOR3 + BLOCK3)
new = new.replace(ANCHOR4, ANCHOR4 + ADD4)
assert len(new) > len(text), "no growth"

c = BridgeClient()
w = c.write_doc(text=new, id=KB_MASTER_ID)
print("KB_MASTER write:", w.get("ok"), "old", len(text), "new", len(new))
if not w.get("ok"):
    print("FAIL:", w)
    raise SystemExit(1)

r = c._call("read_doc", id=KB_MASTER_ID)
back = r.get("text", "") if r.get("ok") else ""
print("verify read:", r.get("ok"), "len", len(back),
      "block3 in:", "ПРАЙС-БОТ В ПРОДЕ, ПОДТВЕРЖДЁН ЖИВЬЁМ" in back,
      "add4 in:", "нужна правка сетки; финальный клиент-тест" in back)

with open("docs/knowledge_base.md", encoding="utf-8") as f:
    kb = f.read()
w2 = c.write_doc(text=kb, name="knowledge_base")
print("knowledge_base sync:", w2.get("ok"), "len", len(kb))
r2 = c._call("read_doc", name="knowledge_base")
back2 = r2.get("text", "") if r2.get("ok") else ""
print("verify kb:", r2.get("ok"), "len", len(back2), "delta", len(back2) - len(kb),
      "lessons in:", "Уроки-классы дев-контура (ночь 11–12.07.2026)" in back2)
