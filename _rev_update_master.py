#!/usr/bin/env python3
"""Ревизия 16.07: правки KB_MASTER (§3 +⭐13-15.07, §4 WA-фронт, §5 роадмап-архив, §6 якорь)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=90)

# Читаем KB_MASTER
r = c._call("read_doc", name="index")
assert r.get("ok"), f"read index failed: {r}"
txt = r["text"]
print(f"KB_MASTER: {len(txt)} chars")

# ───────────────────────────────────────────────
# ПРАВКА 1: §3 — вставить блок ⭐13-15.07
# (перед строкой "СРЕДА «РУЛЮ С ТЕЛЕФОНА»")
# ───────────────────────────────────────────────
NEW_STAR_BLOCK = """
- ⭐ 13–15.07 — УСКОРЕНИЕ ЦЕПЕЙ + WA-ФРОНТ + ИНЦИДЕНТ 2478 (классы-к-фиксу):
  • УСКОРЕНИЕ ЦЕПЕЙ (2 коммита, 13.07): (1) EXECUTOR_MODEL=sonnet (afd18d2) — модель исполнителя шагов декомпозера и одиночных «тз:» в .env (думанье: планировщик/самопочинка/адаптация/куратор — прежний ORCH_MODEL; откат = убрать переменную + рестарт). (2) СЕЛЕКТИВНЫЙ ГЕЙТ промежуточных шагов (d288947, флаг GATE_STEP_SELECTIVE): промежуточный [шаг i/N] с i < N → smoke + затронутые тесты вместо полного сьюта; последний шаг, одиночки, --final — полный сьют; fail-safe: нельзя определить → полный. ч.3 (9c3c3e7, 15.07) расширяет на одиночки (GATE_SINGLE_SELECTIVE). Гейты 90→91 зелёные.
  • «СТАТУС» = ЕДИНАЯ СВОДКА СИСТЕМЫ (087d26b + 6e4007b, 13.07): _queue_snapshot одним lane=all; секции: ⚙️ активные цепи (шаг i/N) + 🧑 needs_approval + 👁 ревизор; призраки VPS-цепей (pcloc-dec-done без незакрытых шагов) убраны; «🟢 ТИХО: в работе 0, ждёт тебя 0» — явный сигнал завершения.
  • GUARD-КАРТОЧКИ → ИНБОКС 1160 (47c8979, 13.07): pretool_guard шлёт в тему-инбокс HQ 1160 (фолбэк → личка); devbot слушает 1160 («да/нет N» тем-агностичны); дедуп ×N правкой В ТОМ ЖЕ чате. Маршрут «ждут владельца» единый.
  • WA-0 WEBHOOK В ПРОДЕ (49c90d3 14.07 → 534478f 15.07 → 88de57e 15.07): приёмник WhatsApp Cloud API (тонкий транзит: GET-верификация + POST-лог; wa-webhook.service на Caddy/localhost:8084; 360dialog + Twilio-совместимый путь + v1-нормализация). Фикс класса «однопоточный Flask виснет намертво» (534478f, инцидент 15.07 → threaded=True). Новое направление WA-ФРОНТ — Раздел 4.
  • ЗОНЫ ДОСТАВКИ Bridge (86de758, 14.07): экшены delivery_zones_list / delivery_zones_init + тесты.
  • ПЛАШКА ПРОДОЛЖЕНИЯ (b7e95a9, 15.07): в done/failed-карточках devbot — «→ [куратор]»/«→ след.шаг X».
  • КУРАТОР УТОЧНЁН (15.07): (а) e0e0b9e CURATOR_SCOPE — done без git-коммита → мимо куратора (read-only результат не курируется; fail-safe = как было); (б) f744023 — дедуп followup-проверок окном 30 мин (deploy-событие исключено из курации); (в) ee738ef — реестр проверенных фактов (разрыв петли повторных диагностик).
  • ДОКТРИНА УТОЧНЕНА (ec15779, 15.07): рестарт/старт своих сервисов (splinter/orchestrator-daemon/wa-webhook) = ОРАНЖЕВЫЙ ЦИКЛ (гейт + бэкап + отчёт), НЕ NEEDS_APPROVAL — это техническая операция, «да» Филиппа не нужно.
  • ОРАНЖЕВЫЙ ЦИКЛ CLASP REDEPLOY (1caaab5, 15.07): Termux-сессия деплоит Bridge без «да» Филиппа — оранжевый протокол с бэкапом версии и ping-тестом.
  • ИНЦИДЕНТ 2478 — КЛАСС-К-ФИКСУ (15.07): ТО байка 2478 — масло накачали из vision-нарратива («было на 2450 км»), приняв за одометр-команду. (А) Класс A ЗАКРЫТ: d66059c — масло-нарратив «было на N» парсится отдельно, не трактуется как km-правка одометра. Инварианты v1: d73a25d (6 непрерывных инвариантов живых данных) + 61b7c44 (предложения инвариантов класса 2478 в stdout). (Б) ГАРД Б — В ХВОСТАХ: коррекция прошла в обход инварианта «одометр растёт» — боковой маршрут не закрыт (разблокирует отдельная задача «инвариант Б, все пути»).

