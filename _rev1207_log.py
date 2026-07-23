#!/usr/bin/env python3
"""Финальный лог дельта-ревизии 12.07: cc_log DONE + пульс одной операцией."""
from datetime import datetime, timezone
from bridge_client import BridgeClient
from cclog import _insert_under_vrezka

ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
line = (f"DONE {ts} UTC (headless, дельта-ревизия мозга): ночь 11–12.07 внесена в мозг. "
        "KB_MASTER §3 КЛИЕНТСКИЙ + блок ⭐11–12.07: прайс-бот в проде, подтверждён живьём — сетка price_sheet "
        "12 моделей (c6d8a30), формат карточка-на-байк + «низкий сезон до 31.10» (aae1ed2), детерминированный "
        "детект каталог↔модель (1ed85df, корень: модель-гард глушил сетку по всему окну диалога), reconcile "
        "out-of-band коммитов (6d8a3b1); §4 — указатель. PENDING зафиксированы: (а) XMAX «от 9900» — read-only "
        "чек Лист1 СДЕЛАН: XMAX в парке 10, СТАРЫХ 3 (№17 BLUE 5773/2019, №6 GREEN 4248/2020, №1 GREY 4246/2019) "
        "→ сетка ЗАВЫШАЕТ минимум, честный мин 8900 (кап старого), нужна правка сетки — решение владельца; "
        "(б) финальный клиент-тест @samhold + ответ @cryptopeppa. knowledge_base + раздел «Уроки-классы "
        "дев-контура (ночь 11–12.07)»: LLM-детект юнитами не закрывается — только живой прогон, golden = "
        "дословные фразы клиентов; короткие алиасы моделей в claude -p дают 404 — полные id либо нормализация "
        "на импорте (ПК b18ad08); load_dotenv override=False не перебивает застрявший env демонов; ТЗ для "
        "CC/Cowork — нейтральная лексика (2 ложных фильтра за ночь); devbot: зелёные команды только короткими "
        "сообщениями, префиксы приоритетны (e2b5c8b). Синк verify ok: KB_MASTER 63348→65171, knowledge_base "
        "delta 0; commit 89c53c2 запушен, гейт 80/80. Код не тронут (read-only + доки). "
        "Хвосты: решение по XMAX-сетке; клиент-тест формата.")

PULSE = (f"{ts} | 🟢 | дельта-ревизия мозга 11–12.07 внесена: KB_MASTER §3–4 (прайс-бот в проде + PENDING) и "
         "knowledge_base (уроки ночи), commit 89c53c2, гейт 80/80 | жду решения по XMAX-сетке: в парке 3 старых "
         "XMAX под кап 8900, «от 9900» завышает | детали→cc_log DONE 12.07 «дельта-ревизия мозга»")

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL — не пишу:", r)
    raise SystemExit(1)
new = _insert_under_vrezka(r.get("text", ""), line)
w = c.write_doc(text=new, name="cc_log")
print("cc_log:", w.get("ok"))
wp = c.write_doc(text=PULSE, name="pulse")
print("pulse:", wp.get("ok"))
if not (w.get("ok") and wp.get("ok")):
    raise SystemExit(1)