"""

SREДА_ANCHOR = "\nСРЕДА «РУЛЮ С ТЕЛЕФОНА, ВСЁ В МОЗГ»:"
assert SREДА_ANCHOR in txt, "Anchor СРЕДА not found!"
txt = txt.replace(SREДА_ANCHOR, NEW_STAR_BLOCK + SREДА_ANCHOR, 1)
print("§3 new block inserted ✓")

# ───────────────────────────────────────────────
# ПРАВКА 2: §4 — добавить WA-ФРОНТ как направление
# (после блока КЛИЕНТСКИЙ ПУТЬ, перед КЛЮЧЕВОЙ СВЯЗКОЙ)
# ───────────────────────────────────────────────
WA_DIRECTION = """\nWA-ФРОНТ (WhatsApp, новое направление с 14.07.2026): wa-webhook.service принимает события WhatsApp Cloud API (360dialog). Текущее состояние: тонкий транзит (верификация + лог). Следующий кирпич = роутинг входящих WA-сообщений в клиентский контур (параллельно Telegram userbot; реализация после дозревания O3/Dispatch).\n"""

WA_ANCHOR = "\n🔑 КЛЮЧЕВАЯ СВЯЗКА"
assert WA_ANCHOR in txt, "Anchor КЛЮЧЕВАЯ СВЯЗКА not found!"
txt = txt.replace(WA_ANCHOR, WA_DIRECTION + WA_ANCHOR, 1)
print("§4 WA-direction inserted ✓")

# ───────────────────────────────────────────────
# ПРАВКА 3: §5 — упростить pointer roadmap_master
# ───────────────────────────────────────────────
OLD_ROADMAP = """- KB_ROADMAP_MASTER (ключ `roadmap_master`, id 1Z70Epg…) — расширенный backlog P1-P11 (под этой картой; живой
  регистрированный dok). АВТОРИТЕТ ПО ОСИ O1-O4 = РАЗДЕЛ 4 этой карты; roadmap_master = детальный план-лист
  локальных задач. (Имя «KB_ROADMAP_v2» из прежней навигации не существует в манифесте — единственный
  зарегистрированный роадмап = roadmap_master.) Эфемерные/слитые источники — в подпапке Brain/_archive."""

NEW_ROADMAP = "- KB_ROADMAP_MASTER — В АРХИВЕ (_archive; перемещён ревизией 16.07). Авторитет по оси O1-O5 = РАЗДЕЛ 4 этой карты. Хвосты → Раздел 7."

# Попробуем точное совпадение; если нет — попробуем частичное
if OLD_ROADMAP in txt:
    txt = txt.replace(OLD_ROADMAP, NEW_ROADMAP, 1)
    print("§5 roadmap_master pointer simplified ✓ (exact match)")
else:
    # Ищем по частичному ключу
    key = "KB_ROADMAP_MASTER (ключ `roadmap_master`"
    if key in txt:
        # Найдём и заменим от начала строки до конца абзаца
        start = txt.find("- " + key)
        if start == -1:
            start = txt.find(key)
        end = txt.find("\n- ", start + 1)
        if end == -1:
            end = txt.find("\n\n", start)
        if end > start:
            old_chunk = txt[start:end]
            print(f"Found roadmap chunk ({len(old_chunk)} chars): {old_chunk[:100]!r}...")
            txt = txt[:start] + NEW_ROADMAP + txt[end:]
            print("§5 roadmap_master pointer simplified ✓ (partial match)")
        else:
            print("WARNING: could not bound roadmap chunk")
    else:
        print("WARNING: roadmap_master anchor not found in text")

# ───────────────────────────────────────────────
# ПРАВКА 4: §6 — обновить дату ревизии
# ───────────────────────────────────────────────
OLD_ANCHOR = "ЯКОРЬ: ревизии проведены 07.07.2026 утром (веха O4-ст2 + клиентский контур) и 07.07.2026 ВЕЧЕРОМ (веха: ЛЕСТНИЦА О4 СТ1–СТ4 ЗАВЕРШЕНА на VPS-полосе); следующая ПЛАНОВАЯ НЕ ПОЗЖЕ 21.07.2026"
NEW_ANCHOR = "ЯКОРЬ: последние ревизии — 07.07.2026 (веха лестница ст1–ст4 VPS) и 16.07.2026 (рубеж ≤21.07 + расхождения штаба); следующая ПЛАНОВАЯ НЕ ПОЗЖЕ 30.07.2026"

if OLD_ANCHOR in txt:
    txt = txt.replace(OLD_ANCHOR, NEW_ANCHOR, 1)
    print("§6 ЯКОРЬ updated ✓")
else:
    print(f"WARNING: ЯКОРЬ anchor not found (try partial search)")
    key2 = "следующая ПЛАНОВАЯ НЕ ПОЗЖЕ 21.07.2026"
    if key2 in txt:
        txt = txt.replace(key2, "следующая ПЛАНОВАЯ НЕ ПОЗЖЕ 30.07.2026", 1)
        print("§6 date updated (partial) ✓")

print(f"New size: {len(txt)} chars")

# Сохраняем во временный файл на случай сбоя записи
with open("/tmp/kb_master_new.txt", "w") as f:
    f.write(txt)
print("Saved to /tmp/kb_master_new.txt")

# Записываем через POST
w = c.write_doc(name="index", text=txt)
if w.get("ok"):
    print(f"KB_MASTER updated OK ({len(txt)} chars)")
else:
    print(f"FAILED: {w}")
